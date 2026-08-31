#!/usr/bin/env python3
"""Senka od krošnji duž trase — ray-casting na Meta/WRI 1 m Canopy Height Map.

Nastavak uspavanog shadeMap eksperimenta (post-mortem u dnevnik.html, jun 2026):
uslov za reaktivaciju — „slobodno dostupan canopy tile source" — ispunjen je.
Meta/WRI Global Canopy Height Map (1.19 m/px, COG na AWS Open Data) daje visine
krošnji, a izračun senke radimo sami: NOAA formule za položaj sunca + numpy
ray-marching od svake tačke trase ka suncu preko CHM rastera. Bez Puppeteer-a,
bez API ključa.

Koridor nije jedna linija nego tri paralelne staze na razmaku od ~9 m —
biciklistička i pešačke na gornjem i donjem bedemu — i one imaju bitno
različitu izloženost suncu. Zato se senka računa za sve tri, ali se prikazuje
na zajedničkoj kilometraži biciklističke ose, da bi ostale uporedive.

Pipeline:
  1. Učitaj tri mreže iz data/staze_mreza.geojson (convert.py). Referentna
     osa = lanac sa `uloga: "osa"`. Svaka staza se resample-uje na 10 m, a
     svaka tačka dobija km projekcijom na osu; tačke dalje od 40 m od ose
     (prilazi, krakovi ka naseljima) se izostavljaju.
  2. Preuzmi CHM prozor oko svih staza (HTTP range read COG-a; keš u
     data/.cache/).
  3. Za 4 referentna dana (solsticiji + ravnodnevnice) × svaki sat 05–20h:
     položaj sunca → zrak od tačke (1.5 m visine) ka suncu → blokiran ako
     bilo koja krošnja duž zraka premašuje visinu zraka.
  4. Zapiši data/shade_canopy.json: po stazi bitmask senke po satu, visine
     krošnji i agregati po deonicama.

Izvor: https://registry.opendata.aws/dataforgood-fb-forests/ (CC BY 4.0,
Maxar snimci 2018–2020 — novije sadnje/seče se ne vide).
"""
import hashlib
import json
import math
import os
import sys

try:
    import numpy as np
    import rasterio
    from rasterio.warp import transform as rio_transform
    from rasterio.windows import Window
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

ROOT = os.path.dirname(os.path.abspath(__file__))
MREZA_FILE = os.path.join(ROOT, "data", "staze_mreza.geojson")
DEONICE_FILE = os.path.join(ROOT, "data", "deonice.geojson")
OUT_FILE = os.path.join(ROOT, "data", "shade_canopy.json")
CACHE_DIR = os.path.join(ROOT, "data", ".cache", "canopy")

# Niš pada u quadkey 120233133 tile (z9) globalnog CHM mozaika.
CHM_URL = ("https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/"
           "alsgedi_global_v6_float/chm/120233133.tif")

CANOPY_SCHEMA = 3   # 3: tri staze (bici + oba bedema) na zajedničkoj km-osi

STAZE = [
    ("bici",           "Biciklistička staza"),
    ("pesacki_gornji", "Pešačka staza — gornji bedem"),
    ("pesacki_donji",  "Pešačka staza — donji bedem"),
]
PROJ_MAX_M = 40.0        # dalje od ose = prilaz, ne deo koridora

STEP_M = 10.0            # korak uzorkovanja trase
OBSERVER_H = 1.5         # visina bicikliste (m)
MAX_TREE_H = 26.0        # iznad ovoga ne tražimo krošnje (max u koridoru: 22 m)
RAY_STEP_M = 1.2         # ≈ rezolucija CHM grida
RAY_MAX_M = 300.0        # najduža senka koju pratimo (dec, nisko sunce)
MIN_SUN_ELEV = 2.0       # ispod 2° elevacije nema efektivnog direktnog sunca
BUFFER_PX = 8            # ±9.5 m prozor za visinu krošnje kod tačke
TREE_MIN_H = 3.0         # prag „ovo je drvo" za pokrivenost krošnjama
CHM_PAD_PX = 300         # margina CHM prozora za duge senke (~360 m)

LAT0 = 43.315            # centar trase — za solarne formule i metar/stepen
LON0 = 21.92
M_PER_DEG_LAT = 111320.0
M_PER_DEG_LON = M_PER_DEG_LAT * math.cos(math.radians(LAT0))

# Referentni dani kao u shade_real.py: DOY + UTC offset (mart/dec su CET).
DATES = [
    {"key": "mar21", "label": "Prolećna ravnodnevnica (21. mart)", "doy": 80, "tz": 1},
    {"key": "jun21", "label": "Letnji solsticij (21. jun)", "doy": 172, "tz": 2},
    {"key": "sep21", "label": "Jesenja ravnodnevnica (21. septembar)", "doy": 264, "tz": 2},
    {"key": "dec21", "label": "Zimski solsticij (21. decembar)", "doy": 355, "tz": 1},
]
HOURS = list(range(5, 21))  # lokalni sati 05..20


# ---------- trasa ----------

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


def resample_line(coords):
    """Tačke na svakih STEP_M duž linije, sa kumulativnom dužinom u metrima."""
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


def build_samples(axis, chains):
    """Uzorci po stazi, svaki sa km projektovanim na referentnu osu.

    Zajednička km-osa je jedino što tri staze čini uporedivim: one imaju
    različite sopstvene dužine i različite početke, pa bi sopstvena
    kilometraža poredila neuporedive tačke.
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
        extra = f", {dropped} van koridora" if dropped else ""
        print(f"  {tip}: {len(samples)} tačaka{extra}")
    return by_tip


def samples_hash(samples):
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


# ---------- CHM ----------

def load_chm(samples, key):
    """CHM prozor oko svih staza. Vraća (arr, origin_xy_3857, res_m). Keš: .npz.

    Keš nosi hash uzoraka — prozor mora da se preuzme ponovo kad se skup
    staza promeni, inače bi tačke pale van prozora.
    """
    cache = os.path.join(CACHE_DIR, "chm_window.npz")
    if os.path.exists(cache):
        z = np.load(cache)
        if str(z["key"]) == key:
            return z["arr"], z["origin"], float(z["res"])
        print("CHM keš je za drugi skup staza — preuzimam ponovo")
    print(f"Preuzimam CHM prozor ({CHM_URL.rsplit('/', 1)[-1]})...", flush=True)
    with rasterio.open(CHM_URL) as ds:
        lons = [p["lon"] for p in samples]
        lats = [p["lat"] for p in samples]
        xs, ys = rio_transform("EPSG:4326", ds.crs, lons, lats)
        idx = [ds.index(x, y) for x, y in zip(xs, ys)]
        rows = [i[0] for i in idx]
        cols = [i[1] for i in idx]
        rmin, rmax = min(rows) - CHM_PAD_PX, max(rows) + CHM_PAD_PX
        cmin, cmax = min(cols) - CHM_PAD_PX, max(cols) + CHM_PAD_PX
        arr = ds.read(1, window=Window(cmin, rmin, cmax - cmin, rmax - rmin))
        arr = np.ascontiguousarray(arr, dtype=np.float32)
        x0, y0 = ds.xy(rmin, cmin, offset="ul")
        res = float(ds.res[0])
    os.makedirs(CACHE_DIR, exist_ok=True)
    np.savez_compressed(cache, arr=arr, origin=np.array([x0, y0]), res=res,
                        key=np.array(key))
    return arr, np.array([x0, y0]), res


def merc_xy(lon, lat):
    R = 6378137.0
    return (math.radians(lon) * R,
            R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


# ---------- sunce ----------

def sun_pos(doy, hour_local, tz, lat=LAT0, lon=LON0):
    """NOAA aproksimacija. Vraća (elevacija °, azimut ° od severa u smeru sata)."""
    g = 2 * math.pi / 365 * (doy - 1 + (hour_local - 12) / 24)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    tst = hour_local * 60 + eqtime + 4 * lon - 60 * tz
    ha = math.radians(tst / 4 - 180)
    latr = math.radians(lat)
    cosz = (math.sin(latr) * math.sin(decl)
            + math.cos(latr) * math.cos(decl) * math.cos(ha))
    z = math.acos(max(-1.0, min(1.0, cosz)))
    elev = 90.0 - math.degrees(z)
    if math.sin(z) < 1e-6:
        az = 180.0
    else:
        cosa = ((math.sin(decl) - math.sin(latr) * cosz)
                / (math.cos(latr) * math.sin(z)))
        a = math.degrees(math.acos(max(-1.0, min(1.0, cosa))))
        az = a if ha < 0 else 360.0 - a
    return elev, az


# ---------- senka ----------

def compute_masks(samples, arr, origin, res):
    """Za svaki datum: bitmask po tački (bit i = sunce u satu HOURS[i]).

    Vraća (masks po datumu, daylight sati po datumu, canopy_h po tački).
    """
    H, W = arr.shape
    n = len(samples)
    px = np.empty(n)
    py = np.empty(n)
    for i, s in enumerate(samples):
        x, y = merc_xy(s["lon"], s["lat"])
        px[i] = (x - origin[0]) / res
        py[i] = (origin[1] - y) / res

    ix = px.astype(np.int32)
    iy = py.astype(np.int32)

    # Visina krošnje kod tačke: max u ±BUFFER_PX prozoru (drvored je uz stazu,
    # ne na njenoj osi — tačkasto očitavanje bi dalo lažne nule).
    canopy_h = np.empty(n, dtype=np.float32)
    for i in range(n):
        r0, r1 = max(iy[i] - BUFFER_PX, 0), iy[i] + BUFFER_PX + 1
        c0, c1 = max(ix[i] - BUFFER_PX, 0), ix[i] + BUFFER_PX + 1
        canopy_h[i] = arr[r0:r1, c0:c1].max()

    # Tačka direktno pod krošnjom je u senci nezavisno od ugla sunca.
    under = arr[iy, ix] > OBSERVER_H + 0.5

    n_steps = int(RAY_MAX_M / RAY_STEP_M)
    t = (np.arange(n_steps) + 0.5) * RAY_STEP_M

    masks = {}
    daylight = {}
    for d in DATES:
        m = np.zeros(n, dtype=np.int64)
        dl = []
        for hi, h in enumerate(HOURS):
            elev, az = sun_pos(d["doy"], h, d["tz"])
            if elev <= MIN_SUN_ELEV:
                continue
            dl.append(h)
            tan_e = math.tan(math.radians(elev))
            ray_h = OBSERVER_H + t * tan_e
            reach = ray_h < MAX_TREE_H
            tv = t[reach]
            rh = ray_h[reach]
            dcol = math.sin(math.radians(az)) / res
            drow = -math.cos(math.radians(az)) / res
            cols = (px[:, None] + tv[None, :] * dcol).astype(np.int32)
            rows = (py[:, None] + tv[None, :] * drow).astype(np.int32)
            np.clip(cols, 0, W - 1, out=cols)
            np.clip(rows, 0, H - 1, out=rows)
            blocked = (arr[rows, cols] > rh[None, :]).any(axis=1)
            sun = ~(blocked | under)
            m |= sun.astype(np.int64) << hi
        masks[d["key"]] = m
        daylight[d["key"]] = dl
    return masks, daylight, canopy_h


# ---------- agregati ----------

def popcount(v):
    return bin(int(v)).count("1")


def continuity(samples, idx, canopy_h):
    """Najduži neprekidan deo uz drvored, najduža rupa i broj prelaza (m).

    Rupe u samoj stazi (donji bedem nedostaje na dva mesta) prekidaju
    niz — inače bi se odsustvo staze računalo kao odsustvo drvoreda.
    """
    best_tree = best_gap = 0.0
    run = 0.0
    transitions = 0
    prev_tree = None
    prev_km = None
    for i in idx:
        i = int(i)
        km = samples[i]["km"]
        tree = bool(canopy_h[i] >= TREE_MIN_H)
        broken = prev_km is not None and (km - prev_km) * 1000.0 > STEP_M * 1.5
        if prev_tree is None or broken or tree != prev_tree:
            if prev_tree is not None:
                target = "tree" if prev_tree else "gap"
                if target == "tree":
                    best_tree = max(best_tree, run)
                else:
                    best_gap = max(best_gap, run)
                if not broken:
                    transitions += 1
            run = 0.0
        run += STEP_M
        prev_tree, prev_km = tree, km
    if prev_tree is not None:
        if prev_tree:
            best_tree = max(best_tree, run)
        else:
            best_gap = max(best_gap, run)
    return {"longest_m": round(best_tree), "longest_gap_m": round(best_gap),
            "transitions": transitions}


def aggregate(samples, masks, daylight, canopy_h, deon_order):
    def stats(idx):
        out = {"n": len(idx), "pct_shade": {}, "avg_sun_hours": {},
               "canopy_pct": round(100.0 * float(
                   (canopy_h[idx] >= TREE_MIN_H).mean()), 1),
               "canopy_avg_h": round(float(
                   canopy_h[idx][canopy_h[idx] >= TREE_MIN_H].mean()), 1)
               if (canopy_h[idx] >= TREE_MIN_H).any() else 0.0,
               "continuity": continuity(samples, idx, canopy_h)}
        for d in DATES:
            k = d["key"]
            nd = len(daylight[k])
            sh = np.array([popcount(masks[k][i]) for i in idx], dtype=float)
            out["avg_sun_hours"][k] = round(float(sh.mean()), 2)
            out["pct_shade"][k] = round(100.0 * (1.0 - float(sh.mean()) / nd), 1)
        return out

    all_idx = np.arange(len(samples))
    by_deonica = {}
    for dn in deon_order:
        idx = np.array([i for i, s in enumerate(samples) if s["deonica"] == dn])
        if not len(idx):
            continue          # staza ne prolazi kroz ovu deonicu
        st = stats(idx)
        st["km_start"] = round(samples[int(idx[0])]["km"], 3)
        st["km_end"] = round(samples[int(idx[-1])]["km"], 3)
        by_deonica[dn] = st
    return by_deonica, stats(all_idx)


# ---------- glavni ulaz ----------

def main():
    if not HAS_DEPS:
        print("ERROR: treba numpy + rasterio — pokreni `make venv`.", file=sys.stderr)
        return 1
    for f in (MREZA_FILE, DEONICE_FILE):
        if not os.path.exists(f):
            print(f"ERROR: nema {f} — prvo pokreni `make convert`.",
                  file=sys.stderr)
            return 1

    axis, chains = load_mreza()
    by_tip = build_samples(axis, chains)
    for samples in by_tip.values():
        assign_deonice(samples)

    # zajednički redosled deonica — po kilometraži referentne ose
    deon_order = []
    for s in by_tip["bici"]:
        if s["deonica"] not in deon_order:
            deon_order.append(s["deonica"])
    for samples in by_tip.values():
        for s in samples:
            if s["deonica"] not in deon_order:
                deon_order.append(s["deonica"])

    flat = [s for tip, _ in STAZE for s in by_tip[tip]]
    cur_hash = samples_hash(flat)
    if os.path.exists(OUT_FILE):
        try:
            with open(OUT_FILE) as f:
                old = json.load(f)
            if (old.get("schema") == CANOPY_SCHEMA
                    and old.get("samples_hash") == cur_hash):
                print(f"shade_canopy cache hit ({len(flat)} tačaka)")
                return 0
        except (OSError, json.JSONDecodeError):
            pass

    arr, origin, res = load_chm(flat, cur_hash)
    print(f"CHM prozor {arr.shape[0]}×{arr.shape[1]} px, {res:.2f} m/px")

    staze_out = []
    for tip, label in STAZE:
        samples = by_tip[tip]
        masks, daylight, canopy_h = compute_masks(samples, arr, origin, res)
        by_deonica, totals = aggregate(samples, masks, daylight, canopy_h,
                                       deon_order)
        print(f"  {label}: drvored {totals['canopy_pct']}%, senka " + ", ".join(
            f"{d['key']} {totals['pct_shade'][d['key']]:.1f}%" for d in DATES))
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
                "canopy_h": [round(float(h), 1) for h in canopy_h],
            },
            "masks": {k: [int(v) for v in m] for k, m in masks.items()},
            "by_deonica": by_deonica,
            "totals": totals,
        })
    # daylight zavisi samo od datuma, isti je za sve tri staze
    out = {
        "schema": CANOPY_SCHEMA,
        "samples_hash": cur_hash,
        "source": "Meta/WRI Global Canopy Height (1 m, CC BY 4.0, 2018-2020)",
        "step_m": STEP_M,
        "osa_km": round(resample_line(axis)[-1][2] / 1000.0, 2),
        "hours": HOURS,
        "dates": [{"key": d["key"], "label": d["label"],
                   "daylight": daylight[d["key"]]} for d in DATES],
        "deonice": deon_order,
        "staze": staze_out,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    size = os.path.getsize(OUT_FILE) / 1024
    print(f"  -> {os.path.relpath(OUT_FILE, ROOT)} ({size:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
