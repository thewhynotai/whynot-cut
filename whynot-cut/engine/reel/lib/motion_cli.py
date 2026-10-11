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
    "motion-icons": [
        (("--search",), {"required": True, "help": "concept words in English, e.g. \"money, growth\""}),
        (("--limit",), {"type": int, "default": 12}),
    ],
    "motion-library": [],
    "motion-plan": [],
    "motion-animatic": [(("--width",), {"type": int, "default": 540})],
    "motion-build": [
        (("--replace-edited",), {"action": "store_true", "help": "the editor changed the .aep: keep a backup, then rebuild"}),
        (("--allow-fallback-font",), {"action": "store_true",
                                      "help": "only with the editor's OK: a system Arabic font where a brand font is missing"}),
        (("--script-only",), {"action": "store_true", "help": "write the self-contained JSX (no After Effects needed)"}),
        (("--run-script",), {"action": "store_true", "help": "no bridge: hand the JSX to AE (no read-back; QC cannot pass)"}),
        (("--timeout",), {"type": int, "default": 900}),
    ],
}
NO_ID = {"ae-status", "ae-probe", "motion-icons", "motion-library"}


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


def cmd_motion_icons(a):
    from .motion_icons import load_index, search
    hits = []
    for part in [x for x in a.search.split(",") if x.strip()] or [a.search]:
        hits += [dict(h, query=part.strip()) for h in search(part, a.limit)]
    out({"set": "lucide (ISC)", "icons": len(load_index()), "hits": hits,
         "how": "use the name in motion-script.json (\"icon\": \"<name>\"); arrows/chevrons are mirrored in RTL"})


def cmd_motion_library(a):
    from .motion_library import library_dir, load_packs
    packs = load_packs()
    out({"library_dir": str(library_dir()), "packs": [{k: (list(v) if k == "items" else v) for k, v in p.items()}
                                                      for p in packs],
         "how": "illustrations are used as \"pack/item\"; only packs with ok: true (a pack.json with an allowed "
                "license) can be used" if packs else
                "no packs: add licensed illustration packs (each with pack.json) to the library folder, or use icons"})


def cmd_motion_plan(a):
    from .motion_plan import compile_motion
    p = P(a)
    r = compile_motion(p)
    out({"ok": r["ok"], "errors": r["errors"], "warnings": r["warnings"], "approvals": r["approvals"],
         "editorial_lines": len(r["editorial_lines"]), "plan": r["plan"], "md": r["md"],
         "next": ("reel motion-animatic, VIEW the storyboard, then show the editor motion-plan.md + the animatic "
                  "(Gate 1)") if r["ok"] else "fix 01_analysis/motion-script.json and run motion-plan again"})


def cmd_motion_animatic(a):
    from .motion_animatic import render
    r = render(P(a), width=a.width)
    r["next"] = ("VIEW the storyboard and watch the animatic, then show the editor motion-plan.md + the animatic "
                 "(Gate 1: `reel approve-plan --by editor` only with their words)")
    out(r)


def cmd_motion_build(a):
    from . import motion_build as mb
    p = P(a)
    if a.script_only:
        out(mb.script_only(p))
        return
    if a.run_script:
        out(mb.run_script(p, timeout=a.timeout))
        return
    r = mb.build(p, replace_edited=a.replace_edited, allow_fallback_font=a.allow_fallback_font, timeout=a.timeout)
    r = {k: v for k, v in r.items() if k != "readback"}
    r["next"] = ("reel motion-render" if r["status"] == "PROJECT_ASSEMBLED" else
                 "fix the reasons above (Needs you items go to the editor), then motion-build again")
    out(r)


def dispatch(a) -> bool:
    fn = globals().get("cmd_" + a.cmd.replace("-", "_"))
    if a.cmd not in ARGS or fn is None:
        return False
    fn(a)
    return True
