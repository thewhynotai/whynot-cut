# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Tidy: which bin a project item belongs in (Python twin of adobe/tools/tidy/src/js/classify.js).

Faithful to the JavaScript, which is the reference (the panel's live logic): same names in snake_case, same dict keys, same
tables and the same regular expressions (as text, with `$` written `\\Z` and everything ASCII like JS: re.ASCII). Items and
contexts are plain dicts as the panel sends them; a property that is not there behaves as JS `undefined`. Nothing is
generalised here; tests/test_tidy_twins.py compares both implementations on the owner's cases and on random corpora, and
compares the constants and regex sources with classify.js as text.
"""
from __future__ import annotations

import functools
import re

from . import jsutil as J

__all__ = ["BINS", "COLORS", "MIC_MIN", "ext", "category", "bin_for", "camera_numbers"]

BINS = {
    "footage": "01 Footage", "renders": "02 Renders & Stock",
    "voice": "03 Audio/Voice", "music": "03 Audio/Music", "sfx": "03 Audio/SFX", "mics": "03 Audio/Mics",
    "png": "04 Images/PNG", "jpg": "04 Images/JPG", "icons": "04 Images/Icons", "images": "04 Images/Other",
    "graphics": "05 Graphics", "sequences": "06 Sequences", "nests": "07 Nests", "captions": "08 Captions", "other": "09 Other",
}
# Premiere label colour indexes (0 violet, 1 iris, 2 caribbean, 3 lavender, 4 cerulean, 5 forest,
# 6 rose, 7 mango, 8 purple, 9 blue, 10 teal, 11 magenta, 12 tan, 13 green, 14 brown, 15 yellow)
COLORS = {"footage": 9, "renders": 4, "voice": 2, "music": 8, "sfx": 7, "mics": 10, "png": 3, "jpg": 3, "icons": 3, "images": 3,
          "graphics": 11, "sequences": 5, "nests": 13, "captions": 15, "other": 12}
MIC_MIN = 180   # podcast: a recorder file at least this long (s) is a mic track

VIDEO = "mp4 mov m4v mxf avi mts m2ts mkv wmv webm r3d braw crm ari mpg mpeg 3gp dv insv"
AUDIO = "wav mp3 aif aiff m4a aac flac ogg wma caf bwf"
IMAGE = "png jpg jpeg tif tiff psd ai gif heic heif webp exr dpx tga bmp svg eps ico icns"
CAPTION = "srt vtt scc stl sbv mcc dfxp ttml"
GRAPHIC = "mogrt aegraphic prgraphic aep"
RECORDER = "wav bwf aif aiff"

_A = re.ASCII
SFX_WORDS = re.compile(r"(sfx|fx_|whoosh|swoosh|swish|riser|hit|impact|boom|click|ding|pop|transition|glitch|beep|foley|ambience|ambient)", _A | re.I)
# videos: whole words only ("White smoke", "Architecture" are not sound effects)
SFX_VIDEO = re.compile(r"(^|[^a-z])(sfx|whoosh|swoosh|swish|riser|hit|impact|boom|click|ding|transition|glitch|beep|foley)([^a-z]|\Z)", _A | re.I)
MUSIC_STRICT = re.compile(r"(^|[^a-z])(music|bgm|song)([^a-z]|\Z)", _A | re.I)
MUSIC_WORDS = re.compile(r"(music|bgm|song|track|beat|score|ost|instrumental|melody|loop)", _A | re.I)
_EXT = re.compile(r"\.([A-Za-z0-9]+)\Z", _A)


def _has(lst: str, e: str) -> bool:
    return (" " + e + " ") in (" " + lst + " ")


def ext(path) -> str:
    p = path if J.truthy(path) else ""
    m = _EXT.search(J.js_str(p))
    return m.group(1).lower() if m else ""


def category(item: dict, ctx=None) -> str:
    ctx = ctx if J.truthy(ctx) else {}
    nid = J.key(item["nodeId"]) if "nodeId" in item else "undefined"
    if J.truthy(item.get("isSequence")):
        nest = ctx.get("nestIds")
        return "nests" if J.truthy(nest) and J.truthy(nest.get(nid)) else "sequences"
    if not J.truthy(item.get("path")):
        return "graphics"
    e = ext(item["path"])
    nm = item.get("name")
    name = J.js_str(nm if J.truthy(nm) else "")
    duration = J.num(item.get("duration"))
    if _has(VIDEO, e):
        if item.get("kind") == "camera":
            return "footage"
        return "sfx" if SFX_VIDEO.search(name) else "renders"
    if _has(IMAGE, e):
        if J.truthy(item.get("icon")):
            return "icons"
        return "png" if e == "png" else ("jpg" if e in ("jpg", "jpeg") else "images")
    if _has(CAPTION, e):
        return "captions"
    if _has(GRAPHIC, e):
        return "graphics"
    if _has(AUDIO, e):
        # podcast: a long recorder file is a mic, whatever its name looks like ("Host", "Guest Track")
        if ctx.get("mode") == "podcast" and _has(RECORDER, e) and duration >= MIC_MIN and not MUSIC_STRICT.search(name):
            return "mics"
        if SFX_WORDS.search(name):
            return "sfx"
        if MUSIC_WORDS.search(name):
            return "music"
        return "sfx" if duration > 0 and duration <= 8 else "voice"
    return "other"


def bin_for(cat: str, item: dict, ctx=None):
    """The bin path for a category; podcast footage is split per camera."""
    if cat == "footage" and J.truthy(ctx) and ctx.get("mode") == "podcast" and J.truthy(ctx.get("camNumbers")):
        n = ctx["camNumbers"].get(J.key(item["camId"]) if "camId" in item else "undefined")
        if J.truthy(n):
            return BINS["footage"] + "/Cam " + J.js_str(n)
    return BINS.get(cat)


def camera_numbers(items: list) -> dict:
    """{camId: 1..n}: the camera with the most footage is Cam 1 (ties: by camId in UTF-16 order, as JS `<`)."""
    total, ids, out = {}, [], {}
    for it in items:
        if it.get("kind") != "camera" or not J.truthy(it.get("camId")):
            continue
        cid = J.key(it["camId"])
        if cid not in total:
            total[cid] = 0
            ids.append(cid)
        d = it.get("duration")
        total[cid] += d if J.truthy(d) else 0

    def cmp(a, b):
        diff = total[b] - total[a]
        if diff == diff and diff != 0:
            return -1 if diff < 0 else 1
        ka, kb = J.u16key(a), J.u16key(b)
        return -1 if ka < kb else (1 if ka > kb else 0)
    ids.sort(key=functools.cmp_to_key(cmp))
    for i, cid in enumerate(ids):
        out[cid] = i + 1
    return out
