"""`reel settings --allow-reel` (3.0 T3.9): let the editor run `reel` without a permission prompt for every command.

Merges `{"permissions": {"allow": ["Bash(reel *)", "PowerShell(reel *)"]}}` into <clients folder>/.claude/settings.json.

Rule forms (checked against the Claude Code permissions docs, 2026-10-13):
  * `Bash(reel *)` and `PowerShell(reel *)` are the two tool names a shell command goes through (PowerShell(...) is a
    real rule name: the same shape as Bash, `*` anywhere, `:*` equivalent to a trailing ` *`, matching case-insensitive).
    The plugin's bin/ is on PATH while it is enabled, so Claude writes `reel <command> ...`; a trailing ` *` with the
    space also matches a bare `reel`, and not `reelx`. The skills already declare the same two rules in `allowed-tools`.
  * NOT added: the wrapper's absolute path (bin/reel, bin\reel.cmd). It lives in the plugin cache folder, whose name
    changes with every version, so a rule for it would go stale at the next update and grant a path the editor never
    chose. Claude Code also strips only timeout/time/nice/nohup/stdbuf, so `Bash(reel *)` does not cover
    `/path/to/reel ...` anyway: that form is simply prompted, which is the safe default.
  * Equivalent spellings already in the file (`Bash(reel:*)`) count as present, so nothing is added twice.
Project allow rules apply only after the editor accepts Claude Code's workspace-trust dialog for the folder.

Merge, never overwrite: every other key of the file stays (order kept), other allow/deny/ask entries stay, a rule
already there is not added twice. A change to an existing file is preceded by a timestamped copy next to it
(settings.json.whynot-backup-YYYYMMDD-HHMMSS); a run that changes nothing writes nothing, so the installer can call it
on every run. A UTF-8 BOM is accepted (PowerShell 5.1 writes one; the rewrite drops it). A file that is not valid JSON
(comments, trailing commas) or whose `permissions` / `allow` has the wrong type is refused with guidance and left alone.
Never prompts: it is called by the installer.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from .errors import FileFormatError, Guidance

RULES = ("Bash(reel *)", "PowerShell(reel *)")
EQUIVALENT = {"Bash(reel *)": {"Bash(reel *)", "Bash(reel:*)"},
              "PowerShell(reel *)": {"PowerShell(reel *)", "PowerShell(reel:*)"}}
SETTINGS_REL = Path(".claude") / "settings.json"
BACKUP_INFIX = ".whynot-backup-"


def check_clients_root(p: Path, configured: Path | None) -> Path:
    """The folder that holds the client folders, or Guidance. A new empty folder is accepted (the installer may call
    this before the first client exists); a folder with other material is accepted only if it is the configured
    clients folder or already holds a client folder."""
    from .client_marker import has_layout, in_sources
    p = Path(p).expanduser()
    where = str(p)
    if not p.is_dir():
        raise Guidance(f"{p} is not a folder (nothing was written)",
                       "Pass --clients-root the folder that holds the client folders, e.g. D:/WhyNot Clients.", where=where)
    if has_layout(p) or in_sources(p):
        raise Guidance(f"{p} is a client folder (or inside one), not the folder that holds the clients (nothing was written)",
                       "Pass --clients-root the parent folder: the one that contains the client folders.", where=where)
    try:
        entries = [e for e in p.iterdir() if not e.name.startswith(".")]
    except OSError as e:
        raise Guidance(f"cannot read {p}: {e.strerror or e}", "Check the folder exists and you may write in it.", where=where) from None
    if not entries:
        return p
    try:
        same = bool(configured) and Path(configured).resolve() == p.resolve()
    except OSError:
        same = False
    if same or any(has_layout(e) for e in entries if e.is_dir()):
        return p
    raise Guidance(f"{p} is not a WhyNot Cut clients folder: it holds other files and no client folder (nothing was written)",
                   "Pass --clients-root the folder that holds the client folders (each with assets/ and data/), or "
                   "set it as the clients folder first.", where=where)


def read_settings(path: Path):
    """(settings dict, existed). Not JSON / not UTF-8 / not an object -> Guidance; the file is never touched."""
    from .common import read_json
    try:
        doc = read_json(path, None)
    except FileFormatError as e:
        raise Guidance(f"{e.path} cannot be read: {e.reason} (line {e.line}, column {e.column}); nothing was changed",
                       "Fix or remove that line (settings.json must be plain JSON: no comments, no trailing commas), "
                       "then run this again.", where=str(path)) from None
    if doc is None and not path.exists():
        return {}, False
    if not isinstance(doc, dict):
        raise Guidance(f"{path} is not a JSON object; nothing was changed",
                       "settings.json must hold one JSON object ({ ... }). Fix the file, then run this again.", where=str(path))
    return doc, True


def merge_allow(doc: dict, rules=RULES, where: str = "settings.json") -> list[str]:
    """Add the missing `rules` to doc["permissions"]["allow"] in place; the rules that were added."""
    perms = doc.setdefault("permissions", {})
    if not isinstance(perms, dict):
        raise Guidance(f"{where}: \"permissions\" is not an object; nothing was changed",
                       "Fix that key (it should be { \"allow\": [ ... ] }), then run this again.", where=where)
    allow = perms.setdefault("allow", [])
    if not isinstance(allow, list):
        raise Guidance(f"{where}: \"permissions.allow\" is not a list; nothing was changed",
                       "Fix that key (it should be a list of rules), then run this again.", where=where)
    have = {a.strip() for a in allow if isinstance(a, str)}
    added = [r for r in rules if not (EQUIVALENT.get(r, {r}) & have)]
    allow.extend(added)
    return added


def allow_reel(clients_root: Path, configured: Path | None = None) -> dict:
    """The command: {ok, file, added, backup, changed}. Idempotent; the backup only when an existing file changes."""
    from .common import write_json
    root = check_clients_root(clients_root, configured)
    path = root / SETTINGS_REL
    doc, existed = read_settings(path)
    added = merge_allow(doc, where=str(path))
    backup = None
    if added:
        if existed:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            backup = path.with_name(f"{path.name}{BACKUP_INFIX}{stamp}")
            n = 1
            while backup.exists():            # two runs in one second never overwrite a backup
                n += 1
                backup = path.with_name(f"{path.name}{BACKUP_INFIX}{stamp}-{n}")
            shutil.copy2(path, backup)
        try:
            write_json(path, doc)
        except OSError as e:
            raise Guidance(f"cannot write {path}: {e.strerror or e}", "Check the folder is not read-only, then run this again.",
                           where=str(path)) from None
    return {"ok": True, "file": str(path), "added": added, "backup": str(backup) if backup else None,
            "changed": bool(added)}
