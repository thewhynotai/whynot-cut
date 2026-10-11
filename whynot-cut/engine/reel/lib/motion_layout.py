"""Layout for motion scenes (spec §4.1 "Layout fitting" and "Contrast"): Arabic-safe wrapping, HarfBuzz measurement with
the brand font FILE (AE reads the installed font; the read-back after the build is the truth), WCAG contrast, and
per-scene-type placement presets that read the reading direction instead of hardcoding sides.
"""
from __future__ import annotations

import re

from .ae_builder import _balance, wrap_lines

NBSP = ""          # glue marker (private use, NOT whitespace: str.split() would break U+00A0)
UNITS = {"%", "٪", "مليون", "ملايين", "الف", "ألف", "آلاف", "الاف", "سنة", "سنه", "سنين", "سنوات", "يوم", "ايام", "أيام",
         "ساعة", "ساعه", "ساعات", "دقيقة", "دقيقه", "دقايق", "جنيه", "دولار", "ريال", "درهم", "k", "m", "kg", "km"}
_LATIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-.'’+/]*[A-Za-z0-9%]?$")
_HAS_LETTER = re.compile(r"[A-Za-z]")
_NUMBER = re.compile(r"^[0-9٠-٩][0-9٠-٩.,٬٫%٪]*$")


def _latin(tok: str) -> bool:
    return bool(_LATIN.match(tok)) and bool(_HAS_LETTER.search(tok))


def glue(text: str) -> list[str]:
    """Tokens where protected pairs are joined by the glue marker: a Latin run, a number and its unit, "ال"/"الـ" + Latin."""
    toks = text.split()
    out: list[str] = []
    for t in toks:
        if out:
            prev_last = out[-1].split(NBSP)[-1]
            if (_latin(t) and _latin(prev_last)) or (_NUMBER.match(prev_last) and t.lower() in UNITS) or \
                    (prev_last in ("ال", "الـ") and _latin(t)):
                out[-1] += NBSP + t
                continue
        out.append(t)
    return out


def wrap(text: str, max_chars: int, max_lines: int) -> list[str]:
    lines = wrap_lines(" ".join(glue(text)), max_chars).split("\r")
    if len(lines) > max_lines:                      # the fitter shrinks the size; here keep the minimal break count
        lines = _balance(glue(text), max_lines)
    return [ln.replace(NBSP, " ") for ln in lines]


def fit(text: str, font_file: str, box_w: int, size_range: tuple[int, int], max_lines: int) -> dict:
    """Largest size (4 px steps) at which the text fits box_w in ≤ max_lines balanced lines, measured with HarfBuzz."""
    from . import hb_text
    words = glue(text)
    hi, lo = int(size_range[0]), int(size_range[1])
    size = hi
    while size >= lo:
        font = hb_text.HBFontSpec(font_file, size)
        for n in range(1, min(max_lines, len(words)) + 1):
            lines = [ln.replace(NBSP, " ") for ln in _balance(words, n)]
            widths = [hb_text.measure(ln, font) for ln in lines]
            if max(widths) <= box_w:
                return {"ok": True, "size": size, "lines": lines, "widths": [round(w, 1) for w in widths]}
        size -= 4
    font = hb_text.HBFontSpec(font_file, lo)
    lines = [ln.replace(NBSP, " ") for ln in _balance(words, min(max_lines, len(words)))]
    return {"ok": False, "size": lo, "lines": lines, "widths": [round(hb_text.measure(ln, font), 1) for ln in lines]}


# --------------------------------------------------------------------------- colour
def _lum(rgb: tuple) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(float(x)) for x in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: tuple, bg: tuple) -> float:
    a, b = _lum(fg), _lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def pick_text_color(bg: tuple, candidates: list[tuple[str, tuple]], size_px: int, cfg: dict) -> tuple[str, float]:
    need = cfg.get("min_contrast_large", 3.0) if size_px >= cfg.get("large_px", 64) else cfg.get("min_contrast", 4.5)
    name, rgb = max(candidates, key=lambda c: contrast(c[1], bg))
    r = contrast(rgb, bg)
    if r + 1e-9 < need:
        raise ValueError(f"no brand colour reaches contrast {need} on this background (best: {name} {r:.2f})")
    return name, round(r, 2)


def theme_colors(theme: str, brand) -> dict:
    from .motion_config import motion_cfg
    t = (motion_cfg().get("themes") or {}).get(theme) or {"bg": "ink", "text": "white", "accent": "primary"}
    named = {"ink": brand.ink, "paper": brand.paper, "primary": brand.teal, "white": brand.white}
    return {k: tuple(named[t[k]]) for k in ("bg", "text", "accent")} | {"names": dict(t)}


# --------------------------------------------------------------------------- placement
# y = fraction of the safe height (top safe line → bottom safe line); x = center | start | end | start_half | end_half
PRESETS: dict[str, dict] = {
    "kinetic_quote": {"text": {"y": 0.45, "x": "center", "role": "quote"}},
    "title_card": {"eyebrow": {"y": 0.30, "x": "center", "role": "label"}, "title": {"y": 0.45, "x": "center", "role": "title"},
                   "subtitle": {"y": 0.62, "x": "center", "role": "body"}},
    "stat_counter": {"icon": {"y": 0.22, "x": "center", "role": "label"}, "value": {"y": 0.45, "x": "center", "role": "stat"},
                     "label": {"y": 0.64, "x": "center", "role": "body"}},
    "icon_point": {"icon": {"y": 0.30, "x": "center", "role": "label"}, "text": {"y": 0.62, "x": "center", "role": "body"}},
    "list_steps": {"title": {"y": 0.10, "x": "center", "role": "label"}, "number": {"y": 0.28, "x": "start", "role": "body"},
                   "item": {"y": 0.28, "x": "start", "role": "body"}},
    "comparison": {"first": {"y": 0.45, "x": "start_half", "role": "body"}, "second": {"y": 0.45, "x": "end_half", "role": "body"},
                   "verdict": {"y": 0.85, "x": "center", "role": "label"}},
    "timeline": {"line": {"y": 0.50, "x": "center", "role": "label"}, "label": {"y": 0.60, "x": "center", "role": "label"},
                 "when": {"y": 0.40, "x": "center", "role": "label"}},
    "quote_card": {"text": {"y": 0.42, "x": "center", "role": "quote"}, "attribution": {"y": 0.72, "x": "center", "role": "label"}},
    "context_card": {"text": {"y": 0.45, "x": "center", "role": "body"}},
    "person_card": {"photo": {"y": 0.36, "x": "center", "role": "label"}, "name": {"y": 0.64, "x": "center", "role": "title"},
                    "role": {"y": 0.74, "x": "center", "role": "label"}},
    "illustration_scene": {"image": {"y": 0.40, "x": "center", "role": "label"}, "text": {"y": 0.78, "x": "center", "role": "body"}},
    "outro": {"logo": {"y": 0.36, "x": "center", "role": "label"}, "cta": {"y": 0.62, "x": "center", "role": "title"},
              "show": {"y": 0.74, "x": "center", "role": "label"}},
    "_persistent": {"caption": {"y": 0.97, "x": "center", "role": "caption"}, "badge": {"y": 0.02, "x": "start", "role": "label"}},
}
MARGIN = 60


def place(scene_type: str, element: str, fmt: dict, direction: str) -> tuple[float, float]:
    p = PRESETS[scene_type][element]
    w, h, s = fmt["w"], fmt["h"], fmt["safe"]
    y = s["top"] + p["y"] * (h - s["top"] - s["bottom"])
    usable = w - 2 * s["side"]
    rtl = direction == "rtl"
    x = {"center": w / 2,
         "start": (w - s["side"] - MARGIN) if rtl else (s["side"] + MARGIN),
         "end": (s["side"] + MARGIN) if rtl else (w - s["side"] - MARGIN),
         "start_half": s["side"] + usable * (0.75 if rtl else 0.25),
         "end_half": s["side"] + usable * (0.25 if rtl else 0.75)}[p["x"]]
    return (x, round(y, 1))


def role_of(scene_type: str, element: str) -> str:
    return PRESETS[scene_type][element]["role"]
