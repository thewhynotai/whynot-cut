"""One resolver from a brand ROLE (caption, headline, term, body, small) to a font FACE of the client's own families.

Every renderer asks this module (preview stills, caption stills, publish thumbnails, the motion plan, the After Effects
font names), so a role means the same weight everywhere. Which weight a role wants, best source first:
  1. typography.json `roles` (what `reel client-db` / the researcher recorded): a PostScript name, a font file or a style;
  2. brand.json `font_roles_fallback.weights` (the profile's own override);
  3. the house default (headline black, caption/term bold, body medium, small regular).
If the family has no face of that weight the NEAREST available weight is used (black -> extrabold -> bold -> semibold ->
medium ...; regular -> book -> medium -> light ...). Never "the first font file".
"""
from __future__ import annotations

import re

DEFAULT_ROLE_STYLE = {"caption": "bold", "headline": "black", "body": "medium", "term": "bold", "small": "regular"}

# preference order per role when two weights are equally near the wanted one (also: every weight the role may fall to)
NEAREST = {"headline": ["black", "heavy", "extrabold", "bold", "semibold", "medium", "regular"],
           "caption": ["bold", "semibold", "extrabold", "black", "medium", "regular"],
           "term": ["bold", "semibold", "extrabold", "black", "medium", "regular"],
           "body": ["medium", "regular", "book", "semibold", "light", "bold"],
           "small": ["regular", "book", "medium", "light", "semibold"]}

WEIGHT = {"thin": 100, "hairline": 100, "extralight": 200, "ultralight": 200, "light": 300, "book": 400, "regular": 400,
          "normal": 400, "roman": 400, "medium": 500, "semibold": 600, "demibold": 600, "demi": 600, "bold": 700,
          "extrabold": 800, "ultrabold": 800, "heavy": 900, "black": 900, "ultra": 900, "extrablack": 950}
_SLANT = re.compile(r"italic|oblique")


def style_key(style) -> str:
    """'Extra Bold', 'ExtraBold', 'extra-bold' -> 'extrabold'; slant words are dropped ('Bold Italic' -> 'bold')."""
    return re.sub(r"[^a-z0-9]", "", _SLANT.sub("", str(style or "").lower()))


def _weight_of(key: str, weight_class) -> int:
    if key in WEIGHT:
        return WEIGHT[key]
    if isinstance(weight_class, (int, float)) and weight_class:
        return int(weight_class)
    return WEIGHT["regular"]


def faces(typography: dict) -> list[dict]:
    """Every face of every family in typography.json, in file order."""
    out = []
    for fam_name, fam in ((typography or {}).get("families") or {}).items():
        for w in (fam or {}).get("weights") or []:
            key = style_key(w.get("style"))
            out.append({"family": fam_name, "style": str(w.get("style") or ""), "key": key,
                        "weight": _weight_of(key, w.get("weight_class")), "file": w.get("file"),
                        "ps": w.get("postscript_name"), "italic": bool(_SLANT.search(str(w.get("style") or "").lower()))})
    return out


def _lc(v) -> str:
    return str(v or "").strip().lower()


def _stem(path) -> str:
    return re.split(r"[\\/]", _lc(path))[-1]


def _file_key(path) -> str:
    """A font file path compared whole: either slash, `.` parts dropped, case folded. client_db.load resolves a role's
    file like the families' files (review d224a9a P3-1), so the same file gives the same key and no other file does."""
    import os
    return os.path.normpath(str(path).replace("\\", "/")).replace("\\", "/").casefold() if path else ""


def _by_name(fs: list[dict], name) -> dict | None:
    """A face named exactly: PostScript name or the whole font file path; else a bare file name, when it names one
    file only (the same name in two folders names no face: which one is meant is not known, review c84f652 P3-5)."""
    n = _lc(name)
    if not n:
        return None
    key = _file_key(name)
    hit = next((f for f in fs if n == _lc(f["ps"]) or key == _file_key(f["file"])), None)
    if hit:
        return hit
    same = [f for f in fs if n == _stem(f["file"])]
    return same[0] if len({_file_key(f["file"]) for f in same}) == 1 else None


def _target(fs: list[dict], spec) -> tuple[dict | None, int | None, str | None]:
    """What one typography.json role entry asks for: (an exact face, a weight number, a style key). Entry forms:
    {"postscript_name"|"file": ...} · {"style"|"weight"|"font_weight"|"weight_class": "Bold" | 700} · "Bold" · "Brand-Bold"."""
    if isinstance(spec, str):
        spec = {"style": spec}
    if not isinstance(spec, dict):
        return None, None, None
    for k in ("postscript_name", "postscript", "ps", "file"):
        hit = _by_name(fs, spec.get(k))
        if hit:
            return hit, None, None
    suffix = style_key(re.split(r"[-_]", str(spec.get("postscript_name") or ""))[-1])
    if suffix in WEIGHT and "style" not in spec:       # a PostScript name that is not in the families still says "-Bold"
        return None, None, suffix
    for k in ("style", "weight", "font_weight", "weight_class"):
        v = spec.get(k)
        if isinstance(v, (int, float)) and v:
            return None, int(v), None
        hit = _by_name(fs, v) if isinstance(v, str) else None
        if hit:                                            # a bare string may be a PostScript name
            return hit, None, None
        if style_key(v):
            return None, None, style_key(v)
    return None, None, None


def _nearest(fs: list[dict], role: str, key: str | None, weight: int | None) -> dict | None:
    if not fs:
        return None
    want = weight if weight is not None else _weight_of(key or "", None)
    order = NEAREST.get(role, NEAREST["body"])
    pref = lambda f: order.index(f["key"]) if f["key"] in order else len(order)
    return min(fs, key=lambda f: (f["italic"], f["key"] != key if key else True, abs(f["weight"] - want), pref(f), -f["weight"]))


def resolve(typography: dict, role: str, fallback_weights: dict | None = None) -> dict:
    """The face for `role`: {file, ps, style, family, wanted, source, exact}. `wanted` is the style key asked for (from
    `source`: typography.json roles | brand.json font_roles_fallback | default); `exact` is False when the nearest weight
    stood in for it. file/ps are None when the client has no font at all."""
    fs = faces(typography)
    roles = (typography or {}).get("roles") or {}
    fb = fallback_weights or {}
    face, weight, key, source = None, None, None, "default"
    for src, spec in (("typography.json roles", roles.get(role)), ("brand.json font_roles_fallback", fb.get(role))):
        face, weight, key = _target(fs, spec)
        if face or weight or key:
            source = src
            break
    if not (face or weight or key):
        key = DEFAULT_ROLE_STYLE.get(role, "regular")
    wanted = face["key"] if face else (key or next((k for k, w in WEIGHT.items() if w == weight), str(weight)))
    exact = bool(face)
    if not face:
        face = _nearest(fs, role, key, weight)
        exact = bool(face) and ((key and face["key"] == key) or (weight is not None and face["weight"] == weight)) \
            and not face["italic"]
    if not face:
        return {"file": None, "ps": None, "style": None, "family": None, "wanted": wanted, "source": source, "exact": False}
    return {"file": face["file"], "ps": face["ps"], "style": face["style"], "family": face["family"], "wanted": wanted,
            "source": source, "exact": exact}
