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
                     read_json, write_json)

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
    """A time in edit-decisions.json -> ms: an int is milliseconds, a float or numeric string seconds, else a clock
    ("00:01:02.500", "01:02.5"). One parser for the engine: media_util.parse_time (T2.17, MI-7)."""
    from .media_util import parse_time
    return parse_time(v, int_is_ms=True)


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


# --------------------------------------------------------------------------- compile_plan
# 3.0 T2.17 (engine MI-6): one ~440-line function became a chain of steps. `read_inputs` does every read; each step
# is pure (no file reads or writes, never mutates its inputs) and returns (data, errors, warnings);
# `write_outputs` does every write. compile_plan concatenates errors/warnings in step order, so plan-validation.json
# lists them exactly as before. Frame maths (ms_to_frame, TimeMap, shots) uses the sequence rate of the Context the
# inputs were read with: PlanInputs keeps it (`inp.ctx`) and every public step binds it, so a step called on its own
# (`build_plan(read_inputs(p, ctx))`, a long-lived process) never mixes the client's rate with another one.
#   validate_decisions -> build_camera -> apply_framing -> apply_timemap -> build_audio -> final_checks -> write_outputs
_CAPTION_SRTS = ("subtitles", "captions-short")


class PlanInputs:
    """Everything compile_plan reads, read once (files, profile config, the client folder's file checks), and the
    Context it was read with (`ctx`: its sequence rate drives every frame number)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def _in_context(step):
    """Run a plan step with its inputs' Context bound (T2.17 review I1)."""
    import functools
    from .common import use_context

    @functools.wraps(step)
    def bound(inp, *a, **kw):
        with use_context(inp.ctx):
            return step(inp, *a, **kw)
    return bound


def read_inputs(paths: Paths, ctx=None) -> PlanInputs:
    from .common import current_context, use_context
    ctx = ctx or current_context()
    with use_context(ctx):
        return _read_inputs(paths, ctx)


def _read_inputs(paths: Paths, ctx) -> PlanInputs:
    from .common import source_range
    from .recipes import for_paths
    from .transcribe import transcript_flags
    ed = read_json(paths.p("01_analysis/edit-decisions.json"))
    if not ed:
        raise FileNotFoundError("01_analysis/edit-decisions.json missing — author it (see references/edit-decision-engine.md)")
    tpl = load_config("graphics-templates.json", ctx)["templates"]
    manifest = read_json(paths.client_db / "asset-manifest.json", {"assets": []})
    ttext, dur_ms = _transcript_text(paths)
    base = ed.get("global", {})
    rp = base.get("remove_pauses")
    words = read_json(paths.p("02_transcription/words.json"), {"words": []})["words"]
    pauses = read_json(paths.p("06_audio/dialogue/pauses.json")) if rp else None
    wranges, wcut, _ = word_cut_ranges(words, base.get("cut_words") or [], dur_ms)
    timemap_on = bool((rp and pauses) or wranges)
    srts = {}                      # the caption files apply_timemap maps onto the sequence clock (None = no file)
    if timemap_on and not wcut:    # with words cut, the captions are rebuilt from words.json instead
        from . import srt as srtlib
        for name in _CAPTION_SRTS:
            f = paths.p(f"02_transcription/{name}.srt")
            srts[name] = srtlib.read_srt(f) if f.exists() else None
    pre_all = read_json(paths.p("00_inputs/preflight.json"), {}) or {}
    rng = source_range(paths)
    main_file = base.get("main_footage") or rng.get("footage")
    main_default = None if main_file else _default_footage(paths)     # G71: never compile a plan without footage
    main_file = main_file or main_default
    shots_on = bool((pre_all.get("shots") or {}).get("shots") and base.get("base_scale_percent") in (None, "auto")
                    and main_video(pre_all, main_file))
    flagged = transcript_flags(paths)
    return PlanInputs(
        ctx=ctx, paths=paths, root=paths.root, video_id=paths.video_id, ed=ed, base=base, tpl=tpl,
        known_assets={a["rel"]: a for a in manifest["assets"]}, ttext=ttext, dur_ms=dur_ms, fps=seq_fps(ctx),
        recipe=for_paths(paths), pre_all=pre_all, rng=rng, main_file=main_file, main_default=main_default,
        seq_cfg=load_config("sequence-settings.json", ctx), style=load_config("style.json", ctx),
        podcast=load_config("podcast.json", ctx) if shots_on else {},
        speakers=(read_json(paths.p("00_inputs/speakers.json"), {}) or {}) if shots_on else {},
        words=words, pauses=pauses, srts=srts,
        subtitle_style=load_config("subtitle-style.json", ctx) if wcut and timemap_on else None,
        flagged=flagged, profile=load_config("profile.json", ctx), sfx_kinds=_sfx_kinds(paths),
        exists=lambda rel: (paths.root / rel).exists(), is_file=lambda rel: (paths.root / rel).is_file())


def _sfx_kinds(paths: Paths) -> list[str]:
    """Cue kinds a decision's `sound[].type` may name: the procedural recipes and the keys of 06_audio/sfx-map.json (T2.7)."""
    from . import sfx
    return sfx.valid_kinds(sfx.load_map(paths.p(sfx.MAP_REL)))


def _sfx_kind_ok(errors: list, label: str, kind, inp) -> bool:
    """One cue kind checked against the valid kinds (a plan error naming them when it is not a known string)."""
    if isinstance(kind, str) and kind in inp.sfx_kinds:
        return True
    errors.append(f"{label} {kind!r} is not a sound kind — use one of: {', '.join(inp.sfx_kinds)} "
                  "(or map it in 06_audio/sfx-map.json)")
    return False


def _default_footage(paths: Paths) -> str | None:
    """global.main_footage left out of a whole-clip video (gap G71): the raw clip this video id names (`reel inbox`),
    else the client's only raw clip, as a path relative to the client root; None when discovery cannot tell."""
    from .clip_ids import resolve
    inv = read_json(paths.output / "discovery/input-inventory.json")
    if not inv or not paths.video_id:
        return None
    try:
        f = resolve(paths.root, paths.video_id, inv)
    except SystemExit:                    # an id whose clip left data/: no default (the plan error says what to do)
        return None
    raw = [x for x in inv.get("files", []) if x.get("role") == "source_footage"]
    if f is None and len(raw) == 1:
        f = Path(raw[0]["path"])
    if f is None:
        return None
    try:
        return Path(f).resolve().relative_to(paths.root).as_posix()
    except ValueError:
        return str(f)


def _try_ms(v) -> int | None:
    """to_ms, or None when v is not a time."""
    try:
        return to_ms(v)
    except (TypeError, ValueError):
        return None


@_in_context
def validate_decisions(inp: PlanInputs):
    """Decisions -> graphic events, B-roll entries, SFX cues and the story camera moves; overlap and recipe checks."""
    import copy
    ed = copy.deepcopy(inp.ed)            # the steps never mutate their inputs
    FPS_, tpl, dur_ms, ttext = inp.fps, inp.tpl, inp.dur_ms, inp.ttext
    errors, warnings = [], []
    events, cues, broll, camera = [], [], [], []
    seen_ids = set()

    def chk_range(label, a, b):
        if b <= a:
            errors.append(f"{label}: end <= start")
        if a < 0 or b > dur_ms + 40:
            errors.append(f"{label}: outside media duration {fmt_ts(dur_ms)}")

    def ms(label, v):
        """A time field -> ms, or None with an error (T2.2: never a ValueError out of the plan)."""
        t = _try_ms(v)
        if t is None:
            errors.append(f"{label} {v!r} is not a time (seconds such as 12.5, or a clock such as 00:00:12.500)")
        return t

    def num(label, v, default):
        try:
            return float(v if v is not None else default)
        except (TypeError, ValueError):
            errors.append(f"{label} {v!r} is not a number")
            return float(default)

    for h in ed.get("caption_highlights", []) or []:
        if isinstance(h, dict) and h.get("at"):
            ms(f"caption_highlights '{h.get('text', '')}': at", h["at"])

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
        if d.get("start") in (None, "") or d.get("end") in (None, ""):
            continue                      # reported above; nothing below can be timed without both
        s_ms, e_ms = ms(f"{did}: start", d["start"]), ms(f"{did}: end", d["end"])
        if s_ms is None or e_ms is None:
            continue
        chk_range(did, s_ms, e_ms)
        d["_start_ms"], d["_end_ms"] = s_ms, e_ms

        cam = d.get("camera")
        if cam:
            ctype = cam.get("type", "hold")
            if ctype not in VALID_CAMERA:
                errors.append(f"{did}: camera.type {ctype} invalid")
            at = ms(f"{did}: camera.at", cam.get("at", d["start"]))
            until = ms(f"{did}: camera.until", cam["until"]) if cam.get("until") else e_ms
            if at is not None and until is not None:
                camera.append({"decision_id": did, "type": ctype, "at_ms": at, "frame": ms_to_frame(at),
                               "until_ms": until,
                               "scale_factor": num(f"{did}: camera.scale_factor", cam.get("scale_factor"), 1.0),
                               "offset_y": num(f"{did}: camera.offset_y", cam.get("offset_y"), 0.0),
                               "offset_x": num(f"{did}: camera.offset_x", cam.get("offset_x"), 0.0),
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
            gs, ge = ms(f"{gid}: start", g.get("start", d["start"])), ms(f"{gid}: end", g.get("end", d["end"]))
            if gs is None or ge is None:
                continue
            chk_range(gid, gs, ge)
            if not (s_ms - 40 <= gs and ge <= e_ms + 2000):
                warnings.append(f"{gid}: graphic extends well beyond its decision window")
            for it in g.get("items", []):
                it["_at_ms"] = (ms(f"{gid}: item '{it.get('text')}' at", it["at"]) if "at" in it else gs)
                if it["_at_ms"] is None:
                    it["_at_ms"] = gs     # reported above
                if not (gs <= it["_at_ms"] < ge):
                    errors.append(f"{gid}: item '{it.get('text')}' at outside graphic span")
            imgs = [g["image"]] if g.get("image") else []
            for im in imgs:
                if im not in inp.known_assets and not inp.exists(im):
                    errors.append(f"{gid}: image not found in client asset manifest: {im}")
            if t == "broll_video":
                vid = g.get("video")
                if not vid or not inp.exists(vid):
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
            kind = g.get("sfx", info.get("sfx"))
            if kind not in (None, "", "none") and _sfx_kind_ok(errors, f"{did}: graphics sfx", kind, inp):
                cues.append({"cue_id": f"SFX_{gid}", "kind": kind, "at_ms": gs, "related_visual": gid,
                             "decision_id": did, "segment_id": d.get("segment_id"), "auto": True,
                             "gain_db": g.get("sfx_gain_db", -14)})
                for it in g.get("items", [])[1:] if t == "checklist" else []:
                    cues.append({"cue_id": f"SFX_{gid}_{it['frame']}", "kind": "tick",
                                 "at_ms": round(it["frame"] * 1000 / FPS_), "related_visual": gid,
                                 "decision_id": did, "segment_id": d.get("segment_id"), "auto": True, "gain_db": -18})

        for s in d.get("sound", []):
            kind_ok = _sfx_kind_ok(errors, f"{did}: sound.type", s.get("type", "pop"), inp)
            at = ms(f"{did}: sound.at", s.get("at", d["start"]))
            if at is None or not kind_ok:
                continue
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
    recipe, recipe_info = inp.recipe, None
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
    return {"events": events, "cues": cues, "broll": broll, "camera": camera, "recipe_info": recipe_info}, \
        errors, warnings


@_in_context
def build_camera(inp: PlanInputs, camera: list, events: list):
    """The speaker framing: explicit base scale, preflight's auto-reframe, source cutaways shown whole, or per-shot
    framing (podcast reels); story camera moves are composed over it."""
    warnings = []
    camera = list(camera)
    base, pre_all, main_file = inp.base, inp.pre_all, inp.main_file
    # THIS video's footage (global.main_footage, or a range reel's footage in 00_inputs/source.json) and its preflight
    # entry: every framing step below is sized from this file, never from whichever file preflight lists first
    main_v = main_video(pre_all, main_file)
    # framing: an explicit global.base_scale_percent wins; "auto"/absent uses preflight's face-centred reframe (wider
    # sources such as 16:9 episodes); otherwise the source is fitted as before
    rf = None
    bsp, box, boy, framing = base.get("base_scale_percent"), base.get("base_offset_x"), base.get("base_offset_y"), "explicit"
    if bsp in (None, "auto"):
        mf = main_file
        rf = next((r for k, r in (pre_all.get("reframe") or {}).items()
                   if mf and (Path(k).name == Path(mf).name or Path(k) == inp.root / mf)), None)
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
        pre_v = main_v
        if pre_v:
            seq_cfg = inp.seq_cfg["general"]
            fit = min(seq_cfg["frame_width"] / pre_v["display_width"], seq_cfg["frame_height"] / pre_v["display_height"]) * 100
            for a, b in cutaways:
                camera.append({"decision_id": "AUTO_CUTAWAY", "type": "reframe", "at_ms": a, "frame": ms_to_frame(a),
                               "until_ms": b, "scale_factor": round(fit / bsp, 5), "offset_x": -float(box or 0.0),
                               "offset_y": -float(boy or 0.0), "rationale": "source cutaway shown whole (not cropped)"})
            warnings.append("source cutaways (not the speaker) shown whole over a blurred fill: " +
                            ", ".join(f"{a / 1000:.1f}-{b / 1000:.1f}s" for a, b in cutaways))
    # podcast reels: per-shot framing (preflight "shots", see shots.py) replaces the single auto-reframe; story camera
    # moves are composed over the shot layer. Anything without a shot analysis keeps the path above.
    shots_rep = pre_all.get("shots") or {}
    if shots_rep.get("shots") and base.get("base_scale_percent") in (None, "auto"):
        pv = main_v
        if pv:
            from .shots import compose_camera, frame_shots
            seq_g = inp.seq_cfg["general"]
            SW, SH = seq_g["frame_width"], seq_g["frame_height"]
            dw, dh = pv["display_width"], pv["display_height"]
            pc = inp.podcast
            layer = frame_shots(shots_rep["shots"], inp.speakers, dw, dh, SW, SH,
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
    return {"camera": camera, "main_v": main_v, "bsp": bsp, "box": box, "boy": boy, "framing": framing}, [], warnings


@_in_context
def apply_framing(inp: PlanInputs, cam: dict):
    """The 4:5 window (when the framing asks for one) and the V01 pieces cut at every camera change point."""
    errors, warnings = [], []
    base, main_file, main_v, dur_ms = inp.base, inp.main_file, cam["main_v"], inp.dur_ms
    camera, bsp, box, framing = list(cam["camera"]), cam["bsp"], cam["box"], cam["framing"]
    # 4:5 framing (a client's plan: "4:5 (1080x1350) inside 9:16 over a blurred fill of the same video, title above,
    # captions below"): every speaker piece is drawn in a window; story moves and jump-cut zooms stay inside it (the
    # build crops the picture to the window); source cutaways stay whole
    framing_mode = str(base.get("framing") or inp.style.get("framing") or "9:16")
    win = window_rect(framing_mode, base.get("framing_window_y"))
    if win and main_v is None:       # a 4:5 reel silently built as 9:16 would be the wrong deliverable
        errors.append(f"framing {framing_mode} needs this video's preflight: "
                      f"{Path(main_file).name if main_file else 'its footage'} is not in 00_inputs/preflight.json — run "
                      "`reel preflight` for this video first")
    elif main_file and inp.pre_all.get("files") and main_v is None:
        warnings.append(f"{Path(main_file).name} is not in 00_inputs/preflight.json: per-shot framing is skipped (the "
                        "picture is fitted) — run `reel preflight` for this video")
    if win and main_v and not bsp:   # a source already in the sequence's shape (a phone clip) has no reframe: its fit
        seq_g = inp.seq_cfg["general"]                             # scale is the base the window zooms from
        bsp = round(min(seq_g["frame_width"] / main_v["display_width"],
                        seq_g["frame_height"] / main_v["display_height"]) * 100, 3)
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
    dur_f = ms_to_frame(dur_ms)
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
        s_["src_in_ms"] = s_["start_frame"] * 1000 / inp.fps
        s_["src_out_ms"] = s_["end_frame"] * 1000 / inp.fps
    return {"camera": camera, "merged": merged, "bsp": bsp, "framing": framing}, errors, warnings


@_in_context
def apply_timemap(inp: PlanInputs, camera: list, merged: list, events: list, broll: list, cues: list, box):
    """Pause removal and word cuts: the TimeMap of kept source ranges, everything moved onto the sequence clock, and
    the captions mapped (rebuilt without cut words). Identity (no TimeMap) when nothing is removed."""
    import copy
    errors, warnings = [], []
    base, words_all = inp.base, inp.words
    dur_ms, dur_f, FPS_ = inp.dur_ms, ms_to_frame(inp.dur_ms), inp.fps
    out = {"merged": merged, "events": events, "broll": broll, "cues": cues, "tmap": None, "time_map_info": None,
           "seq_srts": {}, "dur_ms": dur_ms, "dur_f": dur_f}
    rp = base.get("remove_pauses")
    wcut_ranges, words_cut, wcut_err = word_cut_ranges(words_all, base.get("cut_words") or [], dur_ms)
    errors += wcut_err
    pz = None
    if rp:
        pz = inp.pauses
        if not pz:
            errors.append("global.remove_pauses is set but 06_audio/dialogue/pauses.json is missing — run `reel audio-clean`")
    if not ((rp and pz) or wcut_ranges):
        return out, errors, warnings
    from .timemap import TimeMap
    events, cues = copy.deepcopy(events), copy.deepcopy(cues)
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
    from .transcribe import caption_cues
    gone = {c["word_id"] for c in words_cut}
    rebuilt = dict(zip(_CAPTION_SRTS, caption_cues([w for w in words_all if w["id"] not in gone], inp.subtitle_style))) \
        if gone else {}
    seq_srts = {}
    for name in _CAPTION_SRTS:
        src = rebuilt[name] if name in rebuilt else inp.srts.get(name)
        if src is None:
            continue
        seq_srts[name] = [{"start_ms": round(tmap.ms(q["start_ms"])), "end_ms": round(tmap.ms(q["end_ms"])),
                           "text": q["text"]} for q in src if not tmap.removed(q["start_ms"], q["end_ms"])]
    dur_f = tmap.total_frames
    out.update(merged=merged, events=events, broll=broll, cues=cues, tmap=tmap, time_map_info=time_map_info,
               seq_srts=seq_srts, dur_f=dur_f, dur_ms=round(dur_f * 1000 / FPS_))
    return out, errors, warnings


@_in_context
def build_audio(inp: PlanInputs, cues: list, tmap, dur_f: int):
    """SFX cues on their tracks and frames; the music bed and its cue points."""
    errors, warnings = [], []
    FPS_ = inp.fps
    cues = [dict(c) for c in cues]
    for c in cues:
        c["start_frame"] = ms_to_frame(c["at_ms"])
        c["timeline_tc"] = frame_to_tc(c["start_frame"])
        c["track"] = SFX_TRACK.get(c["kind"], "A03")
    cues.sort(key=lambda c: c["start_frame"])

    music = dict(inp.ed.get("music", {"status": "NO_MUSIC_SUPPLIED"}))
    cps = []
    for cp in music.get("cue_points", []):
        src_ms = _try_ms(cp["at"]) if cp.get("at") is not None else int(cp.get("frame", 0)) * 1000 / FPS_
        if src_ms is None:
            errors.append(f"music cue '{cp.get('label', '')}': at {cp['at']!r} is not a time (seconds such as 12.5, "
                          "or a clock such as 00:00:12.500)")
            continue
        f = tmap.frame(src_ms) if tmap else ms_to_frame(src_ms)
        if f >= dur_f:
            warnings.append(f"music cue '{cp.get('label', '')}' at source {src_ms / 1000:.2f}s falls after the end; placed on the last frame")
        cps.append(dict(cp, source_ms=int(src_ms), frame=max(0, min(f, dur_f - 1))))
    if cps:
        music["cue_points"] = cps
    if music.get("file"):   # a licensed bed from the client's library, placed on A06 under the dialogue
        mf = str(music["file"]).replace("\\", "/")
        if not mf.lower().startswith("data/music/") or not inp.is_file(mf):
            errors.append(f"music.file {mf!r} must be an existing licensed track under data/Music/ (never other audio)")
        else:
            music.update(status="PLACED", file=mf, fade_out_s=float(music.get("fade_out_s", 2.0)),
                         level_db=float(music.get("level_db", ((inp.recipe or {}).get("music") or {}).get("level_db", -24))))
    return {"cues": cues, "music": music}, errors, warnings


@_in_context
def final_checks(inp: PlanInputs, events: list):
    """The range reel's footage, uncertain words on screen, and honorifics against the profile's people[]."""
    errors, warnings = [], []
    base, rng = inp.base, inp.rng
    if rng and base.get("main_footage") and Path(base["main_footage"]).name != Path(rng["footage"]).name:
        errors.append(f"global.main_footage {base['main_footage']} is not this video's range file {rng['footage']} "
                      "(`reel range`)")
    # G71: every later stage plays this file; a plan without it compiled "ok" and previews then crashed
    if not inp.main_file:
        errors.append("global.main_footage missing: set it in the \"global\" block of 01_analysis/edit-decisions.json "
                      "(the raw file this video is cut from, e.g. data/Raw/C0239.MP4); with `reel discover` run, a video "
                      "id that names one raw clip defaults to it")
    elif not inp.exists(inp.main_file):
        errors.append(f"global.main_footage {inp.main_file} not found in the client folder: give the raw file's path "
                      "relative to the client folder (e.g. data/Raw/C0239.MP4)")
    elif inp.main_default:
        warnings.append(f"global.main_footage not set: using {inp.main_default} (the raw clip of {inp.video_id}); "
                        "set it in edit-decisions.json to make it explicit")
    # words the transcript editor flagged as uncertain never go on a graphic until the editor has heard them
    flagged = inp.flagged
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
    # an on-screen honorific must match the person's gender in the profile's people[] («الدكتورة» for a man = error)
    from .people import check_many, check_nameless, load_people
    ppl, p_issues = load_people(inp.profile)
    shown = [(e["event_id"], s) for e in events for s in onscreen_strings(e["params"])]
    p_err, p_warn = check_many(shown, ppl)
    errors += p_err
    # and a nameless «الدكتورة» when everyone in people[] is male (or the mirror): the incident's own wording
    warnings += p_issues + p_warn + [w for where, s in shown for w in check_nameless(where, s, ppl)]
    return {}, errors, warnings


@_in_context
def assemble_spec(inp: PlanInputs, cam: dict, fr: dict, tm: dict, au: dict, recipe_info) -> dict:
    """The timeline spec (01_analysis/timeline-spec.json) from the steps' data."""
    FPS_, rng = inp.fps, inp.rng
    caption_hl = [{"text": h["text"], "at_ms": _try_ms(h["at"]) if h.get("at") else None}   # bad "at": a plan error
                  for h in inp.ed.get("caption_highlights", [])]
    return {"generated": now_iso(), "video_id": inp.video_id, "fps": FPS_,
            "source_in_ms": int(rng.get("in_ms", 0)), "source_range": rng or None,
            "duration_ms": tm["dur_ms"], "duration_frames": tm["dur_f"],
            "rounding_policy": f"frame = round_half_up(ms*{FPS_:.5g}/1000) from absolute time (no accumulation)",
            "main_footage": inp.main_file, "base_scale_percent": fr["bsp"],
            "base_offset_x": float(cam["box"] or 0.0), "base_offset_y": float(cam["boy"] or 0.0), "framing": fr["framing"],
            "main_segments": tm["merged"], "events": sorted(tm["events"], key=lambda e: (e["start_frame"], e["track"])),
            "caption_source": "02_transcription/captions-short-seq.srt" if tm["tmap"] else "02_transcription/captions-short.srt",
            "caption_highlights": caption_hl, "time_map": tm["time_map_info"],
            "music": au["music"], "recipe": recipe_info}


def write_outputs(paths: Paths, plan: dict) -> dict:
    """Every write of `reel plan`: the sequence-clock captions, plan-validation.json and, when valid, the timeline
    spec, B-roll manifest, audio cue sheet, edit-plan.md and the stale mark on an earlier approval (edit-plan.md's
    timecodes use the plan's Context, bound here)."""
    import contextlib
    from .common import use_context
    with use_context(plan["ctx"]) if plan.get("ctx") is not None else contextlib.nullcontext():
        return _write_outputs(paths, plan)


def _write_outputs(paths: Paths, plan: dict) -> dict:
    from . import srt as srtlib
    for name, cues_ in plan["seq_srts"].items():
        srtlib.write_srt(paths.p(f"02_transcription/{name}-seq.srt"), cues_)
    ok, errors, warnings = plan["ok"], plan["errors"], plan["warnings"]
    spec, events, cues, merged = plan["spec"], plan["spec"]["events"], plan["cues"], plan["spec"]["main_segments"]
    write_json(paths.p("01_analysis/plan-validation.json"), {"generated": now_iso(), "ok": ok,
               "errors": errors, "warnings": warnings, "decisions": plan["decisions"],
               "events": len(events), "cues": len(cues), "main_segments": len(merged)})
    if ok:
        write_json(paths.p("01_analysis/timeline-spec.json"), spec)
        write_json(paths.p("03_broll/broll-manifest.json"), {"generated": now_iso(), "assets": plan["broll"]})
        sfx_dir = "06_audio/sfx"
        write_json(paths.p("06_audio/audio-cue-sheet.json"), {
            "generated": now_iso(), "fps": spec["fps"], "cues": [dict(c, **{
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


@_in_context
def build_plan(inp: PlanInputs) -> dict:
    """The pure part of compile_plan: the steps in order, their errors and warnings concatenated in that order."""
    errors, warnings = [], []

    def step(r):
        data, e, w = r
        errors.extend(e)
        warnings.extend(w)
        return data

    vd = step(validate_decisions(inp))
    cam = step(build_camera(inp, vd["camera"], vd["events"]))
    fr = step(apply_framing(inp, cam))
    tm = step(apply_timemap(inp, fr["camera"], fr["merged"], vd["events"], vd["broll"], vd["cues"], cam["box"]))
    au = step(build_audio(inp, tm["cues"], tm["tmap"], tm["dur_f"]))
    spec = assemble_spec(inp, cam, fr, tm, au, vd["recipe_info"])
    step(final_checks(inp, tm["events"]))
    return {"ok": not errors, "errors": errors, "warnings": warnings, "spec": spec, "broll": tm["broll"],
            "cues": au["cues"], "seq_srts": tm["seq_srts"], "decisions": len(inp.ed.get("decisions", [])),
            "ctx": inp.ctx}


def compile_plan(paths: Paths, ctx=None) -> dict:
    """Validate 01_analysis/edit-decisions.json against the transcript and compile the timeline spec, B-roll manifest
    and audio cue sheet: read_inputs -> build_plan (pure steps) -> write_outputs. `ctx` (the CLI's Context) is bound
    by every step; without it the current Context applies."""
    return write_outputs(paths, build_plan(read_inputs(paths, ctx)))


def plan_fingerprint(paths: Paths) -> str:
    """Gate 1 fingerprint: the whole compiled timeline spec (camera, framing, scale, duration, main footage, events,
    captions, music) except the `generated` timestamp, so a re-compile that changes nothing stays approved and
    anything that changes what gets built does not (3.0 T1.4, engine IM-3). Sorted keys: the hash does not depend on
    key order or file formatting."""
    import hashlib
    import json
    spec = json.loads(paths.p("01_analysis/timeline-spec.json").read_text(encoding="utf-8"))
    body = {k: v for k, v in spec.items() if k != "generated"}
    if isinstance(body.get("source_range"), dict):        # `reel range` re-run with the same points: set_at etc. only
        body["source_range"] = {k: v for k, v in body["source_range"].items() if not _volatile(k)}
    text = json.dumps(body, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _volatile(key: str) -> bool:
    """A timestamp key (`set_at`, `selected_at`, any `*_at`): when something was recorded, not what gets built."""
    return key == "generated" or key.endswith("_at")


APPROVAL_FORMAT = 3                        # plan-approval.json records written by 3.0+ carry "format": 3


def approval_state(paths: Paths) -> dict:
    """{"state": "none" | "current" | "stale", "by", "message"} of 01_analysis/plan-approval.json against the plan
    as it is now (3.0 T11): a stale approval says "plan changed since approval — re-approve", and a record from before
    3.0 (no "format") adds that the approval format changed, so the editor knows why their approval no longer holds."""
    appr = read_json(paths.p("01_analysis/plan-approval.json"), {}) or {}
    by = appr.get("by") or "?"
    if not appr.get("approved"):
        return {"state": "none", "by": None, "message": "NOT approved"}
    try:
        if appr.get("kind") == "motion":
            from .motion_plan import fingerprint as motion_fp
            now = motion_fp(paths)
        else:
            now = plan_fingerprint(paths)
    except (OSError, ValueError):
        now = None                                         # no compiled plan: nothing the approval still matches
    if not appr.get("stale") and now and appr.get("plan_fingerprint") == now:
        return {"state": "current", "by": by, "message": f"approved by {by}"}
    msg = "plan changed since approval — re-approve"
    if appr.get("format") != APPROVAL_FORMAT:
        msg += " (approval format changed in 3.0)"
    return {"state": "stale", "by": by, "message": msg}


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
