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

from .common import seq_fps, still_category, Paths, ffmpeg_exe, frame_size, frame_to_tc, now_iso, read_json, run, write_json, write_text

FULLSCREEN = {"broll_card", "broll_video", "logo_outro", "flash_transition"}
TILE_W = 360     # a verify tile is this wide; its height keeps the frame's aspect


def safe_area(w: int, h: int) -> dict:
    """The platform safe area of a w x h frame: 60 px at the sides, 150 px at the top, 200 px at the bottom
    (the 9:16 values, 60/1020/150/1720, are what 1080x1920 gives)."""
    return {"x0": 60, "x1": w - 60, "y0": 150, "y1": h - 200}


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


def _prproj_xml(path: Path) -> str | None:
    import gzip
    try:
        with gzip.open(path) as f:
            return f.read().decode("utf-8", "replace")
    except (OSError, EOFError):
        return None


def _legacy_signature(xml: str) -> str:
    """The 2.x / pre-B2 signature (no prefix): records written by those builds are still compared with it."""
    import hashlib
    for pat in _VOLATILE:
        xml = re.sub(pat, "", xml)
    return hashlib.sha1(re.sub(r"\s+", " ", xml).encode("utf-8")).hexdigest()


# Gate 2 B2 (measured on 26.5, 13-Oct, a byte diff of the build's save against the save Premiere makes when the next
# build closes the project, nothing touched): Premiere finishes background work AFTER the build has saved, so the close
# save differs although no one edited. Elements it adds or rewrites on its own, never editor content:
#   - the content-credentials scan of imported media: <ContentCredentialsInfo>65536 (pending) -> <CCFileModTime>
#     (every still, first build in a fresh Premiere);
#   - the timeline's source patching / track targeting, written when the timeline panel initialises the new
#     sequence, before or after the build's save (a race): HSL.TimelinePatchingAndTargeting.* on the sequence,
#     MZ.SourceTrackState / MZ.SourceTrackNumber on every track;
#   - property bags (<Properties>, <ScratchDiskSettings>) saved in another key order (a hash map).
# Also left out by name: pure view state (timeline scroll/zoom, Program monitor zoom, bin expansion) that a save
# writes whenever the panel moved. The rest of the file counts: a deny-list, not an allow-list, because a missing
# allow-list entry would silently miss editor work (the loss B2 guards against), while a missing deny-list entry
# only costs a refusal that names --replace-edited.
_VOLATILE_TAG = re.compile(
    r"MZ\.BuildVersion\.Modified|NextID|MasterClipChangeVersion|MZ\.EditLine"
    r"|ContentCredentialsInfo|CCFileModTime"
    r"|HSL\.TimelinePatchingAndTargeting\..*|MZ\.SourceTrackState|MZ\.SourceTrackNumber"
    r"|TL\.SQ(?:VisibleBaseTime|TimePerPixel|VideoVisibleBase|AudioVisibleBase|DataVisibleBase)"
    r"|Monitor\.ProgramZoom(?:In|Out)|list\.view\.expanded\.state\..*")
# Gate 2 recheck (13-Oct, §8.2): which effect is selected in Effect Controls (MZ.ComponentChain.ActiveComponentID /
# ActiveComponentParamIndex, written on a chain once it is shown or selected there, e.g. when the panel switches
# projects) is UI selection, not editor work. The first time it appears, a chain that was an empty <ComponentChain>
# gains <Node><Properties>..keys..</Properties></Node>: the wrapper is left out too when only selection keys (and
# other drift above) are in it, so that the chain signs the same with or without them. Real component and effect
# parameter values, and the order of the effects, are not touched.
_SELECTION_TAG = re.compile(r"MZ\.ComponentChain\.Active.*")
SIGNATURE_PREFIX = "c2:"


_WRAPPER_TAG = ("Node", "Properties")        # the property-bag wrappers Premiere puts around a chain's keys


def _droppable(el) -> bool:
    """True when `el` is a selection key or an earlier-listed drift key, or a Node / Properties wrapper that holds
    only those (at any depth) and no text of its own. Any other element (the chain itself, a component) is content."""
    if _SELECTION_TAG.fullmatch(el.tag) or _VOLATILE_TAG.fullmatch(el.tag):
        return True
    return el.tag in _WRAPPER_TAG and len(el) > 0 and not (el.text or "").strip() and all(_droppable(c) for c in el)


def _has_selection(el) -> bool:
    return bool(_SELECTION_TAG.fullmatch(el.tag)) or any(_has_selection(c) for c in el)


def _selection_only(el) -> bool:
    """A selection key, or a Node / Properties wrapper that the selection keys are the only content of."""
    return _has_selection(el) and _droppable(el)


def _canonical(el, out: list) -> None:
    """Element -> text: attributes sorted, whitespace trimmed, Premiere's own drift (above) left out. Children whose
    names are all different and that have no children of their own (property bags, param records) are sorted by name:
    their order carries nothing. Lists (repeated names) keep their order."""
    kids = [k for k in el if not _VOLATILE_TAG.fullmatch(k.tag) and not _selection_only(k)
            and not (k.tag == "Node" and [c.tag for c in k] == ["ID"] and not k.attrib.keys() - {"Version"})]
    if kids and all(len(k) == 0 for k in kids) and len({k.tag for k in kids}) == len(kids):
        kids.sort(key=lambda k: k.tag)
    out.append("<" + el.tag + "".join(f' {a}="{v}"' for a, v in sorted(el.attrib.items())) + ">"
               + (el.text or "").strip())
    for k in kids:
        _canonical(k, out)
    out.append("</" + el.tag + ">")


# XML that ElementTree rejects (a character XML 1.0 forbids, e.g. `&#x1;` or a raw \x01 pasted into a title, or a
# truncated file) is signed from its raw text instead, and a file that is not gzip at all from its bytes: it still
# changes with every edit, but also with Premiere's drift, so such a project can only cost a refusal, never a missed
# edit. Every readable file has a signature: a None one would compare equal to None.
RAW_PREFIX = "raw:"
BYTES_PREFIX = "bytes:"


def _content_signature(xml: str) -> str:
    import hashlib
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return RAW_PREFIX + _legacy_signature(xml)
    out: list = []
    _canonical(root, out)
    return SIGNATURE_PREFIX + hashlib.sha1("\n".join(out).encode("utf-8")).hexdigest()


def prproj_signature(path: Path) -> str | None:
    """Signature of the project's editable content: Premiere's save-time bookkeeping, its background drift and view
    state left out ("raw:" when the XML does not parse, "bytes:" when the file is not gzip; None only when the file
    cannot be read at all)."""
    import gzip
    import hashlib
    import zlib
    try:
        data = path.read_bytes()
    except OSError:
        return None
    try:
        xml = gzip.decompress(data).decode("utf-8", "replace")
    except (OSError, EOFError, zlib.error):
        return BYTES_PREFIX + hashlib.sha1(data).hexdigest()
    return _content_signature(xml)


def signature_matches(path: Path, recorded: str | None, current: str | None = None) -> bool:
    """The file's content equals what was recorded, compared like with like: a "c2:" / "raw:" / "bytes:" record with
    the file's own signature (`current` when the caller already has it fresh: no second parse; a c2 record against a
    project that now only signs raw is a change), a 2.x record (no prefix) with the legacy hash of the file."""
    if not recorded:
        return False
    if recorded.startswith((SIGNATURE_PREFIX, RAW_PREFIX, BYTES_PREFIX)):
        if current is None:
            current = prproj_signature(path)
        return current is not None and current == recorded
    if current is not None and current.startswith(RAW_PREFIX):
        return current[len(RAW_PREFIX):] == recorded         # the raw hash IS the legacy one
    xml = _prproj_xml(path)
    return xml is not None and _legacy_signature(xml) == recorded


def editor_modified(paths: Paths, current: dict | None = None) -> dict | None:
    """The .prproj was saved after the pipeline built it AND its content differs from what the pipeline saved -> the
    editor has been working in it. A save with no change (Premiere saving an open project when another one is built,
    or its auto-save) only moves the file time: seen live, it blocked a rebuild as "editor changes".
    `current` ({project path: signature}) passes signatures the caller hashed just now, so they are not parsed again.
    A project without a signature (not readable) counts as changed."""
    import datetime as _dt
    rec = read_json(paths.p("07_premiere/ppro-build-result.json"), {}) or {}
    for m in paths.p("07_premiere/project").glob("*.prproj"):
        if m.name.startswith("._") or "_prev_" in m.name:
            continue
        bt = prproj_build_time(paths, m)
        if bt is not None and m.stat().st_mtime > bt + 120:
            sig = rec.get("content_signature")
            if sig and signature_matches(m, sig, (current or {}).get(str(m))):
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
    from .stamps import read_compiled
    spec = read_compiled(paths.p("01_analysis/timeline-spec.json"))
    if not spec:
        from .errors import Guidance
        raise Guidance("no compiled plan yet (01_analysis/timeline-spec.json)", "Run `reel plan` first",
                       where=str(paths.p("01_analysis/timeline-spec.json")))
    from .common import spec_footage
    src = spec_footage(paths, spec)
    W, H = frame_size(paths)
    TH = round(TILE_W * H / W)
    SAFE = safe_area(W, H)
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
                 "-filter_complex", f"[0]scale={W}:{H}[b];[b][1]overlay,scale={TILE_W}:{TH}", "-frames:v", "1", str(out)], check=False)
            bbox = _alpha_bbox(alpha_png) if alpha_png.exists() else None
            alpha_png.unlink(missing_ok=True)
        else:
            cat = still_category(e["template"])
            png = paths.p(f"03_broll/{cat}/{e['event_id']}.png")
            comp = paths.p(f"08_quality_control/previews/{e['event_id']}_{e['template']}.jpg")
            source = "PREVIEW ONLY (not AE)"
            bbox = _alpha_bbox(png) if png.exists() else None
            if comp.exists():
                open_rgb(comp).resize((TILE_W, TH)).save(out, quality=85)
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
                 "-filter_complex", f"[0]scale={W}:{H}[b];[b][1]overlay,scale={TILE_W}:{TH}", "-frames:v", "1", str(out)], check=False)
            rows.append({"tile": len(tiles) + 1, "event": "CAPTIONS", "template": "highlight_caption",
                         "tc": frame_to_tc(round(t * seq_fps())), "source": "AE render",
                         "expected_text": c["text"].replace("\n", " ") + "  (may be hidden if a graphic carries the words)"})
            tile(out, f"{len(tiles) + 1} CAP")
    for psd_prev in sorted(paths.p("05_photoshop/layered-assets").glob("*_preview.png")):
        if psd_prev.name.startswith("._"):
            continue
        out = vdir / (psd_prev.stem + ".jpg")
        open_rgb(psd_prev).resize((TILE_W, TH)).save(out, quality=85)
        rows.append({"tile": len(tiles) + 1, "event": psd_prev.stem.replace("_preview", ""), "template": "psd",
                     "source": "Photoshop", "expected_text": "see edit-decisions.global.photoshop_jobs"})
        tile(out, f"{len(tiles) + 1} PSD")

    sheet_p = vdir / "verify_sheet.jpg"
    if not contact_sheet(tiles, sheet_p, cols=6, tile_w=TILE_W, tile_h=TH, label_box=(150, 24)):
        Image.new("RGB", (6 * TILE_W, TH), "black").save(sheet_p, quality=85)  # nothing to verify: the old empty sheet

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
        from .errors import Guidance
        raise Guidance("no verification sheet to record against (08_quality_control/verify/verify-build.json)",
                       "Run `reel verify` (it builds the sheet), VIEW the sheet, then `reel verify --record --verdict "
                       "pass|fail --note \"...\"`", where=str(paths.p("08_quality_control/verify/verify-build.json")))
    sheet = Path(sheet_override or vb["sheet"])
    if sheet.stat().st_mtime < newest_render_mtime(paths):
        from .errors import Guidance
        raise Guidance("the verification sheet is older than the newest render/PSD",
                       "Rebuild it with `reel verify`, look at it again, then record the verdict", where=str(sheet))
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
