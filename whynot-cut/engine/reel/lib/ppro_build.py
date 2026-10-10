"""Premiere-only build through the WhyNot Cut Bridge: a real .prproj created and saved by Premiere itself.

Footage, punch-ins, dialogue and SFX come from the base XML (imported INSIDE Premiere); graphics
are brand stills placed on named tracks and animated with Premiere keyframes; captions are a
native, editable caption track; sequence settings are applied via Premiere's API and read back.
No After Effects involved.
"""
from __future__ import annotations

from pathlib import Path

from .common import still_category, caption_hide_default, Paths, seq_fps, project_prefix, load_config, ms_to_frame, now_iso, read_json, write_json
from . import srt as srtlib
from .plan import norm, to_ms

SETTINGS = {  # user's sequence spec; verified field names/values from Premiere 26.5 getSettings()
    "previewCodec": "apcs",               # Apple ProRes 422 LT
    "previewFrameWidth": 1080, "previewFrameHeight": 1920,
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


def job_data(paths: Paths, overwrite: bool = False, stage_media: bool = False) -> dict:
    from .premiere_xml import build_xml
    from .previews import render_captions
    from .timemap import TimeMap
    spec = read_json(paths.p("01_analysis/timeline-spec.json"))
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
    # captions never sit on a card (name card etc.): while one is up, captions move above its top edge
    avoid = []
    for e in spec["events"]:
        if e["template"] in ("name_card", "glass_card", "cta"):
            png = paths.p(f"03_broll/typography/{e['event_id']}.png")
            if png.exists():
                from PIL import Image
                bb = Image.open(png).getchannel("A").getbbox()
                if bb:
                    avoid.append((e["start_ms"], e["end_ms"], bb[1]))
    caps = render_captions(paths, hidden, avoid=avoid)
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
    vnames = ["V1 Main Footage" + (" (+ blurred fill under cutaways)" if cut_off else "")] +         (["V2 Source cutaways (whole)"] if cut_off else []) +         [f"V{i + 2 + cut_off} {LANE_NAMES.get(ln, 'Checklist item ' + ln[4:])}" for i, ln in enumerate(lanes)]
    dlg = "Dialogue (clean)" if paths.p("06_audio/dialogue/dialogue_clean.wav").exists() else "Dialogue (camera, not cleaned)"
    anames = [f"A1 {dlg} L", f"A2 {dlg} R"]
    for k in base["tracks"]["audio"][1:]:
        nm = k["name"].replace(" (L/R mono pair)", "")
        anames += [f"A{len(anames) + 1} {nm} L", f"A{len(anames) + 2} {nm} R"]
    return {"project_path": str(paths.p(f"07_premiere/project/{paths.video_id}_{project_prefix()}_EDIT.prproj")),
            "overwrite_existing": overwrite, "xml_path": base["xml"], "sequence_name": base["sequence_name"],
            "settings": SETTINGS, "graphics": g_out, "srt_path": str(paths.p("02_transcription/subtitles-seq.srt")),
            "native_caption_track": bool(g.get("native_caption_track", False)),
            "markers": markers, "track_names": {"video": vnames, "audio": anames}, "_missing": missing,
            "blur_v1_clips": (base.get("cutaways") or {}).get("blur_v1_clip_indices") or [],
            "_lanes": lanes, "duration_s": spec["duration_frames"] * F}


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


def build(paths: Paths, overwrite: bool = False, replace_edited: bool = False) -> dict:
    from .ppro_bridge import submit, status
    st = status()
    if not st["alive"]:
        return {"status": "BRIDGE_NOT_RUNNING", "detail": st["detail"]}
    prproj = paths.p(f"07_premiere/project/{paths.video_id}_{project_prefix()}_EDIT.prproj")
    backup = None
    if prproj.exists() and not overwrite:
        return {"status": "EXISTS", "project": str(prproj), "fix": "re-run with --force (previous version is kept as a backup)"}
    from .verify import editor_modified
    em = editor_modified(paths) if prproj.exists() else None
    if em and not replace_edited:
        return {"status": "EDITOR_CHANGES_PRESENT", "detail": em,
                "fix": "The editor saved changes in Premiere after the last build. A rebuild starts from the plan, so their manual "
                       "edits would NOT carry over (the old file is kept as *_prev_*.prproj). Ask the editor; only with their OK "
                       "re-run with --force --replace-edited."}
    closed = None
    if prproj.exists():
        # close it in Premiere first (saved, nothing lost): on Windows an open project locks the stills it uses, and they
        # are re-rendered below
        closed = submit("close_project_path", {"path": str(prproj)}, timeout=60)
        if ((closed.get("response") or {}).get("result") or {}).get("closed") and not em:
            # that close saved the file: the save is the pipeline's own, not the editor's (else a failed rebuild would
            # make the next one report EDITOR_CHANGES_PRESENT)
            rec = read_json(paths.p("07_premiere/ppro-build-result.json"), {})
            if rec:
                rec["prproj_mtime"] = prproj.stat().st_mtime
                rec["closed_by_pipeline_at"] = now_iso()
                write_json(paths.p("07_premiere/ppro-build-result.json"), rec)
    data = job_data(paths, overwrite, stage_media=True)
    if data["_missing"]:
        return {"status": "MISSING_GRAPHICS", "missing": data["_missing"], "fix": "run `reel previews`"}
    if prproj.exists():
        import time as _t
        backup = prproj.with_name(f"{prproj.stem}_prev_{_t.strftime('%Y%m%d-%H%M%S')}.prproj")
        prproj.rename(backup)
    import time
    t0 = time.time()
    r = submit("build_project", {k: v for k, v in data.items() if not k.startswith("_")}, timeout=900)
    resp = (r.get("response") or {})
    res = resp.get("result") or {}
    saved_now = prproj.exists() and prproj.stat().st_mtime >= t0 - 1
    sa = res.get("settings_after", {})
    checks = {
        "prproj_saved_this_run": saved_now,
        "preview_codec_prores_422_lt": sa.get("previewCodec") == "apcs",
        "frame_1080x1920": (sa.get("videoFrameWidth"), sa.get("videoFrameHeight")) == (1080, 1920),
        f"fps_{seq_fps():.4g}": abs((sa.get("videoFrameRate") or {}).get("seconds", 0) - 1 / seq_fps()) < 1e-6,
        "linear_color_on": sa.get("compositeLinearColor") is True,
        "max_bit_depth_off": sa.get("maximumBitDepth") is False,
        "max_render_quality_off": sa.get("maximumRenderQuality") is False,
        "all_graphics_placed": len(res.get("placed", [])) == len(data["graphics"]),
        "caption_track_ok": bool(res.get("captionTrack")) if data["native_caption_track"] else True,
        "dialogue_on_A1_A2": all(a["clips"] > 0 for a in (res.get("tracks", {}).get("audio") or [])[:2]) if res.get("tracks") else False,
    }
    out = {"status": "PRPROJ_BUILT" if all(checks.values()) else ("PRPROJ_BUILT_WITH_ISSUES" if saved_now else "FAILED"),
           "checks": checks, "project": str(prproj), "bridge": {k: r.get(k) for k in ("ok", "elapsed_s", "job", "error")},
           "premiere_error": resp.get("error"), "previous_version_backup": str(backup) if backup else None,
           "closed_previous": (closed or {}).get("response"),
           "result": res, "at": now_iso(), "prproj_mtime": prproj.stat().st_mtime if prproj.exists() else None}
    write_json(paths.p("07_premiere/ppro-build-result.json"), out)
    return out


def export_frames(paths: Paths, times: list[float] | None = None) -> dict:
    """Premiere renders frames of its own timeline. Each run gets a FRESH folder (old frames left next to new ones
    once misled a review) plus a labelled contact sheet `_sheet.jpg` for the reviewer."""
    import time as _t
    from .ppro_bridge import submit
    from .common import frame_to_tc
    spec = read_json(paths.p("01_analysis/timeline-spec.json"))
    labels = {}
    if times is None:
        for e in spec["events"]:
            if e["template"] == "flash_transition":
                continue
            t = round((e["start_frame"] + (e["end_frame"] - e["start_frame"]) * 0.7) / seq_fps(), 3)
            labels.setdefault(t, f"{e['event_id']} {e['template']}")
        end = spec["duration_frames"] / seq_fps()
        times = sorted(t for t in set(labels) | {2.5, end * 0.15, end * 0.5, end - 0.5} if 0 <= t < end)
        times = sorted({round(t, 3) for t in times})
    od = paths.p(f"08_quality_control/premiere_frames/run-{_t.strftime('%Y%m%d-%H%M%S')}")
    od.mkdir(parents=True, exist_ok=True)
    t0 = _t.time()
    r = submit("export_frames", {"sequence_name": f"{paths.video_id}_{project_prefix()}_EDIT", "times": times, "out_dir": str(od)}, timeout=600)
    frames = sorted(f for f in od.glob("*.png") if not f.name.startswith("._") and f.stat().st_mtime >= t0 - 1)
    sheet = None
    if frames:
        from PIL import Image, ImageDraw
        cols, w, h = 6, 270, 480
        rows = (len(frames) + cols - 1) // cols
        im = Image.new("RGB", (cols * w, rows * (h + 18)), "black")
        d = ImageDraw.Draw(im)
        for i, f in enumerate(frames):
            x, y = (i % cols) * w, (i // cols) * (h + 18)
            im.paste(Image.open(f).convert("RGB").resize((w, h)), (x, y + 18))
            ms = next((int(tok) for tok in f.stem.split("_") if tok.isdigit()), None)
            t = ms / 1000 if ms is not None else None
            tc = frame_to_tc(round(t * seq_fps())) if t is not None else ""
            lab = labels.get(round(t, 3), "") if t is not None else ""
            d.text((x + 4, y + 3), f"{tc} {lab}"[:44], fill="yellow")
        sheet = od / "_sheet.jpg"
        im.save(sheet, quality=85)
    # Premiere reports failures per frame inside a successful job: surface them (0 frames must never look like success)
    per_frame = ((r.get("response") or {}).get("result") or {}).get("frames") or []
    frame_errors = sorted({f["error"] for f in per_frame if f.get("error")})
    error = None if r.get("ok") else (r.get("response") or r.get("error"))
    if not error and len(frames) < len(times):
        error = f"{len(times) - len(frames)} of {len(times)} frames missing" + (f": {frame_errors}" if frame_errors else "")
    return {"bridge": r.get("ok"), "ok": not error, "dir": str(od), "frames": len(frames), "expected": len(times),
            "sheet": str(sheet) if sheet else None, "error": error,
            "next": "VIEW the sheet (qc-reviewer: fan out frame-inspectors over the PNGs), then the lead records "
                    "`reel verify --record --verdict pass|fail --sheet <sheet> --notes ...`"}
