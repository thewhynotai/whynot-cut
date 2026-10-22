"""Opens the WhyNot Control Center: the dashboard server (hidden, started once), the dashboard in the browser, and one
Windows Terminal window ("WhyNotCC") with exactly one tab per account. Tabs that are already open are not opened again.

    python -X utf8 launch.py            # what the desktop shortcut runs
    python -X utf8 launch.py --no-browser
"""
import os, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common, console, server  # noqa: E402

TAB_COLOURS = {"main": "#5aa9ff", "h1": "#3ecf8e", "h2": "#b48cff"}
WINDOW = "WhyNotCC"


def ensure_server(cfg):
    url = server.running_url(cfg)
    if url:
        return url
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pyw if pyw.exists() else sys.executable)
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | \
        getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen([exe, "-X", "utf8", str(Path(__file__).with_name("server.py"))], cwd=str(Path(__file__).parent),
                     creationflags=flags, close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    for _ in range(60):
        time.sleep(0.5)
        url = server.running_url(cfg)
        if url:
            return url
    return None


def window_args(cfg, url):
    """The dashboard as its own app window (Edge --app, own profile on D, so it never mixes with your browsing)."""
    w = cfg.get("app_window") or {}
    exe = w.get("browser")
    if not exe or not os.path.exists(exe):
        return None
    return [exe, f"--app={url}", f"--user-data-dir={w.get('profile_dir')}", "--no-first-run",
            "--no-default-browser-check", "--window-size=1500,950"]


def open_window(cfg, url):
    args = window_args(cfg, url)
    if args:
        subprocess.Popen(args)
    else:
        os.startfile(url)  # noqa: S606  fallback: the default browser, this PC only


def console_open(cfg, acct_id):
    p = common.state_path(cfg, "consoles", f"{acct_id}.lock")
    try:
        return console.pid_alive(int(p.read_text().split()[0]))
    except (OSError, ValueError, IndexError):
        return False


def tab_args(cfg, a):
    py = str(Path(sys.executable).with_name("python.exe"))
    title = f"{a['name']} · {a['email'].split('@')[0]}@"
    return ["new-tab", "--title", title, "--tabColor", TAB_COLOURS.get(a["id"], "#888888"), "--suppressApplicationTitle",
            "-d", a.get("work_dir") or str(common.CC), py, "-X", "utf8", str(Path(__file__).with_name("console.py")), a["id"]]


def wt_command(cfg, missing):
    args = ["wt.exe", "-w", WINDOW]
    for i, a in enumerate(missing):
        if i:
            args.append(";")
        args += tab_args(cfg, a)
    return args


def tell(msg):
    """Print, and also show a box when started without a console (the desktop shortcut uses pythonw)."""
    print(msg)
    if sys.executable.lower().endswith("pythonw.exe") and os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "WhyNot Control Center", 0x30)


def main():
    if console.started_inside_claude():
        tell("Open the Control Center from its desktop shortcut, not from inside a Claude session.")
        return 6
    cfg = common.load_config()
    print("Starting the WhyNot Control Center…")
    url = ensure_server(cfg)
    if not url:
        tell("The dashboard server did not start. See D:\\ClaudeData\\control-center\\server.log")
    elif "--no-browser" not in sys.argv:
        open_window(cfg, url)
    missing = [a for a in cfg["accounts"] if not console_open(cfg, a["id"])]
    if missing:
        subprocess.Popen(wt_command(cfg, missing))
        print("Terminals opened: " + ", ".join(a["name"] for a in missing))
    else:
        subprocess.Popen(["wt.exe", "-w", WINDOW, "focus-tab", "-t", "0"])
        print("All three terminals are already open (window WhyNotCC).")
    return 0 if url else 1


if __name__ == "__main__":
    sys.exit(main())
