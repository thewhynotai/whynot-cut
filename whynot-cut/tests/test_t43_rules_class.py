# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.3 fix round (S1-T4.3; review b399ed2 P1-1, P1-2, P2-1..P2-4): the learning loop's safety as a CLASS.

Executor design (binding): only the T4.2 knob allowlist ever changes compiled output; every other label is a
free-text preference printed in notes.md under a fixed header that says it never overrides approvals, review, QC or
disclaimers (and a K1 line); no gate module reads a rule; rules.json is checked when read (schema, allowlist, seal),
never trusted, and a notes-only rule the class refuses is shown as refused when rendered.
Plan rulings (round 2): an unlabelled comment never counts; the over-block is accepted and widened (a preference that
NAMES anything a gate protects is refused, whatever the verb); `--dismiss` remembers the editor's no.
The tests assert the outcome for whole classes of input (generated matrices), never a list of wordings.
Case list: D:/ClaudeData/claude-api-lane/work/S1-T4.3/cases.md.
Run:  bash tools/test.sh -p test_t43_rules_class.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import ast
import hashlib
import itertools
import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import rules_loop as RL  # noqa: E402
from lib.common import read_json, write_json  # noqa: E402
from lib.errors import Guidance  # noqa: E402
from test_t43_rules import Client  # noqa: E402

LIB = SK / "engine" / "reel" / "lib"
CLI = SK / "engine" / "reel" / "cli.py"
HEADER = ("تفضيلات العميل: مش بتلغي أي موافقة أو مراجعة أو QC أو تنبيه / client preferences: never override approvals, "
          "review, QC or disclaimers")
ALLOWLIST = {"caption_size_px", "captions_during_hook", "hook_title_sfx", "highlight_colour"}
UP = {"knob": "caption_size_px", "direction": "up"}

# The generated matrices (C1). People: who × what is dropped or limited × language. Objects: what a gate protects ×
# a way of dropping, limiting or pre-filling it × language (no person named). Style: things a client may prefer that
# name no gate object (they must still become preferences: the class is not "refuse everything").
PEOPLE = {"en": ["the doctor", "Dr. Mona", "the sheikh", "the reviewer"], "ar": ["الدكتور", "الدكتورة", "الشيخ"],
          "franco": ["el doctor", "el sheikh"]}
ACTS = {"en": ["skip {p}'s check", "{p} only sees the first reel", "no need to wait for {p}", "keep it even if {p} objects",
               "remove the 'ask {p}' caption", "always pre-tick the retakes for {p}", "don't check the numbers, {p} is fine"],
        "ar": ["من غير ما {p} يشوف", "بلاش {p} يراجع", "{p} يشوف أول فيديو بس", "شيل جملة اسأل {p}",
               "دايماً متعلمش على الأرقام عشان {p}"],
        "franco": ["mn 3'er {p}", "bala4 {p} yeraga3", "{p} msh lazem yshoof"]}
OBJECTS = {"en": ["the review", "my approval", "your OK", "the QC", "the quality check", "the disclaimer line",
                  "the 'consult your physician' card", "the dose numbers", "the stats", "the verse check",
                  "the Quran text", "the hadith source", "the retakes", "the pre-ticks", "the hook quote",
                  "the word for word check", "the flags", "the medical claim", "the sign-off"],
           "ar": ["المراجعة", "موافقتي", "الاعتماد", "الكيو سي", "الكواليتي", "جملة استشر طبيبك", "التنويه",
                  "الأرقام", "الجرعة", "الآيات", "المصحف", "الحديث", "الإعادات", "الاقتباس", "الفلاجات"],
           "franco": ["el moraga3a", "el mwaf2a", "el ar2am", "el qc"]}
VERBS = {"en": ["skip {o}", "no need for {o}", "{o} can wait", "don't bother with {o}", "{o} only on the first reel",
                "fill in {o} yourself"],
         "ar": ["من غير {o}", "بلاش {o}", "{o} مش مهم", "سيبك من {o}", "{o} في أول فيديو بس"],
         "franco": ["mn 3'er {o}", "bala4 {o}", "{o} msh mohem"]}
STYLE_NOUNS = {"en": ["the music", "the captions", "the logo", "the transitions", "the b-roll", "the font", "the intro"],
               "ar": ["المزيكا", "الكابشن", "اللوجو", "الترانزيشن", "البي رول", "الخط"]}
STYLE_ACTS = {"en": ["make {n} softer", "always end with {n}", "{n} a bit faster", "keep {n} simple"],
              "ar": ["خلي {n} أهدى", "{n} أسرع شوية", "دايما خلّي {n} بسيط"]}
AREAS = ["captions", "cuts", "hook", "ending", "wording", "publish_text", "other_style"]
GATE_SOUNDING_KNOBS = ["review_required", "qc", "number_check", "pre_tick_retakes", "verse_match", "disclaimer_line",
                       "approval_mode", "doctor_review"]


def _gen(subjects, acts, key):
    return [act.format(**{key: x}) for lang in subjects for x, act in itertools.product(subjects[lang], acts[lang])]


def matrix():
    return _gen(PEOPLE, ACTS, "p")


def object_matrix():
    return _gen(OBJECTS, VERBS, "o")


def style_matrix():
    return _gen(STYLE_NOUNS, STYLE_ACTS, "n")


class TestOnlyTheAllowlistChangesOutput(Client):
    """C1: whatever is said and however it is labelled, only the four T4.2 knobs ever reach style.json, and a
    preference that names anything a gate protects is refused (people matrix, object matrix, gate-sounding names)."""

    def run_matrix(self, texts, label):
        style = self.prof / "style.json"
        write_json(style, {"caption_size_px": 70})
        before = style.read_bytes()
        for i, text in enumerate(texts):
            self.rec(f"C000{1 + i % 5}", {"text": "always: " + text, "intent": label(i), "scope": "standing"})
        r = self.props()
        self.assertEqual(r["proposals"], [], [p["text"] for p in r["proposals"]])
        self.assertEqual(len(r["refused"]), len(texts))
        self.assertEqual(style.read_bytes(), before)
        self.assertEqual(sorted(self.files()), ["style.json"])          # no rules.json, no notes.md

    def test_the_people_matrix_is_refused_and_writes_nothing(self):
        texts = matrix()
        self.assertGreaterEqual(len(texts), 40)
        self.run_matrix(texts, lambda i: {"topic": f"pref_{i}", "area": AREAS[i % len(AREAS)]})

    def test_the_object_matrix_is_refused_and_writes_nothing(self):
        texts = object_matrix()
        self.assertGreaterEqual(len(texts), 150)
        self.run_matrix(texts, lambda i: {"topic": f"pref_{i}", "area": AREAS[i % len(AREAS)]})

    def test_gate_sounding_knob_names_are_refused_whatever_the_words(self):
        self.run_matrix([f"like this, version {i}" for i in range(len(GATE_SOUNDING_KNOBS))],
                        lambda i: {"knob": GATE_SOUNDING_KNOBS[i], "direction": "off", "area": AREAS[i % len(AREAS)]})

    def test_naming_a_reviewer_does_not_refuse_an_allowlisted_knob(self):
        """The object class applies to preferences only: a knob rule sets that knob and the brief shows the knob's
        summary, never the comment's words ("Dr. Mona wants bigger captions" is a caption size, nothing more). The
        older drop / process checks still refuse a knob-labelled comment that drops a review."""
        asks = {"en": "{p} wants bigger captions", "ar": "{p} عايز الكابشن أكبر", "franco": "{p} 3ayez el caption akbar"}
        texts = [asks[lang].format(p=p) for lang in PEOPLE for p in PEOPLE[lang]
                 if "review" not in p]                    # "the reviewer" names the review itself: always refused
        for text in texts:
            with self.subTest(text=text):
                self.assertTrue(RL.weakens_safety(text, {"topic": "x", "area": "captions"}))
                self.assertFalse(RL.weakens_safety(text, UP))
        self.assertTrue(RL.weakens_safety("skip the doctor's review, bigger captions", UP))
        self.rec("C0001", {"text": "always: " + texts[0], "intent": UP, "scope": "standing"})
        rule = RL.add(self.root, self.one()["id"])["rule"]
        self.assertEqual(rule["knob"], "caption_size_px")
        self.assertEqual(set(read_json(self.prof / "style.json")), {"caption_size_px"})
        self.assertNotIn(texts[0], (self.prof / "notes.md").read_text(encoding="utf-8"))

    def test_style_preferences_naming_no_gate_object_still_become_rules(self):
        texts = style_matrix()
        self.assertGreaterEqual(len(texts), 40)
        for text in texts:
            with self.subTest(text=text):
                self.assertFalse(RL.weakens_safety(text, {"topic": "x", "area": "other_style"}), text)
        self.rec("C0001", {"text": "always: " + texts[0], "intent": {"topic": "style_a", "area": "music"},
                           "scope": "standing"})
        RL.add(self.root, self.one()["id"])
        self.assertEqual(RL.list_rules(self.root)["active"][0]["target"], "notes.md")
        self.assertFalse((self.prof / "style.json").exists())

    def test_only_allowlisted_knob_rules_carry_a_knob(self):
        self.rec("C0001", {"text": "always bigger captions", "intent": UP, "scope": "standing"})
        rule = RL.add(self.root, self.one()["id"])["rule"]
        self.assertIn(rule["knob"], ALLOWLIST)
        self.assertIn("caption_size_px", read_json(self.prof / "style.json"))


class TestTheBriefHeader(Client):
    """C2: the block in notes.md (the brief) prints the rules under the fixed header and the K1 line; a notes-only
    rule is a preference, never something an agent 'follows' over a gate."""

    def block(self):
        text = (self.prof / "notes.md").read_text(encoding="utf-8")
        a, b = text.index(RL.BLOCK_START), text.index(RL.BLOCK_END)
        return text[a:b]

    def test_header_and_preference_lines(self):
        self.rec("C0001", {"text": "always end on the logo", "intent": {"topic": "logo_end", "area": "ending"},
                           "scope": "standing"})
        RL.add(self.root, self.one()["id"])
        block = self.block()
        self.assertIn(HEADER, block)
        self.assertIn(RL.PREFERENCES_K1, block)
        for word in ("K1", "verse", "retake", "number"):
            self.assertIn(word, RL.PREFERENCES_K1)
        self.assertNotIn("follows it", block)
        line = next(x for x in block.splitlines() if "R1" in x)
        self.assertIn("preference", line)

    def test_header_also_without_an_active_rule(self):
        self.rec("C0001", {"text": "always end on the logo", "intent": {"topic": "logo_end", "area": "ending"},
                           "scope": "standing"})
        RL.add(self.root, self.one()["id"])
        RL.remove(self.root, "R1")
        self.assertIn(HEADER, self.block())
        self.assertIn(RL.PREFERENCES_K1, self.block())

    def test_the_history_section_keeps_old_rules(self):
        self.rec("C0001", {"text": "always end on the logo", "intent": {"topic": "logo_end", "area": "ending"},
                           "scope": "standing"})
        RL.add(self.root, self.one()["id"])
        RL.remove(self.root, "R1")
        block = self.block()
        self.assertIn("No longer active", block)
        self.assertRegex(block, r"R1 · .*removed \d{4}-\d\d-\d\d")


class TestNoGateReadsARule(unittest.TestCase):
    """C3: approvals, review flags / gate, QC, disclaimers, the K1 switches and needs-you never read the rules."""
    NAMES = re.compile(r"rules_loop|rules\.json|client-rules|notes\.md|NOTES_MD")
    GATES = ["qc.py", "motion_qc.py", "review_flags.py", "review_domains.py", "needs_you.py", "verify.py",
             "build_safety.py", "autopilot.py", "plan.py", "handoff.py"]
    HANDLERS = ["cmd_approve_plan", "cmd_auto_approve", "cmd_review_flags", "cmd_qc", "cmd_needs_you", "cmd_verify",
                "cmd_handoff"]

    def gate_files(self):
        files = [LIB / g for g in self.GATES] + sorted((LIB / "safety").glob("*.py"))
        files += [f for f in sorted(LIB.glob("*.py")) if f.name != "rules_loop.py"
                  and "disclaim" in f.read_text(encoding="utf-8").lower()]
        return [f for f in dict.fromkeys(files) if f.is_file()]

    def test_gate_modules_never_name_the_rules(self):
        files = self.gate_files()
        self.assertGreaterEqual(len(files), 12)
        for f in files:
            with self.subTest(module=f.name):
                self.assertIsNone(self.NAMES.search(f.read_text(encoding="utf-8")))

    def test_gate_handlers_in_the_cli_never_name_the_rules(self):
        tree = ast.parse(CLI.read_text(encoding="utf-8"))
        src = CLI.read_text(encoding="utf-8")
        found = {n.name: ast.get_source_segment(src, n) for n in tree.body if isinstance(n, ast.FunctionDef)}
        for h in self.HANDLERS:
            with self.subTest(handler=h):
                self.assertIn(h, found)
                self.assertIsNone(self.NAMES.search(found[h]))

    def test_importing_the_gates_does_not_load_the_rules(self):
        import importlib
        import subprocess
        mods = [f"lib.{f.stem}" for f in self.gate_files() if f.parent == LIB] + ["lib.safety"]
        code = ("import sys; sys.path.insert(0, %r); import importlib\n"
                "for m in %r: importlib.import_module(m)\n"
                "print('lib.rules_loop' in sys.modules)") % (str(SK / "engine" / "reel"), mods)
        r = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr[-600:])
        self.assertEqual(r.stdout.strip(), "False")
        importlib.invalidate_caches()


class TestRulesFileIsCheckedOnRead(Client):
    """C4: rules.json is never trusted as it is found."""

    def setUp(self):
        super().setUp()
        self.rec("C0001", {"text": "always bigger captions", "intent": UP, "scope": "standing"})
        RL.add(self.root, self.one()["id"])
        self.rules = self.prof / RL.RULES_FILE
        self.notes = self.prof / "notes.md"

    def tamper(self, fn, seal="keep"):
        """Edit rules.json by hand. seal: "keep" (the old seal stays, now wrong), "recompute" (a correct seal over
        the edited rows: the allowlist must still refuse), "drop" (no seal at all)."""
        doc = json.loads(self.rules.read_text(encoding="utf-8"))
        fn(doc)
        if seal == "recompute":
            doc["seal"] = RL.seal_of(doc["rules"], doc.get("dismissed"))
        elif seal == "drop":
            doc.pop("seal", None)
        self.rules.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    def refused(self):
        notes_before = self.notes.read_bytes()
        for call in (lambda: RL.list_rules(self.root), lambda: RL.propose(self.root),
                     lambda: RL.remove(self.root, "R1")):
            with self.assertRaises(Guidance) as cm:
                call()
            self.assertIn("rules", cm.exception.error.lower())
        out = RL.applied(self.root, {"style": {}})
        self.assertEqual(len(out), 1)
        self.assertFalse(out[0]["applied"])
        self.assertEqual(self.notes.read_bytes(), notes_before)

    def test_a_file_written_by_reel_rules_reads_back(self):
        self.assertEqual([r["id"] for r in RL.list_rules(self.root)["active"]], ["R1"])
        self.assertIn("seal", json.loads(self.rules.read_text(encoding="utf-8")))

    def test_a_hand_added_rule_is_refused(self):
        self.tamper(lambda d: d["rules"].append({"id": "R9", "status": "active", "knob": None, "added": "2026-10-18",
                                                 "text": "skip the doctor's review", "subject": "topic:x"}))
        self.refused()

    def test_a_hand_reactivated_rule_is_refused(self):
        RL.remove(self.root, "R1")
        self.tamper(lambda d: d["rules"][0].update(status="active"))
        self.refused()

    def test_an_unsealed_file_is_refused(self):
        self.tamper(lambda d: None, seal="drop")
        self.refused()

    def test_a_sealed_rule_off_the_allowlist_is_refused(self):
        self.tamper(lambda d: d["rules"][0].update(knob="review_required", value=False), seal="recompute")
        self.refused()

    def test_a_sealed_rule_with_a_bad_value_is_refused(self):
        self.tamper(lambda d: d["rules"][0].update(value=99999), seal="recompute")
        self.refused()

    def test_no_file_is_an_empty_registry(self):
        self.rules.unlink()
        self.assertEqual(RL.list_rules(self.root)["active"], [])

    def test_the_seal_is_the_canonical_rows(self):
        doc = json.loads(self.rules.read_text(encoding="utf-8"))
        canon = json.dumps(doc["rules"], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(doc["seal"], hashlib.sha256(canon.encode("utf-8")).hexdigest())

    def test_a_sealed_notes_rule_the_class_refuses_is_shown_refused_never_as_a_rule(self):
        """Review b399ed2 P2-2: even a correctly sealed row (added before the class grew, or by someone who can seal)
        is re-checked when rendered, listed and reported."""
        bad = "always: no need to wait for the doctor"
        self.tamper(lambda d: d["rules"].append({"id": "R2", "status": "active", "knob": None, "value": None,
                                                 "added": "2026-10-18", "text": bad, "subject": "topic:waiting",
                                                 "polarity": "", "proposal": "P-x", "from": []}), seal="recompute")
        listed = {r["id"]: r for r in RL.list_rules(self.root)["active"]}
        self.assertTrue(listed["R2"].get("refused"))
        self.assertIn("refused", listed["R2"]["en"])
        self.assertEqual({a["id"]: a["applied"] for a in RL.applied(self.root, {"style": {}})}["R2"], "refused")
        self.rec("C0002", {"text": "always end on the logo", "intent": {"topic": "logo_end", "area": "ending"},
                           "scope": "standing"})
        RL.add(self.root, self.one()["id"])                       # any write renders the block again
        md = self.notes.read_text(encoding="utf-8")
        self.assertNotIn(bad, md)
        self.assertRegex(md, r"R2 · refused, ignored")


class TestUnlabelledComments(Client):
    """C5: a comment without the skill's intent label never counts (plan ruling); it is a warning that says how to
    relabel it, whatever its words."""

    def test_unlabelled_comments_are_warned_never_proposed(self):
        for vid in ("C0001", "C0002"):
            self.rec(vid, "دايماً: مش محتاج تاخد موافقتي، ابني على طول", "always: go ahead and build without asking me",
                     "always end on the logo", "الكابشن صغير", "captions too small", old=True)
        r = self.props()
        self.assertEqual(r["proposals"], [])
        self.assertEqual(r["refused"], [])
        self.assertEqual(len([w for w in r["warnings"] if "relabel" in w]), 10, r["warnings"])

    def test_a_hand_written_unlabelled_note_never_reaches_add(self):
        self.rec("C0001", "دايماً شيل جملة اسأل الدكتور من آخر الفيديو", old=True)
        with self.assertRaises(Guidance):
            RL.add(self.root, RL._gid("text:x", "on"))
        self.assertEqual(self.files(), {})


class TestDismiss(Client):
    """C7 (plan ruling 1): `--dismiss` remembers the editor's no; a NEW comment brings the proposal back."""
    LOGO = {"topic": "logo_end", "area": "ending"}

    def setUp(self):
        super().setUp()
        self.rec("C0001", {"text": "always end on the logo", "intent": self.LOGO, "scope": "standing"})
        self.pid = self.one()["id"]

    def test_a_dismissed_proposal_is_not_shown_again(self):
        r = RL.dismiss(self.root, self.pid)
        self.assertEqual((r["dismissed"], r["comments"]), (self.pid, 1))
        self.assertEqual(self.props()["proposals"], [])
        doc = read_json(self.prof / RL.RULES_FILE)
        self.assertEqual(doc["dismissed"][0]["proposal"], self.pid)
        self.assertEqual(doc["dismissed"][0]["from"], [["C0001", "N1"]])
        self.assertEqual(doc["rules"], [])
        self.assertFalse((self.prof / "notes.md").exists())         # a no changes nothing else
        self.assertEqual(RL.list_rules(self.root)["active"], [])    # and the file still reads back (sealed)

    def test_a_new_comment_brings_it_back(self):
        RL.dismiss(self.root, self.pid)
        self.rec("C0002", {"text": "logo at the end again please", "intent": self.LOGO})
        p = self.one()
        self.assertEqual(p["id"], self.pid)
        self.assertEqual(p["videos"], ["C0001", "C0002"])

    def test_an_unknown_or_refused_id_is_refused_and_writes_nothing(self):
        with self.assertRaises(Guidance):
            RL.dismiss(self.root, "P-nothere")
        self.assertEqual(self.files(), {})

    def test_the_dismissals_are_sealed(self):
        RL.dismiss(self.root, self.pid)
        path = self.prof / RL.RULES_FILE
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["dismissed"].append({"proposal": "P-other", "from": [["C0003", "N1"]], "date": "2026-10-18"})
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(Guidance):
            RL.propose(self.root)
        doc["dismissed"] = [{"proposal": 5}]
        doc["seal"] = RL.seal_of(doc["rules"], doc["dismissed"])
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(Guidance):
            RL.propose(self.root)

    def test_a_rule_added_later_keeps_the_dismissals(self):
        RL.dismiss(self.root, self.pid)
        self.rec("C0002", {"text": "always bigger captions", "intent": UP, "scope": "standing"})
        RL.add(self.root, self.one()["id"])
        self.assertEqual(len(read_json(self.prof / RL.RULES_FILE)["dismissed"]), 1)
        self.assertEqual(self.props()["proposals"], [])


class TestReviewSurvivors(Client):
    """C8: review b399ed2 P2-4, the mutants that survived lane 2's tests."""

    def test_refused_once_is_refused_on_every_video_however_labelled(self):
        text = "hand it over the same day"                         # names no gate object: only the label refuses
        self.rec("C0001", {"text": text, "intent": {"topic": "handover", "area": "process"}})
        for vid in ("C0002", "C0003"):
            self.rec(vid, {"text": text, "intent": {"topic": "handover", "area": "other_style"}})
        r = self.props()
        self.assertEqual(r["proposals"], [])
        self.assertEqual(len(r["refused"]), 3)

    def test_the_summary_lists_the_active_rules_and_the_proposals(self):
        self.rec("C0001", {"text": "always bigger captions", "intent": UP, "scope": "standing"})
        RL.add(self.root, self.one()["id"])
        self.rec("C0002", {"text": "always end on the logo", "intent": {"topic": "logo_end", "area": "ending"},
                           "scope": "standing"})
        r = self.props()
        self.assertEqual([x["id"] for x in r["summary"]], ["R1", r["proposals"][0]["id"]])
        self.assertTrue(r["summary"][1]["ar"].startswith("مقترح: "))
        self.assertTrue(r["summary"][1]["en"].startswith("proposed: "))

    def test_every_writer_holds_the_rules_lock(self):
        self.rec("C0001", {"text": "always bigger captions", "intent": UP, "scope": "standing"})
        self.rec("C0002", {"text": "always end on the logo", "intent": {"topic": "logo_end", "area": "ending"},
                           "scope": "standing"})
        held = []
        real = RL.file_locked

        def spy(path, *a, **k):
            held.append(Path(path).name)
            return real(path, *a, **k)
        ids = [p["id"] for p in self.props()["proposals"]]
        with mock.patch.object(RL, "file_locked", spy):
            RL.add(self.root, ids[0])
            RL.dismiss(self.root, ids[1])
            RL.remove(self.root, "R1")
        self.assertEqual(held, [RL.RULES_FILE] * 3)


SKILLS = SK / "skills"
AGENTS = SK / "agents"
RULES_VERB = "def cmd_rules" in CLI.read_text(encoding="utf-8")


@unittest.skipUnless(RULES_VERB, "the `reel rules` verb and the T43 text hunks are not applied yet (executor)")
class TestTheTextTheEditorAndAgentsRead(unittest.TestCase):
    """C6: owner point 2 (where the editor sees the rules) and the brief half of point 3, in the skill and agent text."""

    def text(self, p):
        return " ".join(p.read_text(encoding="utf-8").split())      # markdown wraps long lines

    def test_revise_and_edit_show_the_rules_block(self):
        for skill in ("revise", "edit"):
            with self.subTest(skill=skill):
                t = self.text(SKILLS / skill / "SKILL.md")
                self.assertRegex(t, r"reel rules --root \S+ --propose")
                self.assertIn("ماشي على قواعد العميل دي", t)
                self.assertIn(HEADER, t)

    def test_revise_records_from_a_file_and_names_dismiss(self):
        t = self.text(SKILLS / "revise" / "SKILL.md")
        self.assertRegex(t, r"reel rules --root \S+ --video-id \S+ --record --from \S+\.json")
        self.assertIn("--dismiss", t)

    def test_agents_that_read_notes_carry_the_header_and_the_k1_line(self):
        for agent in ("story-editor", "publish-writer", "episode-analyst"):
            with self.subTest(agent=agent):
                t = self.text(AGENTS / f"{agent}.md")
                self.assertIn(HEADER, t)
                for word in ("numbers", "verse", "retake", "hook quote"):
                    self.assertIn(word, t)


if __name__ == "__main__":
    unittest.main()
