"""User preferences, layered. Stdlib only (hooks import it).

Highest wins, key by key (3.0 T3.5); a layer that does not set a key lets the next one decide:
  1. the client's `.claude/whynot-cut.local.md` (the --root / current folder and its parents, nearest first)
  2. the machine's: <clients folder>/.claude/whynot-cut.local.md, then ~/.claude/whynot-cut.local.md
  3. the plugin options (userConfig: language, approval, whisper_model, magnific_budget_credits), through the
     CLAUDE_PLUGIN_OPTION_* variables, the pointer file ~/.whynot-cut/plugin-options.json or settings.json
     pluginConfigs (plat.plugin_options)
  4. DEFAULTS
An invalid value is ignored with a warning in `_problems` (the next layer, in the end the default, applies). The API key
(`magnific_api_key`) is not a preference: it never enters this module's output, files or warnings (plat.secret_option).
`clients_root` is not layered: the plugin option wins over the file (plat.clients_root_setting). Files are written by
/whynot-cut:start or /whynot-cut:preferences and hold only the values someone set. Never committed (add
`.claude/*.local.md` to .gitignore).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

FILE = "whynot-cut.local.md"
DEFAULTS = {
    "editor_name": "",            # how to address the editor
    "language": "ar",             # chat language: en | ar (the plugin option defaults to ar too)
    "approval": "ask",            # ask = stop at Gate 1 every time | auto = proceed after showing the plan (delegated)
    "whisper_model": "large-v3",  # large-v3 (best) | large-v3-turbo (faster) | medium
    "preview_video": True,        # render a watchable MP4 of the plan before approval
    "clients_root": "",           # folder holding the client folders
    "notify_done": True,          # say clearly when a long run finishes
    "panel_link": True,           # start the engine the Premiere panel talks to (`reel serve`) at session start
    "magnific_budget_credits": 300,  # most Magnific credits one edit may spend (0 = never use Magnific)
}
CHOICES = {"language": {"en", "ar"}, "approval": {"ask", "auto"},
           "whisper_model": {"large-v3", "large-v3-turbo", "medium", "small"}}
NUMBERS = {"magnific_budget_credits"}        # numbers of 0 or more


def _parse_scalar(v: str):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    low = v.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    return v.split(" #", 1)[0].strip()


def parse(text: str) -> tuple[dict, str]:
    """Frontmatter (flat key: value) and body. Unknown keys are kept; bad values fall back to defaults. A leading BOM
    (Notepad / PowerShell 5.1 "UTF-8") and Windows line ends are accepted (3.0 T2.2, engine MI-24)."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n")      # an escape, never a literal invisible BOM (T2.16)
    m = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)(.*)\Z", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        fm[k.strip()] = _parse_scalar(v)
    return fm, m.group(2)


def _number(v):
    """v as a number of 0 or more (a plain int or float, or text that is one), else None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, str):
        v = float(v) if re.fullmatch(r"\s*\d+(\.\d+)?\s*", v) else None
    if isinstance(v, (int, float)) and v == v and v < float("inf") and v >= 0:
        return int(v) if float(v).is_integer() else v
    return None


def check(key: str, value):
    """(value, None) when `value` is fine for `key`, else (None, why). Unknown keys and free-text keys always pass."""
    if key in CHOICES:
        return (value, None) if str(value) in CHOICES[key] else (None, f"is not one of {sorted(CHOICES[key])}")
    if key in NUMBERS:
        n = _number(value)
        return (n, None) if n is not None else (None, "must be a number of 0 or more")
    if isinstance(DEFAULTS.get(key), bool):
        return (value, None) if isinstance(value, bool) else (None, "must be true or false")
    return value, None


def _plat():
    from importlib import import_module      # plat as `lib.plat` (engine) or top-level `plat` (hooks)
    return import_module(".plat", __package__) if __package__ else import_module("plat")


def machine_files() -> list[Path]:
    """The machine-wide files, strongest first: the clients folder's, then ~/.claude's."""
    base = _plat().clients_root_setting()     # plugin option: env, else the saved option (pointer / settings.json)
    return ([base / ".claude" / FILE] if base else []) + [Path.home() / ".claude" / FILE]


def layer_files(start: Path | None = None) -> list[tuple[str, Path]]:
    """[(layer, path)] of the preferences files that exist, strongest first: the client's (the folder and its parents,
    nearest first, up to ~ when the folder is under it), then the machine's. A machine file that is also on the folder
    chain counts as the machine's."""
    start = Path(start or os.getcwd()).resolve()
    machine = machine_files()
    chain = [start, *start.parents]
    try:                                       # a folder under ~ climbs no higher than ~ (its file is the machine's)
        chain = chain[:chain.index(Path.home().resolve()) + 1]
    except ValueError:
        pass

    def key(p: Path) -> str:
        return os.path.normcase(str(p.resolve()))
    mkeys = {key(p) for p in machine}
    out, seen = [], set()
    for layer, cands in (("client", [d / ".claude" / FILE for d in chain]), ("machine", machine)):
        for c in cands:
            if c.is_file() and key(c) not in seen and (layer == "machine" or key(c) not in mkeys):
                seen.add(key(c))
                out.append((layer, c))
    return out


def find(start: Path | None = None) -> Path | None:
    """The strongest preferences file (None = no file)."""
    files = layer_files(start)
    return files[0][1] if files else None


def read_file(f: Path) -> tuple[dict, str, list]:
    """One preferences file on its own: (valid values, notes, problems). Invalid values are dropped, with a problem
    each; an unreadable or non-UTF-8 file gives nothing and one problem."""
    fm, body, data, problems = {}, "", b"", []
    try:
        data = f.read_bytes()
        fm, body = parse(data.decode("utf-8-sig"))
    except OSError as e:
        problems.append(f"unreadable: {e}")
    except UnicodeDecodeError as e:     # never a crash (the hooks read this file): the defaults, and say where
        line = data[:e.start].count(b"\n") + 1
        problems.append(f"{f}: line {line} is not UTF-8 text (save the file as UTF-8); using the defaults")
    vals = {}
    for k, v in fm.items():
        ok, why = check(k, v)
        if why:
            problems.append(f"{f}: {k}: {v!r} {why}; ignored (the next layer or the default applies)")
        else:
            vals[k] = ok
    return vals, body.strip(), problems


def _plugin_layer() -> tuple[dict, list]:
    """The userConfig layer: the non-secret plugin options that are set and valid, and a problem for each that is not."""
    vals, problems = {}, []
    try:
        opts = _plat().plugin_options()
    except Exception:                         # a hook must never fail because of an odd options file
        return vals, problems
    for k, text in opts.items():
        if text == "":
            continue
        ok, why = check(k, _parse_scalar(text))
        if why:
            problems.append(f"plugin option {k}: {text!r} {why}; ignored (the default applies)")
        else:
            vals[k] = ok
    return vals, problems


def load(start: Path | None = None) -> dict:
    """Effective settings and where each came from: `_file` (the strongest preferences file or None), `_files`
    ([{layer, file}]), `_sources` (key -> client | machine | userConfig | default), `_where` (key -> the file, "plugin
    option" or "default"), `_problems` (warnings, never the API key), `_notes` (the strongest file's free text) and
    `magnific_api_key_set` (whether a key reached this process; the key itself never does)."""
    out = dict(DEFAULTS)
    sources = {k: "default" for k in DEFAULTS}
    where = {k: "default" for k in DEFAULTS}
    problems, notes, files = [], "", []
    stack = []                                # strongest first: (layer, where, values)
    for layer, f in layer_files(start):
        vals, body, probs = read_file(f)
        files.append({"layer": layer, "file": str(f)})
        notes = notes or body
        problems += probs
        stack.append((layer, str(f), vals))
    uvals, uprobs = _plugin_layer()
    problems += uprobs
    stack.append(("userConfig", "plugin option", uvals))
    for layer, loc, vals in reversed(stack):  # weakest first, so the stronger layer overwrites
        for k, v in vals.items():
            out[k], sources[k], where[k] = v, layer, loc
    out["_notes"] = notes
    out["_file"] = files[0]["file"] if files else None
    out["_files"] = files
    out["_sources"] = sources
    out["_where"] = where
    out["_problems"] = problems
    out["magnific_api_key_set"] = bool(_plat().secret_option("magnific_api_key"))
    return out


def render(values: dict, notes: str = "") -> str:
    """A preferences file holding exactly `values`: nothing else is written, so the plugin options and the defaults
    keep applying to every key the file leaves out."""
    given = {k: v for k, v in values.items() if not k.startswith("_") and not k.endswith("_key_set")}
    v = {**{k: given[k] for k in DEFAULTS if k in given}, **{k: x for k, x in given.items() if k not in DEFAULTS}}

    def fmt(x):
        if isinstance(x, bool):
            return "true" if x else "false"
        if isinstance(x, (int, float)):
            return str(x)
        s = str(x).replace('"', '\\"')
        return f'"{s}"'
    body = [f"{k}: {fmt(val)}" for k, val in v.items()] or ["# nothing set here: the plugin options and defaults apply"]
    lines = ["---"] + body + ["---", "", notes.strip() or
             "# WhyNot Cut preferences\n\nEdit the values above (or run /whynot-cut:preferences). "
             "Changes apply from the next message; hooks pick them up in the next session."]
    return "\n".join(lines) + "\n"


def save(path: Path, values: dict, notes: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(values, notes), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path
