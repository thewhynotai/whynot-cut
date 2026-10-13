"""Shared helpers: paths, timing math, JSON I/O, logging, project status.

Timing policy (used everywhere):
  * Internal time unit is integer MILLISECONDS taken straight from SRT / Whisper.
  * Sequence frame = round_half_up(ms * 24 / 1000), computed from the absolute
    time every time (never by accumulating durations), so there is no drift.
  * Source frame (for footage that is not 24 fps) = round_half_up(ms * src_fps / 1000).
"""
from __future__ import annotations

import contextlib
import contextvars
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from fractions import Fraction
from pathlib import Path

from .plat import IS_WIN, clients_root_setting, engine_home, native_path, venv_python as _venv_python

PLUGIN_DIR = Path(__file__).resolve().parents[3]  # engine/reel/lib/common.py -> plugin root
SKILL_DIR = PLUGIN_DIR  # back-compat name
CONFIG_DIR = PLUGIN_DIR / "config" / "defaults"
PROFILES_DIR = PLUGIN_DIR / "profiles"
TEMPLATES_DIR = PLUGIN_DIR / "templates"


# Machine state (venv, Whisper models, ffmpeg, bridge queues) lives OUTSIDE the plugin, which is replaced on update:
# `engine_home()` (re-exported from plat) resolves it on every call, so a WHYNOT_HOME set after import is honoured
# (3.0 T2.17, engine MI-8: a long-lived `reel serve` must never keep a home computed at import time).


def models_dir() -> Path:
    """Whisper / face models: <engine home>/models."""
    return engine_home() / "models"


def __getattr__(name: str):
    # Back-compat for one release (3.0): `common.ENV_DIR` was a constant computed at import. It now resolves live;
    # new code calls engine_home(). Remove in 3.1.
    if name == "ENV_DIR":
        return engine_home()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def clients_root() -> Path | None:
    """Folder that holds the client folders, so `--root` can be just a client's name: the plugin option /
    WHYNOT_CLIENTS_ROOT, else `clients_root` in the preferences file (e.g. ~/.claude/whynot-cut.local.md)."""
    explicit = clients_root_setting()
    if explicit:
        return explicit
    from .settings import load
    v = load().get("clients_root")
    return Path(native_path(str(v))).expanduser() if v else None


def client_folders(base: Path | None) -> list[Path]:
    """Client folders (have both assets/ and data/) directly inside base."""
    try:
        return sorted(p for p in base.iterdir() if (p / "assets").is_dir() and (p / "data").is_dir()) if base else []
    except OSError:
        return []


def resolve_root(root: str | None) -> str | None:
    """A --root that is not an existing path is looked up by name inside clients_root."""
    if not root:
        return root
    root = native_path(root)
    p, base = Path(root).expanduser(), clients_root()
    if not p.exists() and not p.is_absolute() and base and (base / p).is_dir():
        return str(base / p)
    return root

SEQ_FPS = 24   # default only: the client's sequence-settings.json decides -> seq_fps()
TPS = 254016000000   # Premiere ticks per second


def seq_rate(ctx: "Context | None" = None) -> tuple[int, bool]:
    """(timebase, ntsc) of the client's sequence: profile sequence-settings.json general.timebase / general.ntsc.
    29.97 fps = (30, True), 23.976 = (24, True), 25 = (25, False). Cached on the Context (one request), never per
    process: a long-lived process gets a fresh Context per request and so sees an edited profile."""
    return (ctx or current_context()).seq_rate()


def seq_fps(ctx: "Context | None" = None) -> float:
    """The sequence frame rate as a number (29.97002997... for NTSC 30)."""
    tb, ntsc = seq_rate(ctx)
    return tb * 1000 / 1001 if ntsc else float(tb)


def fps_fraction(fps: float | Fraction) -> Fraction:
    return Fraction(fps).limit_denominator(1001000)


def fps_arg(fps: float | None = None) -> str:
    """ffmpeg rate string: 30000/1001, 25 ..."""
    fr = fps_fraction(seq_fps() if fps is None else fps)
    return f"{fr.numerator}/{fr.denominator}" if fr.denominator != 1 else str(fr.numerator)


def ticks_per_frame(fps: float | None = None) -> int:
    """Premiere ticks of one frame (exact for 23.976 / 24 / 25 / 29.97 / 30 / 50 / 59.94 / 60)."""
    return round(Fraction(TPS) / fps_fraction(seq_fps() if fps is None else fps))


# --- frame size (3.0 T2.8, IM-16): the client's sequence-settings.json decides, never a literal 1080x1920 ---
DEFAULT_FRAME_SIZE = (1080, 1920)    # only when the settings carry no size at all (the shipped default says 1080x1920)
MAX_FRAME_SIDE = 16384


def frame_size(paths: "Paths | None" = None, ctx: "Context | None" = None) -> tuple[int, int]:
    """(width, height) in pixels of the client's sequence: sequence-settings.json general.frame_width / frame_height,
    config default <- shipped profile <- the client's reel-profile. `paths` names the client (its folder's profile);
    else `ctx`, else the current Context. Read now on every call (an edited profile is seen by the next request).
    A size the settings leave out is DEFAULT_FRAME_SIZE; one that is not a whole number from 1 to 16384 is a Guidance
    error naming the file and key (never a 0-pixel still or a ZeroDivisionError further on)."""
    if ctx is None:
        cur = current_context()
        ctx = Context(paths.root, cur.profile, cur.engine_home) if paths is not None else cur
    return frame_size_of(ctx.config("sequence-settings.json"))


def frame_size_of(seq_cfg: dict | None) -> tuple[int, int]:
    """frame_size() of an already loaded sequence-settings.json (the plan reads it once with its inputs): the same
    defaults and the same Guidance for a bad value (3.0 T2.16, T2.8 review minor 2)."""
    general = (seq_cfg or {}).get("general") or {}
    out = []
    for key, default in zip(("frame_width", "frame_height"), DEFAULT_FRAME_SIZE):
        v = general.get(key)
        if v is None and key not in general:
            out.append(default)
            continue
        if isinstance(v, str) and v.strip().isdigit():
            v = int(v)
        elif isinstance(v, float) and v.is_integer():
            v = int(v)
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= MAX_FRAME_SIDE:
            from .errors import Guidance
            raise Guidance(f"sequence-settings.json general.{key} is {v!r}: it must be a whole number of pixels "
                           f"(1 to {MAX_FRAME_SIDE})",
                           f"Fix `general.{key}` in the client's reel-profile/sequence-settings.json "
                           f"(1080 and 1920 for a 9:16 reel, 1080 and 1350 for 4:5), then run this again",
                           where="sequence-settings.json")
        out.append(v)
    return out[0], out[1]

STATUSES = [
    "NOT_STARTED", "INPUTS_DISCOVERED", "INPUTS_VALIDATED", "CLIENT_DATABASE_READY",
    "TRANSCRIBED", "ANALYZED", "EDIT_PLAN_READY", "AWAITING_APPROVAL",
    "ASSETS_GENERATED", "PROJECT_ASSEMBLED", "QC_PASSED", "READY_FOR_HUMAN_EDITOR", "DELIVERED",
    "BLOCKED",
]
# a clip whose edit is finished: the client board shows it done, `reel next` marks it STALE when inputs change after
DONE_STATUSES = ("QC_PASSED", "READY_FOR_HUMAN_EDITOR", "DELIVERED")

PROJECT_SUBDIRS = [
    "00_inputs", "01_analysis", "02_transcription",
    "03_broll/existing-assets", "03_broll/generated-assets",
    "03_broll/educational-graphics", "03_broll/typography",
    "04_after_effects/project", "04_after_effects/scripts",
    "04_after_effects/compositions", "04_after_effects/assets",
    "05_photoshop/layered-assets", "05_photoshop/scripts",
    "06_audio/music", "06_audio/sfx",
    "07_premiere/project", "07_premiere/interchange", "07_premiere/media",
    "08_quality_control", "09_handoff", "logs",
]

VIDEO_EXT = {".mp4", ".mov", ".mxf", ".m4v", ".avi", ".mkv"}
AUDIO_EXT = {".wav", ".aif", ".aiff", ".mp3", ".m4a", ".aac", ".flac"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".heic", ".psd"}
RAW_IMAGE_EXT = {".arw", ".cr2", ".cr3", ".nef", ".dng", ".raf"}
FONT_EXT = {".otf", ".ttf", ".ttc", ".woff", ".woff2"}
DOC_EXT = {".md", ".markdown", ".txt", ".rtf", ".docx", ".pdf", ".json", ".yaml", ".yml"}
SUB_EXT = {".srt", ".vtt", ".ass"}


# --------------------------------------------------------------------------- time
def round_half_up(fr: Fraction) -> int:
    return int((fr + Fraction(1, 2)).__floor__())


def ms_to_frame(ms: int, fps: float | Fraction | None = None) -> int:
    return round_half_up(Fraction(int(ms)) * fps_fraction(seq_fps() if fps is None else fps) / 1000)


def frame_to_ms(frame: int, fps: float | Fraction | None = None) -> int:
    return round_half_up(Fraction(int(frame)) * 1000 / fps_fraction(seq_fps() if fps is None else fps))


_TS = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")


def parse_ts(ts: str) -> int:
    """'00:01:02,345' or '00:01:02.345' -> ms: the strict SRT grammar (HH:MM:SS plus a 1-3 digit fraction) is checked
    here, the parsing is media_util.parse_time's (one parser: T2.17, MI-7)."""
    if not _TS.fullmatch(ts.strip()):
        raise ValueError(f"Bad timestamp: {ts!r}")
    from .media_util import parse_time
    return parse_time(ts)


def fmt_ts(ms: int, sep: str = ",") -> str:
    ms = int(ms)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, rem = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{rem:03d}"


def frame_to_tc(frame: int, fps: float | None = None) -> str:
    """Non-drop-frame timecode at the nominal rate (29.97 counts 30 frames per timecode second)."""
    s, f = divmod(int(frame), round(seq_fps() if fps is None else fps))
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


# --------------------------------------------------------------------------- io
def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


_IO_RETRIES = 50                      # x ~10 ms: Windows refuses to open/replace a file another process is replacing


def _retry(fn):
    """Run fn, retrying a few ms later on PermissionError (Windows: the file is being replaced by a parallel writer)."""
    import time
    for k in range(_IO_RETRIES):
        try:
            return fn()
        except PermissionError:
            if k == _IO_RETRIES - 1:
                raise
            time.sleep(0.005 + 0.005 * (k % 4))


def read_json(path: Path, default=None):
    """The JSON in path (default when it does not exist). A UTF-8 BOM is accepted (PowerShell 5.1 writes one); a file
    that is not valid JSON or not UTF-8 raises errors.FileFormatError (a ValueError) naming the file and line (T2.2)."""
    from .errors import FileFormatError, decode_position
    path = Path(path)
    if not path.exists():
        return default

    def load():
        with open(path, "rb") as f:
            return f.read()
    try:
        data = _retry(load)
    except FileNotFoundError:
        return default
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        line, col = decode_position(data, e)
        raise FileFormatError(path, line, col, "not UTF-8 text (save it as UTF-8)") from None
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise FileFormatError(path, e.lineno, e.colno, e.msg) from None


def write_json(path: Path, data) -> Path:
    """Atomic write: a temp file with a unique name next to the target (parallel writers never share it), then
    os.replace, retried while another process holds the target (gate G3: parallel subagents writing clip-ids.json)."""
    import secrets
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}-{secrets.token_hex(4)}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        _retry(lambda: os.replace(tmp, path))
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return path


# ---- 3.0 T2.4 (engine IM-11, MI-23): read-modify-write of a shared file under its per-file OS lock (lib/file_lock.py)
from .file_lock import locked as file_locked  # noqa: E402  (stdlib + lib.errors only: no import cycle)


def update_json(path: Path, fn, default=None, wait_s: float | None = None):
    """Read-modify-write of a file other processes update too (parallel subagents of one session), holding
    `<file>.lock` for the whole cycle so no update is lost. fn gets the current document (a deep copy of `default`
    when the file does not exist) and returns the new one, or None after changing it in place. Returns what was
    written."""
    import copy
    with file_locked(path, wait_s):
        cur = read_json(path)
        if cur is None:
            cur = copy.deepcopy(default)
        new = fn(cur)
        doc = cur if new is None else new
        write_json(path, doc)
        return doc
# ---- end T2.4


def write_text(path: Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def sha1_head(path: Path, nbytes: int = 4 * 1024 * 1024) -> str:
    """Fast fingerprint: size + first/last 4 MB. Good enough to detect changed inputs."""
    path = Path(path)
    h = hashlib.sha1()
    size = path.stat().st_size
    h.update(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(nbytes))
        if size > nbytes:
            f.seek(max(0, size - nbytes))
            h.update(f.read(nbytes))
    return h.hexdigest()


def is_junk(p: Path) -> bool:
    n = p.name
    return n.startswith(("._", ".", "~$")) or n in {".DS_Store", "Thumbs.db", "desktop.ini", "Icon\r"}


def slug(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s.upper() or "VIDEO"


def short_hash(text: str, n: int = 6) -> str:
    """Upper-case hex prefix of the SHA-1 of the NFC text (macOS NFD names hash like Windows NFC ones)."""
    return hashlib.sha1(unicodedata.normalize("NFC", text).encode("utf-8")).hexdigest()[:n].upper()


def stable_id(name: str, prefix: str) -> str:
    """Project id from a file stem (episodes: prefix EP, raw clips: CLIP). ASCII names keep slug() (EP12 -> EP12,
    "Dr Sherif intro" -> DR_SHERIF_INTRO); names with other letters (Arabic) or none get a short hash, because slug()
    drops those letters and two such names would collide: <prefix>_<slug>_<hash>, or <prefix>_<hash>."""
    stem = unicodedata.normalize("NFC", name)
    s = slug(stem)
    if s != "VIDEO" and not re.search(r"[^\x00-\x7F]", stem):
        return s
    h = short_hash(stem)
    return f"{prefix}_{s}_{h}" if s not in ("", "VIDEO") else f"{prefix}_{h}"


# --------------------------------------------------------------------------- tools
def venv_python() -> Path:
    return _venv_python(engine_home())


FFMPEG_OVERRIDES = ("WHYNOT_FFMPEG", "NH_FFMPEG")


def ffmpeg_choice() -> dict:
    """{path, source, bad_override}: which ffmpeg the engine runs (3.0 T2.15, MI-18). An override (WHYNOT_FFMPEG, or
    the 2.x NH_FFMPEG; the binary or, like state.json `ffmpeg.path`, its folder) > the pinned ffmpeg in the engine
    home (state.json / ffmpeg/<ver>/, T2.1) > the 2.x <home>/ffmpeg file > the engine runtime's imageio-ffmpeg binary
    > PATH last: an old system build (Chocolatey, Homebrew) may lack filters the engine uses. bad_override names an
    override that is set but neither the binary nor a folder holding it."""
    from .plat import engine_ffmpeg
    bad = None
    for k in FFMPEG_OVERRIDES:
        v = os.environ.get(k)
        f = Path(native_path(v)).expanduser() if v else None
        if f is not None and f.is_dir():
            f = f / ("ffmpeg.exe" if IS_WIN else "ffmpeg")
        if f is not None and f.is_file():
            return {"path": str(f), "source": f"override {k}", "bad_override": None}
        if v and not bad:
            bad = f"{k}={v}"
    pinned = engine_ffmpeg(engine_home())
    legacy = engine_home() / "ffmpeg"
    for src, cand in (("pinned (engine home)", pinned and str(pinned)), ("engine home (2.x)", str(legacy))):
        if cand and Path(cand).is_file():
            return {"path": cand, "source": src, "bad_override": bad}
    try:
        import imageio_ffmpeg  # type: ignore
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return {"path": exe, "source": "engine runtime (imageio-ffmpeg)", "bad_override": bad}
    except Exception:  # noqa: BLE001
        pass
    w = shutil.which("ffmpeg")
    return {"path": w, "source": "PATH" if w else None, "bad_override": bad}


def ffmpeg_exe() -> str | None:
    """The ffmpeg the engine runs (ffmpeg_choice), or None."""
    return ffmpeg_choice()["path"]


def run(cmd, check=True, capture=True, timeout=None, **kw) -> subprocess.CompletedProcess:
    if timeout is None:              # T2.15 (MI-17): an ffmpeg call on a corrupt file or a stalled share never hangs
        from .media_util import ff_timeout
        timeout = ff_timeout(cmd)
    kw.setdefault("errors", "replace")    # Gate 2: a tool's non-UTF-8 output (ANSI code page) never raises on decode
    return subprocess.run(cmd, check=check, capture_output=capture, text=True, timeout=timeout, **kw)


# --------------------------------------------------------------------------- paths
STRICT_ID = re.compile(r"[A-Za-z0-9._-]+")        # every id the engine hands out (clip ids, episodes, reels)
_BAD_ID = re.compile(r"[/\\:*?\"<>|\x00-\x1f]")        # `..` is refused as a whole id (the strip rule below), not inside a name


def check_project_id(vid, kind: str = "video id", strict: bool = False) -> str:
    """A project id is ONE plain folder name under output/projects (or output/episodes): never a path that climbs out
    into assets/ or data/ (Gate 2 B4). Engine ids are `[A-Za-z0-9._-]+`; a clip's raw file stem ("Dr Sherif intro",
    "Interview... part 2", a 2.x project folder kept as is) is also allowed for video ids (strict=False): no separators,
    drive colon, Windows-reserved characters, control characters, leading/trailing space or dot (so never `.` or `..`).
    `..` inside a name is fine: with no separator it cannot climb out."""
    v = str(vid)
    ok = bool(v) and not _BAD_ID.search(v) and v == v.strip(" .") and \
        (STRICT_ID.fullmatch(v) if strict else True)
    if not ok:
        from .errors import Guidance
        raise Guidance(f"invalid {kind} {v!r}: it must be one plain folder name (letters, digits, '.', '_', '-'; "
                       "no '/', '\\', ':'; not just dots)",
                       "Use the id that `reel inbox` (clips) or `reel episodes` (episodes) lists, e.g. C0239 or EP12.")
    return v


class Paths:
    """Resolves every location from the main client folder (contains assets/ and data/)."""

    def __init__(self, root: Path, video_id: str | None = None):
        self.root = Path(root).expanduser().resolve()
        self.assets = self.root / "assets"
        self.data = self.root / "data"
        self.output = self.root / "output"
        self.client_db = self.output / "client_database"
        self.video_id = video_id
        if video_id:
            check_project_id(video_id)
            self.project = self.output / "projects" / video_id

    def p(self, rel: str) -> Path:
        if not self.video_id:
            raise RuntimeError("video_id required for project paths")
        return self.project / rel

    def ensure_project(self):
        for d in PROJECT_SUBDIRS:
            self.p(d).mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- status
def status_path(paths: Paths) -> Path:
    return paths.p("08_quality_control/project-status.json")


def load_status(paths: Paths) -> dict:
    st = read_json(status_path(paths))
    if not st:
        st = {"video_id": paths.video_id, "status": "NOT_STARTED", "history": [],
              "stages": {}, "blockers": [], "created": now_iso()}
    return st


STATUS_HISTORY_MAX = 200              # project-status.json keeps the last 200 status changes


def set_status(paths: Paths, status: str, note: str = "", stage: str | None = None,
               outputs: list | None = None, blockers: list | None = None) -> dict:
    assert status in STATUSES, status
    with file_locked(status_path(paths)):          # T2.4: parallel subagents update one project's status
        st = load_status(paths)
        st["status"] = status
        st["updated"] = now_iso()
        st["history"] = (st.get("history") or [])[-(STATUS_HISTORY_MAX - 1):] + [
            {"status": status, "at": st["updated"], "note": note}]       # T2.15: capped, inside the lock
        if stage:
            st["stages"][stage] = {"done": status != "BLOCKED", "at": st["updated"],
                                   "note": note, "outputs": [str(o) for o in (outputs or [])]}
        if blockers is not None:
            st["blockers"] = blockers
        write_json(status_path(paths), st)
    return st


def log(paths: Paths | None, msg: str):
    line = f"[{now_iso()}] {msg}"
    print(line, file=sys.stderr)
    if paths is not None and paths.video_id:
        lp = paths.p("logs/pipeline.log")
        lp.parent.mkdir(parents=True, exist_ok=True)
        with open(lp, "a", encoding="utf-8") as f:
            f.write(line + "\n")


# --------------------------------------------------------------------------- client profiles
# A profile is a folder of JSON overrides with the same file names as config/defaults/ plus
# profile.json (id, prefix, domain) and notes.md (prose for Claude). Lookup, lowest -> highest:
#   config/defaults/<name>  <-  profiles/<id>/<name> (shipped seed)  <-  <client>/output/client_database/reel-profile/<name>
CLIENT_PROFILE_REL = "output/client_database/reel-profile"


class Context:
    """What one engine request works on (3.0 T2.17, engine MI-8): the client root, the --profile override, the engine
    home and the request's caches (the sequence rate). The CLI builds one per process (`set_context`); a long-lived
    process (`reel serve`) builds one per request and binds it with `use_context`, so two requests never share a
    client, a profile or a stale cache. Profile layers are read from disk on every `config()` call."""

    def __init__(self, root: Path | str | None = None, profile: str | None = None, home: Path | str | None = None):
        self.root = Path(root).expanduser().resolve() if root else None
        self.profile = profile
        self._home = Path(home).expanduser() if home else None
        self._rate: tuple[int, bool] | None = None

    def __repr__(self):
        return f"Context(root={self.root!s}, profile={self.profile!r}, home={self.engine_home!s})"

    @property
    def engine_home(self) -> Path:
        """An explicit home, else the live setting (env / plugin option), resolved now, never at import."""
        return self._home or engine_home()

    def active_profile(self, root: Path | None = None) -> str | None:
        """--profile > client's reel-profile/profile.json. A shipped profile (profiles/<id>/) applies only when it is
        named: by --profile or by the id in the client's own profile.json, never by the client folder's name."""
        if self.profile:
            return self.profile
        root = Path(root) if root else self.root
        if root:
            own = read_json(root / CLIENT_PROFILE_REL / "profile.json", {})
            if own.get("id"):
                return own["id"]
        return None

    def profile_dirs(self, root: Path | None = None) -> list[Path]:
        root = Path(root) if root else self.root
        dirs = []
        pid = self.active_profile(root)
        if pid and (PROFILES_DIR / pid).is_dir():
            dirs.append(PROFILES_DIR / pid)
        if root and (root / CLIENT_PROFILE_REL).is_dir():
            dirs.append(root / CLIENT_PROFILE_REL)
        return dirs

    def config(self, name: str) -> dict:
        """config/defaults/<name> <- shipped profile <- the client's reel-profile, merged (read now, not cached)."""
        cfg = read_json(CONFIG_DIR / name, {})
        for d in self.profile_dirs():
            over = read_json(d / name)
            if over is not None:
                cfg = deep_merge(cfg, over)
        return cfg

    def seq_rate(self) -> tuple[int, bool]:
        if self._rate is None:
            g = self.config("sequence-settings.json").get("general", {})
            self._rate = (int(g.get("timebase") or SEQ_FPS), bool(g.get("ntsc", False)))
        return self._rate


_PROCESS_CTX = Context()                     # the one-shot CLI's context (set_context)
_BOUND_CTX: contextvars.ContextVar = contextvars.ContextVar("whynot_context", default=None)   # per request / thread


_REQUIRE_BOUND = False                       # `reel serve` turns it on: no request may fall back to the process one


def require_bound_context(on: bool = True) -> None:
    """When on, current_context() raises unless a Context is bound (use_context): a long-lived process must never
    serve a request with the process-wide Context (T2.17, T6.2)."""
    global _REQUIRE_BOUND
    _REQUIRE_BOUND = bool(on)


def current_context() -> Context:
    """The Context bound by `use_context` (a long-lived process), else the process one from `set_context`."""
    ctx = _BOUND_CTX.get()
    if ctx is not None:
        return ctx
    if _REQUIRE_BOUND:
        raise RuntimeError("no request context bound — reel serve must bind one per request")
    return _PROCESS_CTX


def set_context(root: Path | None = None, profile: str | None = None) -> Context:
    """Called once by the CLI so every load_config() sees the right client. Returns the new Context."""
    global _PROCESS_CTX
    _PROCESS_CTX = Context(root, profile)
    return _PROCESS_CTX


@contextlib.contextmanager
def use_context(ctx: Context):
    """Bind ctx inside the block, for this thread / task only: how a long-lived process serves one request."""
    tok = _BOUND_CTX.set(ctx)
    try:
        yield ctx
    finally:
        _BOUND_CTX.reset(tok)


def deep_merge(base, over):
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = deep_merge(base[k], v) if k in base else v
        return out
    return over


def shipped_profiles() -> dict:
    out = {}
    for d in sorted(PROFILES_DIR.glob("*/profile.json")) if PROFILES_DIR.exists() else []:
        if d.parent.name.startswith("_"):
            continue
        out[d.parent.name] = read_json(d, {})
    return out


def active_profile(root: Path | None = None) -> str | None:
    """The current Context's profile id (see Context.active_profile)."""
    return current_context().active_profile(root)


def profile_dirs(root: Path | None = None) -> list[Path]:
    return current_context().profile_dirs(root)


def load_config(name: str, ctx: Context | None = None) -> dict:
    return (ctx or current_context()).config(name)


DEFAULT_PREFIX = "WN"          # 3.0 T3.10 (structure 8.3): no ASCII initials -> WN (the 2.x default was RE)
LEGACY_PREFIX = "RE"           # the 2.x default: 2.x clients without a stored prefix built <id>_RE_EDIT.prproj
# A stored prefix is honoured whenever it is safe in a file name (2.x stored free text: "N-H", "Dr_M", longer than 8):
# letters, digits, "_", "-", "." (not first, not last, no ".."), at most 24. Spaces, path separators, Windows-reserved
# characters (<>:"|?*) and control characters are refused, so the template's "<2-3 letters>" is not a prefix.
_PREFIX_OK = re.compile(r"\w[\w.-]{0,23}")
_HONORIFICS = {"dr", "doctor", "prof", "eng", "mr", "mrs", "ms", "miss", "sheikh", "the"}
# where a project's file names carry the tag: <id>_<TAG>_EDIT.prproj, the XML fallback <id>_<TAG>_EDIT[_base].xml,
# <id>_<TAG>_GFX.aep / <id>_<TAG>_MOTION.aep
_TAGGED_DIRS = ("07_premiere/project", "07_premiere/interchange", "04_after_effects/project")
_TAGGED_MAX_PROJECTS = 300


def valid_prefix(value) -> bool:
    """A prefix that is safe in a file name (see _PREFIX_OK): "SH", "N-H", "Dr_M" yes; "N H", "N/H", "<2-3 letters>"
    no."""
    v = str(value or "").strip()
    return bool(_PREFIX_OK.fullmatch(v)) and not v.endswith(".") and ".." not in v


def initials_prefix(name: str) -> str:
    """The file-name tag derived from a client folder's name (3.0 T3.10): the initials of its ASCII words (up to 3,
    a leading title such as Dr/Prof/Eng skipped when other words follow), the first two letters of a single word, else
    WN (an Arabic-only name). "Dr Mona Adel" -> MA, "Nour Hospital" -> NH, "Acme" -> AC, «عميل تجربة» -> WN."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9]*", unicodedata.normalize("NFKD", str(name or "")))
    while len(words) > 1 and words[0].lower() in _HONORIFICS:
        words = words[1:]
    if not words:
        return DEFAULT_PREFIX
    if len(words) == 1:
        return words[0][:2].upper()
    return "".join(w[0] for w in words[:3]).upper()


def marker_prefix(root: Path | None) -> str | None:
    """The prefix `reel scaffold` stored in the client's .whynot-client marker at creation (it survives a renamed
    folder), when it is file-name-safe."""
    if not root:
        return None
    try:
        v = json.loads((Path(root) / ".whynot-client").read_text(encoding="utf-8")).get("prefix")
    except (OSError, ValueError, AttributeError):
        return None
    return str(v).strip() if valid_prefix(v) else None


class _OutOfTime(Exception):
    pass


def existing_prefix(root: Path | None, deadline: float | None = None) -> str | None:
    """The tag the client's existing projects already use (so the engine finds them instead of building a second
    project next to them): <id>_<TAG>_EDIT.prproj, the XML fallback <id>_<TAG>_EDIT[_base].xml, <id>_<TAG>_GFX.aep,
    <id>_<TAG>_MOTION.aep. The most used tag wins, a tie goes to the most recent file. Bounded: one listing of
    output/projects (at most 300 projects) and one listing per tagged folder. Raises _OutOfTime past `deadline`
    (time.monotonic())."""
    import time as _time
    if not root:
        return None
    try:
        with os.scandir(Path(root) / "output" / "projects") as it:
            projects = sorted(e.name for e in it if e.is_dir())[:_TAGGED_MAX_PROJECTS]
    except OSError:
        return None
    seen: dict[str, list] = {}                        # tag -> [count, newest mtime]
    for pid in projects:
        if deadline is not None and _time.monotonic() >= deadline:
            raise _OutOfTime
        pat = re.compile(rf"{re.escape(pid)}_(.+?)_(?:EDIT|GFX|MOTION)(?:_base)?\.(?:prproj|xml|aep)", re.I)
        for sub in _TAGGED_DIRS:
            try:
                with os.scandir(Path(root) / "output" / "projects" / pid / sub) as it:
                    for e in it:
                        m = pat.fullmatch(e.name)
                        if not m or not valid_prefix(m.group(1)):
                            continue
                        try:
                            mt = e.stat().st_mtime
                        except OSError:
                            mt = 0.0
                        rec = seen.setdefault(m.group(1), [0, 0.0])
                        rec[0] += 1
                        rec[1] = max(rec[1], mt)
            except OSError:
                continue
    if not seen:
        return None
    return max(seen.items(), key=lambda kv: (kv[1][0], kv[1][1]))[0]


def derived_prefix(root: Path | None, deadline: float | None = None) -> str | None:
    """The prefix of a client whose reel-profile stores none, in this order (3.0 T3.10 review I2: never orphan an
    existing project): the one `reel scaffold` stored in the marker, else the tag its existing projects already use
    (existing_prefix: RE for most 2.x clients), else the initials of its folder name (initials_prefix), else WN.
    None only when `deadline` passed during the project scan."""
    if not root:
        return DEFAULT_PREFIX
    stored = marker_prefix(root)
    if stored:
        return stored
    try:
        found = existing_prefix(root, deadline)
    except _OutOfTime:
        return None
    return found or initials_prefix(Path(root).name)


def stored_prefix() -> str | None:
    """The client's reel-profile 'prefix' (profile.json), when it is file-name-safe."""
    v = str(load_config("profile.json").get("prefix") or "").strip()
    return v if valid_prefix(v) else None


def project_prefix() -> str:
    """File-name tag, e.g. C0238_NH_EDIT.prproj: profile.json 'prefix' (the client's stored one wins; `client-init`
    stores it), else derived_prefix (the marker's, the tag of the existing projects, the folder's initials, WN).
    Cached on the request's Context (the project scan lists output/projects)."""
    stored = stored_prefix()
    if stored:
        return stored
    ctx = current_context()
    cache = ctx.__dict__.setdefault("_prefix_cache", {})
    key = str(ctx.root) if ctx.root else ""
    if key not in cache:
        cache[key] = derived_prefix(ctx.root)
    return cache[key]


def source_range(paths) -> dict:
    """A video cut from a longer raw file, e.g. reel R02 = 02:04-02:59 of a full episode: 00_inputs/source.json
    {"footage": "data/Raw/EP02.mp4", "in_ms": 124000, "out_ms": 179000} (written by `reel range`).
    Every stage works on the transcript's clock (0 = the in-point); only reads of the raw file add `in_ms`, and the
    Premiere clips point into the original file (handles stay available to the editor). {} = the whole file."""
    if not getattr(paths, "video_id", None):
        return {}
    r = read_json(paths.p("00_inputs/source.json"), {}) or {}
    # also reads the podcast-mode schema (kind "episode_reel": rel/path + in_ms or offset_ms, out_ms or duration_ms)
    foot = r.get("footage") or r.get("rel") or r.get("path")
    if not foot:
        return {}
    i = int(r.get("in_ms", r.get("offset_ms", 0)) or 0)
    o = r.get("out_ms") or (i + int(r["duration_ms"]) if r.get("duration_ms") else None)
    return dict(r, footage=foot, in_ms=i, out_ms=int(o) if o else None)


def range_input_args(rng: dict) -> list:
    """ffmpeg input options (placed before -i) that read only the range; [] for the whole file."""
    if not rng:
        return []
    a = ["-ss", f"{rng.get('in_ms', 0) / 1000:.3f}"]
    if rng.get("out_ms"):
        a += ["-t", f"{(rng['out_ms'] - rng.get('in_ms', 0)) / 1000:.3f}"]
    return a


def spec_footage(paths, spec: dict) -> Path:
    """The raw file a compiled timeline spec plays (its `main_footage`, relative to the client root), or guidance when
    the spec has none: a plan compiled before 3.0 T2.2 (gap G71) could leave it null, and every later stage crashed."""
    from .errors import Guidance
    mf = (spec or {}).get("main_footage")
    if not mf:
        raise Guidance("01_analysis/timeline-spec.json has no main_footage (the raw file this video is cut from)",
                       "Set \"main_footage\" in the \"global\" block of 01_analysis/edit-decisions.json (e.g. "
                       "\"data/Raw/C0239.MP4\"), then run `reel plan` again", where=str(paths.p("01_analysis/timeline-spec.json")))
    f = Path(mf)
    return f if f.is_absolute() else Path(paths.root) / f


def content_domain() -> str:
    """The client's subject area from profile.json `domain` (medical | religious | general; default general).
    Decides which content review applies and how review sheets label glossary hits."""
    d = str(load_config("profile.json").get("domain") or "general").strip().lower()
    return d if d in ("medical", "religious", "general") else "general"


def brand_fallback(key: str) -> str:
    """Brand colour used only when the client database has no measured value."""
    return load_config("brand.json").get("fallback_colors", {}).get(key, {"primary": "#3A7BD5", "neutral_light": "#FFFFFF",
                                                                            "paper_tint": "#E6EEF8", "ink": "#1E2A3B"}[key])


def font_role_fallback() -> dict:
    return load_config("brand.json").get("font_roles_fallback", {})


CAPTION_HIDE_SAFE = ["broll_card", "logo_outro", "hook_title", "statement_highlight", "term_callout", "checklist",
                     "stat_card"]


def caption_hide_default() -> list:
    """Templates during which captions are hidden when edit-decisions don't say: the profile's style.json value, else
    every graphic that already shows words (a caption repeating or crossing them reads as a mistake)."""
    return list(load_config("style.json").get("captions_hidden_during") or CAPTION_HIDE_SAFE)


EDU_TEMPLATES = {"checklist", "broll_card", "broll_video"}


def still_category(template: str) -> str:
    """Folder under 03_broll/ for a template's stills (one place; every module asks this)."""
    return "educational-graphics" if template in EDU_TEMPLATES else "typography"
