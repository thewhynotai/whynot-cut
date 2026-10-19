"""macOS CoreText text rendering for previews: full OpenType shaping (Arabic GSUB joining,
ligatures, marks) and Unicode bidi, so Arabic/mixed lines render like they will in Adobe apps.
Pillow-only fallback (no libraqm) cannot shape fonts that lack presentation-form glyphs.
"""
from __future__ import annotations

import math

try:
    import CoreText
    import Quartz
    from Foundation import NSAttributedString
    AVAILABLE = True
except Exception:  # not macOS / pyobjc missing
    AVAILABLE = False


class CTFontSpec:
    engine = "coretext"

    def __init__(self, ps_name: str, size: float):
        self.ps_name, self.size = ps_name, size
        self._font = CoreText.CTFontCreateWithName(ps_name, size, None)
        actual = CoreText.CTFontCopyPostScriptName(self._font)
        self.resolved = str(actual)
        self.is_exact = self.resolved == ps_name

    def getmetrics(self):
        return (int(math.ceil(CoreText.CTFontGetAscent(self._font))),
                int(math.ceil(CoreText.CTFontGetDescent(self._font))))

    def render(self, text: str, rgba=(255, 255, 255, 255), bidi=None):
        return render_line(text, self, rgba, bidi)


def rtl_base(text: str, base: int | None = None, bidi=None) -> str:
    """CoreText runs its own UAX #9, so it gets lib/bidi_lines.host_text (M2-T1): the text spelled with the marks,
    embeddings and overrides that make any conforming engine draw bidi_lines' order. A line with an Arabic letter, or
    a wrapped line of an Arabic paragraph, keeps a right-to-left BASE direction even when it starts with a Latin word
    ('evidence إنها ممكن تساعد' was laid out left-to-right, the first word on the wrong side: seen live on C0238
    GFX_003), and a phone number reads as dialled. `bidi` = the bidi_lines.Line the text was cut from (a wrapped line
    keeps the levels of its whole block: W7/N0/N1 across the break); without it the text is one paragraph, its
    direction `base` (None = decided from the text, HL1). A Line whose text is not `text` is refused (ValueError):
    a wrong call fails loudly instead of drawing another line's order. One line per call: a paragraph separator
    inside the text (a newline, U+2029 …; previews._wrap_block splits them) or nesting past the host's 125 levels
    raises ValueError from host_text, where HarfBuzz would draw it; no caller sends such text."""
    from . import bidi_lines
    if bidi is not None:
        if bidi.text != text:
            raise ValueError("the bidi Line is not the line being drawn")
        return bidi_lines.host_text(bidi, base)
    return bidi_lines.host_text(bidi_lines.paragraph(text, base=base))


def _line(text: str, font: CTFontSpec, rgba, base: int | None = None, bidi=None):
    text = rtl_base(text, base, bidi)
    r, g, b = rgba[:3]
    a = rgba[3] if len(rgba) > 3 else 255
    color = Quartz.CGColorCreateGenericRGB(r / 255, g / 255, b / 255, a / 255)
    attrs = {CoreText.kCTFontAttributeName: font._font, CoreText.kCTForegroundColorAttributeName: color}
    s = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
    return CoreText.CTLineCreateWithAttributedString(s)


def measure(text: str, font: CTFontSpec) -> float:
    w, asc, desc, lead = CoreText.CTLineGetTypographicBounds(_line(text, font, (0, 0, 0)), None, None, None)
    return float(w)


def render_line(text: str, font: CTFontSpec, rgba=(255, 255, 255, 255), bidi=None):
    """Return (PIL RGBA image, baseline_y_from_top, width). Image height = ascent+descent (+pad)."""
    from PIL import Image
    line = _line(text, font, rgba, bidi=bidi)
    w, asc, desc, lead = CoreText.CTLineGetTypographicBounds(line, None, None, None)
    pad = 4
    W = max(1, int(math.ceil(w)) + pad * 2)
    H = max(1, int(math.ceil(asc + desc)) + pad * 2)
    cs = Quartz.CGColorSpaceCreateDeviceRGB()
    ctx = Quartz.CGBitmapContextCreate(None, W, H, 8, W * 4, cs, Quartz.kCGImageAlphaPremultipliedLast)
    Quartz.CGContextSetShouldAntialias(ctx, True)
    Quartz.CGContextSetTextPosition(ctx, pad, pad + desc)  # CG origin = bottom-left
    CoreText.CTLineDraw(line, ctx)
    img = Quartz.CGBitmapContextCreateImage(ctx)
    bpr = Quartz.CGImageGetBytesPerRow(img)
    data = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(img))
    im = Image.frombuffer("RGBa", (W, H), bytes(data), "raw", "RGBa", bpr, 1).convert("RGBA")
    return im, pad + int(math.ceil(asc)), float(w)
