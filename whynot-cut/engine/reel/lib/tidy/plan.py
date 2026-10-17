# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Tidy: a project scan turned into a clean-up plan (Python twin of adobe/tools/tidy/src/js/plan.js).

Faithful to the JavaScript, which is the reference (the panel's live logic): the same function names in snake_case, the same
keys in the same order, the same rules. Nothing here touches Premiere or the disk, and the scan is never modified.

JS behaviour kept on purpose (the twin is the safety net for later changes, so it reproduces today's behaviour exactly):
* object property semantics: node ids are property names (5 and "5" are one id), `for (k in obj)` order (integer-like keys
  first) decides the order of `duplicates`, a property that is not there is left out of the result like `undefined` in JSON;
* UTF-16 strings: a nest name is cut at 50 UTF-16 units (an emoji is two), which can leave a lone surrogate;
* regular expressions as text: ASCII classes, `$` is the very end (`\\Z`), `\\s` is the JS whitespace set.
"""
from __future__ import annotations

import re

from . import classify as C
from . import jsutil as J
from .media import JS_WS, _WS_CODES

__all__ = ["BACKUP", "TEMP_SYNC", "TIDY_BACKUP", "IMAGE", "NAME_MAX", "path_key", "build", "nest_name", "synced_name"]

_A = re.ASCII
BACKUP = re.compile(r"\((?:WhyNot )?Hush (?:backup|cut) ", _A)
TEMP_SYNC = re.compile(r"^(?:WhyNot )?Tidy sync temp\Z", _A)
TIDY_BACKUP = re.compile(r"\((?:WhyNot )?Tidy backup ", _A)
IMAGE = re.compile(r"\.(png|jpe?g|gif|webp|psd|tiff?|heic|svg|ai|eps|bmp)\Z", _A | re.I)
NAME_MAX = 50

_NOT_WS = "[^" + "".join(re.escape(chr(c)) for c in _WS_CODES) + "]"
_WS_RUN = re.compile(JS_WS + "+")
_EDGE_SPACE = re.compile(r"^ | \Z")
_LAST_WORD = re.compile(" " + _NOT_WS + r"*\Z")
_EXT_TAIL = re.compile(r"\.[A-Za-z0-9]{2,5}\Z", _A)


def path_key(path, platform=None):
    """The key under which two media paths are the same file: Windows paths are case-insensitive and may use either
    separator; anywhere else the path is its own key."""
    return J.js_str(path).replace("\\", "/").lower() if platform == "win32" else path


def _add_path(keep: dict, path) -> None:
    parts = J.js_str(path).split("/")
    for i in range(1, len(parts) + 1):
        keep["/".join(parts[:i])] = True


def _clean(s) -> str:
    s = J.js_str(s if J.truthy(s) else "")
    s = _EDGE_SPACE.sub("", _WS_RUN.sub(" ", s))
    if J.u16len(s) > NAME_MAX:
        return _LAST_WORD.sub("", J.u16slice(s, 0, NAME_MAX), count=1)
    return s


def _bare(name) -> str:
    return _clean(_EXT_TAIL.sub("", J.js_str(name if J.truthy(name) else ""), count=1))


def nest_name(nest, texts, used_ids, by_id) -> str:
    """A nest is named after what it holds: its text, else an image, else the first clip (nested sequences last)."""
    first_clip = first_seq = ""
    for t in texts:
        t = _clean(t)
        if t:
            return t
    for uid in used_ids:
        it = by_id.get(J.key(uid))
        if it is None:
            continue
        seq = J.truthy(it.get("isSequence"))
        if not seq and IMAGE.search(J.js_str(it["path"] if J.truthy(it.get("path")) else "")):
            return _bare(it.get("name"))
        if not seq and not first_clip:
            first_clip = _bare(it.get("name"))
        if seq and not first_seq:
            first_seq = _clean(it.get("name"))
    return first_clip or first_seq or ""


def _nid(it: dict) -> str:
    return J.key(it["nodeId"]) if "nodeId" in it else "undefined"


def build(scan: dict, opts=None) -> dict:
    """scan: {items:[{nodeId,name,path,isSequence,duration,bin,exists,offline,size,color,kind,icon,camId}],
    bins:[{nodeId,path}], usage:{sequenceNodeId:[nodeIds its clips reference]}, texts:{nestNodeId:[text]}};
    opts: {unchecked, checked, noRename: {nodeId: true}, mode: 'reels'|'podcast', platform}.
    Returns {removals, moves, colors, duplicates, offline, emptyBins, renames, stats}."""
    opts = opts if J.truthy(opts) else {}
    unchecked = opts.get("unchecked") if J.truthy(opts.get("unchecked")) else {}
    forced = opts.get("checked") if J.truthy(opts.get("checked")) else {}
    items = scan["items"]
    usage = scan.get("usage") if J.truthy(scan.get("usage")) else {}
    by_id = {}
    for it in items:
        by_id[_nid(it)] = it

    # sequences that stay, and everything they use (Hush/Kalam backups do not count)
    backup, used, nest_ids = {}, {}, {}
    for it in items:
        if J.truthy(it.get("isSequence")) and BACKUP.search(J.js_str(it.get("name", J.MISSING))):
            backup[_nid(it)] = True
    for sid in J.js_order(list(usage)):
        if backup.get(sid):
            continue
        for ref in usage[sid]:
            k = J.key(ref)
            used[k] = True
            if k in by_id and J.truthy(by_id[k].get("isSequence")):
                nest_ids[k] = True
    ctx = {"nestIds": nest_ids, "mode": "podcast" if opts.get("mode") == "podcast" else "reels", "camNumbers": C.camera_numbers(items)}
    platform = opts.get("platform")

    # duplicates: several clip items pointing at the same file
    by_path, dup_of, duplicates = {}, {}, []
    for it in items:
        if J.truthy(it.get("isSequence")) or not J.truthy(it.get("path")):
            continue
        by_path.setdefault(J.key(path_key(it["path"], platform)), []).append(it)
    for pkey in J.js_order(list(by_path)):
        group = by_path[pkey]
        if len(group) < 2:
            continue
        used_copies = [g for g in group if used.get(_nid(g))]
        if len(used_copies) > 1:
            duplicates.append(J.mk(path=J.get(group[0], "path"), name=J.get(group[0], "name"), copies=len(group), used=len(used_copies)))
        elif len(used_copies) == 1:
            for g in group:
                if not used.get(_nid(g)):
                    dup_of[_nid(g)] = used_copies[0].get("nodeId", J.MISSING)

    removals, moves, colors, offline, gone, keep = [], [], [], [], {}, {}
    stats = {"removeCount": 0, "removeSize": 0, "totalSize": 0, "byType": {}}
    for it in items:
        nid = _nid(it)
        cat = C.category(it, ctx)
        stats["byType"][cat] = stats["byType"].get(cat, 0) + 1
        size = it["size"] if J.truthy(it.get("size")) else 0
        stats["totalSize"] += size
        if J.truthy(it.get("path")) and (J.truthy(it.get("offline")) or it.get("exists") is False):
            offline.append(J.mk(nodeId=J.get(it, "nodeId"), name=J.get(it, "name"), path=it["path"], used=bool(used.get(nid))))
        reason = None
        if J.truthy(it.get("isSequence")):
            reason = "backup" if backup.get(nid) else None
        elif not used.get(nid):
            reason = "duplicate" if J.truthy(dup_of.get(nid)) else "unused"
        if reason:
            # captions: Premiere cannot say which are in use; podcast footage and mics: raw material for the sync
            long_rec = J.num(it.get("duration")) >= C.MIC_MIN and cat in ("footage", "mics", "renders", "voice")
            opt_in = cat == "captions" or (ctx["mode"] == "podcast" and (cat == "footage" or cat == "mics" or long_rec))
            checked = not J.truthy(unchecked.get(nid)) and (not opt_in or bool(J.truthy(forced.get(nid))))
            removals.append(J.mk(nodeId=J.get(it, "nodeId"), name=J.get(it, "name"), reason=reason, category=cat, size=size, checked=checked))
            if checked:
                gone[nid] = True
                stats["removeCount"] += 1
                stats["removeSize"] += size
                continue
        to = C.bin_for(cat, it, ctx)
        _add_path(keep, to)
        if it.get("bin", J.MISSING) != to:
            moves.append(J.mk(nodeId=J.get(it, "nodeId"), name=J.get(it, "name"), **{"from": J.get(it, "bin")}, to=to))
        if it.get("color", J.MISSING) != C.COLORS.get(cat):
            colors.append({"nodeId": it.get("nodeId", J.MISSING), "color": C.COLORS.get(cat)})
            if colors[-1]["nodeId"] is J.MISSING:
                del colors[-1]["nodeId"]

    # every kept item ends up in its bin, so the old bins empty out; only bins something goes into stay
    empty_bins = []
    for b in (scan.get("bins") if J.truthy(scan.get("bins")) else []):
        if not keep.get(J.key(J.get(b, "path"))):
            empty_bins.append(J.mk(nodeId=J.get(b, "nodeId"), path=J.get(b, "path")))
    empty_bins.sort(key=lambda b: -len(J.js_str(b.get("path", J.MISSING)).split("/")))        # deepest first (stable, like JS)

    # nests are named after what they hold: their text, else an image, else the first clip
    renames, taken = [], {}
    texts = scan.get("texts") if J.truthy(scan.get("texts")) else {}
    no_rename = opts.get("noRename") if J.truthy(opts.get("noRename")) else {}
    for it in items:
        if J.truthy(it.get("isSequence")) and not nest_ids.get(_nid(it)):
            taken[J.key(J.get(it, "name"))] = True
    for it in items:
        nid = _nid(it)
        if not J.truthy(it.get("isSequence")) or not nest_ids.get(nid) or gone.get(nid):
            continue
        t = texts.get(nid)
        u = usage.get(nid)
        to = nest_name(it, t if J.truthy(t) else [], u if J.truthy(u) else [], by_id)
        if not to:
            taken[J.key(J.get(it, "name"))] = True
            continue
        base, n = to, 2
        while taken.get(to) or to in J.PROTO_KEYS:     # `taken["constructor"]` is the inherited function in JS: truthy
            to = base + " " + str(n)
            n += 1
        taken[to] = True
        if to != it.get("name", J.MISSING):
            renames.append(J.mk(nodeId=J.get(it, "nodeId"), **{"from": J.get(it, "name")}, to=to, checked=not J.truthy(no_rename.get(nid))))

    return {"removals": removals, "moves": moves, "colors": colors, "duplicates": duplicates, "offline": offline,
            "emptyBins": empty_bins, "renames": renames, "stats": stats}


def synced_name(project_name, existing_names=None) -> str:
    """The sequence the synced podcast is built into: "<project> - Synced", else "... - Synced 2", "... - Synced 3"."""
    base = re.sub(r"\.prproj\Z", "", J.js_str(project_name if J.truthy(project_name) else "Podcast"), count=1) + " - Synced"
    taken = existing_names if J.truthy(existing_names) else []
    name, n = base, 2
    while name in taken:
        name = base + " " + str(n)
        n += 1
    return name
