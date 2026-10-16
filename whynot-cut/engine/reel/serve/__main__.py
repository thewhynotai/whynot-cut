"""`python -m serve` (with <plugin>/engine/reel on sys.path) or `python -P <plugin>/engine/reel/serve/__main__.py`: the
`reel serve` command line without cli.py. serve.daemon starts the detached daemon the second way. The start phases
"entry" (the first line here) and "imports" (serve.daemon and everything it pulls in, loaded) are marked for the
daemon's `startup` audit row (ms since this entry)."""
import time as _time

_T0 = _time.monotonic()                         # process entry: the daemon's start phases count from here
import sys  # noqa: E402

sys.dont_write_bytecode = True                  # keep the plugin folder free of __pycache__
if not __package__:                             # run as a file: engine/reel on sys.path, never this folder itself
    from pathlib import Path
    _here = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if not p or Path(p).resolve() != _here]
    sys.path.insert(0, str(_here.parent))

from serve import daemon as _daemon  # noqa: E402  (the heavy imports, timed)

_daemon.mark_phase("entry", _T0)
_daemon.mark_phase("imports")

from serve.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
