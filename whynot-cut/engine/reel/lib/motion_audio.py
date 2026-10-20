"""Audio for motion videos: the cleaned dialogue laid on the sequence clock exactly as the TimeMap quantises it (so
animation cue frames and the voice can never drift apart), its per-frame loudness for the voice pulse, synthesised SFX
files, the music bed (T4.6: a licensed track from data/Music chosen by the recipe's mood, ducked under the dialogue
with level keyframes) and (for the animatic and a render without audio) a full mix.

Music licences (T4.6): a JSON file next to the track (`<track file name>.licence.json`, or `.license.json`) or one per
folder (`licence.json` / `license.json`, covering only that folder's tracks it names in "files", or "*"). Fields as a
library pack.json: "license" (one of motion.json licenses_allowed, or "client" for the client's own music), "source",
"attribution" (CC-BY), "proof" (needed for "commercial": an order id, or a receipt file inside the licence's folder).
Nothing else counts: not a bare PDF/TXT, not music.json's "license" text. No valid licence -> no music and one
NEEDS-YOU item. The client's data/ is only ever read; a licence file is at most 64 KB and never raises.
"""
from __future__ import annotations

import json
import math
import os
import re
import unicodedata
import wave
from pathlib import Path

import numpy as np

SR = 48000

# ducking and level limits (dB, ms); a client profile's motion.json "music" block may override any of them
DUCK_DEFAULTS = {"attack_ms": 150, "release_ms": 400, "hold_ms": 300, "lift_db": 8.0, "free_max_db": -12.0,
                 "floor_db": -60.0, "fade_in_ms": 500, "fade_out_ms": 2000, "level_min_db": -40.0, "level_max_db": -12.0}
TRACK_LICENCE_SUFFIXES = (".licence.json", ".license.json")
FOLDER_LICENCES = ("licence.json", "license.json")
MUSIC_DIR = ("data", "Music")
LICENCE_MAX_BYTES = 64 * 1024
DEFAULT_LICENSES = ["CC0-1.0", "MIT", "ISC", "Apache-2.0", "CC-BY-4.0", "commercial"]
LEVEL_BOUNDS = (-40.0, -12.0)           # the motion-script schema's music.level_db range; a profile never widens it
HASH_SPAN = 1024 * 1024                 # the fingerprint hashes a track's first and last MB (and its size)
FLOOR_BOUNDS = (-96.0, -48.0)           # the silent end of the fades (After Effects reads -48 dB and below as off)
MUSIC_JSON_MAX = 1024 * 1024
# a proof value is a receipt FILE only with one of these extensions (or when such a file exists next to the
# licence); anything else, dots included ("Artlist.io order 88123", "shop@example.com"), is an order id
PROOF_DOC_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".eml", ".html", ".htm", ".docx", ".doc", ".rtf",
                 ".zip"}


def _key(name: str) -> str:
    """File-name identity across platforms: NFC (macOS may hand back NFD), case-folded (NTFS / APFS default)."""
    return unicodedata.normalize("NFC", name).casefold()


# Mood words -> the recipes' English moods. Arabic words (file names, music.json) are compared after _ar_norm; the
# English concept words map too. A word that is not here stays unknown (and the plan says so when nothing fits).
MOOD_TABLE = {
    "hope": (["uplifting", "inspiring", "warm"], ["امل", "الامل", "تفاؤل", "تفاول", "متفائل", "رجاء"]),
    "tension": (["tense", "dark", "cinematic"], ["توتر", "متوتر", "قلق", "تشويق", "اثاره", "اكشن", "دراما", "درامي"]),
    "calm": (["soft", "minimal", "warm"], ["هادي", "هادئ", "هدوء", "سكينه", "رايق", "راحه", "استرخاء", "ساكن"]),
    "energy": (["upbeat", "light", "playful"], ["حماس", "حماسي", "طاقه", "نشاط", "نشيط", "سريع", "مبهج", "فرحان"]),
    "sad": (["soft", "piano"], ["حزين", "حزن", "شجن", "زعل", "زعلان", "كئيب", "حنين"]),
    "inspiring": (["inspiring", "uplifting"], ["ملهم", "الهام", "تحفيز", "تحفيزي", "محفز", "ملهمه"]),
}
_AR_MARKS = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")      # harakat, tatweel
_ARABIC = re.compile("[\u0600-\u06ff]")


def _ar_norm(word: str) -> str:
    """NFC, no diacritics or tatweel, alef forms unified (أ إ آ ٱ -> ا), ى -> ي, ة -> ه."""
    w = _AR_MARKS.sub("", unicodedata.normalize("NFC", word))
    for a in "أإآٱ":
        w = w.replace(a, "ا")
    return w.replace("ى", "ي").replace("ة", "ه")


def _mood_index() -> dict:
    idx = {}
    for concept, (moods, words) in MOOD_TABLE.items():
        for w in [concept] + words:
            idx.setdefault(_ar_norm(w), [])
            idx[_ar_norm(w)] += [m for m in moods if m not in idx[_ar_norm(w)]]
    return idx


def resolve_moods(words: list) -> tuple[list[str], list[str]]:
    """(the moods the words name, the Arabic words not in MOOD_TABLE). English words are kept as they are (and an
    English concept word adds its moods); an Arabic word, with or without the article, maps through the table."""
    idx = _mood_index()
    moods, unknown = [], []

    def add(xs):
        moods.extend(x for x in xs if x not in moods)
    for w in words:
        w = unicodedata.normalize("NFC", str(w)).strip()
        if not w:
            continue
        if _ARABIC.search(w):
            n = _ar_norm(w)
            hit = idx.get(n) or (idx.get(n[2:]) if n.startswith("ال") and len(n) > 4 else None)
            if hit:
                add(hit)
            elif w not in unknown:
                unknown.append(w)
        else:
            add([w.lower()])
            add(idx.get(w.lower(), []))
    return moods, unknown


def duck_cfg() -> dict:
    """DUCK_DEFAULTS with a profile's motion.json "music" numbers on top, clamped: levels inside the schema's
    -40..-12 dB, the floor inside -96..-48 dB; a negative time or lift, or anything that is not a number, keeps the
    default."""
    from . import motion_config
    over = motion_config.motion_cfg().get("music") or {}
    c = dict(DUCK_DEFAULTS)
    if isinstance(over, dict):
        for k, v in over.items():
            if k in c and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
                c[k] = float(v) if isinstance(c[k], float) else v
    lo, hi = LEVEL_BOUNDS
    for k in ("level_min_db", "level_max_db", "free_max_db"):
        c[k] = float(min(hi, max(lo, c[k])))
    c["floor_db"] = float(min(FLOOR_BOUNDS[1], max(FLOOR_BOUNDS[0], c["floor_db"])))
    for k in ("attack_ms", "release_ms", "hold_ms", "fade_in_ms", "fade_out_ms", "lift_db"):
        if c[k] < 0:                    # a negative time or lift: the default, not 0 (review ruling M8)
            c[k] = DUCK_DEFAULTS[k]
    return c


def _is_link(p: str) -> bool:
    return os.path.islink(p) or bool(getattr(os.path, "isjunction", lambda _p: False)(p))


def _music_reached_through_link(root: Path) -> bool:
    """data/ or data/Music is a symlink or junction: music is then never read (nothing is read through a link)."""
    return any(_is_link(str(Path(root).joinpath(*MUSIC_DIR[:k]))) for k in (1, 2))


def _regular(path: str) -> bool:
    import stat as _stat
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return _stat.S_ISREG(st.st_mode) and not _is_link(path)


def _walk(music_dir: Path):
    """(folder, sorted file names) under data/Music, never through a symlink or junction; only regular files are
    listed (a FIFO, device or link named like a track or a licence is skipped)."""
    for dirpath, dirnames, filenames in os.walk(music_dir, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not _is_link(os.path.join(dirpath, d)))
        yield Path(dirpath), sorted(f for f in filenames if _regular(os.path.join(dirpath, f)))


class _Why(str):
    """A licence problem: the technical text (kept in `why`) with its code (and a value, e.g. the licence type) for
    the editor's wording (_plain). Plain strings (read errors) have no code: "can't be read"."""
    code = "unreadable"
    arg = ""


def _why(code: str, text: str, arg: str = "") -> _Why:
    w = _Why(text)
    w.code, w.arg = code, arg
    return w


def _read_small(p: Path, cap: int) -> tuple[bytes | None, str]:
    """(at most cap bytes, '') or (None, why): lstat first (no link, a regular file only: never a FIFO, device or
    folder), then one non-blocking, no-follow handle, fstat again on it, and at most cap + 1 bytes read from it."""
    import stat as _stat
    name = p.name
    try:
        st = os.lstat(p)
    except OSError as e:
        return None, f"{name} cannot be read ({e.strerror or e})"
    if _stat.S_ISLNK(st.st_mode) or _is_link(str(p)):
        return None, f"{name} is a link, not a licence file"
    if _stat.S_ISDIR(st.st_mode):
        return None, f"{name} is a folder, not a licence file"
    if not _stat.S_ISREG(st.st_mode):
        return None, f"{name} is not a regular file"
    if st.st_nlink != 1:
        return None, f"{name} is hard-linked to another file, not a licence file of its own"
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(p, flags)
    except OSError as e:
        return None, f"{name} cannot be read ({e.strerror or e})"
    try:
        with open(fd, "rb") as fh:
            fst = os.fstat(fh.fileno())
            if not _stat.S_ISREG(fst.st_mode):
                return None, f"{name} is not a regular file"
            if not os.path.samestat(st, fst):       # swapped between the lstat and the open (Windows has no O_NOFOLLOW)
                return None, f"{name} changed while reading"
            data = fh.read(cap + 1)
    except OSError as e:
        return None, f"{name} cannot be read ({e.strerror or e})"
    if len(data) > cap:
        return None, f"{name} is over {cap // 1024} KB: a licence file is a few short fields"
    return data, ""


def _read_licence(p: Path) -> tuple[dict | None, str]:
    """(object, '') or (None, why); never raises (a hostile or broken file is just not a licence)."""
    name = p.name
    raw, why = _read_small(p, LICENCE_MAX_BYTES)
    if raw is None:
        return None, why
    if not raw.strip():
        return None, f"{name} is empty"
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, f"{name} is not UTF-8 JSON text"
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        return None, f"{name} is not valid JSON (malformed or nested too deeply)"
    if not isinstance(data, dict):
        return None, f"{name} must be a JSON object (wrong format)"
    return data, ""


def _allowed() -> list[str]:
    """motion.json licenses_allowed (absent: the defaults; [] stays empty, as motion_qc reads it) plus "client"."""
    from . import motion_config
    lst = motion_config.motion_cfg().get("licenses_allowed")
    lst = DEFAULT_LICENSES if lst is None else [str(x).strip() for x in lst] if isinstance(lst, list) else []
    return sorted(set(lst) | {"client"})


def _proof_problem(proof: str, folder: Path, music_dir: Path) -> str:
    """'' when the proof is usable. A value that ends in a document extension (PROOF_DOC_EXT), or names a file that
    exists next to the licence, is a receipt file: relative, no "..", no link on the way, inside the licence's folder
    (or data/Music), and it must exist. Anything else is an order id (dots included)."""
    from pathlib import PurePosixPath, PureWindowsPath
    doc = PurePosixPath(proof.replace("\\", "/")).suffix.lower() in PROOF_DOC_EXT
    try:
        there = os.path.lexists(folder / proof)
    except (OSError, ValueError):
        there = False
    if not doc and not there:
        return ""
    if PureWindowsPath(proof).is_absolute() or PurePosixPath(proof).is_absolute() or PureWindowsPath(proof).drive:
        return f"proof {proof!r} must be a file name next to the licence, not an absolute path"
    parts = PurePosixPath(proof.replace("\\", "/")).parts
    if ".." in parts:
        return f"proof {proof!r} must not leave the licence's folder (\"..\")"
    cur = folder
    for part in parts:
        cur = cur / part
        if _is_link(str(cur)):
            return f"proof {proof!r} goes through a link"
    try:
        real = cur.resolve()
        inside = any(real.is_relative_to(d.resolve()) for d in (folder, music_dir))
    except OSError:
        inside = False
    if not inside:
        return f"proof {proof!r} is outside the licence's folder"
    if not cur.is_file():
        return f"proof file {proof!r} not found next to it"
    return ""


def _stripped(data: dict) -> dict:
    """The licence with its text values (and its "files" names) stripped of surrounding whitespace (review M10)."""
    out = {k: (v.strip() if isinstance(v, str) else v) for k, v in data.items()}
    if isinstance(out.get("files"), list):
        out["files"] = [f.strip() if isinstance(f, str) else f for f in out["files"]]
    return out


def _check_licence(data: dict, name: str, folder: Path, is_folder: bool, music_dir: Path) -> str:
    """Why this licence is not usable, or ''. `data` is _stripped."""
    allowed = _allowed()
    lic = data.get("license")
    if not isinstance(lic, str) or not lic.strip():
        return _why("no_type", f'{name} has no "license" field')
    if lic not in allowed:
        return _why("not_allowed", f"{name}: license {lic!r} is not allowed ({', '.join(allowed)})", lic)
    if not isinstance(data.get("source"), str) or not data["source"].strip():
        return _why("no_source", f'{name} needs a "source" (where the track was licensed from)')
    attr = data.get("attribution")
    if attr is not None and not isinstance(attr, str):
        return _why("attribution", f'{name}: "attribution" must be text')
    if lic.upper().startswith("CC-BY") and not (attr or "").strip():
        return _why("attribution", f"{name}: a {lic} licence needs its attribution text")
    proof = data.get("proof")
    if proof is not None and not isinstance(proof, str):
        return _why("proof", f'{name}: "proof" must be text')
    if lic == "commercial" and not (proof or "").strip():
        return _why("proof", f'{name}: a commercial licence needs a "proof" (an order id, or a receipt file next to it)')
    if proof and proof.strip():
        why = _proof_problem(proof.strip(), folder, music_dir)
        if why:
            return _why("proof", f"{name}: {why}")
    if is_folder:
        files = data.get("files")
        if files != "*" and not (isinstance(files, list) and files and all(isinstance(f, str) for f in files)):
            return _why("files", f'{name}: a folder licence must say which "files" it covers ("*" or a list of names)')
    return ""


def _licence_record(data: dict, path: Path, root: Path, via: str) -> dict:
    return {"license": data["license"], "source": data["source"].strip(),
            "attribution": str(data.get("attribution") or "").strip(), "proof": str(data.get("proof") or "").strip(),
            "via": via, "path": path.relative_to(root).as_posix()}


def _one_of(files: list[Path]) -> tuple[dict | None, Path | None, str]:
    """The licence among every spelling of the same file (.licence/.license, NFC/NFD, case): one that is broken, or
    any two that differ, are no licence."""
    got = [(_read_licence(f), f) for f in files]
    if len(got) == 1:
        (data, why), f = got[0]
        return data, f, why
    first = got[0][0][0]
    if any(d is None or d != first for (d, _w), _f in got):
        names = " and ".join(f.name for _x, f in got)
        return None, got[0][1], _why("disagree", f"{names} exist and disagree (keep one)")
    return first, got[0][1], ""


def licence_for(track: Path, names: list[str], root: Path) -> tuple[dict | None, str, bool]:
    """(licence record, '', False) or (None, why, invalid). `names`: the (non-link) file names in the track's folder.
    `invalid`: a licence file is there but cannot be used (broken, wrong fields), as opposed to none at all or a
    folder licence that does not list the track. A track licence decides alone (a broken one never falls back to the
    folder's); else the folder licence, if it names the track."""
    folder = track.parent
    music_dir = Path(root).joinpath(*MUSIC_DIR)
    tk = _key(track.name)
    side = [folder / n for n in names if _key(n) in {tk + s for s in TRACK_LICENCE_SUFFIXES}]
    if side:
        data, f, why = _one_of(side)
        if data is None:
            return None, why, True
        data = _stripped(data)
        why = _check_licence(data, f.name, folder, False, music_dir)
        return (None, why, True) if why else (_licence_record(data, f, root, "track"), "", False)
    fold = [folder / n for n in names if _key(n) in FOLDER_LICENCES]
    if not fold:
        return None, _why("no_licence", f"no licence for {track.name}: add {track.name}.licence.json next to it (or a "
                                        "licence.json for its folder)"), False
    data, f, why = _one_of(fold)
    if data is None:
        return None, why, True
    data = _stripped(data)
    why = _check_licence(data, f.name, folder, True, music_dir)
    if why:
        return None, why, True
    if data["files"] != "*" and tk not in {_key(n) for n in data["files"] if isinstance(n, str)}:
        return None, _why("not_listed", f"the folder licence {f.name} does not list {track.name}"), False
    return _licence_record(data, f, root, "folder"), "", False


def probe_duration(path: Path) -> float | None:
    from .media_util import media_duration_s
    return media_duration_s(path)


def _moods_meta(music_dir: Path) -> dict:
    """data/Music/music.json by track name, read like a licence (no link, a regular file, at most 1 MB); a broken one
    only loses the mood tags."""
    meta = {}
    f = music_dir / "music.json"
    if os.path.lexists(f):
        raw, _why = _read_small(f, MUSIC_JSON_MAX)
        try:
            meta = json.loads(raw.decode("utf-8-sig")) if raw else {}
        except (ValueError, RecursionError, UnicodeDecodeError):
            meta = {}
    tracks = meta.get("tracks") if isinstance(meta, dict) else None
    return {_key(Path(str(t.get("file", ""))).name): t for t in tracks or [] if isinstance(t, dict)}


def music_catalog(root, probe: bool = True) -> list[dict]:
    """Every track in data/Music (subfolders included, links never followed) with its moods, licence and length:
    {"rel", "file", "moods", "unknown_moods", "licensed", "licence", "why", "licence_invalid", "decodes",
    "duration_s"}. Reads only. probe=False never asks for the length (the fingerprint: a slow or failing probe must
    never make a plan look stale); "decodes" / "duration_s" are then None."""
    from .recipes import MUSIC_EXT
    root = Path(root)
    music_dir = root.joinpath(*MUSIC_DIR)
    if _music_reached_through_link(root) or not music_dir.is_dir():
        return []
    meta = _moods_meta(music_dir)
    out = []
    for folder, names in _walk(music_dir):
        for n in names:
            f = folder / n
            if n.startswith(".") or f.suffix.lower() not in MUSIC_EXT:
                continue
            m = meta.get(_key(n)) or {}
            words = m.get("moods") if isinstance(m.get("moods"), list) else None
            if not words:
                words = [w for w in re.split(r"[^A-Za-z\u0600-\u06ff]+", unicodedata.normalize("NFC", f.stem).lower())
                         if len(w) > 2]
            moods, unknown = resolve_moods(words)
            licence, why, invalid = licence_for(f, names, root)
            dur = ok = None
            if probe:
                try:
                    dur = probe_duration(f)
                except Exception:  # noqa: BLE001  (no probe -> the length is unknown: the track is not used)
                    dur = None
                ok = bool(dur and dur > 0)
            out.append({"rel": f.relative_to(root).as_posix(), "file": str(f), "moods": moods, "unknown_moods": unknown,
                        "licensed": licence is not None, "licence": licence, "why": str(why),
                        "why_code": getattr(why, "code", "unreadable") if why else "",
                        "why_arg": getattr(why, "arg", "") if why else "", "licence_invalid": invalid,
                        "decodes": ok, "duration_s": round(float(dur), 3) if ok else None})
    return out


_CONTENT_IDS: dict = {}


def _content_id(path: Path) -> list:
    """[size, sha256 of the first and last MB]: a replaced track of the very same length still changes it; a copied
    folder (new times, same bytes) does not. Cached in-process by (path, size, mtime_ns); the value never holds a
    time."""
    import hashlib
    import stat as _stat
    try:
        st = os.lstat(path)
        if not _stat.S_ISREG(st.st_mode) or _is_link(str(path)):
            return [None, "not a regular file"]
        key = (str(path), st.st_size, st.st_mtime_ns)
        if key in _CONTENT_IDS:
            return list(_CONTENT_IDS[key])
        h = hashlib.sha256()
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0) |
                     getattr(os, "O_NOFOLLOW", 0))
        with open(fd, "rb") as fh:
            fst = os.fstat(fh.fileno())
            if not _stat.S_ISREG(fst.st_mode) or not os.path.samestat(st, fst):
                return [None, "changed while reading"]
            h.update(fh.read(HASH_SPAN))
            if st.st_size > HASH_SPAN:
                fh.seek(max(HASH_SPAN, st.st_size - HASH_SPAN))
                h.update(fh.read(HASH_SPAN))
        val = [st.st_size, h.hexdigest()]
        if len(_CONTENT_IDS) > 4096:
            _CONTENT_IDS.clear()
        _CONTENT_IDS[key] = tuple(val)
        return val
    except OSError as e:
        return [None, f"unreadable: {e.strerror or e}"]


def _nfc(x):
    return unicodedata.normalize("NFC", x) if isinstance(x, str) else x


def _state_of(e: dict) -> list:
    lic = dict(e["licence"], path=_nfc(e["licence"]["path"])) if e.get("licence") else None
    return [_nfc(e["rel"]), e["moods"], lic, _nfc(e["why"]), _content_id(Path(e["file"]))]


def given_rel(root: Path, given) -> str | None:
    """A motion-script music.file as its data/Music/... path, or None when it is not under data/Music. The folders
    are compared one by one with _key (NFC, case-folded): on macOS resolve() keeps the case the script gives, so
    data/music/Track.WAV still names data/Music/track.wav; the track part keeps the given spelling (the catalog
    lookup is by _key too)."""
    g = str(given).replace("\\", "/")
    try:
        f = (Path(root) / g).resolve()
        md = Path(root).joinpath(*MUSIC_DIR).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    fp, mp = f.parts, md.parts
    if len(fp) <= len(mp) or any(_key(a) != _key(b) for a, b in zip(fp, mp)):
        return None
    return "/".join(MUSIC_DIR + tuple(fp[len(mp):]))


def music_state(root, script_music="__auto__", moods=None) -> list:
    """What the music choice of THIS plan reads, for its fingerprint: music off, or a recipe with no music mood
    (`moods` == []) -> nothing; a track picked by hand -> that track (content, licence) and the bytes of its licence
    files, from the same walk as the plan (music_catalog); the auto pick -> the whole library. No probing, paths NFC.
    What After Effects then holds (the MUSIC layer, its source file and keys) is not fingerprinted: the read-back
    checks it and fails honestly."""
    root = Path(root)
    m = script_music
    if m is False or (isinstance(m, dict) and m.get("off") is True):
        return []
    if isinstance(m, dict) and m.get("file"):
        given = str(m["file"])
        try:
            rel = given_rel(root, given)
            if rel is None:
                return [["outside data/Music", given]]
            e = next((x for x in music_catalog(root, probe=False) if _key(x["rel"]) == _key(rel)), None)
            if e is None:
                return [["not an audio track under data/Music", _nfc(rel)]]
            folder, tk = Path(e["file"]).parent, _key(Path(e["file"]).name)
            raw = []
            for _f, names in [(folder, sorted(n for n in os.listdir(folder) if _regular(os.path.join(folder, n))))]:
                for n in names:
                    if _key(n) in FOLDER_LICENCES or _key(n) in {tk + x for x in TRACK_LICENCE_SUFFIXES}:
                        data, w = _read_small(folder / n, LICENCE_MAX_BYTES)
                        raw.append([_nfc(n), data.decode("utf-8", "replace") if data is not None else w])
            return [_state_of(e) + [raw]]
        except (OSError, ValueError):
            return [["outside data/Music", given]]
    if moods is not None and not moods:
        return []
    return [_state_of(e) for e in music_catalog(root, probe=False)]


def _score(entry: dict, moods: list[str]) -> int:
    want = {_key(str(m)) for m in moods}
    return len(want & {_key(str(m)) for m in entry.get("moods") or []})


def pick_track(catalog: list[dict], moods: list[str], duration_s: float) -> dict | None:
    """The licensed, readable track that fits the most moods; ties: one that covers the video, then the least
    overrun (or the longest short one), then the name. None when no track fits any mood."""
    if not moods:
        return None
    best, best_k = None, None
    for e in catalog:
        if not e.get("licensed") or not e.get("decodes"):
            continue
        s = _score(e, moods)
        if s == 0:
            continue
        d = float(e.get("duration_s") or 0)
        covers = d >= duration_s
        k = (-s, 0 if covers else 1, (d - duration_s) if covers else (duration_s - d),
             unicodedata.normalize("NFC", e["rel"]).casefold(), e["rel"])
        if best_k is None or k < best_k:
            best, best_k = e, k
    return best


def check_level(level_db, cfg: dict | None = None) -> float:
    c = cfg or DUCK_DEFAULTS
    try:
        v = float(level_db)
    except (TypeError, ValueError):
        raise ValueError(f"music level {level_db!r} is not a number") from None
    if isinstance(level_db, bool) or not (c["level_min_db"] <= v <= c["level_max_db"]):
        raise ValueError(f"music level {level_db!r} dB is outside {c['level_min_db']:g}..{c['level_max_db']:g} dB")
    return v


def duck_keyframes(speech: list, n_frames: int, fps: float, level_db: float, cfg: dict | None = None,
                   end_frame: int | None = None) -> list[list]:
    """Audio Levels keys [[frame, dB], ...] for the music bed: `level_db` under speech (frame ranges [a, b] on the
    sequence clock), lifted by lift_db (at most free_max_db) in gaps long enough for attack + release + hold, a fade
    in from floor_db at 0 and a fade out to floor_db at the end (the video's, or the track's own when it is shorter).
    Linear in dB between keys, as After Effects interpolates them."""
    c = dict(DUCK_DEFAULTS, **(cfg or {}))
    level = check_level(level_db, c)
    # the gaps are never quieter than the bed under speech (a free_max below the level would invert the ducking)
    floor, free = float(c["floor_db"]), max(level, min(level + float(c["lift_db"]), float(c["free_max_db"])))
    end = int(n_frames) if end_frame is None else max(1, min(int(n_frames), int(end_frame)))
    fpms = fps / 1000.0
    att, rel = c["attack_ms"] * fpms, c["release_ms"] * fpms
    thr = (c["attack_ms"] + c["release_ms"] + c["hold_ms"]) * fpms
    runs = sorted([max(0, int(a)), min(end, int(b))] for a, b in speech if min(end, int(b)) > max(0, int(a)))
    merged: list[list[int]] = []
    for a, b in runs:
        if merged and (a <= merged[-1][1] or (a - merged[-1][1]) < thr - 1e-9):
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    fi, fo = max(c["fade_in_ms"] * fpms, 1e-9), max(c["fade_out_ms"] * fpms, 1e-9)

    def g(f: int) -> float:
        v = free
        for a, b in merged:
            if a <= f <= b:
                return level
            if f < a and a - f < att:
                v = min(v, level + (free - level) * (a - f) / att)
            if f > b and f - b < rel:
                v = min(v, level + (free - level) * (f - b) / rel)
        return v

    pts = []
    for f in range(end + 1):
        v = min(g(f), floor + (free - floor) * f / fi, floor + (free - floor) * (end - f) / fo)
        pts.append([f, max(floor, v)])
    keys = [pts[0]]
    for i in range(1, len(pts) - 1):           # drop keys that sit on the line between their neighbours
        (f0, v0), (f1, v1), (f2, v2) = keys[-1], pts[i], pts[i + 1]
        if abs(v0 + (v2 - v0) * (f1 - f0) / (f2 - f0) - v1) > 1e-6:
            keys.append(pts[i])
    if len(pts) > 1:
        keys.append(pts[-1])
    return [[int(f), round(float(v), 3)] for f, v in keys]


def speech_frames(words: list[dict], tmap) -> list[list[int]]:
    """The words' [start, end] frames on the sequence clock (TimeMap: removed pauses are gone)."""
    out = []
    for w in words:
        a, b = tmap.frame(w["start_ms"]), tmap.frame(w["end_ms"])
        if b > a:
            out.append([a, b])
    return out


def _need(why: str, ref: str, text: str, text_ar: str) -> dict:
    return {"kind": "music", "text": text, "text_ar": text_ar, "why": why, "ref": ref}


def licence_template() -> str:
    """The licence file an editor writes (English keys, both languages around them): NEEDS-YOU and the handoff."""
    allowed = " | ".join(_allowed())
    return ("Licence file template (نموذج ملف الترخيص): save it next to the track as \"<track file name>.licence.json\", "
            "or as \"licence.json\" for a whole folder (احفظه جنب التراك باسم \"<اسم ملف التراك>.licence.json\"، أو "
            "\"licence.json\" للفولدر كله): "
            f'{{"license": "{allowed}", "source": "where the music came from", "attribution": "the credit line", '
            '"proof": "order id, or receipt.pdf", "files": "*"}. "attribution" only for CC-BY, "proof" only for '
            'commercial (an order id, or a receipt file next to the licence), "files" only in a folder licence ("*" = '
            'every track in that folder, or a list such as ["a.wav", "b.wav"]). '
            '"license": نوع الترخيص (واحد من اللي فوق)؛ "source": جبت الموسيقى منين؛ "attribution": سطر الإسناد '
            '(لـ CC-BY بس)؛ "proof": الإثبات، رقم الأوردر أو ملف الإيصال جنب الترخيص (للـ commercial بس)؛ "files": '
            'في ترخيص الفولدر بس، "*" لكل تراكات الفولدر أو قايمة بأسماء الملفات.')


DRAFTS_README = "README.txt"


def _guess_from_text(text: str) -> str:
    t = text.lower()
    return ("CC0-1.0" if "cc0" in t else "CC-BY-4.0" if ("cc by" in t or "cc-by" in t) else
            "MIT" if t.strip() == "mit" else "commercial")


def _draft_for(e: dict, root: Path, meta: dict) -> dict:
    """A licence the editor completes: what is known (a broken licence's fields, music.json's licence text), the
    licence type guessed (commercial unless the text says otherwise), and where the finished file goes."""
    track = Path(e["file"])
    known = {}
    for suf in TRACK_LICENCE_SUFFIXES:                      # what an unusable licence file already says
        data, _why = _read_licence(track.parent / (track.name + suf))
        if isinstance(data, dict):
            known = data
            break
    text = str((meta.get(_key(track.name)) or {}).get("license") or "").strip()
    lic = known.get("license") if known.get("license") in _allowed() else _guess_from_text(text)
    # "source" stays empty on purpose (review M2): a draft moved unchanged must never become a valid licence; what
    # music.json or a broken licence file said is kept beside it for the editor
    out = {"license": lic, "source": "", "attribution": "", "proof": "",
           "_track": e["rel"], "_move_to": e["rel"] + ".licence.json"}
    if text:
        out["_music_json_said"] = text
    if known:
        out["_licence_file_said"] = {k: v for k, v in known.items() if isinstance(v, (str, int, float, bool))}
    out["_how"] = ("Check \"license\" (one of " + ", ".join(_allowed()) + "), fill in \"source\"; \"attribution\" "
                   "for CC-BY, \"proof\" for commercial. Then move this file to data/Music next to the track (the path "
                   "in _move_to). WhyNot Cut never writes into data/.")
    return out


def write_licence_drafts(entries: list[dict], drafts_dir: Path, root: Path) -> list[str]:
    """Filled licence drafts for `entries` under drafts_dir (the project's output/, never data/), mirroring their
    folders under data/Music, plus a README with the moves. A draft already there is never rewritten (the editor may
    be filling it in). Returns the drafts' paths relative to the client root."""
    root = Path(root)
    music_dir = root.joinpath(*MUSIC_DIR)
    try:
        if Path(drafts_dir).resolve().is_relative_to(root.joinpath("data").resolve()):
            return []
    except OSError:
        return []
    meta = _moods_meta(music_dir) if music_dir.is_dir() else {}
    out, lines = [], []
    for e in entries:
        sub = Path(e["rel"]).relative_to("/".join(MUSIC_DIR))
        f = Path(drafts_dir) / sub.parent / (sub.name + ".licence.json")
        if not f.exists():
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_name(f.name + ".tmp")
            tmp.write_text(json.dumps(_draft_for(e, root, meta), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp.replace(f)
        rel = f.relative_to(root).as_posix() if f.is_relative_to(root) else str(f)
        out.append(rel)
        lines.append(f"- {rel}  ->  {e['rel']}.licence.json")
    if out:
        readme = Path(drafts_dir) / DRAFTS_README
        text = ("Music licence drafts. Fill each one in (license, source; attribution for CC-BY, proof for "
                "commercial), then move it to data/Music next to its track. WhyNot Cut never writes into data/.\n"
                "مسودات ملفات ترخيص الموسيقى: كمّل كل ملف، وبعدين انقله لـ data/Music جنب التراك بتاعه.\n\n"
                + "\n".join(lines) + "\n")
        if not readme.exists() or readme.read_text(encoding="utf-8") != text:
            readme.write_text(text, encoding="utf-8")
    return out


def _draft_line(drafts: list[str]) -> tuple[str, str]:
    """The sentence (EN, AR) that points the editor to the drafts."""
    if not drafts:
        return "", ""
    if len(drafts) == 1:
        return (f" A filled-in draft is at {drafts[0]}: complete it and move it to data/Music next to the track.",
                f" فيه مسودة متعبّية للملف في {drafts[0]}: كمّلها وانقلها لـ data/Music جنب التراك.")
    where = str(Path(drafts[0]).parent.as_posix()).split("/06_audio/licence-drafts")[0] + "/06_audio/licence-drafts"
    return (f" Filled-in drafts are in {where} ({DRAFTS_README} lists them): complete each one and move it to "
            "data/Music next to its track.",
            f" فيه مسودات متعبّية في {where} ({DRAFTS_README} فيه القايمة): كمّل كل واحدة وانقلها لـ data/Music جنب "
            "التراك بتاعها.")


_PLAIN = {   # reason code (licence_for / _check_licence) -> what the editor reads, EN / Egyptian Arabic
    "no_licence": ("no licence file", "ملوش ملف ترخيص"),
    "not_listed": ("the folder licence doesn't list it", "ترخيص الفولدر مش مكتوب فيه"),
    "not_allowed": ("the licence type {0} isn't allowed", "نوع الترخيص {0} مش مسموح بيه"),
    "no_type": ("the licence type (license) is missing", "نوع الترخيص (license) ناقص"),
    "no_source": ("the licence doesn't say where the music came from (source)",
                  "الترخيص مش مكتوب فيه جبت الموسيقى منين (source)"),
    "attribution": ("the credit line (attribution) is missing", "سطر الإسناد (attribution) ناقص"),
    "proof": ("the purchase proof (proof) is missing or not found", "إثبات الشراء (proof) ناقص أو مش موجود"),
    "disagree": ("it has two licence files that say different things", "ليه ملفين ترخيص مكتوب فيهم كلام مختلف"),
    "files": ("the folder licence doesn't say which files it covers (files)",
              "ترخيص الفولدر مش مكتوب فيه الملفات اللي بيغطيها (files)"),
    "unreadable": ("its licence file can't be read (the details say why)",
                   "ملف الترخيص بتاعه مش مقروء (السبب في التفاصيل)"),
}


def _plain_parts(e: dict) -> tuple[str, str, str]:
    """(track name, EN reason, AR reason) of one track's licence problem in the editor's words, from its reason code
    (music_catalog's "why_code"), never from the text: a file or proof value named "proof" or "attribution", in any
    letter case, cannot change it. A file that cannot be read at all (empty, broken, wrong format, a link, a hard
    link, too big) is "can't be read"; the technical reason stays in `why`."""
    en, ar = _PLAIN.get(e.get("why_code") or "unreadable", _PLAIN["unreadable"])
    arg = e.get("why_arg") or ""
    return Path(e["rel"]).name, en.format(arg), ar.format(arg)


def _plain(e: dict) -> tuple[str, str]:
    """(EN, AR): "<track>: <reason>"."""
    name, en, ar = _plain_parts(e)
    return f"{name}: {en}", f"{name}: {ar}"


def _plain_list(entries: list[dict], k: int = 3) -> tuple[str, str]:
    got = [_plain(e) for e in entries[:k]]
    more = len(entries) - k
    return ("; ".join(g[0] for g in got) + (f" (and {more} more)" if more > 0 else ""),
            "؛ ".join(g[1] for g in got) + (f" (و{more} كمان)" if more > 0 else ""))


def _reasons(entries: list[dict], k: int = 3) -> str:
    out = []
    for e in entries[:k]:
        name = Path(e["rel"]).name
        out.append(e["why"] if name in e["why"] else f"{name}: {e['why']}")
    more = len(entries) - k
    return "; ".join(out) + (f" (and {more} more)" if more > 0 else "")


def music_plan(root, script_music, recipe: dict | None, speech: list, n_frames: int, fps: float,
               drafts_dir: Path | None = None) -> dict:
    """The motion plan's music: {"music": dict | None, "needs_you": [...], "warnings": [...], "errors": [...],
    "asset": dict | None}. An explicit motion-script music.file wins (if licensed); `false` / {"off": true} turns
    music off; otherwise the recipe's moods pick the track. No usable licensed track -> no music, one NEEDS-YOU (and,
    with drafts_dir, filled licence drafts for the tracks that only lack a licence, in the project's output/)."""
    root = Path(root)
    res = {"music": None, "needs_you": [], "warnings": [], "errors": [], "asset": None}
    m = script_music
    if m is False or (isinstance(m, dict) and m.get("off") is True):
        return res
    m = m if isinstance(m, dict) else {}
    rmus = (recipe or {}).get("music") or {}
    c = duck_cfg()
    level = m.get("level_db", rmus.get("level_db", -24))
    try:
        level = check_level(level, c)
    except ValueError as e:
        res["errors"].append(f"music.level_db: {e} (allowed {c['level_min_db']:g} to {c['level_max_db']:g} dB)")
        return res
    moods = rmus.get("mood") or []
    moods = [moods] if isinstance(moods, str) else [str(x) for x in moods]
    catalog = music_catalog(root)
    dur_s = n_frames / fps
    def warn_invalid(entries):      # a licence file that is there but unusable, for the tracks this choice reads
        for x in entries:
            if x.get("licence_invalid"):
                res["warnings"].append(f"music: the licence file of {x['rel']} is not valid ({x['why']})")
    tpl = licence_template()
    if m.get("file"):
        rel = given_rel(root, m["file"])
        try:
            there = rel is not None and (root / rel).is_file()
        except OSError:
            there = False
        if not there:
            res["errors"].append(f"music {m['file']!r} must be a licensed track file under data/Music")
            return res
        e = next((x for x in catalog if _key(x["rel"]) == _key(rel)), None)
        if e is None:
            res["errors"].append(f"music {m['file']!r} is not an audio track under data/Music" + (
                " (data/Music is reached through a link, and music is never read through a link: use the real "
                "folder)" if _music_reached_through_link(root) else ""))
            return res
        warn_invalid([e])
        if not e["licensed"]:
            den, dar = _draft_line(write_licence_drafts([e], drafts_dir, root) if drafts_dir else [])
            pen, par = _plain(e)
            res["needs_you"].append(_need(
                f"{e['why']}. {tpl}", e["rel"],
                f"The chosen track {e['rel']} has no valid licence ({pen}). Add the music's licence file next to it "
                f"(the template is in the details), or choose another track.{den}",
                f"التراك المختار {e['rel']} ملوش ترخيص صالح ({par}). ضيف ملف ترخيص الموسيقى جنبه (النموذج في "
                f"التفاصيل)، أو اختار تراك تاني.{dar}"))
            return res
        if not e["decodes"]:
            res["needs_you"].append(_need(
                "the track cannot be read (damaged, or not audio)", e["rel"],
                f"The chosen track {e['rel']} can't be played (damaged, or not audio). Replace it or choose another "
                "track.",
                f"التراك المختار {e['rel']} مش بيشتغل (بايظ أو مش ملف صوت). بدّله أو اختار تراك تاني."))
            return res
        if moods and _score(e, moods) == 0:
            res["warnings"].append(f"music {e['rel']}: its moods ({', '.join(e['moods']) or 'none'}) do not match the "
                                   f"video's mood ({', '.join(moods)}); kept as chosen")
        chosen = e
    else:
        if moods:                   # no mood: the choice reads no track (and warns about none)
            warn_invalid(catalog)
        chosen = None
        usable = [x for x in catalog if x["licensed"] and x["decodes"]]
        # tracks that fit the mood and are refused only for their licence are named first, with their reasons
        fit_unlic = [x for x in catalog if not x["licensed"] and x["decodes"] and _score(x, moods) > 0]
        if fit_unlic:
            parts = [_plain_parts(x) for x in fit_unlic[:3]]
            more = len(fit_unlic) - 3
            if len(fit_unlic) == 1:
                n, r_en, r_ar = parts[0]
                fit_en = f" {n} fits the mood but lacks a valid licence ({r_en})."
                fit_ar = f" {n} على المود بس ملوش ترخيص صالح ({r_ar})."
            else:
                fit_en = (" These tracks fit the mood but lack a valid licence: "
                          + "; ".join(f"{n} ({r})" for n, r, _a in parts) + (f" (and {more} more)" if more > 0 else "")
                          + ".")
                fit_ar = (" التراكات دي على المود بس ملهمش ترخيص صالح: "
                          + "؛ ".join(f"{n} ({a})" for n, _r, a in parts) + (f" (و{more} كمان)" if more > 0 else "")
                          + ".")
        else:
            fit_en = fit_ar = ""
        if not moods:
            why = "this kind of video has no music mood, so no track was picked"
            en = ("This kind of video has no music mood, so no track was picked. Choose a licensed track for it, or "
                  "add music yourself in After Effects.")
            ar = ("النوع ده من الفيديوهات مالوش مود موسيقى، فمفيش تراك اتختار. اختار تراك مرخّص للفيديو، أو حط "
                  "الموسيقى بنفسك في After Effects.")
        elif _music_reached_through_link(root):
            why = "data/ or data/Music is reached through a link (a junction or symlink): music is never read through a link"
            en = ("No music was read: data/Music (or data) is a link (a junction or symlink) to another place, and "
                  "WhyNot Cut never reads music through a link. Put the music in a real data/Music folder. Until then the "
                  "video has speech and sound effects only.")
            ar = ("مفيش مزيكا اتقرت: فولدر data/Music (أو data) متوصّل بلينك (junction) لمكان تاني، والمزيكا مش بتتقري "
                  "من خلال لينك. حط المزيكا في فولدر data/Music حقيقي. لحد ما ده يحصل الفيديو فيه كلام ومؤثرات صوتية "
                  "بس.")
        elif not usable:
            bad = [x for x in catalog if not x["licensed"]]
            damaged = [x for x in catalog if x["licensed"] and not x["decodes"]]
            if bad:
                order = sorted(bad, key=lambda x: 0 if x in fit_unlic else 1)
                rs = _reasons(order)
                pen, par = _plain_list(order)
                fit = [x for x in bad if x["decodes"] and _score(x, moods) > 0]
                den, dar = _draft_line(write_licence_drafts((fit or [x for x in bad if x["decodes"]])[:3], drafts_dir,
                                                            root) if drafts_dir else [])
                why = f"no track in data/Music can be used: {rs}. {tpl}"
                if damaged:         # some licensed but damaged, the rest unlicensed: not "none has a licence"
                    dn = ", ".join(Path(x["rel"]).name for x in damaged[:3])
                    en = (f"No music in data/Music can be used: the licensed {dn} can't be played (damaged, or not "
                          f"audio), and the other tracks have no valid licence ({pen}). Replace the damaged tracks, or "
                          "add each other track's licence file next to it (the template is in the details). Until then "
                          f"the video has speech and sound effects only.{den}")
                    ar = (f"مفيش موسيقى في data/Music تنفع: {dn} مرخّص بس مش بيشتغل (بايظ أو مش ملف صوت)، والباقي "
                          f"ملوش ترخيص صالح ({par}). بدّل التراكات البايظة، أو ضيف ملف الترخيص جنب كل تراك تاني "
                          f"(النموذج في التفاصيل). لحد ما ده يحصل الفيديو فيه كلام ومؤثرات صوتية بس.{dar}")
                else:
                    en = (f"None of the music in data/Music has a valid licence ({pen}). Add each track's licence file "
                          "next to it (the template is in the details), or add licensed tracks. Until then the video "
                          f"has speech and sound effects only.{den}")
                    ar = (f"مفيش موسيقى في data/Music ليها ترخيص صالح ({par}). ضيف ملف الترخيص جنب كل تراك (النموذج "
                          f"في التفاصيل)، أو ضيف تراكات مرخّصة. لحد ما ده يحصل الفيديو فيه كلام ومؤثرات صوتية بس.{dar}")
            elif catalog:
                names3 = ", ".join(Path(x["rel"]).name for x in catalog[:3])
                more = len(catalog) - 3
                rs = names3 + (f" (and {more} more)" if more > 0 else "")
                rs_ar = names3 + (f" (و{more} كمان)" if more > 0 else "")
                why = f"no track in data/Music can be played: {rs}"
                en = (f"None of the licensed music in data/Music can be played ({rs}). Replace the damaged tracks. Until "
                      "then the video has speech and sound effects only.")
                ar = (f"مفيش موسيقى مرخّصة في data/Music بتشتغل ({rs_ar}). بدّل التراكات البايظة. لحد ما ده يحصل "
                      "الفيديو فيه كلام ومؤثرات صوتية بس.")
            else:
                why = f"there is no music in data/Music. {tpl}"
                en = ("There is no music in data/Music. Add licensed tracks, each with its licence file next to it "
                      "(the template is in the details). Until then the video has speech and sound effects only.")
                ar = ("مفيش موسيقى في data/Music. ضيف تراكات مرخّصة، وجنب كل تراك ملف الترخيص بتاعه (النموذج في "
                      "التفاصيل). لحد ما ده يحصل الفيديو فيه كلام ومؤثرات صوتية بس.")
        else:
            chosen = pick_track(catalog, moods, dur_s)
            ms = ", ".join(moods)
            seen = sorted(usable, key=lambda x: 0 if x.get("unknown_moods") else 1)[:3]
            rs = "; ".join(f"{Path(x['rel']).name}: moods {', '.join(x['moods']) or 'none'}"
                           + (f" (Arabic mood words not known: {', '.join(x['unknown_moods'])})"
                              if x.get("unknown_moods") else "") for x in seen)
            rs_ar = "؛ ".join(f"{Path(x['rel']).name}: المود {'، '.join(x['moods']) or 'مفيش'}"
                              + (f" (كلمات مود عربي مش معروفة: {', '.join(x['unknown_moods'])})"
                                 if x.get("unknown_moods") else "") for x in seen)
            if len(usable) > 3:
                rs += f" (and {len(usable) - 3} more)"
                rs_ar += f" (و{len(usable) - 3} كمان)"
            fit = [x for x in catalog if not x["licensed"] and x["decodes"] and _score(x, moods) > 0][:3]
            den, dar = _draft_line(write_licence_drafts(fit, drafts_dir, root) if (drafts_dir and fit and
                                                                                   chosen is None) else [])
            why = f"no licensed track is tagged with this video's mood ({ms}): {rs}" + (
                f"; fitting but not licensed: {_reasons(fit_unlic)}" if fit_unlic else "")
            en = (f"No licensed track fits this video's mood ({ms}): {rs}.{fit_en} Add a licensed track tagged with one "
                  f"of these moods (in its file name or music.json), or choose a track for this video.{den}")
            ar = (f"مفيش تراك مرخّص على مود الفيديو ده ({'، '.join(moods)}): {rs_ar}.{fit_ar} ضيف تراك مرخّص متصنّف على المود ده (في اسم "
                  f"الملف أو music.json)، أو اختار تراك للفيديو ده.{dar}")
        if chosen is None:
            res["needs_you"].append(_need(why, "/".join(MUSIC_DIR), en, ar))
            return res
    end = None
    if chosen["duration_s"] * fps < n_frames:
        end = int(chosen["duration_s"] * fps + 1e-6)
        res["warnings"].append(f"music {chosen['rel']} is shorter than the video ({chosen['duration_s']:.1f} s < "
                               f"{dur_s:.1f} s): it plays once and fades out at its end")
    keys = duck_keyframes(speech, n_frames, fps, level, c, end)
    lic = chosen["licence"]
    res["music"] = {"file": str((root / chosen["rel"]).resolve()), "rel": chosen["rel"], "level_db": level,
                    "keyframes": keys, "end_frame": end if end is not None else int(n_frames),
                    "fade_out_frames": int(round(c["fade_out_ms"] * fps / 1000)), "duration_s": chosen["duration_s"],
                    "license": lic}
    res["asset"] = {"ref": chosen["rel"], "license": lic["license"], "attribution": lic["attribution"]}
    return res


def _write(path: Path, x: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.clip(x, -1, 1)
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[1])
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())
    return path


def sequence_dialogue(paths, tmap) -> Path:
    """06_audio/dialogue/dialogue_motion_seq_<hash>.wav: each kept piece of dialogue_clean.wav at its TimeMap frame.
    Content-addressed: After Effects keeps imported audio open (Windows), so an unchanged file is never rewritten and
    changed audio gets a new name the next build imports."""
    src = paths.p("06_audio/dialogue/dialogue_clean.wav")
    if not src.exists():
        raise SystemExit("06_audio/dialogue/dialogue_clean.wav missing — run `reel audio-clean` for this motion project")
    x = _decode(src)            # any PCM width (audio-clean writes 24-bit), via ffmpeg
    fms = tmap.frame_ms
    out = np.zeros((int(round(tmap.total_frames * fms * SR / 1000)), x.shape[1]), dtype=np.float32)
    for p in tmap.pieces:
        a = int(round(p["src_in_ms"] * SR / 1000))
        n = int(round((p["end_frame"] - p["start_frame"]) * fms * SR / 1000))
        o = int(round(p["start_frame"] * fms * SR / 1000))
        seg = x[a:a + n]
        out[o:o + len(seg)] = seg[: max(0, len(out) - o)]
    import hashlib
    pcm = (np.clip(out, -1, 1) * 32767).astype(np.int16)
    dst = paths.p(f"06_audio/dialogue/dialogue_motion_seq_{hashlib.sha1(pcm.tobytes()).hexdigest()[:8]}.wav")
    if not dst.exists():
        tmp = dst.with_suffix(".tmp")
        _write(tmp, out)
        tmp.replace(dst)
    _prune_dialogue(paths, keep=dst)
    return dst


def _prune_dialogue(paths, keep: Path) -> None:
    """Removes older sequence dialogues that nothing names any more: not the plan, not the last build job, not any
    project .aep (backups included; After Effects stores footage paths as text, a refused build or a fallback-script
    build leaves no job naming them). Names, not paths: the content hash is the identity, and a project moved from
    another computer keeps its old paths. One that After Effects (or a player) still holds open stays until a later
    run (Windows refuses to delete it)."""
    from pathlib import PureWindowsPath     # splits on / and \ alike
    from .common import read_json
    # the PREVIOUS plan, read while motion-plan compiles the new one: plain read_json, no version check (Gate 2 live
    # check: read_compiled here warned "motion-plan.json has no engine_version" about the file being replaced)
    plan = read_json(paths.p("01_analysis/motion-plan.json"), {}) or {}     # compiler-side read (the plan it replaces)
    job = (read_json(paths.p("04_after_effects/data/motion-job.json"), {}) or {}).get("plan") or {}
    named = {keep.name} | {PureWindowsPath(p["audio"]["dialogue"]).name for p in (plan, job)
                           if (p.get("audio") or {}).get("dialogue")}
    olds = [f for f in keep.parent.glob("dialogue_motion_seq_*.wav") if f.name not in named]
    if not olds:
        return
    projects = [a.read_bytes() for a in paths.p("04_after_effects/project").rglob("*.aep")]
    for f in olds:
        if any(f.name.encode("utf-8") in b or f.name.encode("utf-16-le") in b for b in projects):
            continue
        try:
            f.unlink()
        except PermissionError:
            pass


def envelope(wav: Path, fps: float, n_frames: int) -> list[float]:
    """RMS per frame, normalised to 0-1 (95th percentile = 1), rounded to 3 decimals."""
    x = _decode(Path(wav)).mean(axis=1)
    hop = SR / fps
    vals = []
    for k in range(n_frames):
        seg = x[int(k * hop):int((k + 1) * hop)]
        vals.append(float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0)
    ref = float(np.percentile(vals, 95)) if vals and max(vals) > 0 else 1.0
    return [round(min(1.0, v / ref), 3) if ref > 0 else 0.0 for v in vals]


def sfx_files(kinds: set[str], out_dir: Path) -> dict[str, Path]:
    from .sfx import synth
    out_dir.mkdir(parents=True, exist_ok=True)
    # an existing file is reused: synthesis is deterministic and After Effects may hold the old file open
    return {k: (out_dir / f"{k}.wav") if (out_dir / f"{k}.wav").exists() else synth(k, out_dir / f"{k}.wav")
            for k in sorted(kinds)}


def _decode(path: Path, max_s: float | None = None) -> np.ndarray:
    """Any audio file -> float32 (n, 2) at 48 kHz (ffmpeg; SFX are 24-bit, music may be mp3/m4a). `max_s` decodes only
    the first seconds (a one-hour music track is never read whole for a one-minute video)."""
    import subprocess
    from .common import ffmpeg_exe
    from .media_util import ff_timeout
    lim = ["-t", f"{max_s:.3f}"] if max_s is not None else []
    cmd = [ffmpeg_exe(), "-loglevel", "error", "-i", str(path), *lim, "-ac", "2", "-ar", str(SR), "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True, timeout=ff_timeout(cmd)).stdout or b""
    return (np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0).reshape(-1, 2)


def mix(plan: dict, root: Path, out: Path) -> Path:
    """Dialogue + music (its level keyframes, linear in dB as After Effects plays them; an older plan without keys: its
    flat level and fade-out) + each SFX at its frame, the plan's length, 48 kHz WAV."""
    fps = float(plan["fps"])
    n = int(round(plan["duration_frames"] / fps * SR))
    buf = np.zeros((n, 2), dtype=np.float32)

    def put(x: np.ndarray, at: int, gain: float = 1.0):
        if at >= n or not len(x):
            return
        m = min(len(x), n - at)
        buf[at:at + m] += x[:m] * gain
    a = plan["audio"]
    put(_decode(Path(a["dialogue"])), 0)
    if a.get("music"):
        mu = a["music"]
        mus = _decode(Path(mu["file"]), max_s=n / SR + 0.1)[:n].copy()
        keys = mu.get("keyframes")
        if keys:
            t = np.arange(len(mus), dtype=np.float64) * fps / SR          # frame time of each sample
            db = np.interp(t, [float(k[0]) for k in keys], [float(k[1]) for k in keys])
            mus *= (10 ** (db / 20)).astype(np.float32)[:, None]
            put(mus, 0)
        else:
            f = int(mu.get("fade_out_frames", 0) / fps * SR)
            if f and len(mus) >= n:
                mus[n - f:n] *= np.linspace(1, 0, f, dtype=np.float32)[:, None]
            put(mus, 0, 10 ** (float(mu.get("level_db", -24)) / 20))
    for c in a.get("sfx") or []:
        put(_decode(Path(c["file"])), int(round(c["frame"] / fps * SR)), 0.7)
    return _write(Path(out), buf)
