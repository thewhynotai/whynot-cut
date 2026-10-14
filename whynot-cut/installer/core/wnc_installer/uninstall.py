"""`wnc_install.py uninstall` (3.0 T7.8, installer.md R.3): undo what the install did for this user, in this order.

plugin       settings.json is checked and its ORIGINAL bytes backed up first (unreadable JSON: no CLI call, the file
             stays byte-identical, amber with what to remove by hand). Then, with a Claude Code CLI:
             `claude plugin uninstall whynot-cut@thewhynot-ai --scope user` and `claude plugin marketplace remove
             thewhynot-ai`; then our keys come out of settings.json (extraKnownMarketplaces / enabledPlugins entries),
             and plugins the install switched off (ID-5) are switched back on. The Git Bash env key stays while the
             managed Git folder stays: both go only with --remove-engine.
adobe        a running Premiere Pro / After Effects: amber, nothing removed. Else the RECORDED CEP folder (only when it
             is <CEP extensions>/ai.thewhynot.cut.bridge, never a link) and its .prev / .new; the UXP panel through
             UPIA `/remove <id>` (`--remove` on macOS; the id recorded at install); a sandbox only records it.
fonts        only the files listed in state.fonts.installed that sit in the user font folder, and only the registry
             values listed in state.fonts.registry that still point at one of those files.
marketplace  ~/.whynot-cut/marketplace (+ .new / .prev); a link (a development checkout) is left alone.
engine       only with --remove-engine: ONLY the children of the engine home that WhyNot Cut puts there
             (base.ENGINE_LAYOUT: bin, python, runtimes, current, ffmpeg, cuda, bridge, state.json, logs, cache,
             downloads, fonts, marketplace(.new/.prev), the deferred list, the engine's venv / queues / scripts /
             probe / bench / tmp, and their set-aside leftovers; fix round 1), in every engine home including
             ~/.whynot-cut. Anything else is the editor's: kept and listed. models/ is kept unless --remove-models,
             library/ (the editor's licensed motion packs, engine motion_library.py) always, plugin-options.json
             follows the pointer rules (forget_engine_home). Plus
             %LOCALAPPDATA%\\WhyNotCut\\git, then the settings env CLAUDE_CODE_GIT_BASH_PATH that points into it.
             python/ and bin/ (the interpreter running this code: Windows locks it) are listed in
             ~/.whynot-cut/.delete-after-exit, which the bootstrap deletes after this process exits (and the engine
             home itself only when it is then empty). When adobe / fonts left something recorded (a running host, a
             font in use), a minimal state.json keeps those records for the next uninstall. Refused unless the folder
             is a genuine engine home (base.is_engine_home: by content, not by file names). --remove-models alone deletes models/ only. Once nothing is
             left to retry, the saved engine home is forgotten (claude.forget_engine_home: the pointer's engine_home,
             our pluginConfigs option, then an empty ~/.whynot-cut), only while they name this folder.
Never touched: a clients folder (preferences `clients_root`, any folder holding `.whynot-client`), the preferences file
~/.claude/whynot-cut.local.md (kept and reported), fonts / registry values / CEP folders not recorded, anything outside
the engine home, the recorded paths and the managed Git folder. Links are removed as links or left alone, never
followed. With --remove-engine the log goes with logs/; the summary stays on the console. Stdlib only.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from . import base, claude
from .adobe import EXT_ID, UPIA_TIMEOUT, cep_extensions_dir, hosts_running, upia_path
from .fonts import FontRegistry, broadcast_font_change, remove_font_resource, user_font_dir
from .system import PREFS, read_preferences, render_checklist

DEFER_LIST = ".delete-after-exit"
DEFERRED = ("python", "bin")  # the interpreter running this core, and uv: removed by the bootstrap after it exits
KEPT = "library"  # <engine home>/library: licensed motion / illustration packs (engine motion_library.py); never ours
RETRY_SECTIONS = ("adobe", "fonts")  # what an earlier step may leave recorded for the next uninstall


# --------------------------------------------------------------------------------------------- helpers
def _dry(ctx: base.Ctx) -> bool:
    return bool(getattr(ctx.args, "dry_run", False))


def _ids(ctx: base.Ctx) -> tuple:
    name = str(base.cget(ctx.components, "marketplace.name") or "thewhynot-ai")
    return name, f"{base.cget(ctx.components, 'marketplace.plugin') or 'whynot-cut'}@{name}"


def _section(ctx: base.Ctx, key: str) -> dict:
    v = ctx.state.data.get(key)
    return v if isinstance(v, dict) else {}


def _save(ctx: base.Ctx) -> None:
    try:
        ctx.state.save()
    except OSError as e:
        ctx.log.warn(f"could not update state.json: {e}")


def _folder(v) -> Optional[Path]:
    if not isinstance(v, str) or not v.strip():
        return None
    return Path(os.path.abspath(os.path.expanduser(v.strip().strip('"'))))


def clients_roots(ctx: base.Ctx) -> list:
    """The clients folder(s) we know of: the preferences' clients_root and the install's answer."""
    out = []
    for v in (read_preferences(ctx.paths).get("clients_root"), _section(ctx, "answers").get("clients_root")):
        p = _folder(v)
        if p is not None and base._norm(p) not in {base._norm(x) for x in out}:
            out.append(p)
    return out


def _protected(ctx: base.Ctx) -> list:
    return clients_roots(ctx) + [ctx.paths.claude_dir]


def _touches(p: Path, protected: list) -> bool:
    """p (as written or with links resolved) is, contains or lies inside a protected path."""
    for mine in (base._norm(p), base._real(p)):
        for pr in protected:
            for theirs in (base._norm(pr), base._real(pr)):
                if base._within(theirs, mine, strict=False) or base._within(mine, theirs, strict=False):
                    return True
    return False


def _done(name: str, status: str, notes: list, needs_you: Optional[str] = None) -> base.StepResult:
    return base.StepResult(name, status, "; ".join(n for n in notes if n), needs_you)


# --------------------------------------------------------------------------------------------- plugin
def _cli_remove(ctx: base.Ctx, name: str, pid: str, problems: list) -> Optional[bool]:
    """`plugin uninstall` + `marketplace remove` through the CLI, for what Claude Code still lists. None when there is
    no usable CLI, else True when every call worked."""
    paths = ctx.paths
    cands = claude.claude_candidates(os.environ, paths.home, ctx.platform, paths.sandbox)
    if not cands:
        ctx.log.info("no Claude Code CLI found: WhyNot Cut is removed from settings.json only")
        return None
    cmd = claude.claude_command(cands[0])
    rc, out = base.run_cmd(ctx, cmd + ["--version"], claude.CLI_TIMEOUT)
    if rc in (124, 127):
        problems.append(f"the Claude Code CLI at {cands[0]} did not answer (`--version` exit {rc}: {base.tail(out)}); "
                        "it was not used")
        return None
    ok = True
    calls = []
    if claude._plugin_installed(paths, pid):
        calls.append(["plugin", "uninstall", pid, "--scope", "user"])
    if claude._known_source(paths, name) is not None:
        calls.append(["plugin", "marketplace", "remove", name])
    for args in calls:
        rc, out = base.run_cmd(ctx, cmd + args, claude.CLI_TIMEOUT)
        if rc != 0:
            ok = False
            problems.append(f"`claude {' '.join(args)}` failed (exit {rc}: {base.tail(out)})")
    if not calls:
        ctx.log.info(f"Claude Code no longer lists {pid} or the {name} marketplace")
    return ok


def step_plugin(ctx: base.Ctx) -> base.StepResult:
    paths = ctx.paths
    name, pid = _ids(ctx)
    sfile = paths.settings_file
    turned_off = [k for k in _section(ctx, "claude").get("disabled") or [] if isinstance(k, str)]
    if _dry(ctx):
        return _done("plugin", "skipped", [f"dry run: would run `claude plugin uninstall {pid} --scope user` and "
                                           f"`claude plugin marketplace remove {name}`, and take our entries out of "
                                           f"{sfile}"])
    snippet = claude.unmerge_snippet(name, pid)
    by_hand = f"remove these from {sfile} by hand: {snippet}"
    # checked and backed up BEFORE the CLI runs: it writes settings.json too (same rule as the install, R3)
    try:
        _data, original = claude._read_settings(sfile, snippet)
    except claude.SettingsUnreadable as e:
        return _done("plugin", "amber", [f"{sfile} is {e.reason}; it was left exactly as it is and the Claude Code CLI "
                                         f"was not run (it writes there too). Repair it, then remove the entries of "
                                         f"{pid} by hand: {e.snippet}"], by_hand)
    except OSError as e:
        return _done("plugin", "amber", [f"cannot read {sfile}: {e}; nothing was changed"], by_hand)
    backup = None
    if original is not None:
        try:
            backup = claude.write_backup(sfile, original, claude._file_mode(sfile))
        except OSError as e:
            return _done("plugin", "amber", [f"cannot back up {sfile}: {e}; nothing was changed"], by_hand)
    problems, r, fail = [], None, None
    try:
        via_cli = _cli_remove(ctx, name, pid, problems)
        try:
            r = claude.unmerge_claude_settings(sfile, marketplace_name=name, plugin_id=pid, env_keys_if_under={},
                                               enable=turned_off, make_backup=False)
        except claude.SettingsUnreadable as e:  # only when the CLI left it unreadable
            fail = f"{sfile} is {e.reason} after the Claude Code CLI wrote it; it was not changed further"
        except (OSError, UnicodeError, ValueError) as e:
            fail = f"could not write {sfile}: {type(e).__name__}: {e}"
    finally:  # the backup survives exactly when the file changed
        backup = claude._keep_backup_if_changed(sfile, original, backup)
    if fail:
        return _done("plugin", "amber", [fail] + problems, by_hand)
    needs = None
    if claude._plugin_installed(paths, pid):
        problems.append(f"Claude Code still lists {pid}")
        needs = f"in Claude Code open /plugin and uninstall whynot-cut (or run `claude plugin uninstall {pid}`)"
    ctx.state.data.pop("claude", None)
    _save(ctx)
    notes = [f"{pid} removed" + (" with the Claude Code CLI" if via_cli else "")
             + (f"; our entries taken out of {sfile}" if r and r["changed"] else "")]
    if r and r["enabled"]:
        notes.append(f"switched {', '.join(r['enabled'])} back on (the install had switched it off)")
    if backup:
        notes.append(f"backup of the previous settings.json: {backup}")
    return _done("plugin", "amber" if problems else "ok", problems + notes, needs)


# --------------------------------------------------------------------------------------------- adobe
def _remove_cep(ctx: base.Ctx, rec: dict) -> tuple:
    """(status, note, keep the record)."""
    cep_dir = cep_extensions_dir(ctx.paths, ctx.platform)
    p = Path(rec["path"])
    if base._norm(p) != base._norm(cep_dir / EXT_ID):
        return "amber", f"the recorded CEP panel {p} is not WhyNot Cut's folder in {cep_dir}; it was left alone", False
    if base.is_link(p):
        return "amber", f"{p} is a link (a development panel); it was left alone", False
    try:
        gone = base.safe_rmtree(p, [cep_dir])
        for extra in (cep_dir / (EXT_ID + ".prev"), cep_dir / (EXT_ID + ".new")):
            if not base.is_link(extra):
                base.safe_rmtree(extra, [cep_dir])
    except OSError as e:
        return "amber", (f"could not remove the CEP panel {p} ({e}); close Premiere Pro and After Effects, then run "
                         "the uninstall again"), True
    if not gone:
        return "amber", f"the CEP panel {p} was not removed (it holds a client folder marker)", True
    return "ok", f"CEP panel removed from {p}", False


def _remove_uxp(ctx: base.Ctx, rec: dict) -> tuple:
    uid = rec.get("id")  # the id the install used; this build's components.json only when none was recorded
    if not isinstance(uid, str) or not uid.strip() or base.is_placeholder(uid):
        uid = base.cget(ctx.components, "bridge.uxp.id")
    by_hand = "remove the WhyNot Cut panel in the Creative Cloud app (Stock & Marketplace > Plugins)"
    if base.is_placeholder(uid) or not isinstance(uid, str) or not uid.strip():
        return "amber", f"the UXP panel id is not in this build: {by_hand}", True
    upia = upia_path(ctx.platform)
    cmd = [str(upia), "/remove" if ctx.platform.startswith("win") else "--remove", uid.strip()]
    shown = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    if ctx.paths.sandbox:
        return "ok", f"sandbox: the UXP remove command was recorded, not run: {shown}", False
    if not upia.is_file():
        return "amber", f"Adobe's plugin installer (UPIA) was not found: {by_hand}", True
    rc, out = base.run_cmd(ctx, cmd, UPIA_TIMEOUT)
    if rc != 0:
        return "amber", f"UPIA could not remove the UXP panel (exit {rc}: {base.tail(out)}): {by_hand}", True
    return "ok", "UXP panel removed", False


def step_adobe(ctx: base.Ctx) -> base.StepResult:
    rec = _section(ctx, "adobe")
    cep = rec.get("cep") if isinstance(rec.get("cep"), dict) else None
    uxp = rec.get("uxp") if isinstance(rec.get("uxp"), dict) else None
    has_cep = bool(cep and isinstance(cep.get("path"), str) and cep["path"].strip())
    if not has_cep and not uxp:
        return _done("adobe", "skipped", ["no Adobe panel was installed by WhyNot Cut"])
    if _dry(ctx):
        what = " and ".join(x for x in (cep["path"] if has_cep else "", "the UXP panel" if uxp else "") if x)
        return _done("adobe", "skipped", [f"dry run: would remove {what}"])
    running = hosts_running(ctx.paths.sandbox)
    if running:
        msg = f"close {', '.join(running)}, then run the uninstall again"
        return _done("adobe", "amber", [f"the Adobe panel was not removed: {msg}"], msg)
    parts, left = [], {}
    if has_cep:
        status, note, keep = _remove_cep(ctx, cep)
        parts.append((status, note))
        if keep:
            left["cep"] = cep
    if uxp:
        status, note, keep = _remove_uxp(ctx, uxp)
        parts.append((status, note))
        if keep:
            left["uxp"] = uxp
    if left:  # only what is still installed: the next uninstall tries again
        ctx.state.data["adobe"] = left
    else:
        ctx.state.data.pop("adobe", None)
    _save(ctx)
    status = "amber" if any(s == "amber" for s, _n in parts) else "ok"
    return _done("adobe", status, [n for _s, n in parts] + (["restart Premiere Pro and After Effects"]
                                                            if status == "ok" else []))


# --------------------------------------------------------------------------------------------- fonts
def step_fonts(ctx: base.Ctx) -> base.StepResult:
    paths, plat = ctx.paths, ctx.platform
    rec = _section(ctx, "fonts")
    installed = [p for p in rec.get("installed") or [] if isinstance(p, str) and p.strip()]
    names = [n for n in rec.get("registry") or [] if isinstance(n, str) and n.strip()]
    if not installed and not names:
        return _done("fonts", "skipped", ["no font was installed by WhyNot Cut"])
    target = user_font_dir(paths, plat)
    if _dry(ctx):
        return _done("fonts", "skipped", [f"dry run: would remove {len(installed)} fonts from {target}"])
    win = plat.startswith("win")
    real_win = win and not paths.sandbox and os.name == "nt"
    ours, outside, removed, failed = [], [], [], []
    for s in installed:
        p = Path(s)
        if base._norm(p.parent) != base._norm(target) or p.suffix.lower() not in (".ttf", ".otf"):
            outside.append(p.name)  # not where the install puts fonts: never ours to delete
            continue
        ours.append(p)
        if not os.path.lexists(p):
            removed.append(p)
            continue
        if real_win and not base.is_link(p):
            remove_font_resource(p)
        try:
            base._unlink(str(p))
            removed.append(p)
        except OSError as e:
            failed.append((p, e))
    still = {base._norm(p) for p, _e in failed}
    done = {base._norm(p) for p in removed}
    kept_names = []
    reg = FontRegistry.for_paths(paths) if win else None
    for n in names if reg is not None else ():
        v = reg.get(n)
        if v is None:
            continue
        if base._norm(v) in done:
            reg.delete(n)
        elif base._norm(v) in still:
            kept_names.append(n)
        # else: the value now points somewhere else (someone reinstalled that font): theirs, left alone
    if real_win and removed:
        broadcast_font_change()
    if failed:
        ctx.state.data["fonts"] = dict(rec, installed=[str(p) for p, _e in failed], registry=kept_names)
    else:
        ctx.state.data.pop("fonts", None)
    _save(ctx)
    notes = [f"{len(removed)} fonts removed from {target}"]
    if outside:
        notes.append(f"left alone (recorded outside {target}): {', '.join(outside)}")
    if failed:
        msg = "close Premiere Pro, After Effects and any app using them, then run the uninstall again"
        notes.append("could not remove " + ", ".join(f"{p.name} ({e})" for p, e in failed))
        return _done("fonts", "amber", notes, msg)
    return _done("fonts", "ok", notes)


# --------------------------------------------------------------------------------------------- marketplace
def step_marketplace(ctx: base.Ctx) -> base.StepResult:
    paths = ctx.paths
    d = paths.marketplace_dir
    present = [p for p in (d, d.with_name(d.name + ".new"), d.with_name(d.name + ".prev")) if os.path.lexists(p)]
    if not present:
        return _done("marketplace", "skipped", [f"no marketplace folder in {paths.whynot}"])
    if _dry(ctx):
        return _done("marketplace", "skipped", ["dry run: would delete " + ", ".join(str(p) for p in present)])
    protected, notes, status = _protected(ctx), [], "ok"
    for p in present:
        if base.is_link(p):
            notes.append(f"{p} is a link (a development checkout); it was left alone")
            continue
        try:
            if base.safe_rmtree(p, [paths.whynot], protected):
                notes.append(f"deleted {p}")
            else:
                status = "amber"
                notes.append(f"{p} was left alone (it holds client data)")
        except OSError as e:
            status = "amber"
            notes.append(f"could not delete {p}: {e}")
    return _done("marketplace", status, notes)


# --------------------------------------------------------------------------------------------- engine
def engine_home_problem(paths: base.Paths) -> Optional[str]:
    """Why ~/.whynot-cut must not be emptied (it is the user folder or above it, a drive root, or holds nothing of
    ours), else None."""
    w = base._norm(paths.whynot)
    for other in (paths.home, paths.claude_dir, paths.appdata, paths.localappdata):
        if base._within(base._norm(other), w, strict=False):
            return f"{paths.whynot} is (or holds) {other}"
    if base._is_drive_root(str(paths.whynot)):
        return f"{paths.whynot} is a drive root or a mounted volume"
    if base.is_link(paths.whynot) and not base.linked_default_home(paths.whynot, paths.home):
        return f"{paths.whynot} is a link"
    if base.linked_default_home(paths.whynot, paths.home):
        # Addendum F: ~/.whynot-cut linked to a folder is fine - unless it points somewhere it must never be (fix round
        # 3: Documents, the user folder, a drive root, client data, a folder too big to check)
        why = base.resolved_home_problem(paths.whynot, home=paths.home, clients_roots=base.saved_client_roots(paths),
                                         known=base.shell_folders(paths.home, paths.sandbox))
        if why:
            return f"{paths.whynot} is {why}"
    if not base.is_engine_home(paths.whynot):
        return (f"{paths.whynot} does not look like a WhyNot Cut engine home (no state.json written by WhyNot Cut, no "
                "`current` with its runtime stamp)")
    return None


def _delete_child(ctx: base.Ctx, p: Path, protected: list, removed: list, kept: list, failed: list) -> None:
    if base.is_link(p):
        if _touches(p, protected):
            kept.append(f"{p.name} (a link to your client data)")
            return
        try:
            base._unlink(str(p))  # the link only: its target is never entered
            removed.append(p.name)
        except OSError as e:
            failed.append(f"{p.name} ({e})")
        return
    try:
        if base.safe_rmtree(p, [ctx.paths.whynot], protected):
            removed.append(p.name)
        else:
            kept.append(f"{p.name} (client data: never deleted)")
    except OSError as e:
        failed.append(f"{p.name} ({e})")


def step_engine(ctx: base.Ctx) -> base.StepResult:
    paths = ctx.paths
    engine, models = bool(getattr(ctx.args, "remove_engine", False)), bool(getattr(ctx.args, "remove_models", False))
    if not engine and not models:
        return _done("engine", "skipped", [f"kept {paths.whynot} (runtimes, ffmpeg, models); --remove-engine deletes "
                                           "it, --remove-models deletes the Whisper models"])
    if not paths.whynot.is_dir():
        return _done("engine", "skipped", [f"{paths.whynot} is not there"])
    problem = engine_home_problem(paths)
    if problem:
        return _done("engine", "red", [f"nothing was deleted: {problem}"])
    protected = _protected(ctx)
    busy = _running_download(ctx)  # read now: state.json may be reduced below
    if not engine:  # --remove-models alone
        if "models" not in os.listdir(paths.whynot):  # exact name (`Models` on NTFS / APFS is the editor's)
            return _done("engine", "skipped", ["no Whisper models to delete"])
        if _dry(ctx):
            return _done("engine", "skipped", [f"dry run: would delete {paths.models_dir}"])
        removed, kept, failed = [], [], []
        _delete_child(ctx, paths.models_dir, protected, removed, kept, failed)
        status = "amber" if kept or failed else "ok"
        notes = [f"deleted {paths.models_dir}" if removed else ""] + [f"kept {k}" for k in kept] + [
            f"could not delete {f}" for f in failed]
        if failed and busy:
            notes.append(busy)
        return _done("engine", status, notes, _locked_hint(busy, "--remove-models") if failed and busy else None)
    keep_models = not models
    if _dry(ctx):
        return _done("engine", "skipped", [f"dry run: would delete WhyNot Cut's own folders and files in "
                                           f"{paths.whynot}" + (" except models/ and library/" if keep_models
                                                                 else " except library/")
                                           + f", and {claude.managed_git_dir(paths)}; anything else stays"])
    # what an earlier step could not remove (a running Adobe host, a font in use) stays recorded in a minimal
    # state.json, so the uninstall the editor is told to run again still knows about it
    retry = {k: ctx.state.data[k] for k in RETRY_SECTIONS if isinstance(ctx.state.data.get(k), dict)}
    if retry:
        ctx.state.data = dict({"schema": 1, "plugin": ctx.state.data.get("plugin"), "updated_at": None, "steps": {},
                               "answers": _section(ctx, "answers")}, **retry)
    else:
        ctx.state.dry_run = True  # state.json goes too: nothing may write it again in this run
    removed, kept, failed, foreign = [], [], [], []
    with os.scandir(paths.whynot) as it:
        children = sorted((e.name for e in it), key=lambda n: (n == "logs", n))  # logs last: the log goes with it
    for name in children:
        p = paths.whynot / name
        if name == DEFER_LIST or name in DEFERRED:
            continue
        if name == "models" and keep_models:
            kept.append("models (the Whisper models; --remove-models deletes them)")
            continue
        if name == KEPT:
            kept.append("library (your motion and illustration packs: never deleted by the uninstall)")
            continue
        if name == "state.json" and retry:
            continue
        if name == base.OPTIONS_FILE:  # the pointer: its own rules (claude.forget_engine_home, below)
            continue
        if not (base.is_engine_entry(name) or name == "models"):  # not WhyNot Cut's: never deleted (fix round 1)
            foreign.append(name)
            continue
        if name == "logs":
            ctx.log.info("the uninstall log goes with the engine home; this summary stays on the screen only")
            ctx.log.path = None
        _delete_child(ctx, p, protected, removed, kept, failed)
    git = claude.managed_git_dir(paths)
    for g in (git, git.with_name(git.name + ".staging")):
        if os.path.lexists(g):
            _delete_child_in(ctx, g, git.parent, protected, removed, failed)
    try:
        if git.parent.is_dir() and not base.is_link(git.parent) and not os.listdir(git.parent):
            os.rmdir(git.parent)
    except OSError:
        pass
    if not os.path.lexists(git):  # the Git Bash entry goes together with the managed Git folder, never before it
        _drop_git_bash_key(ctx, git, kept, failed)
    # nothing left to retry: WhyNot Cut no longer points at this folder (ID-10); before `rest` (the pointer may go)
    forgot = claude.forget_engine_home(paths, ctx.log) if not failed and not retry else []
    names = set(os.listdir(paths.whynot))  # exact names: lexists would also match the editor's `Bin` on NTFS
    later = [paths.whynot / n for n in DEFERRED if n in names]
    rest = [n for n in os.listdir(paths.whynot) if n not in DEFERRED and n != DEFER_LIST]
    linked = base.linked_default_home(paths.whynot, paths.home)  # the link and its target folder always stay
    defer_file = paths.whynot / DEFER_LIST
    try:
        if later:
            lines = [str(p) for p in later] + ([str(paths.whynot)] if not rest and not linked else [])
            base.atomic_write_text(defer_file, "\n".join(lines) + "\n")
        else:
            if os.path.lexists(defer_file):
                base._unlink(str(defer_file))
            if not rest and not linked:
                os.rmdir(paths.whynot)
    except OSError as e:
        failed.append(f"{DEFER_LIST} ({e})")
    notes = [f"deleted {len(removed)} items of {paths.whynot}"]
    if retry:
        notes.append(f"kept {paths.whynot} with a small state.json: {', '.join(retry)} could not be removed yet; run "
                     "the uninstall again once that is fixed")
    if later:
        notes.append(", ".join(p.name + "/" for p in later) + " (the Python running this uninstall and uv) are "
                     "deleted by the installer right after it exits"
                     + (", then the engine home itself" if not rest and not linked else ""))
    if linked:
        notes.append(f"kept {paths.whynot} (a link to {os.path.realpath(paths.whynot)}): the link and that folder stay")
    notes += [f"kept {k}" for k in kept] + [f"could not delete {f}" for f in failed]
    if foreign:
        notes.append(f"kept (not WhyNot Cut's, left alone): {', '.join(foreign)}")
    if failed:
        if busy:
            notes.append(busy)
        return _done("engine", "amber", notes, _locked_hint(busy, "--remove-engine"))
    notes += forgot
    custom = not base.same_path(paths.whynot, paths.default_whynot)
    if not retry and custom and any(k.startswith(("models", KEPT)) for k in kept):
        notes.append(f"{paths.whynot} keeps what is listed above; to use it again, install with -EngineHome "
                     f"\"{paths.whynot}\" (macOS: --engine-home)")
    return _done("engine", "ok", notes)


def _running_download(ctx: base.Ctx) -> Optional[str]:
    """A note naming the background Whisper model download (state.models) when its process is still running: it
    holds files of the engine home open, the likely reason a delete failed. None when there is none."""
    m = _section(ctx, "models")
    if not base.pid_alive(m.get("pid")):
        return None
    return (f"the background model download (Whisper {m.get('model') or '?'}, process {m.get('pid')}, log "
            f"{m.get('log') or '?'}) is still running and is the likely cause")


def _locked_hint(busy: Optional[str], flag: str) -> str:
    if busy:
        return ("wait for the model download to finish (or end that process), close Premiere Pro, After Effects and "
                f"Claude, then run the uninstall again with {flag}")
    return f"close Premiere Pro, After Effects and Claude, then run the uninstall again with {flag}"


def _drop_git_bash_key(ctx: base.Ctx, git: Path, kept: list, failed: list) -> None:
    """settings.json env CLAUDE_CODE_GIT_BASH_PATH, only while it points into the (now deleted) managed Git folder.
    Same rules as every settings write: unreadable = untouched, a backup when it changes."""
    sfile = ctx.paths.settings_file
    if not sfile.is_file():
        return
    name, pid = _ids(ctx)
    try:
        r = claude.unmerge_claude_settings(sfile, marketplace_name=name, plugin_id=pid,
                                           env_keys_if_under={claude.GIT_BASH_KEY: git})
    except claude.SettingsUnreadable as e:
        failed.append(f"the {claude.GIT_BASH_KEY} entry in {sfile} ({sfile.name} is {e.reason}; remove it by hand)")
        return
    except (OSError, UnicodeError, ValueError) as e:
        failed.append(f"the {claude.GIT_BASH_KEY} entry in {sfile} ({type(e).__name__}: {e})")
        return
    if r["changed"]:
        ctx.log.info(f"removed {claude.GIT_BASH_KEY} from {sfile} (backup {r['backup']})")


def _delete_child_in(ctx: base.Ctx, p: Path, root: Path, protected: list, removed: list, failed: list) -> None:
    if base.is_link(p):
        return  # someone's own link: left alone
    try:
        if base.safe_rmtree(p, [root], protected):
            removed.append(str(p))
    except OSError as e:
        failed.append(f"{p} ({e})")


# --------------------------------------------------------------------------------------------- run
STEPS = (("plugin", step_plugin, ()), ("adobe", step_adobe, ()), ("fonts", step_fonts, ()),
         ("marketplace", step_marketplace, ()), ("engine", step_engine, ()))
STEP_NAMES = tuple(s[0] for s in STEPS)


def register_uninstall(steps: list) -> None:
    """Append the uninstall steps to cli.UNINSTALL_STEPS (once, in this order)."""
    have = {s[0] for s in steps}
    steps.extend(s for s in STEPS if s[0] not in have)


def uninstall(ctx: base.Ctx, remove_engine: bool, remove_models: bool) -> list:
    """Run the five steps (a red one does not stop the others), record the outcome in state.json (unless the engine
    home went), and print the checklist plus what was kept on purpose. Returns the StepResults."""
    ctx.args.remove_engine, ctx.args.remove_models = bool(remove_engine), bool(remove_models)
    results = base.run_steps(ctx, list(STEPS))
    if not _dry(ctx):
        ctx.state.data["uninstalled"] = {"at": base.now_iso(), "remove_engine": bool(remove_engine),
                                         "remove_models": bool(remove_models),
                                         "steps": {r.name: r.status for r in results}}
        _save(ctx)
    log = ctx.log
    log.info("")
    log.info("WhyNot Cut uninstall checklist:")
    for line in render_checklist(results, None).splitlines():
        log.info(line)
    prefs = ctx.paths.home / ".claude" / PREFS
    if prefs.is_file():
        log.info(f"kept your preferences: {prefs} (a later install uses them again; delete the file to forget them)")
    for root in clients_roots(ctx):
        log.info(f"your client folders were not touched: {root}")
    return results
