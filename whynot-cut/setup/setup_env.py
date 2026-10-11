#!/usr/bin/env python3
"""Machine setup and repair of the WhyNot Cut engine runtime (macOS and Windows). Idempotent; safe to run again.

Builds an isolated runtime in the engine home (default ~/.whynot-cut) from this plugin's hash lock
(setup/locks/runtime-<platform>.lock), side by side with any older runtime or the 2.x venv/, and switches
<home>/current to it only after a smoke import passes (3.0 T2.1; layout and stamps: engine/reel/lib/runtime.py).
Never touches system Python, the user site-packages, Homebrew, the Windows registry or Adobe preferences, and never
deletes the 2.x venv/ or an older runtime (kept for rollback).

How: the pinned uv (<home>/bin/uv, downloaded from components.json with its sha256 when missing) installs the pinned
python-build-standalone 3.12 into <home>/python, `uv venv`, then `uv pip sync --require-hashes <lock>`. Without uv:
a system Python 3.12 (`py -3.12` / python3.12) makes the venv and pip installs the lock with --require-hashes.

Repair: when the runtime exists, its packages are compared with the lock (and the lock's sha256 with the one stamped
in the runtime); any difference -> re-sync from the lock.

    python setup/setup_env.py            # build or repair the runtime, then report
    python setup/setup_env.py --check    # report what would be done, change nothing
    python setup/setup_env.py --force    # re-sync from the lock even when everything matches
    python setup/setup_env.py --home D:/whynot-engine

Prints one JSON report on stdout (progress goes to stderr); exit 0 = ready, 1 = not ready.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
sys.path.insert(0, str(PLUGIN / "engine" / "reel" / "lib"))
import plat  # noqa: E402  (stdlib only)
import runtime as R  # noqa: E402  (stdlib only)

BUILD_LOCK_STALE_S = 2 * 3600


def say(msg: str):
    print(f"[whynot-cut setup] {msg}", file=sys.stderr, flush=True)


class Failed(Exception):
    def __init__(self, msg: str, how: str = "", detail: str = ""):
        super().__init__(msg)
        self.how, self.detail = how, detail


def run(cmd, env=None):
    """Run a setup step; output is kept and its tail reported when the step fails."""
    say("$ " + " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], env=env, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        raise Failed(f"setup step failed (exit {r.returncode}): {Path(str(cmd[0])).name} {' '.join(map(str, cmd[1:3]))}",
                     detail=((r.stderr or "") + (r.stdout or ""))[-3000:])
    return r


# --------------------------------------------------------------------------- uv
def uv_path(home: Path) -> Path:
    return home / "bin" / ("uv.exe" if plat.IS_WIN else "uv")


def uv_env(home: Path) -> dict:
    env = dict(os.environ)
    env.update(UV_PYTHON_INSTALL_DIR=str(home / "python"), UV_CACHE_DIR=str(home / "cache" / "uv"),
               UV_HTTP_TIMEOUT="60", UV_HTTP_RETRIES="5", UV_NO_CONFIG="1")
    return env


def _fetch(url: str, timeout=60, retries=5) -> bytes:
    import urllib.request
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except OSError as e:
            last = e
            time.sleep(min(2 ** i, 10))
    raise Failed(f"download failed: {url}", how="check the internet connection, then run reel setup again",
                 detail=str(last))


def download_uv(asset: dict, dest: Path, fetch=_fetch) -> Path:
    """The pinned uv release (components.json uv.assets.<platform>): sha256-checked, only the `member` extracted."""
    data = fetch(asset["url"])
    got = hashlib.sha256(data).hexdigest()
    if got != asset.get("sha256"):
        raise Failed("the downloaded uv does not match its pinned sha256", how="run reel setup again",
                     detail=f"{asset['url']}: {got}")
    if asset.get("archive") == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            body = z.read(asset["member"])
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
            f = t.extractfile(asset["member"])
            if f is None:
                raise Failed(f"uv archive has no {asset['member']}")
            body = f.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + f".{os.getpid()}.tmp")
    tmp.write_bytes(body)
    tmp.chmod(0o755)
    os.replace(tmp, dest)
    return dest


def find_uv(home: Path, comp: dict, key: str | None, allow_download=True) -> tuple[Path | None, str | None]:
    """(uv, note): <home>/bin/uv, else the pinned release downloaded there, else a uv on PATH (noted), else None."""
    p = uv_path(home)
    if p.is_file():
        return p, None
    asset = ((comp.get("uv") or {}).get("assets") or {}).get(key or "")
    if allow_download and asset:
        try:
            say(f"downloading uv {(comp.get('uv') or {}).get('version')} into {p.parent}")
            return download_uv(asset, p), None
        except Failed as e:
            note = f"pinned uv not downloaded ({e})"
    else:
        note = None
    w = shutil.which("uv")
    if w:
        return Path(w), (note + "; " if note else "") + "using the uv on PATH (not the pinned version)"
    return None, note


def find_python312() -> Path | None:
    """A system Python 3.12 for the no-uv path (the lock is compiled for 3.12)."""
    if sys.version_info[:2] == (3, 12):
        return Path(sys.executable)
    cands = [["py", "-3.12"]] if plat.IS_WIN else [["python3.12"]]
    for c in cands:
        if shutil.which(c[0]):
            r = subprocess.run(c + ["-c", "import sys; print(sys.executable)"], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                return Path(r.stdout.strip().splitlines()[-1])
    return None


# --------------------------------------------------------------------------- build / repair
class BuildLock:
    """<home>/runtimes/.<id>.building, created exclusively: two setups never build the same runtime at once (one
    older than BUILD_LOCK_STALE_S is a crashed run and is taken over)."""

    def __init__(self, path: Path):
        self.path = path

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > BUILD_LOCK_STALE_S:
                        self.path.unlink()
                        continue
                except OSError:
                    continue
                raise Failed("another WhyNot Cut setup is building this runtime right now",
                             how="wait for it to finish, then run reel setup again")
        raise Failed("could not take the runtime build lock", how="run reel setup again")

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except OSError:
            pass


def build(home: Path, *, comp: dict, key: str | None, lock_file: Path, rid: str, by: str = "reel setup",
          check=False, force=False, dev_system_site=False, uv: Path | None = None, runner=run,
          versions=R.installed_versions, smoke: list[str] | None = None, base_python=find_python312,
          probe=R.python_runs, prune=True) -> dict:
    """Create or repair runtimes/<rid> from `lock_file`, smoke-import, stamp, then switch `current` and prune old
    runtimes (current + one previous are kept). Raises Failed; `current` changes only after everything passed.
    A runtime folder whose python is missing or does not start (its base Python removed) is rebuilt in place
    (`uv venv --clear` / `venv --clear`); the stamps are removed before any install and written last, so an
    unfinished or failed install never looks built."""
    lock_bytes = lock_file.read_bytes()
    lock = R.parse_lock(lock_bytes.decode("utf-8"))
    sha = R.lock_sha256(lock_bytes)
    rt = R.runtime_dir(home, rid)
    py = plat.env_python(rt)
    exists = py.is_file() and probe(py)
    broken = rt.exists() and not exists
    stamp = R.read_stamp(rt)
    dec = R.repair_decision(lock, versions(py) if exists else None, exists=exists, stamp_sha=stamp["lock_sha256"],
                            lock_sha=sha)
    if broken:
        dec["reasons"] = ["the runtime folder has no working python: rebuilt in place"]
    if force and dec["action"] == "none":
        dec = {"action": "sync", "reasons": ["--force"]}
    pyver = str((comp.get("runtime") or {}).get("python") or R.DEFAULT_PYTHON)
    previous = plat.current_runtime_id(home)
    rep = {"id": rid, "dir": str(rt), "python": str(py), "platform": key, "lock_file": str(lock_file),
           "lock_sha256": sha, "action": dec["action"], "reasons": dec["reasons"], "previous": previous,
           "via": "uv" if uv else "pip"}
    if check:
        rep["current"] = previous
        rep["would_switch"] = previous != rid
        return rep
    env = uv_env(home) if uv else None
    with BuildLock(R.runtimes_dir(home) / f".{rid}.building"):
        if dec["action"] in ("create", "sync") and rt.exists():
            R.clear_stamps(rt)
        clear = ["--clear"] if broken else []
        if dec["action"] == "create":
            if uv:
                say(f"installing Python {pyver} into {home / 'python'}")
                runner([uv, "python", "install", pyver, "--no-bin", "--no-registry"], env=env)
                runner([uv, "venv", "--python", pyver, "--python-preference", "only-managed", *clear,
                        *(["--system-site-packages"] if dev_system_site else []), rt], env=env)
            else:
                base = base_python()
                if not base:
                    raise Failed("no uv and no Python 3.12 to build the engine runtime",
                                 how="check the internet connection (setup downloads uv), then run reel setup again")
                runner([base, "-m", "venv", *clear, *(["--system-site-packages"] if dev_system_site else []), rt])
        if dec["action"] in ("create", "sync"):
            say(f"installing the locked packages into {rt} (first time: a few minutes, ~400 MB)")
            idx = (comp.get("runtime") or {}).get("index_url")
            idx = ["--index-url", idx] if isinstance(idx, str) and idx and not idx.startswith("<") else []
            if uv:
                verb = ["install", "--reinstall"] if dev_system_site else ["sync"]
                runner([uv, "pip", *verb, "--require-hashes", "--python", py, *idx, lock_file], env=env)
            else:
                runner([py, "-m", "pip", "install", "--disable-pip-version-check", "--require-hashes", "--no-deps",
                        "--timeout", "60", "--retries", "5", *(["--ignore-installed"] if dev_system_site else []),
                        *idx, "-r", lock_file])
            after = R.repair_decision(lock, versions(py), exists=py.is_file(), stamp_sha=sha, lock_sha=sha)
            if after["action"] != "none":
                raise Failed("the runtime still differs from the lock after installing",
                             how="run reel setup again; if it repeats, run reel doctor and send the report",
                             detail="; ".join(after["reasons"]))
        smoke = smoke if smoke is not None else ((comp.get("runtime") or {}).get("smoke") or R.DEFAULT_SMOKE)
        try:
            runner([py, "-s", "-c", "import " + ", ".join(smoke)])
        except Failed as e:
            raise Failed(f"the new runtime failed its smoke import ({', '.join(smoke)}); {home / 'current'} "
                         "was not changed", how="run reel setup again; reel doctor shows which module fails",
                         detail=e.detail) from None
        if dec["action"] != "none" or stamp["lock_sha256"] != sha or not stamp["runtime"]:     # written last
            R.write_stamps(rt, rid=rid, key=key, python=pyver, lock_file=lock_file.relative_to(PLUGIN).as_posix()
                           if lock_file.is_relative_to(PLUGIN) else str(lock_file), lock_sha=sha, by=by)
        if previous != rid:
            R.write_current(home, rid)
    rep["current"] = rid
    rep["switched"] = previous != rid
    if prune:
        rep["pruned"] = R.prune(home, keep_runtimes(home, rid, previous))
    return rep


def keep_runtimes(home: Path, rid: str, previous: str | None) -> set[str]:
    """Current + one previous for rollback: the runtime `current` named before this setup, else the newest other."""
    if previous and previous != rid:
        return {rid, previous}
    d = R.runtimes_dir(home)
    others = sorted((p for p in d.iterdir() if p.is_dir() and p.name != rid and not p.name.startswith(".")
                     and not p.name.endswith(".building") and (p / "pyvenv.cfg").is_file()),
                    key=lambda p: p.stat().st_mtime, reverse=True) if d.is_dir() else []
    return {rid} | ({others[0].name} if others else set())


def check_modules(py: Path) -> dict:
    mods = R.engine_modules()
    code = ("import json,importlib\nr={}\nfor m in %r:\n    try:\n        importlib.import_module(m); r[m]=True\n"
            "    except Exception as e:\n        r[m]='missing (%%s)' %% type(e).__name__\nprint(json.dumps(r))") % mods
    try:
        out = subprocess.run([str(py), "-s", "-c", code], capture_output=True, text=True, timeout=300)
        return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception as e:  # noqa: BLE001
        return {"_error": f"{type(e).__name__}: {e}"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", help="engine home (default: ~/.whynot-cut, or an existing legacy home)")
    ap.add_argument("--check", action="store_true", help="report what would be done; change nothing")
    ap.add_argument("--force", "--upgrade", dest="force", action="store_true",
                    help="re-sync the runtime from the lock even when it matches")
    ap.add_argument("--no-download", action="store_true", help="never download uv (use <home>/bin/uv or PATH)")
    ap.add_argument("--uv", help=argparse.SUPPRESS)                       # dev/tests: a specific uv binary
    ap.add_argument("--by", default="reel setup", help=argparse.SUPPRESS)  # WHYNOT_RUNTIME "by" (installer)
    # dev only (hidden): a runtime that may see the system site-packages, installed with --ignore-installed /
    # --reinstall so every locked package still lands inside the runtime
    ap.add_argument("--system-site-packages", dest="dev_system_site", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    home = Path(a.home).expanduser() if a.home else plat.engine_home()
    key = R.platform_key()
    comp = R.components()
    rep = {"os": plat.describe(), "engine_home": str(home), "setup_python": sys.executable, "platform": key}
    if sys.version_info < (3, 9):
        rep.update(ok=False, error=f"Python {sys.version.split()[0]} is too old to run the setup",
                   how=("winget install Python.Python.3.12" if plat.IS_WIN else "xcode-select --install"))
        print(json.dumps(rep, indent=2))
        return 1
    ent = R.lock_entry(key, comp)
    try:
        if not ent["file"].is_file():
            raise Failed(f"this plugin ships no runtime lock for {key or 'this platform'} ({ent['file'].name})",
                         how="WhyNot Cut runs on Windows x64 and macOS (Apple Silicon or Intel)")
        rid = R.runtime_id(ent["file"].read_bytes(), ent["declared_id"])
        if a.uv:
            uv, note = Path(a.uv), None
        else:
            uv, note = find_uv(home, comp, key, allow_download=not (a.no_download or a.check))
        if note:
            rep["uv_note"] = note
        if not a.check:
            home.mkdir(parents=True, exist_ok=True)
            (home / "models").mkdir(exist_ok=True)
        rep["runtime"] = build(home, comp=comp, key=key, lock_file=ent["file"], rid=rid, by=a.by, check=a.check,
                               force=a.force, dev_system_site=a.dev_system_site, uv=uv)
    except Failed as e:
        rep.update(error=str(e), how=e.how or "run reel setup again")
        if e.detail:
            rep["detail"] = e.detail
    except (OSError, ValueError) as e:
        rep.update(error=f"{type(e).__name__}: {e}", how="run reel setup again; if it repeats, send this report")
    eng = plat.engine_runtime(home)
    py = eng["python"]
    rep["engine"] = {"kind": eng["kind"], "id": eng["id"], "python": str(py) if py else None}
    rep["venv_python"] = str(py) if py else None                 # 2.x report key: the engine interpreter
    rep["python_modules"] = check_modules(py) if py else {}
    ff = plat.engine_ffmpeg(home)
    if not ff and py:
        r = subprocess.run([str(py), "-s", "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
                           capture_output=True, text=True)
        ff = r.stdout.strip() or None
    rep["ffmpeg"] = str(ff) if ff else shutil.which("ffmpeg")
    rep["adobe_apps"] = [f"{x['name']}" for x in plat.find_adobe_apps()]
    mods_ok = bool(rep["python_modules"]) and all(v is True for v in rep["python_modules"].values())
    rt = rep.get("runtime") or {}
    built = eng["kind"] == "runtime" and eng["id"] == rt.get("id") and (not a.check or rt.get("action") == "none")
    rep["ok"] = "error" not in rep and built and mods_ok
    rep["next"] = ("reel setup   (installs the Premiere bridge and reports the environment)" if rep["ok"] else
                   "reel setup   (builds or repairs the runtime)" if a.check else
                   "fix the items above, then run this again")
    rep["note"] = "Whisper large-v3 (~3 GB) downloads to <engine home>/models on the first transcription."
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
