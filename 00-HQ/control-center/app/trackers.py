"""New things on the dashboard without new code:
- trackers: each markdown file listed in config.json `trackers` (its first table) becomes a panel;
- new badge: a BOARD task first seen in the last `new_badge_hours` gets a "New" badge.
"""
import datetime as dt, json, os, re
from pathlib import Path


def _clean(cell):
    return re.sub(r"\*\*|`", "", cell).strip()


def read(spec, hq_dir):
    out = {"id": spec["id"], "title": spec.get("title", spec["id"]), "title_ar": spec.get("title_ar") or spec.get("title"),
           "file": spec["file"], "headers": [], "rows": [], "updated": "", "status_col": None, "error": ""}
    try:
        text = Path(hq_dir, spec["file"]).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        out["error"] = f"cannot read {spec['file']}: {e.strerror}"
        return out
    m = re.search(r"^Updated:\s*(.+?)\.(?:\s|$)", text, re.M)
    out["updated"] = m.group(1).strip() if m else ""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            out["headers"] = [_clean(c) for c in line.strip().strip("|").split("|")]
            for row in lines[i + 2:]:
                if not row.startswith("|"):
                    break
                out["rows"].append([_clean(c) for c in row.strip().strip("|").split("|")])
            break
    n = len(out["headers"])
    if n:  # a stray "|" inside a cell adds cells: keep the column count, merge the overflow into the last column
        out["rows"] = [r[:n - 1] + [" | ".join(x for x in r[n - 1:] if x)] if len(r) > n else r + [""] * (n - len(r))
                       for r in out["rows"]]
    out["status_col"] = next((k for k, h in enumerate(out["headers"]) if h.lower().startswith("status")), None)
    out["file_changed"] = dt.datetime.fromtimestamp(Path(hq_dir, spec["file"]).stat().st_mtime).isoformat(timespec="minutes")
    out["items"] = _items(out)
    out["done"] = sum(1 for i in out["items"] if i["status_short"].upper().startswith("DONE"))
    return out


def _col(headers, pattern, default=None):
    return next((k for k, h in enumerate(headers) if re.search(pattern, h, re.I)), default)


def _items(t):
    """Each table row as one readable item: number, title, short status word, full status, next step, blockers, rest."""
    h = t["headers"]
    if not h:
        return []
    num = _col(h, r"^#$|^no\b|^id$", 0)
    title = _col(h, r"phase|task|title|item|name", 1 if len(h) > 1 else 0)
    stat, nxt, blk = t["status_col"], _col(h, r"^next"), _col(h, r"block")
    used = {num, title, stat, nxt, blk}
    items = []
    for r in t["rows"]:
        status = r[stat] if stat is not None else ""
        items.append({
            "num": r[num], "title": r[title], "status": status,
            "status_short": re.split(r"\s*[(:;—–]", status, maxsplit=1)[0].strip() or status,
            "next": r[nxt] if nxt is not None and r[nxt] not in ("—", "-") else "",
            "blockers": r[blk] if blk is not None and r[blk] not in ("—", "-") else "",
            "more": [[h[k], r[k]] for k in range(len(h)) if k not in used and r[k] not in ("", "—", "-")],
        })
    return items


def mark_new(path, ids, now, hours):
    """Remember when each id was first seen. The very first run marks nothing new (everything was already there)."""
    try:
        with open(path, encoding="utf-8") as f:
            seen = json.load(f)
    except FileNotFoundError:
        seen = None
    except (OSError, ValueError):
        return set()  # unreadable for now: never rewrite it as a "first run" (that would wipe every New badge)
    first = seen is None
    seen = seen or {}
    for i in ids:
        if i not in seen:
            seen[i] = "1970-01-01T00:00:00" if first else now.isoformat(timespec="seconds")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(seen, f, indent=1)
        os.replace(path + ".tmp", path)
    except OSError:
        pass
    limit = now - dt.timedelta(hours=hours)
    return {i for i in ids if dt.datetime.fromisoformat(seen[i]) > limit}
