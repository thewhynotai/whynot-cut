"""Content-type recipes (config/defaults/recipes.json, profile-overridable): how a reel of a given type is paced,
framed, captioned, decorated, scored and written about. The engine applies the numbers; story-editor and
publish-writer follow the rest."""
from __future__ import annotations

import copy

from .common import load_config


def types() -> dict:
    return load_config("recipes.json").get("types", {})


def resolve(type_id: str) -> dict:
    """The recipe for one type (a copy, with its id), or {} for an unknown type."""
    r = types().get(type_id)
    return dict(copy.deepcopy(r), type=type_id) if r else {}


def for_paths(paths) -> dict | None:
    """The recipe a reel was selected with (00_inputs/source.json), or None for an ordinary clip."""
    from .common import source_range
    rng = source_range(paths)
    r = rng.get("recipe") if rng else None
    return r if r else None


def pause_params(paths, cli_min: int | None = None, cli_pad: int | None = None) -> dict:
    """Pause-removal thresholds: explicit CLI value > the reel's recipe > the profile's style.json remove_pauses >
    250/80 ms, per value. `source` says where the values came from (shown to the editor): one origin, or each value's
    when they differ ("command line (min_pause_ms), recipe drama (pad_ms)")."""
    keys = ("min_pause_ms", "pad_ms")
    vals, srcs = {"min_pause_ms": 250, "pad_ms": 80}, dict.fromkeys(keys, "default")

    def layer(given: dict, name: str):
        for k in keys:
            if given.get(k) is not None:
                vals[k], srcs[k] = int(given[k]), name
    style = load_config("style.json").get("remove_pauses") or {}
    if isinstance(style, dict):
        layer({k: style.get(k) or None for k in keys}, "profile style.json")
    rec = for_paths(paths)
    layer({k: ((rec or {}).get("pacing") or {}).get(k) or None for k in keys}, f"recipe {(rec or {}).get('type')}")
    layer({"min_pause_ms": cli_min, "pad_ms": cli_pad}, "command line")
    src = srcs[keys[0]] if len(set(srcs.values())) == 1 else ", ".join(f"{srcs[k]} ({k})" for k in keys)
    return dict(vals, source=src)


MUSIC_EXT = {".wav", ".mp3", ".m4a", ".aac", ".aif", ".aiff", ".flac"}


def music_library(root) -> list[dict]:
    """Licensed tracks in data/Music with mood tags: data/Music/music.json {"tracks": [{"file", "moods", "license"}]}
    wins; otherwise the file name's words are the tags (tense_dark_loop.wav -> tense, dark, loop)."""
    import re
    from pathlib import Path
    from .common import read_json
    d = Path(root) / "data" / "Music"
    if not d.is_dir():
        return []
    meta = {Path(t.get("file", "")).name.lower(): t for t in (read_json(d / "music.json", {}) or {}).get("tracks", [])}
    out = []
    for f in sorted(d.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in MUSIC_EXT or f.name.startswith("."):
            continue
        m = meta.get(f.name.lower(), {})
        moods = m.get("moods") or [w for w in re.split(r"[^A-Za-z؀-ۿ]+", f.stem.lower()) if len(w) > 2]
        out.append({"rel": f.relative_to(root).as_posix(), "moods": moods, "license": m.get("license", ""),
                    "tagged_by": "music.json" if m else "file name"})
    return out
