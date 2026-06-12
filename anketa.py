#!/usr/bin/env python3
"""Anonimizuj anketa.csv i izračunaj statistiku → data/anketa.json.

Izlazi su isključivo agregirani brojevi (count po odgovoru).
Ne čuva: ime, e-mail, timestamp, slobodne komentare. Tih kolona nikad nema
u izlazu, niti su keširane bilo gde.
"""
import csv
import json
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SURVEY_FILE = os.path.join(ROOT, "anketa.csv")
OUT_FILE    = os.path.join(ROOT, "data", "anketa.json")

# Šema pitanja: koja je kolona u CSV-u, kako se zove u JSON-u, kratka labela
# za UI (originalna pitanja su predugačka), tip (single / multi-select).
QUESTIONS = [
    {
        "key":   "frequency",
        "col":   3,
        "title": "Koliko često koristite kej Nišave?",
        "type":  "single",
    },
    {
        "key":   "purposes",
        "col":   4,
        "title": "U koje svrhe najčešće koristite kej?",
        "type":  "multi",
    },
    {
        "key":   "would_use_corridor",
        "col":   5,
        "title": "Da li biste koristili kontinuiran i bezbedan biciklistički koridor?",
        "type":  "single",
    },
    {
        "key":   "willing_to_join",
        "col":   6,
        "title": "Da li želite da se uključite u inicijativu?",
        "type":  "single",
    },
    {
        "key":   "contribution",
        "col":   7,
        "title": "Na koji način biste želeli da doprinesete?",
        "type":  "multi",
    },
]


EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
PHONE_RE = re.compile(r"\b0\d{1,2}[/\s.\-]?\d{2,4}[/\s.\-]?\d{2,4}\b")
URL_RE   = re.compile(r"https?://\S+", re.IGNORECASE)

COMMENT_MIN_LEN = 15  # filter "Da", "Ne", "OK", "+" itd.
COMMENT_COL     = 8


def anonymize_comment(text):
    t = URL_RE.sub("[link]", text)
    t = EMAIL_RE.sub("[e-mail]", t)
    t = PHONE_RE.sub("[telefon]", t)
    return t.strip()


def collect_comments(rows):
    seen = set()
    out = []
    for r in rows:
        if len(r) <= COMMENT_COL:
            continue
        raw = r[COMMENT_COL].strip()
        if not raw:
            continue
        anon = anonymize_comment(raw)
        if len(anon) < COMMENT_MIN_LEN:
            continue
        key = anon.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(anon)
    random.Random(42).shuffle(out)  # stabilan ali raznovrstan redosled
    return out


def aggregate(rows, q):
    col = q["col"]
    if q["type"] == "single":
        counts = {}
        answered = 0
        for r in rows:
            v = (r[col] if len(r) > col else "").strip()
            if not v:
                continue
            counts[v] = counts.get(v, 0) + 1
            answered += 1
        answers = sorted(counts.items(), key=lambda x: -x[1])
        return {
            "key":      q["key"],
            "title":    q["title"],
            "type":     "single",
            "answered": answered,
            "answers":  [{"label": k, "count": c} for k, c in answers],
        }

    # multi-select: vrednosti su odvojene znakom ; (Google Forms default)
    counts = {}
    respondents = 0
    for r in rows:
        v = (r[col] if len(r) > col else "").strip()
        if not v:
            continue
        respondents += 1
        seen = set()
        for opt in v.split(";"):
            o = opt.strip()
            if o and o not in seen:
                seen.add(o)
                counts[o] = counts.get(o, 0) + 1
    answers = sorted(counts.items(), key=lambda x: -x[1])
    return {
        "key":         q["key"],
        "title":       q["title"],
        "type":        "multi",
        "respondents": respondents,
        "answers":     [{"label": k, "count": c} for k, c in answers],
    }


def main():
    if not os.path.exists(SURVEY_FILE):
        print(f"Nema {SURVEY_FILE} — preskačem anketu.")
        return
    with open(SURVEY_FILE, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        print(f"Anketa prazna ({SURVEY_FILE}). Preskačem.")
        return
    data = [r for r in rows[1:] if any(cell.strip() for cell in r)]
    total = len(data)

    comments = collect_comments(data)
    out = {
        "total":     total,
        "questions": [aggregate(data, q) for q in QUESTIONS],
        "comments":  comments,
    }
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  -> {os.path.relpath(OUT_FILE, ROOT)}  ({total} odgovora, {len(QUESTIONS)} pitanja, {len(comments)} komentara)")


if __name__ == "__main__":
    sys.exit(main())
