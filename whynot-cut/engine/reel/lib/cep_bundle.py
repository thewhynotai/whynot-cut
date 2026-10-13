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

Adobe-track owned (3.0 T6.3). Task 6 adds `install_zxp` (the signed path).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
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


def source_dir() -> Path:
    """The CEP shell's source folder: <repo>/adobe/cep-bridge (absent in a shipped plugin)."""
    return PLUGIN_DIR.parent / "adobe" / "cep-bridge"


def has_source() -> bool:
    return all((source_dir() / f).is_file() for f in SHELL_FILES)


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
    family "bundle" = it carries a readable build.json; "legacy" = UNSIGNED and exactly 3.1.1, or the reel-editor
    `com.nh.bridge`; "unknown" = everything else, a signed extension without a readable build.json included (checked
    first: the install rule never replaces it without force)."""
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
    elif bid in LEGACY_EXT_IDS or version == LEGACY_VERSION:
        fam = "legacy"
    else:
        fam = "unknown"
    return {"path": str(ext), "id": bid, "family": fam, "version": version,
            "build": (build or {}).get("build"), "libs": (build or {}).get("libs"), "signed": signed}


def decide_install(cur: dict | None, new: dict, *, force: bool = False) -> dict:
    """The install rule: {"action": "install" | "replace" | "skip" | "keep", "reason"}.
      nothing installed -> install;  force -> replace;  legacy (unsigned 3.1.1, com.nh.bridge) -> replace;
      the same build -> skip;  a newer product, or an unknown layout -> keep;
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
    if cur.get("build") and cur.get("build") == new.get("build"):
        return {"action": "skip", "reason": f"build {cur['build']} is already installed"}
    if _ver(cur.get("version")) > _ver(new.get("version")):
        return {"action": "keep", "reason": f"the installed WhyNot Cut {cur.get('version')} is newer than "
                                            f"{new.get('version')}"}
    if cur.get("signed") and not new.get("signed"):
        return {"action": "keep", "reason": "the installed extension is signed; this build is not"}
    return {"action": "replace", "reason": f"build {cur.get('build') or '?'} -> {new.get('build') or '?'}"}


def install_source(ext: Path, *, force: bool = False) -> dict:
    """Assemble the bundle from the source (an unsigned dev build) and put it in `ext` when `decide_install` says so.
    Returns the decision plus {"installed": <the bundle now in ext>}. Nothing in `ext` is touched before the new
    bundle is complete (it is assembled in a temp folder first)."""
    ext = Path(ext)
    with tempfile.TemporaryDirectory(prefix="wnc-cep-") as t:
        new = installed(assemble(Path(t) / EXT_ID))
        decision = decide_install(installed(ext), new, force=force)
        if decision["action"] in ("install", "replace"):
            ext.parent.mkdir(parents=True, exist_ok=True)
            if ext.exists():
                shutil.rmtree(ext)
            shutil.copytree(Path(t) / EXT_ID, ext)
    return dict(decision, installed=installed(ext), new=new)


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
