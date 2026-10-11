"""Stage 5 compiler: validates Claude-authored edit decisions against the real transcript and
compiles a frame-accurate timeline spec, B-roll manifest, and audio cue sheet.

Input  : 01_analysis/edit-decisions.json  (authored per references/edit-decision-engine.md)
Outputs: 01_analysis/timeline-spec.json, 03_broll/broll-manifest.json,
         06_audio/audio-cue-sheet.json, 01_analysis/plan-validation.json
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .common import (still_category, seq_fps, Paths, fmt_ts, frame_to_tc, load_config, ms_to_frame, now_iso,
                     parse_ts, read_json, write_json)

SFX_TRACK = {"whoosh": "A04", "whoosh_soft": "A04", "riser_soft": "A04", "flash": "A04",
             "pop": "A05", "click": "A05", "tick": "A05", "hit_soft": "A03", "shimmer": "A05"}
VALID_CAMERA = {"hold", "punch_in", "punch_out", "slow_push", "reframe"}
VALID_CONF = {"high", "medium", "low"}

_AR_DIAC = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")


# hamza seats -> the bare letter (دائما = دايما, سؤال = سوال), ta marbuta, alef maqsura, Arabic-Indic and Persian digits
_AR_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ؤ": "و", "ئ": "ي", "ة": "ه", "ى": "ي",
                          **{chr(0x660 + i): str(i) for i in range(10)}, **{chr(0x6F0 + i): str(i) for i in range(10)}})


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    # ئو is the Egyptian spelling of MSA ؤو (مسئول = مسؤول, شئون = شؤون): same word, one form
    s = _AR_DIAC.sub("", s).replace("ئو", "ؤو").translate(_AR_FOLD)
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


ONSCREEN_KEYS = ("text", "headline", "title", "subtitle", "name", "label", "lines", "items", "quote", "body", "caption",
                 "value")


def onscreen_strings(params) -> list:
    """Every piece of text a graphic puts on screen (text, headline, lines, checklist items ...)."""
    out = []
    if isinstance(params, str):
        return [params]
    if isinstance(params, list):
        for x in params:
            out += onscreen_strings(x)
    elif isinstance(params, dict):
        for k, v in params.items():
            if k in ONSCREEN_KEYS:
                out += onscreen_strings(v)
    return out


def subtract_ranges(keep: list, cuts: list) -> list:
    """keep ranges minus cut ranges (all [a, b) in ms), in order, dropping slivers under 40 ms."""
    out = []
    for a, b in keep:
        segs = [(a, b)]
        for c0, c1 in sorted(cuts):
            nxt = []
            for s, e in segs:
                if c1 <= s or c0 >= e:
                    nxt.append((s, e))
                    continue
                if c0 > s:
                    nxt.append((s, c0))
                if c1 < e:
                    nxt.append((c1, e))
            segs = nxt
        out += [(int(s), int(e)) for s, e in segs if e - s >= 40]
    return out


def union_ranges(a: list, b: list) -> list:
    """Union of two lists of [start, end) ranges in ms, merged and sorted (touching ranges join)."""
    out = []
    for s, e in sorted([list(x) for x in a] + [list(x) for x in b]):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([int(s), int(e)])
    return out


def word_cut_ranges(words: list, cut_words: list, dur_ms: int, pad_ms: int = 30) -> tuple[list, list, list]:
    """global.cut_words -> ([a, b] ms ranges, cut word records, errors). Each word is cut from just before it starts to
    just after it ends, never into its neighbours, so the words around it stay whole.
    Entries: a word id, or {"word_ids": [..], "reason": "..."}."""
    by_id = {w["id"]: w for w in words}
    order = sorted(by_id)
    pos = {wid: i for i, wid in enumerate(order)}
    ranges, cut, errors = [], [], []
    for c in cut_words:
        ids = c.get("word_ids", []) if isinstance(c, dict) else [c]
        reason = c.get("reason", "") if isinstance(c, dict) else ""
        for wid in ids:
            w = by_id.get(wid)
            if not w:
                errors.append(f"cut_words: word {wid} not in words.json")
                continue
            i = pos[wid]
            prev = by_id[order[i - 1]] if i > 0 else None
            nxt = by_id[order[i + 1]] if i + 1 < len(order) else None
            a = max(w["start_ms"] - pad_ms, prev["end_ms"] if prev else 0)
            b = min(w["end_ms"] + pad_ms, nxt["start_ms"] if nxt else dur_ms)
            ranges.append((a, max(a, b)))
            cut.append({"word_id": wid, "word": w["word"], "start_ms": w["start_ms"], "reason": reason})
    return ranges, cut, errors


def window_rect(framing: str | None, y: int | None = None, seq_w: int = 1080, seq_h: int = 1920) -> dict | None:
    """The picture window of a framing mode: "4:5" -> 1080x1350 (centred unless global.framing_window_y); "9:16" -> None
    (the picture fills the frame)."""
    f = str(framing or "9:16").replace("x", ":").strip()
    if f in ("9:16", "full", ""):
        return None
    try:
        a, b = (float(v) for v in f.split(":"))
    except ValueError:
        return None
    h = min(seq_h, int(round(seq_w * b / a)))
    top = int(y) if y is not None else (seq_h - h) // 2
    return {"w": seq_w, "h": h, "y": max(0, min(seq_h - h, top)), "mode": f}


def main_video(pre: dict, main: str | None) -> dict | None:
    """Preflight's video info for THIS video's footage (matched by file name); without a named footage, the first file."""
    vids = [f for f in (pre or {}).get("files", []) if f.get("video")]
    if main:
        return next((f["video"] for f in vids if Path(f["path"]).name == Path(main).name), None)
    return vids[0]["video"] if vids else None


def to_ms(v) -> int:
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(round(v * 1000))
    v = str(v).strip()
    if re.fullmatch(r"\d+(\.\d+)?", v):
        return int(round(float(v) * 1000))
    if v.count(":") == 1:
        v = "00:" + v
    return parse_ts(v)


def _transcript_text(paths: Paths) -> tuple[str, int]:
    tj = read_json(paths.p("02_transcription/transcript.json"))
    if not tj:
        raise FileNotFoundError("02_transcription/transcript.json missing — transcribe first")
    from . import srt as srtlib
    srt_p = paths.p("02_transcription/subtitles.srt")
    text = " ".join(s["text"] for s in tj["segments"])
    if srt_p.exists():  # include human-corrected SRT wording
        text += " " + " ".join(c["text"].replace("\n", " ") for c in srtlib.read_srt(srt_p))
    return norm(text), tj["meta"]["duration_ms"]


def compile_plan(paths: Paths) -> dict:
    FPS_ = seq_fps()   # the client's sequence rate (24, 25, 29.97 ...)
    ed = read_json(paths.p("01_analysis/edit-decisions.json"))
    if not ed:
        raise FileNotFoundError("01_analysis/edit-decisions.json missing — author it (see references/edit-decision-engine.md)")
    tpl = load_config("graphics-templates.json")["templates"]
    manifest = read_json(paths.client_db / "asset-manifest.json", {"assets": []})
    known_assets = {a["rel"]: a for a in manifest["assets"]}
    ttext, dur_ms = _transcript_text(paths)
    dur_f = ms_to_frame(dur_ms)
    errors, warnings = [], []
    events, cues, broll, camera = [], [], [], []
    seen_ids = set()

    def chk_range(label, a, b):
        if b <= a:
            errors.append(f"{label}: end <= start")
        if a < 0 or b > dur_ms + 40:
            errors.append(f"{label}: outside media duration {fmt_ts(dur_ms)}")

    for d in ed.get("decisions", []):
        did = d.get("decision_id")
        if not did or did in seen_ids:
            errors.append(f"decision id missing/duplicate: {did}")
        seen_ids.add(did)
        for req in ("segment_id", "evidence", "start", "end", "semantic_intent", "visual_treatment", "confidence"):
            if d.get(req) in (None, ""):
                errors.append(f"{did}: missing '{req}'")
        if d.get("confidence") and d["confidence"] not in VALID_CONF:
            errors.append(f"{did}: confidence must be one of {VALID_CONF}")
        ev = norm(d.get("evidence", ""))
        if ev and ev not in ttext:
            # allow evidence made of '…'-joined fragments
            frags = [norm(f) for f in re.split(r"…|\.\.\.", d.get("evidence", "")) if norm(f)]
            if not frags or not all(f in ttext for f in frags):
                errors.append(f"{did}: evidence not found verbatim in transcript: {d.get('evidence')!r}")
        s_ms, e_ms = to_ms(d["start"]), to_ms(d["end"])
        chk_range(did, s_ms, e_ms)
        d["_start_ms"], d["_end_ms"] = s_ms, e_ms

        cam = d.get("camera")
        if cam:
            ctype = cam.get("type", "hold")
            if ctype not in VALID_CAMERA:
                errors.append(f"{did}: camera.type {ctype} invalid")
            at = to_ms(cam.get("at", d["start"]))
            camera.append({"decision_id": did, "type": ctype, "at_ms": at, "frame": ms_to_frame(at),
                           "until_ms": to_ms(cam["until"]) if cam.get("until") else e_ms,
                           "scale_factor": float(cam.get("scale_factor", 1.0)),
                           "offset_y": float(cam.get("offset_y", 0.0)), "offset_x": float(cam.get("offset_x", 0.0)),
                           "rationale": cam.get("rationale", "")})

        for g in d.get("graphics", []):
            gid = g.get("id")
            t = g.get("template")
            if not gid or gid in seen_ids:
                errors.append(f"{did}: graphic id missing/duplicate {gid}")
            seen_ids.add(gid)
            if t not in tpl:
                errors.append(f"{gid}: unknown template {t}")
                continue
            gs, ge = to_ms(g.get("start", d["start"])), to_ms(g.get("end", d["end"]))
            chk_range(gid, gs, ge)
            if not (s_ms - 40 <= gs and ge <= e_ms + 2000):
                warnings.append(f"{gid}: graphic extends well beyond its decision window")
            for it in g.get("items", []):
                it["_at_ms"] = to_ms(it["at"]) if "at" in it else gs
                if not (gs <= it["_at_ms"] < ge):
                    errors.append(f"{gid}: item '{it.get('text')}' at outside graphic span")
            imgs = [g["image"]] if g.get("image") else []
            for im in imgs:
                if im not in known_assets and not (paths.root / im).exists():
                    errors.append(f"{gid}: image not found in client asset manifest: {im}")
            if t == "broll_video":
                vid = g.get("video")
                if not vid or not (paths.root / vid).exists():
                    errors.append(f"{gid}: broll_video needs 'video' = an existing file (e.g. data/Broll/clip.mp4), got {vid!r}")
                elif not any(k in vid.lower() for k in ("broll", "b-roll", "b_roll", "stock")):
                    warnings.append(f"{gid}: {vid} is not in the licensed B-roll folder (data/Broll): confirm the licence")
                imgs = [vid] if vid else []
            if t in ("hook_title", "term_callout", "glass_card", "cta", "broll_card", "context_card") and \
                    not (g.get("text") or g.get("headline")):
                errors.append(f"{gid}: template {t} needs text/headline")
            if t == "stat_card" and not str(g.get("value") or "").strip():
                errors.append(f"{gid}: template stat_card needs a value (the number or result the speaker said)")
            info = tpl[t]
            ev_ = {"event_id": gid, "decision_id": did, "segment_id": d.get("segment_id"),
                   "template": t, "track": info["track"], "track_name": info["track_name"],
                   "start_ms": gs, "end_ms": ge, "start_frame": ms_to_frame(gs), "end_frame": ms_to_frame(ge),
                   "start_tc": frame_to_tc(ms_to_frame(gs)), "end_tc": frame_to_tc(ms_to_frame(ge)),
                   "params": {k: v for k, v in g.items() if k not in ("id", "template", "start", "end")},
                   "evidence": d.get("evidence"),
                   "approval_required": False if t == "flash_transition" else
                   bool(g.get("approval_required", d.get("approval_required", False)))}
            for it in ev_["params"].get("items", []):
                it["frame"] = ms_to_frame(it.pop("_at_ms"))
                it["rel_frame"] = it["frame"] - ev_["start_frame"]
            events.append(ev_)
            broll.append({
                "asset_id": gid, "segment_id": d.get("segment_id"), "decision_id": did,
                "source_timestamp": fmt_ts(gs, "."), "sequence_start_frame": ev_["start_frame"],
                "duration_frames": ev_["end_frame"] - ev_["start_frame"], "asset_type": info["category"],
                "template": t, "visual_concept": g.get("concept", d.get("visual_treatment")),
                "source_files": imgs, "brand_refs": ["client_database/branding/brand-tokens.json",
                                                     "client_database/branding/typography.json"],
                "method": "after_effects_comp (editable) + pillow_preview_png (fallback)",
                "output_paths": {"ae_comp": f"{gid}", "ae_render": f"04_after_effects/compositions/{gid}.mov",
                                 "preview_png": f"03_broll/{still_category(t)}/{gid}.png"},
                "approval_status": "PENDING_APPROVAL" if ev_["approval_required"] else "AUTO_APPROVED_STYLE",
                "validation_status": "PLANNED"})
            # template default sound
            if g.get("sfx", info.get("sfx")) and g.get("sfx") != "none":
                kind = g.get("sfx", info.get("sfx"))
                cues.append({"cue_id": f"SFX_{gid}", "kind": kind, "at_ms": gs, "related_visual": gid,
                             "decision_id": did, "segment_id": d.get("segment_id"), "auto": True,
                             "gain_db": g.get("sfx_gain_db", -14)})
                for it in g.get("items", [])[1:] if t == "checklist" else []:
                    cues.append({"cue_id": f"SFX_{gid}_{it['frame']}", "kind": "tick",
                                 "at_ms": round(it["frame"] * 1000 / FPS_), "related_visual": gid,
                                 "decision_id": did, "segment_id": d.get("segment_id"), "auto": True, "gain_db": -18})

        for s in d.get("sound", []):
            at = to_ms(s.get("at", d["start"]))
            cues.append({"cue_id": s.get("cue_id") or f"SFX_{did}_{at}", "kind": s.get("type", "pop"),
                         "at_ms": at, "related_visual": s.get("related_visual"), "decision_id": did,
                         "segment_id": d.get("segment_id"), "auto": False, "gain_db": s.get("gain_db", -14),
                         "note": s.get("note", "")})

    # overlap check per track (same track may not overlap)
    by_track = {}
    for e in events:
        by_track.setdefault(e["track"], []).append(e)
    for tr, evs in by_track.items():
        evs.sort(key=lambda e: e["start_frame"])
        for a, b in zip(evs, evs[1:]):
            if b["start_frame"] < a["end_frame"]:
                errors.append(f"track {tr}: {a['event_id']} overlaps {b['event_id']}")

    # podcast reels follow their content-type recipe (00_inputs/source.json); deviations are warnings the editor sees
    # at Gate 1, with the story-editor's reason when a decision carries `recipe_note`
    from .recipes import for_paths
    recipe = for_paths(paths)
    recipe_info = None
    if recipe:
        rt, dev = recipe.get("type"), []
        notes = [f"{d['decision_id']}: {d['recipe_note']}" for d in ed.get("decisions", []) if d.get("recipe_note")]
        g = recipe.get("graphics") or {}
        starts = sorted(e["start_ms"] for e in events if e["template"] != "flash_transition")
        if g.get("max_per_30s") is not None and starts:
            peak = max(sum(1 for t in starts if s <= t < s + 30000) for s in starts)
            if peak > g["max_per_30s"]:
                dev.append(f"{peak} graphics within 30 s (recipe max {g['max_per_30s']})")
        dev += [f"{e['event_id']} uses {e['template']}, which the recipe avoids" for e in events
                if e["template"] in (g.get("avoid") or [])]
        mxs = (recipe.get("camera") or {}).get("max_scale")
        dev += [f"{c['decision_id']} zooms x{c['scale_factor']} (recipe max x{mxs})" for c in camera
                if mxs and c.get("scale_factor", 1.0) > mxs + 1e-9]
        warnings += [f"recipe {rt}: {x}" for x in dev]
        recipe_info = {"type": rt, "label": recipe.get("label"), "deviations": dev, "notes": notes,
                       "pacing": recipe.get("pacing"), "music": recipe.get("music")}

    # camera timeline -> V01 segments (cuts at camera change points)
    base = ed.get("global", {})
    # framing: an explicit global.base_scale_percent wins; "auto"/absent uses preflight's face-centred reframe (wider
    # sources such as 16:9 episodes); otherwise the source is fitted as before
    rf = None
    bsp, box, boy, framing = base.get("base_scale_percent"), base.get("base_offset_x"), base.get("base_offset_y"), "explicit"
    if bsp in (None, "auto"):
        pre = read_json(paths.p("00_inputs/preflight.json"), {})
        mf = base.get("main_footage")
        rf = next((r for k, r in (pre.get("reframe") or {}).items()
                   if mf and (Path(k).name == Path(mf).name or Path(k) == paths.root / mf)), None)
        if rf:
            bsp, framing = rf["base_scale_percent"], f"auto-reframe (face x {rf.get('face_x')}, {rf.get('faces')} faces)"
            box = rf["offset_x"] if box is None else box
            boy = rf["offset_y"] if boy is None else boy
        else:
            bsp, framing = None, "fit"
    # cutaways (graphic cards / B-roll burned into a finished episode) are shown whole, never cropped: an automatic
    # "reframe" camera move back to fit, layered over the speaker reframe (story-editor camera moves inside them lose)
    cutaways = (rf or {}).get("cutaways_ms") or []
    if cutaways and bsp:
        pre_v = next((f["video"] for f in read_json(paths.p("00_inputs/preflight.json"), {"files": []})["files"]
                      if f.get("video") and Path(f["path"]).name == Path(base.get("main_footage") or "").name), None)
        if pre_v:
            seq_cfg = load_config("sequence-settings.json")["general"]
            fit = min(seq_cfg["frame_width"] / pre_v["display_width"], seq_cfg["frame_height"] / pre_v["display_height"]) * 100
            for a, b in cutaways:
                camera.append({"decision_id": "AUTO_CUTAWAY", "type": "reframe", "at_ms": a, "frame": ms_to_frame(a),
                               "until_ms": b, "scale_factor": round(fit / bsp, 5), "offset_x": -float(box or 0.0),
                               "offset_y": -float(boy or 0.0), "rationale": "source cutaway shown whole (not cropped)"})
            warnings.append("source cutaways (not the speaker) shown whole over a blurred fill: " +
                            ", ".join(f"{a / 1000:.1f}-{b / 1000:.1f}s" for a, b in cutaways))
    # podcast reels: per-shot framing (preflight "shots", see shots.py) replaces the single auto-reframe; story camera
    # moves are composed over the shot layer. Anything without a shot analysis keeps the path above.
    pre_all = read_json(paths.p("00_inputs/preflight.json"), {}) or {}
    shots_rep = pre_all.get("shots") or {}
    from .common import source_range
    main_file = base.get("main_footage") or source_range(paths).get("footage")
    main_v = main_video(pre_all, main_file)
    if shots_rep.get("shots") and base.get("base_scale_percent") in (None, "auto"):
        pv = main_v
        if pv:
            from .shots import compose_camera, frame_shots
            seq_g = load_config("sequence-settings.json")["general"]
            SW, SH = seq_g["frame_width"], seq_g["frame_height"]
            dw, dh = pv["display_width"], pv["display_height"]
            pc = load_config("podcast.json")
            layer = frame_shots(shots_rep["shots"], read_json(paths.p("00_inputs/speakers.json"), {}) or {}, dw, dh, SW, SH,
                                pc.get("speaker_min_hold_ms", 1500), pc.get("shots", {}).get("group_fit", 0.8))
            camera = compose_camera([c for c in camera if c["decision_id"] != "AUTO_CUTAWAY"], layer, dw, dh, SW, SH)
            bsp, box, boy = round(max(SW / dw, SH / dh) * 100, 3), 0.0, 0.0
            n_whole = [c for c in layer if c["decision_id"] == "AUTO_CUTAWAY"]
            framing = (f"per-shot reframe ({len(shots_rep['shots'])} shots; {sum(1 for c in layer if c.get('target'))} "
                       f"speaker-follow pieces; {len(n_whole)} shown whole)")
            if shots_rep.get("note"):
                warnings.append(shots_rep["note"])
            for c in n_whole:
                warnings.append(f"shown whole {c['at_ms'] / 1000:.1f}-{c['until_ms'] / 1000:.1f}s: {c['rationale']}")
    # a graphic over a shot shown whole covers the episode's own card or B-roll (seen in a live run): warn the editor
    for c in camera:
        if c["decision_id"] != "AUTO_CUTAWAY":
            continue
        for e in events:
            if e["template"] != "flash_transition" and e["start_ms"] < c["until_ms"] and c["at_ms"] < e["end_ms"]:
                warnings.append(f"{e['event_id']} ({e['template']}) covers {c['at_ms'] / 1000:.1f}-{c['until_ms'] / 1000:.1f}s, "
                                "a shot shown whole (the episode's own card / B-roll): move it to a speaker shot")
    # 4:5 framing (a client's plan: "4:5 (1080x1350) inside 9:16 over a blurred fill of the same video, title above,
    # captions below"): every speaker piece is drawn in a window; story moves and jump-cut zooms stay inside it (the
    # build crops the picture to the window); source cutaways stay whole
    framing_mode = str(base.get("framing") or load_config("style.json").get("framing") or "9:16")
    win = window_rect(framing_mode, base.get("framing_window_y"))
    if win and main_v is None:       # a 4:5 reel silently built as 9:16 would be the wrong deliverable
        errors.append(f"framing {framing_mode} needs this video's preflight: "
                      f"{Path(main_file).name if main_file else 'its footage'} is not in 00_inputs/preflight.json — run "
                      "`reel preflight` for this video first")
    elif main_file and pre_all.get("files") and main_v is None:
        warnings.append(f"{Path(main_file).name} is not in 00_inputs/preflight.json: per-shot framing is skipped (the "
                        "picture is fitted) — run `reel preflight` for this video")
    if win and bsp:
        pv_ = main_v
        if pv_:
            k45 = max(win["w"] / pv_["display_width"], win["h"] / pv_["display_height"]) * 100 / bsp
            bx = float(box or 0.0)
            wcam = []
            for c in camera:
                if c["decision_id"] == "AUTO_CUTAWAY":
                    wcam.append(c)
                    continue
                k = float(c.get("scale_factor", 1.0))   # face (base) offset and story offset scale with the picture
                wcam.append(dict(c, scale_factor=round(k * k45, 5), window=win,
                                 offset_x=round((bx * k + float(c.get("offset_x", 0.0))) * k45 - bx, 2)))
            camera = [{"decision_id": "AUTO_WINDOW", "type": "window", "at_ms": 0, "frame": 0, "until_ms": dur_ms,
                       "scale_factor": round(k45, 5), "offset_x": round(bx * k45 - bx, 2), "offset_y": 0.0, "window": win,
                       "rationale": f"{framing_mode} window {win['w']}x{win['h']} at y {win['y']}"}] + wcam
            framing += f"; {framing_mode} window {win['w']}x{win['h']} (y {win['y']}) over a blurred fill"
    camera.sort(key=lambda c: c["frame"])
    base = ed.get("global", {})
    main_segments = []
    pts = sorted({0, dur_f, *[c["frame"] for c in camera], *[ms_to_frame(c["until_ms"]) for c in camera]})
    pts = [p for p in pts if 0 <= p <= dur_f]
    for a, b in zip(pts, pts[1:]):
        if b - a <= 0:
            continue
        active = [c for c in camera if c["frame"] <= a < ms_to_frame(c["until_ms"])]
        # a source cutaway always wins (it must stay whole); otherwise the latest camera move
        c = next((x for x in active if x["decision_id"] == "AUTO_CUTAWAY"), active[-1] if active else None)
        main_segments.append({"start_frame": a, "end_frame": b,
                              "camera": c["type"] if c else "hold",
                              "scale_factor": c["scale_factor"] if c else 1.0,
                              "offset_x": c["offset_x"] if c else 0.0, "offset_y": c["offset_y"] if c else 0.0,
                              "decision_id": c["decision_id"] if c else None,
                              **({"window": c["window"]} if c and c.get("window") else {})})
    # merge adjacent identical holds
    merged = []
    for s in main_segments:
        if merged and merged[-1]["camera"] == s["camera"] == "hold" and merged[-1]["scale_factor"] == s["scale_factor"]:
            merged[-1]["end_frame"] = s["end_frame"]
        else:
            merged.append(s)

    # explicit source ranges on every V01 piece (identity mapping when pauses are kept)
    for s_ in merged:
        s_["src_in_ms"] = s_["start_frame"] * 1000 / FPS_
        s_["src_out_ms"] = s_["end_frame"] * 1000 / FPS_
    tmap, time_map_info = None, None
    rp = base.get("remove_pauses")
    words_all = read_json(paths.p("02_transcription/words.json"), {"words": []})["words"]
    wcut_ranges, words_cut, wcut_err = word_cut_ranges(words_all, base.get("cut_words") or [], dur_ms)
    errors += wcut_err
    pz = None
    if rp:
        pz = read_json(paths.p("06_audio/dialogue/pauses.json"))
        if not pz:
            errors.append("global.remove_pauses is set but 06_audio/dialogue/pauses.json is missing — run `reel audio-clean`")
    if (rp and pz) or wcut_ranges:
        from .timemap import TimeMap
        keep0 = pz["keep_ms"] if (rp and pz) else [[0, dur_ms]]
        # pauses the editor wants kept (a comedic beat, a dramatic silence): global.remove_pauses.protect, source time
        protect = []
        for pr in ((rp or {}).get("protect") or []) if isinstance(rp, dict) else []:
            try:
                a_, b_ = max(0, to_ms(pr[0])), min(dur_ms, to_ms(pr[1]))
            except Exception:  # noqa: BLE001
                errors.append(f"global.remove_pauses.protect entry {pr!r}: expected [start, end]")
                continue
            if b_ > a_:
                protect.append([a_, b_])
        if protect:
            keep0 = union_ranges(keep0, protect)
        keep = subtract_ranges(keep0, wcut_ranges) if wcut_ranges else keep0
        ms_ = tuple((rp or {}).get("mask_scales", [1.0, 1.06])) if isinstance(rp, dict) else (1.0, 1.06)
        tmap = TimeMap(keep, camera, ms_, base_offset_x=float(box or 0.0))
        merged = tmap.pieces
        removed = dur_ms - sum(b - a for a, b in keep)
        time_map_info = {"keep_ms": [list(k) for k in keep], "removed_ms": removed,
                         "cuts": len(keep) - 1, "pause_cuts": len(pz["cuts_ms"]) if (rp and pz) else 0,
                         "words_cut": words_cut, "source_duration_ms": dur_ms, "sequence_frames": tmap.total_frames,
                         "mask_scales": list(ms_)}
        kept = []
        for e in events:
            e["src_start_ms"], e["src_end_ms"] = e["start_ms"], e["end_ms"]
            if tmap.removed(e["start_ms"], e["end_ms"]):
                warnings.append(f"{e['event_id']} falls entirely inside removed pauses -> dropped")
                continue
            e["start_ms"], e["end_ms"] = round(tmap.ms(e["src_start_ms"])), round(tmap.ms(e["src_end_ms"]))
            e["start_frame"], e["end_frame"] = tmap.frame(e["src_start_ms"]), tmap.frame(e["src_end_ms"])
            e["start_tc"], e["end_tc"] = frame_to_tc(e["start_frame"]), frame_to_tc(e["end_frame"])
            for it in e["params"].get("items", []):
                it["src_frame"] = it["frame"]
                it["frame"] = tmap.frame(it["frame"] * 1000 / FPS_)
                it["rel_frame"] = it["frame"] - e["start_frame"]
            kept.append(e)
        events = kept
        ev_by_id = {e["event_id"]: e for e in events}
        broll_all = list(broll)
        broll = [dict(b, sequence_start_frame=ev_by_id[b["asset_id"]]["start_frame"],
                      duration_frames=ev_by_id[b["asset_id"]]["end_frame"] - ev_by_id[b["asset_id"]]["start_frame"])
                 for b in broll if b["asset_id"] in ev_by_id]
        for c in cues:
            c["src_at_ms"] = c["at_ms"]
            c["at_ms"] = round(tmap.ms(c["at_ms"]))
        dropped = {b["asset_id"] for b in broll_all} - set(ev_by_id)
        cues = [c for c in cues if c.get("related_visual") not in dropped]
        # captions on the sequence clock (rebuilt without the cut words, so they never show on screen)
        from . import srt as _srt
        from .transcribe import caption_cues
        gone = {c["word_id"] for c in words_cut}
        rebuilt = dict(zip(("subtitles", "captions-short"), caption_cues([w for w in words_all if w["id"] not in gone]))) \
            if gone else {}
        for name in ("subtitles", "captions-short"):
            src_p = paths.p(f"02_transcription/{name}.srt")
            if src_p.exists() or name in rebuilt:
                out = []
                for q in (rebuilt[name] if name in rebuilt else _srt.read_srt(src_p)):
                    if tmap.removed(q["start_ms"], q["end_ms"]):
                        continue
                    out.append({"start_ms": round(tmap.ms(q["start_ms"])), "end_ms": round(tmap.ms(q["end_ms"])), "text": q["text"]})
                _srt.write_srt(paths.p(f"02_transcription/{name}-seq.srt"), out)
        dur_f = tmap.total_frames
        dur_ms = round(dur_f * 1000 / FPS_)

    for c in cues:
        c["start_frame"] = ms_to_frame(c["at_ms"])
        c["timeline_tc"] = frame_to_tc(c["start_frame"])
        c["track"] = SFX_TRACK.get(c["kind"], "A03")
    cues.sort(key=lambda c: c["start_frame"])

    music = dict(ed.get("music", {"status": "NO_MUSIC_SUPPLIED"}))
    cps = []
    for cp in music.get("cue_points", []):
        src_ms = to_ms(cp["at"]) if cp.get("at") is not None else int(cp.get("frame", 0)) * 1000 / FPS_
        f = tmap.frame(src_ms) if tmap else ms_to_frame(src_ms)
        if f >= dur_f:
            warnings.append(f"music cue '{cp.get('label', '')}' at source {src_ms / 1000:.2f}s falls after the end; placed on the last frame")
        cps.append(dict(cp, source_ms=int(src_ms), frame=max(0, min(f, dur_f - 1))))
    if cps:
        music["cue_points"] = cps
    if music.get("file"):   # a licensed bed from the client's library, placed on A06 under the dialogue
        mf = str(music["file"]).replace("\\", "/")
        if not mf.lower().startswith("data/music/") or not (paths.root / mf).is_file():
            errors.append(f"music.file {mf!r} must be an existing licensed track under data/Music/ (never other audio)")
        else:
            music.update(status="PLACED", file=mf, fade_out_s=float(music.get("fade_out_s", 2.0)),
                         level_db=float(music.get("level_db", ((recipe or {}).get("music") or {}).get("level_db", -24))))
    caption_hl = [{"text": h["text"], "at_ms": to_ms(h["at"]) if h.get("at") else None}
                  for h in ed.get("caption_highlights", [])]

    from .common import source_range
    rng = source_range(paths)
    if rng and base.get("main_footage") and Path(base["main_footage"]).name != Path(rng["footage"]).name:
        errors.append(f"global.main_footage {base['main_footage']} is not this video's range file {rng['footage']} "
                      "(`reel range`)")
    spec = {"generated": now_iso(), "video_id": paths.video_id, "fps": FPS_,
            "source_in_ms": int(rng.get("in_ms", 0)), "source_range": rng or None,
            "duration_ms": dur_ms, "duration_frames": dur_f,
            "rounding_policy": f"frame = round_half_up(ms*{FPS_:.5g}/1000) from absolute time (no accumulation)",
            "main_footage": base.get("main_footage") or rng.get("footage"), "base_scale_percent": bsp,
            "base_offset_x": float(box or 0.0), "base_offset_y": float(boy or 0.0), "framing": framing,
            "main_segments": merged, "events": sorted(events, key=lambda e: (e["start_frame"], e["track"])),
            "caption_source": "02_transcription/captions-short-seq.srt" if tmap else "02_transcription/captions-short.srt",
            "caption_highlights": caption_hl, "time_map": time_map_info,
            "music": music, "recipe": recipe_info}
    # words the transcript editor flagged as uncertain never go on a graphic until the editor has heard them
    from .transcribe import transcript_flags
    flagged = transcript_flags(paths)
    for e in events:
        toks = set(norm(" ".join(onscreen_strings(e["params"]))).split())
        for f in flagged:
            if f["norm"] and set(f["norm"].split()) <= toks:
                errors.append(f"{e['event_id']}: on-screen text uses '{f['word']}' (word {f['id']}, "
                              f"{fmt_ts(f['start_ms'], '.')}), flagged as uncertain ({f['note']}): confirm it by ear "
                              "first (correct it, or drop the flag, in transcript-corrections.json)")
    if flagged:
        warnings.append(f"{len(flagged)} uncertain word(s) stay in the captions as heard until the editor confirms "
                        "them: " + ", ".join(f"#{f['id']} {f['word']}" for f in flagged[:8]))
    ok = not errors
    write_json(paths.p("01_analysis/plan-validation.json"), {"generated": now_iso(), "ok": ok,
               "errors": errors, "warnings": warnings, "decisions": len(ed.get("decisions", [])),
               "events": len(events), "cues": len(cues), "main_segments": len(merged)})
    if ok:
        write_json(paths.p("01_analysis/timeline-spec.json"), spec)
        write_json(paths.p("03_broll/broll-manifest.json"), {"generated": now_iso(), "assets": broll})
        sfx_dir = "06_audio/sfx"
        write_json(paths.p("06_audio/audio-cue-sheet.json"), {
            "generated": now_iso(), "fps": FPS_, "cues": [dict(c, **{
                "duration_frames": None, "audio_type": "sfx", "source_file": f"{sfx_dir}/{c['kind']}.wav",
                "fade": "baked into generated file (short attack, exponential tail)",
                "gain_instructions": f"clip gain {c['gain_db']} dB; keep dialogue peaks dominant (-6 dBFS dialogue / SFX ≤ -14 dBFS)"})
                for c in cues],
            "music": spec["music"]})
    res = {"ok": ok, "errors": errors, "warnings": warnings, "events": len(events), "cues": len(cues),
           "main_segments": len(merged)}
    if ok:
        res["edit_plan"] = str(write_edit_plan(paths))
        # a changed plan invalidates any earlier approval
        appr = read_json(paths.p("01_analysis/plan-approval.json"))
        if appr and appr.get("plan_fingerprint") != plan_fingerprint(paths):
            appr["stale"] = True
            write_json(paths.p("01_analysis/plan-approval.json"), appr)
    return res


def plan_fingerprint(paths: Paths) -> str:
    import hashlib
    return hashlib.sha1(paths.p("01_analysis/timeline-spec.json").read_bytes().split(b'"events"', 1)[-1]).hexdigest()[:16]


def speaker_covered_frames(spec: dict) -> int:
    """Frames where the speaker is not on screen: full-screen cards/B-roll/outro and source cutaways shown whole."""
    full = sum(e["end_frame"] - e["start_frame"] for e in spec["events"]
               if e["template"] in ("broll_card", "broll_video", "logo_outro"))
    return full + sum(m["end_frame"] - m["start_frame"] for m in spec["main_segments"]
                      if m.get("decision_id") == "AUTO_CUTAWAY")


def _seq_frame(spec: dict, src_ms: float) -> int:
    """A source time on the reel's timeline (pause removal / word cuts), via the compiled main segments."""
    for m in spec["main_segments"]:
        a = m.get("src_in_ms", 0)
        b = a + (m["end_frame"] - m["start_frame"]) * 1000 / spec.get("fps", 24)
        if src_ms < a:
            return m["start_frame"]
        if src_ms < b:
            return m["start_frame"] + round((src_ms - a) * spec.get("fps", 24) / 1000)
    return spec["duration_frames"]


def write_edit_plan(paths: Paths) -> Path:
    """Human-readable playback of the compiled plan for editor approval (01_analysis/edit-plan.md)."""
    from .common import write_text
    spec = read_json(paths.p("01_analysis/timeline-spec.json"))
    ed = read_json(paths.p("01_analysis/edit-decisions.json"), {})
    cues = read_json(paths.p("06_audio/audio-cue-sheet.json"), {"cues": []})["cues"]
    dur = spec["duration_frames"] or 1
    cover = speaker_covered_frames(spec)
    pend = [e for e in spec["events"] if e["approval_required"]]
    story_cam = [d for d in ed.get("decisions", []) if d.get("camera")]
    masks = sum(1 for s in spec["main_segments"] if s["camera"] == "jumpcut_mask" or s.get("masked"))
    cut_away = sum(s["end_frame"] - s["start_frame"] for s in spec["main_segments"] if s.get("decision_id") == "AUTO_CUTAWAY")
    L = [f"# Edit Plan — {paths.video_id} (for editor approval)", "",
         f"Runtime {frame_to_tc(dur)} at {spec.get('fps', 24):.5g} fps · {len(spec['events'])} graphics · "
         f"{len(story_cam)} camera moves (+{masks} automatic jump-cut zooms) · {len(cues)} SFX cues · "
         f"speaker covered {cover / dur:.0%}"
         + (f" (source cutaways shown whole: {cut_away / spec.get('fps', 24):.1f} s)" if cut_away else "")
         + f" · {len(pend)} items need content approval", "",
         "Times are on the reel's timeline (after pause removal and word cuts).", "",
         f"Framing: {spec.get('framing', 'fit')}", ""]
    rec = spec.get("recipe")
    if rec:
        lab = rec.get("label") or {}
        L += [f"Recipe: {rec['type']} ({lab.get('ar') or lab.get('en') or ''}); pauses removed from "
              f"{(rec.get('pacing') or {}).get('min_pause_ms', '?')} ms"]
        L += [f"- deviation: {x}" for x in rec.get("deviations", [])]
        L += [f"- story-editor's note: {x}" for x in rec.get("notes", [])]
        L += [""]
    L += ["## Decisions", "", "| # | Time | Treatment | On-screen text | Why (speaker's words) | Approval |", "|---|---|---|---|---|---|"]
    for d in ed.get("decisions", []):
        gfx = [e for e in spec["events"] if e["decision_id"] == d["decision_id"] and e["template"] != "flash_transition"]
        text = " / ".join((g["params"].get("text") or g["params"].get("headline") or g["params"].get("title") or
                           g["params"].get("name") or "").replace("\n", " ") for g in gfx) or "—"
        cam = f"+{(d['camera'].get('scale_factor', 1) - 1) * 100:.0f}% punch-in; " if d.get("camera") else ""
        segs = [m for m in spec["main_segments"] if m.get("decision_id") == d["decision_id"]]
        f0 = (min(g["start_frame"] for g in gfx) if gfx else min(m["start_frame"] for m in segs) if segs else
              _seq_frame(spec, d["_start_ms"] if "_start_ms" in d else to_ms(d["start"])))
        L.append(f"| {d['decision_id']} | {frame_to_tc(f0)} | "
                 f"{cam}{', '.join(g['template'] for g in gfx) or 'camera only'} | {text[:90]} | "
                 f"{d.get('evidence', '')[:70]} | {'YES' if any(g['approval_required'] for g in gfx) or d.get('approval_required') else ''} |")
    wc = (spec.get("time_map") or {}).get("words_cut") or []
    if wc:
        L += ["", f"## Words cut ({len(wc)}): picture, sound and captions", ""]
        L += [f"- {fmt_ts(w['start_ms'], '.')} «{w['word']}» (word {w['word_id']}){' — ' + w['reason'] if w.get('reason') else ''}"
              for w in wc]
    L += ["", "## Not included (and why)", ""]
    sem = read_json(paths.p("01_analysis/transcript-semantic-analysis.json"), {})
    L += [f"- {o.get('concept')}: {o.get('reason')}" for o in sem.get("broll_opportunities", [])
          if str(o.get("decision", "")).startswith(("rejected", "deferred"))] or ["- (none recorded)"]
    mu = spec.get("music", {})
    L += ["", f"Music: {mu.get('status')}" + (f" — {mu.get('file')} at {mu.get('level_db')} dB, {mu.get('fade_out_s')} s fade-out"
                                               if mu.get("status") == "PLACED" else ""), "",
          "**To approve:** reply 'approved' (or list changes). Adobe builds wait for `reel approve-plan`."]
    return write_text(paths.p("01_analysis/edit-plan.md"), "\n".join(L) + "\n")
