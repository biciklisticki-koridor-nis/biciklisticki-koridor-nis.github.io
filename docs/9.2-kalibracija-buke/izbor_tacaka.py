#!/usr/bin/env python3
"""Izbor mernih tačaka za kalibraciju modela buke (analiza 9.2).

Model iz buka.py daje relativan indeks 0–100. Da bi se preveo u dB(A)
treba regresija sa dva slobodna parametra:

    dB(A) = a + b · 10·log10(E_model)

Dva parametra znače da je bitan RASPON prediktora, a ne količina merenja.
Zato se tačke biraju raslojeno po indeksu, a ne ravnomerno po kilometraži:
nekoliko iz svakog pojasa, sa naglaskom na krajevima skale koji nose najviše
informacije za nagib.

Uz to se biraju uparene tačke gornji/donji bedem na istoj kilometraži.
Njihova izmerena razlika daje zaklon nasipa — član koji model nema, jer
SRTM na 30 m stavlja 88 % parova te dve staze u istu ćeliju. Parovi se
biraju u bučnim zonama: u tišini šum Nišave nadjača razliku.

Skript piše četiri stvari:
    tacke.gpx     — za aplikaciju za mape na telefonu
    tacke.csv     — za upis i kasniju obradu
    obrazac.html  — za štampu; iz njega `make teren-pdf` pravi obrazac.pdf
    data/merne_tacke.json — da se tačke vide na mapi u analizi 9.2

Pokretanje iz korena repo-a:
    .venv/bin/python docs/9.2-kalibracija-buke/izbor_tacaka.py
"""
import html
import io
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "data", "buka.json")
WEB = os.path.join(ROOT, "data", "merne_tacke.json")

# Odakle se fajlovi preuzimaju kad se skenira QR kod sa odštampanog obrasca.
SITE = "https://biciklisticki-koridor-nis.github.io"
DOCS_URL = f"{SITE}/docs/9.2-kalibracija-buke/"

# Aplikacije na trećoj strani obrasca. Identifikatori paketa su provereni na
# Play Store-u — pogrešan QR u odštampanom dokumentu je gori nego nijedan.
PLAY = "https://play.google.com/store/apps/details?id="
APLIKACIJE = [
    ("NoiseCapture", "org.noise_planet.noisecapture",
     "merenje zvuka", "obavezno", True),
    ("OsmAnd", "net.osmand", "mapa sa tačkama", "preporučeno", False),
    ("Organic Maps", "app.organicmaps", "mapa sa tačkama", "jednostavnija", False),
]

N_PAIRS = 4              # uparenih lokacija gornji/donji bedem
MIN_SEP_M = 350.0        # nespojene tačke moraju biti nezavisne
PAIR_MIN_IDX = 40        # ispod ovoga nema signala za razliku staza
PAIR_SEP_M = (8, 60)     # stvarno dve staze, ne isto mesto
# pojas indeksa -> koliko tačaka; krajevi skale nose najviše za nagib
BINS = [((0, 12), 2), ((12, 25), 1), ((25, 38), 2), ((38, 50), 1),
        ((50, 62), 1), ((62, 75), 1), ((75, 101), 2)]

TIPN = {"bici": "Biciklistička", "pesacki_gornji": "Gornji bedem",
        "pesacki_donji": "Donji bedem"}


def haversine(a, b):
    r = 6371000.0
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = p2 - p1
    dl = math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def load():
    with open(SRC) as f:
        d = json.load(f)
    deon = d["deonice"]
    out = {}
    for s in d["staze"]:
        p = s["points"]
        out[s["tip"]] = [
            {"tip": s["tip"], "km": p["km"][i], "lat": p["lat"][i],
             "lon": p["lon"][i], "idx": p["idx"][i], "near": p["near_m"][i],
             "deon": deon[p["deonica"][i]]}
            for i in range(len(p["km"]))
        ]
    return out


def pick(by_tip):
    chosen = []

    def far_enough(c, others):
        return all(haversine(c, o) >= MIN_SEP_M for o in others)

    # 1) uparene tačke gornji/donji bedem
    pairs = []
    for g in by_tip["pesacki_gornji"]:
        if g["idx"] < PAIR_MIN_IDX:
            continue
        d = min(by_tip["pesacki_donji"], key=lambda x: abs(x["km"] - g["km"]))
        if abs(d["km"] - g["km"]) > 0.02:
            continue
        sep = haversine(g, d)
        if PAIR_SEP_M[0] <= sep <= PAIR_SEP_M[1]:
            pairs.append((g, d, sep))
    pairs.sort(key=lambda t: -t[0]["idx"])

    taken = []
    for g, d, sep in pairs:
        if len(taken) >= N_PAIRS:
            break
        if far_enough(g, [x for p in taken for x in p[:2]]):
            taken.append((g, d, sep))
    for i, (g, d, sep) in enumerate(taken, 1):
        g["rola"], d["rola"] = f"par {i} — gornji", f"par {i} — donji"
        g["par"] = d["par"] = i
        g["sep"] = d["sep"] = round(sep)
        chosen += [g, d]

    # 2) raslojeno po indeksu duž referentne ose
    for (lo, hi), quota in BINS:
        cand = [c for c in by_tip["bici"] if lo <= c["idx"] < hi]
        got = 0
        while got < quota and cand:
            cand.sort(key=lambda c: -min((haversine(c, o) for o in chosen),
                                         default=1e9))
            nxt = next((c for c in cand if far_enough(c, chosen)), None)
            if nxt is None:
                break
            nxt["rola"] = f"osa · pojas {lo}–{hi - 1}"
            chosen.append(nxt)
            cand.remove(nxt)
            got += 1

    chosen.sort(key=lambda c: c["km"])
    for i, c in enumerate(chosen, 1):
        c["id"] = f"T{i:02d}"
    return chosen


def describe(c):
    s = [f"Model indeks {c['idx']} ({c['rola']})",
         f"km {c['km']:.2f} · {c['deon']} · {TIPN[c['tip']]}",
         "Najbliži glavni put: "
         + (f"{c['near']} m" if c["near"] is not None else "nema u 300 m")]
    if "sep" in c:
        s.append(f"UPARENA — druga staza na {c['sep']} m. "
                 "Meriti obe u razmaku od par minuta.")
    s.append("LAeq, A-ponderisano, Fast, 3–5 min, mikrofon na 1,5 m.")
    return " | ".join(s)


def write_gpx(pts, path):
    wpts = "\n".join(
        f'  <wpt lat="{c["lat"]:.6f}" lon="{c["lon"]:.6f}">\n'
        f'    <name>{c["id"]} · idx {c["idx"]}</name>\n'
        f'    <desc>{html.escape(describe(c))}</desc>\n'
        f'    <sym>Flag</sym>\n  </wpt>' for c in pts)
    rte = "\n".join(
        f'    <rtept lat="{c["lat"]:.6f}" lon="{c["lon"]:.6f}">'
        f'<name>{c["id"]}</name></rtept>' for c in pts)
    pairs = ", ".join(f'{a["id"]}–{b["id"]}' for a, b in
                      zip(pts, pts[1:]) if a.get("par") and a["par"] == b.get("par"))
    with open(path, "w", encoding="utf-8") as f:
        f.write(f'''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="biciklisticki-koridor / izbor_tacaka.py"
     xmlns="http://www.topografix.com/GPX/1/1"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
  <metadata>
    <name>Kalibracija modela buke — Nišavski koridor</name>
    <desc>{len(pts)} mernih tačaka, raslojenih po modeliranom indeksu izlozenosti.
Cilj: regresija dB(A) = a + b * 10*log10(E) i provera rangiranja deonica.
Uparene tacke ({pairs}) su gornji/donji bedem na istoj kilometrazi — njihova
razlika meri zaklon nasipa, koji model nema.
Jedan prolaz, isti vremenski prozor, radnim danom.</desc>
  </metadata>
{wpts}
  <rte>
    <name>Redosled obilaska {pts[0]["id"]}–{pts[-1]["id"]}</name>
{rte}
  </rte>
</gpx>
''')


def write_csv(pts, path):
    # Podloga i klupe se upisuju na istom izlasku, iako pripadaju analizi 9.3:
    # tip podloge nam nedostaje za termalni komfor (OSM ga za staze uz Nišavu
    # skoro ne beleži), a klupe su osnov za „mesta predaha". Drugi obilazak
    # trase samo zbog toga bio bi traćenje jednog istog puta od 13 km.
    head = ("id;km;staza;deonica;lat;lon;model_indeks;najblizi_glavni_put_m;"
            "uloga;izmereno_LAeq_dBA;izmereno_LA90_dBA;vreme;podloga;klupe;"
            "napomena")
    rows = [head]
    for c in pts:
        rows.append(
            f"{c['id']};{c['km']:.2f};{TIPN[c['tip']]};{c['deon']};"
            f"{c['lat']:.6f};{c['lon']:.6f};{c['idx']};"
            f"{c['near'] if c['near'] is not None else ''};{c['rola']};;;;;;")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")


def qr_svg(data, mm=26):
    """QR kod kao inline SVG — bez slike, da PDF ostane jedan fajl."""
    import qrcode                                    # noqa: PLC0415
    import qrcode.image.svg                          # noqa: PLC0415

    q = qrcode.QRCode(box_size=10, border=2,
                      error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(data)
    q.make(fit=True)
    buf = io.BytesIO()
    q.make_image(image_factory=qrcode.image.svg.SvgPathImage).save(buf)
    svg = buf.getvalue().decode("utf-8")
    svg = svg.split("?>", 1)[-1].strip()
    # generator upisuje svoju veličinu u mm; menjamo je našom
    return svg.replace('width="', f'width="{mm}mm" data-w="', 1) \
              .replace('height="', f'height="{mm}mm" data-h="', 1)


def write_form(pts, path):
    """Obrazac za štampu: tabela sa koordinatama i praznim kolonama za upis."""
    def red(c):
        par = f'<span class="par">par {c["par"]}</span>' if c.get("par") else ""
        return f"""      <tr>
        <td class="id">{c['id']}{par}</td>
        <td class="km">{c['km']:.2f}</td>
        <td class="mesto">{html.escape(c['deon'])}<span class="staza">{TIPN[c['tip']]}</span></td>
        <td class="koord">{c['lat']:.5f}<br>{c['lon']:.5f}</td>
        <td class="idx">{c['idx']}</td>
        <td class="upis"></td>
        <td class="upis"></td>
        <td class="upis uzak"></td>
        <td class="upis"></td>
        <td class="upis uzak"></td>
        <td class="upis siroko"></td>
      </tr>"""

    parovi = sorted({c["par"] for c in pts if c.get("par")})
    redovi = "\n".join(red(c) for c in pts)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"""<!DOCTYPE html>
<html lang="sr">
<head>
<meta charset="UTF-8">
<title>Terenski obrazac — kalibracija modela buke</title>
<style>
  @page {{ size: A4 landscape; margin: 9mm 10mm; }}
  * {{ box-sizing: border-box; }}
  body {{
    font: 9pt/1.32 "DejaVu Sans", "Liberation Sans", Arial, sans-serif;
    color: #111; margin: 0;
  }}
  .list {{ break-after: page; }}
  .list:last-child {{ break-after: auto; }}

  header {{ display: flex; gap: 5mm; align-items: flex-start; margin-bottom: 2.5mm; }}
  h1 {{ font-size: 13pt; margin: 0 0 1mm; }}
  .pod {{ font-size: 8pt; color: #444; margin: 0; }}
  .naslov {{ flex: 1 1 auto; }}
  .polja {{ flex: 0 0 96mm; display: grid; grid-template-columns: 1fr 1fr; gap: 1.6mm 4mm; }}
  .polje {{ font-size: 7.5pt; color: #444; }}
  .polje span {{ display: block; border-bottom: .4pt solid #111; height: 5.2mm; }}
  .qr {{ flex: 0 0 auto; display: flex; gap: 4mm; text-align: center; }}
  .qr figcaption {{ font-size: 6.5pt; color: #444; margin-top: .6mm; line-height: 1.2; }}
  .qr svg {{ display: block; }}

  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ border: .4pt solid #999; padding: .5mm 1.2mm; vertical-align: middle; }}
  thead th {{
    background: #eee; font-size: 7pt; text-transform: uppercase;
    letter-spacing: .02em; text-align: left;
  }}
  thead th.num {{ text-align: center; }}
  tbody tr {{ height: 7.6mm; }}
  tbody tr:nth-child(even) td {{ background: #fafafa; }}
  td.id {{ font-weight: 700; font-size: 9.5pt; white-space: nowrap; }}
  td.km, td.idx {{ text-align: center; font-variant-numeric: tabular-nums; }}
  td.koord {{ font-size: 6.6pt; line-height: 1.15; font-variant-numeric: tabular-nums; white-space: nowrap; }}
  td.mesto {{ font-size: 7.6pt; line-height: 1.2; }}
  .staza {{ display: block; font-size: 6.4pt; color: #555; }}
  .par {{
    display: inline-block; margin-left: 1mm; padding: 0 1mm;
    border: .4pt solid #111; border-radius: 1mm; font-size: 6.5pt; font-weight: 600;
  }}
  td.upis {{ background: #fff !important; }}
  col.c-id {{ width: 15mm; }} col.c-km {{ width: 10mm; }} col.c-mesto {{ width: 30mm; }}
  col.c-koord {{ width: 20mm; }} col.c-idx {{ width: 11mm; }}
  col.c-laeq, col.c-la90 {{ width: 20mm; }} col.c-vreme {{ width: 14mm; }}
  col.c-podloga {{ width: 24mm; }} col.c-klupe {{ width: 14mm; }}

  .uput {{ columns: 2; column-gap: 8mm; font-size: 8.5pt; }}
  .uput h2 {{ font-size: 10pt; margin: 0 0 1.5mm; break-after: avoid; }}
  .uput h3 {{ font-size: 8.5pt; margin: 3mm 0 1mm; break-after: avoid; }}
  .uput ol, .uput ul {{ margin: 0 0 2mm; padding-left: 4.5mm; }}
  .uput li {{ margin-bottom: 1mm; }}
  .uput p {{ margin: 0 0 2mm; }}
  .okvir {{ border: .6pt solid #111; padding: 2mm 2.5mm; margin-bottom: 3mm; break-inside: avoid; }}
  .okvir strong {{ display: block; margin-bottom: 1mm; }}

  .belezke-naslov {{ font-size: 10pt; margin: 5mm 0 2mm; }}
  .belezke span {{ display: block; border-bottom: .4pt solid #999; height: 8mm; }}

  /* treća strana: aplikacije i QR kodovi */
  .app-red {{ display: flex; gap: 6mm; margin: 4mm 0 5mm; }}
  .app {{
    flex: 0 0 auto; margin: 0; text-align: center;
    border: .5pt solid #111; border-radius: 1.5mm; padding: 2.5mm 3mm 2mm;
  }}
  .app-fajl {{ border-width: 1.2pt; }}
  .app svg {{ display: block; margin: 0 auto; }}
  .app figcaption {{ margin-top: 1.2mm; line-height: 1.25; }}
  .app figcaption strong {{ display: block; font-size: 9pt; }}
  .app figcaption span {{ display: block; font-size: 7pt; color: #444; }}
  .app-oznaka {{
    margin-top: .8mm; font-weight: 600; text-transform: uppercase;
    letter-spacing: .03em; font-size: 6.5pt !important;
  }}
  .app-must {{ color: #111 !important; }}
  .upozorenje {{ border-left: 1.2pt solid #111; padding-left: 2.5mm; }}
  /* Eksplicitne kolone, ne tekuće: sa `columns: 2` upozorenje uz NoiseCapture
     iscuri na vrh desne kolone i pročita se kao deo uputstva za mapu. */
  .uput-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0 8mm; font-size: 8.5pt; }}
  .uput-grid h2 {{ font-size: 10pt; margin: 0 0 1.5mm; }}
  .uput-grid h2 + p {{ margin-top: 0; }}
  .uput-grid p {{ margin: 0 0 2mm; }}
  .uput-grid ol {{ margin: 0 0 2mm; padding-left: 4.5mm; }}
  .uput-grid li {{ margin-bottom: 1.2mm; }}

  .lista-naslov {{ font-size: 10pt; margin: 6mm 0 2mm; }}
  .kontrolna {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.8mm 8mm; font-size: 8.5pt; }}
  .kontrolna span {{ display: flex; align-items: center; gap: 2mm; }}
  .kontrolna span::before {{
    content: ""; flex: 0 0 auto; width: 4.2mm; height: 4.2mm;
    border: .6pt solid #111; border-radius: .8mm;
  }}
</style>
</head>
<body>

<section class="list">
  <header>
    <div class="naslov">
      <h1>Kalibracija modela buke · Nišavski koridor</h1>
      <p class="pod">{len(pts)} tačaka, jedan prolaz. Na svakoj <strong>LAeq i LA90</strong>,
      A-ponderisano, Fast, <strong>3–5 min</strong>, mikrofon na 1,5 m.
      Parovi ({', '.join(str(p) for p in parovi)}) su gornji i donji bedem na istoj
      kilometraži — meriti obe u razmaku od par minuta. Uputstvo je na poleđini.</p>
    </div>
    <div class="polja">
      <label class="polje">Datum<span></span></label>
      <label class="polje">Merilac<span></span></label>
      <label class="polje">Telefon i aplikacija<span></span></label>
      <label class="polje">Vreme (vetar, kiša)<span></span></label>
    </div>
    <div class="qr">
      <figure>{qr_svg(DOCS_URL + "tacke.gpx")}<figcaption>GPX<br>za mape</figcaption></figure>
      <figure>{qr_svg(DOCS_URL + "tacke.csv")}<figcaption>CSV<br>za unos</figcaption></figure>
    </div>
  </header>

  <table>
    <colgroup>
      <col class="c-id"><col class="c-km"><col class="c-mesto"><col class="c-koord">
      <col class="c-idx"><col class="c-laeq"><col class="c-la90"><col class="c-vreme">
      <col class="c-podloga"><col class="c-klupe"><col>
    </colgroup>
    <thead>
      <tr>
        <th>Tačka</th><th class="num">km</th><th>Deonica i staza</th>
        <th>Koordinate</th><th class="num">model</th>
        <th>LAeq dB(A)</th><th>LA90 dB(A)</th><th>vreme</th>
        <th>podloga</th><th>klupe</th><th>napomena</th>
      </tr>
    </thead>
    <tbody>
{redovi}
    </tbody>
  </table>
</section>

<section class="list">
  <h1>Kako se meri</h1>
  <div class="uput">
    <div class="okvir">
      <strong>Jedan telefon, jedna aplikacija, ceo prolaz.</strong>
      Aplikacije mere razliku pouzdano, ali svaki mikrofon nosi svoj stalni pomeraj.
      Taj pomeraj se u obradi sam poništi — ali samo ako je isti na svim tačkama.
      Menjanje telefona usred obilaska pokvarilo bi ceo izlazak.
    </div>

    <h2>Na svakoj tački</h2>
    <ol>
      <li>Nađi tačku po GPX-u. Odstupanje do desetak metara nije problem; veće upiši u napomenu.</li>
      <li>Stani bar 1 m od zida, ograde i parkiranih vozila. Mikrofon na oko 1,5 m, usmeren naviše.</li>
      <li>Pokreni merenje i sačekaj <strong>3 do 5 minuta</strong>. Ne pričaj i ne pomeraj telefon.</li>
      <li>Upiši <strong>LAeq</strong> (prosek) i <strong>LA90</strong> (pozadina, tiših 90 % vremena) i tačno vreme.</li>
      <li>Ako naiđe sirena, pas ili kosilica — zabeleži u napomenu. Takvo merenje se u obradi izbacuje.</li>
    </ol>

    <h3>Uparene tačke</h3>
    <p>Kod parova izmeri gornji pa odmah donji bedem, u razmaku od par minuta i pod
    istim saobraćajem. Njihova razlika je jedino merenje zaklona nasipa koje imamo —
    visinski podaci su pregrubi da ga izračunaju.</p>

    <h3>Podloga i klupe</h3>
    <p>Dve kolone koje ne služe buci nego analizi 9.3. Podloga: <em>asfalt, beton,
    behaton, tucanik, zemlja, trava</em>. Klupe: koliko ih ima na dvadesetak metara
    oko tačke, i ima li hlada nad njima (npr. <em>2, u hladu</em>).</p>

    <h2>Čemu ovo služi</h2>
    <p>Model iz analize 9.2 daje indeks 0–100, ne decibele. Sa ovih {len(pts)} merenja
    radi se regresija sa dva slobodna parametra, pa indeks dobija skalu u dB(A).
    Zato je važan <strong>raspon</strong>, ne broj tačaka: tačke su birane tako da
    pokriju i najtiše i najbučnije delove trase.</p>

    <h3>Šta se ne meri</h3>
    <ul>
      <li>Ne meri se po kiši ni na vetru jačem od slabog — oboje ulaze u mikrofon.</li>
      <li>Ne meri se vikendom: model je građen na uobičajenom saobraćaju.</li>
      <li>Ne treba obilaziti trasu više puta. Ceo niz staje u jedan prolaz od oko 13 km.</li>
    </ul>

    <div class="okvir">
      <strong>Posle izlaska</strong>
      Upiši brojeve u <em>tacke.csv</em> (QR kod na prvoj strani) i vrati ga u repozitorijum.
      Obrada i regresija idu odatle.
    </div>
  </div>

  <h2 class="belezke-naslov">Opšte beleške sa izlaska</h2>
  <div class="belezke">{"".join('<span></span>' for _ in range(9))}</div>
</section>

<section class="list">
  <h1>Pre izlaska: šta instalirati</h1>
  <p class="pod">Skeniraj kodove telefonom. Sve je besplatno i bez naloga.
  Uradi ovo kod kuće, na Wi-Fi mreži — ne na trasi.</p>

  <div class="app-red">
    {"".join(f"""
    <figure class="app">
      {qr_svg(PLAY + pkg, 25)}
      <figcaption><strong>{ime}</strong><span>{sta}</span>
        <span class="app-oznaka{' app-must' if must else ''}">{oznaka}</span></figcaption>
    </figure>""" for ime, pkg, sta, oznaka, must in APLIKACIJE)}
    <figure class="app app-fajl">
      {qr_svg(DOCS_URL + "tacke.gpx", 25)}
      <figcaption><strong>tacke.gpx</strong><span>{len(pts)} tačaka za mapu</span>
        <span class="app-oznaka app-must">preuzmi</span></figcaption>
    </figure>
  </div>

  <div class="uput-grid">
   <div>
    <h2>Zvuk — NoiseCapture</h2>
    <p>Otvoren kod, iza njega stoje Université Gustave Eiffel i CNRS, pravljen
    baš za građansko mapiranje buke. Daje <strong>LA90 i LA50 percentile</strong>
    i sam GPS-taguje merenja. Ima ga i na F-Droid-u.</p>
    <div class="okvir">
      <strong>Jedan telefon i jedna aplikacija za ceo prolaz.</strong>
      Svaki mikrofon nosi svoj stalni pomeraj. U obradi se sam poništi — ali
      samo ako je isti na svim tačkama.
    </div>
    <p><strong>Trik koji štedi posao:</strong> pusti NoiseCapture da snima
    neprekidno kroz ceo obilazak. Zaustavljanja ispadaju kao čiste zaravni u
    GPS tragu i iz njih se vade vrednosti. Vožnja između tačaka je zagađena
    šumom vetra i baca se, ali ništa ne košta.</p>
    <p class="upozorenje">Ne koristi generičke „Sound Meter" aplikacije.
    Skoro nijedna ne traži neobrađen audio izvor, pa im automatska kontrola
    pojačanja izravna tačno ono što merimo. Daju uverljive brojeve bez značenja.</p>
   </div>
   <div>
    <h2>Mapa — kako ubaciti GPX</h2>
    <ol>
      <li>Skeniraj kod <strong>tacke.gpx</strong>. Fajl se preuzme u Downloads.</li>
      <li>Otvori preuzeti fajl i izaberi <strong>OsmAnd</strong> ili
        <strong>Organic Maps</strong> kao aplikaciju. U OsmAnd-u radi i
        <em>Meni → Podešavanja → Uvoz/izvoz → Uvoz</em>.</li>
      <li><strong>Proveri da se vidi svih {len(pts)} tačaka</strong>, od
        {pts[0]["id"]} do {pts[-1]["id"]}. Organic Maps ume da preskoči prvu i
        poslednju — ako fali, dodaj ih ručno po koordinatama sa prve strane.</li>
      <li>Skini <strong>offline mapu Srbije</strong> dok si na Wi-Fi mreži.</li>
    </ol>
    <p>OsmAnd je preporučen zato što prikazuje <strong>opis</strong> svake
    tačke, a u opisu stoji ceo protokol za tu tačku — model indeks, kilometraža,
    deonica i način merenja. Uz njega papir služi samo za upis, ne i za
    podsećanje šta se radi. Organic Maps je jednostavniji i lakši, ali pokazuje
    samo pin.</p>
   </div>
  </div>

  <h2 class="lista-naslov">Kontrolna lista pre polaska</h2>
  <div class="kontrolna">
    <span>telefon pun, punjač u torbi</span>
    <span>NoiseCapture instaliran i probano snimanje</span>
    <span>tacke.gpx učitan, vidi se svih {len(pts)} tačaka</span>
    <span>offline mapa Srbije skinuta</span>
    <span>pena na mikrofonu (protiv vetra)</span>
    <span>ovaj obrazac odštampan, olovka</span>
    <span>radni dan, bez kiše i jakog vetra</span>
    <span>2–3 sata slobodno, 13 km trase</span>
    <span>voda — merenje je leti, po suncu</span>
  </div>
</section>

</body>
</html>
""")


def write_web_json(pts, path):
    """Tačke za mapu u analizi 9.2 — samo ono što mapa prikazuje."""
    out = {
        "opis": "Planirane tačke merenja buke za kalibraciju modela (analiza 9.2)",
        "gpx": DOCS_URL + "tacke.gpx",
        "tacke": [{
            "id": c["id"], "km": round(c["km"], 2),
            "lat": round(c["lat"], 6), "lon": round(c["lon"], 6),
            "idx": c["idx"], "staza": c["tip"], "deonica": c["deon"],
            "uloga": c["rola"], "par": c.get("par"),
        } for c in pts],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))


def main():
    pts = pick(load())
    write_gpx(pts, os.path.join(HERE, "tacke.gpx"))
    write_csv(pts, os.path.join(HERE, "tacke.csv"))
    write_form(pts, os.path.join(HERE, "obrazac.html"))
    write_web_json(pts, WEB)

    route = sum(haversine(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    sep = min(haversine(a, b) for i, a in enumerate(pts) for b in pts[i + 1:])
    print(f"{len(pts)} tačaka | indeks {min(c['idx'] for c in pts)}–"
          f"{max(c['idx'] for c in pts)} | km {pts[0]['km']:.2f}–{pts[-1]['km']:.2f}")
    print(f"obilazak redom: {route / 1000:.1f} km | najmanje rastojanje: {sep:.0f} m")
    print("-> tacke.gpx, tacke.csv, obrazac.html, data/merne_tacke.json")
    print("   PDF za štampu: make teren-pdf")
    for c in pts:
        print(f"  {c['id']}  km {c['km']:6.2f}  {TIPN[c['tip']]:14} "
              f"{c['deon']:14} idx {c['idx']:3}  {c['rola']}")


if __name__ == "__main__":
    main()
