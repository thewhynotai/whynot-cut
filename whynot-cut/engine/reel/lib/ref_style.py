"""Client-level reference style (Stage 5): authored once per client, reused by every video, flagged when stale.

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
    """What `reel next` lists for Stage 5 of this video: one step (or none) plus notices."""
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
    elif vs["state"] == "legacy" and cs["state"] != "current":
        notices.append(f"client reference style not authored yet ({cs['message']}); this video keeps its own "
                       f"{VIDEO_STYLE}, the next new video authors the client style once")
    return {"client": cs, "video": vs, "step": step, "notices": notices}
