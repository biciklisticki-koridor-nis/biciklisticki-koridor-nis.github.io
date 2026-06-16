"""ESA WorldCover 2021 v2 sampling preko Terrascope WMTS.

Preuzima 256×256 PNG tile-ove iz EPSG:3857 grid-a za bbox trase, mozaikuje
ih u jednu sliku, pa po lat/lon uzorkuje klase land cover-a (RGB → kod).
Tile-ovi se keširaju u data/.cache/worldcover/. Mozaik se ne čuva.
"""
import hashlib
import json
import math
import os
import urllib.error
import urllib.request

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


WMTS_URL = "https://wmts.terrascope.be/"
WMTS_LAYER = "esa-worldcover-map-10m-2021-v2_map"
WMTS_TIME = "2021-01-01"          # jedina podržana vrednost za ovaj layer
WMTS_TILE_SET = "EPSG:3857"
WMTS_ZOOM = 14                    # ~9.5 m/pix na lat 43.3 — bliske 10 m source rezoluciji
WC_KERNEL_HALF = 1                # 3×3 majority (≈30×30 m) — gladi mixed-pixel artefakte
WC_SCHEMA = 5                     # bump pri promeni logike

SHADE_CLASSES = {"tree_cover"}                                # daje senku tokom celog dana
GREEN_CLASSES = {"tree_cover", "shrubland", "grassland", "cropland", "wetland"}

# ESA WorldCover klase ↔ RGB paleta (iz tehničke specifikacije)
RGB_TO_CLASS = {
    (0, 100, 0):     (10,  "tree_cover"),
    (255, 187, 34):  (20,  "shrubland"),
    (255, 255, 76):  (30,  "grassland"),
    (240, 150, 255): (40,  "cropland"),
    (250, 0, 0):     (50,  "built_up"),
    (180, 180, 180): (60,  "bare"),
    (240, 240, 240): (70,  "snow_ice"),
    (0, 100, 200):   (80,  "water"),
    (0, 150, 160):   (90,  "wetland"),
    (0, 207, 117):   (95,  "mangroves"),
    (250, 230, 160): (100, "moss_lichen"),
}

CLASS_LABELS = {
    "tree_cover":  "Drveće",
    "shrubland":   "Žbunje",
    "grassland":   "Travna površina",
    "cropland":    "Obradivo",
    "built_up":    "Izgrađeno (asfalt/beton/zgrade)",
    "bare":        "Golo/peskovito",
    "water":       "Voda",
    "wetland":     "Močvarno",
    "snow_ice":    "Sneg/led",
    "mangroves":   "Mangrove",
    "moss_lichen": "Mahovina/lišaj",
}


# ---------- WMTS tile math ----------

def deg2tile(lat, lon, z):
    lat_rad = math.radians(lat)
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def tile_corner_lat_lon(x, y, z):
    """NW corner (lat, lon) tile-a u EPSG:3857 grid-u."""
    n = 2 ** z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))
    return lat, lon


# ---------- tile fetch / mozaik ----------

def fetch_tile(x, y, z, cache_dir):
    path = os.path.join(cache_dir, f"wc_{z}_{x}_{y}.png")
    if not os.path.exists(path):
        url = (f"{WMTS_URL}?service=wmts&request=GetTile&version=1.0.0"
               f"&layer={WMTS_LAYER}&style=default&format=image/png"
               f"&tileMatrixSet={WMTS_TILE_SET}&tileMatrix={z}"
               f"&tileRow={y}&tileCol={x}&TIME={WMTS_TIME}")
        req = urllib.request.Request(url, headers={"User-Agent": "koridor-konverter/1.0"})
        os.makedirs(cache_dir, exist_ok=True)
        try:
            with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
                f.write(r.read())
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            print(f"  ! WMTS tile {z}/{x}/{y}: {e}")
            return None
    return Image.open(path).convert("RGB")


def build_mosaic(bbox, z, cache_dir):
    """bbox: (lon_min, lat_min, lon_max, lat_max). Vraća (Image, mosaic_bbox).
    mosaic_bbox je pravo (lon_left, lat_bot, lon_right, lat_top) mozaika u stepenima.
    """
    lon_min, lat_min, lon_max, lat_max = bbox
    x_min, y_max = deg2tile(lat_min, lon_min, z)
    x_max, y_min = deg2tile(lat_max, lon_max, z)
    cols = list(range(x_min, x_max + 1))
    rows = list(range(y_min, y_max + 1))
    W, H = 256 * len(cols), 256 * len(rows)
    mosaic = Image.new("RGB", (W, H), (0, 0, 0))
    for ci, x in enumerate(cols):
        for ri, y in enumerate(rows):
            tile = fetch_tile(x, y, z, cache_dir)
            if tile is not None:
                mosaic.paste(tile, (ci * 256, ri * 256))
    lat_top, lon_left  = tile_corner_lat_lon(cols[0], rows[0], z)
    lat_bot, lon_right = tile_corner_lat_lon(cols[-1] + 1, rows[-1] + 1, z)
    return mosaic, (lon_left, lat_bot, lon_right, lat_top), len(cols) * len(rows)


# ---------- (lat, lon) → pixel u mozaiku (Web Mercator-tačno) ----------

def _merc_y(lat):
    return math.asinh(math.tan(math.radians(lat))) / math.pi


def sample_majority(pixels, cx, cy, W, H, half=WC_KERNEL_HALF):
    """Većinska klasa u (2·half+1)² okruženju, sa land-prior bias-om.

    Trasa je suvozemna (na keju, ne u reci). Granični pixel od 10 m često hvata
    i kej i ivicu reke; pošto je voda dominantna po površini, klasifikator vraća
    "water". Pretpostavljamo: ako u okruženju postoji bar jedna non-water klasa,
    bira se ona — water vraćamo samo kada su svi susedi voda (most ne važi: most
    je beton = built_up, što je već non-water).
    """
    counts = {}
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            x, y = cx + dx, cy + dy
            if 0 <= x < W and 0 <= y < H:
                cls = RGB_TO_CLASS.get(pixels[x, y])
                if cls:
                    counts[cls] = counts.get(cls, 0) + 1
    if not counts:
        return None
    non_water = {k: v for k, v in counts.items() if k[1] != "water"}
    pool = non_water if non_water else counts
    return max(pool.items(), key=lambda kv: kv[1])[0]


def latlon_to_pixel(lat, lon, bbox, W, H):
    lon_left, lat_bot, lon_right, lat_top = bbox
    # Linearno po lon (Web Mercator je u x linearan po lon)
    x = int(round((lon - lon_left) / (lon_right - lon_left) * (W - 1)))
    # Web Mercator y — koristimo Mercator-skaliranje da bismo bili tačni
    yt = _merc_y(lat_top)
    yb = _merc_y(lat_bot)
    yp = _merc_y(lat)
    y = int(round((yt - yp) / (yt - yb) * (H - 1)))
    return x, y


# ---------- shade / green metrics ----------

def _run_stats(seq_of_bools, step_m):
    """Iz niza True/False vrati (pct_true, longest_true_m, longest_false_m, transitions)."""
    n = len(seq_of_bools)
    if n == 0:
        return 0.0, 0, 0, 0
    n_true = sum(1 for v in seq_of_bools if v)
    pct_true = round(100.0 * n_true / n, 1)
    longest_t = longest_f = 0
    transitions = 0
    cur_state = seq_of_bools[0]
    cur_len = 1
    for v in seq_of_bools[1:]:
        if v == cur_state:
            cur_len += 1
        else:
            seg_m = cur_len * step_m
            if cur_state:
                longest_t = max(longest_t, seg_m)
            else:
                longest_f = max(longest_f, seg_m)
            transitions += 1
            cur_state = v
            cur_len = 1
    seg_m = cur_len * step_m
    if cur_state:
        longest_t = max(longest_t, seg_m)
    else:
        longest_f = max(longest_f, seg_m)
    return pct_true, longest_t, longest_f, transitions


def compute_shade(profile, step_m):
    """Izračunaj senku i zelenu pokrivenost po deonici + ukupno + strip intervals."""
    valid = [p for p in profile if p.get("klasa")]
    if not valid:
        return None

    def metrics_for(pts, classes):
        seq = [p["klasa"] in classes for p in pts]
        pct, lt, lf, tr = _run_stats(seq, step_m)
        return {"pct": pct, "longest_m": lt, "longest_gap_m": lf, "transitions": tr}

    totals = {
        "shade":  metrics_for(valid, SHADE_CLASSES),
        "green":  metrics_for(valid, GREEN_CLASSES),
    }

    by_deonica = {}
    groups = {}
    for p in valid:
        dn = p.get("deonica")
        if dn:
            groups.setdefault(dn, []).append(p)
    for dn, pts in groups.items():
        by_deonica[dn] = {
            "shade": metrics_for(pts, SHADE_CLASSES),
            "green": metrics_for(pts, GREEN_CLASSES),
        }

    # Strip: kontinuirani intervali shade ↔ sun, takođe prekida i na granici deonice
    # da bi se uredno mapiralo u per-deonica mini stripove.
    # Dužina svakog intervala = broj sample-a × step_m (sample je 50 m, ne 0 m).
    step_km = step_m / 1000.0
    strip = []
    cur_shade = valid[0]["klasa"] in SHADE_CLASSES
    cur_deonica = valid[0].get("deonica")
    cur_start_idx = 0
    for i in range(1, len(valid)):
        s  = valid[i]["klasa"] in SHADE_CLASSES
        dn = valid[i].get("deonica")
        if s != cur_shade or dn != cur_deonica:
            n = i - cur_start_idx
            km_start = valid[cur_start_idx]["km"]
            strip.append({
                "km_start": round(km_start, 3),
                "km_end":   round(km_start + n * step_km, 3),
                "length_m": n * step_m,
                "shade":    cur_shade,
                "deonica":  cur_deonica,
            })
            cur_shade = s
            cur_deonica = dn
            cur_start_idx = i
    n = len(valid) - cur_start_idx
    km_start = valid[cur_start_idx]["km"]
    strip.append({
        "km_start": round(km_start, 3),
        "km_end":   round(km_start + n * step_km, 3),
        "length_m": n * step_m,
        "shade":    cur_shade,
        "deonica":  cur_deonica,
    })

    return {
        "step_m": step_m,
        "totals": totals,
        "by_deonica": by_deonica,
        "strip": strip,
    }


# ---------- glavni ulaz ----------

def compute_or_load(sample_points, out_file, cache_dir, step_m, pad_deg=0.005):
    """sample_points: lista dictova {'lon','lat','km','deonica'}.

    Generiše/učita data/landcover.json sa:
      - profile: [{km, code, klasa, deonica}, ...]
      - by_deonica_pct: {deonica: {klasa: %}}
      - totals_pct: {klasa: %}
    """
    if not HAS_PIL:
        print("  ! Pillow nije instaliran — preskačem land cover. Pokreni: make venv")
        return None
    if not sample_points:
        return None

    lons = [p["lon"] for p in sample_points]
    lats = [p["lat"] for p in sample_points]
    bbox = (min(lons) - pad_deg, min(lats) - pad_deg, max(lons) + pad_deg, max(lats) + pad_deg)

    # Cache ključ: bbox + zoom + schema; sample tačke se mogu razlikovati ali tile-ovi se ne menjaju
    samples_hash = hashlib.sha1(
        json.dumps([(round(p["lon"], 6), round(p["lat"], 6)) for p in sample_points]).encode()
    ).hexdigest()
    if os.path.exists(out_file):
        try:
            with open(out_file) as f:
                old = json.load(f)
            if (old.get("schema") == WC_SCHEMA
                    and old.get("zoom") == WMTS_ZOOM
                    and old.get("samples_hash") == samples_hash):
                print(f"WorldCover cache hit ({len(old.get('profile', []))} tačaka)")
                return old
        except (OSError, json.JSONDecodeError):
            pass

    print(f"WorldCover: bbox {bbox}, zoom {WMTS_ZOOM}...")
    mosaic, mosaic_bbox, ntiles = build_mosaic(bbox, WMTS_ZOOM, cache_dir)
    W, H = mosaic.size
    print(f"  mozaik {W}×{H} px ({ntiles} tile-ova)")
    pixels = mosaic.load()

    profile = []
    for p in sample_points:
        x, y = latlon_to_pixel(p["lat"], p["lon"], mosaic_bbox, W, H)
        cls = sample_majority(pixels, x, y, W, H)
        profile.append({
            "km": round(p["km"], 3),
            "code": cls[0] if cls else None,
            "klasa": cls[1] if cls else None,
            "deonica": p.get("deonica"),
        })

    def pct(counts):
        total = sum(counts.values()) or 1
        return {k: round(100.0 * v / total, 1) for k, v in counts.items()}

    by_deonica_cnt = {}
    total_cnt = {}
    for q in profile:
        if not q["klasa"]:
            continue
        total_cnt[q["klasa"]] = total_cnt.get(q["klasa"], 0) + 1
        dn = q["deonica"]
        if dn:
            by_deonica_cnt.setdefault(dn, {})
            by_deonica_cnt[dn][q["klasa"]] = by_deonica_cnt[dn].get(q["klasa"], 0) + 1

    by_deonica_pct = {dn: pct(c) for dn, c in by_deonica_cnt.items()}
    totals_pct = pct(total_cnt)

    shade = compute_shade(profile, step_m)
    data = {
        "schema": WC_SCHEMA,
        "zoom": WMTS_ZOOM,
        "time": WMTS_TIME,
        "step_m": step_m,
        "samples_hash": samples_hash,
        "profile": profile,
        "totals_pct": totals_pct,
        "by_deonica_pct": by_deonica_pct,
        "shade": shade,
        "labels": CLASS_LABELS,
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  -> {os.path.basename(out_file)}  ({len(profile)} tačaka, {len(totals_pct)} klasa)")
    return data
