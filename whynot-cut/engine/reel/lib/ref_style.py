"""Client-level reference style (Stage 4): authored once per client, reused by every video, flagged when stale.

The reference edits in data/ (role editing_reference_video / editing_reference_doc) belong to the CLIENT, so their
interpretation does too:

  output/client_database/reference_style/
    editing-style-analysis.md   prose, measured vs inferred clearly marked        (client-researcher writes)
    editing-style.json          numbers and observed treatments                   (client-researcher writes)
    editing-rules.json          mandatory / preferences / optional / conflicts    (client-researcher writes)
    reference-set.json          the reference set it was written from             (`reel ref-style --record`)

Each video gets a copy (`reel ref-style --apply`): 01_analysis/editing-style.json + editing-rules.json, plus the
video's own 01_analysis/editing-style-overrides.json when it differs from the client's standing style.

The reference set's fingerprint is every reference file's path, size and modification time. Adding, removing or
editing (even touching) a reference makes the client style STALE until it is refreshed and recorded again. A client
folder copied without keeping modification times reads as stale too (never as current by mistake).
Stdlib only at import time (the SessionStart hook imports it).
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .common import CLIENT_PROFILE_REL, deep_merge, is_junk, now_iso, read_json, write_json

STYLE_REL = "output/client_database/reference_style"
FILES = ("editing-style-analysis.md", "editing-style.json", "editing-rules.json")
RULE_KEYS = ("mandatory", "preferences", "optional", "conflicts")
RECORD = "reference-set.json"
REF_ROLES = ("editing_reference_video", "editing_reference_doc")
VIDEO_STYLE = "01_analysis/editing-style.json"
VIDEO_RULES = "01_analysis/editing-rules.json"
OVERRIDES = "01_analysis/editing-style-overrides.json"

STALE = "reference style stale — refresh client style + reel-profile style.json/notes.md"
AUTHOR = ("AUTHOR client reference style once (" + STYLE_REL.replace("output/", "", 1) + "/: " + ", ".join(FILES)
          + "), then `reel ref-style --record`")
UNRECORDED = "ref-style --record (client reference style written but not recorded against the current references)"
APPLY = "ref-style --apply (reuse the client reference style for this video)"
APPLY_OUTDATED = "ref-style --apply (the client reference style changed since this video copied it)"


def style_dir(root) -> Path:
    return Path(root) / STYLE_REL


def reference_set(root) -> list[dict]:
    """Every reference edit under data/, classified exactly as discovery does (live scan: a reference dropped in
    after the last `discover` counts)."""
    from .discover import classify
    root = Path(root)
    data = root / "data"
    out = []
    for p in sorted(data.rglob("*")) if data.is_dir() else []:
        if p.is_dir() or is_junk(p):
            continue
        rel = p.relative_to(root).as_posix()
        role = classify(p, rel)["role"]
        if role in REF_ROLES:
            st = p.stat()
            out.append({"rel": rel, "role": role, "size": st.st_size, "mtime": int(st.st_mtime)})
    return out


def fingerprint(refs: list[dict]) -> str:
    lines = sorted(f"{r['rel']}|{r['size']}|{r['mtime']}" for r in refs)
    return hashlib.sha1("\n".join(lines).encode("utf-8")).hexdigest()


def _sha1(files: list[Path]) -> str | None:
    h = hashlib.sha1()
    seen = False
    for f in files:
        if f.exists():
            h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
            seen = True
    return h.hexdigest() if seen else None


def style_sha1(root) -> str | None:
    """The client style the videos copy (the two JSON files; the prose analysis is read, not copied)."""
    d = style_dir(root)
    return _sha1([d / "editing-style.json", d / "editing-rules.json"])


def _diff(rec: dict, refs: list[dict]) -> dict:
    old = {r["rel"]: (r["size"], r["mtime"]) for r in rec.get("references", [])}
    new = {r["rel"]: (r["size"], r["mtime"]) for r in refs}
    return {"added": sorted(set(new) - set(old)), "removed": sorted(set(old) - set(new)),
            "changed": sorted(k for k in set(new) & set(old) if new[k] != old[k])}


def _changes_text(d: dict) -> str:
    parts = [f"{label}: {', '.join(d[k])}" for k, label in (("added", "added"), ("removed", "removed"),
                                                             ("changed", "edited")) if d.get(k)]
    return "; ".join(parts) or "reference set changed"


def state(root) -> dict:
    """missing | unrecorded | stale | current, with the message `reel next` shows."""
    root = Path(root)
    d = style_dir(root)
    refs = reference_set(root)
    fp = fingerprint(refs)
    missing = [f for f in FILES if not (d / f).exists()]
    rec = read_json(d / RECORD)
    out = {"dir": STYLE_REL, "fingerprint": fp, "references": [r["rel"] for r in refs], "missing_files": missing,
           "recorded_fingerprint": (rec or {}).get("fingerprint"), "added": [], "removed": [], "changed": []}
    if missing:
        msg = AUTHOR if len(missing) == len(FILES) else AUTHOR + f" (missing: {', '.join(missing)})"
        return dict(out, state="missing", message=msg)
    if not rec:
        return dict(out, state="unrecorded", message=UNRECORDED)
    if rec.get("fingerprint") != fp:
        diff = _diff(rec, refs)
        return dict(out, **diff, state="stale",
                    message=f"{STALE} ({_changes_text(diff)}), then `reel ref-style --record`")
    if rec.get("adopted_unreviewed"):        # T4.9: `--adopt --yes` merged a per-video style since the record
        au = rec["adopted_unreviewed"]
        who = ", ".join(map(str, au)) if isinstance(au, list) else str(au)
        return dict(out, state="unrecorded", adopted_unreviewed=rec["adopted_unreviewed"],
                    message=f"ref-style --record (the client reference style took in {who}'s per-video style with "
                            "`--adopt`: review it, settle its conflicts with the editor, then record)")
    return dict(out, state="current",
                message=f"client reference style current ({len(refs)} reference(s)): reuse it (`reel ref-style --apply`)")


def record(root, by: str = "claude") -> dict:
    """Mark the client style as written from the CURRENT reference set (after the client-researcher wrote the three
    files and refreshed the reel-profile)."""
    root = Path(root)
    d = style_dir(root)
    problems = [f"missing {STYLE_REL}/{f}" for f in FILES if not (d / f).exists()]
    for f in ("editing-style.json", "editing-rules.json"):
        if (d / f).exists():
            try:
                v = json.loads((d / f).read_text(encoding="utf-8"))
            except ValueError as e:
                problems.append(f"{f} is not valid JSON ({e})")
                continue
            if not isinstance(v, dict):
                problems.append(f"{f} must be a JSON object")
            elif f == "editing-rules.json":
                problems += [f"editing-rules.json needs a `{k}` list (empty if none)" for k in RULE_KEYS
                             if not isinstance(v.get(k), list)]
    if problems:
        return {"ok": False, "problems": problems, "dir": str(d)}
    refs = reference_set(root)
    fp = fingerprint(refs)
    prev = read_json(d / RECORD) or {}
    sha = style_sha1(root)
    warnings = []
    prof = root / CLIENT_PROFILE_REL
    if prev and prev.get("fingerprint") != fp:
        since = float(prev.get("recorded_epoch") or 0)
        for f in ("style.json", "notes.md"):
            pf = prof / f
            if not pf.exists() or pf.stat().st_mtime < since:
                warnings.append(f"reel-profile {f} unchanged since the last record although the references changed "
                                f"({_changes_text(_diff(prev, refs))}): refresh it if the new references change the "
                                f"client's standing style")
        if prev.get("style_sha1") == sha:
            warnings.append("editing-style.json and editing-rules.json are unchanged since the last record although the "
                            "references changed: confirm the new references don't change the style")
    elif not prev and refs and not (prof / "style.json").exists():
        warnings.append("no reel-profile style.json yet: `reel client-init`, then put the standing style seen in the "
                        "references in style.json + notes.md")
    rec = {"fingerprint": fp, "references": refs, "style_sha1": sha, "recorded_at": now_iso(),
           "recorded_epoch": time.time(), "by": by}
    write_json(d / RECORD, rec)
    return {"ok": True, "state": "current", "fingerprint": fp, "references": [r["rel"] for r in refs],
            "record": str(d / RECORD), "warnings": warnings}


def _overrides(paths) -> tuple[dict | None, str | None]:
    f = paths.p(OVERRIDES)
    if not f.exists():
        return None, None
    return read_json(f, {}) or {}, _sha1([f])


def apply(paths) -> dict:
    """Copy the CURRENT client style into this video (+ its overrides). Never copies a missing or stale style."""
    cs = state(paths.root)
    if cs["state"] != "current":
        return {"ok": False, "blocked": cs["message"], "reference_style": cs}
    d = style_dir(paths.root)
    style = read_json(d / "editing-style.json", {})
    rules = read_json(d / "editing-rules.json", {})
    ov, ov_sha = _overrides(paths)
    if ov:
        style = deep_merge(style, ov.get("style") or {})
        for k, items in (ov.get("rules") or {}).items():
            rules[k] = list(rules.get(k) or []) + list(items or [])
    prov = {"from": STYLE_REL, "analysis": f"{STYLE_REL}/editing-style-analysis.md", "fingerprint": cs["fingerprint"],
            "style_sha1": style_sha1(paths.root), "overrides": OVERRIDES if ov is not None else None,
            "overrides_sha1": ov_sha, "applied_at": now_iso(),
            "note": "copied from the client reference style by `reel ref-style --apply`; change the client files or "
                    "this video's editing-style-overrides.json, never this copy"}
    kept = []
    for rel in (VIDEO_STYLE, VIDEO_RULES):
        f = paths.p(rel)
        old = read_json(f) if f.exists() else None
        if isinstance(old, dict) and "_reference_style" not in old:     # authored per video before client-level style
            legacy = f.with_name(f.stem + ".legacy.json")
            if not legacy.exists():
                f.replace(legacy)
                kept.append(str(legacy))
    write_json(paths.p(VIDEO_STYLE), dict(style, _reference_style=prov))
    write_json(paths.p(VIDEO_RULES), dict(rules, _reference_style=prov))
    return {"ok": True, "video_id": paths.video_id, "files": [str(paths.p(VIDEO_STYLE)), str(paths.p(VIDEO_RULES))],
            "overrides": OVERRIDES if ov is not None else None, "fingerprint": cs["fingerprint"],
            "legacy_kept": kept, "analysis": str(d / "editing-style-analysis.md")}


def video_state(paths) -> dict:
    """missing | legacy (authored per video before client-level style) | outdated | current."""
    f = paths.p(VIDEO_STYLE)
    if not f.exists():
        return {"state": "missing", "message": f"{VIDEO_STYLE} not written yet"}
    prov = (read_json(f, {}) or {}).get("_reference_style")
    if not prov:
        return {"state": "legacy", "message": f"{VIDEO_STYLE} was authored for this video before the client-level "
                                              f"reference style existed"}
    # outdated only when a fresh copy would differ: a re-record that keeps the style files as they were (the new
    # references didn't change the style) leaves every video's copy valid
    why = []
    if prov.get("style_sha1") != style_sha1(paths.root):
        why.append("the client style files changed")
    if prov.get("overrides_sha1") != _overrides(paths)[1]:
        why.append("this video's overrides changed")
    if why:
        return {"state": "outdated", "message": "copied from an older client reference style: " + "; ".join(why)}
    return {"state": "current", "message": "copied from the current client reference style"}


def next_step(paths) -> dict:
    """What `reel next` lists for Stage 4 of this video: one step (or none) plus notices."""
    cs = state(paths.root)
    vs = video_state(paths)
    planned = paths.p("01_analysis/timeline-spec.json").exists()
    step, notices = None, []
    if cs["state"] == "stale":
        step = cs["message"]
    elif vs["state"] == "missing":
        step = APPLY if cs["state"] == "current" else cs["message"]
    elif vs["state"] == "outdated":
        if cs["state"] != "current":
            step = cs["message"]
        elif not planned:
            step = APPLY_OUTDATED
        else:
            notices.append(f"this video's {VIDEO_STYLE} was {vs['message']}; `reel ref-style --apply` before re-planning")
    elif vs["state"] == "legacy" and cs.get("adopted_unreviewed"):
        notices.append(f"the client reference style took in a per-video style with `--adopt` and is not reviewed yet "
                       f"({cs['message']}); this video keeps its own {VIDEO_STYLE} until then")
    elif vs["state"] == "legacy" and cs["state"] != "current":
        hint = "" if adopted_from(paths.root, paths.video_id) else             f", or seed it from this video: `reel ref-style --adopt {paths.video_id}` (shows the diff first)"
        notices.append(f"client reference style not authored yet ({cs['message']}); this video keeps its own "
                       f"{VIDEO_STYLE}, the next new video authors the client style once{hint}")
    return {"client": cs, "video": vs, "step": step, "notices": notices}


# --------------------------------------------------------------------------- adopt (3.0 Phase 4 T4.9)
LEGACY_STYLE = "01_analysis/editing-style.legacy.json"     # what --apply kept of a per-video style
LEGACY_RULES = "01_analysis/editing-rules.legacy.json"
SKIP_KEYS = ("_reference_style", "_adopted", "source")   # `source` describes that one video (quoted in the analysis)
ADOPTED_UNREVIEWED = "adopted_unreviewed"                  # in reference-set.json until the next --record


class _Refused(Exception):
    def __init__(self, msg: str, how: str = ""):
        super().__init__(msg)
        self.doc = {"refused": msg, "how": how}


def _load(f: Path, what: str) -> dict | None:
    """A JSON object from f, None when absent; anything else is a refusal naming the file."""
    if not f.exists():
        return None
    try:
        v = json.loads(f.read_bytes().decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as e:
        raise _Refused(f"{what} is not valid UTF-8 JSON ({e}): nothing was written",
                       "Fix or remove that file first (it is never overwritten).") from None
    if not isinstance(v, dict):
        raise _Refused(f"{what} must be a JSON object: nothing was written", "Fix that file first.")
    return v


def _rules_lists(doc: dict, what: str) -> dict:
    for k in RULE_KEYS:
        if k in doc and not isinstance(doc[k], list):
            raise _Refused(f"{what}: `{k}` must be a list: nothing was written", "Fix that file first.")
    return doc


def _same(a, b) -> bool:
    """Equal as JSON values (true is not 1, 1.0 is not "1")."""
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False)


def _key(prefix: str, k) -> str:
    return prefix + str(k).replace("\\", "\\\\").replace(".", "\\.")      # a key named "a.b" is not a > b


def _merge(client: dict, video: dict, prefix: str, diff: dict) -> None:
    """Keys only the video has -> added (a dict is walked, so each leaf is named); equal -> nothing; different ->
    a conflict, the client's value kept. Dicts merge per key; lists and scalars are values."""
    import copy
    for k, v in video.items():
        if prefix == "" and k in SKIP_KEYS:
            continue
        key = _key(prefix, k)
        if k not in client:
            if isinstance(v, dict) and v:
                client[k] = {}
                _merge(client[k], v, key + ".", diff)
            else:
                client[k] = copy.deepcopy(v)
                diff["added"].append(key)
        elif isinstance(client[k], dict) and isinstance(v, dict):
            _merge(client[k], v, key + ".", diff)
        elif _same(client[k], v):
            diff["same"] += 1
        else:
            diff["conflicts"].append({"key": key, "client": client[k], "video": v})


def _video_sources(paths) -> tuple[Path, dict, Path | None, dict | None]:
    vid = paths.video_id
    legacy = paths.p(LEGACY_STYLE)
    if legacy.exists():
        style_f, style = legacy, _load(legacy, f"{vid}'s {LEGACY_STYLE}")
    else:
        cur = paths.p(VIDEO_STYLE)
        doc = _load(cur, f"{vid}'s {VIDEO_STYLE}")
        if doc is not None and "_reference_style" in doc:
            raise _Refused(f"{vid}'s {VIDEO_STYLE} is a copy of the client reference style (`reel ref-style --apply`): "
                           "there is no per-video style to adopt", "Nothing to do for this video.")
        style_f, style = cur, doc
    if style is None:
        raise _Refused(f"{vid} has no per-video style ({VIDEO_STYLE} or {LEGACY_STYLE}): nothing to adopt",
                       "Pick a video that still has its own style (`reel ref-style --video-id <ID>` shows its state).")
    rules_f, rules = None, None
    for rel in (LEGACY_RULES, VIDEO_RULES):
        f = paths.p(rel)
        doc = _load(f, f"{vid}'s {rel}")
        if doc is None or (rel == VIDEO_RULES and "_reference_style" in doc):
            continue
        rules_f, rules = f, _rules_lists(doc, f"{vid}'s {rel}")
        break
    return style_f, style, rules_f, rules


def _sha1_file(f: Path) -> str:
    return hashlib.sha1(f.read_bytes()).hexdigest()


def _read_md(f: Path) -> tuple[str, bool, str]:
    """(text, had a BOM, its line ending) of the analysis file; a file that is not UTF-8 is a refusal."""
    if not f.exists():
        return "# Editing style analysis\n", False, "\n"
    raw = f.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise _Refused(f"{STYLE_REL}/{f.name} is not UTF-8 text: nothing was written",
                       "Save it as UTF-8 (it is never overwritten otherwise), then run the adopt again.") from None
    return text, raw.startswith(b"\xef\xbb\xbf"), "\r\n" if "\r\n" in text else "\n"


def _json_bytes(doc) -> bytes:
    return (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def adopted_from(root, video_id: str) -> list[dict]:
    """The provenance entries of the client style that came from this video."""
    style = read_json(style_dir(root) / "editing-style.json")
    prov = style.get("_adopted") if isinstance(style, dict) else None
    return [p for p in prov if isinstance(p, dict) and str(p.get("from", "")).startswith(f"output/projects/{video_id}/")] \
        if isinstance(prov, list) else []


def adopt(root, video_id: str, yes: bool = False) -> dict:
    """Merge video `video_id`'s per-video style (2.x, authored per clip) into the client reference style. Without
    `yes` only the diff (nothing written); with it the client files are written, all three staged first and then put
    in place. `refused` = nothing written."""
    import copy
    import os

    from .client_move_paths import first_refusal
    from .common import Paths, check_project_id
    from .errors import Guidance
    try:
        check_project_id(video_id)
    except Guidance as e:
        return {"refused": str(e), "how": "Use the project folder name under output/projects (e.g. R02)."}
    paths = Paths(root, video_id)
    root = paths.root
    d = style_dir(root)
    rel = lambda f: Path(f).relative_to(root).as_posix()  # noqa: E731
    files = {n: d / n for n in FILES}
    record_f = d / RECORD
    try:
        if not paths.project.is_dir():
            known = sorted(p.name for p in (root / "output/projects").glob("*")
                           if (p / VIDEO_STYLE).exists() or (p / LEGACY_STYLE).exists())
            raise _Refused(f"no project {video_id} in output/projects: nothing to adopt",
                           f"Projects with a per-video style: {', '.join(known) or 'none'}.")
        style_f, vstyle, rules_f, vrules = _video_sources(paths)
        r = first_refusal(root, [root / "output", root / "output/client_database", d, record_f, *files.values()])
        if r:
            return r
        cstyle = _load(files["editing-style.json"], f"{STYLE_REL}/editing-style.json")
        crules = _load(files["editing-rules.json"], f"{STYLE_REL}/editing-rules.json")
        if crules is not None:
            _rules_lists(crules, f"{STYLE_REL}/editing-rules.json")
        old_prov = (cstyle or {}).get("_adopted", [])
        if not isinstance(old_prov, list):
            raise _Refused(f"{STYLE_REL}/editing-style.json `_adopted` must be a list (the adopt record): nothing was "
                           "written", "Fix that key by hand first.")
        md_text, md_bom, md_nl = _read_md(files["editing-style-analysis.md"])
        rec = _load(record_f, f"{STYLE_REL}/{RECORD}")
    except _Refused as e:
        return e.doc
    src = rel(style_f)
    sha = _sha1_file(style_f)
    rules_sha = _sha1_file(rules_f) if rules_f else None
    base = {"ok": True, "dry_run": not yes, "video_id": video_id, "source": src,
            "rules_source": rel(rules_f) if rules_f else None}
    mine = f"output/projects/{video_id}/"                  # the plain or the .legacy name: --apply renames it
    if any(isinstance(p, dict) and str(p.get("from", "")).startswith(mine) and p.get("sha1") == sha
           and p.get("rules_sha1") == rules_sha for p in old_prov):
        return dict(base, changes=False, diff={"added": [], "conflicts": [], "rules_added": {}, "same": 0},
                    message=f"nothing to change: this exact file of {video_id} was adopted already (settled conflicts "
                            "are not brought back)")
    new_style = copy.deepcopy(cstyle) if cstyle is not None else {}
    diff = {"added": [], "conflicts": [], "rules_added": {}, "same": 0,
            "rules_not_adopted": sorted(k for k in (vrules or {}) if k not in RULE_KEYS and k != "_reference_style")}
    _merge(new_style, vstyle, "", diff)
    new_rules = copy.deepcopy(crules) if crules is not None else {}
    for k in RULE_KEYS:
        new_rules.setdefault(k, [])
    for k in RULE_KEYS:
        for item in (vrules or {}).get(k) or []:
            if not any(_same(item, x) for x in new_rules[k] + diff["rules_added"].get(k, [])):
                diff["rules_added"].setdefault(k, []).append(item)
    for k, items in diff["rules_added"].items():
        new_rules[k] = list(new_rules[k]) + items
    new_conflicts = []
    for c in diff["conflicts"]:
        entry = {"key": c["key"], "video": video_id, "client_value": c["client"], "video_value": c["video"],
                 "note": f"`reel ref-style --adopt {video_id}` kept the client value; settle it with the editor"}
        if not any(isinstance(x, dict) and all(_same(x.get(f), entry[f]) for f in ("key", "video", "client_value",
                                                                                   "video_value"))
                   for x in new_rules["conflicts"]):
            new_conflicts.append(entry)
    new_rules["conflicts"] = list(new_rules["conflicts"]) + new_conflicts
    changes = bool(diff["added"] or diff["rules_added"] or new_conflicts)
    base = dict(base, changes=changes, diff=diff)
    if not changes:
        return dict(base, message=f"nothing to change: {video_id}'s style is already in the client reference style")
    prov = {"from": src, "sha1": sha, "at": now_iso()}
    if rules_f:
        prov.update(rules_from=rel(rules_f), rules_sha1=rules_sha)
    new_style["_adopted"] = list(old_prov) + [prov]
    targets = [files["editing-style.json"]]
    if crules is None or not _same(new_rules, crules):
        targets.append(files["editing-rules.json"])
    targets.append(files["editing-style-analysis.md"])
    if rec is not None:
        targets.append(record_f)
    if not yes:
        return dict(base, would_write=[rel(f) for f in targets],
                    how=f"Show the editor this diff (added keys, rules, and conflicts where the client value is kept); "
                        f"with their OK: `reel ref-style --adopt {video_id} --yes`.")
    section = [f"## Adopted from {video_id} ({now_iso()[:10]})",
               f"`reel ref-style --adopt {video_id}` merged {src} (a per-video style from before the client-level "
               f"style) into editing-style.json"
               + (f" and {rel(rules_f)} into editing-rules.json" if rules_f else "") + ".",
               f"- added: {', '.join(diff['added']) or 'nothing'}",
               f"- conflicts kept as the client had them (listed in editing-rules.json `conflicts`): "
               f"{', '.join(c['key'] for c in diff['conflicts']) or 'none'}"]
    if isinstance(vstyle.get("source"), str) and vstyle["source"].strip():
        section.append(f"- that file's own description of its source: {' '.join(vstyle['source'].split())}")
    section.append("- review this against the current reference edits, then `reel ref-style --record`")
    md = md_text.rstrip("\r\n") + md_nl + md_nl + md_nl.join(section) + md_nl
    blobs = {files["editing-style.json"]: _json_bytes(new_style),
             files["editing-style-analysis.md"]: (b"\xef\xbb\xbf" if md_bom else b"") + md.encode("utf-8")}
    if files["editing-rules.json"] in targets:
        blobs[files["editing-rules.json"]] = _json_bytes(new_rules)
    if rec is not None:                    # recorded before: unreviewed until the next --record (state: unrecorded)
        prev = rec.get(ADOPTED_UNREVIEWED)
        prev = [str(x) for x in prev] if isinstance(prev, list) else []
        rec = dict(rec, **{ADOPTED_UNREVIEWED: sorted(set(prev) | {video_id})})
        blobs[record_f] = _json_bytes(rec)
    d.mkdir(parents=True, exist_ok=True)
    r = first_refusal(root, [d, *blobs])                             # a link swapped in meanwhile
    if r:
        return r
    # The record (with the "not reviewed" flag) goes in first and the style with its provenance last; every file is
    # staged before any is replaced, and a failure part-way puts back what was there (T4.9 review 2): never a merge
    # that reads as reviewed, never a provenance entry without the rules and conflicts it came with.
    order = [f for f in (record_f, files["editing-rules.json"], files["editing-style-analysis.md"],
                         files["editing-style.json"]) if f in blobs]
    staged, before, done = {}, {}, []
    try:
        for f in order:
            before[f] = f.read_bytes() if f.exists() else None
            staged[f] = f.with_name(f"{f.name}.{os.getpid()}-{len(staged)}.tmp")
            staged[f].write_bytes(blobs[f])
        for f in order:
            os.replace(staged[f], f)
            done.append(f)
    except OSError as e:
        undone = []
        for f in reversed(done):
            try:
                if before[f] is None:
                    f.unlink()
                else:
                    f.write_bytes(before[f])
            except OSError:
                undone.append(rel(f))
        return {"ok": False, "error": f"could not write {STYLE_REL}: {e}",
                "how": ("Nothing changed: every file was put back. Close what holds the file (an editor, a scan) "
                        "and run the adopt again." if not undone else
                        f"These files could not be put back: {', '.join(undone)}. Restore them from the editor's backup "
                        "or ask the lead; then run the adopt again."), "written": []}
    finally:
        for tmp in staged.values():
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
    return dict(base, written=[rel(f) for f in targets],
                next="the client-researcher reviews reference_style/ against the current reference edits (and the "
                     "conflicts with the editor), then `reel ref-style --record`; until then the style reads "
                     "unrecorded and videos do not copy it")
