"""Premiere's "Media pending" slate (field test G69).

`ppro-frames` right after a project opens exported 4 of 17 frames as Premiere's placeholder for media that is still
loading (a smooth colour field with "Media pending" written in nine languages); a second run a minute later was clean.
Such a frame says nothing about the edit, so it must be re-exported, never judged.

The test is cheap (a 108x192 thumbnail) and does not rely on the slate's colour, which differs between Premiere
versions (the real 26.5 one is a yellow-to-olive vertical gradient, left-aligned white text; older ones are dark grey
with a small centred line). What every version has in common:
  * the background is a smooth field that does not change from left to right: the left and right margins have the same
    colour on every row (a real picture never does), and that colour changes smoothly from row to row;
  * on top of it a small amount of sparse text, all lighter (or all darker) than the field: a minority of the
    pixels, spread thinly over its bounding box (a person, a photo or a card is a filled blob, not thin text).
Measured on the real slate and on 347 real frames Premiere exported for the test projects: the slate has row
constancy 0.0 (the nearest of the real frames: 13.1); the threshold is 8.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

LONG, SHORT = 192, 108           # thumbnail size (long side x short side)
MARGIN = 0.15                    # left/right strip of each row that is taken as the background colour
BG_TOL = 14                      # a thumbnail pixel is "text" when it differs from its row's background by more
ROW_CONSTANCY_MAX = 8.0          # mean difference between the left and right margin colour of a row (0-255)
SMOOTH_MAX = 3.0                 # mean second difference of the background colour from row to row (0-255)
TEXT_MIN, TEXT_MAX = 0.002, 0.35  # share of the pixels that is text
FILL_MAX = 0.6                   # text pixels / the box they span (thin text is sparse; a person or a photo is not)
THIN_BOX_H = 0.12                # ...unless the box is a single line (shorter than this share of the frame)
SIGN_MIN = 0.85                  # share of the text pixels on the same side (lighter / darker) of the background


def pending_metrics(src) -> dict:
    """Numbers behind the decision for an image path or a PIL image."""
    from PIL import Image
    if hasattr(src, "convert"):
        im = src.convert("RGB")
    else:
        with Image.open(Path(src)) as f:
            im = f.convert("RGB")
    size = (SHORT, LONG) if im.height >= im.width else (LONG, SHORT)
    a = np.asarray(im.resize(size, Image.BOX), dtype=np.float32)
    h, w = a.shape[:2]
    m = max(2, int(w * MARGIN))
    left, right = np.median(a[:, :m], axis=1), np.median(a[:, -m:], axis=1)      # (rows, 3)
    bg = (left + right) / 2
    row_constancy = float(np.abs(left - right).max(axis=1).mean())
    smooth = float(np.abs(bg[2:] - 2 * bg[1:-1] + bg[:-2]).max(axis=1).mean())
    text = np.abs(a - bg[:, None, :]).max(axis=2) > BG_TOL
    frac = float(text.mean())
    out = {"row_constancy": round(row_constancy, 2), "smoothness": round(smooth, 2), "text_fraction": round(frac, 4),
           "fill": None, "sign": None, "bbox": None}
    if text.any():
        ys, xs = np.nonzero(text)
        (x0, x1), (y0, y1) = np.percentile(xs, [1, 99]) / w, np.percentile(ys, [1, 99]) / h   # stray pixels don't count
        x1, y1 = x1 + 1 / w, y1 + 1 / h
        box = max((x1 - x0) * (y1 - y0), 1e-6)
        lum = np.array([0.299, 0.587, 0.114], dtype=np.float32)
        sgn = np.sign((a @ lum) - (bg @ lum)[:, None])[text]
        out.update({"fill": round(min(frac / box, 1.0), 3), "bbox": [round(float(v), 2) for v in (x0, y0, x1, y1)],
                    "sign": round(float(max((sgn > 0).mean(), (sgn < 0).mean())), 3)})
        out["line_only"] = bool(y1 - y0 <= THIN_BOX_H)
    out["pending"] = bool(
        row_constancy <= ROW_CONSTANCY_MAX and smooth <= SMOOTH_MAX and TEXT_MIN <= frac <= TEXT_MAX
        and out["fill"] is not None and (out["fill"] <= FILL_MAX or out["line_only"]) and out["sign"] >= SIGN_MIN)
    return out


def is_media_pending(src) -> bool:
    return pending_metrics(src)["pending"]
