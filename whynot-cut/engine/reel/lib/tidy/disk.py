# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Tidy: what is on disk (Python twin of E.diskInfo, adobe/tools/tidy/_upstream/js/engine.js).

Files are only stat'ed, never changed. No path-key folding here (case, separators on Windows): the plan does that
(TidyPlan.pathKey), the stat needs the path as it is.
"""
from __future__ import annotations

import os
import stat

__all__ = ["disk_info"]


def disk_info(items: list) -> list:
    """Fill item['exists'] and item['size'] of every item (in place, returned). An item without a path counts as
    present with size 0; a directory has size 0; a path that cannot be stat'ed is missing with size 0. One stat per
    distinct path."""
    seen: dict = {}
    for it in items:
        path = it.get("path")
        if not path:
            it["exists"] = True
            it["size"] = 0
            continue
        if path not in seen:
            try:
                st = os.stat(path)
                seen[path] = {"exists": True, "size": 0 if stat.S_ISDIR(st.st_mode) else st.st_size}
            except (OSError, ValueError):
                seen[path] = {"exists": False, "size": 0}
        it["exists"] = seen[path]["exists"]
        it["size"] = seen[path]["size"]
    return items
