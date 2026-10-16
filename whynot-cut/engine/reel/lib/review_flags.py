# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Review flags (3.0 Phase 4 T4.13, `reel review-flags`): the medical/religious review as data the panel can show.

The medical-reviewer is read-only and reports to the lead in chat; the lead puts its table through
`reel review-flags --from <file|->`, and the engine writes `<item>/review-flags.json`
(docs/adobe/eng-data-contract.md §7.6). Each line is keyed by the plan's event id (a clip: `event_id` in
01_analysis/timeline-spec.json; a motion video: the scene id in 01_analysis/motion-plan.json).

    {"schema": 1, "plan_kind": "timeline" | "motion", "plan_fingerprint", "domain": "medical" | "religious" | "general",
     "written_at", "by", "checked", "lines_total",
     "items": [{"event_id", "flag": "medical" | "religious",
                "verdict": "needs-doctor-approval" | "reword-to-match" | "remove",
                "text", "start_s", "end_s", "reason", "carried"?}],
     "ok": [{"event_id", "text"}]}

`text`, `start_s` and `end_s` come from the compiled plan, never from the reviewer: the panel shows the words and the span
the plan really has. The file stores EVERY reviewed line: `items` are the flagged ones, `ok` the lines reviewed and found
fine (one row per line, a line with a flag is not repeated there). `lines_total` is the number of plan lines with
on-screen text (the M of "N of M checked"); `checked` is COMPUTED = the covered lines, so it equals `lines_total` on every
successful write (a `checked` in the table is ignored). `domain` is the client's profile domain the review was done for.
The file is replaced whole with an atomic write.

Rows: a row's flag must be one the client's domain checks (DOMAIN_FLAGS: medical and general clients `medical`, a
religious client `religious` and `medical`), and its id a plan line WITH on-screen text; anything else is refused.

Coverage: a write is refused (nothing written) unless EVERY plan line with on-screen text is covered. A line is covered
when the new table lists it (ok or a flag), or the previous usable file, even a stale one, has it with the SAME id and the
SAME text (a flagged row is carried with `"carried": true`, unless the table mentions that id with that flag; an ok row is
carried as ok). So a revise sends only the changed lines, and an edited, renumbered, split or merged line the table does
not list is refused by name ("G5, G6 have not been reviewed"). A flag is never lost by moving, and where its words went
is never guessed (a split, merge, extension or invisible character all look new). A "new or changed" line is one no
earlier row has with the same id AND the same words. For each earlier flag (id, F):
- not on its line any more (its words changed and the table re-reviews them, or its id is reused or gone): EVERY new or
  changed line must be listed for F, else "G6 is new or changed since G2's medical flag: review G6 for medical" (with the
  hint "G2's flagged wording (medical) is now on G3" where the exact words are);
- still on its line (carried, or re-reviewed in place: same id, same words, listed for F): every new or changed line
  holding an exact copy of its words must be listed for F;
- its words changed and the table does not list (id, F): refused ("its on-screen wording changed").
A line whose words were all removed counts as gone (its flag is dropped; no review of an empty line is asked). The
result and the CLI output (not the file) report `dropped` (earlier flagged rows whose line is gone and whose words were
not re-reviewed for that flag anywhere: harmless, every current line is covered) and `cleared` (`from_event_id` added:
earlier flagged rows the table now marks `ok` for the same flag on the same words, under the same id or a new id the
words moved to, so the editor is told; a flag whose words were re-flagged elsewhere is in neither). A previous file that
exists but cannot be used (bad JSON, another schema or plan kind, any damaged row, or a review done for another profile
domain or none) carries nothing, so the table must list every line. Carrying matches id + words only, not the span or
the speaker's evidence: accepted, low risk (the reviewer checks each line against the full transcript.json).

`load()` returns None for a missing or unreadable file, for a file whose fingerprint is not the current plan's (a re-plan
means the old flags are never served as current), for one done for another domain, and for one inconsistent with the
plan (a damaged row, a row for an id without words or with other words than the plan's, `checked`/`lines_total` not the
plan's count, a plan line in neither `items` nor `ok`). That catches a wiped or careless edit, not a deliberate one: a
flag moved into `ok` by hand cannot be detected without a signature. Nothing here reads the reviewer's own text for
anything but the reason. Stdlib plus the engine's own helpers.
"""
from __future__ import annotations

from pathlib import Path

from .common import Paths, now_iso, read_json, write_json
from .errors import Guidance

SCHEMA = 1
FILE = "review-flags.json"
# The flags a review may use, per client profile domain (common.content_domain), as the skills run it: health claims are
# checked for every client (medical-accuracy: `general` runs the wording/qualifier/uncertain-word checks; the
# medical-reviewer runs on every clip and motion video, whatever the domain), the religious checks only for a `religious`
# client. A new domain (Addendum M: business, AI) is one new entry here; a new flag needs nothing else either.
DOMAIN_FLAGS = {
    "medical": ("medical",),
    "religious": ("religious", "medical"),
    "general": ("medical",),
}


def _all_flags() -> tuple:
    """Every flag some domain uses (read at call time, so a new DOMAIN_FLAGS entry is all a new flag needs)."""
    return tuple(dict.fromkeys(f for fl in DOMAIN_FLAGS.values() for f in fl))


def _allowed(domain: str) -> tuple:
    return DOMAIN_FLAGS.get(domain, DOMAIN_FLAGS["general"])


VERDICTS = ("ok", "needs-doctor-approval", "reword-to-match", "remove")
TIMELINE_SPEC = "01_analysis/timeline-spec.json"
MOTION_PLAN = "01_analysis/motion-plan.json"
SHOWN_IDS = 12                       # ids named in the refusal's `how`
MAX_PROBLEMS = 8
MAX_REASON = 1024


def path(paths: Paths) -> Path:
    return paths.p(FILE)


def _kind(paths: Paths) -> str:
    from .motion_config import is_motion
    return "motion" if is_motion(paths) else "timeline"


def _text(strings) -> str:
    """The on-screen strings of one graphic or scene as one line: whitespace folded, a repeat of the line before it
    dropped, ` / ` between lines (the way edit-plan.md and motion-plan.md show them). Order stays as authored: Arabic
    is never re-ordered here."""
    out: list[str] = []
    for s in strings:
        s = " ".join(str(s).split())
        if s and (not out or out[-1] != s):
            out.append(s)
    return " / ".join(out)


def _strings(params) -> list:
    """The strings a graphic puts on screen: plan.onscreen_strings, plus a number (a stat card's value, 70 or 2.5) as its
    text, so 70 -> 95 is a change of wording."""
    from .plan import ONSCREEN_KEYS
    if isinstance(params, bool):
        return []
    if isinstance(params, (int, float)):
        return [str(params)]
    if isinstance(params, str):
        return [params]
    out: list = []
    if isinstance(params, list):
        for x in params:
            out += _strings(x)
    elif isinstance(params, dict):
        for k, v in params.items():
            if k in ONSCREEN_KEYS:
                out += _strings(v)
    return out


def _seconds(value) -> float:
    return round(float(value), 3)


def _timeline_index(paths: Paths) -> dict:
    """event id -> {text, start_s, end_s} from the compiled timeline spec (times on the result timeline)."""
    from .stamps import read_compiled
    spec = read_compiled(paths.p(TIMELINE_SPEC))
    if not isinstance(spec, dict):
        raise Guidance("there is no compiled plan for this video yet, so there is nothing to attach the review to",
                       "Run `reel plan` first (the story-editor's edit-decisions.json compiles into "
                       "01_analysis/timeline-spec.json), then send the review again", where=str(paths.p(TIMELINE_SPEC)))
    index: dict = {}
    for e in spec.get("events") or []:
        eid = e.get("event_id") if isinstance(e, dict) else None
        if isinstance(eid, str) and eid and eid not in index:
            index[eid] = {"text": _text(_strings(e.get("params"))),
                          "start_s": _seconds((e.get("start_ms") or 0) / 1000),
                          "end_s": _seconds((e.get("end_ms") or 0) / 1000)}
    return index


def _motion_index(paths: Paths) -> dict:
    """scene id -> {text, start_s, end_s} from the compiled motion plan (the scene's text and counter elements)."""
    from .stamps import read_compiled
    plan = read_compiled(paths.p(MOTION_PLAN))
    if not isinstance(plan, dict):
        raise Guidance("there is no compiled motion plan for this video yet, so there is nothing to attach the review to",
                       "Run `reel motion-plan` first, then send the review again", where=str(paths.p(MOTION_PLAN)))
    try:
        fps = float(plan.get("fps"))
    except (TypeError, ValueError):
        fps = 0.0
    if fps <= 0:
        raise Guidance("the compiled motion plan has no frame rate", "Run `reel motion-plan` again, then send the "
                       "review again", where=str(paths.p(MOTION_PLAN)))
    index: dict = {}
    for s in plan.get("scenes") or []:
        sid = s.get("id") if isinstance(s, dict) else None
        if isinstance(sid, str) and sid and sid not in index:
            texts = [el.get("text") for el in s.get("elements") or []
                     if isinstance(el, dict) and el.get("kind") in ("text", "counter") and el.get("text")]
            index[sid] = {"text": _text(texts), "start_s": _seconds((s.get("start_frame") or 0) / fps),
                          "end_s": _seconds((s.get("end_frame") or 0) / fps)}
    return index


def _fingerprint(paths: Paths, kind: str) -> str:
    """The current plan's fingerprint: `plan.plan_fingerprint` (a clip) or `motion_plan.fingerprint` (a motion video)."""
    if kind == "motion":
        from .motion_plan import fingerprint
        if not paths.p(MOTION_PLAN).exists():
            raise FileNotFoundError(paths.p(MOTION_PLAN))
        return fingerprint(paths)
    from .plan import plan_fingerprint
    return plan_fingerprint(paths)


def _current(paths: Paths):
    """(kind, index, fingerprint) of the compiled plan the review is for, or a Guidance when there is none or it is
    older than its inputs."""
    kind = _kind(paths)
    index = _motion_index(paths) if kind == "motion" else _timeline_index(paths)
    fp = _fingerprint(paths, kind)
    if kind == "motion":
        from .stamps import read_compiled
        built = (read_compiled(paths.p(MOTION_PLAN)) or {}).get("fingerprint")
        if built != fp:           # the script, words, pauses or brand changed after the plan compiled: its scenes are old
            raise Guidance("the compiled motion plan is older than the script, words, audio or brand it was built from, "
                           "so the review would be attached to scenes that may no longer exist",
                           "Run `reel motion-plan` again, review the new plan, then send the review again",
                           where=str(paths.p(MOTION_PLAN)))
    return kind, index, fp


def _clean(findings, ids: dict, domain: str) -> list:
    """The reviewer's rows, validated; every problem named, nothing half-accepted. A row's flag must be one the client's
    domain checks (DOMAIN_FLAGS), and its id a plan line WITH on-screen text. A `checked` in the table is accepted and
    ignored: the engine computes it from what is covered."""
    allowed = _allowed(domain)
    how = (f'Send `{{"items": [{{"event_id": "<plan id>", "flag": one of {", ".join(allowed)} (this client\'s domain: '
           f'{domain}), "verdict": "ok", "needs-doctor-approval", "reword-to-match" or "remove", "reason": "<why>"}}]}}`, '
           'one row for every line with on-screen text the reviewer checked (the ok ones too)')
    if not isinstance(findings, dict) or not isinstance(findings.get("items"), list):
        raise Guidance("the review table is not a JSON object with an `items` list", how)
    problems: list[str] = []
    rows: list[dict] = []
    seen: set = set()
    for n, raw in enumerate(findings["items"], 1):
        if not isinstance(raw, dict):
            problems.append(f"row {n} is not an object")
            continue
        eid, flag, verdict, reason = raw.get("event_id"), raw.get("flag"), raw.get("verdict"), raw.get("reason", "")
        bad = []
        if not isinstance(eid, str) or not eid.strip():
            bad.append("`event_id` is missing")
        if flag not in _all_flags():
            bad.append(f"`flag` {flag!r} is not one of {', '.join(allowed)}")
        elif flag not in allowed:
            bad.append(f"`flag` {flag!r} is not checked for a {domain} client (use {', '.join(allowed)})")
        if verdict not in VERDICTS:
            bad.append(f"`verdict` {verdict!r} is not one of {', '.join(VERDICTS)}")
        if reason is None:
            reason = ""
        if not isinstance(reason, str):
            bad.append("`reason` is not text")
        elif len(reason) > MAX_REASON:
            bad.append(f"`reason` is {len(reason)} characters; the most is {MAX_REASON} (shorten it)")
        if bad:
            problems.append(f"row {n} ({eid if isinstance(eid, str) else '?'}): " + "; ".join(bad))
            continue
        eid = eid.strip()
        if (eid, flag) in seen:
            problems.append(f"row {n}: {eid} is listed twice for the {flag} check")
            continue
        seen.add((eid, flag))
        rows.append({"event_id": eid, "flag": flag, "verdict": verdict, "reason": reason})
    unknown = sorted({r["event_id"] for r in rows if r["event_id"] not in ids})
    if unknown and not problems:
        known = ", ".join(list(ids)[:SHOWN_IDS]) + (", …" if len(ids) > SHOWN_IDS else "")
        raise Guidance(f"not in the compiled plan: {', '.join(unknown)}",
                       f"Key each line by the plan's own id (a clip: the graphic's event id; a motion video: the scene "
                       f"id). This plan has: {known or 'none'}. Fix the table and send the review again")
    blank = sorted({r["event_id"] for r in rows if r["event_id"] in ids and not ids[r["event_id"]]["text"]})
    if blank and not problems:
        raise Guidance(f"{', '.join(blank)} {'has' if len(blank) == 1 else 'have'} no on-screen text, so there is "
                       "nothing to review there", f"Leave {'it' if len(blank) == 1 else 'them'} out of the table (only "
                       "lines with words on screen are reviewed), then send the review again")
    if problems:
        shown = problems[:MAX_PROBLEMS] + ([f"… and {len(problems) - MAX_PROBLEMS} more"]
                                           if len(problems) > MAX_PROBLEMS else [])
        raise Guidance("the review table has problems: " + " | ".join(shown), how)
    return rows


def _domain() -> str:
    """The client's profile domain (medical | religious | general) the review is done for."""
    from .common import content_domain
    return content_domain()


UNREADABLE = ("the earlier review file (review-flags.json) can't be read, so nothing could be carried forward: list "
              "every line once")


def _rows(doc: dict, *, need_ok: bool = False):
    """(flagged rows, ok rows) of a review document, or None when ANY row is damaged: an item that is not an object, has
    no text id, a bad flag or verdict (an item never has verdict `ok`), no text, a reason that is not text, or repeats an
    (id, flag); an ok row that is not an object with text id and text, repeats an id, or names a line that has a flag.
    `need_ok`: the `ok` list must be there (a file the engine wrote now); an older file without it is accepted."""
    if not isinstance(doc.get("items"), list) or not isinstance(doc.get("ok", None if need_ok else []), list):
        return None
    def bad_id(v) -> bool:                # the engine writes the plan's ids as they are: never empty, never padded
        return not isinstance(v, str) or not v or v != v.strip()

    flagged, ok, seen = [], [], set()
    for it in doc["items"]:
        if (not isinstance(it, dict) or bad_id(it.get("event_id")) or it.get("flag") not in _all_flags()
                or it.get("verdict") not in VERDICTS or it.get("verdict") == "ok" or not isinstance(it.get("text"), str)
                or not isinstance(it.get("reason", ""), str) or (it["event_id"], it["flag"]) in seen):
            return None
        seen.add((it["event_id"], it["flag"]))
        flagged.append(it)
    flagged_ids, ok_ids = {i for i, _ in seen}, set()
    for it in doc.get("ok", []):
        if (not isinstance(it, dict) or bad_id(it.get("event_id")) or not isinstance(it.get("text"), str)
                or it["event_id"] in ok_ids or it["event_id"] in flagged_ids):
            return None
        ok_ids.add(it["event_id"])
        ok.append(it)
    return flagged, ok


def _previous(paths: Paths, kind: str, domain: str):
    """(why it can't be used or None, flagged rows, ok rows) of the previous review file, stale or not. A missing file is
    usable and empty. A file that exists but cannot be used (bad JSON, another schema or plan kind, ANY damaged row, or a
    review done for another profile domain, or for none it names) carries nothing: it may have held flags, or its ok
    lines were never checked for this domain, so the new table must list every line."""
    f = path(paths)
    if not f.exists():
        return None, [], []
    try:
        old = read_json(f)
    except (OSError, ValueError):
        return UNREADABLE, [], []
    if (not isinstance(old, dict) or old.get("schema") != SCHEMA or old.get("plan_kind") != kind
            or not isinstance(old.get("items"), list) or not isinstance(old.get("ok", []), list)):
        return UNREADABLE, [], []
    rows = _rows(old)
    if rows is None:
        return UNREADABLE, [], []
    flagged, ok = rows
    if old.get("domain") != domain:
        was = old.get("domain")
        was = f"the {was} domain" if isinstance(was, str) and was else "no named domain"
        return (f"the earlier review (review-flags.json) was done for {was} and this client's profile domain is now "
                f"{domain}, so nothing could be carried forward: list every line once"), [], []
    return None, flagged, ok


def write(paths: Paths, findings: dict, *, by: str = "lead") -> dict:
    """Validate the reviewer's table against the compiled plan and write `<item>/review-flags.json`, replacing the
    whole file. Coverage model: every plan line with on-screen text must be COVERED, or nothing is written. A line is
    covered when the table lists it (ok or a flag), or the previous usable file has it, with the SAME id and SAME text,
    flagged (carried: `carried: true`) or ok. `checked` is computed (= the covered lines = `lines_total`); a `checked` in
    the table is ignored. Returns the document written plus `dropped` and `cleared` (see the module docstring). A
    Guidance (nothing written) for a malformed table, a flag the client's domain does not check, an id the plan does not
    have or that has no on-screen text, no compiled plan, any line left uncovered, or a new or changed line the table did
    not review FOR an earlier flag that left its line ("G6 is new or changed since G2's medical flag: review G6 for
    medical") or that holds an exact copy of a flag still on its line."""
    kind, index, fp = _current(paths)
    domain = _domain()
    rows = _clean(findings, index, domain)
    lines = [i for i, v in index.items() if v["text"]]
    unusable, old_flagged, old_ok = _previous(paths, kind, domain)

    def current(eid):                     # a plan line with words; an id whose words were all removed counts as gone
        v = index.get(eid)
        return v if v is not None and v["text"] else None

    mentioned = {(r["event_id"], r["flag"]) for r in rows}
    verdict_of = {(r["event_id"], r["flag"]): r["verdict"] for r in rows}
    items = []
    for r in rows:
        if r["verdict"] == "ok":
            continue                                    # a covered line, never a written flag
        src = index[r["event_id"]]                      # the plan's words and span; the reviewer's own are ignored
        items.append({"event_id": r["event_id"], "flag": r["flag"], "verdict": r["verdict"], "text": src["text"],
                      "start_s": src["start_s"], "end_s": src["end_s"], "reason": r["reason"]})
    carried, carried_keys = [], set()
    for it in old_flagged:
        now = current(it["event_id"])
        if now is not None and now["text"] == it["text"] and (it["event_id"], it["flag"]) not in mentioned:
            carried.append({"event_id": it["event_id"], "flag": it["flag"], "verdict": it["verdict"], "text": now["text"],
                            "start_s": now["start_s"], "end_s": now["end_s"], "reason": it.get("reason", "")[:MAX_REASON],
                            "carried": True})
            carried_keys.add((it["event_id"], it["flag"]))
    ok_carried = {o["event_id"] for o in old_ok if index.get(o["event_id"]) is not None
                  and index[o["event_id"]]["text"] == o["text"]}
    covered = {r["event_id"] for r in rows} | {c["event_id"] for c in carried} | ok_carried
    uncovered = [i for i in lines if i not in covered]
    # New or changed lines: no earlier row (flagged or ok) has the same id AND the same words. Where an earlier flag's
    # words went is never guessed (a split, merge, extension or an invisible character all look new): while a flag is
    # not carried, EVERY new or changed line must be reviewed for that flag.
    before = {(o["event_id"], o["text"]) for o in old_flagged + old_ok}
    fresh = [c for c in lines if (c, index[c]["text"]) not in before]
    problems, dropped, cleared = [], [], []
    for it in old_flagged:
        eid, flag = it["event_id"], it["flag"]
        now = current(eid)
        exact = [c for c in fresh if c != eid and it["text"] and index[c]["text"] == it["text"]]
        row = {"event_id": eid, "from_event_id": eid, "flag": flag, "verdict": it["verdict"], "text": it["text"]}
        in_place = now is not None and now["text"] == it["text"]     # carried, or re-reviewed for this flag in place
        if now is not None and (eid, flag) not in mentioned and not in_place:
            problems.append(f"{eid} ({flag}) was flagged in the earlier review and its on-screen wording changed since "
                            "then, so that sign-off no longer applies")
        elif in_place and (eid, flag) not in carried_keys and verdict_of.get((eid, flag)) == "ok":
            cleared.append(row)                           # the same words, now passed for the same flag: say so
        if not in_place:                                  # the flag left its line: its words may have gone elsewhere
            moved_ok = [c for c in exact if verdict_of.get((c, flag)) == "ok"]
            cleared += [dict(row, event_id=c) for c in moved_ok]       # its words, passed under a new id: say so too
            if now is None and not any((c, flag) in mentioned for c in exact):
                dropped.append({k: v for k, v in row.items() if k != "from_event_id"})   # gone, never re-reviewed
        # A flag still on its line (carried, or re-reviewed in place) holds every exact copy of its words elsewhere to
        # that flag; a flag that is not holds EVERY new or changed line to it.
        need = [c for c in (exact if in_place else fresh) if c != eid and (c, flag) not in mentioned]
        hint = [c for c in need if c in exact]
        rest = [c for c in need if c not in exact]
        if hint:
            ids = ", ".join(hint)
            problems.append(f"{eid}'s flagged wording ({flag}) is now on {ids}; review {ids} for {flag}")
        if rest:
            ids = ", ".join(rest)
            problems.append(f"{ids} {'is' if len(rest) == 1 else 'are'} new or changed since {eid}'s {flag} flag: "
                            f"review {ids} for {flag}")
    if uncovered:
        problems.append(f"{', '.join(uncovered)} {'has' if len(uncovered) == 1 else 'have'} not been reviewed: list "
                        f"{'it' if len(uncovered) == 1 else 'them'} (ok or a flag)")
        if unusable:
            problems.append(unusable)
    if problems:
        raise Guidance("; ".join(problems),
                       "Add those lines to the table (an `ok` row once the wording is fine, or a flag with its verdict), "
                       "then send it again. Nothing was written")
    flagged_ids = {i["event_id"] for i in items} | {c["event_id"] for c in carried}
    ok = [{"event_id": i, "text": index[i]["text"]} for i in lines if i not in flagged_ids]
    doc = {"schema": SCHEMA, "plan_kind": kind, "plan_fingerprint": fp, "domain": domain, "written_at": now_iso(),
           "by": str(by or "lead"), "checked": len(lines), "lines_total": len(lines), "items": items + carried, "ok": ok}
    write_json(path(paths), doc)
    return dict(doc, dropped=dropped, cleared=cleared)


def load(paths: Paths) -> dict | None:
    """The review file when it is readable, whole and belongs to the current plan; None when it is missing, unreadable,
    from another schema, its fingerprint is not the current plan's (the plan changed after the review: stale), it was
    done for another profile domain than the client's current one, or it is not consistent with the plan: any damaged
    row (the checks `write` applies to an earlier file), a flag the domain does not check, a row whose id is not a plan
    line with words or whose text is not that line's current words, no `ok` list, `checked` or `lines_total` not the
    plan's number of lines with text (an integer), or a plan line with text in neither `items` nor `ok`. These catch a
    wiped or carelessly edited file, not a deliberate one: a flag moved into `ok` by hand, with the right words, cannot
    be told from a real `ok` without a signature."""
    try:
        doc = read_json(path(paths))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        return None
    rows = _rows(doc, need_ok=True)
    if rows is None:
        return None
    try:
        kind, index, fp = _current(paths)
        domain = _domain()
        if doc.get("plan_kind") != kind or doc.get("plan_fingerprint") != fp or doc.get("domain") != domain:
            return None
    except Exception:  # noqa: BLE001 — no plan, an unreadable plan or a changed script all mean: not current
        return None
    lines = [i for i, v in index.items() if v["text"]]
    every = rows[0] + rows[1]
    listed = {r["event_id"] for r in every}
    counts = [doc.get("checked"), doc.get("lines_total")]
    if (any(type(n) is not int or n != len(lines) for n in counts) or any(i not in listed for i in lines)
            or any(not index.get(r["event_id"], {}).get("text") or r["text"] != index[r["event_id"]]["text"]
                   for r in every)
            or any(r["flag"] not in _allowed(domain) for r in rows[0])):
        return None
    return doc
