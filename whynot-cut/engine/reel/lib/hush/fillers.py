# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Hush: filler-word matching (Python twin of adobe/tools/hush/src/js/fillers.js).

Words come from Whisper as dicts {w, s, e, p} (seconds relative to the analysed range). Same names in snake_case, same
result keys (s, e, label, kind, on, source). `norm` uses explicit character classes equal to the JS regular
expressions (the JS whitespace set is spelled out; Python's own whitespace class is a different set).
"""
from __future__ import annotations

import math
import re

import numpy as np

from ._js import js_str

# "strong" fillers are ticked by default; "soft" ones are listed but left unticked (they are often real words)
DEFAULT_STRONG = ("um, umm, uh, uhh, uhm, erm, er, ah, ahh, hmm, hm, mm, mmm, mhm, "
                  "\u0627\u0645\u0645, \u0627\u0645\u0645\u0645, \u0645\u0645\u0645, "
                  "\u0645\u0645, \u0622\u0647, \u0627\u0627\u0647, "
                  "\u0627\u0627\u0627\u0647, \u0647\u0645\u0645\u0645, "
                  "\u0647\u0645\u0645, \u0627\u0648\u0647")
DEFAULT_SOFT = ("like, you know, basically, actually, i mean, \u064a\u0639\u0646\u064a, "
                "\u0637\u064a\u0628, \u0627\u0635\u0644\u0627, \u0628\u0642\u0649, "
                "\u0627\u0645, \u0627\u064a\u0647")

# the JS \s set (WhiteSpace + LineTerminator), spelled out
_WS = "\t\n\v\f\r \u00a0\u1680" + "".join(chr(c) for c in range(0x2000, 0x200B)) + \
      "\u2028\u2029\u202f\u205f\u3000\ufeff"
_WS_RUN = re.compile("[" + re.escape(_WS) + "]+")
_DIACRITICS = re.compile("[\u064b-\u065f\u0670\u0640]")  # harakat, dagger alef, tatweel
_ALEF = re.compile("[\u0622\u0623\u0625\u0671]")  # alef forms -> bare alef
# . , ! ? ; : " ' ` right single quote, curly double quotes, ( ) [ ] Arabic comma / semicolon / question mark, ellipsis, -
_PUNCT = {ord(c): None for c in ".,!?;:\"'`()[]-"}
_PUNCT.update({0x2019: None, 0x201C: None, 0x201D: None, 0x060C: None, 0x061B: None, 0x061F: None, 0x2026: None})
_SPLIT = re.compile("[,\n\u060c]+")
_HES_LATIN = re.compile(r"(u+h*m+|u+h+|e+r+m*|a+h+|h+m+|m{2,}|m+h+m+)")
_HES_ARABIC = re.compile("(\u0627+\u0645{2,}|\u0645{2,}|\u0627{2,}\u0647+|\u0627*\u0647+\u0645{2,}"
                         "|\u0627+\u0648+\u0647+)")

__all__ = ["DEFAULT_STRONG", "DEFAULT_SOFT", "norm", "parse_list", "is_hesitation", "find", "untranscribed"]


def norm(w):
    """Lower-case, strip punctuation, Arabic diacritics/tatweel, unify alef/yeh forms, fold whitespace."""
    s = js_str(w).lower()
    s = _DIACRITICS.sub("", s)
    s = _ALEF.sub("\u0627", s)
    s = s.replace("\u0649", "\u064a")  # alef maqsura -> yeh
    s = s.translate(_PUNCT)
    return _WS_RUN.sub(" ", s).strip(_WS)


def parse_list(text):
    """A comma / Arabic comma / newline separated list -> normalised non-empty entries."""
    out = []
    for part in _SPLIT.split(js_str(text) if text else ""):
        n = norm(part)
        if n:
            out.append(n)
    return out


def is_hesitation(n):
    """Elongated hesitations whatever their length: ummmm, hmmmm, aaah, Arabic mmm / aah."""
    return bool(_HES_LATIN.fullmatch(n) or _HES_ARABIC.fullmatch(n))


def find(words, strong_text, soft_text):
    """Match single words and two-word phrases ("you know", "i mean") against the lists."""
    strong, soft = parse_list(strong_text), parse_list(soft_text)
    out, i, count = [], 0, len(words)
    while i < count:
        n = norm(words[i].get("w"))
        if not n:
            i += 1
            continue
        n2 = n + " " + norm(words[i + 1].get("w")) if i + 1 < count else None
        hit = None
        if n2 is not None and n2 in strong:
            hit = (True, 2)
        elif n2 is not None and n2 in soft:
            hit = (False, 2)
        elif n in strong or is_hesitation(n):
            hit = (True, 1)
        elif n in soft:
            hit = (False, 1)
        if hit:
            last = words[i + hit[1] - 1]
            label = js_str(words[i].get("w")) + " " + js_str(last.get("w")) if hit[1] == 2 else words[i].get("w")
            out.append({"s": words[i]["s"], "e": last["e"], "label": label, "kind": "filler", "on": hit[0],
                        "source": "word"})
            i += hit[1] - 1
        i += 1
    return out


def untranscribed(env, hop, threshold, words, min_len, max_len):
    """Sound Whisper did not turn into words: loud runs >= min_len with no word within 15 hops of them."""
    a_env = env.astype(np.float64).tolist() if isinstance(env, np.ndarray) else [float(x) for x in env]
    n = len(a_env)
    out, start, covered = [], -1, bytearray(n)
    for w in words:
        a = max(0, math.floor(w["s"] / hop) - 15)
        b = min(n, math.ceil(w["e"] / hop) + 15)
        if b > a:
            covered[a:b] = b"\x01" * (b - a)
    for i in range(n + 1):
        loud = i < n and a_env[i] >= threshold and not covered[i]
        if loud and start < 0:
            start = i
        if not loud and start >= 0:
            ln = (i - start) * hop
            if min_len <= ln <= max_len:
                out.append({"s": start * hop, "e": i * hop, "label": "(sound)", "kind": "filler", "on": False,
                            "source": "sound"})
            start = -1
    return out
