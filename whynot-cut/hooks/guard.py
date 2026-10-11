#!/usr/bin/env python3
"""WhyNot Cut PreToolUse guard (stdlib only; macOS and Windows). Exit 2 + stderr = block; exit 0 = allow.

Rules enforced in code (prose rules get forgotten in long sessions):
  1. Client source folders are read-only: nothing may write, move or delete inside <client>/assets or
     <client>/data, nor delete or move a folder that holds them (the client folder itself, `rm -rf .` or `*` in it,
     a folder whose direct child is a client), nor delete or overwrite <client>/.whynot-client. A client folder has
     BOTH assets/ and data/ AND a positive sign: a `.whynot-client` file, an `output/client_database/` folder, or it
     lies under the configured clients folder (`clients_root`). A Hugo site or any other repo with assets/ + data/ is
     left alone (engine/reel/lib/client_marker.py).
  2. Whole project folders are not deleted by the agent (rm -r on output/ or output/projects/<ID>).
  3. After Effects / Photoshop builds are opt-in extras: `reel ae-*|ps-*|mogrt-build` need --extras.
  4. Roles: subagents never approve the plan, record a verification verdict or verify a transcript as the editor
     (the lead does, after looking); WhyNot Cut's reviewer agents (matched on the full `whynot-cut:<name>`) are
     read-only; setup-doctor diagnoses and never installs.
  5. Adobe preferences (PlayerDebugMode, After Effects prefs) are the editor's to change.

Covers the Write/Edit tools, Bash (macOS/Linux shells and Git Bash on Windows, incl. /d/... paths) and PowerShell
(cmdlets, aliases, redirection, pipelines, script blocks `{ }`, `$( )` bodies, [IO.File]:: and .Delete()-style
calls, Invoke-Expression), and what they start: `cmd /c|//c` (with its own & && || | and ^), `powershell|pwsh
-Command|-EncodedCommand`, `bash|sh -c`, `eval`, shell heredocs and here-strings, `xargs`, `timeout`/`nice`/`env`/...
Paths are expanded first: globs (against the real folder), $PWD, $(pwd), $HOME, $env:USERPROFILE, ~, and variables
assigned from a client source within the same command (`for f in data/Raw/*`, `$f = Get-ChildItem data`,
`foreach ($f in ...)`, `$_` in a block fed by such a pipeline).
Limits (a guardrail against mistakes, not a sandbox; it errs on the side of allowing reads), not inspected:
  * writes made from inside an interpreter (`python -c`, a script file, `node -e`);
  * variables set in an earlier tool call or outside the command ($env:X set before; `export` in another call);
  * arrays and string building beyond the simple forms (`a=(data assets)`, `"da" + "ta"` are caught; `${a[1]}`,
    `$x = $y + 'ta'`, format strings, `-join` are not);
  * `while read` loops, functions and aliases defined on the fly, `parallel` beyond `parallel CMD ::: ARGS`;
  * folders that hold a client deeper than one level (`rm -rf ~/work` when the client is ~/work/clients/X);
  * a client recognised only by output/client_database (no `.whynot-client`): deleting that folder through a form the
    guard misses switches its protection off, so run `reel doctor --fix` to write the marker.
"""
from __future__ import annotations

import base64
import fnmatch
import glob
import json
import os
import re
import shlex
import sys
import time
from functools import lru_cache
from pathlib import Path

sys.dont_write_bytecode = True        # the plugin folder stays clean of __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine" / "reel" / "lib"))
import client_marker  # noqa: E402  (stdlib only; reads the preferences lazily)

PLUGIN_AGENT = "whynot-cut:"           # role rules apply to this plugin's own agents only
READ_ONLY_AGENTS = {"medical-reviewer", "claim-checker", "frame-inspector", "graphic-checker",
                    "segment-proofreader", "qc-reviewer", "intake-inspector", "setup-doctor", "moment-scout"}
EXTRAS = {"ae-script", "ae-build", "ae-render", "ps-script", "ps-build", "mogrt-build"}
QC_FORBIDDEN = {"ppro-build", "approve-plan", "plan", "previews", "audio-clean", "transcribe",
                "transcript-correct", "client-init", "client-db", "sfx", "premiere", "handoff",
                "reels-select", "reels-plan", "episode-transcribe", "publish-check",
                "motion-plan", "motion-animatic", "motion-build", "motion-render", "ref-analyze"}
SETUP_DOCTOR_FORBIDDEN = {"setup", "model-download", "gpu-enable", "ppro-install"}
GLOBAL_VALUE_OPTS = ("--root", "--video-id", "--profile", "--episode")
MUTATE_ALL = {"rm", "mv", "touch", "chmod", "chown", "truncate", "unlink", "rmdir", "shred", "dot_clean",
              "setfile", "srm"}
MUTATE_DEST = {"cp", "rsync", "ditto", "ln", "ffmpeg", "tee", "mkdir", "install", "scp", "curl", "wget",
               "unzip", "tar", "sips", "convert", "magick"}
FFMPEG_FLAGS = {"-y", "-n", "-hide_banner", "-nostdin", "-stdin", "-shortest", "-an", "-vn", "-sn", "-dn", "-stats",
                "-nostats", "-benchmark", "-copyts", "-re", "-accurate_seek", "-noaccurate_seek", "-report"}
FFMPEG_WRITE_OPTS = {"-progress", "-passlogfile", "-vstats_file", "-dump_attachment"}
FIND_WRITE_ACTIONS = {"-fprint", "-fprint0", "-fprintf", "-fls"}
SEPARATORS = {"&&", "||", ";", "|", "&"}
SHELL_KEYWORDS = {"then", "do", "else", "elif", "if", "while", "until", "!", "{", "(", "&", "."}
WRAPPERS = {  # prefix commands that run the rest of the line: {name: options that take a value}
    "sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-U", "-r", "-t"}, "doas": {"-u", "-C"}, "time": {"-f", "-o"},
    "nohup": set(), "command": set(), "builtin": set(), "exec": {"-a"}, "nice": {"-n"}, "ionice": {"-c", "-n", "-p"},
    "stdbuf": {"-i", "-o", "-e"}, "env": {"-u", "-C", "-S", "--unset", "--chdir"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"}, "winpty": set(), "watch": {"-n", "--interval"},
    "flock": {"-w", "--timeout", "-E", "--conflict-exit-code"}}
LISTERS = {"ls", "dir", "gci", "get-childitem", "find", "fd"}       # list the folder they are given (or the cwd)
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
PWSH = {"powershell", "pwsh"}
GIT_MUTATE = {"checkout", "reset", "clean", "rm", "mv", "restore", "stash"}
XARGS_VALUE_OPTS = {"-I", "-L", "-n", "-P", "-d", "-E", "-s", "-a", "--max-args", "--max-procs", "--delimiter",
                    "--arg-file", "--max-lines", "--eof", "--max-chars"}
PATH_PROPS = {"fullname", "pspath", "path", "literalpath", "directory", "directoryname", "psparentpath", "parent"}

IS_WIN = os.name == "nt"
_MSYS = re.compile(r"^/([a-zA-Z])(/|$)")
TAINT: dict[str, tuple[str, str]] = {}     # variable (lower-case) -> (hit label, a source token) for this command
VALUES: dict[str, str] = {}                # PowerShell string variables of this command (for `iex $s`)
SH_VARS: set[str] = set()                  # tainted variables set by Bash / cmd (no .Property access there)
CMD_CWD: list[Path] = []                   # working folder of the cmd body being converted


def native(s: str) -> str:
    """Git Bash on Windows writes the D: drive as /d/...; Python needs D:/..."""
    if IS_WIN and s:
        m = _MSYS.match(s)
        if m:
            return f"{m.group(1).upper()}:/{s[3:]}"
    return s


def block(msg: str):
    print(f"WhyNot Cut guard: {msg}", file=sys.stderr)
    sys.exit(2)


def norm_exe(tok: str) -> str:
    """Command name as compared: basename, lower-case (Git Bash and Windows are case-insensitive), no .exe/.cmd/.bat,
    no leading backslash (`\\rm`)."""
    name = re.split(r"[\\/]", tok.strip("'\""))[-1].lower()
    for ext in (".exe", ".cmd", ".bat"):
        if name.endswith(ext):
            name = name[:-len(ext)]
    return name


# --------------------------------------------------------------------------- client folders and paths
@lru_cache(maxsize=None)
def _is_client(root: str) -> bool:
    p = Path(root)
    try:
        return client_marker.is_client(p)
    except Exception:      # unreadable preferences etc.: the markers that need no settings still count
        return client_marker.has_layout(p) and ((p / client_marker.MARKER).is_file() or
                                                (p / "output" / "client_database").is_dir())


def is_client(p: Path) -> bool:
    return _is_client(str(p))


def loose_resolve(p: Path) -> Path:
    """Resolve the deepest existing ancestor, keep the rest as written (paths that do not exist yet)."""
    p = p.expanduser()
    rest = []
    cur = p
    while not cur.exists() and cur.parent != cur:
        rest.append(cur.name)
        cur = cur.parent
    try:
        cur = cur.resolve()
    except OSError:
        pass
    for name in reversed(rest):
        cur = cur / name
    return cur


def client_root_of(p: Path) -> tuple[Path, str] | None:
    """If p is inside <root>/assets or <root>/data of a client folder (any case: DATA/new does not exist yet but would
    land in data/ on Windows and macOS), or is <root>/.whynot-client, return (root, 'assets'|'data'|marker)."""
    try:
        p = loose_resolve(p)
    except Exception:
        return None
    if p.name.lower() == client_marker.MARKER and is_client(p.parent):
        return p.parent, client_marker.MARKER
    for anc in [p, *p.parents]:
        low = anc.name.lower()
        if low in ("assets", "data"):
            root = anc.parent
            if client_marker.has_layout(root) and is_client(root):
                return root, low
    return None


def hit_of(p: Path) -> str | None:
    hit = client_root_of(p)
    return f"{hit[0].name}/{hit[1]}" if hit else None


def holds_sources(p: Path) -> str | None:
    """p is a folder that holds a client's sources: the client folder itself or a folder with a client directly in it."""
    try:
        p = loose_resolve(p)
        if not p.is_dir():
            return None
        if client_marker.has_layout(p) and is_client(p):
            return f"{p.name} (the client folder with assets/ and data/)"
        for i, c in enumerate(p.iterdir()):
            if i > 500:
                break
            if c.is_dir() and client_marker.has_layout(c) and is_client(c):
                return f"{p.name} (holds the client folder {c.name})"
    except OSError:
        return None
    return None


_VAR = re.compile(r"^%%?(\w+)%?|^\$\{?((?:env:)?\w+)\}?((?:\.\w+)*)", re.I)
_PWD = re.compile(r"\$\(\s*(?:pwd|get-location)\s*\)|`pwd`|\$\{PWD\}|\$PWD\b|%CD%", re.I)
_HOME = re.compile(r"\$\{HOME\}|\$HOME\b|\$env:USERPROFILE\b|\$env:HOME\b", re.I)


def tainted(tok: str, any_prop: bool = False) -> tuple[str, str] | None:
    """The variable that STARTS tok, when it was set from a client source in this command: $f, "$f", ${f}, $f/x,
    ${F%/}, $f.FullName, %f (cmd). Not "output/${f##*/}.wav" or "output/$(basename "$f")" (the path is output's),
    not $f.Name / $f.BaseName (a bare name)."""
    t = tok.strip("'\"")
    if t.startswith("./"):
        t = t[2:]
    if t.startswith("$("):                       # "$($_.FullName)", "$(dirname "$f")/x.wav" -> the inner value
        depth, j = 1, 2
        while j < len(t) and depth:
            depth += {"(": 1, ")": -1}.get(t[j], 0)
            j += 1
        inner = t[2:j - 1].strip()
        words = inner.split()
        if words and words[0].lower() in ("dirname", "realpath", "readlink", "resolve-path", "split-path"):
            return next((h for h in (tainted(w) for w in words[1:]) if h), None)
        return tainted(inner, any_prop) if len(words) == 1 else None
    m = _VAR.match(t.lstrip("("))
    if not m:
        return None
    name = (m.group(1) or m.group(2)).lower()
    hit = TAINT.get(name)
    if not hit:
        return None
    if name in SH_VARS:                          # Bash: "$f.wav", "${f%.mp4}.wav" stay next to the source;
        return None if re.match(r"^\$\{\w+##?\*?/", t) else hit       # "${f##*/}" is a bare name
    props = [x for x in (m.group(3) or "").lower().split(".") if x]
    if any_prop or not props or props[-1] in PATH_PROPS:
        return hit
    return None


def expand(s: str, cwd: Path) -> str:
    s = _PWD.sub(lambda m: str(cwd).replace("\\", "/"), s)
    s = _HOME.sub(lambda m: str(Path.home()).replace("\\", "/"), s)
    return s


def brace_expand(s: str) -> list[str]:
    """Bash brace expansion: {assets,data} -> assets data, dat{a,} -> data dat (not ${var})."""
    m = re.search(r"(?<!\$)\{([^{}]*,[^{}]*)\}", s)
    if not m:
        return [s]
    out = []
    for part in m.group(1).split(","):
        out += brace_expand(s[:m.start()] + part + s[m.end():])
    return out[:64]


def paths_of(tok: str, cwd: Path) -> list[Path]:
    """The paths a shell word names: quotes stripped, $PWD/%CD%/~ expanded, braces expanded, `key=value` -> value,
    globs matched against the folder (plus the pattern itself when nothing matches)."""
    words = brace_expand(tok.strip("'\""))
    if len(words) > 1:
        return [x for w in words for x in paths_of(w, cwd)]
    s = native(expand(words[0], cwd))
    if "=" in s and not s.startswith("/") and not re.match(r"^[A-Za-z]:[\\/]", s):   # dd of=..., key=value
        s = s.split("=", 1)[1]
    if not s:
        return []
    try:
        p = Path(native(s)).expanduser()
    except Exception:
        return []
    if not p.is_absolute():
        p = cwd / p
    if any(c in s for c in "*?[") and "$" not in s:
        try:
            hits = glob.glob(str(p))[:500]
        except Exception:
            hits = []
        return [Path(h) for h in hits] + [p]
    return [p]


AE_PREFS = re.compile(r"(adobe[\\/]+after effects[\\/]+\d[\d.]*[\\/])|(adobe after effects [^\\/]*prefs[^\\/]*\.txt$)", re.I)
AE_PREFS_MSG = ("After Effects preferences are the editor's to change (scripting security, Type engine). "
                "Give them the step to do themselves.")


def ae_pref_path(path_str: str) -> bool:
    """After Effects preference files (scripting security, Type engine…): the editor's to change, never Claude's."""
    return bool(path_str) and bool(AE_PREFS.search(path_str.replace("\\", "/")))


def protected(path_str: str, cwd: Path, writing: bool = True, recursive: bool = False) -> str | None:
    """'<client>/assets|data' when path_str (relative to cwd) is inside a client's sources. writing=False: a path
    that is only named (read). recursive=True: also a folder that holds a client's sources (delete/move of a tree)."""
    if not path_str or path_str.startswith("-"):
        return None
    if writing and ae_pref_path(path_str.strip("'\"")):
        block(AE_PREFS_MSG)             # every caller is about to write there: not a client-folder message
    t = tainted(path_str)
    if t:
        return t[0]
    for p in paths_of(path_str, cwd):
        hit = hit_of(p) or (holds_sources(p) if recursive else None)
        if hit:
            return hit
    return None


def first_source(tokens: list[str], cwd: Path) -> tuple[str, str] | None:
    """(hit, token) for the first token naming a client source (a read), variables included."""
    for a in tokens:
        hit = protected(a, cwd, writing=False)
        if hit:
            return hit, a
    return None


FIND_FILTERS = {"-name", "-iname", "-path", "-ipath", "-regex", "-iregex", "-wholename", "-iwholename", "-lname",
                "-ilname", "-type", "-newer", "-size", "-mtime", "-mmin", "-user", "-group", "-perm", "-maxdepth",
                "-mindepth", "-empty"}                       # their values are not paths
PS_FILTERS = {"-filter", "-include", "-exclude", "-file", "-directory", "-attributes", "-hidden"}
FILTER_STAGES = {"grep", "egrep", "fgrep", "rg", "findstr", "select-string", "sls", "where-object", "where", "?",
                 "awk", "sed", "head", "tail", "select-object", "select"}
# what narrows a listing (T11): a name/path/regex predicate or a -Filter/-Include that matches none of the client's
# own files (so `-name '*.tmp'` narrows, `-name '*.mp4'`, `-name '*'`, `-Filter *` do not), -File without recursion, a
# grep or Where-Object stage. Depth, type, -empty, -newer, -Directory, -Exclude, head/tail/select do not. In `find`, a
# predicate after `!`/`-not` or in a branch with -prune does not count, and with -o every branch needs one.
FIND_NARROW = {"-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-regex", "-iregex"}
NARROW_STAGES = {"grep", "egrep", "fgrep", "rg", "findstr", "select-string", "sls", "where-object", "where", "?"}
# entries of the clients' assets/ + data/ compared with filters, per guard call (the variable is for tests)
SOURCE_SCAN_BUDGET = int(os.environ.get("WHYNOT_GUARD_SCAN_BUDGET") or 100_000)
TEMP_PATTERNS = {"*.tmp", "*.temp", "*.log", "*.bak", "__pycache__", "*.pyc", ".ds_store", "thumbs.db", "*.part"}
_SCAN = {"left": SOURCE_SCAN_BUDGET}


class _ScanBudget(Exception):
    """The call-wide entry budget is spent: the filter cannot be compared with the client's files."""


def find_starts(argv: list[str]) -> list[str]:
    """`find` start paths: the words before the first expression token."""
    starts = []
    for a in argv[1:]:
        if a.startswith(("-", "(", "!")) and a not in ("-H", "-L", "-P"):
            break
        if not a.startswith("-"):
            starts.append(a)
    return starts


def _source_entries(root: Path):
    """(relative posix path, name) of the client's marker and every folder and file under its assets/ and data/,
    lazily; every entry spends one unit of the call-wide budget (_ScanBudget when it is gone)."""
    if (root / client_marker.MARKER).exists():
        yield client_marker.MARKER, client_marker.MARKER
    try:
        subs = [c for c in root.iterdir() if c.is_dir() and c.name.lower() in ("assets", "data")]
    except OSError:
        return
    for sub in subs:
        yield sub.name, sub.name
        for dirpath, dirs, files in os.walk(sub):
            rel = Path(dirpath).relative_to(root).as_posix()
            for n in dirs + files:
                _SCAN["left"] -= 1
                if _SCAN["left"] < 0:
                    raise _ScanBudget
                yield f"{rel}/{n}", n


def _clients_at(p: Path) -> list[Path]:
    """The client folders a listing that starts at p reaches: p itself, or the clients directly in it."""
    try:
        p = loose_resolve(p)
        if not p.is_dir():
            return []
        if client_marker.has_layout(p) and is_client(p):
            return [p]
        return [c for i, c in enumerate(p.iterdir()) if i <= 500 and c.is_dir() and client_marker.has_layout(c)
                and is_client(c)]
    except OSError:
        return []


def _temp_style(pattern: str) -> bool:
    """A plain temp/junk-file pattern (`*.tmp`, `__pycache__`, `*/.DS_Store` ...): trusted when the scan budget is gone."""
    return re.split(r"[\\/]", pattern.lower())[-1] in TEMP_PATTERNS


@lru_cache(maxsize=None)
def filter_spares_sources(opt: str, pattern: str, start: str, at: Path) -> bool:
    """True when the predicate `opt pattern` (find -name/-path/-regex..., Get-ChildItem -Filter/-Include) matches
    none of the client's own entries reached from `start` (relative to at) -- it narrows the listing away from them.
    Stops at the first matching entry; past the call-wide budget only a temp-style pattern is trusted."""
    pattern = pattern.strip("'\"")
    base = Path(native(expand(start.strip("'\""), at))).expanduser()
    base = base if base.is_absolute() else at / base
    try:
        for root in _clients_at(base):
            prefix = start.strip("'\"").rstrip("/\\") or "."
            if loose_resolve(base) != root:             # the start holds the client: find prints <start>/<client>/...
                prefix = f"{prefix}/{root.name}"
            for rel, name in _source_entries(root):
                path = f"{prefix}/{rel}"
                if opt in ("-name", "-filter", "-include", "-iname"):     # Windows/macOS names ignore case
                    hit = fnmatch.fnmatchcase(name.lower(), pattern.lower())
                elif opt in ("-path", "-wholename"):
                    hit = fnmatch.fnmatchcase(path, pattern)
                elif opt in ("-ipath", "-iwholename"):
                    hit = fnmatch.fnmatchcase(path.lower(), pattern.lower())
                else:                                   # -regex / -iregex match the whole path
                    hit = re.fullmatch(pattern, path, re.I if opt == "-iregex" else 0) is not None
                if hit:
                    return False
    except re.error:
        return False                                    # a pattern we cannot read narrows nothing
    except _ScanBudget:
        return _temp_style(pattern)
    return True


FIND_ACTIONS = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-print", "-print0", "-printf", "-fprint", "-fprint0",
                "-fprintf", "-ls", "-fls"}
FIND_OR = {"-o", "-or", ","}                # `,` also runs both sides


def _find_expr(toks: list[str], j: int = 0) -> tuple[list[list], int]:
    """Parse a find expression into branches (split at -o / -or / `,` on this level); a branch is a list of items:
    a word, or ("group", branches) for `( ... )`. Returns (branches, index after the closing paren)."""
    branches, cur = [], []
    while j < len(toks):
        t = toks[j]
        if t in ("(", "\\("):
            sub, j = _find_expr(toks, j + 1)
            cur.append(("group", sub))
            continue
        if t in (")", "\\)"):
            branches.append(cur)
            return branches, j + 1
        if t.lower() in FIND_OR:
            branches.append(cur)
            cur = []
        else:
            cur.append(t)
        j += 1
    branches.append(cur)
    return branches, j


def _has_action(branch: list) -> bool:
    return any(it[1] and any(_has_action(b) for b in it[1]) if isinstance(it, tuple) else it.lower() in FIND_ACTIONS
               for it in branch)


def find_narrowed(argv: list[str], at: Path | None) -> bool:
    """A `find` whose expression keeps it away from the client's files. Branches split at -o / -or / `,` (and inside
    parentheses). When the expression has an action (-delete, -exec, -print ...), every branch WITH an action must be
    narrowed (a branch that only prunes, `-path ./data -prune`, needs nothing); without one (a listing), every branch.
    A branch is narrowed by a FIND_NARROW predicate that is not after `!`/`-not`, sits in a branch without -prune and
    spares the client's files, or by a group whose branches are all narrowed."""
    starts = find_starts(argv) or ["."]
    k = 1
    while k < len(argv) and not (argv[k].startswith(("-", "(", "!", "\\(")) and argv[k] not in ("-H", "-L", "-P")):
        k += 1
    while k < len(argv) and argv[k] in ("-H", "-L", "-P"):
        k += 1
    expr, _ = _find_expr(argv[k:])

    def narrowed(branch: list) -> bool:
        if any(not isinstance(it, tuple) and it.lower() == "-prune" for it in branch):
            return False
        neg, j = False, 0
        while j < len(branch):
            it = branch[j]
            if isinstance(it, tuple):
                if not neg and all(narrowed(b) for b in it[1]):
                    return True
                neg = False
            else:
                t = it.lower()
                if t in ("!", "-not"):
                    neg = True
                elif t in FIND_FILTERS and t != "-empty" and j + 1 < len(branch):
                    if t in FIND_NARROW and not neg and not isinstance(branch[j + 1], tuple) and \
                            (at is None or all(filter_spares_sources(t, branch[j + 1], s, at) for s in starts)):
                        return True
                    neg = False
                    j += 1
                else:
                    neg = False
            j += 1
        return False
    acting = [b for b in expr if _has_action(b)]
    return all(narrowed(b) for b in (acting or expr))


def stage_paths(argv: list[str], at: Path | None = None, file_narrows: bool = True) -> tuple[list[str], bool]:
    """(the words of a pipeline stage that name paths, narrowed?) -- filter values (-Filter *data*, find -name
    'assets*', grep patterns, Where-Object expressions) are not paths; only a narrowing stage or predicate narrows
    the list (see FIND_NARROW; `at` = the stage's working folder, to compare the filters with the client's files)."""
    e = norm_exe(argv[0])
    args = argv[1:] if not argv[0].startswith("$") else argv
    if e in FILTER_STAGES:
        if e in ("grep", "egrep", "fgrep", "rg", "findstr"):
            pos = [a for a in args if not a.startswith("-")]
            return pos[1:], True                # the first word is the pattern
        return [], e in NARROW_STAGES
    finder = e in ("find", "fd")
    opts = FIND_FILTERS if finder else PS_FILTERS if e in ("gci", "get-childitem", "dir", "ls") else set()
    out, preds, skip, files_only = [], [], None, False
    for a in args:
        if skip:
            if skip in ("-filter", "-include"):
                preds.append((skip, a))
            skip = None
            continue
        low = a.lower()
        if low in opts:
            files_only = files_only or (not finder and low == "-file")
            skip = low if low not in ("-file", "-directory", "-hidden", "-empty") else None
            continue
        out.append(a)
    if finder:
        return out, find_narrowed(argv, at)
    starts = [a for a in out if not a.startswith("-") and a.lower() not in PS_PATH_PARAMS] or ["."]
    spare = bool(preds) and any(at is None or all(filter_spares_sources(o, v, s, at) for s in starts)
                                for o, v in preds)
    return out, (files_only and file_narrows and not lists_tree(argv)) or spare


def excludes_marker(argv: list[str]) -> bool:
    """A Get-ChildItem -Exclude pattern that matches .whynot-client."""
    return any(len(a) > 3 and "-exclude".startswith(a.lower()) and
               any(fnmatch.fnmatchcase(client_marker.MARKER, v.strip("'\" ").lower()) for v in argv[i + 1].split(","))
               for i, a in enumerate(argv[:-1]))


def lists_tree(argv: list[str]) -> bool:
    """A listing stage that descends into folders: find/fd (unless -maxdepth 0|1), Get-ChildItem -Recurse/-Depth,
    ls -R. Fed to a delete, such a list names every file under a client folder it starts from."""
    e = norm_exe(argv[0])
    low = [a.lower() for a in argv[1:]]
    if e in ("find", "fd"):
        return not any(a in ("-maxdepth", "--max-depth", "-d") and i + 1 < len(low) and low[i + 1] in ("0", "1")
                       for i, a in enumerate(low))
    if e in ("gci", "get-childitem", "dir", "ls"):                # -r / -rec... (PowerShell), -R / -lR (ls)
        return any(len(a) > 1 and ("-recurse".startswith(a) or a == "-depth") for a in low) or \
            any(re.fullmatch(r"-[a-zA-Z]*R[a-zA-Z]*", a) for a in argv[1:])
    return False


def pipe_source(stages: list[tuple[list[str], Path]], cwd: Path, recursive: bool = False,
                marker: bool = False, deleting: bool = False) -> tuple[str, str] | None:
    """A client source named by an earlier stage of the pipeline (a read), or a working directory that is one.
    recursive=True (the consumer deletes/moves whole trees): also a listed folder that holds a client's sources
    (`Get-ChildItem | Remove-Item -Recurse`, `ls | xargs rm -rf` in the client folder). marker=True (the consumer
    deletes, moves or changes what it gets): also an unnarrowed listing of a client folder, which names its
    .whynot-client (`find . -maxdepth 1 | xargs rm`)."""
    views = [(argv, at) + stage_paths(argv, at) for argv, at in stages]
    narrowed = any(v[3] for v in views)                          # `find . -name '*.tmp' | xargs rm -rf` is fine
    recursive = (recursive or any(lists_tree(argv) for argv, _ in stages)) and not narrowed
    # a deleting consumer: -File still lists .whynot-client, so only a name/path filter or a grep stage spares it
    # (an -Exclude that matches the marker too; other root files such as START_HERE.md may go, by design)
    if marker and (not narrowed or deleting and not any(stage_paths(a_, t_, file_narrows=False)[1]
                                                        for a_, t_ in stages)):
        for argv, at, args, _ in views:
            if norm_exe(argv[0]) not in LISTERS or excludes_marker(argv):
                continue
            for t in [a for a in args if not a.startswith("-") and a.lower() not in PS_PATH_PARAMS] or ["."]:
                for lp in paths_of(t, at):
                    lp = loose_resolve(lp)
                    if (lp / client_marker.MARKER).is_file() and is_client(lp):
                        return f"{lp.name}/{client_marker.MARKER}", t
    for argv, at, args, _ in views:
        for a in args:
            hit = protected(a, at, writing=False, recursive=recursive)
            if hit:
                return hit, a
        if recursive and norm_exe(argv[0]) in LISTERS and not [a for a in args if not a.startswith("-")]:
            hit = holds_sources(at)
            if hit:
                return hit, "."
    hit = hit_of(cwd)
    return (hit, ".") if hit else None


def piped_text(prev: list[str]) -> str | None:
    """The text an `echo|printf|Write-Output ... |` stage (or a bare PowerShell string) sends down the pipe."""
    e = norm_exe(prev[0])
    if e in ("echo", "printf", "write-output", "write-host", "echo.", "cat") and len(prev) > 1:
        return " ".join(a for a in prev[1:] if not a.startswith("-"))
    if len(prev) == 1 and " " in prev[0]:
        return prev[0]
    return None


def stdin_shell(argv: list[str]) -> str | None:
    """'sh'|'ps'|'cmd' when this stage runs the commands it reads on stdin (`| bash`, `| powershell -Command -`,
    `| iex`, `| cmd`)."""
    e = norm_exe(argv[0])
    if e in SHELLS and all(a.startswith("-") and not re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*", a) for a in argv[1:]):
        return "sh"
    if e in PWSH:
        body = shell_body(e, argv)
        return "ps" if body is None or body[1].strip() in ("", "-") else None
    if e in ("invoke-expression", "iex") and not [a for a in argv[1:] if a.lower() != "-command"]:
        return "ps"
    if e == "cmd" and shell_body(e, argv) is None:
        return "cmd"
    return None


# --------------------------------------------------------------------------- Bash
def split_commands(cmd: str, escapes: bool = True) -> list[tuple[list[str], bool]]:
    """Simple commands, each with `piped` = it reads the previous command's output (`a | b`). escapes=False keeps
    backslashes (Windows paths typed without quotes)."""
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|<>")
        lex.whitespace_split = True
        lex.commenters = ""                 # comments were removed per line (shell_lines): `a#b`, `${#x}` are words
        if not escapes:
            lex.escape = ""
        toks = list(lex)
    except ValueError:
        toks = cmd.split()
    out, cur, piped = [], [], False
    for t in toks:
        if t in SEPARATORS:
            if cur:
                out.append((cur, piped))
            cur, piped = [], t == "|"
        else:
            cur.append(t)
    if cur:
        out.append((cur, piped))
    return out


_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def scan_sh_line(line: str, q: str | None = None, after: str = "") -> tuple[str, str | None, list[int], bool]:
    """One physical line -> (the line without its `# comment`, the quote still open at its end, where `<<` stands
    outside quotes, whether a comment was cut). `#` starts a comment only at the start of a word outside quotes (not
    in `a#b`, `${#x}`, `$#`, '#...', "#..." or $'#...'); `q` is the quote a previous line left open (a multi-line
    string): "'", '"' or "$'" (ANSI-C quoting, where \\' does not close it; `\\$'` and `$$'` open a plain quote).
    `after` is the character this line is glued to by a `\\`-newline continuation (T2.19: `ls output\\` + `#; rm`
    is `ls output#; rm`, no comment). `<<` inside `$(( ))` / `(( ))` is a shift, not a heredoc (T2.19)."""
    i, n, heredocs, parens = 0, len(line), [], []      # parens: "A" for an open (( / $(( , "(" otherwise
    while i < n:
        c = line[i]
        if q == "'":
            if c == "'":
                q = None
        elif q in ('"', "$'"):
            if c == "\\":
                i += 1
            elif c == q[-1]:
                q = None
        elif c == "\\":
            i += 1
        elif line.startswith("$$", i):
            i += 1
        elif line.startswith("$'", i):
            q = "$'"
            i += 1
        elif c in "'\"":
            q = c
        elif c == "#" and (line[i - 1] if i else after[-1:]) in ("", *" \t;&|()<>"):
            return line[:i], None, heredocs, True
        elif line.startswith("$((", i) or (line.startswith("((", i) and (i == 0 or line[i - 1] in " \t;&|(")):
            parens.append("A")
            i += 2 if c == "$" else 1
        elif c == "(":
            parens.append("(")
        elif c == ")" and parens:
            if parens.pop() == "A" and line.startswith("))", i):
                i += 1
        elif line.startswith("<<", i) and not line.startswith("<<<", i):
            if "A" not in parens:
                heredocs.append(i)
            i += 1
        i += 1
    return line, q, heredocs, False


def shell_lines(cmd: str) -> tuple[str, list[tuple[str, str]]]:
    """Drop heredoc BODIES (they are data such as a script's text, not shell commands) and make each line its own
    command (newlines separate commands in a shell; shlex would otherwise glue lines together). Returns the command
    text and [(line that opened the heredoc, body)] so a body fed to a shell can be checked as commands.
    Each physical line loses its comment first (C1); only then does a trailing backslash join the next line, so a
    comment that ends in `\\` never continues (bash runs the next line). `<<` inside quotes opens no heredoc.
    A `\\` before CRLF escapes the CR, not the newline: no continuation (T2.19)."""
    out, delim, docs, body, opener, q, join = [], None, [], [], "", None, False
    for raw in cmd.split("\n"):
        if delim is not None:
            if raw.strip() == delim:
                docs.append((opener, "\n".join(body)))
                delim, body = None, []
            else:
                body.append(raw)
            continue
        inside = q is not None                   # this line continues a quoted string: keep its newline
        code, q, heredocs, commented = scan_sh_line(raw.rstrip("\r"), q, out[-1] if join and out else "")
        cont = not commented and q not in ("'",) and (len(code) - len(code.rstrip("\\"))) % 2 == 1
        if cont:
            code = code[:-1]                     # `\` + newline: the next line continues this one ...
            cont = not raw.endswith("\r")        # ... `\` + CRLF: an escaped CR (dropped), the LF still ends it
        for k in heredocs:
            m = _HEREDOC.match(code, k)
            if m:
                delim, opener = m.group(2), code
                break
        if (join or inside) and out:
            out[-1] += ("" if join else "\n") + code
        else:
            out.append(code)
        join = cont
    if delim is not None:
        docs.append((opener, "\n".join(body)))
    return " ; ".join(out), docs


def shell_kind(name: str) -> str | None:
    return "sh" if name in SHELLS else "ps" if name in PWSH else "cmd" if name == "cmd" else None


def check_text(kind: str, text: str, cwd: Path, agent: str | None):
    if kind == "sh":
        check_bash(text, cwd, agent)
    elif kind == "ps":
        check_powershell(text, cwd, agent)
    else:
        CMD_CWD.append(cwd)
        try:
            check_powershell(cmd_to_ps(text), cwd, agent)
        finally:
            CMD_CWD.pop()


def substitutions(cmd: str, backticks: bool = True) -> list[str]:
    """Bodies of $( ... ), <( ... ), >( ... ) and `...` (they run as commands, also inside double quotes; not
    inside single quotes). PowerShell (backticks=False) has $( ... ) only: its backtick is an escape."""
    out, i, q, n = [], 0, None, len(cmd)
    while i < n:
        c = cmd[i]
        if q == "'":
            if c == "'":
                q = None
        elif c == "\\" and backticks:
            i += 1
        elif c == "'" and q is None:
            q = "'"
        elif c == '"':
            q = None if q == '"' else '"'
        elif c == "`" and backticks:
            j = cmd.find("`", i + 1)
            if j < 0:
                break
            out.append(cmd[i + 1:j])
            i = j
        elif c in "$<>" and cmd.startswith("(", i + 1) and not cmd.startswith("((", i + 1):
            depth, j = 1, i + 2
            while j < n and depth:
                depth += {"(": 1, ")": -1}.get(cmd[j], 0)
                j += 1
            out.append(cmd[i + 2:j - 1] if not depth else cmd[i + 2:])
            i = j - 1
        i += 1
    return out


_DOTNET = re.compile(r"\[(?:System\.)?IO\.(File|Directory)\]::(\w+)\s*\(", re.I)
DOTNET_WRITE = {
    "file": {"delete", "move", "copy", "replace", "writealltext", "writeallbytes", "writealllines", "appendalltext",
             "appendalllines", "create", "createtext", "appendtext", "openwrite", "setattributes", "encrypt",
             "decrypt", "setaccesscontrol", "setcreationtime", "setcreationtimeutc", "setlastwritetime",
             "setlastwritetimeutc", "setlastaccesstime", "setlastaccesstimeutc", "createsymboliclink"},
    "directory": {"delete", "move", "createdirectory", "setaccesscontrol", "setcreationtime", "setcreationtimeutc",
                  "setlastwritetime", "setlastwritetimeutc", "setlastaccesstime", "setlastaccesstimeutc",
                  "createsymboliclink"}}


DOTNET_PATH_ARGS = {"copy": (1,), "move": (0, 1), "replace": (0, 1, 2)}       # else the first argument


def split_args(inner: str) -> list[str]:
    """Top-level comma split of a method's argument list (brackets and quotes respected)."""
    args, cur, depth, q = [], "", 0, None
    for c in inner:
        if q:
            q = None if c == q else q
        elif c in "'\"":
            q = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            args.append(cur.strip())
            cur = ""
            continue
        cur += c
    if cur.strip():
        args.append(cur.strip())
    return args


def arg_paths(arg: str, destructive: bool = False) -> list[str]:
    """Paths one .NET argument may name: a literal; for (Join-Path $PWD 'a' 'b') / [IO.Path]::Combine('a','b') / 'a' +
    'b' the joined literals; every literal on its own too; a $variable (checked for taint). destructive (Delete, Move,
    Replace) with an unknown $base: also a literal that is a path of several segments ('data/Raw/x.mp4'), read from
    the working folder (T11); single names (Combine($out, 'data', 'x.json')) stay the base's."""
    lits = [b for _, b in re.findall(r"(['\"])(.*?)\1", arg)]
    if len(lits) == 1 and re.fullmatch(r"(['\"]).*\1", arg):
        return lits
    m = re.search(r"join-path\s+(\(get-location\)|\S+)|::combine\(\s*([^,]+?)\s*,", arg, re.I)
    if m or (lits and "+" in arg):               # a joined path: judge the whole path, not its pieces
        first = (m.group(1) or m.group(2) or "") if m else arg.lstrip("( ").split("+")[0].strip()
        if first.startswith("$") and not re.match(r"^\$(pwd\b|\{pwd\}|\(\s*(pwd|get-location)\s*\))", first, re.I):
            # an unknown base: only a tainted variable counts, or (delete/move) a multi-segment source literal
            return [first] + ([x for x in lits if re.search(r"[\\/]", x.strip("\\/"))] if destructive else [])
        return ["/".join(lits) if m else "".join(lits)]
    out = list(lits)
    if arg.lstrip("(").startswith("$"):
        out.append(arg.lstrip("("))
    return out


def dotnet_writes(text: str) -> list[list[str]]:
    """Path arguments of every [IO.File]:: / [System.IO.Directory]:: call that writes, moves or deletes (Copy: only the
    destination; WriteAllText: only the file, not the content). A call naming nothing checkable gives ['']."""
    out = []
    for m in _DOTNET.finditer(text):
        kind, meth = m.group(1).lower(), m.group(2).lower()
        if meth not in DOTNET_WRITE[kind]:
            continue
        depth, j = 1, m.end()
        while j < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[j], 0)
            j += 1
        args = split_args(text[m.end():j - 1])
        paths = [x for i in DOTNET_PATH_ARGS.get(meth, (0,)) if i < len(args)
                 for x in arg_paths(args[i], meth in ("delete", "move", "replace"))]
        out.append(paths or [""])
    return out


def check_dotnet(text: str, cwd: Path):
    for args in dotnet_writes(text):
        for a in args:
            hit = protected(a, cwd, recursive=True)
            if hit:
                block(f"a .NET file call on the client's source folder ({hit}) is not allowed — assets/ and data/ "
                      f"are read-only.")


def adobe_pref_change(argv: list[str], reg_loc: str = "") -> bool:
    """Writing Adobe's CEP preferences (PlayerDebugMode lets unsigned panels load). The editor does that, never Claude."""
    exe = norm_exe(argv[0]) if argv else ""
    low = (reg_loc + "\\" + " ".join(argv)).lower().replace("/", "\\")
    csxs = "adobe\\csxs" in low or ("\\adobe" in reg_loc.lower().replace("/", "\\") and "csxs" in low)
    if exe == "defaults" and len(argv) > 2 and argv[1] in ("write", "delete") and "com.adobe.csxs" in argv[2].lower():
        return True
    if exe == "reg" and len(argv) > 1 and argv[1].lower().lstrip("/") in ("add", "delete", "import") and csxs:
        return True
    if exe in ("set-itemproperty", "sp", "new-itemproperty", "new-item", "ni", "remove-itemproperty", "rp") and csxs:
        return True
    return False


def strip_prefixes(argv: list[str]) -> list[str]:
    """Drop env assignments, shell keywords (then/do/if...), group brackets and wrapper commands that run the rest of
    the line (sudo, time, timeout 60, nice -n 5, env -i, nohup, command, exec, stdbuf, ionice)."""
    argv = list(argv)
    while argv:
        a = argv[0]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", a) or a in SHELL_KEYWORDS:
            argv = argv[1:]
            continue
        w = norm_exe(a)
        if w in WRAPPERS:
            argv = argv[1:]
            while argv and argv[0].startswith("-"):
                argv = argv[2:] if argv[0] in WRAPPERS[w] else argv[1:]
            if w in ("timeout", "flock") and argv:
                argv = argv[1:]                       # the duration / the lock file
            continue
        break
    if argv and argv[0][:1] in ("(", "{") and len(argv[0]) > 1:
        argv[0] = argv[0].lstrip("({")
    while argv and argv[-1] in (")", "}", "))"):
        argv = argv[:-1]
    return argv


def xargs_parse(argv: list[str]) -> tuple[list[str], str | None]:
    """`xargs [options] cmd args...` -> ([cmd, args...], replace-string of -I/-i/--replace or None)."""
    i, rep = 1, None
    while i < len(argv) and argv[i].startswith("-"):
        a = argv[i]
        if a == "-I" and i + 1 < len(argv):
            rep, i = argv[i + 1], i + 2
            continue
        if a.startswith("-I"):
            rep = a[2:]
        elif a.startswith("-i") or a.startswith("--replace"):
            rep = (a.split("=", 1)[1] if "=" in a else a[2:] if a.startswith("-i") else "") or "{}"
        i += 2 if a in XARGS_VALUE_OPTS else 1
    return argv[i:], rep


def body_mutates(kind: str, text: str) -> bool:
    if kind != "sh":
        return True
    return any(norm_exe(strip_prefixes(a)[0]) in MUTATE_ALL for a, _ in split_commands(text) if strip_prefixes(a))


def check_xargs_stage(argv: list[str], src: tuple[str, str], cwd: Path, agent: str | None):
    """`... | xargs CMD`: CMD acts on the paths read from the pipe (a client source here)."""
    sub, rep = xargs_parse(argv)
    sub = strip_prefixes(sub)
    if not sub:
        return
    msg = f"`xargs {sub[0]}` would change files listed from the client's source folder ({src[0]}). " \
          f"assets/ and data/ are read-only."
    if rep:                                 # -I{}: the piped name lands where {} is
        check_argv([t.replace(rep, src[1]) for t in sub], cwd, agent)
        return
    name = norm_exe(sub[0])
    body = shell_body(name, sub)
    if name in MUTATE_ALL or (name in ("sed", "perl") and any(a.startswith("-i") for a in sub[1:])) or \
            (body and body_mutates(*body)):
        block(msg)


def check_bash(cmd: str, cwd: Path, agent: str | None):
    text, docs = shell_lines(cmd)           # heredoc bodies are data, not commands ...
    for opener, body in docs:               # ... unless a shell reads them: `bash <<'EOF'`, `cat <<EOF | sh`
        kind = next((shell_kind(norm_exe(t)) for t in re.split(r"[\s|;&]+", opener.split("<<")[0] + " " +
                                                                 opener.split("<<")[-1]) if shell_kind(norm_exe(t))), None)
        if kind:
            check_text(kind, body, cwd, agent)
    for body in substitutions(text):
        check_bash(body, cwd, agent)
    check_dotnet(text, cwd)
    run_bash(split_commands(text), cwd, agent)
    if "\\" in text:                         # `cmd /c del data\Raw\a.mp4` unquoted: also read backslashes as written
        run_bash(split_commands(text, escapes=False), cwd, agent)


def run_bash(stmts: list[tuple[list[str], bool]], cwd: Path, agent: str | None):
    stages = []                                 # earlier stages of the current pipeline: (argv, cwd)
    for argv, piped in stmts:
        if argv and argv[0] == "for" and len(argv) > 3 and argv[2] == "in":     # for f in data/Raw/*; do ...
            src = first_source(argv[3:], cwd)
            if src:
                TAINT[argv[1].lower()] = src
                SH_VARS.add(argv[1].lower())
            continue
        decl = argv[0] in ("export", "declare", "readonly", "local", "typeset")
        words = [a for a in argv[1:] if not a.startswith("-")] if decl else argv
        for k, a in enumerate(words):                                        # f=data/Raw/a.mp4; rm "$f"
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", a)
            if not m:
                break
            vals = [m.group(2)]
            if m.group(2).startswith("("):                                    # a=(data assets)
                vals = [m.group(2)[1:]] + words[k + 1:]
                vals = [v.rstrip(")") for v in vals[:next((n + 1 for n, v in enumerate(vals) if v.endswith(")")),
                                                          len(vals))]]
            src = first_source(vals, cwd)
            if src:
                TAINT[m.group(1).lower()] = src
                SH_VARS.add(m.group(1).lower())
        if decl:
            continue
        argv = strip_prefixes(argv)
        if not argv:
            continue
        stages = stages if piped else []
        kind = stdin_shell(argv) if piped and stages else None
        if kind:                                                             # echo "rm -rf data" | bash
            text = piped_text(stages[-1][0])
            if text:
                check_text(kind, text, cwd, agent)
        if piped and norm_exe(argv[0]) == "xargs":
            sub = strip_prefixes(xargs_parse(argv)[0])
            tree = bool(sub) and (norm_exe(sub[0]) == "mv" or norm_exe(sub[0]) == "rm" and
                                  any(a.startswith("-") and "r" in a.lower() for a in sub[1:]))
            src = pipe_source(stages, cwd, recursive=tree, marker=True,
                              deleting=bool(sub) and norm_exe(sub[0]) in ("rm", "unlink", "shred", "srm", "mv"))
            if src:
                check_xargs_stage(argv, src, cwd, agent)
        stages.append((argv, cwd))
        cwd = check_argv(argv, cwd, agent)


_PS_VALUE_OPTS = {"-executionpolicy", "-ep", "-ex", "-windowstyle", "-w", "-workingdirectory", "-wd",
                  "-configurationname", "-outputformat", "-of", "-inputformat", "-if", "-psconsolefile", "-version",
                  "-v", "-settingsfile", "-custompipename"}


def shell_body(exe: str, argv: list[str]) -> tuple[str, str] | None:
    """('ps'|'sh'|'cmd', command text) for `cmd /c|//c ...`, `powershell|pwsh -Command ...|-EncodedCommand ...`,
    `bash|sh|zsh -c ...` and `bash <<< "..."`: the command the wrapper will run (checked like a command of its own)."""
    if exe == "cmd":
        for i, a in enumerate(argv[1:], 1):
            m = re.match(r"^/{1,2}([ckr])(.*)$", a, re.I | re.S)
            if m:                            # /c, //c (Git Bash), /cdel (no space)
                rest = ([m.group(2)] if m.group(2) else []) + argv[i + 1:]
                # `cmd /c "reg add ..."`: one quoted argument is the whole command
                return "cmd", rest[0] if len(rest) == 1 else " ".join(f'"{t}"' if re.search(r"\s", t) else t
                                                                      for t in rest)
        return None
    if exe in PWSH:
        i = 1
        while i < len(argv):
            a = argv[i].lower()
            if len(a) > 1 and "-command".startswith(a):
                return "ps", " ".join(argv[i + 1:])
            if a in ("-e", "-ec") or (len(a) > 2 and "-encodedcommand".startswith(a)):
                try:
                    return "ps", base64.b64decode(argv[i + 1]).decode("utf-16-le")
                except Exception:
                    return None
            if len(a) > 1 and "-file".startswith(a):
                return None
            if a in _PS_VALUE_OPTS:
                i += 2
                continue
            if a.startswith("-"):
                i += 1
                continue
            return "ps", " ".join(argv[i:])
        return None
    if exe in SHELLS:
        for i, a in enumerate(argv[1:-1], 1):
            if re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*", a):
                return "sh", argv[i + 1]
            if a == "<<<":
                return "sh", argv[i + 1]
    return None


_CMD_IF = re.compile(r"^if\s+(?:/i\s+)?(?:not\s+)?(?:(?:exist|defined|errorlevel)\s+(?:\"[^\"]*\"|\S+)|"
                     r"\S+\s*==\s*\S+|\S+\s+(?:equ|neq|lss|leq|gtr|geq)\s+\S+)\s+(.*)$", re.I | re.S)
_CMD_FOR = re.compile(r"^for\s+(?:/[dlrf]\s+(?:\"([^\"]*)\"\s+|(?!%)(\S+)\s+)?)?%%?(\w)\s+in\s+\((.*?)\)\s+do\s+(.*)$",
                      re.I | re.S)


def cmd_to_ps(body: str) -> str:
    """cmd.exe syntax -> statements the PowerShell checker reads: & && || -> ;, | stays a pipe, ^ escapes,
    `if exist X CMD` / `if A==B CMD` -> CMD, `for %f in (SET) do CMD` -> CMD with %f set from SET, ( ) groups opened."""
    segs, cur, q, i = [], [], False, 0
    while i < len(body):
        c = body[i]
        if c == '"':
            q = not q
            cur.append(c)
        elif not q and c == "^" and i + 1 < len(body):
            cur.append(body[i + 1])
            i += 1
        elif not q and (body.startswith(("&&", "||"), i) or c == "&"):
            segs.append("".join(cur))
            cur = []
            i += 1 if body.startswith(("&&", "||"), i) else 0
        elif not q and c == "|":
            cur.append(" | ")
        else:
            cur.append(c)
        i += 1
    segs.append("".join(cur))
    out = []
    for seg in segs:
        seg = seg.strip().strip("()").strip().lstrip("@")
        while True:
            m = _CMD_IF.match(seg)
            if m:
                seg = m.group(1).strip().strip("()").strip()
                continue
            m = _CMD_FOR.match(seg)
            if m:
                root = m.group(1) or m.group(2)               # for /r ROOT %f in (SET): files under ROOT
                items = [t.strip('"') for t in m.group(4).split()]
                found = first_source(([root] if root else []) + items, Path.cwd() if not CMD_CWD else CMD_CWD[-1])
                if found:
                    TAINT[m.group(3).lower()] = found
                    SH_VARS.add(m.group(3).lower())
                seg = m.group(5).strip().strip("()").strip()
                continue
            break
        if re.match(r"^call\s", seg, re.I):
            seg = seg[5:]
        out.append(seg)
    return " ; ".join(out)


def check_git(argv: list[str], cwd: Path):
    """git checkout/reset/clean/rm/mv/restore/stash on a client's sources (via -C, --work-tree or a path argument)."""
    base, i = cwd, 1
    while i < len(argv) and argv[i].startswith("-"):
        a = argv[i]
        if a in ("-C", "--work-tree") and i + 1 < len(argv):
            t = Path(native(expand(argv[i + 1].strip("'\""), cwd))).expanduser()
            base = t if t.is_absolute() else base / t
            i += 2
            continue
        if a.startswith("--work-tree="):
            t = Path(native(a.split("=", 1)[1])).expanduser()
            base = t if t.is_absolute() else base / t
        i += 2 if a in ("-c", "--git-dir", "--namespace") else 1
    if i >= len(argv) or argv[i] not in GIT_MUTATE:
        return
    sub, rest = argv[i], argv[i + 1:]
    if sub == "rm" and "--cached" in rest:          # only untracks; the files stay
        return
    if sub == "stash" and rest and rest[0] in ("list", "show"):
        return
    hit = hit_of(base)
    paths = [a for a in rest if not a.startswith("-")] if sub != "stash" else []
    whole = sub in ("clean", "stash") or (sub == "reset" and any(a in ("--hard", "--merge", "--keep") for a in rest)) or \
        (sub in ("checkout", "restore") and ("." in paths or "-f" in rest or "--force" in rest))
    root = Path(os.path.abspath(base))
    if not hit and whole and is_client(root):
        hit = f"{root.name}/assets+data"
    for a in paths:
        hit = hit or protected(a, base)
    if hit:
        block(f"`git {sub}` would change the client's source folder ({hit}). assets/ and data/ are read-only.")


def check_argv(argv: list[str], cwd: Path, agent: str | None) -> Path:
    """Checks one simple command; returns the working directory for the next one (follows cd)."""
    argv = strip_prefixes(argv)
    if not argv:
        return cwd
    if adobe_pref_change(argv):
        block("Adobe preferences (PlayerDebugMode) are the editor's to change. Give them the command to run themselves.")
    exe = norm_exe(argv[0])
    body = shell_body(exe, argv)
    if body:                            # the command a wrapper shell runs gets the same checks
        check_text(body[0], body[1], cwd, agent)
        return cwd
    script = next((a for a in argv[1:] if not a.startswith("-")), None) if exe in SHELLS else None
    if script and norm_exe(script) == "reel":                     # bash [-e] "$CLAUDE_PLUGIN_ROOT/bin/reel" ...
        argv, exe = argv[argv.index(script):], "reel"
    if exe == "parallel" and ":::" in argv:                       # parallel rm ::: data/Raw/*
        i = argv.index(":::")
        cmd = [a for a in argv[1:i] if not a.startswith("-")]
        check_argv(cmd + [a for a in argv[i + 1:] if a != ":::"], cwd, agent)
        return cwd
    if exe == "eval":
        check_bash(" ".join(argv[1:]), cwd, agent)
        return cwd
    if exe == "xargs":
        check_argv(xargs_parse(argv)[0], cwd, agent)
        return cwd
    if exe == "git":
        check_git(argv, cwd)
    if exe in ("cd", "pushd"):          # later relative paths are relative to the cd target
        rest = [a for a in argv[1:] if a not in ("--", "-P", "-L", "-e", "-@")]
        if rest and rest[0] == "-":
            return cwd
        tgt = Path(native(expand(rest[0], cwd))).expanduser() if rest else Path.home()
        return tgt if tgt.is_absolute() else cwd / tgt
    # redirections anywhere: > target / >> target
    for i, t in enumerate(argv):
        if t in (">", ">>", ">|") and i + 1 < len(argv):
            hit = protected(argv[i + 1], cwd)
            if hit:
                block(f"writing into the client's source folder ({hit}) is not allowed. Outputs go to <client>/output/.")
    if exe in MUTATE_ALL or (exe in ("sed", "perl") and any(a.startswith("-i") for a in argv[1:])) or \
            (exe == "xattr" and any(a in ("-w", "-d", "-c", "-r") for a in argv[1:])):
        tree = exe in ("rmdir", "mv") or (exe == "rm" and any(a.startswith("-") and "r" in a.lower() for a in argv[1:]))
        last = len(argv) - 1 if exe == "mv" else None       # mv's destination may be a client folder
        for i, a in enumerate(argv[1:], 1):
            hit = protected(a, cwd, recursive=tree and i != last)
            if hit:
                block(f"`{exe}` on the client's source folder ({hit}) is not allowed — assets/ and data/ are read-only.")
    if exe == "rsync" and any(a.startswith(("--remove-source-files", "--remove-sent-files")) for a in argv[1:]):
        for a in [a for a in argv[1:] if not a.startswith("-")][:-1]:          # the sources are moved away
            hit = protected(a, cwd, recursive=True)
            if hit:
                block(f"`rsync --remove-source-files` would move files out of the client's source folder ({hit}).")
    if exe in MUTATE_DEST:
        paths = [a for a in argv[1:] if not a.startswith("-") and a not in (">", ">>")]
        if exe == "tee" or exe == "mkdir":
            cands = paths
        elif exe in ("cp", "ln", "install") and any(a in ("-t", "--target-directory") or
                                                    a.startswith("--target-directory=") for a in argv[1:]):
            # `cp -t DIR SRC...`: the destination is the -t value, every other path is a source (a read)
            cands = [argv[i + 1] if a in ("-t", "--target-directory") else a.split("=", 1)[1]
                     for i, a in enumerate(argv[:-1]) if a in ("-t", "--target-directory")
                     or a.startswith("--target-directory=")]
            cands += [a.split("=", 1)[1] for a in argv[-1:] if a.startswith("--target-directory=")]
        elif exe == "ffmpeg":
            # outputs are the positional args that are not an option's value (-i inputs, filter graphs and
            # other option values are reads), plus the few options that name a file ffmpeg writes
            cands, i = [], 1
            while i < len(argv):
                a = argv[i]
                if a.startswith("-") and a not in FFMPEG_FLAGS:
                    if a in FFMPEG_WRITE_OPTS and i + 1 < len(argv):
                        cands.append(argv[i + 1])
                    i += 2
                    continue
                if not a.startswith("-"):
                    cands.append(a)
                i += 1
        elif exe == "ln":
            cands = paths[-1:]
        elif exe in ("unzip",):
            cands = [argv[argv.index("-d") + 1]] if "-d" in argv[:-1] else []
        elif exe in ("tar",):
            cands = [argv[argv.index("-C") + 1]] if "-C" in argv[:-1] else []
        elif exe in ("curl", "wget"):
            cands = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a in ("-o", "-O", "--output")]
        else:
            cands = paths[-1:]
        for c in cands:
            dest = protected(c, cwd)
            if dest:
                block(f"`{exe}` would write into the client's source folder ({dest}). Write to <client>/output/ instead.")
    if exe == "find":
        # start paths come before the first expression token; -delete or -exec rm/mv/... mutate everything found
        starts = find_starts(argv)
        execs = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a in ("-exec", "-execdir", "-ok", "-okdir")]
        if "-delete" in argv or any(norm_exe(e) in MUTATE_ALL for e in execs):
            # as `find ... | xargs rm`: a predicate that spares the client's files narrows it (T11)
            narrowed = find_narrowed(argv, cwd)
            for a in starts or ["."]:
                hit = protected(a, cwd, recursive=not narrowed)
                if hit:
                    block(f"`find` that deletes or changes files in the client's source folder ({hit}) is not allowed.")
        for i, a in enumerate(argv[:-1]):
            if a in FIND_WRITE_ACTIONS:
                hit = protected(argv[i + 1], cwd)
                if hit:
                    block(f"`find {a}` would write into the client's source folder ({hit}).")
    if exe == "rm" and any(a.startswith("-") and "r" in a.lower() for a in argv[1:]):
        for a in argv[1:]:
            if a.startswith("-"):
                continue
            p = Path(native(expand(a.strip("'\""), cwd)))
            p = p if p.is_absolute() else cwd / p
            parts = p.parts
            if p.name == "output" and is_client(Path(os.path.abspath(p.parent))):
                block("deleting a client's whole output/ folder is not allowed — ask the editor to do it.")
            croot = Path(os.path.abspath(p.parent.parent))
            if p.name == "client_database" and p.parent.name == "output" and is_client(croot) and \
                    not (croot / client_marker.MARKER).is_file():
                block("output/client_database is what marks this client folder (it has no .whynot-client): deleting it "
                      "would switch off the guard. Run `reel doctor --fix` first, then ask the editor.")
            if len(parts) >= 3 and parts[-2] == "projects" and parts[-3] == "output" and \
                    is_client(Path(os.path.abspath(p.parent.parent.parent))):
                block(f"deleting the whole project folder {p.name} is not allowed — ask the editor to do it.")
    # engine-level rules
    check_reel(exe, argv, agent)
    return cwd


def own_role(agent: str | None) -> str | None:
    """This plugin's agent name (`whynot-cut:qc-reviewer` -> `qc-reviewer`); another plugin's agent -> None."""
    return agent[len(PLUGIN_AGENT):] if agent and agent.startswith(PLUGIN_AGENT) else None


def opt_value(argv: list[str], name: str) -> str | None:
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def check_reel(exe: str, argv: list[str], agent: str | None):
    # `python -B .../engine/reel/cli.py ...` / `py -3 .../cli.py` (interpreter flags before the script) is `reel`
    is_reel = exe == "reel" or ((exe.startswith("python") or exe == "py") and
                                any(a.strip("'\"").replace("\\", "/").endswith("engine/reel/cli.py") for a in argv[1:4]))
    if is_reel:
        sub = next((a for a in argv[1:] if not a.startswith("-") and not a.endswith("cli.py")
                    and argv[argv.index(a) - 1] not in GLOBAL_VALUE_OPTS), None)
        if sub in EXTRAS and "--extras" not in argv:
            block(f"`reel {sub}` is an optional After Effects/Photoshop extra. The pipeline is Premiere-only "
                  f"unless the editor explicitly asked for AE/PS; then add --extras.")
        role = own_role(agent)
        if agent:                       # gate rules: every subagent, whatever plugin it comes from
            if sub == "approve-plan":
                block("only the lead editor (main conversation) records plan approval, after the editor approves.")
            if sub == "lock" and "--release" in argv:
                block("only the lead editor releases the client's writer lock (`reel lock --release`), when the editor "
                      "says the other session is finished. Report the lock instead.")
            if sub == "reels-select":
                block("only the lead editor records which reels the editor picked (Gate 0), from the editor's own "
                      "message. Report the candidates instead.")
            if sub == "settings" and "--init" in argv:
                block("only the lead editor changes the editor's preferences (e.g. approval mode), when the editor asks.")
            if sub == "verify" and "--record" in argv:
                block("subagents report a verdict; the lead editor records it after viewing the evidence itself.")
            if sub == "transcript-verify" and (opt_value(argv, "--by") or "").strip("'\"").lower() == "editor":
                block("only the lead editor records `transcript-verify --by editor`, after the editor confirmed the "
                      "words. Report the corrections instead.")
            if role == "qc-reviewer" and sub == "ref-style" and ("--record" in argv or "--apply" in argv):
                block("qc-reviewer is independent and read-only: it may not record or apply the client reference style.")
            if sub == "ae-probe" and "--record" in argv:
                block("only the lead editor records the After Effects probe verdict, after viewing the probe frames itself.")
            if role == "qc-reviewer" and sub in QC_FORBIDDEN:
                block(f"qc-reviewer is independent and read-only: it may not run `reel {sub}`. Report the issue instead.")
            if role == "setup-doctor" and (sub in SETUP_DOCTOR_FORBIDDEN or (sub == "doctor" and "--fix" in argv)):
                block(f"setup-doctor diagnoses without changing anything: it may not run `reel {sub}`. Give the lead "
                      f"the exact fix instead.")


# --------------------------------------------------------------------------- PowerShell (Windows)
PS_MUTATE_ANY = {  # every path argument of these is written, moved or deleted
    "remove-item", "rm", "del", "erase", "rd", "rmdir", "ri", "clear-content", "clc", "clear-item", "cli",
    "new-item", "ni", "mkdir", "md", "rename-item", "ren", "rni", "move-item", "mv", "move", "mi",
    "set-itemproperty", "sp", "set-acl", "compress-archive", "remove-itemproperty", "rp", "new-itemproperty"}
PS_TREE = {"remove-item", "rm", "del", "erase", "rd", "rmdir", "ri", "rename-item", "ren", "rni", "move-item", "mv",
           "move", "mi"}                                         # whole folders go with them
PS_DELETE = {"remove-item", "rm", "del", "erase", "rd", "rmdir", "ri", "move-item", "mv", "move", "mi"}
PS_CONTENT_WRITERS = {"set-content", "sc", "add-content", "ac", "out-file", "tee-object", "tee", "export-csv"}
PS_PIPE_MUTATE = {  # take the paths they act on from the pipeline (Get-ChildItem data | Remove-Item)
    "remove-item", "rm", "del", "erase", "rd", "rmdir", "ri", "rename-item", "ren", "rni", "move-item", "mv", "move",
    "mi", "clear-content", "clc", "clear-item", "cli", "set-content", "sc", "add-content", "ac", "set-itemproperty",
    "sp", "remove-itemproperty", "rp", "new-itemproperty", "set-acl"}
PS_PATH_PARAMS = {"-path", "-literalpath", "-lp", "-pspath", "-filepath"}
_PS_METHOD_WRITE = re.compile(r"\.(delete|moveto|replace|encrypt|decrypt|create|createtext|appendtext|openwrite|"
                              r"writealltext|setaccesscontrol)\s*\(", re.I)
PS_COPY = {"copy-item", "cp", "copy", "cpi"}                      # only the destination is written
PS_DEST_PARAMS = {"-destination", "-destinationpath", "-outfile", "-filepath", "-literalpath", "-path"}
PS_CD = {"set-location", "cd", "sl", "chdir", "push-location", "pushd"}
PS_KEYWORDS = {"try", "catch", "finally", "else", "elseif", "do", "begin", "process", "end", "&", "."}
_REG_LOC = re.compile(r"^(?:HK\w+:|Registry::)", re.I)


def ps_tokens(cmd: str) -> list[tuple[list[str], bool]]:
    """Split a PowerShell command line into simple commands (quote-aware; backtick escapes; > redirects), each with
    `piped` = it reads the previous command's output (`a | b`). Script-block braces come out as their own
    statements ["{"] / ["}"]; `${name}` stays one token."""
    stmts, cur, tok, q, i, piped = [], [], "", None, 0, False

    def push_tok():
        nonlocal tok
        if tok:
            cur.append(tok)
            tok = ""

    def end_stmt(next_piped=False):
        nonlocal cur, piped
        push_tok()
        if cur:
            stmts.append((cur, piped))
        cur, piped = [], next_piped

    while i < len(cmd):
        c = cmd[i]
        if q:
            if c == q:
                q = None
            elif c == "`" and q == '"' and i + 1 < len(cmd):
                tok += cmd[i + 1]
                i += 1
            else:
                tok += c
        elif tok == "" and c == "#":                 # C1: `# comment` to the end of the line (an apostrophe in it
            j = cmd.find("\n", i)                    # never opens a quote that hides the next lines)
            i = (len(cmd) if j < 0 else j) - 1
        elif tok == "" and cmd.startswith("<#", i):  # <# block comment #>
            j = cmd.find("#>", i + 2)
            i = (len(cmd) if j < 0 else j + 2) - 1
        elif tok == "" and re.match(r"@(['\"])[ \t]*\r?\n", cmd[i:]):    # @' here-string '@ : one string token
            qc = cmd[i + 1]
            start = cmd.index("\n", i) + 1
            j = cmd.find(f"\n{qc}@", start - 1)
            tok += cmd[start:j if j >= 0 else len(cmd)]
            push_tok()
            i = (len(cmd) if j < 0 else j + 3) - 1
        elif c in "'\"":
            q = c
        elif c == "`" and i + 1 < len(cmd):
            tok += cmd[i + 1] if cmd[i + 1] not in "\r\n" else ""
            i += 1
        elif c == "{" and tok.endswith("$"):
            j = cmd.find("}", i)
            j = len(cmd) - 1 if j < 0 else j
            tok += cmd[i:j + 1]
            i = j
        elif c in "{}":
            end_stmt()
            stmts.append(([c], False))
        elif c in " \t\r":
            push_tok()
        elif c in ";|\n" or cmd.startswith("&&", i):
            end_stmt(c == "|" and not cmd.startswith("||", i))
            if cmd.startswith(("&&", "||"), i):
                i += 1
        elif c == ">":
            push_tok()
            j = i
            while j + 1 < len(cmd) and cmd[j + 1] == ">":
                j += 1
            if tok == "" and cur and re.fullmatch(r"[0-9*]", cur[-1] or ""):
                cur.pop()                                   # 2> / *> stream number
            cur.append(">")
            i = j
        else:
            tok += c
        i += 1
    end_stmt()
    return stmts


def ps_path_args(args: list[str]) -> list[str]:
    """The path arguments of a content writer: -Path/-LiteralPath/-FilePath values, else the first positional."""
    named = [args[i + 1] for i, a in enumerate(args[:-1]) if a.lower() in PS_PATH_PARAMS]
    if named:
        return named
    pos = [a for i, a in enumerate(args) if not a.startswith("-") and (i == 0 or not args[i - 1].startswith("-"))]
    return pos[:1]


def ps_mutates_inputs(argv: list[str]) -> bool:
    """A pipeline stage that deletes, moves or writes the items piped into it (`| Remove-Item`, `| Set-Content` with
    no path of its own), or calls a writing method / [IO.File]:: on them."""
    name = argv[0].lower()
    if name in PS_CONTENT_WRITERS and ps_path_args(argv[1:]):
        return False                 # `... | Set-Content out.txt`: the piped text is the content, the path is its own
    text = " ".join(argv)
    return name in PS_PIPE_MUTATE or bool(_PS_METHOD_WRITE.search(text)) or bool(dotnet_writes(text))


def strip_filter_values(args: list[str]) -> list[str]:
    """-Filter/-Include/-Exclude and their values (patterns such as *data*, not paths) dropped (T11)."""
    out, skip = [], False
    for a in args:
        low = a.lower()
        if skip:
            skip = False
            continue
        if len(low) > 3 and any(p.startswith(low) for p in ("-filter", "-include", "-exclude")):
            skip = True
            continue
        out.append(a)
    return out


def check_powershell(cmd: str, cwd: Path, agent: str | None):
    cmd = cmd.replace("\r\n", "\n")              # T2.19: backtick + CRLF continues the line like backtick + LF
    for body in substitutions(cmd, backticks=False):
        check_powershell(body, cwd, agent)
    check_dotnet(cmd, cwd)
    stages, stack, reg_loc = [], [], ""          # current pipeline: (argv, cwd); saved state per open block
    for argv, piped in ps_tokens(cmd):
        if argv == ["{"]:                        # a block fed by a pipeline from a source: $_ is that source
            fed = stages and (len(stages) > 1 or stages[-1][0][0].lower().lstrip("(") in ("foreach", "for"))
            src = pipe_source(stages, cwd) if fed else None
            stack.append((stages, TAINT.get("_"), TAINT.get("psitem")))
            if src:
                TAINT["_"] = TAINT["psitem"] = src
            stages = []
            continue
        if argv == ["}"]:
            if stack:
                stages, u, p = stack.pop()
                for k, v in (("_", u), ("psitem", p)):
                    if v:
                        TAINT[k] = v
                    else:
                        TAINT.pop(k, None)
            continue
        while argv and argv[0].lower() in PS_KEYWORDS:
            argv = argv[1:]
        if not argv:
            continue
        m = re.match(r"^(foreach|for|while|if|elseif|switch)\((.*)$", argv[0], re.I | re.S)
        if m:                                                    # foreach($f in ...) without a space
            argv = [m.group(1), "(" + m.group(2)] + argv[1:]
        stages = stages if piped else []
        low0 = argv[0].lower().lstrip("(")
        if low0 in ("foreach", "for") and len(argv) > 3 and argv[2].lower() == "in":   # foreach ($f in <source>)
            src = first_source(argv[3:], cwd)
            if src:
                TAINT[argv[1].lstrip("($").lower()] = src
        if len(argv) > 2 and argv[0].startswith("$") and argv[1] in ("=", "+="):          # $f = Get-ChildItem data
            rhs, name = argv[2:], argv[0][1:].strip("{}").lower()
            cands = rhs + (["".join(t for t in rhs if t != "+")] if "+" in rhs else [])   # "da" + "ta"
            src = first_source(cands, cwd)
            if src:
                TAINT[name] = src
            VALUES[name] = " ".join(rhs).strip().strip("@").strip()
            argv = rhs
        kind = stdin_shell(argv) if piped and stages else None
        if kind:                                                 # "Remove-Item x" | iex, '...' | powershell -c -
            text = piped_text(stages[-1][0])
            if text:
                check_text(kind, text, cwd, agent)
        if piped and ps_mutates_inputs(argv):
            tree = argv[0].lower() in PS_TREE - {"remove-item", "rm", "del", "erase", "rd", "rmdir", "ri"} or any(
                len(a) > 1 and "-recurse".startswith(a.lower()) for a in argv[1:])
            src = pipe_source(stages, cwd, recursive=tree, marker=True, deleting=argv[0].lower() in PS_DELETE)
            if src:
                block(f"`{argv[0]}` would change items piped from the client's source folder ({src[0]}). "
                      f"assets/ and data/ are read-only.")
        stages.append((argv, cwd))
        text = " ".join(argv)
        for dargs in dotnet_writes(text):        # [IO.File]::Delete($_.FullName) inside a block
            for a in dargs:
                hit = protected(a, cwd, recursive=True)
                if hit:
                    block(f"a .NET file call on the client's source folder ({hit}) is not allowed — assets/ and "
                          f"data/ are read-only.")
        if _PS_METHOD_WRITE.search(text):        # (Get-Item data\x).Delete(), $f.MoveTo(...), [IO.FileInfo]::new(x)
            toks = [re.sub(r"\)?\.\w+\s*\(.*$", "", t.lstrip("(")) for t in argv]
            toks += [x.strip().strip("'\"") for x in re.findall(r"\(([^()]*)\)", text)]
            hit = next((h for h in (tainted(t, any_prop=True) for t in argv) if h), None)
            hit = hit[0] if hit else next((h for h in (protected(t, cwd, writing=False) for t in toks) if h), None)
            if hit:
                block(f"a file method call on the client's source folder ({hit}) is not allowed — assets/ and data/ "
                      f"are read-only.")
        argv[0] = argv[0].lstrip("(") or argv[0]
        if argv and argv[0] in ("&", "."):
            argv = argv[1:]
        if not argv:
            continue
        name = norm_exe(argv[0]) if not argv[0].lower().endswith(".ps1") else argv[0].lower()
        for i, t in enumerate(argv):
            if t == ">" and i + 1 < len(argv):
                hit = protected(argv[i + 1], cwd)
                if hit:
                    block(f"writing into the client's source folder ({hit}) is not allowed. Outputs go to <client>/output/.")
        args = strip_filter_values([a for a in argv[1:] if a != ">"])
        if adobe_pref_change([name] + args, reg_loc):
            block("Adobe preferences (PlayerDebugMode) are the editor's to change. Give them the command to run themselves.")
        if name in ("invoke-expression", "iex"):
            words = [VALUES.get(a[1:].lower(), a) if a.startswith("$") else a for a in args if a.lower() != "-command"]
            check_powershell(" ".join(words), cwd, agent)
            continue
        if name in PS_CD:
            tgt = next((a for a in args if not a.startswith("-")), None)
            if tgt and _REG_LOC.match(tgt):
                reg_loc = tgt
            elif tgt:
                tp = Path(native(expand(tgt, cwd))).expanduser()
                cwd = tp if tp.is_absolute() else cwd / tp
            continue
        if name in PS_CONTENT_WRITERS:
            for a in ps_path_args(args):
                hit = protected(a, cwd)
                if hit:
                    block(f"`{argv[0]}` would write into the client's source folder ({hit}). Write to <client>/output/.")
            continue
        if name in PS_MUTATE_ANY:
            for a in args:
                for part in a.split(","):
                    hit = protected(part, cwd, recursive=name in PS_TREE)
                    if hit:
                        block(f"`{argv[0]}` on the client's source folder ({hit}) is not allowed — assets/ and data/ are read-only.")
            continue
        if name in PS_COPY or name in ("expand-archive", "invoke-webrequest", "iwr", "start-bitstransfer"):
            dest = [args[i + 1] for i, a in enumerate(args[:-1]) if a.lower() in PS_DEST_PARAMS - {"-path", "-literalpath"}]
            if not dest and name in PS_COPY:
                pos = [a for i, a in enumerate(args) if not a.startswith("-") and (i == 0 or not args[i - 1].startswith("-"))]
                dest = pos[1:2]
            for d in dest:
                hit = protected(d, cwd)
                if hit:
                    block(f"`{argv[0]}` would write into the client's source folder ({hit}). Write to <client>/output/ instead.")
            continue
        # native programs (ffmpeg, tar, cmd, reel...) follow the same rules as in Bash
        cwd = check_argv([name] + args, cwd, agent)


def heartbeat():
    """${CLAUDE_PLUGIN_DATA}/guard-ok: the guard itself ran (doctor's guard_active); hooks-ok is the runner's."""
    d = os.environ.get("CLAUDE_PLUGIN_DATA")
    if d:
        try:
            Path(d, "guard-ok").write_text(str(int(time.time())), encoding="utf-8")
        except OSError:
            pass


# a shell command naming output/.whynot-lock that could change it (subagents only read it; `reel lock --status`)
LOCK_NAME = ".whynot-lock"
LOCK_WRITE = re.compile(r">|(?<![\w-])-delete\b|\b(rm|del|erase|rd|rmdir|unlink|mv|move|ren|rename|cp|copy|touch|"
                        r"truncate|tee|shred|sed|perl|python\d*|node|ruby|bash|cmd|pwsh|powershell|remove-item|"
                        r"move-item|rename-item|rni|copy-item|cpi|set-content|add-content|clear-content|clc|out-file|"
                        r"new-item|set-itemproperty)\b|::\w*(delete|move|write|copy|replace|create)", re.I)
LOCK_SHORT = {"sc", "ac", "mi", "ni", "ri", "py", "sh"}         # 2-letter aliases: only as a command's first word
_STREAM_REDIR = re.compile(r"[0-9]?>&[0-9-]|[0-9*]>>?\s*(\"[^\"]*\"|'[^']*'|[^\s;|&]+)")
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def names_lock(text: str) -> bool:
    """The text names the lock file, also through a glob (`output/.whynot-l*`, `.whynot-?ock`)."""
    if LOCK_NAME in text.lower():
        return True
    for tok in re.split(r"[\s;|&<>()\"']+", text):
        base = re.split(r"[\\/]", tok)[-1].lower()
        if base.startswith(".") and any(c in base for c in "*?[") and fnmatch.fnmatchcase(LOCK_NAME, base):
            return True
    return False


def lock_write(text: str) -> bool:
    """A shell command that could change the lock: a writing verb, redirection or interpreter. Stream redirects
    (`2>/dev/null`, `2>&1`, `>&2`) are reads unless they point at the lock; sc/ac/mi/ni/ri/py/sh count only as the
    first word of a command (`grep -c py` is a read)."""
    t = _STREAM_REDIR.sub(lambda m: m.group(0) if names_lock(m.group(0)) else " ", text)
    if LOCK_WRITE.search(t):
        return True
    return any(norm_exe(seg.split()[0]) in LOCK_SHORT for seg in re.split(r"[;|&\n(){}]|\$\(", t) if seg.split())


def main():
    if sys.version_info < (3, 8):       # run_python.sh no longer probes the version: fail open, but say so
        print("WhyNot Cut guard: Python 3.8+ needed; protection is OFF (run reel doctor)", file=sys.stderr)
        sys.exit(0)
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    heartbeat()
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    cwd = Path(native(data.get("cwd") or os.getcwd()))
    agent = data.get("agent_type") or None          # full name: `whynot-cut:qc-reviewer` (structure review 4.7)
    text = str(ti.get("command") or ti.get("file_path") or ti.get("notebook_path") or "")
    if agent and names_lock(text) and (tool in WRITE_TOOLS or (tool in ("Bash", "PowerShell") and lock_write(text))):
        block("subagents may not change, move or delete the client's writer lock (output/.whynot-lock); reading it is "
              "fine (`reel lock --status`). Report it to the lead instead: only the lead runs `reel lock --release`, "
              "on the editor's word.")
    if tool in WRITE_TOOLS:
        fp = ti.get("file_path") or ti.get("notebook_path") or ""
        if own_role(agent) in READ_ONLY_AGENTS:
            block(f"{own_role(agent)} is a read-only reviewer; it reports findings instead of editing files.")
        if ae_pref_path(fp):
            block(AE_PREFS_MSG)
        hit = protected(fp, cwd)
        if hit:
            block(f"the client's source folder ({hit}) is read-only. Write outputs under <client>/output/.")
    elif tool == "Bash":
        check_bash(ti.get("command", ""), cwd, agent)
    elif tool == "PowerShell":
        check_powershell(ti.get("command", ""), cwd, agent)
    sys.exit(0)


if __name__ == "__main__":
    main()
