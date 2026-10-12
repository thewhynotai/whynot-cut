"""`python -m serve` (with <plugin>/engine/reel on sys.path) or `python -P <plugin>/engine/reel/serve/__main__.py`: the
`reel serve` command line without cli.py. serve.daemon starts the detached daemon the second way."""
import sys

sys.dont_write_bytecode = True                  # keep the plugin folder free of __pycache__
if not __package__:                             # run as a file: engine/reel on sys.path, never this folder itself
    from pathlib import Path
    _here = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if not p or Path(p).resolve() != _here]
    sys.path.insert(0, str(_here.parent))

from serve.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
