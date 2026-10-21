# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""No-questions autopilot (3.0 T4.7): the plan approval a standing `approval: auto` delegates, `reel auto-approve`.

It is recorded DISTINCTLY from the editor's own approval: 01_analysis/plan-approval.json gets `by: "auto"` (never
"editor" or "delegated"), `delegation` (the preference and the file or plugin option it came from) and `not_covered`
(the medical / religious lines this approval does NOT cover: they stay on output/NEEDS-YOU.md for the editor). The
build gate (`require_plan_approval`) accepts it like any approval of the current plan; a re-plan invalidates it.
Refused, nothing written, unless the MERGED preferences for this client (`reel settings --root <client>`: its own
file, else the machine-wide file, else the plugin option, the same layers a `--by delegated` note names) say
`approval: auto`, or when the last `reel plan` did not compile (a failed re-plan leaves the older timeline on disk).
For a medical or religious client a missing, stale or damaged review of this plan is itself `not_covered`. Picking
podcast reels is never delegated here (`reels-select`, an editorial choice).
"""
from __future__ import annotations

from .common import Context, Paths, now_iso, read_json, set_status, use_context, write_json

APPROVAL_REL = "01_analysis/plan-approval.json"


def _pending(paths: Paths, events: list | None) -> list[dict]:
    """The lines an automatic approval never covers: for a client review_flags.held() holds (a medical or religious
    client, or any client whose review key has religious) whose review of THIS plan is missing, stale or damaged, the
    whole review (`event_id` None); the current review's rows that are not `ok`; then the graphics with
    approval_required (religious when held as religious)."""
    from . import review_flags
    out, seen = [], set()
    try:
        doc = review_flags.load(paths)
    except Exception:  # noqa: BLE001 — an unusable review covers nothing
        doc = None
    hold, _checks = review_flags.held()
    if doc is None and hold:
        out.append({"event_id": None, "kind": hold, "review": "missing or not current"})
    for it in (doc or {}).get("items", []):
        if it.get("verdict") != "ok" and (it["event_id"], it["flag"]) not in seen:
            seen.add((it["event_id"], it["flag"]))
            out.append({"event_id": it["event_id"], "kind": it["flag"]})
    flagged = {e for e, _ in seen}
    kind = "religious" if hold == "religious" else "medical"
    for e in events or []:
        if isinstance(e, dict) and e.get("approval_required") and e.get("event_id") not in flagged:
            out.append({"event_id": str(e["event_id"]), "kind": kind})
    return out


def approve(paths: Paths, note: str | None = None) -> dict:
    """Record the standing approval of the current plan (`by: "auto"`), or return {"refused", "how"} with nothing
    written."""
    from . import settings as S
    from .motion_config import is_motion
    from .plan import APPROVAL_FORMAT
    st = S.load(paths.root)
    where = (st.get("_where") or {}).get("approval") or "default"
    if st.get("approval") != "auto":
        return {"refused": f"this client's approval preference is {st.get('approval')!r} (from {where}), not auto: "
                           "the editor approves each plan",
                "how": "Show the editor the plan; after they approve run `reel approve-plan --by editor`. Only the "
                       "editor switches this client to approval: auto (/whynot-cut:preferences)."}
    with use_context(Context(paths.root)):
        if is_motion(paths):
            from .motion_plan import fingerprint
            val = read_json(paths.p("01_analysis/motion-validation.json"))
            if not paths.p("01_analysis/motion-plan.json").exists() or not val:
                return {"refused": "no compiled motion plan yet", "how": "Run `reel motion-plan` first."}
            if not val.get("ok"):
                return {"refused": "the motion plan has errors (01_analysis/motion-plan.md)",
                        "how": "Fix them and run `reel motion-plan` again; then `reel auto-approve`."}
            fp = fingerprint(paths)
            if val.get("fingerprint") != fp:
                return {"refused": "the motion plan is stale (script, words, audio, brand or the names shown changed)",
                        "how": "Run `reel motion-plan` again; then `reel auto-approve`."}
            from .motion_plan import plan_edited
            edited = plan_edited(paths)             # review 91b6b44 P2-1: never approve a plan edited by hand
            if edited:
                return {"refused": edited["why"], "how": "Run `reel motion-plan` again; then `reel auto-approve`.",
                        "editor_message": edited["editor_message"]}
            events, kind = None, "motion"
        else:
            from .plan import plan_fingerprint
            spec_f = paths.p("01_analysis/timeline-spec.json")
            if not spec_f.exists():
                return {"refused": "no compiled plan yet", "how": "Run `reel plan` first; then `reel auto-approve`."}
            val = read_json(paths.p("01_analysis/plan-validation.json"))
            if not isinstance(val, dict) or val.get("ok") is not True:   # a failed re-plan keeps the OLD spec
                return {"refused": "the last `reel plan` did not compile (01_analysis/plan-validation.json), so the "
                                   "timeline on disk is an older plan",
                        "how": "Fix the errors in 01_analysis/plan-validation.json and run `reel plan` again; then "
                               "`reel auto-approve`."}
            fp = plan_fingerprint(paths, checked=True)
            events, kind = (read_json(spec_f, {}) or {}).get("events") or [], None
        rec = {"approved": True, "by": "auto", "note": note or f"standing preference approval: auto from {where}",
               "at": now_iso(), "plan_fingerprint": fp, "format": APPROVAL_FORMAT,
               "delegation": {"preference": "approval", "value": "auto", "from": where},
               "not_covered": _pending(paths, events)}
        if kind:
            rec["kind"] = kind
        write_json(paths.p(APPROVAL_REL), rec)
    left = len(rec["not_covered"])
    set_status(paths, "EDIT_PLAN_READY", f"plan approved automatically (approval: auto from {where})"
               + (f"; {left} medical/religious line(s) stay with the editor" if left else ""), "plan_approval")
    return rec
