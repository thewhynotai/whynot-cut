# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 25 + K-T7, round 3 (owner pre-mortem 2026-10-18): fix the class, not more word lists.
- the lost-words check of a retake is symmetric: a word the KEPT take says and the dropped one does not counts too
  (only the words after the point where an abandoned take stopped are where the kept take goes on);
- a number word is left out of that check only when both takes read the same value AND the same unit;
- K-T7: any content word difference gives no proposed best, however many words differ (no cap of four);
- a medical or religious client never gets a retake pre-ticked (a client setting, default on for those domains; an
  unreadable or unknown subject area counts as one of them).
Run:  bash tools/test.sh -p test_safety_meaning_round3b.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import shutil
import tempfile
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib import cut_proposals as C  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402
from lib.errors import Guidance  # noqa: E402
from lib.safety import takes as T  # noqa: E402


def two_takes(a, b, gap_ms=700):
    """Two takes as a transcript gives them: one word per token, take b after a pause."""
    a, b = a.split(), b.split()
    spec = [(w, 60) for w in a[:-1]] + [(a[-1], gap_ms)] + [(w, 60) for w in b[:-1]] + [(b[-1], 300)]
    out, t = [], 0
    for i, (w, g) in enumerate(spec, 1):
        out.append({"id": i, "segment_id": 1, "word": w, "start_ms": t, "end_ms": t + 300, "probability": 0.95})
        t += 300 + g
    return out


def retake(a, b, lang="ar"):
    got = [p for p in C.compute(two_takes(a, b), lang=lang)["proposals"] if p["kind"] == "retake"]
    assert len(got) == 1, got
    return got[0]


def group(a, b):
    out, t, wid = [], 0, 1
    for s, text in enumerate((a, b), 1):
        toks = text.split()
        for k, tok in enumerate(toks):
            out.append({"id": wid, "segment_id": s, "word": tok, "start_ms": t, "end_ms": t + 300, "probability": 0.95})
            wid += 1
            t += 300 + (900 if k == len(toks) - 1 else 60)
    [g] = T.groups(out)
    return g


# --- P1: symmetric ----------------------------------------------------------------------------------------------------
class TestSymmetricWords(unittest.TestCase):
    def test_s1_the_kept_take_adds_a_word_to_a_closed_take(self):
        p = retake("الحباية دي مفيدة.", "الحباية دي مفيدة للعضم.")
        self.assertEqual(p["words"], ["الحباية", "دي", "مفيدة."])        # the closed first take is the one to drop
        self.assertEqual(p["default"], "keep")
        self.assertEqual(p["differs"], {"words": {"a": [], "b": ["للعضم"]}})
        self.assertIn("الإعادة اللي هتفضل فيها كلام مش في اللي هتتشال («للعضم»)", p["reason"])
        self.assertIn("the take to keep says words the dropped one does not (للعضم)", p["reason_en"])

    def test_s2_a_word_swapped_is_named_on_both_sides(self):
        p = retake("الحباية دي مفيدة للعضم.", "الحباية دي مفيدة للشعر.")
        self.assertEqual(p["default"], "keep")
        self.assertEqual(p["differs"], {"words": {"a": ["للعضم"], "b": ["للشعر"]}})
        self.assertLess(p["reason"].index("هتتشال فيها كلام"), p["reason"].index("هتفضل فيها كلام"))

    def test_s3_an_abandoned_take_the_kept_one_goes_on_from_is_still_proposed(self):
        p = retake("أول حاجة لازم تعرفي", "أول حاجة لازم تعرفيها كويس.")
        self.assertEqual(p["default"], "proposed")
        self.assertNotIn("differs", p)

    def test_s4_an_abandoned_take_with_a_word_added_before_where_it_stopped(self):
        p = retake("الدوا ده مفيد للكبد", "الدوا ده الجديد مفيد للكبد.")
        self.assertEqual(p["default"], "keep")
        self.assertEqual(p["differs"]["words"]["b"], ["الجديد"])

    def test_s5_the_earlier_take_kept_and_its_extra_word_counts(self):
        p = retake("الدوا ده الجديد مفيد للكبد.", "الدوا ده مفيد للكبد")
        self.assertEqual(p["words"], ["الدوا", "ده", "مفيد", "للكبد"])    # the later, unclosed take is dropped
        self.assertEqual(p["default"], "keep")
        self.assertEqual(p["differs"]["words"]["b"], ["الجديد"])

    def test_s6_a_clitic_or_a_completed_word_is_no_added_word(self):
        for a, b in (("الدوا ده مهم للضغط.", "الدوا ده مهم الضغط."), ("الدوا ده مهم الضغط.", "الدوا ده مهم للضغط."),
                     ("أول حاجة لازم تعرفي", "أول حاجة لازم تعرفيها.")):
            with self.subTest(a=a, b=b):
                p = retake(a, b)
                self.assertNotIn("differs", p)
                self.assertEqual(p["default"], "proposed")
        # round 4 (patch review P1-a): only the last word of an ABANDONED take may be a cut-off; a closed take whose
        # last word starts a kept word says something else («تعرفي.» / «تعرفيها.»)
        p = retake("أول حاجة لازم تعرفي.", "أول حاجة لازم تعرفيها.")
        self.assertEqual(p["default"], "keep")
        self.assertEqual(p["differs"], {"words": {"a": ["تعرفي"], "b": ["تعرفيها"]}})

    def test_s8_english(self):
        p = retake("this pill is helpful.", "this pill is helpful for older patients.", lang="en")
        self.assertEqual(p["default"], "keep")
        self.assertEqual(p["differs"]["words"]["b"], ["for", "older", "patients"])


# --- P2: a number word is excluded only on the same value and unit --------------------------------------------------
class TestNumbersNeedValueAndUnit(unittest.TestCase):
    def test_n1_another_unit_differs(self):
        p = retake("خد ٥ مجم من الدوا.", "خد ٥ جم من الدوا.")
        self.assertIn("numbers", p["differs"])
        self.assertEqual(p["default"], "keep")

    def test_n2_a_unit_in_one_take_only_differs(self):
        p = retake("خد ٥ مجم من الدوا.", "خد ٥ من الدوا.")
        self.assertIn("numbers", p["differs"])
        self.assertEqual(p["default"], "keep")

    def test_n3_the_same_dose_said_two_ways_is_no_lost_or_added_word(self):
        p = retake("خد خمسة مجم من الدوا.", "خد ٥ مجم من الدوا.")
        self.assertNotIn("differs", p)
        self.assertEqual(p["default"], "keep")                 # a dose said again is never ticked (unchanged)


# --- P3: K-T7 ----------------------------------------------------------------------------------------------------------
LONG_A = "today our team reviews the spring garden plan featuring roses tulips lilies daisies orchids ferns."
LONG_B = "today our team reviews the spring garden plan featuring peonies irises poppies asters orchids ferns."


class TestTakesNoBestOnWords(unittest.TestCase):
    def test_k1_one_content_word_gives_no_best(self):
        g = group("النهاردة هنتكلم عن موضوع مهم", "النهاردة هنتكلم عن موضوع جديد.")
        self.assertEqual(g["differ"], {"words": ["جديد", "مهم"]})
        self.assertIsNone(g["best"])
        self.assertIn("⚠", g["line_ar"])
        self.assertIn("مش هنقترح أفضل واحدة", g["line_ar"])
        self.assertIn("no take is proposed", g["line_en"])
        self.assertNotIn("الأفضل", g["line_ar"])

    def test_k2_more_than_four_words_still_named_and_no_best(self):
        g = group(LONG_A, LONG_B)
        self.assertIsNone(g["best"])
        self.assertEqual(len(g["differ"]["words"]), 8)
        self.assertIn("و٢ كمان", g["line_ar"])
        self.assertIn("and 2 more", g["line_en"])

    def test_k3_the_same_take_twice_still_gets_a_best(self):
        g = group("الدوا ده مهم جدا للضغط.", "الدوا ده مهم جدا للضغط.")
        self.assertEqual(g["differ"], {})
        self.assertEqual(g["best"], 2)


class TakesProject(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t25r3b_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        self.root = self.tmp / "د. تجربة Dr Test"
        (self.root / "data/Raw").mkdir(parents=True)
        (self.root / ".whynot-client").write_text("{}", encoding="utf-8")
        self.p = Paths(self.root, "C0001")
        common.set_context(self.root)


class TestTakesApplyOnWords(TakesProject):
    def test_k4_dropping_a_take_of_a_words_only_group_says_why(self):
        ws, t = [], 0
        for s, text in enumerate(("النهاردة هنتكلم عن موضوع مهم", "النهاردة هنتكلم عن موضوع جديد."), 1):
            toks = text.split()
            for k, tok in enumerate(toks):
                ws.append({"id": len(ws) + 1, "segment_id": s, "word": tok, "start_ms": t, "end_ms": t + 300,
                           "probability": 0.95})
                t += 300 + (900 if k == len(toks) - 1 else 60)
        write_json(self.p.p("02_transcription/words.json"), {"meta": {"language": "ar"}, "words": ws})
        write_json(self.p.p("01_analysis/edit-decisions.json"), {"global": {"cut_words": []}, "decisions": []})
        T.report(self.p)
        T.apply(self.p, drop=[1])
        [e] = [c for c in read_json(self.p.p("01_analysis/edit-decisions.json"))["global"]["cut_words"]]
        self.assertEqual(e["reason"], "TK-1 take dropped (no best proposed: the takes differ in words)")
        with self.assertRaises(Guidance) as cm:
            T.apply(self.p, drop=[2])
        self.assertIn("they differ in words", cm.exception.how)


# --- P4: medical and religious clients ------------------------------------------------------------------------------
A_TAKE, B_TAKE = "أول حاجة لازم تعرفي", "أول حاجة لازم تعرفيها كويس."


class DomainProject(TakesProject):
    def setUp(self):
        super().setUp()
        write_json(self.p.p("02_transcription/words.json"),
                   {"meta": {"language": "ar"}, "words": two_takes(A_TAKE, B_TAKE) + self.tail()})
        write_json(self.p.p("01_analysis/edit-decisions.json"), {"global": {}, "decisions": []})
        # round 4 (EXECUTOR RULINGS 2026-10-18 (2) item 4): an unset domain never pre-ticks, so the base client says
        # `general` explicitly (test_safety_meaning_round4.py covers the unset cases)
        self.profile({"domain": "general"})

    @staticmethod
    def tail():
        """A filler later in the clip (never touched by the retake rule)."""
        return [{"id": 100, "segment_id": 2, "word": "مممم", "start_ms": 9000, "end_ms": 9600, "probability": 0.9},
                {"id": 101, "segment_id": 2, "word": "شكرا.", "start_ms": 9700, "end_ms": 10000, "probability": 0.9}]

    def profile(self, doc, raw=None):
        f = self.root / common.CLIENT_PROFILE_REL / "profile.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        if raw is not None:
            f.write_text(raw, encoding="utf-8")
        else:
            write_json(f, doc)

    def setting(self, value, raw=None):
        f = self.root / common.CLIENT_PROFILE_REL / "cut-proposals.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        if raw is not None:
            f.write_text(raw, encoding="utf-8")
        else:
            write_json(f, {"retakes_never_preticked_for": value})

    def retakes(self, doc):
        return [p for p in doc["proposals"] if p["kind"] == "retake"]


class TestDomainSwitch(DomainProject):
    def test_d3_d4_a_general_client_is_proposed_as_before_and_an_unset_one_never(self):
        doc = C.propose(self.p)
        [r] = self.retakes(doc)
        self.assertEqual(r["default"], "proposed")
        self.assertFalse(doc["retake_pretick"]["never"])
        for dom in ("general", " General "):
            with self.subTest(dom=dom):
                self.profile({"domain": dom})
                again = C.propose(self.p)
                self.assertEqual(again["proposals"], doc["proposals"])
        for dom in ("", None):                         # round 4, ruling item 4: unset fails closed
            with self.subTest(dom=dom):
                self.profile({"domain": dom})
                [r] = self.retakes(C.propose(self.p))
                self.assertEqual(r["default"], "keep")
                self.assertIn("حدّد مجال العميل (domain)", r["reason"])

    def test_d1_d2_d12_medical_or_religious_never_pre_ticks_a_retake(self):
        for dom, ar in (("medical", "طبي"), ("religious", "ديني"), (" Medical ", "طبي"), ("RELIGIOUS", "ديني")):
            with self.subTest(dom=dom):
                self.profile({"domain": dom})
                doc = C.propose(self.p)
                [r] = self.retakes(doc)
                self.assertEqual(r["default"], "keep")
                self.assertIn(f"العميل ده مجاله {ar}", r["reason"])
                self.assertIn("never ticked for you", r["reason_en"])
                self.assertTrue(doc["retake_pretick"]["never"])
                self.assertEqual(doc["retake_pretick"]["domains"], ["medical", "religious"])

    def test_d9_fillers_are_not_touched(self):
        general = C.propose(self.p)
        self.profile({"domain": "medical"})
        medical = C.propose(self.p)
        strip = lambda d: [p for p in d["proposals"] if p["kind"] != "retake"]       # noqa: E731
        self.assertTrue(strip(general))
        self.assertEqual(strip(general), strip(medical))

    def test_d5_an_unreadable_or_unknown_subject_area_fails_closed(self):
        # (the template's placeholder «medical | religious | general» is an unset domain since round 4: round4 d1)
        for doc, raw, why in (({"domain": "طبي"}, None, "طبي"), ({"domain": "Medical clinic"}, None, "Medical clinic"),
                              ({"domain": 3}, None, "3"), (["x"], None, "profile.json"),
                              ({"review_domains": "medical"}, None, "review_domains")):
            with self.subTest(doc=doc):
                self.profile(doc, raw)
                rule = C.retake_rule()
                self.assertTrue(rule["never"])
                self.assertIn(why, rule["problem"])
                [r] = self.retakes(C.propose(self.p))
                self.assertEqual(r["default"], "keep")
                self.assertIn("مجال العميل مش واضح", r["reason"])
        self.profile(None, raw="{broken")
        rule = C.retake_rule()
        self.assertTrue(rule["never"])
        self.assertIn("profile.json", rule["problem"])

    def test_d6_the_executor_turns_it_off_per_client(self):
        self.profile({"domain": "medical"})
        self.setting([])
        doc = C.propose(self.p)
        [r] = self.retakes(doc)
        self.assertEqual(r["default"], "proposed")
        self.assertFalse(doc["retake_pretick"]["never"])
        self.assertEqual(doc["retake_pretick"]["domains"], [])
        self.setting(["religious"])
        self.assertFalse(C.retake_rule()["never"])
        self.profile({"domain": "religious"})
        self.assertTrue(C.retake_rule()["never"])

    def test_d7_a_damaged_setting_keeps_the_default(self):
        self.profile({"domain": "medical"})
        for bad in ("[]", "none", ["medical", 3], {"medical": False}, None, False):
            with self.subTest(bad=bad):
                self.setting(bad)
                rule = C.retake_rule()
                self.assertTrue(rule["never"])
                self.assertEqual(rule["domains"], ["medical", "religious"])
                self.assertIn("retakes_never_preticked_for", rule["problem"])
        self.setting(None, raw="{broken")
        self.assertTrue(C.retake_rule()["never"])

    def test_d8_review_domains_listed_by_the_profile(self):
        self.profile({"domain": "general", "review_domains": ["medical"]})
        self.assertTrue(C.retake_rule()["never"])
        self.profile({"domain": "general", "review_domains": ["business"]})
        self.assertFalse(C.retake_rule()["never"])        # the always-on medical review alone is every client

    def test_d10_flipping_the_rule_makes_the_old_list_stale(self):
        doc = C.propose(self.p)
        [r] = self.retakes(doc)
        self.profile({"domain": "medical"})
        with self.assertRaises(Guidance):
            C.accept(self.p, [r["id"]])

    def test_d11_the_editor_ticks_a_kept_retake_in_one_click(self):
        self.profile({"domain": "medical"})
        doc = C.propose(self.p)
        [r] = self.retakes(doc)
        res = C.accept(self.p, [r["id"]])
        self.assertEqual(res["added"], [r["id"]])
        cw = read_json(self.p.p("01_analysis/edit-decisions.json"))["global"]["cut_words"]
        self.assertEqual(cw[0]["word_ids"], r["word_ids"])

    def test_the_file_is_byte_identical_on_a_re_run(self):
        self.profile({"domain": "medical"})
        C.propose(self.p)
        first = self.p.p(C.FILE).read_bytes()
        C.propose(self.p)
        self.assertEqual(self.p.p(C.FILE).read_bytes(), first)
        self.assertEqual(json.loads(first)["retake_pretick"]["client"], ["medical"])


if __name__ == "__main__":
    unittest.main()
