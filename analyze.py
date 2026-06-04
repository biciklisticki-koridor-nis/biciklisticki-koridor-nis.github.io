#!/usr/bin/env python3
"""Analyze KML and print per-folder statistics + per-name counts."""
import xml.etree.ElementTree as ET
import math
import re
from collections import Counter

KML_NS = "{http://www.opengis.net/kml/2.2}"
KML_FILE = "/home/zchira/git/biciklisticki-koridor/koridor_data.kml"


def parse_coords(text):
    pts = []
    for chunk in text.strip().split():
        parts = chunk.split(",")
        if len(parts) >= 2:
            lon, lat = float(parts[0]), float(parts[1])
            pts.append((lon, lat))
    return pts


def haversine_m(lon1, lat1, lon2, lat2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def line_length_m(pts):
    return sum(
        haversine_m(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
        for i in range(len(pts) - 1)
    )


def normalize(name):
    """Normalize a placemark name for grouping."""
    n = (name or "").strip().lower()
    n = re.sub(r"\s+", " ", n)
    return n


def main():
    tree = ET.parse(KML_FILE)
    root = tree.getroot()

    folders = root.findall(f".//{KML_NS}Folder")
    print(f"Folders: {len(folders)}\n")

    for folder in folders:
        fname_el = folder.find(f"{KML_NS}name")
        fname = fname_el.text if fname_el is not None else "(no name)"
        print("=" * 70)
        print(f"FOLDER: {fname}")
        print("=" * 70)

        placemarks = folder.findall(f"{KML_NS}Placemark")
        n_points = n_lines = n_polys = 0
        total_line_m = 0.0
        line_lengths_by_name = {}
        names = []

        for pm in placemarks:
            nm_el = pm.find(f"{KML_NS}name")
            nm = nm_el.text if nm_el is not None else ""
            names.append(normalize(nm))

            pt = pm.find(f".//{KML_NS}Point/{KML_NS}coordinates")
            ls = pm.find(f".//{KML_NS}LineString/{KML_NS}coordinates")
            pg = pm.find(f".//{KML_NS}Polygon")

            if pt is not None:
                n_points += 1
            if ls is not None:
                n_lines += 1
                pts = parse_coords(ls.text)
                L = line_length_m(pts)
                total_line_m += L
                key = normalize(nm)
                line_lengths_by_name[key] = line_lengths_by_name.get(key, 0.0) + L
            if pg is not None:
                n_polys += 1

        print(f"Placemarks: {len(placemarks)}  (points={n_points}, lines={n_lines}, polygons={n_polys})")
        if n_lines:
            print(f"Total line length: {total_line_m:.0f} m  ({total_line_m/1000:.2f} km)")

        counts = Counter(names)
        print("\nTop names (normalized):")
        for nm, c in counts.most_common(20):
            extra = ""
            if nm in line_lengths_by_name:
                extra = f"  [line: {line_lengths_by_name[nm]:.0f} m]"
            print(f"  {c:4d}x  {nm!r}{extra}")

        if len(counts) > 20:
            print(f"  ... +{len(counts) - 20} more unique names")
        print()


if __name__ == "__main__":
    main()
