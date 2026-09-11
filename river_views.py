#!/usr/bin/env python3
"""Pogled na reku duž koridora — ray-casting preko krošnji ka površini Nišave.

Za svaku tačku svake staze (10 m) pušta se 72 zraka u krug (na 5°) i prati
se preko CHM rastera visina krošnji. Pravac „vidi reku" ako zrak stigne do
površine Nišave pre nego što naiđe na vegetaciju višu od oka. Tačka ima
pogled na reku ako voda može da se vidi u uglu od bar MIN_VIEW_DEG —
jedan uski prorez između dva stabla nije pogled.

Za razliku od buke, ovde su krošnje pravi alat: drveće zaklanja pogled
snažno. Slabost CHM-a je druga — on daje visinu VRHA krošnje, a ne njenu
donju ivicu, pa ne zna da li se ispod visokog drveta vidi. Zato se računaju
dve granice:

  konzervativno — svaka vegetacija viša od oka zaklanja
  optimistično  — zaklanja samo niža vegetacija (≤ TALL_TREE_H); ispod
                  visokog drveća pretpostavlja se da se vidi

i uz njih geometrijski potencijal: pogled kad vegetacije ne bi bilo. Razlika
između potencijala i stvarnog pogleda je ono što zaklanja rastinje.

Voda: OSM površine `natural=water + water=river` (pojedinačni poligoni
zapadno od centra, članovi multipoligon relacija istočno, sa adama kao
`inner`), plus linija toka Nišave kao osigurač za rupe u poligonima.
Bare, ribnjaci i staro korito se ne računaju — pitanje je pogled na reku.

Ograničenja: teren je ravan. Gornji bedem je u stvarnosti viši i verovatno
gleda preko niskog rastinja na nižoj terasi, pa je za njega procena
potcenjena. CHM snimci su 2018–2020, a zimi, bez lišća, pogled je otvoreniji.
"""
import hashlib
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

from koridor import (DEONICE_FILE, MREZA_FILE, ROOT, STAZE, axis_km, merc_xy,
                     prepare, samples_hash)

try:
    import numpy as np
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    from shade_canopy import OBSERVER_H, load_chm
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

OUT_FILE = os.path.join(ROOT, "data", "river_views.json")
CACHE_DIR = os.path.join(ROOT, "data", ".cache", "views")

VIEWS_SCHEMA = 1

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
BBOX_PAD_DEG = 0.005          # ~400 m margine oko ose
N_DIRS = 72                   # zraci na svakih 5°
MAX_VIEW_M = 250.0            # dalje od ovoga reka u uskoj dolini nije „pogled"
START_M = 2.0                 # preskoči sopstveni položaj
MIN_VIEW_DEG = 10             # uži ugao je prorez, ne pogled
TALL_TREE_H = 8.0             # optimistično: ispod višeg drveća se vidi


# ---------- voda iz OSM-a ----------

def bbox_of(axis):
    lons = [c[0] for c in axis]
    lats = [c[1] for c in axis]
    return (min(lats) - BBOX_PAD_DEG, min(lons) - BBOX_PAD_DEG,
            max(lats) + BBOX_PAD_DEG, max(lons) + BBOX_PAD_DEG)


def fetch_water(bbox):
    """Površine i tok Nišave za bbox. Keš je vezan za bbox."""
    s, w, n, e = bbox
    key = f"{s:.4f}_{w:.4f}_{n:.4f}_{e:.4f}"
    cache = os.path.join(CACHE_DIR, f"osm_water_{key}.json")
    if os.path.exists(cache):
        with open(cache) as f:
            return json.load(f)["elements"]

    bb = f"({s},{w},{n},{e})"
    # relacije se traže bez geometrije (cela obala Nišave je prevelika za
    # Overpass), a geometrija samo za članove unutar koridora
    q = (f'[out:json][timeout:180];'
         f'(way["natural"="water"]["water"="river"]{bb};'
         f' way["waterway"="river"]["name"~"Нишава|Nišava"]{bb};);'
         f'out tags geom;'
         f'relation["natural"="water"]["water"="river"]{bb}->.r;'
         f'.r out body;'
         f'way(r.r){bb};'
         f'out geom;')
    print("  Preuzimam vodu sa Overpass API-ja...", flush=True)
    req = urllib.request.Request(
        OVERPASS_URL, data=urllib.parse.urlencode({"data": q}).encode(),
        headers={"User-Agent": "biciklisticki-koridor/1.0 (github pages)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                data = json.load(r)
            break
        except Exception as exc:                       # noqa: BLE001
            if attempt == 2:
                raise SystemExit(f"! Overpass nedostupan: {exc}")
            print(f"    pokušaj {attempt + 1} nije uspeo ({exc}); čekam 20 s")
            time.sleep(20)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache, "w") as f:
        json.dump(data, f)
    return data["elements"]


def _stitch(ways):
    """Spoji delove prstena po krajnjim tačkama. Vraća samo zatvorene prstenove."""
    pending = [list(w) for w in ways if len(w) >= 2]
    rings = []
    while pending:
        ring = pending.pop()
        changed = True
        while ring[0] != ring[-1] and changed:
            changed = False
            for i, w in enumerate(pending):
                if w[0] == ring[-1]:
                    ring += w[1:]
                elif w[-1] == ring[-1]:
                    ring += w[::-1][1:]
                elif w[-1] == ring[0]:
                    ring = w[:-1] + ring
                elif w[0] == ring[0]:
                    ring = w[::-1][:-1] + ring
                else:
                    continue
                pending.pop(i)
                changed = True
                break
        if ring[0] == ring[-1] and len(ring) >= 4:
            rings.append(ring)
        else:
            print(f"  ! otvoren prsten ({len(ring)} tačaka) preskočen")
    return rings


def water_shapes(elements):
    """(geometrija u EPSG:3857, vrednost) za rasterizaciju — ade na kraju sa 0."""
    def xy(geom):
        return [merc_xy(p["lon"], p["lat"]) for p in geom]

    outer, inner, lines = [], [], []
    roles = {}
    for el in elements:
        if el["type"] == "relation":
            for m in el.get("members", []):
                if m["type"] == "way":
                    roles[m["ref"]] = m.get("role") or "outer"
    member_geom = {"outer": [], "inner": []}
    for el in elements:
        if el["type"] != "way" or "geometry" not in el:
            continue
        tags = el.get("tags", {})
        g = [(p["lon"], p["lat"]) for p in el["geometry"]]
        if tags.get("waterway") == "river":
            lines.append(el["geometry"])
        elif tags.get("water") == "river":
            outer.append(el["geometry"])
        elif el["id"] in roles:
            member_geom["inner" if roles[el["id"]] == "inner" else "outer"].append(g)

    for role, bucket in (("outer", outer), ("inner", inner)):
        for ring in _stitch(member_geom[role]):
            bucket.append([{"lon": lo, "lat": la} for lo, la in ring])

    shapes = [({"type": "Polygon", "coordinates": [xy(r)]}, 1) for r in outer]
    shapes += [({"type": "LineString", "coordinates": xy(ln)}, 1) for ln in lines]
    shapes += [({"type": "Polygon", "coordinates": [xy(r)]}, 0) for r in inner]
    print(f"  voda: {len(outer)} površina, {len(inner)} ada, {len(lines)} linija toka")
    return shapes


# ---------- zraci ----------

def cast_views(samples, arr, origin, res, wmask):
    """Ugao pogleda na reku po tački (tri varijante) i rastojanje do vode."""
    H, W = arr.shape
    n = len(samples)
    px = np.empty(n)
    py = np.empty(n)
    for i, s in enumerate(samples):
        x, y = merc_xy(s["lon"], s["lat"])
        px[i] = (x - origin[0]) / res
        py[i] = (origin[1] - y) / res

    t = np.arange(START_M, MAX_VIEW_M, res)            # metri duž zraka
    big = len(t) + 1
    deg = 360.0 / N_DIRS
    view = {"kons": np.zeros(n), "opt": np.zeros(n), "pot": np.zeros(n)}
    water_m = np.full(n, np.inf)

    for k in range(N_DIRS):
        az = math.radians(k * deg)
        cols = (px[:, None] + t[None, :] * math.sin(az) / res).astype(np.int32)
        rows = (py[:, None] - t[None, :] * math.cos(az) / res).astype(np.int32)
        np.clip(cols, 0, W - 1, out=cols)
        np.clip(rows, 0, H - 1, out=rows)
        h = arr[rows, cols]
        wet = wmask[rows, cols]

        has_w = wet.any(axis=1)
        first_w = np.where(has_w, wet.argmax(axis=1), big)
        view["pot"] += has_w
        water_m = np.minimum(water_m, np.where(has_w, t[np.minimum(first_w, len(t) - 1)], np.inf))

        for name, blk in (("kons", h > OBSERVER_H),
                          ("opt", (h > OBSERVER_H) & (h <= TALL_TREE_H))):
            has_b = blk.any(axis=1)
            first_b = np.where(has_b, blk.argmax(axis=1), big)
            view[name] += has_w & (first_w < first_b)

    return ({k: v * deg for k, v in view.items()},
            np.where(np.isfinite(water_m), water_m, np.nan))


# ---------- agregati ----------

def aggregate(samples, view, water_m, deon_order):
    def stats(sel):
        sel = np.asarray(sel)
        wm = water_m[sel]
        wm = wm[~np.isnan(wm)]
        return {
            "n": int(len(sel)),
            "pct_view": round(100.0 * float((view["kons"][sel] >= MIN_VIEW_DEG).mean()), 1),
            "pct_view_opt": round(100.0 * float((view["opt"][sel] >= MIN_VIEW_DEG).mean()), 1),
            "pct_potential": round(100.0 * float((view["pot"][sel] >= MIN_VIEW_DEG).mean()), 1),
            "avg_view_deg": round(float(view["kons"][sel].mean()), 1),
            "median_water_m": round(float(np.median(wm))) if len(wm) else None,
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
    if not HAS_DEPS:
        print("ERROR: treba numpy + rasterio — pokreni `make venv`.", file=sys.stderr)
        return 1
    for f in (MREZA_FILE, DEONICE_FILE):
        if not os.path.exists(f):
            print(f"ERROR: nema {f} — prvo pokreni `make convert`.", file=sys.stderr)
            return 1

    axis, by_tip, deon_order = prepare()
    flat = [s for tip, _ in STAZE for s in by_tip[tip]]
    geom_hash = samples_hash(flat)
    cur_hash = geom_hash + "-" + hashlib.sha1(json.dumps(
        [N_DIRS, MAX_VIEW_M, START_M, MIN_VIEW_DEG, TALL_TREE_H, OBSERVER_H]
    ).encode()).hexdigest()[:8]

    if os.path.exists(OUT_FILE):
        try:
            with open(OUT_FILE) as f:
                old = json.load(f)
            if old.get("schema") == VIEWS_SCHEMA and old.get("samples_hash") == cur_hash:
                print(f"river_views cache hit ({len(flat)} tačaka)")
                return 0
        except (OSError, json.JSONDecodeError):
            pass

    # isti ključ kao shade_canopy.py — CHM prozor se deli, ne preuzima ponovo
    arr, origin, res = load_chm(flat, geom_hash)
    shapes = water_shapes(fetch_water(bbox_of(axis)))
    wmask = rasterize(shapes, out_shape=arr.shape,
                      transform=from_origin(origin[0], origin[1], res, res),
                      fill=0, all_touched=True, dtype="uint8").astype(bool)
    print(f"  maska vode: {int(wmask.sum())} px ({wmask.sum() * res * res / 1e4:.1f} ha)")

    staze_out = []
    for tip, label in STAZE:
        samples = by_tip[tip]
        view, water_m = cast_views(samples, arr, origin, res, wmask)
        by_deonica, totals = aggregate(samples, view, water_m, deon_order)
        print(f"  {label}: pogled {totals['pct_view']}–{totals['pct_view_opt']} % "
              f"(bez rastinja {totals['pct_potential']} %), "
              f"voda median {totals['median_water_m']} m")
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
                "view_deg": [int(v) for v in view["kons"]],
                "view_deg_opt": [int(v) for v in view["opt"]],
                "water_m": [None if math.isnan(v) else round(float(v)) for v in water_m],
            },
            "by_deonica": by_deonica,
            "totals": totals,
        })

    out = {
        "schema": VIEWS_SCHEMA,
        "samples_hash": cur_hash,
        "source": "OpenStreetMap (ODbL) voda + Meta/WRI Canopy Height (CC BY 4.0)",
        "step_m": 10.0,
        "osa_km": round(axis_km(axis), 2),
        "min_view_deg": MIN_VIEW_DEG,
        "max_view_m": MAX_VIEW_M,
        "deonice": deon_order,
        "staze": staze_out,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  -> {os.path.relpath(OUT_FILE, ROOT)} ({os.path.getsize(OUT_FILE) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
