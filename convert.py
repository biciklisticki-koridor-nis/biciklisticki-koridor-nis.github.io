#!/usr/bin/env python3
"""Convert KML to per-layer GeoJSON + stats.json.

Reads koridor_data.kml, normalizes names (handles typos), categorizes
placemarks into logical layers, writes GeoJSON files into data/.
"""
import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

import worldcover

KML_NS = "{http://www.opengis.net/kml/2.2}"
ROOT = os.path.dirname(os.path.abspath(__file__))
KML_FILE = os.path.join(ROOT, "koridor_data.kml")
OUT_DIR = os.path.join(ROOT, "data")
IMG_DIR = os.path.join(OUT_DIR, "images")

IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
IMG_FIFE_RE = re.compile(r'\bfife=s\d+\b')
IMG_MAX_PX = 1024  # MyMaps `fife=sNNNN` skalira max dimenziju — dovoljno za popup i lightbox

# elevation: Open-Topo-Data SRTM 30m (free, javni, ~1 req/sec, 1000/day)
ELEV_API = "https://api.opentopodata.org/v1/srtm30m"
ELEV_STEP_M = 50
ELEV_BATCH = 100
ELEV_SMOOTH_WINDOW = 5  # centralni moving average — SRTM ima 1–2 m šuma
ELEV_SCHEMA = 2  # bump na promenu post-processing logike (deonica smoothing)
ELEV_FILE = os.path.join(OUT_DIR, "elevation.json")


# ---------- geometry helpers ----------

def parse_coords(text):
    pts = []
    for chunk in text.strip().split():
        parts = chunk.split(",")
        if len(parts) >= 2:
            pts.append((float(parts[0]), float(parts[1])))
    return pts


def haversine_m(p1, p2):
    R = 6371000.0
    lon1, lat1 = p1
    lon2, lat2 = p2
    a, b = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def line_length_m(pts):
    return sum(haversine_m(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def point_in_polygon(pt, polygon):
    """Ray casting; pt and polygon are (lon, lat)."""
    x, y = pt
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def classify_deonica(geom_type, coords, deonice):
    """Return deonica name or None. Point: test directly; LineString: by midpoint."""
    if not coords:
        return None
    if geom_type == "Point":
        pt = coords[0]
    else:  # LineString — use middle point of the polyline
        mid = len(coords) // 2
        pt = coords[mid]
    for name, ring in deonice:
        if point_in_polygon(pt, ring):
            return name
    return None


def line_length_by_deonica(coords, deonice):
    """Split a LineString's length among deonice by segment midpoint."""
    by = {name: 0.0 for name, _ in deonice}
    for i in range(len(coords) - 1):
        a, b = coords[i], coords[i + 1]
        seg_len = haversine_m(a, b)
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        for name, ring in deonice:
            if point_in_polygon(mid, ring):
                by[name] += seg_len
                break
    return by


# ---------- name normalization ----------

def norm(name):
    n = (name or "").strip().lower()
    return re.sub(r"\s+", " ", n)


def canonical_urban(n):
    """Map a normalized urban-equipment name to a canonical category id."""
    if re.search(r"osvetl", n):  # osvetljenje / osvetlenje / osvetluvanje
        return "osvetljenje"
    if re.search(r"\bklup", n):
        return "klupe"
    if re.search(r"kant|konten?jer", n):
        return "kante"
    if re.search(r"l[ej]tn?[ij]+kovac", n):  # letnjikovac & variants
        return "letnjikovci"
    if re.search(r"sport|vezban|odbojk|kosh?ar|fudbal|teren", n):
        return "sport"
    if re.search(r"decji|deciji|mobilijar", n):
        return "decji_mobilijar"
    return "ostalo"


def canonical_surface(n):
    """Map a path-line name to a surface type."""
    if re.search(r"asfalt", n):
        return "asfalt"
    if re.search(r"poplo[cč]an|kaldrm", n):
        return "popločana"
    if re.search(r"zemlj?[ae]n", n):  # zemljana / zemljena
        return "zemljana"
    return "ostalo"


def canonical_green(n):
    if re.search(r"vi?oska? veget|visoka veget", n):
        return "visoka_vegetacija"
    if re.search(r"niska veget", n):
        return "niska_vegetacija"
    if "izvire" in n or n == "voda" or "izvor" in n:
        return "izvor_vode"
    if "cesma" in n or "česma" in n:
        return "cesma"
    return "ostalo"


def canonical_state(n):
    if re.search(r"lo[sš]e? stanj|lose stanje|loshe stanje", n):
        return "loše"
    if re.search(r"srednje stanj", n):
        return "srednje"
    if re.search(r"dobro stanj", n):
        return "dobro"
    if "deponij" in n:
        return "deponija"
    return "ostalo"


PREKID_LABELS = {
    "dalekovod":             "Dalekovod",
    "privatno_zemljiste":    "Privatno zemljište",
    "most_prelaz":           "Most / prelaz",
    "bedem":                 "Bedem (gornji/donji)",
    "pritoka":               "Pritoka / vodotok",
    "nedostatak_rampe":      "Nedostatak rampe",
    "nedostatak_stepenista": "Nedostatak stepeništa",
    "objekat":               "Objekat / ograda",
    "promena_puta":          "Promena karaktera puta",
    "ostalo":                "Neoznačeno",
}


def canonical_prekid(n):
    if "dalekovod" in n:
        return "dalekovod"
    if "njiv" in n or "privatn" in n:
        return "privatno_zemljiste"
    if "most" in n:
        return "most_prelaz"
    if "bedem" in n:
        return "bedem"
    if "kutinsk" in n or "reka" in n or "potok" in n or "pritok" in n:
        return "pritoka"
    # specifični tipovi nedostataka — pre generičkih "stepenic"/"rampa"
    if "nedostatak" in n and ("ramp" in n):
        return "nedostatak_rampe"
    if "nedostatak" in n and ("stepenist" in n or "stepenic" in n):
        return "nedostatak_stepenista"
    if "objekat" in n or "objekt" in n or "ograd" in n:
        return "objekat"
    if "zemljen" in n or "zemljan" in n:
        return "promena_puta"
    return "ostalo"


# ---------- elevation profile ----------

def sample_line(coords, step_m):
    """Resample LineString uniformly. Returns [(lon, lat, cum_m), ...]."""
    if not coords or len(coords) < 2:
        return []
    samples = [(coords[0][0], coords[0][1], 0.0)]
    cum = 0.0
    next_at = step_m
    for i in range(len(coords) - 1):
        a, b = coords[i], coords[i + 1]
        seg = haversine_m(a, b)
        if seg == 0:
            continue
        seg_start = cum
        while next_at <= cum + seg:
            t = (next_at - seg_start) / seg
            samples.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, next_at))
            next_at += step_m
        cum += seg
    if samples[-1][2] < cum - 1.0:
        samples.append((coords[-1][0], coords[-1][1], cum))
    return samples


def moving_average(vals, window):
    """Centralni MA; preskače None vrednosti u prozoru."""
    n = len(vals)
    out = [None] * n
    half = window // 2
    for i in range(n):
        acc, cnt = 0.0, 0
        for j in range(max(0, i - half), min(n, i + half + 1)):
            if vals[j] is not None:
                acc += vals[j]
                cnt += 1
        out[i] = acc / cnt if cnt else None
    return out


def trasa_hash(coords):
    h = hashlib.sha1()
    for lon, lat in coords:
        h.update(f"{lon:.6f},{lat:.6f};".encode())
    return h.hexdigest()


def fetch_elevations(latlons, batch=ELEV_BATCH):
    """POST batch-ovi na opentopodata; vraća listu visina (m) iste dužine, None na grešku."""
    out = []
    for i in range(0, len(latlons), batch):
        chunk = latlons[i:i + batch]
        locs = "|".join(f"{lat:.6f},{lon:.6f}" for lon, lat in chunk)
        url = f"{ELEV_API}?locations={locs}"
        req = urllib.request.Request(url, headers={"User-Agent": "koridor-konverter/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
            for p in data.get("results", []):
                e = p.get("elevation")
                out.append(float(e) if e is not None else None)
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
            print(f"  ! elevation batch {i // batch + 1}: {e}")
            out.extend([None] * len(chunk))
        # opentopodata rate limit: 1 req/sec — pauziraj posle svakog osim poslednjeg
        if i + batch < len(latlons):
            time.sleep(1.05)
    return out


def smooth_profile_deonica(profile):
    """Popuni izolovane None deonica tačke iz okolnih.

    Trasa može na nekoliko mesta da pređe granicu meta_deonice poligona;
    tačke koje su sa obe strane okružene istom deonicom dobijaju tu deonicu.
    Tačke na ivici (samo jedna strana ima vrednost) nasleđuju je.
    """
    n = len(profile)
    if n == 0:
        return
    # Najpre razveži runs of None
    i = 0
    while i < n:
        if profile[i]["deonica"] is None:
            j = i
            while j < n and profile[j]["deonica"] is None:
                j += 1
            left  = profile[i - 1]["deonica"] if i > 0 else None
            right = profile[j]["deonica"]     if j < n else None
            fill = None
            if left and right and left == right:
                fill = left
            elif left and not right:
                fill = left
            elif right and not left:
                fill = right
            if fill:
                for k in range(i, j):
                    profile[k]["deonica"] = fill
            i = j
        else:
            i += 1


def compute_elevation_stats(profile):
    """profile: list of dicts with elev_smooth (m) and deonica."""
    valid = [p for p in profile if p["elev_smooth"] is not None]
    if not valid:
        return {"totals": {}, "by_deonica": {}}

    def asc_desc_grad(points):
        asc = desc = 0.0
        max_grad = 0.0
        for i in range(1, len(points)):
            de = points[i]["elev_smooth"] - points[i - 1]["elev_smooth"]
            dx = (points[i]["km"] - points[i - 1]["km"]) * 1000.0
            if de > 0:
                asc += de
            else:
                desc += -de
            if dx > 0:
                g = abs(de / dx) * 100.0
                if g > max_grad:
                    max_grad = g
        return asc, desc, max_grad

    elev = [p["elev_smooth"] for p in valid]
    asc, desc, max_grad = asc_desc_grad(valid)
    totals = {
        "min_m": round(min(elev), 1),
        "max_m": round(max(elev), 1),
        "raspon_m": round(max(elev) - min(elev), 1),
        "ascent_m": round(asc),
        "descent_m": round(desc),
        "max_gradient_pct": round(max_grad, 1),
    }

    by_deonica = {}
    seen_order = []
    for p in valid:
        dn = p.get("deonica")
        if dn and dn not in seen_order:
            seen_order.append(dn)
    for dn in seen_order:
        pts = [p for p in valid if p.get("deonica") == dn]
        if len(pts) < 2:
            continue
        el = [p["elev_smooth"] for p in pts]
        a, d, mg = asc_desc_grad(pts)
        by_deonica[dn] = {
            "min_m": round(min(el), 1),
            "max_m": round(max(el), 1),
            "raspon_m": round(max(el) - min(el), 1),
            "ascent_m": round(a),
            "descent_m": round(d),
            "max_gradient_pct": round(mg, 1),
        }
    return {"totals": totals, "by_deonica": by_deonica}


def compute_or_load_elevation(trasa_coords, deonice):
    """Učitaj cache ako trasa nije menjana; inače fetch + cache."""
    samples = sample_line(trasa_coords, ELEV_STEP_M)
    cur_hash = trasa_hash(trasa_coords)
    if os.path.exists(ELEV_FILE):
        try:
            with open(ELEV_FILE) as f:
                old = json.load(f)
            if (old.get("trasa_hash") == cur_hash
                    and old.get("step_m") == ELEV_STEP_M
                    and old.get("schema") == ELEV_SCHEMA):
                print(f"Elevation cache hit ({len(old.get('profile', []))} tačaka)")
                return old
        except (OSError, json.JSONDecodeError):
            pass

    print(f"Preuzimam elevation za {len(samples)} tačaka (~{ELEV_STEP_M} m, ~{(len(samples) // ELEV_BATCH + 1)} batch-ova)...")
    raw = fetch_elevations([(lon, lat) for lon, lat, _ in samples])
    smooth = moving_average(raw, ELEV_SMOOTH_WINDOW)
    profile = []
    for (lon, lat, m), e, es in zip(samples, raw, smooth):
        profile.append({
            "km": round(m / 1000.0, 3),
            "elev": round(e, 1) if e is not None else None,
            "elev_smooth": round(es, 1) if es is not None else None,
            "deonica": classify_deonica("Point", [(lon, lat)], deonice),
        })
    smooth_profile_deonica(profile)
    stats = compute_elevation_stats(profile)
    data = {
        "trasa_hash": cur_hash,
        "step_m": ELEV_STEP_M,
        "schema": ELEV_SCHEMA,
        "profile": profile,
        "totals": stats["totals"],
        "by_deonica": stats["by_deonica"],
    }
    with open(ELEV_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  -> elevation.json ({len(profile)} tačaka)")
    return data


# ---------- image extraction ----------

def extract_image_urls(description):
    if not description:
        return []
    seen = set()
    out = []
    for u in IMG_SRC_RE.findall(description):
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def cache_image(url):
    """Download once, cache by URL hash. Returns relative path or None on failure."""
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    rel = f"images/{h}.jpg"
    dst = os.path.join(IMG_DIR, f"{h}.jpg")
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return rel
    os.makedirs(IMG_DIR, exist_ok=True)
    download_url = IMG_FIFE_RE.sub(f"fife=s{IMG_MAX_PX}", url) if "fife=" in url else url
    req = urllib.request.Request(download_url, headers={"User-Agent": "koridor-konverter/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r, open(dst, "wb") as f:
            f.write(r.read())
        return rel
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(f"  ! preskačem sliku ({e}): {url[:80]}...")
        try:
            os.path.exists(dst) and os.remove(dst)
        except OSError:
            pass
        return None


# ---------- KML iteration ----------

def folder_placemarks(folder):
    out = []
    for pm in folder.findall(f"{KML_NS}Placemark"):
        nm_el = pm.find(f"{KML_NS}name")
        nm = nm_el.text if nm_el is not None else ""
        desc_el = pm.find(f"{KML_NS}description")
        desc = desc_el.text if desc_el is not None else ""
        urls = extract_image_urls(desc)
        images = [p for p in (cache_image(u) for u in urls) if p]
        pt = pm.find(f".//{KML_NS}Point/{KML_NS}coordinates")
        ls = pm.find(f".//{KML_NS}LineString/{KML_NS}coordinates")
        pg = pm.find(f".//{KML_NS}Polygon/{KML_NS}outerBoundaryIs/{KML_NS}LinearRing/{KML_NS}coordinates")
        if pt is not None:
            coords = parse_coords(pt.text)
            geom = {"type": "Point", "coordinates": list(coords[0])} if coords else None
        elif ls is not None:
            coords = parse_coords(ls.text)
            geom = {"type": "LineString", "coordinates": [list(c) for c in coords]} if coords else None
        elif pg is not None:
            coords = parse_coords(pg.text)
            geom = {"type": "Polygon", "coordinates": [[list(c) for c in coords]]} if coords else None
        else:
            coords = []
            geom = None
        out.append({"name": nm, "norm": norm(nm), "geom": geom, "images": images, "coords": coords})
    return out


# ---------- feature factories ----------

def feature(geom, props):
    return {"type": "Feature", "geometry": geom, "properties": props}


def feature_for(p, props):
    """Create a Feature from placemark dict; attach images/deonica if present."""
    if p.get("images"):
        props = {**props, "images": p["images"]}
    if p.get("deonica"):
        props = {**props, "deonica": p["deonica"]}
    return feature(p["geom"], props)


def fc(features):
    return {"type": "FeatureCollection", "features": features}


def write_geojson(name, features):
    path = os.path.join(OUT_DIR, f"{name}.geojson")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fc(features), f, ensure_ascii=False, separators=(",", ":"))
    print(f"  -> {name}.geojson  ({len(features)} features)")


# ---------- main ----------

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    tree = ET.parse(KML_FILE)
    root = tree.getroot()
    folders = root.findall(f".//{KML_NS}Folder")

    # Izdvoji meta_deonice folder pre svega ostalog
    deonice = []  # list of (name, ring_coords) zapadno -> istočno
    other_folders = []
    for folder in folders:
        fname = (folder.find(f"{KML_NS}name").text or "").strip()
        if fname.lower().startswith("meta_deonice"):
            for pm in folder.findall(f"{KML_NS}Placemark"):
                pm_nm_el = pm.find(f"{KML_NS}name")
                pm_nm = (pm_nm_el.text or "").strip() if pm_nm_el is not None else ""
                ring_el = pm.find(f".//{KML_NS}outerBoundaryIs/{KML_NS}LinearRing/{KML_NS}coordinates")
                if ring_el is None:
                    continue
                ring = parse_coords(ring_el.text)
                if ring:
                    deonice.append((pm_nm, ring))
        else:
            other_folders.append((fname, folder))
    deonice.sort(key=lambda d: sum(p[0] for p in d[1]) / len(d[1]))
    DEONICA_NAMES = [n for n, _ in deonice]

    # buckets
    out = {
        "trasa": [], "zelena": [], "prekidi": [],
        "stepenice": [], "rampe": [], "staze": [],
        "osvetljenje": [], "klupe": [], "kante": [], "letnjikovci": [],
        "sport": [], "urbana_ostalo": [],
        "stanja": [], "socijalni": [],
    }

    stats = {
        "total_placemarks": 0,
        "by_layer": {},
        "trasa_km": 0.0,
        "staze": {"asfalt_m": 0.0, "popločana_m": 0.0, "zemljana_m": 0.0, "ostalo_m": 0.0},
        "zelena_linije_m": {"visoka_vegetacija": 0.0, "niska_vegetacija": 0.0},
        "counts": {},
        "prekidi_po_tipu": {},
        "deonice": DEONICA_NAMES,
        "by_deonica": {n: {
            "trasa_m": 0.0,
            "counts": {},
            "staze_m": {"asfalt": 0.0, "popločana": 0.0, "zemljana": 0.0, "ostalo": 0.0},
        } for n in DEONICA_NAMES},
    }
    trasa_coords = None

    def add_count(deonica, key):
        if not deonica:
            return
        d = stats["by_deonica"][deonica]["counts"]
        d[key] = d.get(key, 0) + 1

    for fname, folder in other_folders:
        pms = folder_placemarks(folder)
        # klasifikuj svaki placemark u deonicu (po midpoint za linije, po tački za pinove)
        for p in pms:
            if p["geom"] and p["geom"]["type"] in ("Point", "LineString") and p["coords"]:
                p["deonica"] = classify_deonica(p["geom"]["type"], p["coords"], deonice)
        stats["total_placemarks"] += len(pms)
        stats["by_layer"][fname] = len(pms)

        if "Indicaciones" in fname:
            for p in pms:
                if p["geom"] and p["geom"]["type"] == "LineString":
                    out["trasa"].append(feature_for(p, {"name": "Glavna trasa koridora"}))
                    stats["trasa_km"] = line_length_m(p["coords"]) / 1000.0
                    trasa_coords = p["coords"]
                    for dn, ln in line_length_by_deonica(p["coords"], deonice).items():
                        stats["by_deonica"][dn]["trasa_m"] += ln

        elif "Zelena" in fname:
            for p in pms:
                if not p["geom"]:
                    continue
                cat = canonical_green(p["norm"])
                props = {"name": p["name"], "kategorija": cat}
                out["zelena"].append(feature_for(p, props))
                if p["geom"]["type"] == "LineString" and cat in ("visoka_vegetacija", "niska_vegetacija"):
                    stats["zelena_linije_m"][cat] += line_length_m(p["coords"])
                add_count(p.get("deonica"), "zelena")

        elif "Prekid" in fname:
            for p in pms:
                if p["geom"]:
                    tip = canonical_prekid(p["norm"])
                    out["prekidi"].append(feature_for(p, {"name": p["name"], "tip": tip}))
                    stats["prekidi_po_tipu"][tip] = stats["prekidi_po_tipu"].get(tip, 0) + 1
                    add_count(p.get("deonica"), "prekidi")

        elif "Stepenice i rampe" in fname:
            for p in pms:
                if not p["geom"]:
                    continue
                n = p["norm"]
                if p["geom"]["type"] == "LineString":
                    surf = canonical_surface(n)
                    L = line_length_m(p["coords"])
                    out["staze"].append(feature_for(p, {"name": p["name"], "podloga": surf, "duzina_m": round(L, 1)}))
                    stats["staze"][f"{surf}_m"] = stats["staze"].get(f"{surf}_m", 0.0) + L
                    for dn, ln in line_length_by_deonica(p["coords"], deonice).items():
                        stats["by_deonica"][dn]["staze_m"][surf] = stats["by_deonica"][dn]["staze_m"].get(surf, 0.0) + ln
                else:
                    if "stepenic" in n:
                        out["stepenice"].append(feature_for(p, {"name": p["name"]}))
                        add_count(p.get("deonica"), "stepenice")
                    elif "rampa" in n or "rampe" in n:
                        out["rampe"].append(feature_for(p, {"name": p["name"]}))
                        add_count(p.get("deonica"), "rampe")
                    else:
                        out["stepenice"].append(feature_for(p, {"name": p["name"]}))
                        add_count(p.get("deonica"), "stepenice")

        elif "Urbana oprema" in fname:
            for p in pms:
                if not p["geom"]:
                    continue
                cat = canonical_urban(p["norm"])
                feat = feature_for(p, {"name": p["name"], "kategorija": cat})
                bucket = cat if cat in ("osvetljenje", "klupe", "kante", "letnjikovci", "sport") else "urbana_ostalo"
                out[bucket].append(feat)
                add_count(p.get("deonica"), bucket)

        elif "Stanja" in fname:
            for p in pms:
                if not p["geom"]:
                    continue
                st = canonical_state(p["norm"])
                props = {"name": p["name"], "stanje": st}
                if p["geom"]["type"] == "LineString":
                    props["duzina_m"] = round(line_length_m(p["coords"]), 1)
                out["stanja"].append(feature_for(p, props))
                add_count(p.get("deonica"), "stanja")

        elif "Javni socijalni" in fname or "urbani dzepovi" in fname.lower():
            for p in pms:
                if p["geom"]:
                    out["socijalni"].append(feature_for(p, {"name": p["name"]}))
                    add_count(p.get("deonica"), "socijalni")

    # deonice -> GeoJSON Polygon overlay
    deonice_features = []
    for name, ring in deonice:
        deonice_features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[list(c) for c in ring]]},
            "properties": {"name": name},
        })
    write_geojson("deonice", deonice_features)

    # write all layers
    print("Layers written:")
    for k, feats in out.items():
        write_geojson(k, feats)
        stats["counts"][k] = len(feats)

    # prune orphan images (više se ne referenciraju u bilo kom feature-u)
    used = set()
    for feats in out.values():
        for f in feats:
            for img_rel in (f["properties"].get("images") or []):
                used.add(os.path.basename(img_rel))
    if os.path.isdir(IMG_DIR):
        removed = 0
        for fname in os.listdir(IMG_DIR):
            if fname not in used:
                try:
                    os.remove(os.path.join(IMG_DIR, fname))
                    removed += 1
                except OSError:
                    pass
        if removed:
            print(f"Obrisano {removed} orphan slika iz data/images/")

    # round per-deonica meter values + add km
    for dn, dstats in stats["by_deonica"].items():
        dstats["trasa_km"] = round(dstats["trasa_m"] / 1000.0, 2)
        dstats["trasa_m"] = round(dstats["trasa_m"], 1)
        for surf in list(dstats["staze_m"].keys()):
            dstats["staze_m"][surf] = round(dstats["staze_m"][surf], 1)

    # convenience derived stats
    trasa_m = stats["trasa_km"] * 1000.0
    staze_total = sum(stats["staze"].values())
    stats["staze"]["total_m"] = round(staze_total, 1)
    stats["staze"]["asfalt_pct"] = round(100 * stats["staze"]["asfalt_m"] / staze_total, 1) if staze_total else 0
    stats["staze"]["zemljana_pct"] = round(100 * stats["staze"]["zemljana_m"] / staze_total, 1) if staze_total else 0
    stats["staze"]["popločana_pct"] = round(100 * stats["staze"]["popločana_m"] / staze_total, 1) if staze_total else 0
    # round meter values for display
    for k in list(stats["staze"].keys()):
        if k.endswith("_m"):
            stats["staze"][k] = round(stats["staze"][k], 1)
    for k in stats["zelena_linije_m"]:
        stats["zelena_linije_m"][k] = round(stats["zelena_linije_m"][k], 1)

    stats["density"] = {
        "osvetljenje_per_km": round(stats["counts"]["osvetljenje"] / stats["trasa_km"], 2) if stats["trasa_km"] else 0,
        "klupe_per_km": round(stats["counts"]["klupe"] / stats["trasa_km"], 2) if stats["trasa_km"] else 0,
        "prekidi_per_km": round(stats["counts"]["prekidi"] / stats["trasa_km"], 2) if stats["trasa_km"] else 0,
        "osvetljenje_m_per_lamp": round(trasa_m / stats["counts"]["osvetljenje"], 0) if stats["counts"]["osvetljenje"] else 0,
        "klupe_m_per_klupa": round(trasa_m / stats["counts"]["klupe"], 0) if stats["counts"]["klupe"] else 0,
        "prekidi_m_per_prekid": round(trasa_m / stats["counts"]["prekidi"], 0) if stats["counts"]["prekidi"] else 0,
    }

    stats["trasa_km"] = round(stats["trasa_km"], 2)

    # elevation profile (cache aware)
    if trasa_coords:
        elev = compute_or_load_elevation(trasa_coords, deonice)
        stats["elevation"] = {
            "step_m": elev.get("step_m"),
            "totals": elev.get("totals", {}),
            "by_deonica": elev.get("by_deonica", {}),
        }

        # land cover (ESA WorldCover 2021) na istom 50m sampling-u kao elevation
        samples = sample_line(trasa_coords, ELEV_STEP_M)
        elev_profile = elev.get("profile", [])
        sample_points = []
        for (lon, lat, m), ep in zip(samples, elev_profile):
            sample_points.append({
                "lon": lon, "lat": lat,
                "km": ep["km"],
                "deonica": ep.get("deonica"),
            })
        lc = worldcover.compute_or_load(
            sample_points,
            os.path.join(OUT_DIR, "landcover.json"),
            os.path.join(OUT_DIR, ".cache", "worldcover"),
            step_m=ELEV_STEP_M,
        )
        if lc:
            stats["landcover"] = {
                "zoom": lc.get("zoom"),
                "totals_pct": lc.get("totals_pct", {}),
                "by_deonica_pct": lc.get("by_deonica_pct", {}),
                "labels": lc.get("labels", {}),
            }
            stats["shade"] = lc.get("shade")

    with open(os.path.join(OUT_DIR, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print("\nstats.json:")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
