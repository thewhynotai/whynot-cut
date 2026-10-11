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

STATUSES = [
    "NOT_STARTED", "INPUTS_DISCOVERED", "INPUTS_VALIDATED", "CLIENT_DATABASE_READY",
    "TRANSCRIBED", "ANALYZED", "EDIT_PLAN_READY", "AWAITING_APPROVAL",
    "ASSETS_GENERATED", "PROJECT_ASSEMBLED", "QC_PASSED", "READY_FOR_HUMAN_EDITOR",
    "BLOCKED",
]

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
    """'00:01:02,345' or '00:01:02.345' -> ms."""
    m = _TS.fullmatch(ts.strip())
    if not m:
        raise ValueError(f"Bad timestamp: {ts!r}")
    h, mi, s, frac = m.groups()
    return ((int(h) * 60 + int(mi)) * 60 + int(s)) * 1000 + int(frac.ljust(3, "0"))


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
    path = Path(path)
    if not path.exists():
        return default

    def load():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    try:
        return _retry(load)
    except FileNotFoundError:
        return default


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


def ffmpeg_exe() -> str | None:
    for cand in (os.environ.get("NH_FFMPEG"), shutil.which("ffmpeg"), str(engine_home() / "ffmpeg")):
        if cand and Path(cand).exists():
            return cand
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def run(cmd, check=True, capture=True, timeout=None, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=capture, text=True, timeout=timeout, **kw)


# --------------------------------------------------------------------------- paths
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


def set_status(paths: Paths, status: str, note: str = "", stage: str | None = None,
               outputs: list | None = None, blockers: list | None = None) -> dict:
    assert status in STATUSES, status
    st = load_status(paths)
    st["status"] = status
    st["updated"] = now_iso()
    st["history"].append({"status": status, "at": st["updated"], "note": note})
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


def current_context() -> Context:
    """The Context bound by `use_context` (a long-lived process), else the process one from `set_context`."""
    return _BOUND_CTX.get() or _PROCESS_CTX


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


def project_prefix() -> str:
    """File-name tag, e.g. C0238_NH_EDIT.prproj. From profile.json 'prefix' (default RE)."""
    return load_config("profile.json").get("prefix") or "RE"


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
