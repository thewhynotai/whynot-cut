# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Tidy: what a media file is, from its own bytes (Python twin of adobe/tools/tidy/src/js/media.js).

The JavaScript is the reference; same function names in snake_case, same field names (`kind`, `camId`, `icon`, `imgW`,
`imgH`), and the same latin-1 text in (the first and last 2 MiB of a video, the first 64 KiB of an image). JavaScript
regular expression semantics are kept where Python's differ:
  * `\\d`, `\\w`, `\\b` and `/i` are ASCII only in JS: every pattern is compiled with re.ASCII;
  * `$` matches only at the very end in JS (Python's also before a final newline): `\\Z`;
  * `\\s` is the JS whitespace set (it contains U+FEFF and U+00A0, not U+001C..U+001F): JS_WS below;
  * `.` does not match any line terminator in JS (\\n \\r U+2028 U+2029): NOT_EOL below.
Bytes past the end of the text read as 0 in JS bit operations (charCodeAt gives NaN, NaN << 8 is 0): `_cc`.
"""
from __future__ import annotations

import re

__all__ = ["video_kind", "camera_model", "camera_id", "image_size", "is_icon", "needs_bytes", "describe",
           "text_from_value", "ICON_MAX", "CAMERA_RAW"]

_A = re.ASCII
_WS_CODES = (0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x20, 0xA0, 0x1680) + tuple(range(0x2000, 0x200B)) + (0x2028, 0x2029, 0x202F, 0x205F, 0x3000, 0xFEFF)
JS_WS = "[" + "".join(re.escape(chr(c)) for c in _WS_CODES) + "]"
NOT_EOL = "[^" + "".join(re.escape(chr(c)) for c in (0x0A, 0x0D, 0x2028, 0x2029)) + "]"

# render evidence beats camera evidence: exports keep the tags of their sources
RENDER_TAGS = re.compile(r"(CreatorTool|Mainconcept|MainConcept|Lavf\d|HandBrake|CapCut|Adobe Media Encoder|DaVinci Resolve)", _A)
RENDER_NAME = re.compile(r"(render|export|final|compose|_edit|\bedit\b)", _A | re.I)
CAMERA_TAGS = re.compile(r"(DJI (Osmo|Pocket|Action|Mini|Mavic|Air|Avata|Neo)|com\.apple\.quicktime\.model|NonRealTimeMeta|"
                         r"GoPro|Insta360|Canon|Panasonic|Blackmagic|FUJIFILM|NIKON|com\.android\.manufacturer|samsung)", _A)
CAMERA_NAME = re.compile(r"^(C\d{4}|IMG_\d+|DJI_\d+|GX\d{6}|GH\d{6}|GOPR\d+|MVI_\d+|DSC_?\d+|A\d{3}C\d{3}|PXL_\d+|VID_\d+|"
                         r"MAH\d+|P\d{7}|\d{5}\.MTS\Z)", _A | re.I)
CAMERA_RAW = re.compile(r"\.(r3d|braw|crm|ari|insv)\Z", _A | re.I)   # camera originals only
_DJI_MODEL = re.compile(r"DJI ((Osmo|Pocket|Action|Mini|Mavic|Air|Avata|Neo)[A-Za-z0-9 ]{0,20}?)(?=[^A-Za-z0-9 ]|\Z)", _A)
_IPHONE = re.compile(r"(iPhone \d{1,2}(?: (?:Pro|Plus|Max|mini|SE|e))*)", _A)
_OTHER_MODEL = re.compile(r"(ILCE-\w+|ZV-\w+|FX\d+|DC-\w+|EOS[ \w-]{1,12}|HERO\d+[ \w]{0,10}|Insta360 [\w ]{1,12}|BMPCC\w*)", _A)
_TRAILING_WS = re.compile(JS_WS + r"+\Z")
_VIDEO_EXT = re.compile(r"\.(mp4|mov|m4v|mxf|avi|mts|m2ts|mkv|insv|3gp)\Z", _A | re.I)
_IMAGE_EXT = re.compile(r"\.(png|jpe?g|gif|webp|svg|ico|icns)\Z", _A | re.I)
_EXT = re.compile(r"\.([A-Za-z0-9]+)\Z", _A)
_ICON_NAME = re.compile(r"(icon|logo|emoji)", _A | re.I)
ICON_MAX = 512


def _rstrip_ws(s: str) -> str:
    return _TRAILING_WS.sub("", s)


def video_kind(text, name) -> str:
    """The file's own tags first (users rename camera files), then its name."""
    text = text or ""
    name = name or ""
    if RENDER_TAGS.search(text):
        return "render"
    if CAMERA_TAGS.search(text):
        return "camera"
    if RENDER_NAME.search(name):
        return "render"
    return "camera" if CAMERA_NAME.search(name) else "render"


def camera_model(text) -> str:
    text = text or ""
    m = _DJI_MODEL.search(text)
    if m:
        return "DJI " + _rstrip_ws(m.group(1))
    m = _IPHONE.search(text)
    if m:
        return _rstrip_ws(m.group(1))
    m = _OTHER_MODEL.search(text)
    return _rstrip_ws(m.group(1)) if m else ""


def camera_id(text, name, dir_) -> str:
    """Which camera made it: model + folder (identical cameras are usually kept in their own folders), else folder."""
    model = camera_model(text)
    return model + " | " + (dir_ or "") if model else "folder:" + (dir_ or "")


def _cc(s: str, i: int) -> int:
    return ord(s[i]) if 0 <= i < len(s) else 0


def _u16be(s, i):
    return (_cc(s, i) << 8) | _cc(s, i + 1)


def _u32be(s, i):
    return (_cc(s, i) << 24) + (_cc(s, i + 1) << 16) + (_cc(s, i + 2) << 8) + _cc(s, i + 3)


def _u16le(s, i):
    return _cc(s, i) | (_cc(s, i + 1) << 8)


def image_size(s, ext=None):
    """{'w', 'h'} from the image header (PNG, JPEG, GIF, WebP), or None."""
    if not s or len(s) < 24:
        return None
    if s[1:4] == "PNG" and s[12:16] == "IHDR":
        return {"w": _u32be(s, 16), "h": _u32be(s, 20)}
    if _cc(s, 0) == 0xFF and _cc(s, 1) == 0xD8:
        i = 2
        while i + 9 < len(s):
            if _cc(s, i) != 0xFF:
                i += 1
                continue
            mk = _cc(s, i + 1)
            if 0xC0 <= mk <= 0xCF and mk not in (0xC4, 0xC8, 0xCC):
                return {"w": _u16be(s, i + 7), "h": _u16be(s, i + 5)}
            if mk == 0xD8 or mk == 0x01 or 0xD0 <= mk <= 0xD7 or mk == 0xFF:
                i += 2
                continue
            i += 2 + _u16be(s, i + 2)
        return None
    if s[0:3] == "GIF":
        return {"w": _u16le(s, 6), "h": _u16le(s, 8)}
    if s[0:4] == "RIFF" and s[8:12] == "WEBP":
        kind = s[12:16]
        if kind == "VP8X":
            return {"w": 1 + (_cc(s, 24) | (_cc(s, 25) << 8) | (_cc(s, 26) << 16)),
                    "h": 1 + (_cc(s, 27) | (_cc(s, 28) << 8) | (_cc(s, 29) << 16))}
        if kind == "VP8 ":
            return {"w": _u16le(s, 26) & 0x3FFF, "h": _u16le(s, 28) & 0x3FFF}
        if kind == "VP8L":
            b = (_cc(s, 21) | (_cc(s, 22) << 8) | (_cc(s, 23) << 16) | (_cc(s, 24) << 24)) & 0xFFFFFFFF
            return {"w": (b & 0x3FFF) + 1, "h": ((b >> 14) & 0x3FFF) + 1}
    return None


def is_icon(name, ext, size) -> bool:
    if ext in ("svg", "ico", "icns"):
        return True
    if _ICON_NAME.search(name or ""):
        return True
    return bool(size) and max(size["w"], size["h"]) <= ICON_MAX


def needs_bytes(item):
    """What the engine must read for an item: 'video' (first + last 2 MiB), 'image' (first 64 KiB) or None."""
    p = item.get("path") or ""
    return "video" if _VIDEO_EXT.search(p) else ("image" if _IMAGE_EXT.search(p) else None)


def _dir_of(p: str) -> str:
    i = max(p.rfind("/"), p.rfind("\\"))
    return p[:i] if i > 0 else ""


def describe(item: dict, text) -> dict:
    """Fill item['kind'] / ['camId'] (videos) or ['icon'] / ['imgW'] / ['imgH'] (images) from the text read (None if
    unreadable); anything else is left alone. Returns the item."""
    path = item.get("path") or ""
    need = needs_bytes(item)
    m = _EXT.search(path)
    ext = m.group(1).lower() if m else ""
    if CAMERA_RAW.search(path):
        item["kind"] = "camera"
        item["camId"] = camera_id("", item.get("name"), _dir_of(path))
    elif need == "video":
        item["kind"] = video_kind(text or "", item.get("name"))
        item["camId"] = camera_id(text or "", item.get("name"), _dir_of(path))
    elif need == "image":
        size = image_size(text or "", ext)
        if size:
            item["imgW"] = size["w"]
            item["imgH"] = size["h"]
        item["icon"] = is_icon(item.get("name"), ext, size)
    return item


_TEXT_EDIT = re.compile(r'"textEditValue"' + JS_WS + r'*:' + JS_WS + r'*"((?:\\' + NOT_EOL + r'|[^"\\])*)"')
_U_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")
_NL_ESCAPE = re.compile(r"\\[nr]")
_ANY_ESCAPE = re.compile(r"\\(" + NOT_EOL + ")")
_WS_RUN = re.compile(JS_WS + "+")   # JS: whitespace runs, U+00A0 included (JS_WS has it)
_EDGE_SPACE = re.compile(r"^ | \Z")


def text_from_value(v) -> str:
    """The words of a graphic clip, from the JSON text Premiere returns for "Source Text"."""
    m = _TEXT_EDIT.search(str(v) if v else "")
    if not m:
        return ""
    t = _U_ESCAPE.sub(lambda a: chr(int(a.group(1), 16)), m.group(1))
    t = _NL_ESCAPE.sub(" ", t)
    t = _ANY_ESCAPE.sub(lambda a: a.group(1), t)
    return _EDGE_SPACE.sub("", _WS_RUN.sub(" ", t))
