"""Install step `adobe` (3.0 T7.1 step 7, installer.md R.2 step 7 and B.5): the Phase 6 hook for the Adobe panels.

The panel artefacts come with the plugin (`bridge.cep.zxp` / `bridge.uxp.ccx` in components.json, relative to the
plugin root). Until Phase 6 ships them they are placeholders and the step is `skipped`.
  CEP  a SIGNED ZXP (a zip holding META-INF/signatures.xml) is extracted per user into
       <CEP extensions>/ai.thewhynot.cut.bridge (via .new, the previous copy kept as .prev). An unsigned one is never
       installed: Adobe's debug mode (which would let unsigned panels run) is never switched on by WhyNot Cut.
  UXP  for Premiere Pro >= bridge.uxp.min_host, Adobe's Unified Plugin Installer Agent (UPIA) installs the .ccx; no
       UPIA: the editor double-clicks the .ccx (Creative Cloud installs it).
A running Premiere Pro / After Effects locks its panel folder: the editor is asked to close it (or the step is amber).
Also used by uninstall (Task 6): cep_extensions_dir, hosts_running, EXT_ID. Stdlib only.
"""
from __future__ import annotations

import csv
import io
import json
import os
import plistlib
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Optional

from . import base

EXT_ID = "ai.thewhynot.cut.bridge"  # the CEP bundle id (engine/reel/lib/ppro_bridge.py EXT_ID)
UPIA_TIMEOUT = 300
SIGNATURES = "META-INF/signatures.xml"
# process names of the hosts whose panel folder we write (Windows image names; macOS matches the app names)
_WIN_HOSTS = {"adobe premiere pro.exe": "premiere", "afterfx.exe": "after_effects"}
_UPIA_WIN = ("Adobe", "Adobe Desktop Common", "RemoteComponents", "UPI", "UnifiedPluginInstallerAgent",
             "UnifiedPluginInstallerAgent.exe")
_UPIA_MAC = Path("/Library/Application Support/Adobe/Adobe Desktop Common/RemoteComponents/UPI/"
                 "UnifiedPluginInstallerAgent/UnifiedPluginInstallerAgent.app/Contents/MacOS/"
                 "UnifiedPluginInstallerAgent")


# --------------------------------------------------------------------------------------------- locations / hosts
def cep_extensions_dir(paths: base.Paths, platform: str) -> Path:
    """The per-user CEP extensions folder (no admin): %APPDATA%\\Adobe\\CEP\\extensions or
    ~/Library/Application Support/Adobe/CEP/extensions (under the fake home in a sandbox)."""
    if platform.startswith("win"):
        return paths.appdata / "Adobe" / "CEP" / "extensions"
    return paths.home / "Library" / "Application Support" / "Adobe" / "CEP" / "extensions"


def hosts_running(sandbox: bool) -> list:
    """Process names of a running Premiere Pro / After Effects. A sandbox never probes: it returns what
    $WNC_TEST_HOSTS_RUNNING lists (comma separated). Windows: `tasklist /FO CSV /NH`; macOS: `pgrep -fl`."""
    if sandbox:
        return [x.strip() for x in os.environ.get("WNC_TEST_HOSTS_RUNNING", "").split(",") if x.strip()]
    try:
        if os.name == "nt":
            # (SEC-1) by its full path: CreateProcess would also look for a bare `tasklist` in the current folder
            r = subprocess.run([base.system32("tasklist.exe"), "/FO", "CSV", "/NH"], stdin=subprocess.DEVNULL,
                               capture_output=True,
                               timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            rows = csv.reader(io.StringIO(r.stdout.decode("utf-8", "replace")))
            return sorted({row[0] for row in rows if row and row[0].lower() in _WIN_HOSTS})
        r = subprocess.run(["/usr/bin/pgrep", "-fl", "Adobe Premiere Pro|Adobe After Effects"], stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and "pgrep" not in parts[1] and parts[1] not in out:
            out.append(parts[1])
    return out


def _app_of(process_name: str) -> Optional[str]:
    n = process_name.lower()
    if "premiere" in n:
        return "premiere"
    if "afterfx" in n or "after effects" in n:
        return "after_effects"
    return None


def _exe_version(exe: Path) -> Optional[str]:
    """Windows: the product version from the exe's version resource (read-only, version.dll)."""
    try:
        import ctypes
        from ctypes import wintypes
        ver = ctypes.WinDLL("version")
        size = ver.GetFileVersionInfoSizeW(str(exe), None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(str(exe), 0, size, buf):
            return None
        ptr, n = ctypes.c_void_p(), wintypes.UINT()
        if not ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(n)) or not ptr.value:
            return None
        words = ctypes.cast(ptr, ctypes.POINTER(wintypes.DWORD * 13)).contents  # VS_FIXEDFILEINFO
        ms, ls = words[4], words[5]  # dwProductVersionMS / LS
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}"
    except (OSError, AttributeError, ValueError):
        return None


def _year_version(folder: str) -> Optional[str]:
    """"Adobe Premiere Pro 2026" -> "26.0" (only when the exact version cannot be read)."""
    m = re.search(r"20(\d\d)\b", folder)
    return f"{int(m.group(1))}.0" if m else None


def adobe_hosts(paths: base.Paths, platform: str, *, probe_processes: bool = True) -> list:
    """[{app: premiere|after_effects, version, path, running}] of the installed hosts. A sandbox reads
    $WNC_TEST_ADOBE_HOSTS (a JSON list of {app, version}) and never looks at the machine."""
    found = []
    if paths.sandbox:
        try:
            data = json.loads(os.environ.get("WNC_TEST_ADOBE_HOSTS") or "[]")
        except ValueError:
            data = []
        found = [{"app": h.get("app"), "version": h.get("version"), "path": h.get("path")}
                 for h in data if isinstance(h, dict)]
    elif platform.startswith("win"):
        roots = {os.environ.get(v) for v in ("ProgramFiles", "ProgramW6432") if os.environ.get(v)}
        for root in sorted(roots):
            for app, pattern in (("premiere", "Adobe Premiere Pro 20*/Adobe Premiere Pro.exe"),
                                 ("after_effects", "Adobe After Effects 20*/Support Files/AfterFX.exe")):
                for exe in sorted((Path(root) / "Adobe").glob(pattern)):
                    folder = exe.parent.name if app == "premiere" else exe.parent.parent.name
                    found.append({"app": app, "version": _exe_version(exe) or _year_version(folder),
                                  "path": str(exe)})
    else:
        for app, pattern in (("premiere", "Adobe Premiere Pro 20*/*.app"),
                             ("after_effects", "Adobe After Effects 20*/*.app")):
            for bundle in sorted(Path("/Applications").glob(pattern)):
                try:
                    with open(bundle / "Contents" / "Info.plist", "rb") as f:
                        ver = plistlib.load(f).get("CFBundleShortVersionString")
                except (OSError, ValueError, plistlib.InvalidFileException):
                    ver = None
                found.append({"app": app, "version": ver or _year_version(bundle.parent.name), "path": str(bundle)})
    running = {_app_of(n) for n in hosts_running(paths.sandbox)} if probe_processes else set()
    for h in found:
        h["running"] = h["app"] in running
    return found


def _vt(v) -> tuple:
    """"26.5" -> (26, 5, 0): always three parts, so "26.5" >= "26.5.0"."""
    parts = [int(x) for x in re.findall(r"\d+", str(v or ""))[:3]]
    return tuple(parts + [0] * (3 - len(parts)))


# --------------------------------------------------------------------------------------------- step
def _artefact(ctx: base.Ctx, key: str) -> Optional[Path]:
    rel = base.cget(ctx.components, key)
    if base.is_placeholder(rel) or not isinstance(rel, str) or not rel.strip():
        return None
    p = ctx.plugin_root / rel
    if not p.is_file():
        ctx.log.info(f"{key} names {rel}, which is not in the plugin folder")
        return None
    return p


def _pin_ok(ctx: base.Ctx, f: Path, key: str) -> Optional[str]:
    """None when the file matches its pinned sha256 (or no pin yet), else the problem."""
    pin = base.cget(ctx.components, key)
    if base.is_placeholder(pin):
        return None
    got = base.file_sha256(f)
    return None if got == pin else f"{f.name} does not match its pinned sha256 (expected {pin}, got {got})"


def _wait_for_hosts(ctx: base.Ctx) -> list:
    """The hosts still running after asking the editor (up to three times) to close them."""
    running = hosts_running(ctx.paths.sandbox)
    tries = 0
    while running and base.can_ask(ctx.args) and tries < 3:
        base.ask(f"Please close {', '.join(running)} (save your work first), then press Enter: ")
        running = hosts_running(ctx.paths.sandbox)
        tries += 1
    return running


def _install_cep(ctx: base.Ctx, zxp: Path, rec: dict) -> tuple:
    bad = _pin_ok(ctx, zxp, "bridge.cep.sha256")
    if bad:
        return "red", f"CEP panel not installed: {bad}"
    try:
        with zipfile.ZipFile(zxp) as zf:
            signed = SIGNATURES in zf.namelist()
    except (zipfile.BadZipFile, OSError) as e:
        return "red", f"CEP panel not installed: {zxp.name} is not a ZXP ({e})"
    if not signed:
        rec["cep"] = {"path": None, "signed": False}
        return "amber", (f"unsigned panel: not installed; {zxp.name} has no {SIGNATURES}, and WhyNot Cut never "
                         "switches on Adobe's debug mode to run unsigned panels")
    cep = cep_extensions_dir(ctx.paths, ctx.platform)
    final = cep / EXT_ID
    new, prev = final.with_name(EXT_ID + ".new"), final.with_name(EXT_ID + ".prev")
    if base.is_link(final):
        return "amber", f"{final} is a link (a development panel); it was left alone"
    roots = [cep]
    try:
        if not base.safe_rmtree(new, roots):
            raise OSError(f"cannot clear the leftover {new}")
        base.extract(zxp, new)  # byte-identical: the signature covers every file
        if os.path.lexists(final):
            if os.path.lexists(prev) and not base.safe_rmtree(prev, roots):
                raise OSError(f"cannot remove the older {prev}")
            base._replace(final, prev)
        try:
            base._replace(new, final)
        except OSError:
            if os.path.lexists(prev) and not os.path.lexists(final):
                base._replace(prev, final)
            raise
    except (OSError, base.ExtractError) as e:
        try:
            base.safe_rmtree(new, roots)
        except OSError:
            pass
        return "red", f"CEP panel not installed: {e}"
    rec["cep"] = {"path": str(final), "prev": str(prev) if prev.exists() else None, "signed": True,
                  "sha256": base.file_sha256(zxp)}
    return "ok", f"CEP panel installed in {final}"


def upia_path(platform: str) -> Path:
    if platform.startswith("win"):
        common = os.environ.get("CommonProgramFiles") or r"C:\Program Files\Common Files"
        return Path(common).joinpath(*_UPIA_WIN)
    return _UPIA_MAC


def _install_uxp(ctx: base.Ctx, ccx: Path, hosts: list, rec: dict) -> tuple:
    bad = _pin_ok(ctx, ccx, "bridge.uxp.sha256")
    if bad:
        return "red", f"UXP panel not installed: {bad}"
    need = str(base.cget(ctx.components, "bridge.uxp.min_host") or "26.5.0")
    ppro = [h for h in hosts if h.get("app") == "premiere" and _vt(h.get("version")) >= _vt(need)]
    if not ppro:
        have = ", ".join(str(h.get("version")) for h in hosts if h.get("app") == "premiere") or "none found"
        return "skipped", f"UXP panel not installed: it needs Premiere Pro {need} or newer ({have})"
    upia = upia_path(ctx.platform)
    cmd = [str(upia), "/install" if ctx.platform.startswith("win") else "--install", str(ccx)]
    uid = base.cget(ctx.components, "bridge.uxp.id")  # kept for uninstall (UPIA /remove <id>)
    rec["uxp"] = {"command": cmd, "ran": False, "file": str(ccx),
                  "id": None if base.is_placeholder(uid) or not isinstance(uid, str) else uid}
    if ctx.paths.sandbox:
        return "ok", "sandbox: the UXP install command was recorded, not run"
    double_click = f"double-click {ccx} (Creative Cloud installs it), then restart Premiere Pro"
    if not upia.is_file():
        return "amber", f"Adobe's plugin installer (UPIA) was not found: {double_click}"
    rc, out = base.run_cmd(ctx, cmd, UPIA_TIMEOUT)
    rec["uxp"].update(ran=True, exit=rc)
    if rc != 0:
        return "amber", f"UPIA could not install the UXP panel (exit {rc}: {base.tail(out)}): {double_click}"
    rec["uxp"].update(installed=True, sha256=base.file_sha256(ccx))
    return "ok", "UXP panel installed for Premiere Pro"


def _current(ctx: base.Ctx, zxp: Optional[Path], ccx: Optional[Path]) -> tuple:
    """(cep record, uxp record) of the previous run when that part is already installed from these exact bytes
    (the CEP bundle still on disk / UPIA succeeded); None for a part that needs work."""
    prev = ctx.state.data.get("adobe") if isinstance(ctx.state.data.get("adobe"), dict) else {}
    cep, uxp = prev.get("cep"), prev.get("uxp")
    cep_ok = (zxp is not None and isinstance(cep, dict) and cep.get("signed") and cep.get("path")
              and cep.get("sha256") == base.file_sha256(zxp) and Path(cep["path"]).is_dir()
              and Path(cep["path"]) == cep_extensions_dir(ctx.paths, ctx.platform) / EXT_ID)
    uxp_ok = (ccx is not None and isinstance(uxp, dict) and uxp.get("installed")
              and uxp.get("sha256") == base.file_sha256(ccx))
    return (cep if cep_ok else None), (uxp if uxp_ok else None)


def step_adobe(ctx: base.Ctx) -> base.StepResult:
    zxp, ccx = _artefact(ctx, "bridge.cep.zxp"), _artefact(ctx, "bridge.uxp.ccx")
    if zxp is None and ccx is None:
        return base.StepResult("adobe", "skipped", "Adobe panel files are not in this build yet")
    if ctx.args.dry_run:
        what = " and ".join(x for x in ("the CEP panel" if zxp else "", "the UXP panel" if ccx else "") if x)
        return base.StepResult("adobe", "skipped", f"dry run: would install {what}")
    cep_now, uxp_now = _current(ctx, zxp, ccx)
    if (zxp is None or cep_now) and (ccx is None or uxp_now):  # nothing to do: no host check, no question
        ctx.state.record("adobe", "ok", None, "the Adobe panel is installed and up to date")
        return base.StepResult("adobe", "ok", "the Adobe panel is installed and up to date")
    running = _wait_for_hosts(ctx)
    if running:
        msg = f"close {', '.join(running)}, then run the installer again"
        return base.StepResult("adobe", "amber", f"the Adobe panel was not installed: {msg}", needs_you=msg)
    hosts = ctx.facts.get("adobe_hosts")
    if not isinstance(hosts, list):
        hosts = adobe_hosts(ctx.paths, ctx.platform)
    rec, parts = {"hosts": hosts}, []
    if cep_now:
        rec["cep"] = cep_now
        parts.append(("ok", "the CEP panel is up to date"))
    else:
        parts.append(_install_cep(ctx, zxp, rec) if zxp else ("skipped", "the CEP panel is not in this build yet"))
    if uxp_now:
        rec["uxp"] = uxp_now
        parts.append(("ok", "the UXP panel is up to date"))
    else:
        parts.append(_install_uxp(ctx, ccx, hosts, rec) if ccx
                     else ("skipped", "the UXP panel is not in this build yet"))
    # ~/.whynot-cut/bridge/config.json belongs to the bridge itself (Phase 6), not to this step.
    statuses = [s for s, _t in parts]
    status = next((s for s in ("red", "amber", "ok") if s in statuses), "skipped")
    detail = "; ".join(t for _s, t in parts)
    if status == "ok":
        detail += "; restart Premiere Pro and After Effects to load it"
    rec["at"] = base.now_iso()
    ctx.state.data["adobe"] = rec
    ctx.state.record("adobe", status, None, detail)
    return base.StepResult("adobe", status, detail)
