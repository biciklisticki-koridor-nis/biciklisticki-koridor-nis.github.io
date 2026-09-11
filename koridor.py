#!/usr/bin/env python3
"""Zajednička geometrija koridora — osa, kilometraža, uzorci, deonice.

Koridor nije jedna linija nego tri paralelne staze na razmaku od ~17 m:
biciklistička i pešačke na gornjem i donjem bedemu. Svaka analiza koja se
prikazuje po kilometru mora da ih smesti na *istu* km-osu, inače poredi
neuporedive tačke — staze imaju različite dužine i različite početke.

Referentna osa je najduži lanac tipa `bici` iz staze_mreza.geojson
(convert.py ga označava sa `uloga: "osa"`). Svaka tačka svake staze dobija
km projekcijom na tu osu; tačke dalje od PROJ_MAX_M (prilazi naseljima,
rampe) ispadaju — nisu deo koridora.

Modul drži samo ono što je zajedničko za više analiza. Sve što je specifično
za jednu analizu (CHM, sunce, putevi) ostaje u njenom skriptu.
"""
import hashlib
import json
import math
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
MREZA_FILE = os.path.join(ROOT, "data", "staze_mreza.geojson")
DEONICE_FILE = os.path.join(ROOT, "data", "deonice.geojson")

STAZE = [
    ("bici",           "Biciklistička staza"),
    ("pesacki_gornji", "Pešačka staza — gornji bedem"),
    ("pesacki_donji",  "Pešačka staza — donji bedem"),
]

STEP_M = 10.0            # korak uzorkovanja duž staze
PROJ_MAX_M = 40.0        # dalje od ose = prilaz, ne deo koridora

LAT0 = 43.315            # centar trase — za metar/stepen i solarne formule
LON0 = 21.92
M_PER_DEG_LAT = 111320.0
M_PER_DEG_LON = M_PER_DEG_LAT * math.cos(math.radians(LAT0))


def load_mreza():
    """Vraća (osa_coords, {tip: [lanac, ...]}) iz staze_mreza.geojson."""
    with open(MREZA_FILE) as f:
        gj = json.load(f)
    axis = None
    chains = {tip: [] for tip, _ in STAZE}
    for feat in gj["features"]:
        p = feat["properties"]
        coords = feat["geometry"]["coordinates"]
        if p["uloga"] == "osa":
            axis = coords
        elif p["tip"] in chains and p["tip"] != "bici":
            chains[p["tip"]].append(coords)
    if axis is None:
        raise SystemExit("! staze_mreza.geojson nema lanac sa uloga=\"osa\"")
    chains["bici"] = [axis]   # krakovi biciklističke mreže nisu deo koridora
    return axis, chains


def resample_line(coords, step_m=STEP_M):
    """Tačke na svakih step_m duž linije, sa kumulativnom dužinom u metrima."""
    out = []
    acc = 0.0
    next_m = 0.0
    for (lo1, la1), (lo2, la2) in zip(
            [(c[0], c[1]) for c in coords[:-1]],
            [(c[0], c[1]) for c in coords[1:]]):
        dx = (lo2 - lo1) * M_PER_DEG_LON
        dy = (la2 - la1) * M_PER_DEG_LAT
        seg = math.hypot(dx, dy)
        while seg > 0 and next_m <= acc + seg:
            f = (next_m - acc) / seg
            out.append((lo1 + (lo2 - lo1) * f, la1 + (la2 - la1) * f, next_m))
            next_m += STEP_M
        acc += seg
    return out


def axis_km(axis):
    """Ukupna dužina referentne ose u kilometrima."""
    return resample_line(axis)[-1][2] / 1000.0


def build_samples(axis, chains, verbose=True):
    """Uzorci po stazi, svaki sa km projektovanim na referentnu osu.

    Zajednička km-osa je jedino što tri staze čini uporedivim.
    """
    axis_pts = resample_line(axis)
    cell = PROJ_MAX_M
    grid = {}
    for lon, lat, m in axis_pts:
        x, y = lon * M_PER_DEG_LON, lat * M_PER_DEG_LAT
        grid.setdefault((int(x // cell), int(y // cell)), []).append((x, y, m))

    def project_km(lon, lat):
        x, y = lon * M_PER_DEG_LON, lat * M_PER_DEG_LAT
        cx, cy = int(x // cell), int(y // cell)
        best, best_m = PROJ_MAX_M, None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for px, py, m in grid.get((cx + dx, cy + dy), ()):
                    d = math.hypot(px - x, py - y)
                    if d < best:
                        best, best_m = d, m
        return best_m

    by_tip = {}
    for tip, _ in STAZE:
        samples = []
        dropped = 0
        for ci, ch in enumerate(chains[tip]):
            for lon, lat, _ in resample_line(ch):
                m = project_km(lon, lat)
                if m is None:
                    dropped += 1
                    continue
                samples.append({"km": m / 1000.0, "lon": lon, "lat": lat,
                                "chain": ci})
        samples.sort(key=lambda s: s["km"])
        by_tip[tip] = samples
        if verbose:
            extra = f", {dropped} van koridora" if dropped else ""
            print(f"  {tip}: {len(samples)} tačaka{extra}")
    return by_tip


def samples_hash(samples):
    """Otisak skupa uzoraka — za invalidaciju keševa vezanih za geometriju."""
    h = hashlib.sha1()
    for s in samples:
        h.update(f"{s['km']:.3f},{s['lat']:.6f},{s['lon']:.6f}|".encode())
    return h.hexdigest()[:16]


def _point_in_poly(lon, lat, ring):
    """Ray-casting test (isti pristup kao classify_deonica u convert.py)."""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def assign_deonice(samples):
    """Deonica preko point-in-polygon testa na meta_deonice poligonima.

    Tačke van svih poligona nasleđuju deonicu prethodne tačke duž trase
    (isti smoothing princip kao u convert.py).
    """
    with open(DEONICE_FILE) as f:
        deonice = json.load(f)
    polys = [(feat["properties"]["name"], feat["geometry"]["coordinates"][0])
             for feat in deonice["features"]]
    last = None
    for s in samples:
        name = next((n for n, ring in polys
                     if _point_in_poly(s["lon"], s["lat"], ring)), None)
        if name is None:
            name = last
        s["deonica"] = name
        last = name
    # vodeće tačke pre prvog pogotka
    first = next((s["deonica"] for s in samples if s["deonica"]), None)
    for s in samples:
        if s["deonica"] is None:
            s["deonica"] = first
        else:
            break


def deonica_order(by_tip):
    """Redosled deonica po kilometraži referentne ose (bici prva)."""
    order = []
    for s in by_tip["bici"]:
        if s["deonica"] not in order:
            order.append(s["deonica"])
    for samples in by_tip.values():
        for s in samples:
            if s["deonica"] not in order:
                order.append(s["deonica"])
    return order


def merc_xy(lon, lat):
    """EPSG:3857 — za rad sa rasterima (CHM je u web merkatoru)."""
    R = 6378137.0
    return (math.radians(lon) * R,
            R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def planar_xy(lon, lat):
    """Lokalna ravan u metrima — za rastojanja unutar koridora."""
    return lon * M_PER_DEG_LON, lat * M_PER_DEG_LAT


def prepare():
    """Osa + uzorci po stazi, sa deonicama i njihovim redosledom.

    Zajednički prvi korak svake analize po kilometru.
    """
    axis, chains = load_mreza()
    by_tip = build_samples(axis, chains)
    for samples in by_tip.values():
        assign_deonice(samples)
    return axis, by_tip, deonica_order(by_tip)
