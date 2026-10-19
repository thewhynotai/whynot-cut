"""Portability checks for `reel doctor` (3.0 T2.15, engine review MI-14 and MI-18).

* A non-ASCII engine home on Windows (an Arabic user name puts it under C:\\Users\\<name>\\.whynot-cut): CTranslate2
  (Whisper's model.bin) and OpenCV open files through narrow paths, so Whisper may fail to load and face detection
  silently finds nothing (every reframe centred). Doctor warns and suggests an ASCII engine home (BL-16:
  `suggested_home()`, <drive>:\\WhyNotCut on a fixed local NTFS drive, a non-system drive first; reel setup locks it).
* The engine home's access list (BL-16, lib/home_acl.py): no other account may write there.
* OpenCV's face model: `cv2.CascadeClassifier(<haarcascade>).empty()` must be False, else face detection is off.
* ffmpeg: which binary runs (override, the pinned one, the runtime's imageio-ffmpeg, PATH), its version, and a
  self-test of the filters the engine relies on (builds differ: an old PATH ffmpeg may lack `ebur128=peak=true`).

Every check takes its inputs as arguments (fakes in tests); `doctor_checks()` runs them for this machine.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

try:
    from . import plat
except ImportError:                       # setup/setup_env.py: lib/ is on sys.path, no package (home_path_fix only)
    import plat  # type: ignore[no-redef]

HOME_FOLDER = "WhyNotCut"
_DRIVE_KINDS = {2: "removable", 3: "fixed", 4: "network", 5: "cdrom", 6: "ramdisk"}      # GetDriveTypeW
# the filters the engine's ffmpeg command lines use (audio cleanup, loudness, QC, shots, SFX, previews)
FFMPEG_FILTERS = ("afftdn", "agate", "alimiter", "astats", "bandreject", "highpass", "lowpass", "ebur128", "aformat",
                  "aresample", "aevalsrc", "anoisesrc", "showspectrumpic", "select", "scale", "pad", "crop", "overlay",
                  "format", "fps")
# one real graph: options differ between builds (ebur128's peak option, afftdn's defaults)
SELFTEST = ["-hide_banner", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.3",
            "-af", "afftdn,alimiter,ebur128=peak=true", "-f", "null", "-"]


def windows_drives() -> list[tuple[str, str, str | None]]:
    """[("D:", kind, file system)] for this PC's drive letters: kind removable / fixed / network / cdrom / ramdisk /
    other; the file system is read for fixed drives only (a network or removable drive may stall)."""
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    mask, out = k32.GetLogicalDrives(), []
    for i in range(26):
        if not mask >> i & 1:
            continue
        root = f"{chr(65 + i)}:\\"
        kind = _DRIVE_KINDS.get(k32.GetDriveTypeW(root), "other")
        fs = ctypes.create_unicode_buffer(64)
        ok = kind == "fixed" and k32.GetVolumeInformationW(root, None, 0, None, None, None, fs, 64)
        out.append((root[:2], kind, fs.value if ok else None))
    return out


def suggested_home(drives=None, system: str | None = None) -> str:
    """The ASCII engine home to suggest on Windows: <drive>:\\WhyNotCut on a fixed local NTFS drive, the first
    non-system one in letter order when there is one, else the system drive. Never a network, removable or FAT/exFAT
    drive. Only the engine home goes there, never client folders. A folder made at a drive root inherits "Authenticated
    Users: Modify", so reel setup locks it to the user on creation (lib/home_acl.py). Inputs injectable (tests)."""
    system = (system or os.environ.get("SystemDrive") or "C:")[:2].upper()
    if drives is None:
        try:
            drives = windows_drives() if plat.IS_WIN else []
        except (OSError, AttributeError):
            drives = []
    good = sorted(d[:2].upper() for d, kind, fs in drives if kind == "fixed" and (fs or "").upper() == "NTFS")
    pick = next((d for d in good if d != system), system)
    return f"{pick}\\{HOME_FOLDER}"


def home_path_fix(home, is_win: bool | None = None, suggestion: str | None = None) -> dict | None:
    """A doctor fix when the engine home has non-ASCII characters on Windows, else None."""
    is_win = plat.IS_WIN if is_win is None else is_win
    s = str(home)
    if not is_win or s.isascii():
        return None
    return {"item": f"the engine home {s} has non-ASCII characters: on Windows Whisper's model loader and OpenCV's face "
                    "detector open files through narrow paths there, so transcription may fail and every reframe may "
                    "come out centred", "who": "editor",
            "fix": f"move the engine to an ASCII folder: run `setx WHYNOT_HOME {suggestion or suggested_home()}` in a "
                   "terminal (for example; any ASCII folder on a local NTFS drive, for the engine only), open a new "
                   "Claude Code session, then `reel setup` (it creates the folder, locks it to your account and builds "
                   "the engine there; the Whisper model downloads again unless you copy the models folder across)"}


def face_model_check(cv2=None) -> dict:
    """{ok, path, error}: OpenCV's frontal-face cascade loads (CascadeClassifier(...).empty() is False). ok None when
    OpenCV is not part of this engine (macOS uses Vision)."""
    if cv2 is None:
        try:
            import cv2  # type: ignore
        except Exception as e:  # noqa: BLE001
            return {"ok": None, "path": None, "error": f"OpenCV not importable ({type(e).__name__})"}
    path = None
    try:
        path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        empty = cv2.CascadeClassifier(path).empty()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "path": path, "error": f"{type(e).__name__}: {e}"}
    return {"ok": not empty, "path": path, "error": "the face model did not load (empty classifier)" if empty else None}


def face_model_fix(check: dict, home) -> dict | None:
    if check.get("ok") is not False:
        return None
    hint = (f"set WHYNOT_HOME to an ASCII folder (`setx WHYNOT_HOME {suggested_home()}`), new session, then reel setup"
            if not str(check.get("path") or home).isascii() else
            "reel setup --force   (re-installs the engine packages from the hash lock)")
    return {"item": f"face detection is off: OpenCV cannot load {check.get('path') or 'its face model'} "
                    f"({check.get('error')}), so every reframe would be centred", "who": "claude", "fix": hint}


def ffmpeg_report(ff: str | None, source: str | None, runner=subprocess.run) -> dict:
    """{path, source, version, filters_missing, selftest_ok, selftest_error}: `ffmpeg -version`, `-filters` and one
    real filter graph. runner is injectable (tests)."""
    rep = {"path": ff, "source": source, "version": None, "filters_missing": [], "selftest_ok": None,
           "selftest_error": None}
    if not ff:
        return rep

    def call(args):
        return runner([ff, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                      check=False)
    try:
        v = call(["-hide_banner", "-version"])
        rep["version"] = ((v.stdout or "").splitlines() or [""])[0].strip() or None
        listed = call(["-hide_banner", "-filters"]).stdout or ""
        have = {m.group(1) for m in re.finditer(r"^\s*[A-Z.|]{2,4}\s+(\w+)\s", listed, re.M)}
        rep["filters_missing"] = [f for f in FFMPEG_FILTERS if f not in have]
        t = call(SELFTEST)
        rep["selftest_ok"] = t.returncode == 0
        if t.returncode:
            rep["selftest_error"] = ((t.stderr or "").strip().splitlines() or [f"exit {t.returncode}"])[-1][:300]
    except (OSError, subprocess.SubprocessError) as e:
        rep["selftest_ok"], rep["selftest_error"] = False, f"{type(e).__name__}: {e}"
    return rep


def ffmpeg_fix(rep: dict, bad_override: str | None = None) -> list[dict]:
    fixes = []
    if bad_override:
        fixes.append({"item": f"{bad_override} does not name an ffmpeg file, so it is ignored", "who": "editor",
                      "fix": "point it at the ffmpeg binary (or remove the variable) and open a new session"})
    if rep.get("path") and (rep.get("filters_missing") or rep.get("selftest_ok") is False):
        what = (f"lacks the filters {', '.join(rep['filters_missing'])}" if rep.get("filters_missing")
                else f"failed the filter self-test ({rep.get('selftest_error')})")
        fixes.append({"item": f"ffmpeg {rep['path']} ({rep.get('source')}) {what}: audio cleanup, loudness or QC "
                              "would fail or measure wrong", "who": "claude",
                      "fix": "reel setup   (the engine runtime's ffmpeg is used before any ffmpeg on PATH); or set "
                             "WHYNOT_FFMPEG to a full ffmpeg 6 or newer"})
    return fixes


def doctor_checks(home) -> tuple[dict, list[dict]]:
    """(report, fixes) for reel doctor: engine-home path and access list, OpenCV face model (not on macOS), ffmpeg +
    filter test."""
    from . import home_acl
    from .common import ffmpeg_choice
    fixes = []
    f = home_path_fix(home)
    if f:
        fixes.append(f)
    fixes += home_acl.doctor_fixes(home)
    face = None if plat.IS_MAC else face_model_check()
    f = face_model_fix(face or {}, home)
    if f:
        fixes.append(f)
    ch = ffmpeg_choice()
    ff = ffmpeg_report(ch["path"], ch["source"])
    fixes += ffmpeg_fix(ff, ch.get("bad_override"))
    return {"engine_home_ascii": str(home).isascii(), "face_model": face, "ffmpeg": ff}, fixes
