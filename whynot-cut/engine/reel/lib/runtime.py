"""The engine runtime (3.0 T2.1, review IM-1 / IM-2 / MI-21). Stdlib only: setup/setup_env.py imports it with any
Python, before a runtime exists.

Layout in the engine home (the installer track's runtime contract, R.1):

    bin/uv(.exe)          pinned uv (components.json `uv`)
    python/               UV_PYTHON_INSTALL_DIR: python-build-standalone (components.json `runtime.python`)
    cache/uv/             UV_CACHE_DIR
    runtimes/<id>/        a venv built from setup/locks/runtime-<platform>.lock (no system site, no user site)
        WHYNOT_RUNTIME        JSON {id, platform, python, lock_file, lock_sha256, created_at, by}
        .whynot-lock.sha256   hex sha256 of the lock file's bytes
    current               one line: the runtime id in use (written atomically, only after the smoke import passes)

Runtime id = components.json `runtime.locks.<platform>.id`, or while that is the placeholder "<release>",
"r-" + sha256(lock bytes)[:12] — the installer derives it the same way, so both build and recognise one runtime.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import platform as _platform
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    from . import plat
except ImportError:                       # setup/setup_env.py: lib/ is on sys.path, no package
    import plat  # type: ignore[no-redef]

PLUGIN_DIR = Path(__file__).resolve().parents[3]
COMPONENTS_FILE = PLUGIN_DIR / "setup" / "components.json"
PLACEHOLDER = "<release>"
STAMP = "WHYNOT_RUNTIME"
LOCK_STAMP = ".whynot-lock.sha256"
DEFAULT_PYTHON = "3.12.15"
DEFAULT_SMOKE = ["faster_whisper", "ctranslate2", "av", "numpy", "PIL", "uharfbuzz"]

# every module the engine (or faster-whisper under it) imports from a package, and the distribution that provides it
# (doctor's isolation check; setup's module report). Optional extras (rawpy, mlx_whisper) are not required.
ENGINE_MODULES = ["faster_whisper", "ctranslate2", "av", "numpy", "PIL", "fontTools", "arabic_reshaper", "bidi",
                  "uharfbuzz", "freetype", "pypdf", "imageio_ffmpeg", "huggingface_hub", "onnxruntime", "tokenizers"]
MAC_MODULES = ["CoreText", "Quartz", "Vision", "Foundation"]
OTHER_MODULES = ["cv2"]
MODULE_DIST = {"faster_whisper": "faster-whisper", "PIL": "pillow", "fontTools": "fonttools",
               "arabic_reshaper": "arabic-reshaper", "bidi": "python-bidi", "freetype": "freetype-py",
               "imageio_ffmpeg": "imageio-ffmpeg", "huggingface_hub": "huggingface-hub",
               "Foundation": "pyobjc-framework-Cocoa", "cv2": "opencv-python-headless", "CoreText": "pyobjc-framework-CoreText",
               "Quartz": "pyobjc-framework-Quartz", "Vision": "pyobjc-framework-Vision"}


def engine_modules() -> list[str]:
    return ENGINE_MODULES + (MAC_MODULES if plat.IS_MAC else OTHER_MODULES)


# --------------------------------------------------------------------------- platform, components, lock
def _sysctl(name: str) -> str | None:
    """`sysctl -n <name>` on macOS (None elsewhere, or when the key does not exist: Intel Macs lack these)."""
    if sys.platform != "darwin":
        return None
    try:
        r = subprocess.run(["/usr/sbin/sysctl", "-n", name], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def platform_key(system: str | None = None, machine: str | None = None, sysctl=_sysctl) -> str | None:
    """win-x64 | mac-arm64 | mac-x64 (the lock names), linux-x64 / linux-arm64 (no lock shipped), else None.
    On macOS an x86_64 Python under Rosetta (sysctl.proc_translated = 1) or on Apple Silicon hardware
    (hw.optional.arm64 = 1) still gives mac-arm64: the installer's bootstrap.sh rule, so both build one runtime id."""
    system = (system or _platform.system()).lower()
    m = (machine or _platform.machine()).lower()
    arch = "arm64" if m in ("arm64", "aarch64") else "x64" if m in ("x86_64", "amd64", "x64") else None
    if not arch:
        return None
    if system.startswith("win"):
        return f"win-{arch}"
    if system == "darwin":
        if arch == "x64" and (sysctl("sysctl.proc_translated") == "1" or sysctl("hw.optional.arm64") == "1"):
            arch = "arm64"
        return f"mac-{arch}"
    if system == "linux":
        return f"linux-{arch}"
    return None


def components(path: Path | None = None) -> dict:
    """setup/components.json (owned by the installer track; read only here). {} when missing or unreadable."""
    try:
        d = json.loads((path or COMPONENTS_FILE).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


CLASSES = ("cuda", "mps", "cpu")


def hardware_class(key: str | None, nvidia: bool) -> str | None:
    """The hardware-class lock for a platform (T4.12): "cuda" (Windows x64 with an NVIDIA GPU), "cpu" (Windows x64
    without), "mps" (Apple Silicon), None (Intel Mac: PyTorch has no macOS x86_64 wheels after 2.2; Linux; unknown):
    the base lock only."""
    if key == "win-x64":
        return "cuda" if nvidia else "cpu"
    if key == "mac-arm64":
        return "mps"
    return None


def lock_entry(key: str | None, comp: dict | None = None, plugin_dir: Path | None = None,
               klass: str | None = None) -> dict:
    """{file: Path, declared_id: str | None, klass: str | None} for a platform: components.json runtime.locks.<key>,
    else the default name setup/locks/runtime-<key>.lock. With `klass` (T4.12: cuda | mps | cpu) the class lock
    runtime.locks.<klass>.path is used unless it is missing, a placeholder ("<pending>"), outside the plugin folder or
    not a file: then the platform entry, as before (klass None in the answer)."""
    plugin_dir = plugin_dir or PLUGIN_DIR
    comp = components() if comp is None else comp
    locks = ((comp.get("runtime") or {}).get("locks") or {})
    if klass in CLASSES:
        ce = locks.get(klass) if isinstance(locks.get(klass), dict) else {}
        rel = ce.get("path") if isinstance(ce.get("path"), str) else ce.get("file")
        if isinstance(rel, str) and rel.strip() and not rel.strip().startswith("<"):
            f = (plugin_dir / rel).resolve()
            if f.is_relative_to(Path(plugin_dir).resolve()) and f.is_file():
                did = ce.get("id") if isinstance(ce.get("id"), str) else None
                return {"file": plugin_dir / rel, "declared_id": did, "klass": klass}
    e = locks.get(key or "") or {}
    rel = e.get("file") if isinstance(e.get("file"), str) else f"setup/locks/runtime-{key}.lock"
    did = e.get("id") if isinstance(e.get("id"), str) else None
    return {"file": plugin_dir / rel, "declared_id": did, "klass": None}


def lock_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def runtime_id(lock_bytes: bytes, declared: str | None = None) -> str:
    """The declared id (components.json) unless it is empty or the "<release>" placeholder: then "r-" + the first 12
    hex digits of the lock's sha256."""
    if declared and declared.strip() and declared.strip() != PLACEHOLDER and not declared.startswith("<"):
        return declared.strip()
    return "r-" + lock_sha256(lock_bytes)[:12]


def normalize(name: str) -> str:
    """PEP 503 project name: lower case, runs of - _ . become one -."""
    return re.sub(r"[-_.]+", "-", name).lower()


_REQ = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?\s*==\s*([^\s;\\]+)\s*(?:;\s*([^\\]*?))?\s*$")


def parse_lock(text: str) -> dict[str, dict]:
    """A `uv pip compile --generate-hashes` (pip requirements) lock -> {normalized name: {name, version, hashes,
    marker}}. Continuation lines (`\\`) are joined; comments, blank lines and option lines (--index-url ...) are
    skipped. Every requirement must be pinned with `==` and carry at least one --hash (ValueError otherwise)."""
    out: dict[str, dict] = {}
    logical, buf = [], ""
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        buf += line
        if buf.strip():
            logical.append(buf.strip())
        buf = ""
    if buf.strip():
        logical.append(buf.strip())
    for entry in logical:
        if entry.startswith("-"):
            continue
        hashes = re.findall(r"--hash[= ]\s*(sha256:[0-9a-fA-F]{64})", entry)
        spec = re.split(r"\s--hash", " " + entry, maxsplit=1)[0].strip()
        m = _REQ.match(spec)
        if not m:
            raise ValueError(f"lock line is not a pinned requirement: {spec[:80]!r}")
        if not hashes:
            raise ValueError(f"lock line without --hash: {m.group(1)}")
        out[normalize(m.group(1))] = {"name": m.group(1), "version": m.group(3), "hashes": hashes,
                                     "marker": (m.group(4) or "").strip() or None}
    return out


# --------------------------------------------------------------------------- TLS (T4.12, Addendum J J2.3)
def trust_context(cafile: str | None = None):
    """An SSL client context that verifies certificates and host names: the operating system's own trust store
    (truststore: Windows CryptoAPI, macOS Keychain), so an antivirus doing HTTPS inspection with its root installed
    works WITH verification on; `cafile` adds a trust file (tests, a pinned CA). Without truststore (a runtime from
    before T4.12): Python's default verifying context. Verification is never turned off."""
    import ssl
    ctx = None
    try:
        import truststore
        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:  # noqa: BLE001  not installed (older runtime): the default verifying context
        ctx = ssl.create_default_context()
    if cafile:
        ctx = ssl.create_default_context(cafile=cafile) if not isinstance(ctx, ssl.SSLContext) else ctx
        ctx.load_verify_locations(cafile=cafile)
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = True
    return ctx


def configure_downloads() -> bool:
    """Model / file downloads through huggingface_hub use a client built on trust_context() (one context per client,
    never a global patch of ssl). True when it was set."""
    try:
        import huggingface_hub as hub
        setter = getattr(hub, "set_client_factory", None)
        if not callable(setter):
            return False
        import httpx
        hooks = {}
        try:                           # the hub's own request hook (HF_HUB_OFFLINE, its headers) stays in place
            from huggingface_hub.utils._http import hf_request_event_hook
            hooks = {"request": [hf_request_event_hook]}
        except Exception:  # noqa: BLE001
            pass

        def factory():
            return httpx.Client(verify=trust_context(), follow_redirects=True, timeout=None, event_hooks=hooks)
        setter(factory)
        aset = getattr(hub, "set_async_client_factory", None)
        if callable(aset):
            try:
                from huggingface_hub.utils._http import async_hf_request_event_hook
                ahooks = {"request": [async_hf_request_event_hook]}
            except Exception:  # noqa: BLE001
                ahooks = {}

            def afactory():
                return httpx.AsyncClient(verify=trust_context(), follow_redirects=True, timeout=None,
                                         event_hooks=ahooks)
            aset(afactory)
        return True
    except Exception:  # noqa: BLE001  an older hub: its own verifying defaults stay
        return False


# --------------------------------------------------------------------------- runtime folders and stamps
def runtimes_dir(home: Path) -> Path:
    return home / plat.RUNTIMES_DIR


def runtime_dir(home: Path, rid: str) -> Path:
    return runtimes_dir(home) / rid


def read_stamp(rt_dir: Path) -> dict:
    """{"runtime": WHYNOT_RUNTIME JSON or {}, "lock_sha256": .whynot-lock.sha256 or None}."""
    try:
        st = json.loads((rt_dir / STAMP).read_text(encoding="utf-8"))
        st = st if isinstance(st, dict) else {}
    except (OSError, ValueError):
        st = {}
    try:
        sha = (rt_dir / LOCK_STAMP).read_text(encoding="utf-8").strip() or None
    except OSError:
        sha = None
    return {"runtime": st, "lock_sha256": sha}


IO_RETRIES = 50          # x ~10 ms, like common._retry: Windows briefly refuses to replace a file another process has open


def _atomic_write(path: Path, text: str):
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8", newline="\n")
        for k in range(IO_RETRIES):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:      # an antivirus scan or a reader holding `current` for a moment
                if k == IO_RETRIES - 1:
                    raise
                time.sleep(0.005 + 0.005 * (k % 4))
    finally:
        if tmp.exists():
            tmp.unlink()


def write_stamps(rt_dir: Path, *, rid: str, key: str | None, python: str, lock_file: str, lock_sha: str, by: str,
                 now: str | None = None) -> dict:
    stamp = {"id": rid, "platform": key, "python": python, "lock_file": lock_file, "lock_sha256": lock_sha,
             "created_at": now or _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"), "by": by}
    _atomic_write(rt_dir / STAMP, json.dumps(stamp, indent=2) + "\n")
    _atomic_write(rt_dir / LOCK_STAMP, lock_sha + "\n")
    return stamp


def clear_stamps(rt_dir: Path):
    """Remove both stamps before (re)installing: a runtime whose install did not finish must never look built."""
    for name in (LOCK_STAMP, STAMP):
        try:
            (rt_dir / name).unlink()
        except FileNotFoundError:
            pass


def python_runs(py: Path, timeout: int = 60) -> bool:
    """Does the interpreter start at all (its base Python may have been removed)?"""
    try:
        return subprocess.run([str(py), "-s", "-c", "pass"], capture_output=True, timeout=timeout).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def prune(home: Path, keep: set[str]) -> dict:
    """Delete runtimes/<id> folders other than `keep` (current + one previous, for rollback). Only folders that are
    runtimes (a pyvenv.cfg or a WHYNOT_RUNTIME inside, a valid id) and not being built (no .<id>.building lock).
    A folder that cannot be removed (in use) is reported, never an error. {removed: [...], kept: [...], failed: {}}."""
    import shutil
    out = {"removed": [], "kept": sorted(keep), "failed": {}}
    d = runtimes_dir(home)
    if not d.is_dir():
        return out
    for rt in sorted(d.iterdir()):
        rid = rt.name
        if (rid in keep or not rt.is_dir() or not plat._RUNTIME_ID.match(rid) or ".." in rid
                or rid.endswith(".building")):
            continue
        if not ((rt / "pyvenv.cfg").is_file() or (rt / STAMP).is_file()) or (d / f".{rid}.building").exists():
            continue
        def _chmod_retry(fn, path, _exc):
            try:
                os.chmod(path, 0o700)
                fn(path)
            except OSError:
                pass
        try:
            shutil.rmtree(rt, **({"onexc": _chmod_retry} if sys.version_info >= (3, 12) else
                                 {"onerror": _chmod_retry}))
        except OSError:
            pass
        if rt.exists():
            out["failed"][rid] = "in use or locked; removed on a later reel setup"
        else:
            out["removed"].append(rid)
    return out


def write_current(home: Path, rid: str):
    """Switch <home>/current to `rid` (tmp file + replace: a reader sees the old id or the new one, never half)."""
    if not plat._RUNTIME_ID.match(rid) or ".." in rid:
        raise ValueError(f"not a runtime id: {rid!r}")
    _atomic_write(home / plat.CURRENT_FILE, rid + "\n")


# --------------------------------------------------------------------------- repair decision
_VERSIONS_CODE = ("import json, importlib.metadata as m\n"
                  "print(json.dumps({d.metadata['Name']: d.version for d in m.distributions() if d.metadata['Name']}))")


def installed_versions(py: Path, timeout: int = 120) -> dict[str, str] | None:
    """{normalized name: version} of the distributions the interpreter sees with its user site off (-s), or None
    when it cannot run."""
    try:
        r = subprocess.run([str(py), "-s", "-c", _VERSIONS_CODE], capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return None
        return {normalize(k): v for k, v in json.loads(r.stdout.strip().splitlines()[-1]).items()}
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def repair_decision(lock: dict[str, dict], installed: dict[str, str] | None, *, exists: bool,
                    stamp_sha: str | None, lock_sha: str) -> dict:
    """What `reel setup` must do to a runtime: {"action": "none" | "create" | "sync", "reasons": [...]}.
    create: no runtime (or no interpreter in it). sync (re-install from the lock): the lock's sha256 differs from the
    one stamped in the runtime, the interpreter cannot list its packages, or a locked package is missing or at
    another version. Locked lines with an environment marker are checked only when installed (the per-platform
    locks have none)."""
    if not exists:
        return {"action": "create", "reasons": ["no runtime yet"]}
    reasons = []
    if stamp_sha != lock_sha:
        reasons.append("the lock changed since the runtime was built" if stamp_sha else
                       "the runtime has no lock stamp (unfinished build)")
    if installed is None:
        reasons.append("the runtime's python cannot list its packages")
    else:
        for name, e in sorted(lock.items()):
            have = installed.get(name)
            if have is None:
                if not e.get("marker"):
                    reasons.append(f"{e['name']} missing")
            elif have != e["version"]:
                reasons.append(f"{e['name']} {have} installed, the lock pins {e['version']}")
    return {"action": "sync" if reasons else "none", "reasons": reasons}


# --------------------------------------------------------------------------- isolation (reel doctor)
def _inside(path: str | None, folder: Path) -> bool:
    if not path:
        return False
    try:
        Path(path).resolve().relative_to(folder.resolve())
        return True
    except (ValueError, OSError):
        return False


def _module_file(mod) -> str | None:
    f = getattr(mod, "__file__", None)
    if f:
        return f
    p = list(getattr(mod, "__path__", []) or [])
    return p[0] if p else None


def _dist_version(dist: str) -> str | None:
    import importlib.metadata as md
    try:
        return md.version(dist)
    except md.PackageNotFoundError:
        return None


def isolation(rt: dict, lock: dict[str, dict], modules: list[str] | None = None, *, importer=None,
              dist_version=None, prefix: str | None = None, user_site: bool | None = None) -> dict:
    """Is the engine running from an isolated runtime? `rt` = plat.engine_runtime(). True only when this process is
    the runtime's interpreter, the runtime has no system site, no user site is active, and every engine module loads
    from inside the runtime at the version the lock pins. {isolated, problems[], modules{m: {file, version, lock,
    ok}}}."""
    import importlib
    importer = importer or importlib.import_module
    dist_version = dist_version or _dist_version
    modules = engine_modules() if modules is None else modules
    problems = []
    d = rt.get("dir")
    if rt.get("broken"):
        problems.append(f"runtime {rt['broken']} cannot start (its base Python is missing): reel setup rebuilds it")
    if rt.get("kind") != "runtime" or not d:
        problems.append("the engine runs from the legacy venv/, not an isolated runtime" if rt.get("kind") == "venv"
                        else "no engine runtime")
    else:
        d = Path(d)
        if not _inside(prefix or sys.prefix, d) or not _inside(str(d), Path(prefix or sys.prefix)):
            problems.append(f"this process runs {prefix or sys.prefix}, not the runtime {d}")
        try:
            cfg = (d / "pyvenv.cfg").read_text(encoding="utf-8").lower()
            if re.search(r"include-system-site-packages\s*=\s*true", cfg):
                problems.append("the runtime includes the system site-packages")
        except OSError:
            problems.append("the runtime has no pyvenv.cfg")
        if user_site is None:
            import site
            user_site = bool(site.ENABLE_USER_SITE) and any(_inside(p, Path(site.getusersitepackages()))
                                                             for p in sys.path if p)
        if user_site:
            problems.append("the user site-packages is on sys.path (run the engine with python -s)")
    mods = {}
    for m in modules:
        try:
            mod = importer(m)
        except Exception as e:  # noqa: BLE001
            mods[m] = {"file": None, "version": None, "lock": None, "ok": False}
            problems.append(f"{m} does not import ({type(e).__name__})")
            continue
        f = _module_file(mod)
        dist = MODULE_DIST.get(m, m)
        want = (lock.get(normalize(dist)) or {}).get("version")
        have = dist_version(dist)
        ok = True
        if d and rt.get("kind") == "runtime" and not _inside(f, Path(d)):
            ok = False
            problems.append(f"{m} loads from {f}, outside the runtime")
        if want and have != want:
            ok = False
            problems.append(f"{dist} {have} installed, the lock pins {want}")
        mods[m] = {"file": f, "version": have, "lock": want, "ok": ok}
    return {"isolated": not problems, "problems": problems, "modules": mods}


def current_class(home: Path) -> str | None:
    """The hardware class of the current runtime (T4.12): the class whose lock (setup/locks/runtime-<class>.txt) its
    stamp records, else None (a base runtime, no runtime, or an unreadable stamp)."""
    try:
        rid = plat.current_runtime_id(home)
        st = read_stamp(runtime_dir(home, rid)) if rid else {"runtime": {}}
        name = Path(str((st["runtime"] or {}).get("lock_file") or "")).name
    except (OSError, ValueError, TypeError):
        return None
    for k in CLASSES:
        if name == f"runtime-{k}.txt":
            return k
    return None


def status(home: Path, key: str | None = None, comp: dict | None = None) -> dict:
    """The runtime part of `reel doctor` without importing anything: which interpreter the wrappers pick, the id this
    plugin's lock expects and whether the current runtime was built from it. A runtime built from a hardware-class
    lock (T4.12) is judged against that class lock, not the base one."""
    key = key or platform_key()
    rt = plat.engine_runtime(home)
    klass = current_class(home)
    ent = lock_entry(key, comp, klass=klass)
    if klass and ent["klass"] is None:                  # the shipped class lock (components.json may not list it yet)
        cand = PLUGIN_DIR / "setup" / "locks" / f"runtime-{klass}.txt"
        if cand.is_file():
            ent = {"file": cand, "declared_id": None, "klass": klass}
    try:
        data = ent["file"].read_bytes()
    except OSError:
        data = None
    want_id = runtime_id(data, ent["declared_id"]) if data is not None else None
    want_sha = lock_sha256(data) if data is not None else None
    st = read_stamp(Path(rt["dir"])) if rt["kind"] == "runtime" else {"runtime": {}, "lock_sha256": None}
    return {"kind": rt["kind"], "id": rt["id"], "broken": rt.get("broken"),
            "dir": str(rt["dir"]) if rt["dir"] else None,
            "python": str(rt["python"]) if rt["python"] else None, "platform": key, "klass": ent["klass"],
            "lock_file": str(ent["file"]) if data is not None else None, "expected_id": want_id,
            "lock_sha256": want_sha, "stamp": st["runtime"], "stamp_lock_sha256": st["lock_sha256"],
            "up_to_date": bool(rt["kind"] == "runtime" and want_sha and st["lock_sha256"] == want_sha
                               and rt["id"] == want_id)}
