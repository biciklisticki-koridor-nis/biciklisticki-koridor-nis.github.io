#!/usr/bin/env python3
"""Termalni komfor duž koridora (analiza 9.3).

REZULTAT JE U STEPENIMA, NE U INDEKSU. Prethodne analize daju ocene 0–100 jer
im nedostaje merilo; ovde ga ima. UTCI je ekvivalentna temperatura — kaže na
koliko bi stepeni u mirnom i zaklonjenom okruženju čovek osećao isto što oseća
na ovom mestu. Ima priznatu skalu stresa, pa se ne mora verovati našem izboru
težina: „jak toplotni stres" je definicija, ne naša procena.

Zašto ne indeks od više faktora. Senka, krošnje, vegetacija, otvorenost neba i
izloženost suncu su u velikoj meri ista promenljiva merena pet puta. Sabrati
ih sa izabranim težinama dalo bi broj koji izgleda kao pet faktora a ponaša se
kao jedan, i čija vrednost zavisi od težina koje smo mi izabrali. Umesto toga
se računa fizika, a ti faktori ostaju kao *objašnjenje* zašto je negde toplije.

ŠTA SE RAČUNA, PO TAČKI I PO SATU:

  SVF   faktor vidljivosti neba — koliki deo nebeskog svoda tačka vidi.
        Zrakom u 36 pravaca preko mape visine krošnji; SVF = 1 − ⟨sin²β⟩,
        gde je β najveći ugao zaklona u tom pravcu.

  Tmrt  srednja radijantna temperatura — ono što senka zapravo menja.
        Temperatura vazduha se duž 13 km praktično ne menja, ali Tmrt između
        sunca i senke razlikuje se i po 25 °C. Čovek se modelira kao uspravan
        valjak (1,75 m × 0,35 m), pa faktor projektovane površine izlazi iz
        geometrije, ne iz tabele.

  UTCI  iz Tmrt, temperature vazduha, vetra i vlažnosti (utci.py).

SCENARIO je vruć vedar letnji dan: geometrija Sunca za 21. jun, meteorologija
kao prosek najtoplije četvrtine dana u prozoru od ±15 dana oko solsticija, kroz
poslednjih deset godina, za sate 12–17. To je slučaj zbog kojeg se senka i
sadi — ne prosek leta, u kome kišni dani razblaže ono što se meri.

ŠTA NAMERNO NIJE UNUTRA:

  Zgrade. U OSM-u ih oko koridora ima 38.297, ali 99 % nema nijedan podatak o
  visini, pa bi im se visina morala izmisliti. Izmereno je koliko to košta:
  samo 3,7 % tačaka trase ima zgradu bliže od 20 m, a medijana rastojanja je
  43 m (Centar) do 97 m (Delta–Lidl). Zgrada na 43 m sa 15 m visine zaklanja
  nebo do 19° — a Sunce je u prozoru 12–17 h uvek iznad 30°. Dakle ni ne
  zaklanja niti bitno smanjuje SVF. Kej je nasip uz reku, ne ulični kanjon.

  Tip podloge. Asfalt na suncu je i 20 °C topliji od prirodne podloge, a
  OpenStreetMap ga za staze uz Nišavu skoro ne beleži. Zato se za temperaturu
  tla uzima reanaliza (prirodna podloga), što znači da su vrednosti na
  asfaltnim delovima POTCENJENE. Podloga se upisuje na terenskom izlasku za
  9.2 i ulazi ovde kad stigne.

Izvori: Meta/WRI Global Canopy Height (CC BY 4.0) · ERA5 preko Open-Meteo
(CC BY 4.0) · UTCI operativna procedura (vidi utci.py).
"""
import json
import math
import os
import statistics
import sys
import urllib.parse
import urllib.request

import numpy as np

from koridor import ROOT, STAZE, merc_xy, prepare, samples_hash
from shade_canopy import OBSERVER_H, compute_masks, load_chm, sun_pos
from utci import KATEGORIJE, kategorija, utci

OUT_FILE = os.path.join(ROOT, "data", "termalni.json")
DATA = os.path.join(ROOT, "data")
METEO_CACHE = os.path.join(ROOT, "data", ".cache", "termalni")

TERMALNI_SCHEMA = 1

# ---------- scenario ----------

DATUM = "jun21"                 # maske senke iz 9.1 su za ovaj datum
SATI = [12, 13, 14, 15, 16, 17]  # Sunce je tada iznad 30°, a kej se koristi
DOY = 172                       # 21. jun
TZ = 2                          # Europe/Belgrade, letnje vreme

METEO_GODINE = 10               # koliko godina unazad za klimatologiju
METEO_PROZOR_DANA = 15          # ±dana oko solsticija
VRUCI_UDEO = 0.25               # gornja četvrtina dana po najvišoj temperaturi

# ---------- faktor vidljivosti neba ----------

SVF_SMEROVA = 36                # na svakih 10°; gušće ne menja SVF ni za 0,01
SVF_MAX_M = 150.0               # krošnja od 25 m na 150 m zaklanja 9,5°
SVF_START_M = 2.0               # ne gledaj u sopstvene noge

# ---------- radijacija ----------

SIGMA = 5.670374419e-8          # Stefan-Boltzmann (W/m²K⁴)
EPS_COVEK = 0.97                # emisivnost obučenog čoveka
ALFA_KRATKO = 0.7               # apsorpcija kratkotalasnog zračenja
EPS_TLO = 0.95
EPS_ZELENILO = 0.98
ALBEDO_TLA = 0.15               # između asfalta (0,10) i trave (0,20)

# Uspravan valjak kao model čoveka: visina, prečnik (m). Faktor projektovane
# površine se odatle izvodi, pa nema prepisivanja koeficijenata iz tabela.
COVEK_H = 1.75
COVEK_D = 0.35

# ---------- mesta predaha (9.3.1) ----------

PREDAH_MIN_M = 30.0             # kraće od ovoga nije mesto nego tačka
PREDAH_MIN_SATI = 5             # u senci bar toliko od šest sati prozora
KLUPE_FILE = os.path.join(DATA, "klupe.geojson")
LETNJIKOVCI_FILE = os.path.join(DATA, "letnjikovci.geojson")

# Mapa visine krošnji vidi drveće, ne građevine. Letnjikovac ima sopstveni
# krov, pa „nema senke od krošnji" kod njega ne znači da je na suncu — znači
# samo da nad njim nema drveta. Bez ove napomene broj bi se čitao naopako.
OPREMA_NAPOMENA = {
    "letnjikovci": "imaju sopstveni krov, koji mapa visine krošnji ne vidi",
}
PREDAH_KLUPA_M = 25.0           # klupa ovoliko od predaha se računa kao njegova


# ---------- meteorologija ----------

def _dani_prozora(godine):
    """Datumi u prozoru oko solsticija, za zadate godine."""
    import datetime                                   # noqa: PLC0415
    out = []
    for g in godine:
        sredina = datetime.date(g, 6, 21)
        for d in range(-METEO_PROZOR_DANA, METEO_PROZOR_DANA + 1):
            out.append(sredina + datetime.timedelta(days=d))
    return out


def preuzmi_meteo(lat, lon, godine):
    """Satni ERA5 za prozor oko solsticija. Keš po tački i opsegu godina."""
    os.makedirs(METEO_CACHE, exist_ok=True)
    ime = f"era5_{lat:.4f}_{lon:.4f}_{godine[0]}_{godine[-1]}.json"
    path = os.path.join(METEO_CACHE, ime)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    q = urllib.parse.urlencode({
        "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
        "start_date": f"{godine[0]}-06-06", "end_date": f"{godine[-1]}-07-06",
        "hourly": ("temperature_2m,relative_humidity_2m,wind_speed_10m,"
                   "direct_normal_irradiance,diffuse_radiation,"
                   "shortwave_radiation,cloud_cover,soil_temperature_0_to_7cm"),
        "timezone": "Europe/Belgrade"})
    print(f"  preuzimam ERA5 {godine[0]}–{godine[-1]} ...", flush=True)
    req = urllib.request.Request(
        f"https://archive-api.open-meteo.com/v1/archive?{q}",
        headers={"User-Agent": "biciklisticki-koridor/1.0 (github pages)"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.load(r)
    with open(path, "w") as f:
        json.dump(d, f)
    return d


def vruc_dan(meteo, godine):
    """Prosečni satni uslovi na najtoplijoj četvrtini dana u prozoru.

    Prosek preko svih letnjih dana razblažio bi ono što merimo — kišni i
    oblačni dani spuštaju i sunce i Tmrt, a senka se ne sadi zbog njih.
    """
    h = meteo["hourly"]
    prozor = {d.isoformat() for d in _dani_prozora(godine)}
    po_danu = {}
    for i, t in enumerate(h["time"]):
        dan = t[:10]
        if dan in prozor:
            po_danu.setdefault(dan, []).append(i)

    # rangiraj dane po najvišoj dnevnoj temperaturi
    def tmax(idx):
        v = [h["temperature_2m"][i] for i in idx
             if h["temperature_2m"][i] is not None]
        return max(v) if v else -99
    dani = sorted(po_danu, key=lambda d: tmax(po_danu[d]), reverse=True)
    izabrani = dani[:max(1, int(len(dani) * VRUCI_UDEO))]

    polja = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m",
             "direct_normal_irradiance", "diffuse_radiation",
             "shortwave_radiation", "cloud_cover", "soil_temperature_0_to_7cm"]
    po_satu = {}
    for dan in izabrani:
        for i in po_danu[dan]:
            sat = int(h["time"][i][11:13])
            if sat not in SATI:
                continue
            red = po_satu.setdefault(sat, {p: [] for p in polja})
            for p in polja:
                v = h[p][i]
                if v is not None:
                    red[p].append(v)
    out = {}
    for sat in SATI:
        red = po_satu.get(sat)
        if not red or not red["temperature_2m"]:
            continue
        out[sat] = {p: statistics.fmean(red[p]) for p in polja if red[p]}
        # km/h -> m/s; UTCI traži vetar na 10 m i ne važi ispod 0,5 m/s
        out[sat]["vetar_ms"] = max(0.5, out[sat]["wind_speed_10m"] / 3.6)
    return out, len(izabrani), len(dani)


# ---------- faktor vidljivosti neba ----------

def izracunaj_svf(samples, arr, origin, res):
    """SVF po tački: 1 − ⟨sin²β⟩ preko SVF_SMEROVA pravaca.

    β je najveći ugao pod kojim se iz tačke vidi prepreka u tom pravcu. Formula
    pretpostavlja da prepreka u sektoru zaklanja sve ispod β, što je standardna
    aproksimacija za SVF iz horizontskih uglova.
    """
    H, W = arr.shape
    n = len(samples)
    px = np.empty(n)
    py = np.empty(n)
    for i, s in enumerate(samples):
        x, y = merc_xy(s["lon"], s["lat"])
        px[i] = (x - origin[0]) / res
        py[i] = (origin[1] - y) / res

    t = np.arange(SVF_START_M, SVF_MAX_M, res)
    suma = np.zeros(n)
    for k in range(SVF_SMEROVA):
        az = math.radians(k * 360.0 / SVF_SMEROVA)
        cols = np.clip((px[:, None] + t[None, :] * math.sin(az) / res)
                       .astype(np.int32), 0, W - 1)
        rows = np.clip((py[:, None] - t[None, :] * math.cos(az) / res)
                       .astype(np.int32), 0, H - 1)
        visina = arr[rows, cols] - OBSERVER_H
        ugao = np.arctan2(np.maximum(visina, 0.0), t[None, :])
        suma += np.sin(ugao.max(axis=1)) ** 2
    return 1.0 - suma / SVF_SMEROVA


# ---------- zračenje ----------

def faktor_projekcije(elev_deg):
    """Udeo površine tela okrenut ka direktnom snopu, za uspravan valjak.

    Bočna strana se projektuje kao pravougaonik D·H·cos(h), gornja osnova kao
    disk (πD²/4)·sin(h); deli se ukupnom površinom valjka. Na horizontu daje
    0,29, u zenitu 0,05 — u skladu sa tabelama za uspravnog čoveka.
    """
    h = math.radians(elev_deg)
    proj = COVEK_D * COVEK_H * math.cos(h) + (math.pi * COVEK_D ** 2 / 4) * math.sin(h)
    ukupno = math.pi * COVEK_D * COVEK_H + math.pi * COVEK_D ** 2 / 2
    return proj / ukupno


def emisivnost_neba(ta_c, rh, oblaci_pct):
    """Efektivna emisivnost neba: Brutsaert za vedro, pa korekcija na oblake."""
    tk = ta_c + 273.15
    # pritisak vodene pare (hPa) preko Magnusove formule
    es = 6.112 * math.exp(17.62 * ta_c / (243.12 + ta_c))
    e = es * rh / 100.0
    vedro = 1.24 * (e / tk) ** (1.0 / 7.0)
    c = max(0.0, min(1.0, oblaci_pct / 100.0))
    return vedro + (1.0 - vedro) * c


def tmrt(sunce, svf, m, elev_deg):
    """Srednja radijantna temperatura (°C) za jednu tačku u jednom satu.

    sunce  1 ako direktan snop stiže do tačke (maska senke iz 9.1)
    svf    faktor vidljivosti neba
    m      meteorologija tog sata
    """
    ta = m["temperature_2m"]
    tk = ta + 273.15
    t_tlo = m.get("soil_temperature_0_to_7cm", ta) + 273.15

    # Kratkotalasno. Difuzno i odbijeno nose faktor 0,5 jer telo svaku od njih
    # prima iz jedne polusfere; direktno ga ne nosi, jer faktor projekcije već
    # daje udeo površine okrenut ka snopu.
    k_direkt = sunce * m["direct_normal_irradiance"] * faktor_projekcije(elev_deg)
    k_difuzno = 0.5 * svf * m["diffuse_radiation"]
    # Tlo odbija ono što na njega stigne NA TOM MESTU, a ne globalno zračenje:
    # u senci je i tlo u senci, pa odbija višestruko manje.
    na_tlu = (sunce * m["direct_normal_irradiance"]
              * math.sin(math.radians(max(elev_deg, 0.0)))
              + svf * m["diffuse_radiation"])
    k_odbijeno = 0.5 * ALBEDO_TLA * na_tlu

    # dugotalasno: gornja polusfera je nebo + prepreke, donja je tlo
    l_nebo = svf * emisivnost_neba(ta, m["relative_humidity_2m"],
                                   m["cloud_cover"]) * SIGMA * tk ** 4
    l_prepreke = (1.0 - svf) * EPS_ZELENILO * SIGMA * tk ** 4
    l_tlo = EPS_TLO * SIGMA * t_tlo ** 4

    apsorbovano = (ALFA_KRATKO * (k_direkt + k_difuzno + k_odbijeno)
                   + EPS_COVEK * (0.5 * (l_nebo + l_prepreke) + 0.5 * l_tlo))
    return (apsorbovano / (EPS_COVEK * SIGMA)) ** 0.25 - 273.15


# ---------- mesta predaha ----------

def ucitaj_tacke(path, ime):
    """Tačke iz GeoJSON-a (klupe, letnjikovci) kao lista (lon, lat)."""
    if not os.path.exists(path):
        print(f"  ! nema {ime}, predasi se računaju bez njih")
        return []
    with open(path) as f:
        d = json.load(f)
    out = []
    for f_ in d.get("features", []):
        g = f_.get("geometry") or {}
        if g.get("type") == "Point":
            out.append(tuple(g["coordinates"][:2]))
    return out


def nadji_predahe(samples, u_senci, utci_sr, oprema, step_m):
    """Neprekidni potezi trajne senke — mesta gde se stvarno može stati.

    Uslov je senka u bar PREDAH_MIN_SATI od šest sati prozora, u nizu od bar
    PREDAH_MIN_M. Prag u apsolutnim stepenima ne bi radio: na vruć dan je cela
    trasa iznad granice „bez toplotnog stresa", pa bi spisak bio prazan. Ono
    što se traži nije hladno mesto nego hladnije mesto, i to dovoljno dugo.
    """
    predasi = []
    i = 0
    n = len(samples)
    while i < n:
        if not u_senci[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and u_senci[j + 1] and \
                (samples[j + 1]["km"] - samples[j]["km"]) * 1000.0 <= step_m * 1.5:
            j += 1
        duzina = (j - i + 1) * step_m
        if duzina >= PREDAH_MIN_M:
            sredina = (i + j) // 2
            # oprema se broji ako je blizu BILO KOJE tačke poteza, ne samo
            # sredine — potez od 200 m ima klupu na kraju jednako kao na sredini
            blizu = {}
            for ime, tacke in oprema.items():
                blizu[ime] = sum(
                    1 for lo, la in tacke
                    if min(_rastojanje(lo, la, samples[k]["lon"], samples[k]["lat"])
                           for k in range(i, j + 1)) <= PREDAH_KLUPA_M)
            predasi.append({
                "km": round(samples[sredina]["km"], 2),
                "km_od": round(samples[i]["km"], 2),
                "km_do": round(samples[j]["km"], 2),
                "duzina_m": round(duzina),
                "lat": round(samples[sredina]["lat"], 5),
                "lon": round(samples[sredina]["lon"], 5),
                "deonica": samples[sredina]["deonica"],
                "utci": round(statistics.fmean(utci_sr[i:j + 1]), 1),
                **blizu,
            })
        i = j + 1
    return predasi


def oceni_opremu(oprema, arr, origin, res, meteo, elev, bitovi):
    """UTCI na samim klupama i letnjikovcima, a ne u najbližoj tački staze.

    Senka se računa na koordinati objekta, istim zrakom kao za stazu. Razlika
    je bitna: klupa ume da stoji dvadesetak metara od staze, u sasvim drugim
    uslovima.
    """
    out = {}
    for ime, tacke in oprema.items():
        if not tacke:
            continue
        uzorci = [{"lon": lo, "lat": la} for lo, la in tacke]
        maske, _, _ = compute_masks(uzorci, arr, origin, res)
        svf = izracunaj_svf(uzorci, arr, origin, res)
        m_dat = maske[DATUM]
        sati_senke, utci_sr = [], []
        for i in range(len(uzorci)):
            sunce = [(m_dat[i] >> b) & 1 for b in bitovi]
            sati_senke.append(sum(1 - s for s in sunce))
            v = [utci(meteo[sat]["temperature_2m"],
                      tmrt(sunce[k], float(svf[i]), meteo[sat], elev[sat]),
                      meteo[sat]["vetar_ms"], meteo[sat]["relative_humidity_2m"])
                 for k, sat in enumerate(SATI)]
            v = [x for x in v if x is not None]
            utci_sr.append(statistics.fmean(v) if v else None)
        vazeci = [v for v in utci_sr if v is not None]
        out[ime] = {
            "ukupno": len(tacke),
            "bez_senke": sum(1 for s in sati_senke if s == 0),
            "u_trajnoj_senci": sum(1 for s in sati_senke if s >= PREDAH_MIN_SATI),
            "sati_senke_prosek": round(statistics.fmean(sati_senke), 1),
            "utci": round(statistics.fmean(vazeci), 1) if vazeci else None,
            "utci_min": round(min(vazeci), 1) if vazeci else None,
            "kategorija": kategorija(statistics.fmean(vazeci)) if vazeci else None,
            "napomena": OPREMA_NAPOMENA.get(ime),
        }
    return out


def najduzi_razmak(predasi, osa_km):
    """Najduži potez trase bez ijednog mesta predaha (km)."""
    prev = 0.0
    naj = (0.0, 0.0, 0.0)
    for p in sorted(predasi, key=lambda x: x["km_od"]):
        if p["km_od"] - prev > naj[0]:
            naj = (p["km_od"] - prev, prev, p["km_od"])
        prev = p["km_do"]
    if osa_km - prev > naj[0]:
        naj = (osa_km - prev, prev, osa_km)
    return {"km": round(naj[0], 2), "od": round(naj[1], 2), "do": round(naj[2], 2)}


def _rastojanje(lon1, lat1, lon2, lat2):
    from koridor import planar_xy                     # noqa: PLC0415
    x1, y1 = planar_xy(lon1, lat1)
    x2, y2 = planar_xy(lon2, lat2)
    return math.hypot(x1 - x2, y1 - y2)


# ---------- agregati ----------

def po_kategoriji(vrednosti):
    """Udeo (%) vrednosti po kategorijama toplotnog stresa."""
    imena = [ime for _, ime in KATEGORIJE]
    br = {ime: 0 for ime in imena}
    for v in vrednosti:
        k = kategorija(v)
        if k:
            br[k] += 1
    n = len(vrednosti) or 1
    return {ime: round(100.0 * c / n, 1) for ime, c in br.items() if c}


def main():
    import datetime                                   # noqa: PLC0415

    for f in ("shade_canopy.json",):
        if not os.path.exists(os.path.join(DATA, f)):
            print(f"ERROR: nema data/{f} — prvo `make canopy`.", file=sys.stderr)
            return 1
    with open(os.path.join(DATA, "shade_canopy.json")) as f:
        shade = json.load(f)
    if DATUM not in shade["staze"][0]["masks"]:
        print(f"ERROR: shade_canopy nema datum {DATUM}", file=sys.stderr)
        return 1
    bitovi = [shade["hours"].index(h) for h in SATI]

    axis, by_tip, deon_order = prepare()
    flat = [s for tip, _ in STAZE for s in by_tip[tip]]
    geom = samples_hash(flat)

    lat0 = statistics.fmean(c[1] for c in axis)
    lon0 = statistics.fmean(c[0] for c in axis)
    ove = datetime.date.today().year
    godine = list(range(ove - METEO_GODINE, ove))
    meteo, n_vrucih, n_svih = vruc_dan(preuzmi_meteo(lat0, lon0, godine), godine)
    if len(meteo) < len(SATI):
        print("ERROR: meteorologija nepotpuna", file=sys.stderr)
        return 1
    print(f"Scenario: vruć vedar dan, {n_vrucih} najtoplijih od {n_svih} dana "
          f"({godine[0]}–{godine[-1]})")
    elev = {}
    for sat in SATI:
        e, _ = sun_pos(DOY, sat, TZ)
        elev[sat] = e
        m = meteo[sat]
        print(f"  {sat:2}h  Sunce {e:4.1f}°  vazduh {m['temperature_2m']:4.1f} °C  "
              f"tlo {m.get('soil_temperature_0_to_7cm', float('nan')):4.1f} °C  "
              f"vlaga {m['relative_humidity_2m']:3.0f} %  "
              f"vetar {m['vetar_ms']:3.1f} m/s  "
              f"DNI {m['direct_normal_irradiance']:3.0f}  "
              f"difuzno {m['diffuse_radiation']:3.0f} W/m²")

    arr, origin, res = load_chm(flat, geom)
    oprema = {"klupe": ucitaj_tacke(KLUPE_FILE, "klupe.geojson"),
              "letnjikovci": ucitaj_tacke(LETNJIKOVCI_FILE, "letnjikovci.geojson")}

    maske_po_tipu = {s["tip"]: s["masks"][DATUM] for s in shade["staze"]}
    step_m = shade["step_m"]
    staze_out = []
    svi_predasi = {}

    for tip, label in STAZE:
        samples = by_tip[tip]
        maske = maske_po_tipu[tip]
        svf = izracunaj_svf(samples, arr, origin, res)

        utci_po_satu = []          # [sat][tacka]
        tmrt_po_satu = []
        sunce_po_satu = []
        for sat in SATI:
            m = meteo[sat]
            b = bitovi[SATI.index(sat)]
            sunce = [(maske[i] >> b) & 1 for i in range(len(samples))]
            tm = [tmrt(sunce[i], float(svf[i]), m, elev[sat])
                  for i in range(len(samples))]
            uv = [utci(m["temperature_2m"], tm[i], m["vetar_ms"],
                       m["relative_humidity_2m"]) for i in range(len(samples))]
            utci_po_satu.append(uv)
            tmrt_po_satu.append(tm)
            sunce_po_satu.append(sunce)

        van = sum(1 for red in utci_po_satu for v in red if v is None)
        if van:
            print(f"  ! {van} vrednosti van granica UTCI modela")
        utci_sr = [statistics.fmean([utci_po_satu[h][i] for h in range(len(SATI))
                                     if utci_po_satu[h][i] is not None])
                   for i in range(len(samples))]
        tmrt_sr = [statistics.fmean([tmrt_po_satu[h][i] for h in range(len(SATI))])
                   for i in range(len(samples))]
        sati_u_senci = [sum(1 - sunce_po_satu[h][i] for h in range(len(SATI)))
                        for i in range(len(samples))]
        u_senci = [s >= PREDAH_MIN_SATI for s in sati_u_senci]

        predasi = nadji_predahe(samples, u_senci, utci_sr, oprema, step_m)
        svi_predasi[tip] = predasi

        by_deonica = {}
        for dn in deon_order:
            sel = [i for i, s in enumerate(samples) if s["deonica"] == dn]
            if not sel:
                continue
            v = [utci_sr[i] for i in sel]
            by_deonica[dn] = {
                "n": len(sel),
                "utci": round(statistics.fmean(v), 1),
                "utci_max": round(max(v), 1),
                "tmrt": round(statistics.fmean([tmrt_sr[i] for i in sel]), 1),
                "svf": round(float(np.mean([svf[i] for i in sel])), 2),
                "sati_u_senci": round(statistics.fmean(
                    [sati_u_senci[i] for i in sel]), 1),
                "kategorije": po_kategoriji(v),
                "km_start": round(samples[sel[0]]["km"], 2),
                "km_end": round(samples[sel[-1]]["km"], 2),
            }

        duzina_predaha = sum(p["duzina_m"] for p in predasi)
        totals = {
            "predah_sa_klupom": sum(1 for p in predasi if p["klupe"] > 0),
            "najduzi_bez_predaha": najduzi_razmak(predasi, shade["osa_km"]),
            "n": len(samples),
            "utci": round(statistics.fmean(utci_sr), 1),
            "utci_min": round(min(utci_sr), 1),
            "utci_max": round(max(utci_sr), 1),
            "tmrt": round(statistics.fmean(tmrt_sr), 1),
            "svf": round(float(np.mean(svf)), 2),
            "sati_u_senci": round(statistics.fmean(sati_u_senci), 1),
            "kategorije": po_kategoriji(utci_sr),
            "predaha": len(predasi),
            "predah_m": round(duzina_predaha),
            "pct_predah": round(100.0 * duzina_predaha
                                / (len(samples) * step_m), 1),
        }
        print(f"  {label}: UTCI {totals['utci']} °C "
              f"({totals['utci_min']}–{totals['utci_max']}), Tmrt {totals['tmrt']} °C, "
              f"SVF {totals['svf']}, predaha {totals['predaha']}")

        staze_out.append({
            "tip": tip, "label": label, "n_points": len(samples),
            "points": {
                "km": [round(s["km"], 3) for s in samples],
                "lon": [round(s["lon"], 5) for s in samples],
                "lat": [round(s["lat"], 5) for s in samples],
                "chain": [s["chain"] for s in samples],
                "deonica": [deon_order.index(s["deonica"]) for s in samples],
                "utci": [round(v, 1) for v in utci_sr],
                "tmrt": [round(v, 1) for v in tmrt_sr],
                "svf": [round(float(v), 2) for v in svf],
                "senka_sati": sati_u_senci,
            },
            "po_satu": [{
                "sat": sat,
                "utci": round(statistics.fmean(
                    [v for v in utci_po_satu[k] if v is not None]), 1),
                "tmrt": round(statistics.fmean(tmrt_po_satu[k]), 1),
                "sunce_pct": round(100.0 * sum(sunce_po_satu[k]) / len(samples), 1),
            } for k, sat in enumerate(SATI)],
            "by_deonica": by_deonica,
            "totals": totals,
            "predasi": predasi,
        })

    # Poređenje sunce/senka iz stvarnih tačaka trase, ne iz izmišljenog para:
    # prosek onih koje su na suncu sve sate prema onima koje su u senci skoro
    # sve. Tako broj opisuje ovaj koridor, a ne opšti slučaj.
    uporedba = None
    sve_sunce, sve_senka = [], []
    for s in staze_out:
        p = s["points"]
        for i, sati in enumerate(p["senka_sati"]):
            if sati == 0:
                sve_sunce.append((p["utci"][i], p["tmrt"][i]))
            elif sati >= PREDAH_MIN_SATI:
                sve_senka.append((p["utci"][i], p["tmrt"][i]))
    if sve_sunce and sve_senka:
        def sredi(par):
            u = statistics.fmean(x for x, _ in par)
            t = statistics.fmean(y for _, y in par)
            return {"utci": round(u, 1), "tmrt": round(t, 1),
                    "kategorija": kategorija(u), "n": len(par)}
        uporedba = {"sunce": sredi(sve_sunce), "senka": sredi(sve_senka)}
        uporedba["utci_razlika"] = round(
            uporedba["sunce"]["utci"] - uporedba["senka"]["utci"], 1)
        uporedba["tmrt_razlika"] = round(
            uporedba["sunce"]["tmrt"] - uporedba["senka"]["tmrt"], 1)
        print(f"  sunce {uporedba['sunce']['utci']} °C protiv senke "
              f"{uporedba['senka']['utci']} °C  (Tmrt razlika "
              f"{uporedba['tmrt_razlika']} °C)")

    oprema_ocena = oceni_opremu(oprema, arr, origin, res, meteo, elev, bitovi)
    for ime, v in oprema_ocena.items():
        print(f"  {ime}: {v['ukupno']} ukupno, {v['bez_senke']} bez ijednog sata "
              f"senke od krošnji, UTCI {v['utci']} °C ({v['kategorija']})"
              + (f"  [{v['napomena']}]" if v["napomena"] else ""))

    out = {
        "schema": TERMALNI_SCHEMA,
        "samples_hash": geom,
        "source": ("Meta/WRI Global Canopy Height (CC BY 4.0) · "
                   "ERA5 preko Open-Meteo (CC BY 4.0) · UTCI"),
        "step_m": step_m,
        "osa_km": shade["osa_km"],
        "datum": DATUM,
        "sati": SATI,
        "scenario": {
            "opis": "vruć vedar letnji dan",
            "godine": [godine[0], godine[-1]],
            "dana_u_uzorku": n_vrucih,
            "dana_ukupno": n_svih,
            "prozor_dana": METEO_PROZOR_DANA,
            "po_satu": [{
                "sat": sat,
                "sunce_elev": round(elev[sat], 1),
                "vazduh": round(meteo[sat]["temperature_2m"], 1),
                "tlo": round(meteo[sat].get("soil_temperature_0_to_7cm", 0), 1),
                "vlaga": round(meteo[sat]["relative_humidity_2m"]),
                "vetar_ms": round(meteo[sat]["vetar_ms"], 1),
                "dni": round(meteo[sat]["direct_normal_irradiance"]),
                "difuzno": round(meteo[sat]["diffuse_radiation"]),
                "oblaci": round(meteo[sat]["cloud_cover"]),
            } for sat in SATI],
        },
        "kategorije": [{"do": g if g != float("inf") else None, "naziv": n}
                       for g, n in KATEGORIJE],
        "predah": {"min_m": PREDAH_MIN_M, "min_sati": PREDAH_MIN_SATI,
                   "klupa_m": PREDAH_KLUPA_M},
        "oprema": oprema_ocena,
        "uporedba": uporedba,
        "model": {"svf_smerova": SVF_SMEROVA, "svf_max_m": SVF_MAX_M,
                  "albedo_tla": ALBEDO_TLA, "covek_h": COVEK_H,
                  "covek_d": COVEK_D},
        "deonice": deon_order,
        "staze": staze_out,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  -> {os.path.relpath(OUT_FILE, ROOT)} "
          f"({os.path.getsize(OUT_FILE) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
