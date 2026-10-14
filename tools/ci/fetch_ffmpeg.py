#!/usr/bin/env python3
"""Put the product's pinned ffmpeg + ffprobe into an engine home, the way the installer does (G-T13, CI only).

    python3 tools/ci/fetch_ffmpeg.py <components.json> <platform> <engine home>      e.g. mac-arm64 ~/.whynot-cut

Reads components.json `ffmpeg` (version + per-platform files: url, sha256, bytes, archive, members), downloads each
file, refuses it unless its size and sha256 match the pin, extracts the named members and installs them as
<engine home>/ffmpeg/<version>/<name> (mode 755) - the folder plat.engine_ffmpeg() looks in. Nothing goes on PATH.
Already there and runnable: nothing is downloaded (the workflow caches that folder). Exit 0 done, 1 failed.
Stdlib only, no Homebrew: the same static build a tester's Mac gets.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path


def runs(exe: Path) -> bool:
    try:
        return subprocess.run([str(exe), "-hide_banner", "-version"], capture_output=True, timeout=60,
                              stdin=subprocess.DEVNULL).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def download(url: str, dest: Path, tries: int = 3) -> None:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "whynot-cut-ci"})
            with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            return
        except OSError as e:  # URLError, timeouts, resets
            last = e
            time.sleep(3 * (i + 1))
    raise SystemExit(f"fetch_ffmpeg: cannot download {url}: {last}")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main(argv) -> int:
    if len(argv) != 4:
        print("usage: fetch_ffmpeg.py <components.json> <platform> <engine home>", file=sys.stderr)
        return 2
    comp = json.loads(Path(argv[1]).read_text(encoding="utf-8"))["ffmpeg"]
    ver, plat = comp["version"], argv[2]
    files = comp["assets"][plat]["files"]
    dest = Path(argv[3]).expanduser() / "ffmpeg" / ver
    names = [n for f in files for n in f["members"].values()]
    if all(runs(dest / n) for n in names):
        print(f"ffmpeg {ver} already in {dest}")
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wnc-ffmpeg-") as td:
        for f in files:
            if f.get("archive") != "zip":
                raise SystemExit(f"fetch_ffmpeg: archive type {f.get('archive')!r} is not handled here")
            arc = Path(td) / f["url"].rsplit("/", 1)[-1]
            download(f["url"], arc)
            size, digest = arc.stat().st_size, sha256(arc)
            if size != f["bytes"] or digest != f["sha256"]:
                raise SystemExit(f"fetch_ffmpeg: {f['url']} does not match the pin "
                                 f"(got {size} bytes, sha256 {digest})")
            with zipfile.ZipFile(arc) as z:
                for member, name in f["members"].items():
                    tmp = dest / (name + ".part")
                    with z.open(member) as src, open(tmp, "wb") as out:
                        shutil.copyfileobj(src, out, 1 << 20)
                    os.chmod(tmp, 0o755)
                    os.replace(tmp, dest / name)
    bad = [n for n in names if not runs(dest / n)]
    if bad:
        raise SystemExit(f"fetch_ffmpeg: {', '.join(bad)} in {dest} does not run on this machine")
    print(f"ffmpeg {ver} ({plat}) installed in {dest}: {', '.join(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
