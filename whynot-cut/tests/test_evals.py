"""3.0 T3.7 — the `claude plugin eval` suite (evals/) is well formed, so `claude plugin eval whynot-cut --scaffold` can
run every case: each case has a case.yaml (schema_version, name = folder, runs >= 3, context.scaffold_script inside the
case), a prompt.md whose frontmatter uses only keys the runner accepts, a `tool_used: Skill` grader
(graders/skill-fired.md) that names real whynot-cut skills (or forbids them, for should-not-trigger cases), regex graders
that compile and whose `reel <cmd> --flag` names a real command and option of the REAL parser (test_structure), a
scaffold that only sources the shared fictional fixture, a "Gate 0/1/2" jargon check in every editor-facing case, and
no real client name in the case files (test_plugin's TestShippedProfiles token list; its own scan skips .yaml/.sh).

Key sets mirror the runner's schema in CLI 2.1.295 (`claude plugin eval`; checked against the bundled binary, T3.7
evidence doc). The cases themselves are run with the CLI (needs login), not here.
Run:  bash tools/test.sh -p test_evals.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import test_structure as ts

SK = Path(__file__).resolve().parents[1]
NOT_CASES = {"_fixtures", "mocks", "results"}
CASE_KEYS = {"schema_version", "name", "description", "tags", "plugins", "context", "execution", "runs", "graders",
             "expected_outcome"}
CONTEXT_KEYS = {"scaffold_script", "history_file", "add_dirs"}
PROMPT_KEYS = {"schema_version", "name", "description", "tags", "plugins", "runs", "expected_outcome", "model",
               "max_turns", "timeout_seconds", "allowed_tools", "artifact_publish", "growthbook_overrides",
               "append_system_prompt", "env"}
GRADER_KEYS = {"regex": {"type", "target", "pattern", "flags", "match", "weight", "arm"},
               "tool_order": {"type", "before", "after", "weight", "arm"},
               "tool_used": {"type", "tool", "input_match", "min", "max", "weight", "arm"},
               "file_exists": {"type", "path", "exists", "weight", "arm"},
               "llm": {"type", "criteria", "focus", "weight", "arm"},
               "baseline": {"type", "baseline_file", "criteria", "weight", "arm"}}
FIXTURE_FUNCS = {"make_clinic", "add_references", "add_project", "add_episode_plan", "add_panel_approval", "add_approved_reels",
                 "add_motion_project", "make_hugo_site", "add_review_case", "add_big_transcript"}
SOURCE_LINE = '. "${here%/*}/../_fixtures/example-clinic.sh"'
# a reel command written in a regex grader: reel, reel.cmd or reel(?:\.cmd)?, whitespace, then a word or (?:a|b)
REEL_IN_REGEX = re.compile(r"reel(?:\(\?:\\\.cmd\)\?|\.cmd)?(?:\[\\\"'\]\?|\[\"'\]\?)?(?:\\s\+|\\s\*| )"
                           r"(?:\(\?:([a-z|-]+)\)|([a-z][a-z0-9-]*))")
FLAG_IN_REGEX = re.compile(r"--([a-z][a-z0-9-]*)(?:(?:\[ =\]|=| )([a-z][a-z0-9-]*))?")
SKILL_ALT = re.compile(r'\(\?:whynot-cut:\)\?\(\?:([a-z|-]+)\)')


def yaml_load(text: str):
    return ts.yaml.safe_load(text)


def split_md(text: str) -> tuple[dict, str]:
    fm = ts.frontmatter(text)
    lines = text.splitlines()
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    return fm, "\n".join(lines[end + 1:]).strip()


def cases(plugin: Path) -> list[Path]:
    return sorted(d for d in (plugin / "evals").iterdir() if d.is_dir() and d.name not in NOT_CASES)


def case_issues(plugin: Path, cli: "ts.CLI") -> list[tuple[str, str]]:
    skills, _agents = ts.names(plugin)
    out = []
    for d in cases(plugin):
        n = d.name
        cy = d / "case.yaml"
        if not cy.is_file():
            out.append((n, "no case.yaml"))
            continue
        c = yaml_load(cy.read_text(encoding="utf-8")) or {}
        out += [(n, f"case.yaml: unknown key {k!r}") for k in set(c) - CASE_KEYS]
        if str(c.get("schema_version", "")).split(".")[0] != "1":
            out.append((n, "case.yaml: schema_version must be 1.x"))
        if c.get("name") != n:
            out.append((n, f"case.yaml: name {c.get('name')!r} is not the folder name"))
        if not isinstance(c.get("runs"), int) or c["runs"] < 3:
            out.append((n, "case.yaml: runs must be >= 3"))
        ctx = c.get("context") or {}
        out += [(n, f"case.yaml: unknown context key {k!r}") for k in set(ctx) - CONTEXT_KEYS]
        sc = ctx.get("scaffold_script")
        if sc != "scaffold.sh" or not (d / "scaffold.sh").is_file():
            out.append((n, "context.scaffold_script must be scaffold.sh inside the case"))
        else:
            body = [ln.strip() for ln in (d / "scaffold.sh").read_text(encoding="utf-8").splitlines()]
            if SOURCE_LINE not in body:
                out.append((n, "scaffold.sh does not source ../_fixtures/example-clinic.sh"))
            for ln in body:
                if ln.startswith(". ") and ln != SOURCE_LINE:
                    out.append((n, f"scaffold.sh sources something other than the fixture: {ln!r}"))
                elif ln and not ln.startswith(("#", "here=", ". ")) and ln.split()[0] not in FIXTURE_FUNCS:
                    out.append((n, f"scaffold.sh: {ln.split()[0]!r} is not a fixture function"))
        pm = d / "prompt.md"
        if not pm.is_file():
            out.append((n, "no prompt.md"))
        else:
            fm, body = split_md(pm.read_text(encoding="utf-8"))
            out += [(n, f"prompt.md: unknown frontmatter key {k!r}") for k in set(fm) - PROMPT_KEYS]
            if not body:
                out.append((n, "prompt.md: empty prompt"))
            tools = fm.get("allowed_tools") or []
            if "Skill" not in tools:
                out.append((n, "prompt.md: allowed_tools lacks Skill"))
        gs = {g.stem: g for g in sorted((d / "graders").glob("*.md"))} if (d / "graders").is_dir() else {}
        if "skill-fired" not in gs:
            out.append((n, "no graders/skill-fired.md"))
        elif split_md(gs["skill-fired"].read_text(encoding="utf-8"))[0].get("max") != 0 and "no-gate-jargon" not in gs:
            out.append((n, "no graders/no-gate-jargon.md (every editor-facing case checks for Gate 0/1/2)"))
        if not any(split_md(g.read_text(encoding="utf-8"))[0].get("type") == "llm" for g in gs.values()):
            out.append((n, "no outcome (llm) grader"))
        for gname, g in gs.items():
            fm, body = split_md(g.read_text(encoding="utf-8"))
            t = fm.get("type")
            if t not in GRADER_KEYS:
                out.append((n, f"{gname}: unknown grader type {t!r}"))
                continue
            out += [(n, f"{gname}: unknown key {k!r}") for k in set(fm) - GRADER_KEYS[t]]
            if gname == "skill-fired":
                out += skill_grader_issues(n, fm, skills)
            if t == "regex":
                out += regex_issues(n, gname, body, cli)
    return out


def skill_grader_issues(n: str, fm: dict, skills: set) -> list[tuple[str, str]]:
    if fm.get("type") != "tool_used" or fm.get("tool") != "Skill" or not fm.get("input_match"):
        return [(n, "skill-fired: must be type tool_used, tool Skill, with input_match")]
    im = fm["input_match"]
    try:
        re.compile(im)
    except re.error as e:
        return [(n, f"skill-fired: input_match does not compile: {e}")]
    if fm.get("max") == 0:                         # should-not-trigger: no whynot-cut skill at all, scored in both arms
        ok = fm.get("min") == 0 and fm.get("arm") == "both" and "whynot-cut:" in im
        return [] if ok else [(n, "skill-fired (negative): needs min 0, max 0, arm both and a whynot-cut: match")]
    m = SKILL_ALT.search(im)
    if not m:
        return [] if "[a-z][a-z-]*" in im else [(n, "skill-fired: input_match names no skill")]
    return [(n, f"skill-fired: {s!r} is not a whynot-cut skill") for s in m.group(1).split("|") if s not in skills]


def regex_issues(n: str, gname: str, pattern: str, cli: "ts.CLI") -> list[tuple[str, str]]:
    try:
        re.compile(pattern)
    except re.error as e:
        return [(n, f"{gname}: pattern does not compile: {e}")]
    out = []
    for m in REEL_IN_REGEX.finditer(pattern):
        cmds = (m.group(1) or m.group(2)).split("|")
        for cmd in cmds:
            if cmd not in cli.commands:
                out.append((n, f"{gname}: reel {cmd}: no such command"))
                continue
            for f, val in FLAG_IN_REGEX.findall(pattern[m.end():]):
                if f"--{f}" not in cli.commands[cmd]:
                    out.append((n, f"{gname}: reel {cmd} --{f}: no such option"))
                allowed = cli.choices[cmd].get(f"--{f}")
                if allowed and val and val not in allowed:
                    out.append((n, f"{gname}: reel {cmd} --{f} {val}: not one of {', '.join(sorted(allowed))}"))
    return out


class TestEvalSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cli = ts.CLI(ts.real_parser())

    def test_every_case_is_well_formed(self):
        self.assertEqual(case_issues(SK, self.cli), [])

    def test_no_real_client_name_in_any_case_file(self):
        from test_plugin import TestShippedProfiles
        tokens = TestShippedProfiles("test_no_real_client_name_in_the_product").real_client_tokens
        hits = [(f.relative_to(SK).as_posix(), tokens(f.read_text(encoding="utf-8")))
                for f in sorted((SK / "evals").rglob("*")) if f.is_file() and "results" not in f.parts]
        self.assertEqual([h for h in hits if h[1]], [])

    def test_suite_has_the_6_2_cases(self):
        have = {d.name for d in cases(SK)}
        for want in ("negative-hugo-assets", "edit-arabic-only", "revise-arabic-only", "status-arabic-only",
                     "fix-audio-only", "handoff-for-editor", "help-cheat-sheet", "preferences-stop-asking",
                     "new-client-reference-style", "transcript-words-to-confirm", "medical-religious-approvals",
                     "motion-revision", "wrong-reel-on-path", "gate0-delegation", "magnific-broll-pending",
                     "panel-approval-sessionstart"):
            self.assertIn(want, have)
        negatives = [d.name for d in cases(SK)
                     if split_md((d / "graders/skill-fired.md").read_text(encoding="utf-8"))[0].get("max") == 0]
        self.assertTrue(negatives, "at least one should-not-trigger case")

    def test_suite_has_the_phase_4_cases(self):                # S6b: a positive and a plausible-wrong-trigger case each
        have = {d.name for d in cases(SK)}
        for want in ("rules-standing-comment", "rules-process-comment-refused",                       # T4.3
                     "episode-sheet-before-episode", "episode-sheet-already-there",                   # T4.4
                     "autopilot-approval-auto", "autopilot-auto-never-picks-reels",                   # T4.7
                     "motion-music-no-licence", "motion-music-said-licensed",                         # T4.6
                     "claims-check-scan-first", "claims-check-scan-not-a-filter"):                    # edit stage 7
            self.assertIn(want, have)
            tags = set(yaml_load((SK / "evals" / want / "case.yaml").read_text(encoding="utf-8")).get("tags") or [])
            self.assertEqual(len(tags & {"positive", "negative"}), 1, want)
        # a plain look-up is rightly answered from the sheet without a skill (S6b run 1): record-only, not scored
        fm, _ = split_md((SK / "evals/episode-sheet-already-there/graders/skill-fired.md").read_text(encoding="utf-8"))
        self.assertEqual(fm.get("min"), 0)

    def test_platform_parity(self):                            # G3 review M13: macOS is primary (G11)
        tags = {d.name: set(yaml_load((d / "case.yaml").read_text(encoding="utf-8")).get("tags") or [])
                for d in cases(SK)}
        self.assertTrue([n for n, t in tags.items() if "windows" in t])
        mac = [n for n, t in tags.items() if "macos" in t]
        self.assertIn("macos-bridge-files-access", mac)
        g = SK / "evals/macos-bridge-files-access/graders"
        self.assertIn("defaults write", (g / "player-debug-mode.md").read_text(encoding="utf-8"))
        self.assertIn("Files (?:and|&) Folders", (g / "files-and-folders.md").read_text(encoding="utf-8"))

    def test_fixture_is_fictional_and_generates_clips_with_ffmpeg(self):
        sh = (SK / "evals/_fixtures/example-clinic.sh").read_text(encoding="utf-8")
        self.assertIn("testsrc=", sh)
        self.assertIn("sine=", sh)
        for f in FIXTURE_FUNCS:
            self.assertRegex(sh, rf"(?m)^{f}\(\)")
        self.assertFalse((SK / "evals/_fixtures/prompt.md").exists() or (SK / "evals/_fixtures/case.yaml").exists())

    def test_local_eval_results_never_ship(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("package_t37", SK.parent / "package.py")
        pkg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pkg)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            res = root / "whynot-cut/evals/results/2026-10-13/aggregate-result.json"
            case = root / "whynot-cut/evals/help-cheat-sheet/prompt.md"
            for f in (res, case):
                f.parent.mkdir(parents=True)
                f.write_text("x", encoding="utf-8")
            self.assertFalse(pkg.wanted(res, root))
            self.assertTrue(pkg.wanted(case, root))
        self.assertIn("evals/results/", (SK.parent / ".gitignore").read_text(encoding="utf-8"))

    def test_checks_catch_seeded_mistakes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "whynot-cut"
            for sub in ("skills", "agents", "evals"):
                shutil.copytree(SK / sub, p / sub, ignore=shutil.ignore_patterns("results", "__pycache__"))
            g = p / "evals/gate0-delegation/graders"
            (g / "delegated-pick.md").write_text(
                "---\ntype: regex\nmatch: contains\n---\n\nreel(?:\\.cmd)?\\s+reels-select[^\\n]*--by[ =]boss --bogus\n",
                encoding="utf-8")
            (g / "skill-fired.md").write_text(
                "---\ntype: tool_used\ntool: Skill\ninput_match: '\"skill\"\\s*:\\s*\"(?:whynot-cut:)?(?:podcastz)\"'\n---\n",
                encoding="utf-8")
            (p / "evals/help-cheat-sheet/case.yaml").write_text(
                'schema_version: "1.1"\nname: other\nruns: 1\ncontext:\n  scaffold_script: ../x.sh\n', encoding="utf-8")
            (p / "evals/fix-audio-only/prompt.md").write_text("---\nmax_turns: 3\nturns: 2\n---\n\nhi\n",
                                                              encoding="utf-8")
            (p / "evals/handoff-for-editor/scaffold.sh").write_text("#!/usr/bin/env bash\nrm -rf /\n", encoding="utf-8")
            sc = p / "evals/status-arabic-only/scaffold.sh"
            sc.write_text(sc.read_text(encoding="utf-8") + ". ../../evil.sh\n", encoding="utf-8")
            (p / "evals/preview-before-premiere/graders/no-gate-jargon.md").unlink()
            got = {m for _, m in case_issues(p, self.cli)}
            for want in ("delegated-pick: reel reels-select --by boss: not one of delegated, editor",
                         "delegated-pick: reel reels-select --bogus: no such option",
                         "skill-fired: 'podcastz' is not a whynot-cut skill",
                         "case.yaml: name 'other' is not the folder name", "case.yaml: runs must be >= 3",
                         "context.scaffold_script must be scaffold.sh inside the case",
                         "prompt.md: unknown frontmatter key 'turns'", "prompt.md: allowed_tools lacks Skill",
                         "scaffold.sh does not source ../_fixtures/example-clinic.sh",
                         "scaffold.sh: 'rm' is not a fixture function",
                         "scaffold.sh sources something other than the fixture: '. ../../evil.sh'",
                         "no graders/no-gate-jargon.md (every editor-facing case checks for Gate 0/1/2)"):
                self.assertIn(want, got)


if __name__ == "__main__":
    unittest.main()
