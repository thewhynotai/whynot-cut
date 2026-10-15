"""Static PNG previews of every planned graphic (the profile's frame size, 1080x1920 by default; transparent where overlay).

Purpose: (1) instant visual QC of the plan, (2) fallback media for the Premiere XML when
After Effects renders are unavailable. Final animated/editable versions are the AE comps.
Text engines, best first: macOS CoreText (installed brand font), HarfBuzz + FreeType (the client's font FILE; every
OS), then the arabic_reshaper + python-bidi fallback (breaks fonts with few presentation forms; last resort only).
Stored text always stays in logical order.
"""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .common import still_category, Paths, brand_fallback, font_role_fallback, frame_size, load_config, read_json, write_json, now_iso, ms_to_frame
from .font_roles import DEFAULT_ROLE_STYLE, WEIGHT, resolve
from . import fonts as fontdb

_ARABIC_TEXT = __import__("re").compile("[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")


def _shape(s: str) -> str:
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        import re as _re
        rtl = bool(_re.search('[\u0600-\u06FF]', s))
        return get_display(arabic_reshaper.reshape(s), base_dir='R' if rtl else None)
    except Exception:
        return s


class Brand:
    def __init__(self, db: Path):
        tok = read_json(db / "branding/brand-tokens.json", {})
        roles, der = tok.get("roles", {}), tok.get("derived", {})
        hx = lambda h: tuple(int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        self.teal = hx(roles.get("primary", {}).get("hex", brand_fallback("primary")))
        self.white = hx(roles.get("neutral_light", {}).get("hex", brand_fallback("neutral_light")))
        self.paper = hx(der.get("paper_tint", {}).get("hex", brand_fallback("paper_tint")))
        self.ink = hx(der.get("ink", {}).get("hex", brand_fallback("ink")))
        typ = read_json(db / "branding/typography.json", {})
        self.files, self.ps_names = {}, {}
        for fam in typ.get("families", {}).values():
            for wgt in fam["weights"]:
                self.files[wgt["style"].lower()] = wgt["file"]
                self.ps_names[wgt["style"].lower()] = wgt["postscript_name"]
        self.engines = set()
        self.typography, self._faces, self._fallbacks_used = typ, {}, {}
        # the weight each role wants (typography.json roles, then brand.json, then the house default)
        self.role_style = {r: self.face(r)["wanted"] for r in DEFAULT_ROLE_STYLE}

    def face(self, role: str) -> dict:
        """The font face this role draws with: {file, ps, style, wanted, source, exact} (see font_roles.resolve)."""
        if role not in self._faces:
            self._faces[role] = resolve(self.typography, role, font_role_fallback().get("weights", {}))
        return self._faces[role]

    def font(self, role: str, size: int):
        """Shaping text engine for this role. The chosen engine is recorded in self.engines (QC shows it).
        G72: when the client's font for the role has no Arabic, a text block with Arabic is drawn with the system
        Arabic fallback (lib/fonts.py) at the same size, never Pillow's bitmap font; font_warnings() names it."""
        face = self.face(role)
        own = self._font(face, size)
        if own is not None and self._has_arabic(face):
            return own
        fb = fontdb.arabic_fallback(bold=WEIGHT.get(face["wanted"], 400) >= 600)
        fb_font = self._font(fb, size) if fb else None
        if fb_font is None:             # no Arabic font on this computer either: Arabic text is named in font_warnings()
            return _ArabicAware(own, None, self, None)
        return _ArabicAware(own, fb_font, self, fb)

    def _font(self, face: dict, size: int):
        """The engine for one face {file, ps[, index]}: CoreText, HarfBuzz, else Pillow; None when it has neither."""
        from . import ct_text, hb_text
        if ct_text.AVAILABLE:
            ps = face["ps"]
            if ps:
                spec = ct_text.CTFontSpec(ps, size)
                if spec.is_exact:  # font installed -> exact brand font, full shaping (verified on macOS)
                    self.engines.add("coretext")
                    return spec
        f, index = face["file"], face.get("index") or 0
        if f and hb_text.AVAILABLE:
            try:
                spec = hb_text.HBFontSpec(f, size, index=index)
                self.engines.add("harfbuzz")
                return spec
            except Exception:  # unreadable font file -> fallback below
                pass
        if not f:
            return None
        self.engines.add("pillow-fallback")
        return ImageFont.truetype(f, size, index=index)

    def _has_arabic(self, face: dict) -> bool:
        fam = ((self.typography or {}).get("families") or {}).get(face.get("family")) or {}
        if "supports_arabic" in fam:
            return bool(fam["supports_arabic"])
        return fontdb.supports_arabic(face["file"], face.get("index") or 0) if face.get("file") else True

    def font_warnings(self) -> list[str]:
        """'client has no Arabic font — using <fallback>' for each fallback that drew Arabic text, or the "no Arabic
        font at all" warning when Arabic text was drawn and neither the client nor the computer has one (G72)."""
        return [fontdb.fallback_warning(f) for f in self._fallbacks_used.values()]

    def arabic_warnings(self) -> list[str]:
        """The same warnings before anything is drawn (`reel plan`): one per fallback a role whose font has no Arabic
        would use, or the "no Arabic font at all" one."""
        out = []
        for role in DEFAULT_ROLE_STYLE:
            face = self.face(role)
            if (face.get("file") or face.get("ps")) and self._has_arabic(face):
                continue
            w = fontdb.fallback_warning(fontdb.arabic_fallback(bold=WEIGHT.get(face["wanted"], 400) >= 600))
            if w not in out:
                out.append(w)
        return out


def arabic_font_warnings(db: Path, texts) -> list[str]:
    """G72 for `reel plan`: when any of `texts` (on-screen strings, captions) has Arabic and the client's font for a
    role has none, the warning naming the system fallback (or saying there is no Arabic font at all)."""
    if not any(_ARABIC_TEXT.search(str(t or "")) for t in texts):
        return []
    return Brand(db).arabic_warnings()


class _ArabicAware:
    """A role's font when the client's font has no Arabic (G72): _text_block asks for_text(), which gives the system
    Arabic fallback for a block with Arabic (and for every block when the client has no font), else the brand font.
    The choice is per text block, not per run: a Latin brand name inside an Arabic line is drawn with the fallback too
    (same size; the metrics come from the font actually used, so baselines stay consistent). No fallback on this
    computer: the brand font (or Pillow's bitmap font) draws, and font_warnings() says Arabic cannot be drawn."""

    def __init__(self, own, fallback, brand: Brand, fb_face: dict | None):
        self.own, self.fallback, self.brand, self.fb_face = own, fallback, brand, fb_face

    def for_text(self, text: str):
        arabic = bool(_ARABIC_TEXT.search(str(text or "")))
        if arabic:
            key = self.fb_face["ps"] if self.fb_face else ""
            self.brand._fallbacks_used.setdefault(key, self.fb_face)
        if self.fallback is None:
            return self.own if self.own is not None else ImageFont.load_default()
        return self.fallback if arabic or self.own is None else self.own

    def __getattr__(self, k):
        if k.startswith("__") or k in ("own", "fallback", "brand", "fb_face"):
            raise AttributeError(k)
        return getattr(self.for_text(""), k)


def _text_block(d: ImageDraw.ImageDraw, text: str, font, cx: int, cy: int, fill, line_gap=1.3, max_chars=24,
                shadow=True):
    from .ae_builder import wrap_lines
    font = font.for_text(text) if hasattr(font, "for_text") else font     # G72: Arabic without an Arabic brand font
    lines = wrap_lines(text, max_chars).split("\r")
    if getattr(font, "engine", None) in ("coretext", "harfbuzz"):
        im = d._image
        asc, desc = font.getmetrics()
        lh = int((asc + desc) * line_gap)
        y = cy - lh * len(lines) // 2
        boxes = []
        col = tuple(fill) + ((255,) if len(fill) == 3 else ())
        for l in lines:
            img, base, w = font.render(l, col)
            x = int(cx - w / 2) - 4
            if shadow:
                sh, _, _ = font.render(l, (0, 0, 0, 110))
                im.alpha_composite(sh, (max(0, x + 3), max(0, y + 4))) if im.size[0] > 1 else None
            if im.size[0] > 1:
                im.alpha_composite(img, (max(0, x), max(0, y)))
            boxes.append((x + 4, y + 4, x + 4 + w, y + 4 + asc + desc))
            y += lh
        return boxes
    shaped = [_shape(l) for l in lines]
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * line_gap)
    total = lh * len(lines)
    y = cy - total // 2
    boxes = []
    for s in shaped:
        w = d.textlength(s, font=font)
        x = cx - w / 2
        if shadow:
            d.text((x + 3, y + 4), s, font=font, fill=(0, 0, 0, 110))
        d.text((x, y), s, font=font, fill=fill)
        boxes.append((x, y, x + w, y + asc + desc))
        y += lh
    return boxes


def _round_rect(im, box, r, fill=None, outline=None, width=2):
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(lay).rounded_rectangle(box, r, fill=fill, outline=outline, width=width)
    im.alpha_composite(lay)


def _face_center(im: Image.Image):
    """Centre of the detected faces (0..1, top-left origin): macOS Vision, else OpenCV (Windows/Linux); None if
    unavailable or no face (the crop then sits slightly above centre)."""
    return _face_center_vision(im) or _face_center_opencv(im)


def _face_center_vision(im: Image.Image):
    try:
        import io
        import Vision
        from Foundation import NSData
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "PNG")
        data = NSData.dataWithBytes_length_(buf.getvalue(), len(buf.getvalue()))
        req = Vision.VNDetectFaceRectanglesRequest.alloc().init()
        h = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
        if not h.performRequests_error_([req], None)[0]:
            return None
        faces = [o.boundingBox() for o in (req.results() or [])]
        if not faces:
            return None
        x0 = min(f.origin.x for f in faces); x1 = max(f.origin.x + f.size.width for f in faces)
        y0 = min(f.origin.y for f in faces); y1 = max(f.origin.y + f.size.height for f in faces)
        return (x0 + x1) / 2, 1 - (y0 + y1) / 2          # Vision's origin is bottom-left
    except Exception:
        return None


def _face_center_opencv(im: Image.Image):
    try:
        import cv2
        import numpy as np
        g = np.array(im.convert("L"))
        sc = min(1.0, 1200 / max(g.shape))               # detector works on a ~1200 px copy
        if sc < 1:
            g = cv2.resize(g, (int(g.shape[1] * sc), int(g.shape[0] * sc)))
        mins = (int(0.06 * g.shape[1]),) * 2
        det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = list(det.detectMultiScale(g, scaleFactor=1.1, minNeighbors=6, minSize=mins))
        if not faces:   # speaker turned sideways: profile detector, both directions (it only knows one)
            prof = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
            faces = list(prof.detectMultiScale(g, scaleFactor=1.1, minNeighbors=5, minSize=mins))
            flipped = prof.detectMultiScale(cv2.flip(g, 1), scaleFactor=1.1, minNeighbors=5, minSize=mins)
            faces += [(g.shape[1] - x - w, y, w, h) for (x, y, w, h) in flipped]
        if not faces:
            return None
        big = max(f[2] * f[3] for f in faces)            # ignore tiny background faces
        faces = [f for f in faces if f[2] * f[3] >= 0.25 * big]
        x0 = min(f[0] for f in faces); x1 = max(f[0] + f[2] for f in faces)
        y0 = min(f[1] for f in faces); y1 = max(f[1] + f[3] for f in faces)
        return (x0 + x1) / 2 / g.shape[1], (y0 + y1) / 2 / g.shape[0]
    except Exception:
        return None


def _fit_image(path: str, w: int, h: int, radius: int, centering=None) -> Image.Image:
    """Cover-crop to w x h. An explicit `centering` (params.crop_center, 0..1) wins; otherwise the crop is centred on
    the detected faces so eyes are never cut; otherwise slightly above centre."""
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGBA")
    c = centering
    if c is None:
        fc = _face_center(im)
        if fc:   # convert "face centre" into Pillow's crop offset so the face lands at the centre of the crop
            sw, sh = im.size
            cw_, ch_ = (sw, sw * h / w) if sw / sh < w / h else (sh * w / h, sh)
            c = ((fc[0] * sw - cw_ / 2) / (sw - cw_) if sw > cw_ + 1 else 0.5,
                 (fc[1] * sh - ch_ / 2) / (sh - ch_) if sh > ch_ + 1 else 0.5)
    c = c or (0.5, 0.35)
    im = ImageOps.fit(im, (w, h), centering=(min(max(c[0], 0.0), 1.0), min(max(c[1], 0.0), 1.0)))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
    im.putalpha(mask)
    return im


BAR_TEMPLATES = {"hook_title", "term_callout", "statement_highlight", "highlight_caption"}


def _role_color(b: "Brand", role: str) -> tuple:
    """Brand colour by role name (templates choose box_role / text_role): primary | neutral_light | paper | ink."""
    return {"primary": b.teal, "neutral_light": b.white, "paper": b.paper, "ink": b.ink}.get(role, b.teal)


def _hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(int(c) for c in rgb[:3])


def _readable_over_frame(col: tuple, boxes: list, probe, size: float, b: "Brand", label: str, notes) -> tuple:
    """Text drawn straight over the footage (no box behind it) in a brand colour: measure it against the frame region
    behind each line (WCAG contrast, see legibility.py) and fall back to white / paper when it is too faint (a brown
    brand primary on a warm set read 1.1-1.5:1). White and paper themselves are left alone. `probe` is the frame (1080x1920)
    or a callable returning it; a warning goes to `notes` when the colour had to change."""
    if tuple(col) in (tuple(b.white), tuple(b.paper)):
        return col
    frame = probe() if callable(probe) else probe
    if frame is None:
        return col
    from .legibility import legible, region_mean
    r = legible(col, [region_mean(frame, bx) for bx in boxes], size, [("white", b.white), ("paper", b.paper)])
    if notes is not None and (r["fallback"] or r["ratio"] < r["need"]):
        notes.append(f"{label}: text colour {_hex(col)} has contrast {r['original_ratio']:.1f}:1 against the frame behind it "
                     f"(needs {r['need']:.1f}:1)" + (f" - drawn in {r['name']} ({r['ratio']:.1f}:1) instead" if r["fallback"]
                                                    else " - kept, white is no better on this frame"))
    return r["rgb"]


def save_still(im: Image.Image, out: Path) -> Path:
    """Write a still only when its pixels changed. Unchanged stills are never rewritten: on Windows Premiere keeps the
    stills it imported locked (even after the project closes, until Premiere quits), and a rebuild must not fail on them."""
    import io
    out.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    data = buf.getvalue()
    try:
        if out.exists() and out.read_bytes() == data:
            return out
    except OSError:
        pass
    try:
        out.write_bytes(data)
    except PermissionError as e:
        raise RuntimeError(f"{out.name} changed but is locked by another program. On Windows Premiere locks stills it "
                           f"imported until it quits: quit Premiere (File > Exit), reopen it, then run this again.") from e
    return out


def render_event(ev: dict, t: dict, b: Brand, assets: dict, logo: str | None, out: Path, frame_bg=None,
                 layer: str = "all", probe=None, notes: list | None = None, size: tuple | None = None) -> Path:
    """layer: 'all' | 'bars' (teal bars/boxes only) | 'fg' (everything except bars) -> separate stills so
    Premiere can animate bars (RTL crop sweep) and text (pop) independently.
    probe: the frame behind the graphic (a frame-sized image, or a callable returning it). It never reaches the still; it only
    decides whether a brand-coloured text drawn straight over the footage is readable (else white/paper + a line in `notes`).
    size: the frame (width, height); default the profile's (common.frame_size). The layout (style.json y, sizes) is in pixels."""
    W, H = size or frame_size()
    BARS, FG = layer in ("all", "bars"), layer in ("all", "fg")
    tp, p = ev["template"], ev["params"]
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if layer == "bars" and tp not in BAR_TEMPLATES:   # nothing to sweep for this template
        return save_still(im, out)
    if tp in ("hook_title", "term_callout", "statement_highlight", "highlight_caption"):
        box_c, txt_c = _role_color(b, t.get("box_role", "primary")), _role_color(b, t.get("text_role", "neutral_light"))
        role = {"hook_title": "headline", "term_callout": "term", "statement_highlight": "body", "highlight_caption": "caption"}[tp]
        f = b.font(role, p.get("size", t["size"]))
        mc = p.get("max_chars", t.get("max_chars", 22 if tp != "highlight_caption" else 30))
        gap = t.get("line_gap", 1.3)
        y = p.get("y", t["y"])
        boxes = _text_block(ImageDraw.Draw(Image.new("RGBA", (1, 1))), p["text"], f, W // 2, y, b.white,
                            line_gap=gap, max_chars=mc, shadow=False)
        # box_all (profile): every caption on a translucent box (readable on light backgrounds); keyword cues keep the
        # brand box
        plain_box = tp == "highlight_caption" and not p.get("highlight") and (t.get("box_all") or p.get("on_fill"))
        alpha = int(255 * t.get("plain_box_alpha", 0.6)) if plain_box else 255
        if plain_box:
            box_c = _role_color(b, t.get("plain_box_role", "ink"))
        if probe is not None and (tp == "term_callout" or (tp == "hook_title" and t.get("bar_style", "underline") != "box")
                                  or (tp == "highlight_caption" and not p.get("highlight") and not plain_box)):
            txt_c = _readable_over_frame(txt_c, boxes, probe, p.get("size", t["size"]), b,
                                         f"{ev.get('event_id', tp)} ({tp})", notes)
        if BARS and (tp != "highlight_caption" or p.get("highlight") or plain_box):
            for (x0, y0, x1, y1) in boxes:
                if tp == "hook_title" and t.get("bar_style", "underline") == "box":   # same teal box as statements
                    px, py = t.get("pad_x", 22), t.get("pad_y", 8)
                    _round_rect(im, (x0 - px, y0 - py, x1 + px, y1 + py - 4), 8, fill=box_c + (255,))
                elif tp == "hook_title":
                    hh = (y1 - y0) * 0.42
                    _round_rect(im, (x0 - 24, y1 - hh - 6, x1 + 24, y1), 4, fill=box_c + (255,))
                elif tp == "term_callout":
                    _round_rect(im, (x0 - 10, y1 + 6, x1 + 10, y1 + 14), 4, fill=box_c + (255,))
                else:  # full box behind each line
                    px, py = t.get("pad_x", 22), t.get("pad_y", 8)
                    _round_rect(im, (x0 - px, y0 - py, x1 + px, y1 + py - 4), 8, fill=box_c + (alpha,))
        if FG:
            _text_block(ImageDraw.Draw(im), p["text"], f, W // 2, y, txt_c, line_gap=gap, max_chars=mc,
                        shadow=((tp == "hook_title" and t.get("bar_style", "underline") != "box") or tp == "term_callout"
                                or (tp in ("statement_highlight", "highlight_caption") and not p.get("highlight"))))
    elif tp == "glass_card":
        f = b.font("body", p.get("size", t["size"]))
        probe = _text_block(ImageDraw.Draw(Image.new("RGBA", (1, 1))), p["text"], f, W // 2, p.get("y", t["y"]), b.white, line_gap=1.35, max_chars=26, shadow=False)
        y0, y1 = min(bx[1] for bx in probe) - 45, max(bx[3] for bx in probe) + 45
        w = p.get("w", t["w"])
        if frame_bg is not None:  # simulate frosted backdrop on preview only
            crop = frame_bg.crop((W // 2 - w // 2, int(y0), W // 2 + w // 2, int(y1))).filter(ImageFilter.GaussianBlur(28))
            m = Image.new("L", crop.size, 0)
            ImageDraw.Draw(m).rounded_rectangle((0, 0, crop.size[0] - 1, crop.size[1] - 1), t["radius"], fill=255)
            im.paste(crop.convert("RGBA"), (W // 2 - w // 2, int(y0)), m)
        _round_rect(im, (W // 2 - w // 2, y0, W // 2 + w // 2, y1), t["radius"],
                    fill=b.white + (int(255 * t["fill_opacity"]),), outline=b.white + (int(255 * t["stroke_opacity"]),), width=3)
        ix, iy = W // 2 + w // 2 - 30, int(y0) + 14
        _round_rect(im, (ix - 14, iy - 30, ix + 30, iy + 14), 8, outline=b.white + (200,), width=3)
        _round_rect(im, (ix - 24, iy - 20, ix + 20, iy + 24), 8, fill=b.white + (70,), outline=b.white + (255,), width=3)
        _text_block(ImageDraw.Draw(im), p["text"], f, W // 2, p.get("y", t["y"]), b.white, line_gap=1.35, max_chars=26, shadow=False)
    elif tp == "checklist":
        items = p.get("items", [])
        gap = p.get("line_gap", t["line_gap"])
        n_rows = p.get("_row_count", len(items))     # rows reserved for the FULL list (stable layout per item still)
        off = p.get("_row_offset", 0)
        top = p.get("y", t["y"]) - (n_rows - 1) * gap // 2
        if p.get("title") and not p.get("_no_title"):
            _text_block(d, p["title"], b.font("body", t["title_size"]), W // 2, int(top - gap * 1.1), b.white)
        f = b.font("body", t["size"])
        for i, it in enumerate(items):
            y = top + (i + off) * gap
            bx = _text_block(d, it["text"], f, W // 2 - 20, y, b.white, max_chars=40)
            x1 = bx[0][2]
            d.ellipse((x1 + 18, y - 13, x1 + 44, y + 13), outline=b.white, width=3)
    elif tp == "broll_card":
        im = Image.new("RGBA", (W, H), b.paper + (255,))
        d = ImageDraw.Draw(im)
        _text_block(d, p.get("headline") or p.get("text", ""), b.font("body", p.get("size", t["size"])), W // 2, t["headline_y"], b.ink, shadow=False)
        cw, ch, cy = t["card_w"], t["card_h"], t["card_y"]
        src = p.get("image_path")
        if src:
            card = _fit_image(src, cw, ch, 40, p.get("crop_center"))
            sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(sh).rounded_rectangle((W // 2 - cw // 2 + 10, cy - ch // 2 + 18, W // 2 + cw // 2 + 10, cy + ch // 2 + 18), 40, fill=(0, 0, 0, 90))
            im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(22)))
            im.alpha_composite(card, (W // 2 - cw // 2, cy - ch // 2))
        else:
            _round_rect(im, (W // 2 - cw // 2, cy - ch // 2, W // 2 + cw // 2, cy + ch // 2), 40, fill=b.white + (140,), outline=b.teal + (255,), width=4)
            _text_block(ImageDraw.Draw(im), "IMAGE PLACEHOLDER — needs approved visual", b.font("small", 30), W // 2, cy, b.ink, shadow=False, max_chars=40)
    elif tp == "photo_card":
        cw, ch, cy = t["card_w"], t["card_h"], t["card_y"]
        if p.get("image_path"):
            im.alpha_composite(_fit_image(p["image_path"], cw, ch, 36, p.get("crop_center")), (W // 2 - cw // 2, cy - ch // 2))
            _round_rect(im, (W // 2 - cw // 2, cy - ch // 2, W // 2 + cw // 2, cy + ch // 2), 36, outline=b.white + (255,), width=4)
        if logo:
            lg = Image.open(logo).convert("RGBA")
            lg.thumbnail((180, 180))
            im.alpha_composite(lg, (W // 2 - lg.width // 2, cy - ch // 2 - 70 - lg.height // 2))
        if p.get("text"):
            _text_block(ImageDraw.Draw(im), p["text"], b.font("body", t["size"]), W // 2, cy + ch // 2 + 90, b.white)
    elif tp == "name_card":
        y, w = p.get("y", t["y"]), p.get("w", t["w"])
        lines = p.get("lines", [])
        h = 170 + 50 * len(lines)
        _round_rect(im, (W // 2 - w // 2, y - 120, W // 2 + w // 2, y - 120 + h), 26, fill=b.white + (30,), outline=b.white + (216,), width=3)
        d = ImageDraw.Draw(im)
        _text_block(d, p["name"], b.font("headline", t["name_size"]), W // 2, y - 70, b.white)
        d.line((W // 2 - (w - 160) // 2, y - 25, W // 2 + (w - 160) // 2, y - 25), fill=b.white + (204,), width=2)
        for i, l in enumerate(lines):
            _text_block(d, l, b.font("small", t["line_size"]), W // 2, y + 22 + i * 50, b.white, max_chars=60)
    elif tp == "cta":
        f = b.font("headline", p.get("size", t["size"]))
        boxes = _text_block(ImageDraw.Draw(Image.new("RGBA", (1, 1))), p["text"], f, W // 2, p.get("y", t["y"]), b.white, shadow=False)
        x0, y0 = min(bx[0] for bx in boxes), min(bx[1] for bx in boxes)
        x1, y1 = max(bx[2] for bx in boxes), max(bx[3] for bx in boxes)
        _round_rect(im, (x0 - 45, y0 - 22, x1 + 45, y1 + 22), int((y1 - y0 + 44) / 2),
                    fill=_role_color(b, t.get("box_role", "primary")) + (255,))
        _text_block(ImageDraw.Draw(im), p["text"], f, W // 2, p.get("y", t["y"]),
                    _role_color(b, t.get("text_role", "neutral_light")), shadow=False)
    elif tp == "stat_card":
        # big value (white, readable whatever the brand colour) on a dense ink card, a brand-primary accent bar under
        # it, one label line below
        y, w = p.get("y", t["y"]), p.get("w", t["w"])
        fv, fl = b.font("headline", p.get("value_size", t["value_size"])), b.font("body", p.get("label_size", t["label_size"]))
        vy, ly = y - 55, y + 95
        probe_d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        vb = _text_block(probe_d, str(p["value"]), fv, W // 2, vy, b.white, max_chars=12, shadow=False)
        lb = _text_block(probe_d, p.get("label", ""), fl, W // 2, ly, b.white, max_chars=28, shadow=False) \
            if p.get("label") else []
        y0 = min(bx[1] for bx in vb) - 45
        y1 = max(bx[3] for bx in (lb or vb)) + 45
        w = min(max(w, max(bx[2] - bx[0] for bx in vb + lb) + 120), W - 100)
        if frame_bg is not None:  # frosted backdrop on the QC preview only
            crop = frame_bg.crop((W // 2 - w // 2, int(y0), W // 2 + w // 2, int(y1))).filter(ImageFilter.GaussianBlur(28))
            m = Image.new("L", crop.size, 0)
            ImageDraw.Draw(m).rounded_rectangle((0, 0, crop.size[0] - 1, crop.size[1] - 1), t["radius"], fill=255)
            im.paste(crop.convert("RGBA"), (W // 2 - w // 2, int(y0)), m)
        _round_rect(im, (W // 2 - w // 2, y0, W // 2 + w // 2, y1), t["radius"],
                    fill=b.ink + (int(255 * t["fill_opacity"]),), outline=b.white + (int(255 * t["stroke_opacity"]),), width=3)
        bar_y = max(bx[3] for bx in vb) + 8
        _round_rect(im, (W // 2 - 70, bar_y, W // 2 + 70, bar_y + 9), 4, fill=_role_color(b, t.get("accent_role", "primary")) + (255,))
        d2 = ImageDraw.Draw(im)
        _text_block(d2, str(p["value"]), fv, W // 2, vy, b.white, max_chars=12, shadow=True)
        if p.get("label"):
            _text_block(d2, p["label"], fl, W // 2, ly, b.white, max_chars=28, shadow=False)
    elif tp == "context_card":
        # one editorial line in a brand pill near the top: what came before this moment
        f = b.font("body", p.get("size", t["size"]))
        y, mc = p.get("y", t["y"]), p.get("max_chars", t["max_chars"])
        boxes = _text_block(ImageDraw.Draw(Image.new("RGBA", (1, 1))), p["text"], f, W // 2, y, b.white, max_chars=mc,
                            shadow=False)
        px, py = t.get("pad_x", 34), t.get("pad_y", 18)
        x0, y0 = max(40, min(bx[0] for bx in boxes) - px), min(bx[1] for bx in boxes) - py
        x1, y1 = min(W - 40, max(bx[2] for bx in boxes) + px), max(bx[3] for bx in boxes) + py
        _round_rect(im, (x0, y0, x1, y1), int(min(48, (y1 - y0) / 2)), fill=_role_color(b, t.get("box_role", "primary")) + (235,))
        _text_block(ImageDraw.Draw(im), p["text"], f, W // 2, y, _role_color(b, t.get("text_role", "neutral_light")),
                    max_chars=mc, shadow=False)
    elif tp == "logo_outro":
        im = Image.new("RGBA", (W, H), b.white + (255,))
        if logo:
            lg = Image.open(logo).convert("RGBA")
            lg.thumbnail((780, 780))
            im.alpha_composite(lg, (W // 2 - lg.width // 2, H // 2 - lg.height // 2))
    elif tp == "broll_video":   # QC/contact-sheet still only; Premiere gets the real clip from the XML
        fr = grab_frame(Path(p["video_path"]), int(float(p.get("in", 0) or 0) * 1000) + 500, (W, H)) if p.get("video_path") else None
        im = fr if fr is not None else Image.new("RGBA", (W, H), (40, 40, 40, 255))
    elif tp == "flash_transition":
        im = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * t.get("peak_opacity", 0.9))))
    return save_still(im, out)


def grab_frame(video: Path, ms: int, size: tuple | None = None) -> Image.Image | None:
    """The source frame at ms, cropped to fill the W x H sequence frame (RGBA; the profile's size by default), or None.
    Through a pipe: the old version left a temp PNG and its descriptor behind on every call (MI-9)."""
    from .media_util import grab_frame as _grab
    W, H = size or frame_size()
    return _grab(video, ms / 1000, W, H, fit="crop", mode="RGBA")


# --------------------------------------------------------------------------- what each still was drawn from (3.0 F1)
# `reel previews` records, per event, a hash of everything its stills are drawn from (the event as compiled, its
# template, the brand, the frame, the footage the readability check looks at, the drawing code) and the hash of each file
# it wrote, plus the plan fingerprint (lib/plan.py). Every build that places stills compares that record with the plan as
# it is now (ensure_fresh_stills): a still drawn from an older plan is redrawn through render_all, never placed with
# outdated wording.
STILLS_MANIFEST = "03_broll/.stills-manifest.json"
MANIFEST_FORMAT = 1
_RENDERER_SOURCES = ("previews.py", "font_roles.py", "fonts.py", "hb_text.py", "ct_text.py", "legibility.py")


def _sha256(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _file_sha(path) -> str | None:
    try:
        return _sha256(Path(path).read_bytes())
    except (OSError, TypeError):
        return None


def _canon(obj) -> str:
    import json
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def renderer_version() -> str:
    """The engine version plus a hash of the drawing code: a still drawn by other code is redrawn."""
    import hashlib
    from .stamps import engine_version
    h = hashlib.sha256()
    for name in _RENDERER_SOURCES:
        f = Path(__file__).with_name(name)
        h.update(name.encode())
        h.update(f.read_bytes().replace(b"\r\n", b"\n") if f.exists() else b"-")
    return f"{engine_version()}+{h.hexdigest()[:12]}"


def still_files(ev: dict) -> list[str]:
    """Every still render_all writes for one event, relative to the reel folder."""
    eid, cat = ev["event_id"], still_category(ev["template"])
    out = [f"03_broll/{cat}/{eid}.png"]
    if ev["template"] in BAR_TEMPLATES:
        out += [f"03_broll/{cat}/{eid}_fg.png", f"03_broll/{cat}/{eid}_bar.png"]
    if ev["template"] == "checklist":
        out.append(f"03_broll/{cat}/{eid}_title.png")
        out += [f"03_broll/{cat}/{eid}_i{k + 1}.png" for k in range(len(ev["params"].get("items", [])))]
    return out


def _no_timestamps(doc):
    """A brand file without its `generated` / `*_at` stamps: a client-db rebuild that changes nothing redraws nothing."""
    return {k: v for k, v in doc.items() if k != "generated" and not str(k).endswith("_at")} \
        if isinstance(doc, dict) else doc


def _shared_inputs(paths: Paths, spec: dict, asset_manifest: dict) -> dict:
    """What every still of the reel is drawn from: the drawing code, the frame, the brand (colours, fonts, logo) and the
    footage the readability check looks at."""
    db = paths.client_db
    typ = read_json(db / "branding/typography.json", {}) or {}
    fonts = sorted({str(w.get("file")) for fam in (typ.get("families") or {}).values() if isinstance(fam, dict)
                    for w in fam.get("weights", []) if isinstance(w, dict) and w.get("file")})
    logo = next((a.get("display_derivative") for a in asset_manifest.get("assets", [])
                 if isinstance(a, dict) and a.get("category") == "logo"), None)
    brand_cfg = load_config("brand.json") or {}
    main = spec.get("main_footage")
    foot = (Path(main) if Path(main).is_absolute() else paths.root / main) if main else None
    return {"renderer": renderer_version(), "frame": list(frame_size(paths)),
            "brand_tokens": _no_timestamps(read_json(db / "branding/brand-tokens.json", {}) or {}),
            "typography": _no_timestamps(typ), "fonts": {f: _file_sha(f) for f in fonts},
            "brand_fallbacks": [brand_cfg.get("fallback_colors"), brand_cfg.get("font_roles_fallback")],
            "logo": [logo, _file_sha(logo) if logo else None],
            "footage": [main, foot.stat().st_size if foot and foot.exists() else None, spec.get("source_in_ms")]}


def _event_inputs(paths: Paths, ev: dict, tpls: dict, shared: dict, assets: dict) -> str:
    """Hash of everything one event's stills are drawn from (the event as compiled, before render_all adds paths)."""
    img = (ev.get("params") or {}).get("image")
    img_sha = None
    if img:
        a = assets.get(img)
        img_sha = _file_sha(a["display_derivative"] if a else paths.root / img)
    body = {"shared": shared, "event": ev, "template": tpls.get(ev["template"]), "image": img_sha}
    return _sha256(_canon(body).encode("utf-8"))


def _drawing_context(paths: Paths, spec: dict) -> tuple[dict, dict, dict, dict]:
    """(templates, assets by rel, the asset manifest, shared inputs): read once per render or check."""
    tpls = load_config("graphics-templates.json")["templates"]
    man = read_json(paths.client_db / "asset-manifest.json", {"assets": []}) or {"assets": []}
    assets = {a["rel"]: a for a in man.get("assets", []) if isinstance(a, dict) and "rel" in a}
    return tpls, assets, man, _shared_inputs(paths, spec, man)


def stale_stills(paths: Paths, spec: dict | None = None) -> dict:
    """{"stale": [event_id, ...] in plan order, "why": {event_id: reason}}: the events whose stills were not drawn from
    the plan as it is now (no record of them, the plan or brand changed, a still missing or changed on disk)."""
    import copy
    from .stamps import read_compiled
    if spec is None:
        spec = read_compiled(paths.p("01_analysis/timeline-spec.json"))
    if not spec:
        return {"stale": [], "why": {}}
    rec = read_json(paths.p(STILLS_MANIFEST), None)
    have_all = (rec.get("events") or {}) if isinstance(rec, dict) and rec.get("format") == MANIFEST_FORMAT else {}
    tpls, assets, _man, shared = _drawing_context(paths, spec)
    stale, why = [], {}
    for ev in spec["events"]:
        eid = ev["event_id"]
        have = have_all.get(eid)
        reason = None
        if not isinstance(have, dict):
            reason = "no record of how it was drawn (drawn by an older WhyNot Cut, or never drawn)"
        elif have.get("inputs") != _event_inputs(paths, copy.deepcopy(ev), tpls, shared, assets):
            reason = "the plan, the brand or the drawing code changed since it was drawn"
        else:
            files = have.get("files") or {}
            for rel in still_files(ev):
                if rel not in files or not paths.p(rel).exists():
                    reason = f"{Path(rel).name} is missing"
                    break
                if _file_sha(paths.p(rel)) != files[rel]:
                    reason = f"{Path(rel).name} was changed after it was drawn"
                    break
        if reason:
            stale.append(eid)
            why[eid] = reason
    return {"stale": stale, "why": why}


def ensure_fresh_stills(paths: Paths) -> dict:
    """Before stills are placed (ppro-build, the serve build, the preview video, the XML fallback): redraw, through
    render_all (the `reel previews` code), the stills that were not drawn from the plan as it is now. Stills that match
    are not touched (no work, no write). {"redrawn": [event_id, ...], "why": {...}, "warnings": [...]}. A redraw that
    fails, or leaves a still that still does not match, raises Guidance (with `stills_out_of_date`) and the one fix."""
    from .errors import Guidance
    st = stale_stills(paths)
    if not st["stale"]:
        return {"redrawn": [], "why": {}, "warnings": []}
    error = f"The graphics {', '.join(st['stale'])} were drawn from an older version of the plan, and redrawing them stopped"
    how = "Run `reel previews` to redraw the graphics, fix what it reports, then build again."
    try:
        r = render_all(paths, composite_preview=True, only=set(st["stale"]))
    except Guidance as e:
        raise _stills_guidance(f"{error}: {e.error}", e.how or how) from e
    except Exception as e:  # noqa: BLE001 — a locked file, a font that cannot be read, ...: one plain fix
        raise _stills_guidance(f"{error}: {e}", how) from e
    left = stale_stills(paths)["stale"]
    if left:
        raise _stills_guidance(f"The graphics {', '.join(left)} still do not match the plan after redrawing them", how)
    return {"redrawn": st["stale"], "why": st["why"], "warnings": r.get("warnings") or []}


def _stills_guidance(error: str, how: str):
    from .errors import Guidance
    g = Guidance(error, how)
    g.stills_out_of_date = True
    return g


def _write_manifest(paths: Paths, spec: dict, records: dict, only: set | None) -> None:
    """The record of a full render replaces the old one; a partial one (`only`) keeps the other events' entries."""
    from .plan import plan_fingerprint
    old = read_json(paths.p(STILLS_MANIFEST), None) if only is not None else None
    keep = (old.get("events") or {}) if isinstance(old, dict) and old.get("format") == MANIFEST_FORMAT else {}
    events = {}
    for ev in spec["events"]:
        eid = ev["event_id"]
        if eid in records or eid in keep:
            events[eid] = records.get(eid) or keep[eid]
    try:
        fp = plan_fingerprint(paths)
    except (OSError, ValueError):
        fp = None
    write_json(paths.p(STILLS_MANIFEST), {"format": MANIFEST_FORMAT, "generated": now_iso(), "plan_fingerprint": fp,
                                          "renderer": renderer_version(), "events": events})


def render_all(paths: Paths, composite_preview: bool = True, only: set | None = None) -> dict:
    """`reel previews`: every event's stills (and QC composites), recorded in STILLS_MANIFEST. `only` (a set of event
    ids) redraws just those events and keeps the record of the others (ensure_fresh_stills)."""
    import copy
    from .common import spec_footage
    from .stamps import read_compiled
    spec = read_compiled(paths.p("01_analysis/timeline-spec.json"))
    if not spec:
        from .errors import Guidance
        raise Guidance("no compiled plan yet (01_analysis/timeline-spec.json)", "Run `reel plan` first")
    main = spec_footage(paths, spec)
    size = frame_size(paths)
    W, H = size
    tpls, assets, man, shared = _drawing_context(paths, spec)
    b = Brand(paths.client_db)
    logo = next((a["display_derivative"] for a in man["assets"] if a["category"] == "logo"), None)
    outs, comps, warns, records = [], [], [], {}
    for ev in spec["events"]:
        if only is not None and ev["event_id"] not in only:
            continue
        inputs = _event_inputs(paths, copy.deepcopy(ev), tpls, shared, assets)     # before the paths are added below
        p = ev["params"]
        if p.get("image"):
            a = assets.get(p["image"])
            p["image_path"] = a["display_derivative"] if a else str(paths.root / p["image"])
        if p.get("video"):
            p["video_path"] = str(paths.root / p["video"])
        cat = still_category(ev["template"])
        out = paths.p(f"03_broll/{cat}/{ev['event_id']}.png")
        # the background frame is a SOURCE frame: after pause removal / word cuts start_ms is on the reel's timeline
        mid = (ev.get("src_start_ms", ev["start_ms"]) + ev.get("src_end_ms", ev["end_ms"])) // 2
        # the frame behind the graphic, grabbed only when a brand-coloured text has to be measured against it (or for the
        # QC composite below)
        grabbed = []

        def probe(mid=mid):
            if not grabbed:
                grabbed.append(grab_frame(main, mid + int(spec.get("source_in_ms") or 0), size))
            return grabbed[0]
        # PRODUCTION still: clean transparent overlay (never bake footage into it; the speaker moves)
        render_event(ev, tpls[ev["template"]], b, assets, logo, out, frame_bg=None, probe=probe, notes=warns, size=size)
        outs.append(str(out))
        if ev["template"] in BAR_TEMPLATES:   # separate layers: text (pop) + bars (RTL sweep)
            fg = paths.p(f"03_broll/{cat}/{ev['event_id']}_fg.png")
            bars = paths.p(f"03_broll/{cat}/{ev['event_id']}_bar.png")
            render_event(ev, tpls[ev["template"]], b, assets, logo, fg, layer="fg", probe=probe, size=size)
            render_event(ev, tpls[ev["template"]], b, assets, logo, bars, layer="bars", size=size)
            outs += [str(fg), str(bars)]
        if ev["template"] == "checklist":
            # title still + one still per item in its final row -> items slide in one by one in Premiere
            items = ev["params"].get("items", [])
            ttl = dict(ev, params=dict(ev["params"], items=[], _row_count=len(items)))
            tp_ = paths.p(f"03_broll/{cat}/{ev['event_id']}_title.png")
            render_event(ttl, tpls["checklist"], b, assets, logo, tp_, size=size)
            outs.append(str(tp_))
            for k, it in enumerate(items):
                one = dict(ev, params=dict(ev["params"], items=[it], _row_count=len(items), _row_offset=k, _no_title=True))
                ip = paths.p(f"03_broll/{cat}/{ev['event_id']}_i{k + 1}.png")
                render_event(one, tpls["checklist"], b, assets, logo, ip, size=size)
                outs.append(str(ip))
        records[ev["event_id"]] = {"template": ev["template"], "inputs": inputs,
                                   "files": {rel: _file_sha(paths.p(rel)) for rel in still_files(ev)}}
        bg = probe() if composite_preview else None
        if bg is not None:  # QC composite only: graphic over the actual frame (frosted look simulated)
            import tempfile
            fd, tmp = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            tmp = Path(tmp)
            render_event(ev, tpls[ev["template"]], b, assets, logo, tmp, frame_bg=bg, probe=probe, size=size)
            comp = bg.copy()
            with Image.open(tmp) as im:
                comp.alpha_composite(im.convert("RGBA"))
            tmp.unlink(missing_ok=True)
            cp = paths.p(f"08_quality_control/previews/{ev['event_id']}_{ev['template']}.jpg")
            cp.parent.mkdir(parents=True, exist_ok=True)
            comp.convert("RGB").resize((540, round(540 * H / W))).save(cp, quality=85)
            comps.append(str(cp))
    _write_manifest(paths, spec, records, only)
    sheet = comps
    if only is not None and comps:      # a partial redraw: the sheet still shows every graphic of the plan
        sheet = [str(c) for c in (paths.p(f"08_quality_control/previews/{e['event_id']}_{e['template']}.jpg")
                                  for e in spec["events"]) if c.exists()]
    # contact sheet of composites: exactly one tile per composite (G73: it was half empty, 6 columns for 3 tiles)
    if sheet:
        from .media_util import contact_sheet
        contact_sheet([(c, "") for c in sheet], paths.p("08_quality_control/previews/_contact_sheet.jpg"),
                      cols=6, tile_w=270, tile_h=round(270 * H / W))
    warns += [w for w in b.font_warnings() if w not in warns]
    return {"previews": outs, "composites": comps, "warnings": warns}


SAFE_TOP_PX = 220   # platform UI covers the top of a 1080x1920 reel


def caption_text(text: str, strip: str | None = None) -> str:
    """Burned caption text on one line, minus the punctuation the client's style removes (e.g. commas: «احذف
    الفواصل … واستخدم "…" فقط»); with stripping on, "..." becomes "…"."""
    out = " ".join((text or "").split())
    if strip:
        out = out.replace("...", "…")
        out = " ".join("".join(ch for ch in out if ch not in strip).split())
    return out


def render_captions(paths: Paths, hidden_ms: list, avoid: list | None = None,
                    warnings: list | None = None) -> list[dict]:
    """Animated caption stills on the SEQUENCE clock: text (pop) + teal box (RTL sweep) on keyword cues.
    Cues under a graphic that already shows the words are trimmed/dropped (reference behaviour). `warnings` (a list)
    receives the G72 font warnings (Arabic captions drawn with a system fallback, or no Arabic font at all)."""
    from . import srt as srtlib
    from .plan import norm
    size = frame_size(paths)
    W, H = size
    from .stamps import read_compiled
    spec = read_compiled(paths.p("01_analysis/timeline-spec.json"))
    ed = read_json(paths.p("01_analysis/edit-decisions.json"), {})
    t = load_config("graphics-templates.json")["templates"]["highlight_caption"]
    b = Brand(paths.client_db)
    style = ed.get("global", {}).get("caption_style", "keywords")
    hl = [norm(h["text"]) for h in spec.get("caption_highlights", [])]
    out_dir = paths.p("03_broll/captions")
    out_dir.mkdir(parents=True, exist_ok=True)
    res = []
    lead = int(t.get("lead_in_ms") or 0)          # a line appears slightly before the speech (client style)
    prev_end = 0
    # over a source card's blurred fill the background is bright: those captions get the translucent box even when the
    # client's captions are plain (white text on a light blur was hard to read in a live check)
    fps_ = float(spec.get("fps") or 24)
    fills = [(m["start_frame"] * 1000 / fps_, m["end_frame"] * 1000 / fps_) for m in spec.get("main_segments", [])
             if m.get("decision_id") == "AUTO_CUTAWAY"]
    for i, c in enumerate(srtlib.read_srt(paths.p(spec["caption_source"]))):
        s, e = c["start_ms"], c["end_ms"]
        if lead:
            s = max(prev_end, s - lead, 0)            # never over the previous line
        for a, z in hidden_ms:
            if a <= s < z:
                s = z
            elif s < a < e:
                e = a
        if e - s < 250:
            continue
        is_hl = style == "highlight_all" or any(h and h in norm(c["text"]) for h in hl)
        text = caption_text(c["text"], t.get("strip_punctuation"))
        if not text:
            continue
        ev = {"template": "highlight_caption", "params": {"text": text, "highlight": is_hl}}
        if any(s < b_ and a_ < e for a_, b_ in fills):
            ev["params"]["on_fill"] = True
        # a card (name card, glass card, CTA) overlaps the caption band at the same time: move the caption above the
        # card, or below it when there is no room above (a card at the top of the frame: seen on a real client)
        from .ae_builder import wrap_lines
        n = len(wrap_lines(ev["params"]["text"], t.get("max_chars", 30)).split("\r"))
        half = n * t["size"] * t.get("line_gap", 1.3) / 2 + t.get("bar_pad_y", 8)
        cards = [(av[2], av[3] if len(av) > 3 else H) for av in (avoid or []) if s < av[1] and av[0] < e]
        clash = [(top, bot) for top, bot in cards if not (bot < t["y"] - half - 12 or top > t["y"] + half + 12)]
        if clash:
            top, bot = min(c[0] for c in clash), max(c[1] for c in clash)
            up = top - half - 24
            ev["params"]["y"] = int(up) if up - half >= SAFE_TOP_PX else int(min(H - 300, bot + half + 24))
        fg = out_dir / f"CAP_{i + 1:03d}_fg.png"
        render_event(ev, t, b, {}, None, fg, layer="fg", size=size)
        item = {"id": f"CAP_{i + 1:03d}", "fg": str(fg), "start_ms": s, "end_ms": e, "highlight": is_hl, "text": text}
        prev_end = e
        if is_hl or t.get("box_all") or ev["params"].get("on_fill"):
            bar = out_dir / f"CAP_{i + 1:03d}_bar.png"
            render_event(ev, t, b, {}, None, bar, layer="bars", size=size)
            item["bar"] = str(bar)
        res.append(item)
    write_json(out_dir / "captions-manifest.json", {"generated": now_iso(), "captions": res})
    if warnings is not None:
        warnings += [w for w in b.font_warnings() if w not in warnings]
    return res
