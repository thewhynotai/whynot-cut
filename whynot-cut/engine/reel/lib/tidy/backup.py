# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Tidy: the backup copy of the project file (Python twin of E.backup, _upstream/js/engine.js).

"<name> (WhyNot Tidy backup 2026-10-12 154233).prproj" next to the project (A6b name; upstream: "(Tidy backup ...)",
same stamp format YYYY-MM-DD HHMMSS, local time). The copy is exclusive: an existing file is never overwritten
(FileExistsError, like the JS COPYFILE_EXCL), a failed copy leaves no half file behind, and the modification time of the
project is kept on the copy.
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

__all__ = ["backup", "backup_name", "is_backup_name", "TIDY_BACKUP"]

EXT = ".prproj"
TIDY_BACKUP = re.compile(r"\((?:WhyNot )?Tidy backup ")   # the same rule as TidyPlan.TIDY_BACKUP


def backup_name(project_path, now: datetime | None = None) -> str:
    """The file name of the backup of `project_path` made at `now` (default: the local time now)."""
    name = Path(project_path).name
    base = name[:-len(EXT)] if name.endswith(EXT) and len(name) > len(EXT) else name
    stamp = (now or datetime.now()).strftime("%Y-%m-%d %H%M%S")
    return "%s (WhyNot Tidy backup %s)%s" % (base, stamp, EXT)


def is_backup_name(name) -> bool:
    """True for a Tidy backup file name, the legacy "(Tidy backup ...)" and the new "(WhyNot Tidy backup ...)"."""
    return bool(TIDY_BACKUP.search(str(name or "")))


def backup(project_path, now: datetime | None = None) -> str:
    """Copy the (saved) project file next to itself and return the path of the copy. Raises FileNotFoundError when the
    project is missing, FileExistsError when the backup name is taken."""
    src = Path(project_path)
    dst = src.with_name(backup_name(src, now))
    with open(src, "rb") as fin:
        try:
            with open(dst, "xb") as fout:
                shutil.copyfileobj(fin, fout, 1024 * 1024)
        except FileExistsError:
            raise
        except BaseException:
            try:
                dst.unlink()                       # we created it a moment ago (exclusive open), so it is ours to remove
            except OSError:
                pass
            raise
    shutil.copystat(str(src), str(dst))
    return str(dst)
