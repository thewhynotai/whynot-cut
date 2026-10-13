"""3.0 T3.1 + T3.2 — what the skill texts must say (and must not say) to the editor and to Claude.

- User-facing skills never call the stops "Gate 0/1/2": the editor hears "pick the reels / approve the plan / proof
  check". The internal names may appear only in a paragraph that says it is internal (the mapping for engine messages).
- No release-label appendices ("## Motion mode (2.2)", "(2.1)"): folded into the main text.
- Trigger overlaps settled: fix-audio = one audio-only request; revise = a list of 2+ comments or any non-audio one; the
  app rule (Clip edits → Premiere. Motion videos → After Effects. AE/PS for clip graphics → only on request) in edit,
  motion and adobe-extras.
- Every bash full-path `"${CLAUDE_PLUGIN_ROOT}/bin/reel"` has the PowerShell `& "${CLAUDE_PLUGIN_ROOT}/bin/reel.cmd"`
  next to it; own references use ${CLAUDE_SKILL_DIR}, cross references ${CLAUDE_PLUGIN_ROOT}/skills/…
- `reel doctor` guard_active: false is a stop item in start, setup and edit.
- Edit stages are numbered 1…12 in execution order (no 3b/7b/8b, no 13).
- T3.2: revise has the motion route (motion-director → motion-plan → motion-animatic → approval → ae-builder
  motion-build --replace-edited → render/frames → qc-reviewer); podcast runs the medical-reviewer for religious clients.
Run:  bash tools/test.sh -p test_skill_text.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import re
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
SKILLS = SK / "skills"


def text(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def user_facing() -> list[str]:
    return sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md")
                  if not re.search(r"^user-invocable:\s*false\s*$", p.read_text(encoding="utf-8"), re.M))


def paragraphs(s: str) -> list[tuple[int, str]]:
    """(first line number, paragraph) — blank lines and table rows/headings end a paragraph."""
    out, cur, start = [], [], 0
    for n, line in enumerate(s.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith(("#", "|", "```")):
            if cur:
                out.append((start, "\n".join(cur)))
            cur = []
            if line.strip():
                out.append((n, line))
            continue
        if not cur:
            start = n
        cur.append(line)
    if cur:
        out.append((start, "\n".join(cur)))
    return out


GATE = re.compile(r"\bGate\s*[012]\b")


def gate_word_issues(s: str) -> list[str]:
    return [f"line {n}: {p.splitlines()[0][:90]}" for n, p in paragraphs(s)
            if GATE.search(p) and "internal" not in p.lower()]


class TestGateWords(unittest.TestCase):
    def test_user_facing_skills_say_pick_approve_proof(self):
        names = user_facing()
        self.assertIn("edit", names)
        self.assertNotIn("story-craft", names)
        bad = {n: gate_word_issues(text(n)) for n in names}
        self.assertEqual({n: v for n, v in bad.items() if v}, {})

    def test_the_mapping_is_written_once_where_engine_messages_need_it(self):
        for n in ("edit", "podcast", "motion"):
            s = text(n)
            self.assertRegex(s, r"(?is)internal.{0,200}Gate 0\s*=\s*\**pick the reels", n)
            self.assertRegex(s, r"(?is)Gate 1\s*=\s*\**approve the plan", n)

    def test_the_grep_catches_a_bare_gate_word(self):
        self.assertTrue(gate_word_issues("## 2. Gate 1: approval\nShow the plan.\n"))
        self.assertTrue(gate_word_issues("Stop at Gate 0 and wait.\n"))
        self.assertFalse(gate_word_issues("Internal names: Gate 0 = pick the reels.\n"))
        self.assertFalse(gate_word_issues("Approve the plan, then build.\n"))


class TestFoldedAppendices(unittest.TestCase):
    def test_no_release_label_sections(self):
        bad = [f"{p.relative_to(SK)}:{n}" for p in sorted(SKILLS.rglob("*.md"))
               for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
               if re.search(r"\(2\.[0-9]\)", line)]
        self.assertEqual(bad, [])

    def test_help_table_lists_motion(self):
        s = text("help")
        table = [ln for ln in s.splitlines() if ln.startswith("|")]
        self.assertTrue(any("/whynot-cut:motion" in ln for ln in table))
        self.assertRegex(table[0], "[؀-ۿ]")          # an Arabic word in the table header


class TestRouting(unittest.TestCase):
    RULE = "Clip edits → Premiere. Motion videos → After Effects. AE/PS for clip graphics →"

    def test_app_rule_stated_in_edit_motion_adobe_extras(self):
        for n in ("edit", "motion", "adobe-extras"):
            self.assertTrue(self.RULE in " ".join(text(n).split()), f"{n}: the app rule is missing")

    def test_fix_audio_and_revise_point_at_each_other(self):
        fa, rv = text("fix-audio"), text("revise")
        self.assertIn("/whynot-cut:revise", fa)
        self.assertRegex(fa, r"(?i)two or more comments")
        self.assertIn("/whynot-cut:fix-audio", rv)
        self.assertRegex(rv, r"(?i)only about the dialogue audio")

    def test_motion_description_does_not_claim_after_effects_requests(self):
        desc = re.search(r"^description:\s*(.*)$", text("motion"), re.M).group(1)
        self.assertNotIn("build it in After Effects", desc)

    def test_fix_audio_defers_to_audio_craft_for_what_audio_clean_does(self):
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/skills/audio-craft/SKILL.md", text("fix-audio"))


class TestMotionAndReligiousRoutes(unittest.TestCase):
    """T3.2."""
    def test_revise_has_the_motion_route(self):
        s = text("revise")
        sec = s[s.index("## Motion videos"):]
        for word in ("_MO", "motion-director", "reel motion-plan", "reel motion-animatic", "reel approve-plan",
                     "ae-builder", "reel motion-build --replace-edited", "reel motion-render", "reel motion-frames",
                     "qc-reviewer", "reel verify --record", "reel qc"):
            self.assertIn(word, sec, word)
        self.assertNotIn("ppro-build", sec.replace("never with `ppro-build`", ""))
        order = [sec.index(w) for w in ("reel motion-plan", "reel approve-plan", "reel motion-build",
                                         "reel motion-render", "qc-reviewer` checks")]
        self.assertEqual(order, sorted(order))

    def test_podcast_runs_the_medical_reviewer_for_religious_clients(self):
        s = " ".join(text("podcast").split())
        self.assertRegex(s, r"medical-reviewer runs for `domain: medical` \*\*and\*\* `domain: religious`")
        self.assertNotIn("runs only for a medical client", s)


class TestPathsAndShells(unittest.TestCase):
    def test_every_bash_full_path_has_the_powershell_form_next_to_it(self):
        bad = []
        for p in sorted(SKILLS.rglob("*.md")):
            lines = p.read_text(encoding="utf-8").splitlines()
            for n, line in enumerate(lines):
                if '${CLAUDE_PLUGIN_ROOT}/bin/reel"' in line:
                    near = "\n".join(lines[max(0, n - 4):n + 5])
                    if '& "${CLAUDE_PLUGIN_ROOT}/bin/reel.cmd"' not in near:
                        bad.append(f"{p.relative_to(SK)}:{n + 1}")
        self.assertEqual(bad, [])

    def test_own_references_use_the_skill_dir(self):
        bad = [f"{p.parent.name}:{n}" for p in sorted(SKILLS.glob("*/SKILL.md"))
               for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
               if re.search(r"(?<![\w/}])references/", line)
               or re.search(r"`(?:skills/)?[a-z-]+-craft/references/", line)]
        self.assertEqual(bad, [])

    def test_skill_dir_references_exist(self):
        for p in sorted(SKILLS.glob("*/SKILL.md")):
            for m in re.finditer(r"\$\{CLAUDE_SKILL_DIR\}/([\w./-]+\.md)", p.read_text(encoding="utf-8")):
                if p.parent.name == "start" and m.group(1) == "references/install-from-claude.md":
                    continue                                  # installer-owned, linked "when present"
                self.assertTrue((p.parent / m.group(1)).is_file(), f"{p.parent.name}: {m.group(1)}")

    def test_language_option_in_motion_and_podcast(self):
        for n in ("edit", "motion", "podcast"):
            self.assertIn("${user_config.language}", text(n), n)

    def test_validate_hint_in_the_authoring_crafts(self):
        for n, f in (("episode-craft", "reels-plan.json"), ("motion-craft", "motion-script.json"),
                     ("publish-craft", "publish.json"), ("transcript-craft", "transcript-corrections.json"),
                     ("story-craft", "edit-decisions.json")):
            self.assertRegex(text(n), r"reel validate [^`]*" + re.escape(f), n)

    def test_start_links_the_install_reference(self):
        self.assertIn("${CLAUDE_SKILL_DIR}/references/install-from-claude.md", text("start"))


class TestGuardAndStages(unittest.TestCase):
    def test_guard_off_is_a_stop_item(self):
        for n in ("start", "setup", "edit"):
            s = " ".join(text(n).split())
            self.assertIn("guard_active: false", s, n)
            self.assertIn("WhyNot Cut protection is OFF", s, n)
            self.assertIn("guard_heartbeat.fix", s, n)

    def test_edit_stages_run_1_to_12_in_order(self):
        s = text("edit")
        rows = [ln for ln in s.splitlines() if re.match(r"\|\s*\**\d", ln)]
        nums = [int(x) for ln in rows for x in re.findall(r"(?<![\w.])(\d{1,2})(?=\s+[A-Z])", ln.split("|")[1])]
        self.assertEqual(nums, list(range(1, 13)))
        self.assertNotRegex(s, r"\b(3b|7b|8b)\b")
        self.assertNotRegex(s.lower(), r"stage 13\b")

    def test_fix_audio_matches_the_audio_engineer_report(self):
        s = text("fix-audio")
        for word in ("decisions", "speech-to-noise", "loudness", "cut-verification.json", "missing words"):
            self.assertIn(word, s)


if __name__ == "__main__":
    unittest.main()
