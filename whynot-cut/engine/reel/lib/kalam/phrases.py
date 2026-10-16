# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
# Ported unchanged from the owner's Kalam engine (kalam/phrases.py); see adobe/tools/README.md
"""Spoken phrases: runs of aligned words with no real pause between them."""


_STOP = ".?!" + chr(0x61F) + chr(0x2026)
_COMMA = ",;:" + chr(0x60C) + chr(0x61B)


def end_punct(word: str) -> str:
    """how the transcriber ended this word: "." sentence end, "," clause end, "" nothing"""
    w = word.rstrip()
    if w and w[-1] in _STOP:
        return "."
    if w and w[-1] in _COMMA:
        return ","
    return ""


def make_phrase(words: list) -> dict:
    return {"text": " ".join(w["w"] for w in words), "s": words[0]["s"], "e": words[-1]["e"], "words": words,
            "punct": end_punct(words[-1]["w"])}


def phrases(words: list, min_pause: float = 0.22) -> list:
    out, cur = [], []
    for w in words:
        if cur and w["s"] - cur[-1]["e"] >= min_pause:
            out.append(make_phrase(cur))
            cur = []
        cur.append(w)
    if cur:
        out.append(make_phrase(cur))
    return out
