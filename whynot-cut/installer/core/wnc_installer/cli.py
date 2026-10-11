"""wnc_install: install | uninstall | plan.

The bootstrap (install.ps1 / install.sh) has put uv and python-build-standalone in place and runs
    <engine python> -I -B installer/core/wnc_install.py install [--log <file>] [--yes] ...
Step modules append (name, fn, needs) to STEPS (install) or UNINSTALL_STEPS; `install` runs the registered steps in
STEP_ORDER, whatever order they were registered in. `plan` prints the order as JSON and writes nothing.
Exit codes: 0 done (ok / amber / skipped), 1 at least one step red, 2 cannot start (platform, components.json).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import base

STEP_ORDER = ("preflight", "questions", "runtime", "ffmpeg", "gitbash", "gpu", "claude", "adobe", "fonts",
              "settings", "model", "state", "doctor", "launch")
STEPS: list = []            # install steps: (name, fn(ctx) -> StepResult, needs: tuple of step names)
UNINSTALL_STEPS: list = []  # uninstall steps, run in registration order


def _register_step_modules() -> None:
    """Each step module has register(STEPS) (and, for uninstall, register_uninstall(UNINSTALL_STEPS)). Imported here,
    after the registries exist, so a step module never imports cli."""
    from . import claude, runtime
    for mod in (runtime, claude):
        mod.register(STEPS)


_register_step_modules()


def default_plugin_root() -> Path:
    """The plugin folder: two levels above wnc_install.py (installer/core/ -> plugin root)."""
    return Path(__file__).resolve().parents[3]


def _csv(text: str) -> list:
    return [x.strip() for x in text.split(",") if x.strip()]


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--home", help="sandbox home: everything (engine home, .claude, AppData) goes under it")
    common.add_argument("--plugin-root", help="plugin folder (default: two levels above wnc_install.py)")
    common.add_argument("--components", help="components.json (default: <plugin>/setup/components.json)")
    common.add_argument("--uv", help="uv binary the bootstrap installed")
    common.add_argument("--python", help="python-build-standalone interpreter the bootstrap installed")
    common.add_argument("--log", help="log file shared with the bootstrap (default: logs/<command>-<time>.log)")
    common.add_argument("--dry-run", action="store_true", help="say what would happen; write nothing")
    common.add_argument("--yes", "-y", action="store_true", help="no questions: take the defaults")
    common.add_argument("--skip", type=_csv, default=[], help="comma-separated step names to skip")
    common.add_argument("--clients-folder", help="folder that holds the client folders")
    common.add_argument("--language", choices=("ar", "en"))
    common.add_argument("--channel", choices=("stable", "beta"))
    common.add_argument("--quiet", action="store_true", help="log file only, no console lines")
    p = argparse.ArgumentParser(prog="wnc_install", description="WhyNot Cut per-user installer core")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("install", parents=[common], help="install or repair WhyNot Cut for this user")
    un = sub.add_parser("uninstall", parents=[common], help="remove WhyNot Cut for this user")
    un.add_argument("--remove-engine", action="store_true", help="also delete the engine home (runtimes, ffmpeg...)")
    un.add_argument("--remove-models", action="store_true", help="also delete the Whisper models (~3 GB each)")
    sub.add_parser("plan", parents=[common], help="print the ordered step list as JSON")
    return p


def ordered(steps: list) -> list:
    """Registered install steps in STEP_ORDER; an unknown name is a programming error."""
    for name, _fn, _needs in steps:
        if name not in STEP_ORDER:
            raise ValueError(f"unknown install step {name!r}")
    return sorted(steps, key=lambda s: STEP_ORDER.index(s[0]))


def _utf8_console() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass


def main(argv=None) -> int:
    _utf8_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    unknown = [s for s in args.skip if s not in STEP_ORDER]
    if unknown:
        parser.error(f"--skip: unknown step(s) {', '.join(unknown)}; steps are {', '.join(STEP_ORDER)}")
    plugin_root = Path(args.plugin_root).resolve() if args.plugin_root else default_plugin_root()
    paths = base.Paths.from_env(args.home)

    if args.command == "plan":
        try:
            plat = base.platform_id(sandbox=paths.sandbox)
        except base.Unsupported:
            plat = None
        print(json.dumps({"steps": list(STEP_ORDER), "registered": [n for n, _f, _d in ordered(STEPS)],
                          "uninstall": [n for n, _f, _d in UNINSTALL_STEPS], "skip": args.skip, "platform": plat,
                          "engine_home": str(paths.whynot), "sandbox": paths.sandbox}, ensure_ascii=False, indent=2))
        return 0

    try:
        plat = base.platform_id(sandbox=paths.sandbox)
    except base.Unsupported as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    comp_path = Path(args.components) if args.components else plugin_root / "setup" / "components.json"
    try:
        components = base.load_components(comp_path)
    except (OSError, ValueError) as e:
        print(f"ERROR: cannot read {comp_path}: {e}", file=sys.stderr)
        return 2
    if args.channel is None:
        args.channel = components.get("channel", "stable")

    log_path = Path(args.log) if args.log else (None if args.dry_run else
                                               paths.logs_dir / f"{args.command}-{base.stamp()}.log")
    log = base.Log(log_path, args.dry_run, console=not args.quiet)
    try:
        state = base.State(paths, dry_run=args.dry_run).load()
    except OSError as e:  # locked / unreadable, not corrupt: never rename or overwrite it, stop instead
        log.error(f"cannot read {paths.state_file}: {e}. Close any program using it (antivirus, editor) and run "
                  "the installer again.")
        return 2
    if state.set_aside:
        log.warn(f"state.json was unreadable; kept it as {state.set_aside.name} and started fresh")
    ctx = base.Ctx(paths=paths, log=log, components=components, state=state, plugin_root=plugin_root,
                   platform=plat, args=args)
    log.info(f"WhyNot Cut {components.get('plugin')} {args.command} on {plat}; engine home {paths.whynot}"
             + (" (sandbox)" if paths.sandbox else "") + (" (dry run: nothing is written)" if args.dry_run else ""))
    steps = ordered(STEPS) if args.command == "install" else list(UNINSTALL_STEPS)
    results = base.run_steps(ctx, steps)
    red = [r.name for r in results if r.status == "red"]
    log.info(f"{args.command} finished: " + (", ".join(f"{r.name} {r.status}" for r in results) or "no steps"))
    if log.path:
        log.info(f"log: {log.path}")
    return 1 if red else 0
