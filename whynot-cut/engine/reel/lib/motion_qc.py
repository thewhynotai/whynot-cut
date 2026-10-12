"""QC for motion projects (`reel qc`, spec §4.10), the visual-verification record (`reel verify --record`) and the
resumable step list (`reel next`, spec §4.11). Every FAIL blocks QC_PASSED; evidence must be fresh and consistent.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from .common import now_iso, read_json, write_json

VV = "08_quality_control/visual-verification.json"


def _t(p: Path) -> float | None:
    return p.stat().st_mtime if p.exists() else None


def _newest_render(paths) -> float:
    d = paths.p("04_after_effects/render")
    ts = [f.stat().st_mtime for f in d.rglob("*") if f.is_file() and f.suffix.lower() in (".mov", ".mp4")] if d.exists() else []
    return max(ts) if ts else 0.0


def newest_frames_sheet(paths) -> Path | None:
    d = paths.p("08_quality_control/ae_frames")
    runs = sorted((r for r in d.glob("run-*") if (r / "_sheet.jpg").exists()), key=lambda r: (r / "_sheet.jpg").stat().st_mtime) \
        if d.exists() else []
    return (runs[-1] / "_sheet.jpg") if runs else None


def record_visual(paths, verdict: str, notes: str, by: str = "claude") -> dict:
    if verdict not in ("pass", "fail"):
        raise SystemExit("verdict must be pass or fail")
    sheet = newest_frames_sheet(paths)
    if not sheet:
        raise SystemExit("no After Effects frames sheet: run `reel motion-frames` and look at every frame first")
    if sheet.stat().st_mtime < _newest_render(paths):
        raise SystemExit("the frames sheet is older than the newest render: run `reel motion-frames` and look again")
    rec = {"verdict": verdict, "notes": notes, "by": by, "at": now_iso(), "recorded_epoch": time.time(),
           "sheet": str(sheet), "sheet_mtime": sheet.stat().st_mtime, "kind": "motion"}
    write_json(paths.p(VV), rec)
    return rec


def _env(x: np.ndarray, fps: float) -> np.ndarray:
    hop = 48000 / fps
    n = int(len(x) / hop)
    return np.array([np.sqrt(np.mean(x[int(k * hop):int((k + 1) * hop)] ** 2)) for k in range(n)])


def _has_audio(f: Path) -> bool:
    from .media import probe
    return bool(probe(Path(f)).get("audio"))


def audio_sync(render: Path, dialogue: Path, fps: float, max_lag: int = 6) -> dict:
    """Per-frame loudness of the render's audio against the sequence-clock dialogue: best correlation and its lag."""
    from .motion_audio import _decode
    a, b = _decode(Path(render)).mean(axis=1), _decode(Path(dialogue)).mean(axis=1)
    if not len(a) or not len(b):
        return {"corr": None, "offset_frames": None, "detail": "no audio to compare"}
    ea, eb = _env(a, fps), _env(b, fps)
    best = (-2.0, 0)
    for lag in range(-max_lag, max_lag + 1):
        x = ea[max(0, lag):len(ea) + min(0, lag)]
        y = eb[max(0, -lag):len(eb) + min(0, -lag)]
        n = min(len(x), len(y))
        if n < 10 or np.std(x[:n]) == 0 or np.std(y[:n]) == 0:
            continue
        c = float(np.corrcoef(x[:n], y[:n])[0, 1])
        if c > best[0]:
            best = (c, lag)
    return {"corr": round(best[0], 3) if best[0] > -2 else None, "offset_frames": best[1]}


def sync_detail(s: dict) -> str:
    """audio_sync's measurement in words, with a note for a near miss (0.8 <= correlation < 0.9)."""
    if s.get("corr") is None:
        return s.get("detail") or "no correlation measured (silent or too short)"
    d = f"correlation {s['corr']}, offset {s['offset_frames']} frames"
    if 0.8 <= s["corr"] < 0.9:
        d += (" (just under 0.9: the render's full mix is compared with the dry dialogue, so a loud music bed or SFX can "
              "cause this)")
    return d


def _planned_mix_check(paths, plan: dict, main: Path) -> str:
    """Is it the bed or the voice? The render against the engine's own mix of the plan (same sequence clock)."""
    import tempfile
    from .motion_audio import mix
    a = plan["audio"]
    files = [a["dialogue"]] + ([a["music"]["file"]] if a.get("music") else []) + [c["file"] for c in a.get("sfx") or []]
    gone = sorted({Path(f).name for f in files if not Path(f).exists()})
    if gone:
        return f"planned mix unavailable: {', '.join(gone)} missing (motion-plan again)"
    with tempfile.TemporaryDirectory(prefix="whynot-qc-") as td:
        m = audio_sync(main, mix(plan, paths.root, Path(td) / "planned_mix.wav"), float(plan["fps"]))
    said = f"against the planned mix (dialogue + music + SFX): correlation {m['corr']}, offset {m['offset_frames']} frames"
    if m["corr"] is not None and m["corr"] >= 0.9 and abs(m["offset_frames"]) <= 1:
        return said + (" - the render matches the planned mix, so the voice is in sync and the bed lowers the dialogue "
                       "correlation: lower music.level_db (or the SFX) in motion-script.json, then motion-plan and "
                       "render again")
    return said + (" - the render does not match the planned mix either: the voice or the bed level in After Effects "
                   "differs from the plan (check the DIALOGUE and MUSIC layers in MAIN)")


def run(paths) -> dict:
    from .motion_build import RESULT as BUILD, _sha1, aep_path
    from .motion_config import motion_cfg
    from .motion_plan import fingerprint
    from .motion_render import RESULT as RENDER
    checks = []

    def add(check, ok, detail, warn=False):
        checks.append({"check": check, "result": "PASS" if ok else ("WARN" if warn else "FAIL"), "detail": detail})
    fp = fingerprint(paths)
    plan = read_json(paths.p("01_analysis/motion-plan.json"), {}) or {}
    val = read_json(paths.p("01_analysis/motion-validation.json"), {}) or {}
    add("plan_valid", bool(val.get("ok")) and val.get("fingerprint") == fp,
        "motion plan compiled without errors and current" if val.get("ok") else "motion plan missing, with errors or stale")
    appr = read_json(paths.p("01_analysis/plan-approval.json"), {}) or {}
    add("approval_current", bool(appr.get("approved")) and appr.get("plan_fingerprint") == fp,
        f"Gate 1 by {appr.get('by')}" if appr.get("plan_fingerprint") == fp else "Gate 1 approval missing or older than the plan")
    b = read_json(paths.p(BUILD), {}) or {}
    aep = aep_path(paths)
    fresh = b.get("status") in ("PROJECT_ASSEMBLED", "BUILT_UNVERIFIED") and aep.exists() and _sha1(aep) == b.get("aep_sha1")
    add("aep_fresh", fresh, "the .aep is the one this build saved" if fresh else
        "no build, or the .aep changed after it was built (rebuild: motion-build)")
    rb_ok = b.get("status") == "PROJECT_ASSEMBLED" and b.get("readback") is not None and (b.get("comparison") or {}).get("ok")
    add("readback", bool(rb_ok), "After Effects read-back matches the plan" if rb_ok else
        ("no read-back (built without the bridge)" if b.get("status") == "BUILT_UNVERIFIED" else
         "read-back failed: " + "; ".join(((b.get("comparison") or {}).get("failures") or [])[:3])))
    rr = read_json(paths.p(RENDER), {}) or {}
    main = Path(rr["main"]) if rr.get("main") else None
    r_ok = rr.get("status") == "RENDERED" and not rr.get("reasons") and main is not None and main.exists() \
        and aep.exists() and main.stat().st_mtime >= aep.stat().st_mtime
    silent = bool(r_ok) and not _has_audio(main)
    add("render", bool(r_ok) and not silent,
        "the render has no audio stream: check the DIALOGUE layer in MAIN and the output module's audio output, then "
        "motion-render again" if silent else "render exists, is newer than the .aep and matches the plan" if r_ok else
        "render missing, failed, or older than the .aep (motion-render)")
    dia = Path((plan.get("audio") or {}).get("dialogue") or paths.p("06_audio/dialogue/_missing.wav"))
    if main and main.exists() and dia.exists() and plan:
        s = audio_sync(main, dia, float(plan["fps"]))
        ok = s["corr"] is not None and s["corr"] >= 0.9 and abs(s["offset_frames"]) <= 1
        detail = sync_detail(s)
        a = plan.get("audio") or {}
        if not ok and s["corr"] is not None and (a.get("music") or a.get("sfx")):
            detail += "; " + _planned_mix_check(paths, plan, main)
        add("audio_sync", ok, detail)
    else:
        add("audio_sync", False, "render or sequence dialogue missing")
    cv = read_json(paths.p("06_audio/dialogue/cut-verification.json"), {}) or {}
    add("cut_proof", bool(cv.get("ok")), cv.get("verdict") or ("no speech cut" if cv.get("ok") else
                                                               "cut proof missing or failed (audio-clean)"))
    vv = read_json(paths.p(VV), {}) or {}
    sheet = newest_frames_sheet(paths)
    v_ok = vv.get("verdict") == "pass" and vv.get("kind") == "motion" and sheet is not None \
        and Path(vv.get("sheet", "")) == sheet and abs(sheet.stat().st_mtime - vv.get("sheet_mtime", 0)) < 1 \
        and sheet.stat().st_mtime >= _newest_render(paths)
    add("visual_verified", bool(v_ok), f"frames viewed and recorded by {vv.get('by')}" if v_ok else
        "no pass verdict on the newest frames (motion-frames, look, verify --record)")
    allowed = set(motion_cfg().get("licenses_allowed") or []) | {"client", "ISC"}
    bad = [a["ref"] for a in plan.get("assets") or [] if a.get("license") not in allowed]
    noattr = [a["ref"] for a in plan.get("assets") or [] if a.get("license") == "CC-BY-4.0" and not a.get("attribution")]
    add("licenses", not bad and not noattr, "every asset licensed" if not bad and not noattr else
        f"unlicensed: {bad}; CC-BY without attribution: {noattr}")
    appr_items = plan.get("approvals") or []
    add("approvals_listed", not appr_items, "; ".join(appr_items) or "no approvals needed", warn=True)
    failed = [c for c in checks if c["result"] == "FAIL"]
    res = {"ok": not failed, "checks": checks, "failed": failed, "generated": now_iso(), "kind": "motion"}
    write_json(paths.p("08_quality_control/qc-results.json"), res)
    return res


def motion_next(paths) -> dict:
    from .ae_probe import capabilities
    from .common import active_profile, load_status
    from .motion_build import RESULT as BUILD
    from .motion_plan import fingerprint
    from .motion_render import RESULT as RENDER
    P = paths.p
    val = read_json(P("01_analysis/motion-validation.json"), {}) or {}
    appr = read_json(P("01_analysis/plan-approval.json"), {}) or {}
    b = read_json(P(BUILD), {}) or {}
    rr = read_json(P(RENDER), {}) or {}
    anim = P(f"08_quality_control/animatic/{paths.video_id}_animatic.mp4")
    fp = fingerprint(paths) if P("01_analysis/motion-script.json").exists() else None
    steps = [
        ("audio-clean", P("06_audio/dialogue/pauses.json").exists()),
        ("AUTHOR 01_analysis/motion-script.json (motion-director)", P("01_analysis/motion-script.json").exists()),
        ("motion-plan", P("01_analysis/motion-plan.json").exists() and bool(val.get("ok"))),
        ("motion-animatic", anim.exists()),
        ("PLAYBACK motion-plan.md + animatic to the editor, then approve-plan", bool(appr.get("approved"))),
        ("ae-probe (once per After Effects version), VIEW, --record", capabilities().get("verdict") == "ok" or bool(b)),
        ("motion-build (needs After Effects + bridge; fallback --script-only)", b.get("status") == "PROJECT_ASSEMBLED"),
        ("motion-render", rr.get("status") == "RENDERED"),
        ("motion-frames, LOOK at every frame, verify --record", P(VV).exists()),
        ("qc", P("08_quality_control/qc-results.json").exists()),
        ("handoff", P("09_handoff/README.md").exists()),
    ]
    todo = [n for n, done in steps if not done]
    tm = {k: _t(P(v)) for k, v in (("script", "01_analysis/motion-script.json"), ("pauses", "06_audio/dialogue/pauses.json"),
                                   ("plan", "01_analysis/motion-plan.json"), ("approval", "01_analysis/plan-approval.json"),
                                   ("build", BUILD), ("render", RENDER), ("vv", VV),
                                   ("qc", "08_quality_control/qc-results.json"), ("handoff", "09_handoff/README.md"))}
    tm["anim"] = _t(anim)

    def newer(a, *ups):
        return tm.get(a) is not None and any(tm.get(u) is not None and tm[u] > tm[a] + 1 for u in ups)
    stale = []
    if newer("plan", "script", "pauses"):
        stale.append("motion-plan (older than motion-script.json or pauses.json)")
    if newer("anim", "plan"):
        stale.append("motion-animatic (older than the plan)")
    if appr and fp and appr.get("plan_fingerprint") != fp:
        stale.append("approve-plan (the plan changed after approval: show the editor again)")
    if newer("build", "plan", "approval"):
        stale.append("motion-build (older than the plan or its approval)")
    if newer("render", "build"):
        stale.append("motion-render (older than the build)")
    if newer("vv", "render"):
        stale.append("motion-frames, LOOK at every frame, verify --record (older than the render)")
    if newer("qc", "vv", "render"):
        stale.append("qc (older than the verification or the render)")
    if newer("handoff", "qc"):
        stale.append("handoff (older than qc)")
    names = [s.split(" (")[0] for s in stale]
    remaining = stale + [n for n in todo if n.split(" (")[0] not in names]
    status = load_status(paths)["status"]
    from .common import DONE_STATUSES
    if stale and status in DONE_STATUSES:                       # T2.15: DELIVERED too
        status = f"{status} (STALE: inputs changed since)"
    from .people import profile_notice
    return {"status": status, "profile": active_profile(paths.root), "kind": "motion",
            "next": remaining[0] if remaining else "done", "remaining": remaining, "stale": stale,
            "notices": [n for n in (profile_notice(paths.root),) if n]}
