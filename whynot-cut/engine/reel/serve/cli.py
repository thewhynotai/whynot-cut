"""`reel serve` on the command line (3.0 T6.2): --ensure | --status (default) | --stop | --foreground.

Two entries share this module:
  * the `reel` CLI (engine/reel/cli.py) registers the subcommand with `add_args(sp)` on its subparser (or
    `build_parser(subparsers)`) and runs `cmd_serve(a)`; `serve` needs no client folder and takes no writer lock;
  * `python -m serve` / `python -P <plugin>/engine/reel/serve/__main__.py` call `main(argv)` (the detached daemon is
    started this way, so it does not depend on cli.py).
--ensure / --status / --stop print one JSON document (lib.errors.emit: a failure exits 1); --quiet prints nothing and
then always exits 0 (the SessionStart hook). --foreground prints a `running` line when it serves and a closing
document, and exits with the daemon's own code whatever --quiet says: 0, 1 (could not start) or 3 (EXIT_LOCKED: another
daemon holds this engine home; ensure() turns that into its "not answering" guidance). The token is never printed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

__all__ = ["HELP", "add_args", "build_parser", "cmd_serve", "main"]

HELP = ("the local engine daemon the Premiere panel talks to: --ensure (start once, idempotent) | --status | --stop "
        "| --foreground")


def add_args(sp) -> None:
    """The `reel serve` options on an existing (sub)parser."""
    from .daemon import ENSURE_WAIT
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--ensure", action="store_true",
                   help="start the daemon in the background unless one already answers (idempotent)")
    g.add_argument("--status", action="store_true", help="is it running, on which port, how many sessions (default)")
    g.add_argument("--stop", action="store_true", help="ask the running daemon to exit (authenticated)")
    g.add_argument("--foreground", action="store_true", help="run the daemon in this process until it is stopped")
    sp.add_argument("--wait", type=float, default=None,
                    help=f"with --ensure: seconds to wait for a new daemon to answer (default {ENSURE_WAIT:g})")
    sp.add_argument("--quiet", action="store_true", help="print nothing and always exit 0 (for hooks)")
    sp.add_argument("--home", default=None, help=argparse.SUPPRESS)      # tests: a temp engine home


def build_parser(subparsers):
    """Register `serve` on an argparse subparsers object; returns its parser."""
    sp = subparsers.add_parser("serve", help=HELP, description=HELP)
    add_args(sp)
    return sp


def _announce(home):
    def ready(_stop) -> None:
        from .security import read_engine_json
        info = read_engine_json(home) or {}
        print(json.dumps({"ok": True, "running": True, "state": "running", "pid": info.get("pid"),
                          "port": info.get("port"), "version": info.get("version")}), flush=True)
    return ready


def cmd_serve(a) -> None:
    """Run `reel serve` for a parsed namespace (the reel CLI's or main()'s)."""
    from lib.errors import emit
    from lib.plat import engine_home

    from . import daemon
    home = Path(a.home).expanduser() if getattr(a, "home", None) else engine_home()
    quiet = bool(getattr(a, "quiet", False))
    try:
        if getattr(a, "foreground", False):
            code = daemon.run(home, ready=None if quiet else _announce(home))
            if code == daemon.EXIT_OK:
                doc = {"ok": True, "running": False, "state": "stopped"}
            elif code == daemon.EXIT_LOCKED:
                doc = {"ok": False, "running": False, "state": "refused",
                       "error": "another reel serve already serves this engine home",
                       "how": "reel serve --status shows it; reel serve --stop stops it"}
            else:
                doc = {"ok": False, "running": False, "state": "failed", "error": "reel serve could not start",
                       "how": f"see {home / 'logs' / 'serve-audit.log'}, then run: reel doctor"}
            if not quiet:                  # not emit(): it maps every failure to 1, and ensure() reads EXIT_LOCKED
                print(json.dumps(doc, ensure_ascii=False, indent=2), flush=True)
            if code != daemon.EXIT_OK:
                raise SystemExit(code)
            return
        elif getattr(a, "stop", False):
            doc = daemon.stop(home)
        elif getattr(a, "ensure", False):
            wait = getattr(a, "wait", None)
            doc = daemon.ensure(home, wait=daemon.ENSURE_WAIT if wait is None else wait)
        else:
            doc = daemon.status(home)
    except Exception:              # noqa: BLE001 — a hook must never fail the session start
        if quiet:
            return
        raise
    if not quiet:
        emit(doc)


def main(argv=None) -> int:
    """`python -m serve [--ensure|--status|--stop|--foreground] [--wait S] [--quiet]`; returns the exit code."""
    ap = argparse.ArgumentParser(prog="reel serve", description=HELP)
    add_args(ap)
    a = ap.parse_args(sys.argv[1:] if argv is None else list(argv))
    try:
        cmd_serve(a)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return 0
