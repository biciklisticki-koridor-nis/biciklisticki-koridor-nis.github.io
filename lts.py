#!/usr/bin/env python3
"""Nivo saobraćajnog stresa — LTS (analiza 2).

Metod je Mekuria, Furth i Nixon (2012), „Low-Stress Bicycling and Network
Connectivity", MTI Report 11-19. Ocena 1–4 se čita iz tabela, a segment
dobija NAJGORU ocenu po bilo kojoj dimenziji (weakest link) — nema težina
koje bismo mi birali.

Zašto originalne tabele, a ne v2.2 (Furth, maj 2022): v2.2 traži dnevni
protok vozila (ADT) za svaku ulicu, a za Niš takav podatak ne postoji ni u
jednom javnom izvoru. Original koristi broj traka kao zamenu za protok i to je
jedino što se ovde može pošteno primeniti. Brzine su u km/h; granice pojaseva
su sredine između vrednosti iz tabela (25/30/35/40 mph), preračunate.

Zašto ovo nije samo ocena keja: po tabeli 1 samostalna staza ima LTS 1 po
definiciji, a 73 % ose je dalje od 50 m od bilo kog puta. Bukvalan LTS bi bio
jedna boja. Stres na ovom koridoru je na ULAZU — u ulicama kojima se do keja
stiže i u prelazima preko njih. Zato se računa i povezanost niskog stresa
(isti izvor, poglavlje 5): koliki deo stanovnika u zahvatu stiže do keja a da
nijednom ne pređe zadati nivo stresa, uz obilazak najviše 25 % duži od
najkraćeg puta.

Četiri sloja izlaza:
  osa       — gde osa zaista ide ulicom i koji su prelazi u nivou
  pristupi  — 32 mapirana kraka: kakva je ulica na koju izlaze
  povezanost— stanovnici (WorldPop) do 2 km mrežnog rastojanja od keja
  barijere  — prelazi i potezi čije bi smirivanje priključilo najviše ljudi

Izvori: OpenStreetMap (Geofabrik ekstrakt, ODbL), WorldPop R2025A 2025 100 m
constrained (CC BY 4.0), terensko mapiranje koridora.
"""
import hashlib
import heapq
import time
import json
import math
import os
import sys
import urllib.request
from collections import Counter, defaultdict

import numpy as np

from koridor import (DEONICE_FILE, MREZA_FILE, ROOT, load_mreza, planar_xy,
                     prepare)
from lts_osm import extract

OUT_FILE = os.path.join(ROOT, "data", "lts.json")
NET_FILE = os.path.join(ROOT, "data", "lts_mreza.json")
CACHE_DIR = os.path.join(ROOT, "data", ".cache", "lts")
POP_URL = ("https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/"
           "2025/SRB/v1/100m/constrained/srb_pop_2025_CN_100m_R2025A_v1.tif")
POP_FILE = os.path.join(CACHE_DIR, "pop", os.path.basename(POP_URL))
STEPENICE_FILE = os.path.join(ROOT, "data", "stepenice.geojson")
PREKIDI_FILE = os.path.join(ROOT, "data", "prekidi.geojson")

LTS_SCHEMA = 1

# ---------- parametri ----------

PAD_LAT, PAD_LON = 0.03, 0.04   # ~3,3 km oko ose — rutiranje ne sme da udari u ivicu
CATCH_M = 2000                  # glavni zahvat: ~8 min bicikla do keja
CATCH_RADII = (1000, 2000, 3000)
DETOUR = 1.25                   # Mekuria et al. 2012: obilazak do 25 %
DETOUR_SENS = 1.50              # osetljivost — da se vidi koliko zavisi od praga
SNAP_M = 150.0                  # ćelija stanovništva → najbliži čvorovi mreže
SNAP_K = 10
CORR_SNAP_M = 12.0              # čvor OSM mreže koji leži na koridoru
KRAK_SNAP_M = 25.0              # spoljni kraj kraka → ulica
AXIS_STREET_M = 8.0             # osa „ide ulicom" ako je ulica ovoliko blizu...
AXIS_PARALLEL_DEG = 30.0        # ...i paralelna
SIGNAL_R_M = 25.0               # semafor ovoliko blizu čvora = signalisan prelaz
ISLAND_R_M = 15.0
DIVIDED_R_M = 40.0              # dva jednosmerna kolovoza istog imena = bulevar
URBAN_KMH = 50                  # ZOBS: u naselju 50 km/h kad znak ne kaže drugo
STAIRS_R_M = 15.0
PREKID_R_M = 25.0
CUTOFF_M = max(CATCH_RADII) * DETOUR_SENS + SNAP_M
BLOCK_MAX_M = 600.0             # duži potezi nisu „jedna intervencija"
TOP_BARIJERE = 10

MOTOR = {"motorway", "motorway_link", "trunk", "trunk_link", "primary",
         "primary_link", "secondary", "secondary_link", "tertiary",
         "tertiary_link", "unclassified", "residential", "living_street",
         "service", "road"}
CROSSABLE = MOTOR - {"motorway", "motorway_link"}
BIKE_OK = {"yes", "designated", "permissive"}
CYCLEWAY_KEYS = ("cycleway", "cycleway:left", "cycleway:right", "cycleway:both")
LOW_VOLUME = {"residential", "living_street", "service", "track"}

# Tabele u metričkom obliku. Kolone: ≤3 / 4–5 / 6+ traka (ukupno).
# Tabela 4 (mešani saobraćaj); vrsta sa dve vrednosti: niža za ulice bez
# središnje linije i sa malim protokom — proxy je klasa ulice.
T4 = [
    {"do_kmh": 44, "vrednosti": [[1, 2], 3, 4]},   # do 25 mph
    {"do_kmh": 52, "vrednosti": [[2, 3], 4, 4]},   # 30 mph
    {"do_kmh": 999, "vrednosti": [4, 4, 4]},       # 35+ mph
]
# Tabela 6 (prelaz bez semafora), a: bez ostrva, b: sa ostrvom.
T6_BANDS = [44, 52, 60, 999]                       # do 25 / 30 / 35 / 40+ mph
T6A = [[1, 2, 4], [1, 2, 4], [2, 3, 4], [3, 4, 4]]
T6B = [[1, 1, 2], [1, 2, 3], [2, 3, 4], [3, 4, 4]]


# ---------- pomoćno ----------

def bbox_of(axis):
    lons = [c[0] for c in axis]
    lats = [c[1] for c in axis]
    return (min(lats) - PAD_LAT, min(lons) - PAD_LON,
            max(lats) + PAD_LAT, max(lons) + PAD_LON)


def bearing(a, b):
    """Azimut u stepenima (0 = sever, u smeru kazaljke) u lokalnoj ravni."""
    return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])) % 360.0


def ang_diff(a, b):
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx
                                               + (p[1] - a[1]) * dy) / ll))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def seg_intersect(p1, p2, p3, p4):
    """Parametar t na p1–p2 gde seče p3–p4, ili None."""
    d = (p2[0] - p1[0]) * (p4[1] - p3[1]) - (p2[1] - p1[1]) * (p4[0] - p3[0])
    if abs(d) < 1e-12:
        return None
    t = ((p3[0] - p1[0]) * (p4[1] - p3[1]) - (p3[1] - p1[1]) * (p4[0] - p3[0])) / d
    u = ((p3[0] - p1[0]) * (p2[1] - p1[1]) - (p3[1] - p1[1]) * (p2[0] - p1[0])) / d
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return t
    return None


class Grid:
    """Prostorni indeks nad tačkama ili segmentima u lokalnoj ravni."""

    def __init__(self, cell):
        self.cell = cell
        self.g = defaultdict(list)

    def add_point(self, p, item):
        self.g[(int(p[0] // self.cell), int(p[1] // self.cell))].append(item)

    def add_seg(self, a, b, item):
        c = self.cell
        for cx in range(int(min(a[0], b[0]) // c), int(max(a[0], b[0]) // c) + 1):
            for cy in range(int(min(a[1], b[1]) // c), int(max(a[1], b[1]) // c) + 1):
                self.g[(cx, cy)].append(item)

    def near(self, p, r):
        c = self.cell
        n = int(r // c) + 1
        cx, cy = int(p[0] // c), int(p[1] // c)
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                yield from self.g.get((cx + i, cy + j), ())

    def along(self, a, b):
        c = self.cell
        seen = set()
        for cx in range(int(min(a[0], b[0]) // c), int(max(a[0], b[0]) // c) + 1):
            for cy in range(int(min(a[1], b[1]) // c), int(max(a[1], b[1]) // c) + 1):
                for it in self.g.get((cx, cy), ()):
                    if id(it) not in seen:
                        seen.add(id(it))
                        yield it


# ---------- atributi ulice ----------

def speed_kmh(tags):
    """(km/h, izvor). Izvor se nosi da se zna koliko je pretpostavki."""
    raw = str(tags.get("maxspeed", "")).strip()
    if raw:
        tok = raw.split()[0].split(";")[0]
        if tok.isdigit():
            v = int(tok)
            return (round(v * 1.609) if "mph" in raw else v), "znak"
        low = raw.lower()
        if low.endswith("urban"):
            return 50, "RS:urban"
        if low.endswith("rural"):
            return 80, "RS:rural"
        if low.endswith("motorway"):
            return 130, "RS:motorway"
        if "living_street" in low or low == "walk":
            return 10, "znak"
    hw = tags.get("highway")
    if hw == "living_street":
        return 10, "zakon"
    if hw in ("motorway", "motorway_link"):
        return 130, "zakon"
    if hw in ("trunk", "trunk_link"):
        return 100, "zakon"
    return URBAN_KMH, "pretpostavka"


def is_oneway(tags):
    return (tags.get("oneway") in ("yes", "1", "true", "-1")
            or tags.get("junction") in ("roundabout", "circular"))


def lanes_of(tags):
    raw = tags.get("lanes")
    if raw:
        tok = str(raw).split(";")[0].strip()
        if tok.isdigit() and int(tok) > 0:
            return int(tok), "tag"
    return (1 if is_oneway(tags) else 2), "pretpostavka"


def street_key(way):
    nm = way["tags"].get("name")
    return ("n:" + nm.strip().lower()) if nm else f"w:{way['id']}"


def find_divided(ways, P):
    """Bulevari mapirani kao dva jednosmerna kolovoza.

    Za prelaz i za vožnju broji se ukupan broj traka oba kolovoza, a razdelno
    ostrvo se priznaje kao ostrvo za pešački prelaz (tabela 6b). Bez ovoga bi
    se bulevar 3+3 ocenio kao ulica od tri trake.
    """
    cand = [w for w in ways
            if w["tags"].get("highway") in ("primary", "secondary", "tertiary",
                                            "trunk")
            and is_oneway(w["tags"]) and w["tags"].get("name")
            and w["tags"].get("junction") not in ("roundabout", "circular")]
    by_name = defaultdict(list)
    for w in cand:
        by_name[w["tags"]["name"]].append(w)
    out = {}
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        grid = Grid(DIVIDED_R_M)
        segs = []
        for w in group:
            pts = P[w["id"]]
            for a, b in zip(pts, pts[1:]):
                s = (w["id"], a, b, bearing(a, b))
                segs.append(s)
                grid.add_seg(a, b, s)
        for w in group:
            pts = P[w["id"]]
            total = matched = 0.0
            partner_lanes = Counter()
            for a, b in zip(pts, pts[1:]):
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                total += L
                mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                br = bearing(a, b)
                for wid, c, d, br2 in grid.near(mid, DIVIDED_R_M):
                    if wid == w["id"] or ang_diff(br, br2) < 135:
                        continue
                    if seg_dist(mid, c, d) <= DIVIDED_R_M:
                        matched += L
                        other = next(x for x in group if x["id"] == wid)
                        partner_lanes[lanes_of(other["tags"])[0]] += 1
                        break
            if total > 0 and matched / total >= 0.3:
                out[w["id"]] = partner_lanes.most_common(1)[0][0]
    return out


# ---------- klasifikacija (tabele 1–4) ----------

def trake(n):
    """1 traka, 2–4 trake, 5+ traka."""
    d, h = n % 10, n % 100
    return f"{n} {'trake' if 2 <= d <= 4 and not 12 <= h <= 14 else 'traka'}"


def lts_mixed(v, n, low):
    row = next(r for r in T4 if v <= r["do_kmh"])
    col = 0 if n <= 3 else (1 if n <= 5 else 2)
    val = row["vrednosti"][col]
    if isinstance(val, list):
        val = val[0] if low else val[1]
    return val


def classify(tags, n_total, divided, speed_bump=0, low_residential=True,
             footways=True):
    """(LTS ili None, pravilo). None = nije deo mreže za bicikl.

    speed_bump se koristi samo za osetljivost: stvarna brzina na bulevarima
    je po pravilu veća od ograničenja, a merenja nemamo.
    """
    hw = tags.get("highway")
    bic = tags.get("bicycle")
    acc = tags.get("access")
    if hw in ("motorway", "motorway_link") or tags.get("motorroad") == "yes":
        return None, "autoput — zabranjen za bicikl"
    if hw == "construction":
        return None, "u izgradnji"
    if hw == "steps":
        return None, "stepenice"
    if hw == "bridleway":
        return None, "jahačka staza"
    if bic in ("no", "use_sidepath"):
        return None, "zabrana za bicikl"
    if acc in ("no", "private") and bic not in BIKE_OK:
        return None, "privatni put"
    if hw == "footway" and tags.get("footway") == "sidewalk" and bic not in BIKE_OK:
        return None, "trotoar — vožnja nije dozvoljena"
    if not footways and hw in ("footway", "pedestrian") and bic not in BIKE_OK:
        return None, "pešačka staza — osetljivost bez njih"
    if hw == "cycleway":
        return 1, "T1: biciklistička staza"
    if hw in ("path", "footway", "pedestrian"):
        return 1, "T1: samostalna staza"
    if any(tags.get(k) == "track" for k in CYCLEWAY_KEYS):
        return 1, "T1: odvojena staza uz kolovoz"
    if tags.get("motor_vehicle") == "no" or (acc == "no" and bic in BIKE_OK):
        return 1, "T1: bez motornih vozila"
    if hw == "living_street":
        return 1, "T4: zona usporenog saobraćaja"
    if hw == "track":
        return 2, "poljski put (BikeOttawa)"
    if hw == "service" and tags.get("service") in ("driveway", "parking_aisle",
                                                   "alley", "drive-through"):
        return 2, "prilaz ili parking (BikeOttawa)"
    v, _ = speed_kmh(tags)
    if hw in ("primary", "secondary", "tertiary", "trunk", "primary_link",
              "secondary_link", "tertiary_link", "trunk_link"):
        v += speed_bump
    low = hw in LOW_VOLUME or tags.get("lane_markings") == "no"
    if not low_residential and hw == "residential" and tags.get("lane_markings") != "no":
        low = False
    lts = lts_mixed(v, n_total, low)
    rule = f"T4: {v} km/h, {trake(n_total)}"
    if any(tags.get(k) in ("lane", "opposite_lane") for k in CYCLEWAY_KEYS):
        # Tabela 3 bez podataka o širini; u zahvatu trenutno nema nijedne
        # obeležene trake, ali grana ostaje da se nova traka ne bi prećutala.
        n_dir = n_total if is_oneway(tags) else max(1, n_total // 2)
        t3 = max(1 if v <= 52 else (3 if v <= 60 else 4),
                 1 if n_dir <= 1 else (2 if divided else 3))
        if t3 < lts:
            return t3, f"T3: traka, {v} km/h"
    return lts, rule


def crossing_lts(v, n, island):
    band = next(i for i, b in enumerate(T6_BANDS) if v <= b)
    col = 0 if n <= 3 else (1 if n <= 5 else 2)
    return (T6B if island else T6A)[band][col]


# ---------- graf ----------

class Net:
    pass


def build_net(osm, speed_bump=0, low_residential=True, footways=True):
    """Graf nad SVIM temenima puteva (ne samo raskrsnicama), da se stanovnik
    može prikačiti za ulicu i usred dugog bloka."""
    ways = osm["ways"]
    P = {w["id"]: [planar_xy(lo, la) for lo, la in w["coords"]] for w in ways}
    divided = find_divided(ways, P)

    node_ix = {}
    xy = []

    def nid(ref, p):
        i = node_ix.get(ref)
        if i is None:
            i = node_ix[ref] = len(xy)
            xy.append(p)
        return i

    winfo = []      # po putu: atributi koji ulaze u tabele
    edges = []      # (u, v, dužina, way_index)
    for wi, w in enumerate(ways):
        t = w["tags"]
        n_own, n_src = lanes_of(t)
        dv = w["id"] in divided
        n_total = n_own + divided[w["id"]] if dv else n_own
        lts, rule = classify(t, n_total, dv, speed_bump, low_residential, footways)
        v, v_src = speed_kmh(t)
        if t.get("highway") in ("primary", "secondary", "tertiary", "trunk",
                                "primary_link", "secondary_link",
                                "tertiary_link", "trunk_link"):
            v += speed_bump
        layer = t.get("layer", "0")
        elevated = (t.get("bridge") not in (None, "no")
                    or t.get("tunnel") not in (None, "no")
                    or layer not in ("0", ""))
        winfo.append({
            "lts": lts, "rule": rule, "key": street_key(w),
            "hw": t.get("highway"), "name": t.get("name"),
            "v": v, "v_src": v_src, "n": n_total, "n_src": n_src,
            "divided": dv, "elevated": elevated, "id": w["id"],
        })
        pts = P[w["id"]]
        prev = None
        for ref, p in zip(w["nodes"], pts):
            i = nid(ref, p)
            if prev is not None and prev != i:
                a, b = xy[prev], xy[i]
                edges.append((prev, i, math.hypot(b[0] - a[0], b[1] - a[1]), wi))
            prev = i

    net = Net()
    net.ways, net.winfo, net.xy, net.edges = ways, winfo, xy, edges
    net.node_ix = node_ix
    net.lts = [winfo[e[3]]["lts"] for e in edges]     # None = isključeno
    # jednosmernost za bicikl: +1 samo u smeru crtanja puta, -1 suprotno
    ow_way = []
    for w in ways:
        t = w["tags"]
        if (t.get("highway") in MOTOR and is_oneway(t)
                and t.get("oneway:bicycle") != "no"):
            ow_way.append(-1 if t.get("oneway") == "-1" else 1)
        else:
            ow_way.append(0)
    net.ow = [ow_way[e[3]] for e in edges]
    adj = [[] for _ in xy]
    for ei, (u, v, L, wi) in enumerate(edges):
        if net.lts[ei] is None:
            continue
        adj[u].append((ei, v, L))
        adj[v].append((ei, u, L))
    net.adj = adj
    net.deg_all = Counter()
    for u, v, _, _ in edges:
        net.deg_all[u] += 1
        net.deg_all[v] += 1

    # signalizacija i ostrva
    sig = Grid(SIGNAL_R_M)
    isl = Grid(ISLAND_R_M)
    for nd in osm["nodes"]:
        p = planar_xy(nd["lon"], nd["lat"])
        tg = nd["tags"]
        if (tg.get("highway") == "traffic_signals"
                or tg.get("crossing") == "traffic_signals"
                or tg.get("crossing:signals") == "yes"):
            sig.add_point(p, p)
        if tg.get("crossing:island") == "yes":
            isl.add_point(p, p)
    net.sig, net.isl = sig, isl
    net.n_signals = sum(len(v) for v in sig.g.values())
    compute_crossings(net)
    return net


def near_any(grid, p, r):
    return any(math.hypot(q[0] - p[0], q[1] - p[1]) <= r for q in grid.near(p, r))


def compute_crossings(net):
    """Za svaki čvor: ulice koje kroz njega PROLAZE i ocena prelaza preko njih.

    Ulica „prolazi" kroz čvor ako ima bar dve ivice u njemu. Ulica koja se tu
    završava (T-raskrsnica sa sporedne strane) ne preseca se — na nju se
    skreće, a vožnja po njoj se ocenjuje tabelom 4 kao i svaka ivica.
    """
    net.cross = {}          # čvor -> [(key, lts_prelaza, [ivice ulice])]
    net.signalized = set()
    for u, lst in enumerate(net.adj):
        if len(lst) < 3:
            continue
        by_key = defaultdict(list)
        for ei, v, L in lst:
            wi = net.edges[ei][3]
            if net.winfo[wi]["hw"] in CROSSABLE:
                by_key[net.winfo[wi]["key"]].append(ei)
        through = []
        p = net.xy[u]
        island_here = near_any(net.isl, p, ISLAND_R_M)
        for key, eis in by_key.items():
            if len(eis) < 2:
                continue
            worst = 0
            for ei in eis:
                w = net.winfo[net.edges[ei][3]]
                worst = max(worst, crossing_lts(w["v"], w["n"],
                                                w["divided"] or island_here))
            through.append((key, worst, eis))
        if through:
            net.cross[u] = through
            if near_any(net.sig, p, SIGNAL_R_M):
                net.signalized.add(u)


def build_split(net, k, unsplit=()):
    """Čvorovi gde neprelazna ulica deli prostor na sektore.

    Prelaz preko ulice sa ocenom > k bez semafora nije dozvoljen pri nivou k,
    pa se čvor deli na onoliko stanja koliko ga ulica deli sektora. Ivice same
    te ulice spajaju sve sektore (vožnja po njoj ili skretanje na nju nije
    prelaz — ali je vožnja po njoj ionako ocenjena tabelom 4).
    """
    split = {}
    for u, through in net.cross.items():
        if u in net.signalized or u in unsplit:
            continue
        cut = set()
        for key, lts_x, eis in through:
            if lts_x > k:
                cut.update(eis)
        if not cut:
            continue
        p = net.xy[u]
        inc = []
        for ei, v, L in net.adj[u]:
            q = net.xy[v]
            inc.append((bearing(p, q), ei))
        inc.sort()
        # rotiraj da lista počne sečenom ivicom
        start = next(i for i, (_, ei) in enumerate(inc) if ei in cut)
        inc = inc[start:] + inc[:start]
        sec = -1
        smap = {}
        bounds = []
        for br, ei in inc:
            if ei in cut:
                sec += 1
                smap[ei] = -1
                bounds.append((br, sec))
            else:
                smap[ei] = sec
        nsec = sec + 1
        if nsec < 2:
            continue
        split[u] = (min(nsec, 8), smap, bounds)
    return split


def sector_of_bearing(split_u, br):
    """Sektor u koji pada pravac br (za kačenje stanovnika na podeljen čvor)."""
    # sektor počinje na sečenoj ivici i traje do sledeće, rastućim azimutom;
    # pravac pre najmanjeg azimuta pripada poslednjem (krug se zatvara)
    bounds = sorted(split_u[2])
    cur = bounds[-1][1]
    for b, s in bounds:
        if br >= b:
            cur = s
    return min(cur, 7)


def states_of(split, u):
    if u in split:
        return [u * 8 + s for s in range(split[u][0])]
    return [u * 8]


def propagate(net, k, split, dist, lab, heap, lts_override=None, changed=None,
              direction=0):
    """Dijkstra nad stanjima (čvor, sektor). Radi i inkrementalno: dist može
    već biti popunjen, a heap sadrži samo nova semena.

    direction: 0 = jednosmerne ulice se ne poštuju; +1 = putovanje od keja ka
    kući (pretraga ide istim smerom); -1 = od kuće ka keju (pretraga ide
    unazad, pa se smer ivice obrće).
    """
    adj, lts, xy, ow, edges = net.adj, net.lts, net.xy, net.ow, net.edges
    while heap:
        d, st, lb = heapq.heappop(heap)
        if d > dist.get(st, math.inf) + 1e-9:
            continue
        u, su = st >> 3, st & 7
        su_split = split.get(u)
        for ei, v, L in adj[u]:
            le = lts[ei]
            if lts_override is not None and ei in lts_override:
                le = lts_override[ei]
            if k is not None and le > k:
                continue
            if direction and ow[ei]:
                sign = 1 if edges[ei][0] == u else -1
                if sign * direction != ow[ei]:
                    continue
            if su_split is not None:
                es = su_split[1].get(ei, 0)
                if es != -1 and min(es, 7) != su:
                    continue
            nd = d + L
            if nd > CUTOFF_M:
                continue
            sv = split.get(v)
            if sv is None:
                targets = (v * 8,)
            else:
                vs = sv[1].get(ei, 0)
                targets = ([v * 8 + s for s in range(sv[0])] if vs == -1
                           else (v * 8 + min(vs, 7),))
            for t in targets:
                if nd < dist.get(t, math.inf) - 1e-9:
                    if changed is not None and t not in changed:
                        changed[t] = (dist.get(t), lab.get(t))
                    dist[t] = nd
                    lab[t] = lb
                    heapq.heappush(heap, (nd, t, lb))


def run(net, k, split, sources, lts_override=None, direction=0):
    dist, lab, heap = {}, {}, []
    for u, lb in sources:
        for st in states_of(split, u):
            if 0.0 < dist.get(st, math.inf):
                dist[st] = 0.0
                lab[st] = lb
                heap.append((0.0, st, lb))
    heapq.heapify(heap)
    propagate(net, k, split, dist, lab, heap, lts_override, direction=direction)
    return dist, lab


# ---------- koridor u grafu ----------

def corridor_sources(net, axis, chains_bici_krak, axis_samples):
    """Čvorovi OSM mreže koji leže na koridoru + spoljni krajevi krakova.

    Na 3,3 km ose OSM nema stazu, pa se koridor ne sme izvoditi iz OSM-a:
    referenca je naša osa i naših 32 kraka. Čvorovi na mostovima ne računaju
    se kao ulaz — most nadvisuje kej, sa njega se ne silazi.
    """
    samp_grid = Grid(50.0)
    for s in axis_samples:
        samp_grid.add_point(planar_xy(s["lon"], s["lat"]), s)

    def deonica_at(p):
        r = 400.0
        while True:
            best, bd = None, math.inf
            for s in samp_grid.near(p, r):
                q = planar_xy(s["lon"], s["lat"])
                d = math.hypot(q[0] - p[0], q[1] - p[1])
                if d < bd:
                    best, bd = s, d
            if best is not None or r > 20000:
                return best
            r *= 2

    node_grid = Grid(30.0)
    for i, p in enumerate(net.xy):
        if net.adj[i]:
            node_grid.add_point(p, i)

    def grounded(i):
        return any(not net.winfo[net.edges[ei][3]]["elevated"]
                   for ei, _, _ in net.adj[i])

    lines = [axis] + chains_bici_krak
    src = {}
    for line in lines:
        pts = [planar_xy(lo, la) for lo, la in ((c[0], c[1]) for c in line)]
        for a, b in zip(pts, pts[1:]):
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            r = math.hypot(b[0] - a[0], b[1] - a[1]) / 2 + CORR_SNAP_M
            for i in node_grid.near(mid, r):
                if i in src or not grounded(i):
                    continue
                if seg_dist(net.xy[i], a, b) <= CORR_SNAP_M:
                    src[i] = "osa"

    krak_src = {}
    for ch in chains_bici_krak:
        ends = [planar_xy(ch[0][0], ch[0][1]), planar_xy(ch[-1][0], ch[-1][1])]
        for p in ends:
            best, bd = None, KRAK_SNAP_M
            for i in node_grid.near(p, KRAK_SNAP_M):
                if not grounded(i):
                    continue
                d = math.hypot(net.xy[i][0] - p[0], net.xy[i][1] - p[1])
                if d < bd:
                    best, bd = i, d
            if best is not None:
                krak_src[best] = p
                src.setdefault(best, "krak")

    out = []
    for i in src:
        s = deonica_at(net.xy[i])
        out.append((i, s["deonica"] if s else None))
    return out, src, krak_src, deonica_at


# ---------- stanovništvo ----------

def ensure_pop():
    if os.path.exists(POP_FILE):
        return POP_FILE
    os.makedirs(os.path.dirname(POP_FILE), exist_ok=True)
    print(f"  Preuzimam WorldPop ({os.path.basename(POP_FILE)})...", flush=True)
    req = urllib.request.Request(POP_URL, headers={
        "User-Agent": "biciklisticki-koridor/1.0 (github pages)"})
    with urllib.request.urlopen(req, timeout=300) as r, \
            open(POP_FILE + ".part", "wb") as f:
        f.write(r.read())
    os.replace(POP_FILE + ".part", POP_FILE)
    return POP_FILE


def load_pop(bbox):
    import rasterio
    from rasterio.windows import from_bounds
    s, w, n, e = bbox
    with rasterio.open(ensure_pop()) as r:
        win = from_bounds(w, s, e, n, r.transform)
        a = r.read(1, window=win)
        tr = r.window_transform(win)
        nod = r.nodata
    cells = []
    for (row, col), val in np.ndenumerate(a):
        if val is None or val == nod or not (val > 0):
            continue
        lon, lat = tr * (col + 0.5, row + 0.5)
        cells.append((lon, lat, float(val)))
    return cells


def snap_pairs(net, cells, k, split, barrier_grid):
    """Za svaku ćeliju: do SNAP_K najbližih čvorova mreže nivoa k, bez
    presecanja barijere (ulica iznad k, autoput, reka, pruga) na putu do njih.

    Bez ovog uslova bi kuća sa druge strane bulevara ili Nišave „stigla" do
    keja preko čvora do koga u stvarnosti ne može.
    """
    allowed = np.zeros(len(net.xy), dtype=bool)
    for ei, (u, v, L, wi) in enumerate(net.edges):
        le = net.lts[ei]
        if le is not None and (k is None or le <= k):
            allowed[u] = allowed[v] = True
    grid = Grid(SNAP_M)
    for i, p in enumerate(net.xy):
        if allowed[i]:
            grid.add_point(p, i)
    pc, pn, pd, ps = [], [], [], []
    for ci, (lon, lat, _) in enumerate(cells):
        p = planar_xy(lon, lat)
        cand = []
        for i in grid.near(p, SNAP_M):
            q = net.xy[i]
            d = math.hypot(q[0] - p[0], q[1] - p[1])
            if d <= SNAP_M:
                cand.append((d, i))
        cand.sort()
        got = 0
        for d, i in cand:
            q = net.xy[i]
            blocked = False
            for item in barrier_grid.along(p, q):
                a, b, ends = item
                if i in ends:
                    continue
                if seg_intersect(p, q, a, b) is not None:
                    blocked = True
                    break
            if blocked:
                continue
            sec = 0
            if i in split:
                sec = sector_of_bearing(split[i], bearing(q, p))
            pc.append(ci)
            pn.append(i)
            pd.append(d)
            ps.append(sec)
            got += 1
            if got >= SNAP_K:
                break
    return {"cell": np.array(pc, dtype=np.int64), "node": np.array(pn, dtype=np.int64),
            "d": np.array(pd), "sec": np.array(ps, dtype=np.int64)}


def barrier_grid_for(net, osm, k):
    """Segmenti preko kojih se ne kači: ulice iznad k, autoputevi, reka, pruga."""
    g = Grid(50.0)
    for ei, (u, v, L, wi) in enumerate(net.edges):
        w = net.winfo[wi]
        le = net.lts[ei]
        hard = w["hw"] in ("motorway", "motorway_link")
        if w["elevated"]:
            continue
        if hard or (k is not None and le is not None and le > k
                    and w["hw"] in CROSSABLE):
            g.add_seg(net.xy[u], net.xy[v], (net.xy[u], net.xy[v], (u, v)))
    for b in osm["barriers"]:
        pts = [planar_xy(lo, la) for lo, la in b["coords"]]
        for a, c in zip(pts, pts[1:]):
            g.add_seg(a, c, (a, c, ()))
    return g


def pair_states(pairs, split, nnode, unsplit=()):
    """Stanje (čvor, sektor) za svaki par ćelija–čvor."""
    is_split = np.zeros(nnode, dtype=bool)
    if split:
        is_split[np.fromiter(split.keys(), dtype=np.int64)] = True
    st = pairs["node"] * 8 + np.where(is_split[pairs["node"]], pairs["sec"], 0)
    if unsplit:
        m = np.isin(pairs["node"], np.fromiter(unsplit, dtype=np.int64))
        st[m] = pairs["node"][m] * 8
    return st


def dist_array(dist, nnode):
    arr = np.full(nnode * 8, math.inf)
    if dist:
        arr[np.fromiter(dist.keys(), dtype=np.int64)] = np.fromiter(
            dist.values(), dtype=float)
    return arr


def cell_dist_arr(pairs, st, darr, ncell):
    tot = darr[st] + pairs["d"]
    out = np.full(ncell, math.inf)
    np.minimum.at(out, pairs["cell"], tot)
    return out


def cell_dist(pairs, dist, split, ncell, nnode, unsplit=()):
    """Najkraće rastojanje ćelije do koridora preko njenih parova."""
    return cell_dist_arr(pairs, pair_states(pairs, split, nnode, unsplit),
                         dist_array(dist, nnode), ncell)


# ---------- osa ----------

def axis_layer(net, axis, axis_samples, osm):
    """Gde osa ide ulicom (tabela 4) i gde preseca ulicu u nivou (tabela 6)."""
    seg_grid = Grid(20.0)
    for ei, (u, v, L, wi) in enumerate(net.edges):
        w = net.winfo[wi]
        if w["hw"] not in CROSSABLE or w["elevated"] or net.lts[ei] is None:
            continue
        a, b = net.xy[u], net.xy[v]
        seg_grid.add_seg(a, b, (a, b, ei))

    pts = [planar_xy(s["lon"], s["lat"]) for s in axis_samples]
    rows = []
    for i, s in enumerate(axis_samples):
        p = pts[i]
        a = pts[max(0, i - 1)]
        b = pts[min(len(pts) - 1, i + 1)]
        br = bearing(a, b)
        best = None
        for sa, sb, ei in seg_grid.near(p, AXIS_STREET_M):
            d = seg_dist(p, sa, sb)
            if d > AXIS_STREET_M:
                continue
            dd = ang_diff(br, bearing(sa, sb))
            if min(dd, 180 - dd) > AXIS_PARALLEL_DEG:
                continue
            if best is None or d < best[0]:
                best = (d, ei)
        if best:
            w = net.winfo[net.edges[best[1]][3]]
            rows.append({"km": s["km"], "deonica": s["deonica"],
                         "lts": net.lts[best[1]], "ulica": w["name"],
                         "hw": w["hw"], "pravilo": w["rule"]})
        else:
            rows.append({"km": s["km"], "deonica": s["deonica"], "lts": 1,
                         "ulica": None, "hw": None,
                         "pravilo": "T1: samostalna staza"})

    # potezi
    potezi = []
    for r in rows:
        key = (r["ulica"], r["hw"], r["lts"])
        if potezi and potezi[-1]["_key"] == key and r["km"] - potezi[-1]["km_do"] < 0.025:
            potezi[-1]["km_do"] = r["km"]
            potezi[-1]["n"] += 1
        else:
            potezi.append({"_key": key, "km_od": r["km"], "km_do": r["km"],
                           "n": 1, "lts": r["lts"], "ulica": r["ulica"],
                           "hw": r["hw"], "deonica": r["deonica"],
                           "pravilo": r["pravilo"]})
    ulicni = [{k: (round(v, 3) if isinstance(v, float) else v)
               for k, v in p.items() if k != "_key"}
              for p in potezi if p["hw"] is not None and p["n"] >= 3]
    for p in ulicni:
        p["duzina_m"] = p.pop("n") * 10

    # prelazi u nivou i ispod mostova
    ap = [planar_xy(lo, la) for lo, la in ((c[0], c[1]) for c in axis)]
    cum = [0.0]
    for a, b in zip(ap, ap[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    all_grid = Grid(30.0)
    for ei, (u, v, L, wi) in enumerate(net.edges):
        if net.winfo[wi]["hw"] in CROSSABLE:
            a, b = net.xy[u], net.xy[v]
            all_grid.add_seg(a, b, (a, b, ei))
    hits = []
    for i, (a, b) in enumerate(zip(ap, ap[1:])):
        for sa, sb, ei in all_grid.along(a, b):
            t = seg_intersect(a, b, sa, sb)
            if t is None:
                continue
            m = cum[i] + t * (cum[i + 1] - cum[i])
            hits.append((m, ei, (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))))
    hits.sort()
    prelazi, mostovi = [], []
    last = {}
    for m, ei, p in hits:
        w = net.winfo[net.edges[ei][3]]
        # dva kolovoza istog mosta su jedno ukrštanje; u nivou se razlikuje
        # po ulici, jer dve ulice mogu da se ukrste osom na istom mestu
        key = "van_nivoa" if w["elevated"] else w["key"]
        if key in last and m - last[key] < 40:
            continue
        last[key] = m
        km = m / 1000.0
        rec = {"km": round(km, 3), "ulica": w["name"], "hw": w["hw"],
               "kmh": w["v"], "kmh_izvor": w["v_src"], "trake": w["n"],
               "trake_izvor": w["n_src"], "bulevar": w["divided"]}
        if w["elevated"]:
            t = net.ways[net.edges[ei][3]]["tags"]
            rec["tip"] = "tunel" if t.get("tunnel") not in (None, "no") else "most"
            mostovi.append(rec)
            continue
        island = w["divided"] or near_any(net.isl, p, ISLAND_R_M)
        signal = near_any(net.sig, p, SIGNAL_R_M)
        rec.update({
            "ostrvo": island, "semafor": signal,
            "lts": 1 if signal else crossing_lts(w["v"], w["n"], island),
            "lts_bez_semafora": crossing_lts(w["v"], w["n"], island),
            "tabela": "signalisan" if signal else ("6b" if island else "6a"),
        })
        prelazi.append(rec)

    # deonica preseka
    def deon(km):
        return min(axis_samples, key=lambda s: abs(s["km"] - km))["deonica"]
    for rec in prelazi + mostovi:
        rec["deonica"] = deon(rec["km"])

    # koliko je osa daleko od ulice uopšte — to je razlog zašto je LTS ose 1
    far_grid = Grid(50.0)
    for ei, (u, v, L, wi) in enumerate(net.edges):
        w = net.winfo[wi]
        if w["hw"] in MOTOR and not w["elevated"]:
            a, b = net.xy[u], net.xy[v]
            far_grid.add_seg(a, b, (a, b))
    bins = Counter()
    for p in pts:
        d = min((seg_dist(p, a, b) for a, b in far_grid.near(p, 50.0)), default=math.inf)
        bins["do_10" if d <= 10 else "10_50" if d <= 50 else "preko_50"] += 1
    udaljenost = {k: round(100 * v / len(pts), 1) for k, v in bins.items()}

    km_by = Counter(r["lts"] for r in rows)
    by_deonica = defaultdict(Counter)
    for r in rows:
        by_deonica[r["deonica"]][r["lts"]] += 1
    return {
        "duzina_km": round(len(rows) * 10 / 1000.0, 2),
        "udaljenost_od_ulice_pct": udaljenost,
        "km_po_lts": {str(k): round(v * 10 / 1000.0, 2) for k, v in sorted(km_by.items())},
        "po_deonici": [{"deonica": d, **{str(k): round(v * 10 / 1000.0, 2)
                                         for k, v in sorted(c.items())}}
                       for d, c in by_deonica.items()],
        "ulicni_potezi": ulicni,
        "prelazi": prelazi,
        "van_nivoa": mostovi,
        "uzorci": [[round(r["km"], 2), r["lts"]] for r in rows],
    }


# ---------- pristupi ----------

def access_layer(net, axis, krakovi, stepenice, prekidi, deonica_at):
    """32 mapirana kraka: na kakvu ulicu izlaze i šta je na samom ulazu."""
    ap = [planar_xy(c[0], c[1]) for c in axis]
    ax_grid = Grid(50.0)
    for a, b in zip(ap, ap[1:]):
        ax_grid.add_seg(a, b, (a, b))

    def d_axis(p):
        best = math.inf
        r = 50.0
        while best == math.inf and r < 3000:
            for a, b in ax_grid.near(p, r):
                best = min(best, seg_dist(p, a, b))
            r *= 2
        return best

    street_grid = Grid(30.0)
    for ei, (u, v, L, wi) in enumerate(net.edges):
        w = net.winfo[wi]
        if w["hw"] in CROSSABLE and not w["elevated"] and net.lts[ei] is not None:
            a, b = net.xy[u], net.xy[v]
            street_grid.add_seg(a, b, (a, b, ei))

    st_pts = [planar_xy(*f["geometry"]["coordinates"][:2]) for f in stepenice]
    pk_pts = [planar_xy(*f["geometry"]["coordinates"][:2]) for f in prekidi
              if f["geometry"]["type"] == "Point"]

    out = []
    seen = []
    for f in krakovi:
        c = f["geometry"]["coordinates"]
        e0, e1 = planar_xy(c[0][0], c[0][1]), planar_xy(c[-1][0], c[-1][1])
        outer = e0 if d_axis(e0) >= d_axis(e1) else e1
        if any(math.hypot(outer[0] - q[0], outer[1] - q[1]) < 10 for q in seen):
            continue
        seen.append(outer)
        best = None
        for a, b, ei in street_grid.near(outer, KRAK_SNAP_M):
            d = seg_dist(outer, a, b)
            if d <= KRAK_SNAP_M and (best is None or d < best[0]):
                best = (d, ei)
        s = deonica_at(outer)
        rec = {
            "km": round(s["km"], 2) if s else None,
            "deonica": s["deonica"] if s else None,
            "duzina_kraka_m": round(f["properties"]["duzina_m"]),
            "stepenice": any(math.hypot(outer[0] - q[0], outer[1] - q[1]) <= STAIRS_R_M
                             for q in st_pts),
            "prekid": any(math.hypot(outer[0] - q[0], outer[1] - q[1]) <= PREKID_R_M
                          for q in pk_pts),
        }
        # koordinate za mapu
        idx = 0 if outer is e0 else -1
        rec["lon"], rec["lat"] = round(c[idx][0], 6), round(c[idx][1], 6)
        if best:
            w = net.winfo[net.edges[best[1]][3]]
            rec.update({"ulica": w["name"], "hw": w["hw"], "lts": net.lts[best[1]],
                        "kmh": w["v"], "kmh_izvor": w["v_src"], "trake": w["n"],
                        "pravilo": w["rule"], "d_m": round(best[0])})
        else:
            rec.update({"ulica": None, "hw": None, "lts": 1,
                        "pravilo": "nema ulice na 25 m — izlaz na stazu"})
        out.append(rec)
    out.sort(key=lambda r: (r["km"] is None, r["km"]))
    return out


# ---------- glavni tok ----------

DIRS = (1, -1)      # +1: od keja ka kući, -1: od kuće ka keju


def conn_mask(dall, dk, detour=DETOUR):
    """Povezano u SVIM smerovima iz dk (obilazak meren prema svom smeru)."""
    m = None
    for dr, arr in dk.items():
        x = np.isfinite(arr) & (arr <= detour * dall[dr])
        m = x if m is None else (m & x)
    return m


def conn2(popv, dall, dk, radius, detour):
    inside = np.maximum.reduce([dall[dr] for dr in dk]) <= radius
    ok = inside & conn_mask(dall, dk, detour)
    return float(popv[inside].sum()), float(popv[ok].sum())


def connectivity(cells, d_all, d_k, radius, detour):
    pop = cells if isinstance(cells, np.ndarray) else np.array([c[2] for c in cells])
    inside = d_all <= radius
    # d_k mora biti konačno: inače je pri pragu ∞ i nedostižna ćelija „povezana"
    ok = inside & np.isfinite(d_k) & (d_k <= detour * d_all)
    return float(pop[inside].sum()), float(pop[ok].sum())


def inputs_hash(osm_stamp):
    h = hashlib.sha1()
    for f in (MREZA_FILE, DEONICE_FILE, STEPENICE_FILE, PREKIDI_FILE, __file__,
              os.path.join(ROOT, "lts_osm.py"), os.path.join(ROOT, "koridor.py")):
        with open(f, "rb") as fh:
            h.update(fh.read())
    h.update(osm_stamp.encode())
    h.update(os.path.basename(POP_FILE).encode())
    return h.hexdigest()[:16]


def main():
    for f in (MREZA_FILE, DEONICE_FILE):
        if not os.path.exists(f):
            print(f"ERROR: nema {f} — prvo pokreni `make convert`.", file=sys.stderr)
            return 1

    axis, by_tip, deon_order = prepare()
    axis_samples = by_tip["bici"]
    bbox = bbox_of(axis)
    osm = extract(bbox)
    cur_hash = inputs_hash(osm["stamp"])
    if os.path.exists(OUT_FILE):
        try:
            with open(OUT_FILE) as f:
                old = json.load(f)
            if old.get("schema") == LTS_SCHEMA and old.get("hash") == cur_hash:
                print("lts cache hit")
                return 0
        except (OSError, json.JSONDecodeError):
            pass

    with open(MREZA_FILE) as f:
        mreza = json.load(f)
    krakovi = [ft for ft in mreza["features"]
               if ft["properties"]["tip"] == "bici" and ft["properties"]["uloga"] != "osa"]
    with open(STEPENICE_FILE) as f:
        stepenice = json.load(f)["features"]
    with open(PREKIDI_FILE) as f:
        prekidi = json.load(f)["features"]

    print("  Gradim graf i klasifikujem ulice...", flush=True)
    net = build_net(osm)
    n_edges = sum(1 for x in net.lts if x is not None)
    print(f"  {len(net.xy)} čvorova, {n_edges} ivica, "
          f"{len(net.cross)} raskrsnica sa ulicom koja prolazi, "
          f"{len(net.signalized)} signalisanih")

    sources, src_kind, krak_src, deonica_at = corridor_sources(
        net, axis, [ft["geometry"]["coordinates"] for ft in krakovi], axis_samples)
    print(f"  ulaza u koridor: {len(sources)} čvorova "
          f"({sum(1 for v in src_kind.values() if v == 'krak')} samo preko kraka)")

    print("  Stanovništvo (WorldPop)...", flush=True)
    cells = load_pop(bbox)
    ncell = len(cells)
    print(f"  {ncell} naseljenih ćelija, {sum(c[2] for c in cells):.0f} stanovnika u bbox-u")

    NN = len(net.xy)
    popv = np.array([c[2] for c in cells])
    osa = axis_layer(net, axis, axis_samples, osm)
    pristupi = access_layer(net, axis, krakovi, stepenice, prekidi, deonica_at)

    # --- povezanost ---
    # Jednosmerne ulice se poštuju: ćelija je povezana tek ako i put od kuće do
    # keja (-1) i povratak (+1) prolaze bez prelaska nivoa k i uz obilazak do
    # 25 %. Vožnja kontra smeru nije nizak stres nego prekršaj.
    print("  Rutiranje...", flush=True)

    def route(net_, k, split, srcs, pairs, dirs=DIRS):
        out = {}
        for dr in dirs:
            dist, lab = run(net_, k, split, srcs, direction=dr)
            out[dr] = {"dist": dist, "lab": lab,
                       "cell": cell_dist(pairs, dist, split, ncell, NN)}
        return out

    def cells_of(r):
        return {dr: v["cell"] for dr, v in r.items()}

    res = {}
    split_by_k = {}
    pairs_by_k = {}
    for k in (None, 1, 2, 3):
        split = {} if k is None else build_split(net, k)
        split_by_k[k] = split
        t0 = time.time()
        pairs = snap_pairs(net, cells, k, split, barrier_grid_for(net, osm, k))
        t1 = time.time()
        pairs_by_k[k] = pairs
        res[k] = route(net, k, split, sources, pairs)
        print(f"    k={k}: kačenje {t1 - t0:.1f} s, rutiranje {time.time() - t1:.1f} s, "
              f"{len(split)} podeljenih čvorova")

    dall = cells_of(res[None])
    pop = popv
    inside = np.maximum(dall[1], dall[-1]) <= CATCH_M

    # deonica ćelije: preko izvora najkraćeg puta od kuće do keja
    lab_all = res[None][-1]["lab"]
    dist_in = res[None][-1]["dist"]
    cell_lab = [None] * ncell
    best = np.full(ncell, math.inf)
    pa = pairs_by_k[None]
    for j in range(len(pa["node"])):
        ci = int(pa["cell"][j])
        st = int(pa["node"][j]) * 8
        dv = dist_in.get(st, math.inf) + pa["d"][j]
        if dv < best[ci]:
            best[ci] = dv
            cell_lab[ci] = lab_all.get(st)
    cell_lab = np.array(cell_lab, dtype=object)

    pov = {"zahvat_m": CATCH_M, "obilazak": DETOUR, "smerovi": "oba",
           "radijusi": [], "po_deonici": []}
    for R in CATCH_RADII:
        row = {"r_m": R}
        for k in (1, 2, 3):
            tot, ok = conn2(popv, dall, cells_of(res[k]), R, DETOUR)
            row["stanovnika"] = round(tot)
            row[f"lts{k}"] = round(ok)
            row[f"lts{k}_pct"] = round(100 * ok / tot, 1) if tot else None
        pov["radijusi"].append(row)
        print(f"    R={R} m: {row['stanovnika']} st., LTS1 {row['lts1_pct']} %, "
              f"LTS2 {row['lts2_pct']} %, LTS3 {row['lts3_pct']} %")

    for d in deon_order:
        m = inside & (cell_lab == d)
        tot = float(pop[m].sum())
        if tot <= 0:
            continue
        row = {"deonica": d, "stanovnika": round(tot)}
        for k in (1, 2, 3):
            ok = m & conn_mask(dall, cells_of(res[k]))
            row[f"lts{k}_pct"] = round(100 * float(pop[ok].sum()) / tot, 1)
        pov["po_deonici"].append(row)

    # osetljivost — svaka menja tačno jednu pretpostavku
    sens = {}

    def pct(tot_ok):
        tot, ok = tot_ok
        return round(100 * ok / tot, 1) if tot else None

    sens["obilazak_50"] = pct(conn2(popv, dall, cells_of(res[2]), CATCH_M, DETOUR_SENS))
    sens["bez_praga_obilaska"] = pct(conn2(popv, dall, cells_of(res[2]), CATCH_M, math.inf))
    # ulaz na kome su mapirane stepenice nije ulaz za bicikl
    stair_grid = Grid(STAIRS_R_M)
    for f in stepenice:
        q = planar_xy(*f["geometry"]["coordinates"][:2])
        stair_grid.add_point(q, q)
    drop = {i for i, _ in sources if near_any(stair_grid, net.xy[i], STAIRS_R_M)}
    src2 = [(i, d) for i, d in sources if i not in drop]
    r2 = route(net, 2, split_by_k[2], src2, pairs_by_k[2])
    ra2 = route(net, None, {}, src2, pairs_by_k[None])
    sens["bez_ulaza_kod_stepenica"] = pct(conn2(popv, cells_of(ra2), cells_of(r2),
                                                CATCH_M, DETOUR))
    sens["ulaza_kod_stepenica"] = len(drop)
    sens["ulaza_ukupno"] = len(sources)
    # Grafovi se grade istim redom, pa su indeksi čvorova isti; rastojanja bez
    # ograničenja ne zavise od klasifikacije.
    for name, kw in (("brzina_plus_10", {"speed_bump": 10}),
                     ("stambene_kao_lts3", {"low_residential": False}),
                     ("bez_pesackih_staza", {"footways": False})):
        alt = build_net(osm, **kw)
        assert alt.node_ix == net.node_ix
        sp_alt = build_split(alt, 2)
        pr = snap_pairs(alt, cells, 2, sp_alt, barrier_grid_for(alt, osm, 2))
        ra = route(alt, 2, sp_alt, sources, pr)
        if name == "bez_pesackih_staza":
            # bez pešačkih staza menja se i najkraći put, pa i obilazak
            dall_alt = cells_of(route(alt, None, {}, sources,
                                      snap_pairs(alt, cells, None, {},
                                                 barrier_grid_for(alt, osm, None))))
        else:
            dall_alt = dall
        sens[name] = pct(conn2(popv, dall_alt, cells_of(ra), CATCH_M, DETOUR))
    r0 = route(net, 2, split_by_k[2], sources, pairs_by_k[2], dirs=(0,))
    ra0 = route(net, None, {}, sources, pairs_by_k[None], dirs=(0,))
    sens["jednosmerne_ignorisane"] = pct(conn2(popv, cells_of(ra0), cells_of(r0),
                                               CATCH_M, DETOUR))
    sens["jednosmernih_kolovoza"] = sum(
        1 for w in net.ways if w["tags"].get("highway") in MOTOR
        and is_oneway(w["tags"]) and w["tags"].get("oneway:bicycle") != "no")
    pov["osetljivost"] = sens
    print(f"    osetljivost: {sens}")

    # --- barijere (k=2) ---
    print("  Rangiram barijere...", flush=True)
    base_tot, base_ok = conn2(popv, dall, cells_of(res[2]), CATCH_M, DETOUR)
    split2 = split_by_k[2]
    pairs2 = pairs_by_k[2]
    D2 = {dr: res[2][dr]["dist"] for dr in DIRS}
    L2 = {dr: res[2][dr]["lab"] for dr in DIRS}
    A2 = {dr: dist_array(D2[dr], NN) for dr in DIRS}
    pst2 = pair_states(pairs2, split2, NN)
    dist_any = {}
    for dr in DIRS:
        for st, dv in res[None][dr]["dist"].items():
            if dv < dist_any.get(st, math.inf):
                dist_any[st] = dv

    def node_reached(u, both=False):
        hit = [any(st in D2[dr] for st in states_of(split2, u)) for dr in DIRS]
        return all(hit) if both else any(hit)

    def node_d_all(u):
        return dist_any.get(u * 8, math.inf)

    cands = []
    # a) prelazi bez semafora koji seku mrežu niskog stresa
    for u, (nsec, smap, _) in split2.items():
        if node_d_all(u) > CATCH_M + 500:
            continue
        secs_ok = {s for ei, s in smap.items() if s != -1 and net.lts[ei] is not None
                   and net.lts[ei] <= 2}
        if len(secs_ok) < 2 or not node_reached(u):
            continue
        cands.append(("prelaz", u))
    # b) potezi ulice iznad LTS 2 na ivici ostrva niskog stresa
    junction = {u for u, c in net.deg_all.items() if c != 2}
    seen_e = set()
    for ei, (u, v, L, wi) in enumerate(net.edges):
        if ei in seen_e or net.lts[ei] is None or net.lts[ei] <= 2:
            continue
        key = net.winfo[wi]["key"]
        block = [ei]
        seen_e.add(ei)
        for start in (u, v):
            cur, prev_e = start, ei
            while cur not in junction:
                nxt = [(e2, o) for e2, o, _ in net.adj[cur]
                       if e2 != prev_e and net.winfo[net.edges[e2][3]]["key"] == key
                       and net.lts[e2] is not None and net.lts[e2] > 2]
                if len(nxt) != 1:
                    break
                e2, o = nxt[0]
                if e2 in seen_e:
                    break
                seen_e.add(e2)
                block.append(e2)
                prev_e, cur = e2, o
        length = sum(net.edges[e][2] for e in block)
        if length > BLOCK_MAX_M:
            continue
        ends = set()
        for e in block:
            ends.update(net.edges[e][:2])
        if not any(node_reached(n) for n in ends):
            continue
        if all(node_reached(n, both=True) for n in ends):
            continue
        if min(node_d_all(n) for n in ends) > CATCH_M:
            continue
        cands.append(("potez", block))
    print(f"    kandidata: {sum(1 for c in cands if c[0] == 'prelaz')} prelaza, "
          f"{sum(1 for c in cands if c[0] == 'potez')} poteza")

    def evaluate(changes_cross, changes_block):
        """Inkrementalno, u oba smera: primeni intervencije, izmeri, vrati."""
        unsplit = set(changes_cross)
        sp = {u: v for u, v in split2.items() if u not in unsplit}
        override = {}
        for blk in changes_block:
            for e in blk:
                override[e] = 2
        pst = pair_states(pairs2, split2, NN, unsplit) if unsplit else pst2
        dc = {}
        undo = []
        for dr in DIRS:
            dist2, lab2, darr2 = D2[dr], L2[dr], A2[dr]
            changed = {}
            heap = []
            for u in changes_cross:
                sts = [st for st in states_of(split2, u) if st in dist2]
                if not sts:
                    continue
                # spojeni čvor koristi stanje sektora 0, sa najboljim
                # rastojanjem svih sektora
                stb = min(sts, key=lambda x: dist2[x])
                d0, lb = dist2[stb], lab2[stb]
                st0 = u * 8
                if st0 not in changed:
                    changed[st0] = (dist2.get(st0), lab2.get(st0))
                dist2[st0] = d0
                lab2[st0] = lb
                heap.append((d0, st0, lb))
            for blk in changes_block:
                for e in blk:
                    for n in net.edges[e][:2]:
                        for st in states_of(sp, n):
                            if st in dist2:
                                heap.append((dist2[st], st, lab2[st]))
            heapq.heapify(heap)
            propagate(net, 2, sp, dist2, lab2, heap, override, changed, direction=dr)
            for st in changed:
                darr2[st] = dist2[st]
            dc[dr] = cell_dist_arr(pairs2, pst, darr2, ncell)
            undo.append((dist2, lab2, darr2, changed))
        _, ok = conn2(popv, dall, dc, CATCH_M, DETOUR)
        for dist2, lab2, darr2, changed in undo:
            for st, (dv, lv) in changed.items():
                if dv is None:
                    dist2.pop(st, None)
                    lab2.pop(st, None)
                    darr2[st] = math.inf
                else:
                    dist2[st] = dv
                    lab2[st] = lv
                    darr2[st] = dv
        return ok - base_ok

    t0 = time.time()
    scored = []
    for kind, obj in cands:
        gain = evaluate([obj], []) if kind == "prelaz" else evaluate([], [obj])
        if gain > 0.5:
            scored.append((gain, kind, obj))
    scored.sort(key=lambda x: -x[0])
    print(f"    ocenjeno za {time.time() - t0:.0f} s, {len(scored)} sa dobitkom")

    def describe(kind, obj):
        if kind == "prelaz":
            u = obj
            through = [t for t in net.cross[u] if t[1] > 2]
            key, lx, eis = max(through, key=lambda t: t[1])
            w = net.winfo[net.edges[eis[0]][3]]
            names = sorted({net.winfo[net.edges[ei][3]]["name"] for ei, _, _ in net.adj[u]
                            if net.winfo[net.edges[ei][3]]["name"]
                            and net.winfo[net.edges[ei][3]]["key"] != key})
            return {"tip": "prelaz", "ulica": w["name"], "preko": names[:3],
                    "lts": lx, "kmh": w["v"], "kmh_izvor": w["v_src"],
                    "trake": w["n"], "bulevar": w["divided"], "_p": net.xy[u],
                    "mera": "semafor ili ostrvo za prelaz"}
        blk = obj
        w = net.winfo[net.edges[blk[0]][3]]
        length = sum(net.edges[e][2] for e in blk)
        mid = net.xy[net.edges[blk[len(blk) // 2]][0]]
        return {"tip": "potez", "ulica": w["name"], "hw": w["hw"],
                "duzina_m": round(length),
                "lts": max(net.lts[e] for e in blk), "kmh": w["v"],
                "kmh_izvor": w["v_src"], "trake": w["n"], "trake_izvor": w["n_src"],
                "pravilo": w["rule"], "_p": mid,
                "mera": "odvojena staza ili smirivanje do LTS 2"}

    def to_lonlat(p):
        from koridor import M_PER_DEG_LAT, M_PER_DEG_LON
        return round(p[0] / M_PER_DEG_LON, 6), round(p[1] / M_PER_DEG_LAT, 6)

    # Pohlepno: svaka sledeća stavka je ona koja uz već izabrane dodaje
    # najviše. Pojedinačni dobici se ne sabiraju — dve susedne mere često
    # rešavaju istu prepreku — pa lista sa sopstvenim dobicima ne bi imala zbir.
    barijere = []
    chosen_cross, chosen_block = [], []
    current = 0.0
    pool = list(scored)
    for _ in range(TOP_BARIJERE):
        best = None
        for item in pool:
            g, kind, obj = item
            cc = chosen_cross + ([obj] if kind == "prelaz" else [])
            cb = chosen_block + ([obj] if kind == "potez" else [])
            marg = evaluate(cc, cb) - current
            if best is None or marg > best[0]:
                best = (marg, item)
        if best is None or best[0] < 50:      # ispod 50 ljudi nije prioritet
            break
        marg, item = best
        pool.remove(item)
        g, kind, obj = item
        (chosen_cross if kind == "prelaz" else chosen_block).append(obj)
        current += marg
        d = describe(kind, obj)
        d["lon"], d["lat"] = to_lonlat(d.pop("_p"))
        d["prikljucuje"] = round(marg)
        d["sam_prikljucuje"] = round(g)
        d["deonica"] = deonica_at(planar_xy(d["lon"], d["lat"]))["deonica"]
        barijere.append(d)
    combined = current
    print(f"    top {len(barijere)}: zajedno +{combined:.0f} stanovnika "
          f"({100 * base_ok / base_tot:.1f} → {100 * (base_ok + combined) / base_tot:.1f} %)")

    # --- ostrva ---
    # Komponente mreže niskog stresa, bez smera: ostrvo je deo grada do koga se
    # sa keja ne može ni kontra smeru. Ono što je dostižno samo kontra smeru
    # ili tek uz ogroman obilazak ide u posebnu grupu.
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    def edge_states(n, ei):
        sn = split2.get(n)
        if sn is None:
            return [n * 8]
        s_ = sn[1].get(ei, 0)
        return [n * 8 + x for x in range(sn[0])] if s_ == -1 else [n * 8 + min(s_, 7)]

    for ei, (u, v, L, wi) in enumerate(net.edges):
        if net.lts[ei] is None or net.lts[ei] > 2:
            continue
        for a in edge_states(u, ei):
            for b in edge_states(v, ei):
                union(a, b)
    corridor_roots = {find(st) for u, _ in sources for st in states_of(split2, u)}
    connected2 = conn_mask(dall, cells_of(res[2]))
    reach_any = np.isfinite(res[2][1]["cell"]) & np.isfinite(res[2][-1]["cell"])
    unconn = inside & ~connected2
    island_pop = Counter()
    island_cells = defaultdict(list)
    bestpair = {}
    for j in range(len(pairs2["node"])):
        ci = int(pairs2["cell"][j])
        if not unconn[ci] or reach_any[ci]:
            continue
        if ci not in bestpair or pairs2["d"][j] < bestpair[ci][0]:
            u = int(pairs2["node"][j])
            s_ = int(pairs2["sec"][j]) if u in split2 else 0
            bestpair[ci] = (pairs2["d"][j], u * 8 + s_)
    for ci, (_, st) in bestpair.items():
        r = find(st)
        if r in corridor_roots:
            continue
        island_pop[r] += pop[ci]
        island_cells[r].append(ci)
    root_names = defaultdict(Counter)
    for ei, (u, v, L, wi) in enumerate(net.edges):
        if net.lts[ei] is None or net.lts[ei] > 2:
            continue
        nm = net.winfo[wi]["name"]
        if nm:
            r = find(edge_states(u, ei)[0])
            if r in island_pop:
                root_names[r][nm] += L
    has_pair = np.zeros(ncell, dtype=bool)
    has_pair[pairs2["cell"]] = True
    bez_mreze = float(pop[unconn & ~reach_any & ~has_pair].sum())
    ostrva = []
    for r, pp in island_pop.most_common(6):
        cs = island_cells[r]
        lon = float(np.average([cells[c][0] for c in cs], weights=[cells[c][2] for c in cs]))
        lat = float(np.average([cells[c][1] for c in cs], weights=[cells[c][2] for c in cs]))
        ostrva.append({"stanovnika": round(pp), "lon": round(lon, 5), "lat": round(lat, 5),
                       "ulice": [n for n, _ in root_names[r].most_common(3)]})

    # --- mreža za mapu ---
    cell_cls = np.where(~inside, -1, np.where(connected2, 2, np.where(reach_any, 1, 0)))
    dist2 = {st: 0.0 for st in D2[1] if st in D2[-1]}   # dostignuto u oba smera
    node_dall = {}
    for st, dv in dist_any.items():
        node_dall[st >> 3] = min(dv, node_dall.get(st >> 3, math.inf))
    lines = []
    for wi, w in enumerate(net.winfo):
        if w["lts"] is None:
            continue
        coords = net.ways[wi]["coords"]
        refs = net.ways[wi]["nodes"]
        ixs = [net.node_ix[r] for r in refs]
        if min(node_dall.get(i, math.inf) for i in ixs) > CATCH_M + 300:
            continue
        cur, cur_cls = [], None
        for j, i in enumerate(ixs):
            if w["lts"] <= 2:
                reached = any(st in dist2 for st in states_of(split2, i))
                cls = "k" if reached else "o"
            else:
                cls = "s"
            if cur and cls != cur_cls:
                cur.append(coords[j])
                lines.append([w["lts"], cur_cls, cur])
                cur = []
            cur.append(coords[j])
            cur_cls = cls
        if len(cur) >= 2:
            lines.append([w["lts"], cur_cls, cur])
    # Za mapu: Douglas–Peucker na 2 m, pa celobrojne razlike u 1e-5 stepena.
    # Pun zapis bi bio ~1 MB; ovako je nekoliko puta manji, a 1e-5 je ~1 m.
    def simplify(cs, tol=2.0):
        if len(cs) < 3:
            return cs
        pts = [planar_xy(c[0], c[1]) for c in cs]
        keep = [False] * len(cs)
        keep[0] = keep[-1] = True
        stack = [(0, len(cs) - 1)]
        while stack:
            i, j = stack.pop()
            best, bi = 0.0, None
            for m in range(i + 1, j):
                d = seg_dist(pts[m], pts[i], pts[j])
                if d > best:
                    best, bi = d, m
            if bi is not None and best > tol:
                keep[bi] = True
                stack.append((i, bi))
                stack.append((bi, j))
        return [c for c, k in zip(cs, keep) if k]

    def enc(cs):
        out, px, py = [], 0, 0
        for lon, lat in cs:
            x, y = round(lon * 1e5), round(lat * 1e5)
            out += [x - px, y - py]
            px, py = x, y
        return out

    cls_ix = {"k": 0, "o": 1, "s": 2}
    flat = [[lts_v, cls_ix[cls], enc(simplify(cs))] for lts_v, cls, cs in lines]
    lon0 = min(c[0] for c in cells)
    lat0 = min(c[1] for c in cells)
    step = 1 / 1200.0                    # WorldPop 3 lučne sekunde
    net_out = {
        "schema": LTS_SCHEMA,
        "kodiranje": "linije: [lts, klasa 0=ostrvo koridora 1=drugo ostrvo "
                     "2=stres, razlike x/y u 1e-5°]; ćelije: [kol, red, st., "
                     "klasa 2=povezano 1=obilazak>25% 0=nedostižno]",
        "linije": flat,
        "celije_origin": [lon0, lat0, step],
        "celije": [[round((cells[i][0] - lon0) / step), round((cells[i][1] - lat0) / step),
                    round(cells[i][2]), int(cell_cls[i])]
                   for i in range(ncell) if cell_cls[i] >= 0],
    }

    # --- ciljevi (2.3) ---
    ciljevi = {
        "osa_km_iznad_2": round(sum(v for k, v in osa["km_po_lts"].items() if int(k) > 2), 2),
        "prelazi_iznad_2": sum(1 for p in osa["prelazi"] if p["lts"] > 2),
        "pristupi_iznad_2": sum(1 for p in pristupi if p["lts"] > 2),
        "pristupi_stepenice": sum(1 for p in pristupi if p["stepenice"]),
        "povezano_lts2_pct": round(100 * base_ok / base_tot, 1),
        "povezano_lts2_posle_top": round(100 * (base_ok + combined) / base_tot, 1),
        "povezano_lts1_pct": next(r["lts1_pct"] for r in pov["radijusi"] if r["r_m"] == CATCH_M),
        "top_prikljucuje": round(combined),
    }

    v_src = Counter(w["v_src"] for w in net.winfo
                    if w["lts"] is not None and w["hw"] in CROSSABLE)
    n_src = Counter(w["n_src"] for w in net.winfo
                    if w["lts"] is not None and w["hw"] in CROSSABLE)
    out = {
        "schema": LTS_SCHEMA,
        "hash": cur_hash,
        "izvori": {"osm": osm["stamp"], "worldpop": "R2025A, 2025, 100 m constrained"},
        "kriterijumi": {"T4": T4, "T6_pojasevi_kmh": T6_BANDS, "T6a": T6A, "T6b": T6B,
                        "niska_frekvencija": sorted(LOW_VOLUME),
                        "podrazumevana_brzina": URBAN_KMH},
        "parametri": {"zahvat_m": CATCH_M, "obilazak": DETOUR, "kacenje_m": SNAP_M,
                      "semafor_r_m": SIGNAL_R_M, "bulevar_r_m": DIVIDED_R_M},
        "podaci": {
            "ulica": sum(v_src.values()),
            "brzina_sa_znaka_pct": round(100 * (v_src["znak"] + v_src["RS:urban"]
                                                + v_src["RS:rural"] + v_src["zakon"])
                                         / sum(v_src.values()), 1),
            "trake_tag_pct": round(100 * n_src["tag"] / sum(n_src.values()), 1),
            "semafora": net.n_signals,
            "bulevara_kolovoza": sum(1 for w in net.winfo if w["divided"]),
            "obelezenih_traka": sum(1 for w in net.ways
                                    if any(w["tags"].get(k) in ("lane", "opposite_lane")
                                           for k in CYCLEWAY_KEYS)),
        },
        "osa": osa,
        "pristupi": pristupi,
        "povezanost": pov,
        "barijere": barijere,
        "ostrva": ostrva,
        "nedostizno": {
            "stanovnika": round(float(pop[inside & ~reach_any].sum())),
            "u_ostrvima": round(sum(island_pop.values())),
            "bez_ulice_niskog_stresa": round(bez_mreze),
            # dostižno mrežom niskog stresa, ali tek preko granice pretrage
            # (CUTOFF_M) — obilazak veći od 2,3 puta
            "van_dometa": round(float(pop[inside & ~reach_any].sum())
                                - sum(island_pop.values()) - bez_mreze),
            "granica_pretrage_m": CUTOFF_M,
        },
        "ciljevi": ciljevi,
    }
    with open(OUT_FILE, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    with open(NET_FILE, "w") as f:
        json.dump(net_out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  → {OUT_FILE} ({os.path.getsize(OUT_FILE) // 1024} KB), "
          f"{NET_FILE} ({os.path.getsize(NET_FILE) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
