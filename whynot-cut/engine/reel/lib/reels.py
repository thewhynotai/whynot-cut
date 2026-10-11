"""Podcast mode: the REELS PLAN of an episode (validation, sentence snapping, candidate previews) and Gate 0 (the editor
picks reels; each picked reel becomes an ordinary clip project cut from a window of the episode file).

Input (authored by the episode-analyst): output/episodes/<EP>/01_analysis/reels-plan.json
Outputs: 01_analysis/reels-plan-validated.json, reels-plan.md, reels-plan-validation.json
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .common import fmt_ts, load_config, now_iso, read_json, write_json, write_text

PUNCT_END = re.compile(r"[.?!؟…۔]\s*$")
SCORE_KEYS = ("hook", "standalone", "payoff", "ending")
RID = re.compile(r"^R\d+$")


def recipes() -> dict:
    return load_config("recipes.json").get("types", {})


def content_types() -> list[str]:
    return list(recipes())


def type_label(t: str, lang: str = "ar") -> str:
    lab = recipes().get(t, {}).get("label", {})
    return lab.get(lang) or lab.get("en") or t


# --------------------------------------------------------------------------- snapping
def boundary_words(words: list, gap_ms: int = 300) -> tuple[set, set]:
    """Indices of words that can START a reel (segment start, after a sentence end, after a pause) and that can END
    one (segment end, sentence-final punctuation, before a pause)."""
    n = len(words)
    starts, ends = set(), set()
    for i, w in enumerate(words):
        prev = words[i - 1] if i else None
        nxt = words[i + 1] if i + 1 < n else None
        if prev is None or prev.get("segment_id") != w.get("segment_id") or PUNCT_END.search(prev["word"] or "") \
                or w["start_ms"] - prev["end_ms"] >= gap_ms:
            starts.add(i)
        if nxt is None or nxt.get("segment_id") != w.get("segment_id") or PUNCT_END.search(w["word"] or "") \
                or nxt["start_ms"] - w["end_ms"] >= gap_ms:
            ends.add(i)
    return starts, ends


def _nearest(idx: list, key, t: int) -> int | None:
    return min(idx, key=lambda i: (abs(key(i) - t), i)) if idx else None


def snap_in(words: list, t_ms: int, cfg: dict) -> int:
    """In-point at the nearest sentence-like word start within ±search (else the nearest word), minus a short lead-in
    that never reaches back into the previous word. Never below 0."""
    if not words:
        return max(0, int(t_ms))
    sc = cfg.get("snap", {})
    search, lead = sc.get("search_ms", 1500), sc.get("lead_in_ms", 120)
    starts, _ = boundary_words(words, sc.get("gap_ms", 300))
    near = [i for i in range(len(words)) if abs(words[i]["start_ms"] - t_ms) <= search]
    i = _nearest([k for k in near if k in starts], lambda k: words[k]["start_ms"], t_ms)
    if i is None:
        i = _nearest(near or list(range(len(words))), lambda k: words[k]["start_ms"], t_ms)
    w = words[i]
    floor = words[i - 1]["end_ms"] + 20 if i else 0
    return max(0, min(w["start_ms"], max(w["start_ms"] - lead, floor)))


def snap_out(words: list, t_ms: int, cfg: dict, total_ms: int) -> int:
    """Out-point at the nearest sentence-like word end within ±search (else the nearest word), plus a short tail that
    never reaches into the next word. Never beyond the episode."""
    if not words:
        return min(int(t_ms), total_ms)
    sc = cfg.get("snap", {})
    search, tail = sc.get("search_ms", 1500), sc.get("tail_ms", 250)
    _, ends = boundary_words(words, sc.get("gap_ms", 300))
    near = [i for i in range(len(words)) if abs(words[i]["end_ms"] - t_ms) <= search]
    i = _nearest([k for k in near if k in ends], lambda k: words[k]["end_ms"], t_ms)
    if i is None:
        i = _nearest(near or list(range(len(words))), lambda k: words[k]["end_ms"], t_ms)
    w = words[i]
    ceil = words[i + 1]["start_ms"] - 20 if i + 1 < len(words) else total_ms
    return min(total_ms, max(w["end_ms"], min(w["end_ms"] + tail, ceil)))


def _tokens(words: list) -> list[tuple[str, int]]:
    from .plan import norm
    return [(t, i) for i, w in enumerate(words) for t in norm(w["word"]).split()]


def find_evidence(words: list, text: str, near_ms: int, tol_ms: int, anchor: str = "start") -> bool:
    """True when the words of `text` (Arabic-normalised: hamza forms, ta marbuta, ya, tashkeel, punctuation) occur in a
    row in the transcript, with their first word starting (anchor 'start') or last word ending ('end') within tol_ms."""
    from .plan import norm
    want = norm(text or "").split()
    if not want:
        return False
    toks = _tokens(words)
    seq = [t for t, _ in toks]
    n = len(want)
    for k in range(len(seq) - n + 1):
        if seq[k:k + n] == want:
            t = words[toks[k][1]]["start_ms"] if anchor == "start" else words[toks[k + n - 1][1]]["end_ms"]
            if abs(t - near_ms) <= tol_ms:
                return True
    return False


# --------------------------------------------------------------------------- validation
def validate_topics(topics: list, total_ms: int, min_ms: int = 10000) -> list[str]:
    """Problems with a topic map (also the YouTube chapters): sorted, non-overlapping, >= 10 s each, first at the start."""
    from .plan import to_ms
    probs, prev_end = [], None
    for k, t in enumerate(topics):
        try:
            a, b = to_ms(t["start"]), to_ms(t["end"])
        except Exception:  # noqa: BLE001
            probs.append(f"topic {t.get('id', k + 1)}: start/end missing or unreadable")
            continue
        if k == 0 and a > 5000:
            probs.append(f"topic {t.get('id', 1)} starts at {fmt_ts(a, '.')}: the first topic must start at 00:00")
        if b - a < min_ms:
            probs.append(f"topic {t.get('id', k + 1)} is {(b - a) / 1000:.1f} s (chapters must be >= 10 s)")
        if prev_end is not None and a < prev_end - 40:
            probs.append(f"topic {t.get('id', k + 1)} overlaps or is out of order")
        if b > total_ms + 1000:
            probs.append(f"topic {t.get('id', k + 1)} ends after the episode")
        if not str(t.get("title", "")).strip():
            probs.append(f"topic {t.get('id', k + 1)} has no title")
        prev_end = b
    return probs


def reels_plan_fingerprint(ep) -> str:
    h = hashlib.sha1()
    for rel in ("01_analysis/reels-plan.json", "02_transcription/words.json"):
        f = ep.p(rel)
        h.update(f.read_bytes() if f.exists() else b"-")
    return h.hexdigest()[:16]


def compile_reels_plan(ep) -> dict:
    from .episode import podcast_cfg
    from .plan import norm, to_ms
    plan = read_json(ep.p("01_analysis/reels-plan.json"))
    if not plan:
        raise SystemExit("01_analysis/reels-plan.json missing — the episode-analyst authors it (see episode-craft)")
    wj = read_json(ep.p("02_transcription/words.json"))
    tj = read_json(ep.p("02_transcription/transcript.json"))
    if not wj or not tj:
        raise SystemExit(f"episode transcript missing — run `reel episode-transcribe --episode {ep.episode_id}`")
    words, total = wj["words"], int(tj["meta"]["duration_ms"])
    cfg = podcast_cfg()
    dur_cfg, tol = cfg["reel_duration_s"], cfg["snap"].get("evidence_tol_ms", 3000)
    types = content_types()
    info = read_json(ep.p("00_inputs/episode.json"), {}) or {}
    avoid = [a for a in (info.get("sheet", {}) or {}).get("avoid") or [] if str(a).strip()]
    if isinstance(avoid, str):
        avoid = [avoid]
    people = (read_json(ep.p("01_analysis/speakers.json"), {}) or {}).get("people") or {}
    errors, warnings, out, seen = [], [], [], set()
    for c in plan.get("candidates", []):
        cid = str(c.get("id") or "")
        err0 = len(errors)
        if not RID.match(cid) or cid in seen:
            errors.append(f"candidate id {cid!r} missing, duplicate or not like R01")
        seen.add(cid)
        try:
            s_ms, e_ms = to_ms(c["start"]), to_ms(c["end"])
        except Exception:  # noqa: BLE001
            errors.append(f"{cid}: start/end missing or unreadable")
            continue
        if not (0 <= s_ms < e_ms <= total + 40):
            errors.append(f"{cid}: {fmt_ts(s_ms, '.')}–{fmt_ts(e_ms, '.')} is empty or outside the episode ({fmt_ts(total, '.')})")
            continue
        if c.get("type") not in types:
            errors.append(f"{cid}: type {c.get('type')!r} is not one of {types}")
        if c.get("secondary_type") and c["secondary_type"] not in types:
            errors.append(f"{cid}: secondary_type {c['secondary_type']!r} is not one of {types}")
        for key, at, anchor in (("evidence", s_ms, "start"), ("end_evidence", e_ms, "end")):
            if not str(c.get(key) or "").strip():
                errors.append(f"{cid}: {key} missing (copy the first/last words exactly from the transcript)")
            elif not find_evidence(words, c[key], at, tol, anchor):
                errors.append(f"{cid}: {key} not found verbatim within ±{tol / 1000:.0f} s of {fmt_ts(at, '.')}: {c[key]!r}")
        score = c.get("score") or {}
        bad = [k for k in SCORE_KEYS if not isinstance(score.get(k), int) or not 1 <= score[k] <= 10]
        if bad:
            errors.append(f"{cid}: score needs integers 1-10 for {', '.join(bad)}")
        in_ms, out_ms = snap_in(words, s_ms, cfg), snap_out(words, e_ms, cfg, total)
        if out_ms <= in_ms:
            errors.append(f"{cid}: snapped range is empty ({fmt_ts(in_ms, '.')}–{fmt_ts(out_ms, '.')})")
        d = (out_ms - in_ms) / 1000
        if d < dur_cfg["hard_min"] or d > dur_cfg["hard_max"]:
            errors.append(f"{cid}: duration {d:.1f} s outside {dur_cfg['hard_min']}-{dur_cfg['hard_max']} s")
        elif d < dur_cfg["min"] or d > dur_cfg["max"]:
            warnings.append(f"{cid}: duration {d:.1f} s outside the usual {dur_cfg['min']}-{dur_cfg['max']} s")
        cw = []
        if c.get("needs_context") and not str(c.get("context_line") or "").strip():
            cw.append("needs_context without a context_line (the context_card text)")
        unknown = [s for s in c.get("speakers") or [] if people and s not in people]
        if unknown:
            cw.append(f"speakers {unknown} not in speakers.json people {list(people)}")
        inside = [w for w in words if w["start_ms"] >= in_ms - 50 and w["end_ms"] <= out_ms + 50]
        text = norm(" ".join(w["word"] for w in inside))
        hits = [a for a in avoid if norm(str(a)) and re.search(rf"(^| ){re.escape(norm(str(a)))}( |$)", text)]
        if hits:
            cw.append(f"mentions topics the sheet says to avoid: {hits} (selection needs --confirm-avoid {cid})")
        warnings += [f"{cid}: {x}" for x in cw]
        total_score = round(sum(score.get(k, 0) for k in SCORE_KEYS) / len(SCORE_KEYS), 1) if not bad else 0.0
        out.append(dict(c, in_ms=in_ms, out_ms=out_ms, duration_ms=out_ms - in_ms, total=total_score,
                        type_label=type_label(c.get("type", "")), avoid_hits=hits, warnings=cw,
                        excerpt_start=" ".join(w["word"] for w in inside[:12]),
                        excerpt_end=" ".join(w["word"] for w in inside[-12:]), words=len(inside),
                        ok=len(errors) == err0))
    for i, a in enumerate(out):
        for b in out[i + 1:]:
            ov = min(a["out_ms"], b["out_ms"]) - max(a["in_ms"], b["in_ms"])
            short = min(a["duration_ms"], b["duration_ms"]) or 1
            if ov > cfg.get("max_overlap_ratio", 0.5) * short:
                warnings.append(f"{a['id']} and {b['id']} overlap by {ov / 1000:.1f} s ({ov / short:.0%} of the shorter)")
    hours = total / 3_600_000
    if hours >= 0.25:
        lo, hi = cfg["candidates_per_hour"]["min"] * hours, cfg["candidates_per_hour"]["max"] * hours
        if len(out) < int(lo) or len(out) > int(hi + 0.999):
            warnings.append(f"{len(out)} candidates for a {total / 60000:.0f}-min episode (expected about "
                            f"{int(lo)}-{int(hi + 0.999)})")
    topics = (read_json(ep.p("01_analysis/topics.json"), {}) or {}).get("topics")
    if topics:
        warnings += [f"topics: {p}" for p in validate_topics(topics, total)]
    out.sort(key=lambda c: (-c["total"], c["in_ms"]))
    ok = not errors
    res = {"generated": now_iso(), "episode_id": ep.episode_id, "ok": ok, "errors": errors, "warnings": warnings,
           "duration_ms": total, "fingerprint": reels_plan_fingerprint(ep), "candidates": out}
    write_json(ep.p("01_analysis/reels-plan-validation.json"), {k: res[k] for k in ("generated", "ok", "errors", "warnings")})
    if ok:
        write_json(ep.p("01_analysis/reels-plan-validated.json"), res)
        write_reels_plan_md(ep, res)
    else:
        ep.p("01_analysis/reels-plan-validated.json").unlink(missing_ok=True)
    return res


def fresh_validated(ep) -> dict:
    """The validated plan, refused when reels-plan.json or the transcript changed since `reels-plan` ran."""
    res = read_json(ep.p("01_analysis/reels-plan-validated.json"))
    if not res:
        raise SystemExit(f"no validated reels plan — run `reel reels-plan --episode {ep.episode_id}`")
    if res.get("fingerprint") != reels_plan_fingerprint(ep):
        raise SystemExit("reels-plan.json or the transcript changed since validation — run "
                         f"`reel reels-plan --episode {ep.episode_id}` again")
    return res


def _label_png(path: Path, lines: list[str], w: int = 540, h: int = 960) -> Path:
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.load_default(size=22)
    except TypeError:   # Pillow < 10.1
        f = ImageFont.load_default()
    d.rectangle((0, 0, w, 34 * len(lines) + 16), fill=(0, 0, 0, 170))
    for k, line in enumerate(lines):
        d.text((14, 10 + 34 * k), line, fill=(255, 230, 80, 255) if k == 0 else (235, 235, 235, 255), font=f)
    d.rectangle((0, h - 34, w, h), fill=(0, 0, 0, 150))
    d.text((14, h - 28), "candidate preview - whole frame, not the edit", fill=(200, 200, 200, 255), font=f)
    im.save(path)
    return path


def render_candidates(ep, ids: list[str] | None = None) -> dict:
    """A quick 540x960 preview per candidate: the whole 16:9 frame letterboxed (not cropped: the reframe is decided
    per shot later), the episode audio for the range, and a Latin label. Plus a first-frame JPG and a sheet."""
    from PIL import Image, ImageDraw
    from .common import ffmpeg_exe, run
    from .episode import episode_file
    res = fresh_validated(ep)
    src = episode_file(ep)
    cands = [c for c in res["candidates"] if not ids or c["id"] in ids]
    d = ep.p("03_candidates")
    d.mkdir(parents=True, exist_ok=True)
    outs, failed = [], []
    for c in cands:
        a, dur = c["in_ms"] / 1000, (c["out_ms"] - c["in_ms"]) / 1000
        lab = _label_png(d / f"_{c['id']}_label.png",
                         [f"{c['id']}  score {c.get('total')}  {c.get('type')}",
                          f"{fmt_ts(c['in_ms'], '.')} -> {fmt_ts(c['out_ms'], '.')}  ({dur:.0f} s)"])
        mp4, jpg = d / f"{c['id']}.mp4", d / f"{c['id']}.jpg"
        r = run([ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{a:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
                 "-i", str(lab), "-filter_complex",
                 "[0:v]scale=540:-2,pad=540:960:0:(oh-ih)/2:color=0x111111[v];[v][1:v]overlay=0:0[o]",
                 "-map", "[o]", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(mp4)], check=False)
        run([ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{a + 0.2:.3f}", "-i", str(src), "-frames:v", "1",
             "-vf", "scale=540:-2", "-q:v", "3", str(jpg)], check=False)
        lab.unlink(missing_ok=True)
        if r.returncode or not mp4.exists():
            failed.append({"id": c["id"], "error": (r.stderr or "")[-300:]})
            continue
        outs.append({"id": c["id"], "mp4": str(mp4), "jpg": str(jpg) if jpg.exists() else None})
    sheet = None
    tiles = [o for o in outs if o["jpg"]]
    if tiles:
        cols, w, h = 4, 360, 203
        rows = (len(tiles) + cols - 1) // cols
        im = Image.new("RGB", (cols * w, rows * (h + 24)), "black")
        dr = ImageDraw.Draw(im)
        byid = {c["id"]: c for c in cands}
        for k, o in enumerate(tiles):
            t = Image.open(o["jpg"]).convert("RGB")
            t.thumbnail((w, h))
            x, y = (k % cols) * w, (k // cols) * (h + 24)
            im.paste(t, (x, y + 24))
            c = byid[o["id"]]
            dr.text((x + 6, y + 6), f"{o['id']}  {c.get('total')}  {c.get('type')}  {fmt_ts(c['in_ms'], '.')[:8]}", fill="yellow")
        sheet = d / "_sheet.jpg"
        im.save(sheet, quality=85)
    write_reels_plan_md(ep, res)
    return {"ok": not failed, "previews": outs, "failed": failed, "sheet": str(sheet) if sheet else None}


# --------------------------------------------------------------------------- Gate 0: selection -> reel projects
def parse_adjust(items: list[str]) -> dict:
    """['R03:in=00:12:04.000', 'R03:out=780.5'] -> {'R03': {'in': 724000, 'out': 780500}}."""
    from .plan import to_ms
    out = {}
    for it in items or []:
        m = re.fullmatch(r"\s*(R\d+)\s*:\s*(in|out)\s*=\s*(.+?)\s*", it or "")
        if not m:
            raise SystemExit(f"--adjust {it!r}: expected like R03:in=00:12:04.000 or R03:out=00:13:05")
        out.setdefault(m.group(1), {})[m.group(2)] = to_ms(m.group(3))
    return out


def slice_wav(src: Path, dst: Path, in_ms: int, out_ms: int) -> Path:
    """Exact sample slice of a PCM WAV (the episode's 16 kHz mono transcript audio)."""
    import wave
    with wave.open(str(src)) as r:
        sr, ch, sw = r.getframerate(), r.getnchannels(), r.getsampwidth()
        a = int(round(in_ms * sr / 1000))
        n = int(round(out_ms * sr / 1000)) - a
        r.setpos(min(a, r.getnframes()))
        data = r.readframes(max(0, n))
    dst.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(sw)
        w.setframerate(sr)
        w.writeframes(data)
    return dst


def slice_transcript(ep, reel, in_ms: int, out_ms: int) -> dict:
    """The reel's transcript = the episode words inside the window, on the reel clock (0 = in-point), renumbered
    (episode_word_id kept), flags and corrections kept; then the standard transcript files via finalize()."""
    from .transcribe import finalize, transcript_verified, words_fingerprint
    wj, tj = read_json(ep.p("02_transcription/words.json")), read_json(ep.p("02_transcription/transcript.json"))
    dur = out_ms - in_ms
    words, seg_of = [], {}
    for w in wj["words"]:
        if w["start_ms"] >= in_ms - 50 and w["end_ms"] <= out_ms + 50:
            nw = dict(w, id=len(words) + 1, episode_word_id=w["id"], start_ms=max(0, w["start_ms"] - in_ms),
                      end_ms=min(dur, w["end_ms"] - in_ms))
            words.append(nw)
            seg_of.setdefault(w.get("segment_id"), []).append(nw)
    src_segs = {s["id"]: s for s in tj["segments"]}
    segs = []
    for sid, ws in seg_of.items():
        s0 = src_segs.get(sid, {})
        seg = {"id": len(segs) + 1, "start_ms": ws[0]["start_ms"], "end_ms": ws[-1]["end_ms"],
               "text": " ".join(w["word"] for w in ws), "avg_logprob": s0.get("avg_logprob", 0.0),
               "no_speech_prob": s0.get("no_speech_prob", 0.0), "compression_ratio": s0.get("compression_ratio", 1.0),
               "words": [w["id"] for w in ws], "episode_segment_id": sid}
        for w in ws:
            w["segment_id"] = seg["id"]
        segs.append(seg)
    meta = {k: v for k, v in tj["meta"].items() if k not in ("chunks", "scripts", "corrections_applied", "corrections_file")}
    meta.update({"duration_ms": dur, "offset_ms": in_ms, "sliced_from": f"episode {ep.episode_id}",
                 "episode_transcript": str(ep.p("02_transcription/transcript.json"))})
    out = reel.p("02_transcription")
    for f in ("verification.json", "transcript-corrections.json"):
        (out / f).unlink(missing_ok=True)
    res = finalize(reel, meta, segs, words)
    for name in ("transcript", "words"):
        (out / f"{name}.machine.json").write_bytes((out / f"{name}.json").read_bytes())
    wav = ep.p("02_transcription/dialogue_16k_mono.wav")
    if wav.exists():
        slice_wav(wav, out / "dialogue_16k_mono.wav", in_ms, out_ms)
    if transcript_verified(ep):
        write_json(out / "verification.json", {"verified": True, "by": "episode verification", "at": now_iso(),
                                                "note": f"the episode transcript of {ep.episode_id} was verified",
                                                "words_sha1": words_fingerprint(reel)})
    return res


def slice_speakers(ep, in_ms: int, out_ms: int) -> dict:
    """Episode speaker turns inside the window, on the reel clock (ints), plus the people and their positions."""
    from .plan import to_ms
    sp = read_json(ep.p("01_analysis/speakers.json"), {}) or {}
    turns = []
    for t in sp.get("turns", []):
        try:
            a, b = to_ms(t["start"]), to_ms(t["end"])
        except Exception:  # noqa: BLE001
            continue
        a, b = max(a, in_ms), min(b, out_ms)
        if b > a:
            turns.append({"start_ms": a - in_ms, "end_ms": b - in_ms, "speaker": t.get("speaker")})
    return {"method": sp.get("method", "none"), "people": sp.get("people", {}), "turns": turns}


def window_stale(paths) -> str | None:
    """A reel whose episode file changed after selection must not be built from the old window."""
    from .common import sha1_head, source_range
    src = source_range(paths)
    if src.get("kind") != "episode_reel" or not src.get("fingerprint"):
        return None
    f = Path(src["footage"])
    f = f if f.is_absolute() else paths.root / f
    redo = (f"re-run the episode steps (episode-prep, episode-transcribe, reels-plan) and `reel reels-select --episode "
            f"{src.get('episode_id')} --pick {src.get('reel_id')} --force`")
    if not f.exists():
        return f"the episode file {src['footage']} is gone: {redo}"
    if sha1_head(f) != src["fingerprint"]:
        return f"the episode file {src['footage']} changed after this reel was selected: {redo}"
    return None


def select(ep, picks: list[str], adjust: list[str], by: str, note: str = "", confirm_avoid=(), force: bool = False,
           resync: bool = False) -> dict:
    """Gate 0. Only the editor (or the lead on the editor's explicit delegation) runs this; a hook blocks subagents.
    Each pick becomes output/projects/<EP>_<RID>/ with 00_inputs/source.json (the shared range format), the sliced
    transcript and 16 kHz audio, the speaker turns and the recipe. --resync re-slices the transcripts of the reels
    already selected (after episode transcript corrections) without changing their windows."""
    from .common import Paths, load_status, set_status, sha1_head
    from .episode import episode_file, load_episode, podcast_cfg
    from .recipes import resolve
    if by not in ("editor", "delegated"):
        raise SystemExit("--by must be editor or delegated")
    info = load_episode(ep)
    src = episode_file(ep)
    fp = sha1_head(src)
    if info.get("fingerprint") and info["fingerprint"] != fp:
        raise SystemExit(f"the episode file changed since episode-prep: re-run `reel episode-prep --episode {ep.episode_id}`, "
                         "then transcribe and plan again")
    rel = src.relative_to(ep.root).as_posix() if src.is_relative_to(ep.root) else str(src)
    sel_f = ep.p("01_analysis/selection.json")
    sel = read_json(sel_f, {"history": []}) or {"history": []}
    out = []
    if resync:
        done = sorted({r for h in sel["history"] for r in h.get("picked", [])})
        for rid in done:
            reel = Paths(ep.root, f"{ep.episode_id}_{rid}")
            s = read_json(reel.p("00_inputs/source.json"))
            if not s:
                continue
            slice_transcript(ep, reel, s["in_ms"], s["out_ms"])
            out.append({"reel_id": reel.video_id, "status": "transcript re-sliced", "in_ms": s["in_ms"], "out_ms": s["out_ms"]})
        return {"reels": out, "next": "re-run `reel plan` for these reels (their approval became stale if words changed)"}
    res = fresh_validated(ep)
    byid = {c["id"]: c for c in res["candidates"]}
    adj = parse_adjust(adjust)
    unknown = [p for p in picks + list(adj) if p not in byid]
    if unknown:
        raise SystemExit(f"unknown candidate(s) {unknown}; the plan has {list(byid)}")
    blocked = [p for p in picks if byid[p].get("avoid_hits") and p not in (confirm_avoid or ())]
    if blocked:
        raise SystemExit(f"{blocked} mention topics the episode sheet says to avoid "
                         f"({ {p: byid[p]['avoid_hits'] for p in blocked} }): only with the editor's explicit OK, add "
                         + " ".join(f"--confirm-avoid {p}" for p in blocked))
    wj = read_json(ep.p("02_transcription/words.json"))
    cfg = podcast_cfg()
    dur_cfg = cfg["reel_duration_s"]
    intake = read_json(ep.p("00_inputs/intake.json"), {}) or {}
    for rid in picks:
        c = byid[rid]
        in_ms, out_ms = c["in_ms"], c["out_ms"]
        if "in" in adj.get(rid, {}):
            in_ms = snap_in(wj["words"], adj[rid]["in"], cfg)
        if "out" in adj.get(rid, {}):
            out_ms = snap_out(wj["words"], adj[rid]["out"], cfg, res["duration_ms"])
        d = (out_ms - in_ms) / 1000
        if adj.get(rid) and not dur_cfg["hard_min"] <= d <= dur_cfg["hard_max"]:   # the plan's own windows were validated
            raise SystemExit(f"{rid}: adjusted duration {d:.1f} s is outside {dur_cfg['hard_min']}-{dur_cfg['hard_max']} s")
        reel = Paths(ep.root, f"{ep.episode_id}_{rid}")
        old = read_json(reel.p("00_inputs/source.json"))
        status = "created"
        if old:
            if (old.get("in_ms"), old.get("out_ms"), old.get("fingerprint")) == (in_ms, out_ms, fp):
                out.append({"reel_id": reel.video_id, "status": "unchanged", "in_ms": in_ms, "out_ms": out_ms})
                continue
            if not force:
                raise SystemExit(f"{reel.video_id} already exists with {fmt_ts(old['in_ms'], '.')}–{fmt_ts(old['out_ms'], '.')}; "
                                 f"the new window {fmt_ts(in_ms, '.')}–{fmt_ts(out_ms, '.')} needs --force (the reel is "
                                 "re-sliced; its plan and build become stale)")
            status = "re-sliced"
        reel.ensure_project()
        cand = {k: v for k, v in c.items() if k not in ("warnings", "ok")}
        write_json(reel.p("00_inputs/source.json"), {
            "footage": rel, "in_ms": in_ms, "out_ms": out_ms, "duration_ms": out_ms - in_ms, "offset_ms": in_ms,
            "label": f"{ep.episode_id} {rid} {c.get('title', '')}".strip(), "set_at": now_iso(),
            "kind": "episode_reel", "episode_id": ep.episode_id, "reel_id": rid, "fingerprint": fp,
            "content_type": c.get("type"), "secondary_type": c.get("secondary_type"), "recipe": resolve(c.get("type", "")),
            "context_line": c.get("context_line") if c.get("needs_context") else "", "candidate": cand,
            "intake": intake, "selected_by": by, "selected_at": now_iso(), "note": note})
        write_json(reel.p("00_inputs/speakers.json"), slice_speakers(ep, in_ms, out_ms))
        slice_transcript(ep, reel, in_ms, out_ms)
        st = load_status(reel)
        if st.get("status") in (None, "NOT_STARTED", "TRANSCRIBED") or status == "re-sliced":
            set_status(reel, "TRANSCRIBED", f"sliced from episode {ep.episode_id} ({rid}, "
                                            f"{fmt_ts(in_ms, '.')}–{fmt_ts(out_ms, '.')})", "transcribe")
        out.append({"reel_id": reel.video_id, "status": status, "in_ms": in_ms, "out_ms": out_ms,
                    "type": c.get("type"), "project": str(reel.project)})
    sel["history"].append({"picked": picks, "adjust": adjust or [], "confirm_avoid": list(confirm_avoid or ()),
                           "by": by, "note": note, "at": now_iso(), "plan_fingerprint": res["fingerprint"]})
    write_json(sel_f, sel)
    return {"reels": out, "next": "per reel: reel preflight, audio-clean, story-editor (recipe in 00_inputs/source.json), "
                                  "plan, previews, preview-video, then ONE combined Gate 1"}


def write_reels_plan_md(ep, res: dict) -> Path:
    L = [f"# Reels plan — {ep.episode_id} (Gate 0: the editor picks)", "",
         f"Episode {fmt_ts(res['duration_ms'], '.')} · {len(res['candidates'])} candidates · validated {res.get('generated', '')}", "",
         "| # | Score | Type | In → Out | Dur | Title | Hook | Flags | Preview |", "|---|---|---|---|---|---|---|---|---|"]
    for c in res["candidates"]:
        flags = []
        if c.get("needs_context"):
            flags.append("needs context")
        if c.get("avoid_hits"):
            flags.append("AVOID: " + ", ".join(c["avoid_hits"]))
        if c.get("risks"):
            flags.append("risks: " + "; ".join(map(str, c["risks"]))[:60])
        prev = ep.p(f"03_candidates/{c['id']}.mp4")
        L.append(f"| {c['id']} | {c['total']} | {c.get('type')} ({c.get('type_label')}) | {fmt_ts(c['in_ms'], '.')} → "
                 f"{fmt_ts(c['out_ms'], '.')} | {c['duration_ms'] / 1000:.0f} s | {str(c.get('title', ''))[:50]} | "
                 f"{str(c.get('hook_text') or c.get('hook_quote') or '')[:60]} | {'; '.join(flags) or '—'} | "
                 f"{prev.name if prev.exists() else '—'} |")
    L += ["", "## Details", ""]
    for c in res["candidates"]:
        sc = c.get("score") or {}
        L += [f"### {c['id']} · {c.get('title', '')}",
              f"- Type: {c.get('type')} ({c.get('type_label')})" + (f", also {c['secondary_type']}" if c.get("secondary_type") else ""),
              f"- Score {c['total']}: hook {sc.get('hook')}, standalone {sc.get('standalone')}, payoff {sc.get('payoff')}, "
              f"ending {sc.get('ending')}",
              f"- Why: {c.get('why', '')}",
              f"- Opens with: «{c.get('excerpt_start', '')}»",
              f"- Ends with: «{c.get('excerpt_end', '')}»"]
        if c.get("needs_context"):
            L.append(f"- Context card: {c.get('context_line') or '(missing)'}")
        L += [f"- Note: {w}" for w in c.get("warnings", [])] + [""]
    if res.get("warnings"):
        L += ["## Warnings", ""] + [f"- {w}" for w in res["warnings"]] + [""]
    L += ["**To choose:** tell the lead which reels to make (e.g. \"R01, R03; R03 start at 12:04\"). Nothing is cut "
          "until you pick (`reel reels-select --by editor`)."]
    return write_text(ep.p("01_analysis/reels-plan.md"), "\n".join(L) + "\n")
