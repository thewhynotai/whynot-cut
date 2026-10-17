# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""The look recommender (3.0 Phase 4 Task 28, R-4.6): which caption look (now) and which motion look (Phase 6) suits
one reel, with the top three and one plain line for the editor.

    score(look) = 3 x fit[content type][look]   the reel's content type (00_inputs/source.json), 0..1
                + 2 x reference match            the client's reference videos (cuts per minute, optional traits)
                + 1 x delivery fit               caption looks: the grouping against the speech rate; motion: neutral
                - recent use                     motion looks only: weight x decay^age over the client's last reels
                                                 that used a motion look

Every table lives in config/defaults/looks/recommender.json. Caption looks have no recent-use penalty and no variety
rule (the brand stays consistent): the same content type and speech rate give the same caption look. Motion looks:
only `accepted` looks that fit at least the variety min_fit are picked, `preview_gate` looks are offered for a hand
pick, `planned` ones never; a look used in both of the client's last two motion reels gives way to the next one;
playful looks never on medical or religious content (an override included). A fixed client choice or a reel override
wins, with no scoring. A client's own looks or content types that the tables do not name score neutral, with a
warning (never a crash).

The recommender only suggests: nothing here changes a reel. record_choice keeps what a reel used
(01_analysis/look-choice.json), the history the motion penalty and the variety rule read.
"""
from __future__ import annotations

import copy
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import looks
from .common import CONFIG_DIR, current_context, file_locked, load_config, read_json, write_json
from .errors import FileFormatError

CHOICE_REL = "01_analysis/look-choice.json"
LEVELS = {"low": 0, "medium": 1, "high": 2, "light": 0, "regular": 1, "heavy": 2}
OPTIONAL_REF = ("caption_density", "text_weight")


class RecommendError(ValueError):
    pass


def _read(path, default=None):
    """A JSON input the recommender only weighs: missing or not valid JSON counts as absent (never a crash). Other
    errors (a file that cannot be opened) are real and propagate."""
    try:
        v = read_json(path, default)
    except (FileFormatError, UnicodeDecodeError, ValueError):
        return default
    return default if v is None else v


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# --------------------------------------------------------------------------- catalogue
def catalog() -> dict:
    return copy.deepcopy(load_config("looks/recommender.json"))


def problems(cat: dict) -> list[str]:
    """What the caption tables do not cover or name wrongly, against the caption catalogue in force (a client may add
    looks; a profile may add fit rows): missing entries score neutral, unknown names are never used."""
    names = set(looks.caption_catalog()["looks"])
    c = cat.get("caption") or {}
    out = []
    for key in ("order", "traits", "display"):
        got = set(c.get(key) or [])
        if got - names:
            out.append(f"caption {key} names unknown looks {sorted(got - names)}")
        if names - got:
            out.append(f"caption {key} misses {sorted(names - got)}")
    for ctype, row in (c.get("fit") or {}).items():
        row = row if isinstance(row, dict) else {}
        if set(row) - names:
            out.append(f"caption fit[{ctype}] names unknown looks {sorted(set(row) - names)}")
        if names - set(row):
            out.append(f"caption fit[{ctype}] misses {sorted(names - set(row))}")
    return out


def validate(cat: dict) -> None:
    """The shipped tables must be complete (tests, release): any problem raises."""
    p = problems(cat)
    if p:
        raise RecommendError("recommender.json: " + "; ".join(p))


def motion_looks() -> list[dict]:
    """The motion look catalogue (R-6.1): config/defaults/looks/motion/*.json and a profile's own, each {name,
    display, status}. Empty until Phase 6 builds the first look."""
    names = set()
    for d in [CONFIG_DIR] + list(current_context().profile_dirs()):
        folder = Path(d) / "looks" / "motion"
        if folder.is_dir():
            names |= {p.name for p in folder.glob("*.json")}
    out = []
    for n in sorted(names):
        lk = load_config(f"looks/motion/{n}")
        if isinstance(lk, dict) and isinstance(lk.get("name"), str):
            out.append(lk)
    return out


# --------------------------------------------------------------------------- inputs
def _content_type(paths) -> str | None:
    src = _read(paths.p("00_inputs/source.json"), {})
    if not isinstance(src, dict):
        return None
    rec = src.get("recipe") if isinstance(src.get("recipe"), dict) else {}
    t = src.get("content_type") or rec.get("type")
    return t if isinstance(t, str) and t else None


def _rate(paths) -> float | None:
    """Words per second of the clip's speech; None without at least two timed words (the pace is then unknown)."""
    doc = _read(paths.p("02_transcription/words.json"), {})
    words = [w for w in (doc.get("words") or []) if isinstance(w, dict) and str(w.get("word") or "").strip()
             and _num(w.get("start_ms")) and _num(w.get("end_ms"))] if isinstance(doc, dict) else []
    if len(words) < 2:
        return None
    ignore = int((looks.caption_catalog().get("auto") or {}).get("pause_ignore_ms", 1500))
    rate = looks.speech_rate(words, ignore)
    return rate if _num(rate) and rate > 0 else None


def _band(rate: float | None, cat: dict) -> str:
    b = cat["rate_bands"]
    if rate is None:
        return "medium"
    return "fast" if rate >= b["fast"] else "slow" if rate <= b["slow"] else "medium"


def _reference(paths, cat: dict) -> dict | None:
    """The client's measured reference style: energy from the median cuts per minute of its reference videos, plus the
    optional caption_density / text_weight of editing-style.json when they hold a known value. None = no references."""
    doc = _read(paths.client_db / "reference_analysis" / "reference-measurements.json", None)
    refs = doc.get("references") if isinstance(doc, dict) else None
    cpm = [r["cuts_per_minute"] for r in (refs if isinstance(refs, list) else [])
           if isinstance(r, dict) and _num(r.get("cuts_per_minute"))]
    if not cpm:
        return None
    e = cat["energy_from_cuts"]
    out = {"energy": min(1.0, max(0.0, (statistics.median(cpm) - e["floor_cpm"]) / e["span_cpm"]))}
    style = _read(paths.client_db / "reference_style" / "editing-style.json", {})
    for key in OPTIONAL_REF:
        v = style.get(key) if isinstance(style, dict) else None
        if isinstance(v, str) and v in LEVELS:
            out[key] = v
    return out


def _ref_match(traits: dict, ref: dict | None, cat: dict) -> float:
    if ref is None:
        return float(cat["neutral"])
    e = traits.get("energy")
    parts = [1 - abs((float(e) if _num(e) else float(cat["neutral"])) - ref["energy"])]
    m = cat["match"]
    for key in OPTIONAL_REF:
        if key in ref and traits.get(key) in LEVELS:
            d = abs(LEVELS[traits[key]] - LEVELS[ref[key]])
            parts.append(m["same"] if d == 0 else m["next"] if d == 1 else m["far"])
    return sum(parts) / len(parts)


def _lang(paths, lang: str | None, cat: dict) -> str:
    if not lang:
        try:
            from . import settings
            lang = str(settings.load(paths.root).get("language") or "ar")
        except Exception:  # noqa: BLE001  unreadable settings: the default language
            lang = "ar"
    lang = str(lang).strip().lower()
    return lang if lang in (cat.get("reason") or {}) else "ar"


def _sensitive(ctype: str | None) -> bool:
    """Medical content, or a client whose profile reviews religious content: no playful look. A profile that cannot be
    read counts as sensitive (the safe side)."""
    if ctype == "medical_claim":
        return True
    try:
        from . import review_domains
        return "religious" in review_domains.client_set(load_config("profile.json"))
    except Exception:  # noqa: BLE001  an unreadable or invalid profile: treated as sensitive
        return True


# --------------------------------------------------------------------------- history
def _when(v) -> datetime | None:
    """An ISO time as UTC; a time with no zone is the machine's local time."""
    if not isinstance(v, str):
        return None
    try:
        d = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d if d.tzinfo else d.astimezone()).astimezone(timezone.utc)


def _choice(folder: Path, kind: str) -> tuple[str | None, datetime | None]:
    """(look, when it was recorded) of one reel's `kind` choice; a choice without a valid `at` (older files) is dated
    by its project-status `created`."""
    ch = _read(folder / CHOICE_REL, {})
    entry = ch.get(kind) if isinstance(ch, dict) else None
    if not isinstance(entry, dict):
        return None, None
    look = entry.get("look") if isinstance(entry.get("look"), str) and entry.get("look") else None
    at = _when(entry.get("at"))
    if at is None:
        ps = _read(folder / "08_quality_control" / "project-status.json", {})
        at = _when(ps.get("created")) if isinstance(ps, dict) else None
    return look, at


def _reels(paths, kind: str, n: int) -> list[str]:
    """The `kind` looks of the client's other reels that recorded one, newest first by when each was recorded, up to
    n. Reels picked at Gate 0 share one `created` second, so the order is the order their looks were chosen. When
    this reel already recorded its own look (a re-recommend), only the choices recorded up to it count. Choices with no
    valid time, and this reel itself (any letter case), are left out."""
    base = paths.output / "projects"
    own = (getattr(paths, "video_id", None) or "").casefold()
    own_at = _choice(paths.project, kind)[1] if own else None
    rows = []
    if base.is_dir():
        for d in base.iterdir():
            if not d.is_dir() or d.name.casefold() == own:
                continue
            look, at = _choice(d, kind)
            if look is None or at is None or (own_at is not None and at > own_at):
                continue
            rows.append((at, d.name, look))
    rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
    return [r[2] for r in rows[:n]]


def history(paths, kind: str, n: int | None = None) -> list[str]:
    """The looks of the client's last reels that recorded one (newest first)."""
    return _reels(paths, kind, n or int(catalog()["recent"]["reels"]))


def _now() -> datetime:
    return datetime.now().astimezone()


def _stamp(paths) -> str:
    """Now, to the microsecond, nudged just past the newest look this client already recorded: on Windows one clock
    tick covers many calls, and the history must keep the order the looks were chosen in."""
    t = _now()
    base = paths.output / "projects"
    newest = None
    for d in (base.iterdir() if base.is_dir() else []):
        ch = _read(d / CHOICE_REL, {}) if d.is_dir() else {}
        for e in (ch.values() if isinstance(ch, dict) else []):
            at = _when(e.get("at")) if isinstance(e, dict) else None
            if at is not None and (newest is None or at > newest):
                newest = at
    if newest is not None and t.astimezone(timezone.utc) <= newest:
        t = (newest + timedelta(microseconds=1)).astimezone(t.tzinfo)
    return t.isoformat(timespec="microseconds")


def record_choice(paths, kind: str, look: str, source: str) -> Path:
    """Keep the look this reel uses (`source`: recommender | client | reel | editor; an editor swap feeds the learning
    loop). The other kind's entry is kept; a garbled file is replaced. Locked like every shared read-modify-write."""
    p = paths.p(CHOICE_REL)
    p.parent.mkdir(parents=True, exist_ok=True)
    with file_locked(p):
        d = _read(p, {})
        d = d if isinstance(d, dict) else {}
        d[kind] = {"look": look, "source": source, "at": _stamp(paths)}
        return write_json(p, d)


# --------------------------------------------------------------------------- recommend
def recommend(paths, kind: str = "caption", stills: bool = True, override=None, lang: str | None = None) -> dict:
    """-> {kind, pick (None = no look: today's look stays), top [{look, display, score, fit, still}], reason (one plain
    line in the editor's language), source (recommender | client | reel | none), hand_pick (motion: the looks the
    editor may choose by hand), notes (lines for the editor), warnings (table gaps, still problems)}."""
    cat = catalog()
    words = cat["reason"][_lang(paths, lang, cat)]
    ctype = _content_type(paths)
    if kind == "motion":
        return _motion(paths, cat, words, ctype, override)
    return _caption(paths, cat, words, ctype, override, stills)


def _ranked(names: list, fit_row: dict | None, traits: dict, ref, delivery, cat: dict, penalty=None) -> list[dict]:
    w, order = cat["weights"], {n: i for i, n in enumerate(names)}
    out = []
    for n in names:
        v = (fit_row or {}).get(n)
        fit = float(v) if _num(v) else float(cat["neutral"])
        s = w["fit"] * fit + w["ref"] * _ref_match(traits.get(n) or {}, ref, cat) + w["delivery"] * delivery(n)
        s -= (penalty or {}).get(n, 0.0)
        out.append({"look": n, "score": round(s, 4), "fit": fit})
    return sorted(out, key=lambda r: (-round(r["score"], 6), -r["fit"], order[r["look"]]))


def _result(kind, pick, top, reason, source, hand=(), notes=(), warnings=()) -> dict:
    return {"kind": kind, "pick": pick, "top": list(top), "reason": reason, "source": source, "hand_pick": list(hand),
            "notes": list(notes), "warnings": list(warnings)}


def _axes(value, cc: dict) -> dict:
    """{grouping, presentation} a reel override or a client preference fixes (valid values only)."""
    out = {}
    if isinstance(value, dict):
        for axis, pool in (("grouping", cc["groupings"]), ("presentation", cc["presentations"])):
            v = value.get(axis)
            v = v.get("value") if isinstance(v, dict) and v.get("mode") == "fixed" else v
            if isinstance(v, str) and v in pool:
                out[axis] = v
    return out


def _caption(paths, cat, words, ctype, override, stills) -> dict:
    c, cc = cat["caption"], looks.caption_catalog()
    warnings = problems(cat)
    display = lambda n: (c.get("display") or {}).get(n, n)
    notes = []
    if override is None:
        ed = _read(paths.p("01_analysis/edit-decisions.json"), {})
        override = ((ed.get("global") or {}).get("caption_look") if isinstance(ed, dict) else None) or None
    if isinstance(override, str) and override:
        try:
            look = looks.resolve(override=override, style={})["look"]
        except Exception:  # noqa: BLE001  an unknown reel override name: scored as usual below
            look = None
        if look:
            return _fixed_caption(paths, look, display(look), words["fixed_reel"], "reel", stills, warnings)
        notes.append(words["override_unknown"].format(look=override))
    reel_axes = _axes(override, cc) if isinstance(override, dict) else {}
    for axis in ("grouping", "presentation"):
        if isinstance(override, dict) and axis in override and axis not in reel_axes:
            notes.append(words["override_unknown"].format(look=override[axis]))
    style = load_config("style.json")
    prefs = style.get("captions") if isinstance(style.get("captions"), dict) else {}
    client_axes = _axes(prefs, cc)
    fixed = dict(client_axes, **reel_axes)
    if len(fixed) == 2:
        look = looks.combine(fixed["grouping"], fixed["presentation"], "colour", cc)["look"]
        src = "reel" if reel_axes else "client"
        return _fixed_caption(paths, look, display(look), words["fixed_reel" if reel_axes else "fixed_client"], src,
                              stills, warnings)
    order = [n for n in (c.get("order") or []) if n in cc["looks"]]
    order += sorted(n for n in cc["looks"] if n not in order)            # a client's own look: scored, at the end
    names = [n for n in order if all(cc["looks"][n][a] == v for a, v in fixed.items())]
    band = _band(_rate(paths), cat)
    fit_rows = c.get("fit") or {}
    known = ctype if ctype in fit_rows else None
    table = c.get("delivery") or {}
    unknown = sorted({cc["looks"][n]["grouping"] for n in names} - set(table))
    if unknown:
        warnings.append(f"caption delivery misses groupings {unknown}: scored neutral")

    def delivery(n):
        v = (table.get(cc["looks"][n]["grouping"]) or {}).get(band)
        return float(v) if _num(v) else float(cat["neutral"])

    ranked = _ranked(names, fit_rows.get(known) if known else None, c.get("traits") or {}, _reference(paths, cat),
                     delivery, cat)
    top = [dict(r, display=display(r["look"]), still=None) for r in ranked[:3]]
    pick = top[0]["look"]
    tname = words["types"].get(known) if known else None
    tmpl = words["caption_type"] if tname else words["caption_rate"]
    reason = tmpl.format(look=display(pick), type=tname or "", rate=words["rates"][band])
    if stills:
        warnings += _stills(paths, top)
    return _result("caption", pick, top, reason, "recommender", notes=notes, warnings=warnings)


def _fixed_caption(paths, look, disp, tmpl, source, stills, warnings) -> dict:
    top = [{"look": look, "display": disp, "score": None, "fit": None, "still": None}]
    if stills:
        warnings = list(warnings) + _stills(paths, top)
    return _result("caption", look, top, tmpl.format(look=disp), source, warnings=warnings)


def _stills(paths, top: list) -> list[str]:
    """One gallery still per listed caption look (08_quality_control/previews/caption-looks, never 03_broll; the
    editor's gallery sheet is left as it is). -> the gallery's warnings."""
    from . import looks_captions
    res = looks_captions.render(paths, looks_=[t["look"] for t in top], sheet=False)
    by = {lk["name"]: lk["png"] for lk in res.get("looks") or []}
    for t in top:
        t["still"] = by.get(t["look"])
    return list(res.get("warnings") or [])


def _motion(paths, cat, words, ctype, override) -> dict:
    m = cat["motion"]
    catalogue = {lk["name"]: lk for lk in motion_looks()}
    disp = lambda n: (catalogue.get(n) or {}).get("display") or n
    traits = m.get("traits") or {}
    playful = lambda n: bool((traits.get(n) or {}).get("playful"))
    sensitive = _sensitive(ctype)
    ready = [n for n, lk in catalogue.items() if lk.get("status") in ("preview_gate", "accepted")]
    hand = [n for n in ready if not (sensitive and playful(n))]        # never offered where it would be refused
    notes, warnings = [], []
    if override is None:
        ed = _read(paths.p("01_analysis/edit-decisions.json"), {})
        override = ((ed.get("global") or {}).get("motion_look") if isinstance(ed, dict) else None) or None
    if isinstance(override, str) and override:
        if override in hand:
            return _result("motion", override, [{"look": override, "display": disp(override), "score": None,
                                                 "fit": None, "still": None}],
                           words["fixed_reel"].format(look=disp(override)), "reel", hand)
        notes.append(words["override_refused" if override in ready else "override_unknown"].format(look=disp(override)))
    order = [n for n in (m.get("order") or []) if n in catalogue]
    missing = sorted(n for n, lk in catalogue.items() if lk.get("status") == "accepted" and n not in order)
    if missing:
        warnings.append(f"motion looks {missing} are accepted but not in recommender.json motion.order: ranked last")
        order += missing
    fit_rows = m.get("fit") or {}
    known = ctype if ctype in fit_rows else None
    row = fit_rows.get(known) if known else None
    fit_of = lambda n: float(row[n]) if row and _num(row.get(n)) else float(cat["neutral"])
    min_fit = float(cat["variety"]["min_fit"])
    names = [n for n in order if catalogue[n].get("status") == "accepted" and not (sensitive and playful(n))
             and fit_of(n) >= min_fit]
    if not names:
        return _result("motion", None, [], words["no_motion"], "none", hand, notes, warnings)
    rc = cat["recent"]
    past = _reels(paths, "motion", int(rc["reels"]))
    penalty: dict = {}
    for age, lk in enumerate(past):
        penalty[lk] = penalty.get(lk, 0.0) + float(rc["weight"]) * float(rc["decay"]) ** age
    ranked = _ranked(names, row, traits, _reference(paths, cat), lambda n: float(cat["neutral"]), cat, penalty)
    variety = len(past) >= 2 and past[0] == past[1] == ranked[0]["look"]
    if variety:
        ranked = ranked[1:]                     # the hard variety rule: never three in a row
        if not ranked:
            return _result("motion", None, [], words["no_motion_variety"], "none", hand, notes, warnings)
    top = [dict(r, display=disp(r["look"]), still=None) for r in ranked[:3]]
    pick = top[0]["look"]
    tname = words["types"].get(known) if known else None
    key = ("motion_variety" if variety else "motion_type") if tname else \
        ("motion_plain_variety" if variety else "motion_plain")
    return _result("motion", pick, top, words[key].format(look=disp(pick), type=tname or ""), "recommender", hand,
                   notes, warnings)
