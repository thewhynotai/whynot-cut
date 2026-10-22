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
    out["status_col"] = next((k for k, h in enumerate(out["headers"]) if h.lower().startswith("status")), None)
    return out


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
