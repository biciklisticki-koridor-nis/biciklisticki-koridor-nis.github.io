#!/usr/bin/env python3
"""Ulična mreža za analizu 2 (LTS) — ekstrakt iz Geofabrik PBF-a Srbije.

Overpass se ovde ne koristi: za mrežu celog zahvata (osa ± 3 km, sve klase
puteva, sa referencama čvorova za topologiju) javni Overpass vraća 502/504 i
izričito poručuje da nije za automatizovanu upotrebu. Geofabrik ekstrakt je
dnevni, pun i proverljiv (md5), a seče se lokalno.

Izlaz je keš u data/.cache/lts/ — JSON sa putevima (tagovi + čvorovi sa
koordinatama), čvorovima signalizacije i prelaza, i linijama barijera (reka,
kanal, pruga) koje služe samo da se stanovnik ne „prikači" za ulicu preko
Nišave ili pruge. Keš je vezan za bbox i za
datum PBF-a, pa se ne meša sa starim stanjem mape.

Izvor: OpenStreetMap saradnici, Geofabrik (ODbL).
"""
import hashlib
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(ROOT, "data", ".cache", "lts")
PBF_URL = "https://download.geofabrik.de/europe/serbia-latest.osm.pbf"
PBF_FILE = os.path.join(CACHE_DIR, "pbf", "serbia-latest.osm.pbf")

# Tagovi koji ulaze u klasifikaciju; ostali se ne čuvaju da keš ostane mali.
KEEP_TAGS = {
    "highway", "name", "maxspeed", "lanes", "lanes:forward", "lanes:backward",
    "oneway", "oneway:bicycle", "junction", "bicycle", "access", "motor_vehicle",
    "foot", "footway", "service", "cycleway", "cycleway:left", "cycleway:right",
    "cycleway:both", "parking:lane", "parking:lane:both", "parking:lane:left",
    "parking:lane:right", "parking:both", "parking:left", "parking:right",
    "lane_markings", "bridge", "tunnel", "layer", "surface", "sidewalk",
    "motorroad", "construction", "area", "crossing", "crossing:island",
    "crossing:signals", "segregated", "width",
}
SKIP_HW = {"proposed", "abandoned", "razed", "platform", "raceway",
           "bus_guideway", "corridor", "elevator", "via_ferrata", "escape",
           "emergency_bay", "rest_area", "services", "bus_stop", "no"}
NODE_KEEP = {"traffic_signals", "crossing", "stop", "give_way", "mini_roundabout"}
BARRIER_WATER = {"river", "canal"}
BARRIER_RAIL = {"rail"}


# Podiže se kad se menja šta ekstrakt čuva, da stari keš ne prođe kao nov.
EXTRACT_VERSION = 2


def ensure_pbf():
    if os.path.exists(PBF_FILE):
        return PBF_FILE
    os.makedirs(os.path.dirname(PBF_FILE), exist_ok=True)
    print(f"  Preuzimam {PBF_URL} (~240 MB)...", flush=True)
    tmp = PBF_FILE + ".part"
    req = urllib.request.Request(PBF_URL, headers={
        "User-Agent": "biciklisticki-koridor/1.0 (github pages)"})
    with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    # md5 sa Geofabrika — bez provere bi pola fajla izgledalo kao cela mapa
    with urllib.request.urlopen(PBF_URL + ".md5", timeout=60) as r:
        want = r.read().decode().split()[0]
    h = hashlib.md5()
    with open(tmp, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != want:
        os.remove(tmp)
        raise SystemExit("! PBF md5 se ne poklapa — preuzimanje oštećeno")
    os.replace(tmp, PBF_FILE)
    return PBF_FILE


def pbf_stamp(path):
    """Datum stanja mape iz zaglavlja PBF-a (osmosis_replication_timestamp)."""
    import osmium
    hdr = osmium.io.Reader(path, osmium.osm.osm_entity_bits.NOTHING).header()
    ts = hdr.get("osmosis_replication_timestamp") or ""
    return ts[:10] or "nepoznat"


def extract(bbox):
    """Putevi i čvorovi signalizacije u bbox-u (s, w, n, e). Keširano."""
    import osmium

    pbf = ensure_pbf()
    stamp = pbf_stamp(pbf)
    s, w, n, e = bbox
    key = f"{s:.4f}_{w:.4f}_{n:.4f}_{e:.4f}_{stamp}"
    cache = os.path.join(CACHE_DIR, f"mreza_v{EXTRACT_VERSION}_{key}.json")
    if os.path.exists(cache):
        with open(cache) as f:
            data = json.load(f)
        print(f"  OSM keš ({stamp}): {len(data['ways'])} puteva, "
              f"{len(data['nodes'])} čvorova signalizacije")
        return data

    def inside(lat, lon):
        return s <= lat <= n and w <= lon <= e

    ways, nodes, barriers = [], [], []

    class H(osmium.SimpleHandler):
        def node(self, nd):
            hw = nd.tags.get("highway")
            cr = nd.tags.get("crossing")
            if hw not in NODE_KEEP and cr is None:
                return
            if not nd.location.valid():
                return
            lat, lon = nd.location.lat, nd.location.lon
            if inside(lat, lon):
                nodes.append({"id": nd.id, "lat": round(lat, 7),
                              "lon": round(lon, 7),
                              "tags": {k: v for k, v in nd.tags
                                       if k in KEEP_TAGS or k == "highway"}})

        def way(self, wy):
            hw = wy.tags.get("highway")
            barrier = (wy.tags.get("waterway") in BARRIER_WATER
                       or (wy.tags.get("railway") in BARRIER_RAIL
                           and wy.tags.get("service") is None))
            if barrier and hw is None:
                try:
                    pts = [(nd.location.lat, nd.location.lon) for nd in wy.nodes]
                except osmium.InvalidLocationError:
                    return
                if any(inside(la, lo) for la, lo in pts):
                    barriers.append({
                        "id": wy.id,
                        "tip": wy.tags.get("waterway") or "pruga",
                        "name": wy.tags.get("name"),
                        "coords": [[round(lo, 7), round(la, 7)]
                                   for la, lo in pts]})
                return
            if hw is None or hw in SKIP_HW:
                return
            try:
                pts = [(nd.ref, nd.location.lat, nd.location.lon)
                       for nd in wy.nodes]
            except osmium.InvalidLocationError:
                return
            if not any(inside(la, lo) for _, la, lo in pts):
                return
            ways.append({"id": wy.id,
                         "tags": {k: v for k, v in wy.tags if k in KEEP_TAGS},
                         "nodes": [r for r, _, _ in pts],
                         "coords": [[round(lo, 7), round(la, 7)]
                                    for _, la, lo in pts]})

    print(f"  Sečem {os.path.basename(pbf)} ({stamp}) na zahvat...", flush=True)
    H().apply_file(pbf, locations=True, idx="flex_mem")
    data = {"stamp": stamp, "bbox": bbox, "ways": ways, "nodes": nodes,
            "barriers": barriers}
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache, "w") as f:
        json.dump(data, f)
    print(f"  OSM ({stamp}): {len(ways)} puteva, {len(nodes)} čvorova "
          f"signalizacije, {len(barriers)} linija barijera")
    return data


if __name__ == "__main__":
    bb = tuple(float(x) for x in sys.argv[1:5])
    extract(bb)
