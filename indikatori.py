#!/usr/bin/env python3
"""Pokazatelji sekcije 9 — jedna mala tabela iz rezultata tri analize.

Stranica sa spiskom analiza ne treba da učitava stotine kilobajta po tački
da bi prikazala petnaest brojeva. Ovaj skript ih izvodi jednom, pri build-u,
iz već izračunatih izlaza:

  shade_canopy.json  -> pokrivenost krošnjama, kontinuitet senke, sunce
  noise_air.json     -> izloženost buci
  river_views.json   -> pogled na reku

i piše data/indikatori.json (~2 KB). Termalni komfor je analiza 9.3 i za
sada nema vrednost. Zagađenje vazduha po mestu (hotspot) je namerno izostavljeno:
CAMS ćelija od 11 km ne razlučuje prostor duž koridora.
"""
import json
import os
import sys

from koridor import ROOT, STAZE
from shade_canopy import TREE_MIN_H

DATA = os.path.join(ROOT, "data")
OUT_FILE = os.path.join(DATA, "indikatori.json")

# Sunce i kontinuitet senke gledaju isti trenutak: kada je vrućina, ne prosek
# dana. Oba reda tabele su tako direktno uporediva — kontinuitet senke ne može
# biti veći od udela staze koji je uopšte u senci.
SUN_DATE = "jun21"
SUN_HOURS = [12, 13, 14, 15, 16]

# Kontinuitet senke: udeo dužine u neprekidnim nizovima STVARNE senke (tačka u
# senci u većini sati iz SUN_HOURS) od bar CONT_MIN_M.
#
# Prva verzija je brojala nizove drvoreda (krošnja ≥ 3 m u prozoru ±9,5 m) i
# za donji bedem davala 45 %, dok je u senci bilo svega 19 % staze: leti u
# podne sunce je na ~69°, stablo od 10 m baca senku od 3,8 m, pa drvored pored
# staze ne zaseni stazu. Drvored je red „krošnje", ne senka.
#
# Senka se računa u samoj tački, bez prozora, pa jedna krošnja iznad staze
# daje niz od 10–20 m. Raspodela dužina nizova ima prelom između 20 i 30 m;
# ispod 30 m mera broji pojedinačne krošnje.
CONT_MIN_M = 30.0
CONT_MAJORITY = 3         # od 5 sati; 1 ili 5 daju skoro isto — tačka je
                          # u senci ili ceo vrh vrućine, ili uopšte ne

NOISE_MIN_IDX = 50        # „izloženo" i „vrlo izloženo" na stranici 9.2


def continuity_pct(staza, hours, step_m):
    """% dužine u nizovima stvarne senke >= CONT_MIN_M.

    Isto pravilo prekida kao continuity() u shade_canopy.py: rupa u samoj
    stazi prekida niz, da se odsustvo staze ne računa kao odsustvo senke.
    """
    km = staza["points"]["km"]
    masks = staza["masks"][SUN_DATE]
    bits = [hours.index(h) for h in SUN_HOURS]
    total = 0.0
    run = 0.0
    prev = None
    for i in range(len(km)):
        # bit = 1 znači sunce u tom satu
        shade = sum(1 - ((masks[i] >> b) & 1) for b in bits) >= CONT_MAJORITY
        broken = i > 0 and (km[i] - km[i - 1]) * 1000.0 > step_m * 1.5
        if i == 0 or broken or shade != prev:
            if prev and run >= CONT_MIN_M:
                total += run
            run = 0.0
        if shade:
            run += step_m
        prev = shade
    if prev and run >= CONT_MIN_M:
        total += run
    return round(100.0 * total / (len(km) * step_m), 1)


def sun_pct(staza, hours):
    """% dužine na direktnom suncu, uprosečeno kroz zadate sate."""
    idx = [hours.index(h) for h in SUN_HOURS]
    masks = staza["masks"][SUN_DATE]
    lit = sum((m >> b) & 1 for m in masks for b in idx)
    return round(100.0 * lit / (len(masks) * len(idx)), 1)


def load(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        print(f"ERROR: nema {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def main():
    shade = load("shade_canopy.json")
    noise = load("noise_air.json")
    views = load("river_views.json")
    by = {name: {s["tip"]: s for s in d["staze"]}
          for name, d in (("shade", shade), ("noise", noise), ("views", views))}

    def row(key, izvor, bolje, fn):
        return {"key": key, "izvor": izvor, "bolje": bolje,
                "vrednosti": {tip: fn(tip) for tip, _ in STAZE}}

    rows = [
        row("kontinuitet_senke", "9.1", "vece",
            lambda t: continuity_pct(by["shade"][t], shade["hours"], shade["step_m"])),
        row("krosnje", "9.1", "vece",
            lambda t: by["shade"][t]["totals"]["canopy_pct"]),
        row("sunce", "9.1", "manje",
            lambda t: sun_pct(by["shade"][t], shade["hours"])),
        row("pogled_na_reku", "9.3", "vece",
            lambda t: by["views"][t]["totals"]["pct_view"]),
        row("buka", "9.2", "manje",
            lambda t: by["noise"][t]["totals"]["pct_izlozeno"]),
        {"key": "termalni_komfor", "izvor": "9.3", "bolje": None, "vrednosti": None},
    ]

    out = {
        "staze": [{"tip": tip, "label": label} for tip, label in STAZE],
        "parametri": {
            "kontinuitet_min_m": CONT_MIN_M,
            "krosnje_min_h_m": TREE_MIN_H,
            "sunce_datum": SUN_DATE,
            # položaj sunca se računa za pun sat (12:00 … 16:00), ne za interval
            "sunce_sati": [SUN_HOURS[0], SUN_HOURS[-1]],
            "buka_min_indeks": NOISE_MIN_IDX,
            "pogled_min_ugao": views["min_view_deg"],
            "pogled_max_m": views["max_view_m"],
        },
        "redovi": rows,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    for r in rows:
        v = r["vrednosti"]
        print(f"  {r['key']:18} " + ("u pripremi" if v is None else
              "  ".join(f"{tip} {v[tip]:5.1f} %" for tip, _ in STAZE)))
    print(f"  -> {os.path.relpath(OUT_FILE, ROOT)} ({os.path.getsize(OUT_FILE)} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
