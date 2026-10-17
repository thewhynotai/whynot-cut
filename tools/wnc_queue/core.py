"""Paths, config, job validation and atomic file IO for wnc-queue (stdlib only)."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

IS_WIN = os.name == "nt"
TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
TASK_NAME = "WNC-Queue"
SCHEMA = 1

CLASSES = ("cpu", "gpu", "suite", "gate", "none")  # heavy.sh slot; "none" = light (CI watch, download): no slot
HEAVY_KIND = {"cpu": "job", "gpu": "gpu", "suite": "suite", "gate": "gate"}
GATE_OWNER = "executor"        # a gate reserves the whole machine: only the executor's QC-gate suites use it
MODES = ("exit", "repeat", "until_fail", "until_streak", "until_match")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
# Ids that would collide with the runner's own files in running/ and logs/ (<id>.spec.json, <id>.json.dup-N …),
# a trailing dot (Windows drops it, so "t." would be job t's files) and "runner" (logs/runner.log is the runner's).
RESERVED_ID_RE = re.compile(r"\.(spec|started|cancel|refused|cancelling)$|\.json(\.|$)|\.log(\.\d+)?$|\.dup-\d+$"
                            r"|\.refused-\d{8}-\d{6}-\d+-\d+$"     # a refusal record's name (would fake one)
                            r"|\.$|^runner$", re.I)
MAX_ARGV_CHARS = 32767                              # the Windows command-line limit (a cheap first check)
CMDLINE_MAX = 32766            # CreateProcess: 32 767 characters including the terminating NUL
CMDLINE_MAX_BATCH = 8191       # a .cmd/.bat runs inside cmd.exe, whose own limit is lower

# Executables a job may start, by file stem (python/runtime, bash, node, npm, gh, git, ffmpeg, our tools). No cmd,
# powershell, curl, npx or claude: AI work never goes through this queue, and shell strings are refused below.
ALLOWED_EXES = frozenset({"python", "python3", "py", "bash", "sh", "node", "npm", "gh", "git", "ffmpeg", "ffprobe",
                          "reel", "uv"})
SHELLS = frozenset({"bash", "sh"})
# URLs written into a job must point at these hosts (the usual dev allowlist). This checks the job text only: what a
# program fetches on its own is not sandboxed (no firewall changes, by rule).
ALLOWED_HOSTS = ("github.com", "api.github.com", ".githubusercontent.com", "registry.npmjs.org", "pypi.org",
                 "files.pythonhosted.org", "huggingface.co", ".huggingface.co", ".hf.co", "www.gyan.dev", "gyan.dev",
                 "evermeet.cx", "localhost", "127.0.0.1")
# Never touched by a job: client folders and Adobe preferences (matched case-insensitively, any slash style).
FORBIDDEN_FRAGMENTS = ("/whynot clients", "/appdata/roaming/adobe", "/documents/adobe/", "/library/preferences/adobe",
                       "/library/application support/adobe")
# AI tooling by name (also as an npm package or a script path): never queued, whatever runs it.
AI_RE = re.compile(r"claude-code|@anthropic-ai/", re.I)
# Recursive deletes that follow junctions (COORDINATION rule 15): refused anywhere in a job's argv. Any rm with a
# recursive flag anywhere after it (rm -rf, rm -r -f, rm --recursive, rm x -R), Remove-Item -Recurse (or -r…),
# robocopy /MIR /MOV /MOVE /PURGE (by name or full path), rmdir /s and rd /s. Over-cautious on purpose: a refused job
# is cheap, a followed junction is not. Each is (the command, then its switch anywhere after the command's FIRST
# occurrence): a switch after any occurrence is after the first, so two linear searches give the same answer as one
# regex with a lazy middle, which was quadratic on a crafted "rm " * 10 900 (~3 s for a 32 KB argv).
DELETE_PATTERNS = (
    (re.compile(r"\brm(?=\s)", re.I),
     re.compile(r"\s(?:-(?=[a-z]*r)[a-z]+|--recursive)(?=[\s\"',)\]]|$)", re.I)),
    (re.compile(r"\bremove-item\b", re.I), re.compile(r"\s-r[a-z]*\b", re.I)),
    (re.compile(r"(?<![\w.-])robocopy(?:\.exe)?[\"']?(?=\s)", re.I),
     re.compile(r"\s/(?:mir|mov|move|purge)(?=[\s/:\"',)\]]|$)", re.I)),
)
# cmd's rd/del/erase as a command (not a path segment like D:/x/del/s.py), then a /s switch anywhere after it
# (rd /s /q x, del /q/s x, rd/s/q x). Two linear searches instead of one regex: a crafted argv can't make it slow.
CMD_DELETE_RE = re.compile(r"(?<![\w./\\:-])(?:rmdir|rd|del|erase)(?:\.exe)?(?=[\s/\"']|$)", re.I)
SWITCH_S_RE = re.compile(r"(?:^|\s|(?<![\w./\\:-])(?:rmdir|rd|del|erase)(?:\.exe)?)(?:/[a-z]+)*/s(?=[\s/\"',)\]]|$)",
                         re.I)                      # also a later name glued to its switch: "... & rd/s/q build"


def is_destructive(text: str) -> bool:
    for command, switch in DELETE_PATTERNS:
        m = command.search(text)
        if m and switch.search(text, m.end()):
            return True
    m = CMD_DELETE_RE.search(text)
    return bool(m and SWITCH_S_RE.search(text[m.end():]))


BATCH_OK = frozenset({"npm", "reel"})   # the only allowed programs that are .cmd files on Windows
SHELL_VALUE_OPTS = frozenset({"-o", "+o", "-O", "+O", "--rcfile", "--init-file"})   # bash options taking a value
CMD_META = frozenset('"%^&|<>!')    # cmd.exe re-parses a .cmd/.bat command line: these would be shell syntax
DEFAULT_HEAVY_SH = r"C:\Users\LOQ\AppData\Roaming\Claude\side-session-notes\local_263cabbf-75e3-42a1-b384-1753a7bd4dad\heavy.sh"


class JobError(ValueError):
    """A job file that must not run (the reason is shown to the session that queued it)."""


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def default_home() -> Path:
    env = os.environ.get("WNC_QUEUE_HOME")
    if env:
        return Path(env)
    if IS_WIN and Path("D:/ClaudeData").is_dir():
        return Path("D:/ClaudeData/jobs")
    return Path.home() / ".wnc-queue"


class Paths:
    def __init__(self, home: Path | str | None = None):
        self.home = Path(home) if home else default_home()
        self.queue = self.home / "queue"
        self.running = self.home / "running"
        self.done = self.home / "done"
        self.logs = self.home / "logs"
        self.stop = self.home / "STOP"
        self.lock = self.home / "runner.lock"
        self.runner_json = self.home / "runner.json"
        self.runner_log = self.logs / "runner.log"
        self.config = self.home / "config.json"

    def ensure(self) -> "Paths":
        for d in (self.queue, self.running, self.done, self.logs):
            d.mkdir(parents=True, exist_ok=True)
        return self

    def spec(self, jid: str) -> Path:
        return self.running / f"{jid}.spec.json"

    def started(self, jid: str) -> Path:
        return self.running / f"{jid}.started"

    def cancel(self, jid: str) -> Path:
        return self.running / f"{jid}.cancel"

    def log(self, jid: str) -> Path:
        return self.logs / f"{jid}.log"


def _which_bash() -> str | None:
    for c in (r"C:\Program Files\Git\bin\bash.exe",):
        if IS_WIN and Path(c).is_file():
            return c
    return search_path("bash")                     # never the current folder (shutil.which looks there first)


def console_python(exe: str) -> str:
    """python.exe next to pythonw.exe: the trampoline must be a console program so its children get a hidden console."""
    p = Path(exe)
    if p.name.lower() == "pythonw.exe" and (p.parent / "python.exe").is_file():
        return str(p.parent / "python.exe")
    return exe


def load_config(paths: Paths) -> dict:
    cfg = {
        "python": console_python(sys.executable),
        "bash": _which_bash(),
        "heavy_sh": os.environ.get("WNC_HEAVY_SH") or DEFAULT_HEAVY_SH,
        "max_parallel": 4,             # heavy.sh still gates the heavy ones (RAM valve); light jobs count too
        "poll_s": 1.0,
        "sample_s": 2.0,
        "max_log_mb": 50,              # per job log; above it the log rotates to <id>.log.1
        "max_logs_total_mb": 2048,
        "retention_days": 30,
        "temp_root": str(Path("D:/ClaudeData/Temp/wnc-queue")) if IS_WIN and Path("D:/ClaudeData").is_dir()
        else str(paths.home / "tmp"),
        "allowed_roots": [],
        "extra_executables": [],
        "extra_hosts": [],
        "locks_dir": "D:/ClaudeData/Temp/wnc-locks",   # heavy.sh slots (kept fresh while a job holds one)
        "slot_refresh_s": 120,                          # how often (heavy.sh v2 frees a slot silent for 10 min)
        "pressure_ram_pct": PRESSURE_RAM_PCT,           # system RAM peak during a run that makes its verdict suspect
    }
    try:
        user = json.loads(paths.config.read_text(encoding="utf-8-sig"))
        if isinstance(user, dict):
            cfg.update({k: v for k, v in user.items() if k in cfg})
    except (OSError, ValueError):
        pass
    cfg["pressure_ram_pct"] = pressure_threshold(cfg.get("pressure_ram_pct"))
    return cfg


def allowed_roots(cfg: dict) -> list[Path]:
    roots = [REPO]
    if IS_WIN:
        roots += [Path("D:/ClaudeData"), Path("D:/Claude")]
    roots += [Path(r) for r in cfg.get("allowed_roots", [])]
    out = []
    for r in roots:
        try:
            out.append(Path(os.path.realpath(r)))
        except OSError:
            pass
    return out


def _inside(p: Path, roots: list[Path]) -> bool:
    for r in roots:
        try:
            p.relative_to(r)
            return True
        except ValueError:
            continue
    return False


def _norm(s: str) -> str:
    return s.replace("\\", "/").lower()


def check_text(s: str, cfg: dict, where: str) -> None:
    n = _norm(s)
    for frag in FORBIDDEN_FRAGMENTS:
        if frag in n or n.startswith(frag.lstrip("/")):
            raise JobError(f"{where} touches a forbidden area ({frag.strip('/')}): client folders and Adobe "
                           "preferences are off limits")
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s\"'<>]+", s):
        host = (urlsplit(m.group(0)).hostname or "").lower()
        hosts = tuple(ALLOWED_HOSTS) + tuple(h.lower() for h in cfg.get("extra_hosts", []))
        if not any(host == h or (h.startswith(".") and host.endswith(h)) for h in hosts):
            raise JobError(f"{where}: host {host or '?'} is not on the network allowlist")


def exe_stem(path: str) -> str:
    name = Path(path).name.lower()
    for ext in (".exe", ".cmd", ".bat", ".com"):
        if name.endswith(ext):
            return name[: -len(ext)]
    return name


def resolve_exe(argv0: str, cwd: Path, cfg: dict, path_env: str | None = None) -> str:
    stem = exe_stem(argv0)
    allowed = ALLOWED_EXES | {s.lower() for s in cfg.get("extra_executables", [])}
    if stem not in allowed:
        raise JobError(f"executable {argv0!r} is not allowlisted (allowed: {', '.join(sorted(allowed))})")
    if any(sep in argv0 for sep in ("/", "\\")):
        p = Path(argv0)
        if not p.is_absolute():
            p = cwd / p
        if not p.is_file():
            raise JobError(f"executable {argv0!r} not found")
        if p.suffix.lower() in (".cmd", ".bat"):
            raise JobError(f"{argv0!r}: name a program, not a batch file (cmd.exe would re-parse its arguments)")
        return str(p)
    if stem == "bash" and cfg.get("bash"):
        return str(cfg["bash"])
    if stem in ("python", "python3") and cfg.get("python"):
        return str(cfg["python"])
    found = search_path(argv0, path_env)
    if not found:
        raise JobError(f"executable {argv0!r} not found on PATH")
    if Path(found).suffix.lower() in (".cmd", ".bat") and stem not in BATCH_OK:
        raise JobError(f"{argv0!r} resolves to the batch file {found}: only {', '.join(sorted(BATCH_OK))} may be "
                       "batch files (cmd.exe would re-parse the arguments)")
    return found


def search_path(name: str, path_env: str | None = None) -> str | None:
    """Like shutil.which, but never looks in the current folder (on Windows, which() puts it first even with an
    explicit path, so a planted gh.bat next to the runner would win)."""
    exts = [""]
    if IS_WIN and not Path(name).suffix:
        exts = [e for e in (os.environ.get("PATHEXT") or ".COM;.EXE;.BAT;.CMD").lower().split(";") if e]
    for d in (path_env if path_env is not None else os.environ.get("PATH", "")).split(os.pathsep):
        d = d.strip().strip('"')
        if not d or not os.path.isabs(d):
            continue
        for ext in exts:
            c = os.path.join(d, name + ext)
            if os.path.isfile(c) and (IS_WIN or os.access(c, os.X_OK)):
                return c
    return None


def check_batch_args(exe: str, args: list[str]) -> None:
    """npm and reel are .cmd files on Windows: cmd.exe re-parses their command line, so shell syntax is refused."""
    if Path(exe).suffix.lower() in (".cmd", ".bat"):
        for a in args:
            bad = CMD_META & set(a)
            if bad:
                raise JobError(f"{Path(exe).name} runs through cmd.exe: argument {a!r} has {''.join(sorted(bad))} "
                               "(put it in a script and run that with python or node)")


def check_command_line(exe: str, args: list[str]) -> None:
    """Measure the command line Windows will build (quoting doubles a quote or a run of backslashes) against the
    limit that applies, so a job that could never start is refused now with a reason, not run as an rc-127 failure.
    The same limit on every platform: a job runs the same on any machine."""
    batch = Path(exe).suffix.lower() in (".cmd", ".bat")
    n = len(subprocess.list2cmdline([exe, *args])) + (len('cmd.exe /c ""') if batch else 0)
    limit = CMDLINE_MAX_BATCH if batch else CMDLINE_MAX
    if n > limit:
        raise JobError(f"the command line would be {n} characters, over the {limit} limit for "
                       f"{Path(exe).name}{' (it runs inside cmd.exe)' if batch else ''}: put the long part in a file")


def parse_duration(v) -> float:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smhd]?)\s*", str(v))
    if not m:
        raise JobError(f"bad duration {v!r} (use 90, 90s, 30m, 2h, 1d)")
    return float(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]


def new_id(title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()[:24] or "job"
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}-{secrets.token_hex(2)}"


def validate(job: dict, cfg: dict) -> dict:
    """Normalise a job dict or raise JobError. Returns a new dict (the runner re-validates every job it claims)."""
    if not isinstance(job, dict):
        raise JobError("a job is a JSON object")
    j = dict(job)
    jid = j.get("id") or new_id(str(j.get("title") or "job"))
    if not isinstance(jid, str) or not ID_RE.match(jid):
        raise JobError(f"bad id {jid!r} (letters, digits, . _ -; max 64)")
    if RESERVED_ID_RE.search(jid):
        raise JobError(f"bad id {jid!r}: it looks like one of the runner's own files (.spec, .started, .cancel, "
                       ".refused, .cancelling, .json, .log, .dup-)")
    j["id"] = jid
    j["title"] = str(j.get("title") or jid)[:200]
    argv = j.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a and "\0" not in a for a in argv):
        raise JobError("argv must be a non-empty list of strings (no shell strings)")
    if len(" ".join(argv)) > MAX_ARGV_CHARS:
        raise JobError(f"argv is longer than {MAX_ARGV_CHARS} characters (the Windows limit): use a script file")
    stem = exe_stem(argv[0])
    allowed = ALLOWED_EXES | {x.lower() for x in cfg.get("extra_executables", [])}
    if stem not in allowed:
        raise JobError(f"executable {argv[0]!r} is not allowlisted (allowed: {', '.join(sorted(allowed))})")
    for a in argv:
        if exe_stem(a) == "claude" or AI_RE.search(a):
            raise JobError("AI work (claude) never runs in wnc-queue")
        check_text(a, cfg, "argv")
    if is_destructive(" ".join(argv)):
        raise JobError("recursive deletes (rm -rf, Remove-Item -Recurse, rmdir /s) are refused: they follow "
                       "junctions (COORDINATION rule 15)")
    if stem in SHELLS:
        rest = iter(argv[1:])
        for a in rest:
            if a == "--":                              # end of options: the next word is the script
                break
            if a in SHELL_VALUE_OPTS:
                values = 1
            elif a.startswith("--"):
                continue
            elif not a.startswith(("-", "+")):
                break
            elif "c" in a[1:]:
                raise JobError("shell strings are refused (bash -c / sh -c): run a script file")
            else:                                      # a cluster like -eo pipefail / -xO extglob: o and O take values
                values = a[1:].count("o") + a[1:].count("O")
            for _ in range(values):
                v = next(rest, None)
                if v is not None and v.startswith(("-", "+")):
                    raise JobError(f"bash option {a} needs a value, got {v!r}")
    cwd = Path(j.get("cwd") or REPO)
    if not cwd.is_absolute():
        raise JobError("cwd must be an absolute path")
    check_text(str(cwd), cfg, "cwd")
    real = Path(os.path.realpath(cwd))
    if not real.is_dir():
        raise JobError(f"cwd {cwd} does not exist")
    if not _inside(real, allowed_roots(cfg)):
        raise JobError(f"cwd {cwd} is outside the repo, D:\\ClaudeData and D:\\Claude")
    j["cwd"] = str(cwd)
    env = j.get("env") or {}
    if not isinstance(env, dict) or not all(isinstance(k, str) and ENV_KEY_RE.match(k) and isinstance(v, str)
                                            for k, v in env.items()):
        raise JobError("env must map NAME to string")
    if any(k.upper().startswith("HEAVY_") for k in env):     # HEAVY_INSIDE / HEAVY_LOCKS would let nested calls skip
        raise JobError("env must not set HEAVY_* (heavy.sh's own variables: a job can't change how it takes slots)")
    for v in env.values():
        check_text(v, cfg, "env")
    j["env"] = dict(env)
    heavy = j.get("heavy", "cpu")
    if heavy not in CLASSES:
        raise JobError(f"heavy class must be one of {', '.join(CLASSES)}")
    j["heavy"] = heavy
    j["timeout_s"] = parse_duration(j.get("timeout_s", 3600))
    j["max_wait_s"] = parse_duration(j.get("max_wait_s", 6 * 3600))
    for k in ("timeout_s", "max_wait_s"):
        if not 1 <= j[k] <= 7 * 86400:
            raise JobError(f"{k} must be between 1 s and 7 days")
    stop = dict(j.get("stop") or {"mode": "exit"})
    mode = stop.get("mode", "exit")
    if mode not in MODES:
        raise JobError(f"stop.mode must be one of {', '.join(MODES)}")

    def count(key, default=None):
        v = stop.get(key, default)
        if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 1000:
            raise JobError(f"stop.{key} must be an integer 1..1000")
        return v
    if mode == "repeat":
        stop["times"] = count("times")
    elif mode == "until_fail":
        stop["max"] = count("max")
    elif mode == "until_streak":
        stop["k"] = count("k")
        stop["max"] = count("max", max(stop["k"], 1) * 5 if isinstance(stop.get("k"), int) else None)
        if stop["k"] > stop["max"]:
            raise JobError("stop.k must not exceed stop.max")
    elif mode == "until_match":
        if not isinstance(stop.get("regex"), str) or not stop["regex"]:
            raise JobError("stop.regex is required for until_match")
    stop["mode"] = mode
    j["stop"] = stop
    pats = {k: j.get(k) for k in ("pass_regex", "fail_regex")}
    if mode == "until_match":
        pats["stop.regex"] = stop["regex"]
    for k, pat in pats.items():
        if pat is None:
            continue
        if not isinstance(pat, str):
            raise JobError(f"{k} must be a string")
        try:
            re.compile(pat)
        except re.error as e:
            raise JobError(f"{k}: {e}") from None
    pr = j.get("priority", 0)
    if not isinstance(pr, int) or isinstance(pr, bool) or not -100 <= pr <= 100:
        raise JobError("priority must be an integer -100..100 (higher runs first)")
    j["priority"] = pr
    j["owner"] = str(j.get("owner") or "unknown")[:64]
    if heavy == "gate" and j["owner"] != GATE_OWNER:
        raise JobError(f"class gate reserves the whole machine: only for the {GATE_OWNER}'s QC-gate suites "
                       f"(--owner {GATE_OWNER}); use suite for other full suites")
    ma = j.get("max_attempts", 3)
    if not isinstance(ma, int) or isinstance(ma, bool) or not 1 <= ma <= 10:
        raise JobError("max_attempts must be 1..10")
    j["max_attempts"] = ma
    j.setdefault("schema", SCHEMA)
    j.setdefault("queued_at", now_iso())
    j.setdefault("queued_ns", time.time_ns())          # FIFO order finer than queued_at's whole seconds
    j.setdefault("attempts", 0)
    j.setdefault("iterations", [])
    j.setdefault("events", [])
    return j


def write_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    for i in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:            # a reader holds it open on Windows: retry briefly
            time.sleep(0.05 * (i + 1))
    os.replace(tmp, path)


def read_json(path: Path) -> dict | None:
    """A JSON file, or None if it is missing or not JSON. Only a held file (PermissionError) is retried: our own
    writes are atomic, so bad JSON stays bad (the runner counts such files over several passes instead)."""
    for i in range(10):
        try:
            text = path.read_text(encoding="utf-8-sig")   # a BOM (PowerShell 5.1 Out-File) is fine
        except FileNotFoundError:
            return None
        except PermissionError:
            time.sleep(0.05 * (i + 1))
            continue
        except OSError:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return None
    return None


def unlink(path: Path) -> None:
    """Remove one file (never a directory, never recursive)."""
    try:
        path.unlink()
    except FileNotFoundError:
        pass


FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def _kind(path) -> tuple[bool, bool]:
    """(is_link, is_dir) from lstat, never following the path itself. Any reparse point (junction, symlink, mount
    point …) counts as a link: this does not rely on DirEntry.is_junction, which needs Python 3.12."""
    st = os.lstat(path)
    attrs = getattr(st, "st_file_attributes", 0)
    is_link = stat.S_ISLNK(st.st_mode) or bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
    is_dir = stat.S_ISDIR(st.st_mode) or bool(attrs & FILE_ATTRIBUTE_DIRECTORY)
    return is_link, is_dir


if IS_WIN:
    import ctypes
    from ctypes import wintypes as _wt

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateFileW.restype = _wt.HANDLE
    _k32.CreateFileW.argtypes = [_wt.LPCWSTR, _wt.DWORD, _wt.DWORD, _wt.LPVOID, _wt.DWORD, _wt.DWORD, _wt.HANDLE]
    _k32.CloseHandle.argtypes = [_wt.HANDLE]

    class _BHFI(ctypes.Structure):                   # BY_HANDLE_FILE_INFORMATION
        _fields_ = [("dwFileAttributes", _wt.DWORD)] + [(n, _wt.DWORD) for n in (
            "c1", "c2", "a1", "a2", "w1", "w2", "serial", "size_hi", "size_lo", "links", "index_hi", "index_lo")]
    _k32.GetFileInformationByHandle.argtypes = [_wt.HANDLE, ctypes.POINTER(_BHFI)]
    _INVALID_HANDLE = _wt.HANDLE(-1).value


def _pin_dir(path):
    """Windows: open the folder itself (never a link's target) sharing read and write but NOT delete, so nobody can
    rename or remove it, and so swap it for a junction, while it is listed and emptied. Returns the handle, or None
    when it can't be opened or is no longer a plain folder (then it is left alone). POSIX: True (nothing to hold)."""
    if not IS_WIN:
        return True
    h = _k32.CreateFileW(str(path), 0x1 | 0x80, 0x1 | 0x2, None, 3, 0x02000000 | 0x00200000, None)
    # FILE_LIST_DIRECTORY|FILE_READ_ATTRIBUTES (attribute-only handles skip the sharing check, so they would block
    # nothing), FILE_SHARE_READ|WRITE (no DELETE), OPEN_EXISTING, BACKUP_SEMANTICS (folders)|OPEN_REPARSE_POINT
    if not h or h == _INVALID_HANDLE:
        return None
    info = _BHFI()
    ok = _k32.GetFileInformationByHandle(h, ctypes.byref(info))
    attrs = info.dwFileAttributes
    if not ok or attrs & FILE_ATTRIBUTE_REPARSE_POINT or not attrs & FILE_ATTRIBUTE_DIRECTORY:
        _k32.CloseHandle(h)
        return None
    return h


def remove_tree(path) -> None:
    """Delete a folder bottom-up without ever following a junction or symlink, the folder given included: a link is
    removed as a link only (rmdir for a directory link, unlink for a file link; COORDINATION rule 15). On Windows each
    folder is held open (no delete sharing) while it is listed and emptied, so it can't be swapped for a junction
    between the check and the walk. Best effort: files still in use stay."""
    try:
        is_link, is_dir = _kind(path)
    except OSError:
        return
    try:
        if is_link or not is_dir:
            remove = os.rmdir if is_link and is_dir else os.unlink
            try:
                remove(path)
            except PermissionError:
                if is_link:
                    raise
                # read-only (e.g. git pack files): make writable, retry once; never through a link swapped in meanwhile
                if _kind(path)[0]:
                    return
                try:
                    os.chmod(path, stat.S_IWRITE, follow_symlinks=False)
                except NotImplementedError:          # Windows before Python 3.13: checked just above
                    os.chmod(path, stat.S_IWRITE)
                remove(path)
            return
    except OSError:
        return
    pin = _pin_dir(path)
    if pin is None:
        return
    try:
        try:
            entries = [e.path for e in os.scandir(path)]
        except OSError:
            return
        for e in entries:
            remove_tree(e)
    finally:
        if IS_WIN:
            _k32.CloseHandle(pin)
    try:
        os.rmdir(path)
    except OSError:
        pass


def queued_jobs(paths: Paths, bad: list | None = None, skip=frozenset()) -> list[dict]:
    """Queued jobs in run order. Files that are not a JSON object are skipped (and listed in `bad` if given);
    folders and the names in `skip` are not read at all."""
    jobs = []
    for f in paths.queue.glob("*.json"):
        if f.name in skip or not f.is_file():
            continue
        j = read_json(f)
        if isinstance(j, dict):
            j["_file"] = f
            jobs.append(j)
        elif bad is not None and f.exists():
            bad.append(f)
    pri = lambda j: j.get("priority", 0) if isinstance(j.get("priority", 0), int) else 0  # noqa: E731
    ns = lambda j: j.get("queued_ns") if isinstance(j.get("queued_ns"), int) else 0  # noqa: E731
    jobs.sort(key=lambda j: (-pri(j), str(j.get("queued_at", "")), ns(j), str(j.get("id", ""))))
    return jobs


SUITE_CLASSES = ("suite", "gate")


def owner_suites(paths: Paths, owner: str) -> list[tuple[str, dict]]:
    """(state, job) of this owner's queued or running full suites (class suite or gate)."""
    out = []
    for state, d in (("running", paths.running), ("queued", paths.queue)):
        for f in d.glob("*.json"):
            j = read_json(f)
            if isinstance(j, dict) and f.stem == j.get("id") and j.get("owner") == owner \
                    and j.get("heavy") in SUITE_CLASSES:
                out.append((state, j))
    return out


def add_job(paths: Paths, job: dict, cfg: dict | None = None, replace: str | None = None,
            allow_second: bool = False) -> dict:
    """Queue a job. Machine-load rule (COORDINATION, 2026-10-17): one full suite per owner at a time — a second
    `suite`/`gate` of the same owner is refused unless it `replace`s the first (that one is cancelled) or says
    `allow_second` (recorded, shown by status). The executor's gate suites are exempt (a gate cancels nothing)."""
    cfg = cfg or load_config(paths)
    j = validate(job, cfg)
    paths.ensure()
    jid = j["id"]
    for d in (paths.queue, paths.running, paths.done):
        if (d / f"{jid}.json").exists():
            raise JobError(f"id {jid} already exists in {d.name}/")
    exe = resolve_exe(j["argv"][0], Path(j["cwd"]), cfg, j["env"].get("PATH"))   # fail now, not hours later
    check_batch_args(exe, j["argv"][1:])
    check_command_line(exe, j["argv"][1:])
    if replace is not None and (j["heavy"] not in SUITE_CLASSES):
        raise JobError("--replace is for full suites (class suite or gate): it cancels your other suite")
    if j["heavy"] in SUITE_CLASSES and not (j["heavy"] == "gate" and j["owner"] == GATE_OWNER):
        others = owner_suites(paths, j["owner"])
        if replace is not None:
            if replace not in [o["id"] for _s, o in others]:
                raise JobError(f"--replace {replace}: not a queued or running suite of owner {j['owner']} "
                               f"(theirs: {', '.join(o['id'] for _s, o in others) or 'none'})")
            others = [(s, o) for s, o in others if o["id"] != replace]
        if others and not allow_second:
            names = ", ".join(f"{o['id']} ({s})" for s, o in others)
            raise JobError(f"owner {j['owner']} already has a full suite: {names}. One suite per owner at a time "
                           f"(machine-load rule): `cancel <id>`, or queue this one with `--replace <id>` (cancels "
                           f"that one), or `--allow-second` if both must run")
        if allow_second and others:
            j["allow_second"] = [o["id"] for _s, o in others]
        if replace is not None:
            cancel_job(paths, replace)
            j["replaces"] = replace
    write_json(paths.queue / f"{jid}.json", j)
    return j


def find(paths: Paths, jid: str) -> tuple[str, dict] | None:
    for state, d in (("queued", paths.queue), ("running", paths.running), ("done", paths.done)):  # the way jobs move
        j = read_json(d / f"{jid}.json")
        if j is not None:
            return state, j
    return None


def cancel_job(paths: Paths, jid: str) -> str:
    """Cancel a queued job at once, or ask the runner to stop a running one. Returns what happened."""
    q = paths.queue / f"{jid}.json"
    claim = paths.queue / f"{jid}.json.cancelling"
    try:
        os.replace(q, claim)                        # atomic: whoever moves the file first owns it
    except FileNotFoundError:
        pass
    else:
        j = read_json(claim) or {"id": jid}
        rec = done_record(j, "cancelled", "cancelled before it started", log=None)
        write_json(paths.done / f"{jid}.json", rec)
        unlink(claim)
        return "cancelled (was queued)"
    if (paths.running / f"{jid}.json").exists():
        paths.cancel(jid).write_text(now_iso(), encoding="utf-8")
        return "cancel requested (running: the runner stops it within seconds)"
    if (paths.done / f"{jid}.json").exists():
        return "already finished"
    raise JobError(f"no job {jid}")


def fmt_secs(s) -> str:
    s = int(round(s or 0))
    h, rest = divmod(s, 3600)
    m, s = divmod(rest, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s" if m else f"{s}s"


PRESSURE_RAM_PCT = 85              # the machine's own brake: no new heavy job at >= 85% RAM
DELIBERATE = ("cancelled", "stopped")      # someone chose these: counted, never flagged


def pressure_threshold(v) -> float:
    """config `pressure_ram_pct`: a number in (0, 100], else the default (a bad value never breaks a verdict)."""
    if isinstance(v, bool):                  # JSON true is not 1%
        return float(PRESSURE_RAM_PCT)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return float(PRESSURE_RAM_PCT)
    return f if 0 < f <= 100 else float(PRESSURE_RAM_PCT)


JOB_SHARE = 0.5                    # the job's own peak is at least half the RAM in use: its own memory, a code verdict


def fmt_mb(mb) -> str:
    return f"{round(mb)} MB" if round(mb) < 1024 else f"{mb / 1024:.1f} GB"


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _job_mb(run: dict):
    """The job's own memory at the machine's RAM peak (its Job Object commit sampled with that peak); else its peak
    over the whole run (an over-estimate: memory it had freed by then still counts); else None (POSIX)."""
    at = _num(run.get("job_mb_at_ram_peak"))
    return at if at is not None else _num(run.get("peak_ram_mb"))


def _job_filled_it(run: dict) -> bool:
    """The job's own memory is at least JOB_SHARE of the RAM in use at the machine's peak. Commit, not resident
    pages, so still an estimate; unknown figures (POSIX, old records) never say "job"."""
    mb, total, pct = _job_mb(run), _num(run.get("ram_total_mb")), _num(run.get("peak_sys_ram_pct"))
    return bool(mb and total and pct and mb >= JOB_SHARE * pct / 100 * total)


def memory_pressure(status: str, iterations: list, at=PRESSURE_RAM_PCT) -> dict | None:
    """Why the system RAM sampled while runs were running makes this verdict worth a note, else None:
    {"ram_peak_pct", "job_mb", "total_mb", "cause"}. cause "machine": other programs filled RAM (re-check before
    trusting a failure); "job": the job's own memory filled it (a code verdict).
    - failed / timeout: only when EVERY failed run ran at >= `at` (a failed run at 60% is a code verdict, a run with
      no sample never started); "job" if any failed run filled RAM itself, else "machine" with the lowest peak.
    - passed: the run with the highest peak (a note only).
    - anything else (cancelled, stopped, error, stranded) is a choice or a runner problem: None."""
    at = pressure_threshold(at)
    if status == "passed":
        runs = [i for i in iterations if _num(i.get("peak_sys_ram_pct")) is not None]
        if not runs:
            return None
        pick = max(runs, key=lambda i: i["peak_sys_ram_pct"])
        if pick["peak_sys_ram_pct"] < at:
            return None
        cause = "job" if _job_filled_it(pick) else "machine"
    elif status in ("failed", "timeout"):
        runs = [i for i in iterations if not i.get("passed")]
        if not runs or any(_num(i.get("peak_sys_ram_pct")) is None for i in runs):
            return None
        if any(i.get("outcome") in ("wait_timeout", "error") for i in runs):   # never ran: RAM explains nothing
            return None
        if min(i["peak_sys_ram_pct"] for i in runs) < at:
            return None
        own = [i for i in runs if _job_filled_it(i)]
        if own:
            cause, pick = "job", max(own, key=_job_mb)
        else:
            cause, pick = "machine", min(runs, key=lambda i: i["peak_sys_ram_pct"])
    else:
        return None
    return {"ram_peak_pct": pick["peak_sys_ram_pct"], "job_mb": _job_mb(pick),
            "total_mb": _num(pick.get("ram_total_mb")), "cause": cause}


def _pressure_note(rec: dict) -> str:
    pk = rec.get("pressure_ram_peak_pct")
    if pk is None:
        return ""
    job, total = _num(rec.get("pressure_job_mb")), _num(rec.get("pressure_ram_total_mb"))
    of = f" of {fmt_mb(total)}" if total else ""
    mine = rec.get("pressure_cause") == "job" and job
    if rec.get("status") == "passed":
        who = f", mostly this job: {fmt_mb(job)}" if mine else f", this job {fmt_mb(job)}" if job else ""
        return f" (note: RAM peak {pk}% during the run{who})"
    if mine:
        return f" (RAM peak {pk}%, mostly this job: {fmt_mb(job)}{of}; a code verdict)"
    who = f", this job {fmt_mb(job)}{of}" if job else ""
    return f" (under memory pressure: RAM peak {pk}%{who}; re-check before treating it as a code verdict)"


def headline(rec: dict) -> str:
    """One line a resuming session can stop at: the result first, then which job and how long. A verdict reached
    while RAM was nearly full says so before anything else, and whose memory it was."""
    who = f"{rec.get('id')}" + (f", {rec['owner']}" if rec.get("owner") else "")
    return (f"{str(rec.get('status')).upper()}{_pressure_note(rec)}: {rec.get('summary')}  "
            f"[{who}; ran {fmt_secs(rec.get('run_s'))}]")


def done_record(job: dict, status: str, summary: str, log: str | None, **extra) -> dict:
    """The done\\<id>.json record. Keys are ordered for reading at a glance: the result first (headline, status,
    summary), then counts and peaks, then the long details (events, tail, every run, the job spec) last."""
    its = job.get("iterations", [])
    mp = memory_pressure(status, its, extra.pop("pressure_at", PRESSURE_RAM_PCT))
    note = {} if mp is None else {k: v for k, v in (
        ("pressure_ram_peak_pct", mp["ram_peak_pct"]), ("pressure_cause", mp["cause"]),
        ("pressure_job_mb", mp["job_mb"]), ("pressure_ram_total_mb", mp["total_mb"])) if v is not None}
    spec = {k: job.get(k) for k in ("argv", "cwd", "env", "heavy", "timeout_s", "max_wait_s", "stop", "pass_regex",
                                    "fail_regex", "priority", "max_attempts")}
    rec = {
        "headline": None, "status": status, "passed": status == "passed", "summary": summary,
        "pressure": mp is not None and mp["cause"] == "machine", **note,
        "id": job.get("id"), "title": job.get("title"), "owner": job.get("owner"), "finished_at": now_iso(),
        "exit_code": its[-1].get("rc") if its else None, "iterations_run": len(its),
        "passes": sum(1 for i in its if i.get("passed")),
        "run_s": round(sum(i.get("run_s") or 0 for i in its), 1),
        "wait_s": round(sum(i.get("wait_s") or 0 for i in its), 1),
        "log": log, "peak": extra.pop("peak", None),
        "queued_at": job.get("queued_at"), "started_at": job.get("started_at"), "attempts": job.get("attempts", 0),
        "schema": SCHEMA, "events": job.get("events", []), "tail": extra.pop("tail", []),
    }
    rec.update(extra)
    rec["iterations"], rec["job"] = its, spec
    rec["headline"] = headline(rec)
    return rec
