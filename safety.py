#!/usr/bin/env python3
"""Bezbednosni audit koridora (analiza 8) — izveden iz terenskih podataka.

Tri kategorije, sve iz postojećih GeoJSON fajlova — nema novih API poziva:

  8.1 Infrastrukturna bezbednost
      Stanje površina (loše/srednje/dobro/deponija) iz stanja.geojson.
      Stepenice kao prepreka za bicikle po deonici.

  8.2 Lična bezbednost
      Zone bez osvetljenja: segmenti duž trase gde između dve uzastopne
      svetiljke ima više od DARK_GAP_M metara. Koristi biciklističku osu
      kao referencu.

  8.3 Saobraćajni konflikti
      Tačke iz prekidi.geojson klasifikovane po tipu konflikta:
      - parking (rampa, koso parkiranje, divo parkiranje)
      - prelaz (most, promena puta, nedostatak pešačkog prelaza)

Izlaz: data/safety.json
"""
import json
import math
import os
import re

from koridor import (DEONICE_FILE, M_PER_DEG_LAT, M_PER_DEG_LON, PROJ_MAX_M,
                     ROOT, build_samples, load_mreza, resample_line)

OUT_FILE = os.path.join(ROOT, "data", "safety.json")

STANJA_FILE    = os.path.join(ROOT, "data", "stanja.geojson")
OSVETLJENJE_FILE = os.path.join(ROOT, "data", "osvetljenje.geojson")
PREKIDI_FILE   = os.path.join(ROOT, "data", "prekidi.geojson")
STEPENICE_FILE = os.path.join(ROOT, "data", "stepenice.geojson")

DARK_GAP_M = 200.0   # gap između svetiljki > ovoga → tamna zona


# ── geometry helpers ──────────────────────────────────────────────────────────

def planar(lon, lat):
    return lon * M_PER_DEG_LON, lat * M_PER_DEG_LAT


def build_axis_index(axis):
    """Spatial grid nad tačkama ose — za brzu projekciju."""
    pts = resample_line(axis)
    cell = PROJ_MAX_M
    grid = {}
    for lon, lat, m in pts:
        x, y = planar(lon, lat)
        grid.setdefault((int(x // cell), int(y // cell)), []).append((x, y, m))
    return grid, cell, pts


def project_onto_axis(lon, lat, grid, cell):
    """Vraća km od početka ose, ili None ako je tačka van PROJ_MAX_M."""
    x, y = planar(lon, lat)
    cx, cy = int(x // cell), int(y // cell)
    best_d, best_m = PROJ_MAX_M, None
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for px, py, m in grid.get((cx + dx, cy + dy), ()):
                d = math.hypot(px - x, py - y)
                if d < best_d:
                    best_d, best_m = d, m
    return best_m / 1000.0 if best_m is not None else None


def km_to_lonlat(km, axis_pts):
    """Najbliža tačka ose za zadatu kilometražu."""
    m = km * 1000
    best = min(axis_pts, key=lambda p: abs(p[2] - m))
    return best[0], best[1]


def point_in_poly(lon, lat, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            xc = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < xc:
                inside = not inside
        j = i
    return inside


def load_deonice_polys():
    with open(DEONICE_FILE) as f:
        gj = json.load(f)
    return [(feat["properties"]["name"], feat["geometry"]["coordinates"][0])
            for feat in gj["features"]]


def assign_deonica(lon, lat, polys):
    return next((n for n, ring in polys if point_in_poly(lon, lat, ring)), None)


def load_geojson(path):
    with open(path) as f:
        return json.load(f)["features"]


# ── 8.2 tamne zone ────────────────────────────────────────────────────────────

def compute_dark_zones(axis):
    grid, cell, axis_pts = build_axis_index(axis)
    total_km = axis_pts[-1][2] / 1000.0
    polys = load_deonice_polys()

    # Projekcija svetiljki na osu
    kms = []
    for feat in load_geojson(OSVETLJENJE_FILE):
        lon, lat = feat["geometry"]["coordinates"][:2]
        km = project_onto_axis(lon, lat, grid, cell)
        if km is not None:
            kms.append(km)
    kms.sort()

    # Presečne tačke: [0, ...kms..., total_km]
    anchors = [0.0] + kms + [total_km]

    dark_zones = []
    for i in range(len(anchors) - 1):
        km_od = anchors[i]
        km_do = anchors[i + 1]
        gap_m = (km_do - km_od) * 1000

        # Preskočimo intervale između dve svetiljke koji su kratki
        # (između 0 i prve svetiljke, ili između dve uzastopne svetiljke,
        # ili između poslednje i kraja trase)
        if gap_m <= DARK_GAP_M:
            continue

        mid_km = (km_od + km_do) / 2
        lon, lat = km_to_lonlat(mid_km, axis_pts)
        deonica = assign_deonica(lon, lat, polys)

        dark_zones.append({
            "km_od": round(km_od, 3),
            "km_do": round(km_do, 3),
            "duzina_m": round(gap_m),
            "deonica": deonica,
        })

    total_dark_m = sum(z["duzina_m"] for z in dark_zones)

    return {
        "prag_m": DARK_GAP_M,
        "ukupno_tamnih_m": round(total_dark_m),
        "tamno_pct": round(total_dark_m / (total_km * 10), 1),
        "najduza_zona_m": max((z["duzina_m"] for z in dark_zones), default=0),
        "broj_zona": len(dark_zones),
        "zone": dark_zones,
    }


# ── 8.1 stanja infrastrukture ─────────────────────────────────────────────────

STANJE_VRSTE = ["loše", "srednje", "dobro", "deponija", "ostalo"]


def compute_stanja(axis):
    grid, cell, _ = build_axis_index(axis)
    tacke = []
    by_deonica = {}

    for feat in load_geojson(STANJA_FILE):
        props = feat["properties"]
        stanje = props.get("stanje", "ostalo")
        deonica = props.get("deonica")
        geom = feat["geometry"]

        if geom["type"] == "LineString":
            coords = geom["coordinates"]
            mid = coords[len(coords) // 2]
            lon, lat = mid[0], mid[1]
        else:
            lon, lat = geom["coordinates"][0], geom["coordinates"][1]

        km = project_onto_axis(lon, lat, grid, cell)

        entry = {
            "stanje": stanje,
            "name": props.get("name", ""),
            "lon": lon,
            "lat": lat,
            "km": round(km, 3) if km is not None else None,
            "deonica": deonica,
        }
        if props.get("images"):
            entry["images"] = props["images"]
        if props.get("duzina_m"):
            entry["duzina_m"] = props["duzina_m"]

        tacke.append(entry)

        if deonica:
            bd = by_deonica.setdefault(deonica, {v: 0 for v in STANJE_VRSTE})
            bd[stanje] = bd.get(stanje, 0) + 1

    counts = {v: 0 for v in STANJE_VRSTE}
    for t in tacke:
        counts[t["stanje"]] = counts.get(t["stanje"], 0) + 1

    return {
        "ukupno": len(tacke),
        "po_tipu": counts,
        "po_deonici": by_deonica,
        "tacke": tacke,
    }


# ── 8.3 saobraćajni konflikti ─────────────────────────────────────────────────

PARKING_RE = re.compile(
    r"parking|koso\s*park|rampa\s*za\s*park|divo\s*park", re.IGNORECASE
)
CROSSING_TIPS = {"most_prelaz", "promena_puta"}
CROSSING_RE = re.compile(
    r"prelaz|nema\s*pesh|most\s+|bridge", re.IGNORECASE
)


def compute_konflikti():
    parking = []
    prelazi = []

    for feat in load_geojson(PREKIDI_FILE):
        if feat["geometry"]["type"] != "Point":
            continue
        props = feat["properties"]
        name = props.get("name", "")
        tip = props.get("tip", "ostalo")
        deonica = props.get("deonica")
        lon, lat = feat["geometry"]["coordinates"][:2]

        entry = {
            "name": name,
            "tip": tip,
            "lon": lon,
            "lat": lat,
            "deonica": deonica,
        }
        if props.get("images"):
            entry["images"] = props["images"]

        if PARKING_RE.search(name):
            entry["konflikt_tip"] = "parking"
            parking.append(entry)
        elif tip in CROSSING_TIPS or CROSSING_RE.search(name):
            entry["konflikt_tip"] = "prelaz"
            prelazi.append(entry)

    by_deonica = {}
    for e in parking + prelazi:
        d = e.get("deonica") or "—"
        bd = by_deonica.setdefault(d, {"parking": 0, "prelaz": 0})
        bd[e["konflikt_tip"]] += 1

    return {
        "ukupno_parking": len(parking),
        "ukupno_prelaza": len(prelazi),
        "po_deonici": by_deonica,
        "parking": parking,
        "prelazi": prelazi,
    }


# ── stepenice po deonici + gustina ───────────────────────────────────────────

BIN_M = 500       # širina bins za histogram gustine
STEP_MAX_M = 100.0  # veći prag — stepenice su na bedemima, dalje od bici ose


def build_all_staze_index(axis, chains):
    """Spatial grid nad sirovim uzorcima SVIH staza, svaki sa bici-axis km.

    Ne koristi build_samples jer on odbacuje tačke >PROJ_MAX_M od bici ose.
    Ovde uzorkujemo sve lance direktno i projektujemo na osu bez gornje granice.
    """
    # Axis grid za projekciju — bez ograničenja rastojanja
    axis_pts = resample_line(axis)
    axis_cell = PROJ_MAX_M
    axis_grid = {}
    for alo, ala, m in axis_pts:
        ax, ay = planar(alo, ala)
        axis_grid.setdefault((int(ax // axis_cell), int(ay // axis_cell)), []).append((ax, ay, m))

    # Flat list for unconstrained nearest-neighbor search
    axis_flat = [(ax, ay, m) for cell_pts in axis_grid.values() for ax, ay, m in cell_pts]

    def project_unconstrained(lon, lat):
        """Projektuje na osu bez ikakve gornje granice rastojanja."""
        x, y = planar(lon, lat)
        best_d, best_m = float("inf"), None
        for px, py, m in axis_flat:
            d = math.hypot(px - x, py - y)
            if d < best_d:
                best_d, best_m = d, m
        return best_m / 1000.0 if best_m is not None else None

    # Index nad svim sirovim tačkama svih lanaca
    cell = STEP_MAX_M
    grid = {}
    for chain_list in chains.values():
        for chain in chain_list:
            for lon, lat, _ in resample_line(chain):
                km = project_unconstrained(lon, lat)
                if km is None:
                    continue
                x, y = planar(lon, lat)
                grid.setdefault((int(x // cell), int(y // cell)), []).append((x, y, km))

    return grid, cell


def project_all_staze(lon, lat, grid, cell, max_d=STEP_MAX_M):
    """Projektuje tačku na najbliži uzorak bilo koje staze; vraća bici km."""
    x, y = planar(lon, lat)
    cx, cy = int(x // cell), int(y // cell)
    best_d, best_km = max_d, None
    for dx in (-2, -1, 0, 1, 2):
        for dy in (-2, -1, 0, 1, 2):
            for px, py, km in grid.get((cx + dx, cy + dy), ()):
                d = math.hypot(px - x, py - y)
                if d < best_d:
                    best_d, best_km = d, km
    return best_km


def compute_stepenice(axis, chains, osa_km):
    grid, cell = build_all_staze_index(axis, chains)
    by_deonica = {}
    n_bins = math.ceil(osa_km * 1000 / BIN_M)
    bins = [0] * n_bins
    missed = 0

    for feat in load_geojson(STEPENICE_FILE):
        props = feat["properties"]
        deonica = props.get("deonica")
        lon, lat = feat["geometry"]["coordinates"][:2]

        if deonica:
            by_deonica[deonica] = by_deonica.get(deonica, 0) + 1

        km = project_all_staze(lon, lat, grid, cell)
        if km is not None:
            b = int(km * 1000 / BIN_M)
            if 0 <= b < n_bins:
                bins[b] += 1
        else:
            missed += 1

    histogram = [
        {
            "km_od": round(i * BIN_M / 1000, 3),
            "km_do": round(min((i + 1) * BIN_M / 1000, osa_km), 3),
            "count": bins[i],
        }
        for i in range(n_bins)
    ]

    return {"po_deonici": by_deonica, "histogram": histogram,
            "bin_m": BIN_M, "missed": missed}


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("Učitavam geometriju koridora...")
    axis, chains = load_mreza()

    print("8.2  Tamne zone...")
    tamne = compute_dark_zones(axis)
    print(f"     {tamne['broj_zona']} zona, ukupno {tamne['ukupno_tamnih_m']} m "
          f"({tamne['tamno_pct']} %), najduža {tamne['najduza_zona_m']} m")

    print("8.1  Stanja infrastrukture...")
    stanja = compute_stanja(axis)
    print(f"     {stanja['ukupno']} zapisa — {stanja['po_tipu']}")

    print("8.3  Saobraćajni konflikti...")
    konflikti = compute_konflikti()
    print(f"     {konflikti['ukupno_parking']} parking-konflikta, "
          f"{konflikti['ukupno_prelaza']} prelaza")

    axis_pts = resample_line(axis)
    osa_km = round(axis_pts[-1][2] / 1000.0, 3)

    print("     Stepenice po deonici + histogram...")
    stepenice = compute_stepenice(axis, chains, osa_km)
    print(f"     po deonici: {stepenice['po_deonici']}")
    print(f"     bins (count>0): {[(b['km_od'], b['count']) for b in stepenice['histogram'] if b['count'] > 0]}")
    print(f"     van domašaja: {stepenice['missed']}")

    out = {
        "schema": 1,
        "osa_km": osa_km,
        "tamne_zone": tamne,
        "stanja": stanja,
        "konflikti": konflikti,
        "stepenice_po_deonici": stepenice,
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nZapisano: {OUT_FILE}")


if __name__ == "__main__":
    main()
