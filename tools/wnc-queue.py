"""Entry point of the wnc-queue CLI and runner (docs/dev/wnc-queue.md). Stdlib only: run it with the system Python 3,
never the engine runtime (the scheduled task pins the interpreter that ran `install`)."""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wnc_queue.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
