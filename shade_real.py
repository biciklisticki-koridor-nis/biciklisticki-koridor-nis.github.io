#!/usr/bin/env python3
"""Pokrivenost senkom po dobu godine — orchestrator za shadeMap pre-compute.

Pipeline:
  1. Učitaj sample tačke iz data/elevation.json (491 uzorak na 30 m korak).
  2. Pripremi JSON input za Node skriptu (shade_compute.js).
  3. Pokreni Puppeteer headless Chrome sa Leaflet + leaflet-shadow-simulator.
  4. Za 4 referentna dana (oba solsticija + obe ravnodnevnice) preuzmi
     getHoursOfSun po tački.
  5. Agregiraj po deonicama i zapiši data/shade_real.json.

ENV:
  SHADEMAP_API_KEY  — neophodan, dobija se na https://shademap.app/about/
"""
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def load_dotenv():
    """Mini parser za .env (KEY=value, # komentari). Ne diramo postojeće env vrednosti."""
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)


load_dotenv()

ELEV_FILE = os.path.join(ROOT, "data", "elevation.json")
OUT_FILE  = os.path.join(ROOT, "data", "shade_real.json")
NODE_SCRIPT = os.path.join(ROOT, "shade_compute.js")

SHADE_SCHEMA = 1

# Niš je u Europe/Belgrade vremenskoj zoni.
# DST 2026: u snazi od 29.03 (poslednja nedelja marta) do 25.10.
# 21.03. je još CET (+01:00); 21.06, 21.09 su CEST (+02:00); 21.12 je CET.
DATES = [
    {
        "key": "mar21",
        "label": "Prolećna ravnodnevnica (21. mart)",
        "start": "2026-03-21T06:30:00+01:00",
        "end":   "2026-03-21T18:30:00+01:00",
    },
    {
        "key": "jun21",
        "label": "Letnji solsticij (21. jun)",
        "start": "2026-06-21T05:00:00+02:00",
        "end":   "2026-06-21T20:00:00+02:00",
    },
    {
        "key": "sep21",
        "label": "Jesenja ravnodnevnica (21. septembar)",
        "start": "2026-09-21T06:30:00+02:00",
        "end":   "2026-09-21T18:30:00+02:00",
    },
    {
        "key": "dec21",
        "label": "Zimski solsticij (21. decembar)",
        "start": "2026-12-21T08:00:00+01:00",
        "end":   "2026-12-21T16:00:00+01:00",
    },
]


def daylight_hours(d):
    """Decimalni sati između start i end (npr. 15.0 za 21. jun)."""
    from datetime import datetime
    s = datetime.fromisoformat(d["start"])
    e = datetime.fromisoformat(d["end"])
    return (e - s).total_seconds() / 3600.0


def samples_hash(samples, dates):
    h = hashlib.sha1()
    for s in samples:
        h.update(f"{s['km']:.3f},{s['lat']:.6f},{s['lon']:.6f},{s['deonica']}|".encode())
    for d in dates:
        h.update(f"{d['key']}:{d['start']}:{d['end']}|".encode())
    return h.hexdigest()[:16]


def load_samples():
    with open(ELEV_FILE) as f:
        elev = json.load(f)
    out = []
    for p in elev["profile"]:
        if p.get("deonica") and p.get("elev_smooth") is not None:
            out.append({
                "km": p["km"],
                "lat": p["lat"],
                "lon": p["lon"],
                "deonica": p["deonica"],
            })
    return out


def aggregate_by_deonica(samples, dates):
    """Računaj pct_sun, pct_shade, avg_sun_hours po deonici i po datumu."""
    by = {}
    for s in samples:
        dn = s["deonica"]
        if dn not in by:
            by[dn] = {"samples": []}
        by[dn]["samples"].append(s)

    daylight = {d["key"]: daylight_hours(d) for d in dates}

    result = {}
    for dn, info in by.items():
        n = len(info["samples"])
        avg_hours = {}
        pct_sun = {}
        pct_shade = {}
        for d in dates:
            k = d["key"]
            hours = [s["sun_hours"].get(k, 0.0) for s in info["samples"]]
            avg = sum(hours) / n
            avg_hours[k] = round(avg, 2)
            pct_sun[k] = round(avg / daylight[k], 3)
            pct_shade[k] = round(1.0 - avg / daylight[k], 3)
        result[dn] = {
            "n_samples": n,
            "avg_sun_hours": avg_hours,
            "pct_sun": pct_sun,
            "pct_shade": pct_shade,
        }
    return result


def aggregate_totals(samples, dates):
    n = len(samples)
    daylight = {d["key"]: daylight_hours(d) for d in dates}
    out = {"n_samples": n, "avg_sun_hours": {}, "pct_sun": {}, "pct_shade": {}}
    for d in dates:
        k = d["key"]
        hours = [s["sun_hours"].get(k, 0.0) for s in samples]
        avg = sum(hours) / n
        out["avg_sun_hours"][k] = round(avg, 2)
        out["pct_sun"][k] = round(avg / daylight[k], 3)
        out["pct_shade"][k] = round(1.0 - avg / daylight[k], 3)
    return out


def main():
    api_key = os.environ.get("SHADEMAP_API_KEY", "").strip()
    if not api_key:
        print("ERROR: SHADEMAP_API_KEY nije postavljen.", file=sys.stderr)
        print("Dobija se na https://shademap.app/about/ (educational tier).", file=sys.stderr)
        print("Pokreni: SHADEMAP_API_KEY=... make shade", file=sys.stderr)
        return 1

    if not os.path.exists(ELEV_FILE):
        print(f"ERROR: nema {ELEV_FILE} — prvo pokreni `make convert`.", file=sys.stderr)
        return 1

    samples = load_samples()
    if not samples:
        print("ERROR: nema validnih sample tačaka u elevation.json.", file=sys.stderr)
        return 1
    cur_hash = samples_hash(samples, DATES)

    if os.path.exists(OUT_FILE):
        try:
            with open(OUT_FILE) as f:
                old = json.load(f)
            if (old.get("samples_hash") == cur_hash
                    and old.get("schema") == SHADE_SCHEMA):
                print(f"shade_real cache hit ({len(samples)} tačaka, {len(DATES)} datuma)")
                return 0
        except (OSError, json.JSONDecodeError):
            pass

    payload = {
        "apiKey":   api_key,
        "samples":  samples,
        "dates":    [{"key": d["key"], "start": d["start"], "end": d["end"]} for d in DATES],
        "viewport": {"w": 1600, "h": 1000},
    }
    print(f"Pokrećem shade_compute.js ({len(samples)} tačaka × {len(DATES)} datuma)...", flush=True)

    proc = subprocess.run(
        ["node", NODE_SCRIPT],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=20 * 60,  # 20 min hard limit
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return proc.returncode

    sys.stderr.write(proc.stderr)
    result = json.loads(proc.stdout)
    enriched_samples = result["samples"]

    by_deonica = aggregate_by_deonica(enriched_samples, DATES)
    totals = aggregate_totals(enriched_samples, DATES)

    out = {
        "schema": SHADE_SCHEMA,
        "samples_hash": cur_hash,
        "dates": [
            {
                "key": d["key"],
                "label": d["label"],
                "start": d["start"],
                "end": d["end"],
                "daylight_hours": round(daylight_hours(d), 2),
            }
            for d in DATES
        ],
        "samples": enriched_samples,
        "by_deonica": by_deonica,
        "totals": totals,
    }
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  -> {os.path.relpath(OUT_FILE, ROOT)}  ({len(enriched_samples)} tačaka)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
