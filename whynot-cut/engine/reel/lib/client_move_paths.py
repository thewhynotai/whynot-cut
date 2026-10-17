# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Where a write in a client folder really lands (3.0 Phase 4, T4.4/T4.9, and T4.5's client move).

The client's assets/ and data/ are read-only for the engine. A link inside output/ (a junction or a symlink, made by
hand or left by a copy) can carry a write there without any path saying "data/". So a writer checks the REAL path of
what it is about to create, followed through every link, against the real paths of assets/ and data/.

Case: Windows and macOS file systems ignore case by default, so the comparison folds case there (it can only refuse
more, never less). Stdlib only.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

FOLD_CASE = sys.platform in ("win32", "darwin")
PROTECTED = ("data", "assets")


def real(p) -> str:
    """The path followed through every link (also for a path that does not exist yet: its existing part is)."""
    return os.path.realpath(str(p))


def inside(path, folder, fold: bool = FOLD_CASE) -> bool:
    """Is `path` the folder itself or under it (both already real)? Case folded where the file system folds it."""
    a, b = os.path.normpath(str(path)), os.path.normpath(str(folder))
    if fold:
        a, b = a.casefold(), b.casefold()
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def _is_client(d: Path) -> bool:
    """A client folder: assets/ and data/, and a sign WhyNot Cut worked there (its marker, or output/client_database/).
    A store that merely has folders named assets and data (a mirror on a bigger disk) is not one."""
    return (d / "assets").is_dir() and (d / "data").is_dir() and \
        ((d / ".whynot-client").exists() or (d / "output" / "client_database").is_dir())


def other_client(landed: str, root) -> str | None:
    """The client folder that `landed` is inside of, when it is not this client."""
    me = real(root)
    p = Path(landed)
    for anc in [p, *p.parents]:
        if inside(real(anc), me) and inside(me, real(anc)):
            return None
        if _is_client(anc):
            return str(anc)
    return None


def protected_refusal(root, target, how: str | None = None) -> dict | None:
    """`{"refused", "how"}` when `target` (followed through links) lands in the client's data/ or assets/, or inside
    ANOTHER client's folder (a link to another client's output/ would mix two clients), else None. A link elsewhere
    (output/ moved to a bigger disk) is fine. Nothing is created by the check."""
    root = Path(root)
    landed = real(target)
    is_output = Path(os.path.normpath(str(target))) == Path(os.path.normpath(str(root / "output")))
    fix = how or (("output/ itself is a link to that place: point it somewhere outside the client's data/ and assets/ "
                   "(or make it a plain folder again, moving its contents first), then run the command again.")
                  if is_output else
                  "Remove that link inside output/ (delete only the link itself, never what it points to), then run "
                  "the command again.")
    for name in PROTECTED:
        if inside(landed, real(root / name)):
            return {"refused": f"{target} leads into the client's {name}/ ({landed}) through a link: the engine never "
                               f"writes into {name}/ (nothing was written)", "how": fix}
    other = other_client(landed, root)
    if other:
        return {"refused": f"{target} leads into another client's folder ({other}) through a link: the engine writes "
                           "only into this client's own output (nothing was written)", "how": fix}
    return None


def first_refusal(root, targets, how: str | None = None) -> dict | None:
    for t in targets:
        r = protected_refusal(root, t, how)
        if r:
            return r
    return None
