# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Arabic + Latin font pairing (Addendum M §M2.1 req 4, §M2.2 "Font harmony"; M2-T4, Task 56).

The Arabic and the Latin face of one video must match in personality (formal, geometric, humanist, handwritten,
display) and in visual weight and size. This module MEASURES each face from its file and scores a pair 0-100.

Traits (per face, at the role's weight; cached by the file's sha256):
  x_height      Latin: ink height of "x" per em, else OS/2 sxHeight, else None
  arabic_body   Arabic: median tooth height of the isolated «س ب ن ي» per em, read from their dotless forms (ٮ ں ى;
                س has no dots) so a dot can never be the body. A font without a dotless form: ب and ي carry their dots
                below the body, so their full top counts; ن is classified by contours (_body: the contours joined to
                the largest one, minus small marks whose centre lies outside its height)
  contrast_*    1 - thin/thick stroke from scanlines through the middle of a FreeType raster. Latin: the sides vs the
                top/bottom of "o"; Arabic: the alef stem vs the base stroke of ب. 0 = even strokes
  density_*     ink coverage of a fixed string / (its advance x the script's body height): the visual weight
  width_*       advance of a fixed string / (letters x body height); space_*: the word space / body height
  angularity_*  share of straight segments in the outlines of a fixed glyph set (terminal shape)
A static family serves a weight with its file of the nearest usWeightClass (ties: the heavier; a one-file family serves
every weight, its weight is then judged by its measured ink); a variable font is instanced at that weight (fontTools
instancer, other axes at their defaults), never measured at its default master.

Coverage gate: ARABIC_TEST (the letters with ڤ, ٪ ، ؛ ؟, Arabic-Indic digits with the decimal and thousands
separators ٫ ٬, tatweel ـ and the harakat U+064B-0652) plus the lam-alef ligature (one glyph, or a lam and an alef
that both differ from their plain joining forms), and LATIN_TEST (A-Z a-z 0-9 % & ®). A face missing any of them
never enters a table pair; the misses are named. A miss on the client's own face is a finding, never a switch to
another family.

Score = class 40 + weight 20 + height 15 + contrast 15 + width/rhythm 10 (WEIGHTS), every part bounded. >= 70: used
automatically; 50-69: shown to the editor with explain() as the reason; < 50: never used, except the client's own
pair, which always wins with its score shown. latin_scale = TARGET_RATIO x arabic_body / x_height, clamped to
SCALE_RANGE: drawn at that scale, the Latin x-height sits on the Arabic letter body (heights_aligned: within ALIGN_TOL,
3 %, of the target ratio).

Sources, in order (pick): the client's pairing in typography.json; then, when the role's face (font_roles.resolve,
which honours typography.json roles and brand.json fallback weights) is the client's own: its own family when that
family passes both gates (a superfamily), else the other script measured against that very face (the client's other
families, then the installed table faces), best >= 50; with no client face, the curated table
config/defaults/font-pairings.json. A Latin is never handed over that was scored against another Arabic face (nor an
Arabic against another Latin). A missing fontTools, uharfbuzz, freetype-py or numpy is a FontProbeError naming it
(pick returns no pair with that finding). The table is built by
build_table() from folders of OFL font families (each family folder holds its OFL.txt): the repo's guide-ar/fonts and,
when given, a downloaded folder. Every face carries its licence proof (nameID 13/14, OFL.txt sha256, file sha256).
A family measured from a folder outside the repo keeps its rows when the table is rebuilt without that folder.
Build, from whynot-cut/engine/reel with the engine runtime:
  python -m lib.font_pairing build --fonts <folder> [--fonts <folder> ...] [--write]
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import statistics
import struct
import sys
from pathlib import Path

from .font_roles import DEFAULT_ROLE_STYLE, WEIGHT
from .font_roles import faces as typography_faces

DEFAULT_TABLE = Path(__file__).resolve().parents[3] / "config" / "defaults" / "font-pairings.json"
TABLE_VERSION = 1
TRAITS_VERSION = 2          # 2: the Arabic body from the dotless forms (fix round 1)

CLASSES = ("formal", "geometric", "humanist", "handwritten", "display")
WEIGHTS = {"class": 40, "weight": 20, "height": 15, "contrast": 15, "width": 10}
BAND_AUTO, BAND_SHOWN = 70.0, 50.0
TARGET_RATIO = 1.0          # scaled Latin x-height / Arabic letter body (executor ruling Q56-4)
ALIGN_TOL = 0.03
SCALE_RANGE = (0.7, 1.4)
WEIGHT_TOL = 0.5            # relative ink-density gap that scores 0
HEIGHT_TOL = 1.6            # natural x-height/body ratio this far off the target (either way) scores 0
CONTRAST_TOL = 0.5          # contrast gap that scores 0
WIDTH_TOL = 2.0             # width or word-space ratio this far off (either way) scores 0
UNKNOWN_CLASS_MAX = 30      # an uncurated face never earns the full class part: terminal shape stands in for it
ANGULARITY_TOL = 0.5
WEIGHT_REACH = 150          # a family serves a weight only within this many usWeightClass units (one-file: always)
PAIR_MIN_CLASS = 20         # the table pairs two families only when their classes earn at least this many points
_PAIR_CLASS = {frozenset(("geometric", "humanist")): 20, frozenset(("geometric", "display")): 16,
               frozenset(("humanist", "formal")): 12, frozenset(("formal", "handwritten")): 12,
               frozenset(("humanist", "display")): 8}

ARABIC_TEST = "ابتثجحخدذرزسشصضطظعغفقكلمنهويءآأؤإئةىڤ٪،؛؟٠١٢٣٤٥٦٧٨٩٫٬ـ" + "".join(chr(c) for c in range(0x064B, 0x0653))
ARABIC_LIGATURES = ("لا",)
LATIN_TEST = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789%&®"
ARABIC_BODY = "سبني"
DOTLESS = {"ب": "ٮ", "ن": "ں", "ي": "ى"}   # the same letter bodies without dots (س has none)
DOT_ABOVE = "ن"                          # without its dotless form, only this letter needs contour classes
SMALL_MARK = 0.15                        # a contour under this share of the largest contour's area is a mark
REQUIRED_MODULES = ("fontTools", "uharfbuzz", "freetype", "numpy")
LATIN_DENSITY, ARABIC_DENSITY = "noxeacsmuvwrz", "سببنسبس"
LATIN_WIDTH, ARABIC_WIDTH = "hamburgefonstiv", "مستشفيات"
LATIN_SHAPES, ARABIC_SHAPES = "acegsoR", "عسجهوص"
_PX = 400                   # raster probe: pixels per em
_FONT_EXT = (".ttf", ".otf", ".ttc", ".otc")
ROW_WEIGHTS = tuple(sorted({WEIGHT[s] for s in DEFAULT_ROLE_STYLE.values()}))
_READ_ERRORS = (OSError, KeyError, AssertionError, ValueError, IndexError, TypeError, AttributeError,
                ZeroDivisionError, struct.error)


class FontProbeError(ValueError):
    """A font file that cannot be read or measured (the message names the file)."""


class PairingRefused(ValueError):
    """The table builder refused (licence, unreadable font, structure): nothing was written."""


# --------------------------------------------------------------------------- files and faces
def file_sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text_sha256(path) -> str:
    """sha256 of a text file with its line endings as LF: a checkout's line endings never change a licence proof."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _fold(name) -> str:
    """File names compare case-insensitively where the file system does (Windows, macOS default), exactly elsewhere."""
    s = str(name or "").strip()
    return s.lower() if sys.platform == "win32" or sys.platform == "darwin" else s


_CACHE: dict = {}
_STATS = {"hits": 0, "misses": 0}


def clear_cache() -> None:
    _CACHE.clear()
    _STATS.update(hits=0, misses=0)


def cache_info() -> dict:
    return {"hits": _STATS["hits"], "misses": _STATS["misses"], "size": len(_CACHE)}


def _require(names=None) -> None:
    """Raise FontProbeError naming every required package that cannot be imported (a clear refusal, never a crash)."""
    miss = missing_modules(names)
    if miss:
        raise FontProbeError(f"font pairing needs {', '.join(miss)}, which cannot be imported here (run reel setup)")


def _open(data: bytes, index: int, name: str):
    _require(("fontTools",))
    from fontTools.ttLib import TTFont, TTLibError
    try:
        return TTFont(io.BytesIO(data), fontNumber=int(index or 0))
    except (TTLibError,) + _READ_ERRORS as e:
        raise FontProbeError(f"{name}: not a readable font ({type(e).__name__}: {e})") from e


class _Face:
    """One face: the font (instanced at `weight` when it is variable and `instance` is True), its bytes for HarfBuzz
    and its glyph set."""

    def __init__(self, path, index: int = 0, weight=None, instance: bool = True):
        _require()
        from fontTools.ttLib import TTFont, TTLibError
        self.path = Path(path)
        try:
            data = self.path.read_bytes()
        except OSError as e:
            raise FontProbeError(f"{self.path.name}: cannot be read ({e})") from e
        self.sha = hashlib.sha256(data).hexdigest()
        font = _open(data, index, self.path.name)
        self.index = int(index or 0)
        try:
            axes = {a.axisTag: a for a in font["fvar"].axes} if "fvar" in font else {}
            self.variable = "wght" in axes
            self.weight = int(font["OS/2"].usWeightClass) if "OS/2" in font else 400
            if axes and instance:
                from fontTools.varLib import instancer
                limits = {t: a.defaultValue for t, a in axes.items()}
                if self.variable and weight is not None:
                    a = axes["wght"]
                    limits["wght"] = min(max(float(weight), a.minValue), a.maxValue)
                font = instancer.instantiateVariableFont(font, limits)
                buf = io.BytesIO()
                font.save(buf)
                data = buf.getvalue()
                font = TTFont(io.BytesIO(data))
                self.index = 0
                if self.variable:
                    self.weight = int(round(limits["wght"]))
            self.font, self.data = font, data
            self.upm = int(font["head"].unitsPerEm)
            self.cmap = font.getBestCmap() or {}
            self.glyphs = font.getGlyphSet()
            self.order = font.getGlyphOrder()
        except (TTLibError,) + _READ_ERRORS as e:
            raise FontProbeError(f"{self.path.name}: not a readable font ({type(e).__name__}: {e})") from e
        if self.upm <= 0:
            raise FontProbeError(f"{self.path.name}: unitsPerEm is {self.upm}")
        self._hb = None

    def shape(self, text: str) -> list[tuple]:
        """[(glyph name, x advance, x offset, y offset, cluster)] in visual order, font units."""
        import uharfbuzz as hb
        if self._hb is None:
            self._hb = hb.Font(hb.Face(hb.Blob(self.data), self.index))
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self._hb, buf, {})
        return [(self.order[i.codepoint] if i.codepoint < len(self.order) else ".notdef",
                 p.x_advance, p.x_offset, p.y_offset, i.cluster)
                for i, p in zip(buf.glyph_infos, buf.glyph_positions)]

    def char_contours(self, ch: str) -> list[list]:
        """The contours HarfBuzz draws for `ch` alone (the isolated form; every glyph of the cluster, e.g. a base and
        its dot drawn as two glyphs), placed at their positions. Empty when the font lacks the character."""
        if ord(ch) not in self.cmap:
            return []
        glyphs = self.shape(ch)
        if not glyphs or any(g[0] == ".notdef" for g in glyphs):
            return []
        out, x = [], 0
        for name, adv, xo, yo, _cl in glyphs:
            out += [_moved(c, x + xo, yo) for c in _contours(self, name)]
            x += adv
        return out


# --------------------------------------------------------------------------- outlines and rasters
def _contours(face: _Face, name: str) -> list[list]:
    from fontTools.pens.recordingPen import DecomposingRecordingPen
    pen = DecomposingRecordingPen(face.glyphs)
    face.glyphs[name].draw(pen)
    out, cur = [], []
    for op, args in pen.value:
        cur.append((op, args))
        if op in ("closePath", "endPath"):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def _moved(ops, dx: float, dy: float) -> list:
    if not dx and not dy:
        return ops
    return [(op, tuple(None if pt is None else (pt[0] + dx, pt[1] + dy) for pt in args)) for op, args in ops]


def _replay(ops, pen) -> None:
    for op, args in ops:
        getattr(pen, op)(*args)


def _bounds(ops):
    from fontTools.pens.boundsPen import BoundsPen
    p = BoundsPen(None)
    _replay(ops, p)
    return p.bounds


def _area(ops) -> float:
    from fontTools.pens.areaPen import AreaPen
    p = AreaPen(None)
    _replay(ops, p)
    return abs(p.value)


def _touch(a, b) -> bool:
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def _body(contours: list[list]) -> list[list]:
    """The body of a letter, by contour classes: the contours joined to the largest one through touching boxes (a
    tooth that touches only a middle stroke stays), minus small marks (under SMALL_MARK of the largest area) whose
    vertical centre lies outside the largest contour's height (a dot stays out even when its box dips into the
    bowl's). Order kept."""
    cs = [(i, c, _bounds(c), _area(c)) for i, c in enumerate(contours) if _bounds(c)]
    if not cs:
        return []
    main = max(cs, key=lambda x: x[3])
    comp, rest = [main], [x for x in cs if x is not main]
    grew = True
    while grew:
        grew = False
        for x in list(rest):
            if any(_touch(x[2], y[2]) for y in comp):
                comp.append(x)
                rest.remove(x)
                grew = True
    lo, hi = main[2][1], main[2][3]
    keep = [x for x in comp if not (x[3] < SMALL_MARK * main[3] and not lo <= (x[2][1] + x[2][3]) / 2 <= hi)]
    return [x[1] for x in sorted(keep, key=lambda x: x[0])]


def _letter_top(face, letter: str):
    """Font units from the baseline to the top of `letter`'s body (see DOTLESS / DOT_ABOVE), None when not drawn."""
    stand_in = DOTLESS.get(letter)
    if stand_in and ord(stand_in) in face.cmap and face.char_contours(stand_in):
        cs = face.char_contours(stand_in)
    elif letter in DOT_ABOVE:
        cs = _body(face.char_contours(letter))
    else:
        cs = face.char_contours(letter)                    # no dots, or dots below: the full top is the body
    top = max((b[3] for b in (_bounds(c) for c in cs) if b), default=0)
    return top if top > 0 else None


def body_tops(path, index: int = 0, weight=None) -> dict:
    """{letter: body top per em} for the letters of ARABIC_BODY the face draws (a variable font at `weight`)."""
    face = _Face(path, index, weight)
    out = {}
    for letter in ARABIC_BODY:
        top = _letter_top(face, letter)
        if top:
            out[letter] = round(top / face.upm, 4)
    return out


def _raster(face: _Face, items):
    """Coverage array (rows top to bottom) of items [(contour op lists, x, y in font units)] at _PX per em."""
    from fontTools.pens.freetypePen import FreeTypePen
    from fontTools.pens.transformPen import TransformPen
    s = _PX / face.upm
    pen = FreeTypePen(None)
    for contours, x, y in items:
        tp = TransformPen(pen, (s, 0, 0, s, x * s, y * s))
        for c in contours:
            _replay(c, tp)
    return pen.array(contain=True)


def _runs(line) -> list[float]:
    """Ink runs along one scanline, each as its summed coverage (sub-pixel exact for anti-aliased edges)."""
    out, acc = [], 0.0
    for v in line:
        if v > 0.02:
            acc += float(v)
        elif acc:
            out.append(acc)
            acc = 0.0
    if acc:
        out.append(acc)
    return out


def _ink_box(arr):
    import numpy as np
    ys, xs = np.nonzero(arr > 0.5)
    if not len(ys):
        return None
    return int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())


def _contrast(thick, thin) -> float | None:
    if not thick or not thin:
        return None
    return round(1.0 - min(thick, thin) / max(thick, thin), 4)


def _string(face: _Face, text: str):
    """(items for _raster, total advance) of a shaped string, or None when a glyph is missing."""
    glyphs = face.shape(text)
    if not glyphs or any(g[0] == ".notdef" for g in glyphs):
        return None
    items, x = [], 0
    for name, adv, xo, yo, _cl in glyphs:
        items.append((_contours(face, name), x + xo, yo))
        x += adv
    return items, x


def _angularity(face: _Face, chars: str) -> float | None:
    lines = curves = 0
    for ch in chars:
        for c in face.char_contours(ch):
            for op, _args in c:
                if op == "lineTo":
                    lines += 1
                elif op in ("qCurveTo", "curveTo"):
                    curves += 1
    return round(lines / (lines + curves), 4) if lines + curves else None


def _measure(face: _Face) -> dict:
    import numpy as np
    upm, reasons = face.upm, []
    t = {"traits_version": TRAITS_VERSION, "file_sha256": face.sha, "index": face.index, "upm": upm,
         "variable": face.variable, "weight": face.weight}
    xc = face.char_contours("x")
    xb = _bounds([op for c in xc for op in c]) if xc else None
    os2 = face.font["OS/2"] if "OS/2" in face.font else None
    sx = getattr(os2, "sxHeight", 0) if os2 is not None and os2.version >= 2 else 0
    if xb and xb[3] > 0:
        t["x_height"], t["x_height_source"] = round(xb[3] / upm, 4), "ink"
    elif sx and sx > 0:
        t["x_height"], t["x_height_source"] = round(sx / upm, 4), "os2"
    else:
        t["x_height"], t["x_height_source"] = None, None
        reasons.append("x-height: no 'x' glyph and no OS/2 sxHeight")
    heights = [h for h in (_letter_top(face, ch) for ch in ARABIC_BODY) if h]
    t["arabic_body"] = round(statistics.median(heights) / upm, 4) if heights else None
    if not heights:
        reasons.append("Arabic body: none of «س ب ن ي» is drawn")
    cl = None
    oc = face.char_contours("o")
    if oc:
        arr = _raster(face, [(oc, 0, 0)])
        box = _ink_box(arr)
        if box:
            h, v = _runs(arr[(box[0] + box[1]) // 2, :]), _runs(arr[:, (box[2] + box[3]) // 2])
            if len(h) >= 2 and len(v) >= 2:
                cl = _contrast((h[0] + h[-1]) / 2, (v[0] + v[-1]) / 2)
    t["contrast_latin"] = cl
    if cl is None:
        reasons.append("Latin contrast: no measurable 'o'")
    ca = None
    dotless_beh = DOTLESS["ب"]
    ac = face.char_contours("ا")
    bc = face.char_contours(dotless_beh) if ord(dotless_beh) in face.cmap else _body(face.char_contours("ب"))
    if ac and bc:
        a_arr, b_arr = _raster(face, [(ac, 0, 0)]), _raster(face, [(bc, 0, 0)])
        abox, bbox = _ink_box(a_arr), _ink_box(b_arr)
        if abox and bbox:
            stem = _runs(a_arr[(abox[0] + abox[1]) // 2, :])
            base = _runs(b_arr[:, (bbox[2] + bbox[3]) // 2])
            if stem and base:
                ca = _contrast(stem[0], base[-1])
    t["contrast_arabic"] = ca
    if ca is None:
        reasons.append("Arabic contrast: no measurable alef and beh")
    for script, dens, wid, ref, shapes in (("latin", LATIN_DENSITY, LATIN_WIDTH, t["x_height"], LATIN_SHAPES),
                                           ("arabic", ARABIC_DENSITY, ARABIC_WIDTH, t["arabic_body"], ARABIC_SHAPES)):
        t[f"density_{script}"] = t[f"width_{script}"] = t[f"space_{script}"] = None
        if ref:
            got = _string(face, dens)
            if got and got[1] > 0:
                ink = float(np.sum(_raster(face, got[0]))) / (_PX / upm) ** 2
                t[f"density_{script}"] = round(ink / (got[1] * ref * upm), 4)
            w = face.shape(wid)
            if w and all(g[0] != ".notdef" for g in w):
                t[f"width_{script}"] = round(sum(g[1] for g in w) / (len(wid) * ref * upm), 4)
            sp = face.shape(" ")
            if sp and sp[0][0] != ".notdef" and sp[0][1] > 0:
                t[f"space_{script}"] = round(sp[0][1] / (ref * upm), 4)
        t[f"angularity_{script}"] = _angularity(face, shapes)
    t["reasons"] = reasons
    return t


def _is_variable(data: bytes, index: int, name: str) -> bool:
    f = _open(data, index, name)
    try:
        return "fvar" in f and any(a.axisTag == "wght" for a in f["fvar"].axes)
    except _READ_ERRORS as e:
        raise FontProbeError(f"{name}: not a readable font ({type(e).__name__}: {e})") from e


def traits(path, index: int = 0, weight=None) -> dict:
    """The measured traits of a face (see the module docstring). A variable font is instanced at `weight` (clamped to
    its axis; None = its default); a static file is measured as it is. Cached by (file sha256, index, weight of a
    variable font). Raises FontProbeError for a file that is not a readable font."""
    _require()
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError as e:
        raise FontProbeError(f"{p.name}: cannot be read ({e})") from e
    sha = hashlib.sha256(data).hexdigest()
    var = _is_variable(data, index, p.name)
    key = (sha, int(index or 0), int(weight) if (var and weight is not None) else None)
    hit = _CACHE.get(key)
    if hit is not None:
        _STATS["hits"] += 1
        return json.loads(hit)
    _STATS["misses"] += 1
    face = _Face(p, index, weight)
    try:
        t = _measure(face)
    except _READ_ERRORS as e:
        raise FontProbeError(f"{p.name}: cannot be measured ({type(e).__name__}: {e})") from e
    _CACHE[key] = json.dumps(t, sort_keys=True)
    return t


def _ligature_forms(face: _Face, lig: str) -> bool:
    """lam-alef forms: one glyph, or a lam and an alef that both differ from their plain joining forms (fonts that
    build lam-alef from contextual alternates)."""
    got = face.shape(lig)
    if len(got) == 1:
        return got[0][0] != ".notdef"
    by = {g[4]: g[0] for g in got}
    plain_lam = {g[4]: g[0] for g in face.shape(lig[0] + "ب")}.get(0)
    plain_alef = {g[4]: g[0] for g in face.shape("ب" + lig[1])}.get(1)
    return len(got) == 2 and by.get(0) != plain_lam and by.get(1) != plain_alef


def coverage(path, script: str, index: int = 0) -> dict:
    """{"ok", "missing": [characters, or "لا" when the lam-alef ligature does not form]} for "arabic" or "latin".
    An unreadable file is {"ok": False, "missing": [], "error": "..."}."""
    try:
        face = _Face(path, index, instance=False)
    except FontProbeError as e:
        return {"ok": False, "missing": [], "error": str(e)}
    test = ARABIC_TEST if script == "arabic" else LATIN_TEST
    missing = [ch for ch in test if ord(ch) not in face.cmap]
    if script == "arabic":
        missing += [lig for lig in ARABIC_LIGATURES
                    if all(ord(c) in face.cmap for c in lig) and not _ligature_forms(face, lig)]
    return {"ok": not missing, "missing": missing}


def nearest_face(family: list[dict], weight: int, reach: int | None = None) -> dict | None:
    """The face of a static family nearest `weight` by usWeightClass (ties: the heavier); None beyond `reach`."""
    if not family:
        return None
    wc = lambda f: int(f.get("weight_class") or 400)   # noqa: E731
    best = min(family, key=lambda f: (abs(wc(f) - weight), -wc(f)))
    if reach is not None and abs(wc(best) - weight) > reach:
        return None
    return best


def is_superfamily(family: list[dict], weight: int) -> bool:
    """One family whose face for `weight` passes both coverage gates (Latin digits alone are not a Latin side)."""
    f = nearest_face(family, weight)
    if not f:
        return False
    idx = int(f.get("index") or 0)
    return coverage(f["file"], "arabic", idx)["ok"] and coverage(f["file"], "latin", idx)["ok"]


# --------------------------------------------------------------------------- score
def band(score, scale_clamped: bool = False) -> str:
    """auto (>= 70), shown (50-69), refused (< 50). A pair whose latin_scale is clamped keeps its heights apart, so it
    is never automatic: at most shown, with the clamp in its reason."""
    if not isinstance(score, (int, float)):
        return "unmeasured"
    if score >= BAND_AUTO and not scale_clamped:
        return "auto"
    return "shown" if score >= BAND_SHOWN else "refused"


def class_part(ar_class, lat_class) -> tuple:
    """(points, None) for two curated classes; (None, reason) when one is unknown (score() then uses terminal shape)."""
    if ar_class in CLASSES and lat_class in CLASSES:
        if ar_class == lat_class:
            return WEIGHTS["class"], None
        return _PAIR_CLASS.get(frozenset((ar_class, lat_class)), 0), None
    return None, f"class unknown (not curated): terminal shape stands in, at most {UNKNOWN_CLASS_MAX}"


def _lin(gap: float, tol: float, pts: float) -> float:
    return pts * max(0.0, 1.0 - gap / tol)


def _log(ratio: float, tol: float, pts: float) -> float:
    return pts * max(0.0, 1.0 - abs(math.log(ratio)) / math.log(tol))


def _pos(*vals) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0 for v in vals)


def _num(*vals) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in vals)


def _clean(v: float):
    v = round(v, 2)
    return int(v) if v == int(v) else v


def latin_scale(x_height, arabic_body, target: float = TARGET_RATIO) -> dict:
    """{"scale", "clamped", "reason"}: the factor that puts the Latin x-height on the Arabic letter body. `clamped`
    means the heights stay apart: the factor needed lies outside SCALE_RANGE by more than ALIGN_TOL (a clamp that
    still lands within ALIGN_TOL is reported in the reason only)."""
    if not _pos(x_height, arabic_body):
        return {"scale": 1.0, "clamped": False, "reason": "x-height or Arabic body not measured: Latin kept at 1.0"}
    raw = target * float(arabic_body) / float(x_height)
    lo, hi = SCALE_RANGE
    s = min(max(raw, lo), hi)
    clamped = abs(s / raw - 1.0) > ALIGN_TOL
    reason = "" if s == raw else f"latin_scale {raw:.3f} clamped to {s:.2f}: " + \
        ("the heights stay apart" if clamped else f"still within {ALIGN_TOL:.0%}")
    return {"scale": round(s, 4), "clamped": clamped, "reason": reason}


def heights_aligned(x_height, arabic_body, scale, target: float = TARGET_RATIO, tol: float = ALIGN_TOL) -> bool:
    """The scaled Latin x-height sits on the Arabic body: |scale*x_height/body - target| <= tol*target."""
    if not _pos(x_height, arabic_body, scale):
        return False
    return abs(float(scale) * float(x_height) / float(arabic_body) - target) <= tol * target + 1e-9


def score(ar: dict, lat: dict, ar_class=None, lat_class=None, target: float = TARGET_RATIO,
          superfamily: bool = False) -> dict:
    """Score an Arabic face's traits `ar` against a Latin face's traits `lat` (see the module docstring). A
    superfamily (one family, both scripts by design) earns the full class part."""
    parts, reasons, vals = {}, [], {"class": [ar_class, lat_class]}
    if superfamily:
        pts = WEIGHTS["class"]
        vals["superfamily"] = True
    else:
        pts, why = class_part(ar_class, lat_class)
        if pts is None:
            a, b = ar.get("angularity_arabic"), lat.get("angularity_latin")
            pts = _lin(abs(a - b), ANGULARITY_TOL, UNKNOWN_CLASS_MAX) if _num(a, b) else 0.0
            reasons.append(why)
            vals["angularity"] = [a, b]
    parts["class"] = pts
    da, dl = ar.get("density_arabic"), lat.get("density_latin")
    parts["weight"] = _lin(abs(da - dl) / max(da, dl), WEIGHT_TOL, WEIGHTS["weight"]) if _pos(da, dl) else 0.0
    if not _pos(da, dl):
        reasons.append("weight: ink density not measured")
    vals["weight"] = [da, dl]
    xh, body = lat.get("x_height"), ar.get("arabic_body")
    parts["height"] = _log((xh / body) / target, HEIGHT_TOL, WEIGHTS["height"]) if _pos(xh, body) else 0.0
    if not _pos(xh, body):
        reasons.append("height: x-height or Arabic body not measured")
    vals["height"] = [body, xh]
    ca, cl = ar.get("contrast_arabic"), lat.get("contrast_latin")
    parts["contrast"] = _lin(abs(ca - cl), CONTRAST_TOL, WEIGHTS["contrast"]) if _num(ca, cl) else 0.0
    if not _num(ca, cl):
        reasons.append("contrast: not measured")
    vals["contrast"] = [ca, cl]
    half = WEIGHTS["width"] / 2
    wa, wl, sa, sl = ar.get("width_arabic"), lat.get("width_latin"), ar.get("space_arabic"), lat.get("space_latin")
    parts["width"] = (_log(wl / wa, WIDTH_TOL, half) if _pos(wa, wl) else 0.0) + \
                     (_log(sl / sa, WIDTH_TOL, half) if _pos(sa, sl) else 0.0)
    if not _pos(wa, wl, sa, sl):
        reasons.append("width: width or word space not measured")
    vals["width"] = [wa, wl, sa, sl]
    parts = {k: _clean(v) for k, v in parts.items()}
    total = _clean(sum(parts.values()))
    sc = latin_scale(xh, body, target)
    if sc["reason"]:
        reasons.append(sc["reason"])
    return {"score": total, "band": band(total, sc["clamped"]), "parts": parts, "values": vals,
            "latin_scale": sc["scale"], "scale_clamped": sc["clamped"], "reasons": reasons}


def _f(v) -> str:
    return "n/a" if v is None else f"{v:.3f}" if isinstance(v, float) else str(v)


def explain(result: dict) -> str:
    """The score's reason text, one clause per part with its trait values (deterministic)."""
    p, v = result["parts"], result.get("values") or {}
    ac, lc = (v.get("class") or [None, None])[:2]
    cls = f"class {p['class']}/{WEIGHTS['class']} (" + ("one family drawn for both scripts" if v.get("superfamily")
                                                         else f"{ac or 'uncurated'} + {lc or 'uncurated'}")
    if "angularity" in v:
        cls += f"; terminal shape ar {_f(v['angularity'][0])} vs lat {_f(v['angularity'][1])}"
    da, dl = (v.get("weight") or [None, None])[:2]
    body, xh = (v.get("height") or [None, None])[:2]
    ca, cl = (v.get("contrast") or [None, None])[:2]
    wa, wl, sa, sl = (v.get("width") or [None] * 4)[:4]
    clauses = [cls + ")",
               f"weight {p['weight']}/{WEIGHTS['weight']} (ink density ar {_f(da)} vs lat {_f(dl)})",
               f"height {p['height']}/{WEIGHTS['height']} (x-height {_f(xh)} vs Arabic body {_f(body)}, target "
               f"{TARGET_RATIO:.2f}, latin_scale {result.get('latin_scale')})",
               f"contrast {p['contrast']}/{WEIGHTS['contrast']} (ar {_f(ca)} vs lat {_f(cl)})",
               f"width {p['width']}/{WEIGHTS['width']} (proportion ar {_f(wa)} vs lat {_f(wl)}, word space ar "
               f"{_f(sa)} vs lat {_f(sl)})"]
    text = f"score {float(result['score']):.2f} ({result.get('band') or band(result['score'])}): " + "; ".join(clauses)
    if result.get("reasons"):
        text += ". Notes: " + "; ".join(result["reasons"])
    return text


# --------------------------------------------------------------------------- licence
def is_ofl(name13, name14) -> bool:
    n13, n14 = str(name13 or "").lower(), str(name14 or "").lower()
    return "open font license" in n13 or "/ofl" in n14 or "openfontlicense.org" in n14


def licence(path, index: int = 0) -> dict:
    """The OFL proof of a face: nameID 13/14, the sha256 of the OFL.txt next to it, the font file's sha256; "ok" only
    when the name table says OFL and the folder's OFL.txt holds the OFL text."""
    p = Path(path)
    out = {"name13": None, "name14": None, "ofl_sha256": None, "file_sha256": None, "ok": False, "reason": ""}
    try:
        data = p.read_bytes()
    except OSError as e:
        out["reason"] = f"{p.name}: cannot be read ({type(e).__name__})"
        return out
    try:
        font = _open(data, index, p.name)
        from fontTools.ttLib import TTLibError
        try:
            nm = font["name"]
            n13, n14 = nm.getDebugName(13), nm.getDebugName(14)
        except (TTLibError,) + _READ_ERRORS as e:          # a truncated or damaged name table
            raise FontProbeError(f"{p.name}: its name table cannot be read ({type(e).__name__})") from e
    except FontProbeError as e:
        out["reason"] = str(e)
        return out
    out.update(name13=n13, name14=n14, file_sha256=hashlib.sha256(data).hexdigest())
    ofl = p.parent / "OFL.txt"
    text = ""
    if ofl.is_file():
        out["ofl_sha256"] = text_sha256(ofl)
        text = ofl.read_text(encoding="utf-8", errors="replace").upper()
    if not is_ofl(out["name13"], out["name14"]):
        out["reason"] = f"{p.name}: the name table does not say SIL Open Font License"
    elif "SIL OPEN FONT LICENSE" not in text:
        out["reason"] = f"{p.name}: no OFL.txt with the OFL text next to it"
    else:
        out["ok"] = True
    return out


# --------------------------------------------------------------------------- pairs from the client and the table
PAIRING_SOURCES = ("client", "table")
LATIN_SCALE_RANGE = (0.5, 2.0)        # a latin_scale set by hand (the client database's range)


def missing_modules(names=None) -> list[str]:
    """The required packages that cannot be imported here (a broken install): fontTools, uharfbuzz, freetype-py,
    numpy. Empty on a healthy engine runtime (all are pinned in every lock)."""
    import importlib
    out = []
    for name in names or REQUIRED_MODULES:
        try:
            importlib.import_module(name)
        except ImportError:
            out.append(name)
    return out


def _families(typography: dict) -> dict:
    fams: dict = {}
    raw = (typography or {}).get("families") or {}
    for f in typography_faces(typography or {}):
        if f["italic"] or not f.get("file"):
            continue
        wc = f["weight"]
        for w in (raw.get(f["family"]) or {}).get("weights") or []:
            if w.get("file") == f["file"] and _pos(w.get("weight_class")):
                wc = int(w["weight_class"])
        fams.setdefault(f["family"], []).append({"family": f["family"], "file": f["file"], "ps": f.get("ps"),
                                                 "weight_class": wc, "index": 0})
    return fams


def _brand_weights() -> dict:
    """brand.json font_roles_fallback.weights of the active profile (what font_roles.resolve's callers pass)."""
    from .common import font_role_fallback
    w = (font_role_fallback() or {}).get("weights")
    return w if isinstance(w, dict) else {}


def _resolved(typography: dict, role: str, fallback_weights: dict | None, fams: dict) -> tuple:
    """(the client's face for the role or None, the role's weight): font_roles.resolve, the one resolver every renderer
    uses (typography.json roles, brand.json font_roles_fallback, the house default)."""
    from .font_roles import resolve
    r = resolve(typography or {}, role, fallback_weights or {})
    face = next((f for fs in fams.values() for f in fs if r.get("file") and f["file"] == r["file"]), None)
    if face:
        return face, int(face["weight_class"])
    wanted = str(r.get("wanted") or "")
    if wanted in WEIGHT:
        return None, WEIGHT[wanted]
    return None, int(wanted) if wanted.isdigit() else WEIGHT[DEFAULT_ROLE_STYLE.get(role, "regular")]


def role_weight(role: str, typography: dict | None = None, fallback_weights: dict | None = None) -> int:
    """The weight `role` is drawn at, as a usWeightClass number (see _resolved)."""
    return _resolved(typography or {}, role, fallback_weights, _families(typography or {}))[1]


def _client_face(fams: dict, spec, weight: int) -> dict | None:
    """A face named by a pairing entry: a family name (its face nearest the role weight), a PostScript name or a font
    file name (case folded where the file system folds it)."""
    name = (spec or {}).get("family") if isinstance(spec, dict) else spec
    if not name or not isinstance(name, str):
        return None
    if name in fams:
        return nearest_face(fams[name], weight)
    allf = [f for fs in fams.values() for f in fs]
    hit = next((f for f in allf if f.get("ps") and f["ps"] == name), None)
    if hit:
        return hit
    key = _fold(name)
    return next((f for f in allf if _fold(Path(str(f["file"])).name) == key or _fold(f["file"]) == key), None)


def _pairing_entry(typography: dict, role: str) -> tuple:
    """The client's pairing entry for `role`, checked: (entry or None, findings). A source other than client/table
    drops the entry; a latin_scale that is not a finite number in LATIN_SCALE_RANGE, or a class that is not one of
    CLASSES, is dropped from it. Each is named in the findings (a hand-edited typography.json reaches here directly)."""
    pairing = (typography or {}).get("pairing")
    if pairing is None:
        return None, []
    if not isinstance(pairing, dict):
        return None, ["typography.json pairing is not a mapping: ignored"]
    e = pairing.get(role)
    if e is None:
        return None, []
    if not isinstance(e, dict):
        return None, [f"pairing.{role} is not a mapping: ignored"]
    src = e.get("source", "client")
    if src not in PAIRING_SOURCES:
        return None, [f"pairing.{role}: source {src!r} is not client or table: ignored"]
    out, found = dict(e, source=src), []
    ls = e.get("latin_scale")
    lo, hi = LATIN_SCALE_RANGE
    if ls is not None and not (_num(ls) and lo <= ls <= hi):
        found.append(f"pairing.{role}: latin_scale {ls!r} is not a number in {lo}-{hi}: the measured scale is used")
        out.pop("latin_scale")
    for k in ("class", "latin_class"):
        if out.get(k) is not None and out[k] not in CLASSES:
            found.append(f"pairing.{role}: {k} {out[k]!r} is not one of {', '.join(CLASSES)}: ignored")
            out.pop(k)
    return out, found


def _face_out(f: dict) -> dict:
    out = {"family": f.get("family"), "ps": f.get("ps"), "file": f.get("file"), "weight_class": f.get("weight_class")}
    if f.get("instance") is not None:
        out["instance"] = f["instance"]
    return out


def measure_pair(ar_face: dict, lat_face: dict, weight: int, ar_class=None, lat_class=None,
                 superfamily: bool = False) -> dict:
    """Score two faces ({file, index}) at `weight`: score() plus {coverage, findings}. An unreadable face gives score
    None and a finding (never an exception)."""
    findings, cov = [], {}
    try:
        ta = traits(ar_face["file"], int(ar_face.get("index") or 0), weight)
        tl = traits(lat_face["file"], int(lat_face.get("index") or 0), weight)
    except FontProbeError as e:
        return {"score": None, "band": "unmeasured", "parts": {}, "values": {}, "latin_scale": 1.0,
                "scale_clamped": False, "reasons": [str(e)], "coverage": {}, "findings": [str(e)]}
    for side, f in (("arabic", ar_face), ("latin", lat_face)):
        c = coverage(f["file"], side, int(f.get("index") or 0))
        cov[side] = c["missing"]
        if not c["ok"]:
            findings.append(f"{f.get('family') or Path(str(f['file'])).name} ({side}) cannot draw: "
                            + " ".join(c["missing"]))
    r = score(ta, tl, ar_class, lat_class, superfamily=superfamily)
    r.update(coverage=cov, findings=findings)
    return r


def _pair_out(ar: dict, lat: dict, r: dict, source: str, latin_scale_override=None, kind: str | None = None) -> dict:
    out = {"arabic": _face_out(ar), "latin": _face_out(lat), "source": source, "score": r.get("score"),
           "band": band(r.get("score"), r.get("scale_clamped")), "latin_scale": r.get("latin_scale", 1.0),
           "parts": r.get("parts") or {},
           "explain": explain(r) if r.get("parts") else "; ".join(r.get("reasons") or ["not measured"])}
    if latin_scale_override is not None:
        out["latin_scale"] = float(latin_scale_override)
    if kind:
        out["kind"] = kind
    out["reason"] = "" if out["band"] == "auto" else out["explain"]
    return out


def _row_values(row: dict) -> dict:
    t = row.get("traits") or {}
    return {"superfamily": row.get("kind") == "superfamily",
            "class": [(row.get("class") or {}).get("arabic"), (row.get("class") or {}).get("latin")],
            "weight": [t.get("density_arabic"), t.get("density_latin")],
            "height": [t.get("arabic_body"), t.get("x_height")],
            "contrast": [t.get("contrast_arabic"), t.get("contrast_latin")],
            "width": [t.get("width_arabic"), t.get("width_latin"), t.get("space_arabic"), t.get("space_latin")]}


def _row_weights(row: dict) -> list[int]:
    ws = row.get("weights")
    if isinstance(ws, list):
        return [int(w) for w in ws]
    return [int(row["weight"])] if isinstance(row.get("weight"), (int, float)) else []


def row_key(row: dict) -> tuple:
    """Table order: Arabic class, Latin class, score (high first), Arabic family, Latin family, weights."""
    cls = row.get("class") or {}
    sc = row.get("score")
    return (str(cls.get("arabic") or ""), str(cls.get("latin") or ""), -(sc if _num(sc) else -1),
            str((row.get("arabic") or {}).get("family") or ""), str((row.get("latin") or {}).get("family") or ""),
            _row_weights(row))


def _rows_for(table: dict | None, weight: int) -> list:
    """The measured rows serving `weight`: rows listing it, else the rows of the nearest row weight within
    WEIGHT_REACH (a role resolved to 600 uses the 500/700 rows nearest it)."""
    rows = [r for r in (table or {}).get("rows") or [] if r.get("status") == "measured"]
    exact = [r for r in rows if weight in _row_weights(r)]
    if exact:
        return exact
    near = min(ROW_WEIGHTS, key=lambda w: (abs(w - weight), -w))
    return [r for r in rows if near in _row_weights(r)] if abs(near - weight) <= WEIGHT_REACH else []


def _row_pair(r: dict) -> dict:
    res = {"score": r["score"], "latin_scale": r.get("latin_scale", 1.0), "parts": r.get("parts") or {},
           "scale_clamped": bool(r.get("scale_clamped")), "values": _row_values(r), "reasons": r.get("reasons") or []}
    if not res["parts"]:
        res["parts"] = {k: 0 for k in WEIGHTS}
    return _pair_out(r["arabic"], r["latin"], res, "table")


def _draws(face: dict, findings: list) -> tuple:
    """(draws Arabic letters, draws Latin letters, passes the Arabic gate, passes the Latin gate) for a client face. A
    gate miss on a script the face does draw is a finding, never a reason to leave the client's face."""
    idx, name = int(face.get("index") or 0), face.get("family") or Path(str(face["file"])).name
    ca, cl = coverage(face["file"], "arabic", idx), coverage(face["file"], "latin", idx)
    for c in (ca, cl):
        if c.get("error") and c["error"] not in findings:
            findings.append(c["error"])
    ar = not ca.get("error") and "ا" not in ca["missing"] and "ب" not in ca["missing"]
    la = not cl.get("error") and "a" not in cl["missing"] and "A" not in cl["missing"]
    for script, drawn, c in (("arabic", ar, ca), ("latin", la, cl)):
        if drawn and not c["ok"]:
            findings.append(f"{name} ({script}) cannot draw: " + " ".join(c["missing"]))
    return ar, la, ca["ok"], cl["ok"]


def _partner(anchor: dict, anchor_script: str, fams: dict, rows: list, weight: int, locate, findings: list):
    """The best partner measured against the client's own face `anchor` (drawn in `anchor_script`): the client's own
    families of the other script first, then the table faces of the other script found on this computer. Every
    candidate passes its own script's gate; the anchor's gate misses are findings. Returns a pair dict (>= 50) or
    None."""
    other = "latin" if anchor_script == "arabic" else "arabic"
    own, table = [], []
    for name in sorted(fams):
        if name == anchor.get("family"):
            continue
        f = nearest_face(fams[name], weight)
        if f and coverage(f["file"], other, int(f.get("index") or 0))["ok"]:
            own.append((f, None))
    if locate is not None:
        seen = set()
        for r in sorted(rows, key=row_key):
            side = r[other]
            key = (side.get("family"), side.get("file"), side.get("instance"))
            if key in seen or side.get("family") in fams:
                continue
            seen.add(key)
            file = locate(side)
            if file:
                table.append((dict(side, file=file, index=0), (r.get("class") or {}).get(other)))
    for group, source in ((own, "client-fonts"), (table, "table")):
        best = None
        for f, cls in group:
            ar, la = (anchor, f) if anchor_script == "arabic" else (f, anchor)
            r = measure_pair(ar, la, weight, cls if other == "arabic" else None, cls if other == "latin" else None)
            if r["score"] is not None and (best is None or r["score"] > best[0]["score"]):
                best = (r, ar, la)
        if best and band(best[0]["score"], best[0]["scale_clamped"]) in ("auto", "shown"):
            findings += [x for x in best[0]["findings"] if x not in findings]
            kind = None if source == "client-fonts" else f"client-{anchor_script}"
            return _pair_out(best[1], best[2], best[0], source, kind=kind)
    return None


def pick(role: str = "caption", typography: dict | None = None, table: dict | None = None, *, locate=None,
         fallback_weights: dict | None = None) -> dict:
    """The pair for `role`: {"pair": {...} | None, "findings": [...], "reason": str}. The role's face and weight come
    from font_roles.resolve (typography.json roles, then `fallback_weights`, by default brand.json
    font_roles_fallback.weights, then the house default). Order:
      1. the client's pairing (typography.json `pairing.<role>`, checked): source client always wins with its score
         shown; a stored table pair is used while it still scores >= 50;
      2. when the role's face is the client's own: a superfamily only when that face's own family passes both gates;
         otherwise the other script is measured against that very face (the client's own families first, then the
         installed table faces) and the best >= 50 wins; table rows for the face's own family are taken as they are
         when nothing can be measured (no locate). Another family's pair is never handed over;
      3. no client face: the table rows serving the role's weight, best score first.
    `locate(face) -> file | None` says which table faces are on this computer. None when nothing reaches 50: the
    caller keeps today's font chain. A broken install (a required package missing) returns None with that finding."""
    miss = missing_modules()
    if miss:
        why = f"font pairing unavailable: {', '.join(miss)} cannot be imported (run reel setup): today's chain is kept"
        return {"pair": None, "findings": [why], "reason": why}
    typography = typography if isinstance(typography, dict) else {}
    table = load_table() if table is None else table
    fams, findings = _families(typography), []
    fallback = _brand_weights() if fallback_weights is None else fallback_weights
    anchor, weight = _resolved(typography, role, fallback, fams)
    entry, notes = _pairing_entry(typography, role)
    findings += notes
    if entry:
        src = entry["source"]
        ar, lat = _client_face(fams, entry.get("arabic"), weight), _client_face(fams, entry.get("latin"), weight)
        for side, f in (("arabic", ar), ("latin", lat)):
            if f is None:
                findings.append(f"pairing.{role}.{side}: {entry.get(side)!r} is not a face in typography.json")
        if ar and lat:
            r = measure_pair(ar, lat, weight, entry.get("class"), entry.get("latin_class"),
                             superfamily=ar.get("family") == lat.get("family"))
            findings += r["findings"]
            if src == "client" or band(r["score"], r["scale_clamped"]) in ("auto", "shown"):
                return {"pair": _pair_out(ar, lat, r, src, entry.get("latin_scale")), "findings": findings,
                        "reason": ""}
            findings.append(f"pairing.{role} (table) now scores {r['score']}: not used")
    rows = _rows_for(table, weight)
    usable = [r for r in rows if band(r.get("score"), r.get("scale_clamped")) in ("auto", "shown")]
    if anchor:
        draws_ar, draws_la, gate_ar, gate_la = _draws(anchor, findings)
        name = anchor.get("family")
        if draws_ar or draws_la:
            if draws_ar and draws_la and gate_ar and gate_la:
                r = measure_pair(anchor, anchor, weight, superfamily=True)
                if band(r["score"], r["scale_clamped"]) in ("auto", "shown"):
                    return {"pair": _pair_out(anchor, anchor, r, "superfamily"), "findings": findings, "reason": ""}
                findings.append(f"{name}: one family for both scripts scoring {r['score']}: not used")
            script = "arabic" if draws_ar else "latin"
            got = _partner(anchor, script, fams, rows, weight, locate, findings)
            if got:
                return {"pair": got, "findings": findings, "reason": ""}
            if locate is None:
                same = sorted((r for r in usable if r[script].get("family") == name), key=lambda r: (-r["score"],)
                              + row_key(r))
                if same:
                    return {"pair": _row_pair(same[0]), "findings": findings, "reason": ""}
            why = (f"nothing scores >= {BAND_SHOWN:.0f} against the client's {script} face {name} for {role} "
                   f"({weight}): today's font chain is kept")
            return {"pair": None, "findings": findings, "reason": why}
    usable.sort(key=lambda r: (-r["score"],) + row_key(r))
    for r in usable:
        if locate is not None:
            gone = [r[s]["family"] for s in ("arabic", "latin") if not locate(r[s])]
            if gone:
                findings.append(f"table pair {r['arabic']['family']} + {r['latin']['family']}: "
                                f"{', '.join(gone)} not on this computer")
                continue
        return {"pair": _row_pair(r), "findings": findings, "reason": ""}
    return {"pair": None, "findings": findings,
            "reason": f"no pair scoring >= {BAND_SHOWN:.0f} serves {role} ({weight}): today's font chain is kept"}


# --------------------------------------------------------------------------- the curated table
def load_table(path=None) -> dict:
    p = Path(path) if path else DEFAULT_TABLE
    return json.loads(p.read_text(encoding="utf-8"))


def _rel(p: Path, rel_root) -> str | None:
    if not rel_root:
        return None
    try:
        return p.resolve().relative_to(Path(rel_root).resolve()).as_posix()
    except ValueError:
        return None


def _scan(roots, rel_root) -> tuple[dict, list]:
    """Families under the roots: {family: {source, origin, ofl_sha256, name13, name14, files: [face]}}, plus the
    refusals (unreadable or non-OFL files). Italic faces are left out."""
    from fontTools.ttLib import TTCollection, TTLibError
    fams, refusals = {}, []
    for root in roots:
        root = Path(root)
        files = sorted((q for q in root.rglob("*") if q.suffix.lower() in _FONT_EXT and q.is_file()),
                       key=lambda q: q.relative_to(root).as_posix())
        for p in files:
            try:
                data = p.read_bytes()
                count = len(TTCollection(io.BytesIO(data)).fonts) if p.suffix.lower() in (".ttc", ".otc") else 1
                for idx in range(count):
                    f = _open(data, idx, p.name)
                    nm, os2 = f["name"], f["OS/2"]
                    fam = nm.getDebugName(16) or nm.getDebugName(1)
                    style = str(nm.getDebugName(17) or nm.getDebugName(2) or "").lower()
                    if (os2.fsSelection & 1) or "italic" in style:
                        continue
                    lic = licence(p, idx)
                    if not lic["ok"]:
                        refusals.append(f"{fam} ({p.name}): {lic['reason']}")
                        continue
                    axes = {a.axisTag: a for a in f["fvar"].axes} if "fvar" in f else {}
                    src = _rel(p.parent, rel_root)
                    info = fams.setdefault(fam, {"source": src, "origin": "repo" if src else "external",
                                                 "ofl_sha256": lic["ofl_sha256"], "name13": lic["name13"],
                                                 "name14": lic["name14"], "files": []})
                    info["files"].append({"file": p.name, "ps": nm.getDebugName(6), "index": idx,
                                          "weight_class": int(os2.usWeightClass),
                                          "wght": [axes["wght"].minValue, axes["wght"].maxValue] if "wght" in axes
                                          else None, "sha256": lic["file_sha256"], "_path": p})
            except (FontProbeError, TTLibError) + _READ_ERRORS as e:
                refusals.append(f"{p.name}: not a readable font ({type(e).__name__}: {e})")
    return fams, refusals


def _serve(info: dict, weight: int) -> dict | None:
    """The face of a scanned family for a row weight: a variable face instanced at the weight (clamped to its axis,
    within WEIGHT_REACH), else the nearest static file within WEIGHT_REACH (a one-file family: always)."""
    for f in info["files"]:
        if f["wght"]:
            inst = int(min(max(weight, f["wght"][0]), f["wght"][1]))
            if abs(inst - weight) <= WEIGHT_REACH:
                return dict(f, instance=inst)
    static = [f for f in info["files"] if not f["wght"]]
    if len(static) == 1 and len(info["files"]) == 1:
        return dict(static[0], instance=None)
    f = nearest_face(static, weight, WEIGHT_REACH)
    return dict(f, instance=None) if f else None


def _lic(info: dict, f: dict) -> dict:
    return {"name13": info["name13"], "name14": info["name14"], "ofl_sha256": info["ofl_sha256"],
            "file_sha256": f["sha256"]}


def _side(name: str, f: dict) -> dict:
    return {"family": name, "file": f["file"], "ps": f["ps"], "weight_class": f["weight_class"],
            "instance": f["instance"]}


def build_table(roots, curation: dict, rel_root=None) -> dict:
    """The table from the OFL families under `roots` and the curation (usually the current table): its `families`
    ({name: {class, use, note}}) say which families pair and in which class; its rows and families measured from a
    folder outside `rel_root` are kept when that folder is not among the roots this time. A pair is a superfamily (one
    family passing both coverage gates) or an Arabic family with a Latin-only family whose classes earn at least
    PAIR_MIN_CLASS. Raises PairingRefused (naming every bad file) when a font is unreadable or not OFL."""
    fams, refusals = _scan([Path(r) for r in roots], rel_root)
    if refusals:
        raise PairingRefused("font-pairings: refused, nothing written:\n  " + "\n  ".join(refusals))
    cur = curation.get("families") or {}
    prev_rows = [r for r in curation.get("rows") or [] if r.get("status") == "measured"]
    carried = {n for n, c in cur.items() if n not in fams and c.get("origin") == "external" and c.get("files")}
    findings = [f"{n}: found but not curated (no class): not paired" for n in sorted(fams) if n not in cur]
    findings += [f"{n}: not used ({cur[n].get('note') or 'curation'})" for n in sorted(fams)
                 if n in cur and not cur[n].get("use", True)]
    use = {n: i for n, i in fams.items() if n in cur and cur[n].get("use", True)}
    cov: dict = {}

    def gate(name, f, script):
        key = (name, f["file"], f["index"], script)
        if key not in cov:
            cov[key] = coverage(f["_path"], script, f["index"])
        return cov[key]

    misses: dict = {}
    pairs: dict = {}
    for w in ROW_WEIGHTS:
        for an in sorted(use):
            af = _serve(use[an], w)
            if not af:
                continue
            ga = gate(an, af, "arabic")
            if not ga["ok"]:
                if "ا" not in ga["missing"] and an not in misses:      # an Arabic family with a gap, not a Latin one
                    misses[an] = f"Arabic coverage gate: {af['file']} cannot draw " + " ".join(ga["missing"])
                continue
            for ln in sorted(use):
                lf = _serve(use[ln], w)
                if not lf:
                    continue
                if ln != an:
                    lf_ar = gate(ln, lf, "arabic")
                    if lf_ar["ok"] or (class_part(cur[an].get("class"), cur[ln].get("class"))[0] or 0) < PAIR_MIN_CLASS:
                        continue
                gl = gate(ln, lf, "latin")
                if not gl["ok"]:
                    if "A" not in gl["missing"] and ln not in misses:
                        misses[ln] = f"Latin coverage gate: {lf['file']} cannot draw " + " ".join(gl["missing"])
                    continue
                key = (an, af["file"], af["index"], af["instance"], ln, lf["file"], lf["index"], lf["instance"])
                if key in pairs:
                    pairs[key]["weights"].append(w)
                    continue
                try:
                    ta = traits(af["_path"], af["index"], af["instance"])
                    tl = traits(lf["_path"], lf["index"], lf["instance"])
                except FontProbeError as e:
                    raise PairingRefused(f"font-pairings: refused, nothing written:\n  {e}") from e
                r = score(ta, tl, cur[an].get("class"), cur[ln].get("class"), superfamily=an == ln)
                pairs[key] = {
                    "weights": [w], "arabic": _side(an, af), "latin": _side(ln, lf),
                    "kind": "superfamily" if an == ln else "pair",
                    "class": {"arabic": cur[an].get("class"), "latin": cur[ln].get("class")},
                    "score": r["score"], "band": r["band"], "parts": r["parts"],
                    "latin_scale": r["latin_scale"], "scale_clamped": r["scale_clamped"],
                    "traits": {k: (ta if k.endswith("arabic") or k == "arabic_body" else tl)[k] for k in
                               ("arabic_body", "x_height", "density_arabic", "density_latin", "contrast_arabic",
                                "contrast_latin", "width_arabic", "width_latin", "space_arabic", "space_latin")},
                    "reasons": r["reasons"], "status": "measured",
                    "licence": {"arabic": _lic(use[an], af), "latin": _lic(use[ln], lf)}}
    for line in curation.get("findings") or []:            # a carried family keeps its coverage-gate finding
        name, _, rest = str(line).partition(": ")
        if name in carried and "coverage gate" in rest:
            misses.setdefault(name, rest)
    findings += [f"{n}: {misses[n]}" for n in sorted(misses)]
    rows = list(pairs.values())
    live = set(use) | carried
    rows += [r for r in prev_rows if {r["arabic"]["family"], r["latin"]["family"]} & carried
             and {r["arabic"]["family"], r["latin"]["family"]} <= live]
    rows.sort(key=row_key)
    in_rows = {r[s]["family"] for r in rows for s in ("arabic", "latin")}
    families = {}
    for name in sorted(cur):
        c = cur[name]
        entry = {"class": c.get("class"), "use": c.get("use", True), "note": c.get("note", "")}
        if name in carried:
            entry.update({k: c.get(k) for k in ("source", "origin", "ofl_sha256", "files")})
        elif name in fams:
            i = fams[name]
            entry.update(source=i["source"], origin=i["origin"], ofl_sha256=i["ofl_sha256"],
                         files=[{"file": f["file"], "ps": f["ps"], "weight_class": f["weight_class"], "wght": f["wght"],
                                 "sha256": f["sha256"]}
                                for f in sorted(i["files"], key=lambda f: (f["weight_class"], f["file"]))])
        else:
            entry.update(source=None, origin="absent", ofl_sha256=None, files=[])
        families[name] = entry
    candidates = []
    for name in sorted(cur):
        if name in in_rows or not cur[name].get("use", True):
            continue
        if name in carried:                                 # its folder is not given this time: the earlier reason
            prev = next((c for c in curation.get("candidates") or [] if c.get("family") == name), None)
            reason = prev["reason"] if prev and prev.get("reason") else "measured earlier: no row qualified"
        elif name in misses:
            reason = misses[name]
        elif name in fams:
            reason = "no partner family of a matching class in the measured folders"
        else:
            reason = "font files not in the measured folders (download needs the owner's OK)"
        candidates.append({"family": name, "class": cur[name].get("class"), "status": "candidate-unmeasured",
                           "reason": reason})
    return {"version": TABLE_VERSION,
            "about": curation.get("about") or "",
            "method": {"traits_version": TRAITS_VERSION, "weights": WEIGHTS,
                       "bands": {"auto": BAND_AUTO, "shown": BAND_SHOWN}, "target_ratio": TARGET_RATIO,
                       "align_tol": ALIGN_TOL, "scale_range": list(SCALE_RANGE), "row_weights": list(ROW_WEIGHTS),
                       "weight_reach": WEIGHT_REACH, "pair_min_class": PAIR_MIN_CLASS, "arabic_test": ARABIC_TEST,
                       "arabic_ligatures": list(ARABIC_LIGATURES), "latin_test": LATIN_TEST},
            "families": families, "candidates": candidates, "rows": rows, "findings": findings}


_ROW_KEYS = ("weights", "arabic", "latin", "class", "score", "band", "latin_scale", "status", "licence")


def check_table(table: dict) -> list[str]:
    """Structure problems of a table (empty = fine): every row is measured, has its fields and a full OFL proof per
    face; every candidate is "candidate-unmeasured" with a reason."""
    bad = []
    for i, r in enumerate(table.get("rows") or []):
        if r.get("status") != "measured":
            bad.append(f"rows[{i}]: status {r.get('status')!r} (only measured rows belong in rows)")
            continue
        bad += [f"rows[{i}]: no {k}" for k in _ROW_KEYS if k not in r]
        for side in ("arabic", "latin"):
            lic = (r.get("licence") or {}).get(side) or {}
            bad += [f"rows[{i}].licence.{side}: no {k}" for k in ("name13", "name14", "ofl_sha256", "file_sha256")
                    if not lic.get(k)]
            if lic and not is_ofl(lic.get("name13"), lic.get("name14")):
                bad.append(f"rows[{i}].licence.{side}: not OFL")
        if _num(r.get("score")) and r.get("band") != band(r["score"], r.get("scale_clamped")):
            bad.append(f"rows[{i}]: band {r.get('band')} does not match score {r['score']}")
    for i, c in enumerate(table.get("candidates") or []):
        if c.get("status") != "candidate-unmeasured" or not c.get("reason"):
            bad.append(f"candidates[{i}]: must be candidate-unmeasured with a reason")
    return bad


def dumps_table(table: dict) -> str:
    """The table as text: two-space indent, one row per line (readable diffs), UTF-8 characters kept, LF."""
    rows = table.get("rows") or []
    head = json.dumps(dict(table, rows="\x00ROWS\x00"), ensure_ascii=False, indent=2)
    body = "[]" if not rows else "[\n" + ",\n".join("    " + json.dumps(r, ensure_ascii=False) for r in rows) + "\n  ]"
    return head.replace('"\\u0000ROWS\\u0000"', body) + "\n"


def write_table(path, table: dict) -> Path:
    """Write the table: the same input gives the same bytes. Refuses a table with structure problems before touching
    the disk."""
    bad = check_table(table)
    if bad:
        raise PairingRefused("font-pairings: refused, nothing written:\n  " + "\n  ".join(bad))
    text = dumps_table(table)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, p)
    return p


# --------------------------------------------------------------------------- specimen sheet (for the designer)
SPECIMEN_AR, SPECIMEN_LAT = "نتيجة التحليل سليمة", "MRI scan box"


def _line(face: _Face, text: str) -> list[tuple]:
    """[(x in font units, cluster)] of each glyph of `text` shaped as one line: HarfBuzz orders an Arabic line right
    to left (the first word's clusters sit rightmost)."""
    out, x = [], 0
    for _name, adv, xo, _yo, cl in face.shape(text):
        out.append((x + xo, cl))
        x += adv
    return out


def _ink_top(face: _Face, items) -> float:
    """Font units from the baseline to the top of the ink of `items`."""
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.transformPen import TransformPen
    pen = BoundsPen(None)
    for contours, x, y in items:
        for c in contours:
            _replay(c, TransformPen(pen, (1, 0, 0, 1, x, y)))
    return pen.bounds[3] if pen.bounds else 0.0


def specimen_sheet(table: dict, roots, out, width: int = 1600) -> dict:
    """An AR+EN specimen PNG for the designer: one band per measured row, the Arabic sample (shaped as one right-to-left
    line) and the Latin sample at latin_scale on one baseline, with the Arabic body line (black) and the scaled
    x-height line (grey), both measured afresh from the drawn faces, never copied from the table.
    {"rows", "missing", "file", "bands": [{arabic_px, latin_px, arabic_body_em, x_height_em}]}; a row whose font files
    are not under `roots` is listed in "missing"."""
    import numpy as np
    from PIL import Image, ImageDraw
    files: dict = {}
    for root in roots:
        for p in sorted(Path(root).rglob("*")):
            if p.suffix.lower() in _FONT_EXT:
                files.setdefault(p.name, p)
    rows = [r for r in table.get("rows") or [] if r.get("status") == "measured"]
    em, band_h, base, missing, bands, opened, geometry = 64.0, 140, 96, [], [], {}, []
    for r in rows:
        pa, pl = files.get(r["arabic"]["file"]), files.get(r["latin"]["file"])
        if not pa or not pl:
            missing.append(f"{r['arabic']['file']} / {r['latin']['file']}")
            continue
        img = Image.new("L", (width, band_h), 255)
        d = ImageDraw.Draw(img)
        x, guides, geo = 20, [], {}
        for side, p, text, scale in (("arabic", pa, SPECIMEN_AR, 1.0), ("latin", pl, SPECIMEN_LAT, r["latin_scale"])):
            key = (str(p), r[side].get("instance"))
            face = opened.get(key) or opened.setdefault(key, _Face(p, 0, r[side].get("instance")))
            got = _string(face, text)                      # one shaped line: Arabic words run right to left
            items = got[0] if got else []
            if not items:
                missing.append(f"{p.name}: cannot draw the sample")
                continue
            k = em * float(scale) / _PX
            arr = np.clip(_raster(face, items), 0, 1)
            top_px = _ink_top(face, items) * _PX / face.upm
            ink = Image.fromarray((255 * arr).astype("uint8"))
            size = (max(1, int(round(ink.width * k))), max(1, int(round(ink.height * k))))
            ink = ink.resize(size)
            img.paste(0, (x, base - int(round(top_px * k))), ink)
            fresh = traits(p, 0, r[side].get("instance"))
            h = fresh["arabic_body" if side == "arabic" else "x_height"] or 0
            geo[f"{side}_px"] = size[1]
            geo["arabic_body_em" if side == "arabic" else "x_height_em"] = h
            guides.append((base - int(round(em * float(scale) * h)), 0 if side == "arabic" else 140))
            x += size[0] + 40
        for y, shade in guides:
            d.line([(10, y), (x, y)], fill=shade, width=1)
        d.line([(10, base), (x, base)], fill=190, width=1)
        d.text((min(x + 10, width - 380), 30), f"{r['arabic']['family']} + {r['latin']['family']} "
               f"{r.get('weights')}", fill=0)
        d.text((min(x + 10, width - 380), 55), f"score {r['score']} ({r['band']}) latin_scale {r['latin_scale']}",
               fill=0)
        bands.append(img)
        geometry.append(geo)
    sheet = Image.new("L", (width, max(1, band_h * len(bands))), 255)
    for i, b in enumerate(bands):
        sheet.paste(b, (0, i * band_h))
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(p)
    return {"rows": len(bands), "missing": missing, "file": str(p), "bands": geometry}


# --------------------------------------------------------------------------- command line (table builder)
def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m lib.font_pairing", description="Build the font-pairing table")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="measure the OFL families under --fonts; --write rewrites --table")
    b.add_argument("--fonts", action="append", required=True, help="a folder of font families (each with OFL.txt)")
    b.add_argument("--table", default=str(DEFAULT_TABLE), help="the table to read the curation from and write")
    b.add_argument("--rel-root", default=str(DEFAULT_TABLE.parents[3]),
                   help="family folders inside it are stored relative to it (default: the repo root)")
    b.add_argument("--write", action="store_true", help="write the table (default: print a summary only)")
    s = sub.add_parser("specimen", help="draw the AR+EN specimen sheet of the table")
    s.add_argument("--fonts", action="append", required=True)
    s.add_argument("--table", default=str(DEFAULT_TABLE))
    s.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "specimen":
        print(json.dumps(specimen_sheet(load_table(a.table), a.fonts, a.out), ensure_ascii=False, indent=2))
        return 0
    try:
        t = build_table(a.fonts, load_table(a.table), rel_root=a.rel_root)
        if a.write:
            write_table(a.table, t)
    except PairingRefused as e:
        print(str(e), file=sys.stderr)
        return 2
    print(json.dumps({"rows": len(t["rows"]), "candidates": [c["family"] for c in t["candidates"]],
                      "findings": t["findings"], "written": bool(a.write)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
