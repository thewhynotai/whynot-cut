"""Install steps `runtime`, `ffmpeg` and `gpu` (3.0 T7.1, installer.md R.1 runtime contract).

runtime  builds ~/.whynot-cut/runtimes/<id>/ IN PLACE from setup/locks/runtime-<platform>.lock, exactly like
         `reel setup` (T2.1): under the O_EXCL build lock runtimes/.<id>.building, the stamps removed first, `uv venv`
         (or a repair of a venv whose python works), `uv pip sync --require-hashes`, the smoke import, the stamps
         last, then `current` (atomic). A failed build leaves no stamps and `current` as it was.
ffmpeg   the pinned ffmpeg + ffprobe for this platform into ffmpeg/<version>/ with the GPL text and SOURCE.txt;
         extraction is staged in ffmpeg/<version>.staging so a crash never leaves a half-written binary in place.
gpu      Windows x64 with an NVIDIA GPU: `reel gpu-enable` (cuBLAS for Whisper) through the new runtime.
Stdlib only, like the rest of the core.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

from . import base

STAMP = "WHYNOT_RUNTIME"
LOCK_STAMP = ".whynot-lock.sha256"
_RID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")  # same rule as the engine (lib/plat.py)
_MODULE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
UV_VENV_TIMEOUT, PIP_SYNC_TIMEOUT, SMOKE_TIMEOUT, GPU_TIMEOUT = 300, 3600, 120, 1800
BUILD_LOCK_STALE_S = 2 * 3600  # same as setup/setup_env.py
GPL_TEXT = ("installer", "licenses", "GPL-3.0.txt")


# --------------------------------------------------------------------------------------------- helpers
def _check_rid(rid: str) -> str:
    if not isinstance(rid, str) or not _RID.match(rid) or ".." in rid:
        raise ValueError(f"not a runtime id: {rid!r}")
    return rid


# --------------------------------------------------------------------------------------------- runtime
def lock_rel(components: dict, platform: str) -> str:
    rel = base.cget(components, f"runtime.locks.{platform}.file")
    return rel if isinstance(rel, str) and rel and not base.is_placeholder(rel) else f"setup/locks/runtime-{platform}.lock"


def runtime_id(components: dict, platform: str, lock_path) -> str:
    """components `runtime.locks.<platform>.id`, or while that is a placeholder "r-" + sha256(lock bytes)[:12]."""
    declared = base.cget(components, f"runtime.locks.{platform}.id")
    if not base.is_placeholder(declared) and isinstance(declared, str) and declared.strip():
        return _check_rid(declared.strip())
    return "r-" + base.file_sha256(lock_path)[:12]


def runtime_python(paths: base.Paths, rid: str, platform: Optional[str] = None) -> Path:
    """The runtime's interpreter: the venv layout that exists (Scripts/python.exe or bin/python), else the one this
    platform's venvs use (`platform`, default this OS)."""
    d = paths.runtimes_dir / rid
    win, posix = d / "Scripts" / "python.exe", d / "bin" / "python"
    expect_win = platform.startswith("win") if platform else os.name == "nt"
    first, second = (win, posix) if expect_win else (posix, win)
    for p in (first, second):
        if p.is_file():
            return p
    return first


def current_runtime(paths: base.Paths) -> Optional[str]:
    """The id in `current`, or None when the file is missing, not an id, or names a runtime without its python."""
    try:
        rid = paths.current_file.read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeDecodeError):
        return None
    if not rid or not _RID.match(rid) or ".." in rid:
        return None
    return rid if runtime_python(paths, rid).is_file() else None


def uv_command(ctx: base.Ctx) -> list:
    """uv as a command list: WNC_TEST_UV (sandbox only; a .py runs on this interpreter), --uv, else bin/uv(.exe)."""
    test = os.environ.get("WNC_TEST_UV") if ctx.paths.sandbox else None
    if test:
        return [sys.executable, "-B", test] if test.lower().endswith(".py") else [test]
    if getattr(ctx.args, "uv", None):
        return [ctx.args.uv]
    return [str(ctx.paths.bin_dir / ("uv.exe" if ctx.platform.startswith("win") else "uv"))]


def _smoke(ctx: base.Ctx, py: Path, modules: list) -> tuple:
    return base.run_cmd(ctx, [py, "-s", "-c", "import " + ", ".join(modules)], SMOKE_TIMEOUT)


class BuildLock:
    """runtimes/.<id>.building, created with O_EXCL: the installer and `reel setup` (setup_env.BuildLock) never build
    the same runtime at once. A lock older than BUILD_LOCK_STALE_S is a crashed run and is taken over."""

    def __init__(self, path: Path):
        self.path = path
        self.held = False

    def acquire(self) -> bool:
        """True when taken; False when another process holds a fresh lock."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime <= BUILD_LOCK_STALE_S:
                        return False
                    self.path.unlink()  # stale: a crashed run
                except FileNotFoundError:
                    pass  # released meanwhile: try again
                except OSError:
                    return False
                continue
            try:
                os.write(fd, f"{os.getpid()} {base.now_iso()} installer\n".encode("utf-8"))
            finally:
                os.close(fd)
            self.held = True
            return True
        return False

    def release(self) -> None:
        if self.held:
            self.held = False
            try:
                self.path.unlink()
            except OSError:
                pass


def _base_python(ctx: base.Ctx, uv: list) -> tuple:
    """(interpreter, error): --python from the bootstrap, else the uv-managed python of components runtime.python
    (installed with --no-bin --no-registry when missing; a system Python is never picked)."""
    if getattr(ctx.args, "python", None):
        return ctx.args.python, None
    ver = str(base.cget(ctx.components, "runtime.python") or "3.12")
    find = uv + ["python", "find", ver, "--python-preference", "only-managed"]
    rc, out = base.run_cmd(ctx, find, 60, split=True)
    if rc != 0:
        rc, inst = base.run_cmd(ctx, uv + ["python", "install", ver, "--no-bin", "--no-registry"], 1800)
        if rc != 0:
            return None, f"uv could not install Python {ver}: {base.tail(inst)}"
        rc, out = base.run_cmd(ctx, find, 60, split=True)
    found = out.strip().splitlines()[-1].strip() if rc == 0 and out.strip() else ""
    if not found:
        return None, f"uv cannot find Python {ver} (exit {rc})"
    return found, None


def _clear_stamps(rdir: Path) -> None:
    for name in (STAMP, LOCK_STAMP):
        try:
            (rdir / name).unlink()
        except FileNotFoundError:
            pass


def step_runtime(ctx: base.Ctx) -> base.StepResult:
    paths, plat = ctx.paths, ctx.platform
    rel = lock_rel(ctx.components, plat)
    lock = ctx.plugin_root / rel
    if not lock.is_file():
        return base.StepResult("runtime", "skipped", f"no {rel} in this build (the runtime lock arrives with T2.1)")
    lock_sha = base.file_sha256(lock)
    rid = runtime_id(ctx.components, plat, lock)
    smoke = base.cget(ctx.components, "runtime.smoke") or []
    bad = [m for m in smoke if not isinstance(m, str) or not _MODULE.match(m)]
    if bad or not smoke:
        return base.StepResult("runtime", "red", f"components.json runtime.smoke is not a list of modules: {smoke!r}")
    rdir = paths.runtimes_dir / rid

    # already built from this lock (the stamps are written last) and still importing: nothing to do, no uv call
    py = runtime_python(paths, rid, plat)
    try:
        stamped = (rdir / LOCK_STAMP).read_text(encoding="utf-8").strip() == lock_sha
    except OSError:
        stamped = False
    if stamped and py.is_file() and ctx.args.dry_run:  # a dry run starts no process, not even the smoke import
        return base.StepResult("runtime", "skipped", f"dry run: would check runtime {rid} (built from {rel})")
    if stamped and py.is_file():
        rc, out = _smoke(ctx, py, smoke)
        if rc == 0:
            if current_runtime(paths) != rid and not ctx.args.dry_run:
                base.atomic_write_text(paths.current_file, rid + "\n")
            return _runtime_ok(ctx, rid, py, lock_sha, f"runtime {rid} is installed")
        ctx.log.warn(f"runtime {rid} no longer imports ({base.tail(out)}); repairing it")
    if ctx.args.dry_run:
        return base.StepResult("runtime", "skipped", f"dry run: would build runtime {rid} from {rel}")

    build_lock = BuildLock(paths.runtimes_dir / f".{rid}.building")
    if not build_lock.acquire():
        return base.StepResult("runtime", "amber", "another WhyNot Cut setup is building this runtime; run the "
                                                   "installer again when it finishes")
    try:
        return _build_in_place(ctx, rid, rdir, rel, lock, lock_sha, smoke)
    finally:
        build_lock.release()


def _build_in_place(ctx: base.Ctx, rid: str, rdir: Path, rel: str, lock: Path, lock_sha: str,
                    smoke: list) -> base.StepResult:
    """Under the build lock: create or repair runtimes/<rid> in place, like `reel setup`. The stamps go first, so an
    unfinished build is never trusted; they come back last, after the smoke import; then `current` switches."""
    paths, plat = ctx.paths, ctx.platform

    def fail(msg: str) -> base.StepResult:
        return base.StepResult("runtime", "red", msg + "; the runtime in use was not changed")

    uv = uv_command(ctx)
    if rdir.is_dir():
        _clear_stamps(rdir)
    py = runtime_python(paths, rid, plat)
    repair = py.is_file() and base.run_cmd(ctx, [py, "-s", "-c", "pass"], SMOKE_TIMEOUT)[0] == 0
    if repair:
        ctx.log.info(f"runtime {rid} has a working python: re-syncing it from the lock")
    else:
        if os.path.lexists(rdir) and not base.safe_rmtree(rdir, [paths.runtimes_dir]):
            return fail(f"cannot clear the broken {rdir}")
        paths.runtimes_dir.mkdir(parents=True, exist_ok=True)
        base_py, err = _base_python(ctx, uv)
        if err:
            return fail(err)
        rc, out = base.run_cmd(ctx, uv + ["venv", rdir, "--python", base_py, "--python-preference", "only-managed"],
                          UV_VENV_TIMEOUT, cwd=paths.runtimes_dir)
        if rc != 0:
            return fail(f"uv venv failed (exit {rc}): {base.tail(out)}")
        py = runtime_python(paths, rid, plat)
        if not py.is_file():
            return fail(f"uv venv made no interpreter at {py}")
    sync = uv + ["pip", "sync", "--require-hashes", "--python", py]
    index = base.cget(ctx.components, "runtime.index_url")
    if not base.is_placeholder(index):
        sync += ["--index-url", index]
    rc, out = base.run_cmd(ctx, sync + [lock], PIP_SYNC_TIMEOUT, cwd=paths.runtimes_dir)
    if rc != 0:
        return fail(f"uv pip sync failed (exit {rc}): {base.tail(out)}")
    rc, out = _smoke(ctx, py, smoke)
    if rc != 0:
        return fail(f"the runtime cannot import {', '.join(smoke)}: {base.tail(out)}")
    rc, ver = base.run_cmd(ctx, [py, "-s", "-c", "import platform; print(platform.python_version())"], SMOKE_TIMEOUT)
    stamp_obj = {"id": rid, "platform": plat, "python": base.tail(ver) if rc == 0 else "", "lock_file": rel,
                 "lock_sha256": lock_sha, "created_at": base.now_iso(), "by": "installer"}
    base.atomic_write_json(rdir / STAMP, stamp_obj)
    base.atomic_write_text(rdir / LOCK_STAMP, lock_sha + "\n")
    base.atomic_write_text(paths.current_file, rid + "\n")
    return _runtime_ok(ctx, rid, py, lock_sha, f"runtime {rid} {'repaired' if repair else 'built'} from {rel}")


def _runtime_ok(ctx: base.Ctx, rid: str, py: Path, lock_sha: str, detail: str) -> base.StepResult:
    ctx.runtime_python = py
    ctx.state.data["runtime"] = {"id": rid, "python": str(py), "lock_sha256": lock_sha}
    ctx.state.record("runtime", "ok", lock_sha, detail)
    return base.StepResult("runtime", "ok", detail)


# --------------------------------------------------------------------------------------------- ffmpeg
def _ffmpeg_fingerprint(ver: str, files: list) -> str:
    raw = json.dumps({"version": ver, "files": [[f.get("url"), f.get("sha256"), f.get("members")] for f in files]},
                     sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def step_ffmpeg(ctx: base.Ctx) -> base.StepResult:
    paths, plat, c = ctx.paths, ctx.platform, ctx.components
    ver, source = base.cget(c, "ffmpeg.version"), base.cget(c, "ffmpeg.source")
    files = base.cget(c, f"ffmpeg.assets.{plat}.files")
    pinned = isinstance(files, list) and files and all(
        isinstance(f, dict) and isinstance(f.get("members"), dict) and f["members"]
        and not base.is_placeholder(f.get("url")) and not base.is_placeholder(f.get("sha256")) for f in files)
    if base.is_placeholder(ver) or base.is_placeholder(source) or not pinned:
        return base.StepResult("ffmpeg", "skipped", f"ffmpeg for {plat} is not in this build (placeholder pin)")
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", str(ver)) or ".." in str(ver):
        return base.StepResult("ffmpeg", "red", f"components.json ffmpeg.version is not a version: {ver!r}")
    exe = ".exe" if plat.startswith("win") else ""
    names = (f"ffmpeg{exe}", f"ffprobe{exe}")
    dest = paths.ffmpeg_dir / ver
    fp = _ffmpeg_fingerprint(ver, files)

    # already installed from these pins, and the binary is still the one recorded: no download
    rec = ctx.state.data.get("ffmpeg")
    main = dest / names[0]
    if (ctx.state.step_done("ffmpeg", fp) and isinstance(rec, dict) and all((dest / n).is_file() for n in names)
            and rec.get("sha256") == base.file_sha256(main)):
        return base.StepResult("ffmpeg", "ok", f"ffmpeg {ver} is installed")
    lic = ctx.plugin_root.joinpath(*GPL_TEXT)
    if not lic.is_file():
        return base.StepResult("ffmpeg", "red", f"the plugin lacks {'/'.join(GPL_TEXT)}; ffmpeg is not installed "
                                                "without its licence")
    if ctx.args.dry_run:
        return base.StepResult("ffmpeg", "skipped", f"dry run: would install ffmpeg {ver} into {dest}")

    archives = []
    for f in files:
        leaf = str(f["url"]).rsplit("/", 1)[-1].split("?", 1)[0] or "ffmpeg.zip"
        try:
            archives.append(base.download(f["url"], f["sha256"], paths.downloads_dir, ctx.log,
                                          name=f"ffmpeg-{ver}-{plat}-{leaf}"))
        except base.DownloadError as e:
            return base.StepResult("ffmpeg", "red", str(e))

    staging = paths.ffmpeg_dir / f"{ver}.staging"
    roots = [paths.ffmpeg_dir]
    if not base.safe_rmtree(staging, roots):
        return base.StepResult("ffmpeg", "red", f"cannot clear the leftover {staging}")
    try:
        for f, archive in zip(files, archives):
            base.extract(archive, staging, f["members"])
        missing = [n for n in names if not (staging / n).is_file()]
        if missing:
            raise base.ExtractError(f"the archives gave no {', '.join(missing)}")
        shutil.copyfile(lic, staging / "LICENSE.GPL-3.0.txt")
        lines = [f"FFmpeg {ver} ({base.cget(c, 'ffmpeg.license') or 'GPL-3.0-or-later'})",
                 f"Corresponding source code: {source}", "", "Binaries installed by the WhyNot Cut installer from:"]
        for f in files:
            lines += [f"  {f['url']}", f"    sha256 {f['sha256']}"]
        base.atomic_write_text(staging / "SOURCE.txt", "\n".join(lines) + "\n")
        if os.name != "nt":
            for n in names:
                os.chmod(staging / n, 0o755)
        base.move_aside_and_replace(staging, dest, paths.ffmpeg_dir)
    except (OSError, base.ExtractError) as e:
        try:
            base.safe_rmtree(staging, roots)
        except OSError as e2:
            ctx.log.warn(f"could not remove {staging}: {e2}")
        return base.StepResult("ffmpeg", "red", f"ffmpeg {ver} could not be installed: {e}")
    ctx.state.data["ffmpeg"] = {"version": ver, "path": str(main), "sha256": base.file_sha256(main)}
    ctx.state.record("ffmpeg", "ok", fp, f"ffmpeg {ver}")
    return base.StepResult("ffmpeg", "ok", f"ffmpeg {ver} installed in {dest}")


# --------------------------------------------------------------------------------------------- gpu
def _nvidia_present(ctx: base.Ctx) -> bool:
    if ctx.paths.sandbox:  # never probe the real hardware from a test
        return os.environ.get("WNC_TEST_NVIDIA") == "1"
    smi = shutil.which("nvidia-smi")
    sys32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe"
    if not smi and sys32.is_file():
        smi = str(sys32)
    if not smi:
        return False
    rc, _out = base.run_cmd(ctx, [smi, "-L"], 30)
    return rc == 0


def step_gpu(ctx: base.Ctx) -> base.StepResult:
    if ctx.platform == "mac-arm64":
        return base.StepResult("gpu", "skipped", "nothing to install: MLX comes with the mac-arm64 lock")
    if ctx.platform != "win-x64":
        return base.StepResult("gpu", "skipped", "no GPU support for Whisper on Intel Macs; it uses the CPU")
    if ctx.args.dry_run:  # no nvidia-smi either
        return base.StepResult("gpu", "skipped", "dry run: with an NVIDIA GPU, would run reel gpu-enable")
    ctx.facts["nvidia"] = _nvidia_present(ctx)
    if not ctx.facts["nvidia"]:
        return base.StepResult("gpu", "skipped", "no NVIDIA GPU found (nvidia-smi); Whisper uses the CPU")
    py = ctx.runtime_python
    if py is None:
        rid = current_runtime(ctx.paths)
        py = runtime_python(ctx.paths, rid, ctx.platform) if rid else None
    if py is None or not Path(py).is_file():
        return base.StepResult("gpu", "amber", "the engine runtime is missing; Whisper keeps using the CPU")
    cli_py = ctx.plugin_root / "engine" / "reel" / "cli.py"
    rc, out = base.run_cmd(ctx, [py, "-s", "-B", cli_py, "gpu-enable"], GPU_TIMEOUT,
                      cwd=ctx.paths.whynot if ctx.paths.whynot.is_dir() else None)
    if rc != 0:
        return base.StepResult("gpu", "amber", f"reel gpu-enable failed (exit {rc}: {base.tail(out)}); "
                                               "Whisper keeps using the CPU")
    return base.StepResult("gpu", "ok", "NVIDIA GPU enabled for Whisper")


# --------------------------------------------------------------------------------------------- registry
STEPS = (("runtime", step_runtime, ()), ("ffmpeg", step_ffmpeg, ()), ("gpu", step_gpu, ("runtime",)))


def register(steps: list) -> None:
    """Append this module's install steps to cli.STEPS (once)."""
    have = {s[0] for s in steps}
    steps.extend(s for s in STEPS if s[0] not in have)
