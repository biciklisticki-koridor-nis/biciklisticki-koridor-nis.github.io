#!/usr/bin/env python3
"""Izloženost buci duž koridora (analiza 9.2).

Buka je prostorna, pa se modelira po tački. Svaki segment puta iz
OpenStreetMap-a (preko Overpass API-ja) je niz nekoherentnih tačkastih izvora
jačine po klasi puta, energija opada sa 1/d², a zbir preko svih segmenata u
krugu od 300 m daje relativnu izloženost tačke. Integral tačkastih izvora duž
linije reprodukuje ponašanje linijskog izvora (−10·log10 d).

Kvalitet vazduha je bio u ovom modulu dok je dolazio iz CAMS-a i bio jedan broj
za ceo koridor. Sada dolazi sa mernih stanica i ima svoju prostornu logiku, pa
živi u vazduh.py.

Indeks buke NIJE u decibelima. Nema nijednog merenja duž keja; kalibracija
bi bila lažna preciznost. Indeks je 0–100 relativno na sam koridor, gde je
100 njegova najizloženija tačka. Rangira deonice — ne tvrdi koliko je glasno.

Vegetacija namerno NE ulazi u model. Drvored zaklanja pogled na saobraćaj
snažno, ali zvuk slabo (red veličine 1–3 dB na 10 m gustog pojasa); ubaciti
je u indeks značilo bi preuveličati efekat koji se čuje.

Izvor: OpenStreetMap (ODbL).
"""
import hashlib
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

from koridor import (DEONICE_FILE, MREZA_FILE, ROOT, STAZE, axis_km,
                     planar_xy, prepare, samples_hash)

OUT_FILE = os.path.join(ROOT, "data", "buka.json")
CACHE_DIR = os.path.join(ROOT, "data", ".cache", "noise")

NOISE_SCHEMA = 2

# ---------- buka ----------

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
BBOX_PAD_DEG = 0.005          # ~400 m margine oko ose
SEARCH_R_M = 300.0            # dalje od ovoga doprinos je zanemarljiv
D_MIN_M = 15.0                # ne dozvoli singularitet kad staza dodiruje put

# Relativna jačina izvora po klasi puta. Rang, ne dB — odnos protoka i brzine
# između klasa, kalibrisan na to da autoput nosi red veličine više energije
# od stambene ulice.
ROAD_W = {
    "motorway": 1.00, "motorway_link": 0.55,
    "trunk": 0.85, "trunk_link": 0.45,
    "primary": 0.70, "primary_link": 0.35,
    "secondary": 0.50, "secondary_link": 0.28,
    "tertiary": 0.30, "tertiary_link": 0.18,
    "unclassified": 0.15,
    "residential": 0.12,
    "living_street": 0.05,
    "service": 0.03,
}
# Brzina diže emisiju kotrljanja; ovo su množioci, ne apsolutne vrednosti.
SPEED_MULT = [(30, 0.75), (50, 1.0), (70, 1.25), (90, 1.5), (999, 1.8)]

# Fiksne kotve skale u log-prostoru, da indeks ne skače između pokretanja
# kad se OSM promeni. Izabrane iz raspona izmerenog na koridoru.
IDX_LO_DB = -32.0
IDX_HI_DB = -1.0

BANDS = [(25, "tiho"), (50, "umereno"), (75, "izloženo"), (101, "vrlo izloženo")]


def bbox_of(axis):
    lons = [c[0] for c in axis]
    lats = [c[1] for c in axis]
    return (min(lats) - BBOX_PAD_DEG, min(lons) - BBOX_PAD_DEG,
            max(lats) + BBOX_PAD_DEG, max(lons) + BBOX_PAD_DEG)


def fetch_roads(bbox):
    """Putevi iz OSM-a za bbox. Keš je vezan za bbox — menja se sa osom."""
    s, w, n, e = bbox
    key = f"{s:.4f}_{w:.4f}_{n:.4f}_{e:.4f}"
    cache = os.path.join(CACHE_DIR, f"osm_{key}.json")
    if os.path.exists(cache):
        with open(cache) as f:
            data = json.load(f)
        print(f"  OSM keš: {len(data['elements'])} puteva")
        return data["elements"]

    classes = "|".join(ROAD_W)
    q = (f'[out:json][timeout:120];'
         f'(way["highway"~"^({classes})$"]({s},{w},{n},{e}););'
         f'out tags geom;')
    print("  Preuzimam puteve sa Overpass API-ja...", flush=True)
    req = urllib.request.Request(
        OVERPASS_URL, data=urllib.parse.urlencode({"data": q}).encode(),
        headers={"User-Agent": "biciklisticki-koridor/1.0 (github pages)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.load(r)
            break
        except Exception as exc:                       # noqa: BLE001
            if attempt == 2:
                raise SystemExit(f"! Overpass nedostupan: {exc}")
            print(f"    pokušaj {attempt + 1} nije uspeo ({exc}); čekam 10 s")
            time.sleep(10)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache, "w") as f:
        json.dump(data, f)
    print(f"  OSM: {len(data['elements'])} puteva")
    return data["elements"]


def parse_maxspeed(tags):
    raw = tags.get("maxspeed", "")
    for tok in str(raw).split():
        if tok.isdigit():
            return int(tok)
    return None


def build_segments(elements):
    """(a, b, težina, dužina, glavni?) po segmentu, u lokalnoj ravni (metri).

    „Glavni" se nosi kao zastavica iz klase puta, a ne izvodi iz težine —
    težina je već pomnožena brzinom i brojem traka, pa bi poređenje sa
    pragom klase propustilo širok tercijarni put kao da je magistrala.
    """
    segs = []
    for el in elements:
        tags = el.get("tags", {})
        hw = tags.get("highway")
        base = ROAD_W.get(hw)
        if base is None or "geometry" not in el:
            continue
        major = hw in MAJOR
        w = base
        sp = parse_maxspeed(tags)
        if sp:
            w *= next(m for lim, m in SPEED_MULT if sp <= lim)
        try:
            lanes = int(str(tags.get("lanes", "")).split(";")[0])
            w *= 1.0 + 0.15 * max(0, lanes - 2)   # više traka = veći protok
        except ValueError:
            pass
        pts = [planar_xy(nd["lon"], nd["lat"]) for nd in el["geometry"]]
        for a, b in zip(pts, pts[1:]):
            length = math.hypot(b[0] - a[0], b[1] - a[1])
            if length > 0:
                segs.append((a, b, w, length, major))
    return segs


def grid_segments(segs, cell=SEARCH_R_M):
    grid = {}
    for s in segs:
        (ax, ay), (bx, by) = s[0], s[1]
        for cx in range(int(min(ax, bx) // cell), int(max(ax, bx) // cell) + 1):
            for cy in range(int(min(ay, by) // cell), int(max(ay, by) // cell) + 1):
                grid.setdefault((cx, cy), []).append(s)
    return grid


def seg_dist(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
    return math.hypot(px - (ax + dx * t), py - (ay + dy * t))


MAJOR = {"motorway", "trunk", "primary", "secondary"}


def exposure(samples, grid, cell=SEARCH_R_M):
    """Energija i rastojanje do najbližeg glavnog puta, po tački."""
    out = []
    for s in samples:
        x, y = planar_xy(s["lon"], s["lat"])
        cx, cy = int(x // cell), int(y // cell)
        energy = 0.0
        nearest = None
        seen = set()
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for seg in grid.get((cx + i, cy + j), ()):
                    sid = id(seg)
                    if sid in seen:
                        continue
                    seen.add(sid)
                    d = seg_dist(x, y, seg[0], seg[1])
                    if d > SEARCH_R_M:
                        continue
                    energy += seg[2] * seg[3] / max(d, D_MIN_M) ** 2
                    if seg[4] and (nearest is None or d < nearest):
                        nearest = d
        out.append((energy, nearest))
    return out


def to_index(energy):
    """Energija -> indeks 0–100 preko fiksnih kotvi u log-prostoru."""
    db = 10.0 * math.log10(energy) if energy > 0 else IDX_LO_DB
    f = (db - IDX_LO_DB) / (IDX_HI_DB - IDX_LO_DB)
    return max(0, min(100, round(f * 100)))


def band(idx):
    return next(name for lim, name in BANDS if idx < lim)


# ---------- agregati ----------

def aggregate(samples, idx_list, near_list, deon_order):
    def stats(sel):
        vals = [idx_list[i] for i in sel]
        near = [near_list[i] for i in sel if near_list[i] is not None]
        avg = sum(vals) / len(vals)
        return {
            "n": len(sel),
            "avg": round(avg, 1),
            "max": max(vals),
            "min": min(vals),
            "band": band(round(avg)),
            "pct_tiho": round(100.0 * sum(1 for v in vals if v < 25) / len(vals), 1),
            "pct_izlozeno": round(100.0 * sum(1 for v in vals if v >= 50) / len(vals), 1),
            "najblizi_glavni_m": round(min(near)) if near else None,
            "pct_bez_glavnog": round(
                100.0 * sum(1 for i in sel if near_list[i] is None) / len(sel), 1),
        }

    by_deonica = {}
    for dn in deon_order:
        sel = [i for i, s in enumerate(samples) if s["deonica"] == dn]
        if not sel:
            continue
        st = stats(sel)
        st["km_start"] = round(samples[sel[0]]["km"], 3)
        st["km_end"] = round(samples[sel[-1]]["km"], 3)
        by_deonica[dn] = st
    return by_deonica, stats(list(range(len(samples))))


# ---------- glavni ulaz ----------

def main():
    for f in (MREZA_FILE, DEONICE_FILE):
        if not os.path.exists(f):
            print(f"ERROR: nema {f} — prvo pokreni `make convert`.", file=sys.stderr)
            return 1

    axis, by_tip, deon_order = prepare()
    flat = [s for tip, _ in STAZE for s in by_tip[tip]]
    # otisak pokriva i parametre modela, ne samo geometriju — inače izmena
    # težina ili radijusa ne bi ponovo generisala izlaz
    cur_hash = samples_hash(flat) + "-" + hashlib.sha1(
        json.dumps([ROAD_W, SPEED_MULT, SEARCH_R_M, D_MIN_M,
                    IDX_LO_DB, IDX_HI_DB, BANDS], sort_keys=True).encode()
    ).hexdigest()[:8]

    if os.path.exists(OUT_FILE):
        try:
            with open(OUT_FILE) as f:
                old = json.load(f)
            if (old.get("schema") == NOISE_SCHEMA
                    and old.get("samples_hash") == cur_hash):
                print(f"buka cache hit ({len(flat)} tačaka)")
                return 0
        except (OSError, json.JSONDecodeError):
            pass

    roads = fetch_roads(bbox_of(axis))
    segs = build_segments(roads)
    grid = grid_segments(segs)
    print(f"  {len(segs)} segmenata puta u modelu")

    staze_out = []
    for tip, label in STAZE:
        samples = by_tip[tip]
        raw = exposure(samples, grid)
        idx_list = [to_index(e) for e, _ in raw]
        near_list = [n for _, n in raw]
        by_deonica, totals = aggregate(samples, idx_list, near_list, deon_order)
        print(f"  {label}: prosek {totals['avg']} ({totals['band']}), "
              f"tiho {totals['pct_tiho']}%, izloženo {totals['pct_izlozeno']}%")
        staze_out.append({
            "tip": tip,
            "label": label,
            "n_points": len(samples),
            "points": {
                "km": [round(s["km"], 3) for s in samples],
                "lon": [round(s["lon"], 5) for s in samples],
                "lat": [round(s["lat"], 5) for s in samples],
                "chain": [s["chain"] for s in samples],
                "deonica": [deon_order.index(s["deonica"]) for s in samples],
                "idx": idx_list,
                "near_m": [round(n) if n is not None else None for n in near_list],
            },
            "by_deonica": by_deonica,
            "totals": totals,
        })

    out = {
        "schema": NOISE_SCHEMA,
        "samples_hash": cur_hash,
        "source": "OpenStreetMap (ODbL) — modelirano, bez merenja",
        "step_m": 10.0,
        "osa_km": round(axis_km(axis), 2),
        "radius_m": SEARCH_R_M,
        "bands": [{"do": lim, "naziv": name} for lim, name in BANDS],
        "deonice": deon_order,
        "staze": staze_out,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  -> {os.path.relpath(OUT_FILE, ROOT)} "
          f"({os.path.getsize(OUT_FILE) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
