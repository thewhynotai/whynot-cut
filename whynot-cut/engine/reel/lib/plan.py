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


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = _AR_DIAC.sub("", s)
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


ONSCREEN_KEYS = ("text", "headline", "title", "subtitle", "name", "label", "lines", "items", "quote", "body", "caption")


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
            if t in ("hook_title", "term_callout", "glass_card", "cta", "broll_card") and not (g.get("text") or g.get("headline")):
                errors.append(f"{gid}: template {t} needs text/headline")
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
                              "decision_id": c["decision_id"] if c else None})
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
        keep = subtract_ranges(keep0, wcut_ranges) if wcut_ranges else keep0
        ms_ = tuple((rp or {}).get("mask_scales", [1.0, 1.06])) if isinstance(rp, dict) else (1.0, 1.06)
        tmap = TimeMap(keep, camera, ms_)
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
            "music": music}
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


def write_edit_plan(paths: Paths) -> Path:
    """Human-readable playback of the compiled plan for editor approval (01_analysis/edit-plan.md)."""
    from .common import write_text
    spec = read_json(paths.p("01_analysis/timeline-spec.json"))
    ed = read_json(paths.p("01_analysis/edit-decisions.json"), {})
    cues = read_json(paths.p("06_audio/audio-cue-sheet.json"), {"cues": []})["cues"]
    dur = spec["duration_frames"] or 1
    cover = sum(e["end_frame"] - e["start_frame"] for e in spec["events"]
                if e["template"] in ("broll_card", "broll_video", "logo_outro"))
    pend = [e for e in spec["events"] if e["approval_required"]]
    L = [f"# Edit Plan — {paths.video_id} (for editor approval)", "",
         f"Runtime {frame_to_tc(dur)} · {len(spec['events'])} graphics · "
         f"{sum(1 for s in spec['main_segments'] if s['camera'] != 'hold')} punch-ins · {len(cues)} SFX cues · "
         f"speaker covered {cover / dur:.0%} · {len(pend)} items need medical/content approval", "",
         "## Decisions", "", "| # | Time | Treatment | On-screen text | Why (speaker's words) | Approval |", "|---|---|---|---|---|---|"]
    for d in ed.get("decisions", []):
        gfx = [e for e in spec["events"] if e["decision_id"] == d["decision_id"] and e["template"] != "flash_transition"]
        text = " / ".join((g["params"].get("text") or g["params"].get("headline") or g["params"].get("title") or
                           g["params"].get("name") or "").replace("\n", " ") for g in gfx) or "—"
        cam = f"+{(d['camera'].get('scale_factor', 1) - 1) * 100:.0f}% punch-in; " if d.get("camera") else ""
        L.append(f"| {d['decision_id']} | {frame_to_tc(ms_to_frame(d['_start_ms'] if '_start_ms' in d else to_ms(d['start'])))} | "
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
    L += ["", f"Music: {spec.get('music', {}).get('status')}", "",
          "**To approve:** reply 'approved' (or list changes). Adobe builds wait for `reel approve-plan`."]
    return write_text(paths.p("01_analysis/edit-plan.md"), "\n".join(L) + "\n")
