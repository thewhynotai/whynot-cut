# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 67 (Addendum K1, K-T7) — repeated takes: numbered sentences, take groups with the better take
proposed from measured features, `--drop/--keep` written into the plan's cut list, `--undo` one step at a time, and
nothing cut before the plan is approved again. Fixtures: tests/fixtures/safety/kt7 (made-up transcripts).
Run:  bash tools/test.sh -p test_safety_takes.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402
from lib.errors import Guidance  # noqa: E402
from lib.safety import takes as T  # noqa: E402

FIX = SK / "tests/fixtures/safety/kt7"


def fixture(name):
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def words(sentences):
    """[(text, probability, gap_after_ms)] -> word records, one segment per sentence."""
    out, t, wid = [], 0, 1
    for s, (text, p, gap) in enumerate(sentences, 1):
        toks = text.split()
        for k, tok in enumerate(toks):
            out.append({"id": wid, "segment_id": s, "word": tok, "start_ms": t, "end_ms": t + 300, "probability": p})
            wid += 1
            t += 300 + (gap if k == len(toks) - 1 else 60)
    return out


def group_numbers(res):
    return [[s["n"] for s in g["takes"]] for g in res]


class TestNumberingAndGroups(unittest.TestCase):
    def test_numbering_stable(self):
        fx = fixture("ar")
        a = T.sentences(fx["words"])
        b = T.sentences(list(reversed(fx["words"])))
        self.assertEqual(a, b)
        self.assertEqual([s["n"] for s in a], list(range(1, len(a) + 1)))
        self.assertEqual(json.dumps(T.groups(fx["words"]), ensure_ascii=False),
                         json.dumps(T.groups(fx["words"]), ensure_ascii=False))

    def test_fixture_groups_and_the_better_take_match_the_hand_labels(self):
        for name in ("ar", "en", "mixed"):
            with self.subTest(fixture=name):
                fx = fixture(name)
                res = T.groups(fx["words"])
                self.assertEqual(group_numbers(res), fx["groups"])
                self.assertEqual([g["best"] for g in res], fx["best"])

    def test_three_takes_best_is_the_last_one(self):
        res = T.groups(fixture("ar")["words"])
        g = [g for g in res if len(g["takes"]) == 3][0]
        self.assertEqual(g["best"], 6)
        self.assertTrue(g["line_ar"].startswith("٤ و ٥ و ٦ نفس الجملة: الأفضل ٦"))
        self.assertIn("same sentence", g["line_en"])

    def test_better_take_features(self):
        base = [("الدوا ده مهم جدا للضغط.", 0.95, 900), ("الدوا ده مهم جدا للضغط.", 0.95, 300)]
        self.assertEqual(T.groups(words(base))[0]["best"], 2)                     # a tie keeps the later
        mumbled = [("الدوا ده مهم جدا للضغط.", 0.95, 900), ("الدوا ده مهم جدا للضغط.", 0.55, 300)]
        self.assertEqual(T.groups(words(mumbled))[0]["best"], 1)
        filler = [("الدوا ده مهم جدا للضغط.", 0.95, 900), ("الدوا ده اممم مهم جدا للضغط.", 0.95, 300)]
        self.assertEqual(T.groups(words(filler))[0]["best"], 1)
        restart = [("الدوا ده مهم جدا للضغط.", 0.95, 900), ("الدوا ده مه مهم جدا للضغط.", 0.95, 300)]
        self.assertEqual(T.groups(words(restart))[0]["best"], 1)
        cut = [("الدوا ده مهم جدا للضغط.", 0.95, 900), ("الدوا ده مهم جدا", 0.95, 900), ("خلاص.", 0.95, 0)]
        self.assertEqual(T.groups(words(cut))[0]["best"], 1)

    def test_clipping_counts_only_when_audio_is_given(self):
        ws = words([("الدوا ده مهم جدا للضغط.", 0.95, 900), ("الدوا ده مهم جدا للضغط.", 0.95, 300)])
        sr = 1000
        n = ws[-1]["end_ms"] + 100
        samples = [0.1] * n
        for k in range(ws[5]["start_ms"], ws[-1]["end_ms"]):       # the second take clips
            samples[k] = 1.0
        self.assertEqual(T.groups(ws)[0]["best"], 2)
        g = T.groups(ws, samples=samples, sr=sr)[0]
        self.assertEqual(g["best"], 1)
        self.assertIn("clipping", g["takes"][1]["features"])

    def test_a_different_sentence_is_not_a_take(self):
        ws = words([("الضغط مرض صامت.", 0.95, 700), ("السكر محتاج متابعة.", 0.95, 700)])
        self.assertEqual(T.groups(ws), [])


class Project(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kt7_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        self.root = self.tmp / "د. تجربة Dr Test"
        for d in ("assets", "data/Raw"):
            (self.root / d).mkdir(parents=True)
        (self.root / ".whynot-client").write_text("{}", encoding="utf-8")
        self.p = Paths(self.root, "C0001")
        common.set_context(self.root)
        self.fx = fixture("ar")
        write_json(self.p.p("02_transcription/words.json"), {"meta": {"language": "ar"}, "words": self.fx["words"]})
        write_json(self.p.p("01_analysis/edit-decisions.json"),
                   {"global": {"cut_words": [{"word_ids": [1], "reason": "editor's own cut"}]}, "decisions": []})
        write_json(self.p.p("01_analysis/timeline-spec.json"), {"events": []})
        write_json(self.p.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor"})
        self.ed = self.p.p("01_analysis/edit-decisions.json")
        T.report(self.p)                       # the editor chooses from a listing

    def words_of(self, n):
        s = [s for s in T.sentences(self.fx["words"]) if s["n"] == n][0]
        return s["word_ids"]

    def tk_entries(self):
        return [c for c in read_json(self.ed)["global"]["cut_words"] if str(c.get("reason", "")).startswith("TK-")]


class TestApply(Project):
    def test_report_lists_groups_and_writes_nothing_but_its_state(self):
        before = self.ed.read_bytes()
        rep = T.report(self.p)
        self.assertEqual(group_numbers(rep["groups"]), self.fx["groups"])
        self.assertTrue(rep["lines"][0].startswith("٢ و ٣ نفس الجملة"))
        self.assertEqual(self.ed.read_bytes(), before)

    def test_drop_keep_writes_plan(self):
        T.apply(self.p, drop=[2, 4], keep=[5])
        ids = sorted(i for c in self.tk_entries() for i in c["word_ids"])
        self.assertEqual(ids, sorted(self.words_of(2) + self.words_of(4)))
        self.assertEqual([c["reason"].split(" ")[0] for c in self.tk_entries()], ["TK-2", "TK-4"])
        self.assertIn({"word_ids": [1], "reason": "editor's own cut"}, read_json(self.ed)["global"]["cut_words"])
        first = [c for c in self.tk_entries() if c["reason"].startswith("TK-2 ")][0]
        ws = {w["id"]: w for w in self.fx["words"]}
        a, b = first["range_ms"]                                    # one range: the take and the breath after it
        self.assertLessEqual(a, ws[first["word_ids"][0]]["start_ms"])
        self.assertGreaterEqual(b, ws[first["word_ids"][-1]]["end_ms"])
        self.assertLess(b, ws[first["word_ids"][-1] + 1]["start_ms"])
        T.apply(self.p, keep=[4])                                   # keep brings a dropped take back
        self.assertEqual([c["reason"].split(" ")[0] for c in self.tk_entries()], ["TK-2"])
        T.apply(self.p, drop=[2])                                   # idempotent
        self.assertEqual(len(self.tk_entries()), 1)

    def test_undo_restores_exact(self):
        b0 = self.ed.read_bytes()
        T.apply(self.p, drop=[2])
        b1 = self.ed.read_bytes()
        T.apply(self.p, drop=[4, 5])
        T.undo(self.p)
        self.assertEqual(self.ed.read_bytes(), b1)
        T.undo(self.p)
        self.assertEqual(self.ed.read_bytes(), b0)
        with self.assertRaises(Guidance) as cm:                      # nothing left to undo
            T.undo(self.p)
        self.assertTrue(str(cm.exception).startswith("مفيش خطوة"))
        self.assertEqual(self.ed.read_bytes(), b0)

    def test_no_cut_before_approval(self):
        spec, appr = (self.p.p(f).read_bytes() for f in ("01_analysis/timeline-spec.json",
                                                          "01_analysis/plan-approval.json"))
        res = T.apply(self.p, drop=[2])
        self.assertEqual(self.p.p("01_analysis/timeline-spec.json").read_bytes(), spec)
        self.assertEqual(self.p.p("01_analysis/plan-approval.json").read_bytes(), appr)
        self.assertIn("reel plan", res["next"])
        self.assertIn("approve", res["next"])

    def test_refusals_write_nothing(self):
        before = self.ed.read_bytes()
        for kw in ({"drop": [99]}, {"drop": [2], "keep": [2]}, {"drop": [4, 5, 6]}, {}, {"drop": [0]}):
            with self.subTest(kw=kw):
                with self.assertRaises(Guidance):
                    T.apply(self.p, **kw)
                self.assertEqual(self.ed.read_bytes(), before)
                self.assertFalse(self.p.p(T.HISTORY).exists())

    def test_stale_numbers_are_refused(self):
        T.report(self.p)
        wf = self.p.p("02_transcription/words.json")
        d = read_json(wf)
        d["words"][0]["word"] = "مرحبا"
        write_json(wf, d)
        before = self.ed.read_bytes()
        with self.assertRaises(Guidance) as cm:          # the numbers the editor saw belong to the old words
            T.apply(self.p, drop=[2])
        self.assertIn("التفريغ اتغير", str(cm.exception))
        self.assertEqual(self.ed.read_bytes(), before)
        T.report(self.p)                                 # listed again: the new numbers can be used
        T.apply(self.p, drop=[2])
        self.assertEqual(len(self.tk_entries()), 1)

    def test_missing_edit_decisions_refused(self):
        self.ed.unlink()
        with self.assertRaises(Guidance):
            T.apply(self.p, drop=[2])
        self.assertFalse(self.ed.exists())

    def test_missing_or_damaged_words_refused(self):
        wf = self.p.p("02_transcription/words.json")
        wf.write_text("{x", encoding="utf-8")
        with self.assertRaises(Guidance):
            T.report(self.p)

    def test_same_on_macos(self):
        a = T.report(self.p)
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertEqual(T.report(self.p), a)


# --- review round 1 (independent reviewer, 2026-10-17): I1–I7 and the Minors -----------------------------------------
class TestReviewRound1Groups(unittest.TestCase):
    def test_i1_takes_that_differ_in_a_dose_are_flagged(self):
        ws = words([("خد الدواء ده خمسمية مجم مرتين في اليوم", 0.95, 900),
                    ("خد الدواء ده خمسمية مجم مرة في اليوم.", 0.95, 300)])
        g = T.groups(ws)[0]
        self.assertIn("numbers", g["differ"])
        self.assertIn("⚠", g["line_ar"])
        self.assertLess(g["line_ar"].index("نفس الجملة"), g["line_ar"].index("⚠"))
        same = words([("خد الدواء ده خمسمية مجم مرتين في اليوم", 0.95, 900),
                      ("خد الدواء ده خمسمية مجم مرتين في اليوم.", 0.95, 300)])
        self.assertEqual(T.groups(same)[0]["differ"], {})

    def test_i1_takes_that_differ_in_a_negation_or_a_word_are_flagged(self):
        g = T.groups(words([("الدوا ده بيعالج البرد", 0.95, 900), ("الدوا ده مش بيعالج البرد.", 0.95, 300)]))[0]
        self.assertTrue(g["differ"].get("negation"))
        g = T.groups(words([("النهاردة هنتكلم عن مرض السكر", 0.95, 900),
                            ("النهاردة هنتكلم عن مرض الضغط.", 0.95, 300)]))[0]
        self.assertIn("words", g["differ"])

    def test_r2_tie_line_reads_well_and_harmless_differences_stay_quiet(self):
        g = T.groups(words([("الدوا ده مهم جدا للضغط.", 0.95, 900), ("الدوا ده مهم جدا للضغط.", 0.95, 300)]))[0]
        self.assertNotIn("وولما", g["line_ar"])
        self.assertIn("؛ ولما اتساووا اخترنا الأخيرة", g["line_ar"])
        for a, b in (("الدواء ده مهم للضغط", "والدواء ده مهم للضغط."),
                     ("خد خمسمية مجم من الدوا", "خد ٥٠٠ مجم من الدوا.")):
            with self.subTest(a=a):
                g = T.groups(words([(a, 0.95, 900), (b, 0.95, 300)]))[0]
                self.assertEqual(g["differ"], {})

    def test_no_chains(self):
        # B matches A, C matches B, but C does not match A: C is not pulled into A's line
        ws = words([("الأكل الصحي مهم للضغط", 0.95, 900), ("الأكل الصحي مهم للضغط والقلب والسكر", 0.95, 900),
                    ("مهم للضغط والقلب والسكر", 0.95, 900)])
        from lib import cut_proposals as CP
        ss = T.sentences(ws)
        V, F = CP.settings()["values"], CP.settings()["fillers"]
        self.assertTrue(T._same(ss[1], ss[2], F, V))
        self.assertFalse(T._same(ss[0], ss[2], F, V))
        self.assertEqual(group_numbers(T.groups(ws)), [[1, 2]])

    def test_i7_a_much_quieter_take_loses_when_audio_is_given(self):
        ws = words([("الدوا ده مهم جدا للضغط.", 0.95, 900), ("الدوا ده مهم جدا للضغط.", 0.95, 300)])
        sr, n = 1000, ws[-1]["end_ms"] + 100
        samples = [0.3] * n
        for k in range(ws[5]["start_ms"], ws[-1]["end_ms"]):
            samples[k] = 0.01
        g = T.groups(ws, samples=samples, sr=sr)[0]
        self.assertEqual(g["best"], 1)
        self.assertLess(g["takes"][1]["features"]["level_db"], g["takes"][0]["features"]["level_db"] - 10)

    def test_minor_numbers_with_arabic_comma_and_odd_digits(self):
        self.assertEqual(T._ints(["٤،٥", "7"], "--drop"), [4, 5, 7])
        with self.assertRaises(Guidance):
            T._ints(["²"], "--drop")


class TestReviewRound1Apply(Project):
    def test_i3_no_listing_no_drop(self):
        self.p.p(T.FILE).unlink()
        before = self.ed.read_bytes()
        with self.assertRaises(Guidance) as cm:
            T.apply(self.p, drop=[2])
        self.assertIn("reel takes", cm.exception.how if hasattr(cm.exception, "how") else str(cm.exception))
        self.assertEqual(self.ed.read_bytes(), before)
        self.p.p(T.FILE).write_text("{x", encoding="utf-8")
        with self.assertRaises(Guidance):
            T.apply(self.p, drop=[2])

    def test_i4_settings_changed_after_the_listing_are_refused(self):
        write_json(self.root / common.CLIENT_PROFILE_REL / "cut-proposals.json",
                   {"thresholds": {"complete_pause_ms": {"value": 2000, "basis": "test"}}})
        before = self.ed.read_bytes()
        with self.assertRaises(Guidance):
            T.apply(self.p, drop=[2])
        self.assertEqual(self.ed.read_bytes(), before)

    def test_i2_keep_and_drop_follow_the_words_not_the_label(self):
        T.apply(self.p, drop=[2])
        ed = read_json(self.ed)
        for c in ed["global"]["cut_words"]:
            if str(c.get("reason", "")).startswith("TK-2"):
                c["reason"] = "TK-9 a stale label"
        write_json(self.ed, ed)
        T.report(self.p)
        T.apply(self.p, keep=[2])                       # finds the entry by its words, whatever its label
        self.assertEqual(self.tk_entries(), [])

    def test_i5_words_cut_by_another_entry_count(self):
        ed = read_json(self.ed)
        ed["global"]["cut_words"].append({"word_ids": self.words_of(5), "reason": "CP-007 retake: x"})
        write_json(self.ed, ed)
        res = T.apply(self.p, drop=[5])
        self.assertEqual(res["already"], [5])
        self.assertEqual(self.tk_entries(), [])
        before = self.ed.read_bytes()
        with self.assertRaises(Guidance):                # 4 and 6 dropped + 5 cut by the proposal = the line is gone
            T.apply(self.p, drop=[4, 6])
        self.assertEqual(self.ed.read_bytes(), before)

    def test_i6_undo_never_overwrites_later_changes(self):
        T.apply(self.p, drop=[2])
        ed = read_json(self.ed)
        ed["global"]["note"] = "the story editor changed something"
        write_json(self.ed, ed)
        after = self.ed.read_bytes()
        with self.assertRaises(Guidance) as cm:
            T.undo(self.p)
        self.assertTrue(str(cm.exception).startswith("الخطة اتغيرت"))
        self.assertEqual(self.ed.read_bytes(), after)

    def test_minor_damaged_history_is_refused_plainly(self):
        T.apply(self.p, drop=[2])
        self.p.p(T.HISTORY).write_text("{x", encoding="utf-8")
        with self.assertRaises(Guidance):
            T.undo(self.p)
        with self.assertRaises(Guidance):
            T.apply(self.p, drop=[4])

    def test_r2_an_untouched_line_cut_elsewhere_never_blocks_a_drop(self):
        ed = read_json(self.ed)                          # line 2/3 cut whole by hand, before any takes step
        ed["global"]["cut_words"].append({"word_ids": self.words_of(2) + self.words_of(3), "reason": "editor"})
        write_json(self.ed, ed)
        res = T.apply(self.p, drop=[4])
        self.assertTrue(res["changed"])

    def test_r2_keep_of_a_take_cut_by_another_entry_says_so(self):
        ed = read_json(self.ed)
        ed["global"]["cut_words"].append({"word_ids": self.words_of(5), "reason": "CP-004 filler: x"})
        write_json(self.ed, ed)
        res = T.apply(self.p, keep=[5])
        self.assertEqual(res["blocked_by_other_cuts"], [5])
        self.assertTrue(res["note"].startswith("الجمل ٥ لسه متشالة"))

    def test_minor_bad_cut_words_type_is_refused(self):
        write_json(self.ed, {"global": {"cut_words": "x"}})
        with self.assertRaises(Guidance):
            T.apply(self.p, drop=[2])



# --- acceptance follow-ups (executor, 2026-10-17): the shared meaning reader, no best when the meaning differs ---------
def pair(a, b):
    return T.groups(words([(a, 0.95, 900), (b, 0.95, 300)]))[0]


class TestMeaningDiffers(unittest.TestCase):
    def assertNoBest(self, g):
        self.assertIsNone(g["best"])
        self.assertNotIn("الأفضل", g["line_ar"])
        self.assertNotIn("best ", g["line_en"].split("—")[0])
        self.assertIn("اسمعهم", g["line_ar"])
        self.assertNotIn("None", g["line_ar"] + g["line_en"])

    def test_c1_arabic_negated_verb(self):
        g = pair("الدوا ده بيقلل الضغط عند الكبار في السن جدا", "الدوا ده مبيقللش الضغط عند الكبار في السن جدا.")
        self.assertEqual(g["differ"]["negation"], ["مبيقللش"])
        self.assertNoBest(g)
        self.assertIn("نفي", g["line_ar"])
        self.assertIn("«مبيقللش»", g["line_ar"])
        self.assertLess(g["line_ar"].index("نفس الجملة"), g["line_ar"].index("⚠"))

    def test_c2_english_contractions_and_no_doesn_t(self):
        for a, b, neg in (("this drug lowers blood pressure in older patients a lot",
                           "this drug doesn't lower blood pressure in older patients a lot.", "doesn't"),
                          ("this drug is safe for pregnant women in the first months",
                           "this drug isn't safe for pregnant women in the first months.", "isn't")):
            with self.subTest(neg=neg):
                g = pair(a, b)
                self.assertEqual(g["differ"]["negation"], [neg])
                self.assertNoBest(g)
                blob = json.dumps(g, ensure_ascii=False)
                self.assertNotIn(neg.replace("'", " "), blob)

    def test_c3_timing(self):
        for a, b, said in (("خدي حباية واحدة الصبح بعد الفطار", "خدي حباية واحدة بالليل بعد الفطار.", ["الصبح", "بالليل"]),
                           ("خدي الدوا بعد الفطار كل يوم", "خدي الدوا قبل الفطار كل يوم.", ["بعد الفطار", "قبل الفطار"])):
            with self.subTest(a=a):
                g = pair(a, b)
                self.assertEqual(g["differ"]["timing"], said)
                self.assertNoBest(g)
                self.assertIn("توقيت", g["line_ar"])

    def test_c4_dose(self):
        g = pair("خدي حباية واحدة من الدوا ده الصبح", "خدي حبايتين من الدوا ده الصبح.")
        self.assertEqual(g["differ"]["numbers"], ["حباية واحدة", "حبايتين"])
        self.assertNoBest(g)

    def test_c5_negation_reported_past_the_words_cap(self):
        a = ("الدكتور قال إن الدوا ده بيقلل الضغط عند الكبار في السن وده مهم جدا للناس اللي عندها مشاكل في القلب "
             "والكلى والسكر والكبد وكمان للستات الحوامل في الشهور الأولى من الحمل")
        b = ("الدكتور قال إن الدوا ده مبيقللش الضغط عند الكبار في السن وده مهم جدا للناس اللي عندها مشاكل في الرئة "
             "والمعدة والعظام والمخ وكمان للستات الحوامل في الشهور الأولى من الحمل.")
        g = pair(a, b)
        self.assertNotIn("words", g["differ"])                 # more than 4 words differ: the word list stays quiet
        self.assertEqual(g["differ"]["negation"], ["مبيقللش"])
        self.assertNoBest(g)

    def test_c6_three_takes_only_the_last_negated(self):
        res = T.groups(words([("الدوا ده بيقلل الضغط عند الكبار", 0.95, 900),
                              ("الدوا ده بيقلل الضغط عند الكبار", 0.95, 900),
                              ("الدوا ده مبيقللش الضغط عند الكبار.", 0.95, 300)]))
        g = res[0]
        self.assertEqual(group_numbers(res), [[1, 2, 3]])
        self.assertNoBest(g)
        self.assertEqual([p["takes"] for p in g["differ"]["pairs"]], [[1, 3], [2, 3]])
        self.assertIn("١ مقابل ٣", g["line_ar"])

    def test_c7_same_meaning_keeps_a_best(self):
        for a, b in (("الدواء ده مهم للضغط", "والدواء ده مهم للضغط."), ("خد خمسمية مجم من الدوا", "خد ٥٠٠ مجم من الدوا."),
                     ("الدوا ده مش بيقلل الضغط عند الكبار في السن خالص",
                      "الدوا ده مبيقللش الضغط عند الكبار في السن خالص.")):
            with self.subTest(a=a):
                g = pair(a, b)
                self.assertEqual(g["differ"], {})
                self.assertEqual(g["best"], 2)

    def test_c8_a_content_word_alone_warns_and_keeps_the_proposal(self):
        g = pair("النهاردة هنتكلم عن مرض السكر", "النهاردة هنتكلم عن مرض الضغط.")
        self.assertEqual(g["differ"], {"words": ["السكر", "الضغط"]})
        self.assertEqual(g["best"], 2)
        self.assertIn("⚠", g["line_ar"])

    def test_c13_a_take_that_may_have_stopped_early_still_gets_no_best(self):
        # 7193e9a P2-1 (executor ruling 2026-10-17 20:10): a start that may have stopped early is no exception: a dose
        # more and an abandoned start look the same on paper, so the editor listens and chooses
        res = T.groups(fixture("mixed")["words"])           # «خدي الـ vitamin D» then «… ألف وحدة كل يوم.»
        self.assertIsNone(res[0]["best"])
        self.assertEqual(res[0]["differ"]["pairs"][0]["cut_short"], 1)
        self.assertNotIn("cut_short", res[0]["differ"])
        self.assertIn("⚠ ١ يمكن تكون وقفت قبل: رقم أو جرعة «ألف وحدة كل يوم»", res[0]["line_ar"])
        self.assertIn("1 may have stopped before: number or dose", res[0]["line_en"])
        self.assertIn("اسمعهم واختار انت", res[0]["line_ar"])
        g = pair("خدي حباية واحدة من الدوا ده", "خدي حباية واحدة من الدوا ده الصبح بعد الفطار.")
        self.assertIsNone(g["best"])
        self.assertCountEqual(g["differ"]["timing"], ["الصبح", "بعد الفطار"])
        # a cut-off take that says something else where it overlaps is a plain difference
        g = pair("خدي حباية واحدة من الدوا ده بالليل", "خدي حباية واحدة من الدوا ده الصبح بعد الفطار.")
        self.assertIsNone(g["best"])
        self.assertCountEqual(g["differ"]["timing"], ["بالليل", "الصبح", "بعد الفطار"])
        self.assertNotIn("cut_short", g["differ"]["pairs"][0])

    def test_c14_a_closed_take_that_leaves_out_the_timing_differs(self):
        g = pair("خدي حباية واحدة من الدوا ده.", "خدي حباية واحدة من الدوا ده الصبح.")
        self.assertEqual(g["differ"]["timing"], ["الصبح"])
        self.assertIsNone(g["best"])
        self.assertIn("(مفيش) مقابل «الصبح»", g["line_ar"])

    def test_c15_the_cut_off_take_is_never_proposed_past_a_meaning(self):
        ws = words([("خدي حباية واحدة من الدوا ده", 0.95, 900), ("خدي حباية واحدة من الدوا ده الصبح بعد الفطار.", 0.95, 300)])
        with mock.patch.object(T, "_rank_key", lambda f, idx, loudest: (-idx,)):      # rank the cut-off take first
            g = T.groups(ws)[0]
        self.assertIsNone(g["best"])
        self.assertEqual(g["differ"]["timing"], ["بعد الفطار", "الصبح"])

    def test_r1_c1_a_later_shorter_take_without_full_stops_still_differs(self):
        # Whisper often writes no full stop: a later, shorter correction is a full take, never "cut short"
        for a, b, kind in (("خدي حباية واحدة الصبح وحباية بالليل", "خدي حباية واحدة الصبح", "timing"),
                           ("الحباية دي بتتاخد على الريق قبل الفطار", "الحباية دي بتتاخد على الريق", "timing"),
                           ("you can take this pill with food but not with alcohol", "you can take this pill with food",
                            "negation")):
            with self.subTest(a=a):
                g = T.groups(words([(a, 0.95, 900), (b, 0.95, 300)]))[0]
                self.assertIn(kind, g["differ"])
                self.assertIsNone(g["best"])
                label = {"timing": "توقيت", "negation": "نفي"}[kind]          # the meaning is named, not a fragment
                self.assertIn(label + ":", g["line_ar"])
                self.assertNotIn("(قبل)", g["line_ar"])
        a = "خدي حباية واحدة الصبح وحباية بالليل"
        g = T.groups(words([(a, 0.95, 900), ("خدي حباية واحدة الصبح", 0.95, 900), (a, 0.95, 300)]))[0]
        self.assertIsNone(g["best"])

    def test_r1_i1_an_abandoned_start_names_what_it_left_out_not_as_words(self):
        g = T.groups(words([("خدي حباية واحدة الصبح", 0.95, 900), ("خدي حباية واحدة الصبح يوميا كمان", 0.95, 300)]))[0]
        self.assertIsNone(g["best"])                               # 7193e9a P2-1: no best past a meaning
        self.assertNotIn("words", g["differ"])
        self.assertIn("توقيت «يوميا»", g["line_ar"])

    def test_r2_minors_the_note_and_the_words_after_an_abandoned_start(self):
        g = T.groups(words([("مش لازم تاخدي الدوا ده", 0.95, 900), ("مش لازم تاخدي الدوا ده ولا لازم تكمليه", 0.95, 300)]))[0]
        self.assertIn("نفي «ولا»", g["line_ar"])                 # the cut-off take said «مش» too
        self.assertNotIn("«مش»", g["line_ar"])
        g = T.groups(words([("خدي حباية واحدة من", 0.95, 900), ("خدي حباية واحدة من الدوا ده", 0.95, 900),
                            ("خدي حباية واحدة من الدوا ده مرتين في اليوم بعد الأكل", 0.95, 300)]))[0]
        self.assertNotIn("words", g["differ"])                   # take 1 only stopped before «الدوا»

    def test_r3_a_word_said_again_and_words_among_the_full_takes(self):
        g = T.groups(words([("you should not take this pill", 0.95, 900),
                            ("you should not take this pill and not with milk", 0.95, 300)]))[0]
        self.assertIn("negation \"not\"", g["line_en"])         # the second «not» is new, counted, not matched away
        g = T.groups(words([("مش لازم تاخدي الدوا ده", 0.95, 900), ("مش لازم تاخدي الدوا ده مش كل يوم", 0.95, 300)]))[0]
        self.assertIn("نفي «مش»", g["line_ar"])
        g = T.groups(words([("النهاردة هنتكلم عن مرض", 0.95, 900), ("النهاردة هنتكلم عن مرض السكر الصبح", 0.95, 900),
                            ("النهاردة هنتكلم عن مرض الضغط الصبح.", 0.95, 300)]))[0]
        self.assertEqual(g["differ"]["words"], ["السكر", "الضغط"])  # the full takes are compared with each other
        g = T.groups(words([("النهاردة هنتكلم عن مرض", 0.95, 900),
                            ("النهاردة هنتكلم عن مرض السكر عند الكبار", 0.95, 900),
                            ("النهاردة هنتكلم عن مرض السكر عند الصغار.", 0.95, 300)]))[0]
        self.assertEqual(g["differ"]["words"], ["الصغار", "الكبار"])   # never «السكر»: take 1 just did not get there

    def test_c12_words_shown_as_said(self):
        g = pair("today we talk about the patient's diet and sleep", "today we talk about the Doctor's diet and sleep.")
        self.assertEqual(g["differ"]["words"], ["Doctor's", "patient's"])
        g = pair("النهاردة هنتكلم عن مرض للسكر", "النهاردة هنتكلم عن مرض «الضغط».")
        self.assertEqual(g["differ"]["words"], ["الضغط", "للسكر"])


class TestApplyWhenMeaningDiffers(Project):
    def setUp(self):
        super().setUp()
        self.fx = {"words": words([("الدوا ده بيقلل الضغط عند الكبار", 0.95, 900),
                                   ("الدوا ده مبيقللش الضغط عند الكبار.", 0.95, 300)])}
        write_json(self.p.p("02_transcription/words.json"), {"meta": {"language": "ar"}, "words": self.fx["words"]})
        write_json(self.ed, {"global": {"cut_words": []}, "decisions": []})
        self.rep = T.report(self.p)

    def test_c9_listing_drop_and_refusal_without_a_best(self):
        self.assertIsNone(self.rep["groups"][0]["best"])
        self.assertEqual(read_json(self.p.p(T.FILE))["best"], [None])
        res = T.apply(self.p, drop=[1])
        self.assertTrue(res["changed"])
        [e] = self.tk_entries()
        self.assertEqual(e["reason"], "TK-1 take dropped (no best proposed: the takes differ in meaning)")
        with self.assertRaises(Guidance) as cm:
            T.apply(self.p, drop=[2])
        self.assertNotIn("None", str(cm.exception) + str(getattr(cm.exception, "fix", "")))


if __name__ == "__main__":
    unittest.main()
