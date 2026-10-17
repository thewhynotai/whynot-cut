# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Caption looks (R-4.1, Phase 4 Task 23): the look catalog, the caption-look palette from the client's brand tokens,
the per-client preference and the reel override, and `pick` (diff first, write only when asked).

A caption look is `<grouping>-<presentation>` (word | phrase | line × clean | boxed | highlight, minus the refused
`word-highlight`) plus an emphasis (colour | weight | tag). The catalog is `config/defaults/looks/caption-looks.json`
(a client may override it in its reel-profile, like every config file). The preference lives in the client's
`reel-profile/style.json` under `captions`:
    {"grouping": {"mode": "auto" | "fixed", "value": …}, "presentation": {…}, "emphasis": {…}}
A client with no `captions` block keeps today's captions (resolve() returns look None), so its output stays
byte-identical. A one-reel override (edit-decisions) wins for that reel and never changes the profile.
Spec: docs/superpowers/specs/addendum-h/source-r-specs/R-4.1-caption-looks.md.
"""
from __future__ import annotations

import copy
from fractions import Fraction
from pathlib import Path

from .common import (CLIENT_PROFILE_REL, brand_fallback, current_context, load_config, read_json, round_half_up,
                     write_json)

CATALOG = "looks/caption-looks.json"
AXES = ("grouping", "presentation", "emphasis")
EMPHASES = ("colour", "weight", "tag")
DIGIT_SETS = ("western", "arabic_indic")


class LookError(ValueError):
    """An unknown look, axis value or a pick with no client to write to."""


def caption_catalog() -> dict:
    """The caption-look catalog (defaults <- shipped profile <- client reel-profile), a private copy."""
    return copy.deepcopy(load_config(CATALOG))


def validate_catalog(cat: dict) -> list[str]:
    """Problems in a catalog, one line each (empty = valid)."""
    errs = []
    groupings, presentations = cat.get("groupings") or {}, cat.get("presentations") or {}
    lks = cat.get("looks") or {}
    if not lks:
        errs.append("no looks")
    for name, lk in lks.items():
        g, p = lk.get("grouping"), lk.get("presentation")
        if g not in groupings:
            errs.append(f"{name}: unknown grouping {g!r}")
        if p not in presentations:
            errs.append(f"{name}: unknown presentation {p!r}")
        if name != f"{g}-{p}":
            errs.append(f"{name}: the name must be <grouping>-<presentation> ({g}-{p})")
        if not isinstance(lk.get("size"), (int, float)) or lk["size"] <= 0:
            errs.append(f"{name}: size must be a positive number")
    for name, r in (cat.get("refused") or {}).items():
        if name in lks:
            errs.append(f"{name}: refused but also listed as a look")
        if (r or {}).get("use") not in lks:
            errs.append(f"{name}: refused, but its replacement {(r or {}).get('use')!r} is not a look")
    for old, new in (cat.get("legacy") or {}).items():
        if new not in lks:
            errs.append(f"legacy name {old}: {new!r} is not a look")
    for e in cat.get("emphasis") or {}:
        if e not in EMPHASES:
            errs.append(f"unknown emphasis {e!r}")
    return errs


def combine(grouping: str, presentation: str, emphasis: str, cat: dict | None = None) -> dict:
    """The look for these axis values: {look, grouping, presentation, emphasis, notes}. `word-highlight` is refused
    and becomes its replacement with a note; an unknown value raises LookError."""
    cat = cat or caption_catalog()
    if grouping not in cat["groupings"]:
        raise LookError(f"unknown caption grouping {grouping!r} (use {', '.join(cat['groupings'])})")
    if presentation not in cat["presentations"]:
        raise LookError(f"unknown caption presentation {presentation!r} (use {', '.join(cat['presentations'])})")
    if emphasis not in cat["emphasis"]:
        raise LookError(f"unknown caption emphasis {emphasis!r} (use {', '.join(cat['emphasis'])})")
    name, notes = f"{grouping}-{presentation}", []
    refused = (cat.get("refused") or {}).get(name)
    if refused:
        notes.append(f"{name} is not offered ({refused.get('why', 'refused')}): using {refused['use']}")
        name = refused["use"]
    lk = cat["looks"][name]
    on_band = ((cat["emphasis"].get(emphasis) or {}).get("on_band") or {})
    if lk["presentation"] == "highlight" and on_band.get("use"):
        notes.append(f"{emphasis} emphasis on {name}: {on_band.get('why', 'not on the band')}: using {on_band['use']}")
        emphasis = on_band["use"]
    return {"look": name, "grouping": lk["grouping"], "presentation": lk["presentation"], "emphasis": emphasis,
            "notes": notes}


def legacy_look(name: str, cat: dict | None = None) -> str:
    """A catalog look name for `name`: a look's own name, or one of Task 16's four starter names."""
    cat = cat or caption_catalog()
    if name in cat["looks"]:
        return name
    if name in (cat.get("legacy") or {}):
        return cat["legacy"][name]
    if name in (cat.get("refused") or {}):            # word-highlight: its replacement (combine() says why)
        return cat["refused"][name]["use"]
    raise LookError(f"unknown caption look {name!r} (use one of {', '.join(sorted(cat['looks']))})")


def frames(n: int, fps: float) -> int:
    """A duration given in frames at the catalog's 30 fps base, at `fps` (round half up, at least 1)."""
    return max(1, round_half_up(Fraction(int(n)) * Fraction(fps).limit_denominator(1001) / 30))


# --------------------------------------------------------------------------- palette
def _rgb(h: str) -> tuple:
    h = str(h).lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def palette(db: Path) -> dict:
    """The colour roles caption looks draw with, from the client's brand-tokens.json: primary, accent (else primary),
    highlight (else accent), ink, paper and white (each else the brand fallback)."""
    tok = read_json(Path(db) / "branding/brand-tokens.json", {}) or {}
    roles, der = tok.get("roles") or {}, tok.get("derived") or {}

    def role(src: dict, key: str):
        v = (src.get(key) or {}).get("hex")
        return _rgb(v) if v else None
    primary = role(roles, "primary") or _rgb(brand_fallback("primary"))
    accent = role(roles, "accent") or primary
    return {"primary": primary, "accent": accent, "highlight": role(roles, "highlight") or accent,
            "ink": role(der, "ink") or _rgb(brand_fallback("ink")),
            "paper": role(der, "paper_tint") or _rgb(brand_fallback("paper_tint")),
            "white": role(roles, "neutral_light") or _rgb(brand_fallback("neutral_light"))}


# --------------------------------------------------------------------------- preference
def speech_rate(words: list, pause_ignore_ms: int | None = None) -> float:
    """Spoken words per second: the words over the time from the first to the last word, minus pauses longer than
    `pause_ignore_ms` (a long silence is not slow speech). 0.0 when there are no timed words."""
    if pause_ignore_ms is None:
        pause_ignore_ms = int((caption_catalog().get("auto") or {}).get("pause_ignore_ms", 1500))
    ws = sorted((w for w in words or [] if str(w.get("word", "")).strip()), key=lambda w: w["start_ms"])
    if not ws:
        return 0.0
    span = ws[-1]["end_ms"] - ws[0]["start_ms"]
    for a, b in zip(ws, ws[1:]):
        gap = b["start_ms"] - a["end_ms"]
        if gap > pause_ignore_ms:
            span -= gap
    return len(ws) / (span / 1000) if span > 0 else 0.0


def _auto(axis: str, cat: dict, rate: float | None) -> tuple[str, str]:
    a = cat.get("auto") or {}
    if axis == "grouping":
        if rate is None or rate <= 0:
            return "phrase", "no word timing: phrase"
        if rate >= a.get("fast_wps", 3.2):
            return "phrase", f"{rate:.1f} words/s (fast speech): phrase"
        if rate <= a.get("slow_wps", 2.2):
            return "line", f"{rate:.1f} words/s (calm speech): line"
        return "phrase", f"{rate:.1f} words/s: phrase"
    if axis == "presentation":
        return a.get("presentation", "clean"), f"presentation {a.get('presentation', 'clean')} (the default)"
    return a.get("emphasis", "colour"), f"emphasis {a.get('emphasis', 'colour')} (the default)"


def _valid(axis: str, value, cat: dict) -> bool:
    pool = {"grouping": cat["groupings"], "presentation": cat["presentations"], "emphasis": cat["emphasis"]}[axis]
    return isinstance(value, str) and value in pool


def resolve(words: list | None = None, override=None, motion_look: dict | None = None,
            style: dict | None = None) -> dict:
    """The caption look of one reel: reel override > the client's fixed value > auto, per axis.

    -> {look, grouping, presentation, emphasis, sources {axis: reel|fixed|auto}, source, reason, notes, motion, rate,
    digits}. `digits` is the client's digit set for Arabic runs (captions.digits: western | arabic_indic).
    look is None (source "default") when the client saved no caption preference and the reel has no override: the
    caller keeps today's captions. `override` is a look name (Task 16 names too) or {axis: value}. A motion look
    with caption_motion "none" (R-6.1) turns the entrance off and a moving highlight into boxed."""
    cat = caption_catalog()
    style = load_config("style.json") if style is None else style
    prefs = style.get("captions") if isinstance(style.get("captions"), dict) else None
    motion = dict(cat.get("motion") or {})
    if prefs is None and not override:
        return {"look": None, "grouping": None, "presentation": None, "emphasis": None, "sources": {},
                "source": "default", "reason": "no caption look saved for this client: today's captions",
                "notes": [], "motion": motion, "rate": None, "digits": "western"}
    notes: list[str] = []
    digits = (prefs or {}).get("digits", "western")
    if digits not in DIGIT_SETS:
        notes.append(f"client caption digits {digits!r} is not a digit set ({', '.join(DIGIT_SETS)}): using western")
        digits = "western"
    over: dict = {}
    if isinstance(override, str):
        if override in (cat.get("refused") or {}):
            r = cat["refused"][override]
            notes.append(f"{override} is not offered ({r.get('why', 'refused')}): using {r['use']}")
        lk = cat["looks"][legacy_look(override, cat)]
        over = {"grouping": lk["grouping"], "presentation": lk["presentation"]}
    elif isinstance(override, dict):
        for axis, v in override.items():
            if axis in AXES and _valid(axis, v, cat):
                over[axis] = v
            else:
                notes.append(f"reel caption override {axis}={v!r} is not valid: ignored")
    rate = speech_rate(words, int((cat.get("auto") or {}).get("pause_ignore_ms", 1500))) if words else None
    vals, sources, why = {}, {}, []
    for axis in AXES:
        if axis in over:
            vals[axis], sources[axis] = over[axis], "reel"
            why.append(f"{axis} {over[axis]} (this reel)")
            continue
        pref = (prefs or {}).get(axis)
        if isinstance(pref, str):
            pref = {"mode": "fixed", "value": pref}
        if isinstance(pref, dict) and pref.get("mode") == "fixed":
            if _valid(axis, pref.get("value"), cat):
                vals[axis], sources[axis] = pref["value"], "fixed"
                why.append(f"{axis} {pref['value']} (client choice)")
                continue
            notes.append(f"client caption {axis} {pref.get('value')!r} is not a known value: using auto")
        v, line = _auto(axis, cat, rate)
        vals[axis], sources[axis] = v, "auto"
        why.append(f"auto {line}")
    res = combine(vals["grouping"], vals["presentation"], vals["emphasis"], cat)
    notes += res["notes"]
    if (motion_look or {}).get("caption_motion") == "none":
        motion["entrance"] = "none"
        if res["presentation"] == "highlight":
            boxed = combine(res["grouping"], "boxed", res["emphasis"], cat)
            notes.append(f"this motion look keeps captions still: {res['look']} becomes {boxed['look']}")
            res = boxed
    return {"look": res["look"], "grouping": res["grouping"], "presentation": res["presentation"],
            "emphasis": res["emphasis"], "sources": sources,
            "source": "reel" if "reel" in sources.values() else "profile",
            "reason": f"{res['look']} + {res['emphasis']}: " + "; ".join(why), "notes": notes, "motion": motion,
            "rate": None if rate is None else round(rate, 2), "digits": digits}


# --------------------------------------------------------------------------- pick
def _client_style_file() -> Path:
    root = current_context().root
    if not root:
        raise LookError("no client folder: run this inside a client (or pass --root)")
    return Path(root) / CLIENT_PROFILE_REL / "style.json"


def pick_preference(look: str, emphasis: str | None = None, yes: bool = False) -> dict:
    """Make `look` (and `emphasis`, when given) this client's fixed caption choice. The diff against the current
    preference comes first; the client's reel-profile/style.json is written only with yes=True, only its `captions`
    block, and only when something changes. -> {look, diff: [{key, from, to}], written, file}."""
    cat = caption_catalog()
    name = legacy_look(look, cat)
    if emphasis is not None and emphasis not in cat["emphasis"]:
        raise LookError(f"unknown caption emphasis {emphasis!r} (use {', '.join(cat['emphasis'])})")
    lk = cat["looks"][name]
    want = {"grouping": lk["grouping"], "presentation": lk["presentation"]}
    if emphasis is not None:
        want["emphasis"] = emphasis
    current = (load_config("style.json").get("captions") or {})
    diff = []
    for axis, v in want.items():
        new = {"mode": "fixed", "value": v}
        old = current.get(axis)
        if old != new:
            diff.append({"key": f"captions.{axis}", "from": old, "to": new})
    f = _client_style_file()
    written = False
    if yes and diff:
        own = read_json(f, {}) or {}
        block = dict(own.get("captions") or {})
        for d in diff:
            block[d["key"].split(".", 1)[1]] = d["to"]
        own["captions"] = block
        write_json(f, own)
        written = True
    return {"look": name, "diff": diff, "written": written, "file": str(f)}
