"""3.0 T3.8 — plugin-structure tests: every skill and agent frontmatter parses as YAML, agent colours are valid, every
`skills:` entry and every referenced `whynot-cut:<name>` exists, and every `reel <cmd> --flag` written in the skills,
agents, READMEs and evals exists in the REAL argparse parser that `cli.main` builds (subcommands, options and their
aliases, the global options, `reel serve <verb>`; `reel py` passes everything to the script).

The Phase 1 checks (description budget, version triple, exec bits) stay in test_plugin.py / test_release_hygiene.py.
Each check is a function over a plugin folder, so a seeded bad fixture (a temp folder) proves it fails.
KNOWN: violations the repo has today, each owned by the Phase 3 task that rewrites the file; the owner deletes the entry
when fixing it (a stale entry fails `test_allow_list_has_no_stale_entries`).
Run:  bash tools/test.sh -p test_structure.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import argparse
import contextlib
import importlib.util
import io
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import yaml  # pyyaml is pinned in setup/locks/runtime-*.lock (the engine runtime runs this suite)
except ImportError:  # pragma: no cover - only outside the engine runtime
    yaml = None

sys = _sys
SK = Path(__file__).resolve().parents[1]
REPO = SK.parent
sys.path.insert(0, str(SK / "engine" / "reel"))

COLOURS = {"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"}
GLOBAL_VALUE_OPTS = {"--root", "--video-id", "--profile", "--episode"}

# Current violations, (repo-relative file, issue) -> "owner task: reason". Line numbers are left out on purpose (edits
# above an entry must not break it); the report lists them.
KNOWN: dict[tuple[str, str], str] = {
    ("whynot-cut/agents/motion-director.md", "colour 'magenta' is not one of " + ", ".join(sorted(COLOURS))):
        "T3.3: agents rewrite; motion-director predates the colour rule (Claude Code agent colours are the 8 above)",
}


# ---------------------------------------------------------------------------------------------------------- parsing
def frontmatter(text: str) -> dict:
    """The YAML between the opening `---` (first line) and the next `---` line, parsed with PyYAML (safe_load)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("no frontmatter: the first line is not ---")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise ValueError("frontmatter is not closed by a --- line") from None
    try:
        data = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as e:
        raise ValueError(f"frontmatter is not valid YAML: {e}".replace("\n", " ")) from None
    if not isinstance(data, dict):
        raise ValueError("frontmatter is not a YAML mapping")
    return data

# ------------------------------------------------------------------------------------------------- frontmatter schema
# Closed key sets with types, from the Claude Code docs read 2026-10-13: https://code.claude.com/docs/en/sub-agents.md
# (agent fields), https://code.claude.com/docs/en/skills.md (skill fields) and the plugin-dev agent-development skill
# (model: inherit | sonnet | opus | haiku). Claude Code ignores an unknown or misspelt key without any error, so a typo
# (`maxTurn`, `disallowedtools`) or a wrong type (`maxTurns: "8"`) silently does nothing: that is what these catch.
def _str(v):
    return None if isinstance(v, str) and v.strip() else "a non-empty string"


def _bool(v):
    return None if isinstance(v, bool) else "true or false"


def _posint(v):
    return None if isinstance(v, int) and not isinstance(v, bool) and v > 0 else "an integer greater than 0"


def _strs(v):                      # tools / allowed-tools / paths: a comma or space string, or a list of strings
    ok = (isinstance(v, str) and v.strip()) or (isinstance(v, list) and v and all(isinstance(x, str) for x in v))
    return None if ok else "a string or a list of strings"


def _one_of(*values):
    return lambda v: None if v in values else "one of " + ", ".join(values)


def _model(v):                     # an alias, `inherit`, or a full model id
    ok = isinstance(v, str) and (v in {"inherit", "sonnet", "opus", "haiku", "fable"} or v.startswith("claude-"))
    return None if ok else "inherit, sonnet, opus, haiku, fable or a full model id (claude-…)"


def _any(v):                       # checked elsewhere (colour, skills:) or free-form
    return None


EFFORT = _one_of("low", "medium", "high", "xhigh", "max")
KNOWN_KEYS: dict[str, dict] = {
    "agent": {"name": _str, "description": _str, "tools": _strs, "disallowedTools": _strs, "model": _model,
              "color": _any, "skills": _any, "maxTurns": _posint, "effort": EFFORT,
              "memory": _one_of("user", "project", "local"), "background": _bool, "isolation": _one_of("worktree"),
              "omitClaudeMd": _bool, "experimental": lambda v: None if isinstance(v, dict) else "a mapping"},
    "skill": {"name": _str, "description": _str, "when_to_use": _str, "argument-hint": _str,
              "arguments": _strs, "disable-model-invocation": _bool, "user-invocable": _bool,
              "allowed-tools": _strs, "disallowed-tools": _strs, "model": _str, "effort": EFFORT,
              "context": _one_of("fork"), "agent": _str, "background": _bool,
              "hooks": lambda v: None if isinstance(v, dict) else "a mapping", "paths": _strs,
              "shell": _one_of("bash", "powershell"), "metadata": lambda v: None if isinstance(v, dict) else "a mapping",
              "license": _str, "compatibility": _str},
}
# keys Claude Code documents but does not honour in plugin agents (security): they do nothing, so they fail too
IGNORED_IN_PLUGIN_AGENTS = {"permissionMode", "hooks", "mcpServers", "initialPrompt"}


def schema_issues(kind: str, fm: dict) -> list[tuple[str, str]]:
    """(key, message) for every unknown key and every value of the wrong type or outside its closed set."""
    out = []
    for k, v in fm.items():
        if kind == "agent" and k in IGNORED_IN_PLUGIN_AGENTS:
            out.append((k, f"frontmatter key {k!r} is ignored in plugin agents (Claude Code does not honour it there)"))
        elif k not in KNOWN_KEYS[kind]:
            out.append((k, f"unknown {kind} frontmatter key {k!r}: add it to KNOWN_KEYS if Claude Code supports it"))
        else:
            want = KNOWN_KEYS[kind][k](v)
            if want:
                out.append((k, f"{kind} frontmatter {k}: expected {want}, got {v!r}"))
    return out


def names(plugin: Path) -> tuple[set[str], set[str]]:
    """(skill names, agent names) of a plugin folder."""
    return ({p.parent.name for p in (plugin / "skills").glob("*/SKILL.md")},
            {p.stem for p in (plugin / "agents").glob("*.md")})


def frontmatter_issues(plugin: Path) -> list[tuple[Path, int, str]]:
    """Parse errors and required keys of every SKILL.md and agent; agent colours and `skills:` entries."""
    skills, _ = names(plugin)
    out = []
    for f in sorted((plugin / "skills").glob("*/SKILL.md")) + sorted((plugin / "agents").glob("*.md")):
        is_agent = f.parent.name == "agents"
        want = f.stem if is_agent else f.parent.name
        text = f.read_text(encoding="utf-8")
        at = {k: n for n, k in reversed(list(enumerate((ln.split(":", 1)[0] for ln in text.splitlines()), 1)))}
        try:
            fm = frontmatter(text)
        except ValueError as e:
            out.append((f, 1, str(e)))
            continue
        if fm.get("name") != want:
            out.append((f, at.get("name", 1), f"name {fm.get('name')!r} is not {want!r}"))
        if not isinstance(fm.get("description"), str) or not fm["description"].strip():
            out.append((f, at.get("description", 1), "description missing or not a string"))
        out += [(f, at.get(k, 1), m) for k, m in schema_issues("agent" if is_agent else "skill", fm)]
        if not is_agent:
            continue
        colour = fm.get("color")
        if colour not in COLOURS:
            out.append((f, at.get("color", 1), f"colour {colour!r} is not one of " + ", ".join(sorted(COLOURS))))
        listed = fm.get("skills") or []
        if not isinstance(listed, list) or not all(isinstance(s, str) for s in listed):
            out.append((f, at.get("skills", 1), f"skills: is not a list of names: {listed!r}"))
            continue
        for s in listed:
            if s.split(":", 1)[-1] not in skills or (":" in s and not s.startswith("whynot-cut:")):
                out.append((f, at.get("skills", 1), f"skills: entry {s!r} is not a whynot-cut skill"))
    return out


def text_files(plugin: Path) -> list[Path]:
    """Where commands and agent names are written for Claude and the editor: skills, agents, READMEs, evals."""
    files = sorted((plugin / "skills").rglob("*.md")) + sorted((plugin / "agents").glob("*.md"))
    files += [p for p in (plugin / "README.md", plugin.parent / "README.md") if p.is_file()]
    return files + sorted((plugin / "evals").rglob("*.md"))


REF = re.compile(r"(?<![\w-])whynot-cut:([a-z0-9][a-z0-9-]*)")
SUBAGENT = re.compile(r"subagent_type\W{0,6}whynot-cut:([a-z0-9][a-z0-9-]*)")     # must be an agent, a skill cannot run


def reference_issues(plugin: Path) -> list[tuple[Path, int, str]]:
    """Every `whynot-cut:<name>` (a subagent type or a /skill) names an agent or skill that exists; a `subagent_type`
    names an agent."""
    skills, agents = names(plugin)
    out = []
    for f in text_files(plugin):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for m in REF.finditer(line):
                if m.group(1) not in agents | skills:
                    out.append((f, n, f"whynot-cut:{m.group(1)} is no agent or skill"))
            for m in SUBAGENT.finditer(line):
                if m.group(1) in skills and m.group(1) not in agents:
                    out.append((f, n, f"whynot-cut:{m.group(1)} is a skill, not an agent: it cannot be a subagent_type"))
    return out


# ------------------------------------------------------------------------------------------------ the real parser
class _Built(Exception):
    pass


def real_parser() -> argparse.ArgumentParser:
    """The parser `cli.main` builds, caught at its parse_args (argv `serve` so serve's own options are added too)."""
    spec = importlib.util.spec_from_file_location("reel_cli_t38", SK / "engine/reel/cli.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    got = {}

    def grab(self, args=None, namespace=None):
        got["ap"] = self
        raise _Built

    with mock.patch.object(argparse.ArgumentParser, "parse_args", grab), mock.patch.dict(os.environ), \
            contextlib.redirect_stdout(io.StringIO()):
        try:
            m.main(["serve"])
        except _Built:
            pass
    return got["ap"]


def _choices(ap: argparse.ArgumentParser) -> dict[str, set[str]]:
    """option string (every alias) -> its allowed values, for options that take one value from a closed set."""
    return {o: {str(c) for c in a.choices} for o, a in ap._option_string_actions.items()
            if a.choices and a.nargs is None and a.option_strings}


class CLI:
    """What the parser accepts: top-level options, each command (aliases included) with its options and the choices
    of its first positional (serve's verb); commands that pass the rest through (py)."""
    def __init__(self, ap: argparse.ArgumentParser):
        self.top = set(ap._option_string_actions)
        sub = next(a for a in ap._actions if isinstance(a, argparse._SubParsersAction))
        self.commands: dict[str, set[str]] = {}
        self.choices: dict[str, dict[str, set[str]]] = {"": _choices(ap)}   # command ("" = top level) -> option -> values
        self.verbs: dict[str, set[str]] = {}
        self.passthrough: set[str] = set()
        for name, sp in sub.choices.items():
            self.commands[name] = set(sp._option_string_actions)
            self.choices[name] = _choices(sp)
            pos = [a for a in sp._actions if not a.option_strings and a.dest != "help"]
            if pos and pos[0].nargs == argparse.REMAINDER:
                self.passthrough.add(name)
            elif pos and pos[0].choices:
                self.verbs[name] = set(pos[0].choices)


REEL = re.compile(r"(?<![\w-])reel(?:\.cmd)?[\"']?(?=[ \t])")
STOP = re.compile(r"`|\s\|\s|;|&&|\|\||\s[—→]\s")
FLAG = re.compile(r"--[A-Za-z0-9][A-Za-z0-9-]*")
WORD = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
# fenced shell languages (json/markdown/text: data or prose) and the character that continues a line in each
CONT_BASH, CONT_PS, CONT_CMD = "\\", "`", "^"
SHELL_CONT = {"bash": (CONT_BASH,), "sh": (CONT_BASH,), "zsh": (CONT_BASH,),
              "powershell": (CONT_PS,), "pwsh": (CONT_PS,), "ps1": (CONT_PS,),
              "cmd": (CONT_CMD,), "bat": (CONT_CMD,), "batch": (CONT_CMD,),
              "": (CONT_BASH, CONT_PS, CONT_CMD), "shell": (CONT_BASH, CONT_PS, CONT_CMD),
              "console": (CONT_BASH, CONT_PS, CONT_CMD), "shell-session": (CONT_BASH, CONT_PS, CONT_CMD)}
SHELLS = set(SHELL_CONT)


def _clean(tok: str) -> str:
    return tok.lstrip("[(\"'").rstrip(".,:;)]\"'")


VALUE = re.compile(r"[a-z0-9][a-z0-9.-]*")        # a bare option value; <x>, a|b, NAME, … are placeholders


def logical_lines(text: str) -> list[tuple[int, str, str | None]]:
    r"""(first line number, text, fenced language or None) with a shell fence's continued lines joined: a line ending in
    a backslash (bash), a backtick (PowerShell) or ^ (cmd) continues on the next line, so "reel plan \" followed by
    "--bogus" is one command."""
    src = text.splitlines()
    out, fence, i = [], None, 0
    while i < len(src):
        line, n = src[i], i + 1
        i += 1
        if line.lstrip().startswith("```"):
            if fence is None:
                info = line.lstrip()[3:].split()
                fence = info[0].lower() if info else ""                 # "bash title=x" is a bash fence
            else:
                fence = None
            continue
        conts = SHELL_CONT.get(fence, ()) if fence is not None else ()
        while conts and line.rstrip().endswith(conts) and i < len(src) and not src[i].lstrip().startswith("```"):
            line = line.rstrip()[:-1] + " " + src[i]
            i += 1
        out.append((n, line, fence))
    return out


def reel_issues_in(text: str, cli: CLI) -> list[tuple[int, str]]:
    """Each `reel …` written in the text: the command exists (when written as code), every --flag up to the end of that
    command (a backtick, a pipe, ;, &&, an arrow) is an option of that command (or a global one before it), and a bare
    value after an option with closed choices (--by, --verdict, --hum, --model …) is one of them."""
    out = []
    for n, line, fence in logical_lines(text):
        for m in REEL.finditer(line):
            code = fence in SHELLS or (fence is None and line[:m.start()].count("`") % 2 == 1)
            rest = line[m.end():]
            stop = STOP.search(rest)
            toks = [_clean(t) for t in (rest[:stop.start()] if stop else rest).split()]
            i = 0
            while i < len(toks) and toks[i].startswith("--"):       # global options before the command
                flag = toks[i].split("=", 1)[0]
                if code and flag not in cli.top:                   # prose: "a reel --like this" is English
                    out.append((n, f"reel {flag}: no such global option"))
                i += 2 if flag in GLOBAL_VALUE_OPTS and "=" not in toks[i] else 1
            if i >= len(toks):
                continue
            cmd = toks[i]
            if cmd not in cli.commands:
                if code and WORD.fullmatch(cmd):
                    out.append((n, f"reel {cmd}: no such command"))
                continue
            if cmd in cli.passthrough:
                continue
            args = toks[i + 1:]
            if code and cmd in cli.verbs and args and WORD.fullmatch(args[0]) and args[0] not in cli.verbs[cmd]:
                out.append((n, f"reel {cmd} {args[0]}: not one of {', '.join(sorted(cli.verbs[cmd]))}"))
            for k, t in enumerate(args):
                f = FLAG.match(t)
                if not f:
                    continue
                if f.group(0) not in cli.commands[cmd]:
                    out.append((n, f"reel {cmd} {f.group(0)}: no such option"))
                    continue
                allowed = cli.choices[cmd].get(f.group(0))
                if allowed:
                    val = _clean(t.split("=", 1)[1]) if "=" in t else (args[k + 1] if k + 1 < len(args) else "")
                    if VALUE.fullmatch(val) and val not in allowed:
                        out.append((n, f"reel {cmd} {f.group(0)} {val}: not one of {', '.join(sorted(allowed))}"))
    return out


def reel_issues(plugin: Path, cli: CLI) -> list[tuple[Path, int, str]]:
    return [(f, n, msg) for f in text_files(plugin) for n, msg in reel_issues_in(f.read_text(encoding="utf-8"), cli)]


# ------------------------------------------------------------------------------------------------------------ tests
_CLI = None


def cli() -> CLI:
    global _CLI
    if _CLI is None:
        _CLI = CLI(real_parser())
    return _CLI


def rel(f: Path) -> str:
    try:
        return f.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return f.as_posix()


def unexpected(issues) -> list[str]:
    return [f"{rel(f)}:{n}: {msg}" for f, n, msg in issues if (rel(f), msg) not in KNOWN]


class YamlRequired(unittest.TestCase):
    def setUp(self):
        if yaml is None:
            self.fail("PyYAML is missing: it is in setup/locks/runtime-*.lock; run the suite with the engine runtime")


class TestRealParser(YamlRequired):
    """The introspection sees what `reel` really accepts (guards the guard)."""
    def test_commands_aliases_verbs_and_passthrough(self):
        c = cli()
        for name in ("doctor", "plan", "verify", "serve", "py", "reels-select", "motion-plan"):
            self.assertIn(name, c.commands)
        self.assertEqual(c.verbs["serve"], {"ensure", "status", "stop", "run"})
        self.assertIn("py", c.passthrough)
        self.assertIn("--notes", c.commands["verify"])               # an alias spelling
        self.assertIn("--root", c.commands["plan"])                  # globals after the command
        self.assertTrue({"--root", "--version", "--episode"} <= c.top)
        self.assertGreater(len(c.commands["serve"]), 6)              # serve's daemon options were added


class TestFrontmatter(YamlRequired):
    def test_repo_frontmatter_parses_with_valid_colours_and_skills(self):
        self.assertEqual(unexpected(frontmatter_issues(SK)), [])

    def test_seeded_bad_frontmatter_fails(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)
            (p / "skills/good").mkdir(parents=True)
            (p / "agents").mkdir()
            (p / "skills/good/SKILL.md").write_text('---\nname: good\ndescription: "ok"\n---\n', encoding="utf-8")
            (p / "skills/broken").mkdir()
            (p / "skills/broken/SKILL.md").write_text('---\nname: broken\ndescription: "unclosed\n---\n',
                                                      encoding="utf-8")
            (p / "agents/painter.md").write_text("---\nname: painter\ndescription: x\ncolor: magenta\n"
                                                 "skills:\n  - good\n  - whynot-cut:good\n  - missing-craft\n---\n",
                                                 encoding="utf-8")
            msgs = [m for _, _, m in frontmatter_issues(p)]
        self.assertTrue(any(m.startswith("frontmatter is not valid YAML") for m in msgs), msgs)
        self.assertIn("colour 'magenta' is not one of blue, cyan, green, orange, pink, purple, red, yellow", msgs)
        self.assertIn("skills: entry 'missing-craft' is not a whynot-cut skill", msgs)
        self.assertEqual(len(msgs), 3, msgs)                         # the good skill and both good entries pass

    def test_seeded_unknown_keys_and_wrong_types_fail(self):
        def run(kind, body):
            with tempfile.TemporaryDirectory() as t:
                p = Path(t)
                (p / "skills/s").mkdir(parents=True)
                (p / "agents").mkdir()
                if kind == "agent":
                    (p / "agents/a.md").write_text(f"---\nname: a\ndescription: x\ncolor: red\n{body}---\n",
                                                   encoding="utf-8")
                else:
                    (p / "skills/s/SKILL.md").write_text(f"---\nname: s\ndescription: x\n{body}---\n",
                                                         encoding="utf-8")
                return sorted(m for _, _, m in frontmatter_issues(p))
        add = "add it to KNOWN_KEYS if Claude Code supports it"
        # a good agent and a good skill using the newer keys pass
        self.assertEqual(run("agent", "tools: Read, Grep\ndisallowedTools: [Bash]\nmodel: inherit\nmaxTurns: 8\n"
                                      "effort: high\nomitClaudeMd: true\n"), [])
        self.assertEqual(run("skill", "user-invocable: false\nallowed-tools: Bash(reel *)\nargument-hint: x\n"), [])
        # typos: Claude Code would ignore them silently
        self.assertEqual(run("agent", "maxTurn: 8\ndisallowedtools: Bash\n"),
                         [f"unknown agent frontmatter key 'disallowedtools': {add}",
                          f"unknown agent frontmatter key 'maxTurn': {add}"])
        self.assertEqual(run("skill", "user-invokable: false\n"),
                         [f"unknown skill frontmatter key 'user-invokable': {add}"])
        # a skill key is not an agent key and the other way round
        self.assertEqual(run("agent", "allowed-tools: Read\n"),
                         [f"unknown agent frontmatter key 'allowed-tools': {add}"])
        self.assertEqual(run("skill", "tools: Read\n"), [f"unknown skill frontmatter key 'tools': {add}"])
        # documented but ignored in plugin agents
        self.assertEqual(run("agent", "permissionMode: plan\n"),
                         ["frontmatter key 'permissionMode' is ignored in plugin agents (Claude Code does not honour "
                          "it there)"])
        # wrong types and values
        self.assertEqual(run("agent", 'maxTurns: "8"\n'),
                         ["agent frontmatter maxTurns: expected an integer greater than 0, got '8'"])
        self.assertEqual(run("agent", "maxTurns: 0\n"),
                         ["agent frontmatter maxTurns: expected an integer greater than 0, got 0"])
        self.assertEqual(run("agent", "omitClaudeMd: yes please\n"),
                         ["agent frontmatter omitClaudeMd: expected true or false, got 'yes please'"])
        self.assertEqual(run("agent", "model: gpt-5\n"),
                         ["agent frontmatter model: expected inherit, sonnet, opus, haiku, fable or a full model id "
                          "(claude-…), got 'gpt-5'"])
        self.assertEqual(run("agent", "effort: huge\n"),
                         ["agent frontmatter effort: expected one of low, medium, high, xhigh, max, got 'huge'"])
        self.assertEqual(run("agent", "tools: [Read, 3]\n"),
                         ["agent frontmatter tools: expected a string or a list of strings, got ['Read', 3]"])
        self.assertEqual(run("skill", 'user-invocable: "false"\n'),
                         ["skill frontmatter user-invocable: expected true or false, got 'false'"])


class TestReferences(YamlRequired):
    def test_repo_references_exist(self):
        self.assertEqual(unexpected(reference_issues(SK)), [])

    def test_seeded_missing_agent_fails(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)
            (p / "skills/edit").mkdir(parents=True)
            (p / "agents").mkdir()
            (p / "skills/edit/SKILL.md").write_text("Fan out whynot-cut:qc-reviewer, then /whynot-cut:edit.\n",
                                                    encoding="utf-8")
            (p / "agents/story-editor.md").write_text("Ask whynot-cut:frame-inspectr and whynot-cut:story-editor.\n",
                                                      encoding="utf-8")
            msgs = sorted(m for _, _, m in reference_issues(p))
        self.assertEqual(msgs, ["whynot-cut:frame-inspectr is no agent or skill",
                                "whynot-cut:qc-reviewer is no agent or skill"])

    def test_seeded_skill_used_as_subagent_type_fails(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)
            (p / "skills/edit").mkdir(parents=True)
            (p / "agents").mkdir()
            (p / "agents/qc-reviewer.md").write_text("x\n", encoding="utf-8")
            (p / "skills/edit/SKILL.md").write_text("\n".join([
                'Agent(subagent_type="whynot-cut:edit", prompt="x")',            # a skill: cannot run as a subagent
                "subagent_type: whynot-cut:qc-reviewer",                          # an agent: fine
                "Run /whynot-cut:edit, or whynot-cut:qc-reviewer.",              # a skill by name: fine
            ]) + "\n", encoding="utf-8")
            msgs = [(n, m) for _, n, m in reference_issues(p)]
        self.assertEqual(msgs, [(1, "whynot-cut:edit is a skill, not an agent: it cannot be a subagent_type")])


class TestReelFlags(YamlRequired):
    def test_repo_reel_commands_and_flags_exist(self):
        self.assertEqual(unexpected(reel_issues(SK, cli())), [])

    def test_seeded_unknown_flag_command_and_verb_fail(self):
        text = "\n".join([
            "Run `reel plan --root X --force` then `reel --root X next`.",          # --force: not a plan option
            "```bash",
            "reel transcribe --model large-v3 --langauge ar",                       # typo
            'reel verify --record --verdict pass --notes "ok" | tee x --bogus',     # after the pipe: not reel's
            "reel frobnicate --x",                                                  # no such command
            "reel serve start",                                                     # not a serve verb
            "reel serve ensure --foreground",
            "reel py -c 'print(1)' --anything",                                     # passthrough
            "reel --rooot X doctor",                                                # bad global option
            "```",
            "Make a reel --like this one, and reel plan --nope in prose.",          # prose: known command checked
            "```json",
            '{"reason": "this reel is a list", "x": "reel next --oops"}',           # data, not a shell
            "```",
        ])
        msgs = [f"{n}: {m}" for n, m in reel_issues_in(text, cli())]
        self.assertEqual(msgs, ["1: reel plan --force: no such option",
                                "3: reel transcribe --langauge: no such option",
                                "5: reel frobnicate: no such command",
                                "6: reel serve start: not one of ensure, run, status, stop",
                                "9: reel --rooot: no such global option",
                                "11: reel plan --nope: no such option",
                                "13: reel next --oops: no such option"])


    def test_seeded_continuation_lines_are_joined(self):
        text = "\n".join([
            "```bash",
            "reel plan \\",                        # 2: bash continuation, the bad flag is on line 4
            "  --root X \\",
            "  --bogus",
            "reel verify --record \\",             # 5: fine when joined
            "  --verdict pass",
            "```",
            "```powershell",
            "reel plan `",                         # 9: PowerShell backtick
            "  --bogus2",
            "reel `",                              # 11: the command is on the next line
            "  plan --bogus3",
            "```",
            "```cmd",
            "reel plan ^",                         # 15: cmd caret
            "  --bogus4",
            "```",
            "```zsh",
            "reel plan \\",                        # 19: zsh is a shell fence too
            "  --bogus5",
            "```",
            "```bash",
            "reel plan",                           # 23: no continuation: the next line is not part of it
            "--bogus6",
            "```",
            "```bash",
            "echo done \\",                        # a continuation never runs into the fence close
            "```",
            "reel next --prose",                   # 29: prose after the fence
        ])
        msgs = [f"{n}: {m}" for n, m in reel_issues_in(text, cli())]
        self.assertEqual(msgs, ["2: reel plan --bogus: no such option",
                                "9: reel plan --bogus2: no such option",
                                "11: reel plan --bogus3: no such option",
                                "15: reel plan --bogus4: no such option",
                                "19: reel plan --bogus5: no such option",
                                "29: reel next --prose: no such option"])

    def test_seeded_option_values_quoting_and_fence_labels(self):
        text = "\n".join([
            "Run `reel approve-plan --by robot` and `reel approve-plan --by=editor`.",      # 1: --by robot
            "```bash title=run.sh",
            "reel verify --record --verdict maybe",                                       # 3: bad value
            "reel transcribe --model large-v3 --hum 55",                                    # 4: --hum is not transcribe's
            "reel approve-plan --by <editor|delegated>",                                    # 5: placeholder: skipped
            "reel approve-plan --by editor|delegated",                                      # 6: placeholder: skipped
            "```",
            "```shell-session",
            "$ reel frobnicate",                                                           # 9: no such command
            "```",
            "```batch",
            "reel frobnicate2",                                                           # 12: no such command
            "```",
            "& '${CLAUDE_PLUGIN_ROOT}/bin/reel.cmd' plan --bogus",                          # 14: single-quoted path
            "& '${CLAUDE_PLUGIN_ROOT}/bin/reel' plan --bogus2",                             # 15
        ])
        msgs = [f"{n}: {m}" for n, m in reel_issues_in(text, cli())]
        self.assertEqual(msgs, ["1: reel approve-plan --by robot: not one of delegated, editor",
                                "3: reel verify --verdict maybe: not one of fail, pass",
                                "4: reel transcribe --hum: no such option",
                                "9: reel frobnicate: no such command",
                                "12: reel frobnicate2: no such command",
                                "14: reel plan --bogus: no such option",
                                "15: reel plan --bogus2: no such option"])


class TestAllowList(YamlRequired):
    def test_allow_list_has_no_stale_entries(self):
        live = {(rel(f), m) for f, _, m in frontmatter_issues(SK) + reference_issues(SK) + reel_issues(SK, cli())}
        stale = sorted(k for k in KNOWN if k not in live)
        self.assertEqual(stale, [], "fixed: remove these KNOWN entries")


if __name__ == "__main__":
    unittest.main()
