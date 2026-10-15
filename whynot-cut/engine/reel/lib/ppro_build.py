"""Premiere-only build through the WhyNot Cut Bridge: a real .prproj created and saved by Premiere itself.

Footage, punch-ins, dialogue and SFX come from the base XML (imported INSIDE Premiere); graphics
are brand stills placed on named tracks and animated with Premiere keyframes; captions are a
native, editable caption track; sequence settings are applied via Premiere's API and read back.
No After Effects involved.
"""
from __future__ import annotations

from pathlib import Path

from .common import still_category, caption_hide_default, frame_size, Paths, seq_fps, project_prefix, load_config, ms_to_frame, now_iso, read_json, write_json
from . import srt as srtlib
from .plan import norm, to_ms

SETTINGS = {  # user's sequence spec; verified field names/values from Premiere 26.5 getSettings()
    "previewCodec": "apcs",               # Apple ProRes 422 LT; previewFrameWidth/Height = the profile's frame (job_data)
    "maximumBitDepth": False, "maximumRenderQuality": False, "compositeLinearColor": True,
}
LANE_NAMES = {"broll": "B-roll (full screen)", "gfx_bar": "Graphic bars (sweep)", "card": "Cards (closing glass)",
              "gfx_text": "Graphic text", "cap_bar": "Caption bars (sweep)", "cap_text": "Captions (animated)",
              "fx": "Transitions"}
BAR_T = {"hook_title", "term_callout", "statement_highlight"}


def premiere_captions(paths: Paths, spec: dict, ed: dict) -> Path:
    """captions-short.srt minus words a graphic already shows (reference behaviour) -> native caption track."""
    from .timemap import TimeMap
    g = ed.get("global", {})
    hide_t = set(g.get("captions_hidden_during") or caption_hide_default())
    blocked = [(e["start_ms"], e["end_ms"]) for e in spec["events"] if e["template"] in hide_t]
    # events are on the SEQUENCE clock; hidden ranges are authored in SOURCE time -> map them, and read the
    # sequence-clock captions (captions-short-seq.srt after pause removal)
    tm = spec.get("time_map")
    remap = TimeMap(tm["keep_ms"]) if tm else None
    for a, b in g.get("captions_hidden_ranges", []):
        a, b = to_ms(a), to_ms(b)
        blocked.append((remap.ms(a), remap.ms(b)) if remap else (a, b))
    out = []
    for c in srtlib.read_srt(paths.p(spec.get("caption_source", "02_transcription/captions-short.srt"))):
        s, e = c["start_ms"], c["end_ms"]
        for a, b in blocked:
            if a <= s < b:
                s = b
            elif s < a < e:
                e = a
        if e - s >= 250:
            out.append({"start_ms": s, "end_ms": e, "text": c["text"]})
    p = paths.p("02_transcription/captions-premiere.srt")
    srtlib.write_srt(p, out)
    return p


def cutaway_bands(paths: Paths, spec: dict) -> list:
    """(start_ms, end_ms, top_px, bottom_px) of every source card shown whole (AUTO_CUTAWAY: fit over a blurred fill),
    on the sequence clock, so captions move off the card like they move off a graphic card."""
    from .common import seq_fps
    from .plan import main_video
    pre = read_json(paths.p("00_inputs/preflight.json"), {}) or {}
    v = main_video(pre, spec.get("main_footage"))     # this reel's footage, not the first file preflight lists
    if not v:
        return []
    H = frame_size(paths)[1]
    bsp = float(spec.get("base_scale_percent") or 100.0)
    fps = seq_fps()
    out = []
    for m in spec.get("main_segments", []):
        if m.get("decision_id") != "AUTO_CUTAWAY":
            continue
        h = v["display_height"] * bsp / 100 * float(m.get("scale_factor", 1.0))
        cy = H / 2 + float(m.get("offset_y", 0.0)) + float(spec.get("base_offset_y", 0.0))
        out.append((m["start_frame"] * 1000 / fps, m["end_frame"] * 1000 / fps, int(cy - h / 2), int(cy + h / 2)))
    return out


def job_data(paths: Paths, overwrite: bool = False, stage_media: bool = False, fresh_stills: bool = False) -> dict:
    """The build_project job. fresh_stills (every build, and the preview video): first redraw the graphic stills that
    were not drawn from the plan as it is now (previews.ensure_fresh_stills, 3.0 F1); `_stills_redrawn` names them.
    A redraw that fails raises its Guidance (`stills_out_of_date`)."""
    from .premiere_xml import build_xml
    from .previews import render_captions
    from .timemap import TimeMap
    from .stamps import read_compiled
    fresh = {"redrawn": [], "warnings": []}
    if fresh_stills:
        from .previews import ensure_fresh_stills
        fresh = ensure_fresh_stills(paths)
    spec = read_compiled(paths.p("01_analysis/timeline-spec.json"))
    ed = read_json(paths.p("01_analysis/edit-decisions.json"), {})
    tpl = load_config("graphics-templates.json")["templates"]
    F = 1 / seq_fps()
    n_items = max([len(e["params"].get("items", [])) for e in spec["events"] if e["template"] == "checklist"] or [0])
    lanes = ["broll", "gfx_bar", "card", "gfx_text"] + [f"item{k + 1}" for k in range(n_items)] + ["cap_bar", "cap_text", "fx"]
    base = build_xml(paths, native_graphics=True, lanes=lanes)
    cut_off = 1 if (base.get("cutaways") or {}).get("track") else 0   # V2 = source cutaways (whole) when the source has them
    lane_idx = {ln: i + 1 + cut_off for i, ln in enumerate(lanes)}   # 0 = V1 main footage
    g_out, missing = [], []

    def add(gid, png, lane, anim, s, e, **kw):
        g_out.append(dict(id=gid, png=str(png), track_index=lane_idx[lane], anim=anim, start_s=round(s, 4), end_s=round(e, 4), **kw))

    for e in spec["events"]:
        if e["template"] == "broll_video":      # placed as a real video clip by the base XML (video only)
            continue
        t = tpl[e["template"]]
        cat = still_category(e["template"])
        d = paths.p(f"03_broll/{cat}")
        s, en = e["start_frame"] * F, e["end_frame"] * F
        fo = t.get("out_frames", 5) * F
        tp = e["template"]
        if tp in BAR_T:
            add(e["event_id"] + "_bar", d / f"{e['event_id']}_bar.png", "gfx_bar", "bar_sweep", s, en, fade_out_s=fo)
            add(e["event_id"] + "_fg", d / f"{e['event_id']}_fg.png", "gfx_text", "text_pop", s, en, fade_out_s=fo)
        elif tp == "checklist":
            add(e["event_id"] + "_title", d / f"{e['event_id']}_title.png", "gfx_text", "text_pop", s, en, fade_out_s=fo)
            for k, it in enumerate(e["params"].get("items", [])):
                add(f"{e['event_id']}_i{k + 1}", d / f"{e['event_id']}_i{k + 1}.png", f"item{k + 1}", "slide",
                    max(s, it["frame"] * F), en, fade_out_s=fo)
        elif tp == "broll_card" or tp == "logo_outro":
            add(e["event_id"], d / f"{e['event_id']}.png", "broll", "push" if tp == "broll_card" else "fade", s, en, fade_out_s=0)
        elif tp == "flash_transition":
            add(e["event_id"], d / f"{e['event_id']}.png", "fx", "flash", s, en, peak=90)
        else:  # name_card / glass_card / photo_card / cta
            add(e["event_id"], d / f"{e['event_id']}.png", "card", "card", s, en,
                fade_in_s=t.get("in_frames", 10) * F, fade_out_s=fo)

    # animated captions (sequence clock); hide where a graphic already carries the words
    g = ed.get("global", {})
    hide_t = set(g.get("captions_hidden_during") or caption_hide_default())
    hidden = [(e["start_ms"], e["end_ms"]) for e in spec["events"] if e["template"] in hide_t]
    tm = spec.get("time_map")
    remap = TimeMap(tm["keep_ms"]) if tm else None
    for a, b in g.get("captions_hidden_ranges", []):
        a, b = to_ms(a), to_ms(b)
        hidden.append((remap.ms(a), remap.ms(b)) if remap else (a, b))
    # captions never sit on a card (name card etc.): while one overlaps the caption band, the caption moves
    avoid = []
    for e in spec["events"]:
        if e["template"] in ("name_card", "glass_card", "cta", "stat_card", "context_card"):
            png = paths.p(f"03_broll/typography/{e['event_id']}.png")
            if png.exists():
                from .media_util import open_rgb
                bb = open_rgb(png, "RGBA").getchannel("A").getbbox()
                if bb:
                    avoid.append((e["start_ms"], e["end_ms"], bb[1], bb[3]))
    avoid += cutaway_bands(paths, spec)
    font_warns = list(fresh["warnings"])     # the redraw's readability notes; G72: Arabic captions without an Arabic font
    caps = render_captions(paths, hidden, avoid=avoid, warnings=font_warns)
    for c in caps:
        s, en = c["start_ms"] / 1000, c["end_ms"] / 1000
        if c.get("bar"):
            add(c["id"] + "_bar", c["bar"], "cap_bar", "bar_sweep", s, en, delay_f=1, sweep_f=5)
        add(c["id"], c["fg"], "cap_text", "text_pop", s, en)
    for x in g_out:
        if not Path(x["png"]).exists():
            missing.append(x["png"])
    if stage_media and not missing:
        stage_stills(paths, g_out)
    markers = [{"t": e["start_frame"] * F, "name": e["event_id"],
                "comment": f"{e['template']} | {(e.get('evidence') or '')[:200]}"} for e in spec["events"]]
    windowed = "window" in str(spec.get("framing", ""))
    vnames = ["V1 Main Footage" + (" (blurred fill)" if windowed else " (+ blurred fill under cutaways)" if cut_off else "")] +         (["V2 Speaker in window + source cutaways" if windowed else "V2 Source cutaways (whole)"] if cut_off else []) +         [f"V{i + 2 + cut_off} {LANE_NAMES.get(ln, 'Checklist item ' + ln[4:])}" for i, ln in enumerate(lanes)]
    dlg = "Dialogue (clean)" if paths.p("06_audio/dialogue/dialogue_clean.wav").exists() else "Dialogue (camera, not cleaned)"
    anames = [f"A1 {dlg} L", f"A2 {dlg} R"]
    for k in base["tracks"]["audio"][1:]:
        nm = k["name"].replace(" (L/R mono pair)", "")
        anames += [f"A{len(anames) + 1} {nm} L", f"A{len(anames) + 2} {nm} R"]
    return {"project_path": str(paths.p(f"07_premiere/project/{paths.video_id}_{project_prefix()}_EDIT.prproj")),
            "overwrite_existing": overwrite, "xml_path": base["xml"], "sequence_name": base["sequence_name"],
            "settings": dict(SETTINGS, **dict(zip(("previewFrameWidth", "previewFrameHeight"), frame_size(paths)))),
            "graphics": g_out, "srt_path": str(paths.p("02_transcription/subtitles-seq.srt")),
            "native_caption_track": bool(g.get("native_caption_track", False)),
            "markers": markers, "track_names": {"video": vnames, "audio": anames}, "_missing": missing,
            "blur_v1_clips": (base.get("cutaways") or {}).get("blur_v1_clip_indices") or [],
            "sharpen_v1": sharpen_settings(spec),
            "_lanes": lanes, "_warnings": font_warns, "_stills_redrawn": fresh["redrawn"],
            "duration_s": spec["duration_frames"] * F}


def sharpen_settings(spec: dict) -> dict | None:
    """Sharpen (+ grain) for the speaker clips on V1 when the source is upscaled at least `min_upscale_percent`
    (style.json reframe_sharpen). None = leave the footage untouched."""
    cfg = load_config("style.json").get("reframe_sharpen") or {}
    amount = float(cfg.get("amount") or 0)
    # only the speaker pieces on V1 are sharpened: in 4:5 framing V1 is all blurred fill (the window is upscaled less)
    if spec.get("main_segments") and not any(m.get("decision_id") != "AUTO_CUTAWAY" and not m.get("window")
                                             for m in spec["main_segments"]):
        return None
    if amount <= 0 or float(spec.get("base_scale_percent") or 0) < float(cfg.get("min_upscale_percent", 150)):
        return None
    return {"amount": amount, "grain": float(cfg.get("grain_percent") or 0)}


def stage_stills(paths: Paths, graphics: list) -> Path:
    """Premiere gets its own copy of the stills for each build. On Windows it keeps imported stills locked until it quits,
    so pointing it at 03_broll/ would block every later re-render (revisions). Older copies are removed when free."""
    import shutil
    import time as _t
    root = paths.p("07_premiere/media")
    dst = root / f"stills-{_t.strftime('%Y%m%d-%H%M%S')}"
    dst.mkdir(parents=True, exist_ok=True)
    for x in graphics:
        src = Path(x["png"])
        tgt = dst / f"{src.parent.name}__{src.name}"
        shutil.copy2(src, tgt)
        x["png"] = str(tgt)
    for old in sorted(root.glob("stills-*"))[:-2]:      # keep this build's and the previous one
        shutil.rmtree(old, ignore_errors=True)            # a copy Premiere still holds simply stays until next time
    return dst


LOCK_HOLD_S = 3600          # the expiry written in the lock: honoured for holders on OTHER computers only (a live holder here is never stale)
BUILD_TIMEOUT_MIN_S, BUILD_TIMEOUT_PER_CLIP_S = 900, 6     # G2 R1: max(900, 6 x the clip's seconds)


def build_timeout(duration_s) -> float:
    """How long the build_project job may run once Premiere claims it: a long clip gets longer than the fixed 900 s."""
    try:
        d = float(duration_s or 0)
    except (TypeError, ValueError):
        d = 0.0
    return max(BUILD_TIMEOUT_MIN_S, BUILD_TIMEOUT_PER_CLIP_S * d)


def build(paths: Paths, overwrite: bool = False, replace_edited: bool = False, *, lock_wait_s: float | None = None) -> dict:
    """Build the reel's .prproj in Premiere. One build at a time on this machine (the bridge's build lock): a second
    session waits up to `lock_wait_s` (default cep_queue.LOCK_WAIT_S), then gets BRIDGE_BUSY."""
    from . import cep_queue
    from .ppro_bridge import BRIDGE_VERSION, build_lock, status
    st = status()
    if not st["alive"]:
        return {"status": "BRIDGE_NOT_RUNNING", "detail": st["detail"]}
    if "bridge_version" in st:          # a heartbeat that names its version must be this engine's bridge
        refused = cep_queue.version_refusal(st, BRIDGE_VERSION, "Premiere")
        if refused:
            return {"status": "BRIDGE_VERSION_MISMATCH", "ok": False, "blocked": refused["blocked"],
                    "error": refused["error"], "how": refused["how"]}
    prproj = paths.p(f"07_premiere/project/{paths.video_id}_{project_prefix()}_EDIT.prproj")
    wait = cep_queue.LOCK_WAIT_S if lock_wait_s is None else lock_wait_s
    try:
        with build_lock(f"ppro-build {paths.video_id}", hold_s=LOCK_HOLD_S, wait_s=wait):
            return _build_locked(paths, prproj, overwrite, replace_edited)
    except cep_queue.BuildLockBusy as e:
        return dict(cep_queue.lock_busy_result(e, "Premiere"), ok=False, status="BRIDGE_BUSY")
    except OSError as e:                # G2 R1: a full disk in plain words (_build_locked already put the old project back)
        from .build_safety import disk_full_message, is_disk_full
        if not is_disk_full(e):
            raise
        return {"status": "DISK_FULL", "ok": False, "error": disk_full_message(prproj), "project": str(prproj),
                "how": ("The previous project is in place; nothing of it was lost." if prproj.exists() else
                        "If a *_prev_* project is next to the expected one, rename it back to keep working in it.")}


def approval_refusal(paths: Paths) -> dict | None:
    """The CLI's Gate 1 check (cli.require_plan_approval) for callers that are not the CLI (reel serve): the CURRENT
    plan must be approved; a re-plan after approval, a stale record or no compiled plan refuses. A record from before
    3.0 says so plainly (plan.OLDER_APPROVAL, 3.0 F2)."""
    from .plan import OLDER_APPROVAL, approved_before_3, plan_fingerprint
    appr = read_json(paths.p("01_analysis/plan-approval.json"), {}) or {}
    try:
        now = plan_fingerprint(paths)
    except (OSError, ValueError):
        now = None
    if appr.get("approved") and not appr.get("stale") and now and appr.get("plan_fingerprint") == now:
        return None
    if now and approved_before_3(appr):
        return {"status": "REFUSED", "ok": False, "blocked": OLDER_APPROVAL["en"],
                "error": OLDER_APPROVAL["en"] + " Nothing was built.", "editor_message": dict(OLDER_APPROVAL),
                "how": "Show the editor 01_analysis/edit-plan.md; after they approve it (`reel approve-plan --by "
                       "editor`), build again."}
    return {"status": "REFUSED", "ok": False, "blocked": "edit plan not approved (or changed since approval)",
            "error": "The edit plan is not approved, or it changed after the approval: nothing was built.",
            "how": "Show the editor 01_analysis/edit-plan.md; after they approve it (`reel approve-plan --by editor`), "
                   "build again."}


def build_for_serve(data: dict, *, lock_wait_s: float | None = None) -> dict:
    """`reel serve`'s build_project (Addendum G2 R1): the CLI's `reel ppro-build`, never the raw bridge action. The reel
    is the one whose .prproj the request's project_path names; then the CLI's gates in its order (the episode window,
    Gate 1 approval of the current plan) and build() itself: the build lock, the editor-changes and unsaved-changes
    checks, `_prev_` parking and restore, the free-space check. overwrite_existing is --force; --replace-edited is
    never available from serve. The job is made from the approved plan: the request's other data is not used."""
    from .build_safety import reel_for_target, serve_context
    from .common import use_context
    from .reels import window_stale
    target = (data or {}).get("project_path")
    paths, why = reel_for_target(target, "07_premiere/project")
    ctx = serve_context(paths.root) if paths else None
    if paths and ctx is None:
        why = "The project file is in another client folder than the request: nothing was built."
    if why:
        return {"status": "REFUSED", "ok": False, "refused": why}
    with use_context(ctx):
        want = paths.p(f"07_premiere/project/{paths.video_id}_{project_prefix()}_EDIT.prproj")
        if Path(target).resolve() != want.resolve():
            return {"status": "REFUSED", "ok": False,
                    "refused": f"{Path(target).name} is not this reel's project file ({want.name}): nothing was built."}
        stale = window_stale(paths)
        if stale:
            return {"status": "REFUSED", "ok": False, "blocked": stale}
        refused = approval_refusal(paths)
        if refused:
            return refused
        r = build(paths, overwrite=(data or {}).get("overwrite_existing") is True, replace_edited=False,
                  lock_wait_s=lock_wait_s)
        if r.get("status") == "PRPROJ_BUILT":           # as cmd_ppro_build records it
            from .common import set_status
            set_status(paths, "PROJECT_ASSEMBLED", "native .prproj built in Premiere via WhyNot Cut Bridge",
                       "premiere_native", [r["project"]])
        return r


def parked_previous(paths: Paths) -> dict | None:
    """The newest `<project>_prev_*.prproj` when the project itself is missing: a build was hard-killed between moving
    the old project aside and putting it back (or Premiere never saved the new one). Reported with how to restore it;
    nothing is moved (Premiere may still be saving a claimed build at that path)."""
    prproj = paths.p(f"07_premiere/project/{paths.video_id}_{project_prefix()}_EDIT.prproj")
    if prproj.exists():
        return None
    import glob as _glob
    parked = sorted(prproj.parent.glob(f"{_glob.escape(prproj.stem)}_prev_*.prproj"))      # a stem with [ ] * ?
    if not parked:
        return None
    last = parked[-1]
    return {"file": str(last), "project": str(prproj),
            "how": f"A previous project was parked as {last.name} and no project is at the expected path "
                   f"({prproj.name}). Make sure Premiere is not building this reel, then rename {last.name} back to "
                   f"{prproj.name} to keep working in it, or run with --force to build a new project (the parked file "
                   "stays as a backup)."}


_PREV_SEQ = __import__("itertools").count()


def prev_name(prproj: Path) -> Path:
    """`<project>_prev_<YYYYmmdd-HHMMSS>-<microseconds><seq>.prproj`: unique below the second (two builds in one second
    on macOS once produced the same name) and still sorted oldest -> newest (parked_previous takes the last)."""
    import time
    while True:
        t = time.time()
        name = prproj.with_name(f"{prproj.stem}_prev_{time.strftime('%Y%m%d-%H%M%S', time.localtime(t))}-"
                                f"{int(t % 1 * 1e6):06d}{next(_PREV_SEQ) % 100:02d}.prproj")
        if not name.exists():
            return name


def _build_locked(paths: Paths, prproj: Path, overwrite: bool, replace_edited: bool) -> dict:
    # decided once the lock is held: the editor may save in Premiere while this build waits behind another one
    from .ppro_bridge import submit
    from .verify import editor_modified
    parked = parked_previous(paths)
    if parked and not overwrite:
        return {"status": "PREVIOUS_PARKED", "ok": False, "blocked": f"no {prproj.name}; a previous project is parked",
                "parked_previous": parked, "how": parked["how"]}
    if prproj.exists() and not overwrite:
        # T2.16: nothing was built, so not exit 0: a refusal (exit 2) that says how to rebuild
        return {"status": "EXISTS", "project": str(prproj), "refused": f"{prproj.name} already exists (nothing built)",
                "how": "re-run with --force to rebuild it (the previous version is kept as a backup)",
                "fix": "re-run with --force (previous version is kept as a backup)"}
    em = editor_modified(paths) if prproj.exists() else None
    if em and not replace_edited:
        return {"status": "EDITOR_CHANGES_PRESENT", "detail": em,
                "blocked": "the editor saved changes in Premiere after the last build",
                "fix": "The editor saved changes in Premiere after the last build. A rebuild starts from the plan, so their manual "
                       "edits would NOT carry over (the old file is kept as *_prev_*.prproj). Ask the editor; only with their OK "
                       "re-run with --force --replace-edited."}
    from .build_safety import files_size, free_space_refusal
    # G2 R1: before anything is written (the close below saves the open project): the project and its staged stills
    short = free_space_refusal(prproj.parent, files_size([prproj, *paths.p("03_broll").rglob("*.png")]))
    if short:
        return short
    backup = None
    closed = None
    if prproj.exists():
        from .verify import prproj_signature, signature_matches
        rec_p = paths.p("07_premiere/ppro-build-result.json")
        rec = read_json(rec_p, {}) or {}
        # what the pipeline saved last (else, for a project it never signed, the file as it is before the close)
        pipeline_sig = rec.get("content_signature") or prproj_signature(prproj)
        # close it in Premiere first: on Windows an open project locks the stills it uses, and they are re-rendered
        # below. The close SAVES the open project, so it may write the editor's unsaved work to disk (Gate 2 B2).
        # The signature leaves out what Premiere itself adds after the build's save (verify._VOLATILE_TAG).
        # save "if_clean": a Premiere that reports unsaved changes (dirty true) saves and closes nothing, and the build
        # stops before any write; dirty false / null (unknown, never taken as clean) keep the signature check below.
        closed = submit("close_project_path", {"path": str(prproj), "save": "if_clean"}, timeout=60)
        if (((closed or {}).get("response") or {}).get("result") or {}).get("dirty") is True:
            if not replace_edited:
                return {"status": "EDITOR_CHANGES_PRESENT", "closed_previous": (closed or {}).get("response"),
                        "detail": "unsaved changes in Premiere (nothing was saved or closed)",
                        "blocked": "the project open in Premiere has unsaved changes",
                        "fix": "The project is open in Premiere with unsaved changes (nothing was saved or closed). A "
                               "rebuild starts from the plan, so the editor's work would NOT carry over. Ask the "
                               "editor; only with their OK re-run with --force --replace-edited (the old file is kept "
                               "as *_prev_*.prproj)."}
            closed = submit("close_project_path", {"path": str(prproj), "save": "always"}, timeout=60)
        if not prproj.exists():
            after_sig, unchanged = pipeline_sig, True
        else:
            # hashed once; a c2/raw record is compared with it directly. No signature on either side (a project that
            # is not readable gzip) is a change: None == None must never let a rebuild go over the editor's work
            after_sig = prproj_signature(prproj)
            unchanged = bool(pipeline_sig and after_sig) and signature_matches(prproj, pipeline_sig, after_sig)
        if not unchanged and not replace_edited:
            # never recorded as the pipeline's: the record keeps the pipeline's signature, so the next run sees it too
            return {"status": "EDITOR_CHANGES_PRESENT", "closed_previous": (closed or {}).get("response"),
                    "detail": {"project": str(prproj), "content": "changed (saved by Premiere when the build closed "
                                                                  "the open project)"},
                    "blocked": "the project open in Premiere had changes that are not the pipeline's",
                    "fix": "Premiere saved the editor's work in this project when the build closed it. A rebuild starts "
                           "from the plan, so their manual edits would NOT carry over. Ask the editor; only with their "
                           "OK re-run with --force --replace-edited (the old file is kept as *_prev_*.prproj)."}
        if ((closed.get("response") or {}).get("result") or {}).get("closed") and not em and rec \
                and unchanged and prproj.exists():
            # that close saved the file without a change: the save is the pipeline's own, not the editor's (else a
            # failed rebuild would make the next one report EDITOR_CHANGES_PRESENT)
            rec["prproj_mtime"] = prproj.stat().st_mtime
            rec["closed_by_pipeline_at"] = now_iso()
            rec["content_signature"] = after_sig
            write_json(rec_p, rec)
    try:
        data = job_data(paths, overwrite, stage_media=True, fresh_stills=True)
    except Exception as e:              # 3.0 F1: stills from an older plan that could not be redrawn: nothing is built
        if not getattr(e, "stills_out_of_date", False):
            raise
        return {"status": "STILLS_OUT_OF_DATE", "ok": False, "error": e.error + ": nothing was built", "how": e.how}
    if data["_missing"]:
        return {"status": "MISSING_GRAPHICS", "ok": False, "missing": data["_missing"],      # T2.16: exit 1
                "error": f"{len(data['_missing'])} graphic still(s) missing: nothing was built",
                "how": "run `reel previews` (it renders the stills), then `reel ppro-build` again",
                "fix": "run `reel previews`"}
    import time
    t0 = time.time()
    r, claimed, restored, saved_now, submitting = {}, False, False, False, False
    try:
        if prproj.exists():
            # out of Premiere's way (it creates the new project at this path); it stays `_prev_` only if the build
            # saves a new project, else it is put back below
            backup = prev_name(prproj)
            prproj.rename(backup)
        submitting = True       # from here an exception without cep_queue's verdict may come after the job was queued
        r = submit("build_project", {k: v for k, v in data.items() if not k.startswith("_")},
                   timeout=build_timeout(data.get("duration_s")))
        claimed = bool(r.get("claimed"))
        submitting = False
        saved_now = prproj.exists() and prproj.stat().st_mtime >= t0 - 1      # before any restore below
    except BaseException as e:          # Ctrl-C, or an OSError writing the job: cep_queue says whether it was claimed
        # never downgrade a claimed job; no verdict at all (a second Ctrl-C inside cep_queue's own cleanup, T2.15)
        # while submitting = maybe queued: keep the backup aside rather than restore over a project Premiere may write
        claimed = claimed or bool(getattr(e, "wnc_claimed", submitting))
        raise
    finally:
        if backup and not prproj.exists() and not claimed:
            # nothing new was saved (and Premiere is not still working on it: a claimed job that timed out may yet
            # save there): the previous project goes back where the editor expects it
            try:
                backup.rename(prproj)
                backup, restored = None, True
            except OSError:
                pass                    # left parked: the next ppro-build reports it (parked_previous)
    resp = (r.get("response") or {})
    res = resp.get("result") or {}
    sa = res.get("settings_after", {})
    fw, fh = frame_size(paths)
    checks = {
        "prproj_saved_this_run": saved_now,
        "preview_codec_prores_422_lt": sa.get("previewCodec") == "apcs",
        f"frame_{fw}x{fh}": (sa.get("videoFrameWidth"), sa.get("videoFrameHeight")) == (fw, fh),
        f"fps_{seq_fps():.4g}": abs((sa.get("videoFrameRate") or {}).get("seconds", 0) - 1 / seq_fps()) < 1e-6,
        "linear_color_on": sa.get("compositeLinearColor") is True,
        "max_bit_depth_off": sa.get("maximumBitDepth") is False,
        "max_render_quality_off": sa.get("maximumRenderQuality") is False,
        "all_graphics_placed": len(res.get("placed", [])) == len(data["graphics"]),
        "v1_sharpened": (len(res.get("sharpened") or []) > 0 and all(x.get("ok") for x in res.get("sharpened") or []))
                        if data.get("sharpen_v1") else True,
        "caption_track_ok": bool(res.get("captionTrack")) if data["native_caption_track"] else True,
        "dialogue_on_A1_A2": all(a["clips"] > 0 for a in (res.get("tracks", {}).get("audio") or [])[:2]) if res.get("tracks") else False,
    }
    out = {"status": "PRPROJ_BUILT" if all(checks.values()) else ("PRPROJ_BUILT_WITH_ISSUES" if saved_now else "FAILED"),
           "checks": checks, "project": str(prproj), "bridge": {k: r.get(k) for k in ("ok", "elapsed_s", "job", "error")},
           "premiere_error": resp.get("error"), "previous_version_backup": str(backup) if backup else None,
           "previous_restored": restored,
           "closed_previous": (closed or {}).get("response"),
           "job_data": {k: data.get(k) for k in ("sequence_name", "track_names", "native_caption_track")},   # for the handoff
           "result": res, "at": now_iso(), "prproj_mtime": prproj.stat().st_mtime if prproj.exists() else None}
    if r.get("how"):
        out["how"] = r["how"]
    if data.get("_warnings"):           # G72: captions drawn with a system Arabic fallback, or no Arabic font at all
        out["warnings"] = data["_warnings"]
    if data.get("_stills_redrawn"):     # 3.0 F1: graphics drawn from an older plan, redrawn before they were placed
        out["stills_redrawn"] = data["_stills_redrawn"]
    if parked:                          # --force over a parked project: it stays a backup; say where
        out["parked_previous"] = parked
    from .verify import prproj_signature
    # what the pipeline saved: a later save that only moves the file time (Premiere saving open projects, auto-save)
    # is not an editor change (verify.editor_modified)
    if not (restored and not saved_now):         # (else the previous record's signature is kept, below: no parse)
        out["content_signature"] = prproj_signature(prproj) if prproj.exists() else None
    if restored and not saved_now:
        # Gate 2 B1: the project on disk is the PREVIOUS one again (maybe with the editor's work): the record keeps what
        # the pipeline saved last, so verify.editor_modified still sees the editor's changes on the next --force
        from .verify import prproj_build_time
        prev = read_json(paths.p("07_premiere/ppro-build-result.json"), {}) or {}
        out["prproj_mtime"] = prproj_build_time(paths, prproj)
        out["content_signature"] = prev.get("content_signature")
        if prev.get("closed_by_pipeline_at"):
            out["closed_by_pipeline_at"] = prev["closed_by_pipeline_at"]
        if prev.get("project"):
            out["project"] = prev["project"]
        # (a project the pipeline never built: no mtime/signature, so any later save of it counts as the editor's)
    write_json(paths.p("07_premiere/ppro-build-result.json"), out)
    return out


MEDIA_WAIT_S, MEDIA_POLL_S = 30.0, 3.0      # wait for Premiere's media before the frames are exported (G69)


def export_frames(paths: Paths, times: list[float] | None = None, *, retries: int = 3, wait_s: float = 5.0,
                  media_wait_s: float = MEDIA_WAIT_S, media_poll_s: float = MEDIA_POLL_S,
                  lock_wait_s: float | None = None) -> dict:
    """Premiere renders frames of its own timeline. Each run gets a FRESH folder (old frames left next to new ones
    once misled a review) plus a labelled contact sheet `_sheet.jpg` for the reviewer.

    Right after a project opens, Premiere may still be loading media and exports its "Media pending" slate instead of
    the picture (G69). So, first, one frame is exported into a scratch folder every `media_poll_s` until it shows the
    picture, for up to `media_wait_s` (0 = no wait); then all frames are exported. Slate frames are detected
    (media_pending.py), exported again after a wait that grows with each attempt (`wait_s`, 2*`wait_s`, ...) up to
    `retries` times, and if they are still the slate they are reported under `media_pending` / `pending_frames` instead
    of counted as frames: a slate says nothing about the edit, and the result is never ok while one remains.
    Holds the bridge's build lock (one Premiere build or frame export at a time on this machine)."""
    from . import cep_queue
    from .ppro_bridge import build_lock
    wait = cep_queue.LOCK_WAIT_S if lock_wait_s is None else lock_wait_s
    try:
        with build_lock(f"ppro-frames {paths.video_id}", hold_s=LOCK_HOLD_S, wait_s=wait):
            return _export_frames(paths, times, retries, wait_s, media_wait_s, media_poll_s)
    except cep_queue.BuildLockBusy as e:
        r = cep_queue.lock_busy_result(e, "Premiere")
        return dict(r, ok=False, error=r["blocked"], frames=0, media_pending=[], pending_frames=[])


def _wait_for_media(export, probe_dir: Path, t: float, limit_s: float, poll_s: float) -> dict:
    """Export the frame at `t` into `probe_dir` until it is not Premiere's Media pending slate. online: True (the
    picture), False (still the slate after `limit_s`), None (Premiere wrote no frame: the export itself reports why)."""
    import shutil
    import time as _t
    from .media_pending import is_media_pending
    polls, online = 0, None
    probe_dir.mkdir(parents=True, exist_ok=True)
    try:
        while True:
            for f in probe_dir.glob("*.png"):
                f.unlink(missing_ok=True)
            polls += 1
            export([t], probe_dir)
            got = sorted(probe_dir.glob("*.png"))
            if not got:
                online = None
                break
            if not is_media_pending(got[0]):
                online = True
                break
            if polls * poll_s >= limit_s:           # counted, not timed: the waits are the polls' own
                online = False
                break
            _t.sleep(poll_s)
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)
    return {"online": online, "polls": polls, "limit_s": limit_s}


def _export_frames(paths: Paths, times, retries: int, wait_s: float, media_wait_s: float, media_poll_s: float) -> dict:
    import time as _t
    from .ppro_bridge import submit
    from .common import frame_to_tc
    from .media_pending import is_media_pending
    from .stamps import read_compiled
    spec = read_compiled(paths.p("01_analysis/timeline-spec.json"))
    labels = {}
    if times is None:
        for e in spec["events"]:
            if e["template"] == "flash_transition":
                continue
            t = round((e["start_frame"] + (e["end_frame"] - e["start_frame"]) * 0.7) / seq_fps(), 3)
            labels.setdefault(t, f"{e['event_id']} {e['template']}")
        # source cutaways (the card whole over a blurred fill) and camera moves are checked in Premiere's own frames too
        for m in spec["main_segments"]:
            if m.get("decision_id") and m["end_frame"] - m["start_frame"] >= 6:
                t = round((m["start_frame"] + m["end_frame"]) / 2 / seq_fps(), 3)
                labels.setdefault(t, f"{m['decision_id']} {m['camera']}")
        end = spec["duration_frames"] / seq_fps()
        times = sorted(t for t in set(labels) | {2.5, end * 0.15, end * 0.5, end - 0.5} if 0 <= t < end)
        times = sorted({round(t, 3) for t in times})
    od = paths.p(f"08_quality_control/premiere_frames/run-{_t.strftime('%Y%m%d-%H%M%S')}")
    od.mkdir(parents=True, exist_ok=True)
    t0 = _t.time()
    prj = paths.p(f"07_premiere/project/{paths.video_id}_{project_prefix()}_EDIT.prproj")

    def export(ts, out_dir=od):
        return submit("export_frames", {"sequence_name": f"{paths.video_id}_{project_prefix()}_EDIT", "times": ts,
                                        "out_dir": str(out_dir), "project_path": str(prj) if prj.exists() else None},
                      timeout=600)

    def pngs():
        return sorted(f for f in od.glob("*.png") if not f.name.startswith("._") and f.stat().st_mtime >= t0 - 1)

    def ms_of(f):
        return next((int(tok) for tok in f.stem.split("_") if tok.isdigit()), None)
    media = {"online": None, "polls": 0, "limit_s": media_wait_s}
    if media_wait_s > 0 and times:
        media = _wait_for_media(export, od / "_media_check", times[len(times) // 2], media_wait_s, media_poll_s)
    r = export(times)
    all_frames = pngs()
    pending = [f for f in all_frames if is_media_pending(f)]
    ever_pending, attempts, by_ms = {ms_of(f) for f in pending}, 0, {round(t * 1000): t for t in times}
    while pending and attempts < retries:
        attempts += 1
        _t.sleep(wait_s * attempts)                      # media loads in the background: give it longer each time
        parked = {}
        for f in pending:                                # the re-export must not depend on overwriting: park the slate
            try:
                f.replace(f.with_suffix(".slate"))
                parked[f] = f.with_suffix(".slate")
            except OSError:
                pass
        export(sorted(by_ms.get(ms_of(f), (ms_of(f) or 0) / 1000) for f in pending))
        for f, park in parked.items():
            if f.exists():
                park.unlink(missing_ok=True)
            else:                                        # the re-export wrote nothing: the slate is still what we have
                park.replace(f)
        pending = [f for f in pending if f.exists() and is_media_pending(f)]
    all_frames = pngs()
    frames = [f for f in all_frames if f not in pending]            # a slate is not a frame of the edit
    media_pending = [{"t": by_ms.get(ms_of(f), (ms_of(f) or 0) / 1000), "file": str(f), "retries": attempts} for f in pending]
    def label(f):
        ms = ms_of(f)
        t = ms / 1000 if ms is not None else None
        tc = frame_to_tc(round(t * seq_fps())) if t is not None else ""
        lab = labels.get(round(t, 3), "") if t is not None else ""
        return f"{tc} {lab}"[:44]
    from .media_util import contact_sheet
    sheet = contact_sheet([(f, label(f)) for f in frames], od / "_sheet.jpg", cols=6, tile_w=270, tile_h=480,
                          label_h=18, label_xy=(4, 3))
    # Premiere reports failures per frame inside a successful job: surface them (0 frames must never look like success)
    per_frame = ((r.get("response") or {}).get("result") or {}).get("frames") or []
    frame_errors = sorted({f["error"] for f in per_frame if f.get("error")})
    error = None if r.get("ok") else (r.get("response") or r.get("error"))
    if not error and len(all_frames) < len(times):
        error = f"{len(times) - len(all_frames)} of {len(times)} frames missing" + (f": {frame_errors}" if frame_errors else "")
    if media_pending:
        slate = (f"{len(media_pending)} of {len(times)} frames are Premiere's 'Media pending' slate (the media was still "
                 f"loading) after {attempts} re-export{'s' if attempts != 1 else ''}")
        error = f"{error}; {slate}" if error else slate
    nxt = ("VIEW the sheet (qc-reviewer: fan out frame-inspectors over the PNGs), then the lead records "
           "`reel verify --record --verdict pass|fail --sheet <sheet> --note \"...\"`")
    if media_pending:
        nxt = (f"{len(media_pending)} frame(s) are Premiere's 'Media pending' slate, listed under media_pending and left "
               "out of the sheet: a Media pending frame is neither a pass nor a fail. Wait until Premiere has finished "
               "loading the project's media, run `reel ppro-frames` again, and judge only frames that show the picture. "
               + nxt)
    return {"bridge": r.get("ok"), "ok": not error, "dir": str(od), "frames": len(frames), "expected": len(times),
            "sheet": str(sheet) if sheet else None, "error": error, "media_pending": media_pending,
            "pending_frames": [m["t"] for m in media_pending], "media_wait": media,
            "pending_retries": {"attempts": attempts, "wait_s": wait_s,
                                "recovered": sorted(by_ms.get(m, (m or 0) / 1000) for m in ever_pending
                                                    if m not in {ms_of(f) for f in pending}),
                                "still_pending": sorted(m["t"] for m in media_pending)},
            "next": nxt}
