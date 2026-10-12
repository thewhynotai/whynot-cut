"""The engine state `reel serve` shows in the panel (3.0 Addendum C2.3 / C2.4). Read only: nothing here writes a file.

active.json
    <engine home>/state/active.json (contract/engine_state.schema.json): {client_root, item, stage, session_id,
    claude_pid, at}. The `reel` writer commands write it (T6.2b, the executor's part). It is read defensively. Each of
    these means "no item": a missing file, one over ACTIVE_MAX (64 KiB), one that is not UTF-8 JSON or breaks the
    schema, an `at` more than STALE_S (12 h) old or more than SKEW_S in the future, a client_root that is relative, has
    a '..' segment or is not a folder, an item that is not one plain folder name (lib/common.py:420
    check_project_id), and an item folder that resolves outside <client_root>/output/projects.

PanelState from the item's evidence files (panel_fields)
    Every path is relative to the item folder <client_root>/output/projects/<item> (lib/common.py:449 Paths) and is the
    one the engine's own writer uses; no file is invented. A file that is missing, over EVIDENCE_MAX or not a JSON
    object reads as "not there". A motion item is one whose 00_inputs/source.json has kind "motion_reel"
    (lib/motion_config.py:24-31). Line numbers are those of release/3.0 at 57d3211 (engine/reel/...).
      transcript  02_transcription/transcript.json exists (cli.py:822, cmd_next)
      plan        01_analysis/timeline-spec.json exists (cli.py:826); motion: 01_analysis/motion-plan.json exists and
                  motion-validation.json `ok` is true, failed when false (motion_qc.py:195, motion_plan.py:744-746)
      approve     lib/plan.py approval_state (plan.py:945) over 01_analysis/plan-approval.json {approved, by, at,
                  plan_fingerprint, format[, kind]} (cli.py:488, 496): "current" -> done; a compiled plan without a
                  current approval -> waiting, with the approval card
      build       07_premiere/ppro-build-result.json `status`: PRPROJ_BUILT and PRPROJ_BUILT_WITH_ISSUES -> done,
                  FAILED -> failed (ppro_build.py:367); motion: 04_after_effects/motion-build-result.json `status`
                  PROJECT_ASSEMBLED -> done (motion_build.py:108, motion_qc.py:199)
      frames      08_quality_control/visual-verification.json `verdict`: pass -> done, fail -> failed
                  (verify.py:306-308, motion_qc.py:41-43)
      qc          08_quality_control/qc-results.json `ok`: true -> done, false -> failed (qc.py:291-292,
                  motion_qc.py:175)
      handoff     09_handoff/README.md exists (cli.py:835)
    Approval card (only while the approve step is waiting):
      fingerprint the current plan's, what approve-plan records: lib/plan.py plan_fingerprint (plan.py:912,
                  cli.py:496); motion: motion-validation.json `fingerprint` when it equals lib/motion_plan.py
                  fingerprint() now (cli.py:480-488). No current fingerprint -> no card.
      summary     01_analysis/edit-plan.md (plan.py:1042); motion: 01_analysis/motion-plan.md (motion_plan.py:804);
                  clipped to 20000 characters
      preview_mp4 08_quality_control/preview/<item>_preview.mp4 (cli.py:828); motion:
                  08_quality_control/animatic/<item>_animatic.mp4 (motion_qc.py:190); null when absent
      flagged     []: no evidence file carries the medical / religious flags (the reviewers report to the lead)
    QC tiles (at most QC_MAX):
      the newest 08_quality_control/premiere_frames/run-*/ folder (ppro_build.py:479): every frame_<ms>.png
      (adobe/premiere-uxp/src/ops/export-frames.ts:30; the first all-digit name token is the ms, ppro_build.py:492-493);
      t_s = ms / 1000, tc = frame_to_tc at the sequence rate (ppro_build.py:524), label "" (the engine keeps no
      per-frame label). Motion: the newest 08_quality_control/ae_frames/run-*/frames.json {frames: [{frame, scene,
      kind, file}]} (motion_render.py:151, 208), t_s = frame / motion-plan.json `fps` (motion_render.py:190), label
      "<scene> <kind>". The verdict is visual-verification.json's when its `sheet` is that run's _sheet.jpg and its
      `sheet_mtime` is not older than the sheet (verify.py:306-307, ppro_build.py:528, motion_qc.py:26-30), else
      "pending".
    Left out on purpose: `context` (project path, sequence name, ...), staleness of a done step other than the approval
    (cli.py stale_steps), media-pending slates among the frames, per-frame labels and thumbnails.

The build stamp (C2.3)
    <plugin>/adobe/expected.json {product, build, sha} is written by release.py (the executor's part). panel_update
    compares the hello's client.build with its `build` (messages.compare_builds).
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import stat
from pathlib import Path, PurePath

from contract import validate
from lib import common

__all__ = ["ACTIVE_MAX", "EXPECTED_MAX", "EVIDENCE_MAX", "STALE_S", "SKEW_S", "QC_MAX", "STEP_IDS", "active_path",
           "expected_path", "read_active", "read_expected", "panel_update", "panel_fields"]

log = logging.getLogger(__name__)

ACTIVE_MAX = 64 * 1024
EXPECTED_MAX = 64 * 1024
EVIDENCE_MAX = 8 * 1024 * 1024
STALE_S = 12 * 3600
SKEW_S = 5 * 60                       # a writer's clock a little ahead is fine; a record from the future is not
QC_MAX = 500                          # session.schema.json panel_state.qc maxItems
SUMMARY_MAX = 20000                   # approval.summary maxLength
PATH_MAX = 4096                       # qc_frame.file / approval.preview_mp4 maxLength
STEP_IDS = ("transcript", "plan", "approve", "build", "frames", "qc", "handoff")    # pipeline_step.id, in order
EMPTY = {"client": "", "item": "", "pipeline": [], "approval": None, "qc": []}


def active_path(home) -> Path:
    return Path(home) / "state" / "active.json"


def expected_path() -> Path:
    return common.PLUGIN_DIR / "adobe" / "expected.json"


# ------------------------------------------------------------------------------------------------ reading files
def _read_capped(path: Path, cap: int) -> bytes | None:
    """The bytes of a regular file of at most `cap` bytes; None for anything else (missing, a folder, too big, I/O)."""
    try:
        st = os.stat(path)
        if not stat.S_ISREG(st.st_mode) or st.st_size > cap:
            return None
        with open(path, "rb") as f:
            data = f.read(cap + 1)
    except (OSError, ValueError):
        return None
    return data if len(data) <= cap else None


def _json(path: Path, cap: int = EVIDENCE_MAX) -> dict | None:
    """A JSON object from a UTF-8 file (a BOM is fine), or None."""
    data = _read_capped(path, cap)
    if data is None:
        return None
    try:
        doc = json.loads(data.decode("utf-8-sig"))
    except (ValueError, RecursionError):
        return None
    return doc if isinstance(doc, dict) else None


def _text(path: Path, n: int) -> str | None:
    data = _read_capped(path, EVIDENCE_MAX)
    if data is None:
        return None
    text = data.decode("utf-8-sig", "replace")
    return text if len(text) <= n else text[:n - 1] + "…"


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


# ------------------------------------------------------------------------------------------------ build stamp
def read_expected(path=None) -> dict | None:
    """<plugin>/adobe/expected.json as {product, build, sha} (only `build` is needed), or None."""
    doc = _json(Path(path) if path else expected_path(), EXPECTED_MAX)
    if not doc or not isinstance(doc.get("build"), str) or not 0 < len(doc["build"]) <= 64:
        return None
    return doc


def panel_update(client_build, path=None) -> str:
    """welcome.update.panel for a hello's client.build: ok | stale | newer | unknown (no expected.json: unknown)."""
    from .messages import compare_builds
    exp = read_expected(path)
    return compare_builds(client_build, exp["build"]) if exp else "unknown"


# ------------------------------------------------------------------------------------------------ active.json
def _parse_at(s: str) -> _dt.datetime | None:
    try:
        at = _dt.datetime.fromisoformat(s.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return None
    return at if at.tzinfo is not None else None


def _client_root(raw: str) -> Path | None:
    if "\x00" in raw or any(part == ".." for part in PurePath(raw).parts):
        return None
    p = Path(raw)
    if not p.is_absolute():
        return None
    try:
        r = p.resolve(strict=True)
        return r if r.is_dir() else None
    except (OSError, RuntimeError, ValueError):
        return None


def _item(raw: str) -> str | None:
    try:
        common.check_project_id(raw)            # one plain folder name: no separator, drive colon, control char, '..'
    except Exception:
        return None
    return raw


def read_active(home, now: _dt.datetime | None = None) -> dict | None:
    """{client_root: Path, item, project: Path, record} of a usable active.json, else None."""
    rec = _json(active_path(home), ACTIVE_MAX)
    if rec is None or validate(rec, "engine_state"):
        return None
    at = _parse_at(rec["at"])
    now = now or _dt.datetime.now(_dt.timezone.utc)
    if at is None or (now - at).total_seconds() > STALE_S or (at - now).total_seconds() > SKEW_S:
        return None
    root, item = _client_root(rec["client_root"]), _item(rec["item"])
    if root is None or item is None:
        return None
    projects = root / "output" / "projects"
    project = projects / item
    try:
        if project.exists() and not project.resolve().is_relative_to(projects.resolve()):
            return None                          # a link that leaves the client folder
    except (OSError, RuntimeError, ValueError):
        return None
    return {"client_root": root, "item": item, "project": project, "record": rec}


# ------------------------------------------------------------------------------------------------ evidence
def _is_motion(paths: common.Paths) -> bool:
    return (_json(paths.p("00_inputs/source.json")) or {}).get("kind") == "motion_reel"


def _plan_fingerprint(paths: common.Paths, motion: bool) -> str | None:
    """The fingerprint approve-plan would record now; None when there is no current, readable plan."""
    try:
        if motion:
            val = _json(paths.p("01_analysis/motion-validation.json")) or {}
            if not val.get("ok") or not isinstance(val.get("fingerprint"), str):
                return None
            from lib.motion_plan import fingerprint
            return val["fingerprint"] if fingerprint(paths) == val["fingerprint"] else None
        if _read_capped(paths.p("01_analysis/timeline-spec.json"), EVIDENCE_MAX) is None:
            return None
        from lib.plan import plan_fingerprint
        return plan_fingerprint(paths)
    except Exception as e:                       # the engine's own readers: a broken file is "no plan", never a crash
        log.debug("engine state: no plan fingerprint (%s)", type(e).__name__)
        return None


def _approval_current(paths: common.Paths) -> bool:
    try:
        from lib.plan import approval_state
        return approval_state(paths)["state"] == "current"
    except Exception as e:
        log.debug("engine state: approval unreadable (%s)", type(e).__name__)
        return False


def _short_path(p: Path) -> str | None:
    s = str(p)
    return s if len(s) <= PATH_MAX else None


def _newest_run(folder: Path, need: str) -> Path | None:
    try:
        runs = sorted(d for d in folder.glob("run-*") if d.is_dir() and (not need or _is_file(d / need)))
    except OSError:
        return None
    return runs[-1] if runs else None            # run-YYYYmmdd-HHMMSS: the name order is the time order


def _same_file(a, b: Path) -> bool:
    try:
        return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))
    except (TypeError, ValueError):
        return False


def _run_verdict(vv: dict | None, run: Path) -> str:
    sheet = run / "_sheet.jpg"
    if not vv or vv.get("verdict") not in ("pass", "fail") or not _same_file(vv.get("sheet"), sheet):
        return "pending"
    try:
        recorded = float(vv.get("sheet_mtime"))
        if sheet.stat().st_mtime > recorded + 1:  # the sheet was rebuilt after the verdict
            return "pending"
    except (OSError, TypeError, ValueError):
        return "pending"
    return vv["verdict"]


def _ms_of(name: str) -> int | None:
    return next((int(tok) for tok in Path(name).stem.split("_") if tok.isdigit()), None)


def _edit_tiles(paths: common.Paths, vv: dict | None) -> list:
    run = _newest_run(paths.p("08_quality_control/premiere_frames"), "")
    if run is None:
        return []
    verdict = _run_verdict(vv, run)
    fps = common.seq_fps()
    frames = []
    try:
        pngs = sorted(f for f in run.glob("*.png") if not f.name.startswith("._"))
    except OSError:
        return []
    for f in pngs:
        ms = _ms_of(f.name)
        file = _short_path(f)
        if ms is None or file is None:
            continue
        t = ms / 1000
        frames.append({"t_s": t, "tc": common.frame_to_tc(round(t * fps)), "file": file, "label": "",
                       "verdict": verdict})
    frames.sort(key=lambda q: q["t_s"])
    return frames[:QC_MAX]


def _motion_tiles(paths: common.Paths, vv: dict | None) -> list:
    run = _newest_run(paths.p("08_quality_control/ae_frames"), "frames.json")
    plan = _json(paths.p("01_analysis/motion-plan.json")) or {}
    fps = plan.get("fps")
    if run is None or isinstance(fps, bool) or not isinstance(fps, (int, float)) or not fps > 0:
        return []
    doc = _json(run / "frames.json") or {}
    verdict = _run_verdict(vv, run)
    out = []
    for rec in doc.get("frames") or []:
        if not isinstance(rec, dict):
            continue
        frame, name = rec.get("frame"), rec.get("file")
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0 or not isinstance(name, str) \
                or not name or Path(name).name != name or PurePath(name).name != name or name in (".", ".."):
            continue                              # a file name, never a path
        file = _short_path(run / name)
        if file is None:
            continue
        label = " ".join(str(rec.get(k)) for k in ("scene", "kind") if isinstance(rec.get(k), str))[:512]
        out.append({"t_s": round(frame / float(fps), 6), "tc": common.frame_to_tc(frame, float(fps)), "file": file,
                    "label": label, "verdict": verdict})
        if len(out) >= QC_MAX:
            break
    return out


def _evidence(paths: common.Paths) -> dict:
    P = paths.p
    motion = _is_motion(paths)
    st = dict.fromkeys(STEP_IDS, "pending")
    approval = None
    if _is_file(P("02_transcription/transcript.json")):
        st["transcript"] = "done"
    if motion:
        val = _json(P("01_analysis/motion-validation.json"))
        if _is_file(P("01_analysis/motion-plan.json")) and val is not None:
            st["plan"] = "done" if val.get("ok") is True else "failed" if val.get("ok") is False else "pending"
    elif _is_file(P("01_analysis/timeline-spec.json")):
        st["plan"] = "done"
    if st["plan"] == "done":
        if _approval_current(paths):
            st["approve"] = "done"
        else:
            fp = _plan_fingerprint(paths, motion)
            if fp:
                st["approve"] = "waiting"
                md = P("01_analysis/motion-plan.md" if motion else "01_analysis/edit-plan.md")
                pv = P(f"08_quality_control/animatic/{paths.video_id}_animatic.mp4" if motion
                       else f"08_quality_control/preview/{paths.video_id}_preview.mp4")
                approval = {"summary": _text(md, SUMMARY_MAX) or "",
                            "preview_mp4": _short_path(pv) if _is_file(pv) else None,
                            "flagged": [], "fingerprint": fp[:256]}
    build = _json(P("04_after_effects/motion-build-result.json" if motion
                    else "07_premiere/ppro-build-result.json")) or {}
    status = build.get("status")
    if motion:
        st["build"] = "done" if status == "PROJECT_ASSEMBLED" else "pending"
    else:
        st["build"] = ("done" if status in ("PRPROJ_BUILT", "PRPROJ_BUILT_WITH_ISSUES") else
                       "failed" if status == "FAILED" else "pending")
    vv = _json(P("08_quality_control/visual-verification.json"))
    verdict = (vv or {}).get("verdict")
    st["frames"] = "done" if verdict == "pass" else "failed" if verdict == "fail" else "pending"
    ok = (_json(P("08_quality_control/qc-results.json")) or {}).get("ok")
    st["qc"] = "done" if ok is True else "failed" if ok is False else "pending"
    if _is_file(P("09_handoff/README.md")):
        st["handoff"] = "done"
    try:
        qc = _motion_tiles(paths, vv) if motion else _edit_tiles(paths, vv)
    except Exception as e:
        log.debug("engine state: no QC tiles (%s)", type(e).__name__)
        qc = []
    return {"pipeline": [{"id": s, "state": st[s]} for s in STEP_IDS], "approval": approval, "qc": qc}


def panel_fields(home, now: _dt.datetime | None = None) -> dict:
    """{client, item, pipeline, approval, qc} for PanelState: the item active.json names, else the empty values.
    Blocking (file reads, hashing): the daemon runs it in a worker thread."""
    act = read_active(home, now)
    if act is None:
        return dict(EMPTY)
    root, item = act["client_root"], act["item"]
    out = dict(EMPTY, client=root.name[:256] or str(root)[:256], item=item[:256])
    try:
        with common.use_context(common.Context(root=root, home=home)):
            out.update(_evidence(common.Paths(root, item)))
    except Exception as e:                        # never fail a snapshot over an evidence file
        log.warning("reel serve: engine state for %s unreadable (%s)", item, type(e).__name__)
        out["pipeline"] = [{"id": s, "state": "pending"} for s in STEP_IDS]
    return out
