#!/usr/bin/env python3
"""WhyNot Cut pipeline CLI (Claude Code plugin engine, by The Why Not AI). macOS and Windows.

Run via the plugin wrapper:  reel <command> --root <CLIENT_FOLDER> [--video-id ID] [--profile ID]
(the wrapper runs the engine runtime in ~/.whynot-cut/runtimes/<id>, named by ~/.whynot-cut/current, or a 2.x
venv/; `reel setup` builds or repairs the runtime)

Deterministic stages are scripts; the semantic stages (client style, main topic, narrative segments, statement
analysis, edit-decisions.json) are files Claude authors, then `reel plan` validates and compiles them.
`reel --help` lists every command with its one line; it is generated from the command table (CORE_COMMANDS here,
HELP in lib/podcast_cli.py and lib/motion_cli.py), so there is no list to keep in sync in this docstring.
`reel <command> --help` shows that command's options.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if __name__ == "__main__" and os.environ.get("WHYNOT_TEST_ECHO_ARGV") == "1":   # TEST ONLY (tests/test_wrappers.py):
    print(json.dumps({"argv": sys.argv[1:], "whynot_home": os.environ.get("WHYNOT_HOME"),    # what the wrapper
                      "env_keys": sorted(os.environ), "prefix": sys.prefix,                 # handed the engine,
                      "no_user_site": bool(sys.flags.no_user_site)}))                       # and with which python
    sys.exit(0)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.common import (Paths, load_status, log, read_json, set_status, write_json, now_iso,  # noqa: E402
                        set_context, active_profile, profile_dirs, project_prefix, models_dir, PROFILES_DIR, CLIENT_PROFILE_REL,
                        clients_root, client_folders, resolve_root)

# 01_analysis/editing-style.json is the video's copy of the client reference style (`reel ref-style --apply`), not
# authored per video; the other files are written by the story editor (+ medical reviewer) for each video
SEMANTIC_FILES = ["01_analysis/editing-style.json", "01_analysis/main-topic.md",
                  "01_analysis/narrative-segments.json", "01_analysis/transcript-semantic-analysis.json",
                  "01_analysis/medical-content-review.md", "01_analysis/edit-decisions.json"]
STYLE_COPY = SEMANTIC_FILES[0]


def P(a) -> Paths:
    if getattr(a, "episode", None) and not a.video_id:   # podcast episode project (output/episodes/<EP>/)
        from lib.episode import EpisodePaths
        return EpisodePaths(a.root, a.episode)
    return Paths(a.root, a.video_id)


def out(obj, check: bool = True):
    """Print the command's one JSON document; a failed result (`ok: false`, a FAILED/REFUSED/BLOCKED status) exits 1,
    a refusal (`blocked`/`refused`) exits 2 (3.0 T2.2, lib/errors.py). check=False when `status` is a project state
    (`reel status`, `reel next`), not this command's result."""
    from lib.errors import emit
    emit(obj, check)


def error_log(a) -> Path:
    """Where the top-level handler appends a traceback: the project's (or episode's) logs/pipeline.log, else the
    client's output/logs/pipeline.log, else the engine home's logs/pipeline.log (no client folder)."""
    from lib.common import engine_home
    try:
        root = Path(a.root).expanduser() if getattr(a, "root", None) else None
        if root and (root / "assets").is_dir() and (root / "data").is_dir():
            if getattr(a, "video_id", None) or getattr(a, "episode", None):
                p = P(a)
                if p.project.is_dir():
                    return p.p("logs/pipeline.log")
            return root / "output" / "logs" / "pipeline.log"
    except Exception:  # noqa: BLE001 — the log location must never raise in the handler
        pass
    return engine_home() / "logs" / "pipeline.log"


def fail(a, exc: BaseException):
    """An exception reached the top: guidance JSON on stdout ({"ok": false, "error", "where", "how", "log"}), the
    traceback in the log (never on stdout or stderr), exit 1 (3.0 T2.2, engine IM-7)."""
    from lib.errors import report
    shown = ["reel", str(getattr(a, "cmd", ""))] + [f"{o} {v}" for o, v in (("--video-id", getattr(a, "video_id", None)),
                                                                          ("--episode", getattr(a, "episode", None))) if v]
    out(report(exc, error_log(a), " ".join(shown)))


def footage_path(paths: Paths, s: str) -> Path:
    """A --footage value as a path: a Git Bash path (/d/Work/x.mp4) or ~ through plat.native_path (T2.15, MI-15),
    a relative one under the client folder."""
    from lib.plat import native_path
    f = Path(native_path(str(s))).expanduser()
    return f if f.is_absolute() else paths.root / f


def main_footage(paths: Paths, explicit: str | None) -> list[Path]:
    """The raw file of THIS video: --footage, else the project's range (`reel range`), else the raw clip the video id
    names (its id from `reel inbox`, its file stem or its 2.x slug: lib/clip_ids.py), else the only raw clip. Never
    silently another clip."""
    from lib.common import source_range
    if explicit:
        return [footage_path(paths, explicit)]
    rng = source_range(paths)
    if rng:
        f = Path(rng["footage"])
        return [f if f.is_absolute() else paths.root / f]
    inv = read_json(paths.output / "discovery/input-inventory.json")
    if not inv:
        raise SystemExit("run `discover` first")
    files = [Path(f["path"]) for f in inv["files"] if f["role"] == "source_footage"]
    if not paths.video_id or len(files) <= 1:
        return files
    from lib.clip_ids import clip_ids, resolve
    f = resolve(paths.root, paths.video_id, inv)
    if f:
        return [f]
    ids = "; ".join(f"{k} = {v}" for k, v in clip_ids(paths.root, inv).items())
    raise SystemExit(f"no raw clip with id '{paths.video_id}'. Clip ids (`reel inbox` lists them): {ids}. Use one as "
                     f"--video-id, pass --footage, or cut this video from a longer file with `reel range`")


def canonical_video_id(a):
    """--video-id given as the raw file stem ("Dr Sherif intro", "مقابلة ١"), the 2.x slug or in another case is
    rewritten to the clip's id from `reel inbox`, so the work lands in the project inbox tracks. A project folder that
    already exists under the given name is kept (a case-only difference is always normalised). `reel range` names a new
    reel's id, so it is left alone."""
    if not a.video_id or getattr(a, "episode", None) or a.cmd == "range":
        return
    root = Path(a.root).expanduser()
    if not (root / "output/discovery/input-inventory.json").exists():
        return
    from lib.clip_ids import canonical
    try:
        c = canonical(root, a.video_id)
    except SystemExit:
        return                    # an id whose clip is gone: main_footage refuses it with the full message
    if not c or c == a.video_id:
        return
    if c.upper() != a.video_id.upper() and Paths(root, a.video_id).project.is_dir():
        return
    sys.stderr.write(f"note: --video-id {a.video_id!r} is clip {c} (`reel inbox` id); using output/projects/{c}\n")
    a.video_id = c


def cmd_discover(a):
    from lib.discover import run_discovery
    p = P(a)
    if p.video_id:
        p.ensure_project()
    r = run_discovery(p)
    if p.video_id:
        set_status(p, "INPUTS_DISCOVERED", f"{r['inventory']['file_count']} files", "discover",
                   [p.output / "discovery/discovery-report.md"])
    from lib.ref_style import state
    rs = state(p.root)
    out({"files": r["inventory"]["file_count"], "by_role": {k: len(v) for k, v in r["inventory"]["by_role"].items()},
         "warnings": r["inventory"]["warnings"], "report": str(p.output / "discovery/discovery-report.md"),
         "reference_style": {"state": rs["state"], "message": rs["message"]}})


def cmd_client_db(a):
    from lib.client_db import build
    p = P(a)
    inv = read_json(p.output / "discovery/input-inventory.json")
    if not inv:
        raise SystemExit("run `discover` first")
    st = build(p, inv)
    if p.video_id and st["ready"]:
        set_status(p, "CLIENT_DATABASE_READY", "; ".join(st["issues"]), "client_db", [p.client_db])
    out(st)


def refuse_stale_window(p: Paths):
    """A reel cut from a podcast episode is never built from an episode file that changed after selection."""
    from lib.reels import window_stale
    msg = window_stale(p)
    if msg:
        out({"ok": False, "blocked": msg})
        raise SystemExit(2)


def cmd_preflight(a):
    from lib.media import preflight
    p = P(a)
    refuse_stale_window(p)
    p.ensure_project()
    rep = preflight(p, main_footage(p, a.footage))
    from lib.common import STATUSES
    cur = load_status(p).get("status")
    keep = rep["ok"] and cur in STATUSES and cur != "BLOCKED" and STATUSES.index(cur) > STATUSES.index("INPUTS_VALIDATED")
    set_status(p, cur if keep else ("INPUTS_VALIDATED" if rep["ok"] else "BLOCKED"),   # a re-run never moves a clip back
               f"{len(rep['valid'])} valid, {len(rep['issues'])} notes", "preflight",
               [p.p("00_inputs/preflight-report.md")],
               blockers=[i["msg"] for i in rep["issues"] if i["severity"] == "error"])
    out({"ok": rep["ok"], "issues": rep["issues"], "conversions": rep["conversions"]})


def _parse_time_ms(v: str) -> int:
    """--start/--end: seconds ("90", "90.5") or a clock ("1:30", "00:01:30.5") -> ms."""
    from lib.media_util import parse_time
    return parse_time(v)


def cmd_range(a):
    """This video = part of a longer raw file (a reel cut from a full episode). Without --footage: show the range."""
    from lib.media import probe
    p = P(a)
    f_src = p.p("00_inputs/source.json")
    if not a.footage:
        out(read_json(f_src, {}) or {"range": None, "note": "whole raw file (no range set)"})
        return
    f = footage_path(p, a.footage)
    if not f.exists():
        raise SystemExit(f"{f} not found")
    dur_ms = int((probe(f).get("duration_s") or 0) * 1000)
    i, o = _parse_time_ms(a.start), (_parse_time_ms(a.end) if a.end else dur_ms)
    if not (0 <= i < o <= dur_ms + 40):
        raise SystemExit(f"range {i / 1000:.3f}-{o / 1000:.3f}s outside the file (0-{dur_ms / 1000:.3f}s) or empty")
    from lib.media import snap_range_points
    snap = snap_range_points(f, i, o if a.end else None)
    if a.snap:
        i = snap["in"]["suggested_ms"]
        o = snap["out"]["suggested_ms"] if "out" in snap else o
    p.ensure_project()
    old = read_json(f_src, {}) or {}
    from lib.plan import _client_rel       # T2.15: the plan's main_footage rule (inventory rel, else realpath on both
    rel = _client_rel(p, f, read_json(p.output / "discovery/input-inventory.json", {}) or {})    # sides: junction, 8.3)
    rec = {"footage": rel, "in_ms": i, "out_ms": min(o, dur_ms), "duration_ms": min(o, dur_ms) - i,
           "label": a.label or "", "set_at": now_iso()}
    write_json(f_src, rec)
    changed = bool(old) and (old.get("footage"), old.get("in_ms"), old.get("out_ms")) != (rec["footage"], i, rec["out_ms"])
    stale = [x for x in ("02_transcription/transcript.json", "06_audio/dialogue/dialogue_clean.wav")
             if changed and p.p(x).exists()]
    moved = {k: v for k, v in snap.items() if v["moved_ms"]}
    out(dict(rec, stale=stale, snap=snap, applied_snap=bool(a.snap),
             next=("re-run with --snap to start/end in the pause (speech at the requested point)" if moved and not a.snap else
                   "reel preflight, then reel transcribe" + (" --force (the range changed)" if stale else ""))))


def cmd_transcribe(a):
    from lib.transcribe import transcribe, verify_existing_srt
    from lib.media import probe
    p = P(a)
    p.ensure_project()
    from lib.common import source_range
    rng = source_range(p)
    if rng.get("kind") == "episode_reel":
        # a podcast reel's transcript is sliced from the episode's (corrections, flags and verification included):
        # never re-decode it here. Missing -> re-slice; present -> say how to refresh it.
        if p.p("02_transcription/transcript.json").exists():
            out({"refused": "this reel's transcript is sliced from episode " + str(rng.get("episode_id")) + ": correct the "
                            "EPISODE transcript (`reel transcript-correct --episode " + str(rng.get("episode_id")) + "`), then "
                            "`reel reels-select --episode " + str(rng.get("episode_id")) + " --resync`"})
            raise SystemExit(2)
        from lib.episode import EpisodePaths
        from lib.reels import slice_transcript
        r = slice_transcript(EpisodePaths(p.root, rng["episode_id"]), p, int(rng["in_ms"]), int(rng["out_ms"]))
        set_status(p, "TRANSCRIBED", f"re-sliced from episode {rng['episode_id']}", "transcribe")
        out(dict(r, resliced_from=rng["episode_id"]))
        return
    src = main_footage(p, a.footage)[0]
    st = load_status(p)
    if p.p("02_transcription/transcript.json").exists() and not a.force:
        out({"skipped": "transcript exists (use --force to redo)"})
        return
    inv = read_json(p.output / "discovery/input-inventory.json", {"files": []})
    existing = [f for f in inv["files"] if f["role"] == "existing_transcript"]
    if existing and not a.force:
        dur = int(probe(src)["duration_s"] * 1000)
        checks = {f["rel"]: verify_existing_srt(Path(f["path"]), dur) for f in existing}
        write_json(p.p("02_transcription/existing-srt-check.json"), checks)
        log(p, f"Existing SRT check: {checks} — Whisper still runs; compare before reuse")
    if not a.model:
        from lib import settings as S
        a.model = S.load(p.root).get("whisper_model") or "large-v3"
    r = transcribe(p, src, model_size=a.model, language=a.language, backend=a.backend, batch_size=a.batch_size,
                   force=a.force)
    set_status(p, "TRANSCRIBED", f"{r['segments']} segs, lang {r['meta']['language']}", "transcribe",
               [p.p("02_transcription/subtitles.srt")])
    out(r)


def cmd_transcript_correct(a):
    from lib.transcribe import apply_corrections
    out(apply_corrections(P(a)))


def cmd_transcript_verify(a):
    from lib.transcribe import words_fingerprint
    p = P(a)
    write_json(p.p("02_transcription/verification.json"), {"verified": True, "by": a.by or "editor", "at": now_iso(),
                                                            "note": a.note or "", "words_sha1": words_fingerprint(p)})
    out({"verified": True})


def cmd_transcript_relisten(a):
    from lib.transcribe import relisten
    ids = [int(x) for x in a.words.split(",") if x.strip()] if a.words else None
    from lib import settings as S
    p = P(a)
    out(relisten(p, ids, model_size=a.model or S.load(p.root).get("whisper_model") or "large-v3"))


def cmd_ref_analyze(a):
    from lib.ref_analysis import analyze_all
    from lib.media import probe
    p = P(a)
    inv = read_json(p.output / "discovery/input-inventory.json")
    if not inv:
        from lib.errors import Guidance
        raise Guidance("no discovery yet: the client's reference edits are found by `reel discover`",
                       f'Run `reel discover --root "{p.root}"` first, then `reel ref-analyze` again',
                       where=str(p.output / "discovery/input-inventory.json"))
    refs = [Path(f["path"]) for f in inv["files"] if f["role"] == "editing_reference_video"]
    docs = [f["rel"] for f in inv["files"] if f["role"] == "editing_reference_doc"]
    res = analyze_all(p, refs, {str(r): probe(r)["duration_s"] for r in refs}) if refs else {}
    from lib import ref_style
    cs = ref_style.state(p.root)
    applied = None
    if p.video_id and cs["state"] == "current":
        vs = ref_style.video_state(p)
        # reuse, never re-author: copy the client style when this video has none yet (or an outdated copy and no plan)
        if vs["state"] == "missing" or (vs["state"] == "outdated" and not p.p("01_analysis/timeline-spec.json").exists()):
            applied = ref_style.apply(p)
    if cs["state"] == "current":
        nxt = ("client reference style reused for this video (" + STYLE_COPY + "); put anything specific to this video "
               "in " + ref_style.OVERRIDES + " and re-run `reel ref-style --apply`") if applied else cs["message"]
    else:
        nxt = (f"View the contact sheets, then {cs['message']}" if cs["state"] != "unrecorded" else cs["message"])
    out({"reference_docs": docs, "reference_videos": len(refs), "measurements": res.get("aggregate"),
         "contact_sheets": [s for r in res.get("references", []) for s in r["contact_sheets"]],
         "reference_style": {"state": cs["state"], "message": cs["message"], "added": cs["added"],
                             "removed": cs["removed"], "changed": cs["changed"]},
         "applied": applied, "next": nxt})


def cmd_ref_style(a):
    """Client reference style: show its state, --record it against the current references, or --apply it to a video."""
    from lib import ref_style
    p = P(a)
    if a.record:
        r = ref_style.record(p.root, by=a.by or "claude")
        out(r, check=False)
        if not r["ok"]:
            raise SystemExit(2)           # a refusal: the client style files are not ready to record
        return
    if a.apply:
        if not p.video_id:
            raise SystemExit("--video-id required for --apply (the video that reuses the client style)")
        p.ensure_project()
        r = ref_style.apply(p)
        out(r, check=False)
        if not r["ok"]:
            raise SystemExit(2)
        return
    st = ref_style.state(p.root)
    if p.video_id:
        st["video"] = ref_style.video_state(p)
    out(st)


def cmd_plan(a):
    from lib.plan import compile_plan
    p = P(a)
    refuse_stale_window(p)
    missing = [f for f in SEMANTIC_FILES if not p.p(f).exists()]
    from lib import ref_style
    rs = ref_style.next_step(p)
    if missing:
        set_status(p, load_status(p)["status"], f"semantic files missing: {missing}")
        res = {"ok": False, "missing_semantic_files": missing}
        if STYLE_COPY in missing:
            res["how"] = (f"{STYLE_COPY}: `reel ref-style --apply` (copies the client reference style)"
                          if rs["client"]["state"] == "current" else f"{STYLE_COPY}: {rs['client']['message']}, "
                                                                       f"then `reel ref-style --apply`")
        out(res)
        return
    set_status(p, "ANALYZED", "semantic analysis files present", "analysis")
    r = compile_plan(p, getattr(a, "ctx", None))
    if rs["step"] or rs["notices"]:
        r["reference_style"] = {"state": rs["client"]["state"], "video": rs["video"]["state"],
                                "note": rs["step"] or "; ".join(rs["notices"])}
    if r["ok"]:
        spec = read_json(p.p("01_analysis/timeline-spec.json"))
        pend = [e["event_id"] for e in spec["events"] if e["approval_required"]]
        set_status(p, "EDIT_PLAN_READY", f"{r['events']} events, {r['cues']} cues", "plan",
                   [p.p("01_analysis/timeline-spec.json")])
        if pend:
            set_status(p, "AWAITING_APPROVAL", f"pending approval: {pend} (generation continues as drafts)")
    out(r)


def cmd_validate(a):
    """3.0 T2.3: {ok, kind, file, errors[{path, msg}]}; the kind from the file name or --kind. A relative path that is
    not in the current folder is looked up in the project (--video-id: output/projects/<ID>/), the episode (--episode:
    output/episodes/<EP>/) and then --root, so `reel --root C --video-id CLIP1 validate 01_analysis/edit-decisions.json`
    finds the clip's own file. When nothing exists the error lists every place tried."""
    from lib.schemas import validate_file
    f = Path(a.file).expanduser()
    tried = [f]
    if not f.is_absolute() and a.root:
        root = Path(a.root).expanduser()
        if a.video_id:
            tried.append(Paths(root, a.video_id).p(a.file))
        if getattr(a, "episode", None):
            from lib.episode import EpisodePaths
            tried.append(EpisodePaths(root, a.episode).p(a.file))
        tried.append(root / f)
    found = next((c for c in tried if c.exists()), tried[0])
    res = validate_file(found, a.kind)
    if not found.exists() and res.get("error", "").startswith("not found"):
        res["tried"] = [str(c) for c in tried]
        res["error"] = f"not found: {a.file}"
        res["how"] = "looked in: " + "; ".join(str(c) for c in tried)
    out(res)


def cmd_previews(a):
    from lib.previews import render_all
    p = P(a)
    refuse_stale_window(p)
    r = render_all(p, composite_preview=not a.no_composite)
    out({"previews": len(r["previews"]), "contact_sheet": str(p.p("08_quality_control/previews/_contact_sheet.jpg")),
         **({"warnings": r["warnings"]} if r.get("warnings") else {})})


def cmd_sfx(a):
    from lib.sfx import MAP_REL, install_needed, load_map
    p = P(a)
    cues = read_json(p.p("06_audio/audio-cue-sheet.json"), {"cues": []})["cues"]
    kinds = {c["kind"] for c in cues}
    sfx_map = load_map(p.p(MAP_REL))
    inv = read_json(p.output / "discovery/input-inventory.json", {"files": []})
    if [f for f in inv["files"] if f["role"] == "sfx"] and not sfx_map:
        log(p, "Client SFX library present — map kinds to library files in 06_audio/sfx-map.json (procedural used for unmapped kinds)")
    r = install_needed(kinds, sfx_map, p.root, p.p("06_audio/sfx"))
    write_json(p.p("06_audio/sfx/sfx-library.json"), r)
    out({"kinds": sorted(kinds), "files": len(r), "mapped": sorted(k for k in r if k in sfx_map)})


def require_plan_approval(p: Paths):
    """Hard gate before slow Adobe builds: the CURRENT plan must be approved (by the editor, or
    explicitly delegated by them). A re-plan after approval invalidates it."""
    from lib.plan import plan_fingerprint
    appr = read_json(p.p("01_analysis/plan-approval.json"))
    if not appr or appr.get("stale") or appr.get("plan_fingerprint") != plan_fingerprint(p):
        out({"blocked": "edit plan not approved (or changed since approval)",
             "how": "Show the editor 01_analysis/edit-plan.md (playback in chat); after they approve run "
                    "`reel approve-plan --by editor`. If they told you to proceed without review: "
                    "`reel approve-plan --by delegated --note \"<their words>\"`."})
        raise SystemExit(2)


def cmd_approve_plan(a):
    from lib.plan import APPROVAL_FORMAT, plan_fingerprint
    from lib.motion_config import is_motion
    p = P(a)
    if is_motion(p):                      # motion video (2.2): Gate 1 approves the compiled motion plan
        from lib.motion_plan import fingerprint
        val = read_json(p.p("01_analysis/motion-validation.json"))
        if not p.p("01_analysis/motion-plan.json").exists() or not val:
            raise SystemExit("compile the motion plan first (`motion-plan`)")
        if not val.get("ok"):
            raise SystemExit("the motion plan has errors (01_analysis/motion-plan.md): fix them before approval")
        if val.get("fingerprint") != fingerprint(p):
            raise SystemExit("the motion plan is stale (script, words, audio or brand changed): run `motion-plan` again")
        rec = {"approved": True, "by": a.by, "note": a.note or "", "at": now_iso(), "plan_fingerprint": fingerprint(p),
               "kind": "motion", "format": APPROVAL_FORMAT}
        write_json(p.p("01_analysis/plan-approval.json"), rec)
        set_status(p, "EDIT_PLAN_READY", f"motion plan approved by {a.by}", "plan_approval")
        out(rec)
        return
    if not p.p("01_analysis/timeline-spec.json").exists():
        raise SystemExit("compile the plan first (`plan`)")
    rec = {"approved": True, "by": a.by, "note": a.note or "", "at": now_iso(), "plan_fingerprint": plan_fingerprint(p, checked=True),
           "format": APPROVAL_FORMAT}
    write_json(p.p("01_analysis/plan-approval.json"), rec)
    set_status(p, "EDIT_PLAN_READY", f"plan approved by {a.by}", "plan_approval")
    out(rec)


def cmd_verify(a):
    from lib import verify
    from lib.motion_config import is_motion
    p = P(a)
    if is_motion(p):                      # motion video (2.2): the sheet of frames After Effects rendered
        from lib.motion_qc import record_visual
        if not a.record:
            raise SystemExit("motion projects: `reel motion-frames` builds the sheet; then `verify --record`")
        out(record_visual(p, a.verdict, a.notes or "", a.by or "claude"))
        return
    if a.record:
        out(verify.record(p, a.verdict, a.notes or "", a.by or "claude", a.sheet))
    else:
        r = verify.build(p)
        r["next"] = "VIEW the sheet image and check every tile against the checklist, then record a verdict."
        out(r)


def cmd_ppro_install(a):
    from lib.ppro_bridge import install
    out(install(force=getattr(a, "force", False)))


def cmd_ppro_status(a):
    from lib.ppro_bridge import status, submit
    st = status()
    if st["alive"]:
        st["ping"] = submit("ping", timeout=30)
    out(st)


def cmd_ppro_probe(a):
    from lib.ppro_bridge import submit
    out(submit("probe", timeout=120))


def cmd_ppro_build(a):
    from lib.ppro_build import build
    p = P(a)
    refuse_stale_window(p)
    require_plan_approval(p)
    r = build(p, overwrite=a.force, replace_edited=a.replace_edited)
    if r.get("status") == "PRPROJ_BUILT":
        set_status(p, "PROJECT_ASSEMBLED", "native .prproj built in Premiere via WhyNot Cut Bridge", "premiere_native", [r["project"]])
    out(r)


def cmd_ppro_frames(a):
    from lib.ppro_build import export_frames
    out(export_frames(P(a), retries=a.pending_retries, wait_s=a.pending_wait))


def cmd_audio_clean(a):
    from lib.audio_clean import clean, detect_pauses, verify_cuts
    p = P(a)
    refuse_stale_window(p)
    src = main_footage(p, None)[0]
    hum = "auto" if a.hum == "auto" else () if a.hum == "off" else tuple(range(int(a.hum) * 2, 501, int(a.hum)))
    from lib.recipes import pause_params
    pp = pause_params(p, a.min_pause, a.pad)    # explicit > the reel's recipe > profile style.json > 250/80
    r = clean(p, src, nr_db=a.nr, expander=a.expander, hum_notches_hz=hum)
    q = detect_pauses(p, min_pause_ms=pp["min_pause_ms"], pad_ms=pp["pad_ms"])
    q["pause_params"] = pp
    v = verify_cuts(p) if not a.no_verify else {"skipped": True}
    out({"decisions": r.get("decisions"), "loudness": r.get("loudness"), "metrics": r["metrics"],
         "regions_ms": r["regions_ms"], "pauses": len(q["pauses_ms"]),
         "removed_ms": q["removed_ms"], "new_duration_ms": q["new_duration_ms"], "pause_params": pp,
         "cut_verification": {k: v.get(k) for k in ("ok", "verdict", "coverage", "orig_words", "tight_words", "missing")}})


def cmd_mogrt_build(a):
    from lib.mogrt_builder import build
    out(build(P(a)))


def cmd_ae_script(a):
    from lib.ae_builder import generate
    out(generate(P(a)))


def cmd_ae_build(a):
    from lib.ae_builder import generate, execute
    p = P(a)
    refuse_stale_window(p)
    require_plan_approval(p)
    g = generate(p)
    r = execute(p, Path(g["jsx"]))
    doc = {"generate": g, "execute": r, "warnings": list(g.get("warnings") or [])}
    if r.get("ok") is False:                    # T2.2: a build that saved no project this run exits 1, not 0
        doc["ok"] = False
        doc["status"] = r.get("status")
    out(doc)


def cmd_ae_render(a):
    from lib.ae_builder import render
    out(render(P(a)))


def cmd_ps_script(a):
    from lib.ps_builder import generate
    out(generate(P(a)))


def cmd_ps_build(a):
    from lib.ps_builder import generate, execute
    p = P(a)
    refuse_stale_window(p)
    require_plan_approval(p)
    g = generate(p)
    out({"generate": g, "execute": execute(p, Path(g["jsx"])) if g["jobs"] else "no jobs"})


def cmd_premiere(a):
    from lib.premiere_xml import build_xml
    p = P(a)
    refuse_stale_window(p)
    tm = build_xml(p, prefer_ae_renders=False)   # Premiere-only: brand stills, never stale AE renders
    gen = [x for x in tm["media"]]
    set_status(p, "ASSETS_GENERATED", f"{len(gen)} media referenced", "assets")
    set_status(p, "PROJECT_ASSEMBLED", "FCP7 XML interchange built", "premiere", [tm["xml"]])
    out(tm)


def cmd_qc(a):
    from lib.qc import run_qc
    from lib.motion_config import is_motion
    p = P(a)
    if is_motion(p):
        from lib.motion_qc import run as motion_qc
        r = motion_qc(p)
        set_status(p, "QC_PASSED" if r["ok"] else "BLOCKED", f"{len(r['failed'])} mandatory failures", "qc",
                   [p.p("08_quality_control/qc-results.json")],
                   blockers=[f"{f['check']}: {f['detail']}" for f in r["failed"]])
        out({"ok": r["ok"], "failed": r["failed"], "warnings": [c for c in r["checks"] if c["result"] == "WARN"]})
        return
    r = run_qc(p)
    set_status(p, "QC_PASSED" if r["ok"] else "BLOCKED", f"{len(r['failed'])} mandatory failures", "qc",
               [p.p("08_quality_control/validation-report.md")],
               blockers=[f"{f['check']}: {f['detail']}" for f in r["failed"]])
    out({"ok": r["ok"], "failed": r["failed"],
         "warnings": [c for c in r["checks"] if c["result"] in ("WARN", "MANUAL")]})


def cmd_handoff(a):
    from lib.handoff import build
    from lib.motion_config import is_motion
    p = P(a)
    if is_motion(p):
        from lib.handoff import motion_readme
        r = {"readme": str(motion_readme(p))}
    else:
        r = build(p)
    st = load_status(p)
    if st["status"] == "QC_PASSED":
        set_status(p, "READY_FOR_HUMAN_EDITOR", "handoff package written", "handoff", list(r.values()))
    out(r)


def cmd_status(a):
    out(load_status(P(a)), check=False)      # "status": "BLOCKED" is the project's state, not a failed command


def _has_reference_videos(p: Paths) -> bool:
    inv = read_json(p.output / "discovery/input-inventory.json", {"files": []})
    return any(f["role"] == "editing_reference_video" for f in inv["files"])


def _want_preview(p: Paths) -> bool:
    from lib import settings as S
    return bool(S.load(p.root).get("preview_video", True))


def cmd_next(a):
    """Tell Claude/the user what the next step is (resumable workflow)."""
    from lib.motion_config import is_motion
    p = P(a)
    if is_motion(p):
        from lib.motion_qc import motion_next
        out(motion_next(p), check=False)
        return
    from lib import ref_style
    from lib.people import profile_notice as people_notice
    rs = ref_style.next_step(p)     # Stage 5 is client-level: author once, reuse, flag when the references change
    # references are measured per client: a video that already holds its copy of the style needs no ref-analyze
    need_ref = _has_reference_videos(p) and rs["video"]["state"] not in ("current", "legacy")
    chk = [
        ("discover", p.output / "discovery/input-inventory.json"),
        ("client-db", p.client_db / "branding/brand-tokens.json"),
        ("preflight", p.p("00_inputs/preflight.json")),
        ("transcribe", p.p("02_transcription/transcript.json")),
    ] + ([("ref-analyze", p.p("01_analysis/reference_analysis/reference-measurements.json"))]
         if need_ref else []) + ([(rs["step"], None)] if rs["step"] else []) + [
        ("AUTHOR " + f, p.p(f)) for f in SEMANTIC_FILES if f != STYLE_COPY] + [
        ("plan", p.p("01_analysis/timeline-spec.json")),
        ("previews", p.p("08_quality_control/previews/_contact_sheet.jpg")),
    ] + ([("preview-video (the editor watches the edit)", p.p(f"08_quality_control/preview/{p.video_id}_preview.mp4"))]
         if _want_preview(p) else []) + [
        ("PLAYBACK edit-plan.md to editor, then approve-plan", p.p("01_analysis/plan-approval.json")),
        ("sfx", p.p("06_audio/sfx/sfx-library.json")),
        ("ppro-build (needs Premiere + bridge; fallback: premiere)", p.p(f"07_premiere/project/{p.video_id}_{project_prefix()}_EDIT.prproj")),
        ("ppro-frames, LOOK at every frame, verify --record", p.p("08_quality_control/visual-verification.json")),
        ("qc", p.p("08_quality_control/qc-results.json")),
        ("handoff", p.p("09_handoff/README.md")),
    ]
    todo = [name for name, f in chk if f is None or not Path(f).exists()]
    # a step is STALE when something it depends on changed after it ran (e.g. audio re-cleaned after the plan)
    from lib.verify import prproj_build_time
    prj = p.p(f"07_premiere/project/{p.video_id}_{project_prefix()}_EDIT.prproj")

    def t(f):
        f = Path(f)
        if f == prj and f.exists():
            return prproj_build_time(p, f) or f.stat().st_mtime
        return f.stat().st_mtime if f.exists() else None
    audio, ed = p.p("06_audio/dialogue/pauses.json"), p.p("01_analysis/edit-decisions.json")
    spec, prev = p.p("01_analysis/timeline-spec.json"), p.p("08_quality_control/previews/_contact_sheet.jpg")
    vv, qcr, ho = p.p("08_quality_control/visual-verification.json"), p.p("08_quality_control/qc-results.json"), \
        p.p("09_handoff/README.md")
    pv = p.p(f"08_quality_control/preview/{p.video_id}_preview.mp4")
    deps = [("plan", spec, [audio, ed]), ("previews", prev, [spec]),
            ("preview-video (the editor watches the edit)", pv, [spec, prev]), ("ppro-build --force", prj, [spec, prev]),
            ("ppro-frames, LOOK at every frame, verify --record", vv, [prj]), ("qc", qcr, [vv, prj]),
            ("handoff", ho, [qcr])]
    stale = []
    for name, f, ups in deps:
        tf = t(f)
        if tf is None or name in todo:
            continue
        newer = [u.name for u in ups if t(u) and t(u) > tf + 1]
        if newer or any(s_.split(" (")[0] in [n for n, f2, _ in deps if f2 in ups] for s_ in stale):
            stale.append(f"{name} (older than {', '.join(newer) or 'a stale upstream step'})")
    from lib.plan import approval_state
    appr = approval_state(p) if spec.exists() else None
    if appr and appr["state"] == "stale":            # the approval is for another plan: Gate 1 again, before the build
        k = next((i for i, s_ in enumerate(stale) if s_.startswith(("ppro-build", "ppro-frames", "qc", "handoff"))),
                 len(stale))
        stale.insert(k, f"PLAYBACK edit-plan.md to editor, then approve-plan ({appr['message']})")
    todo = [s_ for s_ in stale] + [n for n in todo if n not in [s_.split(" (")[0] for s_ in stale]]
    status = load_status(p)["status"]
    from lib.common import DONE_STATUSES
    if stale and status in DONE_STATUSES:
        status = f"{status} (STALE: inputs changed since)"
    out({"status": status, "profile": active_profile(p.root), "next": todo[0] if todo else "done",
         "remaining": todo, "stale": stale,
         "reference_style": {"state": rs["client"]["state"], "video": rs["video"]["state"], "message": rs["client"]["message"]},
         "notices": rs["notices"] + [n for n in (people_notice(p.root),) if n]}, check=False)


EXTRAS = {"ae-script", "ae-build", "ae-render", "ps-script", "ps-build", "mogrt-build"}
NO_ROOT = {"setup", "doctor", "py", "model-download", "gpu-enable", "bench", "ppro-install", "ppro-status", "ppro-probe", "profile", "scaffold", "settings",
           "ae-status", "ae-probe", "motion-icons", "motion-library", "validate"}
NO_ID = NO_ROOT | {"discover", "client-db", "client-init", "mogrt-build", "inbox", "lock"}
OPTIONAL_ID = {"ref-analyze", "ref-style"}   # client-level without a video id (onboarding), per video with one

# One writer per client folder (3.0 T1.8). Every command chooses (test_writer_lock checks each is in exactly one):
#   CORE_WRITES  write into the client folder: take or refresh the session's lease on output/.whynot-lock
#                (lib/writer_lock.py); another session's writers are refused until the lease ends
#   CORE_READS   never write into the client folder (machine-level commands write only in the engine home); `lock`
#                manages the lock itself and never takes it (`--release` is the escape hatch, lead only)
#   WRITES_IF    write only with a flag. inbox: `--no-refresh` reads the last discovery (its clip-ids map and probe
#                cache are deterministic caches) but runs discovery when there is none yet, so it writes then.
# scaffold creates a new folder: there is nothing to lock yet (it runs before the lock is taken).
CORE_WRITES = {"scaffold", "client-init", "discover", "client-db", "ref-analyze", "preflight", "transcribe",
               "transcript-correct", "transcript-verify", "transcript-relisten", "audio-clean", "plan",
               "approve-plan", "previews", "sfx", "preview-video", "ppro-build", "ppro-frames", "premiere", "verify",
               "qc", "handoff", "mogrt-build", "ae-script", "ae-build", "ae-render", "ps-script", "ps-build"}
# doctor: --fix writes only the idempotent .whynot-client at client roots (outside output/), so it takes no lease
# and works while another session holds the client (gate G2).
CORE_READS = {"setup", "py", "model-download", "gpu-enable", "bench", "profile", "ppro-install", "ppro-status", "ppro-probe",
              "status", "next", "lock", "doctor", "validate"}
WRITES_IF = {
    "inbox": lambda a: not a.no_refresh or not (Path(a.root or ".").expanduser()
                                                / "output/discovery/input-inventory.json").exists(),
    "settings": lambda a: bool(a.init),
    "range": lambda a: bool(a.footage),
    "ref-style": lambda a: bool(a.record or a.apply),
}


def writes(a) -> bool:
    """Does this invocation write into the client folder (and so need the one-writer lock)?"""
    from lib import motion_cli, podcast_cli
    if a.cmd in WRITES_IF:
        return WRITES_IF[a.cmd](a)
    return a.cmd in CORE_WRITES or a.cmd in podcast_cli.WRITES or a.cmd in motion_cli.WRITES


def mark_legacy_client(root: Path):
    """A 2.x client folder (assets/ + data/ + output/ with a WhyNot Cut sign, no `.whynot-client`) gets its marker on
    the first writing command, so the guard protects it from then on (gate G5). Idempotent; logged in
    output/logs/pipeline.log."""
    from lib.client_marker import MARKER, write_marker
    if (root / MARKER).exists() or not (root / "output").is_dir():
        return
    signs = ("output/discovery", "output/projects", "output/client_database", "output/logs/pipeline.log",
             "START_HERE.md")                     # WhyNot Cut worked here before (fix round 2): not just any output/
    if not any((root / s_).exists() for s_ in signs):
        return
    try:
        if write_marker(root):
            from lib import writer_lock
            writer_lock.client_log(root, f"wrote {MARKER} at the client root (a 2.x client folder without the marker):"
                                         " the guard now protects its assets/ and data/")
    except (OSError, ValueError):
        pass


def take_writer_lock(a):
    """Take or refresh the session's lease on the client for a writing command (None for readers and commands
    without a client folder). Another session's live lease -> `{"blocked", "how"}` and exit 2."""
    if not a.root or not writes(a):
        return None
    root = Path(a.root).expanduser()
    if not ((root / "assets").is_dir() and (root / "data").is_dir()):
        return None                       # not a client folder: the command reports that itself
    from lib import writer_lock
    mark_legacy_client(root)
    shown = ["reel", a.cmd] + [f"{o} {v}" for o, v in (("--video-id", a.video_id), ("--episode", a.episode)) if v]
    try:
        return writer_lock.acquire(root, " ".join(shown))
    except writer_lock.Busy as e:
        out(e.refusal())
        raise SystemExit(2)


def cmd_lock(a):
    """One writer per client folder: show the lock (--status, the default) or remove it (--release, the lead only,
    when the editor says the other session is finished or stuck)."""
    from lib import writer_lock
    out(writer_lock.release(a.root) if a.release else writer_lock.status(a.root))


def run_setup_env(force=False, check=False) -> dict:
    """setup/setup_env.py in a child process (stdlib only, so any engine python runs it): builds or repairs the
    isolated runtime from the platform's hash lock and switches `current` after a smoke import (3.0 T2.1).
    Progress goes to stderr; returns its JSON report."""
    import subprocess
    from lib.common import PLUGIN_DIR, engine_home
    cmd = [sys.executable, "-s", str(PLUGIN_DIR / "setup" / "setup_env.py"), "--home", str(engine_home())]
    cmd += ["--force"] * force + ["--check"] * check
    r = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {"ok": False, "error": f"setup_env.py exit {r.returncode} without a report", "detail": r.stdout[-2000:]}


def doctor_in_engine() -> dict:
    """The doctor report from the engine's own interpreter: in this process when it is the current runtime, else
    (setup just built a runtime while the legacy venv runs this command) from the runtime's python."""
    import subprocess
    from lib import plat
    from lib.common import engine_home
    from lib.onboard import doctor
    rt = plat.engine_runtime(engine_home())
    if rt["kind"] != "runtime" or Path(sys.prefix).resolve() == Path(rt["dir"]).resolve():
        return doctor()
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([str(rt["python"]), "-s", str(Path(__file__).resolve()), "doctor"], stdout=subprocess.PIPE,
                       text=True, encoding="utf-8", errors="replace", env=env)
    try:
        return json.loads(r.stdout)
    except ValueError:
        rep = doctor()
        rep["fixes"].append({"item": f"the new runtime's doctor did not run (exit {r.returncode})", "who": "claude",
                             "fix": "reel doctor   (in a new command, so it runs on the new runtime)"})
        return rep


def cmd_setup(a):
    """Idempotent machine setup and repair: the isolated runtime (built or re-synced from the hash lock), the
    Premiere bridge, then the doctor report (never changes Adobe prefs)."""
    from lib.ppro_bridge import install
    from lib.errors import Guidance
    from lib import plat
    rep = {"runtime": run_setup_env(force=a.force, check=a.check)}
    if a.check:
        out(rep)
        return
    skipped = None
    if not a.no_bridge:
        have = None
        for key in ("premiere", "after_effects"):       # one bundle serves both
            try:    # a stale WHYNOT_PREMIERE_APP / _AE_APP is the doctor's fix to list, not a reason to lose the report
                have = have or plat.newest_app(key)
            except Guidance as e:
                skipped = skipped or e
        if have:
            rep["bridge_install"] = install()
        elif skipped:
            rep["bridge_install"] = f"skipped: {skipped.error}"
        else:
            rep["bridge_install"] = "skipped: Premiere Pro or After Effects not found on this computer"
    rep["doctor"] = doctor_in_engine()
    fixes = rep["doctor"].get("fixes") or []
    if skipped and not any(f.get("item") == skipped.error for f in fixes):
        fixes.append({"item": skipped.error, "who": "editor", "fix": skipped.how})
    if not rep["runtime"].get("ok"):
        fixes.insert(0, {"item": "engine runtime: " + str(rep["runtime"].get("error") or "not ready"),
                         "who": "claude", "fix": rep["runtime"].get("how") or "reel setup"})
    rep["next"] = [f["fix"] for f in fixes] or ["all set: run /whynot-cut:start or reel inbox"]
    out(rep)


PY_USAGE = "reel py <script.py> [args] | reel py -m <module> [args] | reel py -c <code> [args]"


GLOBAL_VALUE_OPTS = ("--root", "--video-id", "--profile", "--episode")


def py_argv(argv: list[str]) -> list[str] | None:
    """The script arguments when the command is `py`, also after global options (`reel --root X py -c ...`; they do
    not apply to the script), else None."""
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in GLOBAL_VALUE_OPTS:
            i += 2
        elif a.startswith(tuple(o + "=" for o in GLOBAL_VALUE_OPTS)):
            i += 1
        else:
            return argv[i + 1:] if a == "py" else None
    return None


def cmd_py(a):
    """Run Python with the engine runtime (3.0 T2.1 / T2.16): engine packages and the engine's `lib` importable,
    user site off when the engine runs that way. Output and exit code are the script's own."""
    import subprocess
    args = list(a.pyargs or [])
    if args[:1] == ["--"]:
        args = args[1:]
    if not args or args[0] in ("-h", "--help"):
        out({"error": "reel py needs a script, -m <module> or -c <code>", "how": PY_USAGE})
        raise SystemExit(2)
    env = dict(os.environ)
    here = str(Path(__file__).resolve().parent)
    env["PYTHONPATH"] = os.pathsep.join([here] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    flags = ["-s"] if sys.flags.no_user_site else []
    sys.stdout.flush()
    raise SystemExit(subprocess.run([sys.executable, *flags, *args], env=env).returncode)


def cmd_model_download(a):
    """Download a Whisper model into the engine home once (ask the editor first: large-v3 is about 3 GB)."""
    import time
    from faster_whisper.utils import download_model
    from lib.onboard import whisper_model_state
    t0 = time.time()
    path = download_model(a.model, cache_dir=str(models_dir()))
    out({"model": a.model, "path": path, "elapsed_s": round(time.time() - t0, 1), "state": whisper_model_state()})


def cmd_bench(a):
    """Whisper speed on this machine (3.0 T2.12): decode --seconds of --audio (default: the project's own audio with
    --root and --video-id / --episode) once and cache the real-time factor for `reel doctor`."""
    from lib.whisper_backends import cli_bench
    out(cli_bench(a, P(a) if a.root and (a.video_id or a.episode) else None))


# The cuBLAS wheel, pinned and hash-checked like the rest of the runtime (T2.15 review m-7): 12.9.1 is the library
# plat.install_cuda_redist takes from NVIDIA (redistrib_12.9.1.json); the locked ctranslate2 4.8.2 (CUDA 12 build, no
# torch in the runtime) loads cublas64_12 / libcublas.so.12 of any CUDA 12.x. Hashes: PyPI's win_amd64,
# manylinux x86_64 and aarch64 wheels.
CUDA_WHEEL_PINS = {"nvidia-cublas-cu12": ("12.9.1.4", (
    "1e5fee10662e6e52bd71dec533fbbd4971bb70a5f24f3bc3793e5c2e9dc640bf",
    "453611eb21a7c1f2c2156ed9f3a45b691deda0440ec550860290dc901af5b4c2",
    "7a950dae01add3b415a5a5cdc4ec818fb5858263e9cca59004bb99fdbbd3a5d6"))}


def cuda_wheel_install(pkgs: list[str], home: Path | None = None) -> tuple[list | None, dict | None, str]:
    """(argv, env, via) installing the cuBLAS wheels into the engine runtime (T2.15): uv-built runtimes have no pip,
    so the pinned uv of the engine home installs with `uv pip install --python <runtime python>`; a 2.x venv
    (pip inside) uses pip. (None, None, "") when neither is possible. Pinned packages (CUDA_WHEEL_PINS) go through a
    hash-checked requirements file in <home>/cache when every package has hashes (Windows), else as `name==version`;
    components.json `runtime.index_url` is the index when set (UV_NO_CONFIG hides any other uv config). A runtime
    sync (`reel setup` after an update) removes these wheels again: doctor then names `reel gpu-enable` again."""
    import subprocess
    from lib import plat
    from lib.common import engine_home
    from lib.runtime import components
    home = home or engine_home()
    rt = plat.engine_runtime(home)
    py = str(rt["python"]) if rt.get("kind") == "runtime" and rt.get("python") else sys.executable
    specs = [f"{p}=={CUDA_WHEEL_PINS[p][0]}" if p in CUDA_WHEEL_PINS else p for p in pkgs]
    if all(p in CUDA_WHEEL_PINS for p in pkgs):
        req = home / "cache" / "gpu-enable-requirements.txt"
        req.parent.mkdir(parents=True, exist_ok=True)
        req.write_text("".join(f"{s} " + " ".join(f"--hash=sha256:{h}" for h in CUDA_WHEEL_PINS[p][1]) + "\n"
                               for p, s in zip(pkgs, specs)), encoding="utf-8")
        what = ["--require-hashes", "-r", str(req)]
    else:
        what = specs
    idx = (components().get("runtime") or {}).get("index_url")
    idx = ["--index-url", idx] if isinstance(idx, str) and idx and not idx.startswith("<") else []
    uv = home / "bin" / ("uv.exe" if plat.IS_WIN else "uv")
    if uv.is_file():
        env = dict(os.environ, UV_CACHE_DIR=str(home / "cache" / "uv"), UV_NO_CONFIG="1", UV_HTTP_TIMEOUT="60",
                   UV_HTTP_RETRIES="5")
        return [str(uv), "pip", "install", "--python", py, *idx, *what], env, "uv pip"
    try:
        has_pip = subprocess.run([py, "-m", "pip", "--version"], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        has_pip = False
    if has_pip:
        return [py, "-m", "pip", "install", "--disable-pip-version-check", *idx, *what], None, "pip"
    return None, None, ""


def cmd_gpu_enable(a):
    """Install NVIDIA's cuBLAS 12 (pip wheel, ~550 MB) into the engine so Whisper runs on an NVIDIA GPU.
    Ask the editor first. macOS has no CUDA: Whisper stays on the CPU there."""
    import subprocess
    from lib import plat
    before = plat.gpu_info()
    if plat.IS_MAC or not before.get("cuda_devices"):
        out({"gpu": before, "installed": [], "note": "no NVIDIA GPU visible to CTranslate2: nothing to install"})
        return
    pkgs = plat.CUDA_PIP["windows" if plat.IS_WIN else "linux"]
    how, installed, redist_error = None, [], None
    if before.get("cuda_libs_missing") and plat.IS_WIN:
        try:   # NVIDIA's own CDN: much faster than PyPI here, sha256-checked
            r = plat.install_cuda_redist(log=lambda m: print(m, file=sys.stderr))
            how, installed = "nvidia-redist", r["installed"]
        except Exception as e:  # noqa: BLE001
            redist_error = f"{type(e).__name__}: {e}"
    if before.get("cuda_libs_missing") and not installed:
        cmd, env, how = cuda_wheel_install(pkgs)
        if not cmd:
            from lib.errors import Guidance
            raise Guidance("the cuBLAS wheels cannot be installed: the engine runtime has no pip and the pinned uv is "
                           "missing" + (f" (NVIDIA download: {redist_error})" if redist_error else ""),
                           "run `reel setup` (it puts the pinned uv in the engine home), then `reel gpu-enable` again; "
                           "Whisper keeps using the CPU meanwhile")
        r = subprocess.run(cmd, env=env)
        if r.returncode:
            raise SystemExit(f"{how} install {' '.join(pkgs)} failed (exit {r.returncode}); Whisper keeps using the CPU"
                             + (f" (NVIDIA download: {redist_error})" if redist_error else ""))
        installed = pkgs
    after = plat.gpu_info()
    out({"gpu_before": before, "gpu": after, "installed": installed, "via": how, "redist_error": redist_error,
         "whisper_device": after.get("whisper_device")})


def cmd_doctor(a):
    """Machine report; also the `.whynot-client` markers of --root / the current client folder / clients_root.
    --fix writes the missing marker only for --root or the current client folder (G70: never every client of
    clients_root); --fix --all-clients lists the unmarked clients and writes them only with --yes."""
    from lib.onboard import client_markers, doctor, marker_roots, own_marker_roots
    rep = doctor()
    roots, own = marker_roots(a.root), own_marker_roots(a.root)
    every = a.fix and a.all_clients
    fix_roots = (roots if a.yes else []) if every else own if a.fix else []
    cm = rep["client_markers"] = client_markers(roots, fix_roots)
    if every and not a.yes:
        rep["how"] = ("nothing written: these client folders have no .whynot-client marker (client_markers.missing). "
                      "Show the list to the editor; with their OK run `reel doctor --fix --all-clients --yes`.")
    if cm["missing"]:
        mine = {str(r) for r in own}
        unprot = set(cm["unprotected"])
        hint = (f'reel doctor --fix --root "{cm["missing"][0]}"' if set(cm["missing"]) <= mine
                else "reel doctor --fix --all-clients")
        rep["fixes"].append({"item": "client folder(s) without the .whynot-client marker: " + ", ".join(
            f"{m} ({'NOT protected by the guard' if m in unprot else 'protected by clients_root or client_database only'})"
            for m in cm["missing"]), "who": "claude", "fix": hint})
    out(rep)


def cmd_scaffold(a):
    from lib.onboard import scaffold
    if not a.root:
        raise SystemExit("--root required: the new client folder to create, e.g. --root \"D:/Clients/Dr Sherif\"")
    out(scaffold(Path(a.root), a.name))


def cmd_inbox(a):
    from lib.onboard import inbox
    out(inbox(Path(a.root), refresh=not a.no_refresh))


def cmd_preview_video(a):
    from lib.preview_video import render
    p = P(a)
    refuse_stale_window(p)
    out(render(p, width=a.width, label=not a.no_label))


def cmd_settings(a):
    from lib import settings as S
    from lib.plat import native_path
    st = S.load(Path(a.root) if a.root else None)
    if a.init:
        folder = Path(native_path(a.init)).expanduser().resolve()
        target = folder / ".claude" / S.FILE
        if target.exists() and not a.force:
            raise SystemExit(f"{target} exists (use --force to rewrite it; your values are kept unless overridden)")
        base = S.load(folder) if target.exists() else dict(S.DEFAULTS)   # never copy another folder's values
        vals = {k: v for k, v in base.items() if not k.startswith("_")}
        st = base
        for kv in a.set or []:
            k, _, v = kv.partition("=")
            k, val = k.strip(), S._parse_scalar(v)
            if k not in S.DEFAULTS:
                raise SystemExit(f"unknown preference {k!r}; known: {', '.join(S.DEFAULTS)}")
            if k in S.CHOICES and str(val) not in S.CHOICES[k]:
                raise SystemExit(f"{k}={val!r} is not one of {sorted(S.CHOICES[k])}")
            if isinstance(S.DEFAULTS[k], bool) and not isinstance(val, bool):
                raise SystemExit(f"{k} must be true or false")
            vals[k] = val
        S.save(target, vals, st.get("_notes", ""))
        st = S.load(folder)
    out(st)


def cmd_profile(a):
    """Show which client profile applies and where its values come from."""
    from lib.common import shipped_profiles
    root = Path(a.root).expanduser().resolve() if a.root else None
    out({"active": active_profile(root) if root else None,
         "layers": ["config/defaults"] + [str(d) for d in profile_dirs(root)] if root else ["config/defaults"],
         "shipped_profiles": shipped_profiles(), "prefix": project_prefix()})


def cmd_client_init(a):
    """Create <client>/output/client_database/reel-profile/ from a shipped profile or the blank template."""
    import shutil
    p = Path(a.root).expanduser().resolve()
    dst = p / CLIENT_PROFILE_REL
    if dst.exists() and any(dst.iterdir()) and not a.force:
        raise SystemExit(f"{dst} already exists (use --force to refresh from the template; existing files are kept as *.bak)")
    src = PROFILES_DIR / (a.from_profile or "_template")
    if not src.is_dir():
        raise SystemExit(f"unknown profile {a.from_profile!r}; shipped: {[d.name for d in PROFILES_DIR.iterdir() if d.is_dir()]}")
    dst.mkdir(parents=True, exist_ok=True)
    written = []
    for f in src.iterdir():
        if f.name.startswith(".") or not f.is_file():
            continue
        t = dst / f.name
        if t.exists():
            t.rename(t.with_suffix(t.suffix + ".bak"))
        shutil.copy2(f, t)
        written.append(str(t))
    pj = read_json(dst / "profile.json", {})
    pj["id"] = a.id
    if a.prefix:
        pj["prefix"] = a.prefix
    write_json(dst / "profile.json", pj)
    from lib.client_marker import MARKER, write_marker
    try:
        write_marker(p)                   # the guard and the session hook recognise the client folder by it
    except ValueError as e:
        print(f"note: {e}", file=sys.stderr)
    out({"profile_dir": str(dst), "id": a.id, "from": src.name, "files": written, "marker": str(p / MARKER),
         "next": "Fill brand.json / transcription.json / glossary / notes.md from the client's own documents (never invent)."})


def _utf8_stdio():
    """Arabic in JSON output must not crash on Windows, where pipes default to the ANSI code page."""
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# The command table: every core subcommand with the one line `reel --help` shows (podcast and motion commands carry
# theirs in lib/podcast_cli.HELP and lib/motion_cli.HELP). Order = the order of the editing workflow.
CORE_COMMANDS: dict[str, str] = {
    "doctor": "machine report (engine, ffmpeg, Premiere bridge, PATH, guard, client markers); --fix marks this client",
    "setup": "install or repair the engine runtime (hash-locked), ffmpeg and the Premiere bridge (idempotent)",
    "py": "run Python with the engine runtime: reel py <script.py> | -m <module> | -c <code> [args]",
    "scaffold": "create a client folder (assets/, data/, START_HERE.md, .whynot-client)",
    "inbox": "list the new raw clips of a client folder and their video ids",
    "settings": "show or change the editor's WhyNot Cut preferences",
    "model-download": "download a Whisper model once (large-v3 is about 3 GB)",
    "gpu-enable": "install NVIDIA cuBLAS so Whisper runs on an NVIDIA GPU",
    "bench": "measure how fast Whisper runs on this computer (real-time factor, shown by doctor)",
    "profile": "show which client profile applies and where its values come from",
    "client-init": "create the client's reel-profile from a shipped profile or the blank template",
    "discover": "inventory of the client folder: inputs, footage, brand files, environment",
    "client-db": "client database: brand colours, fonts, photos and assets",
    "ref-analyze": "measure the client's reference edits",
    "ref-style": "show, record or apply the client's reference editing style",
    "preflight": "inspect the raw footage (streams, frame rate, audio) before editing",
    "range": "set or show the in/out range of a reel cut from a longer raw file",
    "transcribe": "word-timed Whisper transcript (SRT and words) of the clip",
    "transcript-correct": "apply proofread corrections to the transcript",
    "transcript-verify": "record that the transcript was proofread",
    "transcript-relisten": "re-transcribe flagged words from the audio",
    "audio-clean": "clean the dialogue and remove pauses, with before/after measurements",
    "plan": "validate and compile edit-decisions.json into the build plan",
    "validate": "check an authored JSON file (edit-decisions, reels-plan, motion-script, publish...) against its schema",
    "approve-plan": "record the approval of the compiled plan (editor or delegated)",
    "previews": "render PNG previews of the graphics and captions, with QC composites",
    "sfx": "prepare the sound effects the plan needs: the client's mapped library files (06_audio/sfx-map.json) "
           "converted to wav, built-in synthesized sounds for the rest",
    "preview-video": "render a watchable MP4 of the planned edit (no Premiere needed)",
    "ppro-install": "install the Premiere bridge (WhyNot Cut Bridge CEP panel)",
    "ppro-status": "is Premiere running and the bridge answering",
    "ppro-probe": "probe the Premiere bridge (what the host reports back)",
    "ppro-build": "build the native Premiere project through the bridge",
    "ppro-frames": "export frames from the built Premiere timeline for QC",
    "premiere": "write the FCP7 XML interchange (fallback when the bridge cannot be used)",
    "verify": "build the evidence sheet of the Premiere frames, or --record the verdict after viewing it",
    "qc": "run the QC checks on the build and write the report",
    "handoff": "write the editor handoff for a finished or paused edit",
    "status": "show the project status record",
    "next": "what the next step is (resumable workflow), with stale-input warnings",
    "lock": "one writer per client folder: show (--status) or release (--release, lead only) output/.whynot-lock",
    "mogrt-build": "build MOGRT templates (extra: needs --extras and an explicit editor request)",
    "ae-script": "write the After Effects script (extra: needs --extras)",
    "ae-build": "build the After Effects project (extra: needs --extras)",
    "ae-render": "render the After Effects project (extra: needs --extras)",
    "ps-script": "write the Photoshop script (extra: needs --extras)",
    "ps-build": "build the Photoshop file (extra: needs --extras)",
}


def command_table() -> dict[str, str]:
    """Every registered subcommand (core, podcast, motion) -> its one-line help, in listing order."""
    from lib import motion_cli, podcast_cli
    return {**CORE_COMMANDS, **podcast_cli.HELP, **motion_cli.HELP}


def registered_commands() -> list[str]:
    """The subcommand names main() registers: the command table's keys (core in `CORE_COMMANDS`, plus the
    podcast and motion ARGS keys)."""
    from lib import motion_cli, podcast_cli
    return [*CORE_COMMANDS, *podcast_cli.ARGS, *motion_cli.ARGS]


def main(argv: list[str] | None = None):
    argv = sys.argv[1:] if argv is None else list(argv)
    _utf8_stdio()
    import os
    # Hugging Face "Xet" transfers died on a Windows test machine (WinError 10038) and left 3 MB partial model caches;
    # plain HTTPS downloads work everywhere. WHYNOT_HF_XET=1 turns Xet back on.
    if os.environ.get("WHYNOT_HF_XET") != "1":
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from lib.common import PLUGIN_DIR
    from lib.selfid import tag

    class NamedParser(argparse.ArgumentParser):      # usage errors say which plugin's `reel` this is (G66)
        def error(self, message):
            self.print_usage(sys.stderr)
            self.exit(2, f"{tag()}: {self.prog}: error: {message}\n")
    ap = NamedParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"{tag()}\nplugin root: {PLUGIN_DIR}",
                    help="print the plugin name and version, and the plugin folder")
    ap.add_argument("--root", help="client folder containing assets/ and data/ (default: current folder if it has both)")
    ap.add_argument("--video-id", help="stable project id (default: footage file stem)")
    ap.add_argument("--profile", help="shipped profile id to apply (default: the id in the client's own reel-profile; never matched by folder name)")
    ap.add_argument("--episode", help="podcast episode id (`reel episodes` lists them)")
    from lib import motion_cli, podcast_cli
    table = command_table()
    sub = ap.add_subparsers(dest="cmd", required=True, title="commands", metavar="<command>")
    for name in registered_commands():
        sp = sub.add_parser(name, help=table[name], description=table[name])
        # global options are accepted after the command too (`reel next --root X`), as the skills write them
        sp.add_argument("--root", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--video-id", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--profile", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--episode", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        podcast_cli.add_args(name, sp)
        motion_cli.add_args(name, sp)
        if name in ("preflight", "transcribe"):
            sp.add_argument("--footage")
        if name == "ppro-install":
            sp.add_argument("--force", action="store_true", help="replace an installed bridge that is newer")
        if name == "transcribe":
            sp.add_argument("--model", default=None, help="default: preferences whisper_model, else large-v3")
            sp.add_argument("--language", default=None)
            sp.add_argument("--force", action="store_true")
        if name in ("transcribe", "bench"):
            from lib.whisper_backends import add_cli_args
            add_cli_args(name, sp)
        if name == "range":
            sp.add_argument("--footage", help="the longer raw file, e.g. data/Raw/EP02.mp4 (omit to show the range)")
            sp.add_argument("--in", dest="start", default="0", help="in-point: 02:04, 00:02:04.500 or seconds")
            sp.add_argument("--out", dest="end", default=None, help="out-point (default: end of file)")
            sp.add_argument("--label", help="e.g. the reel's name in the client's plan")
            sp.add_argument("--snap", action="store_true", help="move in/out to the nearest pause (never mid-word)")
        if name == "transcript-relisten":
            sp.add_argument("--words", help="word ids, e.g. 79,80 (default: every flagged word)")
            sp.add_argument("--model", default=None)
        if name == "transcript-verify":
            sp.add_argument("--by")
            sp.add_argument("--note")
        if name == "audio-clean":
            sp.add_argument("--min-pause", type=int, default=None,
                            help="ms (default: the reel's recipe, else the profile's style.json remove_pauses, else 250)")
            sp.add_argument("--pad", type=int, default=None, help="ms of breath kept at each cut (default as above, else 80)")
            sp.add_argument("--no-verify", action="store_true")
            sp.add_argument("--nr", type=float, default=None,
                            help="denoise strength in dB (default: 24, or none when the source is already clean; gentler: 16)")
            sp.add_argument("--hum", default="auto", choices=["auto", "off", "50", "60"],
                            help="mains-hum notches: measured (auto), none, or every harmonic of 50/60 Hz up to 500 Hz")
            sp.add_argument("--expander", action="store_true", help="gentle downward expander between words (more noise reduction, can sound choppy)")
        if name == "ppro-build":
            sp.add_argument("--force", action="store_true")
            sp.add_argument("--replace-edited", action="store_true",
                            help="rebuild even though the editor saved changes in Premiere (only with their OK)")
        if name == "ppro-frames":
            sp.add_argument("--pending-retries", type=int, default=3,
                            help="re-exports of frames that came out as Premiere's 'Media pending' slate (0 = only report them)")
            sp.add_argument("--pending-wait", type=float, default=5.0,
                            help="seconds to wait before the first re-export (2x before the second, ...)")
        if name == "approve-plan":
            sp.add_argument("--by", required=True, choices=["editor", "delegated"])
            sp.add_argument("--note")
        if name == "verify":
            sp.add_argument("--record", action="store_true")
            sp.add_argument("--verdict", choices=["pass", "fail"])
            sp.add_argument("--notes")
            sp.add_argument("--by")
            sp.add_argument("--sheet", help="evidence image to record against (e.g. Premiere frame sheet)")
        if name in EXTRAS:
            sp.add_argument("--extras", action="store_true", help="confirm the editor explicitly asked for After Effects/Photoshop")
        if name == "setup":
            sp.add_argument("--no-bridge", action="store_true")
            sp.add_argument("--force", action="store_true", help="re-install the runtime from the lock even when it matches")
            sp.add_argument("--check", action="store_true", help="report what setup would do; change nothing")
        if name == "py":
            sp.add_argument("pyargs", nargs=argparse.REMAINDER, help="a script, -m <module> or -c <code>, then its args")
        if name == "doctor":
            sp.add_argument("--fix", action="store_true",
                            help="write the missing .whynot-client marker of --root or the current client folder "
                                 "(never in assets/ or data/)")
            sp.add_argument("--all-clients", action="store_true",
                            help="with --fix: every client of clients_root (lists them; writes only with --yes)")
            sp.add_argument("--yes", action="store_true", help="with --fix --all-clients: write the markers")
        if name == "client-init":
            sp.add_argument("--id", required=True, help="profile id, kebab-case, e.g. dr-sherif")
            sp.add_argument("--from-profile", help="copy a shipped profile instead of the blank template")
            sp.add_argument("--prefix", help="file-name tag, e.g. SH -> C0001_SH_EDIT.prproj")
            sp.add_argument("--force", action="store_true")
        if name == "ref-style":
            sp.add_argument("--record", action="store_true",
                            help="record the client style files as written from the current reference edits")
            sp.add_argument("--apply", action="store_true",
                            help="copy the current client style (+ 01_analysis/editing-style-overrides.json) into the video")
            sp.add_argument("--by", help="who wrote the client style (e.g. client-researcher)")
        if name == "previews":
            sp.add_argument("--no-composite", action="store_true")
        if name == "validate":
            sp.add_argument("file", help="the JSON file, e.g. 01_analysis/edit-decisions.json")
            sp.add_argument("--kind", help="edit-decisions | reels-plan | motion-script | publish | publish-reel | "
                                           "transcript-corrections | asset-needs (default: from the file name)")
        if name == "model-download":
            sp.add_argument("--model", default="large-v3", choices=["large-v3", "large-v3-turbo", "medium", "small"])
        if name == "scaffold":
            sp.add_argument("--name", help="client display name for START_HERE.md")
        if name == "inbox":
            sp.add_argument("--no-refresh", action="store_true", help="use the last discovery instead of rescanning")
        if name == "preview-video":
            sp.add_argument("--width", type=int, default=540)
            sp.add_argument("--no-label", action="store_true")
        if name == "settings":
            sp.add_argument("--init", metavar="FOLDER", help="write FOLDER/.claude/whynot-cut.local.md")
            sp.add_argument("--set", action="append", metavar="KEY=VALUE")
            sp.add_argument("--force", action="store_true")
        if name == "lock":
            g = sp.add_mutually_exclusive_group()
            g.add_argument("--status", action="store_true", help="who holds the lock, since when, stale or not (default)")
            g.add_argument("--release", action="store_true",
                           help="remove the lock (lead only, when the editor says the other session is finished)")
    pyargs = py_argv(argv)
    if pyargs is not None:          # everything after `py` belongs to the script (argparse would read its -m / -c)
        cmd_py(argparse.Namespace(cmd="py", pyargs=pyargs))
        return
    a = ap.parse_args(argv)
    try:
        start(a)
    except Exception as e:  # noqa: BLE001 — 3.0 T2.2 (IM-7): guidance JSON and exit 1, never a traceback
        fail(a, e)


def start(a):
    """Gates, the client folder, the writer lock, then the command (main() turns any exception into guidance)."""
    if a.cmd in EXTRAS and not a.extras:
        out({"blocked": f"`{a.cmd}` is an optional After Effects/Photoshop extra. The default pipeline is Premiere only.",
             "how": "Only if the editor explicitly asked for AE/PS in this conversation, re-run with --extras."})
        raise SystemExit(2)
    a.root = resolve_root(a.root)
    if a.cmd == "scaffold":
        globals()["cmd_scaffold"](a)
        return
    if not a.root and a.cmd not in NO_ROOT:
        cwd = Path.cwd()
        if (cwd / "assets").is_dir() and (cwd / "data").is_dir():
            a.root = str(cwd)
        else:
            known = [p.name for p in client_folders(clients_root())]
            raise SystemExit("--root required (client folder containing assets/ and data/)"
                             + (f"; client folders in {clients_root()}: {', '.join(known)}" if known else ""))
    a.ctx = set_context(a.root, a.profile)      # the request's Context, passed down where practical (T2.17)
    lock = take_writer_lock(a)
    try:
        run(a)
    finally:
        if lock:
            lock.release()


def run(a):
    """Dispatch the parsed command (inside the client's writer lock when it writes)."""
    from lib import motion_cli, podcast_cli
    if a.cmd in podcast_cli.ARGS:
        podcast_cli.dispatch(a)
        return
    if a.cmd in motion_cli.ARGS:
        motion_cli.dispatch(a)
        return
    if not a.video_id and a.cmd not in NO_ID and not a.episode:
        inv = read_json(Path(a.root).expanduser() / "output/discovery/input-inventory.json")
        src = [f for f in (inv or {}).get("files", []) if f["role"] == "source_footage"]
        if len(src) == 1:
            from lib.clip_ids import clip_ids, id_of
            a.video_id = id_of(clip_ids(a.root, inv), src[0]["rel"])
        else:
            if a.cmd not in OPTIONAL_ID:
                raise SystemExit("--video-id required (found %d source files; `reel inbox` lists them)" % len(src))
    canonical_video_id(a)
    globals()["cmd_" + a.cmd.replace("-", "_")](a)


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:        # G66: every message says which plugin's `reel` it came from
        if isinstance(e.code, str):
            from lib.selfid import tag
            sys.stderr.write(f"{tag()}: {e.code}\n")
            sys.exit(1)
        raise
