"""Podcast mode: an EPISODE project (output/episodes/<EP>/) for a finished episode in data/Episodes/, its episode sheet,
intake frames for the intake-inspector, and chunked, resumable Whisper transcription of the whole episode.

An episode is never edited whole: the episode-analyst plans reels from it, the editor picks them (Gate 0) and each
picked reel becomes an ordinary clip project whose source is a window of the episode file (see source.py, reels.py).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

from .common import Paths, ffmpeg_exe, fmt_ts, load_config, now_iso, read_json, run, sha1_head, slug, write_json

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
        body = m.group(2)
    out["_notes"] = body.strip()
    out["_text"] = text
    return out


# --------------------------------------------------------------------------- ids, listing
def episode_id_for(path: Path) -> str:
    """Stable project id from the file name. ASCII names keep the clip rule (EP12.mp4 -> EP12); names with other
    letters (Arabic) get a short hash so two Arabic names never collide (slug drops them)."""
    stem = unicodedata.normalize("NFC", Path(path).stem)
    s = slug(stem)
    if not re.search(r"[^\x00-\x7F]", stem):
        return s
    h = hashlib.sha1(stem.encode("utf-8")).hexdigest()[:6].upper()
    return f"EP_{s}_{h}" if s not in ("", "VIDEO") else f"EP_{h}"


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
                    "sheet": sheets.get((str(Path(f["rel"]).parent), Path(f["rel"]).stem.lower())),
                    "state": _episode_state(ep), "project": str(ep.project)})
    return sorted(out, key=lambda e: e["rel"])


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
    if pr["errors"] or not v:
        warnings.append("unreadable video: " + "; ".join(pr["errors"]))
    if not pr["audio"]:
        warnings.append("no audio stream: nothing to transcribe")
    if v and v.get("display_width") and v["display_height"] and abs(v["display_width"] / v["display_height"] - 16 / 9) > 0.05:
        warnings.append(f"aspect {v.get('aspect')} is not 16:9 (podcast mode expects a finished 16:9 episode)")
    if not hit.get("sheet"):
        warnings.append(f"no episode sheet: add data/Episodes/{src.stem}.md (guest, links, sponsor, avoid) — names "
                        "and links in the publish package come only from it")
    sheet_img = intake_frames(ep, src, dur_s) if v and dur_s else None
    est = _estimate(dur_s / 60)
    info = {"episode_id": ep.episode_id, "file": str(src), "rel": hit["rel"], "fingerprint": sha1_head(src),
            "duration_ms": int(round(dur_s * 1000)), "video": {k: v.get(k) for k in ("display_width", "display_height",
            "fps", "codec", "aspect")}, "audio": pr["audio"], "sheet_rel": hit.get("sheet"), "sheet": sheet,
            "sheet_text": sheet_text, "intake_sheet": str(sheet_img) if sheet_img else None,
            "estimate_minutes": est, "warnings": warnings, "created": now_iso()}
    write_json(ep.p("00_inputs/episode.json"), info)
    return {"episode_id": ep.episode_id, "duration_ms": info["duration_ms"], "video": info["video"],
            "sheet": hit.get("sheet"), "intake_sheet": info["intake_sheet"], "estimate_minutes": est,
            "warnings": warnings,
            "next": "intake-inspector views the intake sheet (burned subtitles/logo, layout) ∥ `reel episode-transcribe`"}
