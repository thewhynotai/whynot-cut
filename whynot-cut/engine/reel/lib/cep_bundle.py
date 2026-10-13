"""The WhyNot Cut CEP bundle (`ai.thewhynot.cut.bridge`): where its source lives and how a bundle folder is assembled.

The CEP **shell** (CSXS/manifest.xml, index.html, js/bridge.js, jsx/host.jsx) lives in `<repo>/adobe/cep-bridge/`, next
to the plugin folder, never inside it: a shipped plugin carries no shell (the signed extension comes with the WhyNot Cut
installer), so `source_dir()` is missing there and callers must say so instead of installing anything. The JSX libraries
stay in `whynot-cut/templates/**` as their single source (3.0 T6.3, design decision 1).

Adobe-track owned (3.0 T6.3). Task 1: `source_dir`, `assemble` (the shell only). Later tasks add the libraries and
`build.json` to `assemble`, and the install rule.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .common import PLUGIN_DIR

SHELL_FILES = ("CSXS/manifest.xml", "index.html", "js/bridge.js", "jsx/host.jsx")


def source_dir() -> Path:
    """The CEP shell's source folder: <repo>/adobe/cep-bridge (absent in a shipped plugin)."""
    return PLUGIN_DIR.parent / "adobe" / "cep-bridge"


def assemble(dst: Path) -> Path:
    """Copy the bundle into `dst`, which must not exist yet; returns `dst`. Task 1: the shell files, byte for byte.
    FileNotFoundError when the source is missing (a shipped plugin): check `source_dir()` first."""
    src, dst = source_dir(), Path(dst)
    missing = [f for f in SHELL_FILES if not (src / f).is_file()]
    if missing:
        raise FileNotFoundError(f"CEP bundle source incomplete in {src}: missing {', '.join(missing)}")
    dst.mkdir(parents=True)
    for f in SHELL_FILES:
        out = dst / f
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / f, out)
    return dst
