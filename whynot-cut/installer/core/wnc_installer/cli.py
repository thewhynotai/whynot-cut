"""wnc_install: install | uninstall | plan.

The bootstrap (install.ps1 / install.sh) has put uv and python-build-standalone in place and runs
    <engine python> -I -B installer/core/wnc_install.py install [--log <file>] [--yes] ...
Step modules append (name, fn, needs) to STEPS (install) or UNINSTALL_STEPS; `install` runs the registered steps in
STEP_ORDER, whatever order they were registered in; `uninstall` runs uninstall.py's steps (plugin, adobe, fonts,
marketplace, engine) with --remove-engine / --remove-models and prints its own checklist. `plan` prints the order as JSON and writes nothing.
Exit codes: 0 done (ok / amber / skipped), 1 at least one step red, 2 cannot start (platform, components.json) or
preflight is red (not enough free space: nothing was downloaded).
After the steps, install prints the checklist ([OK] / [!!] / [XX] per step and the doctor's fixes, also written to
logs/install-checklist.json) and how to start (/whynot-cut:start).
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
    from . import claude, runtime, system, uninstall
    for mod in (runtime, claude, system):
        mod.register(STEPS)
    uninstall.register_uninstall(UNINSTALL_STEPS)


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
    common.add_argument("--engine-home", help="the engine home the bootstrap uses: with --engine-home-chosen the "
                                              "folder the editor chose (it wins); without it, the folder the "
                                              "bootstrap resolved, which must be the core's own resolution (else "
                                              "the run stops with 2)")
    common.add_argument("--engine-home-chosen", action="store_true",
                        help="--engine-home was chosen by the editor (-EngineHome / --engine-home or the bootstrap's "
                             "location question), not resolved")
    common.add_argument("--model", choices=("large-v3", "large-v3-turbo", "medium", "small"),
                        help="the Whisper model to install (default: your saved preference, else large-v3)")
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


def _engine_home_problem(paths: base.Paths, plugin_root: Path, chosen) -> str:
    """A chosen engine home is checked like the bootstraps check it (base.engine_home_choice_problem: the clients
    folder from the preferences and the pointer counts); a sandbox's engine home must stay inside the sandbox."""
    if not chosen and not paths.sandbox:
        return ""
    from .system import read_preferences
    roots = [read_preferences(paths).get("clients_root")]
    ptr = base.read_pointer(paths.options_file)
    roots.append(ptr.get("clients_root") if ptr is not None else None)
    roots = [base.saved_path(r, paths.home) for r in roots if isinstance(r, str) and r.strip()]
    if not chosen:  # a sandbox's own pointer / settings.json named it: only the sandbox rule
        return "" if base._within(base._norm(paths.whynot), base._norm(paths.home), strict=True) else \
            f"it is outside the sandbox home {paths.home} (--home: nothing outside it is used)"
    return base.engine_home_choice_problem(str(chosen), home=paths.home, plugin_root=plugin_root,
                                           clients_roots=roots,
                                           sandbox_home=paths.home if paths.sandbox else None) or ""


def main(argv=None) -> int:
    _utf8_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    names = [n for n, _f, _d in UNINSTALL_STEPS] if args.command == "uninstall" else list(STEP_ORDER)
    unknown = [s for s in args.skip if s not in names]
    if unknown:
        parser.error(f"--skip: unknown step(s) {', '.join(unknown)}; steps are {', '.join(names)}")
    plugin_root = Path(args.plugin_root).resolve() if args.plugin_root else default_plugin_root()
    chosen = args.engine_home if args.engine_home and args.engine_home_chosen else None
    paths = base.Paths.from_env(args.home, engine_home=chosen)
    if args.engine_home and not chosen and base._norm(args.engine_home) != base._norm(paths.whynot):
        print(f"ERROR: the bootstrap placed uv and Python in {args.engine_home}, but the engine home is "
              f"{paths.whynot} ({base.describe_engine_home_source(paths.engine_home_source)}). Nothing was changed. "
              f"To fix it yourself, run the installer again with -EngineHome \"{paths.whynot}\" (macOS: --engine-home "
              f"\"{paths.whynot}\"), or name the other folder the same way; if it happens again, tell WhyNot Cut "
              "support (the two resolvers disagree).", file=sys.stderr)
        return 2
    problem = _engine_home_problem(paths, plugin_root, chosen)
    if problem:
        print(f"ERROR: WhyNot Cut cannot use {paths.whynot} as its engine home: {problem}. Nothing was changed; run "
              "the installer again with -EngineHome <folder> (macOS: --engine-home <folder>).", file=sys.stderr)
        return 2

    if args.command == "plan":
        try:
            plat = base.platform_id(sandbox=paths.sandbox)
        except base.Unsupported:
            plat = None
        print(json.dumps({"steps": list(STEP_ORDER), "registered": [n for n, _f, _d in ordered(STEPS)],
                          "uninstall": [n for n, _f, _d in UNINSTALL_STEPS], "skip": args.skip, "platform": plat,
                          "engine_home": str(paths.whynot), "engine_home_source": paths.engine_home_source,
                          "sandbox": paths.sandbox}, ensure_ascii=False, indent=2))
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
    log.info(f"WhyNot Cut {components.get('plugin')} {args.command} on {plat}; engine home {paths.whynot} "
             f"({base.describe_engine_home_source(paths.engine_home_source)})"
             + (" (dry run: nothing is written)" if args.dry_run else ""))
    if args.command == "install":
        return install(ctx)
    from . import uninstall
    results = uninstall.uninstall(ctx, args.remove_engine, args.remove_models)
    red = [r.name for r in results if r.status == "red"]
    log.info(f"{args.command} finished: " + (", ".join(f"{r.name} {r.status}" for r in results) or "no steps"))
    if log.path:
        log.info(f"log: {log.path}")
    return 1 if red else 0


def install(ctx: base.Ctx) -> int:
    """preflight first: red (too little free space) stops here with 2, before any download. Then every other step in
    STEP_ORDER, the checklist, and how to start. 0 when no step is red, else 1."""
    from . import system
    log, steps = ctx.log, ordered(STEPS)
    first = [s for s in steps if s[0] == "preflight"]
    results = base.run_steps(ctx, first)
    if any(r.status == "red" for r in results):
        log.error("preflight found a problem that stops the install (see above); nothing was downloaded")
        _finish(ctx, results, system)
        return 2
    results += base.run_steps(ctx, [s for s in steps if s[0] != "preflight"], {r.name: r.status for r in results})
    _finish(ctx, results, system)
    return 1 if any(r.status == "red" for r in results) else 0


def _finish(ctx: base.Ctx, results: list, system) -> None:
    log, doctor = ctx.log, ctx.facts.get("doctor")
    log.info("")
    log.info("WhyNot Cut install checklist:")
    for line in system.render_checklist(results, doctor).splitlines():
        log.info(line)
    if not ctx.args.dry_run:
        try:
            system.write_checklist(ctx.paths, results, doctor)
        except OSError as e:
            log.warn(f"could not write the checklist file: {e}")
    log.info("")
    log.info(system.START_MESSAGE)
    log.info(system.START_MESSAGE_AR)
    if ctx.platform.startswith("mac"):
        log.info(system.MAC_ALLOW_MESSAGE)
        log.info(system.MAC_ALLOW_MESSAGE_AR)
    if log.path:
        log.info(f"log: {log.path}")
