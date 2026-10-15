"""Test-only stand-in for the Claude Code CLI (tests/test_installer.py, T7.1 claude step). Never shipped to editors.

How the installer core runs it: env WNC_CLAUDE_CLI (or CLAUDE_CLI; only these and the bundles under the fake home are
searched in a sandbox, --home) names this file or one of its wrappers. A value ending in `.py` is run as
`<the core's own sys.executable> -B fake_claude.py ...`; a value ending in `.sh` is run as `bash fake_claude.sh ...` (git keeps
it 100644, so it is never exec'd); any other value (fake_claude.cmd on Windows) is run directly. The wrappers start this file with $FAKE_CLAUDE_PYTHON (default `python` / `python3`).

Behaviour (it imitates the files the real CLI keeps, but only under $CLAUDE_CONFIG_DIR, which the sandboxed core
always sets; without it every call that would write fails, so the real ~/.claude is never touched):
  --version                              prints `<FAKE_CLAUDE_VERSION or 2.1.300> (Claude Code)`
  plugin marketplace add <source>        records {"source": {"source": "directory"|"url", ...}} under its name
                                         (`thewhynot-ai`) in plugins/known_marketplaces.json, and (like the real
                                         CLI) in settings.json extraKnownMarketplaces
  plugin marketplace remove <name>       removes that entry (and the name's plugins from installed_plugins.json)
  plugin install <id> [--scope user]     lists <id> in plugins/installed_plugins.json and sets
                                         settings.json enabledPlugins[<id>] = true
                                         settings.json is rewritten only when its content changes; one it cannot parse
                                         is REPLACED (the worst case a real CLI could do), so a test can prove the
                                         installer never lets the CLI near an unreadable settings.json
  plugin update <id>                     exit 0 (exit 1 when <id> is not installed)
  plugin uninstall <id> [--scope user]   removes <id> from installed_plugins.json and settings.json enabledPlugins
                                         (exit 1 when it is not installed)
  FAKE_CLAUDE_INSTALLED=1                every call (even --version) first lists whynot-cut@thewhynot-ai in
                                         installed_plugins.json (an editor who already has the plugin)
  FAKE_CLAUDE_FAIL=<word>                exit 1 for the call whose argv contains <word> (add / remove / install /
                                         update / --version), after logging it
Every call appends {"argv": [...], "CLAUDE_CONFIG_DIR": <env value>} as one JSON line to $FAKE_CLAUDE_LOG (when set).
"""
import json
import os
import sys

MARKETPLACE = "thewhynot-ai"


def _plugins_dir():
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    if not cfg:
        sys.stderr.write("fake claude: CLAUDE_CONFIG_DIR is not set; refusing to write\n")
        sys.exit(3)
    d = os.path.join(cfg, "plugins")
    os.makedirs(d, exist_ok=True)
    return d


def _load(name):
    p = os.path.join(_plugins_dir(), name)
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _save(name, data):
    with open(os.path.join(_plugins_dir(), name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _install(pid):
    inst = _load("installed_plugins.json")
    inst.setdefault("version", 2)
    inst.setdefault("plugins", {})[pid] = [{"scope": "user", "version": "3.0.0"}]
    _save("installed_plugins.json", inst)


def _settings(key, name, value):
    """settings.json[key][name] = value, written only when that changes anything (or the file cannot be parsed)."""
    path = os.path.join(os.path.dirname(_plugins_dir()), "settings.json")
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except FileNotFoundError:
        data = {}
    except ValueError:  # unparsable: replaced
        data = {}
    else:
        if isinstance(data.get(key), dict) and data[key].get(name) == value:
            return
    if not isinstance(data.get(key), dict):
        data[key] = {}
    data[key][name] = value
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _unset(key, name):
    """del settings.json[key][name] (and an emptied [key]), written only when that changes anything."""
    path = os.path.join(os.path.dirname(_plugins_dir()), "settings.json")
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        return
    if not isinstance(data, dict) or not isinstance(data.get(key), dict) or name not in data[key]:
        return
    del data[key][name]
    if not data[key]:
        del data[key]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main(argv):
    log = os.environ.get("FAKE_CLAUDE_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"argv": argv, "CLAUDE_CONFIG_DIR": os.environ.get("CLAUDE_CONFIG_DIR")},
                               ensure_ascii=False) + "\n")
    fail = os.environ.get("FAKE_CLAUDE_FAIL")
    if fail and fail in argv:
        sys.stderr.write(f"fake claude: failing {argv!r} on purpose\n")
        return 1
    if os.environ.get("FAKE_CLAUDE_INSTALLED") == "1":
        _install(f"whynot-cut@{MARKETPLACE}")
    if argv[:1] == ["--version"]:
        print(os.environ.get("FAKE_CLAUDE_VERSION", "2.1.300") + " (Claude Code)")
        return 0
    if argv[:3] == ["plugin", "marketplace", "add"] and len(argv) >= 4:
        src = argv[3]
        source = {"source": "url", "url": src} if "://" in src else {"source": "directory", "path": src}
        known = _load("known_marketplaces.json")
        known[MARKETPLACE] = {"source": source, "installLocation": src, "lastUpdated": "2026-10-12T00:00:00.000Z"}
        _save("known_marketplaces.json", known)
        _settings("extraKnownMarketplaces", MARKETPLACE, {"source": source})
        return 0
    if argv[:3] == ["plugin", "marketplace", "remove"] and len(argv) >= 4:
        known = _load("known_marketplaces.json")
        known.pop(argv[3], None)
        _save("known_marketplaces.json", known)
        inst = _load("installed_plugins.json")
        for pid in [p for p in inst.get("plugins", {}) if p.endswith("@" + argv[3])]:
            del inst["plugins"][pid]
        _save("installed_plugins.json", inst)
        return 0
    if argv[:2] == ["plugin", "install"] and len(argv) >= 3:
        _install(argv[2])
        _settings("enabledPlugins", argv[2], True)
        return 0
    if argv[:2] == ["plugin", "update"] and len(argv) >= 3:
        return 0 if argv[2] in _load("installed_plugins.json").get("plugins", {}) else 1
    if argv[:2] == ["plugin", "uninstall"] and len(argv) >= 3:
        inst = _load("installed_plugins.json")
        if argv[2] not in inst.get("plugins", {}):
            sys.stderr.write(f"fake claude: {argv[2]} is not installed\n")
            return 1
        del inst["plugins"][argv[2]]
        _save("installed_plugins.json", inst)
        _unset("enabledPlugins", argv[2])
        return 0
    sys.stderr.write(f"fake claude: unsupported call {argv!r}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
