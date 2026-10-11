"""Is a colour readable where it is drawn? WCAG relative-luminance contrast of a text colour against the pixels behind it.

Used wherever the engine draws a brand colour straight over footage (publish thumbnails, preview stills): the profile may
say "highlight in brand gold" while the measured primary is a brown that disappears on a warm set (field test round 4:
brown primary on the warm set read 1.1-1.5:1). The thresholds are the engine's own (motion.json min_contrast 4.5,
min_contrast_large 3.0 from large_px). When the colour is too faint the caller falls back to white / paper and warns.
"""
from __future__ import annotations

from .motion_layout import contrast


def needed(size_px: float) -> float:
    """Minimum contrast for text of this pixel size: 3:1 for large text, 4.5:1 below (motion.json, profile-overridable)."""
    from .motion_config import motion_cfg
    cfg = motion_cfg()
    return float(cfg.get("min_contrast_large", 3.0) if size_px >= cfg.get("large_px", 64) else cfg.get("min_contrast", 4.5))


def region_mean(im, box) -> tuple:
    """Average RGB of `box` (x0, y0, x1, y1) of a PIL image, the box clamped to the image."""
    from PIL import ImageStat
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(im.width, x1), min(im.height, y1)
    if x1 <= x0 or y1 <= y0:
        return (0, 0, 0)
    st = ImageStat.Stat(im.crop((x0, y0, x1, y1)).convert("RGB"))
    return tuple(int(round(v)) for v in st.mean[:3])


def legible(fg: tuple, regions: list, size_px: float, fallbacks: list) -> dict:
    """Keep `fg` when it reaches the contrast text of `size_px` needs against EVERY background colour in `regions` (the
    worst one decides); otherwise the most readable of `fallbacks` [(name, rgb), ...] when it is actually better.
    -> {rgb, name, ratio, need, fallback, original_ratio}: ratio is the contrast of the colour returned (the worst
    region's), original_ratio that of `fg`, name the fallback's name (None while fg is kept)."""
    need = needed(size_px)
    worst = lambda c: min((contrast(c, bg) for bg in regions), default=21.0)
    orig = worst(fg)
    if orig + 1e-9 >= need or not fallbacks:
        return {"rgb": tuple(fg), "name": None, "ratio": round(orig, 2), "need": need, "fallback": False,
                "original_ratio": round(orig, 2)}
    name, rgb = max(fallbacks, key=lambda c: worst(c[1]))
    best = worst(rgb)
    if best <= orig:                       # nothing on offer reads better: keep the brand colour (the caller still sees ratio < need)
        return {"rgb": tuple(fg), "name": None, "ratio": round(orig, 2), "need": need, "fallback": False,
                "original_ratio": round(orig, 2)}
    return {"rgb": tuple(rgb), "name": name, "ratio": round(best, 2), "need": need, "fallback": True,
            "original_ratio": round(orig, 2)}
