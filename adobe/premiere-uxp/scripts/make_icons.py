"""Generate the Premiere UXP panel icons from brand/logo.png (run once, commit the PNGs).

    ~/.whynot-cut/venv/Scripts/python.exe adobe/premiere-uxp/scripts/make_icons.py

Output (under adobe/premiere-uxp/icons/):
    {dark,light}/icon-23.png, icon-23@2x.png, icon-46.png   panel chrome (the mark alone: white on dark, #1C0E47 on light)
    {dark,light}/icon-24.png, icon-24@2x.png, icon-48.png   plugin list (gradient tile #D95C9B -> #5400FB + white mark)

icon-46 and icon-23@2x are the same file (and icon-48 / icon-24@2x), so the manifest works whichever way UXP
resolves a `scale: [1, 2]` icon (explicit pixel size or the @2x sibling).
"""
from __future__ import annotations

import pathlib
import sys

from PIL import Image, ImageChops, ImageDraw

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
LOGO = REPO / "brand" / "logo.png"
OUT = HERE.parent / "icons"

PINK = (0xD9, 0x5C, 0x9B)
VIOLET = (0x54, 0x00, 0xFB)
LIGHT_INK = (0x1C, 0x0E, 0x47)
WHITE = (255, 255, 255)
SS = 8  # supersampling factor


def monogram_mask() -> Image.Image:
    """The 'TWN' monogram (left part of brand/logo.png) as an L mask, tightly cropped."""
    im = Image.open(LOGO).convert("RGB")
    # Left block of the lockup, before "THE WHY NOT" starts (x ~ 285 in the 900x280 art).
    block = im.crop((0, 0, 285, im.height))
    r, g, b = block.split()
    # White strokes only: the pink 'AI heart' and its purple frame brackets are coloured, so min(r,g,b) drops them
    # (they turn into mush at 23 px). The result is the open monogram.
    mask = ImageChops.darker(ImageChops.darker(r, g), b).point(lambda v: 255 if v > 150 else 0)
    bbox = mask.point(lambda v: 255 if v > 24 else 0).getbbox()
    return mask.crop(bbox)


def fit(mask: Image.Image, box: int, pad: float) -> Image.Image:
    """Scale `mask` to fit inside a square of `box` px minus `pad` fraction margins; return an RGBA-ready L canvas."""
    inner = int(box * (1 - 2 * pad))
    scale = min(inner / mask.width, inner / mask.height)
    w, h = max(1, round(mask.width * scale)), max(1, round(mask.height * scale))
    scaled = mask.resize((w, h), Image.LANCZOS)
    canvas = Image.new("L", (box, box), 0)
    canvas.paste(scaled, ((box - w) // 2, (box - h) // 2))
    return canvas


def solid(mask: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    out = Image.new("RGBA", mask.size, color + (0,))
    out.putalpha(mask)
    return out


def chrome_icon(mask: Image.Image, size: int, color: tuple[int, int, int]) -> Image.Image:
    big = solid(fit(mask, size * SS, 0.04), color)
    return big.resize((size, size), Image.LANCZOS)


def tile_icon(mask: Image.Image, size: int) -> Image.Image:
    box = size * SS
    # diagonal gradient pink (top-left) -> violet (bottom-right)
    grad = Image.new("RGB", (box, box))
    px = grad.load()
    for y in range(box):
        for x in range(box):
            t = (x + y) / (2 * (box - 1))
            px[x, y] = tuple(round(PINK[i] + (VIOLET[i] - PINK[i]) * t) for i in range(3))
    rounded = Image.new("L", (box, box), 0)
    ImageDraw.Draw(rounded).rounded_rectangle((0, 0, box - 1, box - 1), radius=round(box * 0.22), fill=255)
    tile = grad.convert("RGBA")
    tile.putalpha(rounded)
    mark = solid(fit(mask, box, 0.17), WHITE)
    tile = Image.alpha_composite(tile, mark)
    return tile.resize((size, size), Image.LANCZOS)


def main() -> int:
    mask = monogram_mask()
    for theme, ink in (("dark", WHITE), ("light", LIGHT_INK)):
        d = OUT / theme
        d.mkdir(parents=True, exist_ok=True)
        c1, c2 = chrome_icon(mask, 23, ink), chrome_icon(mask, 46, ink)
        t1, t2 = tile_icon(mask, 24), tile_icon(mask, 48)
        for name, img in (("icon-23", c1), ("icon-46", c2), ("icon-23@2x", c2), ("icon-24", t1), ("icon-48", t2), ("icon-24@2x", t2)):
            img.save(d / f"{name}.png")
    # contact sheet for eyeballing (not shipped): 23/46/24/48 on dark and light backgrounds
    sheet = Image.new("RGBA", (4 * 120, 2 * 120), (0, 0, 0, 255))
    for row, (theme, bg) in enumerate((("dark", (38, 38, 38)), ("light", (232, 232, 232)))):
        ImageDraw.Draw(sheet).rectangle((0, row * 120, sheet.width, row * 120 + 119), fill=bg + (255,))
        for col, name in enumerate(("icon-23", "icon-46", "icon-24", "icon-48")):
            im = Image.open(OUT / theme / f"{name}.png").convert("RGBA")
            big = im.resize((im.width * 2, im.height * 2), Image.NEAREST) if im.width < 40 else im
            sheet.alpha_composite(big, (col * 120 + 10, row * 120 + 10))
    preview = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if preview:
        sheet.save(preview)
    print("icons written to", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
