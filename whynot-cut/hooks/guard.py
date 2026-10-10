#!/usr/bin/env python3
"""WhyNot Cut PreToolUse guard (stdlib only; macOS and Windows). Exit 2 + stderr = block; exit 0 = allow.

Rules enforced in code (prose rules get forgotten in long sessions):
  1. Client source folders are read-only: nothing may write, move or delete inside <client>/assets or
     <client>/data (a client folder is any folder that has BOTH assets/ and data/).
  2. Whole project folders are not deleted by the agent (rm -r on output/ or output/projects/<ID>).
  3. After Effects / Photoshop builds are opt-in extras: `reel ae-*|ps-*|mogrt-build` need --extras.
  4. Roles: subagents never approve the plan or record a verification verdict (the lead does, after
     looking); reviewer agents are read-only.

Covers the Write/Edit tools, Bash (macOS/Linux shells and Git Bash on Windows, incl. /d/... paths) and PowerShell
(cmdlets, aliases, redirection). This is a guardrail against mistakes, not a sandbox. It errs on the side of allowing
reads. Writes made from inside an interpreter (`python -c`, a script file, `node -e`) are not inspected.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

READ_ONLY_AGENTS = {"medical-reviewer", "claim-checker", "frame-inspector", "graphic-checker",
                    "segment-proofreader", "qc-reviewer", "intake-inspector", "setup-doctor"}
EXTRAS = {"ae-script", "ae-build", "ae-render", "ps-script", "ps-build", "mogrt-build"}
QC_FORBIDDEN = {"ppro-build", "approve-plan", "plan", "previews", "audio-clean", "transcribe",
                "transcript-correct", "client-init", "client-db", "sfx", "premiere", "handoff"}
MUTATE_ALL = {"rm", "mv", "touch", "chmod", "chown", "truncate", "unlink", "rmdir", "shred", "dot_clean",
              "setfile", "srm"}
MUTATE_DEST = {"cp", "rsync", "ditto", "ln", "ffmpeg", "tee", "mkdir", "install", "scp", "curl", "wget",
               "unzip", "tar", "sips", "convert", "magick"}
FFMPEG_FLAGS = {"-y", "-n", "-hide_banner", "-nostdin", "-stdin", "-shortest", "-an", "-vn", "-sn", "-dn", "-stats",
                "-nostats", "-benchmark", "-copyts", "-re", "-accurate_seek", "-noaccurate_seek", "-report"}
FFMPEG_WRITE_OPTS = {"-progress", "-passlogfile", "-vstats_file", "-dump_attachment"}
FIND_WRITE_ACTIONS = {"-fprint", "-fprint0", "-fprintf", "-fls"}
SEPARATORS = {"&&", "||", ";", "|", "&"}


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
            if (root / "assets").is_dir() and (root / "data").is_dir():
                return root, anc.name
    return None


def protected(path_str: str, cwd: Path) -> str | None:
    if not path_str or path_str.startswith("-"):
        return None
    s = native(path_str.strip("'\""))
    if "=" in s and not s.startswith("/") and not re.match(r"^[A-Za-z]:[\\/]", s):   # dd of=..., key=value
        s = s.split("=", 1)[1]
    p = Path(native(s)).expanduser()
    if not p.is_absolute():
        p = cwd / p
    hit = client_root_of(p)
    return f"{hit[0].name}/{hit[1]}" if hit else None


def split_commands(cmd: str) -> list[list[str]]:
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|<>")
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:
        toks = cmd.split()
    out, cur = [], []
    for t in toks:
        if t in SEPARATORS:
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        out.append(cur)
    return out


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


def check_bash(cmd: str, cwd: Path, agent: str | None):
    for argv in split_commands(shell_lines(cmd)):
        cwd = check_argv(argv, cwd, agent)


def check_argv(argv: list[str], cwd: Path, agent: str | None) -> Path:
    """Checks one simple command; returns the working directory for the next one (follows cd)."""
    if not argv:
        return cwd
    # strip env assignments / sudo / time
    while argv and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[0]) or argv[0] in ("sudo", "time", "nohup", "command")):
        argv = argv[1:]
    if not argv:
        return cwd
    if adobe_pref_change(argv):
        block("Adobe preferences (PlayerDebugMode) are the editor's to change. Give them the command to run themselves.")
    exe = Path(argv[0]).name
    if exe.lower().endswith((".exe", ".cmd", ".bat")):
        exe = exe.rsplit(".", 1)[0]
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
                    (f"{p.resolve().name}/assets+data" if (p / "assets").is_dir() and (p / "data").is_dir() else None)
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
            if p.name == "output" and (p.parent / "assets").is_dir():
                block("deleting a client's whole output/ folder is not allowed — ask the editor to do it.")
            if len(parts) >= 3 and parts[-2] == "projects" and parts[-3] == "output":
                block(f"deleting the whole project folder {p.name} is not allowed — ask the editor to do it.")
    # engine-level rules
    check_reel(exe, argv, agent)
    return cwd


def check_reel(exe: str, argv: list[str], agent: str | None):
    is_reel = exe == "reel" or (exe.startswith("python") and any(a.replace("\\", "/").endswith("engine/reel/cli.py")
                                                                 for a in argv[1:2]))
    if is_reel:
        sub = next((a for a in argv[1:] if not a.startswith("-") and not a.endswith("cli.py")
                    and argv[argv.index(a) - 1] not in ("--root", "--video-id", "--profile")), None)
        if sub in EXTRAS and "--extras" not in argv:
            block(f"`reel {sub}` is an optional After Effects/Photoshop extra. The pipeline is Premiere-only "
                  f"unless the editor explicitly asked for AE/PS; then add --extras.")
        if agent:
            if sub == "approve-plan":
                block("only the lead editor (main conversation) records plan approval, after the editor approves.")
            if sub == "settings" and "--init" in argv:
                block("only the lead editor changes the editor's preferences (e.g. approval mode), when the editor asks.")
            if sub == "verify" and "--record" in argv:
                block("subagents report a verdict; the lead editor records it after viewing the evidence itself.")
            if agent == "qc-reviewer" and sub in QC_FORBIDDEN:
                block(f"qc-reviewer is independent and read-only: it may not run `reel {sub}`. Report the issue instead.")


# --------------------------------------------------------------------------- PowerShell (Windows)
PS_MUTATE_ANY = {  # every path argument of these is written, moved or deleted
    "remove-item", "rm", "del", "erase", "rd", "rmdir", "ri", "clear-content", "clc", "clear-item", "cli",
    "set-content", "sc", "add-content", "ac", "out-file", "new-item", "ni", "mkdir", "md", "rename-item", "ren",
    "rni", "move-item", "mv", "move", "mi", "set-itemproperty", "sp", "tee-object", "tee", "export-csv",
    "set-acl", "compress-archive", "remove-itemproperty", "rp", "new-itemproperty"}
PS_COPY = {"copy-item", "cp", "copy", "cpi"}                      # only the destination is written
PS_DEST_PARAMS = {"-destination", "-destinationpath", "-outfile", "-filepath", "-literalpath", "-path"}
PS_CD = {"set-location", "cd", "sl", "chdir", "push-location", "pushd"}
PS_SEP = {";", "|", "&&", "||", "\n"}


def ps_tokens(cmd: str) -> list[list[str]]:
    """Split a PowerShell command line into simple commands (quote-aware; backtick escapes; > redirects)."""
    stmts, cur, tok, q, i = [], [], "", None, 0
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
                stmts.append(cur)
            cur = []
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
        stmts.append(cur)
    return stmts


def check_powershell(cmd: str, cwd: Path, agent: str | None):
    for argv in ps_tokens(cmd):
        if argv and argv[0] in ("&", "."):
            argv = argv[1:]
        if not argv:
            continue
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
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    cwd = Path(data.get("cwd") or os.getcwd())
    agent = data.get("agent_type") or None
    if agent:
        agent = agent.split(":")[-1]
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        fp = ti.get("file_path") or ti.get("notebook_path") or ""
        if agent in READ_ONLY_AGENTS:
            block(f"{agent} is a read-only reviewer; it reports findings instead of editing files.")
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
