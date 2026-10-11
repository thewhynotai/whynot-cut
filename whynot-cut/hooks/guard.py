#!/usr/bin/env python3
"""WhyNot Cut PreToolUse guard (stdlib only; macOS and Windows). Exit 2 + stderr = block; exit 0 = allow.

Rules enforced in code (prose rules get forgotten in long sessions):
  1. Client source folders are read-only: nothing may write, move or delete inside <client>/assets or
     <client>/data. A client folder has BOTH assets/ and data/ AND a positive sign: a `.whynot-client` file, an
     `output/client_database/` folder, or it lies under the configured clients folder (`clients_root`). A Hugo site
     or any other repo with assets/ + data/ is left alone (engine/reel/lib/client_marker.py).
  2. Whole project folders are not deleted by the agent (rm -r on output/ or output/projects/<ID>).
  3. After Effects / Photoshop builds are opt-in extras: `reel ae-*|ps-*|mogrt-build` need --extras.
  4. Roles: subagents never approve the plan, record a verification verdict or verify a transcript as the editor
     (the lead does, after looking); WhyNot Cut's reviewer agents (matched on the full `whynot-cut:<name>`) are
     read-only; setup-doctor diagnoses and never installs.
  5. Adobe preferences (PlayerDebugMode, After Effects prefs) are the editor's to change.

Covers the Write/Edit tools, Bash (macOS/Linux shells and Git Bash on Windows, incl. /d/... paths) and PowerShell
(cmdlets, aliases, redirection, pipelines, `$( )` bodies, [IO.File]:: calls), and the shells they start (`cmd /c`,
`powershell -Command`, `bash -c`, `xargs`). This is a guardrail against mistakes, not a sandbox. It errs on the side
of allowing reads. Writes made from inside an interpreter (`python -c`, a script file, `node -e`) are not inspected.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shlex
import sys
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
SHELL_PREFIXES = {"sudo", "time", "nohup", "command", "exec", "env", "then", "do", "else", "elif", "if", "while",
                  "until", "!", "{", "("}
GIT_MUTATE = {"checkout", "reset", "clean", "rm", "mv", "restore"}
XARGS_VALUE_OPTS = {"-I", "-L", "-n", "-P", "-d", "-E", "-s", "-a", "--max-args", "--max-procs", "--delimiter",
                    "--arg-file", "--max-lines", "--eof", "--max-chars", "--replace"}


IS_WIN = os.name == "nt"
_MSYS = re.compile(r"^/([a-zA-Z])(/|$)")


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


def client_root_of(p: Path) -> tuple[Path, str] | None:
    """If p is inside <root>/assets or <root>/data of a client folder, return (root, 'assets'|'data')."""
    try:
        p = p.expanduser()
        p = p.resolve() if p.exists() else (p.parent.resolve() / p.name if p.parent.exists() else p)
    except Exception:
        return None
    for anc in [p, *p.parents]:
        if anc.name in ("assets", "data"):
            root = anc.parent
            if client_marker.has_layout(root) and is_client(root):
                return root, anc.name
    return None


def hit_of(p: Path) -> str | None:
    hit = client_root_of(p)
    return f"{hit[0].name}/{hit[1]}" if hit else None


AE_PREFS = re.compile(r"(adobe[\\/]+after effects[\\/]+\d[\d.]*[\\/])|(adobe after effects [^\\/]*prefs[^\\/]*\.txt$)", re.I)
AE_PREFS_MSG = ("After Effects preferences are the editor's to change (scripting security, Type engine). "
                "Give them the step to do themselves.")


def ae_pref_path(path_str: str) -> bool:
    """After Effects preference files (scripting security, Type engine…): the editor's to change, never Claude's."""
    return bool(path_str) and bool(AE_PREFS.search(path_str.replace("\\", "/")))


def protected(path_str: str, cwd: Path, writing: bool = True) -> str | None:
    """'<client>/assets|data' when path_str (relative to cwd) is inside a client's sources. writing=False: a path
    that is only named (read), e.g. in the first stage of a pipeline."""
    if not path_str or path_str.startswith("-"):
        return None
    if writing and ae_pref_path(path_str.strip("'\"")):
        block(AE_PREFS_MSG)             # every caller is about to write there: not a client-folder message
    s = native(path_str.strip("'\""))
    if "=" in s and not s.startswith("/") and not re.match(r"^[A-Za-z]:[\\/]", s):   # dd of=..., key=value
        s = s.split("=", 1)[1]
    try:
        p = Path(native(s)).expanduser()
    except Exception:
        return None
    if not p.is_absolute():
        p = cwd / p
    return hit_of(p)


def pipe_source(stages: list[tuple[list[str], Path]], cwd: Path) -> str | None:
    """A client source path named by an earlier stage of the pipeline (a read), or a working directory that is one."""
    for argv, at in stages:
        for a in argv[1:]:
            hit = protected(a, at, writing=False)
            if hit:
                return hit
    return hit_of(cwd)


def split_commands(cmd: str) -> list[tuple[list[str], bool]]:
    """Simple commands, each with `piped` = it reads the previous command's output (`a | b`)."""
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|<>")
        lex.whitespace_split = True
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


def dotnet_writes(text: str) -> list[list[str]]:
    """String arguments of every [IO.File]:: / [System.IO.Directory]:: call that writes, moves or deletes
    (for Copy only the destination). A call with no string argument ($_.FullName...) gives ['']."""
    out = []
    for m in _DOTNET.finditer(text):
        kind, meth = m.group(1).lower(), m.group(2).lower()
        if meth not in DOTNET_WRITE[kind]:
            continue
        depth, j = 1, m.end()
        while j < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[j], 0)
            j += 1
        args = [a for _, a in re.findall(r"""(['"])(.*?)\1""", text[m.end():j - 1])]
        out.append(args[1:2] if meth == "copy" else args or [""])
    return out


def check_dotnet(text: str, cwd: Path):
    for args in dotnet_writes(text):
        for a in args:
            hit = protected(a, cwd)
            if hit:
                block(f"a .NET file call on the client's source folder ({hit}) is not allowed — assets/ and data/ "
                      f"are read-only.")


_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def shell_lines(cmd: str) -> str:
    """Drop heredoc BODIES (they are data such as a script's text, not shell commands) and make each line its own
    command (newlines separate commands in a shell; shlex would otherwise glue lines together)."""
    out, delim = [], None
    for line in cmd.replace("\\\n", " ").split("\n"):
        if delim is not None:
            if line.strip() == delim:
                delim = None
            continue
        m = _HEREDOC.search(line)
        if m:
            delim = m.group(2)
        out.append(line)
    return " ; ".join(out)


def adobe_pref_change(argv: list[str]) -> bool:
    """Writing Adobe's CEP preferences (PlayerDebugMode lets unsigned panels load). The editor does that, never Claude."""
    exe = Path(argv[0]).name.lower().rsplit(".", 1)[0] if argv else ""
    low = " ".join(argv).lower().replace("/", "\\")
    if exe == "defaults" and len(argv) > 2 and argv[1] in ("write", "delete") and "com.adobe.csxs" in argv[2].lower():
        return True
    if exe == "reg" and len(argv) > 1 and argv[1].lower() in ("add", "delete", "import") and "adobe\\csxs" in low:
        return True
    if exe in ("set-itemproperty", "sp", "new-itemproperty", "new-item", "ni", "remove-itemproperty", "rp") \
            and "adobe\\csxs" in low:
        return True
    return False


def strip_prefixes(argv: list[str]) -> list[str]:
    """Drop env assignments, sudo/time/env, shell keywords (then/do/if...) and subshell/group brackets."""
    argv = list(argv)
    while argv and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[0]) or argv[0] in SHELL_PREFIXES):
        argv = argv[1:]
    if argv and argv[0][:1] in ("(", "{") and len(argv[0]) > 1:
        argv[0] = argv[0].lstrip("({")
    while argv and argv[-1] in (")", "}", "))"):
        argv = argv[:-1]
    return argv


def xargs_command(argv: list[str]) -> list[str]:
    """`xargs [options] cmd args...` -> [cmd, args...]."""
    i = 1
    while i < len(argv) and argv[i].startswith("-"):
        i += 2 if argv[i] in XARGS_VALUE_OPTS else 1
    return argv[i:]


def mutates_inputs(argv: list[str]) -> bool:
    """A pipeline stage that deletes, moves or edits the paths it reads on stdin (`xargs rm`, `xargs sed -i`)."""
    if not argv or Path(argv[0]).name != "xargs":
        return False
    sub = strip_prefixes(xargs_command(argv))
    name = Path(sub[0]).name if sub else ""
    return name in MUTATE_ALL or (name in ("sed", "perl") and any(a.startswith("-i") for a in sub[1:]))


def check_bash(cmd: str, cwd: Path, agent: str | None):
    text = shell_lines(cmd)                     # heredoc bodies are data, not commands
    for body in substitutions(text):
        check_bash(body, cwd, agent)
    check_dotnet(text, cwd)
    stages = []                                 # earlier stages of the current pipeline: (argv, cwd)
    for argv, piped in split_commands(text):
        argv = strip_prefixes(argv)
        if not argv:
            continue
        stages = stages if piped else []
        if piped and mutates_inputs(argv):
            src = pipe_source(stages, cwd)
            if src:
                block(f"`{' '.join(argv[:2])}` would change files listed from the client's source folder ({src}). "
                      f"assets/ and data/ are read-only.")
        stages.append((argv, cwd))
        cwd = check_argv(argv, cwd, agent)


_PS_VALUE_OPTS = {"-executionpolicy", "-ep", "-ex", "-windowstyle", "-w", "-workingdirectory", "-wd",
                  "-configurationname", "-outputformat", "-of", "-inputformat", "-if", "-psconsolefile", "-version",
                  "-v", "-settingsfile", "-custompipename"}


def shell_body(exe: str, argv: list[str]) -> tuple[str, str] | None:
    """('ps'|'sh', command text) for `cmd /c ...`, `powershell|pwsh -Command ...|-EncodedCommand ...` and
    `bash|sh|zsh -c ...`: the command the wrapper will run (checked like a command of its own)."""
    low = exe.lower()
    if low == "cmd":
        for i, a in enumerate(argv[1:], 1):
            if a.lower() in ("/c", "/k", "/r"):
                rest = argv[i + 1:]          # `cmd /c "reg add ..."`: one quoted argument is the whole command
                return "ps", rest[0] if len(rest) == 1 else " ".join(f'"{t}"' if re.search(r"\s", t) else t
                                                                     for t in rest)
        return None
    if low in ("powershell", "pwsh"):
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
    if low in ("bash", "sh", "zsh", "dash", "ksh"):
        for i, a in enumerate(argv[1:-1], 1):
            if re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*", a):
                return "sh", argv[i + 1]
    return None


def check_git(argv: list[str], cwd: Path):
    """git checkout/reset/clean/rm/mv/restore on a client's sources (via -C, --work-tree or a path argument)."""
    base, i = cwd, 1
    while i < len(argv) and argv[i].startswith("-"):
        a = argv[i]
        if a in ("-C", "--work-tree") and i + 1 < len(argv):
            t = Path(native(argv[i + 1].strip("'\""))).expanduser()
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
    hit = hit_of(base)
    paths = [a for a in rest if not a.startswith("-")]
    whole = sub == "clean" or (sub == "reset" and any(a in ("--hard", "--merge", "--keep") for a in rest)) or \
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
    exe = Path(argv[0]).name
    if exe.lower().endswith((".exe", ".cmd", ".bat")):
        exe = exe.rsplit(".", 1)[0]
    body = shell_body(exe, argv)
    if body:                            # the command a wrapper shell runs gets the same checks
        (check_powershell if body[0] == "ps" else check_bash)(body[1], cwd, agent)
        return cwd
    if exe == "xargs":
        check_argv(xargs_command(argv), cwd, agent)
        return cwd
    if exe == "git":
        check_git(argv, cwd)
    if exe in ("cd", "pushd"):          # later relative paths are relative to the cd target
        tgt = Path(native(argv[1])).expanduser() if len(argv) > 1 and argv[1] != "-" else Path.home()
        return tgt if tgt.is_absolute() else cwd / tgt
    # redirections anywhere: > target / >> target
    for i, t in enumerate(argv):
        if t in (">", ">>", ">|") and i + 1 < len(argv):
            hit = protected(argv[i + 1], cwd)
            if hit:
                block(f"writing into the client's source folder ({hit}) is not allowed. Outputs go to <client>/output/.")
    if exe in MUTATE_ALL or (exe in ("sed", "perl") and any(a.startswith("-i") for a in argv[1:])) or \
            (exe == "xattr" and any(a in ("-w", "-d", "-c", "-r") for a in argv[1:])):
        for a in argv[1:]:
            hit = protected(a, cwd)
            if hit:
                block(f"`{exe}` on the client's source folder ({hit}) is not allowed — assets/ and data/ are read-only.")
    if exe in MUTATE_DEST:
        paths = [a for a in argv[1:] if not a.startswith("-") and a not in (">", ">>")]
        dest = None
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
        starts = []
        for a in argv[1:]:
            if a.startswith(("-", "(", "!")) and a not in ("-H", "-L", "-P"):
                break
            if not a.startswith("-"):
                starts.append(a)
        execs = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a in ("-exec", "-execdir", "-ok", "-okdir")]
        if "-delete" in argv or any(Path(e).name in MUTATE_ALL for e in execs):
            for a in starts or ["."]:
                p = Path(native(a.strip("'\""))).expanduser()
                p = p if p.is_absolute() else cwd / p
                hit = protected(a, cwd) or \
                    (f"{p.resolve().name}/assets+data" if is_client(Path(os.path.abspath(p))) else None)
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
            p = Path(native(a.strip("'\"")))
            p = p if p.is_absolute() else cwd / p
            parts = p.parts
            if p.name == "output" and is_client(Path(os.path.abspath(p.parent))):
                block("deleting a client's whole output/ folder is not allowed — ask the editor to do it.")
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
    # `python -B .../engine/reel/cli.py ...` (interpreter flags before the script) is the same as `reel`
    is_reel = exe == "reel" or (exe.startswith("python") and any(a.strip("'\"").replace("\\", "/").endswith("engine/reel/cli.py")
                                                                 for a in argv[1:4]))
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
    "set-content", "sc", "add-content", "ac", "out-file", "new-item", "ni", "mkdir", "md", "rename-item", "ren",
    "rni", "move-item", "mv", "move", "mi", "set-itemproperty", "sp", "tee-object", "tee", "export-csv",
    "set-acl", "compress-archive", "remove-itemproperty", "rp", "new-itemproperty"}
PS_PIPE_MUTATE = {  # take the paths they act on from the pipeline (Get-ChildItem data | Remove-Item)
    "remove-item", "rm", "del", "erase", "rd", "rmdir", "ri", "rename-item", "ren", "rni", "move-item", "mv", "move",
    "mi", "clear-content", "clc", "clear-item", "cli", "set-content", "sc", "add-content", "ac", "set-itemproperty",
    "sp", "remove-itemproperty", "rp", "new-itemproperty", "set-acl"}
PS_CONTENT_WRITERS = {"set-content", "sc", "add-content", "ac"}
_PS_METHOD_WRITE = re.compile(r"\.(delete|moveto|replace|encrypt|decrypt|create|createtext|appendtext|openwrite)\s*\(",
                              re.I)
PS_COPY = {"copy-item", "cp", "copy", "cpi"}                      # only the destination is written
PS_DEST_PARAMS = {"-destination", "-destinationpath", "-outfile", "-filepath", "-literalpath", "-path"}
PS_CD = {"set-location", "cd", "sl", "chdir", "push-location", "pushd"}
PS_SEP = {";", "|", "&&", "||", "\n"}


def ps_tokens(cmd: str) -> list[tuple[list[str], bool]]:
    """Split a PowerShell command line into simple commands (quote-aware; backtick escapes; > redirects), each with
    `piped` = it reads the previous command's output (`a | b`)."""
    stmts, cur, tok, q, i, piped = [], [], "", None, 0, False
    def push_tok():
        nonlocal tok
        if tok:
            cur.append(tok)
            tok = ""
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
        elif c in "'\"":
            q = c
        elif c == "`" and i + 1 < len(cmd):
            tok += cmd[i + 1] if cmd[i + 1] not in "\r\n" else ""
            i += 1
        elif c in " \t\r":
            push_tok()
        elif c in ";|\n" or cmd.startswith("&&", i):
            push_tok()
            if cur:
                stmts.append((cur, piped))
            cur = []
            piped = c == "|" and not cmd.startswith("||", i)
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
    push_tok()
    if cur:
        stmts.append((cur, piped))
    return stmts


def ps_mutates_inputs(argv: list[str]) -> bool:
    """A pipeline stage that deletes, moves or writes the items piped into it: a mutating cmdlet in command
    position (also inside `ForEach-Object { ... }`), `$_.Delete()`-style methods, or a writing [IO.File]:: call."""
    words, prev = [], "{"
    for t in argv:
        if prev.endswith(("{", "(")) or prev in ("%", "foreach-object", "foreach"):
            words.append(t)
        words += [w for w in re.split(r"[{(]", t)[1:] if w]
        prev = t.lower()
    if argv[0].lower() in PS_CONTENT_WRITERS and (
            any(a.lower() in ("-path", "-literalpath", "-lp", "-pspath") for a in argv[1:]) or
            any(not a.startswith("-") and not argv[i].startswith("-") for i, a in enumerate(argv[1:]))):
        words = words[1:]            # `... | Set-Content out.txt`: the piped text is the content, the path is its own
    text = " ".join(argv)
    return any(w.lower() in PS_PIPE_MUTATE for w in words) or bool(_PS_METHOD_WRITE.search(text)) or \
        bool(dotnet_writes(text))


def check_powershell(cmd: str, cwd: Path, agent: str | None):
    for body in substitutions(cmd, backticks=False):
        check_powershell(body, cwd, agent)
    check_dotnet(cmd, cwd)
    stages = []                                 # earlier stages of the current pipeline: (argv, cwd)
    for argv, piped in ps_tokens(cmd):
        if argv and argv[0] in ("&", "."):
            argv = argv[1:]
        if not argv:
            continue
        stages = stages if piped else []
        if piped and ps_mutates_inputs(argv):
            src = pipe_source(stages, cwd)
            if src:
                block(f"`{argv[0]}` would change items piped from the client's source folder ({src}). "
                      f"assets/ and data/ are read-only.")
        stages.append((argv, cwd))
        name = Path(native(argv[0])).name.lower()
        for ext in (".exe", ".cmd", ".bat", ".ps1"):
            name = name[:-len(ext)] if name.endswith(ext) else name
        for i, t in enumerate(argv):
            if t == ">" and i + 1 < len(argv):
                hit = protected(argv[i + 1], cwd)
                if hit:
                    block(f"writing into the client's source folder ({hit}) is not allowed. Outputs go to <client>/output/.")
        args = [a for a in argv[1:] if a != ">"]
        if adobe_pref_change([name] + args):
            block("Adobe preferences (PlayerDebugMode) are the editor's to change. Give them the command to run themselves.")
        if name in PS_CD:
            tgt = next((a for a in args if not a.startswith("-")), None)
            if tgt:
                tp = Path(native(tgt)).expanduser()
                cwd = tp if tp.is_absolute() else cwd / tp
            continue
        if name in PS_MUTATE_ANY:
            for a in args:
                for part in a.split(","):
                    hit = protected(part, cwd)
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
        # native programs (ffmpeg, tar, reel...) follow the same rules as in Bash
        cwd = check_argv([name] + args, cwd, agent)


def main():
    if sys.version_info < (3, 8):       # run_python.sh no longer probes the version: fail open, but say so
        print("WhyNot Cut guard: Python 3.8+ needed; protection is OFF (run reel doctor)", file=sys.stderr)
        sys.exit(0)
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    cwd = Path(native(data.get("cwd") or os.getcwd()))
    agent = data.get("agent_type") or None          # full name: `whynot-cut:qc-reviewer` (structure review 4.7)
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
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
