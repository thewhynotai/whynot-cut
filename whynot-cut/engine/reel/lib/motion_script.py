"""motion-script.json (authored by the motion-director): field rules and the truth checks for on-screen text (spec §3.4,
§3.5, §4.1). Pure functions; the compiler (motion_plan) applies them with the transcript, the sheet and the recipe.

Text sources: `speech` fields must be the speaker's own words, in order, nothing added (fillers may be dropped);
`editorial` fields are Claude's lines, shown at Gate 1 as such; `either` fields say which with a sibling
`<field>_source` ("speech" by default; comparison uses one scene-level `text_source`).
"""
from __future__ import annotations

import re

from .plan import norm

SCENE_TYPES: dict[str, dict] = {
    "kinetic_quote": {"required": ["text"], "speech": ["text"], "editorial": [], "either": []},
    "title_card": {"required": ["title"], "speech": [], "editorial": ["eyebrow", "subtitle"], "either": ["title"]},
    "stat_counter": {"required": ["value", "evidence"], "speech": [], "editorial": [], "either": ["label"]},
    "icon_point": {"required": ["icon", "text"], "speech": [], "editorial": [], "either": ["text"]},
    "list_steps": {"required": ["items"], "speech": ["items.text"], "editorial": ["title"], "either": []},
    "comparison": {"required": ["first", "second"], "speech": [], "editorial": [],
                   "either": ["first.label", "first.points", "second.label", "second.points", "verdict"]},
    "timeline": {"required": ["points"], "speech": ["points.label"], "editorial": ["points.when"], "either": []},
    "quote_card": {"required": ["text", "attribution"], "speech": ["text"], "editorial": [], "either": []},
    "context_card": {"required": ["text"], "speech": [], "editorial": ["text"], "either": []},
    "person_card": {"required": ["who"], "speech": [], "editorial": [], "either": []},
    "illustration_scene": {"required": ["illustration"], "speech": [], "editorial": [], "either": ["text"]},
    "outro": {"required": ["cta"], "speech": [], "editorial": ["cta"], "either": []},
}
REPLAYS_SPEECH = {"kinetic_quote", "quote_card"}     # shown word by word as spoken: the drop-ratio limit applies
QUOTES = "«»\"“”„"
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_RUN = re.compile(r"\d+(?:[.,٬٫]\d+)*")


def load_script(paths) -> dict:
    from .common import read_json
    s = read_json(paths.p("01_analysis/motion-script.json"))
    if not s:
        raise SystemExit("01_analysis/motion-script.json missing — the motion-director authors it (see motion-craft "
                         "references/motion-scenes.md), then run `reel motion-plan` again")
    return s


def source_of(scene: dict, field: str) -> str:
    """'speech' | 'editorial' for an `either` field."""
    key = "text_source" if scene.get("type") == "comparison" else f"{field.split('.')[0]}_source"
    return scene.get(key) or "speech"


def check_fields(script: dict) -> list[str]:
    errs = []
    scenes = script.get("scenes") or []
    if not scenes:
        return ["motion-script.json has no scenes"]
    beats = {b.get("id") for b in script.get("beats") or []}
    seen = set()
    for k, sc in enumerate(scenes):
        sid, typ = str(sc.get("id", "")), sc.get("type")
        where = sid or f"scene #{k + 1}"
        if not re.fullmatch(r"S\d+", sid):
            errs.append(f"{where}: id must look like S01")
        elif sid in seen:
            errs.append(f"{where}: duplicate scene id")
        seen.add(sid)
        spec = SCENE_TYPES.get(typ)
        if not spec:
            errs.append(f"{where}: unknown scene type {typ!r} (known: {', '.join(SCENE_TYPES)})")
            continue
        missing = [f for f in spec["required"] if sc.get(f) in (None, "", [], {})]
        if missing:
            errs.append(f"{where} ({typ}): missing {', '.join(missing)}")
        at = sc.get("at")
        if not at:
            errs.append(f"{where}: `at` is required (the first words spoken when the scene starts, or @start/@end)")
        elif k == 0 and at != "@start":
            errs.append(f"{where}: the first scene starts the video: \"at\": \"@start\"")
        elif at == "@end" and (k != len(scenes) - 1 or typ != "outro"):
            errs.append(f"{where}: \"@end\" is only for a last outro scene")
        elif at == "@start" and k != 0:
            errs.append(f"{where}: \"@start\" is only for the first scene")
        for lst in ("items", "points"):
            if typ in ("list_steps", "timeline") and lst in spec["required"]:
                vals = sc.get(lst) or []
                if vals and not 2 <= len(vals) <= 5:
                    errs.append(f"{where}: {len(vals)} {lst} (2-5)")
                for j, it in enumerate(vals if 2 <= len(vals) <= 5 else []):
                    need = ["text", "at"] if lst == "items" else ["label", "at"]
                    if any(not it.get(f) for f in need):
                        errs.append(f"{where}: {lst}[{j}] needs {' and '.join(need)}")
        if typ == "comparison":
            for side in ("first", "second"):
                pts = (sc.get(side) or {}).get("points") or []
                if len(pts) > 3:
                    errs.append(f"{where}: {side} has {len(pts)} points (max 3)")
        for f in spec["either"]:
            src = sc.get("text_source" if typ == "comparison" else f"{f.split('.')[0]}_source")
            if src not in (None, "speech", "editorial"):
                errs.append(f"{where}: {f.split('.')[0]}_source must be speech or editorial")
        if sc.get("beat") and beats and sc["beat"] not in beats:
            errs.append(f"{where}: beat {sc['beat']!r} is not in beats")
    return errs


def _tokens(words: list[str]) -> list[tuple[str, int]]:
    out = []
    for i, w in enumerate(words):
        out += [(t, i) for t in norm(w).split()]
    return out


def match_subsequence(shown: str, spoken: list[str], max_drop: float) -> dict:
    """Shown text against the spoken words: in order, nothing added. idx = indexes of the spoken words used;
    dropped_ratio = share of the spoken words not shown."""
    toks, j = _tokens(spoken), 0
    idx, added = [], []
    for t in norm(shown).split():
        k = j
        while k < len(toks) and toks[k][0] != t:
            k += 1
        if k == len(toks):
            added.append(t)
            continue
        if toks[k][1] not in idx:
            idx.append(toks[k][1])
        j = k + 1
    dropped = 1 - len(idx) / len(spoken) if spoken else 1.0
    return {"ok": not added and bool(idx) and dropped <= max_drop + 1e-9, "idx": idx, "dropped_ratio": dropped,
            "added": added}


def digits_of(s: str) -> str:
    return "".join(ch for ch in str(s).translate(_DIGITS) if ch.isdigit())


def digit_runs(s: str) -> set[str]:
    return {re.sub(r"[.,٬٫]", "", m) for m in _RUN.findall(str(s).translate(_DIGITS))}


def check_number(value: str, evidence: str) -> bool:
    runs = digit_runs(value)
    return bool(runs) and runs <= digit_runs(evidence)


def check_editorial(text: str, window_digits: set[str]) -> list[str]:
    probs = []
    if any(q in str(text) for q in QUOTES):
        probs.append("quotation marks in an editorial line (quotes are only the speaker's words)")
    extra = sorted(digit_runs(text) - set(window_digits))
    if extra:
        probs.append(f"number(s) {', '.join(extra)} not said in this window")
    return probs


def person_name(value: str) -> str:
    return re.split(r"\s+[—–-]\s+", str(value or ""))[0].strip()


def fill_placeholders(text: str, sheet: dict) -> tuple[str, list[str]]:
    vals = {"host": person_name(sheet.get("host")), "guest": person_name(sheet.get("guest")),
            "show": str(sheet.get("show") or "").strip()}
    missing = []

    def sub(m):
        k = m.group(1)
        if not vals.get(k):
            missing.append(k)
            return m.group(0)
        return vals[k]
    return re.sub(r"\{(host|guest|show)\}", sub, str(text or "")), missing
