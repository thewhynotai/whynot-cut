"""Paths, config, job validation and atomic file IO for wnc-queue (stdlib only)."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import secrets
import shutil
import stat
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

IS_WIN = os.name == "nt"
TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
TASK_NAME = "WNC-Queue"
SCHEMA = 1

CLASSES = ("cpu", "gpu", "suite", "none")          # heavy.sh slot; "none" = light (CI watch, download): no slot
HEAVY_KIND = {"cpu": "job", "gpu": "gpu", "suite": "suite"}
MODES = ("exit", "repeat", "until_fail", "until_streak", "until_match")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
# Ids that would collide with the runner's own files in running/ and logs/ (<id>.spec.json, <id>.json.dup-N …),
# a trailing dot (Windows drops it, so "t." would be job t's files) and "runner" (logs/runner.log is the runner's).
RESERVED_ID_RE = re.compile(r"\.(spec|started|cancel|refused|cancelling)$|\.json(\.|$)|\.log(\.\d+)?$|\.dup-\d+$"
                            r"|\.$|^runner$", re.I)
MAX_ARGV_CHARS = 32767                              # the Windows command-line limit

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
# rmdir /s and rd /s. Over-cautious on purpose: a refused job is cheap, a followed junction is not.
DESTRUCTIVE_RE = re.compile(r"\brm\s+(?:\S+\s+)*?(?:-(?=[a-z]*r)[a-z]+|--recursive)(?=[\s\"',)\]]|$)"
                            r"|\bremove-item\b.*\s-r[a-z]*\b"
                            # robocopy by name or by its full path (C:\Windows\System32\robocopy.exe)
                            r"|(?<![\w.-])robocopy(?:\.exe)?[\"']?\s(?:.*?\s)?/(?:mir|mov|move|purge)"
                            r"(?=[\s/:\"',)\]]|$)", re.I | re.S)     # re.S: also across newlines in -c code
# cmd's rd/del/erase as a command (not a path segment like D:/x/del/s.py), then a /s switch anywhere after it
# (rd /s /q x, del /q/s x, rd/s/q x). Two linear searches instead of one regex: a crafted argv can't make it slow.
CMD_DELETE_RE = re.compile(r"(?<![\w./\\:-])(?:rmdir|rd|del|erase)(?:\.exe)?(?=[\s/\"']|$)", re.I)
SWITCH_S_RE = re.compile(r"(?:^|\s|(?<![\w./\\:-])(?:rmdir|rd|del|erase)(?:\.exe)?)(?:/[a-z]+)*/s(?=[\s/\"',)\]]|$)",
                         re.I)                      # also a later name glued to its switch: "... & rd/s/q build"


def is_destructive(text: str) -> bool:
    if DESTRUCTIVE_RE.search(text):
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
    return shutil.which("bash")


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
        "slot_refresh_s": 600,                          # how often; heavy.sh takes over slots older than 3 h
    }
    try:
        user = json.loads(paths.config.read_text(encoding="utf-8-sig"))
        if isinstance(user, dict):
            cfg.update({k: v for k, v in user.items() if k in cfg})
    except (OSError, ValueError):
        pass
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


def remove_tree(path) -> None:
    """Delete a folder bottom-up without ever following a junction or symlink, the folder given included: a link is
    removed as a link only (rmdir for a directory link, unlink for a file link; COORDINATION rule 15). Best effort:
    files still in use stay."""
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
                os.chmod(path, stat.S_IWRITE)     # read-only (e.g. git pack files): make writable, retry once
                remove(path)
            return
        entries = [e.path for e in os.scandir(path)]
    except OSError:
        return
    for e in entries:
        remove_tree(e)
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


def add_job(paths: Paths, job: dict, cfg: dict | None = None) -> dict:
    cfg = cfg or load_config(paths)
    j = validate(job, cfg)
    paths.ensure()
    jid = j["id"]
    for d in (paths.queue, paths.running, paths.done):
        if (d / f"{jid}.json").exists():
            raise JobError(f"id {jid} already exists in {d.name}/")
    exe = resolve_exe(j["argv"][0], Path(j["cwd"]), cfg, j["env"].get("PATH"))   # fail now, not hours later
    check_batch_args(exe, j["argv"][1:])
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


def headline(rec: dict) -> str:
    """One line a resuming session can stop at: the result first, then which job and how long."""
    who = f"{rec.get('id')}" + (f", {rec['owner']}" if rec.get("owner") else "")
    return f"{str(rec.get('status')).upper()}: {rec.get('summary')}  [{who}; ran {fmt_secs(rec.get('run_s'))}]"


def done_record(job: dict, status: str, summary: str, log: str | None, **extra) -> dict:
    """The done\\<id>.json record. Keys are ordered for reading at a glance: the result first (headline, status,
    summary), then counts and peaks, then the long details (events, tail, every run, the job spec) last."""
    its = job.get("iterations", [])
    spec = {k: job.get(k) for k in ("argv", "cwd", "env", "heavy", "timeout_s", "max_wait_s", "stop", "pass_regex",
                                    "fail_regex", "priority", "max_attempts")}
    rec = {
        "headline": None, "status": status, "passed": status == "passed", "summary": summary,
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
