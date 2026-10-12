"""Install steps preflight, questions, settings, model, state, doctor and launch (3.0 T7.1, installer.md R.2 steps 1
and 9-12), the end-of-install checklist, and the registration of these plus `adobe` (adobe.py) and `fonts` (fonts.py).

preflight  read-only facts (ctx.facts): OS, free space on the engine drive (< 6 GB red: the install stops before any
           download; < 9 GB amber), a home path with non-ASCII letters or a space, Documents in OneDrive / iCloud,
           Claude Code, Adobe hosts, NVIDIA, an earlier install, Windows Smart App Control. A sandbox (--home) never
           reads the registry or probes processes; a dry run starts no process.
questions  the clients folder and the chat language, asked right after preflight (ID-6) so the long downloads run
           unattended: --clients-folder / --language, else the editor's preferences file, else the defaults
           (language `ar`, ID-4). The clients folder is never created here.
settings   `reel settings --init <home> --force --set clients_root=... --set language=... --set whisper_model=...`.
model      the Whisper model for this hardware, downloaded by a detached background `reel model-download`.
state      state.json: plugin, channel, installed_at, platform, uv, python, runtime, answers.
doctor     `reel doctor` (JSON) -> state.last_doctor; render_checklist() prints [OK] / [!!] / [XX] per step and the
           doctor's fixes.
launch     opens Claude on /whynot-cut:start (never in a sandbox).
Engine calls: <runtime python> -s -B <plugin>/engine/reel/cli.py <cmd> with the engine environment. Stdlib only.
"""
from __future__ import annotations

import json
import os
import platform as _platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from . import base, claude, runtime
from .adobe import EXT_ID, adobe_hosts, cep_extensions_dir, hosts_running, step_adobe  # noqa: F401 (re-exported)
from .fonts import FontRegistry, user_font_dir, step_fonts  # noqa: F401 (re-exported)

GB = 1024 ** 3
RED_GB, AMBER_GB = 6, 9  # without the model / with large-v3
ENGINE_TIMEOUT = 300  # settings, doctor
PREFS = "whynot-cut.local.md"
LANGUAGES = ("ar", "en")
MODELS = ("large-v3", "large-v3-turbo", "medium", "small")  # `reel model-download --model` choices
CLIENTS_FOLDER = "WhyNot Clients"
START_URL = "claude://code/new?q=%2Fwhynot-cut%3Astart"
START_MESSAGE = "Open Claude and type /whynot-cut:start"
START_MESSAGE_AR = "افتح Claude واكتب /whynot-cut:start"
# macOS (installer.md R.2): the first file access to Documents or an external drive brings a privacy (TCC) dialog
MAC_ALLOW_MESSAGE = ("The first time Claude opens files in Documents or on an external drive, macOS asks for "
                     "permission: click Allow")
MAC_ALLOW_MESSAGE_AR = "أول مرة يفتح فيها Claude ملفات في Documents أو على قرص خارجي سيطلب macOS الإذن: اضغط Allow"
MARK = {"ok": "[OK]", "skipped": "[!!]", "amber": "[!!]", "red": "[XX]"}
_DETACHED: list = []  # background downloads started by this process: kept referenced, never waited for


# --------------------------------------------------------------------------------------------- engine calls
def engine_python(ctx: base.Ctx) -> Optional[Path]:
    """The runtime interpreter: the one the runtime step set, else the one `current` names."""
    if ctx.runtime_python:
        return Path(ctx.runtime_python)
    rid = runtime.current_runtime(ctx.paths)
    return runtime.runtime_python(ctx.paths, rid, ctx.platform) if rid else None


def engine_cmd(ctx: base.Ctx, *args) -> list:
    py = engine_python(ctx)
    return [str(py) if py else "<engine python>", "-s", "-B", str(ctx.plugin_root / "engine" / "reel" / "cli.py"),
            *[str(a) for a in args]]


def _cwd(ctx: base.Ctx) -> Optional[Path]:
    return ctx.paths.whynot if ctx.paths.whynot.is_dir() else None


def _shown(cmd: list) -> str:
    return " ".join(f'"{c}"' if (" " in c or not c) else c for c in cmd)


def _engine_missing(ctx: base.Ctx) -> bool:
    py = engine_python(ctx)
    return py is None or not py.is_file()


# --------------------------------------------------------------------------------------------- preflight
def documents_dir(paths: base.Paths, platform: str) -> Path:
    """The editor's Documents folder: on real Windows the shell folder (it may be redirected to OneDrive)."""
    if paths.sandbox or not platform.startswith("win") or os.name != "nt":
        return paths.home / "Documents"
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            value = winreg.QueryValueEx(k, "Personal")[0]
        if isinstance(value, str) and value.strip():
            return Path(os.path.expandvars(value.strip()))
    except OSError:
        pass
    return paths.home / "Documents"


def _icloud_documents(paths: base.Paths) -> bool:
    cloud = paths.home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    docs = paths.home / "Documents"
    if not cloud.is_dir():
        return False
    return base.is_link(docs) or base._within(base._real(docs), base._real(cloud))


def _sac_state(paths: base.Paths, platform: str) -> Optional[int]:
    """Smart App Control, read-only: 0 off, 1 on, 2 evaluation; None when not looked at (sandbox, macOS)."""
    if paths.sandbox or not platform.startswith("win") or os.name != "nt":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\CI\Policy") as k:
            return int(winreg.QueryValueEx(k, "VerifiedAndReputablePolicyState")[0])
    except FileNotFoundError:
        return 0
    except (OSError, ValueError, TypeError):
        return None


def _os_version() -> str:
    """Without starting a process (platform.platform() may run `ver`)."""
    if os.name == "nt":
        v = sys.getwindowsversion()
        return f"Windows {v.major}.{v.minor}.{v.build}"
    return f"macOS {_platform.mac_ver()[0]}".strip()


def free_gb(path: Path) -> float:
    p = Path(path)
    while not p.exists() and p.parent != p:
        p = p.parent
    return round(shutil.disk_usage(p).free / GB, 1)


def preflight(ctx: base.Ctx) -> base.StepResult:
    paths, plat, dry = ctx.paths, ctx.platform, bool(ctx.args.dry_run)
    home = str(paths.home)
    docs = documents_dir(paths, plat)
    f = ctx.facts
    f.update(os="windows" if plat.startswith("win") else "macos", arch=plat.split("-", 1)[1],
             os_version=_os_version(), free_gb=free_gb(paths.whynot), home_ascii=home.isascii(),
             home_space=" " in home,
             onedrive_documents=plat.startswith("win") and "onedrive" in str(docs).lower(),
             icloud_documents=(not plat.startswith("win")) and _icloud_documents(paths),
             claude_found=bool(claude.claude_candidates(os.environ, paths.home, plat, paths.sandbox)),
             sac=_sac_state(paths, plat), engine_home=str(paths.whynot), engine_home_source=paths.engine_home_source)
    f["adobe_hosts"] = adobe_hosts(paths, plat, probe_processes=paths.sandbox or not dry)
    if paths.sandbox:
        f["nvidia"] = os.environ.get("WNC_TEST_NVIDIA") == "1"
    elif plat == "win-x64" and not dry:
        f["nvidia"] = runtime._nvidia_present(ctx)
    else:
        f["nvidia"] = False if plat.startswith("mac") else None
    name = str(base.cget(ctx.components, "marketplace.name") or "thewhynot-ai")
    # an earlier install = state.json or `current` (the engine home itself exists already: the log lives there)
    f["existing"] = {"engine": paths.state_file.is_file() or paths.current_file.is_file(),
                     "legacy_reel_editor": (paths.home / ".reel-editor").exists(),
                     "marketplace_source": claude._known_source(paths, name)}

    notes, status = [], "ok"
    if f["free_gb"] < RED_GB:
        status = "red"
        notes.append(f"only {f['free_gb']} GB free on the drive of {paths.whynot}; WhyNot Cut needs {RED_GB} GB "
                     f"({AMBER_GB} GB with the transcription model). Free some space and run the installer again")
    elif f["free_gb"] < AMBER_GB:
        notes.append(f"{f['free_gb']} GB free: enough for WhyNot Cut, tight for the transcription model "
                     f"({AMBER_GB} GB recommended)")
    if not f["home_ascii"] or f["home_space"]:
        notes.append(f"your user folder {home} has " + " and ".join(
            x for x in ("non-ASCII letters" if not f["home_ascii"] else "", "a space" if f["home_space"] else "")
            if x) + "; WhyNot Cut handles it, but tell us if a tool fails")
    if f["onedrive_documents"]:
        notes.append(f"Documents is in OneDrive ({docs}); keep the clients folder (the raw footage) outside OneDrive")
    if f["icloud_documents"]:
        notes.append("Documents is in iCloud Drive; keep the clients folder (the raw footage) outside iCloud")
    if f["sac"] == 1:
        notes.append("Windows Smart App Control is on; it can block parts of the engine. If a step fails, see the "
                     "troubleshooting chapter")
    if notes and status == "ok":
        status = "amber"
    facts = [f"{f['os']} {f['arch']}",
             f"engine home {paths.whynot} ({base.describe_engine_home_source(paths.engine_home_source)})",
             f"{f['free_gb']} GB free",
             "Claude Code found" if f["claude_found"] else "no Claude Code CLI (settings.json is used)"]
    if f["adobe_hosts"]:
        facts.append(", ".join(f"{h['app']} {h.get('version')}" + (" (running)" if h.get("running") else "")
                               for h in f["adobe_hosts"]))
    if f["existing"]["engine"]:
        facts.append("updating an existing install")
    ctx.state.data["preflight"] = {k: v for k, v in f.items() if k != "doctor"}
    return base.StepResult("preflight", status, "; ".join(facts + notes))


# --------------------------------------------------------------------------------------------- questions
def read_preferences(paths: base.Paths) -> dict:
    """The flat `key: value` frontmatter of <home>/.claude/whynot-cut.local.md (quotes and `#` comments removed);
    {} when there is none or it cannot be read."""
    f = paths.home / ".claude" / PREFS
    try:
        text = f.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return {}
    m = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        else:
            v = v.split(" #", 1)[0].strip()
        out[k.strip()] = v
    return out


def cloud_documents(facts: Optional[dict]) -> Optional[str]:
    """"OneDrive" / "iCloud Drive" when preflight found Documents synced to that cloud, else None."""
    f = facts or {}
    return "OneDrive" if f.get("onedrive_documents") else "iCloud Drive" if f.get("icloud_documents") else None


def default_clients_root(paths: base.Paths, platform: str, facts: Optional[dict] = None) -> Path:
    """The `start` skill's default: Windows D:\\WhyNot Clients when D:\\ exists (always first), else Documents\\WhyNot
    Clients; macOS ~/Documents/WhyNot Clients. When Documents is synced to OneDrive / iCloud Drive (preflight facts),
    ~/WhyNot Clients instead: raw footage must not be uploaded or evicted by the cloud. A sandbox never looks at D:\\
    (its ~ is the fake home)."""
    if platform.startswith("win") and not paths.sandbox and os.path.isdir("D:\\"):
        return Path("D:\\") / CLIENTS_FOLDER
    if cloud_documents(facts):
        return paths.home / CLIENTS_FOLDER
    if paths.sandbox:
        return paths.home / "Documents" / CLIENTS_FOLDER
    if platform.startswith("win"):
        return documents_dir(paths, platform) / CLIENTS_FOLDER
    return paths.home / "Documents" / CLIENTS_FOLDER


def _norm_folder(p: str) -> str:
    return os.path.abspath(os.path.expanduser(p.strip().strip('"')))


def resolve_answers(ctx: base.Ctx) -> dict:
    """The answers without asking: flags, else preferences, else defaults."""
    prefs = read_preferences(ctx.paths)
    flag_root, flag_lang = getattr(ctx.args, "clients_folder", None), getattr(ctx.args, "language", None)
    if flag_root:
        root, rsrc = flag_root, "--clients-folder"
    elif prefs.get("clients_root"):
        root, rsrc = prefs["clients_root"], "your preferences"
    else:
        root = str(default_clients_root(ctx.paths, ctx.platform, ctx.facts))
        cloud = cloud_documents(ctx.facts)
        rsrc = f"default: outside Documents, which {cloud} syncs" \
            if cloud and Path(root) == ctx.paths.home / CLIENTS_FOLDER else "default"
    if flag_lang in LANGUAGES:
        lang, lsrc = flag_lang, "--language"
    elif prefs.get("language") in LANGUAGES:
        lang, lsrc = prefs["language"], "your preferences"
    else:
        lang, lsrc = "ar", "default"
    return {"clients_root": _norm_folder(root), "language": lang, "from": {"clients_root": rsrc, "language": lsrc}}


def step_questions(ctx: base.Ctx) -> base.StepResult:
    a = resolve_answers(ctx)
    if base.can_ask(ctx.args):
        cloud = cloud_documents(ctx.facts)
        if cloud and a["from"]["clients_root"].startswith("default:"):
            ctx.log.info(f"Your Documents folder is synced to {cloud}; the suggested clients folder is outside it, so "
                         "raw footage is not uploaded or moved to the cloud.")
            ctx.log.info(f"مجلد Documents متزامن مع {cloud}؛ المجلد المقترح للعملاء خارجه حتى لا تُرفع ملفات "
                         "التصوير إلى السحابة.")
        root = base.ask(f"Folder for your client folders / مجلد العملاء [{a['clients_root']}]: ", "")
        if root:
            a["clients_root"], a["from"]["clients_root"] = _norm_folder(root), "you"
        while True:
            lang = base.ask(f"Language / اللغة: ar = العربية, en = English [{a['language']}]: ", "").lower()
            if not lang:
                break
            if lang in LANGUAGES:
                a["language"], a["from"]["language"] = lang, "you"
                break
    ctx.answers = a
    return base.StepResult("questions", "ok", f"clients folder {a['clients_root']} ({a['from']['clients_root']}; "
                                              "created when you add your first client); language "
                                              f"{a['language']} ({a['from']['language']})")


# --------------------------------------------------------------------------------------------- settings / model
def model_for(facts: dict, platform: str, components: dict) -> str:
    """components models.by_hardware: NVIDIA -> large-v3, Apple silicon -> large-v3 (MLX), else large-v3-turbo."""
    table = base.cget(components, "models.by_hardware") or {}
    if facts.get("nvidia"):
        m = table.get("nvidia", "large-v3")
    elif platform == "mac-arm64":
        m = table.get("apple_silicon", "large-v3")
    else:
        m = table.get("cpu", "large-v3-turbo")
    return m if m in MODELS else "large-v3-turbo"


def saved_model(paths: base.Paths) -> Optional[str]:
    """The editor's own whisper_model from the raw preferences file (not the engine's defaults); None when there is
    none or it is not a model the engine knows."""
    m = read_preferences(paths).get("whisper_model")
    return m if m in MODELS else None


def chosen_model(ctx: base.Ctx) -> str:
    """The editor's saved choice wins (kept on re-install); else the model for this hardware."""
    return saved_model(ctx.paths) or model_for(ctx.facts, ctx.platform, ctx.components)


def step_settings(ctx: base.Ctx) -> base.StepResult:
    a = ctx.answers or resolve_answers(ctx)
    saved = saved_model(ctx.paths)
    model = saved or model_for(ctx.facts, ctx.platform, ctx.components)
    args = ["settings", "--init", str(ctx.paths.home), "--force", "--set", f"clients_root={a['clients_root']}",
            "--set", f"language={a['language']}"]
    if not saved:  # an existing choice is kept: only a first install (or an unusable value) gets the hardware pick
        args += ["--set", f"whisper_model={model}"]
    if ctx.args.dry_run:
        return base.StepResult("settings", "skipped", "dry run: would run reel " + _shown(args))
    if _engine_missing(ctx):
        return _record(ctx, "settings", "amber", "the engine runtime is missing; your preferences were not written",
                       "run the installer again")
    rc, out = base.run_cmd(ctx, engine_cmd(ctx, *args), ENGINE_TIMEOUT, _cwd(ctx))
    if rc != 0:
        return _record(ctx, "settings", "amber", f"reel settings failed (exit {rc}: {base.tail(out)})",
                       "set them later with /whynot-cut:preferences in Claude")
    return _record(ctx, "settings", "ok", f"preferences written: clients folder {a['clients_root']}, language "
                                          f"{a['language']}, Whisper {model}")


_pid_alive = base.pid_alive  # kept under its old name (moved to base: the build lock and uninstall use it)


def _spawn_detached(cmd: list, log_path: Path, env: dict, cwd: Optional[Path]) -> int:
    """Start `cmd` so that it outlives the installer and its console window; output to log_path. Returns the pid."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    with open(log_path, "ab") as out:
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, env=env,
                             cwd=str(cwd) if cwd else None, close_fds=True, **kw)
    _DETACHED.append(p)
    return p.pid


def step_model(ctx: base.Ctx) -> base.StepResult:
    model = chosen_model(ctx)
    cmd = engine_cmd(ctx, "model-download", "--model", model)
    shown = _shown(cmd)
    if "model" in (getattr(ctx.args, "skip", None) or ()):
        return base.StepResult("model", "skipped", f"skipped with --skip; download it later with: {shown}")
    if ctx.args.dry_run:
        return base.StepResult("model", "skipped", f"dry run: would start in the background: {shown}")
    if ctx.paths.sandbox and os.environ.get("WNC_TEST_MODEL") != "1":
        return base.StepResult("model", "skipped", f"sandbox: not started; the command is: {shown}")
    if _engine_missing(ctx):
        return _record(ctx, "model", "amber", "the engine runtime is missing; the model was not downloaded",
                       "run the installer again")
    prev = ctx.state.data.get("models") if isinstance(ctx.state.data.get("models"), dict) else {}
    if prev.get("model") == model and _pid_alive(prev.get("pid")):
        return _record(ctx, "model", "ok", f"Whisper {model} is still downloading in the background "
                                           f"(log {prev.get('log')})")
    log_path = ctx.paths.logs_dir / f"model-download-{base.stamp()}.log"
    try:
        pid = _spawn_detached(cmd, log_path, ctx.paths.child_env(), _cwd(ctx))
    except OSError as e:
        return _record(ctx, "model", "amber", f"could not start the model download ({e})",
                       f"run it later: {shown}")
    ctx.state.data["models"] = {"model": model, "pid": pid, "log": str(log_path), "started_at": base.now_iso(),
                                "command": shown}
    return _record(ctx, "model", "ok", f"Whisper {model} is downloading in the background (about 3 GB; log "
                                       f"{log_path}); you can start working meanwhile")


step_model.handles_skip = True  # says itself how to download the model later


# --------------------------------------------------------------------------------------------- state
def plugin_version(plugin_root: Path) -> Optional[str]:
    try:
        v = json.loads((plugin_root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8-sig")).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    return v if isinstance(v, str) else None


def _uv_version(ctx: base.Ctx) -> Optional[str]:
    uv = runtime.uv_command(ctx)
    if not (uv[0] == sys.executable or Path(uv[0]).is_file()):
        return None
    rc, out = base.run_cmd(ctx, uv + ["--version"], 60, split=True)
    m = re.search(r"uv (\S+)", out) if rc == 0 else None
    return m.group(1) if m else None


def step_state(ctx: base.Ctx) -> base.StepResult:
    if ctx.args.dry_run:
        return base.StepResult("state", "skipped", f"dry run: would write {ctx.paths.state_file}")
    d = ctx.state.data
    rt = d.get("runtime") if isinstance(d.get("runtime"), dict) else {}
    rid = rt.get("id") or runtime.current_runtime(ctx.paths)
    lock_sha, py_ver = rt.get("lock_sha256"), None
    if rid:
        try:
            stamp = json.loads((ctx.paths.runtimes_dir / rid / runtime.STAMP).read_text(encoding="utf-8"))
            py_ver, lock_sha = stamp.get("python") or None, lock_sha or stamp.get("lock_sha256")
        except (OSError, ValueError, AttributeError):
            pass
    a = ctx.answers or resolve_answers(ctx)
    d.update(plugin=plugin_version(ctx.plugin_root) or ctx.components.get("plugin"),
             channel=getattr(ctx.args, "channel", None) or ctx.components.get("channel", "stable"),
             installed_at=base.now_iso(), platform=ctx.platform,
             uv={"version": _uv_version(ctx) or base.cget(ctx.components, "uv.version")}, python=py_ver,
             answers={"clients_root": a["clients_root"], "language": a["language"]})
    d["runtime"] = dict(rt, id=rid, lock_sha256=lock_sha) if rid else rt
    return _record(ctx, "state", "ok", f"{ctx.paths.state_file} written")


# --------------------------------------------------------------------------------------------- doctor / checklist
def _parse_json(text: str):
    s = text.strip()
    for cand in (s, s[s.find("{"):] if "{" in s else ""):
        try:
            v = json.loads(cand)
            return v if isinstance(v, dict) else None
        except ValueError:
            continue
    return None


def _is_ready(doc: dict) -> bool:
    r = doc.get("ready")
    if isinstance(r, dict):  # the engine's shape: {"engine": bool, "premiere_build": bool, ...}
        return bool(r.get("engine"))
    return bool(r)


def step_doctor(ctx: base.Ctx) -> base.StepResult:
    if ctx.args.dry_run:
        return base.StepResult("doctor", "skipped", "dry run: would run reel doctor")
    if _engine_missing(ctx):
        return _record(ctx, "doctor", "amber", "the engine runtime is missing; reel doctor was not run")
    rc, out = base.run_cmd(ctx, engine_cmd(ctx, "doctor"), ENGINE_TIMEOUT, _cwd(ctx), split=True)
    doc = _parse_json(out)
    if doc is None:
        ctx.state.data["last_doctor"] = {"at": base.now_iso(), "verdict": None, "ready": None}
        return _record(ctx, "doctor", "amber", f"reel doctor gave no report (exit {rc}: {base.tail(out)})")
    ready = _is_ready(doc)
    ctx.facts["doctor"] = doc
    ctx.state.data["last_doctor"] = {"at": base.now_iso(), "verdict": doc.get("verdict"), "ready": ready}
    if ready:
        return _record(ctx, "doctor", "ok", f"reel doctor: {doc.get('verdict')}")
    return _record(ctx, "doctor", "amber", f"reel doctor: {doc.get('verdict') or 'not ready'}; see the list below")


def render_checklist(results: list, doctor: Optional[dict]) -> str:
    """One line per step ([OK], [!!] amber / skipped with the reason, [XX] red), what the editor must do, then the
    doctor's fixes as `[!!] <item> -> <fix>`."""
    lines = []
    for r in results:
        lines.append(f"{MARK.get(r.status, '[??]')} {r.name}" + (f" - {r.detail}" if r.detail else ""))
        if r.needs_you:
            lines.append(f"     you: {r.needs_you}")
    for fx in (doctor or {}).get("fixes") or []:
        if isinstance(fx, dict) and fx.get("item"):
            lines.append(f"[!!] {fx['item']} -> {fx.get('fix') or ''}".rstrip())
    return "\n".join(lines)


def write_checklist(paths: base.Paths, results: list, doctor: Optional[dict]) -> Path:
    f = paths.logs_dir / "install-checklist.json"
    base.atomic_write_json(f, {"at": base.now_iso(), "steps": [
        {"name": r.name, "status": r.status, "detail": r.detail, "needs_you": r.needs_you} for r in results],
        "doctor": {k: (doctor or {}).get(k) for k in ("verdict", "ready", "fixes")} if doctor else None})
    return f


# --------------------------------------------------------------------------------------------- launch
def step_launch(ctx: base.Ctx) -> base.StepResult:
    if ctx.paths.sandbox:
        return base.StepResult("launch", "skipped", "sandbox: Claude is not opened")
    if ctx.args.dry_run:
        return base.StepResult("launch", "skipped", f"dry run: would open {START_URL}")
    if ctx.platform.startswith("win"):
        try:
            import winreg
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\claude"))
        except OSError:
            return base.StepResult("launch", "skipped", "the Claude desktop app is not installed (no claude:// link)")
        try:
            os.startfile(START_URL)  # noqa: S606 - our own fixed URL
        except OSError as e:
            return base.StepResult("launch", "skipped", f"could not open Claude ({e})")
        return base.StepResult("launch", "ok", "Claude opened on /whynot-cut:start")
    if base.run_cmd(ctx, ["open", "-Ra", "Claude"], 30)[0] != 0:
        return base.StepResult("launch", "skipped", "the Claude desktop app is not installed")
    rc, out = base.run_cmd(ctx, ["open", START_URL], 30)
    if rc != 0:
        return base.StepResult("launch", "skipped", f"could not open Claude ({base.tail(out)})")
    return base.StepResult("launch", "ok", "Claude opened on /whynot-cut:start")


# --------------------------------------------------------------------------------------------- helpers / registry
def _record(ctx: base.Ctx, name: str, status: str, detail: str, needs_you: Optional[str] = None) -> base.StepResult:
    ctx.state.record(name, status, None, detail)
    return base.StepResult(name, status, detail, needs_you)


STEPS = (("preflight", preflight, ()), ("questions", step_questions, ()), ("adobe", step_adobe, ()),
         ("fonts", step_fonts, ()), ("settings", step_settings, ("runtime",)), ("model", step_model, ("runtime",)),
         ("state", step_state, ()), ("doctor", step_doctor, ("runtime",)), ("launch", step_launch, ()))


def register(steps: list) -> None:
    """Append this module's install steps to cli.STEPS (once)."""
    have = {s[0] for s in steps}
    steps.extend(s for s in STEPS if s[0] not in have)
