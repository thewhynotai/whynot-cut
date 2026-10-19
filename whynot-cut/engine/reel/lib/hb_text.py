"""Cross-platform text rendering for the graphics stills: HarfBuzz shaping + FreeType rasterising.

Same contract as ct_text (macOS CoreText): full OpenType shaping (Arabic GSUB joining, marks, ligatures, kerning) and a
right-to-left base direction for any line that contains Arabic, so Arabic/mixed lines render the way they will in
Adobe apps. The run order comes from lib/bidi_lines (UAX #9), the one bidi module every renderer shares. Used on
Windows/Linux, and on macOS when CoreText can't find the exact installed font.
The font FILE comes from the client's own assets (typography.json), so rendering doesn't depend on installed fonts.
"""
from __future__ import annotations

import math

from . import bidi_lines

try:
    import freetype  # type: ignore
    import uharfbuzz as hb  # type: ignore
    AVAILABLE = True
except Exception:  # packages missing
    AVAILABLE = False

_FACES: dict = {}
_FACES_MAX = 32          # a long-lived process renders many clients' fonts: keep the most recent few


def _face(path: str, index: int = 0):
    """(HarfBuzz face, FreeType face) of a font file (face `index` of a .ttc/.otc collection), cached by (path, size,
    mtime): a font file replaced in place (a client's corrected brand font) is read again, never served stale (T2.17)."""
    import io
    import os
    from pathlib import Path
    st = os.stat(path)
    key = (path, st.st_size, st.st_mtime_ns) + ((index,) if index else ())
    hit = _FACES.pop(key, None)
    if hit is None:
        data = Path(path).read_bytes()      # FreeType cannot open a non-ANSI path on Windows (an Arabic client folder)
        hit = (hb.Face(hb.Blob(data), index), freetype.Face(io.BytesIO(data), index))
    _FACES[key] = hit                       # re-inserted last: dict order = least recently used first
    while len(_FACES) > _FACES_MAX:
        del _FACES[next(iter(_FACES))]
    return hit


class HBFontSpec:
    engine = "harfbuzz"

    def __init__(self, path: str, size: float, index: int = 0):
        self.path, self.size, self.index = str(path), float(size), int(index or 0)
        self.hb_face, self.ft = _face(self.path, self.index)
        self.hb_font = hb.Font(self.hb_face)
        self.upem = self.hb_face.upem
        self.ft.set_char_size(int(round(self.size * 64)), 0, 72, 72)
        m = self.ft.size
        self._asc = int(math.ceil(m.ascender / 64))
        self._desc = int(math.ceil(-m.descender / 64))
        self.is_exact = True
        self.resolved = self.ft.postscript_name.decode() if isinstance(self.ft.postscript_name, bytes) else str(self.ft.postscript_name)

    def getmetrics(self):
        return self._asc, self._desc

    def render(self, text: str, rgba=(255, 255, 255, 255), bidi=None):
        return render_line(text, self, rgba, bidi)


# --------------------------------------------------------------------------- bidi (lib/bidi_lines: UAX #9)
def runs(text: str) -> tuple[bool, list[tuple[str, str]]]:
    """Split a line into directional runs in LOGICAL order and say whether the base direction is RTL.
    The order is lib/bidi_lines' (Addendum M2-T1, UAX #9): RTL when the line has any Arabic letter (HL1), neutrals
    between two runs of the same direction join them (N1), a number keeps its left-to-right order in RTL text
    («٥٠٠ مجم», «٣٫٥»; K-T5: «٣٫٥» was once drawn «٥٫٣») and «٧٠٪» has its percent sign on the left, as in the captions."""
    par = bidi_lines.paragraph(text)
    out: list[tuple[str, str]] = []
    for r in bidi_lines.logical_runs(par):
        d = "R" if r.rtl else "L"
        if out and out[-1][0] == d:
            out[-1] = (d, out[-1][1] + r.text)
        else:
            out.append((d, r.text))
    return par.rtl, out


def _shape(run_text: str, direction: str, font: HBFontSpec):
    buf = hb.Buffer()
    buf.add_str(run_text)
    buf.guess_segment_properties()
    buf.direction = "rtl" if direction == "R" else "ltr"
    hb.shape(font.hb_font, buf, {"kern": True, "liga": True})
    k = font.size / font.upem
    return [(info.codepoint, pos.x_advance * k, pos.x_offset * k, pos.y_offset * k)
            for info, pos in zip(buf.glyph_infos, buf.glyph_positions)]


def shape_line(text: str, font: HBFontSpec, bidi=None):
    """Glyphs in VISUAL left-to-right order: [(glyph_id, advance, x_off, y_off)] (px). bidi_lines gives the runs in
    visual order (UAX #9 L1–L2 on this line); HarfBuzz returns each right-to-left run's glyphs already in visual order
    and mirrors its brackets (L4). `bidi` = a bidi_lines.Line cut from a longer paragraph (a wrapped line keeps the
    paragraph's direction and levels); without it the text is one paragraph. A Line whose text is not `text` is
    refused (ValueError): a wrong call fails loudly instead of drawing another line's order."""
    if bidi is not None and bidi.text != text:
        raise ValueError("the bidi Line is not the line being drawn")
    runs = bidi.runs if bidi is not None else bidi_lines.line_runs(bidi_lines.paragraph(text))
    return [g for r in runs for g in _shape(r.text, "R" if r.rtl else "L", font)]


def measure(text: str, font: HBFontSpec) -> float:
    return float(sum(g[1] for g in shape_line(text, font)))


def render_line(text: str, font: HBFontSpec, rgba=(255, 255, 255, 255), bidi=None):
    """Return (PIL RGBA image, baseline_y_from_top, width), same geometry as ct_text.render_line."""
    import numpy as np
    from PIL import Image
    glyphs = shape_line(text, font, bidi)
    w = sum(g[1] for g in glyphs)
    pad = 4
    asc, desc = font.getmetrics()
    W = max(1, int(math.ceil(w)) + pad * 2)
    H = max(1, asc + desc + pad * 2)
    base_y = pad + asc
    cov = np.zeros((H, W), dtype=np.float32)
    ft = font.ft
    # the FreeType face is shared by every size of this font file: set THIS spec's size before rasterising (else a
    # 150 px value drawn after a 52 px label of the same font comes out at 52 px, with 150 px spacing)
    ft.set_char_size(int(round(font.size * 64)), 0, 72, 72)
    pen = float(pad)
    flags = freetype.FT_LOAD_DEFAULT | freetype.FT_LOAD_NO_HINTING
    for gid, adv, xo, yo in glyphs:
        ft.load_glyph(gid, flags)
        ft.glyph.render(freetype.FT_RENDER_MODE_NORMAL)
        bm = ft.glyph.bitmap
        if bm.width and bm.rows:
            arr = np.array(bm.buffer, dtype=np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width].astype(np.float32) / 255
            x0 = int(round(pen + xo)) + ft.glyph.bitmap_left
            y0 = int(round(base_y - yo)) - ft.glyph.bitmap_top
            xa, ya = max(0, x0), max(0, y0)
            xb, yb = min(W, x0 + bm.width), min(H, y0 + bm.rows)
            if xb > xa and yb > ya:
                sub = arr[ya - y0:yb - y0, xa - x0:xb - x0]
                cov[ya:yb, xa:xb] = np.maximum(cov[ya:yb, xa:xb], sub)
        pen += adv
    r, g, b = rgba[:3]
    a = rgba[3] if len(rgba) > 3 else 255
    out = np.zeros((H, W, 4), dtype=np.uint8)
    out[..., 0], out[..., 1], out[..., 2] = r, g, b
    out[..., 3] = np.clip(cov * a, 0, 255).astype(np.uint8)
    return Image.fromarray(out), base_y, float(w)          # HxWx4 uint8 -> RGBA
