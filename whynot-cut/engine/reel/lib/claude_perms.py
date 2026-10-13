"""`reel settings --allow-reel` (3.0 T3.9): let the editor run `reel` without a permission prompt for every command.

Merges `{"permissions": {"allow": ["Bash(reel *)", "PowerShell(reel *)"]}}` into `.claude/settings.json` of the clients
folder AND of every client folder under it.

Why every client folder: Claude Code reads a project's `.claude/settings.json` ONLY from the folder it was launched in
(no parent-folder fallback, docs "Claude Code discovers..."). The editor launches Claude in a client folder, so a rule
that lives only in the clients folder would silently do nothing there; it applies when Claude is started in the clients
folder itself. So the command writes the same merge into the clients folder and into each existing client folder (a
`.whynot-client` marker, or assets/ + data/ with WhyNot Cut output in it: output/client_database or output/projects); `--client <dir>` targets one client folder only. New clients
inherit it: `reel client-init` / `reel scaffold` add it to the new folder when the clients folder already holds the rules
(the editor opted in: a permission they declined is never added behind their back).

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
on every run. Read -> merge -> backup -> write of each file runs under its per-file lock (lib/file_lock; a
`settings.json.lock` stays next to the file), so the installer, `/whynot-cut:start` and a second run never lose each
other's edit. A read-only settings.json is refused up front (no backup is left behind), and a backup or write that fails
is Guidance (a fresh backup is removed again). A UTF-8 BOM is accepted (PowerShell 5.1 writes one; the rewrite drops it).
A file that is not valid JSON (comments, trailing commas) or whose `permissions` / `allow` has the wrong type is refused
with guidance and left alone. Never prompts: it is called by the installer.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from .errors import FileFormatError, Guidance
from .file_lock import locked

RULES = ("Bash(reel *)", "PowerShell(reel *)")
EQUIVALENT = {"Bash(reel *)": {"Bash(reel *)", "Bash(reel:*)"},
              "PowerShell(reel *)": {"PowerShell(reel *)", "PowerShell(reel:*)"}}
SETTINGS_REL = Path(".claude") / "settings.json"
BACKUP_INFIX = ".whynot-backup-"
# What does not count as "material" when deciding that a folder is empty (a new clients folder): the editor's own
# `.claude` and the files the OS adds by itself. Every other dot-entry (`.git`, `.ssh`, ...) is material, so a folder
# that holds only those is not taken for a clients folder.
IGNORED_ENTRIES = {".claude", ".ds_store", ".localized", "desktop.ini", "thumbs.db"}


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
        entries = [e for e in p.iterdir() if e.name.lower() not in IGNORED_ENTRIES]
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


def check_client_folder(p: Path) -> Path:
    """One client folder (`--client`), or Guidance."""
    from .client_marker import MARKER, has_layout, in_sources
    p = Path(p).expanduser()
    where = str(p)
    if not p.is_dir():
        raise Guidance(f"{p} is not a folder (nothing was written)", "Pass --client the client's folder.", where=where)
    if in_sources(p):
        raise Guidance(f"{p} is inside a client's assets/ or data/ (nothing was written)",
                       "Pass --client the client folder itself (the one that holds assets/ and data/).", where=where)
    if (p / MARKER).is_file() or has_layout(p):      # named explicitly by the editor/installer: the layout is enough
        return p
    raise Guidance(f"{p} is not a WhyNot Cut client folder (nothing was written)",
                   "Pass --client a folder that holds assets/ and data/ (a client folder), or use --clients-root for the "
                   "folder that holds all the clients.", where=where)


def client_dirs(root: Path) -> list[Path]:
    """The existing client folders directly under the clients folder, by a POSITIVE sign only (client_marker's rule):
    a `.whynot-client` marker, or the assets/ + data/ layout together with WhyNot Cut output already in it
    (`output/client_database` or `output/projects`). A bare assets/ + data/ layout is not enough: a Hugo site and many
    web/ML repos have it, and this command must not write `.claude/` into them (`--client <dir>` still names one)."""
    from .client_marker import MARKER, has_layout
    try:
        kids = sorted(e for e in Path(root).iterdir() if e.is_dir())
    except OSError:
        return []

    def positive(k: Path) -> bool:
        try:
            if (k / MARKER).is_file():
                return True
            return has_layout(k) and any((k / "output" / sub).is_dir() for sub in ("client_database", "projects"))
        except OSError:
            return False
    return [k for k in kids if positive(k)]


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


def _backup_path(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}{BACKUP_INFIX}{stamp}")
    n = 1
    while backup.exists():                # two runs in one second never overwrite a backup
        n += 1
        backup = path.with_name(f"{path.name}{BACKUP_INFIX}{stamp}-{n}")
    return backup


def apply_file(path: Path) -> dict:
    """The merge into ONE settings.json, under its lock: {file, added, backup, changed}. Guidance when it cannot be
    done (the file is left as it was and no backup is left behind)."""
    from .common import write_json
    path = Path(path)
    if holds_rules(path):                 # a no-op run creates neither `.claude/` nor the lock file
        return {"file": str(path), "added": [], "backup": None, "changed": False}
    with locked(path):
        doc, existed = read_settings(path)
        added = merge_allow(doc, where=str(path))
        if not added:
            return {"file": str(path), "added": [], "backup": None, "changed": False}
        if existed and not os.access(path, os.W_OK):
            raise Guidance(f"cannot change {path}: the file is read-only (nothing was changed)",
                           "Clear the read-only attribute of settings.json (Windows: file Properties, untick Read-only; "
                           "macOS/Linux: chmod u+w), then run this again.", where=str(path))
        backup = None
        try:
            if existed:
                backup = _backup_path(path)
                try:
                    shutil.copyfile(path, backup)
                except OSError as e:
                    raise Guidance(f"cannot write the backup of {path}: {e.strerror or e} (nothing was changed)",
                                   "Check the folder is not read-only or full, then run this again.", where=str(path)) from None
            try:
                write_json(path, doc)
            except OSError as e:
                raise Guidance(f"cannot write {path}: {e.strerror or e} (nothing was changed)",
                               "Check that settings.json and its folder are not read-only and this user may write "
                               "there, then run this again.", where=str(path)) from None
        except BaseException:
            if backup is not None:        # nothing was changed: a fresh backup is not a record of any change
                try:
                    backup.unlink()
                except OSError:
                    pass
            raise
        return {"file": str(path), "added": added, "backup": str(backup) if backup else None, "changed": True}


def holds_rules(path: Path) -> bool:
    """The settings.json at `path` already allows every rule (the editor opted in); False for anything unreadable."""
    try:
        doc, existed = read_settings(Path(path))
        allow = doc.get("permissions", {}).get("allow", []) if existed else []
        have = {a.strip() for a in allow if isinstance(a, str)} if isinstance(allow, list) else set()
    except (Guidance, AttributeError, OSError):
        return False
    return all(EQUIVALENT.get(r, {r}) & have for r in RULES)


def inherit_for_new_client(client: Path) -> dict | None:
    """`reel client-init` / `reel scaffold`: a NEW client folder gets the rules when its parent (the clients folder)
    already holds them. None = the editor has not opted in. Never raises: a new client must not fail on this."""
    client = Path(client)
    target = client / SETTINGS_REL
    if not holds_rules(client.parent / SETTINGS_REL):
        return None
    try:
        return {"ok": True, **apply_file(target)}
    except Guidance as g:
        return {"ok": False, "file": str(target), "error": g.error, "how": g.how}
    except OSError as e:
        return {"ok": False, "file": str(target), "error": str(e),
                "how": "Run `reel settings --allow-reel --client <this folder>` again."}


def allow_reel(clients_root: Path | None, configured: Path | None = None, client: Path | None = None) -> dict:
    """The command: {ok, file, added, backup, changed, files: [{ok, file, added, backup, changed, error?, how?}]}.

    Default: the clients folder and every client folder under it (files[0] is the clients folder). `client`: that one
    client folder only. file/added/backup describe files[0]; `changed` is true when ANY file changed. Idempotent; a
    backup only when an existing file changes. A file that cannot be merged does not stop the others: it is listed with
    its error and the command exits 1 (a busy lock exits 2)."""
    if client is not None:
        targets = [check_client_folder(client)]
    else:
        root = check_clients_root(clients_root, configured)
        targets = [root, *client_dirs(root)]
    files, blocked = [], None
    for t in targets:
        path = t / SETTINGS_REL
        try:
            files.append({"ok": True, **apply_file(path)})
        except Guidance as g:
            files.append({"ok": False, "file": str(path), "added": [], "backup": None, "changed": False,
                          "error": g.error, "how": g.how})
            if getattr(g, "blocked", False):
                blocked = g.error
        except OSError as e:              # settings.json is a folder, an ACL / antivirus lock, ...: this file only
            files.append({"ok": False, "file": str(path), "added": [], "backup": None, "changed": False,
                          "error": f"cannot read or change {path}: {e.strerror or e} (nothing was changed)",
                          "how": "Check that settings.json is a normal file this user may read and write (not a folder, "
                                 "not locked by another program), then run this again."})
    first = files[0]
    doc = {"ok": all(f["ok"] for f in files), "file": first["file"], "added": first["added"], "backup": first["backup"],
           "changed": any(f["changed"] for f in files), "files": files}
    bad = [f for f in files if not f["ok"]]
    if bad:
        err = bad[0]["error"] if len(bad) == 1 else (
            f"{len(bad)} of {len(files)} settings files could not be changed: " + "; ".join(f["error"] for f in bad))
        doc.update(error=err, how=bad[0]["how"], where=bad[0]["file"])
        if blocked:
            doc["blocked"] = blocked
    return doc
