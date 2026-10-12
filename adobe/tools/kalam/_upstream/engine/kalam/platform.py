"""What differs between macOS and Windows: which speech backend runs, and where Claude Code lives."""
import importlib.util
import os
import sys
from pathlib import Path


def is_windows() -> bool:
    return sys.platform == "win32"


def backend() -> str:
    """"mlx" on a Mac with MLX installed, else "portable" (faster-whisper / ONNX / torch). KALAM_BACKEND overrides."""
    forced = os.environ.get("KALAM_BACKEND")
    if forced in ("mlx", "portable"):
        return forced
    if sys.platform == "darwin" and importlib.util.find_spec("mlx_whisper") is not None:
        return "mlx"
    return "portable"


def claude_candidates(env: dict, home: Path, windows: bool) -> list:
    """places the Claude Code CLI is installed by its native installer, npm or Homebrew"""
    if windows:
        out = [str(home / ".local" / "bin" / "claude.exe")]
        if env.get("APPDATA"):
            out.append(str(Path(env["APPDATA"]) / "npm" / "claude.cmd"))
        return out
    return [str(home / ".local" / "bin" / "claude"), "/opt/homebrew/bin/claude", "/usr/local/bin/claude"]
