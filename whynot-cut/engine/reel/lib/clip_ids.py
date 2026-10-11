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

from .common import Paths, read_json, short_hash, slug, stable_id, write_json

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


def assign(root, rels, ids: dict) -> dict:
    """A copy of `ids` with an id for every clip in `rels` that has none yet (pure: writes nothing)."""
    ids = dict(ids)
    have = {_nfc(v) for v in ids.values()}
    new = sorted({_nfc(r) for r in rels} - have)
    projects = Paths(root).output / "projects"
    old_slugs = [slug(Path(_nfc(r)).stem) for r in {_nfc(r) for r in rels} | have]
    for rel in new:
        i = clip_id_for(rel, ids)
        # 2.x named a project after slug(stem) (VIDEO for an Arabic name): adopt that folder when it exists, no other
        # clip slugs the same way and it is free, so a lone Arabic clip edited with 2.x keeps its project
        old = slug(Path(rel).stem)
        if old != i and old_slugs.count(old) == 1 and old.upper() not in {k.upper() for k in ids} \
                and (projects / old).is_dir():
            i = old
        ids[i] = rel
    return ids


def source_rels(inv: dict | None) -> list[str]:
    return [f["rel"] for f in (inv or {}).get("files", []) if f.get("role") == "source_footage" and f.get("rel")]


def clip_ids(root, inv: dict | None = None) -> dict:
    """{id: relative path} for every raw clip in the inventory (default: the last discovery), new ones added and saved."""
    if inv is None:
        inv = read_json(Paths(root).output / "discovery/input-inventory.json", {})
    old = load(root)
    ids = assign(root, source_rels(inv), old)
    if ids != old:
        write_json(Paths(root).output / MAP_REL, ids)
    return ids


def id_of(ids: dict, rel: str) -> str | None:
    rel = _nfc(rel)
    return next((k for k, v in ids.items() if _nfc(v) == rel), None)


def resolve(root, video_id: str, inv: dict | None = None) -> Path | None:
    """The raw clip a --video-id names: its id (any case), else the raw file stem, else the 2.x slug when exactly one
    clip has it. None when nothing matches (or the old slug is shared, e.g. VIDEO for two Arabic names)."""
    if inv is None:
        inv = read_json(Paths(root).output / "discovery/input-inventory.json", {})
    files = {_nfc(f["rel"]): Path(f["path"]) for f in (inv or {}).get("files", [])
             if f.get("role") == "source_footage" and f.get("rel")}
    ids = clip_ids(root, inv)
    want = _nfc(video_id)
    for k, rel in ids.items():
        if k.upper() == want.upper() and _nfc(rel) in files:
            return files[_nfc(rel)]
    stem = [f for r, f in files.items() if Path(r).stem.casefold() == want.casefold()]
    if stem:
        return stem[0]
    old = [f for r, f in files.items() if slug(Path(r).stem) == want.upper()]
    return old[0] if len(old) == 1 else None
