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


def reference_issues(plugin: Path) -> list[tuple[Path, int, str]]:
    """Every `whynot-cut:<name>` (a subagent type or a /skill) names an agent or skill that exists."""
    skills, agents = names(plugin)
    out = []
    for f in text_files(plugin):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for m in REF.finditer(line):
                if m.group(1) not in agents | skills:
                    out.append((f, n, f"whynot-cut:{m.group(1)} is no agent or skill"))
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


class CLI:
    """What the parser accepts: top-level options, each command (aliases included) with its options and the choices
    of its first positional (serve's verb); commands that pass the rest through (py)."""
    def __init__(self, ap: argparse.ArgumentParser):
        self.top = set(ap._option_string_actions)
        sub = next(a for a in ap._actions if isinstance(a, argparse._SubParsersAction))
        self.commands: dict[str, set[str]] = {}
        self.verbs: dict[str, set[str]] = {}
        self.passthrough: set[str] = set()
        for name, sp in sub.choices.items():
            self.commands[name] = set(sp._option_string_actions)
            pos = [a for a in sp._actions if not a.option_strings and a.dest != "help"]
            if pos and pos[0].nargs == argparse.REMAINDER:
                self.passthrough.add(name)
            elif pos and pos[0].choices:
                self.verbs[name] = set(pos[0].choices)


REEL = re.compile(r"(?<![\w-])reel(?:\.cmd)?\"?(?=[ \t])")
STOP = re.compile(r"`|\s\|\s|;|&&|\|\||\s[—→]\s")
FLAG = re.compile(r"--[A-Za-z0-9][A-Za-z0-9-]*")
WORD = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
SHELLS = {"", "bash", "sh", "shell", "console", "powershell", "pwsh", "ps1", "cmd", "bat"}  # json/markdown: prose


def _clean(tok: str) -> str:
    return tok.lstrip("[(\"'").rstrip(".,:;)]\"'")


def reel_issues_in(text: str, cli: CLI) -> list[tuple[int, str]]:
    """Each `reel …` written in the text: the command exists (when written as code), and every --flag up to the end of
    that command (a backtick, a pipe, ;, &&, an arrow) is an option of that command (or a global one before it)."""
    out = []
    fence = None                                    # the open fenced block's language, "" when it has none
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fence = line.lstrip()[3:].strip().lower() if fence is None else None
            continue
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
            for t in args:
                f = FLAG.match(t)
                if f and f.group(0) not in cli.commands[cmd]:
                    out.append((n, f"reel {cmd} {f.group(0)}: no such option"))
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


class TestAllowList(YamlRequired):
    def test_allow_list_has_no_stale_entries(self):
        live = {(rel(f), m) for f, _, m in frontmatter_issues(SK) + reference_issues(SK) + reel_issues(SK, cli())}
        stale = sorted(k for k in KNOWN if k not in live)
        self.assertEqual(stale, [], "fixed: remove these KNOWN entries")


if __name__ == "__main__":
    unittest.main()
