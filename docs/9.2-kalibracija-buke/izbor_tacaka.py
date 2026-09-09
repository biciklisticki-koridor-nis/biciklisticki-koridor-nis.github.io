#!/usr/bin/env python3
"""Izbor mernih tačaka za kalibraciju modela buke (analiza 9.2).

Model iz noise_air.py daje relativan indeks 0–100. Da bi se preveo u dB(A)
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

Pokretanje iz korena repo-a:
    .venv/bin/python docs/9.2-kalibracija-buke/izbor_tacaka.py
"""
import html
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "data", "noise_air.json")

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
    head = ("id;km;staza;deonica;lat;lon;model_indeks;najblizi_glavni_put_m;"
            "uloga;izmereno_LAeq_dBA;izmereno_LA90_dBA;vreme;napomena")
    rows = [head]
    for c in pts:
        rows.append(
            f"{c['id']};{c['km']:.2f};{TIPN[c['tip']]};{c['deon']};"
            f"{c['lat']:.6f};{c['lon']:.6f};{c['idx']};"
            f"{c['near'] if c['near'] is not None else ''};{c['rola']};;;;")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")


def main():
    pts = pick(load())
    write_gpx(pts, os.path.join(HERE, "tacke.gpx"))
    write_csv(pts, os.path.join(HERE, "tacke.csv"))

    route = sum(haversine(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    sep = min(haversine(a, b) for i, a in enumerate(pts) for b in pts[i + 1:])
    print(f"{len(pts)} tačaka | indeks {min(c['idx'] for c in pts)}–"
          f"{max(c['idx'] for c in pts)} | km {pts[0]['km']:.2f}–{pts[-1]['km']:.2f}")
    print(f"obilazak redom: {route / 1000:.1f} km | najmanje rastojanje: {sep:.0f} m")
    print("-> tacke.gpx, tacke.csv")
    for c in pts:
        print(f"  {c['id']}  km {c['km']:6.2f}  {TIPN[c['tip']]:14} "
              f"{c['deon']:14} idx {c['idx']:3}  {c['rola']}")


if __name__ == "__main__":
    main()
