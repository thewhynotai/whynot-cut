"""Animatic for Gate 1 (`reel motion-animatic`, spec §4.4): one still per scene in its hero state (Pillow + HarfBuzz
with the brand font files), a storyboard sheet, and an MP4 that holds each still for its scene with short crossfades
over the mixed audio. A layout approximation for approving the story; After Effects frames are the truth.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .common import ffmpeg_exe, fmt_ts, read_json

ANIM_FPS = 10
LABEL = "layout approximation - After Effects frames are the truth"


def _rgb(c) -> tuple:
    return tuple(int(round(v * 255)) for v in c[:3])


def _font(file: str, size: float):
    from . import hb_text
    size = max(6, int(round(size)))
    if hb_text.AVAILABLE:
        try:
            return hb_text.HBFontSpec(file, size)
        except Exception:  # noqa: BLE001 — unreadable font: Pillow below
            pass
    try:
        return ImageFont.truetype(file, size)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


def _line(im: Image.Image, text: str, font, x: float, y: float, rgb: tuple, anchor: str, rtl: bool):
    col = rgb + (255,)
    if hasattr(font, "render"):
        img, _, w = font.render(text, col)
    else:
        d = ImageDraw.Draw(im)
        w = d.textlength(text, font=font)
        img = None
    if anchor == "start":
        x0 = x - w if rtl else x
    else:
        x0 = x - w / 2
    if img is not None:
        im.alpha_composite(img, (max(0, int(x0)), max(0, int(y))))
    else:
        ImageDraw.Draw(im).text((x0, y), text, font=font, fill=col)


def _text(im, e: dict, plan: dict, s: float, text: str | None = None):
    lines = (text or e.get("text", "")).split("\r") if text is None else [text]
    if e.get("kind") == "counter":
        lines = [e.get("text", "").replace("\r", " ")]
    f = _font(plan["fonts"][e["role"]]["file"], e["size"] * s)
    lh = e["size"] * s * 1.25
    y = e["y"] * s - lh * len(lines) / 2
    for ln in lines:
        _line(im, ln, f, e["x"] * s, y, _rgb(e["color"]), e.get("anchor", "center"), bool(e.get("rtl")))
        y += lh


def _shapes(im, e: dict, s: float, fill: bool):
    from .motion_icons import flatten
    d = ImageDraw.Draw(im)
    col = _rgb(e.get("color") or e.get("fill") or [1, 1, 1])
    for poly in flatten(e["shapes"], 1.0):
        pts = [((e["x"] + x) * s, (e["y"] + y) * s) for x, y in poly]
        if len(pts) < 2:
            continue
        if fill:
            d.polygon(pts, fill=col)
        else:
            d.line(pts, fill=col, width=max(1, int(e.get("stroke", 2) * s)), joint="curve")


def _image(im, e: dict, s: float):
    try:
        src = Image.open(e["path"]).convert("RGBA")
    except Exception:  # noqa: BLE001 — a missing image is reported by the plan; the animatic just skips it
        return
    w, h = max(1, int(e["w"] * s)), max(1, int(e["h"] * s))
    if e.get("fit") == "contain":
        src.thumbnail((w, h))
    else:
        r = max(w / src.width, h / src.height)
        src = src.resize((max(1, int(src.width * r)), max(1, int(src.height * r))))
        l, t = (src.width - w) // 2, (src.height - h) // 2
        src = src.crop((l, t, l + w, t + h))
        if e.get("radius"):
            mask = Image.new("L", src.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, src.width - 1, src.height - 1), radius=int(e["radius"] * s),
                                                   fill=255)
            src.putalpha(mask)
    im.alpha_composite(src, (int(e["x"] * s - src.width / 2), int(e["y"] * s - src.height / 2)))


def scene_still(scene: dict, plan: dict, brand=None, width: int = 540) -> Image.Image:
    s = width / plan["w"]
    W, H = width, int(round(plan["h"] * s / 2)) * 2
    im = Image.new("RGBA", (W, H), _rgb(scene["bg"]) + (255,))
    d = ImageDraw.Draw(im)
    for e in scene["elements"]:
        k = e.get("kind")
        if k in ("text", "counter"):
            _text(im, e, plan, s)
        elif k == "icon":
            _shapes(im, e, s, fill=False)
        elif k == "vector":
            _shapes(im, e, s, fill=True)
        elif k == "image":
            _image(im, e, s)
        elif k == "dot":
            r = e["r"] * s
            d.ellipse((e["x"] * s - r, e["y"] * s - r, e["x"] * s + r, e["y"] * s + r), fill=_rgb(e["color"]))
        elif k == "line":
            d.line([(e["from"][0] * s, e["from"][1] * s), (e["to"][0] * s, e["to"][1] * s)], fill=_rgb(e["color"]),
                   width=max(1, int(e["width"] * s)))
    per = plan.get("persistent") or {}
    hero = scene["hero_frame"]
    cap = next((c for c in ((per.get("captions") or {}).get("cues") or []) if c["start_frame"] <= hero < c["end_frame"]), None)
    if cap:
        c = per["captions"]
        _text(im, {"kind": "text", "role": "caption", "size": c["size"], "x": c["x"], "y": c["y"], "color": c["color"],
                   "rtl": True, "text": cap["text"]}, plan, s)
    badge = next((g for g in ((per.get("speaker_badge") or {}).get("segments") or []) if g["start_frame"] <= hero < g["end_frame"]), None)
    if badge:
        b = per["speaker_badge"]
        _text(im, {"kind": "text", "role": "label", "size": b["size"], "x": b["x"], "y": b["y"], "color": b["accent"],
                   "rtl": True, "anchor": "start", "text": badge["name"]}, plan, s)
    return im


def _label(im: Image.Image, text: str) -> Image.Image:
    out = im.copy()
    d = ImageDraw.Draw(out)
    try:
        f = ImageFont.load_default(size=14)
    except TypeError:   # Pillow < 10.1
        f = ImageFont.load_default()
    d.rectangle((0, out.height - 24, out.width, out.height), fill=(0, 0, 0, 170))
    d.text((8, out.height - 20), text, fill=(235, 235, 235, 255), font=f)
    return out


def render(paths, width: int = 540) -> dict:
    from .motion_audio import mix
    from .previews import Brand
    plan = read_json(paths.p("01_analysis/motion-plan.json"))
    if not plan:
        raise SystemExit("01_analysis/motion-plan.json missing — run `reel motion-plan` first")
    brand = Brand(paths.client_db)
    d = paths.p("08_quality_control/animatic")
    d.mkdir(parents=True, exist_ok=True)
    fps = float(plan["fps"])
    stills, imgs = [], []
    for sc in plan["scenes"]:
        im = scene_still(sc, plan, brand, width)
        p = d / f"{sc['id']}.png"
        im.save(p)
        stills.append(str(p))
        imgs.append(im)
    # storyboard
    tw = 270
    th = int(round(imgs[0].height * tw / imgs[0].width))
    cols = 4
    rows = math.ceil(len(imgs) / cols)
    sheet = Image.new("RGB", (cols * tw, rows * (th + 26)), "black")
    dr = ImageDraw.Draw(sheet)
    for k, (sc, im) in enumerate(zip(plan["scenes"], imgs)):
        x, y = (k % cols) * tw, (k // cols) * (th + 26)
        sheet.paste(im.convert("RGB").resize((tw, th)), (x, y + 26))
        dr.text((x + 6, y + 6), f"{sc['id']} {sc['type']} {fmt_ts(int(sc['start_frame'] * 1000 / fps), '.')[3:10]}",
                fill="yellow")
    sheet_p = d / "_storyboard.jpg"
    sheet.save(sheet_p, quality=88)
    # MP4: 10 fps, 6-frame crossfades at scene starts, label strip, mixed audio
    dur = plan["duration_frames"] / fps
    wav = mix(plan, paths.root, d / "_animatic_mix.wav")
    mp4 = d / f"{paths.video_id}_animatic.mp4"
    W, H = imgs[0].size
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(ANIM_FPS), "-i", "-", "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "libx264",
           "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
           "-t", f"{dur:.3f}", "-movflags", "+faststart", str(mp4)]
    labeled = [_label(im, f"{sc['id']} {sc['type']} · {LABEL}").convert("RGB") for sc, im in zip(plan["scenes"], imgs)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    n = int(math.ceil(dur * ANIM_FPS)) + 1
    cache = {}
    for k in range(n):
        t = k / ANIM_FPS * fps
        i = max((j for j, sc in enumerate(plan["scenes"]) if sc["start_frame"] <= t), default=0)
        a = (t - plan["scenes"][i]["start_frame"]) / 6.0
        if i > 0 and a < 1:
            key = (i, round(a, 2))
            if key not in cache:
                cache[key] = Image.blend(labeled[i - 1], labeled[i], max(0.0, a)).tobytes()
            p.stdin.write(cache[key])
        else:
            p.stdin.write(cache.setdefault((i, 1.0), labeled[i].tobytes()))
    p.stdin.close()
    err = p.stderr.read().decode("utf-8", "replace")
    p.wait()
    if p.returncode or not mp4.exists():
        raise SystemExit(f"animatic encode failed: {err[-400:]}")
    return {"stills": stills, "sheet": str(sheet_p), "mp4": str(mp4), "duration_s": round(dur, 3)}
