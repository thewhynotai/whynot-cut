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
- T3.1 review: the medical-reviewer runs on every clip, podcast reel and motion video (motion: after the script, before
  the plan is approved; revise motion route too); skills Read as files use the plugin-root form.
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
        for n in ("edit", "motion", "adobe-extras", "podcast"):
            self.assertTrue(self.RULE in " ".join(text(n).split()), f"{n}: the app rule is missing")

    def test_podcast_does_not_say_premiere_is_the_only_deliverable(self):
        self.assertNotIn("Premiere is the deliverable", " ".join(text("podcast").split()))

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

    def test_podcast_runs_the_medical_reviewer_on_every_reel(self):
        """T3.1 review: one rule for clips, podcast reels and motion videos — the medical-reviewer runs on every one,
        whatever the client's domain; the religious checklist applies when the profile domain is religious."""
        s = " ".join(text("podcast").split())
        self.assertRegex(s, r"medical-reviewer runs on every reel")
        self.assertRegex(s, r"(?i)whatever the client's `domain`")
        self.assertRegex(s, r"`domain: religious`")
        self.assertNotIn("Other domains skip it", s)
        self.assertNotIn("runs only for a medical client", s)

    def test_motion_reviews_claims_after_the_script_before_approval(self):
        s = text("motion")
        rows = [ln for ln in s[s.index("## 2. Stages"):].splitlines() if ln.startswith("| ")][1:]
        first = [ln.split("|")[1].strip().strip("*").lower() for ln in rows]
        claims = next(i for i, c in enumerate(first) if c.startswith("claims"))
        self.assertLess(first.index("script"), claims)
        self.assertLess(claims, next(i for i, c in enumerate(first) if c.startswith("approve the plan")))
        row = rows[claims]
        self.assertIn("whynot-cut:medical-reviewer", row)
        self.assertIn("motion-plan.md", row)
        flat = " ".join(s.split())
        self.assertRegex(flat, r"(?i)religious")
        self.assertRegex(flat, r"(?i)never ask for approval .{0,80}before the medical-reviewer")

    def test_revise_motion_route_reviews_changed_words_before_approval(self):
        s = text("revise")
        sec = s[s.index("## Motion videos"):]
        table = [ln for ln in sec.splitlines() if ln.startswith("| ")]
        self.assertTrue(any("whynot-cut:medical-reviewer" in ln for ln in table))
        self.assertLess(sec.index("whynot-cut:medical-reviewer` reviews"), sec.index("reel approve-plan"))

    def test_revise_clip_route_re_reviews_changed_wording_before_approval(self):
        """T3.1 round 2 (m1): any change to on-screen wording (story-editor edits to graphics, captions, statements)
        gets a medical-reviewer re-review of the changed items before the changed plan is shown for approval."""
        s = text("revise")
        clip = s[:s.index("## Motion videos")]
        flat = " ".join(clip.split())
        self.assertRegex(flat, r"(?i)any change to on-screen wording")
        self.assertRegex(flat, r"(?i)whynot-cut:medical-reviewer.{0,200}changed (items|elements)")
        route = next(ln for ln in clip.splitlines() if ln.lstrip().startswith("| wording"))
        self.assertIn("medical-reviewer", route)
        step4 = clip.index("\n4. ")
        self.assertLess(clip.index("re-reviews"), step4)
        self.assertRegex(" ".join(clip[:step4].split()), r"(?i)before\W+step 4 shows the changed plan for approval")

    def test_motion_reviewer_reads_the_full_text_section(self):
        for name in ("motion", "revise", "medical-accuracy"):
            self.assertIn("On-screen text (full)", " ".join(text(name).split()), name)

    def test_revise_motion_look_row_changes_the_script_not_a_rebuild_of_the_same_plan(self):
        s = text("revise")
        sec = s[s.index("## Motion videos"):]
        row = next(ln for ln in sec.splitlines() if ln.startswith("| how a scene looks"))
        self.assertNotIn("same approved plan", row)
        self.assertIn("motion-director", row)
        self.assertIn("reel motion-plan", row)

    def test_the_claims_stage_records_the_review_with_review_flags(self):
        """T4.13: the medical-reviewer is read-only, so the lead puts its table through `reel review-flags --from -`
        (the claims stage of edit; the motion video's claims row names it too, with the scene id)."""
        edit = " ".join(text("edit").split())
        self.assertRegex(edit, r"\| 7 Claims .{0,200}review-flags")
        self.assertRegex(edit, r"reel review-flags .{0,80}--from -")
        motion = " ".join(text("motion").split())
        self.assertRegex(motion, r"reel review-flags .{0,120}--from -")
        self.assertRegex(motion, r"(?i)keyed by the \*\*scene id\*\*")
        agent = " ".join((SK / "agents" / "medical-reviewer.md").read_text(encoding="utf-8").split())
        self.assertRegex(agent, r"scene id")
        self.assertRegex(agent, r"the lead runs `reel review-flags`")
        self.assertIn("`event_id`", text("medical-accuracy"))
        self.assertIn("The medical-reviewer runs on every motion video, whatever the client's `domain`", motion)
        revise = " ".join(text("revise").split())
        self.assertRegex(revise, r"changed items only\..{0,400}reel review-flags .{0,120}--from -")
        self.assertRegex(revise, r"(?i)stays covered by itself")
        for name in ("edit", "motion"):                       # the first review is the reviewer's FULL table (coverage model)
            flat = " ".join(text(name).split())
            self.assertRegex(flat, r"FULL table")
            self.assertRegex(flat, r"reported as `dropped`")
            self.assertRegex(flat, r"(?i)have not been reviewed")
            self.assertRegex(flat, r"`cleared`")                # a flag passed as ok on the same words: the editor is told
        for name in ("edit", "motion", "revise"):   # an open flag: every new or changed line is reviewed for that flag
            flat = " ".join(text(name).split())
            self.assertRegex(flat, r"[GS]\d is new or changed since [GS]\d's medical flag: review [GS]\d for medical")
            self.assertRegex(flat, r"(?i)every new or changed (graphic|scene|line)")
            self.assertRegex(flat, r"(?i)left its (graphic|scene|line)")          # the exact rule: off its line ...
            self.assertRegex(flat, r"(?i)an exact copy of its words")              # ... or still on it (in place)
            self.assertRegex(flat, r"only the flags the client's domain checks")   # medical; religious client: both
            self.assertRegex(flat, r"(?i)no words on screen .{0,40}left out")
        self.assertRegex(revise, r"keep graphic ids stable")
        self.assertRegex(revise, r"keep scene ids\s+stable")
        for name in ("story-editor", "motion-director"):
            agent = " ".join((SK / "agents" / f"{name}.md").read_text(encoding="utf-8").split())
            self.assertRegex(agent, r"(?i)keep every (graphic's and decision's|scene's) id stable")

    def test_autopilot_lists_medical_and_religious_approvals(self):
        s = " ".join(text("autopilot").split())
        self.assertRegex(s, r"medical and religious approvals needed")


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

    def test_skills_read_as_files_use_the_plugin_root_form(self):
        """A Read of another skill's SKILL.md substitutes no variable, so ${CLAUDE_SKILL_DIR} would be ambiguous there:
        a skill that another skill tells Claude to Read uses ${CLAUDE_PLUGIN_ROOT}/skills/<itself>/… instead."""
        read = {m.group(1) for p in SKILLS.glob("*/SKILL.md")
                for m in re.finditer(r"\$\{CLAUDE_PLUGIN_ROOT\}/skills/([a-z-]+)/SKILL\.md", p.read_text(encoding="utf-8"))
                if m.group(1) != p.parent.name}
        self.assertTrue({"edit", "podcast", "audio-craft", "client-craft"} <= read, read)
        self.assertEqual({n: True for n in sorted(read) if "${CLAUDE_SKILL_DIR}" in text(n)}, {})

    def test_skill_dir_references_exist(self):
        for p in sorted(SKILLS.glob("*/SKILL.md")):
            for m in re.finditer(r"\$\{CLAUDE_SKILL_DIR\}/([\w./-]+\.md)", p.read_text(encoding="utf-8")):
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
        agent = (SK / "agents" / "audio-engineer.md").read_text(encoding="utf-8")
        for word in ("decisions", "speech-to-noise", "loudness", "cut-verification.json", "missing words"):
            self.assertIn(word, s)
            self.assertIn(word, agent, f"agents/audio-engineer.md no longer reports {word!r}")


class TestNoPythonInstallPath(unittest.TestCase):
    """G3 review I2: a machine without Python (a new Mac without Xcode tools) is handed to the installer that ships in
    the plugin (installer/core/bootstrap.sh | .ps1: pinned uv + Python 3.12), never to xcode-select / winget. The
    interim install-from-claude.md uses exactly the installer track's call contract (2026-10-15)."""
    REF = SKILLS / "start" / "references" / "install-from-claude.md"
    BOOT = SK / "installer" / "core"

    def blocks(self, lang: str) -> list[str]:
        return re.findall(rf"```{lang}\n(.*?)```", self.REF.read_text(encoding="utf-8"), re.S)

    def test_reference_ships_with_the_interim_marker(self):
        s = self.REF.read_text(encoding="utf-8")
        self.assertTrue(s.startswith("<!-- interim (G3 review I2); the installer track replaces this with its D-T2 "
                                     "text -->"))
        self.assertRegex(s, r"[؀-ۿ]")                       # Arabic for the editor
        self.assertIn("AskUserQuestion", s)
        self.assertIn("run_in_background", s)
        for code in ("**0,", "**1,", "**2,", "**3,"):                 # what to say for every exit code
            self.assertIn(code, s)

    def test_commands_follow_the_installer_contract(self):
        sh, ps = self.blocks("bash"), self.blocks("powershell")
        self.assertEqual(len(sh), 1)
        self.assertEqual(len(ps), 1)
        self.assertEqual(sh[0].strip(), 'bash "<ROOT>/installer/core/bootstrap.sh" --plugin-root "<ROOT>" --yes '
                                        '--skip claude </dev/null')
        self.assertEqual(ps[0].strip(), 'powershell -NoProfile -ExecutionPolicy Bypass -File '
                                        '"<ROOT>\\installer\\core\\bootstrap.ps1" -PluginRoot "<ROOT>" -Yes -Skip claude')
        boot_sh = (self.BOOT / "bootstrap.sh").read_text(encoding="utf-8")
        for flag in ("--plugin-root", "--yes", "--skip"):
            self.assertRegex(boot_sh, rf"(?m)^\s*{re.escape(flag)}(\|[^)]*)?\)", flag)
        boot_ps = (self.BOOT / "bootstrap.ps1").read_text(encoding="utf-8")
        params = boot_ps[boot_ps.index("param("):boot_ps.index("\n)", boot_ps.index("param("))]
        for name in ("PluginRoot", "Yes", "Skip"):
            self.assertRegex(params, rf"\${name}\b", name)
        for never in ("--customise", "--home", "--uninstall", "WNC_TEST_", "-Customise", "-Home", "-Uninstall"):
            self.assertNotIn(never, sh[0] + ps[0])

    def test_no_xcode_or_winget_advice_anywhere(self):
        files = [SK / "README.md", SK / "bin" / "reel", SK / "bin" / "reel.cmd", SK / "setup" / "setup_env.sh",
                 SK / "setup" / "setup_env.py", SK / "engine" / "reel" / "lib" / "onboard.py", self.REF,
                 *SKILLS.glob("*/SKILL.md"), *SKILLS.glob("*/references/*.md")]
        bad = [f"{f.relative_to(SK).as_posix()}:{n}" for f in files
               for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1)
               if re.search(r"xcode-select --install|winget install", line)]
        self.assertEqual(bad, [])
        for n in ("start", "setup"):
            self.assertIn("install-from-claude.md", text(n), n)


class TestG3Minors(unittest.TestCase):
    """G3 review minors that live in the skill and context texts (M2, M6, M7, M8, M12, M14)."""
    AR_STOPS = ("«اختار الريلز»", "«وافق على الخطة»", "«فحص الجودة»")

    def test_m2_no_gate_words_in_agents_references_and_contexts(self):
        files = [*sorted((SK / "agents").glob("*.md")), *sorted(SKILLS.glob("*/references/*.md")),
                 SKILLS / "premiere-craft" / "SKILL.md"]
        bad = [f"{f.relative_to(SK).as_posix()}:{n}" for f in files
               for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1) if GATE.search(line)]
        self.assertEqual(bad, [])
        ctx = (SK / "hooks" / "session_context.py").read_text(encoding="utf-8")
        body = ctx[ctx.index("def prefs_line"):ctx.index("def export_options")]
        self.assertNotRegex(body, GATE)

    def test_m6_skill_tables_name_agents_with_the_plugin_namespace(self):
        agents = sorted(p.stem for p in (SK / "agents").glob("*.md"))
        bare = re.compile(r"(?<![\w:/.-])(" + "|".join(map(re.escape, agents)) + r")(?![\w-])")
        bad = [f"{p.parent.name}:{n}: {m}" for p in sorted(SKILLS.glob("*/SKILL.md"))
               for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
               if line.lstrip().startswith("|") for m in bare.findall(line)]
        self.assertEqual(bad, [])

    def test_m7_one_command_per_code_block(self):
        for n in ("start", "setup"):
            s = " ".join(text(n).split())
            self.assertIn("in its own", s.split("PlayerDebugMode", 1)[1], n)
        for p in sorted(SKILLS.glob("*/SKILL.md")):
            self.assertNotRegex(" ".join(p.read_text(encoding="utf-8").split()),
                                r"(?i)commands? [^.]{0,60}in one (fenced|code) block", p.parent.name)

    def test_m8_one_arabic_word_per_stop(self):
        style = (SK / "output-styles" / "whynot-cut-editor.md").read_text(encoding="utf-8")
        for t in (style, text("edit")):
            for w in self.AR_STOPS:
                self.assertIn(w, t)
        _sys.path.insert(0, str(SK / "engine" / "reel"))
        from lib import board
        self.assertTrue(board.STEP_TEXT["ar"]["proof_check"].startswith("فحص الجودة"))
        self.assertEqual(board.STEP_TEXT["ar"]["approve_plan"], "وافق على الخطة")
        self.assertEqual(board.STEP_TEXT["ar"]["pick_reels"], "اختار الريلز")
        readme = (SK / "README.md").read_text(encoding="utf-8")
        self.assertIn("«فحص الجودة»", readme)
        for f in [SK / "README.md", *SKILLS.glob("*/SKILL.md"), SK / "engine" / "reel" / "lib" / "board.py"]:
            for other in ("مراجعة الإثبات", "تقرير جودة", "تقرير الجودة"):
                self.assertNotIn(other, f.read_text(encoding="utf-8"), f"{f.name}: {other}")

    def test_m12_no_release_labels_in_the_readme_intro(self):
        intro = (SK / "README.md").read_text(encoding="utf-8").split("\n## ", 1)[0]
        self.assertNotRegex(intro, r"\(\d\.\d\)")

    def test_m14_revise_names_the_section_it_points_back_to(self):
        s = text("revise")
        self.assertIn("## Clip videos (Premiere)", s)
        self.assertNotIn("as in step 4 above", s)
        self.assertIn("as in step 4 of **Clip videos (Premiere)** above", " ".join(s.split()))


class TestApprovalConsent(unittest.TestCase):
    """G3 review I1: "stop asking" / "just go" never turns on a standing `approval: auto` in the same turn. The
    preferences skill makes the "this clip or from now on?" question a stop; the edit skill's "just go" line approves
    only a plan that is waiting and otherwise defers to that rule; every session context repeats it."""

    def test_preferences_question_is_a_stop(self):
        s = " ".join(text("preferences").split())
        self.assertIn("is a question, never a switch: stop and ask", s)
        self.assertIn("end your turn", s)
        self.assertRegex(s, r"Never write `approval=auto` \([^)]*\) in the same turn as the request")
        self.assertIn("never ask and assume \"from now on\" in the same message", s)
        self.assertIn("Ask even when no clip is in progress", s)

    def test_edit_just_go_approves_only_a_waiting_plan(self):
        s = " ".join(text("edit").split())
        m = re.search(r"\(\"just go\", \"don't ask\"\)(.{0,700})", s)
        self.assertIsNotNone(m, "the edit skill's just-go line is gone")
        rule = m.group(1)
        self.assertIn("while this plan is waiting for approval", rule)
        self.assertIn("approves this plan only", rule)
        self.assertIn("never changes `approval`", rule)
        self.assertIn("/whynot-cut:preferences", rule)
        self.assertIn("never write `approval=auto` in the same turn as the request", rule)

    def test_every_session_context_carries_the_rule(self):
        src = (SK / "hooks" / "session_context.py").read_text(encoding="utf-8")
        rule = re.search(r"CONSENT_RULE = \((.*?)\)\n", src, re.S)
        self.assertIsNotNone(rule)
        self.assertIn("end your turn", rule.group(1))
        self.assertIn("only after the editor answers", rule.group(1))
        body = src[src.index("def prefs_line"):src.index("def export_options")]
        self.assertEqual(body.count("CONSENT_RULE"), 2, "both prefs_line branches (none yet / values) carry it")


class TestBriefs(unittest.TestCase):
    """Addendum M5-T3 (Task 58): the edit, podcast, motion, revise and status skills name `reel brief` and
    02_transcription/transcript.compact.md and say to read them instead of the JSON files."""
    SKILLS5 = ("edit", "podcast", "motion", "revise", "status")
    COMPACT_FOR_WORDS = "read the compact transcript for the words (context, review, claims)"
    IDS_AND_TIMES = ("word ids and exact times still come from `words.json` (proofreader chunks, story-editor timings, "
                     "`cut_words`)")

    def test_m5_t3_skills_name_the_brief_and_the_compact_transcript(self):
        for name in self.SKILLS5:
            s = text(name)
            with self.subTest(name):
                self.assertRegex(s, r"`reel brief --root \"<CLIENT(_FOLDER)?>\" --video-id <[^`]+`")
                self.assertIn("transcript.compact.md", s)
                self.assertIn("`reel transcript-compact`", s)
                para = next((b for _, b in paragraphs(s) if "Read `reel brief`, not the JSON files" in b), "")
                self.assertTrue(para, "the read-the-brief rule is missing")
                for f in ("project-status.json", "qc-results.json", "transcript.json", "words.json"):
                    self.assertIn(f, para, f"{name}: the rule must name {f}")
                self.assertIn("instead of", para)
                self.assertIn("1,500 tokens", para)
                flat = " ".join(para.split())
                # fu1 (review b2db1e7 P2-3): the compact is for reading the words; word ids and exact times are not in
                # it, so proofreaders, the story-editor and cut_words still get them from words.json
                for pin in (self.COMPACT_FOR_WORDS, self.IDS_AND_TIMES):
                    self.assertIn(pin, flat, f"{name}: the compact / words.json split is not stated")
                self.assertNotRegex(flat, r"instead of `transcript\.json` or `words\.json`",
                                    f"{name}: the compact does not replace words.json (no word ids, no ms times)")



class TestClientBrief(unittest.TestCase):
    """Addendum M5-T4 (Task 59): the edit, podcast and motion skills run `reel client-brief` and say to read
    client-brief.md first; the client-researcher, story-editor and motion-director agents read it first (the
    researcher rebuilds it after a database change)."""
    SKILLS3 = ("edit", "podcast", "motion")
    AGENTS3 = ("client-researcher", "story-editor", "motion-director")

    def test_m5_t4_skills_read_the_client_brief_first(self):
        for name in self.SKILLS3:
            s = text(name)
            with self.subTest(name):
                self.assertRegex(s, r'reel client-brief --root "<CLIENT(_FOLDER)?>"')
                para = next((b for _, b in paragraphs(s) if "Read `client-brief.md` first" in b), "")
                self.assertTrue(para, "the read-the-client-brief rule is missing")
                flat = " ".join(para.split())
                self.assertIn("1,000 tokens", flat)
                self.assertIn("instead of", flat)
                for f in ("profile.json", "typography.json", "style.json", "rules.json"):
                    self.assertIn(f, flat, f"{name}: the rule must name {f} as what not to open")
                self.assertLess(s.index("Read `client-brief.md` first"), s.index("## 1."),
                                "the rule belongs to the start (section 0)")

    def test_m5_t4_agents_read_the_client_brief_first(self):
        for name in self.AGENTS3:
            agent = " ".join((SK / "agents" / f"{name}.md").read_text(encoding="utf-8").split())
            with self.subTest(name):
                self.assertRegex(agent, r"\*\*(Read )?`output/client_database/client-brief\.md` first")
                self.assertIn("1,000 tokens", agent)
                self.assertIn("reel client-brief", agent)
        researcher = " ".join((SK / "agents" / "client-researcher.md").read_text(encoding="utf-8").split())
        self.assertIn('run `reel client-brief --root "<CLIENT>"` so it is rebuilt', researcher)


if __name__ == "__main__":
    unittest.main()
