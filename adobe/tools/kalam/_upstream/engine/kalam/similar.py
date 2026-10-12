"""Word similarity across Arabic-script and Latin spellings (for correction checks and word mapping)."""
from difflib import SequenceMatcher

_FOLD = {0x623: 0x627, 0x625: 0x627, 0x622: 0x627, 0x671: 0x627, 0x649: 0x64A, 0x629: 0x647, 0x624: 0x648, 0x626: 0x64A}
_ROMAN = {0x627: "a", 0x628: "b", 0x62A: "t", 0x62B: "s", 0x62C: "g", 0x62D: "h", 0x62E: "kh", 0x62F: "d", 0x630: "z",
          0x631: "r", 0x632: "z", 0x633: "s", 0x634: "sh", 0x635: "s", 0x636: "d", 0x637: "t", 0x638: "z", 0x639: "a",
          0x63A: "gh", 0x641: "f", 0x642: "k", 0x643: "k", 0x644: "l", 0x645: "m", 0x646: "n", 0x647: "h", 0x648: "w",
          0x64A: "y", 0x6AF: "g"}
_PUNCT = ".,!?:;\"'()[]" + chr(0x60C) + chr(0x61F) + chr(0x61B) + chr(0x2026)


def tokens(text: str) -> list:
    out = []
    for w in text.split():
        w = "".join(chr(_FOLD.get(ord(c), ord(c))) for c in w if not (0x64B <= ord(c) <= 0x652) and c not in _PUNCT)
        w = w.replace(chr(0x640), "").lower()
        if w:
            out.append(w)
    return out


def latin(w: str) -> bool:
    return any("a" <= c <= "z" for c in w)


def skeleton(w: str) -> str:
    """consonant outline, comparable between Arabic-script and Latin spellings of one word"""
    r = w if latin(w) else "".join(_ROMAN.get(ord(c), "") for c in w)
    return "".join(c for c in r.replace("ph", "f").replace("c", "k").replace("q", "k").replace("x", "ks") if c not in "aeiouyw")


def close(a: str, b: str) -> bool:
    if latin(a) == latin(b):
        return SequenceMatcher(None, a, b).ratio() >= 0.6
    sa, sb = skeleton(a), skeleton(b)
    return bool(sa and sb) and SequenceMatcher(None, sa, sb).ratio() >= 0.5


def align_tokens(a: list, b: list) -> list:
    """monotonic alignment of token lists a -> b; returns for each a[i] the index in b it matches, or None"""
    n, m = len(a), len(b)
    best = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            best[i][j] = max(best[i + 1][j], best[i][j + 1], best[i + 1][j + 1] + (1 if close(a[i], b[j]) else 0))
    out, i, j = [None] * n, 0, 0
    while i < n and j < m:
        if close(a[i], b[j]) and best[i][j] == best[i + 1][j + 1] + 1:
            out[i] = j
            i, j = i + 1, j + 1
        elif best[i + 1][j] >= best[i][j + 1]:
            i += 1
        else:
            j += 1
    return out
