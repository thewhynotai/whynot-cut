"""Per-shot 9:16 reframe for reels cut from a finished 16:9 episode (podcast mode).

A finished episode cuts between close-ups, two-shots and B-roll, so one crop for the whole reel (media.auto_reframe)
cuts faces off. Here every shot inside the reel's window gets its own framing:
  * one face (or a group that fits in the crop)  -> AUTO_SHOT centred on it
  * no face (graphic card, B-roll)               -> AUTO_CUTAWAY: shown whole over a blurred fill (existing path)
  * two or more faces that don't fit             -> follow the speaker (speaker turns + seating positions);
                                                    unknown speaker or layout -> shown whole
Story-editor camera moves (punch-ins) are then composed ON TOP of the shot framing (compose_camera).
Times are on the reel clock (0 = the reel's in-point). Offsets are Premiere Motion px at the sequence size.
"""
from __future__ import annotations

import re
from pathlib import Path

from .common import ffmpeg_exe, load_config, ms_to_frame, run

SHOWINFO_T = re.compile(r"pts_time:\s*([0-9.]+)")


def _cfg() -> dict:
    return load_config("podcast.json").get("shots", {})


# --------------------------------------------------------------------------- analysis
def detect_cuts(path: Path, offset_ms: int, duration_ms: int, threshold: float = 0.3) -> list[int]:
    """Hard cuts inside [offset, offset+duration) of the file, in ms on the window clock (ffmpeg scene score)."""
    p = run([ffmpeg_exe(), "-hide_banner", "-nostats", "-ss", f"{offset_ms / 1000:.3f}", "-t", f"{duration_ms / 1000:.3f}",
             "-i", str(path), "-an", "-vf", f"scale=270:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
            check=False)
    return sorted({int(round(float(t) * 1000)) for t in SHOWINFO_T.findall(p.stderr or "")
                   if 0 < float(t) * 1000 < duration_ms})


def shots_from_cuts(cuts: list[int], duration_ms: int, min_shot_ms: int = 400) -> list[tuple[int, int]]:
    """Cut times -> contiguous shots; a shot shorter than min_shot_ms (flash, dissolve frames) joins its neighbour."""
    edges = [0]
    for c in sorted(set(cuts)):
        if c - edges[-1] >= min_shot_ms and duration_ms - c >= min_shot_ms:
            edges.append(c)
    edges.append(duration_ms)
    return list(zip(edges, edges[1:]))


def face_boxes(im) -> list[tuple[float, float, float, float]]:
    """Every face as (cx, cy, w, h), 0..1, top-left origin: macOS Vision, else OpenCV (frontal, then profile both
    ways). Faces smaller than face_min_ratio of the largest (background people, posters) are dropped."""
    boxes = _boxes_vision(im)
    if boxes is None:
        boxes = _boxes_opencv(im)
    if not boxes:
        return []
    big = max(b[2] * b[3] for b in boxes)
    keep = _cfg().get("face_min_ratio", 0.3)
    return sorted((b for b in boxes if b[2] * b[3] >= keep * big), key=lambda b: b[0])


def _boxes_vision(im):
    try:
        import io
        import Vision
        from Foundation import NSData
    except Exception:  # noqa: BLE001  (not macOS)
        return None
    try:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "PNG")
        data = NSData.dataWithBytes_length_(buf.getvalue(), len(buf.getvalue()))
        req = Vision.VNDetectFaceRectanglesRequest.alloc().init()
        h = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
        if not h.performRequests_error_([req], None)[0]:
            return []
        out = []
        for o in req.results() or []:
            b = o.boundingBox()
            out.append((b.origin.x + b.size.width / 2, 1 - (b.origin.y + b.size.height / 2), b.size.width, b.size.height))
        return out
    except Exception:  # noqa: BLE001
        return None


def _boxes_opencv(im) -> list:
    try:
        import cv2
        import numpy as np
    except Exception:  # noqa: BLE001
        return []
    g = np.array(im.convert("L"))
    sc = min(1.0, 1200 / max(g.shape))
    if sc < 1:
        g = cv2.resize(g, (int(g.shape[1] * sc), int(g.shape[0] * sc)))
    H, W = g.shape
    mins = (int(0.05 * min(W, H)),) * 2
    det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = list(det.detectMultiScale(g, scaleFactor=1.1, minNeighbors=6, minSize=mins))
    if not faces:
        prof = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
        faces = list(prof.detectMultiScale(g, scaleFactor=1.1, minNeighbors=5, minSize=mins))
        faces += [(W - x - w, y, w, h) for (x, y, w, h) in prof.detectMultiScale(cv2.flip(g, 1), scaleFactor=1.1,
                                                                                    minNeighbors=5, minSize=mins)]
    out = []
    for (x, y, w, h) in faces:   # merge near-duplicates (frontal + profile hits on the same person)
        c = ((x + w / 2) / W, (y + h / 2) / H, w / W, h / H)
        if not any(abs(c[0] - o[0]) < max(c[2], o[2]) * 0.6 and abs(c[1] - o[1]) < max(c[3], o[3]) * 0.6 for o in out):
            out.append(c)
    return out


def split_by_presence(samples: list, a: int, b: int, min_run_ms: int = 1000) -> list[tuple[int, int, list]]:
    """Split a shot where faces appear or disappear for at least min_run_ms (a dissolve to a graphic card and back has
    no hard cut). samples = [(t_ms, faces)] or [(t_ms, faces, speaker_like)]: speaker_like marks a sample without a
    detected face that still looks like the speaker's frames (head turned down: Haar misses it). A single missed
    detection never splits. Each part keeps the median of its samples that have faces."""
    ss = [(s[0], s[1], s[2] if len(s) > 2 else bool(s[1])) for s in samples if a <= s[0] < b]
    if not ss:
        near = min(samples, key=lambda s: abs(s[0] - (a + b) / 2)) if samples else (a, [])
        return [(a, b, near[1])]
    step = (ss[1][0] - ss[0][0]) if len(ss) > 1 else (b - a)
    runs = []
    for i, (_t, f, pres) in enumerate(ss):
        pres = bool(f) or bool(pres)
        if runs and runs[-1][2] == pres:
            runs[-1][1] = i
        else:
            runs.append([i, i, pres])
    changed = True
    while changed and len(runs) > 1:
        changed = False
        for k, r in enumerate(runs):
            if (r[1] - r[0] + 1) * step < min_run_ms:
                if k > 0:
                    runs[k - 1][1] = r[1]
                else:
                    runs[1][0] = r[0]
                runs.pop(k)
                for j in range(len(runs) - 1, 0, -1):
                    if runs[j][2] == runs[j - 1][2]:
                        runs[j - 1][1] = runs[j][1]
                        runs.pop(j)
                changed = True
                break
    out = []
    for k, (i0, i1, _p) in enumerate(runs):
        s = a if k == 0 else (ss[i0 - 1][0] + ss[i0][0]) // 2
        e = b if k == len(runs) - 1 else (ss[i1][0] + ss[i1 + 1][0]) // 2
        with_faces = sorted((f for _t, f, _p in ss[i0:i1 + 1] if f), key=len)
        present = sum(1 for _t, f, p in ss[i0:i1 + 1] if f or p) * 2 > (i1 - i0 + 1)
        out.append((s, e, with_faces[len(with_faces) // 2] if present and with_faces else []))
    return out


def analyze_window(path: Path, offset_ms: int, duration_ms: int, faces_fn=face_boxes) -> dict:
    """Shots inside the window and the faces in each: hard cuts (scene score), then splits where faces appear or
    disappear for >= 1 s (dissolves to cards). Faces are sampled at sample_fps in one decode pass of small frames."""
    import subprocess
    from PIL import Image
    cfg = _cfg()
    cuts = detect_cuts(path, offset_ms, duration_ms, cfg.get("scene_threshold", 0.3))
    hard = shots_from_cuts(cuts, duration_ms, cfg.get("min_shot_ms", 400))
    W, H, fps = 640, 360, float(cfg.get("sample_fps", 2.0))
    p = subprocess.Popen([ffmpeg_exe(), "-loglevel", "error", "-ss", f"{offset_ms / 1000:.3f}", "-t",
                          f"{duration_ms / 1000:.3f}", "-i", str(path), "-an", "-vf",
                          f"fps={fps},scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    from .media import _hist, _similarity
    raw, n = [], 0
    try:
        while True:
            buf = p.stdout.read(W * H * 3)
            if len(buf) < W * H * 3:
                break
            im = Image.frombuffer("RGB", (W, H), buf, "raw", "RGB", 0, 1)
            raw.append((int((n + 0.5) * 1000 / fps), [[round(float(x), 4) for x in f] for f in faces_fn(im)], _hist(im)))
            n += 1
    finally:
        p.stdout.close()
        p.kill()
        p.wait()
    # a frame without a detected face that looks like the frames WITH faces is still the speaker (head turned, hand
    # over the face): colour-histogram intersection, the same rule media.analyze_shots uses for cutaways
    ref = [h for _t, f, h in raw if f]
    mean = [sum(c) / len(ref) for c in zip(*ref)] if ref else None
    thr = float(cfg.get("speaker_similarity", 0.55))
    samples = [(t, f, bool(f) or (mean is not None and _similarity(h, mean) >= thr)) for t, f, h in raw]
    out = []
    for a, b in hard:
        for s, e, faces in split_by_presence(samples, a, b, int(cfg.get("min_presence_run_ms", 1000))):
            out.append({"start_ms": s, "end_ms": e, "faces": faces, "n_faces": len(faces)})
    note = ""
    if out and not any(s["n_faces"] for s in out):
        note = ("no face found in any shot (audio-only or graphics-led episode): the reel is shown whole; "
                "a motion/animation version (motion mode, phase 3) fits better")
    return {"window": {"offset_ms": offset_ms, "duration_ms": duration_ms}, "cuts_ms": cuts, "shots": out,
            "method": "ffmpeg scene cuts + " + ("face detection (Vision / OpenCV)" if faces_fn is face_boxes else "injected faces"),
            "note": note}


# --------------------------------------------------------------------------- framing
def _dims(src_w, src_h, seq_w, seq_h):
    cover, fit = max(seq_w / src_w, seq_h / src_h), min(seq_w / src_w, seq_h / src_h)
    return cover, fit, max(0.0, (src_w * cover - seq_w) / 2)


def _offset(cx: float, src_w: float, cover: float, lim: float) -> float:
    return round(max(-lim, min(lim, -(cx - 0.5) * src_w * cover)), 1)


def frame_shots(shots: list, speakers: dict | None, src_w: int, src_h: int, seq_w: int = 1080, seq_h: int = 1920,
                min_hold_ms: int = 1500, group_fit: float = 0.8) -> list[dict]:
    """Camera layer (reel clock) from analysed shots. See the module docstring for the rules."""
    cover, fit, lim = _dims(src_w, src_h, seq_w, seq_h)
    people = (speakers or {}).get("people") or {}
    turns = sorted((speakers or {}).get("turns") or [], key=lambda t: t["start_ms"])

    def shot_e(a, b, cx, why, target=None):
        return {"decision_id": "AUTO_SHOT", "type": "reframe", "at_ms": a, "until_ms": b, "frame": ms_to_frame(a),
                "scale_factor": 1.0, "offset_x": _offset(cx, src_w, cover, lim), "offset_y": 0.0, "rationale": why,
                "target": target}

    def whole(a, b, why):
        return {"decision_id": "AUTO_CUTAWAY", "type": "reframe", "at_ms": a, "until_ms": b, "frame": ms_to_frame(a),
                "scale_factor": round(fit / cover, 5), "offset_x": 0.0, "offset_y": 0.0, "rationale": why, "target": None}

    out = []
    for s in shots:
        a, b, faces = s["start_ms"], s["end_ms"], sorted(s.get("faces") or [], key=lambda f: f[0])
        if not faces:
            out.append(whole(a, b, "no face in this shot (card / B-roll): shown whole"))
            continue
        x0 = min(f[0] - f[2] / 2 for f in faces)
        x1 = max(f[0] + f[2] / 2 for f in faces)
        if len(faces) == 1 or (x1 - x0) * src_w * cover <= group_fit * seq_w:
            out.append(shot_e(a, b, (x0 + x1) / 2, "single face" if len(faces) == 1 else f"{len(faces)} faces fit together"))
            continue
        pos_face = {"left": faces[0][0], "right": faces[-1][0],
                    "center": min(faces, key=lambda f: abs(f[0] - 0.5))[0]}
        pieces, t = [], a
        for tr in turns:                                   # who speaks when, inside this shot
            # overlapping turns (crosstalk): the later one starts where the earlier ends, so pieces never overlap
            ta, tb = max(a, tr["start_ms"], t), min(b, tr["end_ms"])
            if tb <= ta:
                continue
            if ta > t:
                pieces.append([t, ta, None])
            pieces.append([ta, tb, tr.get("speaker")])
            t = tb
        if t < b:
            pieces.append([t, b, None])
        for k, pc in enumerate(pieces):                    # silence/unknown: keep whoever was framed
            if pc[2] is None:
                pc[2] = next((q[2] for q in reversed(pieces[:k]) if q[2]), None) or \
                    next((q[2] for q in pieces[k + 1:] if q[2]), None)
        merged = []
        for pc in pieces:
            if merged and merged[-1][2] == pc[2]:
                merged[-1][1] = pc[1]
            else:
                merged.append(list(pc))
        changed = True
        while changed and len(merged) > 1:                 # no ping-pong: a framing holds at least min_hold_ms
            changed = False
            for k, pc in enumerate(merged):
                if pc[1] - pc[0] < min_hold_ms:
                    if k > 0:
                        merged[k - 1][1] = pc[1]
                    else:
                        merged[1][0] = pc[0]
                    merged.pop(k)
                    for j in range(len(merged) - 1, 0, -1):
                        if merged[j][2] == merged[j - 1][2]:
                            merged[j - 1][1] = merged[j][1]
                            merged.pop(j)
                    changed = True
                    break
        for pa, pb, who in merged:
            pos = (people.get(who) or {}).get("position") if who else None
            if pos in pos_face:
                out.append(shot_e(pa, pb, pos_face[pos], f"wide shot: following the {who} ({pos})", who))
            else:
                out.append(whole(pa, pb, "wide shot, speaker or seating unknown: shown whole (no guess)"
                                 if turns or people else "wide shot without speaker/layout information: shown whole"))
    return out


def compose_camera(story: list, layer: list, src_w: int, src_h: int, seq_w: int = 1080, seq_h: int = 1920) -> list[dict]:
    """Story-editor camera moves composed over the shot layer: scale multiplies, the shot offset scales with the
    zoom (so the face stays put) and the story offset adds; clamped so the frame stays filled. AUTO_CUTAWAY entries
    pass through untouched (they keep priority downstream)."""
    cover, _fit, _lim = _dims(src_w, src_h, seq_w, seq_h)
    cut = [c for c in layer if c["decision_id"] == "AUTO_CUTAWAY"]
    shots = [c for c in layer if c["decision_id"] != "AUTO_CUTAWAY"]
    pts = sorted({x for c in story + shots for x in (c["at_ms"], c["until_ms"])})
    out = []
    for a, b in zip(pts, pts[1:]):
        if b <= a:
            continue
        act = [c for c in story if c["at_ms"] <= a < c["until_ms"]]
        s = max(act, key=lambda c: c["at_ms"]) if act else None
        h = next((c for c in shots if c["at_ms"] <= a < c["until_ms"]), None)
        if not s and not h:
            continue
        if s and h:
            k = float(s.get("scale_factor", 1.0))
            scale = h["scale_factor"] * k
            lim = max(0.0, (src_w * cover * scale - seq_w) / 2)
            ox = max(-lim, min(lim, h["offset_x"] * k + float(s.get("offset_x", 0.0))))
            e = dict(s, scale_factor=round(scale, 5), offset_x=round(ox, 2), offset_y=float(s.get("offset_y", 0.0)),
                     shot_offset_x=h["offset_x"], target=h.get("target"))
        else:
            e = dict(h or s)
        e.update(at_ms=a, until_ms=b, frame=ms_to_frame(a))
        p = out[-1] if out else None
        if p and p["until_ms"] == a and all(p.get(x) == e.get(x) for x in ("decision_id", "type", "scale_factor",
                                                                           "offset_x", "offset_y")):
            p["until_ms"] = b
        else:
            out.append(e)
    return out + [dict(c, frame=ms_to_frame(c["at_ms"])) for c in cut]
