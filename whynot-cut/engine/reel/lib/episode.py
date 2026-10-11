"""Podcast mode: an EPISODE project (output/episodes/<EP>/) for a finished episode in data/Episodes/, its episode sheet,
intake frames for the intake-inspector, and chunked, resumable Whisper transcription of the whole episode.

An episode is never edited whole: the episode-analyst plans reels from it, the editor picks them (Gate 0) and each
picked reel becomes an ordinary clip project whose source is a window of the episode file (see source.py, reels.py).
"""
from __future__ import annotations

import re
from pathlib import Path

from .common import Paths, ffmpeg_exe, fmt_ts, load_config, now_iso, read_json, run, sha1_head, stable_id, write_json

EPISODE_SUBDIRS = ["00_inputs/intake", "01_analysis", "02_transcription/chunks", "03_candidates", "publish/reels",
                   "publish/thumbnail/candidates", "08_quality_control", "logs"]
SHEET_EXT = (".md", ".markdown", ".txt")


class EpisodePaths(Paths):
    """Same helpers as a clip project (`p()`, `ensure_project()`), rooted at output/episodes/<EP>/."""

    def __init__(self, root: Path, episode_id: str):
        super().__init__(root, episode_id)
        self.episode_id = episode_id
        self.project = self.output / "episodes" / episode_id

    def ensure_project(self):
        for d in EPISODE_SUBDIRS:
            self.p(d).mkdir(parents=True, exist_ok=True)


def podcast_cfg() -> dict:
    return load_config("podcast.json")


# --------------------------------------------------------------------------- sheet
_FM = re.compile(r"\A﻿?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)(.*)\Z", re.S)


def _scalar(v: str):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    return v


def parse_sheet(text: str) -> dict:
    """Episode sheet: frontmatter with flat `key: value`, inline lists `[a, b]` (Arabic comma too) or `- item` lists,
    then free notes. `_notes` = the notes, `_text` = the whole sheet (the only source for names/links in copy)."""
    text = text or ""
    out, body = {}, text
    m = _FM.match(text)
    if m:
        cur = None
        for line in m.group(1).splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            item = re.match(r"^\s*-\s+(.*)$", line)
            if item and cur is not None:
                if not isinstance(out.get(cur), list):
                    out[cur] = []
                out[cur].append(_scalar(item.group(1)))
                continue
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            cur, v = k.strip(), v.strip()
            if v.startswith("[") and v.endswith("]"):
                out[cur] = [_scalar(x) for x in re.split(r"[,،]", v[1:-1]) if x.strip()]
            else:
                out[cur] = _scalar(v) if v else []
        for k, v in list(out.items()):
            if v == []:
                out[k] = ""
        for k in ("avoid", "links"):            # always lists, whether written as `key: x`, `[a, b]` or `- item`
            if k in out and not isinstance(out[k], list):
                out[k] = [out[k]] if str(out[k]).strip() else []
        body = m.group(2)
    out["_notes"] = body.strip()
    out["_text"] = text
    return out


# --------------------------------------------------------------------------- ids, listing
def episode_id_for(path: Path) -> str:
    """Stable project id from the file name. ASCII names keep the clip rule (EP12.mp4 -> EP12); names with other
    letters (Arabic) get a short hash so two Arabic names never collide (slug drops them). Shared with clip ids."""
    return stable_id(Path(path).stem, "EP")


def _inventory(root: Path, refresh: bool = False) -> dict:
    p = Paths(root)
    inv = None if refresh else read_json(p.output / "discovery/input-inventory.json")
    if not inv:
        from .discover import run_discovery
        inv = run_discovery(p)["inventory"]
    return inv


def _episode_state(ep: EpisodePaths) -> str:
    sel = read_json(ep.p("01_analysis/selection.json"), {}) or {}
    picked = sorted({r for h in sel.get("history", []) for r in h.get("picked", [])})
    if picked:
        return f"{len(picked)} reels selected"
    for state, rel in (("planned", "01_analysis/reels-plan-validated.json"),
                       ("transcribed", "02_transcription/transcript.json"),
                       ("prepared", "00_inputs/episode.json")):
        if ep.p(rel).exists():
            return state
    return "new"


def list_episodes(root: Path, refresh: bool = False) -> list[dict]:
    root = Path(root).expanduser().resolve()
    inv = _inventory(root, refresh)
    sheets = {(str(Path(f["rel"]).parent), Path(f["rel"]).stem.lower()): f["rel"] for f in inv["files"]
              if f["role"] == "episode_sheet" and Path(f["rel"]).suffix.lower() in SHEET_EXT}
    out = []
    for f in inv["files"]:
        if f["role"] != "episode":
            continue
        eid = episode_id_for(Path(f["path"]))
        ep = EpisodePaths(root, eid)
        out.append({"episode_id": eid, "file": f["path"], "rel": f["rel"], "size_mb": round(f["size_bytes"] / 1e6, 1),
                    "media": f.get("media", "video"),
                    "sheet": sheets.get((str(Path(f["rel"]).parent), Path(f["rel"]).stem.lower())),
                    "state": _episode_state(ep), "project": str(ep.project)})
    out.sort(key=lambda e: e["rel"])
    ids = [e["episode_id"] for e in out]
    for e in out:                 # EP12.mp4 + EP12.mov share one id: the first file wins, say so (rename one)
        if ids.count(e["episode_id"]) > 1:
            same = [x["rel"] for x in out if x["episode_id"] == e["episode_id"]]
            e["warning"] = (f"duplicate episode id {e['episode_id']}: {', '.join(same)} — rename one; until then "
                            f"--episode {e['episode_id']} means {same[0]}")
    return out


def find_episode(root: Path, episode_id: str) -> dict:
    eps = list_episodes(root)
    hit = next((e for e in eps if e["episode_id"] == episode_id), None)
    if not hit:
        eps = list_episodes(root, refresh=True)
        hit = next((e for e in eps if e["episode_id"] == episode_id), None)
    if not hit:
        raise SystemExit(f"episode {episode_id!r} not found in data/Episodes (known: {[e['episode_id'] for e in eps]})")
    return hit


def episode_file(ep: EpisodePaths) -> Path:
    return Path(find_episode(ep.root, ep.episode_id)["file"])


def load_episode(ep: EpisodePaths) -> dict:
    info = read_json(ep.p("00_inputs/episode.json"))
    if not info:
        raise SystemExit(f"run `reel episode-prep --episode {ep.episode_id}` first")
    return info


# --------------------------------------------------------------------------- prep
def _estimate(dur_min: float) -> dict:
    from . import settings as S
    model = S.load().get("whisper_model") or "large-v3"
    try:
        from .plat import gpu_info
        dev = gpu_info().get("whisper_device", "cpu")
    except Exception:  # noqa: BLE001
        dev = "cpu"
    return {"model": model, "device_now": dev, "gpu": round(dur_min * 0.08, 1),
            "cpu": round(dur_min * (1.2 if model == "large-v3" else 0.5), 1),
            "note": "rough minutes for Whisper; the chunked run resumes from checkpoints if it stops"}


def intake_frames(ep: EpisodePaths, src: Path, duration_s: float, n: int = 6) -> Path:
    """n evenly spaced frames + a labelled 3x2 sheet for the intake-inspector (burned subtitles/logo, layout)."""
    from PIL import Image, ImageDraw
    d = ep.p("00_inputs/intake")
    d.mkdir(parents=True, exist_ok=True)
    tiles = []
    for k in range(n):
        t = duration_s * (k + 0.5) / n
        out = d / f"frame_{k + 1:02d}.jpg"
        run([ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
             "-vf", "scale=640:-2", "-q:v", "3", str(out)], check=False)
        if out.exists():
            tiles.append((out, t))
    w, h = 640, 360
    sheet = Image.new("RGB", (3 * w, 2 * (h + 22)), "black")
    dr = ImageDraw.Draw(sheet)
    for i, (f, t) in enumerate(tiles):
        im = Image.open(f).convert("RGB")
        im.thumbnail((w, h))
        x, y = (i % 3) * w, (i // 3) * (h + 22)
        sheet.paste(im, (x, y + 22))
        dr.text((x + 6, y + 5), f"{i + 1}  {fmt_ts(int(t * 1000), '.')}", fill="yellow")
    out = d / "_intake_sheet.jpg"
    sheet.save(out, quality=85)
    return out


def _grab(src: Path, t: float, out: Path, width: int = 640) -> bool:
    run([ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
         "-vf", f"scale={width}:-2", "-q:v", "3", str(out)], check=False)
    return out.exists()


def supers_sheets(ep: EpisodePaths, src: Path, duration_s: float, scan: dict) -> tuple[Path | None, Path | None]:
    """G65: the 6-frame overview misses name supers (3 s on screen). `_supers_sheet.jpg` = the lower half of every
    frame the overlay scan nominated (`super_NN.jpg` = the whole frame); `_head_sheet.jpg` = a frame every 10 s of the
    first 3 minutes, where name supers live."""
    from PIL import Image, ImageDraw
    from .overlay_scan import dense_times, tc
    d = ep.p("00_inputs/intake")
    d.mkdir(parents=True, exist_ok=True)
    for old in [*d.glob("super_*.jpg"), d / "_supers_sheet.jpg", d / "_head_sheet.jpg"]:
        old.unlink(missing_ok=True)
    tiles = []
    for k, e in enumerate(sorted(scan.get("events", []), key=lambda x: x["t_s"]), 1):
        f = d / f"super_{k:02d}.jpg"
        if _grab(src, e["t_s"], f):
            tiles.append((f, f"{k}  {tc(e['t_s'])}  score {e['score']:.2f}"))
    supers = None
    if tiles:
        w, h, lab = 640, 180, 18
        sheet = Image.new("RGB", (2 * w, ((len(tiles) + 1) // 2) * (h + lab)), "black")
        dr = ImageDraw.Draw(sheet)
        for i, (f, label) in enumerate(tiles):
            im = Image.open(f).convert("RGB")
            hh = round(im.height * w / im.width)
            im = im.resize((w, hh)).crop((0, max(0, hh - h), w, hh))          # the lower half
            x, y = (i % 2) * w, (i // 2) * (h + lab)
            sheet.paste(im, (x, y + lab))
            dr.text((x + 6, y + 4), label, fill="yellow")
        supers = d / "_supers_sheet.jpg"
        sheet.save(supers, quality=85)
    heads = []
    for t in dense_times(duration_s):
        f = d / "_head_tmp.jpg"
        if _grab(src, t, f, width=320):
            heads.append((Image.open(f).convert("RGB").copy(), t))
    (d / "_head_tmp.jpg").unlink(missing_ok=True)
    head = None
    if heads:
        w, h, lab, cols = 320, 180, 16, 6
        sheet = Image.new("RGB", (cols * w, ((len(heads) + cols - 1) // cols) * (h + lab)), "black")
        dr = ImageDraw.Draw(sheet)
        for i, (im, t) in enumerate(heads):
            im.thumbnail((w, h))
            x, y = (i % cols) * w, (i // cols) * (h + lab)
            sheet.paste(im, (x, y + lab))
            dr.text((x + 4, y + 3), tc(t), fill="yellow")
        head = d / "_head_sheet.jpg"
        sheet.save(head, quality=85)
    return supers, head


def _scan_budget() -> float:
    import os
    try:
        return float(os.environ.get("WHYNOT_OVERLAY_SCAN_BUDGET_S", ""))
    except ValueError:
        from .overlay_scan import BUDGET_S
        return BUDGET_S


def prep(ep: EpisodePaths) -> dict:
    from .media import probe
    hit = find_episode(ep.root, ep.episode_id)
    src = Path(hit["file"])
    ep.ensure_project()
    pr = probe(src)
    v = pr.get("video") or {}
    dur_s = pr.get("duration_s") or 0
    sheet, sheet_text = {}, ""
    if hit.get("sheet"):
        sheet_text = (ep.root / hit["sheet"]).read_text(encoding="utf-8", errors="replace")
        sheet = {k: val for k, val in parse_sheet(sheet_text).items() if k != "_text"}
    warnings = []
    media = hit.get("media", "video")          # an audio podcast (audio file): no picture, motion mode only
    if pr["errors"] or (media == "video" and not v):
        warnings.append(f"unreadable {media}: " + "; ".join(pr["errors"]))
    if not pr["audio"]:
        warnings.append("no audio stream: nothing to transcribe")
    if v and v.get("display_width") and v["display_height"] and abs(v["display_width"] / v["display_height"] - 16 / 9) > 0.05:
        warnings.append(f"aspect {v.get('aspect')} is not 16:9 (podcast mode expects a finished 16:9 episode)")
    if not hit.get("sheet"):
        warnings.append(f"no episode sheet: add data/Episodes/{src.stem}.md (guest, links, sponsor, avoid) — names "
                        "and links in the publish package come only from it")
    if media == "audio":
        warnings.append("audio-only episode: reels from it are motion videos (`reels-select --as motion`)")
    sheet_img = intake_frames(ep, src, dur_s) if v and dur_s else None
    scan, supers_img, head_img = None, None, None
    if v and dur_s and _scan_budget() > 0:         # G65: name supers are 3 s long; scan the whole episode for them
        from . import overlay_scan
        scan = overlay_scan.scan_video(src, dur_s, budget_s=_scan_budget())
        supers_img, head_img = supers_sheets(ep, src, dur_s, scan)
        if scan["events"]:
            warnings.append("possible name supers / lower thirds at " + ", ".join(
                e["tc"] for e in sorted(scan["events"], key=lambda x: x["t_s"])) + ": VIEW 00_inputs/intake/_supers_sheet.jpg "
                "(the bar-shaped overlays the scan found) and _head_sheet.jpg (first 3 minutes) before setting lower_thirds")
        if not scan["complete"]:
            warnings.append(f"overlay scan stopped at {overlay_scan.tc(scan['scanned_s'])} of "
                            f"{overlay_scan.tc(scan['duration_s'])} (time budget {scan['budget_s']:.0f} s): later supers are "
                            "not checked; look at the overview sheet and ask the editor")
    est = _estimate(dur_s / 60)
    info = {"episode_id": ep.episode_id, "file": str(src), "rel": hit["rel"], "media": media, "fingerprint": sha1_head(src),
            "duration_ms": int(round(dur_s * 1000)), "video": {k: v.get(k) for k in ("display_width", "display_height",
            "fps", "codec", "aspect")}, "audio": pr["audio"], "sheet_rel": hit.get("sheet"), "sheet": sheet,
            "sheet_text": sheet_text, "intake_sheet": str(sheet_img) if sheet_img else None,
            "overlay_scan": scan, "lower_thirds_hint": bool(scan and scan["events"]),
            "supers_sheet": str(supers_img) if supers_img else None, "head_sheet": str(head_img) if head_img else None,
            "estimate_minutes": est, "warnings": warnings, "created": now_iso()}
    write_json(ep.p("00_inputs/episode.json"), info)
    return {"episode_id": ep.episode_id, "duration_ms": info["duration_ms"], "video": info["video"], "media": media,
            "sheet": hit.get("sheet"), "intake_sheet": info["intake_sheet"], "supers_sheet": info["supers_sheet"],
            "head_sheet": info["head_sheet"], "estimate_minutes": est,
            "warnings": warnings,
            "next": ("`reel episode-transcribe` (audio-only: no intake check)" if media == "audio" else
                     "intake-inspector views the intake sheet (burned subtitles/logo, layout), _supers_sheet.jpg and "
                     "_head_sheet.jpg (name supers) ∥ `reel episode-transcribe`")}


# --------------------------------------------------------------------------- resumable status
def episode_next(ep: EpisodePaths) -> dict:
    """What the episode needs next (resumable, like `reel next` for a clip), stale steps, and its reels' status."""
    from .common import Paths, load_status

    def t(rel):
        f = ep.p(rel)
        return f.stat().st_mtime if f.exists() else None
    steps = [
        ("episode-prep", "00_inputs/episode.json"),
        ("episode-transcribe", "02_transcription/transcript.json"),
        ("AUTHOR 01_analysis/topics.json", "01_analysis/topics.json"),
        ("AUTHOR 01_analysis/speakers.json", "01_analysis/speakers.json"),
        ("AUTHOR 01_analysis/reels-plan.json", "01_analysis/reels-plan.json"),
        ("reels-plan", "01_analysis/reels-plan-validated.json"),
        ("reels-preview", "03_candidates/_sheet.jpg"),
        ("SELECT reels (Gate 0: the editor picks; reels-select --by editor)", "01_analysis/selection.json"),
        ("AUTHOR publish/publish.json", "publish/publish.json"),
        ("publish-check", "publish/publish-validation.json"),
        ("publish-thumbnail --candidates", "publish/thumbnail/candidates.json"),
    ]
    todo = [name for name, rel in steps if t(rel) is None]
    stale = []
    deps = [("reels-plan", "01_analysis/reels-plan-validated.json",
             ["01_analysis/reels-plan.json", "02_transcription/words.json"]),
            ("reels-preview", "03_candidates/_sheet.jpg", ["01_analysis/reels-plan-validated.json"]),
            ("publish-check", "publish/publish-validation.json", ["publish/publish.json"])]
    for name, rel, ups in deps:
        tf = t(rel)
        if tf is None:
            continue
        newer = [Path(u).name for u in ups if t(u) and t(u) > tf + 1]
        if name == "publish-check":
            newer += [f.name for f in ep.p("publish/reels").glob("*.json") if f.stat().st_mtime > tf + 1]
        if newer:
            stale.append(f"{name} (older than {', '.join(newer)})")
    pv = read_json(ep.p("publish/publish-validation.json"), {}) or {}
    if pv and not pv.get("ok") and "publish-check" not in todo:
        stale.append("publish-check (last run had errors)")
    sel = read_json(ep.p("01_analysis/selection.json"), {}) or {}
    # a reels plan re-validated after a pick (its fingerprint changed) may have moved or dropped that reel's window
    fp_now = (read_json(ep.p("01_analysis/reels-plan-validated.json"), {}) or {}).get("fingerprint")
    picked_with = {r: h.get("plan_fingerprint") for h in sel.get("history", []) for r in h.get("picked", [])}
    older = sorted(r for r, fp in picked_with.items() if fp and fp_now and fp != fp_now)
    if older:
        stale.append(f"reels-select (the reels plan was re-validated after {', '.join(f'{ep.episode_id}_{r}' for r in older)} "
                     f"was picked: the editor confirms with `reels-select --pick {','.join(older)} --by editor`, adding "
                     "--force if a window moved; after transcript corrections run `reels-select --resync` first)")
    reels = {}
    for kind, rid in sorted({(h.get("as", "video"), r) for h in sel.get("history", []) for r in h.get("picked", [])}):
        rp = Paths(ep.root, f"{ep.episode_id}_{rid}_MO" if kind == "motion" else f"{ep.episode_id}_{rid}")
        reels[rp.video_id] = load_status(rp).get("status") if rp.project.exists() else "not created"
    names = [s.split(" (")[0] for s in stale]
    remaining = stale + [n for n in todo if n not in names]
    return {"episode_id": ep.episode_id, "state": _episode_state(ep), "next": remaining[0] if remaining else "done",
            "remaining": remaining, "stale": stale, "reels": reels,
            "reels_hint": "each reel resumes with `reel next --video-id <reel id>`" if reels else None}


# --------------------------------------------------------------------------- chunked transcription
def plan_chunks(db: list, hop_ms: int, total_ms: int, chunk_ms: int, search_ms: int = 20000) -> list[tuple[int, int]]:
    """Contiguous chunks of about chunk_ms covering [0, total_ms]. Each boundary sits in the middle of the quietest run
    of windows within ±search_ms of its target, so a chunk never starts or ends inside a word. A short tail
    (< 30 % of a chunk) is merged into the last chunk."""
    if total_ms <= chunk_ms * 1.3 or not db:
        return [(0, total_ms)]
    search_ms = min(search_ms, chunk_ms // 4)        # a boundary never wanders more than a quarter chunk
    bounds, last = [], 0
    while total_ms - (last + chunk_ms) >= 0.3 * chunk_ms:
        target = last + chunk_ms
        lo, hi = max(0, (target - search_ms) // hop_ms), min(len(db) - 1, (target + search_ms) // hop_ms)
        k = min(range(lo, hi + 1), key=lambda i: db[i])
        floor = db[k] + 0.5
        a = b = k
        while a - 1 >= lo and db[a - 1] <= floor:
            a -= 1
        while b + 1 <= hi and db[b + 1] <= floor:
            b += 1
        cut = ((a + b + 1) * hop_ms) // 2
        if cut <= last:
            cut = target
        bounds.append(cut)
        last = cut
    edges = [0] + bounds + [total_ms]
    return list(zip(edges, edges[1:]))


def stitch(chunks: list[dict]) -> tuple[list, list]:
    """Chunk results (absolute times) -> one transcript with fresh word and segment ids."""
    segs, words = [], []
    for ch in sorted(chunks, key=lambda c: c["start_ms"]):
        by_id = {w["id"]: w for w in ch["words"]}
        for s in ch["segments"]:
            sid = len(segs) + 1
            ids = []
            for wid in s.get("words", []):
                w = by_id.get(wid)
                if w is None:
                    continue
                nw = dict(w, id=len(words) + 1, segment_id=sid)
                words.append(nw)
                ids.append(nw["id"])
            segs.append(dict(s, id=sid, words=ids))
    return segs, words


def _energy_db(audio, sr: int = 16000, hop_ms: int = 50) -> list:
    import numpy as np
    hop = sr * hop_ms // 1000
    n = len(audio) // hop
    if n == 0:
        return []
    x = audio[:n * hop].reshape(n, hop)
    return (20 * np.log10(np.sqrt((x ** 2).mean(axis=1)) + 1e-9)).round(2).tolist()


def _decode(model, audio, language, prompt, vad: bool) -> dict:
    segments, info = model.transcribe(audio, language=language, task="transcribe", beam_size=5, word_timestamps=True,
                                      vad_filter=vad, condition_on_previous_text=False, initial_prompt=prompt,
                                      temperature=[0.0, 0.2, 0.4])
    segs, words = [], []
    for s in segments:
        seg = {"id": len(segs) + 1, "start_ms": int(round(s.start * 1000)), "end_ms": int(round(s.end * 1000)),
               "text": s.text.strip(), "avg_logprob": round(s.avg_logprob, 3), "no_speech_prob": round(s.no_speech_prob, 3),
               "compression_ratio": round(s.compression_ratio, 3), "words": []}
        for w in (s.words or []):
            wd = {"id": len(words) + 1, "segment_id": seg["id"], "word": w.word.strip(),
                  "start_ms": int(round(w.start * 1000)), "end_ms": int(round(w.end * 1000)),
                  "probability": round(w.probability, 3)}
            words.append(wd)
            seg["words"].append(wd["id"])
        segs.append(seg)
    return {"segments": segs, "words": words, "language": info.language,
            "language_probability": round(info.language_probability, 3)}


def whisper_runner(model_size: str, vad: bool, ep: EpisodePaths | None = None):
    """run(audio, start_ms, language, prompt) -> {segments, words, language, language_probability} (chunk-relative
    times). The model loads once, on the GPU when usable; a GPU failure at the first inference retries on the CPU."""
    from .common import ENV_DIR, log
    from .transcribe import whisper_model
    state: dict = {}

    def run(audio, start_ms, language, prompt):
        if "model" not in state:
            state["model"], state["device"], state["compute_type"] = whisper_model(model_size)
            log(ep, f"Whisper {model_size} on {state['device']} ({state['compute_type']}), VAD {'on' if vad else 'off'}")
        try:
            return _decode(state["model"], audio, language, prompt, vad)
        except Exception as e:  # noqa: BLE001  (GPU libraries can fail only at the first inference)
            if state["device"] != "cuda":
                raise
            log(ep, f"GPU transcription failed ({type(e).__name__}: {e}); retrying on CPU")
            from faster_whisper import WhisperModel
            state["model"] = WhisperModel(model_size, device="cpu", compute_type="int8", download_root=str(ENV_DIR / "models"))
            state["device"], state["compute_type"] = "cpu", "int8"
            return _decode(state["model"], audio, language, prompt, vad)
    run.state = state
    return run


def transcribe_episode(ep: EpisodePaths, model_size: str = "large-v3", language: str | None = None, force: bool = False,
                       run_chunk=None, chunk_ms: int | None = None) -> dict:
    """Whole-episode transcript in resumable chunks (02_transcription/chunks/chunk_NNN.json). Same output files as a
    clip transcript. The language is detected on the first chunk and reused, so a code-switching guest does not flip
    the decoder language mid-episode."""
    import time
    from .common import log
    from .transcribe import extract_audio, finalize, whisper_audio
    src = episode_file(ep)
    ep.ensure_project()
    out, cdir = ep.p("02_transcription"), ep.p("02_transcription/chunks")
    cdir.mkdir(parents=True, exist_ok=True)
    wav = out / "dialogue_16k_mono.wav"
    if force:
        for f in cdir.glob("chunk_*.json"):
            f.unlink()
        (cdir / "plan.json").unlink(missing_ok=True)
    fp = sha1_head(src)
    plan = read_json(cdir / "plan.json")
    if force or not wav.exists() or not plan or plan.get("fingerprint") != fp:
        extract_audio(src, wav)
    audio = whisper_audio(wav)
    total_ms = int(len(audio) * 1000 / 16000)
    cfg = podcast_cfg()
    chunk_ms = int(chunk_ms or cfg.get("chunk_minutes", 10) * 60000)
    if not plan or plan.get("fingerprint") != fp or plan.get("chunk_ms") != chunk_ms or plan.get("total_ms") != total_ms \
            or (language and plan.get("language") != language):   # an explicit new language re-decodes everything
        for f in cdir.glob("chunk_*.json"):
            f.unlink()
        plan = {"fingerprint": fp, "chunk_ms": chunk_ms, "total_ms": total_ms, "language": language,
                "chunks": plan_chunks(_energy_db(audio), 50, total_ms, chunk_ms), "created": now_iso()}
        write_json(cdir / "plan.json", plan)
    vad = bool(cfg.get("episode_vad", True))
    prompt = load_config("transcription.json").get("initial_prompt")
    runner = run_chunk or whisper_runner(model_size, vad, ep)
    lang, prob, results, ran, t0 = language, None, [], 0, time.time()
    for i, (a, b) in enumerate(plan["chunks"]):
        f = cdir / f"chunk_{i:03d}.json"
        rec = read_json(f)
        if rec and rec.get("start_ms") == a and rec.get("end_ms") == b:
            results.append(rec)
            lang = lang or rec.get("language")
            prob = prob if prob is not None else rec.get("language_probability")
            continue
        r = runner(audio[a * 16:b * 16], a, lang, prompt)
        lang = lang or r.get("language")
        prob = prob if prob is not None else r.get("language_probability")
        rec = {"index": i, "start_ms": a, "end_ms": b, "language": r.get("language"),
               "language_probability": r.get("language_probability"),
               "segments": [dict(s, start_ms=s["start_ms"] + a, end_ms=s["end_ms"] + a) for s in r["segments"]],
               "words": [dict(w, start_ms=w["start_ms"] + a, end_ms=w["end_ms"] + a) for w in r["words"]]}
        write_json(f, rec)
        results.append(rec)
        ran += 1
        done = sum(1 for _ in results)
        el = time.time() - t0
        log(ep, f"episode {ep.episode_id}: chunk {i + 1}/{len(plan['chunks'])} ({fmt_ts(a, '.')}–{fmt_ts(b, '.')}) "
                f"{len(rec['words'])} words; elapsed {el:.0f}s"
                + (f", ETA {el / ran * (len(plan['chunks']) - done):.0f}s" if ran else ""))
    segs, words = stitch(results)
    st = getattr(runner, "state", {}) or {}
    meta = {"source_video": str(src), "audio": str(wav), "backend": "faster-whisper" if run_chunk is None else "injected",
            "model": model_size, "compute_type": st.get("compute_type"), "device": st.get("device"),
            "language": lang, "language_probability": prob if prob is not None else 1.0, "duration_ms": total_ms,
            "initial_prompt": prompt, "elapsed_s": round(time.time() - t0, 1), "translated": False,
            "chunks": len(plan["chunks"]), "vad": vad, "episode_id": ep.episode_id}
    res = finalize(ep, meta, segs, words)
    for name in ("transcript", "words"):   # a NEW machine transcript replaces the old machine originals
        (out / f"{name}.machine.json").write_bytes((out / f"{name}.json").read_bytes())
    return dict(res, chunks=len(plan["chunks"]), chunks_run=ran)
