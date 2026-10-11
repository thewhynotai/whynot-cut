"""Motion-mode commands of the `reel` CLI (registered by cli.py: subparser names, arguments, dispatch).

A motion project is a clip-like project `<EP>_<ID>_MO` created by `reels-select --as motion`; its commands take
`--video-id <EP>_<ID>_MO`. Commands in NO_ID (machine or library level) need no video id.
"""
from __future__ import annotations

import json

ARGS: dict = {
    "ae-status": [],
}
NO_ID = {"ae-status"}


def add_args(name: str, sp) -> None:
    for flags, kw in ARGS.get(name, []):
        sp.add_argument(*flags, **kw)


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def P(a):
    from .common import Paths
    if not getattr(a, "video_id", None):
        raise SystemExit("--video-id required (the motion project id, e.g. EP12_R03_MO; `reel episode-next` lists them)")
    return Paths(a.root, a.video_id)


def cmd_ae_status(a):
    from . import ae_bridge, plat
    st = ae_bridge.status()
    ok = plat.debug_mode_ok()
    if st["alive"]:
        nxt = "ok: After Effects answers through the WhyNot Cut Bridge"
    elif not plat.newest_app("after_effects"):
        nxt = "After Effects is not installed: motion-build --script-only delivers the JSX"
    elif not ok:
        nxt = ("PlayerDebugMode is off, so After Effects will not load the bridge. The editor runs these commands "
               "themselves (an Adobe preference; WhyNot Cut never changes it), then restarts After Effects: "
               + " ; ".join(plat.debug_mode_commands()))
    else:
        nxt = ("start After Effects (the bridge starts by itself). Installed while AE was open? Quit and reopen it. "
               "Not installed yet: `reel ppro-install` (one bundle for Premiere and After Effects)")
    out({"bridge": st, "debug_mode_ok": ok, "next": nxt})


def dispatch(a) -> bool:
    fn = globals().get("cmd_" + a.cmd.replace("-", "_"))
    if a.cmd not in ARGS or fn is None:
        return False
    fn(a)
    return True
