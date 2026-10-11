#!/usr/bin/env python3
"""One-time machine setup for WhyNot Cut (macOS and Windows). Idempotent; safe to run again.

Installs into an isolated venv in the engine home (default ~/.whynot-cut); never touches system Python, Homebrew,
the Windows registry or Adobe preferences. Run with any Python 3.9+:

    python setup/setup_env.py            # create/repair the venv and install pinned packages
    python setup/setup_env.py --check    # report only, install nothing
    python setup/setup_env.py --home D:/whynot-engine

Prints one JSON report on stdout (progress goes to stderr).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "engine" / "reel" / "lib"))
import plat  # noqa: E402  (stdlib only)

CORE_MODULES = ["faster_whisper", "ctranslate2", "av", "numpy", "PIL", "fontTools", "arabic_reshaper", "bidi",
                "uharfbuzz", "freetype", "pypdf", "imageio_ffmpeg"]
MAC_MODULES = ["CoreText", "Quartz", "Vision"]
OTHER_MODULES = ["cv2"]


def say(msg: str):
    print(f"[whynot-cut setup] {msg}", file=sys.stderr, flush=True)


def check_modules(py: Path) -> dict:
    mods = CORE_MODULES + (MAC_MODULES if plat.IS_MAC else OTHER_MODULES)
    code = ("import json,importlib\nr={}\nfor m in %r:\n    try:\n        importlib.import_module(m); r[m]=True\n"
            "    except Exception as e:\n        r[m]='missing (%%s)' %% type(e).__name__\nprint(json.dumps(r))") % mods
    try:
        out = subprocess.run([str(py), "-c", code], capture_output=True, text=True, timeout=300)
        return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception as e:  # noqa: BLE001
        return {"_error": f"{type(e).__name__}: {e}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", help="engine home (default: ~/.whynot-cut, or an existing legacy home)")
    ap.add_argument("--check", action="store_true", help="report only")
    ap.add_argument("--upgrade", action="store_true", help="re-install packages even if the venv looks complete")
    ap.add_argument("--system-site-packages", action="store_true",
                    help="let the venv reuse compatible packages already installed for this Python (pip then downloads "
                         "only what is missing or outside the pinned ranges; useful on slow connections)")
    a = ap.parse_args()
    home = Path(a.home).expanduser() if a.home else plat.engine_home()
    py = plat.venv_python(home)
    rep = {"os": plat.describe(), "engine_home": str(home), "venv_python": str(py), "setup_python": sys.executable}
    if sys.version_info < (3, 9):
        rep.update(ok=False, error=f"Python {sys.version.split()[0]} is too old; install Python 3.10-3.12",
                   how=("winget install Python.Python.3.12" if plat.IS_WIN else "xcode-select --install  (or python.org)"))
        print(json.dumps(rep, indent=2))
        sys.exit(1)
    if sys.version_info >= (3, 14):
        rep["warning"] = "Python 3.14+ may lack wheels for some packages; 3.10-3.12 is the safest choice."
    if not a.check:
        home.mkdir(parents=True, exist_ok=True)
        (home / "models").mkdir(exist_ok=True)
        if not py.exists():
            say(f"creating venv in {home / 'venv'}")
            subprocess.run([sys.executable, "-m", "venv", str(home / "venv")]
                           + (["--system-site-packages"] if a.system_site_packages else []), check=True)
        mods = check_modules(py)
        if a.upgrade or a.system_site_packages or not all(v is True for v in mods.values()):
            say("installing packages (first time: a few minutes, up to ~400 MB)")
            subprocess.run([str(py), "-m", "pip", "install", "-q", "--disable-pip-version-check", "--upgrade", "pip"],
                           check=False)
            r = subprocess.run([str(py), "-m", "pip", "install", "--disable-pip-version-check", "-q",
                                "-r", str(HERE / "requirements.txt")], capture_output=True, text=True)
            if r.returncode != 0:
                rep["pip_error"] = (r.stderr or r.stdout)[-3000:]
    rep["venv_ok"] = py.exists()
    rep["python_modules"] = check_modules(py) if py.exists() else {}
    ff = None
    if py.exists():
        r = subprocess.run([str(py), "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
                           capture_output=True, text=True)
        ff = r.stdout.strip() or None
        if ff and not a.check and not plat.IS_WIN:
            link = home / "ffmpeg"
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(ff)
    rep["ffmpeg"] = ff or shutil.which("ffmpeg")
    rep["adobe_apps"] = [f"{x['name']}" for x in plat.find_adobe_apps()]
    rep["ok"] = rep["venv_ok"] and bool(rep["python_modules"]) and all(v is True for v in rep["python_modules"].values())
    rep["next"] = ("reel setup   (installs the Premiere bridge and reports the environment)" if rep["ok"] else
                   "fix the items above, then run this again")
    rep["note"] = "Whisper large-v3 (~3 GB) downloads to <engine home>/models on the first transcription."
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    sys.exit(0 if rep["ok"] else 1)


if __name__ == "__main__":
    main()
