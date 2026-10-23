"""Podcast mode: an EPISODE project (output/episodes/<EP>/) for a finished episode in data/Episodes/, its episode sheet,
intake frames for the intake-inspector, and chunked, resumable Whisper transcription of the whole episode.

An episode is never edited whole: the episode-analyst plans reels from it, the editor picks them (Gate 0) and each
picked reel becomes an ordinary clip project whose source is a window of the episode file (see source.py, reels.py).
"""
from __future__ import annotations

import re
from pathlib import Path

from .common import Paths, check_project_id, fmt_ts, load_config, now_iso, read_json, sha1_head, stable_id, write_json

EPISODE_SUBDIRS = ["00_inputs/intake", "01_analysis", "02_transcription/chunks", "03_candidates", "publish/reels",
                   "publish/thumbnail/candidates", "08_quality_control", "logs"]
SHEET_EXT = (".md", ".markdown", ".txt")


class EpisodePaths(Paths):
    """Same helpers as a clip project (`p()`, `ensure_project()`), rooted at output/episodes/<EP>/."""

    def __init__(self, root: Path, episode_id: str):
        check_project_id(episode_id, "episode id", strict=True)       # Gate 2 B4: never a path out of output/episodes
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
    from PIL import Image
    from .media_util import contact_sheet
    d = ep.p("00_inputs/intake")
    d.mkdir(parents=True, exist_ok=True)
    tiles = []
    for k in range(n):
        t = duration_s * (k + 0.5) / n
        if _grab(src, t, d / f"frame_{k + 1:02d}.jpg"):
            tiles.append((d / f"frame_{k + 1:02d}.jpg", f"{len(tiles) + 1}  {fmt_ts(int(t * 1000), '.')}"))
    out = d / "_intake_sheet.jpg"
    if not contact_sheet(tiles, out, cols=3, tile_w=640, tile_h=360, label_h=22, label_xy=(6, 5), fit="contain"):
        Image.new("RGB", (3 * 640, 2 * 382), "black").save(out, quality=85)   # no frame readable: the old empty 3x2
    return out


def _grab(src: Path, t: float, out: Path, width: int = 640) -> bool:
    from .media_util import grab_frame_file
    return grab_frame_file(src, t, out, vf=f"scale={width}:-2", quality=3) is not None


def supers_sheets(ep: EpisodePaths, src: Path, duration_s: float, scan: dict) -> tuple[Path | None, Path | None]:
    """G65: the 6-frame overview misses name supers (3 s on screen). `_supers_sheet.jpg` = the lower half of every
    frame the overlay scan nominated (`super_NN.jpg` = the whole frame); `_head_sheet.jpg` = a frame every 10 s of the
    first 3 minutes, where name supers live."""
    from .media_util import contact_sheet, open_rgb
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
    # the lower half of each nominated frame (name supers live there)
    supers = contact_sheet(tiles, d / "_supers_sheet.jpg", cols=2, tile_w=640, tile_h=180, label_h=18,
                           label_xy=(6, 4), fit="bottom")
    heads = []
    for t in dense_times(duration_s):
        f = d / "_head_tmp.jpg"
        if _grab(src, t, f, width=320):
            heads.append((open_rgb(f), tc(t)))
    (d / "_head_tmp.jpg").unlink(missing_ok=True)
    head = contact_sheet(heads, d / "_head_sheet.jpg", cols=6, tile_w=320, tile_h=180, label_h=16, label_xy=(4, 3),
                         fit="contain")
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
        from .episode_sheet import name_problems
        bad = name_problems(sheet)              # review c963132 P2-1: a list, number ... is never a name on screen
        if bad:
            from .errors import Guidance
            raise Guidance("; ".join(bad), f"Fix {hit['sheet']}, then run `reel episode-prep --episode "
                                           f"{ep.episode_id}` again (nothing was written)", where=hit["sheet"])
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
        from .gpu_lock import site_slot
        with site_slot("thumbs", log_to=ep) as lane:          # T4.10: the verb takes the slot once; the scan gets the lane
            scan = overlay_scan.scan_video(src, dur_s, budget_s=_scan_budget(), lane=lane)
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
        ("SELECT reels (the editor picks the reels; reels-select --by editor)", "01_analysis/selection.json"),
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
    from .people import profile_notice
    notices = [n for n in (profile_notice(ep.root),) if n]
    return {"episode_id": ep.episode_id, "state": _episode_state(ep), "next": remaining[0] if remaining else "done",
            "remaining": remaining, "stale": stale, "reels": reels,
            "reels_hint": "each reel resumes with `reel next --video-id <reel id>`" if reels else None,
            "notices": notices}


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


def whisper_runner(model_size: str, vad: bool, ep: EpisodePaths | None = None, backend: str | None = None,
                   batch_size: int | None = None, device: str | None = None):
    """run(audio, start_ms, language, prompt) -> {segments, words, language, language_probability} (chunk-relative
    times), from the configured backend (lib/whisper_backends.py: faster-whisper, batched on CUDA; mlx-whisper on
    Apple Silicon). The model loads once, at the first chunk; a GPU failure at the first inference retries on the CPU.
    `device="cpu"`: the Whisper slot was not had (T4.10, accel.whisper_device)."""
    from . import whisper_backends as WB
    return WB.make_runner(model_size, vad, ep, backend=backend, batch_size=batch_size, device=device)


def _decoder_matches(rec: dict, model: str, prompt, backend, decoder: dict | None = None) -> bool:
    """MI-12: a checkpoint is reused only when the same decoder made it: model, prompt, backend, and (T2.12 review)
    device, batched or sequential (batch size) and VAD. A changed whisper_model, vocabulary hint, backend or
    `batch_size: 0` after a partial batched run (or a 2.x / early-3.0 checkpoint without these fields) redoes the
    chunk, so one transcript never mixes two decoders silently. A chunk decoded after a GPU fallback (smaller batch
    or CPU) records `fallback_from` = the decoder the run wanted: it is kept when that decoder is wanted again (the
    fallback is listed in the transcript meta); `--force` redoes it."""
    if rec.get("model") != model or rec.get("prompt") != prompt or rec.get("backend") != backend:
        return False
    if rec.get("decoder") == decoder:
        return True
    return rec.get("fallback_from") is not None and rec.get("fallback_from") == decoder


def decoders_used(results: list) -> list:
    """The distinct decoders of a run's chunks, e.g. ["cuda/batch4/vad"], with "(fallback)" marks."""
    out = []
    for r in results:
        d = r.get("decoder") or {}
        if not d:
            continue
        name = (f"{d.get('device')}/{'batch' + str(d['batch_size']) if d.get('batch_size') else 'sequential'}/"
                f"{'vad' if d.get('vad') else 'no-vad'}" + (" (fallback)" if r.get("fallback_from") else ""))
        if name not in out:
            out.append(name)
    return out


def run_chunks(paths, cdir: Path, audio, plan: dict, runner, *, model: str, prompt, language: str | None,
               label: str) -> dict:
    """The chunk runner shared by episodes and long clips: decode each planned chunk not already checkpointed in
    cdir/chunk_NNN.json (absolute times), checkpoint it, log progress and an ETA. The language is detected on the
    first chunk and reused, so a code-switching guest does not flip the decoder language mid-run."""
    import time
    from .common import log
    backend = getattr(runner, "backend", None) or "injected"
    sig = getattr(runner, "signature", None)
    want = sig() if sig else None          # the decoder this run starts with (before any GPU fallback)
    st = getattr(runner, "state", None) or {}
    lang, prob, results, ran, t0 = language, None, [], 0, time.time()
    n = len(plan["chunks"])
    for i, (a, b) in enumerate(plan["chunks"]):
        f = cdir / f"chunk_{i:03d}.json"
        rec = read_json(f)
        if rec and rec.get("start_ms") == a and rec.get("end_ms") == b and _decoder_matches(rec, model, prompt, backend, want):
            results.append(rec)
            lang = lang or rec.get("language")
            prob = prob if prob is not None else rec.get("language_probability")
            continue
        seen = len(st.get("redecoded") or [])
        r = runner(audio[a * 16:b * 16], a, lang, prompt)
        lang = lang or r.get("language")
        prob = prob if prob is not None else r.get("language_probability")
        rec = {"index": i, "start_ms": a, "end_ms": b, "language": r.get("language"),
               "language_probability": r.get("language_probability"), "model": model, "prompt": prompt,
               "backend": backend, "decoder": sig() if sig else None,
               "redecoded": [dict(x, start_ms=x["start_ms"] + a, end_ms=x["end_ms"] + a)
                             for x in (st.get("redecoded") or [])[seen:]],
               "segments": [dict(s, start_ms=s["start_ms"] + a, end_ms=s["end_ms"] + a) for s in r["segments"]],
               "words": [dict(w, start_ms=w["start_ms"] + a, end_ms=w["end_ms"] + a) for w in r["words"]]}
        if st.get("fallback_from"):
            rec["fallback_from"] = st["fallback_from"]
        write_json(f, rec)
        results.append(rec)
        ran += 1
        el = time.time() - t0
        log(paths, f"{label}: chunk {i + 1}/{n} ({fmt_ts(a, '.')}–{fmt_ts(b, '.')}) {len(rec['words'])} words; "
                   f"elapsed {el:.0f}s, ETA {el / ran * (n - len(results)):.0f}s")
    used = decoders_used(results)
    if len(used) > 1:
        log(paths, f"{label}: the chunks were decoded by {len(used)} decoders ({', '.join(used)}); "
                   "--force transcribes every chunk again with one")
    return {"results": results, "ran": ran, "language": lang, "language_probability": prob,
            "elapsed_s": round(time.time() - t0, 1), "decoders": used,
            "redecoded": [x for r in results for x in (r.get("redecoded") or [])]}


def chunk_plan(cdir: Path, audio, fingerprint: str, chunk_ms: int, language: str | None, force: bool = False) -> dict:
    """cdir/plan.json: chunk bounds in the quietest moments (plan_chunks). A new source, chunk size, length or an
    explicit new language replans and drops every checkpoint; --force drops them too."""
    cdir.mkdir(parents=True, exist_ok=True)
    total_ms = int(len(audio) * 1000 / 16000)
    plan = None if force else read_json(cdir / "plan.json")
    if force or not plan or plan.get("fingerprint") != fingerprint or plan.get("chunk_ms") != chunk_ms \
            or plan.get("total_ms") != total_ms or (language and plan.get("language") != language):
        for f in cdir.glob("chunk_*.json"):
            f.unlink()
        plan = {"fingerprint": fingerprint, "chunk_ms": chunk_ms, "total_ms": total_ms, "language": language,
                "chunks": plan_chunks(_energy_db(audio), 50, total_ms, chunk_ms), "created": now_iso()}
        write_json(cdir / "plan.json", plan)
    return plan


def transcribe_episode(ep: EpisodePaths, model_size: str = "large-v3", language: str | None = None, force: bool = False,
                       run_chunk=None, chunk_ms: int | None = None, backend: str | None = None,
                       batch_size: int | None = None) -> dict:
    """Whole-episode transcript in resumable chunks (02_transcription/chunks/chunk_NNN.json). Same output files as a
    clip transcript. Each checkpoint records the model, prompt and backend that decoded it (MI-12)."""
    from .transcribe import extract_audio, finalize, whisper_audio
    from .whisper_backends import LABEL
    src = episode_file(ep)
    ep.ensure_project()
    out, cdir = ep.p("02_transcription"), ep.p("02_transcription/chunks")
    cdir.mkdir(parents=True, exist_ok=True)
    wav = out / "dialogue_16k_mono.wav"
    fp = sha1_head(src)
    plan = read_json(cdir / "plan.json")
    if force or not wav.exists() or not plan or plan.get("fingerprint") != fp:
        extract_audio(src, wav)
    audio = whisper_audio(wav)
    cfg = podcast_cfg()
    chunk_ms = int(chunk_ms or cfg.get("chunk_minutes", 10) * 60000)
    plan = chunk_plan(cdir, audio, fp, chunk_ms, language, force)
    vad = bool(cfg.get("episode_vad", True))
    prompt = load_config("transcription.json").get("initial_prompt")
    from . import accel, gpu_lock
    # T4.10: the longest GPU job of all holds the Whisper slot for the model load and every chunk (waits up to 600 s
    # for another GPU job or a Premiere / AE export, then the CPU: slower, same words)
    with gpu_lock.whisper_slot("transcribe", backend=backend, log_to=ep) as lane:
        runner = run_chunk or whisper_runner(model_size, vad, ep, backend=backend, batch_size=batch_size,
                                             device=accel.whisper_device(lane))
        try:
            done = run_chunks(ep, cdir, audio, plan, runner, model=model_size, prompt=prompt, language=language,
                              label=f"episode {ep.episode_id}")
        finally:                        # T4.11: Whisper leaves memory before the slot does (success, error, Ctrl+C)
            rel = getattr(runner, "release", None)
            if callable(rel):
                rel()
    segs, words = stitch(done["results"])
    st = getattr(runner, "state", {}) or {}
    prob = done["language_probability"]
    meta = {"source_video": str(src), "audio": str(wav),
            "backend": LABEL.get(getattr(runner, "backend", None), "injected"),
            "model": model_size, "compute_type": st.get("compute_type"), "device": st.get("device"),
            "batch_size": st.get("batch_size"), "cpu_threads": st.get("cpu_threads"),
            "language": done["language"], "language_probability": prob if prob is not None else 1.0,
            "duration_ms": plan["total_ms"], "initial_prompt": prompt, "elapsed_s": done["elapsed_s"],
            "translated": False, "chunks": len(plan["chunks"]), "vad": st.get("vad", vad), "episode_id": ep.episode_id,
            "decoders": done["decoders"], "mixed_decoders": len(done["decoders"]) > 1,
            "redecoded_segments": done["redecoded"]}
    res = finalize(ep, meta, segs, words)
    for name in ("transcript", "words"):   # a NEW machine transcript replaces the old machine originals
        (out / f"{name}.machine.json").write_bytes((out / f"{name}.json").read_bytes())
    return dict(res, chunks=len(plan["chunks"]), chunks_run=done["ran"])
