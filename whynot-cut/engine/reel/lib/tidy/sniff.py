# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Tidy: read what a media file says about itself (Python twin of E.sniff, _upstream/js/engine.js).

Each video's first and last 2 MiB and each image's first 64 KiB are read (read only), decoded as latin-1 and handed to
`media.describe`, which decides camera or render, which camera, icon or not. Only the description is kept per path,
never the bytes (4 MiB per video). A file that cannot be read falls back to its name (`describe(item, None)`).
Camera RAW originals (.r3d .braw .crm .ari .insv) need no bytes: describe(item, None) calls them cameras.
"""
from __future__ import annotations

from . import media

__all__ = ["sniff", "HEAD", "IMAGE_HEAD"]

HEAD = 2097152        # E.HEAD: 2 MiB of a video, from the start and from the end
IMAGE_HEAD = 65536    # 64 KiB of an image
FIELDS = ("kind", "camId", "icon", "imgW", "imgH")


def _read_text(path, need: str):
    """latin-1 text of the head (and, for a video larger than the head, the tail) of the file, or None."""
    n = HEAD if need == "video" else IMAGE_HEAD
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(0)
            text = f.read(min(n, size)).decode("latin-1")
            if need == "video" and size > n:
                tail_len = min(n, size - n)
                f.seek(size - tail_len)
                text += f.read(tail_len).decode("latin-1")
            return text
    except (OSError, ValueError):
        return None


def sniff(items: list) -> list:
    """Fill kind / camId (videos) and icon / imgW / imgH (images) of every item that needs it (in place, returned)."""
    seen: dict = {}
    for it in items:
        need = media.needs_bytes(it)
        if not need and not media.CAMERA_RAW.search(it.get("path") or ""):
            continue
        path = it.get("path")
        if path in seen:                                  # keep the description, never the bytes
            for f in FIELDS:
                if f in seen[path]:
                    it[f] = seen[path][f]
            continue
        text = _read_text(path, need) if need else None
        media.describe(it, text)
        seen[path] = {f: it[f] for f in FIELDS if f in it}
    return items
