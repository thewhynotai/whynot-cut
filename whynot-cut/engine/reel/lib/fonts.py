"""Font discovery: every installed font face, found by the names inside the font (3.0 T2.10, IM-12, G72).

One index of the font folders (plat.font_dirs(): Windows system + per-user fonts, the macOS folders including
/System/Library/Fonts/Supplemental, the Linux folders, and the Adobe Fonts / Creative Cloud "livetype" folder), read
recursively. Collections (.ttc/.otc) are indexed face by face with their face index. Adobe Fonts keeps activated fonts
under obfuscated file names without an extension (livetype/r/62878), so files without an extension are kept when they
start like a font, and every face is looked up by its PostScript, full or family name, never by its file name.

The index is cached in memory and in <engine home>/cache/font-index.json, keyed by the folders and the modification
times of every folder below them: a font installed or activated while a long-lived process runs is found (T2.17).
Every caller asks here: client_db (is a brand font installed), motion_layout (PostScript name -> file for After
Effects measurements), motion_plan and previews (the system Arabic fallback when a client has no Arabic font, G72).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import plat

VERSION = 1
FONT_SUFFIXES = {".ttf", ".otf", ".ttc", ".otc"}
_MAGIC = {b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf"}     # sfnt / CFF / Apple TrueType / collection
_ARABIC_BIT = 1 << 13                                         # OS/2 ulUnicodeRange1 bit 13: Arabic (U+0600-06FF)
_MEM: dict = {}                                               # stamp key -> faces (most recent last)
_MEM_MAX = 4
_ARABIC_FILES: dict = {}                                      # (file, index, size, mtime) -> supports Arabic

# System Arabic fallbacks, best first (PostScript names). Windows: Segoe UI, Arial, Tahoma; macOS: Geeza Pro (a .ttc)
# and Arial (Supplemental); Linux: Noto Sans Arabic, DejaVu Sans.
FALLBACKS = {
    "windows": {"regular": ["SegoeUI", "ArialMT", "Tahoma"], "bold": ["SegoeUI-Bold", "Arial-BoldMT", "Tahoma-Bold"]},
    "darwin": {"regular": ["GeezaPro", "ArialMT", "Tahoma"], "bold": ["GeezaPro-Bold", "Arial-BoldMT", "Tahoma-Bold"]},
    "linux": {"regular": ["NotoSansArabic-Regular", "NotoNaskhArabic-Regular", "DejaVuSans"],
              "bold": ["NotoSansArabic-Bold", "NotoNaskhArabic-Bold", "DejaVuSans-Bold"]},
}


def _system(system: str | None) -> str:
    return system or ("windows" if plat.IS_WIN else "darwin" if plat.IS_MAC else "linux")


def _roots(dirs) -> list[Path]:
    """The folders to scan, each once (a folder listed twice, or inside another listed one, is scanned once)."""
    cand = []
    for d in (plat.font_dirs() if dirs is None else dirs):
        n = os.path.normcase(os.path.abspath(str(d)))
        if n not in (c for c, _ in cand):
            cand.append((n, Path(d)))
    inside = lambda a, b: a.startswith(b.rstrip(os.sep) + os.sep)
    return [p for n, p in cand if not any(inside(n, m) for m, _ in cand)]


def _walk(root: Path):
    """(folder, sorted file names) for root and every folder below it, sorted; nothing for a missing root."""
    for here, subdirs, files in os.walk(str(root), onerror=lambda e: None):
        subdirs.sort()
        yield here, sorted(files)


def _stamp(roots: list[Path]) -> list:
    """[folder, mtime_ns] of every root and folder below it (a root that is missing: [root, None])."""
    out = []
    for r in roots:
        found = False
        for here, _ in _walk(r):
            found = True
            try:
                out.append([here, os.stat(here).st_mtime_ns])
            except OSError:
                out.append([here, None])
        if not found:
            out.append([str(r), None])
    return out


def _is_font(path: str, name: str) -> bool:
    suffix = os.path.splitext(name)[1].lower()
    if suffix in FONT_SUFFIXES:
        return True
    if suffix:                      # .xml, .db, .fon, .txt ...: not an OpenType font
        return False
    try:                            # Adobe Fonts: obfuscated names without an extension
        with open(path, "rb") as f:
            return f.read(4) in _MAGIC
    except OSError:
        return False


def _arabic(tt) -> bool:
    """Does this face cover Arabic: the OS/2 Unicode range when the font fills it in, else its character map."""
    os2 = tt["OS/2"] if "OS/2" in tt else None
    ranges = [getattr(os2, f"ulUnicodeRange{i}", 0) for i in (1, 2, 3, 4)] if os2 is not None else []
    if any(ranges):
        return bool(ranges[0] & _ARABIC_BIT)
    cmap = tt.getBestCmap() or {}
    return sum(1 for c in (0x0627, 0x0628, 0x062A, 0x0645, 0x0646, 0x0647, 0x0648, 0x064A) if c in cmap) >= 6


def _face(tt, path: str, index: int) -> dict | None:
    name = tt["name"]

    def nm(i):
        r = name.getDebugName(i)
        return str(r).strip() if r else None
    ps = nm(6)
    if not ps:
        return None
    os2 = tt["OS/2"] if "OS/2" in tt else None
    style = nm(17) or nm(2) or ""
    return {"file": path, "index": index, "ps": ps, "family": nm(1), "style": nm(2), "full": nm(4),
            "typo_family": nm(16), "typo_style": nm(17), "weight": getattr(os2, "usWeightClass", None),
            "italic": bool(re.search(r"italic|oblique", style.lower())), "arabic": _arabic(tt),
            "source": "adobe-fonts" if "livetype" in path.lower().replace("\\", "/").split("/") else "system"}


def _read_faces(path: str) -> list[dict]:
    """Every face of one font file (a collection: one per face index). Unreadable files give nothing."""
    from fontTools.ttLib import TTCollection, TTFont
    out = []
    try:
        with open(path, "rb") as f:
            collection = f.read(4) == b"ttcf"
        if collection:
            coll = TTCollection(path, lazy=True)
            try:
                for i, tt in enumerate(coll.fonts):
                    face = _face(tt, path, i)
                    if face:
                        out.append(face)
            finally:
                coll.close()
        else:
            with TTFont(path, lazy=True) as tt:
                face = _face(tt, path, 0)
                if face:
                    out.append(face)
    except Exception:  # noqa: BLE001 — a damaged or encrypted file is not a font we can use
        return []
    return out


def _scan(roots: list[Path]) -> list[dict]:
    out, seen = [], set()
    for r in roots:
        for here, files in _walk(r):
            for n in files:
                p = os.path.join(here, n)
                key = os.path.normcase(os.path.abspath(p))
                if key in seen or not _is_font(p, n):
                    continue
                seen.add(key)
                out += _read_faces(p)
    return out


def _cache_file() -> Path | None:
    try:
        from .common import current_context
        return current_context().engine_home / "cache" / "font-index.json"
    except Exception:  # noqa: BLE001 — no context bound (a server request outside one): memory cache only
        return None


def _load_disk(stamp: list) -> list[dict] | None:
    f = _cache_file()
    try:
        data = json.loads(f.read_text(encoding="utf-8")) if f and f.is_file() else None
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != VERSION:
        return None
    hit = next((e for e in data.get("entries") or [] if isinstance(e, dict) and e.get("stamp") == stamp), None)
    return hit.get("faces") if hit and isinstance(hit.get("faces"), list) else None


def _save_disk(stamp: list, faces: list[dict]) -> None:
    f = _cache_file()
    if not f:
        return
    try:
        old = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    except (OSError, ValueError):
        old = {}
    entries = [e for e in (old.get("entries") or []) if isinstance(e, dict) and e.get("stamp") != stamp] \
        if isinstance(old, dict) and old.get("version") == VERSION else []
    entries = (entries + [{"stamp": stamp, "faces": faces}])[-_MEM_MAX:]
    try:
        from .common import write_json
        write_json(f, {"version": VERSION, "entries": entries})
    except OSError:
        pass                        # a read-only engine home: the memory cache still works


def clear_cache(disk: bool = True) -> None:
    """Forget the index (tests; `disk` also removes the engine-home cache file)."""
    _MEM.clear()
    _ARABIC_FILES.clear()
    f = _cache_file() if disk else None
    if f:
        try:
            f.unlink()
        except OSError:
            pass


def faces(dirs=None) -> list[dict]:
    """Every font face in the font folders (default plat.font_dirs()): {file, index, ps, family, style, full,
    typo_family, typo_style, weight, italic, arabic, source}, in folder order. Cached until a folder changes."""
    roots = _roots(dirs)
    stamp = _stamp(roots)
    key = json.dumps(stamp)
    if key in _MEM:
        _MEM[key] = _MEM.pop(key)
        return _MEM[key]
    out = _load_disk(stamp)
    if out is None:
        out = _scan(roots)
        _save_disk(stamp, out)
    _MEM[key] = out
    while len(_MEM) > _MEM_MAX:
        del _MEM[next(iter(_MEM))]
    return out


def _norm(s) -> str:
    return re.sub(r"[\s_-]+", " ", str(s or "").lower()).strip()


def find(name: str, dirs=None) -> dict | None:
    """The face named `name`: its PostScript name (exact, any case), else its full name ("IBM Plex Sans Arabic Bold"),
    else its family ("IBM Plex Sans Arabic": the upright face nearest Regular). None when nothing is installed."""
    if not name:
        return None
    fs = faces(dirs)
    low = str(name).strip().lower()
    hit = next((f for f in fs if f["ps"].lower() == low), None)
    if hit:
        return hit
    n = _norm(name)
    hit = next((f for f in fs if _norm(f["full"]) == n), None)
    if hit:
        return hit
    fam = [f for f in fs if n in (_norm(f["family"]), _norm(f["typo_family"]))]
    return min(fam, key=lambda f: (f["italic"], abs((f["weight"] or 400) - 400))) if fam else None


def find_file(name: str, dirs=None) -> str | None:
    """The font file of the face named `name` (see find), or None."""
    hit = find(name, dirs)
    return hit["file"] if hit else None


def postscript_names(dirs=None) -> dict:
    """PostScript name -> font file, every installed face (the first one found wins)."""
    out = {}
    for f in faces(dirs):
        out.setdefault(f["ps"], f["file"])
    return out


def supports_arabic(file: str, index: int = 0) -> bool:
    """Does the face `index` of a font file (a client's brand font) cover Arabic. Unreadable: False."""
    try:
        st = os.stat(file)
    except OSError:
        return False
    key = (str(file), int(index or 0), st.st_size, st.st_mtime_ns)
    if key not in _ARABIC_FILES:
        from fontTools.ttLib import TTFont
        try:
            with TTFont(str(file), lazy=True, fontNumber=int(index or 0)) as tt:
                _ARABIC_FILES[key] = _arabic(tt)
        except Exception:  # noqa: BLE001 — unreadable font file
            _ARABIC_FILES[key] = False
    return _ARABIC_FILES[key]


def arabic_fallback(bold: bool = False, dirs=None, system: str | None = None) -> dict | None:
    """The system font that draws Arabic when the client has none (G72): the platform's list (Windows: Segoe UI, Arial,
    Tahoma; macOS: Geeza Pro, Arial; Linux: Noto Sans Arabic, DejaVu Sans), the bold faces first when `bold`, else
    any installed face that covers Arabic. None when the machine has no Arabic font at all."""
    fs = [f for f in faces(dirs) if f["arabic"]]
    by_ps = {}
    for f in fs:
        by_ps.setdefault(f["ps"], f)
    lists = FALLBACKS[_system(system)]
    for ps in (lists["bold"] + lists["regular"]) if bold else lists["regular"]:
        if ps in by_ps:
            return by_ps[ps]
    want = 700 if bold else 400
    upright = [f for f in fs if not f["italic"]] or fs
    return min(upright, key=lambda f: abs((f["weight"] or 400) - want)) if upright else None


def fallback_name(face: dict) -> str:
    return face.get("full") or " ".join(x for x in (face.get("family"), face.get("style")) if x) or face["ps"]


def fallback_warning(face: dict | None) -> str:
    """The plan / previews warning for a client without an Arabic font (G72)."""
    if not face:
        return ("client has no Arabic font and this machine has none either — Arabic text cannot be drawn; install "
                "the brand font")
    return (f"client has no Arabic font — using {fallback_name(face)} ({Path(face['file']).name}); install the brand "
            f"font")
