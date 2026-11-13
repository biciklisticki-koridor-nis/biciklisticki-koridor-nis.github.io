"""Preslovljavanje srpske ćirilice u latinicu (koriste lts.py i anketa.py)."""

_CYR = dict(zip("абвгдђежзијклљмнњопрстћуфхцчџш",
                ["a","b","v","g","d","đ","e","ž","z","i","j","k","l","lj","m","n","nj",
                 "o","p","r","s","t","ć","u","f","h","c","č","dž","š"]))


def latin(s):
    """Srpska ćirilica → latinica. Sajt je na latinici, a OSM nazivi ulica i deo
    odgovora u anketi su na ćirilici."""
    if not s:
        return s
    out = []
    for i, ch in enumerate(s):
        lo = ch.lower()
        if lo not in _CYR:
            out.append(ch)
            continue
        t = _CYR[lo]
        if ch != lo:  # veliko slovo: Lj u reči, LJ kad je i sledeće slovo veliko
            nxt = s[i + 1] if i + 1 < len(s) else ""
            t = t.upper() if len(t) > 1 and nxt.isupper() else t.capitalize()
        out.append(t)
    return "".join(out)
