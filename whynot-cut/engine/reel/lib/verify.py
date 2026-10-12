"""Visual verification: the evidence step between "the tool said it worked" and "it works".

Exit codes and *-result.json files prove a file exists, not that it looks right. In the first
production run every real defect (broken Arabic glyphs, reversed RTL order, a face cropped out
of a photo card, a logo with a white box, a graphic over the speaker's neck) passed all automated checks
and was caught only by looking. So:

  reel verify            -> builds 08_quality_control/verify/verify_sheet.jpg + verify-checklist.md
  (Claude views the sheet, compares every tile with the checklist)
  reel verify --record --verdict pass|fail --notes "..."   -> visual-verification.json

QC requires a PASS verdict newer than the newest AE render / PSD.
"""
from __future__ import annotations

import re
from pathlib import Path

from .common import seq_fps, still_category, Paths, ffmpeg_exe, frame_to_tc, now_iso, read_json, run, write_json, write_text

SAFE = {"x0": 60, "x1": 1020, "y0": 150, "y1": 1720}
FULLSCREEN = {"broll_card", "broll_video", "logo_outro", "flash_transition"}
W, H = 1080, 1920


def _rendered_media(paths: Paths) -> list[Path]:
    out = [m for m in paths.p("04_after_effects/compositions").glob("*.mov") if not m.name.startswith("._")]
    out += [m for m in paths.p("05_photoshop/layered-assets").glob("*.psd") if not m.name.startswith("._")]
    out += [m for m in paths.p("07_premiere/project").glob("*.prproj") if not m.name.startswith("._") and "_prev_" not in m.name]
    return out


def prproj_build_time(paths: Paths, prproj: Path) -> float | None:
    """When the PIPELINE last saved this .prproj (from ppro-build-result.json), or None if it didn't build it."""
    import datetime as _dt
    pb = read_json(paths.p("07_premiere/ppro-build-result.json"), {})
    if not pb.get("project") or Path(pb["project"]).resolve() != prproj.resolve():
        return None
    if pb.get("prproj_mtime"):
        return float(pb["prproj_mtime"])
    try:
        return _dt.datetime.fromisoformat(pb["at"]).timestamp()
    except Exception:
        return None


def _media_time(paths: Paths, m: Path) -> float:
    if m.suffix == ".prproj":
        bt = prproj_build_time(paths, m)
        if bt is not None:          # the editor's own later saves don't make our verification stale
            return min(bt, m.stat().st_mtime)
    return m.stat().st_mtime


def newest_render_mtime(paths: Paths) -> float:
    return max([_media_time(paths, m) for m in _rendered_media(paths)] or [0.0])


# What Premiere rewrites on any save, edit or not (measured on 26.5 by saving an untouched project): the save stamp, ID
# counters, empty ID nodes and the playhead. A signature without them changes only when the timeline does.
_VOLATILE = [r"<MZ\.BuildVersion\.Modified>[^<]*</MZ\.BuildVersion\.Modified>", r"<NextID>\d+</NextID>",
             r"<MasterClipChangeVersion>\d+</MasterClipChangeVersion>", r"<MZ\.EditLine>-?\d+</MZ\.EditLine>",
             r"<Node Version=\"1\">\s*<ID>\d+</ID>\s*</Node>"]


def prproj_signature(path: Path) -> str | None:
    """sha1 of the project's XML without Premiere's save-time bookkeeping (None if unreadable)."""
    import gzip
    import hashlib
    try:
        with gzip.open(path) as f:
            xml = f.read().decode("utf-8", "replace")
    except (OSError, EOFError):
        return None
    for pat in _VOLATILE:
        xml = re.sub(pat, "", xml)
    return hashlib.sha1(re.sub(r"\s+", " ", xml).encode("utf-8")).hexdigest()


def editor_modified(paths: Paths) -> dict | None:
    """The .prproj was saved after the pipeline built it AND its content differs from what the pipeline saved -> the
    editor has been working in it. A save with no change (Premiere saving an open project when another one is built,
    or its auto-save) only moves the file time: seen live, it blocked a rebuild as "editor changes"."""
    import datetime as _dt
    rec = read_json(paths.p("07_premiere/ppro-build-result.json"), {}) or {}
    for m in paths.p("07_premiere/project").glob("*.prproj"):
        if m.name.startswith("._") or "_prev_" in m.name:
            continue
        bt = prproj_build_time(paths, m)
        if bt is not None and m.stat().st_mtime > bt + 120:
            sig = rec.get("content_signature")
            if sig and prproj_signature(m) == sig:
                continue   # saved, not edited
            f = lambda t: _dt.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M")
            return {"project": str(m), "built_at": f(bt), "edited_at": f(m.stat().st_mtime),
                    "content": "changed" if sig else "unknown (built before content signatures)"}
    return None


def _alpha_bbox(png: Path):
    from .media_util import open_rgb
    return open_rgb(png, "RGBA").getchannel("A").point(lambda a: 255 if a > 24 else 0).getbbox()


def build(paths: Paths) -> dict:
    from PIL import Image
    from .media_util import contact_sheet, open_rgb
    spec = read_json(paths.p("01_analysis/timeline-spec.json"))
    if not spec:
        raise FileNotFoundError("timeline-spec.json missing — run plan first")
    from .common import spec_footage
    src = spec_footage(paths, spec)
    vdir = paths.p("08_quality_control/verify")
    vdir.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_exe()
    tiles, rows = [], []

    def tile(path: Path, label: str):
        if path.exists():
            tiles.append((path, label))

    for e in spec["events"]:
        if e["template"] == "flash_transition":
            continue
        n = e["end_frame"] - e["start_frame"]
        rel = round(n * 0.7) / seq_fps()
        t = e.get("src_start_ms", e["start_ms"]) / 1000 + rel + (spec.get("source_in_ms") or 0) / 1000   # a SOURCE time
        mov = paths.p(f"04_after_effects/compositions/{e['event_id']}.mov")
        out = vdir / f"{e['event_id']}.jpg"
        source = "AE render"
        if mov.exists():
            alpha_png = vdir / f"{e['event_id']}_alpha.png"
            run([ff, "-y", "-loglevel", "error", "-ss", f"{rel:.3f}", "-i", str(mov), "-frames:v", "1", str(alpha_png)], check=False)
            run([ff, "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(src), "-ss", f"{rel:.3f}", "-i", str(mov),
                 "-filter_complex", f"[0]scale={W}:{H}[b];[b][1]overlay,scale=360:640", "-frames:v", "1", str(out)], check=False)
            bbox = _alpha_bbox(alpha_png) if alpha_png.exists() else None
            alpha_png.unlink(missing_ok=True)
        else:
            cat = still_category(e["template"])
            png = paths.p(f"03_broll/{cat}/{e['event_id']}.png")
            comp = paths.p(f"08_quality_control/previews/{e['event_id']}_{e['template']}.jpg")
            source = "PREVIEW ONLY (not AE)"
            bbox = _alpha_bbox(png) if png.exists() else None
            if comp.exists():
                open_rgb(comp).resize((360, 640)).save(out, quality=85)
        safe_ok = None
        if bbox and e["template"] not in FULLSCREEN:
            safe_ok = bbox[0] >= SAFE["x0"] and bbox[2] <= SAFE["x1"] and bbox[1] >= SAFE["y0"] and bbox[3] <= SAFE["y1"]
        p = e["params"]
        expected = (p.get("text") or p.get("headline") or p.get("name") or "").replace("\n", " ")
        if p.get("items"):
            expected += " | items: " + " / ".join(i["text"] for i in p["items"])
        if p.get("lines"):
            expected += " | " + " / ".join(p["lines"])
        rows.append({"tile": len(tiles) + 1, "event": e["event_id"], "template": e["template"],
                     "tc": frame_to_tc(e["start_frame"]), "source": source, "expected_text": expected,
                     "alpha_bbox": list(bbox) if bbox else None, "inside_safe_area": safe_ok,
                     "image": p.get("image")})
        tile(out, f"{len(tiles) + 1} {e['event_id']}")

    cap = paths.p("04_after_effects/compositions/CAPTIONS.mov")
    if cap.exists():
        from . import srt as srtlib
        cues = srtlib.read_srt(paths.p("02_transcription/captions-short.srt"))
        picks = [cues[i] for i in sorted({0, len(cues) // 3, (2 * len(cues)) // 3, len(cues) - 1})] if cues else []
        for c in picks:
            t = (c["start_ms"] + c["end_ms"]) / 2000
            out = vdir / f"CAP_{int(t * 1000):06d}.jpg"
            ts = t + (spec.get("source_in_ms") or 0) / 1000
            run([ff, "-y", "-loglevel", "error", "-ss", f"{ts:.3f}", "-i", str(src), "-ss", f"{t:.3f}", "-i", str(cap),
                 "-filter_complex", f"[0]scale={W}:{H}[b];[b][1]overlay,scale=360:640", "-frames:v", "1", str(out)], check=False)
            rows.append({"tile": len(tiles) + 1, "event": "CAPTIONS", "template": "highlight_caption",
                         "tc": frame_to_tc(round(t * seq_fps())), "source": "AE render",
                         "expected_text": c["text"].replace("\n", " ") + "  (may be hidden if a graphic carries the words)"})
            tile(out, f"{len(tiles) + 1} CAP")
    for psd_prev in sorted(paths.p("05_photoshop/layered-assets").glob("*_preview.png")):
        if psd_prev.name.startswith("._"):
            continue
        out = vdir / (psd_prev.stem + ".jpg")
        open_rgb(psd_prev).resize((360, 640)).save(out, quality=85)
        rows.append({"tile": len(tiles) + 1, "event": psd_prev.stem.replace("_preview", ""), "template": "psd",
                     "source": "Photoshop", "expected_text": "see edit-decisions.global.photoshop_jobs"})
        tile(out, f"{len(tiles) + 1} PSD")

    sheet_p = vdir / "verify_sheet.jpg"
    if not contact_sheet(tiles, sheet_p, cols=6, tile_w=360, tile_h=640, label_box=(150, 24)):
        Image.new("RGB", (6 * 360, 640), "black").save(sheet_p, quality=85)  # nothing to verify: the old empty sheet

    L = [f"# Visual Verification Checklist — {paths.video_id}", "", f"Sheet: `{sheet_p}` (generated {now_iso()})", "",
         "View the sheet and check EVERY tile. A tile passes only if all of these hold:", "",
         "1. Text matches `expected_text` word-for-word, in the right order (RTL: first word on the RIGHT).",
         "2. Arabic letters are joined (no isolated forms, no missing letters, no boxes).",
         "3. Graphic doesn't cover the speaker's face/eyes; photo crops show the face.",
         "4. No white boxes/halos around logos or cut-outs; colours are brand teal/white.",
         "5. Nothing doubled (e.g. caption + card saying the same thing at once).",
         "6. Source says `AE render`. `PREVIEW ONLY` tiles mean the AE render is missing.", "",
         "| Tile | Event | Template | TC | Source | Safe area | Expected text |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        sa = {True: "ok", False: "**OUTSIDE**", None: "n/a"}[r.get("inside_safe_area")]
        L.append(f"| {r['tile']} | {r['event']} | {r['template']} | {r.get('tc', '')} | {r['source']} | {sa} | {r['expected_text'][:120]} |")
    L += ["", "Record the result: `reel verify --record --verdict pass|fail --notes \"<what you checked / what failed>\"`"]
    write_text(vdir / "verify-checklist.md", "\n".join(L) + "\n")
    res = {"sheet": str(sheet_p), "checklist": str(vdir / "verify-checklist.md"), "tiles": len(tiles),
           "outside_safe_area": [r["event"] for r in rows if r.get("inside_safe_area") is False],
           "preview_only": [r["event"] for r in rows if r["source"].startswith("PREVIEW")]}
    write_json(vdir / "verify-build.json", dict(res, rows=rows, at=now_iso()))
    return res


def record(paths: Paths, verdict: str, notes: str, by: str = "claude", sheet_override: str | None = None) -> dict:
    """sheet_override: e.g. a sheet of frames Premiere rendered from its own timeline (ppro-frames)."""
    import time
    if verdict not in ("pass", "fail"):
        raise ValueError("verdict must be pass or fail")
    vb = read_json(paths.p("08_quality_control/verify/verify-build.json"))
    if not vb and not sheet_override:
        raise FileNotFoundError("run `reel verify` (build the sheet) before recording a verdict")
    sheet = Path(sheet_override or vb["sheet"])
    if sheet.stat().st_mtime < newest_render_mtime(paths):
        raise RuntimeError("verify sheet is older than the newest render/PSD — rebuild it with `reel verify` and look again")
    rec = {"verdict": verdict, "notes": notes, "by": by, "at": now_iso(), "recorded_epoch": time.time(),
           "sheet": str(sheet), "sheet_mtime": sheet.stat().st_mtime}
    write_json(paths.p("08_quality_control/visual-verification.json"), rec)
    return rec


def status(paths: Paths) -> dict:
    rec = read_json(paths.p("08_quality_control/visual-verification.json"))
    newest = newest_render_mtime(paths)
    if not rec:
        return {"ok": False, "detail": "no visual verification recorded — run `reel verify`, view the sheet, then --record"}
    if rec.get("sheet_mtime", 0) < newest:
        return {"ok": False, "detail": "renders/PSDs changed after the last visual verification — re-verify"}
    return {"ok": rec["verdict"] == "pass", "detail": f"{rec['verdict']} by {rec['by']} at {rec['at']}: {rec['notes'][:150]}"}
