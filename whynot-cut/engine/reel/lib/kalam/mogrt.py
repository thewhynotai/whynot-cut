# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Kalam: the Motion Graphics Templates gallery scan (Python twin of the owner's G.scan, adobe/tools/kalam/_upstream/
js/mogrt.js; Task 5 moved it out of the panel because a UXP panel has no Node fs / zlib / crypto).

scan(base, cache_dir) -> [{path, name, folder, textFields, thumb}]: every .mogrt under Premiere's Local Templates folder
(`base`), sorted by folder then name (UTF-16 code-unit order, like the JavaScript it replaces). A .mogrt is a zip:
definition.json (name, text controls) and thumb.png are read from it (read only) with stdlib zipfile; the thumbnail is
written as <cache_dir>/mogrt-thumbs/<sha1 of the path>.png and the records are cached in <cache_dir>/mogrt-index.json keyed
"<path>|<modification time>", so a template is opened again only when it changed (or its thumbnail was lost). Cache files
are written atomically (temp name + replace) with default permissions (nothing in them is secret). A hidden
file or folder (a name starting with ".") is skipped; a template that cannot be read still gets a record (name from the
file name, no text fields, no thumbnail), as upstream. definition_info / folder_of are the engine twins of the panel's pure
functions KalamMogrt.definitionInfo / folderOf (tested against the JS port).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile


def _atomic_write(path: str, data: bytes) -> None:
    """write through a temp name and replace: a crash or a full disk leaves the previous file whole (default permissions:
    the cache holds thumbnails and a template index, nothing secret)"""
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

__all__ = ["scan", "definition_info", "folder_of"]


def _localized(v) -> str:
    db = v.get("strDB") if isinstance(v, dict) else None
    if not isinstance(db, list) or not db:
        return ""
    for e in db:
        if isinstance(e, dict) and e.get("localeString") == "en_US":
            return e.get("str") or ""
    first = db[0]
    return (first.get("str") or "") if isinstance(first, dict) else ""


def definition_info(d) -> dict:
    """{name, textFields: [names of the template's text controls]} (definition.json -> what the gallery shows)"""
    d = d if isinstance(d, dict) else {}
    fields = []
    controls = d.get("clientControls")
    for c in controls if isinstance(controls, list) else []:
        if isinstance(c, dict) and c.get("type") == 6:
            fields.append(_localized(c.get("uiName")) or ("Text %d" % (len(fields) + 1)))
    name = _localized(d.get("capsuleNameLocalized")) or d.get("capsuleName") or ""
    return {"name": name if isinstance(name, str) else "", "textFields": fields}


def folder_of(p, base) -> str:
    """the template's folder below `base`, "/"-separated ("" for a template directly in `base`)"""
    rel = str(p)[len(str(base)):].lstrip("/\\")
    cut = max(rel.rfind("/"), rel.rfind("\\"))
    return rel[:cut].replace("\\", "/") if cut > 0 else ""


def _u16(s: str) -> bytes:
    return s.encode("utf-16-be", "surrogatepass")


def _basename(p: str) -> str:
    """path.basename(p, '.mogrt'): the extension is cut only when it is exactly ".mogrt" (lower case), as in Node"""
    n = re.split(r"[\\/]", p)[-1]
    return n[:-len(".mogrt")] if n.endswith(".mogrt") and len(n) > len(".mogrt") else n


def _read(p: str, key: str, thumbs: str):
    try:
        with zipfile.ZipFile(p) as z:
            names = set(z.namelist())
            definition = json.loads(z.read("definition.json").decode("utf-8")) if "definition.json" in names else None
            png = z.read("thumb.png") if "thumb.png" in names else None
        info = definition_info(definition or {})
        thumb = ""
        if png:
            thumb = os.path.join(thumbs, hashlib.sha1(p.encode("utf-8")).hexdigest() + ".png")
            _atomic_write(thumb, png)
        return {"path": p, "name": info["name"] or _basename(p), "textFields": info["textFields"], "thumb": thumb}, True
    except Exception:  # noqa: BLE001  (upstream catches everything: a template we cannot read is still listed)
        return {"path": p, "name": _basename(p), "textFields": [], "thumb": ""}, False


def scan(base, cache_dir) -> list:
    base, cache_dir = str(base), str(cache_dir)
    thumbs = os.path.join(cache_dir, "mogrt-thumbs")
    index_file = os.path.join(cache_dir, "mogrt-index.json")
    try:
        os.makedirs(thumbs, exist_ok=True)
    except OSError:
        pass
    try:
        with open(index_file, encoding="utf-8") as f:
            cache = json.load(f)
        if not isinstance(cache, dict):
            cache = {}
    except (OSError, ValueError):
        cache = {}
    out, seen = [], set()

    def walk(d):
        try:
            real = os.path.realpath(d)
            if real in seen:                      # a link back into the tree: never loop
                return
            seen.add(real)
            names = sorted(os.listdir(d))
        except OSError:
            return
        for n in names:
            if n.startswith("."):
                continue
            p = os.path.normpath(os.path.join(d, n))
            try:
                st = os.stat(p)
            except OSError:
                continue
            if os.path.isdir(p):
                walk(p)
                continue
            if not n.lower().endswith(".mogrt"):
                continue
            key = "%s|%s" % (p, st.st_mtime_ns)
            hit = cache.get(key)
            if not hit or not os.path.exists(hit.get("thumb") or os.path.join(os.sep, "nonexistent")):
                hit, ok = _read(p, key, thumbs)
                if ok:
                    cache[key] = hit
            hit = dict(hit)
            hit["folder"] = folder_of(p, base)
            out.append(hit)

    walk(base)
    try:
        _atomic_write(index_file, json.dumps(cache, ensure_ascii=False).encode("utf-8"))
    except OSError:
        pass
    out.sort(key=lambda m: (_u16(m["folder"]), _u16(m["name"]), _u16(m["path"])))
    return [{"path": m["path"], "name": m["name"], "folder": m["folder"], "textFields": m["textFields"],
             "thumb": m["thumb"]} for m in out]
