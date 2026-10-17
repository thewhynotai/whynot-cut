# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Word and character error rates for transcripts (Phase 4 T4.14; the 6B eval set, benchmark G-06/G-17, reuses it).

ONE normalisation for both sides (`tokens`): plan.norm (NFKC, Arabic diacritics and tatweel removed, أ/إ/آ -> ا,
ة -> ه, ى -> ي, ؤ/ئ seats, ئو = ؤو, Arabic-Indic and Persian digits -> ASCII, punctuation dropped, lower case), except
that a number with a decimal point stays ONE token and keeps it: "3.5", "٣٫٥" and "3,5" are all "3.5" (a dose must
never compare equal to "35"). A point already spoken as its own word ("3 . 5") is two tokens. Thousands separators
read the same way ("1,000" -> "1.000") on both sides, so they still compare equal.
WER = (substitutions + deletions + insertions) / reference words; CER = character edit distance over the normalised
text with the spaces removed, so Arabic word-splitting variants ("عبد الله" / "عبدالله") cost nothing in CER but
count in WER. An empty reference gives None (undefined), never a division by zero. Corpus totals add the counts
(`total`), never average the per-clip rates. Standard library only.
"""
from __future__ import annotations

import re
import unicodedata

from .plan import norm

_DIGITS = str.maketrans({**{chr(0x660 + i): str(i) for i in range(10)}, **{chr(0x6F0 + i): str(i) for i in range(10)}})
_SEP = "[.,٫،]"                  # point, comma, Arabic decimal separator, Arabic comma
_DECIMAL = re.compile(rf"\d+(?:{_SEP}\d+)+")
_GLUED = re.compile(rf"(\d+(?:{_SEP}\d+)+)(\D.*)")         # "3.5mg", "3.5مجم": the number, then the unit


def _no_format(t: str) -> str:
    """Invisible format characters (RLM/LRM marks, zero-width spaces: category Cf) removed."""
    return "".join(c for c in t if unicodedata.category(c) != "Cf")


def _strip_edges(t: str) -> str:
    """Punctuation (Unicode category P*) and symbols trimmed from both ends of one raw token."""
    a, b = 0, len(t)
    while a < b and unicodedata.category(t[a])[0] in "PS":
        a += 1
    while b > a and unicodedata.category(t[b - 1])[0] in "PS":
        b -= 1
    return t[a:b]


def tokens(x) -> list:
    """The normalised words of a text or a list of words (non-text items are dropped)."""
    if isinstance(x, (list, tuple)):
        text = " ".join(w for w in x if isinstance(w, str))
    else:
        text = x if isinstance(x, str) else ""
    out = []
    for raw in _no_format(text).split():
        t = _strip_edges(unicodedata.normalize("NFKC", raw).translate(_DIGITS))
        g = _GLUED.fullmatch(t)
        if _DECIMAL.fullmatch(t) or g:
            out.append(re.sub(_SEP, ".", g.group(1) if g else t))
            if g:
                out += norm(g.group(2)).split()
            continue
        out += norm(raw).split()
    return out


def _trim(a: list, b: list) -> tuple:
    """Drop the common prefix and suffix (they cost nothing): long, mostly equal transcripts stay fast."""
    i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]:
        i += 1
    j = 0
    while j < len(a) - i and j < len(b) - i and a[-1 - j] == b[-1 - j]:
        j += 1
    return a[i:len(a) - j], b[i:len(b) - j]


def _counts(r: list, h: list) -> tuple:
    """(sub, del, ins) of a minimum edit script; ties prefer substitution, then deletion, then insertion."""
    r, h = _trim(r, h)
    n, m = len(r), len(h)
    if not n or not m:
        return 0, n, m
    # rows of (cost, sub, del, ins); one row at a time
    prev = [(j, 0, 0, j) for j in range(m + 1)]
    for i in range(1, n + 1):
        cur = [(i, 0, i, 0)]
        ri = r[i - 1]
        for j in range(1, m + 1):
            d = prev[j - 1]
            if ri == h[j - 1]:
                best = d
            else:
                best = (d[0] + 1, d[1] + 1, d[2], d[3])
            up = prev[j]
            if up[0] + 1 < best[0]:
                best = (up[0] + 1, up[1], up[2] + 1, up[3])
            left = cur[j - 1]
            if left[0] + 1 < best[0]:
                best = (left[0] + 1, left[1], left[2], left[3] + 1)
            cur.append(best)
        prev = cur
    _, s, dl, ins = prev[m]
    return s, dl, ins


def wer(ref, hyp) -> dict:
    """{"wer", "sub", "del", "ins", "n"} of hyp against ref (lists of words or texts), after `tokens`."""
    r, h = tokens(ref), tokens(hyp)
    s, d, i = _counts(r, h)
    n = len(r)
    rate = round((s + d + i) / n, 4) if n else (0.0 if not h else None)
    return {"wer": rate, "sub": s, "del": d, "ins": i, "n": n}


def _distance(a: str, b: str) -> int:
    """Character edit distance, bit-parallel (Myers / Hyyroe): one pass over b with Python big integers, so a whole
    episode's transcript (tens of thousands of characters) takes about a second, not an O(n*m) table."""
    a, b = _trim(list(a), list(b))
    if not a or not b:
        return len(a) + len(b)
    m = len(a)
    peq: dict = {}
    for i, c in enumerate(a):
        peq[c] = peq.get(c, 0) | (1 << i)
    mask, hi = (1 << m) - 1, 1 << (m - 1)
    pv, mv, score = mask, 0, m
    for c in b:
        eq = peq.get(c, 0)
        xv = eq | mv
        xh = (((eq & pv) + pv) ^ pv) | eq
        ph = (mv | ~(xh | pv)) & mask
        mh = pv & xh
        if ph & hi:
            score += 1
        elif mh & hi:
            score -= 1
        ph = ((ph << 1) | 1) & mask
        mh = (mh << 1) & mask
        pv = (mh | ~(xv | ph)) & mask
        mv = ph & xv
    return score


def cer(ref, hyp) -> float | None:
    """Character error rate over the normalised text without spaces; None for an empty reference with a hypothesis."""
    r, h = "".join(tokens(ref)), "".join(tokens(hyp))
    if not r:
        return 0.0 if not h else None
    return round(_distance(r, h) / len(r), 4)


def total(results: list) -> dict:
    """Corpus totals of several wer() results: the counts add, WER = all errors / all reference words."""
    s = sum(x.get("sub", 0) for x in results)
    d = sum(x.get("del", 0) for x in results)
    i = sum(x.get("ins", 0) for x in results)
    n = sum(x.get("n", 0) for x in results)
    return {"wer": round((s + d + i) / n, 4) if n else None, "sub": s, "del": d, "ins": i, "n": n}
