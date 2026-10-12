"""Install steps `gitbash` and `claude` (3.0 T7.1 step 6, T7.3; installer.md R.2 step 6 and B.1).

gitbash  Windows only. Claude Code runs its Bash tool and bash hooks through Git Bash. A bash.exe that Claude Code finds
         by itself (settings env CLAUDE_CODE_GIT_BASH_PATH, `git` on PATH, Program Files) is left alone; one in a place
         it does not look (%LOCALAPPDATA%\\Programs\\Git, our own copy) is written into settings `env`; none at all: the
         pinned PortableGit is unpacked per user (no admin) into %LOCALAPPDATA%\\WhyNotCut\\git and set the same way.
claude   registers the WhyNot Cut marketplace and plugin with Claude Code:
         (c) a `thewhynot-ai` marketplace with another source is removed first (CLI), and the 1.x `reel-editor@*`
             plugin is switched off in enabledPlugins (ID-5: it would put a second `reel` on PATH);
         (a) with a Claude Code CLI (not older than components `claude_code.min`): `plugin marketplace add <source>`,
             then `plugin install whynot-cut@thewhynot-ai --scope user` (or `plugin update` once installed);
         (b) always: extraKnownMarketplaces + enabledPlugins merged into ~/.claude/settings.json, so a desktop-only
             editor gets the plugin on the next Claude Code start.
         Until `marketplace.url` is pinned the source is the managed folder ~/.whynot-cut/marketplace, refreshed from
         the folder the installer runs from; once pinned, the URL with autoUpdate (ID-7).
settings.json is merged, never overwritten: read as utf-8-sig, key order kept, a timestamped backup only when something
changes, written atomically (indent 2, UTF-8, trailing newline). Invalid JSON is never written to: the step is amber and
gives the editor the JSON to paste. Managed settings are never touched. Stdlib only.
"""
from __future__ import annotations

import copy
import fnmatch
import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path
from typing import Iterable, Mapping, Optional

from . import base

CLI_TIMEOUT = 300
SFX_TIMEOUT = 900
GIT_BASH_KEY = "CLAUDE_CODE_GIT_BASH_PATH"
GIT_DOWNLOAD = "https://git-scm.com/download/win"
LEGACY_PLUGINS = ("reel-editor@*",)  # ID-5: the 1.x product name
_COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.local.md", ".git")


class SettingsUnreadable(Exception):
    """settings.json exists but cannot be merged (not UTF-8, not JSON, not an object, a key of ours is not an object).
    `snippet` is the JSON the editor can merge in by hand (one line); `reason` completes "settings.json is ..."."""

    def __init__(self, snippet: str, reason: str):
        super().__init__(reason)
        self.snippet = snippet
        self.reason = reason


# --------------------------------------------------------------------------------------------- Claude Code CLI
def _ver_key(p: Path):
    for part in reversed(p.parts):
        if re.fullmatch(r"\d+(\.\d+)+", part):
            return tuple(int(x) for x in part.split("."))
    return (0,)


def _is_win(platform) -> bool:
    return platform == "win32" or str(platform).startswith("win")


def claude_candidates(env: Mapping, home, platform: str, sandbox: bool) -> list:
    """Every Claude Code CLI on this machine, best first: the same order and rules as WhyNotCut/tools/find_claude.py
    (`candidates`; that file is not shipped, so its logic lives here too): $CLAUDE_CLI, `claude` on PATH, fixed npm /
    native install paths, then the CLIs bundled with the desktop app, newest version first. `platform` is sys.platform
    style ("win32", "darwin") or ours ("win-x64", ...). In a sandbox only $WNC_CLAUDE_CLI / $CLAUDE_CLI and the bundles
    under the (fake) home are searched: never PATH, AppData from the environment, or /usr/local."""
    home = Path(home)
    win = _is_win(platform)
    exe = "claude.exe" if win else "claude"
    out = []
    if sandbox:
        out += [Path(env[k]) for k in ("WNC_CLAUDE_CLI", "CLAUDE_CLI") if env.get(k)]
        appdata = home / "AppData" / "Roaming"
    else:
        if env.get("CLAUDE_CLI"):
            out.append(Path(env["CLAUDE_CLI"]))
        which = shutil.which("claude", path=env.get("PATH"))
        if which:
            out.append(Path(which))
        appdata = Path(env.get("APPDATA") or home / "AppData" / "Roaming")
        if win:
            local = Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local")
            out += [local / "Programs" / "claude" / exe, home / ".local" / "bin" / exe, appdata / "npm" / "claude.cmd"]
        else:
            out += [home / ".local" / "bin" / exe, home / ".claude" / "local" / exe, Path("/usr/local/bin") / exe,
                    Path("/opt/homebrew/bin") / exe]
    bundle = (appdata if win else home / "Library" / "Application Support") / "Claude" / "claude-code"
    found = []
    if bundle.is_dir():
        found += [p for p in bundle.glob(f"*/*/{exe}") if p.is_file()]
        found += [p for p in bundle.glob(f"*/{exe}") if p.is_file()]
    found.sort(key=_ver_key, reverse=True)
    return [p for p in out if p.is_file()] + found


def claude_command(cli) -> list:
    """The CLI as a command list; a `.py` (the test stand-in) runs on this interpreter, like WNC_TEST_UV."""
    cli = str(cli)
    return [sys.executable, "-B", cli] if cli.lower().endswith(".py") else [cli]


def _version(text) -> Optional[tuple]:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", str(text or ""))
    return tuple(int(x) for x in m.groups()) if m else None


# --------------------------------------------------------------------------------------------- settings.json
def settings_snippet(marketplace: Optional[dict] = None, plugin_id: Optional[str] = None,
                     env: Optional[dict] = None) -> str:
    """One line of JSON with what we would merge: shown to the editor when settings.json cannot be merged."""
    snip = {}
    if marketplace:
        snip["extraKnownMarketplaces"] = marketplace
    if plugin_id:
        snip["enabledPlugins"] = {plugin_id: True}
    if env:
        snip["env"] = env
    return json.dumps(snip, ensure_ascii=False)


def _read_settings(path: Path, snippet: str) -> tuple:
    """(settings dict, original bytes or None when the file is absent). SettingsUnreadable when it cannot be merged;
    an empty / whitespace-only file counts as {}."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {}, None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise SettingsUnreadable(snippet, f"not UTF-8 text ({e.reason} at byte {e.start})") from None
    if not text.strip():
        return {}, raw
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise SettingsUnreadable(snippet, f"not valid JSON ({e.msg} at line {e.lineno} column {e.colno})") from None
    if not isinstance(data, dict):
        raise SettingsUnreadable(snippet, "not valid JSON for settings (the top level is not an object)")
    for k in ("extraKnownMarketplaces", "enabledPlugins", "env"):
        if k in data and not isinstance(data[k], dict):
            raise SettingsUnreadable(snippet, f"not valid JSON for settings (`{k}` is not an object)")
    try:
        _encode(data)
    except (UnicodeError, ValueError) as e:  # a lone UTF-16 surrogate parses but cannot be written back
        raise SettingsUnreadable(snippet, "not valid JSON for settings (it cannot be written back as UTF-8: "
                                          f"{type(e).__name__})") from None
    return data, raw


def _encode(data: dict) -> bytes:
    """The bytes we write: indent 2, UTF-8 (ensure_ascii=False), trailing newline. UnicodeError / ValueError when the
    data cannot be written; called before anything is written, so a failure leaves no stray backup."""
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _file_mode(path: Path) -> Optional[int]:
    try:
        return stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        return None


def write_backup(path: Path, raw: bytes, mode: Optional[int] = None) -> Path:
    """`<settings.json>.whynot-backup-YYYYmmdd-HHMMSS` (`-N` when taken) holding exactly `raw`, with `mode` (the
    original file's permission bits)."""
    stem = f"{path.name}.whynot-backup-{base.stamp()}"
    n = 0
    while True:
        cand = path.with_name(stem if n == 0 else f"{stem}-{n}")
        try:
            with open(cand, "xb") as f:
                f.write(raw)
            break
        except FileExistsError:
            n += 1
    if mode is not None:
        os.chmod(cand, mode)
    return cand


def _write_settings(path: Path, raw_before: Optional[bytes], data: dict, make_backup: bool = True) -> Optional[str]:
    """Encode first (nothing is written when that fails), then a backup of the exact original bytes (when there was a
    file and make_backup), then the atomic write; the original permission bits are kept on both. A settings.json that
    is a symlink (dotfiles) keeps being one: its target is written."""
    payload = _encode(data)
    target = Path(os.path.realpath(path)) if os.path.islink(path) else path
    mode = _file_mode(target)
    backup = None
    if raw_before is not None and make_backup:
        backup = str(write_backup(path, raw_before, mode))
    base.atomic_write_bytes(target, payload, mode)
    return backup


def merge_claude_settings(path, *, marketplace: Optional[dict], plugin_id: Optional[str],
                          env: Optional[dict] = None, disable=(), dry_run: bool = False,
                          make_backup: bool = True) -> dict:
    """Merge into a Claude Code settings.json. `marketplace` = {name: entry}: extraKnownMarketplaces[name] is replaced
    by ours (in place, other marketplaces kept); enabledPlugins[plugin_id] = true; `env` merged key by key; plugins
    matching a `disable` pattern (fnmatch, e.g. "reel-editor@*") that are on are set to false, never added. Returns
    {changed, backup, disabled}; nothing is written (and no backup made) when nothing changes or with dry_run.
    make_backup=False: the caller keeps its own backup of the original (step_claude, around the CLI calls)."""
    path = Path(path)
    data, raw = _read_settings(path, settings_snippet(marketplace, plugin_id, env))
    before = copy.deepcopy(data)
    if marketplace:
        ekm = data.setdefault("extraKnownMarketplaces", {})
        for name, entry in marketplace.items():
            ekm[name] = copy.deepcopy(entry)
    disabled = []
    plugins = data.get("enabledPlugins")
    if disable and isinstance(plugins, dict):
        for key, on in list(plugins.items()):
            if on is True and key != plugin_id and any(fnmatch.fnmatchcase(key, pat) for pat in disable):
                plugins[key] = False
                disabled.append(key)
    if plugin_id:
        data.setdefault("enabledPlugins", {})[plugin_id] = True
    if env:
        e = data.setdefault("env", {})
        for k, v in env.items():
            e[k] = v
    changed = data != before
    backup = _write_settings(path, raw, data, make_backup) if changed and not dry_run else None
    return {"changed": changed, "backup": backup, "disabled": disabled}


def unmerge_snippet(marketplace_name: str, plugin_id: str, env_keys: Iterable = ()) -> str:
    """One line of JSON naming what uninstall removes (shown when settings.json cannot be changed)."""
    return json.dumps({"remove": {"extraKnownMarketplaces": [marketplace_name], "enabledPlugins": [plugin_id],
                                  "env": sorted(env_keys)}}, ensure_ascii=False)


def unmerge_claude_settings(path, *, marketplace_name: str, plugin_id: str, env_keys_if_under: dict,
                            enable=(), dry_run: bool = False, make_backup: bool = True) -> dict:
    """Undo merge_claude_settings (uninstall): remove extraKnownMarketplaces[marketplace_name] and
    enabledPlugins[plugin_id], and each env key of `env_keys_if_under` only when its value is a path inside (or equal
    to) the given folder. A container emptied by this is removed. `enable`: plugin ids the install switched off (ID-5)
    that are set back to true, only while they are still false. Same backup / atomic rules; {changed, backup,
    enabled}. make_backup=False: the caller keeps its own backup of the original (around the CLI calls)."""
    path = Path(path)
    snippet = unmerge_snippet(marketplace_name, plugin_id, env_keys_if_under)
    data, raw = _read_settings(path, snippet)
    if raw is None:
        return {"changed": False, "backup": None, "enabled": []}
    before = copy.deepcopy(data)
    for key, sub in (("extraKnownMarketplaces", marketplace_name), ("enabledPlugins", plugin_id)):
        cont = data.get(key)
        if isinstance(cont, dict) and sub in cont:
            del cont[sub]
            if not cont:
                del data[key]
    env = data.get("env")
    if isinstance(env, dict):
        for k, folder in env_keys_if_under.items():
            v = env.get(k)
            if isinstance(v, str) and v.strip() and base._within(base._norm(v.strip()), base._norm(folder),
                                                                 strict=False):
                del env[k]
        if not env and before.get("env"):
            del data["env"]
    enabled = []
    plugins = data.get("enabledPlugins")
    if isinstance(plugins, dict):
        for key in enable:
            if isinstance(key, str) and key != plugin_id and plugins.get(key) is False:
                plugins[key] = True
                enabled.append(key)
    changed = data != before
    backup = _write_settings(path, raw, data, make_backup) if changed and not dry_run else None
    return {"changed": changed, "backup": backup, "enabled": enabled}


# --------------------------------------------------------------------------------------------- marketplace
def marketplace_entry(components: dict, paths: base.Paths) -> dict:
    """The extraKnownMarketplaces entry: the pinned URL with autoUpdate, else the managed folder (ID-7)."""
    url = base.cget(components, "marketplace.url")
    if not base.is_placeholder(url) and isinstance(url, str) and url.strip():
        return {"source": {"source": "url", "url": url.strip()}, "autoUpdate": True}
    return {"source": {"source": "directory", "path": str(paths.marketplace_dir)}}


def refresh_marketplace_dir(src_root, paths: base.Paths) -> bool:
    """Copy `.claude-plugin/` and `whynot-cut/` of src_root (the unpacked installer zip or a checkout; without
    __pycache__, *.pyc, *.local.md, .git) into ~/.whynot-cut/marketplace.new, then swap it in: the current folder
    becomes marketplace.prev (an older prev is removed with safe_rmtree). False (nothing done) when src_root is the
    managed folder itself, or when that folder is a link someone made on purpose."""
    src_root, dest = Path(src_root), paths.marketplace_dir
    if base._real(src_root) == base._real(dest) or base.is_link(dest):
        return False
    new, prev = dest.with_name(dest.name + ".new"), dest.with_name(dest.name + ".prev")
    roots = [paths.whynot]
    if not base.safe_rmtree(new, roots):
        raise OSError(f"cannot clear the leftover {new}")
    try:
        for part in (".claude-plugin", "whynot-cut"):
            shutil.copytree(src_root / part, new / part, ignore=_COPY_IGNORE)
        if os.path.lexists(prev) and not base.safe_rmtree(prev, roots):
            raise OSError(f"cannot remove the older {prev}")
        if os.path.lexists(dest):
            base._replace(dest, prev)
        try:
            base._replace(new, dest)
        except OSError:
            if os.path.lexists(prev) and not os.path.lexists(dest):
                base._replace(prev, dest)
            raise
    except BaseException:
        try:
            base.safe_rmtree(new, roots)
        except OSError:
            pass
        raise
    return True


def _read_json(path: Path):
    """A Claude Code bookkeeping file (known_marketplaces.json, installed_plugins.json), read-only and defensively."""
    try:
        return json.loads(path.read_bytes().decode("utf-8-sig"))
    except (OSError, ValueError):
        return None


def _norm_path(p: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(p)))


def _same_source(a, b) -> bool:
    if not isinstance(a, dict) or not isinstance(b, dict) or a.get("source") != b.get("source"):
        return False
    if a.get("source") in ("directory", "file"):
        pa, pb = a.get("path"), b.get("path")
        return isinstance(pa, str) and isinstance(pb, str) and _norm_path(pa) == _norm_path(pb)
    if a.get("source") == "url":
        return a.get("url") == b.get("url")
    return a == b


def _known_source(paths: base.Paths, name: str):
    known = _read_json(paths.claude_dir / "plugins" / "known_marketplaces.json")
    entry = known.get(name) if isinstance(known, dict) else None
    return entry.get("source") if isinstance(entry, dict) else None


def _legacy_source(paths: base.Paths, name: str, ours: dict):
    """The source Claude Code knows `name` by, when it is not ours (a 2.x directory, a git repo ...); else None."""
    src = _known_source(paths, name)
    if src is None or _same_source(src, ours):
        return None
    return src


def _plugin_installed(paths: base.Paths, plugin_id: str) -> bool:
    data = _read_json(paths.claude_dir / "plugins" / "installed_plugins.json")
    if not isinstance(data, dict):
        return False
    plugins = data.get("plugins")
    return (isinstance(plugins, dict) and plugin_id in plugins) or plugin_id in data


def _describe(src) -> str:
    if isinstance(src, dict):
        return f"{src.get('source')} {src.get('path') or src.get('url') or src.get('repo') or ''}".strip()
    return repr(src)


# --------------------------------------------------------------------------------------------- claude step
def _cli_register(ctx: base.Ctx, cmd: list, name: str, plugin_id: str, source: dict, legacy,
                  problems: list) -> bool:
    """(c) + (a) through the CLI. True when the plugin is installed / updated from our marketplace."""
    log = ctx.log

    def run(args: list) -> tuple:
        rc, out = base.run_cmd(ctx, cmd + args, CLI_TIMEOUT)
        if rc != 0:
            problems.append(f"`claude {' '.join(args)}` failed (exit {rc}: {base.tail(out)})")
        return rc, out

    ok = True
    if legacy is not None:
        log.info(f"Claude Code knows the {name} marketplace from another source ({_describe(legacy)}); removing it "
                 "first (the plugin's data lives in the engine home, so nothing is lost)")
        ok = run(["plugin", "marketplace", "remove", name])[0] == 0
    src_arg = source.get("url") or source.get("path")
    rc, out = base.run_cmd(ctx, cmd + ["plugin", "marketplace", "add", src_arg], CLI_TIMEOUT)
    if rc != 0:
        if _same_source(_known_source(ctx.paths, name), source):
            log.info(f"marketplace {name} is already registered with this source")
        else:
            problems.append(f"`claude plugin marketplace add {src_arg}` failed (exit {rc}: {base.tail(out)})")
            return False
    action = (["plugin", "update", plugin_id] if _plugin_installed(ctx.paths, plugin_id)
              else ["plugin", "install", plugin_id, "--scope", "user"])
    return run(action)[0] == 0 and ok


def step_claude(ctx: base.Ctx) -> base.StepResult:
    paths, c, log = ctx.paths, ctx.components, ctx.log
    name = str(base.cget(c, "marketplace.name") or "thewhynot-ai")
    plugin_id = f"{base.cget(c, 'marketplace.plugin') or 'whynot-cut'}@{name}"
    entry = marketplace_entry(c, paths)
    source = entry["source"]
    where = source.get("url") or source.get("path")
    if ctx.args.dry_run:
        return base.StepResult("claude", "skipped", f"dry run: would register {plugin_id} from {where} and merge "
                                                    f"{paths.settings_file}")
    problems, needs = [], []

    # the managed marketplace folder (directory source, until marketplace.url is pinned)
    if source["source"] == "directory":
        src_root = ctx.plugin_root.parent
        if (src_root / ".claude-plugin" / "marketplace.json").is_file():
            try:
                if refresh_marketplace_dir(src_root, paths):
                    log.info(f"marketplace folder {paths.marketplace_dir} refreshed from {src_root}")
            except OSError as e:
                log.warn(f"could not refresh {paths.marketplace_dir}: {e}")
                problems.append(f"the marketplace folder could not be refreshed ({e}); the previous copy is used")
        if not (paths.marketplace_dir / ".claude-plugin" / "marketplace.json").is_file():
            return base.StepResult("claude", "amber", f"nothing to register: {src_root} has no "
                                                      f".claude-plugin/marketplace.json and {paths.marketplace_dir} "
                                                      "is empty",
                                   needs_you="run the installer from the unpacked WhyNot Cut folder")

    # settings.json is checked and its original bytes kept BEFORE the CLI runs: `plugin install` / `marketplace add`
    # write into it too, so an unreadable file never reaches the CLI and the one backup holds the editor's original
    sfile = paths.settings_file
    snippet = settings_snippet({name: entry}, plugin_id)
    try:
        _data, original = _read_settings(sfile, snippet)
    except SettingsUnreadable as e:
        detail = (f"{sfile} is {e.reason}; it was left exactly as it is and the Claude Code CLI was not run (it "
                  "writes there too). Repair it and merge in the JSON below by hand")
        return _claude_done(ctx, "amber", "; ".join([detail] + problems), e.snippet, "settings", entry, None, [])
    except OSError as e:
        return _claude_done(ctx, "amber", "; ".join([f"cannot read {sfile}: {e}"] + problems), snippet, "settings",
                            entry, None, [])
    backup = None
    if original is not None:
        try:
            backup = write_backup(sfile, original, _file_mode(sfile))
        except OSError as e:
            return _claude_done(ctx, "amber", "; ".join([f"cannot back up {sfile}: {e}; nothing was changed"]
                                                        + problems), snippet, "settings", entry, None, [])
    method, r, fail = "settings", None, None
    try:
        method = _cli_phase(ctx, name, plugin_id, source, problems, needs)
        # (b) always: settings.json (no second backup: the one above holds the original)
        try:
            r = merge_claude_settings(sfile, marketplace={name: entry}, plugin_id=plugin_id, disable=LEGACY_PLUGINS,
                                      make_backup=False)
        except SettingsUnreadable as e:  # only when the CLI left it unreadable
            fail = (f"{sfile} is {e.reason} after the Claude Code CLI wrote it; it was not changed further. Merge in "
                    "the JSON below by hand", e.snippet)
        except (OSError, UnicodeError, ValueError) as e:
            fail = (f"could not write {sfile}: {type(e).__name__}: {e}", snippet)
    finally:  # also on an unexpected error: the backup survives exactly when the file changed
        backup = _keep_backup_if_changed(sfile, original, backup)
    if fail is not None:
        return _claude_done(ctx, "amber", "; ".join([fail[0]] + problems), fail[1], method, entry, backup, [])
    if r["disabled"]:
        log.info(f"switched off {', '.join(r['disabled'])} in Claude Code: the older product name puts a second "
                 "`reel` on PATH (ID-5; the backup keeps the old value)")
    if backup:
        log.info(f"settings.json backed up to {backup}")
    how = ("installed with the Claude Code CLI" if method == "cli"
           else "set in settings.json; Claude Code installs it on its next start (/reload-plugins if it is open)")
    if problems:
        return _claude_done(ctx, "amber", "; ".join(problems) + f"; WhyNot Cut is {how}",
                            "; ".join(needs) or None, method, entry, backup, r["disabled"])
    return _claude_done(ctx, "ok", f"{plugin_id} {how}", None, method, entry, backup, r["disabled"])


def _keep_backup_if_changed(sfile: Path, original: Optional[bytes], backup) -> Optional[str]:
    """The backup made before the CLI is kept only when settings.json now differs from the original bytes (exactly
    one backup, of the editor's original); otherwise it is removed. Returns the kept path or None."""
    if backup is None:
        return None
    try:
        now = sfile.read_bytes()
    except OSError:
        now = None
    if now == original:
        try:
            Path(backup).unlink()
            return None
        except OSError:
            pass
    return str(backup)


def _cli_phase(ctx: base.Ctx, name: str, plugin_id: str, source: dict, problems: list, needs: list) -> str:
    """(c) + (a): the CLI, when there is one, it answers and it is new enough. Returns the method ("cli" when the
    plugin was installed / updated through it, else "settings")."""
    paths, c, log = ctx.paths, ctx.components, ctx.log
    legacy = _legacy_source(paths, name, source)
    cands = claude_candidates(os.environ, paths.home, ctx.platform, paths.sandbox)
    cli = cands[0] if cands else None
    method, cli_ran = "settings", False
    if cli is None:
        log.info("no Claude Code CLI found: WhyNot Cut is registered through settings.json only")
    else:
        cmd = claude_command(cli)
        rc, out = base.run_cmd(ctx, cmd + ["--version"], CLI_TIMEOUT)
        have = _version(out) if rc == 0 else None
        minimum = str(base.cget(c, "claude_code.min") or "")
        need = _version(minimum)
        if rc in (124, 127):  # timed out / cannot start: no usable CLI
            problems.append(f"the Claude Code CLI at {cli} did not answer (`--version` exit {rc}: {base.tail(out)}); "
                            "it was not used")
        elif have and need and have < need:
            shown = ".".join(map(str, have))
            problems.append(f"update Claude Code: this one is {shown}, WhyNot Cut needs {minimum} or newer")
            needs.append(f"update Claude Code to {minimum} or newer, then run the installer again")
        else:
            if have is None:
                log.warn(f"could not read the version of {cli}; using it anyway")
            cli_ran = True
            if _cli_register(ctx, cmd, name, plugin_id, source, legacy, problems):
                method = "cli"
    if legacy is not None and not cli_ran:
        problems.append(f"Claude Code still knows the {name} marketplace from {_describe(legacy)}")
        needs.append(f"run `claude plugin marketplace remove {name}` (or remove it in Claude Code under /plugin > "
                     "Marketplaces), then start Claude Code again")
    return method


def _claude_done(ctx: base.Ctx, status: str, detail: str, needs_you, method: str, entry: dict, backup,
                 disabled: list) -> base.StepResult:
    prev = ctx.state.data.get("claude") if isinstance(ctx.state.data.get("claude"), dict) else {}
    before = prev.get("disabled")  # kept across runs: uninstall can switch them back on
    was_off = [k for k in before if isinstance(k, str)] if isinstance(before, list) else []
    ctx.state.data["claude"] = {"method": method, "marketplace": entry, "settings_backup": backup,
                                "disabled": was_off + [k for k in disabled if k not in was_off]}
    ctx.state.record("claude", status, None, detail)
    return base.StepResult("claude", status, detail, needs_you)


# --------------------------------------------------------------------------------------------- gitbash step
def managed_git_dir(paths: base.Paths) -> Path:
    return paths.localappdata / "WhyNotCut" / "git"


def find_git_bash(paths: base.Paths, settings_env: Mapping, sandbox: bool) -> tuple:
    """(bash.exe or None, is_standard_location). Standard = Claude Code finds it without our settings entry (or the
    entry is already there): settings env CLAUDE_CODE_GIT_BASH_PATH (when the file exists), `git` on PATH
    (<git>\\..\\..\\bin\\bash.exe), %ProgramFiles%\\Git, %ProgramFiles(x86)%\\Git. Then, not standard:
    %LOCALAPPDATA%\\Programs\\Git (per-user Git for Windows) and our own %LOCALAPPDATA%\\WhyNotCut\\git. A sandbox looks
    only at the settings value and the two LOCALAPPDATA places under the fake home."""
    v = settings_env.get(GIT_BASH_KEY) if isinstance(settings_env, Mapping) else None
    if isinstance(v, str) and v.strip():
        p = Path(v.strip().strip('"'))
        if p.is_file():
            return p, True
    if not sandbox:
        git = shutil.which("git")
        if git:
            p = Path(git).parent.parent / "bin" / "bash.exe"
            if p.is_file():
                return p, True
        for var in ("ProgramFiles", "ProgramFiles(x86)"):
            if os.environ.get(var):
                p = Path(os.environ[var]) / "Git" / "bin" / "bash.exe"
                if p.is_file():
                    return p, True
    for p in (paths.localappdata / "Programs" / "Git" / "bin" / "bash.exe",
              managed_git_dir(paths) / "bin" / "bash.exe"):
        if p.is_file():
            return p, False
    return None, False


def _is_managed(paths: base.Paths, bash: Path) -> bool:
    return base._within(base._norm(bash), base._norm(managed_git_dir(paths)))


def _settings_env(path: Path) -> dict:
    """settings env for the search only: an absent or unreadable file is {} (the merge reports it)."""
    try:
        data, _raw = _read_settings(path, "{}")
    except (SettingsUnreadable, OSError):
        return {}
    return data.get("env") or {}


def _unpack_git(ctx: base.Ctx, archive: Path, kind: str) -> Optional[str]:
    """PortableGit into %LOCALAPPDATA%\\WhyNotCut\\git through git.staging (renamed into place once bin\\bash.exe is
    there). None when done, else the error."""
    dest = managed_git_dir(ctx.paths)
    root, staging = dest.parent, dest.with_name(dest.name + ".staging")
    try:
        if not base.safe_rmtree(staging, [root]):
            return f"cannot clear the leftover {staging}"
        if kind == "7z-sfx":
            rc, out = base.run_cmd(ctx, [archive, f"-o{staging}", "-y"], SFX_TIMEOUT)
            if rc != 0:
                raise base.ExtractError(f"the Git for Windows self-extractor failed (exit {rc}: {base.tail(out)})")
        elif kind == "zip":
            base.extract(archive, staging)
        else:
            raise base.ExtractError(f"components.json git archive type {kind!r} is not supported")
        if not (staging / "bin" / "bash.exe").is_file():
            raise base.ExtractError(f"{archive.name} gave no bin\\bash.exe")
        base.move_aside_and_replace(staging, dest, root)
    except (OSError, base.ExtractError) as e:
        try:
            base.safe_rmtree(staging, [root])
        except OSError as e2:
            ctx.log.warn(f"could not remove {staging}: {e2}")
        return str(e)
    return None


def step_gitbash(ctx: base.Ctx) -> base.StepResult:
    if not ctx.platform.startswith("win"):
        return base.StepResult("gitbash", "skipped", "Git Bash is only needed on Windows")
    paths, c = ctx.paths, ctx.components
    found, standard = find_git_bash(paths, _settings_env(paths.settings_file), paths.sandbox)
    if found is not None and standard:
        managed = _is_managed(paths, found)
        ctx.state.data["gitbash"] = {"path": str(found), "managed": managed,
                                     "version": base.cget(c, "git.version") if managed else None}
        ctx.state.record("gitbash", "ok", None, f"Git Bash at {found}")
        return base.StepResult("gitbash", "ok", f"Claude Code finds Git Bash at {found}")
    if ctx.args.dry_run:
        return base.StepResult("gitbash", "skipped", f"dry run: would {'set' if found else 'install and set'} "
                                                     f"Git Bash for Claude Code")
    ver = base.cget(c, "git.version")
    if found is None:
        asset = base.cget(c, f"git.assets.{ctx.platform}") or {}
        url, sha, kind = asset.get("url"), asset.get("sha256"), asset.get("archive")
        if base.is_placeholder(url) or base.is_placeholder(sha) or base.is_placeholder(kind):
            return base.StepResult("gitbash", "amber", "Git for Windows is not in this build (placeholder pin); "
                                                       "Claude Code falls back to PowerShell",
                                   needs_you=f"install Git for Windows from {GIT_DOWNLOAD}, then run the installer "
                                             "again")
        try:
            archive = base.download(url, sha, paths.downloads_dir, ctx.log)
        except base.DownloadError as e:
            return base.StepResult("gitbash", "red", str(e))
        err = _unpack_git(ctx, archive, kind)
        if err:  # e.g. the real SFX exits 1 after a partial extraction under a long base path (MAX_PATH)
            return base.StepResult("gitbash", "amber", f"Git for Windows could not be set up; install it from "
                                                       f"{GIT_DOWNLOAD} ({err})",
                                   needs_you=f"install Git for Windows from {GIT_DOWNLOAD}, then run the installer "
                                             "again")
        found = managed_git_dir(paths) / "bin" / "bash.exe"
        ctx.log.info(f"Git for Windows {ver} unpacked into {found.parents[1]}")
    try:
        r = merge_claude_settings(paths.settings_file, marketplace=None, plugin_id=None,
                                  env={GIT_BASH_KEY: str(found)})
    except SettingsUnreadable as e:
        return base.StepResult("gitbash", "amber", f"Git Bash is at {found}, but {paths.settings_file} is {e.reason}; "
                                                   "it was left exactly as it is. Merge in the JSON below by hand",
                               needs_you=e.snippet)
    except (OSError, UnicodeError, ValueError) as e:
        return base.StepResult("gitbash", "amber", f"Git Bash is at {found}, but {paths.settings_file} could not be "
                                                   f"written: {type(e).__name__}: {e}",
                               needs_you=settings_snippet(env={GIT_BASH_KEY: str(found)}))
    managed = _is_managed(paths, found)
    ctx.state.data["gitbash"] = {"path": str(found), "managed": managed, "version": ver if managed else None,
                                 "settings_backup": r["backup"]}
    detail = f"Git Bash at {found}, set as {GIT_BASH_KEY} in Claude Code's settings"
    ctx.state.record("gitbash", "ok", None, detail)
    return base.StepResult("gitbash", "ok", detail)


# --------------------------------------------------------------------------------------------- registry
STEPS = (("gitbash", step_gitbash, ()), ("claude", step_claude, ()))


def register(steps: list) -> None:
    """Append this module's install steps to cli.STEPS (once)."""
    have = {s[0] for s in steps}
    steps.extend(s for s in STEPS if s[0] not in have)
