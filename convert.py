#!/usr/bin/env python3
"""Convert KML to per-layer GeoJSON + stats.json.

Reads koridor_data.kml, normalizes names (handles typos), categorizes
placemarks into logical layers, writes GeoJSON files into data/.
"""
import json
import math
import os
import re
import xml.etree.ElementTree as ET

KML_NS = "{http://www.opengis.net/kml/2.2}"
ROOT = os.path.dirname(os.path.abspath(__file__))
KML_FILE = os.path.join(ROOT, "koridor_data.kml")
OUT_DIR = os.path.join(ROOT, "data")


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


# ---------- KML iteration ----------

def folder_placemarks(folder):
    out = []
    for pm in folder.findall(f"{KML_NS}Placemark"):
        nm_el = pm.find(f"{KML_NS}name")
        nm = nm_el.text if nm_el is not None else ""
        pt = pm.find(f".//{KML_NS}Point/{KML_NS}coordinates")
        ls = pm.find(f".//{KML_NS}LineString/{KML_NS}coordinates")
        if pt is not None:
            coords = parse_coords(pt.text)
            geom = {"type": "Point", "coordinates": list(coords[0])} if coords else None
        elif ls is not None:
            coords = parse_coords(ls.text)
            geom = {"type": "LineString", "coordinates": [list(c) for c in coords]} if coords else None
        else:
            geom = None
        out.append({"name": nm, "norm": norm(nm), "geom": geom, "coords": coords if (pt is not None or ls is not None) else []})
    return out


# ---------- feature factories ----------

def feature(geom, props):
    return {"type": "Feature", "geometry": geom, "properties": props}


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
    }

    for folder in folders:
        fname = (folder.find(f"{KML_NS}name").text or "").strip()
        pms = folder_placemarks(folder)
        stats["total_placemarks"] += len(pms)
        stats["by_layer"][fname] = len(pms)

        if "Indicaciones" in fname:
            for p in pms:
                if p["geom"] and p["geom"]["type"] == "LineString":
                    out["trasa"].append(feature(p["geom"], {"name": "Glavna trasa koridora"}))
                    stats["trasa_km"] = line_length_m(p["coords"]) / 1000.0

        elif "Zelena" in fname:
            for p in pms:
                if not p["geom"]:
                    continue
                cat = canonical_green(p["norm"])
                props = {"name": p["name"], "kategorija": cat}
                out["zelena"].append(feature(p["geom"], props))
                if p["geom"]["type"] == "LineString" and cat in ("visoka_vegetacija", "niska_vegetacija"):
                    stats["zelena_linije_m"][cat] += line_length_m(p["coords"])

        elif "Prekid" in fname:
            for p in pms:
                if p["geom"]:
                    out["prekidi"].append(feature(p["geom"], {"name": p["name"]}))

        elif "Stepenice i rampe" in fname:
            for p in pms:
                if not p["geom"]:
                    continue
                n = p["norm"]
                if p["geom"]["type"] == "LineString":
                    surf = canonical_surface(n)
                    L = line_length_m(p["coords"])
                    out["staze"].append(feature(p["geom"], {"name": p["name"], "podloga": surf, "duzina_m": round(L, 1)}))
                    stats["staze"][f"{surf}_m"] = stats["staze"].get(f"{surf}_m", 0.0) + L
                else:
                    # point
                    if "stepenic" in n:
                        out["stepenice"].append(feature(p["geom"], {"name": p["name"]}))
                    elif "rampa" in n or "rampe" in n:
                        out["rampe"].append(feature(p["geom"], {"name": p["name"]}))
                    else:
                        # uncommon (e.g. "peshachki most") — keep in stepenice bucket as misc
                        out["stepenice"].append(feature(p["geom"], {"name": p["name"]}))

        elif "Urbana oprema" in fname:
            for p in pms:
                if not p["geom"]:
                    continue
                cat = canonical_urban(p["norm"])
                feat = feature(p["geom"], {"name": p["name"], "kategorija": cat})
                if cat in ("osvetljenje", "klupe", "kante", "letnjikovci", "sport"):
                    out[cat].append(feat)
                else:
                    out["urbana_ostalo"].append(feat)

        elif "Stanja" in fname:
            for p in pms:
                if not p["geom"]:
                    continue
                st = canonical_state(p["norm"])
                props = {"name": p["name"], "stanje": st}
                if p["geom"]["type"] == "LineString":
                    props["duzina_m"] = round(line_length_m(p["coords"]), 1)
                out["stanja"].append(feature(p["geom"], props))

        elif "Javni socijalni" in fname or "urbani dzepovi" in fname.lower():
            for p in pms:
                if p["geom"]:
                    out["socijalni"].append(feature(p["geom"], {"name": p["name"]}))

    # write all layers
    print("Layers written:")
    for k, feats in out.items():
        write_geojson(k, feats)
        stats["counts"][k] = len(feats)

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

    with open(os.path.join(OUT_DIR, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print("\nstats.json:")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
