"""macOS CoreText text rendering for previews: full OpenType shaping (Arabic GSUB joining,
ligatures, marks) and Unicode bidi, so Arabic/mixed lines render like they will in Adobe apps.
Pillow-only fallback (no libraqm) cannot shape fonts that lack presentation-form glyphs.
"""
from __future__ import annotations

import math
import re

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

    def render(self, text: str, rgba=(255, 255, 255, 255)):
        return render_line(text, self, rgba)


_ARABIC = re.compile("[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
RLM = "\u200f"


def rtl_base(text: str) -> str:
    """Any line with Arabic gets a right-to-left BASE direction. Otherwise the first strong character decides,
    and a line that starts with a Latin word ('evidence إنها ممكن تساعد') is laid out left-to-right, putting
    the first word on the wrong side (seen live on C0238 GFX_003)."""
    return RLM + text if _ARABIC.search(text) and not text.startswith(RLM) else text


def _line(text: str, font: CTFontSpec, rgba):
    text = rtl_base(text)
    r, g, b = rgba[:3]
    a = rgba[3] if len(rgba) > 3 else 255
    color = Quartz.CGColorCreateGenericRGB(r / 255, g / 255, b / 255, a / 255)
    attrs = {CoreText.kCTFontAttributeName: font._font, CoreText.kCTForegroundColorAttributeName: color}
    s = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
    return CoreText.CTLineCreateWithAttributedString(s)


def measure(text: str, font: CTFontSpec) -> float:
    w, asc, desc, lead = CoreText.CTLineGetTypographicBounds(_line(text, font, (0, 0, 0)), None, None, None)
    return float(w)


def render_line(text: str, font: CTFontSpec, rgba=(255, 255, 255, 255)):
    """Return (PIL RGBA image, baseline_y_from_top, width). Image height = ascent+descent (+pad)."""
    from PIL import Image
    line = _line(text, font, rgba)
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
