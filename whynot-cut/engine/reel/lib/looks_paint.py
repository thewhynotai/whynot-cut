# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Drawing caption looks (R-4.1, Phase 4 Task 23): one caption cue becomes transparent full-frame layers.

  plate     clean and highlight: a soft drop plate (the text's own shape in brand ink, blurred, 4 px below, 35 %,
            no outline); boxed: a squared plate in brand ink with an accent foot along its bottom edge.
  underlay  highlight only: one low accent band across the line (from 35 % of the x-height above the baseline to
            20 % below it); `spans` give each word's band in frame pixels and its spoken time, so a builder crops or
            moves it from word to word (the band slides in the reading direction).
  fg        the text, word by word with each run in its own font (looks_type), and the static emphasis: the
            highlight colour, one weight heavier, or an accent tag behind the word.
Every colour pair is checked against what is really behind it (the frame's pixels when a frame is given, the plate
otherwise): a colour that falls short of legibility.needed(size) is stepped in lightness toward contrast, else the
look's neutral is used, with a note for the editor. Layers stack plate → underlay → fg.
"""
from __future__ import annotations

import colorsys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import looks
from .looks_type import Typesetter
from .motion_layout import contrast

EMPHASIS_NOTE_AR = "الكلمة المميزة اتغيّر لونها عشان تتقري على الخلفية الفاتحة"
EMPHASIS_NOTE_AR_DARK = "الكلمة المميزة اتغيّر لونها عشان تتقري على الخلفية الغامقة"
SAFE_TOP_PX = 220            # at 1920 px height: the platform UI covers the top of a reel (as previews.SAFE_TOP_PX)


def _blend(a: tuple, b: tuple, t: float) -> tuple:
    """a over b with opacity t."""
    return tuple(int(round(a[i] * t + b[i] * (1 - t))) for i in range(3))


def _lum(rgb) -> float:
    from .motion_layout import _lum as lum
    return lum(rgb)


def step_to_contrast(fg: tuple, bg, need: float, steps: int = 14, amount: float = 0.04) -> tuple | None:
    """`fg` with its lightness moved away from `bg` (darker on a light background, lighter on a dark one) until the
    contrast reaches `need`; None when it never does within `steps`. The hue and saturation are kept. `bg` may be a
    list of colours `fg` must read against (all of them; the direction follows their mean luminance)."""
    bgs = [tuple(bg)] if isinstance(bg, tuple) else [tuple(b) for b in bg]
    ok = lambda c: min(contrast(c, b) for b in bgs) + 1e-9 >= need
    if ok(fg):
        return tuple(fg)
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in fg[:3]))
    sign = -1 if sum(_lum(b) for b in bgs) / len(bgs) > 0.18 else 1
    for _ in range(steps):
        l = min(1.0, max(0.0, l + sign * amount))
        rgb = tuple(int(round(c * 255)) for c in colorsys.hls_to_rgb(h, l, s))
        if ok(rgb):
            return rgb
    return None


def _needed(size_px: float) -> float:
    from .legibility import needed
    return needed(size_px)


STRIP_PX = 40               # at 1080: the caption area is judged strip by strip, so busy footage is not averaged away


EXTREME = 0.10              # each strip is judged on its brightest and its darkest tenth, never on its mean


def _extremes(im, box) -> list[tuple]:
    """The mean colour of the brightest and of the darkest EXTREME of `box` (one colour when they are the same): a
    letter over a strip meets its brightest pixels (white text) or its darkest (ink text), not their average."""
    from PIL import ImageStat
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(im.width, x1), min(im.height, y1)
    if x1 <= x0 or y1 <= y0:
        return []
    crop = im.crop((x0, y0, x1, y1)).convert("RGB")
    lum = crop.convert("L")
    hist, n = lum.histogram(), crop.width * crop.height
    want = max(1, int(n * EXTREME))
    out = []
    for levels in (range(255, -1, -1), range(256)):          # brightest tenth, then darkest tenth
        acc, cut = 0, 0
        for v in levels:
            acc += hist[v]
            if acc >= want:
                cut = v
                break
        mask = lum.point(lambda v, c=cut, hi=levels.start == 255: 255 if (v >= c if hi else v <= c) else 0)
        c = tuple(int(round(m)) for m in ImageStat.Stat(crop, mask).mean[:3])
        if c not in out:
            out.append(c)
    return out


def _regions(frame, box, scale: float = 1.0) -> list | None:
    """The brightest and darkest colours of each vertical strip of `box` in `frame` (None without a frame). The worst
    one decides: over stripes or a busy set the average reads fine while some letters sit on a colour they vanish
    into, and inside one strip a bar edge or a window can hide behind the mean."""
    if frame is None:
        return None
    x0, y0, x1, y1 = box
    step = max(8.0, STRIP_PX * scale)
    out, x = [], x0
    while x1 - x >= 2:                     # a sliver under 2 px rounds to nothing
        out += [c for c in _extremes(frame, (x, y0, min(x1, x + step), y1)) if c not in out]
        x += step
    return out or _extremes(frame, box) or [(0, 0, 0)]


def _worst(c: tuple, bgs: list) -> float:
    return min(contrast(c, b) for b in bgs)


class CaptionPainter:
    """Draws one caption look. `chain`/`heavy` come from looks_type.font_chain (heavy: the `weight` emphasis);
    `palette` from looks.palette; `y` is the caption line's centre (default: the highlight_caption template's y,
    scaled to the frame); `entrance` "none" when a motion look keeps captions still."""

    def __init__(self, look: str, chain: dict, palette: dict, frame_size: tuple = (1080, 1920), heavy: dict | None = None,
                 emphasis: str = "colour", engine=None, cat: dict | None = None, y: float | None = None,
                 entrance: str | None = None, highlight: tuple | None = None):
        self.cat = cat or looks.caption_catalog()
        self.name = looks.legacy_look(look, self.cat)
        self.look = self.cat["looks"][self.name]
        self.pres = self.cat["presentations"][self.look["presentation"]]
        self.chain, self.heavy, self.pal, self.engine = chain, heavy or chain, palette, engine
        self.W, self.H = frame_size
        self.scale = self.W / 1080
        self.notes: list[str] = []
        on_band = ((self.cat.get("emphasis") or {}).get(emphasis) or {}).get("on_band") or {}
        if self.look["presentation"] == "highlight" and on_band.get("use"):
            self.notes.append(f"{emphasis} emphasis on {self.name}: {on_band.get('why', '')}: using {on_band['use']}")
            emphasis = on_band["use"]
        self.emphasis = emphasis
        if y is None:
            from .common import load_config
            t = (load_config("graphics-templates.json").get("templates") or {}).get("highlight_caption") or {}
            y = float(t.get("y", 1180)) * self.H / 1920
        self.cy = float(y)
        self.entrance = entrance or (self.cat.get("motion") or {}).get("entrance", "focus_in")
        # the client's highlight colour (T4.2) for every highlight role: the colour emphasis, the tag's foot rule and
        # the moving foot; the brand highlight without one
        self.highlight = tuple(highlight) if highlight else tuple(palette["highlight"])
        self.fixed_foot: tuple | None = None     # render_captions decides the foot colour once per clip

    # ------------------------------------------------------------------ geometry
    def size_of(self, cue: dict) -> float:
        return float(cue.get("size") or round(self.look["size"] * self.scale))

    ORDER = ("plate", "underlay", "fg")          # bottom to top: scrim and drop plate, the band over them, the text

    def _setter(self, size: float) -> Typesetter:
        tag = ((self.cat.get("emphasis") or {}).get("tag") or {})
        return Typesetter(self.chain, size, engine=self.engine, heavy=self.heavy,
                          tag_pad_px=float(tag.get("pad_x_px", 10)), scale=self.scale, tag_pad_em=tag.get("pad_em"))

    def _pad(self) -> tuple[float, float]:
        p = self.pres.get("plate") or {}
        return float(p.get("pad_x_px", 26)) * self.scale, float(p.get("pad_y_px", 12)) * self.scale

    def _centre_y(self, cue: dict, half: float, avoid) -> float:
        """The line's centre: the look's y, moved above a card that shares the caption band at the same time (or below
        it when there is no room above), like today's captions."""
        cy = self.cy
        s, e = cue["start_ms"], cue["end_ms"]
        cards = [(a[2], a[3] if len(a) > 3 else self.H) for a in (avoid or []) if s < a[1] and a[0] < e]
        clash = [(t, b) for t, b in cards if not (b < cy - half - 12 or t > cy + half + 12)]
        if clash:
            top, bot = min(c[0] for c in clash), max(c[1] for c in clash)
            up = top - half - 24
            cy = up if up - half >= SAFE_TOP_PX * self.H / 1920 else min(self.H - 300 * self.H / 1920, bot + half + 24)
        return cy

    # ------------------------------------------------------------------ colours
    def _foot_rows(self, size: float, box: tuple) -> tuple:
        """Where the moving foot can lie: from the font's descender line + gap, down a quarter em more than its own
        height (deep ink only moves it lower): the strip of the frame behind it, for its visibility check."""
        u = self.pres.get("underlay") or {}
        y0 = box[3] + float(u.get("gap_em", 0.06)) * size
        return (box[0], y0, box[2], y0 + 0.25 * size + float(u.get("height_px", 8)) * self.scale)

    def scrim_for(self, cue: dict, frame=None, avoid=None) -> dict:
        """What this caption needs on `frame`, layout and colours only, nothing drawn: {scrim: opacity (0 when none),
        behind: the strip colours behind it (None without a frame), behind_foot: the same behind the moving foot
        (highlight looks), for layers(behind=..., behind_foot=...)}."""
        size = self.size_of(cue)
        ts = self._setter(size)
        mode = self.emphasis if self.emphasis in ("weight", "tag") else None
        ln = ts.line([w["text"] for w in cue["words"]], emphasis=set(cue.get("emphasis") or []), mode=mode)
        asc, desc = ts.metrics()
        half = (asc + desc) / 2 + self._pad()[1]
        cy = self._centre_y(cue, half, avoid)
        left, baseline = (self.W - ln["w"]) / 2, cy + (asc - desc) / 2
        box = (left, baseline - asc, left + ln["w"], baseline + desc)
        behind = _regions(frame, box, self.scale)
        bf = _regions(frame, self._foot_rows(size, box), self.scale) if self.look["presentation"] == "highlight" \
            else None
        colors, _ = self._colors(size, box, None, behind=behind, behind_foot=bf)
        return {"scrim": float(colors["plate_opacity"]) if colors.get("scrim") else 0.0, "behind": behind,
                "behind_foot": bf}

    def _colors(self, size: float, box: tuple, frame, min_scrim: float = 0.0, behind: list | None = None,
                behind_foot: list | None = None) -> tuple[dict, list[str]]:
        pal, pres, notes = self.pal, self.look["presentation"], []
        need = _needed(size / self.scale)             # judged at the 1080 reference size, on every frame shape
        if behind is None:
            behind = _regions(frame, box, self.scale)
        dp = self.pres.get("drop_plate") or {}
        plate_op, scrim = float(dp.get("opacity", 0.35)), False
        if pres == "boxed":
            op = float((self.pres.get("plate") or {}).get("opacity", 0.92))
            bgs = [_blend(pal["ink"], b, op) for b in (behind or [pal["ink"]])]
        elif dp and behind is None and min_scrim > 0:
            # no frame here (a grab failed) but a neighbour needs the scrim: it stays steady, unjudged
            scrim, plate_op, bgs = True, max(plate_op, float(min_scrim)), None
        elif dp and behind is not None and (min_scrim > 0 or _worst(pal["white"], behind) + 1e-9 < need):
            # white fails on the footage itself: a soft ink scrim behind the line, stronger step by step (up to
            # max_opacity) before the text colour changes. The glyph-shaped drop plate is never counted: it only
            # sits under the strokes, so the letters' edges still meet the bare frame.
            scrim, sc = True, dp.get("scrim") or {}
            plate_op = max(plate_op, float(min_scrim))
            cover, aim = float(sc.get("coverage", 0.95)), max(need, float(sc.get("target_contrast", 4.5)))
            top, step = float(dp.get("max_opacity", plate_op)), float(dp.get("opacity_step", 0.15)) or 0.15
            while True:
                bgs = [_blend(pal["ink"], b, plate_op * cover) for b in behind]
                if _worst(pal["white"], bgs) + 1e-9 >= aim or plate_op >= top - 1e-9:
                    break
                plate_op = min(top, plate_op + step)
        else:
            bgs = behind
        text = pal["white"]
        if bgs is not None and _worst(text, bgs) + 1e-9 < need:
            best = max((pal["white"], pal["paper"], pal["ink"]), key=lambda c: _worst(c, bgs))
            if best != text and _worst(best, bgs) > _worst(text, bgs):
                notes.append(f"caption text drawn in {'ink' if best == pal['ink'] else 'paper'}: white has contrast "
                             f"{_worst(text, bgs):.1f}:1 on this frame (needs {need:.1f}:1)")
                text = best
            if _worst(text, bgs) + 1e-9 < need:
                notes.append(f"no caption colour reads everywhere on this footage (best {_worst(text, bgs):.1f}:1, "
                             f"needs {need:.1f}:1): choose a boxed look for this clip")
        out = {"text": text, "bg": bgs[0] if bgs else None, "bgs": bgs, "plate_opacity": round(plate_op, 3),
               "scrim": scrim, "need": need}
        if self.emphasis == "colour":
            want = self.highlight
            got = want if bgs is None else (step_to_contrast(want, bgs, need) or text)
            if got != want:
                light = sum(_lum(b) for b in bgs) / len(bgs) > 0.18
                notes.append(EMPHASIS_NOTE_AR if light else EMPHASIS_NOTE_AR_DARK)
            out["emphasis"] = got
        if self.emphasis == "tag":
            tag = pal[((self.cat.get("emphasis") or {}).get("tag") or {}).get("role", "accent")]
            on_tag = max((pal["white"], pal["ink"]), key=lambda c: contrast(c, tag))
            out["tag"], out["tag_text"] = tag, step_to_contrast(on_tag, tag, need) or on_tag
        if pres == "highlight":
            out["underlay"], out["foot_bgs"] = self._foot_colour(size, box, frame, behind_foot, out, notes)
        return out, notes

    def _foot_colour(self, size, box, frame, behind_foot, out, notes) -> tuple:
        """The moving foot's colour: the client's highlight colour (T4.2) or the brand highlight, never stepped. It
        carries no text, so G68 does not apply, but it must show against what is behind it (the scrim included):
        under min_contrast the next brand colour (highlight, accent, primary) is used, else the best one with a note."""
        if behind_foot is None and frame is not None:
            behind_foot = _regions(frame, self._foot_rows(size, box), self.scale)
        bgs = [] if behind_foot is None else self.foot_backgrounds(behind_foot, out["plate_opacity"] if out.get("scrim")
                                                                    else 0.0)
        if self.fixed_foot is not None:
            return self.fixed_foot, bgs
        if not bgs:
            return self.highlight, bgs
        colour, note = self.pick_foot([bgs])
        if note:
            notes.append(note)
        return colour, bgs

    def foot_backgrounds(self, behind_foot: list, scrim: float) -> list:
        """What the foot shows against: the footage strips, under the scrim when there is one."""
        cover = float(((self.pres.get("drop_plate") or {}).get("scrim") or {}).get("coverage", 0.95))
        return [_blend(self.pal["ink"], b, scrim * cover) if scrim else tuple(b) for b in behind_foot]

    def pick_foot(self, bgs_lists: list) -> tuple:
        """The foot colour for these backgrounds (one caption's, or every caption's of a clip): the first of the
        chosen highlight, the brand highlight, accent and primary that shows at min_contrast against all of them,
        else the best one. -> (colour, note or None); the note carries no numbers, so it is said once per clip."""
        pal, u = self.pal, self.pres.get("underlay") or {}
        bgs = [b for lst in bgs_lists for b in lst]
        if not bgs:
            return self.highlight, None
        need = float(u.get("min_contrast", 3.0))
        names = [("the chosen highlight colour", self.highlight), ("the brand highlight", pal["highlight"]),
                 ("the brand accent", pal["accent"]), ("the brand primary", pal["primary"])]
        seen, cands = set(), []
        for n, c in names:
            if tuple(c) not in seen:
                seen.add(tuple(c))
                cands.append((n, tuple(c)))
        hexs = lambda c: "#%02X%02X%02X" % tuple(c[:3])
        ok = next(((n, c) for n, c in cands if _worst(c, bgs) + 1e-9 >= need), None)
        if ok is None:
            n, c = max(cands, key=lambda nc: _worst(nc[1], bgs))
            return c, (f"no brand colour shows the moving foot on this footage (needs {need:.0f}:1): drawn in {n} "
                       f"{hexs(c)}, the most visible")
        if ok[1] != tuple(self.highlight):
            return ok[1], (f"the moving foot's colour {hexs(self.highlight)} does not show on this footage (needs "
                           f"{need:.0f}:1): drawn in {ok[0]} {hexs(ok[1])}")
        return ok[1], None

    # ------------------------------------------------------------------ layers
    def layers(self, cue: dict, frame=None, avoid=None, min_scrim: float = 0.0, behind: list | None = None,
               behind_foot: list | None = None) -> dict:
        """The caption's layers. `min_scrim`: the scrim a neighbouring caption needs (render_captions keeps the scrim
        steady across captions close in time, so it never pumps on and off). `behind`: the strip colours behind the
        caption measured earlier (scrim_for), used instead of `frame` so no frame has to be kept."""
        size = self.size_of(cue)
        ts = self._setter(size)
        emph = set(cue.get("emphasis") or [])
        mode = self.emphasis if self.emphasis in ("weight", "tag") else None
        ln = ts.line([w["text"] for w in cue["words"]], emphasis=emph, mode=mode)
        asc, desc = ts.metrics()
        pad_x, pad_y = self._pad()
        half = (asc + desc) / 2 + pad_y
        cy = self._centre_y(cue, half, avoid)
        left = (self.W - ln["w"]) / 2
        baseline = cy + (asc - desc) / 2
        top, bottom = baseline - asc, baseline + desc
        box = (left, top, left + ln["w"], bottom)
        colors, notes = self._colors(size, box, frame, min_scrim, behind, behind_foot)
        notes = list(self.notes) + notes
        word_boxes = {it["i"]: (left + it["x"], top, left + it["x"] + it["w"], bottom) for it in ln["items"]}
        faces = {it["i"]: [s["ps"] for s in it["segments"]] for it in ln["items"]}
        text = self._text(ln, ts, left, baseline, colors)
        foot = self._foot(text, size, box) if self.look["presentation"] == "highlight" else None
        plate = self._plate(ln, ts, left, baseline, box, colors, foot)
        underlay, spans = self._underlay(cue, ln, text, word_boxes, size, foot, colors) if foot else (None, [])
        fg = self._fg(text, word_boxes, colors, emph, box, foot)
        return {"baseline": baseline, "plate": plate, "underlay": underlay, "fg": fg, "spans": spans, "word_boxes": word_boxes, "box": box,
                "colors": colors, "notes": notes, "faces": faces, "cue": cue, "size": size, "engines": set(ts.engines),
                "missing": ln["missing"]}

    def _blank(self) -> Image.Image:
        return Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))

    def _draw_text(self, im: Image.Image, ln: dict, ts: Typesetter, left: float, baseline: float, color_of) -> None:
        for it in ln["items"]:
            x = left + it["x"] + it["pad"]
            rgba = tuple(color_of(it)) + (255,)
            for seg in it["segments"]:
                eng, font = ts.font_for(seg["face"])
                img, base_y, w = eng.render(seg["text"], seg["dir"], font, rgba)
                im.alpha_composite(img, (int(round(x - 4)), int(round(baseline - base_y))))
                x += seg["w"]

    def _text(self, ln, ts, left, baseline, colors) -> Image.Image:
        """The words alone (no tag), in their colours: the ink every other layer is placed against."""
        im = self._blank()
        emph_col = {"colour": colors.get("emphasis"), "tag": colors.get("tag_text")}.get(self.emphasis)
        self._draw_text(im, ln, ts, left, baseline,
                        lambda it: emph_col if it["emphasis"] and emph_col is not None else colors["text"])
        return im

    def _foot(self, text: Image.Image, size: float, box: tuple) -> tuple[float, float]:
        """The moving foot's rows: one y for the whole line, under the lower of its lowest ink and the font's descender
        line, so a line without descenders does not lift it from one caption to the next (R2 rounds 5–6)."""
        u = self.pres.get("underlay") or {}
        bb = text.getchannel("A").getbbox()
        y0 = max(bb[3] if bb else box[3], box[3]) + float(u.get("gap_em", 0.06)) * size
        return y0, y0 + float(u.get("height_px", 8)) * self.scale

    def _plate(self, ln, ts, left, baseline, box, colors, foot=None) -> Image.Image | None:
        pres = self.look["presentation"]
        if pres in ("clean", "highlight") and self.pres.get("drop_plate"):
            dp = self.pres.get("drop_plate") or {}
            mask = self._blank()
            ink = self.pal[dp.get("role", "ink")]
            self._draw_text(mask, ln, ts, left, baseline + float(dp.get("offset_px", 4)) * self.scale, lambda it: ink)
            mask = mask.filter(ImageFilter.GaussianBlur(float(dp.get("blur_px", 10)) * self.scale))
            base = float(dp.get("opacity", 0.35))
            a = mask.getchannel("A").point(lambda v: int(v * base))
            if colors.get("scrim"):
                sc = dp.get("scrim") or {}
                px, py = float(sc.get("pad_x_px", 22)) * self.scale, float(sc.get("pad_y_px", 14)) * self.scale
                rect = Image.new("L", (self.W, self.H), 0)
                low = max(box[3], foot[1]) if foot else box[3]          # down past the moving foot too
                ImageDraw.Draw(rect).rectangle((box[0] - px, box[1] - py, box[2] + px, low + py),
                                               fill=int(round(255 * float(colors["plate_opacity"]))))
                rect = rect.filter(ImageFilter.GaussianBlur(float(sc.get("blur_px", 7)) * self.scale))
                a = ImageChops.lighter(a, rect)
            mask.putalpha(a)
            return mask
        if pres == "boxed":
            p, foot = self.pres.get("plate") or {}, self.pres.get("foot") or {}
            pad_x, pad_y = self._pad()
            x0, y0, x1, y1 = box[0] - pad_x, box[1] - pad_y, box[2] + pad_x, box[3] + pad_y
            im = self._blank()
            d = ImageDraw.Draw(im)
            alpha = int(round(255 * float(p.get("opacity", 0.92))))
            d.rounded_rectangle((x0, y0, x1, y1), radius=float(p.get("radius_px", 6)) * self.scale,
                                fill=tuple(self.pal[p.get("role", "ink")]) + (alpha,))
            fh = float(foot.get("height_px", 6)) * self.scale
            d.rectangle((x0, y1 - fh, x1, y1), fill=tuple(self.pal[foot.get("role", "accent")]) + (255,))
            return im
        return None

    def _underlay(self, cue, ln, text, word_boxes, size, foot, colors) -> tuple[Image.Image, list]:
        """The moving foot: one full-line bar at the foot's rows (builders crop it word to word) and each word's span:
        its ink bounds + pad_em, square ends. A tagged word's foot hides behind its tag (same bottom line)."""
        u = self.pres.get("underlay") or {}
        y0, y1 = foot
        pad = float(u.get("pad_em", 0.04)) * size
        items = ln["items"]
        im = self._blank()
        a = text.getchannel("A")
        xs = []
        for it in items:
            wx0, wy0, wx1, _ = word_boxes[it["i"]]
            bb = a.crop((int(wx0), 0, int(round(wx1)) + 1, self.H)).getbbox()
            # a word that draws nothing (its glyphs missing): its box, so the foot still shows while it is spoken
            xs.append((int(wx0) + bb[0] - pad, int(wx0) + bb[2] + pad) if bb else (wx0 - pad, wx1 + pad))
        ImageDraw.Draw(im).rectangle((min(a for a, _ in xs), y0, max(b for _, b in xs), y1),
                                     fill=tuple(colors["underlay"]) + (255,))
        words = cue["words"]
        spans = []
        for it, (a, b) in zip(items, xs):
            i = it["i"]
            nxt = words[i + 1]["start_ms"] if i + 1 < len(words) else cue["end_ms"]
            spans.append({"i": i, "x0": round(a, 2), "x1": round(b, 2), "y0": round(y0, 2), "y1": round(y1, 2),
                          "start_ms": words[i]["start_ms"] if i else cue["start_ms"], "end_ms": nxt})
        return im, spans

    def _fg(self, text, word_boxes, colors, emph, box, foot=None) -> Image.Image:
        im = self._blank()
        if self.emphasis == "tag" and emph:
            # squared, and its bottom edge sits on the caption's bottom line: the plate's foot (boxed) or the line's
            # bottom: foot, band and tag share one bottom-accent line (R2 review)
            t = (self.cat.get("emphasis") or {}).get("tag") or {}
            d = ImageDraw.Draw(im)
            py = float(t.get("pad_y_px", 4)) * self.scale
            boxed = self.look["presentation"] == "boxed"
            bottom = box[3] + (self._pad()[1] if boxed else py)
            if foot:                             # highlight: the tag shares the moving foot's bottom line
                bottom = foot[1]
            foot_px = 0.0 if boxed else float(t.get("foot_px", 0)) * self.scale
            for i in sorted(emph):
                if i in word_boxes:
                    x0, y0, x1, y1 = word_boxes[i]
                    d.rounded_rectangle((x0, y0 - py, x1, bottom), radius=float(t.get("radius_px", 4)) * self.scale,
                                        fill=tuple(colors["tag"]) + (255,))
                    if foot_px:                  # anchored like the boxed look's foot (R2 review)
                        role = t.get("foot_role", "highlight")
                        rule = colors.get("underlay") or (self.highlight if role == "highlight" else self.pal[role])
                        d.rectangle((x0, bottom - foot_px, x1, bottom), fill=tuple(rule) + (255,))

        im.alpha_composite(text)
        return im

    # ------------------------------------------------------------------ preview and motion
    def composite(self, lay: dict, state: int | None = None, background=None) -> Image.Image:
        """The layers on `background` (a frame, else transparent), the underlay cropped to word `state`."""
        out = background.convert("RGBA").copy() if background is not None else self._blank()
        for layer in self.ORDER:
            if layer == "underlay":
                if lay.get("underlay") is not None and lay["spans"]:
                    sp = next((s for s in lay["spans"] if s["i"] == state), lay["spans"][0])
                    box = tuple(int(round(v)) for v in (sp["x0"], sp["y0"], sp["x1"], sp["y1"] + 1))
                    out.alpha_composite(lay["underlay"].crop(box), box[:2])
            elif lay.get(layer) is not None:
                out.alpha_composite(lay[layer])
        return out

    def motion(self, fps: float) -> dict:
        """How builders animate this look's captions (R-4.1 §2): a focus-in in place, a short fade out, and for
        highlight the band's slide between words."""
        m = self.cat.get("motion") or {}
        out = {"entrance": self.entrance, "enter_frames": looks.frames(int(m.get("enter_frames", 6)), fps),
               "scale_from": float(m.get("enter_scale_from", 0.96)), "travel_px": int(m.get("enter_travel_px", 0)),
               "ease": m.get("enter_ease", "ease_out"), "exit_frames": looks.frames(int(m.get("exit_frames", 4)), fps)}
        if self.look["presentation"] == "highlight":
            out["underlay_slide_frames"] = looks.frames(
                int((self.pres.get("underlay") or {}).get("slide_frames", 4)), fps)
        return out
