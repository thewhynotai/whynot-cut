"""Which folders are WhyNot Cut client folders (stdlib only; the hooks import it as a top-level module).

A folder with assets/ and data/ is a client folder only with a positive sign, because that layout is also a Hugo
site's or many web/ML repos' (structure review 4.1):
  * a `.whynot-client` file at its root (written by `reel scaffold`, `reel client-init`, `reel doctor --fix`), or
  * an `output/client_database/` folder (every onboarded client has one), or
  * it lies under the configured clients folder (`clients_root`: plugin option / WHYNOT_CLIENTS_ROOT, else the
    preferences file the engine reads).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

MARKER = ".whynot-client"
_UNSET = object()


def has_layout(p: Path) -> bool:
    return (p / "assets").is_dir() and (p / "data").is_dir()


def _lib(name: str):
    """settings/plat both as `lib.<name>` (engine) and as top-level modules (hooks put engine/reel/lib on sys.path)."""
    from importlib import import_module
    return import_module(f".{name}", __package__) if __package__ else import_module(name)


def clients_base(start: Path | None = None) -> Path | None:
    """The clients folder: the plugin option / WHYNOT_CLIENTS_ROOT, else `clients_root` in the nearest preferences
    file (looked up from `start`, as the engine does)."""
    plat = _lib("plat")
    explicit = plat.clients_root_setting()
    if explicit:
        return explicit
    v = _lib("settings").load(start).get("clients_root")
    return Path(plat.native_path(str(v))).expanduser() if v else None


def _under(p: Path, base: Path) -> bool:
    try:
        rp, rb = p.resolve(), base.resolve()
    except OSError:
        return False
    return rb in rp.parents


def is_client(p: Path, base=_UNSET) -> bool:
    """p is a client folder root. `base` = the clients folder if the caller already knows it (None = no clients
    folder); left out, it is read lazily and only when the folder has no marker of its own."""
    if not has_layout(p):
        return False
    if (p / MARKER).is_file() or (p / "output" / "client_database").is_dir():
        return True
    base = clients_base(p) if base is _UNSET else base
    return bool(base) and _under(p, base)


def in_sources(p: Path) -> bool:
    """p is (inside) the assets/ or data/ folder of a folder that has the client layout."""
    p = p.resolve()
    return any(a.name in ("assets", "data") and has_layout(a.parent) for a in [p, *p.parents])


def write_marker(root: Path) -> Path | None:
    """Write <root>/.whynot-client (small JSON) unless it is there. Never inside assets/ or data/. Returns the path
    when it was written, None when it already existed."""
    root = Path(root)
    if in_sources(root):
        raise ValueError(f"{root} is inside a client's assets/ or data/; the marker belongs at the client root")
    m = root / MARKER
    if m.exists():
        return None
    m.write_text(json.dumps({"whynot_client": 1, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z")}) + "\n",
                 encoding="utf-8")
    return m
