"""Install step `fonts` (3.0 T7.1 step 8, installer.md B.6, ID-2): our OFL fonts, per user, no admin.

Every `fonts.files[]` and `fonts.licenses[]` of components.json is downloaded (pinned, sha256) into
~/.whynot-cut/fonts/<version>/ (licences as `<Family>-OFL.txt`); nothing is installed unless every download verified.
  Windows  copied to %LOCALAPPDATA%\\Microsoft\\Windows\\Fonts\\, value "<file stem> (TrueType)" = full path under
           HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Fonts, then AddFontResourceW + WM_FONTCHANGE. A
           sandbox (--home) writes those values to <home>/.wnc-sandbox/registry-fonts.json and calls no Windows API.
  macOS    copied to ~/Library/Fonts/.
A font file already there with other bytes is never replaced (amber). state.fonts.installed lists only the files this
installer put there, so uninstall (Task 6) removes exactly those: FontRegistry, user_font_dir, remove_font_resource.
Stdlib only.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Optional

from . import base

REG_KEY = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"
_SAFE_NAME = re.compile(r"^[^\\/:*?\"<>|]+\.(ttf|otf)$", re.I)


def user_font_dir(paths: base.Paths, platform: str) -> Path:
    if platform.startswith("win"):
        return paths.localappdata / "Microsoft" / "Windows" / "Fonts"
    return paths.home / "Library" / "Fonts"


def registry_name(file_name: str) -> str:
    """The HKCU value name Windows itself uses for a per-user font: "<stem> (TrueType)" / "(OpenType)"."""
    p = Path(file_name)
    return f"{p.stem} ({'OpenType' if p.suffix.lower() == '.otf' else 'TrueType'})"


# --------------------------------------------------------------------------------------------- registry
class FontRegistry:
    """The per-user font values: get / set / delete / names. `for_paths` picks the sandbox JSON file or the real
    HKCU key (Windows only, never in a sandbox)."""

    @staticmethod
    def for_paths(paths: base.Paths) -> "FontRegistry":
        if paths.sandbox:
            return SandboxFontRegistry(paths.sandbox_dir / "registry-fonts.json")
        return WinFontRegistry()

    def get(self, name: str) -> Optional[str]:
        raise NotImplementedError

    def set(self, name: str, path: str) -> None:
        raise NotImplementedError

    def delete(self, name: str) -> None:
        raise NotImplementedError

    def names(self) -> list:
        raise NotImplementedError


class SandboxFontRegistry(FontRegistry):
    """{value name: path} in a JSON file (atomic writes)."""

    def __init__(self, file: Path):
        self.file = Path(file)

    def _load(self) -> dict:
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def get(self, name):
        return self._load().get(name)

    def set(self, name, path):
        data = self._load()
        data[name] = str(path)
        base.atomic_write_json(self.file, data)

    def delete(self, name):
        data = self._load()
        if name in data:
            del data[name]
            base.atomic_write_json(self.file, data)

    def names(self):
        return list(self._load())


class WinFontRegistry(FontRegistry):
    """HKCU\\...\\Fonts (REG_SZ values). HKLM is never touched."""

    def get(self, name):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
                return str(winreg.QueryValueEx(k, name)[0])
        except OSError:
            return None

    def set(self, name, path):
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, str(path))

    def delete(self, name):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, name)
        except FileNotFoundError:
            pass

    def names(self):
        import winreg
        out = []
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
                i = 0
                while True:
                    try:
                        out.append(winreg.EnumValue(k, i)[0])
                    except OSError:
                        break
                    i += 1
        except OSError:
            pass
        return out


def _gdi(fn: str, path: str) -> bool:
    """AddFontResourceW / RemoveFontResourceW (real Windows only; callers never reach this in a sandbox)."""
    try:
        import ctypes
        return bool(getattr(ctypes.windll.gdi32, fn)(str(path)))
    except (OSError, AttributeError):
        return False


def add_font_resource(path) -> bool:
    return _gdi("AddFontResourceW", path)


def remove_font_resource(path) -> bool:
    return _gdi("RemoveFontResourceW", path)


def broadcast_font_change() -> None:
    """Tell running programs the font list changed (WM_FONTCHANGE to every top-level window, 1 s per window max)."""
    try:
        import ctypes
        from ctypes import wintypes
        result = wintypes.DWORD()
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001D, 0, 0, 0x0002, 1000, ctypes.byref(result))
    except (OSError, AttributeError):
        pass


# --------------------------------------------------------------------------------------------- step
def _pinned(items) -> bool:
    return isinstance(items, list) and bool(items) and all(
        isinstance(x, dict) and not base.is_placeholder(x.get("url")) and not base.is_placeholder(x.get("sha256"))
        for x in items)


def step_fonts(ctx: base.Ctx) -> base.StepResult:
    paths, c, plat = ctx.paths, ctx.components, ctx.platform
    ver, files, lics = base.cget(c, "fonts.version"), base.cget(c, "fonts.files"), base.cget(c, "fonts.licenses")
    if base.is_placeholder(ver) or not _pinned(files) or not (lics in (None, []) or _pinned(lics)):
        return base.StepResult("fonts", "skipped", "the fonts are not in this build (placeholder pin)")
    ver = str(ver)
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", ver) or ".." in ver:
        return base.StepResult("fonts", "red", f"components.json fonts.version is not a version: {ver!r}")
    bad = [f.get("file") for f in files if not _SAFE_NAME.match(str(f.get("file") or ""))]
    bad += [x.get("family") for x in lics or [] if not re.match(r"^[A-Za-z0-9][A-Za-z0-9 ._-]*$",
                                                               str(x.get("family") or ""))]
    if bad:
        return base.StepResult("fonts", "red", f"components.json fonts has unusable names: {bad!r}")
    store, target = paths.fonts_dir / ver, user_font_dir(paths, plat)
    win = plat.startswith("win")
    if ctx.args.dry_run:
        return base.StepResult("fonts", "skipped", f"dry run: would download {len(files)} fonts into {store} and "
                                                   f"install them in {target}")
    got = []
    try:  # every file verified before any is installed
        for f in files:
            got.append((f, base.download(f["url"], f["sha256"], store, ctx.log, name=f["file"])))
        for lic in lics or []:
            base.download(lic["url"], lic["sha256"], store, ctx.log, name=f"{lic['family']}-OFL.txt")
    except base.DownloadError as e:
        return _done(ctx, "red", f"no font was installed: {e}")

    prev = ctx.state.data.get("fonts") if isinstance(ctx.state.data.get("fonts"), dict) else {}
    ours_before = {str(p) for p in prev.get("installed") or [] if isinstance(p, str)}
    reg = FontRegistry.for_paths(paths) if win else None
    installed, names, kept, theirs, added = [], [], [], [], []
    for f, src in got:
        dst = target / f["file"]
        ours = str(dst) in ours_before
        if dst.exists() and base.file_sha256(dst) == f["sha256"]:
            if not ours:  # the same font, put there by someone else: theirs to keep
                theirs.append(dst.name)
                continue
        elif dst.exists() and not ours:  # someone else's file with that name: never replaced
            kept.append(dst.name)
            continue
        else:  # missing, or ours with other bytes (a font update): (re)placed with the pinned file
            target.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_name(f".{dst.name}.wnc-tmp")
            shutil.copyfile(src, tmp)
            base._replace(tmp, dst)
            added.append(dst)
        installed.append(str(dst))
        if reg is not None:
            name = registry_name(f["file"])
            if reg.get(name) != str(dst):
                reg.set(name, str(dst))
            names.append(name)
    if win and not paths.sandbox and added:
        for p in added:
            add_font_resource(p)
        broadcast_font_change()
    ctx.state.data["fonts"] = {"version": ver, "store": str(store), "dir": str(target), "installed": installed,
                               "registry": names}
    detail = f"{len(installed)} fonts installed in {target}"
    if theirs:
        detail += f"; already there (not ours, kept): {', '.join(theirs)}"
    if kept:
        return _done(ctx, "amber", detail + f"; {', '.join(kept)} already exists with different content and was left "
                                            "alone")
    return _done(ctx, "ok", detail + ("; restart Premiere Pro and After Effects to see them" if added else ""))


def _done(ctx: base.Ctx, status: str, detail: str) -> base.StepResult:
    ctx.state.record("fonts", status, None, detail)
    return base.StepResult("fonts", status, detail)
