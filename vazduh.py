#!/usr/bin/env python3
"""Kvalitet vazduha duž koridora iz zvaničnih mernih stanica (analiza 9.2).

Zamenjuje CAMS kao izvor nivoa. CAMS (Open-Meteo, ćelija ~11 km) potcenjuje
Niš 1,6–5,9 puta, a za NO2 praktično nema veštinu (r=0,30 na dnevnim
vrednostima) — ćelija te veličine ne vidi grad. Poređenje se računa ovde i
ostaje u izlazu, da tvrdnja na stranici ima pokriće.

IZVOR. SEPA-ini sajtovi su nedostupni, ali Srbija izveštava EEA, pa se
validirani časovni podaci dohvataju sa EEA download servisa, bez ključa i bez
registracije. Tri stanice su relevantne za koridor:

  RS0033A  urbana pozadina   288 m od ose  <- reprezentativna za koridor
  RS0030A  saobraćajna     1054 m od ose  <- daje saobraćajni doprinos
  RS0005R  ruralna pozadina  8,8 km       <- daje regionalnu pozadinu

ŠTA OVDE JESTE PROSTORNO, A ŠTA NIJE. Dve urbane stanice su 400 m jedna od
druge; interpolacija između njih preko 13 km trase ne bi izvlačila prostornu
informaciju nego oblikovala artefakt od toga gde su stanice postavljene. Zato
se ne interpolira. Umesto toga se koristi ono što par stanica zaista meri —
razlika između saobraćajne i pozadinske lokacije — kao *veličina* saobraćajnog
doprinosa, a raspoređuje se duž trase modelom blizine puteva iz buka.py:

  C(tačka) = C_regionalno + C_urbano + k · P(tačka)

gde je P suma emisija puteva sa eksponencijalnim opadanjem (NO2 blizu puta pada
sa karakterističnom dužinom od ~60 m, ne sa 1/d² kao zvuk), a k je ukotvljeno
tako da razlika P između dve stanice daje izmerenu razliku koncentracija.
Regionalni i urbani član su izmereni, ne modelirani.

Zato izlaz ide po deonici, ne po tački: ukotvljena je samo *ukupna* razlika
između dve lokacije, pa razlika na nivou pojedinačne tačke od 10 m nosi više
preciznosti nego što podaci imaju.

PARQUET. EEA daje parquet, a ni pyarrow ni duckdb nemaju wheel za Python 3.14
koji projekat koristi. Skript zato radi i van projektnog venv-a:

  uv run --python 3.13 --with pyarrow python vazduh.py

Zbog toga uvozi samo standardnu biblioteku, koridor.py i buka.py — nigde
numpy, da izolovano okruženje ne mora ništa više da instalira.

Izvori: EEA / SEPA (validirani E1a) · CAMS preko Open-Meteo (CC BY 4.0).
"""
import csv
import email.utils
import json
import math
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from koridor import ROOT, STAZE, planar_xy, prepare
from buka import bbox_of, build_segments, fetch_roads

OUT_FILE = os.path.join(ROOT, "data", "vazduh.json")
CACHE_DIR = os.path.join(ROOT, "data", ".cache", "vazduh")

VAZDUH_SCHEMA = 1

# ---------- izvori ----------

EEA_API = "https://eeadmz1-downloads-api-appservice.azurewebsites.net"
EEA_META = "https://discomap.eea.europa.eu/map/fme/metadata/PanEuropean_metadata.csv"
AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
UA = {"User-Agent": "biciklisticki-koridor/1.0 (github pages)"}

ZEMLJA = "RS"
# EEA šifre polutanata -> naši ključevi
POLUTANTI = {"pm2_5": 6001, "pm10": 5, "no2": 8}
# dataset 2 = validirani (E1a). Nevalidirani skorašnji podaci (1) se ne koriste.
DATASET = 2

# Stanica ulazi u razmatranje ako je bliža od ovoga osi koridora. Ruralna
# pozadina je 8,8 km i treba nam — bez nje nema regionalnog člana.
MAX_D_KM = 15.0

# ---------- pragovi ----------

# SZO 2021 (µg/m³). Preporuke, nisu obavezujuće.
SZO_DNEVNI = {"pm2_5": 15.0, "pm10": 45.0, "no2": 25.0}
SZO_GODISNJI = {"pm2_5": 5.0, "pm10": 15.0, "no2": 10.0}

# Uredba o uslovima za monitoring i zahtevima kvaliteta vazduha (RS), usklađena
# sa 2008/50/EZ. Ovo su granične vrednosti — obavezujuće, sa dopuštenim brojem
# prekoračenja gde ga zakon predviđa.
GRANICA_DNEVNA = {"pm10": 50.0}
GRANICA_DOPUSTENO_DANA = {"pm10": 35}
GRANICA_GODISNJA = {"pm10": 40.0, "pm2_5": 25.0, "no2": 40.0}

MESECI = ["jan", "feb", "mar", "apr", "maj", "jun",
          "jul", "avg", "sep", "okt", "nov", "dec"]

# ---------- model raspodele saobraćajnog doprinosa ----------

# Karakteristična dužina opadanja NO2 uz put. Literatura daje 50–150 m za
# prigradske i gradske uslove; 60 m je konzervativno (brže opadanje = manja
# razlika između deonica, pa se ne preuveličava efekat izbora staze).
DECAY_L_M = 60.0
PROX_R_M = 400.0        # exp(-400/60) = 0,001 — dalje je nemerljivo
EMIT_STEP_M = 10.0      # na koliko se segmenti puta dele u tačkaste emitere
D_MIN_M = 5.0           # ne dozvoli nulu kad tačka leži na putu

# Posle ovoliko dana se proverava da li EEA ima noviju verziju fajla.
# Validirani podaci stižu jednom godišnje, ali provera je uslovna pa
# ništa ne košta kad promene nema.
CACHE_MAX_DANA = 14

MIN_DANA_GODINA = 300   # ispod ovoga godina nije reprezentativna
MIN_SATI_DAN = 18       # dnevni prosek zahteva ovoliko validnih sati

# Glavni brojevi se računaju iz poslednjih toliko godina koje SVE stanice za
# taj polutant imaju. NO2 postoji od 2013, PM2.5 tek od 2024 — bez ovoga bi se
# na istoj stranici poredio trinaestogodišnji prosek sa dvogodišnjim. Cela
# istorija po godinama ostaje u izlazu, za trend.
GLAVNIH_GODINA = 3

# Sezona korišćenja keja — isti prozor koji 9.1 koristi za leto. Nije samo
# pitanje relevantnosti nego i ispravnosti: zimi pozadinska stanica ima VIŠI
# NO2 od saobraćajne (januar 41,7 prema 25,2), jer stoji u naselju sa
# individualnim grejanjem. Godišnja razlika između dve stanice zato meša
# saobraćaj sa dimnjacima i potcenjuje saobraćajni deo tri i po puta. U toploj
# polovini godine grejanja nema, pa razlika između te dve lokacije ostaje ono
# što i tvrdimo da jeste — blizina puta.
SEZONA_MESECI = (5, 6, 7, 8, 9)


# ---------- EEA metapodaci ----------

def _cache_get(url, name):
    """Fajl iz keša, sa rokom trajanja.

    EEA menja iste URL-ove u mestu kad objavi novu porciju validiranih
    podataka — nova godina ne dobija novo ime fajla. Keš bez roka bi zato
    značio da `make vazduh` i za godinu dana vrti istu, zastarelu 2025.

    Posle CACHE_MAX_DANA se šalje uslovni zahtev sa `If-Modified-Since`.
    Discomap ga poštuje i na nepromenjen fajl vraća 304, pa se metapodaci od
    26 MB ne skidaju ponovo. Azure blob, na kome stoje parquet fajlovi, vraća
    200 bez obzira na zaglavlje, pa se oni ponovo preuzimaju — ali svih osam
    zajedno je oko 4,6 MB jednom u dve nedelje, što ne vredi zaobilaziti.

    Skida se u privremeni fajl pa preimenuje, da prekinuto preuzimanje ne
    ostavi krnj keš koji izgleda ispravno.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, name)
    od_kada = None
    if os.path.exists(path) and os.path.getsize(path) > 0:
        mtime = os.path.getmtime(path)
        if time.time() - mtime < CACHE_MAX_DANA * 86400:
            return path
        od_kada = mtime

    req = urllib.request.Request(url, headers=dict(UA))
    if od_kada is not None:
        req.add_header("If-Modified-Since",
                       email.utils.formatdate(od_kada, usegmt=True))
        print(f"  proveravam ima li novija verzija: {name} ...", flush=True)
    else:
        print(f"  preuzimam {name} ...", flush=True)

    try:
        r = urllib.request.urlopen(req, timeout=300)
    except urllib.error.HTTPError as exc:
        if exc.code == 304 and od_kada is not None:
            os.utime(path, None)
            print("    bez promene na serveru")
            return path
        raise

    tmp = path + ".tmp"
    with r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    os.replace(tmp, path)
    if od_kada is not None:
        print("    preuzeta novija verzija")
    return path


def fetch_stanice():
    """Stanice za ZEMLJA iz EEA metapodataka: koordinate, tip, polutanti."""
    path = _cache_get(EEA_META, "PanEuropean_metadata.csv")
    st = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r.get("Countrycode") != ZEMLJA:
                continue
            try:
                lat, lon = float(r["Latitude"]), float(r["Longitude"])
            except (TypeError, ValueError):
                continue
            kod = r["AirQualityStationEoICode"]
            d = st.setdefault(kod, {
                "kod": kod, "lat": lat, "lon": lon,
                "tip": r["AirQualityStationType"],
                "okruzenje": r["AirQualityStationArea"],
                "polutanti": set(), "od": None,
            })
            sifra = r["AirPollutantCode"].rsplit("/", 1)[-1]
            for kljuc, s in POLUTANTI.items():
                if sifra == str(s):
                    d["polutanti"].add(kljuc)
            beg = (r.get("ObservationDateBegin") or "")[:4]
            if beg.isdigit():
                d["od"] = min(d["od"] or 9999, int(beg))
    return st


def izaberi_stanice(axis):
    """Stanice bliže od MAX_D_KM osi, sa rastojanjem do najbliže tačke ose."""
    osa = [planar_xy(c[0], c[1]) for c in axis]
    out = []
    for d in fetch_stanice().values():
        if not d["polutanti"]:
            continue
        x, y = planar_xy(d["lon"], d["lat"])
        dist = min(math.hypot(x - px, y - py) for px, py in osa)
        if dist / 1000.0 > MAX_D_KM:
            continue
        d = dict(d, do_koridora_m=round(dist), polutanti=sorted(d["polutanti"]))
        out.append(d)
    out.sort(key=lambda d: d["do_koridora_m"])
    return out


# ---------- EEA merenja ----------

def parquet_urls(polutant):
    """URL-ovi parquet fajlova za jedan polutant, po mernom mestu."""
    body = json.dumps({
        "countries": [ZEMLJA], "cities": [],
        "pollutants": [f"http://dd.eionet.europa.eu/vocabulary/aq/pollutant/"
                       f"{POLUTANTI[polutant]}"],
        "dataset": DATASET, "source": "API",
    }).encode()
    req = urllib.request.Request(f"{EEA_API}/ParquetFile/urls", data=body,
                                 headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        txt = r.read().decode("utf-8-sig")
    return [ln.strip() for ln in txt.splitlines()
            if ln.strip().startswith("http")]


def dnevni_proseci(kod, polutant, urls):
    """Dnevni proseci validnih časovnih vrednosti za stanicu i polutant.

    Ako stanica ima više mernih mesta za isti polutant, časovi se spajaju;
    u praksi u Nišu ima po jedno.
    """
    import pyarrow.parquet as pq          # noqa: PLC0415  (samo ovde je potreban)

    mine = [u for u in urls if f"SPO-{kod}_" in u]
    if not mine:
        return {}
    po_danu = {}
    for u in mine:
        path = _cache_get(u, os.path.basename(u))
        t = pq.read_table(path, columns=["Start", "Value", "Validity"]).to_pydict()
        for s, v, val in zip(t["Start"], t["Value"], t["Validity"]):
            if val != 1 or v is None:
                continue
            x = float(v)
            if x < 0:
                continue
            po_danu.setdefault(s.date(), []).append(x)
    return {d: statistics.fmean(v) for d, v in po_danu.items()
            if len(v) >= MIN_SATI_DAN}


def casovni(kod, polutant, urls):
    """Validne časovne vrednosti {datetime: value} — za parne razlike."""
    import pyarrow.parquet as pq          # noqa: PLC0415

    out = {}
    for u in (u for u in urls if f"SPO-{kod}_" in u):
        path = _cache_get(u, os.path.basename(u))
        t = pq.read_table(path, columns=["Start", "Value", "Validity"]).to_pydict()
        for s, v, val in zip(t["Start"], t["Value"], t["Validity"]):
            if val == 1 and v is not None and float(v) >= 0:
                out[s] = float(v)
    return out


# ---------- statistika po stanici ----------

def po_godini(daily):
    g = {}
    for d, v in daily.items():
        g.setdefault(d.year, []).append(v)
    return {y: v for y, v in g.items() if len(v) >= MIN_DANA_GODINA}


def statistika(polutant, daily):
    """Prekoračenja i prosek po godini. Godina ulazi samo ako je popunjena."""
    god = po_godini(daily)
    if not god:
        return None
    szo_d = SZO_DNEVNI[polutant]
    gr_d = GRANICA_DNEVNA.get(polutant)
    godine = {}
    for y in sorted(god):
        v = god[y]
        godine[str(y)] = {
            "prosek": round(statistics.fmean(v), 1),
            "dana": len(v),
            "preko_szo": sum(1 for x in v if x > szo_d),
            "preko_granice": (sum(1 for x in v if x > gr_d)
                              if gr_d is not None else None),
        }
    return {"godine": godine}


def agregat(polutant, daily, godine, meseci=None):
    """Prosek, prekoračenja i sezonski hod preko zadatog skupa godina."""
    v = [(d, x) for d, x in daily.items() if d.year in godine
         and (meseci is None or d.month in meseci)]
    if not v:
        return None
    szo_d = SZO_DNEVNI[polutant]
    gr_d = GRANICA_DNEVNA.get(polutant)
    po_mesecu = {}
    for d, x in v:
        po_mesecu.setdefault(d.month, []).append(x)
    vals = [x for _, x in v]
    n_god = len(godine)
    return {
        "prosek": round(statistics.fmean(vals), 1),
        "dana": len(vals),
        "preko_szo": sum(1 for x in vals if x > szo_d),
        "pct_preko_szo": round(100.0 * sum(1 for x in vals if x > szo_d) / len(vals)),
        # prekoračenja granice se porede sa dopuštenim brojem PO GODINI, pa se
        # i prikazuju kao godišnji prosek, ne kao zbir kroz period
        "preko_granice_god": (round(sum(1 for x in vals if x > gr_d) / n_god)
                              if gr_d is not None else None),
        "po_mesecu": [round(statistics.fmean(po_mesecu[m]), 1) if m in po_mesecu
                      else None for m in range(1, 13)],
        "period": [min(godine), max(godine)],
    }


def glavni_period(polutant, kodovi, mereno):
    """Poslednjih GLAVNIH_GODINA godina koje sve zadate stanice imaju."""
    skupovi = [{int(y) for y in mereno[k][polutant]["godine"]}
               for k in kodovi if polutant in mereno.get(k, {})]
    if not skupovi:
        return []
    return sorted(set.intersection(*skupovi))[-GLAVNIH_GODINA:]


# ---------- poređenje sa CAMS-om ----------

CAMS_VAR = {"pm2_5": "pm2_5", "pm10": "pm10", "no2": "nitrogen_dioxide"}


def cams_dnevni(lat, lon, od, do):
    """Dnevni proseci CAMS-a na tački stanice, keširano po tački i periodu."""
    name = f"cams_{lat:.4f}_{lon:.4f}_{od}_{do}.json"
    path = os.path.join(CACHE_DIR, name)
    if os.path.exists(path):
        with open(path) as f:
            d = json.load(f)
    else:
        q = urllib.parse.urlencode({
            "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
            "hourly": ",".join(CAMS_VAR.values()),
            "domains": "cams_europe",
            "start_date": f"{od}-01-01", "end_date": f"{do}-12-31",
            "timezone": "Europe/Belgrade"})
        print(f"  preuzimam CAMS {od}–{do} ...", flush=True)
        req = urllib.request.Request(f"{AQ_URL}?{q}", headers=UA)
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.load(r)
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(path, "w") as f:
            json.dump(d, f)
    h = d["hourly"]
    out = {}
    for kljuc, var in CAMS_VAR.items():
        po_danu = {}
        for t, v in zip(h["time"], h.get(var) or []):
            if v is not None:
                po_danu.setdefault(t[:10], []).append(v)
        out[kljuc] = {dd: statistics.fmean(v) for dd, v in po_danu.items()
                      if len(v) >= MIN_SATI_DAN}
    return out


POLEN = {"grass_pollen": "trave", "birch_pollen": "breza",
         "ragweed_pollen": "ambrozija"}


def polen(lat, lon, od, do):
    """Sezonski hod polena iz CAMS-a, na centru koridora.

    Polen ostaje na CAMS-u jer ga merne stanice ne mere. To je i u redu: polen
    je regionalna pojava, pa ćelija od 11 km ovde nije nedostatak kao za NO2.
    """
    name = f"polen_{lat:.4f}_{lon:.4f}_{od}_{do}.json"
    path = os.path.join(CACHE_DIR, name)
    if os.path.exists(path):
        with open(path) as f:
            d = json.load(f)
    else:
        q = urllib.parse.urlencode({
            "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
            "hourly": ",".join(POLEN), "domains": "cams_europe",
            "start_date": f"{od}-01-01", "end_date": f"{do}-12-31",
            "timezone": "Europe/Belgrade"})
        print(f"  preuzimam polen {od}–{do} ...", flush=True)
        req = urllib.request.Request(f"{AQ_URL}?{q}", headers=UA)
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.load(r)
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(path, "w") as f:
            json.dump(d, f)
    h = d["hourly"]
    out = {}
    for var, naziv in POLEN.items():
        par = [(t, v) for t, v in zip(h["time"], h.get(var) or []) if v is not None]
        if not par:
            continue
        po_mesecu = {}
        for t, v in par:
            po_mesecu.setdefault(int(t[5:7]), []).append(v)
        vrhunac = max(po_mesecu, key=lambda m: statistics.fmean(po_mesecu[m]))
        out[naziv] = {
            "max": round(max(v for _, v in par)),
            "vrhunac_mesec": MESECI[vrhunac - 1],
            "po_mesecu": [round(statistics.fmean(po_mesecu[m]), 1)
                          if m in po_mesecu else None for m in range(1, 13)],
        }
    return {"period": [od, do], "vrste": out}


def pearson(a, b):
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else None


def uporedi_sa_cams(daily_st, cams, periodi):
    """Stanica protiv CAMS-a na istim danima. Opravdanje za zamenu izvora.

    Svaki polutant se poredi na svom glavnom periodu, da odnos ne bi mešao
    trinaest godina NO2 sa dve godine PM2.5.
    """
    out = {}
    for polutant, st in daily_st.items():
        cm = cams.get(polutant, {})
        godine = set(periodi.get(polutant, ()))
        par = [(st[d], cm[d.isoformat()]) for d in sorted(st)
               if d.year in godine and d.isoformat() in cm]
        if len(par) < 200:
            continue
        a = [x for x, _ in par]
        b = [y for _, y in par]
        sa, sb = statistics.fmean(a), statistics.fmean(b)
        out[polutant] = {
            "dana": len(par),
            "period": [min(godine), max(godine)],
            "stanica": round(sa, 1),
            "cams": round(sb, 1),
            "odnos": round(sa / sb, 2) if sb else None,
            "r": round(pearson(a, b), 2),
            "preko_szo_stanica": round(
                100.0 * sum(1 for x in a if x > SZO_DNEVNI[polutant]) / len(a)),
            "preko_szo_cams": round(
                100.0 * sum(1 for y in b if y > SZO_DNEVNI[polutant]) / len(b)),
        }
    return out


# ---------- doprinosi iz parova stanica ----------

def razlika(a_h, b_h, godine, meseci=None):
    """Prosečna razlika dve stanice na istim časovima, i dnevni hod razlike."""
    par = [(t, a_h[t] - b_h[t]) for t in a_h if t in b_h and t.year in godine
           and (meseci is None or t.month in meseci)]
    if len(par) < 1000:
        return None
    po_satu = {}
    for t, dv in par:
        po_satu.setdefault(t.hour, []).append(dv)
    return {
        "parova": len(par),
        "razlika": round(statistics.fmean([d for _, d in par]), 1),
        "po_satu": [round(statistics.fmean(po_satu[h]), 1) if h in po_satu
                    else None for h in range(24)],
    }


# ---------- prostorna raspodela saobraćajnog dela ----------

def emiteri(segs):
    """Segmenti puta -> tačkasti emiteri na svakih EMIT_STEP_M, sa težinom.

    Emisija je proporcionalna dužini, pa deljenje segmenta ne menja ukupnu
    jačinu — samo aproksimira integral duž linije sumom po delovima.
    """
    pts = []
    for (ax, ay), (bx, by), w, length, _major in segs:
        n = max(1, int(math.ceil(length / EMIT_STEP_M)))
        dx, dy = (bx - ax) / n, (by - ay) / n
        wd = w * length / n
        for i in range(n):
            pts.append((ax + dx * (i + 0.5), ay + dy * (i + 0.5), wd))
    return pts


def grid_emitera(pts, cell=PROX_R_M):
    g = {}
    for p in pts:
        g.setdefault((int(p[0] // cell), int(p[1] // cell)), []).append(p)
    return g


def blizina(x, y, grid, cell=PROX_R_M):
    """P(x) = Σ w·exp(-d/L) po emiterima u krugu PROX_R_M."""
    cx, cy = int(x // cell), int(y // cell)
    s = 0.0
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for px, py, w in grid.get((cx + i, cy + j), ()):
                d = math.hypot(x - px, y - py)
                if d > PROX_R_M:
                    continue
                s += w * math.exp(-max(d, D_MIN_M) / DECAY_L_M)
    return s


# ---------- glavni ulaz ----------

def main():
    try:
        import pyarrow  # noqa: F401,PLC0415
    except ImportError:
        print("ERROR: treba pyarrow, a za Python 3.14 nema wheel-a.\n"
              "Pokreni:  uv run --python 3.13 --with pyarrow python vazduh.py",
              file=sys.stderr)
        return 1

    axis, by_tip, deon_order = prepare()

    print("Stanice:")
    stanice = izaberi_stanice(axis)
    if not stanice:
        print("ERROR: nema stanica u krugu od %.0f km" % MAX_D_KM, file=sys.stderr)
        return 1
    for s in stanice:
        print(f"  {s['kod']}  {s['tip']:12} {s['okruzenje']:10} "
              f"{s['do_koridora_m']:6} m od ose  {s['polutanti']}")

    # Reprezentativna je najbliža pozadinska: koridor je rečni kej, ne ulica,
    # pa je pozadinski tip i tačan i najbliži.
    poz = [s for s in stanice if s["tip"] == "background"
           and s["okruzenje"] == "urban"]
    saob = [s for s in stanice if s["tip"] == "traffic"]
    rur = [s for s in stanice if s["okruzenje"] == "rural"]
    if not poz:
        print("ERROR: nema urbane pozadinske stanice", file=sys.stderr)
        return 1
    rep, st_saob, st_rur = poz[0], (saob[0] if saob else None), (rur[0] if rur else None)
    print(f"  -> reprezentativna: {rep['kod']} ({rep['do_koridora_m']} m od ose)")

    # ---- merenja ----
    urls = {p: parquet_urls(p) for p in POLUTANTI}
    daily = {}      # (kod, polutant) -> {date: val}
    hourly = {}     # (kod, polutant) -> {datetime: val}
    trazeni = [s for s in (rep, st_saob, st_rur) if s]
    for s in trazeni:
        for p in s["polutanti"]:
            daily[(s["kod"], p)] = dnevni_proseci(s["kod"], p, urls[p])

    mereno = {}
    for s in trazeni:
        po_pol = {}
        for p in s["polutanti"]:
            stat = statistika(p, daily.get((s["kod"], p), {}))
            if stat:
                po_pol[p] = stat
        if po_pol:
            mereno[s["kod"]] = po_pol

    # glavni period po polutantu: presek godina svih stanica koje ga mere
    periodi = {p: glavni_period(p, [s["kod"] for s in trazeni], mereno)
               for p in POLUTANTI}
    periodi = {p: g for p, g in periodi.items() if g}
    for kod, po_pol in mereno.items():
        for p, st in po_pol.items():
            if p in periodi:
                st["glavni"] = agregat(p, daily[(kod, p)], set(periodi[p]))
                st["sezona"] = agregat(p, daily[(kod, p)], set(periodi[p]),
                                       SEZONA_MESECI)

    print("\nGlavni period po polutantu:",
          ", ".join(f"{p} {g[0]}–{g[-1]}" for p, g in periodi.items()))
    print("Izmereno (prosek na glavnom periodu, µg/m³):")
    for kod, po_pol in mereno.items():
        for p, st in po_pol.items():
            g = st.get("glavni")
            if not g:
                continue
            red = (f"  {kod} {p:6} prosek {g['prosek']:5.1f} "
                   f"(SZO god. {SZO_GODISNJI[p]:g}, granica "
                   f"{GRANICA_GODISNJA.get(p, '-')})  "
                   f"preko SZO dnevno {g['pct_preko_szo']:3d} % dana")
            if g["preko_granice_god"] is not None:
                red += (f"  preko granice {g['preko_granice_god']} dana/god "
                        f"(dopušteno {GRANICA_DOPUSTENO_DANA[p]})")
            print(red)

    # ---- CAMS protiv stanice ----
    sve_godine = {y for g in periodi.values() for y in g}
    cams = cams_dnevni(rep["lat"], rep["lon"], min(sve_godine), max(sve_godine))
    poredjenje = uporedi_sa_cams(
        {p: daily[(rep["kod"], p)] for p in mereno.get(rep["kod"], {})},
        cams, periodi)
    print("\nCAMS protiv stanice (isti dani, glavni period):")
    for p, c in poredjenje.items():
        print(f"  {p:6} stanica {c['stanica']:5.1f}  CAMS {c['cams']:5.1f}  "
              f"odnos {c['odnos']:.2f}x  r={c['r']:.2f}  "
              f"dana preko SZO: {c['preko_szo_stanica']}% / {c['preko_szo_cams']}%")

    # ---- doprinosi ----
    for s in trazeni:
        for p in s["polutanti"]:
            hourly[(s["kod"], p)] = casovni(s["kod"], p, urls[p])

    # Imena su namerno opisna a ne tumačeća: ovo su razlike između dve
    # lokacije na istim časovima. Kao saobraćajni doprinos se dalje koristi
    # samo NO2 — razlika u PM2.5 ima vrh u 16–20 h, što je grejanje, a ne špic,
    # pa je nazvati saobraćajnom bilo bi netačno.
    razlike = {}
    for p, godine in periodi.items():
        g = set(godine)
        d = {}
        if st_saob and (st_saob["kod"], p) in hourly and (rep["kod"], p) in hourly:
            r = razlika(hourly[(st_saob["kod"], p)], hourly[(rep["kod"], p)], g)
            if r:
                d["saobracajna_minus_pozadina"] = r
            r = razlika(hourly[(st_saob["kod"], p)], hourly[(rep["kod"], p)], g,
                        SEZONA_MESECI)
            if r:
                d["saobracajna_minus_pozadina_sezona"] = r
        if st_rur and (st_rur["kod"], p) in hourly and (rep["kod"], p) in hourly:
            r = razlika(hourly[(rep["kod"], p)], hourly[(st_rur["kod"], p)], g)
            if r:
                d["pozadina_minus_ruralna"] = r
        if d:
            d["period"] = [godine[0], godine[-1]]
            razlike[p] = d
    print("\nRazlike među stanicama (µg/m³, isti časovi):")
    for p, d in razlike.items():
        s = d.get("saobracajna_minus_pozadina", {}).get("razlika")
        sz = d.get("saobracajna_minus_pozadina_sezona", {}).get("razlika")
        u = d.get("pozadina_minus_ruralna", {}).get("razlika")
        print(f"  {p:6} saobraćajna−pozadina: cela godina "
              f"{s if s is not None else '-':>6}, sezona (maj–sep) "
              f"{sz if sz is not None else '-':>6}   "
              f"pozadina−ruralna {u if u is not None else '-':>6}")

    # ---- raspodela saobraćajnog dela duž trase ----
    po_deonici = None
    model = None
    if st_saob and "saobracajna_minus_pozadina_sezona" in razlike.get("no2", {}):
        # bbox mora da pokrije i stanice, ne samo osu — inače nema puteva oko
        # stanica, pa ni sidra
        lats = [c[1] for c in axis] + [rep["lat"], st_saob["lat"]]
        lons = [c[0] for c in axis] + [rep["lon"], st_saob["lon"]]
        # margina od ~600 m, da tačke na obodu ne izgube puteve iza ivice
        pad_lat = 600.0 / 111320.0
        pad_lon = 600.0 / (111320.0 * math.cos(math.radians(statistics.fmean(lats))))
        bbox = (min(lats) - pad_lat, min(lons) - pad_lon,
                max(lats) + pad_lat, max(lons) + pad_lon)
        segs = build_segments(fetch_roads(bbox))
        grid = grid_emitera(emiteri(segs))
        print(f"\nModel blizine: {len(segs)} segmenata, L={DECAY_L_M:g} m")

        p_saob = blizina(*planar_xy(st_saob["lon"], st_saob["lat"]), grid)
        p_rep = blizina(*planar_xy(rep["lon"], rep["lat"]), grid)
        dp = p_saob - p_rep
        print(f"  P(saobraćajna)={p_saob:.1f}  P(pozadinska)={p_rep:.1f}  ΔP={dp:.1f}")
        if dp <= 0:
            print("  ! ΔP nije pozitivno — sidro ne važi, raspodela se preskače")
        else:
            # Sve tri kotve su iz iste, tople polovine godine: sidro, urbani i
            # regionalni član. Mešanje sezonskog sidra sa godišnjim nivoom dalo
            # bi broj koji ne opisuje nijedan stvarni period.
            c_saob_izm = razlike["no2"]["saobracajna_minus_pozadina_sezona"]["razlika"]
            k = c_saob_izm / dp
            c_rur = (mereno.get(st_rur["kod"], {}).get("no2", {})
                     .get("sezona", {}).get("prosek") if st_rur else None)
            c_rep = mereno[rep["kod"]]["no2"]["sezona"]["prosek"]
            # C = regionalno + urbano + k·P; urbano je ostatak posle
            # regionalnog i saobraćajnog dela NA POZADINSKOJ stanici
            c_urb = c_rep - (c_rur or 0.0) - k * p_rep
            print(f"  sidro je sezonsko (maj–sep): razlika {c_saob_izm} µg/m³")
            print(f"  k={k:.4f} µg/m³ po jedinici P; regionalno={c_rur}, "
                  f"urbano={c_urb:.1f}, pozadina u sezoni={c_rep}")
            po_deonici = {}
            for tip, label in STAZE:
                po_dn = {}
                for dn in deon_order:
                    sel = [s for s in by_tip[tip] if s["deonica"] == dn]
                    if not sel:
                        continue
                    pv = [blizina(*planar_xy(s["lon"], s["lat"]), grid) for s in sel]
                    sr = statistics.fmean(pv)
                    po_dn[dn] = {
                        "n": len(sel),
                        "no2": round((c_rur or 0.0) + c_urb + k * sr, 1),
                        "saobracajni": round(k * sr, 1),
                    }
                po_deonici[tip] = po_dn
                print(f"  {label}: " + "  ".join(
                    f"{dn} {v['no2']:.1f} (+{v['saobracajni']:.1f})"
                    for dn, v in po_dn.items()))
            model = {
                "polutant": "no2",
                "sezona_meseci": list(SEZONA_MESECI),
                "L_m": DECAY_L_M, "radius_m": PROX_R_M, "k": round(k, 5),
                "regionalno": c_rur, "urbano": round(c_urb, 1),
                "pozadina_sezona": c_rep,
                "sidro": {"saobracajna": st_saob["kod"], "pozadinska": rep["kod"],
                          "izmerena_razlika": c_saob_izm,
                          "P_saobracajna": round(p_saob, 1),
                          "P_pozadinska": round(p_rep, 1)},
            }

    lat0 = statistics.fmean(c[1] for c in axis)
    lon0 = statistics.fmean(c[0] for c in axis)
    pol = polen(lat0, lon0, min(sve_godine), max(sve_godine))
    print("\nPolen (vrhunac):", ", ".join(
        f"{n} {v['vrhunac_mesec']}" for n, v in pol["vrste"].items()))

    out = {
        "schema": VAZDUH_SCHEMA,
        "source": "EEA (SEPA, validirani E1a) · CAMS preko Open-Meteo (CC BY 4.0)",
        "stanice": stanice,
        "reprezentativna": rep["kod"],
        "saobracajna": st_saob["kod"] if st_saob else None,
        "ruralna": st_rur["kod"] if st_rur else None,
        "mereno": mereno,
        "szo_dnevni": SZO_DNEVNI,
        "szo_godisnji": SZO_GODISNJI,
        "granica_dnevna": GRANICA_DNEVNA,
        "granica_dopusteno_dana": GRANICA_DOPUSTENO_DANA,
        "granica_godisnja": GRANICA_GODISNJA,
        "cams": poredjenje,
        "periodi": periodi,
        "razlike": razlike,
        "deonice": deon_order,
        "po_deonici": po_deonici,
        "model": model,
        "polen": pol,
        "meseci": MESECI,
    }
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\n  -> {os.path.relpath(OUT_FILE, ROOT)} "
          f"({os.path.getsize(OUT_FILE) / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
