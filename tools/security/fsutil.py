# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Small file-system helpers shared by the scan kit (Addendum L, L-T1). Stdlib only.

  walk_files    files under a folder, NEVER descending into or reading through a junction or symlink (house rule: a
                recursive walk that follows a link reads, and a delete would remove, the real files it points to)
  which_safe    absolute path of a program found on PATH, never from the current folder and never from a relative PATH
                entry (on Windows the current folder is searched first by default: the planted-binary class, L-G11)
"""
import os
import stat
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__"}


def is_reparse(entry):
    """True for a symlink or any Windows reparse point (junction, mount point, cloud placeholder)."""
    try:
        st = entry.stat(follow_symlinks=False)
    except OSError:
        return True
    return entry.is_symlink() or bool(getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def walk_files(root, skip_dirs=SKIP_DIRS):
    stack = [str(root)]
    while stack:
        d = stack.pop()
        try:
            it = list(os.scandir(d))
        except OSError:
            continue
        for e in it:
            if is_reparse(e):
                continue
            if e.is_dir(follow_symlinks=False):
                if e.name not in skip_dirs:
                    stack.append(e.path)
            elif e.is_file(follow_symlinks=False):
                yield e.path


def which_safe(name):
    cwd = os.path.normcase(os.path.abspath(os.getcwd()))
    exts = [""]
    if os.name == "nt":
        exts = [e.lower() for e in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";") if e] + [""]
    for p in os.environ.get("PATH", "").split(os.pathsep):
        if not p or not os.path.isabs(p):
            continue
        if os.path.normcase(os.path.abspath(p)) == cwd:
            continue
        for ext in exts:
            cand = Path(p) / (name + ext)
            if cand.is_file() and (os.name == "nt" or os.access(cand, os.X_OK)):
                return str(cand)
    return None
