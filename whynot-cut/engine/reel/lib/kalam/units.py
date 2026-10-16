# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
# Ported unchanged from the owner's Kalam engine (kalam/units.py); see adobe/tools/README.md
"""Meaning units. While correcting, Claude puts "|" where a sentence or clause the speaker says ends;
a "|" at the very end means the line finishes a unit, no "|" at the end means the sentence continues on the next line.
Captions then break at those places and keep each unit whole."""
from .rules import enforce

SOFT = 1.25     # a whole unit may run this much past the line length rather than be split


def apply_units(p: dict, line, glossary: dict, mode: str) -> dict:
    """set p["text"] (rules enforced per unit), p["unit_breaks"] (word indexes where a unit starts),
    p["unit_end"] (True / False, or None when there is no unit information, e.g. a correction fallback)"""
    if line is None:
        p["unit_breaks"], p["unit_end"] = set(), None
        return p
    segs = line.split("|")
    units = [u for u in (enforce(s, glossary, mode) for s in segs) if u]
    breaks, n = set(), 0
    for u in units[:-1]:
        n += len(u.split(" "))
        breaks.add(n)
    p["text"] = " ".join(units)
    p["unit_breaks"] = breaks
    p["unit_end"] = not segs[-1].strip()
    return p


def is_whole_unit(p: dict, i: int, j: int, n: int) -> bool:
    """words [i, j) of phrase p are exactly one complete meaning unit"""
    if p.get("unit_end") is None:
        return False
    b = p.get("unit_breaks") or set()
    starts_unit = i == 0 or i in b
    ends_unit = j in b or (j == n and p["unit_end"])
    return starts_unit and ends_unit and not any(i < k < j for k in b)


def join_continuations(phrases: list, stop_pause: float = 0.6) -> list:
    """a line that does not end its sentence (unit_end False) is joined with the next line when the speaker
    only paused briefly, so the sentence can be split at its best place instead of at the breath"""
    out = []
    for p in phrases:
        prev = out[-1] if out else None
        if prev is not None and prev.get("unit_end") is False and p.get("unit_end") is not None \
                and p["s"] - prev["e"] < stop_pause:
            n = len(prev["text"].split(" "))
            out[-1] = dict(prev, text=prev["text"] + " " + p["text"], e=p["e"],
                           words=(prev.get("words") or []) + (p.get("words") or []),
                           unit_breaks=set(prev.get("unit_breaks") or set()) | {n + b for b in (p.get("unit_breaks") or set())},
                           unit_end=p["unit_end"], punct=p.get("punct", ""))
        else:
            out.append(p)
    return out


def touches_unit(p: dict, i: int, j: int, n: int) -> bool:
    """words [i, j) start or end exactly at a meaning-unit boundary"""
    if p.get("unit_end") is None:
        return False
    b = p.get("unit_breaks") or set()
    return i == 0 or i in b or j in b or (j == n and p["unit_end"])
