"""The WhyNot Cut CEP bundle (`ai.thewhynot.cut.bridge`): where its source lives, how a bundle folder is assembled, how an
installed one is read, the install rule, and the engine's `config.json` the bundle reads.

Layout of bundle 3.0.0 (3.0 T6.3 Task 4):

    CSXS/manifest.xml   bundle "WhyNot Cut" 3.0.0: the visible panel (After Effects only, ./ui/index.html) and the
                        hidden daemon (./daemon.html, Premiere and After Effects); the only copy that works the queue
    daemon.html, ui/index.html, ui/js/panel.js, js/bridge.js, jsx/wnc_host.jsx      the shell, from <repo>/adobe/cep-bridge
    ui/tokens.css       <repo>/brand/tokens.css as-is (the one brand token source; the After Effects panel links it)
    jsx/wnc_*.jsx       the libraries the daemon runs, copied from whynot-cut/templates/** (their single source, design
                        decision 1); the copy is an artefact of `assemble`, never a second source
    build.json          {"product": "3.0.0", "build": <16 hex: sha256 over the sorted (path, sha256) of every other
                        file>, "sha": <git commit | null>, "protocol": 4, "libs": {name: sha256}}

The shell lives next to the plugin folder, never inside it: a shipped plugin carries no shell (the signed extension comes
with the WhyNot Cut installer), so `source_dir()` is missing there and callers must say so instead of installing.

Two families run during 3.0 (`family`): the bundle (protocol 4, jobs name a bundled `lib`) and the legacy bridge,
exactly 3.1.1 (no protocol; the engine syncs the libraries and sends `script`). Every other version is refused.

`~/.whynot-cut/bridge/config.json` (`config_path`, `write_config`) tells the daemon where the engine home is: always under
the user's home, user-only, no secret, never inside the extension:
    {"schema": 1, "engine_home": "<abs>", "launcher": "<abs>" | null, "written_by": "installer" | "engine", "at": "<iso>"}
`launcher` is <engine home>/bin/wnc-engine.cmd (Windows) or wnc-engine (macOS), the installer's shim, filled only when
that file exists: the daemon starts the engine through it and nothing else (js/bridge.js; docs/adobe/cep-bridge.md).

The signed path (Task 6): `tools/sign_zxp.py build` signs the assembled bundle into
whynot-cut/adobe/WhyNotCut-Bridge-3.0.0.zxp (`zxp_path`; a build artefact, git-ignored, shipped with the plugin) and
`install_zxp` puts it in place: signed only, every entry checked (no absolute path, `..`, link, name ending in `.` or a
space; at most 2,000 entries and 64 MB uncompressed), CRC-checked extraction into `<CEP root>/.wnc-staging/new`, then a
swap that keeps the previous copy as `<CEP root>/.wnc-staging/prev` (`staging_dir`: beside the extensions folder, on
the same volume, never inside it: CEP loads every folder there by its manifest). Every install first runs `recover`.
The unsigned dev build (`install_source`) is used only with WHYNOT_BRIDGE_DEV=1 (`dev_build_allowed`, plan
decision 9).

"Signed" here means the archive carries META-INF/signatures.xml: the engine does not check the signature itself. The
real check is CEP's, when the app loads the extension with PlayerDebugMode off (an extension whose signature fails
does not load).

Adobe-track owned (3.0 T6.3).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
import zlib
from pathlib import Path

from .common import PLUGIN_DIR, TEMPLATES_DIR, now_iso

EXT_ID = "ai.thewhynot.cut.bridge"
LEGACY_EXT_IDS = ("com.nh.bridge",)       # reel-editor 1.x
PRODUCT = "3.0.0"                         # the bundle's version (manifest, bridge.js BUNDLE, build.json product)
PROTOCOL = 4
LEGACY_VERSION = "3.1.1"                  # the one legacy bridge the engine still drives in 3.0 (removed in 3.1)
SHELL_FILES = ("CSXS/manifest.xml", "daemon.html", "ui/index.html", "ui/js/panel.js", "js/bridge.js",
               "jsx/wnc_host.jsx")
BRAND_TOKENS = PLUGIN_DIR.parent / "brand" / "tokens.css"     # copied to ui/tokens.css (an artefact, like the libs)
# the libraries the daemon runs, bundled into jsx/ (Photoshop scripts are standalone: not bundled)
LIBS = {"wnc_ppro_lib.jsx": "premiere", "wnc_ae_bridge.jsx": "after_effects", "wnc_ae_lib.jsx": "after_effects",
        "wnc_motion_lib.jsx": "after_effects"}
CONFIG_SCHEMA = 1
LAUNCHER_NAME = "wnc-engine.cmd" if os.name == "nt" else "wnc-engine"     # <engine home>/bin/<this>, the shim
ZXP_NAME = f"WhyNotCut-Bridge-{PRODUCT}.zxp"     # tools/sign_zxp.py build writes it; tools/release.py pins it
SIGNATURES = "META-INF/signatures.xml"
STAGING = ".wnc-staging"                        # <CEP root>/.wnc-staging/{new,prev}: beside extensions/, never in it
ZXP_MAX_ENTRIES = 2000                          # a ZXP with more entries is refused (the bundle has ~20)
ZXP_MAX_BYTES = 64 * 1024 * 1024                # ... or more uncompressed bytes in total (the bundle is < 1 MB)
DEV_ENV ="WHYNOT_BRIDGE_DEV"                   # =1: the unsigned dev build may be installed / driven (until 3.1)


def source_dir() -> Path:
    """The CEP shell's source folder: <repo>/adobe/cep-bridge (absent in a shipped plugin)."""
    return PLUGIN_DIR.parent / "adobe" / "cep-bridge"


def has_source() -> bool:
    return all((source_dir() / f).is_file() for f in SHELL_FILES)


def zxp_path() -> Path:
    """The signed bundle this plugin carries: whynot-cut/adobe/WhyNotCut-Bridge-<product>.zxp (absent until signed)."""
    return PLUGIN_DIR / "adobe" / ZXP_NAME


def dev_build_allowed() -> bool:
    """WHYNOT_BRIDGE_DEV=1 (off by default, 3.0 only): the unsigned build from the source may be installed."""
    return os.environ.get(DEV_ENV) == "1"


def lib_sources() -> dict[str, Path]:
    """{library name: its single source under whynot-cut/templates}."""
    return {name: TEMPLATES_DIR / folder / name for name, folder in LIBS.items()}


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def expected_libs() -> dict[str, str]:
    """{name: sha256} of the libraries this engine ships: what a bundle's heartbeat `libs` must report."""
    return {name: _sha(src) for name, src in lib_sources().items()}


def build_id(files: dict[str, str]) -> str:
    """16 hex of sha256 over the sorted (posix path, sha256) pairs: the same sources give the same build."""
    text = "".join(f"{p}\t{h}\n" for p, h in sorted(files.items()))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _git_sha() -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(source_dir()), "rev-parse", "HEAD"], capture_output=True, text=True,
                           timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    sha = r.stdout.strip()
    return sha if r.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", sha) else None


def assemble(dst: Path) -> Path:
    """Build the bundle in `dst`, which must not exist yet: the shell, the libraries into jsx/, then build.json.
    Returns `dst`. FileNotFoundError when a source is missing (a shipped plugin): check `has_source()` first."""
    src, dst = source_dir(), Path(dst)
    missing = [f for f in SHELL_FILES if not (src / f).is_file()]
    missing += [str(p) for p in lib_sources().values() if not p.is_file()]
    missing += [] if BRAND_TOKENS.is_file() else [str(BRAND_TOKENS)]
    if missing:
        raise FileNotFoundError(f"CEP bundle source incomplete in {src}: missing {', '.join(missing)}")
    dst.mkdir(parents=True)
    for f in SHELL_FILES:
        out = dst / f
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / f, out)
    for name, lib in lib_sources().items():
        shutil.copy2(lib, dst / "jsx" / name)
    shutil.copy2(BRAND_TOKENS, dst / "ui" / "tokens.css")
    files = {p.relative_to(dst).as_posix(): _sha(p) for p in sorted(dst.rglob("*")) if p.is_file()}
    build = {"product": PRODUCT, "build": build_id(files), "sha": _git_sha(), "protocol": PROTOCOL,
             "libs": {name: files[f"jsx/{name}"] for name in LIBS}}
    (dst / "build.json").write_text(json.dumps(build, indent=1) + "\n", encoding="utf-8")
    return dst


def _ver(v) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", str(v or ""))[:3])


def family(version, protocol=None) -> str | None:
    """Which family a running bridge belongs to, from its heartbeat: "bundle" (protocol 4, version = this engine's
    bundle), "legacy" (no protocol, exactly 3.1.1), else None (refused)."""
    if protocol is None:
        return "legacy" if version == LEGACY_VERSION else None
    return "bundle" if protocol == PROTOCOL and version == PRODUCT else None


def installed(ext: Path) -> dict | None:
    """The bundle installed in `ext` (None when there is none): {path, id, family, version, build, libs, signed}.
    family "bundle" = it carries a readable build.json; "legacy" = UNSIGNED, without build.json, and ours: the id
    ai.thewhynot.cut.bridge at a version up to 3.1.1, or the reel-editor `com.nh.bridge` (the install rule replaces it
    without force; the queue still drives exactly 3.1.1 only, see `family`); "unknown" = everything else, a signed
    extension without a readable build.json included (checked first: the install rule never replaces it without
    force)."""
    ext = Path(ext)
    manifest = ext / "CSXS" / "manifest.xml"
    try:
        text = manifest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = None
    try:
        build = json.loads((ext / "build.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        build = None
    if not isinstance(build, dict) or not isinstance(build.get("product"), str):
        build = None
    if text is None and build is None:      # a 3.1.x bridge-config.json alone is not an installation (never read)
        return None
    m = re.search(r'ExtensionBundleId="([^"]+)"', text or "")
    bid = m.group(1) if m else (ext.name if ext.name in (EXT_ID, *LEGACY_EXT_IDS) else None)
    m = re.search(r'ExtensionBundleVersion="([^"]+)"', text or "")
    version = (build or {}).get("product") or (m.group(1) if m else None)
    signed = (ext / "META-INF" / "signatures.xml").is_file()
    if build is not None:
        fam = "bundle"
    elif signed:
        fam = "unknown"
    elif bid in LEGACY_EXT_IDS or (bid == EXT_ID and _ver(version) and _ver(version) <= _ver(LEGACY_VERSION)):
        fam = "legacy"
    else:
        fam = "unknown"
    return {"path": str(ext), "id": bid, "family": fam, "version": version,
            "build": (build or {}).get("build"), "libs": (build or {}).get("libs"), "signed": signed}


def decide_install(cur: dict | None, new: dict, *, force: bool = False) -> dict:
    """The install rule: {"action": "install" | "replace" | "skip" | "keep", "reason"}.
      nothing installed -> install;  force -> replace;
      legacy (unsigned, ours, up to 3.1.1; com.nh.bridge) -> replace;
      the same build -> skip, except a signed build over the unsigned copy of the same sources -> replace;
      a newer product, or an unknown layout -> keep;
      a signed installation is never replaced by an unsigned build -> keep;  otherwise -> replace."""
    if not cur:
        return {"action": "install", "reason": "nothing installed"}
    if force:
        return {"action": "replace", "reason": "forced"}
    if cur.get("family") == "legacy" or (cur.get("id") in LEGACY_EXT_IDS and not cur.get("signed")):
        return {"action": "replace", "reason": f"the installed bridge {cur.get('version') or '?'} is the legacy family"}
    if cur.get("family") != "bundle":
        return {"action": "keep", "reason": f"the installed extension ({cur.get('version') or 'unknown version'}) is "
                                            "not one this engine knows"}
    if cur.get("build") and cur.get("build") == new.get("build") and (cur.get("signed") or not new.get("signed")):
        return {"action": "skip", "reason": f"build {cur['build']} is already installed"}
    if _ver(cur.get("version")) > _ver(new.get("version")):
        return {"action": "keep", "reason": f"the installed WhyNot Cut {cur.get('version')} is newer than "
                                            f"{new.get('version')}"}
    if cur.get("signed") and not new.get("signed"):
        return {"action": "keep", "reason": "the installed extension is signed; this build is not"}
    return {"action": "replace", "reason": f"build {cur.get('build') or '?'} -> {new.get('build') or '?'}"}


def install_source(ext: Path, *, force: bool = False) -> dict:
    """Assemble the bundle from the source (an unsigned dev build) and put it in `ext` when `decide_install` says so.
    Returns the decision plus {"installed": <the bundle now in ext>, "recovered"}. Nothing in `ext` is touched before
    the new bundle is complete (it is assembled in a temp folder first); `recover` runs first."""
    ext = Path(ext)
    recovered = None if _is_link(ext) else recover(ext)
    with tempfile.TemporaryDirectory(prefix="wnc-cep-") as t:
        new = installed(assemble(Path(t) / EXT_ID))
        decision = decide_install(installed(ext), new, force=force)
        if decision["action"] in ("install", "replace"):
            ext.parent.mkdir(parents=True, exist_ok=True)
            if ext.exists():
                shutil.rmtree(ext)
            shutil.copytree(Path(t) / EXT_ID, ext)
    return dict(decision, installed=installed(ext), new=new, recovered=recovered)


class ZxpError(ValueError):
    """A ZXP that is never installed: unsigned, unreadable, an unsafe entry, a CRC mismatch, another bundle id."""


def _is_link(p: Path) -> bool:
    """A symlink, or any Windows reparse point (a junction)."""
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & 0x400)   # REPARSE_POINT


def _remove(p: Path) -> None:
    """Remove a leftover folder of ours; a link is unlinked, never followed."""
    if _is_link(p):
        try:
            os.unlink(p)
        except OSError:
            os.rmdir(p)        # a Windows junction
    elif p.is_dir():
        shutil.rmtree(p)
    elif os.path.lexists(p):
        p.unlink()


def staging_dir(ext: Path | None = None) -> Path:
    """<CEP root>/.wnc-staging: %APPDATA%\\Adobe\\CEP\\.wnc-staging (Windows) or ~/Library/Application Support/Adobe/
    CEP/.wnc-staging (macOS), the parent of the extensions folder (`plat.cep_extensions_dir()`, or `ext`'s). It holds
    `new` (the extraction) and `prev` (the one previous copy): beside the extensions folder, so on the same volume (the
    renames are atomic) and never scanned by CEP, which loads every folder of the extensions folder by its manifest."""
    from . import plat
    root = Path(ext).parent if ext is not None else plat.cep_extensions_dir()
    return root.parent / STAGING


def recover(ext: Path) -> str | None:
    """Run at the start of every install or update. Moves the Task 6 leftovers `<ext>.new` (removed) and `<ext>.prev`
    (it becomes the staged prev) out of the extensions folder, then, when `ext` is missing and a previous copy exists
    (a crash between the two renames of the swap), puts that copy back. Returns what was put back, else None."""
    ext = Path(ext)
    st = staging_dir(ext)
    prev = st / "prev"
    old_new, old_prev = ext.with_name(ext.name + ".new"), ext.with_name(ext.name + ".prev")
    _remove(old_new)
    note = None
    if os.path.lexists(old_prev):
        if _is_link(old_prev) or not old_prev.is_dir():
            _remove(old_prev)
        elif not os.path.lexists(ext):
            os.replace(old_prev, ext)
            note = f"the previous WhyNot Cut extension was put back from {old_prev}"
        else:
            st.mkdir(parents=True, exist_ok=True)
            _remove(prev)
            os.replace(old_prev, prev)
    if not os.path.lexists(ext) and prev.is_dir() and not _is_link(prev):
        ext.parent.mkdir(parents=True, exist_ok=True)
        os.replace(prev, ext)
        note = f"the previous WhyNot Cut extension was put back from {prev} (an earlier update stopped half-way)"
    return note


def _zxp_members(zf: zipfile.ZipFile, name: str) -> list:
    """The file entries of the archive as (posix relative path, ZipInfo), every entry checked first: an absolute path,
    a drive, a backslash, an empty / `.` / `..` part, a part ending in `.` or a space (Windows drops those: `a.` and
    `a` would be the same file), a link or a duplicate refuses the whole archive; so do more than ZXP_MAX_ENTRIES
    entries or more than ZXP_MAX_BYTES uncompressed in total."""
    infos = zf.infolist()
    if len(infos) > ZXP_MAX_ENTRIES:
        raise ZxpError(f"{name} holds {len(infos)} entries (at most {ZXP_MAX_ENTRIES}): it was not installed")
    total = sum(zi.file_size for zi in infos)
    if total > ZXP_MAX_BYTES:
        raise ZxpError(f"{name} unpacks to {total / 1048576:.0f} MB (at most {ZXP_MAX_BYTES // 1048576} MB): it was "
                       "not installed")
    files, seen = [], set()
    for zi in infos:
        raw = zi.filename
        rel = raw[:-1] if zi.is_dir() else raw
        parts = rel.split("/")
        mode = (zi.external_attr >> 16) & 0o177777 if zi.create_system == 3 else 0     # 3 = made on unix
        if (not rel or raw.startswith("/") or "\\" in raw or ":" in raw or "\0" in raw
                or any(p in ("", ".", "..") or p.endswith((".", " ")) for p in parts) or stat.S_ISLNK(mode)):
            raise ZxpError(f"{name} holds an unsafe entry {raw!r}: it was not installed")
        key = rel.casefold()
        if key in seen:
            raise ZxpError(f"{name} holds {raw!r} twice: it was not installed")
        seen.add(key)
        if not zi.is_dir():
            files.append((rel, zi))
    return files


def _extract_checked(zf: zipfile.ZipFile, files: list, dst: Path, name: str) -> None:
    """Write every file under dst, checking each one's CRC-32 and size against the archive."""
    dst.mkdir(parents=True)
    root = os.path.abspath(dst)
    for rel, zi in files:
        out = dst.joinpath(*rel.split("/"))
        if not os.path.abspath(out).startswith(root + os.sep):
            raise ZxpError(f"{name}: {rel!r} escapes the extension folder")
        out.parent.mkdir(parents=True, exist_ok=True)
        crc, size = 0, 0
        try:
            with zf.open(zi) as src, open(out, "wb") as f:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    crc, size = zlib.crc32(chunk, crc), size + len(chunk)
                    if size > zi.file_size:              # more data than the entry declares: never written
                        raise ZxpError(f"{name}: {rel!r} is larger than it declares: it was not installed")
                    f.write(chunk)
        except (zipfile.BadZipFile, zlib.error, EOFError) as e:
            raise ZxpError(f"{name}: {rel!r} is damaged ({e}): it was not installed") from None
        if crc & 0xFFFFFFFF != zi.CRC or size != zi.file_size:
            raise ZxpError(f"{name}: {rel!r} fails its CRC check: it was not installed")


def install_zxp(zxp: Path, ext: Path, *, force: bool = False) -> dict:
    """Install the SIGNED bundle `zxp` in `ext` when `decide_install` says so (the signed path, plan Task 6).
    Every entry is checked before anything is written (`_zxp_members`); the files are extracted, CRC-checked, into
    `<CEP root>/.wnc-staging/new` (`staging_dir`); the manifest must name ai.thewhynot.cut.bridge. Then `ext` becomes
    `.wnc-staging/prev` (one previous copy is kept) and `new` becomes `ext`. `recover` runs first, so a run that
    stopped between the two renames is put right before anything else.
    ZxpError when the ZXP is not installed, with what happened to `ext`: left as it was, or the previous copy put
    back, or (only when even that rename fails) where the previous copy is, which the next install puts back. A
    staged `new` never survives a failure. Returns the decision plus {"installed", "new", "prev", "recovered"}."""
    zxp, ext = Path(zxp), Path(ext)
    st = staging_dir(ext)
    new, prev = st / "new", st / "prev"
    if _is_link(ext):
        raise ZxpError(f"{ext} is a link (a development extension): it was left alone")
    recovered = recover(ext)
    try:
        zf = zipfile.ZipFile(zxp)
    except (zipfile.BadZipFile, OSError) as e:
        raise ZxpError(f"{zxp.name} is not a readable ZXP ({e})") from None
    with zf:
        files = _zxp_members(zf, zxp.name)
        if SIGNATURES not in {rel for rel, _ in files}:
            raise ZxpError(f"{zxp.name} is not signed (no {SIGNATURES}): an unsigned extension is never installed "
                           "from a ZXP")
        ext.parent.mkdir(parents=True, exist_ok=True)
        st.mkdir(parents=True, exist_ok=True)
        _remove(new)
        try:
            _extract_checked(zf, files, new, zxp.name)
            got = installed(new)
            if not got or got.get("id") != EXT_ID or not got.get("signed"):
                raise ZxpError(f"{zxp.name} is not the WhyNot Cut extension ({EXT_ID}): it was not installed")
        except BaseException:
            _remove(new)
            raise
    got["path"] = str(ext)
    decision = decide_install(installed(ext), got, force=force)
    done = lambda: dict(decision, installed=installed(ext), new=got,  # noqa: E731
                        prev=str(prev) if prev.is_dir() else None, recovered=recovered)
    if decision["action"] not in ("install", "replace"):
        _remove(new)
        return done()
    had, moved = os.path.lexists(ext), False
    try:
        if had:
            _remove(prev)
            os.replace(ext, prev)
            moved = True
        os.replace(new, ext)
    except OSError as e:
        why = e.strerror or type(e).__name__
        if not moved:
            msg = f"the WhyNot Cut extension could not be moved aside ({why}): the installed one was left as it was"
        elif os.path.lexists(ext):
            msg = f"the new WhyNot Cut extension could not be put in place ({why})"
        else:
            try:
                os.replace(prev, ext)
                msg = (f"the new WhyNot Cut extension could not be put in place ({why}): the previous one was put "
                       "back")
            except OSError:
                msg = (f"the new WhyNot Cut extension could not be put in place ({why}) and the previous one is in "
                       f"{prev}: the next install (reel setup) puts it back")
        _remove(new)
        raise ZxpError(msg) from e
    return done()


def config_path() -> Path:
    """~/.whynot-cut/bridge/config.json: always the user's home (the daemon cannot see WHYNOT_HOME)."""
    return Path.home() / ".whynot-cut" / "bridge" / "config.json"


def read_config() -> dict | None:
    try:
        cfg = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return cfg if isinstance(cfg, dict) else None


def launcher_path(engine_home: Path) -> Path:
    """<engine home>/bin/wnc-engine.cmd (Windows) or wnc-engine (macOS): the only file the daemon ever starts."""
    return Path(engine_home) / "bin" / LAUNCHER_NAME


def write_config(engine_home: Path, *, launcher: Path | None = None, written_by: str = "engine") -> Path:
    """Write config.json atomically, user-only (folder 0700, file 0600 on POSIX). Returns its path.
    `launcher` (default: `launcher_path(engine_home)`) is filled only when that file exists, else null: the daemon
    re-reads config.json every 30 s, so whoever writes the shim later writes config.json again."""
    if written_by not in ("installer", "engine"):
        raise ValueError(f"written_by must be installer or engine, not {written_by!r}")
    path = config_path()
    home = Path(engine_home).resolve()
    cand = Path(launcher) if launcher else launcher_path(home)
    doc = {"schema": CONFIG_SCHEMA, "engine_home": str(home),
           "launcher": str(cand.resolve()) if cand.is_file() else None, "written_by": written_by, "at": now_iso()}
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    os.replace(tmp, path)
    return path
