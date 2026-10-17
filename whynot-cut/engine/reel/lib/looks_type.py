# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Typesetting for caption looks (R-4.1 §4, Phase 4 Task 23): the font chain per script, the text engines and a
word-level line layout that knows where every word lands.

Font chain, the same everywhere in R-4.1, R-6.1 and R-6.2:
  Arabic runs: the client's Arabic face for the role → the client's Arabic body face → the look's fallback → house.
  Latin runs:  the client's Latin face for the role → the client's Arabic face if it has Latin → look fallback → house.
House faces: IBM Plex Sans Arabic and Inter (OFL) when installed, else the system fallbacks (lib/fonts.py).
A run whose characters a font cannot draw (glyph id 0, .notdef) moves to the next font in its chain, then to the other
script's chain; a character no font has is reported as U+XXXX and left out (never a silent box).

Words are shaped one by one, each split into script segments: Arabic letters (right to left), Latin (left to right)
and numbers, which always keep their digits left to right (Western and Arabic-Indic alike: lib/hb_text classes
Arabic-Indic digits as RTL, so captions do their own segmenting). The line's base direction is RTL when it holds
Arabic; words are then laid out right to left, with runs of Latin words kept in their own left-to-right order.
Engines: HarfBuzz + FreeType with the font FILE (every OS), CoreText on macOS when the exact face is installed.
"""
from __future__ import annotations

import math
import re
import unicodedata

from .common import load_config

_DIGIT = re.compile("[0-9٠-٩۰-۹]")
_SEP = ".,٫٬"
_ARABIC_CH = re.compile("[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_ARABIC_LETTER = re.compile("[ء-يٮ-ۓۺ-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-ﻼ]")
_IGNORABLE = {"‌", "‍", "‎", "‏", "⁦", "⁧", "⁨", "⁩", "؜", " "}
HOUSE_PS = {"arabic": ["IBMPlexSansArabic-SemiBold", "IBMPlexSansArabic-Bold", "IBMPlexSansArabic-Regular"],
            "latin": ["Inter-SemiBold", "Inter-Bold", "Inter-Regular"]}
LATIN_SYSTEM = ["SegoeUI-Semibold", "SegoeUI", "Arial-BoldMT", "ArialMT", "HelveticaNeue-Medium", "Helvetica",
                "DejaVuSans"]


def hb_available() -> bool:
    from . import hb_text
    return bool(hb_text.AVAILABLE)


def u_plus(ch: str) -> str:
    return f"U+{ord(ch):04X}"


# --------------------------------------------------------------------------- engines
class HBEngine:
    """HarfBuzz shaping + FreeType rasterising from the font file (lib/hb_text's faces and cache)."""
    name = "harfbuzz"

    def __init__(self):
        self._fonts: dict = {}

    def font(self, face: dict, size: float):
        from . import hb_text
        key = (face["file"], int(face.get("index") or 0), round(float(size), 3))
        f = self._fonts.get(key)
        if f is None:
            f = self._fonts[key] = hb_text.HBFontSpec(face["file"], size, index=int(face.get("index") or 0))
        return f

    def shape(self, text: str, direction: str, font) -> list[tuple]:
        """[(glyph id, advance, x offset, y offset)] in visual left-to-right order (px)."""
        import uharfbuzz as hb
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        buf.direction = direction
        hb.shape(font.hb_font, buf, {"kern": True, "liga": True})
        k = font.size / font.upem
        return [(i.codepoint, p.x_advance * k, p.x_offset * k, p.y_offset * k)
                for i, p in zip(buf.glyph_infos, buf.glyph_positions)]

    def advance(self, text: str, direction: str, font) -> float:
        return float(sum(g[1] for g in self.shape(text, direction, font)))

    def missing(self, text: str, font) -> list[str]:
        out = []
        for ch in text:
            if ch in _IGNORABLE or unicodedata.category(ch) == "Cf" or ch in out:
                continue
            if not font.hb_font.get_nominal_glyph(ord(ch)):
                out.append(ch)
        return out

    def space(self, font) -> float:
        return self.advance(" ", "ltr", font)

    def metrics(self, font) -> tuple[int, int]:
        return font.getmetrics()

    def render(self, text: str, direction: str, font, rgba=(255, 255, 255, 255)):
        """(RGBA image, baseline y from the top, advance width), the same geometry as hb_text.render_line."""
        import freetype  # type: ignore
        import numpy as np
        from PIL import Image
        glyphs = self.shape(text, direction, font)
        w = sum(g[1] for g in glyphs)
        pad = 4
        asc, desc = font.getmetrics()
        W, H = max(1, int(math.ceil(w)) + pad * 2), max(1, asc + desc + pad * 2)
        base_y = pad + asc
        cov = np.zeros((H, W), dtype=np.float32)
        ft = font.ft
        ft.set_char_size(int(round(font.size * 64)), 0, 72, 72)     # the face is shared by every size of this file
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
                xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + bm.width), min(H, y0 + bm.rows)
                if xb > xa and yb > ya:
                    cov[ya:yb, xa:xb] = np.maximum(cov[ya:yb, xa:xb], arr[ya - y0:yb - y0, xa - x0:xb - x0])
            pen += adv
        out = np.zeros((H, W, 4), dtype=np.uint8)
        out[..., 0], out[..., 1], out[..., 2] = rgba[:3]
        out[..., 3] = np.clip(cov * (rgba[3] if len(rgba) > 3 else 255), 0, 255).astype(np.uint8)
        return Image.fromarray(out), base_y, float(w)


class CTEngine:
    """macOS CoreText (lib/ct_text) for an installed face, by PostScript name. A direction mark before the text sets
    the run's direction (numbers stay left to right in both)."""
    name = "coretext"
    _MARK = {"rtl": "‏", "ltr": "‎"}

    def font(self, face: dict, size: float):
        from . import ct_text
        return ct_text.CTFontSpec(face["ps"], size)

    def shape(self, text: str, direction: str, font) -> list[tuple]:
        return []                                   # CoreText lays out whole runs; glyph lists are not needed here

    def advance(self, text: str, direction: str, font) -> float:
        from . import ct_text
        return ct_text.measure(self._MARK[direction] + text, font)

    def missing(self, text: str, font) -> list[str]:
        import CoreText  # type: ignore
        out = []
        for ch in text:
            if ch in _IGNORABLE or unicodedata.category(ch) == "Cf" or ch in out:
                continue
            units = ch.encode("utf-16-le")
            n = len(units) // 2
            ok, _ = CoreText.CTFontGetGlyphsForCharacters(font._font, ch, None, n)
            if not ok:
                out.append(ch)
        return out

    def space(self, font) -> float:
        return self.advance(" ", "ltr", font)

    def metrics(self, font) -> tuple[int, int]:
        return font.getmetrics()

    def render(self, text: str, direction: str, font, rgba=(255, 255, 255, 255)):
        from . import ct_text
        return ct_text.render_line(self._MARK[direction] + text, font, rgba)


_HB = None


def pick_engine(face: dict, ct_available: bool | None = None, ct_exact=None):
    """CoreText when it is available here and `face` is installed under its exact PostScript name, else HarfBuzz."""
    global _HB
    from . import ct_text
    ct_available = ct_text.AVAILABLE if ct_available is None else ct_available
    if ct_available and face.get("ps"):
        exact = ct_exact or (lambda ps: ct_text.CTFontSpec(ps, 12).is_exact)
        try:
            if exact(face["ps"]):
                return CTEngine()
        except Exception:  # noqa: BLE001  CoreText refused the name: the file path below
            pass
    if _HB is None:
        _HB = HBEngine()
    return _HB


# --------------------------------------------------------------------------- font chain
def _key(face: dict) -> tuple:
    return (str(face.get("file") or face.get("ps")), int(face.get("index") or 0))


def _has(face: dict, chars: str) -> bool:
    try:
        eng = HBEngine()
        return not eng.missing(chars, eng.font(face, 24))
    except Exception:  # noqa: BLE001  unreadable font file: not usable
        return False


def _arabic(face: dict) -> bool:
    return bool(face.get("file")) and _has(face, "المن")


def _latin(face: dict) -> bool:
    return bool(face.get("file")) and _has(face, "AaZz")


def house_faces() -> dict:
    """The house faces of this computer: IBM Plex Sans Arabic / Inter when installed, else the system Arabic fallback
    (lib/fonts.arabic_fallback) and a common system Latin face. Empty lists when none is installed."""
    from . import fonts
    out = {"arabic": [], "latin": []}
    for script, names in (("arabic", HOUSE_PS["arabic"]), ("latin", HOUSE_PS["latin"] + LATIN_SYSTEM)):
        for ps in names:
            hit = fonts.find(ps)
            if hit and hit["ps"] == ps:
                out[script].append({"file": hit["file"], "index": int(hit.get("index") or 0), "ps": ps,
                                    "family": hit.get("family"), "style": hit.get("style"), "weight": hit.get("weight")})
                break
    if not out["arabic"]:
        fb = fonts.arabic_fallback(bold=True)
        if fb:
            out["arabic"].append({"file": fb["file"], "index": int(fb.get("index") or 0), "ps": fb["ps"],
                                  "family": fb.get("family"), "style": fb.get("style"), "weight": fb.get("weight")})
    return out


def _role_face(typography: dict, role: str) -> dict | None:
    from .common import font_role_fallback
    from .font_roles import resolve
    f = resolve(typography, role, font_role_fallback().get("weights", {}))
    if not f.get("file") and not f.get("ps"):
        return None
    return {"file": f.get("file"), "index": 0, "ps": f.get("ps"), "family": f.get("family"), "style": f.get("style")}


def _heavier(typography: dict, face: dict, step: int) -> tuple[dict, str | None]:
    """The face at least `step` weight units heavier than `face` in the same family (upright; the lightest such face),
    else the family's heaviest face when it is heavier at all, else `face` itself with a note."""
    from .font_roles import faces
    fam = sorted((f for f in faces(typography) if f["family"] == face.get("family") and not f["italic"]),
                 key=lambda f: f["weight"])
    cur = next((f for f in fam if f["ps"] == face.get("ps") or f["file"] == face.get("file")), None)
    if cur is None:
        return face, f"{face.get('ps') or face.get('file')} is not in its family list: the emphasis keeps its weight"
    up = [f for f in fam if f["weight"] >= cur["weight"] + step] or [f for f in fam if f["weight"] > cur["weight"]][-1:]
    if not up:
        return face, f"{face.get('ps') or face.get('file')} has no heavier weight: the emphasis keeps its weight"
    f = up[0]
    return {"file": f["file"], "index": 0, "ps": f["ps"], "family": f["family"], "style": f["style"]}, None


def font_chain(typography: dict, role: str = "caption", house: dict | None = None, look_fallback: dict | None = None,
               weight_step: int = 0) -> dict:
    """{"arabic": [faces], "latin": [faces], "notes": [...]} for a role (see the module docstring). `weight_step`
    (weight units, e.g. 200) moves the client's faces that much heavier in their own family (the `weight` emphasis)."""
    house = house_faces() if house is None else house
    notes: list[str] = []
    def step(f):
        if not (f and weight_step):
            return f
        g, note = _heavier(typography, f, weight_step)
        if note and note not in notes:
            notes.append(note)
        return g
    role_f, body_f = step(_role_face(typography, role)), step(_role_face(typography, "body"))
    client_ar = [f for f in (role_f, body_f) if f and _arabic(f)]
    arabic = client_ar + ([look_fallback] if look_fallback and _arabic(look_fallback) else []) + list(house["arabic"])
    latin = ([role_f] if role_f and _latin(role_f) else []) + [f for f in client_ar[:1] if _latin(f)] + \
            ([look_fallback] if look_fallback and _latin(look_fallback) else []) + list(house["latin"])

    def dedupe(fs):
        seen, out = set(), []
        for f in fs:
            if _key(f) not in seen:
                seen.add(_key(f))
                out.append(f)
        return out
    return {"arabic": dedupe(arabic), "latin": dedupe(latin), "notes": notes}


# --------------------------------------------------------------------------- segments and layout
def _kind(ch: str, prev_kind: str | None, nxt: str | None) -> str | None:
    if _DIGIT.match(ch):
        return "num"
    if ch in _SEP and prev_kind == "num" and nxt and _DIGIT.match(nxt):
        return "num"
    if ch == "%" and prev_kind == "num":
        return "num"
    if _ARABIC_CH.match(ch):
        return "ar"
    cat = unicodedata.category(ch)
    if cat.startswith("L"):
        return "lat"
    if cat == "Mn":
        return prev_kind
    return None                                     # neutral: joins a neighbour


def segments(word: str, rtl_line: bool) -> list[dict]:
    """A word as script segments in VISUAL left-to-right order: [{text, kind (ar | lat | num), dir}]."""
    kinds: list[str | None] = []
    for i, ch in enumerate(word):
        kinds.append(_kind(ch, kinds[-1] if kinds else None, word[i + 1] if i + 1 < len(word) else None))
    if not any(kinds):
        kinds = ["ar" if rtl_line else "lat"] * len(word)
    for i in range(len(kinds)):                     # neutrals join the previous segment, else the next
        if kinds[i] is None:
            kinds[i] = next((k for k in reversed(kinds[:i]) if k), None) or next(k for k in kinds[i:] if k)
    segs: list[dict] = []
    for ch, k in zip(word, kinds):
        if segs and segs[-1]["kind"] == k:
            segs[-1]["text"] += ch
        else:
            segs.append({"text": ch, "kind": k, "dir": "rtl" if k == "ar" else "ltr"})
    if rtl_line and len(segs) > 1:
        segs = _rtl_order(segs, lambda s: s["kind"] != "ar")
    return segs


def _rtl_order(items: list, is_ltr) -> list:
    """Right-to-left visual order of logical items, keeping each run of left-to-right items in its own order."""
    out, run = [], []
    for it in items:
        if is_ltr(it):
            run.append(it)
            continue
        if run:
            out.append(run)
            run = []
        out.append([it])
    if run:
        out.append(run)
    return [it for block in reversed(out) for it in block]


def _word_class(text: str) -> str:
    if _ARABIC_LETTER.search(text):
        return "R"
    if any(unicodedata.category(c).startswith("L") for c in text):
        return "L"
    if _DIGIT.search(text):
        return "D"
    return "N"


class Typesetter:
    """Measures and lays out caption words at one size with a font chain. `engine` forces one engine (tests, the
    darwin fakes); otherwise each face gets pick_engine(face). `heavy` is the chain of the `weight` emphasis; `scale`
    turns the catalog's 1080-wide pixel values (tag padding) into frame pixels."""

    def __init__(self, chain: dict, size: float, engine=None, heavy: dict | None = None, tag_pad_px: float = 10.0,
                 scale: float = 1.0, tag_pad_em: float | None = None):
        self.chain, self.heavy, self.size = chain, heavy or chain, float(size)
        self._forced = engine
        self.engine = engine or (pick_engine(chain["arabic"][0] if chain["arabic"] else chain["latin"][0])
                                 if (chain["arabic"] or chain["latin"]) else HBEngine())
        self.engines: set = set()
        self.tag_pad = tag_pad_em * self.size if tag_pad_em is not None else tag_pad_px * scale
        self._words: dict = {}

    def _eng(self, face: dict):
        return self._forced or pick_engine(face)

    def _font(self, face: dict):
        eng = self._eng(face)
        return eng, eng.font(face, self.size)

    def font_for(self, face: dict):
        """(engine, font) that draws `face` at this size."""
        return self._font(face)

    def _pick(self, text: str, order: list[dict]) -> tuple[dict | None, list[str]]:
        """The first face that draws every character of `text`, else the one missing the fewest (and what it misses)."""
        best = None
        for f in order:
            eng, font = self._font(f)
            miss = eng.missing(text, font)
            if not miss:
                return f, []
            if best is None or len(miss) < len(best[1]):
                best = (f, miss)
        return best if best else (None, list(text))

    def word(self, text: str, heavy: bool = False, rtl_line: bool | None = None) -> dict:
        """{text, w, segments [{text, kind, dir, ps, face, w, glyphs}], missing [U+XXXX]} for one word."""
        rtl = bool(_ARABIC_CH.search(text)) if rtl_line is None else rtl_line
        key = (text, heavy, rtl)
        if key in self._words:
            return self._words[key]
        chain = self.heavy if heavy else self.chain
        missing: list[str] = []
        segs = []
        for s in segments(text, rtl):
            first = chain["arabic"] if s["kind"] == "ar" or (s["kind"] == "num" and rtl) else chain["latin"]
            other = chain["latin"] if first is chain["arabic"] else chain["arabic"]
            face, miss = self._pick(s["text"], first + [f for f in other if _key(f) not in {_key(x) for x in first}])
            draw = "".join(c for c in s["text"] if c not in miss)
            for c in miss:
                if u_plus(c) not in missing:
                    missing.append(u_plus(c))
            if not draw or face is None:
                continue
            eng, font = self._font(face)
            self.engines.add(eng.name)
            glyphs = eng.shape(draw, s["dir"], font)
            segs.append(dict(s, text=draw, ps=face.get("ps"), face=face, w=eng.advance(draw, s["dir"], font),
                             glyphs=glyphs))
        out = {"text": text, "w": float(sum(s["w"] for s in segs)), "segments": segs, "missing": missing}
        self._words[key] = out
        return out

    def space(self, rtl: bool) -> float:
        order = (self.chain["arabic"] if rtl else self.chain["latin"]) or self.chain["arabic"] or self.chain["latin"]
        eng, font = self._font(order[0])
        return eng.space(font)

    def line(self, texts: list[str], emphasis: set | None = None, mode: str | None = None) -> dict:
        """Lay out a caption line: {w, rtl, space, items [{i, text, x, w, segments, emphasis}], missing}. Items are in
        logical order with their visual x (from the line's left edge). `mode` "weight" draws the emphasised words
        with the heavy chain, "tag" adds the tag plate's padding around them."""
        emphasis = emphasis or set()
        rtl = any(_ARABIC_CH.search(t) for t in texts)
        items = []
        for i, t in enumerate(texts):
            emph = i in emphasis
            wd = self.word(t, heavy=emph and mode == "weight", rtl_line=rtl)
            pad = self.tag_pad if emph and mode == "tag" else 0.0
            items.append({"i": i, "text": t, "w": wd["w"] + 2 * pad, "pad": pad, "segments": wd["segments"],
                          "missing": wd["missing"], "emphasis": emph, "cls": _word_class(t)})
        sp = self.space(rtl) if items else 0.0
        if rtl:
            for k, it in enumerate(items):          # a number after a Latin word joins its run (rule W7)
                if it["cls"] == "D":
                    prev = next((x["cls"] for x in reversed(items[:k]) if x["cls"] in "RL"), None)
                    it["cls"] = "L" if prev == "L" else "R"
            visual = _rtl_order(items, lambda it: it["cls"] == "L")
        else:
            visual = items
        x = 0.0
        for k, it in enumerate(visual):
            it["x"] = x
            x += it["w"] + (sp if k < len(visual) - 1 else 0.0)
        missing = []
        for it in items:
            missing += [m for m in it["missing"] if m not in missing]
        return {"w": x, "rtl": rtl, "space": sp, "items": items, "missing": missing}

    def metrics(self) -> tuple[int, int]:
        """(ascent, descent) of the line's base face at this size."""
        order = self.chain["arabic"] or self.chain["latin"]
        eng, font = self._font(order[0])
        return eng.metrics(font)


# --------------------------------------------------------------------------- sizes and the safe width
def floor_px(look_size: float, frame_w: int) -> float:
    """The smallest size a spoken-word caption may shrink to (R-4.1 §6): the look's size × 0.85, never below 44 px,
    both at a 1080 px frame width and scaled with the frame width."""
    from . import looks
    fit = looks.caption_catalog().get("fit") or {}
    v = max(float(look_size) * float(fit.get("floor_ratio", 0.85)), float(fit.get("floor_min_px", 44)))
    return v * frame_w / 1080


def safe_width(frame_w: int) -> float:
    """The width a caption line may use: the selected safe-zone profile's (R-4.5, when there is one), else the
    subtitle style's safe area (left/right margins at 1080 px, scaled with the frame width)."""
    sa = (load_config("subtitle-style.json").get("safe_area") or {})
    left, right = float(sa.get("left", 90)), float(sa.get("right", 90))
    return round((1080 - left - right) * frame_w / 1080, 4)
