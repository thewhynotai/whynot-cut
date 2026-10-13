"""Clip identity (3.0): one stable id per raw clip, the project folder output/projects/<id>/.

The id rule is the episode rule (common.stable_id): an ASCII name keeps its slug ("C0239.MP4" -> C0239,
"Dr Sherif intro.mp4" -> DR_SHERIF_INTRO, so 2.x projects keep their folders); a name with Arabic (or no) letters gets
a short hash ("مقابلة ١.mp4" -> CLIP_<hash>). An id already held by another clip is never handed out again:
the same stem with another extension gets the extension (C0239.mov -> C0239_MOV), another name with the same slug
gets the hash of its name, then the hash of its path.

Ids are persisted in output/discovery/clip-ids.json ({id: relative path}). Once assigned an id never changes and is
never reused, even after its clip is gone.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

from .common import Paths, file_locked, read_json, short_hash, slug, stable_id, write_json

MAP_REL = "discovery/clip-ids.json"


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", str(s))


def clip_id_for(path, taken=None) -> str:
    """The id for one raw clip. `path` is the clip's path relative to the client folder (data/Raw/x.mp4), `taken` the
    ids already in use ({id: relative path}, or any iterable of ids). Ids compare case-insensitively (Windows and
    macOS folders do)."""
    taken = taken or {}
    held = {str(k).upper(): (v if isinstance(taken, dict) else None) for k, v in
            (taken.items() if isinstance(taken, dict) else ((t, None) for t in taken))}
    return _clip_id(path, held)


def _clip_id(path, held: dict) -> str:
    """clip_id_for with the taken ids already as {ID (upper case): relative path or None} (assign keeps one)."""
    p = Path(_nfc(Path(path).as_posix()))
    stem = p.stem
    base = stable_id(stem, "CLIP")
    cands = [base]
    holder = held.get(base.upper())
    hp = Path(_nfc(holder)) if holder else None
    if hp and hp.stem.casefold() == stem.casefold() and p.suffix and hp.suffix.casefold() != p.suffix.casefold():
        cands.append(f"{base}_{slug(p.suffix)}")              # C0239.MP4 + C0239.mov
    if base == slug(stem):
        cands.append(f"{base}_{short_hash(stem)}")            # "Dr Sherif intro" + "dr-sherif-intro"
    cands.append(f"{base}_{short_hash(p.as_posix())}")        # same name in another folder
    for c in cands:
        if c.upper() not in held:
            return c
    n = 2
    while f"{base}_{n}".upper() in held:
        n += 1
    return f"{base}_{n}"


def load(root) -> dict:
    try:
        m = read_json(Paths(root).output / MAP_REL, {})
    except (OSError, ValueError):
        m = None
    return {str(k): str(v) for k, v in m.items()} if isinstance(m, dict) else {}


def _key(rel) -> str:
    """Relative paths compare NFC + case-insensitively: C0239.MP4 renamed C0239.mp4 is the same clip (Windows, macOS)."""
    return _nfc(Path(str(rel)).as_posix()).casefold()


key = _key


def index(ids: dict) -> dict:
    """{key(relative path): id} for a map {id: relative path}: build it once, then look clips up by key(rel) (dict
    lookups; id_of per clip is a scan of the whole map)."""
    return {_key(v): k for k, v in ids.items()}


def assign(root, rels, ids: dict) -> dict:
    """A copy of `ids` with an id for every clip in `rels` that has none yet (pure: writes nothing)."""
    from collections import Counter
    ids = dict(ids)
    have = {_key(v) for v in ids.values()}
    new = {}
    for r in rels:
        if _key(r) not in have:
            new.setdefault(_key(r), _nfc(r))
    if not new:
        return ids
    projects = Paths(root).output / "projects"
    every = [Path(_nfc(r)).stem for r in {_key(r): r for r in list(rels) + list(ids.values())}.values()]
    old_slugs = Counter(slug(st) for st in every)            # counted once: the loop below stays linear (review I1)
    stems = Counter(st.casefold() for st in every)
    held = {str(k).upper(): v for k, v in ids.items()}       # kept up to date as ids are handed out
    for rel in sorted(new.values()):                         # C0239.MP4 before C0239.mov, as in 3.0.0
        i = _clip_id(rel, held)
        # a 2.x project of this clip keeps its folder when it is unambiguous (no other clip slugs/is named the same way)
        # and free: output/projects/<raw stem> (an agent passed the file name as --video-id) or
        # output/projects/<slug(stem)> (VIDEO for a lone Arabic clip, auto-filled by 2.x). When both exist the raw-stem
        # folder wins, for ASCII and Arabic names alike (3.0 T11; CHANGELOG Migration): the other folder is left as it is
        stem = Path(rel).stem
        for old, ok in ((stem, stems[stem.casefold()] == 1), (slug(stem), old_slugs[slug(stem)] == 1)):
            if old.upper() != i.upper() and ok and old.upper() not in held and (projects / old).is_dir():
                i = old
                break
        ids[i] = rel
        held[i.upper()] = rel
    return ids


def source_rels(inv: dict | None) -> list[str]:
    return [f["rel"] for f in (inv or {}).get("files", []) if f.get("role") == "source_footage" and f.get("rel")]


def clip_ids(root, inv: dict | None = None) -> dict:
    """{id: relative path} for every raw clip in the inventory (default: the last discovery), new ones added and saved."""
    if inv is None:
        inv = read_json(Paths(root).output / "discovery/input-inventory.json", {})
    with file_locked(Paths(root).output / MAP_REL):      # T2.4: parallel subagents add clips to one map
        old = load(root)
        ids = assign(root, source_rels(inv), old)
        if ids != old:
            write_json(Paths(root).output / MAP_REL, ids)
    return ids


def id_of(ids: dict, rel: str) -> str | None:
    rel = _key(rel)
    return next((k for k, v in ids.items() if _key(v) == rel), None)


def _resolve_rel(root, video_id: str, inv: dict | None):
    """(ids, files {key: (rel, path)}, the matching key or None). Refuses (SystemExit) an id whose clip is gone."""
    if inv is None:
        inv = read_json(Paths(root).output / "discovery/input-inventory.json", {})
    files = {_key(f["rel"]): (f["rel"], Path(f["path"])) for f in (inv or {}).get("files", [])
             if f.get("role") == "source_footage" and f.get("rel")}
    ids = clip_ids(root, inv)
    want = _nfc(video_id)
    key = next((k for k in ids if k.upper() == want.upper()), None)
    if key is not None:
        if _key(ids[key]) in files:
            return ids, files, _key(ids[key])
        raise SystemExit(f"clip id {key} was {ids[key]}, which is no longer in data/: restore it or pass --footage")
    stem = [k for k, (r, _) in files.items() if Path(_nfc(r)).stem.casefold() == want.casefold()]
    if len(stem) == 1:
        return ids, files, stem[0]
    if stem:                                     # same stem, several extensions: never guess
        return ids, files, None
    old = [k for k, (r, _) in files.items() if slug(Path(_nfc(r)).stem) == want.upper()]
    return ids, files, (old[0] if len(old) == 1 else None)


def resolve(root, video_id: str, inv: dict | None = None) -> Path | None:
    """The raw clip a --video-id names: its id (any case), else the raw file stem, else the 2.x slug, each only when
    exactly one clip matches (VIDEO for two Arabic names, or "C0239" for C0239.MP4 + C0239.mov, matches none).
    An id whose clip left data/ is refused, never swapped for a sibling."""
    _, files, k = _resolve_rel(root, video_id, inv)
    return files[k][1] if k else None


def canonical(root, video_id: str, inv: dict | None = None) -> str | None:
    """The map id for what --video-id names (C0239 for "c0239", DR_SHERIF_INTRO for "Dr Sherif intro"), or None."""
    ids, files, k = _resolve_rel(root, video_id, inv)
    return id_of(ids, files[k][0]) if k else None
