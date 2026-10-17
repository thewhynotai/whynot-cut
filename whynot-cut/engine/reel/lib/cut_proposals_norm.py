# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""The one text normaliser shared by the cut proposals (R-4.3) and the identity scan (`tools/identity_scan.py` loads
this file directly, so it stays standard-library only, with no package-relative imports).

normalize(text) -> words: NFKC, case-fold, format characters (bidi marks, ZWJ/ZWNJ…) removed, Arabic harakat, Quranic
marks and tatweel removed, letter variants unified (أإآٱ→ا ى→ي ة→ه ؤ→و ئ→ي, Persian ی→ي ک→ك ۀ→ه), every character that
is not a letter or a digit is a word break.
segments(text) -> word lists split at hard punctuation (, ; : ! ? ، ؛ ؟ ۔ brackets quotes «» | a '.' before a space or
the end, a spaced dash), so a phrase match never joins words across a comma or a sentence end.
glued_parts(raw_word) / prefix_forms(word): the extra spellings a match should also try (CamelCase and letter/digit
joins; an Arabic proclitic such as و ف ب ك ل ال وال بال لل in front of a word).
"""
from __future__ import annotations

import re
import unicodedata

# Bump on ANY change to what normalize/segments/glued_parts/prefix_forms return: the identity hash file records the
# version it was made with and the scan refuses a mismatch (so a tweak for the cut proposals can never let it pass).
NORM_VERSION = 2

_AR = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
                     "ی": "ي", "ک": "ك", "ۀ": "ه"})
_DROP = re.compile("[\u064b-\u065f\u0670ـ\u06d6-\u06ed\u00ad\u061c\u180e\u200b-\u200f\u202a-\u202e"
                   "\u2060-\u2064\u2066-\u206f\ufeff]")
HARD = re.compile(r"[,;:!?()\[\]{}\"'«»“”‘’„،؛؟۔|<>]|\.(?=\s|$)|\s[-–—]+\s")
WORD = re.compile(r"[^\W_]+")
_GLUE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|(?<=[^\W\d_])(?=\d)|(?<=\d)(?=[^\W\d_])")
AR_PREFIXES = ("وال", "بال", "فال", "كال", "لل", "ال", "و", "ف", "ب", "ك", "ل")
_ARABIC_LETTER = re.compile("[ء-ي]")


_AR_MAP = {chr(k): v for k, v in _AR.items()}
_AR_RX = re.compile("[" + "".join(_AR_MAP) + "]")     # sub over the few variant letters: far faster than translate


def prepare(text: str) -> str:
    """NFKC, format characters and Arabic marks removed, letter variants unified; case kept (for glued_parts).
    Line breaks are never added or removed, so a prepared text keeps the line numbers of the original."""
    t = _DROP.sub("", unicodedata.normalize("NFKC", text))
    return _AR_RX.sub(lambda m: _AR_MAP[m.group()], t)


def strip_marks(text: str) -> str:
    """Only the dropping half of prepare(): format characters, Arabic marks and tatweel out, nothing else changed (no
    NFKC). For a reader that must see neighbouring characters first: a hidden mark between «3» and «½»."""
    return _DROP.sub("", text)


def clean(text: str) -> str:
    return prepare(text).casefold()


def segments(text: str) -> list[list[str]]:
    out = []
    for seg in HARD.split(clean(text)):
        words = WORD.findall(seg)
        if words:
            out.append(words)
    return out


def normalize(text: str) -> list[str]:
    return [w for seg in segments(text) for w in seg]


def glued_parts(raw_word: str) -> list[str]:
    """`VexilorScene` → [vexilor, scene]; `vexilor2` → [vexilor, 2]; a word with no joins → [word] (case-folded)."""
    return [p.casefold() for p in _GLUE.split(raw_word) if p]


_DEFINITE = ("وال", "بال", "فال", "كال", "لل")      # a proclitic fused with the article ال


def prefix_forms(word: str, min_rest: int = 4) -> list[str]:
    """The spellings of `word` without its leading Arabic proclitic (longest prefix first), when at least `min_rest`
    Arabic letters remain: `والكتاب` → [كتاب, الكتاب] (the word may keep its own ال), `لكتاب` → [كتاب]; none → [].
    (A shorter remainder is only safe inside a longer phrase: callers that allow it pass min_rest=3.)"""
    for p in AR_PREFIXES:
        rest = word[len(p):]
        if word.startswith(p) and len(rest) >= min_rest and _ARABIC_LETTER.match(rest):
            return [rest, "ال" + rest] if p in _DEFINITE else [rest]
    return []
