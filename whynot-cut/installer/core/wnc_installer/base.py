"""Shared foundation of the installer core: everything a step needs, nothing step-specific.

Rules every helper here keeps (global constraints of the installer track):
  * a "<release>" / null value in components.json means "not in this build": refused, never guessed;
  * every download is pinned (URL + sha256), verified before use, and deleted on a mismatch;
  * writes that other programs read (state.json, `current`, settings) are atomic (tmp + replace);
  * deletes only happen strictly inside an allowed root, never through a symlink/junction, never next to client data.
Stdlib only, Python >= 3.9.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform as _platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Literal, Mapping, Optional

PLACEHOLDER = "<release>"
PLATFORMS = ("win-x64", "mac-arm64", "mac-x64")
STATUSES = ("ok", "skipped", "amber", "red")
CLIENT_MARKER = ".whynot-client"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class Unsupported(Exception):
    """This OS / CPU has no WhyNot Cut build."""


class DownloadError(Exception):
    """A pinned artefact could not be fetched or did not match its sha256 (nothing is left on disk)."""


class ExtractError(Exception):
    """An archive is unsafe (absolute / `..` / link entries), of an unknown type, or lacks a required member."""


def is_placeholder(v) -> bool:
    """None, or a string starting with "<release" (filled later by the release tool)."""
    return v is None or (isinstance(v, str) and v.startswith("<release"))


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def stamp() -> str:
    """Local time for file names: YYYYmmdd-HHMMSS."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


# --------------------------------------------------------------------------------------------- platform and paths
def platform_id(system: Optional[str] = None, machine: Optional[str] = None, *, sandbox: bool = False,
                env: Optional[Mapping] = None) -> str:
    """win-x64 | mac-arm64 | mac-x64, else Unsupported. WNC_TEST_PLATFORM is honoured only in a sandbox (--home)."""
    env = os.environ if env is None else env
    forced = env.get("WNC_TEST_PLATFORM") if sandbox else None
    if forced:
        if forced in PLATFORMS:
            return forced
        raise Unsupported(f"WNC_TEST_PLATFORM={forced!r} is not one of {', '.join(PLATFORMS)}")
    system = system or _platform.system()
    m = (machine or _platform.machine() or "").lower()
    if system == "Windows" and m in ("amd64", "x86_64", "x64"):
        return "win-x64"
    if system == "Darwin" and m in ("arm64", "aarch64"):
        return "mac-arm64"
    if system == "Darwin" and m in ("x86_64", "amd64"):
        return "mac-x64"
    raise Unsupported(f"WhyNot Cut runs on Windows x64 and macOS (Apple silicon or Intel); this is {system} {m}")


def _abs(p) -> Path:
    return Path(os.path.abspath(os.path.expanduser(str(p))))


@dataclass
class Paths:
    """Every location the installer touches. A --home override is a sandbox: nothing outside that folder is used."""
    home: Path
    whynot: Path
    claude_dir: Path
    appdata: Path
    localappdata: Path
    sandbox: bool

    @classmethod
    def from_env(cls, home_override: Optional[str] = None, env: Mapping = os.environ) -> "Paths":
        if home_override:
            home = _abs(home_override)
            return cls(home=home, whynot=home / ".whynot-cut", claude_dir=home / ".claude",
                       appdata=home / "AppData" / "Roaming", localappdata=home / "AppData" / "Local", sandbox=True)
        order = ("USERPROFILE", "HOME") if os.name == "nt" else ("HOME", "USERPROFILE")
        raw = next((env[k] for k in order if env.get(k)), None)
        home = _abs(raw) if raw else Path.home()
        whynot = _abs(env["WHYNOT_HOME"]) if env.get("WHYNOT_HOME") else home / ".whynot-cut"
        claude = _abs(env["CLAUDE_CONFIG_DIR"]) if env.get("CLAUDE_CONFIG_DIR") else home / ".claude"
        appdata = _abs(env["APPDATA"]) if env.get("APPDATA") else home / "AppData" / "Roaming"
        local = _abs(env["LOCALAPPDATA"]) if env.get("LOCALAPPDATA") else home / "AppData" / "Local"
        return cls(home=home, whynot=whynot, claude_dir=claude, appdata=appdata, localappdata=local, sandbox=False)

    # engine home layout (installer.md R.1)
    bin_dir = property(lambda s: s.whynot / "bin")
    python_dir = property(lambda s: s.whynot / "python")
    runtimes_dir = property(lambda s: s.whynot / "runtimes")
    current_file = property(lambda s: s.whynot / "current")
    ffmpeg_dir = property(lambda s: s.whynot / "ffmpeg")
    models_dir = property(lambda s: s.whynot / "models")
    logs_dir = property(lambda s: s.whynot / "logs")
    state_file = property(lambda s: s.whynot / "state.json")
    cache_dir = property(lambda s: s.whynot / "cache")
    downloads_dir = property(lambda s: s.whynot / "downloads")
    fonts_dir = property(lambda s: s.whynot / "fonts")
    marketplace_dir = property(lambda s: s.whynot / "marketplace")
    bridge_dir = property(lambda s: s.whynot / "bridge")
    settings_file = property(lambda s: s.claude_dir / "settings.json")
    sandbox_dir = property(lambda s: s.home / ".wnc-sandbox")

    def child_env(self, base_env: Optional[Mapping] = None) -> dict:
        """Environment for every child process (uv, the runtime, claude, reel)."""
        env = dict(os.environ if base_env is None else base_env)
        if self.sandbox:
            env.update(HOME=str(self.home), USERPROFILE=str(self.home), APPDATA=str(self.appdata),
                       LOCALAPPDATA=str(self.localappdata), CLAUDE_CONFIG_DIR=str(self.claude_dir))
        env.update(WHYNOT_HOME=str(self.whynot), UV_PYTHON_INSTALL_DIR=str(self.python_dir),
                   UV_CACHE_DIR=str(self.cache_dir / "uv"), PYTHONUTF8="1")
        return env


# --------------------------------------------------------------------------------------------- log
def _console(text: str) -> None:
    out = sys.stdout
    if out is None:
        return
    try:
        out.write(text + "\n")
    except UnicodeEncodeError:
        enc = out.encoding or "ascii"
        out.write(text.encode(enc, "backslashreplace").decode(enc, "replace") + "\n")
    out.flush()


class Log:
    """UTF-8 log lines `<ISO time> <LEVEL> <message>` in logs/install-YYYYmmdd-HHMMSS.log, echoed to the console.
    The bootstrap passes the path (--log) so its own lines and the core's share one file; dry-run = console only."""

    def __init__(self, path: Optional[Path], dry_run: bool = False, *, console: bool = True):
        self.dry_run = dry_run
        self.console = console
        self.path = None if (dry_run or path is None) else Path(path)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, level: str, msg: str, extra: str = "") -> None:
        if self.path:
            with open(self.path, "a", encoding="utf-8", newline="\n") as f:
                f.write(f"{now_iso()} {level} {msg}\n{extra}")
        if self.console:
            _console(msg if level in ("INFO", "STEP") else f"{level}: {msg}")

    def info(self, msg: str) -> None:
        self._write("INFO", msg)

    def warn(self, msg: str) -> None:
        self._write("WARN", msg)

    def error(self, msg: str) -> None:
        self._write("ERROR", msg)

    def step(self, name: str) -> None:
        self._write("STEP", f"== {name} ==")

    def exception(self, msg: str) -> None:
        """ERROR line plus the current traceback (file only; the console gets the one-line message)."""
        self._write("ERROR", msg, traceback.format_exc())


# --------------------------------------------------------------------------------------------- components / files
def load_components(path) -> dict:
    with open(path, encoding="utf-8-sig") as f:
        c = json.load(f)
    if not isinstance(c, dict) or c.get("schema") != 1:
        raise ValueError(f"{path}: not a schema-1 components.json")
    return c


def cget(c: dict, dotted: str, default=None):
    """components value by dotted path (`ffmpeg.assets.win-x64.files.0.url`); default when any part is missing."""
    cur = c
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return default
    return cur


def _replace(src: Path, dst: Path, tries: int = 6) -> None:
    """os.replace, retried briefly: on Windows an antivirus or indexer can hold the target for a moment."""
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.1 * (i + 1))


def atomic_write_text(path, text: str) -> None:
    """UTF-8, LF kept as written, no BOM; readers see the old or the new file, never half of one."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(text.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        _replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def atomic_write_json(path, obj) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------------------------- state.json
def _empty_state() -> dict:
    return {"schema": 1, "plugin": None, "updated_at": None, "steps": {}}


class State:
    """~/.whynot-cut/state.json: what is actually installed. Steps add their own sections (runtime, ffmpeg, ...);
    `steps` holds {name: {status, fingerprint, detail, at}} so a re-run skips work whose fingerprint still matches."""

    def __init__(self, paths: Paths, *, dry_run: bool = False):
        self.paths = paths
        self.dry_run = dry_run
        self.data = _empty_state()
        self.set_aside: Optional[Path] = None  # where an unreadable state.json was moved

    def load(self) -> "State":
        f = self.paths.state_file
        try:
            d = json.loads(f.read_text(encoding="utf-8-sig"))
            if not isinstance(d, dict) or not isinstance(d.get("steps", {}), dict):
                raise ValueError("not a state object")
        except FileNotFoundError:
            self.data = _empty_state()
            return self
        except (OSError, ValueError):
            self.data = _empty_state()
            if not self.dry_run:
                dest = f.with_name(f"{f.name}.corrupt-{stamp()}")
                n = 1
                while dest.exists():
                    dest = f.with_name(f"{f.name}.corrupt-{stamp()}-{n}")
                    n += 1
                try:
                    _replace(f, dest)
                    self.set_aside = dest
                except OSError:
                    pass
            return self
        d.setdefault("schema", 1)
        d.setdefault("plugin", None)
        d.setdefault("updated_at", None)
        d.setdefault("steps", {})
        self.data = d
        return self

    def save(self) -> None:
        if self.dry_run:
            return
        self.data["updated_at"] = now_iso()
        atomic_write_json(self.paths.state_file, self.data)

    def step_done(self, name: str, fingerprint) -> bool:
        s = self.data.get("steps", {}).get(name)
        return isinstance(s, dict) and s.get("status") == "ok" and s.get("fingerprint") == fingerprint

    def record(self, name: str, status: str, fingerprint=None, detail: str = "") -> None:
        self.data.setdefault("steps", {})[name] = {"status": status, "fingerprint": fingerprint, "detail": detail,
                                                   "at": now_iso()}
        self.save()


# --------------------------------------------------------------------------------------------- download
def find_curl() -> Optional[str]:
    """The OS curl first (Windows 10+ System32, macOS /usr/bin: they use the system certificate store)."""
    if os.name == "nt":
        sys32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "curl.exe"
        if sys32.is_file():
            return str(sys32)
    elif Path("/usr/bin/curl").is_file():
        return "/usr/bin/curl"
    return shutil.which("curl")


def _fetch_curl(curl: str, url: str, part: Path) -> None:
    # curl writes to stdout and Python owns the file: no non-ASCII path ever reaches curl's argv
    with open(part, "wb") as fh:
        r = subprocess.run([curl, "--fail", "--location", "--silent", "--show-error", "--proto", "=http,https",
                            "--connect-timeout", "30", "--speed-limit", "1024", "--speed-time", "60", url],
                           stdout=fh, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        msg = r.stderr.decode("utf-8", "replace").strip().splitlines()
        raise OSError(f"curl exit {r.returncode}: {msg[-1] if msg else ''}")


def _fetch_urllib(url: str, part: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "whynot-cut-installer"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as fh:
            shutil.copyfileobj(resp, fh, 1 << 20)
    except urllib.error.HTTPError as e:
        e.close()  # it holds the response body: an unclosed one is a ResourceWarning
        raise OSError(f"HTTP {e.code} {e.reason}") from None


def download(url, sha256, dest_dir, log: Log, *, name: Optional[str] = None, retries: int = 3) -> Path:
    """Fetch a pinned artefact into dest_dir (normally ~/.whynot-cut/downloads) and return its path.

    A cached file with the right sha256 is reused; a wrong one is replaced. The transfer goes to `<name>.part`
    (a stale one from an interrupted run is discarded), is verified, then renamed. A sha256 mismatch deletes the file
    and raises DownloadError (not retried: the pin or the server is wrong). Network errors are retried; each try uses
    curl and falls back to urllib. Placeholder pins are refused before any request. http(s):// and file:// only."""
    if is_placeholder(url) or is_placeholder(sha256):
        raise DownloadError(f"not available in this build (placeholder pin): {url!r} sha256={sha256!r}")
    if not isinstance(sha256, str) or not _HEX64.match(sha256):
        raise DownloadError(f"invalid sha256 pin {sha256!r} for {url}")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("https", "http", "file"):
        raise DownloadError(f"unsupported URL scheme: {url}")
    name = name or urllib.parse.unquote(parsed.path).rsplit("/", 1)[-1]
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise DownloadError(f"cannot name the download for {url!r}")
    dest_dir = Path(dest_dir)
    dest = dest_dir / name
    part = dest_dir / (name + ".part")
    if dest.is_file():
        if file_sha256(dest) == sha256:
            log.info(f"cached {dest.name} (sha256 ok)")
            return dest
        log.warn(f"cached {dest.name} has the wrong sha256; fetching it again")
        dest.unlink()
    dest_dir.mkdir(parents=True, exist_ok=True)
    if part.exists():
        part.unlink()
    log.info(f"download {url}")
    last: Optional[Exception] = None
    for attempt in range(max(1, retries)):
        try:
            if parsed.scheme == "file":
                src = Path(urllib.request.url2pathname(parsed.path))
                if parsed.netloc and parsed.netloc != "localhost":
                    src = Path(f"//{parsed.netloc}{src}")
                shutil.copyfile(src, part)
            else:
                curl = find_curl()
                try:
                    if not curl:
                        raise OSError("curl not found")
                    _fetch_curl(curl, url, part)
                except OSError as e:
                    if curl:
                        log.warn(f"curl failed ({e}); trying Python's downloader")
                    _fetch_urllib(url, part)
            last = None
            break
        except (OSError, urllib.error.URLError, ValueError) as e:
            last = e
            if part.exists():
                part.unlink()
            if attempt < max(1, retries) - 1:
                log.warn(f"download failed ({e}); retrying")
                time.sleep(min(2 ** attempt, 5))
    if last is not None:
        raise DownloadError(f"could not download {url}: {last}")
    got = file_sha256(part)
    if got != sha256:
        part.unlink()
        raise DownloadError(f"sha256 mismatch for {url}: expected {sha256}, got {got}; the file was deleted")
    _replace(part, dest)
    log.info(f"verified {dest.name} (sha256 ok)")
    return dest


# --------------------------------------------------------------------------------------------- extract
def _safe_rel(name: str) -> Optional[str]:
    """Archive entry → clean relative posix path ('' for the root); None when absolute or escaping with `..`."""
    n = name.replace("\\", "/")
    if n.startswith("/") or re.match(r"^[A-Za-z]:", n):
        return None
    parts = [p for p in n.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    return "/".join(parts)


def _archive_kind(archive: Path) -> str:
    n = archive.name.lower()
    if n.endswith(".zip"):
        return "zip"
    if n.endswith((".tar.gz", ".tgz")):
        return "r:gz"
    if n.endswith((".tar.xz", ".txz")):
        return "r:xz"
    if zipfile.is_zipfile(archive):
        return "zip"
    if tarfile.is_tarfile(archive):
        return "r:*"
    raise ExtractError(f"unknown archive type: {archive.name}")


def extract(archive, dest, members: Optional[dict] = None) -> list:
    """Unpack a zip / tar.gz / tar.xz into dest and return the files written.

    `members` maps archive path → output path under dest (e.g. {"ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe":
    "ffmpeg.exe"}); only those are written, and on macOS they are made executable. Without it everything is written,
    keeping the archive's exec bits. Every entry is checked first: an absolute path, a `..` or a link refuses the whole
    archive before anything is written."""
    archive, dest = Path(archive), Path(dest)
    kind = _archive_kind(archive)
    entries = []  # (clean relative name, is_dir, mode, opener)
    try:
        zf = zipfile.ZipFile(archive) if kind == "zip" else tarfile.open(archive, kind)
    except (zipfile.BadZipFile, tarfile.TarError, EOFError, OSError) as e:
        raise ExtractError(f"cannot read {archive.name}: {e}") from None
    with zf:
        if kind == "zip":
            for zi in zf.infolist():
                rel = _safe_rel(zi.filename)
                mode = (zi.external_attr >> 16) & 0o177777 if zi.create_system == 3 else 0  # 3 = made on unix
                if rel is None or stat.S_ISLNK(mode):
                    raise ExtractError(f"unsafe entry in {archive.name}: {zi.filename!r}")
                entries.append((rel, zi.is_dir(), mode & 0o777, (lambda zi=zi: zf.open(zi))))
        else:
            for ti in zf.getmembers():
                rel = _safe_rel(ti.name)
                if rel is None or not (ti.isfile() or ti.isdir()):
                    raise ExtractError(f"unsafe entry in {archive.name}: {ti.name!r}")
                entries.append((rel, ti.isdir(), ti.mode & 0o777, (lambda ti=ti: zf.extractfile(ti))))
        files = {rel: (mode, opener) for rel, is_dir, mode, opener in entries if rel and not is_dir}
        if members is not None:
            plan = []
            for src, out in members.items():
                s, o = _safe_rel(src), _safe_rel(out)
                if not s or not o:
                    raise ExtractError(f"unsafe member mapping {src!r} -> {out!r}")
                if s not in files:
                    raise ExtractError(f"{archive.name} has no {src!r}")
                plan.append((o, 0o755, files[s][1]))
        else:
            plan = [(rel, mode, opener) for rel, (mode, opener) in files.items()]
        dest.mkdir(parents=True, exist_ok=True)
        root = os.path.abspath(dest)
        written = []
        for rel, mode, opener in plan:
            out = dest.joinpath(*rel.split("/"))
            if not os.path.abspath(out).startswith(root + os.sep):
                raise ExtractError(f"entry escapes the destination: {rel!r}")
            out.parent.mkdir(parents=True, exist_ok=True)
            with opener() as src_f, open(out, "wb") as dst_f:
                shutil.copyfileobj(src_f, dst_f, 1 << 20)
            if os.name != "nt" and mode & 0o111:
                os.chmod(out, 0o755)
            written.append(out)
    return written


# --------------------------------------------------------------------------------------------- safe delete
def is_link(p) -> bool:
    """Symlink, or any Windows reparse point (junction, mount point, ...)."""
    try:
        st = os.lstat(p)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _norm(p) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def _real(p) -> str:
    return os.path.normcase(os.path.realpath(str(p)))


def _within(child: str, parent: str, strict: bool = True) -> bool:
    if child == parent:
        return not strict
    return child.startswith(parent.rstrip("\\/") + os.sep)


def _has_marker(top: str) -> bool:
    stack = [top]
    while stack:
        with os.scandir(stack.pop()) as it:
            for e in it:
                if e.name == CLIENT_MARKER:
                    return True
                if not is_link(e.path) and e.is_dir(follow_symlinks=False):
                    stack.append(e.path)
    return False


def _unlink(p: str) -> None:
    try:
        os.unlink(p)  # on Windows this also removes a directory symlink / junction (not its target)
    except PermissionError:
        if is_link(p):
            os.rmdir(p)
        else:
            os.chmod(p, stat.S_IWRITE)  # read-only file (git objects, some wheels)
            os.unlink(p)
    except IsADirectoryError:
        os.rmdir(p)


def _delete(top: str) -> None:
    with os.scandir(top) as it:
        entries = [(e.path, e.is_dir(follow_symlinks=False)) for e in it]
    for path, is_dir in entries:
        if is_link(path) or not is_dir:
            _unlink(path)
        else:
            _delete(path)
    os.rmdir(top)


def safe_rmtree(path, allowed_roots: Iterable, protected: Iterable = ()) -> bool:
    """Delete `path` only when that is certainly safe; False (nothing deleted) when refused, True when gone.

    Refused when: `path` is a symlink/junction; it is not strictly inside one of `allowed_roots` (checked both as
    written and with links resolved, so a junction above it cannot lead outside); it is, contains or lies inside a
    `protected` path (clients folder, models, Claude's folder ...); or a `.whynot-client` marker sits anywhere below
    it. Links found inside are removed as links; their targets are never entered. OS errors while deleting raise."""
    p = str(path)
    if not os.path.lexists(p):
        return True
    if is_link(p):
        return False
    lex, real = _norm(p), _real(p)
    if not any(_within(lex, _norm(r)) and _within(real, _real(r)) for r in allowed_roots):
        return False
    for pr in protected:
        for mine, theirs in ((lex, _norm(pr)), (real, _real(pr))):
            if _within(theirs, mine, strict=False) or _within(mine, theirs, strict=False):
                return False
    if os.path.isdir(p):
        if _has_marker(p):
            return False
        _delete(p)
    else:
        if os.path.basename(p) == CLIENT_MARKER:
            return False
        _unlink(p)
    return True


# --------------------------------------------------------------------------------------------- steps
@dataclass
class StepResult:
    name: str
    status: Literal["ok", "skipped", "amber", "red"]
    detail: str = ""
    needs_you: Optional[str] = None  # one line the editor must act on (shown in the final summary)


@dataclass
class Ctx:
    paths: Paths
    log: Log
    components: dict
    state: State
    plugin_root: Path
    platform: str
    args: argparse.Namespace
    runtime_python: Optional[Path] = None  # set by the runtime step
    facts: dict = field(default_factory=dict)  # what preflight / gpu / adobe found
    answers: dict = field(default_factory=dict)  # the editor's answers (questions step)


StepFn = Callable[[Ctx], StepResult]


def run_steps(ctx: Ctx, steps) -> list:
    """Run (name, fn, needs) in order. A step whose `needs` are not all `ok` is skipped ("needs <name>"); a name in
    --skip is skipped; an exception is `red` (traceback in the log) and later independent steps still run. A red step
    is recorded in state.json so the next run does it again; ok steps record their own fingerprint."""
    skip = set(getattr(ctx.args, "skip", None) or ())
    results, status = [], {}
    for name, fn, needs in steps:
        ctx.log.step(name)
        missing = [n for n in needs if status.get(n) != "ok"]
        if name in skip:
            r = StepResult(name, "skipped", "skipped with --skip")
        elif missing:
            r = StepResult(name, "skipped", "needs " + ", ".join(missing))
        else:
            try:
                r = fn(ctx)
                if not isinstance(r, StepResult) or r.status not in STATUSES:
                    r = StepResult(name, "red", f"internal error: step returned {r!r}")
                elif r.name != name:
                    r = StepResult(name, r.status, r.detail, r.needs_you)
            except Exception as e:  # noqa: BLE001 - one broken step must not stop the others
                ctx.log.exception(f"{name} failed: {type(e).__name__}: {e}")
                r = StepResult(name, "red", f"{type(e).__name__}: {e}")
        if r.status == "red":
            try:
                ctx.state.record(name, "red", None, r.detail)
            except OSError as e:
                ctx.log.warn(f"could not update state.json: {e}")
        line = f"{name}: {r.status}" + (f" - {r.detail}" if r.detail else "")
        {"red": ctx.log.error, "amber": ctx.log.warn}.get(r.status, ctx.log.info)(line)
        if r.needs_you:
            ctx.log.warn(f"{name}: you need to: {r.needs_you}")
        status[name] = r.status
        results.append(r)
    return results
