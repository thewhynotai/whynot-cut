"""Motion-mode commands of the `reel` CLI (registered by cli.py: subparser names, arguments, dispatch).

A motion project is a clip-like project `<EP>_<ID>_MO` created by `reels-select --as motion`; its commands take
`--video-id <EP>_<ID>_MO`. Commands in NO_ID (machine or library level) need no video id.
"""
from __future__ import annotations

import json

ARGS: dict = {
    "ae-status": [],
    "ae-probe": [
        (("--record",), {"choices": ["ok", "fail"], "default": None,
                         "help": "record YOUR verdict after viewing every probe frame"}),
        (("--word-order",), {"choices": ["logical", "visual"], "default": None,
                             "help": "what word_reveal_20 showed: logical = only the first spoken word (rightmost in RTL)"}),
        (("--notes",), {"default": "", "help": "what the frames showed"}),
        (("--timeout",), {"type": int, "default": 600}),
    ],
}
NO_ID = {"ae-status", "ae-probe"}


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


def cmd_ae_probe(a):
    from . import ae_probe
    if a.record:
        if not a.word_order:
            raise SystemExit("--record needs --word-order logical|visual (what the word_reveal frames showed)")
        out(ae_probe.record(a.record, a.notes, a.word_order))
        return
    fonts = None
    if getattr(a, "root", None):                 # probe with the client's brand fonts when a client is given
        from .ae_builder import fonts_map
        from .common import Paths
        fonts = {"headline": fonts_map(Paths(a.root).client_db).get("headline")}
    r = ae_probe.run_probe(fonts, timeout=a.timeout)
    out({k: v for k, v in r.items() if k != "readback"})


def dispatch(a) -> bool:
    fn = globals().get("cmd_" + a.cmd.replace("-", "_"))
    if a.cmd not in ARGS or fn is None:
        return False
    fn(a)
    return True
