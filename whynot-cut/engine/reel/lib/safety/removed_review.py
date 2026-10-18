# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""K-T2 (Phase 4 Task 62): the "what we removed" review clip.

`reel removed-review` renders a short MP4 of only the parts the edit removes (cuts, retakes, pauses removed by
audio-clean, the trimmed head and tail), in timeline order. Each removed piece gets a one-second slate (the source
timecode, the removed words, the reason: pause / filler / retake / editor cut / trimmed) and 0.5 s of kept context
before and after it, dimmed, so the editor hears the seam. Words whose loss changes meaning (negations, numbers,
doses, drug names: K-T1's classes) are highlighted on the slate and listed first in the sheet next to the clip.

The removed parts are the complement of the compiled plan's kept pieces (timeline-spec time_map.keep_ms), so the clip
shows exactly what the plan cuts. Context never reaches outside the source (before 0 or after its end); the file's
in-point (a reel cut from a longer file) is added only when reading the file. Encoding uses the GPU when the engine's
GPU slot gives one (an intermediate, like the preview video), else the processor; a GPU failure is redone once on the
processor. A standalone command: nothing else reads its output, so it has no switch."""
from __future__ import annotations

import json
from pathlib import Path

OUT_DIR = "08_quality_control/removed-review"
SLATE_S = 1.0
CONTEXT_S = 0.5
DIM = 0.35                  # how much the kept context is darkened (eq brightness -DIM) and quieted (volume 1-DIM)
SIZE_H = 720                # the review clip's height; width follows the source (even)
REASON = {"head": ("بداية اتقصت", "trimmed head"), "tail": ("آخر اتقص", "trimmed tail"),
          "pause": ("سكتة", "pause"), "retake": ("إعادة", "retake"), "filler": ("حشو", "filler"),
          "false_start": ("بداية مقطوعة", "false start"), "repeat_word": ("كلمة متكررة", "repeated word"),
          "editor_cut": ("قص المونتير", "editor cut")}


from .risk_words import WEIGHT as _WEIGHT     # the riskiest meaning words first on a slate


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _read(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return None


def _tc(ms) -> str:
    ms = int(ms or 0)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000 // 100}"


def _removed(keep: list, dur: int) -> list:
    """The complement of the kept pieces within [0, dur]; touching or overlapping pieces merge."""
    ks = sorted((max(0, int(a)), min(dur, int(b))) for a, b in keep if _num(a) is not None and _num(b) is not None)
    out, t = [], 0
    for a, b in ks:
        if b <= a:
            continue
        if a > t:
            out.append([t, a])
        t = max(t, b)
    if t < dur:
        out.append([t, dur])
    return out


def _reason(span, dur, first_keep, last_keep, pauses, cut_words, words_in) -> str:
    a, b = span
    if a == 0 and first_keep is not None and b <= first_keep:
        return "head"
    if b == dur and last_keep is not None and a >= last_keep:
        return "tail"
    ids = {w["id"] for w in words_in}
    for c in cut_words:
        if not isinstance(c, dict) or not ids & set(c.get("word_ids") or []):
            continue
        r = str(c.get("reason") or "")
        if r.startswith("TK-") or " retake" in r[:24]:
            return "retake"
        for k in ("false_start", "repeat_word", "filler"):
            if r.startswith("CP-") and f" {k}" in r[:24]:
                return k
        return "editor_cut"
    if any(min(b, q) - max(a, p) >= 0.5 * (b - a) for p, q in pauses):
        return "pause"
    return "editor_cut"


def plan(paths, ctx=None) -> dict:
    """{"pieces": [...], "source", "in_ms", "duration_ms"} from the compiled plan. Each piece: start_ms, end_ms
    (transcript clock), reason, word_ids, words, meaning [{text, risk}], context_before_ms, context_after_ms,
    file_from_ms, file_to_ms (on the source file's own clock). Refused with a plain reason when there is no usable
    compiled plan. Writes nothing."""
    from ..errors import Guidance
    sf = paths.p("01_analysis/timeline-spec.json")
    spec = _read(sf)
    tm = spec.get("time_map") if isinstance(spec, dict) else None
    refuse = Guidance("مفيش خطة متجمعة للفيديو ده، فمش عارف إيه اللي اتشال / no compiled plan for this item, so "
                      "there is nothing to compare (01_analysis/timeline-spec.json is missing or damaged)",
                      "Run `reel plan` first, then `reel removed-review`", where=str(sf))
    if not isinstance(spec, dict):
        raise refuse
    if isinstance(tm, dict) and isinstance(tm.get("keep_ms"), list) and _num(tm.get("source_duration_ms")) is not None:
        dur = int(tm["source_duration_ms"])
        keep = [k for k in tm["keep_ms"] if isinstance(k, (list, tuple)) and len(k) == 2]
    elif "time_map" in spec and tm is None and _num(spec.get("duration_ms")) is not None:
        # no pause removed and no word cut: the plan keeps the whole clip (time_map is null)
        dur = int(spec["duration_ms"])
        keep = [[0, dur]]
    else:
        raise refuse
    in_ms = int(_num(spec.get("source_in_ms")) or 0)
    spans = _removed(keep, dur)
    kept = sorted((int(a), int(b)) for a, b in keep if _num(a) is not None and _num(b) is not None and b > a)
    first_keep = kept[0][0] if kept else None
    last_keep = kept[-1][1] if kept else None
    wj = _read(paths.p("02_transcription/words.json"))
    ws = [w for w in (wj.get("words") or []) if isinstance(w, dict) and _num(w.get("start_ms")) is not None
          and _num(w.get("end_ms")) is not None and isinstance(w.get("word"), str) and w.get("id") is not None] \
        if isinstance(wj, dict) else []
    meta = wj.get("meta") if isinstance(wj, dict) and isinstance(wj.get("meta"), dict) else {}
    pj = _read(paths.p("06_audio/dialogue/pauses.json"))
    pauses = [c for c in (pj.get("cuts_ms") or []) if isinstance(c, (list, tuple)) and len(c) == 2
              and all(_num(x) is not None for x in c)] if isinstance(pj, dict) else []
    ed = _read(paths.p("01_analysis/edit-decisions.json"))
    cut_words = ((ed.get("global") or {}).get("cut_words") or []) if isinstance(ed, dict) else []
    meaning_items, check = _meaning(ws, meta, ctx)
    pieces = []
    for k, (a, b) in enumerate(spans):
        # a word belongs to the removed part when at least half of it is inside (timing drift at a cut edge)
        inside = [w for w in ws if _inside(w, a, b)]
        ids = {w["id"] for w in inside}
        prev_end = spans[k - 1][1] if k else 0              # the context is kept footage only: never the source's
        next_start = spans[k + 1][0] if k + 1 < len(spans) else dur      # outside, never the next removed part
        cb = min(int(CONTEXT_S * 1000), a - prev_end)
        ca = min(int(CONTEXT_S * 1000), next_start - b)
        pieces.append({
            "start_ms": a, "end_ms": b,
            "reason": _reason((a, b), dur, first_keep, last_keep, pauses, cut_words, inside),
            "word_ids": [w["id"] for w in inside], "words": " ".join(w["word"].strip() for w in inside),
            "meaning": [{"text": m["text"], "risk": m["risk"], "start_ms": m["start_ms"]}
                        for m in sorted(meaning_items, key=lambda m: (-_WEIGHT.get(m["risk"], 0), m["start_ms"] or 0))
                        if set(m["word_ids"]) & ids],
            "context_before_ms": cb, "context_after_ms": ca,
            "file_from_ms": in_ms + a - cb, "file_to_ms": in_ms + b + ca})
    return {"pieces": pieces, "source": spec.get("main_footage"), "in_ms": in_ms, "duration_ms": dur,
            "meaning_check": check}


def _inside(w: dict, a: int, b: int) -> bool:
    """At least half of the word is inside [a, b) (timing drift at a cut edge); a zero-length word by its start."""
    s, e = w["start_ms"], w["end_ms"]
    if e <= s:
        return a <= s < b
    return min(b, e) - max(a, s) >= 0.5 * (e - s)


def _meaning(ws, meta, ctx) -> tuple:
    """(K-T1's high-risk items of the whole transcript (sure or not), the check's state {"ran", "why", "partly"}).
    A check that did not run never reads as "nothing found": no transcript words, or K-T1 failing (the clip is still
    made, and the sheet says the words were not marked); a drug list K-T1 refused is named."""
    if not any(w["word"].strip() for w in ws):
        return [], {"ran": False, "why": "no transcript words (02_transcription/words.json missing, empty or unusable)",
                    "partly": []}
    try:
        from . import risk_words
        c = risk_words.context(ctx)
        items = risk_words.classify(ws, meta, domain=c["domain"], terms=c["terms"], groups=c["groups"])
    except Exception as e:  # noqa: BLE001  (a helper on the slate: never blocks the review clip; said on the sheet)
        return [], {"ran": False, "why": f"the meaning reader failed: {type(e).__name__}: {str(e)[:120]}",
                    "partly": []}
    if not isinstance(items, list) or not all(
            isinstance(m, dict) and isinstance(m.get("text"), str) and isinstance(m.get("risk"), str)
            and isinstance(m.get("word_ids"), list) for m in items):
        return [], {"ran": False, "why": "the meaning reader gave an answer that cannot be read", "partly": []}
    refused = c.get("lexicon_refused") if isinstance(c, dict) else None
    if refused is None or isinstance(refused, list) and all(isinstance(r, dict) for r in refused):
        partly = [{"ar": str(r.get("reason_ar") or r.get("id")), "en": f"{r.get('id')}: {r.get('reason')}"}
                  for r in refused or []]
    else:
        partly = [{"ar": "قايمة مصادر الأدوية المرفوضة مش مقروءة", "en": "the list of refused drug sources cannot be read"}]
    return items, {"ran": True, "why": None, "partly": partly}


def duration_s(pieces) -> float:
    """The clip's length: every removed part, its slate, and its clamped context before and after."""
    return round(sum((p["end_ms"] - p["start_ms"] + p["context_before_ms"] + p["context_after_ms"]) / 1000 + SLATE_S
                     for p in pieces), 3)


RISK_AR = {"dose": "جرعة", "drug": "اسم دوا", "negation": "نفي", "duration": "مدة أو عدد مرات", "number": "رقم"}


def not_checked(doc: dict) -> str:
    """The line that says the meaning words were not marked, or only partly ("" when the check ran whole). A doc with
    no record of the check counts as not run."""
    mc = doc.get("meaning_check") if isinstance(doc.get("meaning_check"), dict) else {}
    if mc.get("ran") is not True:
        return ("فحص المعنى ماشتغلش، فالكلمات اللي بتغيّر المعنى مش متعلّم عليها: اسمع الكليب كله / the meaning check "
                f"did not run ({mc.get('why') or 'no record of it'}): words whose loss changes meaning are not marked; "
                "listen to the whole clip")
    if mc.get("partly"):
        return ("أسماء الأدوية اتفحصت جزئيًا (" + "؛ ".join(x["ar"] for x in mc["partly"]) + ") / drug names partly "
                "checked (" + "; ".join(x["en"] for x in mc["partly"]) + ")")
    return ""


def sheet(doc: dict) -> str:
    """The text sheet next to the clip, Arabic first: the meaning words first (each at its own time), then every
    removed part in order."""
    pieces = doc["pieces"]
    risky = [(k, m) for k, p in enumerate(pieces, 1) for m in p["meaning"]]
    L = ["# اللي اتشال من الفيديو — What we removed", "",
         f"- {len(pieces)} جزء، طول الكليب {duration_s(pieces):.1f} ثانية / {len(pieces)} parts, a "
         f"{duration_s(pieces):.1f} s clip", "",
         "## كلمات بتغيّر المعنى — Words whose loss changes meaning", ""]
    ran = isinstance(doc.get("meaning_check"), dict) and doc["meaning_check"].get("ran") is True
    if ran:
        L += [f"- #{k} `{_tc(m.get('start_ms'))}` «{m['text']}» — {RISK_AR.get(m['risk'], m['risk'])} / {m['risk']}"
              for k, m in risky] or ["- مفيش / none"]
    if not_checked(doc):
        L.append(f"- ⚠ {not_checked(doc)}")
    L += ["", "## كل اللي اتشال بالترتيب — Every removed part, in order", ""]
    for k, p in enumerate(pieces, 1):
        ar, en = REASON[p["reason"]]
        L.append(f"- #{k} `{_tc(p['start_ms'])}`–`{_tc(p['end_ms'])}` {ar} / {en}"
                 + (f": «{p['words']}»" if p["words"] else ""))
    return "\n".join(L) + "\n"


# --- rendering ---------------------------------------------------------------------------------------------------------
SITE = "removed_review"


def _slot():
    """The engine's GPU slot for this intermediate (accel.SITE_LANES / gpu_lock.WAITS decide whether it uses the GPU at
    all), held for the whole render: one GPU job at a time; it waits while Premiere or After Effects exports."""
    from .. import gpu_lock
    return gpu_lock.site_slot(SITE, wait_s=120.0)


def _lane(slot_lane: str = "cpu") -> str:
    """The encoder lane: the slot's GPU when this machine's ffmpeg can use it, else the processor."""
    from .. import accel
    return slot_lane if slot_lane in ("cuda", "videotoolbox") and accel.detect().get("kind") == slot_lane else "cpu"


def _short(text: str, n: int = 80) -> str:
    """At most n characters, cut at a word boundary with an ellipsis."""
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0]
    return (cut or text[:n]) + " …"


def _slate(piece: dict, k: int, size: tuple, path: Path) -> None:
    """A dark slate: number, timecode, reason, the removed words; meaning words in a warm colour, the riskiest first.
    Arabic is shaped with HarfBuzz when it is available (the engine's own text renderer), else drawn plainly."""
    from PIL import Image, ImageDraw
    W, H = size
    img = Image.new("RGB", (W, H), (18, 22, 30))
    lines = [(f"#{k}  {_tc(piece['start_ms'])}", (230, 230, 230)),
             ("  /  ".join(REASON[piece["reason"]]), (150, 200, 255))]
    if piece["words"]:
        lines.append((_short(piece["words"]), (255, 255, 255)))
    meaning = piece["meaning"]
    for m in meaning[:3]:
        lines.append((f"! {m['text']}", (255, 190, 80)))
    if len(meaning) > 3:
        lines.append((f"+{len(meaning) - 3}", (255, 190, 80)))
    y, size_px = int(H * 0.2), max(14, H // 18)
    font = _font(size_px)
    draw = ImageDraw.Draw(img)
    for text, rgb in lines:
        # Western digits on the slate: the shared renderer drew Arabic-Indic digits reversed inside Arabic text
        # («٣٫٥» as «٥٫٣»; hb_text patch sent with K-T5) and a reversed dose on a review slate would mislead
        text = text.translate(_WESTERN)
        for line in _wrap(text, font, int(W * 0.9), size_px):
            if y > H - size_px:
                break
            if font is not None:
                from .. import hb_text
                im, _base, _w = hb_text.render_line(line, font, rgba=rgb + (255,))
                img.paste(im, (max(0, (W - im.width) // 2), y), im)
                y += im.height
            else:
                draw.text((W // 20, y), line, fill=rgb)
                y += size_px + size_px // 4
        y += size_px // 3
    img.save(path)


_WESTERN = str.maketrans({**{chr(0x660 + i): str(i) for i in range(10)}, **{chr(0x6F0 + i): str(i) for i in range(10)},
                          "٫": ".", "٬": ",", "٪": "%"})


def _wrap(text: str, font, width: int, px: int) -> list:
    """Words in lines no wider than `width` (measured with the font; about 0.55 em a letter without one)."""
    def wide(s):
        if font is not None:
            from .. import hb_text
            return hb_text.measure(s, font)
        return len(s) * px * 0.55
    out, cur = [], ""
    for w in text.split():
        nxt = f"{cur} {w}".strip()
        if cur and wide(nxt) > width:
            out.append(cur)
            cur = w
        else:
            cur = nxt
    return out + ([cur] if cur else [])


def _font(px: int):
    try:
        from .. import fonts, hb_text
        if not hb_text.AVAILABLE:
            return None
        face = fonts.arabic_fallback(bold=True)
        return hb_text.HBFontSpec(face["file"], px, face.get("index", 0)) if face and face.get("file") else None
    except Exception:  # noqa: BLE001
        return None


def _probe(src: Path) -> tuple:
    """((width, height) of the review clip, whether the source has sound)."""
    try:
        from ..media import probe
        info = probe(src)
        v = info.get("video") or {}
        w, h = int(v.get("display_width") or v.get("width")), int(v.get("display_height") or v.get("height"))
        has_audio = bool(info.get("audio"))
    except Exception:  # noqa: BLE001
        w, h, has_audio = 1080, 1920, True
    W = max(2, int(round(w * SIZE_H / h / 2)) * 2) if h else 406
    return (W, SIZE_H), has_audio


def _piece_cmd(ff: str, lane: str, src: Path, slate: Path, p: dict, size: tuple, out: Path,
               has_audio: bool = True) -> list:
    from .. import accel
    W, H = size
    a = p["file_from_ms"] / 1000
    d = (p["file_to_ms"] - p["file_from_ms"]) / 1000
    cb, rm = p["context_before_ms"] / 1000, (p["end_ms"] - p["start_ms"]) / 1000
    dim = f"lt(t,{cb:.3f})+gt(t,{cb + rm:.3f})"            # the kept context only (nothing when there is none)
    # a source without sound (a screen recording, B-roll) gets silence of the same length, never an error
    audio_in = "[1:a]" if has_audio else "[3:a]"
    fc = (f"[0:v]scale={W}:{H},setsar=1,fps=25,format=yuv420p[s];"
          f"[1:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25,"
          f"eq=brightness=-{DIM}:enable='{dim}',format=yuv420p[m];"
          f"{audio_in}aresample=48000,aformat=channel_layouts=stereo,volume={1 - DIM}:enable='{dim}'[ma];"
          f"[2:a]aformat=channel_layouts=stereo[sa];"
          f"[s][sa][m][ma]concat=n=2:v=1:a=1[v][a]")
    extra = [] if has_audio else ["-f", "lavfi", "-t", f"{d:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
    return [ff, "-y", "-loglevel", "error",
            "-loop", "1", "-framerate", "25", "-t", f"{SLATE_S:.3f}", "-i", str(slate),
            *accel.decode_args(lane), "-ss", f"{a:.3f}", "-t", f"{d:.3f}", "-i", str(src),
            "-f", "lavfi", "-t", f"{SLATE_S:.3f}", "-i", "anullsrc=r=48000:cl=stereo", *extra,
            "-filter_complex", fc, "-map", "[v]", "-map", "[a]", *accel.h264_args(lane, 23),
            "-c:a", "aac", "-b:a", "128k", str(out)]


def _outputs(paths) -> tuple:
    out_dir = paths.p(OUT_DIR)
    return out_dir, out_dir / f"{paths.video_id}_removed-review.mp4", out_dir / "removed-review.md"


def _clear_stale(paths) -> list:
    """Remove an earlier clip and sheet (plain files this command wrote; a link is never followed)."""
    gone = []
    for f in _outputs(paths)[1:]:
        if f.is_symlink():
            f.unlink()
            gone.append(str(f))
        elif f.is_file():
            f.unlink()
            gone.append(str(f))
    return gone


def render(paths, ctx=None, runner=None) -> dict:
    """Render the review clip and its sheet into 08_quality_control/removed-review/. Nothing removed: no clip, a plain
    message, and an earlier clip and sheet are removed so nothing stale is left. A refusal (no plan, no source
    footage, ffmpeg failing) writes nothing."""
    import shutil
    import tempfile
    from ..common import ffmpeg_exe, log
    from ..errors import Guidance
    doc = plan(paths, ctx)
    if not doc["pieces"]:
        gone = _clear_stale(paths)
        return {"clip": None, "sheet": None, "removed_earlier": gone,
                "message": "مفيش حاجة اتشالت في الخطة دي، فمفيش كليب مراجعة / nothing is removed in this plan, "
                           "so there is no review clip"
                           + ("؛ وكليب المراجعة القديم اتشال / the earlier review clip was removed" if gone else "")}
    src = paths.root / str(doc["source"] or "")
    if not doc["source"] or not src.is_file():
        raise Guidance(f"ملف التصوير الأساسي مش موجود / the main footage is not found: {doc['source']}",
                       "Check global.main_footage in edit-decisions.json, run `reel plan`, then try again",
                       where=str(src))
    ff = ffmpeg_exe()
    size, has_audio = _probe(src)
    work = None
    try:
        work = Path(tempfile.mkdtemp(prefix="removed-review-"))
        with _slot() as slot_lane:
            lane = _lane(slot_lane)
            parts, lane = _parts(paths, doc, ff, src, size, has_audio, lane, work, runner, Guidance, log)
            if lane == "cpu" and any(x[1] != "cpu" for x in parts):
                # a GPU failure part-way: every part again on one encoder, so the joined file is consistent
                parts, lane = _parts(paths, doc, ff, src, size, has_audio, "cpu", work, runner, Guidance, log)
        listing = work / "parts.txt"
        listing.write_text("".join(f"file '{x[0].as_posix()}'\n" for x in parts), encoding="utf-8")
        tmp_clip, tmp_sheet = work / "clip.mp4", work / "sheet.md"
        cmd = [ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy",
               str(tmp_clip)]
        from ..common import run
        res = (runner or (lambda c: run(c, check=False)))(cmd)
        if getattr(res, "returncode", 1) != 0 or not tmp_clip.is_file():
            raise Guidance("ffmpeg ماقدرش يجمع الأجزاء / ffmpeg could not join the parts",
                           "Run `reel removed-review` again; if it repeats, send the log")
        tmp_sheet.write_text(sheet(doc), encoding="utf-8", newline="\n")
        out_dir, clip, sheet_path = _outputs(paths)
        out_dir.mkdir(parents=True, exist_ok=True)
        partials = [out_dir / (clip.name + ".part"), out_dir / (sheet_path.name + ".part")]
        try:
            shutil.copyfile(tmp_clip, partials[0])      # both land, or neither does
            shutil.copyfile(tmp_sheet, partials[1])
            partials[0].replace(clip)
            partials[1].replace(sheet_path)
        finally:
            for f in partials:                          # never a half-written leftover
                if f.is_file() and not f.is_symlink():
                    f.unlink()
    finally:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)    # our own temp folder (no links in it)
    return {"clip": str(clip), "sheet": str(sheet_path), "pieces": len(doc["pieces"]),
            "duration_s": duration_s(doc["pieces"]), "lane": lane,
            "message": f"كليب المراجعة جاهز: {len(doc['pieces'])} جزء / the review clip is ready: "
                       f"{len(doc['pieces'])} parts" + (f" — ⚠ {not_checked(doc)}" if not_checked(doc) else "")}


def _parts(paths, doc, ff, src, size, has_audio, lane, work, runner, Guidance, log) -> tuple:
    """Every part as its own small MP4: [(file, lane used)], and the lane at the end."""
    from .. import accel
    parts, n = [], len(doc["pieces"])
    for k, p in enumerate(doc["pieces"], 1):
        slate = work / f"slate{k:04d}.png"
        if not slate.exists():
            _slate(p, k, size, slate)
        part = work / f"part{k:04d}.mp4"
        res, lane = accel.run_ff(lambda ln, p=p, slate=slate, part=part: _piece_cmd(ff, ln, src, slate, p, size, part,
                                                                                     has_audio),
                                 lane, log_to=paths, runner=runner)
        if getattr(res, "returncode", 1) != 0:
            raise Guidance(f"ffmpeg ماقدرش يعمل الجزء {k} / ffmpeg could not render part {k}: "
                           f"{str(getattr(res, 'stderr', '') or '')[-300:]}",
                           "Check that the main footage plays, then run `reel removed-review` again")
        parts.append((part, lane))
        if n >= 20 and k % 20 == 0:
            log(paths, f"removed-review: {k}/{n} parts ({k}/{n} جزء)")
    return parts, lane
