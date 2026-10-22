"""Install / remove the Control Center's few touch points outside its own folder. Every change is backed up first to
<state>\\backups\\<time>\\ and `--undo` removes exactly what this added.

    python -X utf8 install.py           # install (idempotent)
    python -X utf8 install.py --check   # show what is installed
    python -X utf8 install.py --undo    # remove it again

Touch points:
1. Each helper profile's settings.json gets (a) a PostToolUse + UserPromptSubmit hook that delivers owner messages
   (ownermsg.py) and (b) the Control Center status line for chats opened on that seat.
2. Desktop: shortcut "WhyNot - Control Center"; the old "WhyNot - Agency LIVE" shortcut is moved to the backup folder
   (agency_live.py itself stays; run it by hand for a text view).
3. RELOAD-h1 / RELOAD-h2 flags: each helper loop restarts itself on the updated helper_loop.py between two runs (never
   during a run).
"""
import datetime as dt, json, os, re, shutil, subprocess, sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

APP = Path(__file__).resolve().parent
PY = "C:/Python313/python.exe"
MARK = "control-center/app/"
DESKTOP = Path(os.environ.get("USERPROFILE", ""), "Desktop")
NEW_LNK = DESKTOP / "WhyNot - Control Center.lnk"
OLD_LNK = DESKTOP / "WhyNot - Agency LIVE.lnk"
OLD_DIR = DESKTOP / "WhyNot - Old tools"   # the older shortcuts, kept working, out of the way
OLD_GLOB = "WhyNot - Helper *.lnk"
ACCOUNTS = Path(r"D:\ClaudeData\accounts")


def fwd(p):
    return str(p).replace("\\", "/")


def hook_cmd(acct):
    return f'"{PY}" -X utf8 "{fwd(APP / "ownermsg.py")}" hook {acct}'


def status_cmd(acct):
    return f'"{PY}" -X utf8 "{fwd(APP / "statusline.py")}" {acct}'


def deny_rules():
    """Helpers must never write the control center's code or state: a helper could otherwise post a message "from
    Yunus" to the other helper, or change code that runs as another account's hook or in Yunus's terminal."""
    rules = []
    for root in (common.CC, Path(common.load_config()["state_dir"])):
        r = "//" + fwd(root).replace(":", "", 1).lower()[0] + fwd(root)[2:] + "/**"
        rules += [f"Edit({r})", f"Write({r})"]
    return rules + ["Bash(*control-center*)"]


def is_our_rule(rule):
    """Matches what deny_rules() adds, for any install path (undo after the state folder moved)."""
    return rule == "Bash(*control-center*)" or bool(re.fullmatch(r"(Edit|Write)\(//.*/control-center/\*\*\)", rule))


def ours(entry):
    return any(MARK in (h.get("command") or "") for h in entry.get("hooks", []))


def add_entries(settings, acct):
    hooks = settings.setdefault("hooks", {})
    for event, entry in (("PostToolUse", {"matcher": "*", "hooks": [{"type": "command", "command": hook_cmd(acct), "timeout": 10}]}),
                         ("UserPromptSubmit", {"hooks": [{"type": "command", "command": hook_cmd(acct), "timeout": 10}]})):
        lst = [e for e in hooks.get(event, []) if not ours(e)]
        lst.append(entry)
        hooks[event] = lst
    if not settings.get("statusLine") or MARK in (settings["statusLine"].get("command") or ""):
        settings["statusLine"] = {"type": "command", "command": status_cmd(acct), "padding": 0}
    deny = settings.setdefault("permissions", {}).setdefault("deny", [])
    deny += [r for r in deny_rules() if r not in deny]
    return settings


def remove_entries(settings):
    hooks = settings.get("hooks") or {}
    for event in list(hooks):
        hooks[event] = [e for e in hooks[event] if not ours(e)]
        if not hooks[event]:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)
    if MARK in ((settings.get("statusLine") or {}).get("command") or ""):
        del settings["statusLine"]
    perms = settings.get("permissions") or {}
    if "deny" in perms:
        perms["deny"] = [r for r in perms["deny"] if not is_our_rule(r)]
        if not perms["deny"]:
            del perms["deny"]
        if not perms:
            del settings["permissions"]
    return settings


def backup_dir(cfg):
    d = common.state_path(cfg, "backups", dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f"), "x").parent
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_json(path, data):
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def shortcut(path, target, args, workdir, desc, icon=""):
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK);$s.TargetPath=$env:TGT;$s.Arguments=$env:ARGS;"
          "$s.WorkingDirectory=$env:WD;$s.Description=$env:DESC;if($env:ICO){$s.IconLocation=$env:ICO};$s.Save()")
    env = dict(os.environ, LNK=str(path), TGT=target, ARGS=args, WD=workdir, DESC=desc, ICO=icon)
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, check=True, capture_output=True)


def move_old_shortcuts(cfg, bk):
    """Old WhyNot shortcuts go into one desktop folder (they keep working); Agency LIVE comes back there from backup."""
    OLD_DIR.mkdir(exist_ok=True)
    for lnk in DESKTOP.glob(OLD_GLOB):
        shutil.copy2(lnk, bk / lnk.name)
        if not (OLD_DIR / lnk.name).exists():
            shutil.move(str(lnk), OLD_DIR / lnk.name)
            print(f"{lnk.name} -> {OLD_DIR.name}")
    if OLD_LNK.exists():
        shutil.move(str(OLD_LNK), OLD_DIR / OLD_LNK.name)
    elif not (OLD_DIR / OLD_LNK.name).exists():
        olds = sorted(Path(cfg["state_dir"], "backups").glob(f"*/{OLD_LNK.name}"))
        if olds:
            shutil.copy2(olds[-1], OLD_DIR / OLD_LNK.name)
            print(f"{OLD_LNK.name} -> {OLD_DIR.name} (from backup)")


def helper_settings(cfg):
    return [(a["id"], Path(a["profile"], "settings.json")) for a in cfg["accounts"] if a["kind"] == "helper"]


def install(cfg):
    bk = backup_dir(cfg)
    for acct, path in helper_settings(cfg):
        shutil.copy2(path, bk / f"{acct}-settings.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        write_json(path, add_entries(data, acct))
        print(f"{acct}: hooks + status line in {path}")
    pyw = Path(sys.executable).with_name("pythonw.exe")
    shortcut(NEW_LNK, str(pyw if pyw.exists() else sys.executable), f'-X utf8 "{APP / "launch.py"}"', str(common.CC),
             "WhyNot Control Center: dashboard + one terminal per account", f"{common.WEB / 'app.ico'},0")
    print(f"Desktop shortcut: {NEW_LNK.name} (opens as its own window, TWN icon)")
    move_old_shortcuts(cfg, bk)
    for a in cfg["accounts"]:
        if a["kind"] != "helper":
            continue
        alive = subprocess.run([sys.executable, "-X", "utf8", str(ACCOUNTS / "helper_loop.py"), a["id"], "--alive"],
                               capture_output=True).returncode == 0
        if alive:  # a stopped loop loads the new code when it starts: nothing to do, nothing re-enabled
            (ACCOUNTS / f"RELOAD-{a['id']}").write_text("Control Center install: reload between runs\n")
            print(f"{a['id']}: RELOAD flag set (the loop restarts on the new code when its next run ends; an idle or "
                  "yielding loop only after its next run, so restart it by hand if it should change sooner)")
    (bk / "INSTALLED.txt").write_text("install " + dt.datetime.now().isoformat(timespec="seconds"))
    print(f"Backup: {bk}")


def undo(cfg):
    bk = backup_dir(cfg)
    for acct, path in helper_settings(cfg):
        shutil.copy2(path, bk / f"{acct}-settings.json")
        write_json(path, remove_entries(json.loads(path.read_text(encoding="utf-8"))))
        print(f"{acct}: Control Center hooks and status line removed")
    if NEW_LNK.exists():
        shutil.move(str(NEW_LNK), bk / NEW_LNK.name)
    if OLD_DIR.is_dir():
        for lnk in OLD_DIR.glob("*.lnk"):
            if not (DESKTOP / lnk.name).exists():
                shutil.move(str(lnk), DESKTOP / lnk.name)
                print(f"{lnk.name} back on the desktop")
        if not any(OLD_DIR.iterdir()):
            OLD_DIR.rmdir()
    olds = sorted(Path(cfg["state_dir"], "backups").glob(f"*/{OLD_LNK.name}"))
    if olds and not OLD_LNK.exists():
        shutil.copy2(olds[-1], OLD_LNK)
        print("Agency LIVE shortcut restored")
    print(f"Backup of the state before undo: {bk}")


def check(cfg):
    for acct, path in helper_settings(cfg):
        d = json.loads(path.read_text(encoding="utf-8"))
        n = sum(1 for es in (d.get("hooks") or {}).values() for e in es if ours(e))
        sl = MARK in ((d.get("statusLine") or {}).get("command") or "")
        print(f"{acct}: {n} Control Center hook(s), status line {'yes' if sl else 'no'}")
    print(f"shortcut: {'yes' if NEW_LNK.exists() else 'no'} · old tools folder: "
          f"{sorted(p.name for p in OLD_DIR.glob('*.lnk')) if OLD_DIR.is_dir() else 'none'}")


if __name__ == "__main__":
    c = common.load_config()
    if "--undo" in sys.argv:
        undo(c)
    elif "--check" in sys.argv:
        check(c)
    else:
        install(c)
