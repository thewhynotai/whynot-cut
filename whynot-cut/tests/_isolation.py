"""Test sandbox (3.0 G79): no unit test reaches the real engine home, the real ~/.claude or a running Adobe app.

Why a module and not a hook: unittest has no conftest, and the suite is started several ways (tools/test.sh,
`python -m unittest discover -s whynot-cut/tests [-p <file>]`, one file run as a script). Every test module imports
this module as its first statement after the bytecode prelude (tests/test_isolation.py enforces it), so whichever
module is imported first sandboxes the whole process before any engine code runs; later imports are no-ops (module
cache). Child processes inherit the environment, so the engine, hooks and wrappers a test spawns are sandboxed too.

What it does, once per process:
  * records the machine's REAL locations first (plat.engine_home() as the environment gives it, ~/.whynot-cut and the
    legacy homes, the CEP extensions folder) in WHYNOT_TEST_LIVE_ROOTS; REAL_ENGINE_HOME is kept for the few tests that
    read the real runtime (never write to it);
  * points WHYNOT_HOME, HOME, USERPROFILE, APPDATA (Windows: the CEP folder), LOCALAPPDATA and CLAUDE_CONFIG_DIR into a per-run temp
    folder and sets WHYNOT_TEST_SANDBOX to it; drops the variables that would lead back to the real machine
    (CLAUDE_PLUGIN_DATA, CLAUDE_ENV_FILE, WHYNOT_OPTIONS_FILE, other engine-home / clients-root settings and plugin
    options). A test that sets its own (mock.patch.dict) still wins inside that test;
  * points font discovery (lib/fonts.py, through plat.font_search_dirs) at an empty sandbox folder
    (WHYNOT_FONT_DIRS): no test reads the machine's font folders by accident; a test that needs fonts injects them
    (dirs=, or a patched plat.font_dirs). plat.font_dirs() itself still names the real folders;
  * keeps the pinned ffmpeg of the real engine home findable (NH_FFMPEG, read-only) so media tests behave as before
    (a developer's WHYNOT_FFMPEG / WHYNOT_FFMPEG_TIMEOUT_SCALE are dropped: they would win over it / scale timeouts);
  * puts every temp folder of the run inside the sandbox (tempfile.tempdir, and TMP/TEMP/TMPDIR for child processes)
    and makes TemporaryDirectory clean up robustly: Windows under load answers rmtree with WinError 145 ("directory is
    not empty") or a read-only / briefly locked file, so cleanup retries (chmod + short backoff) and whatever still
    lingers stays inside the sandbox, which is removed (with the same retries) when the process that made it exits.
The interpreter itself is unaffected: tools/test.sh resolves the runtime before Python starts.
Under WHYNOT_TEST_SANDBOX the engine also refuses to queue jobs in, sync scripts into or install the bridge into a live
root, and to launch After Effects, Photoshop or aerender (plat.sandbox_refusal), unless WHYNOT_TEST_ALLOW_LIVE_BRIDGE=1.
The sandbox folder is removed when the process that made it exits; a run that was killed leaves it behind, so each
run first sweeps sandboxes older than 24 h from the real temp folder (exact prefix + marker file only).
"""
import atexit
import os
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path

_ENGINE = str(Path(__file__).resolve().parents[1] / "engine" / "reel")
if _ENGINE not in sys.path:
    sys.path.insert(0, _ENGINE)

from lib import plat  # noqa: E402  (stdlib only; computes nothing at import)

PREFIX = "whynot-test-sandbox-"
MARKER = ".whynot-test-sandbox"          # written into every sandbox: only folders holding it are ever swept
STALE_S = 24 * 3600
_DROP = ("CLAUDE_PLUGIN_DATA", "CLAUDE_ENV_FILE", "WHYNOT_OPTIONS_FILE",
         "WHYNOT_PREMIERE_APP", "WHYNOT_AE_APP", "WHYNOT_AERENDER",
         "WHYNOT_FFMPEG", "WHYNOT_FFMPEG_TIMEOUT_SCALE") + plat.HOME_ENV + plat.CLIENTS_ENV + plat.USER_OPTION_ENV   # T2.15: a dev's ffmpeg


def _live_roots() -> list:
    home = Path.home()
    roots = [plat.engine_home(), home / plat.HOME_NAME] + [home / h for h in plat.LEGACY_HOMES]
    roots.append(plat.cep_extensions_dir())
    out = []
    for r in roots:
        s = os.path.abspath(str(r))
        if s not in out:
            out.append(s)
    return out


def rmtree_retry(path, attempts: int = 6) -> bool:
    """rmtree that survives Windows' transient refusals: read-only entries get write permission, then retry with a
    short backoff (0.05 s doubling). True when the folder is gone."""
    def fix(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
            func(p)
        except OSError:
            pass
    kw = {"onexc": fix} if sys.version_info >= (3, 12) else {"onerror": fix}
    for i in range(attempts):
        if not os.path.lexists(path):
            return True
        try:
            shutil.rmtree(path, **kw)
        except OSError:
            pass
        if not os.path.lexists(path):
            return True
        time.sleep(0.05 * 2 ** i)
    return not os.path.lexists(path)


class _TemporaryDirectory(tempfile.TemporaryDirectory):
    """tempfile.TemporaryDirectory for the test run: cleanup retries (rmtree_retry) and never raises; a folder that
    still cannot go stays in the sandbox and leaves with it."""
    def __init__(self, *a, **kw):
        kw.setdefault("ignore_cleanup_errors", True)
        super().__init__(*a, **kw)

    def cleanup(self):
        if self._finalizer.detach() or os.path.exists(self.name):
            rmtree_retry(self.name)


def sweep_stale(tmp_root, now=None) -> list:
    """Remove sandboxes of earlier runs that never cleaned up (killed): folders in `tmp_root` named PREFIX* that hold
    MARKER written more than STALE_S ago. Anything else (no marker, a fresh marker, another name, a file) is left."""
    now = time.time() if now is None else now
    gone = []
    try:
        entries = list(os.scandir(tmp_root))
    except OSError:
        return gone
    for e in entries:
        try:
            if not e.name.startswith(PREFIX) or not e.is_dir(follow_symlinks=False):
                continue
            if now - os.stat(os.path.join(e.path, MARKER)).st_mtime <= STALE_S:
                continue
        except OSError:                 # no marker: not ours
            continue
        if rmtree_retry(e.path, attempts=3):
            gone.append(e.path)
    return gone


def _sandbox() -> None:
    if os.environ.get(plat.SANDBOX_ENV):            # a parent test process already sandboxed this one
        return
    real_engine = plat.engine_home()
    pinned = plat.engine_ffmpeg(real_engine) or next(
        (p for p in [real_engine / "ffmpeg"] if p.is_file()), None)          # or the 2.x <home>/ffmpeg link
    roots = _live_roots()
    sweep_stale(tempfile.gettempdir())
    box = Path(tempfile.mkdtemp(prefix=PREFIX))
    (box / MARKER).write_text(str(os.getpid()), encoding="utf-8")
    pid = os.getpid()
    atexit.register(lambda: os.getpid() == pid and rmtree_retry(box))
    user = box / "user-home"
    (user / ".claude").mkdir(parents=True)
    tmp = box / "tmp"
    tmp.mkdir()
    (box / "fonts").mkdir()             # font discovery reads this empty folder: tests inject the fonts they need
    for k in list(os.environ):
        if k in _DROP or k.startswith("CLAUDE_PLUGIN_OPTION_"):
            del os.environ[k]
    os.environ.update({
        plat.SANDBOX_ENV: str(box),
        plat.LIVE_ROOTS_ENV: os.pathsep.join(roots),
        "WHYNOT_TEST_REAL_ENGINE_HOME": str(real_engine),
        "WHYNOT_HOME": str(box / "engine-home"),
        "HOME": str(user),
        "USERPROFILE": str(user),
        "CLAUDE_CONFIG_DIR": str(user / ".claude"),
        "TMP": str(tmp), "TEMP": str(tmp), "TMPDIR": str(tmp),
        plat.FONT_DIRS_ENV: str(box / "fonts"),
    })
    if plat.IS_WIN:
        os.environ["APPDATA"] = str(user / "AppData" / "Roaming")
        os.environ["LOCALAPPDATA"] = str(user / "AppData" / "Local")           # per-user fonts, caches: not the real ones
    if pinned and not os.environ.get("NH_FFMPEG"):
        os.environ["NH_FFMPEG"] = str(pinned)


def _utf8_child_text() -> None:
    """Every run decodes child output like tools/test.sh does (PYTHONUTF8=1): a bare `python -m unittest` on Windows
    is not in UTF-8 mode, so text-mode pipes used the ANSI code page (cp1252) and the CLI's Arabic UTF-8 output broke
    (Phase 4 hygiene). Children get PYTHONUTF8=1 (Python writes UTF-8 to pipes); text-mode Popen without an explicit
    encoding/errors decodes UTF-8. An explicit encoding= still wins. No-op in UTF-8 mode (tools/test.sh, macOS CI)."""
    if sys.flags.utf8_mode:
        return
    os.environ["PYTHONUTF8"] = "1"          # also over an inherited PYTHONUTF8=0: parent and children must agree
    import subprocess
    init = subprocess.Popen.__init__
    if getattr(init, "_whynot_utf8", False):
        return

    def utf8_init(self, *a, **kw):
        if (kw.get("text") or kw.get("universal_newlines") or kw.get("errors") is not None) \
                and kw.get("encoding") is None:
            kw["encoding"] = "utf-8"
        init(self, *a, **kw)
    utf8_init._whynot_utf8 = True
    subprocess.Popen.__init__ = utf8_init


_sandbox()
_utf8_child_text()
tempfile.tempdir = None                # re-read TMP/TEMP/TMPDIR: this process's temp folders land in the sandbox too
if sys.version_info >= (3, 10) and not issubclass(tempfile.TemporaryDirectory, _TemporaryDirectory):
    tempfile.TemporaryDirectory = _TemporaryDirectory
REAL_ENGINE_HOME = Path(os.environ["WHYNOT_TEST_REAL_ENGINE_HOME"])
LIVE_ROOTS = os.environ[plat.LIVE_ROOTS_ENV]
