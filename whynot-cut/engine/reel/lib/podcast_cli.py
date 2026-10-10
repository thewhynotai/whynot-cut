"""Podcast-mode commands of the `reel` CLI (registered by cli.py: subparser names, arguments, dispatch).

Episode commands take `--episode <EP>` (the id from `reel episodes`); when a client has exactly one episode it is used.
"""
from __future__ import annotations

import json
from pathlib import Path

ARGS: dict = {
    "episodes": [],
    "episode-prep": [],
}


def add_args(name: str, sp) -> None:
    for flags, kw in ARGS.get(name, []):
        sp.add_argument(*flags, **kw)


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def EP(a):
    from .episode import EpisodePaths
    return EpisodePaths(a.root, a.episode)


def resolve_episode(a) -> None:
    """Fill a.episode when the command needs one and the client has exactly one episode."""
    if a.cmd == "episodes" or getattr(a, "episode", None):
        return
    from .episode import list_episodes
    eps = list_episodes(Path(a.root))
    if len(eps) == 1:
        a.episode = eps[0]["episode_id"]
        return
    raise SystemExit("--episode required (" + (f"episodes: {', '.join(e['episode_id'] for e in eps)}"
                                               if eps else "no episode in data/Episodes") + ")")


def cmd_episodes(a):
    from .episode import list_episodes
    out({"episodes": list_episodes(Path(a.root), refresh=True)})


def cmd_episode_prep(a):
    from .episode import prep
    out(prep(EP(a)))


def dispatch(a) -> bool:
    fn = globals().get("cmd_" + a.cmd.replace("-", "_"))
    if a.cmd not in ARGS or fn is None:
        return False
    resolve_episode(a)
    fn(a)
    return True
