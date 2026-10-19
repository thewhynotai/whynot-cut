# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 25 + K-T7, round 5 (executor ruling after review a31ae0c, the last fix):
- P1: an ending added on the later word that ends in «ش» / «شي» is a negation, never the rest of a cut-off word
  («بيقلل» / «بيقللوش», «عنده» / «عندهوش», «عندها» / «عندهاش», «ينفع» / «ينفعكش», «بيجي» / «بيجيليش», «تاخد» /
  «تاخدوهاش»): Task 25 leaves the retake unticked with a reason, K-T7 proposes no best and shows ⚠, for a general
  client and for a medical one; a real cut-off that adds ordinary letters («تعرفي» / «تعرفيها») is still proposed;
- P2: a later take longer than the 12-word cap that the cut would stop inside is never ticked, with the line
  «الإعادة أطول من الحد: راجع القص يدويًا» / "the retake is longer than the limit: check the cut by hand"; the cut is
  not extended on its own;
- P3: one test for each mutant that survived review a31ae0c (N8, T4, C7, C2, C4, C13; C10 and C12 are equivalent, see
  the close-out; C10's path is still pinned).
Run:  bash tools/test.sh -p test_safety_meaning_round5.py
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
from lib.common import Paths, write_json  # noqa: E402
from lib.safety import numbers as NU  # noqa: E402
from lib.safety import takes as T  # noqa: E402

# what retake_rule() gives for an explicit general client and for a medical one
GENERAL = {"never": False, "domains": ["medical", "religious"], "client": ["general"], "unset": False,
           "unclear": False, "problem": None, "problem_ar": None}
MEDICAL = {"never": True, "domains": ["medical", "religious"], "client": ["medical"], "unset": False,
           "unclear": False, "problem": None, "problem_ar": None}
RULES = (("general", GENERAL), ("medical", MEDICAL))
MEDICAL_EN = "this is a medical client, so a retake is never ticked for you"
CAP_AR = "الإعادة أطول من الحد: راجع القص يدويًا"
CAP_EN = "the retake is longer than the limit: check the cut by hand"
PRE = "الدكتور قال إن "


def two_takes(a, b, gap_ms=700):
    """Two takes as a transcript gives them: one word per token, take b after a pause."""
    a, b = a.split(), b.split()
    spec = [(w, 60) for w in a[:-1]] + [(a[-1], gap_ms)] + [(w, 60) for w in b[:-1]] + [(b[-1], 300)]
    out, t = [], 0
    for i, (w, g) in enumerate(spec, 1):
        out.append({"id": i, "segment_id": 1, "word": w, "start_ms": t, "end_ms": t + 300, "probability": 0.95})
        t += 300 + g
    return out


def retake(a, b, rule=GENERAL, cfg=None, lang=None):
    lang = lang or ("en" if a.isascii() else "ar")
    got = [p for p in C.compute(two_takes(a, b), lang=lang, rule=rule, cfg=cfg)["proposals"] if p["kind"] == "retake"]
    assert len(got) == 1, (a, b, got)
    return got[0]


def group(a, b):
    out, t, wid = [], 0, 1
    for s, text in enumerate((a, b), 1):
        toks = text.split()
        for k, tok in enumerate(toks):
            out.append({"id": wid, "segment_id": s, "word": tok, "start_ms": t, "end_ms": t + 300, "probability": 0.95})
            wid += 1
            t += 300 + (900 if k == len(toks) - 1 else 60)
    got = T.groups(out)
    assert len(got) == 1, (a, b, got)
    return got[0]


def cfg_with(**values):
    return {"values": {**C.DEFAULTS, **values}, "fillers": {k: list(v) for k, v in C.FILLERS.items()}}


class Base(unittest.TestCase):
    def safe(self, a, b, said):
        """Task 25: unticked for a general and a medical client, and the reason names `said` (the meaning check
        itself, not only the domain rule); K-T7: no best, ⚠, `said` named."""
        for name, rule in RULES:
            with self.subTest(client=name, a=a):
                p = retake(a, b, rule)
                self.assertEqual(p["default"], "keep", (name, a, b, p["reason_en"]))
                self.assertIn("differs", p)
                self.assertIn(f"«{said}»", p["reason"])
                self.assertIn(said, p["reason_en"])
                if name == "medical":
                    self.assertIn(MEDICAL_EN, p["reason_en"])
        with self.subTest(kt7=a):                        # K-T7 reads no domain: the same for every client
            g = group(a, b)
            self.assertIsNone(g["best"], (a, b, g["differ"]))
            self.assertIn("⚠", g["line_ar"])
            self.assertIn(said, g["differ"].get("words", []), g["differ"])

    def proposed(self, a, b, kt7=True):
        p = retake(a, b, GENERAL)
        self.assertEqual(p["default"], "proposed", (a, b, p.get("differs"), p["reason_en"]))
        self.assertNotIn("differs", p)
        if not kt7:
            return
        g = group(a, b)
        self.assertEqual(g["best"], 2, g["differ"])
        self.assertNotIn("words", g["differ"])


# --- P1: an ending in «ش» is a negation -----------------------------------------------------------------------------------
REVIEW_FORMS = (      # review a31ae0c P1-1: (abandoned take, kept take, the negated word)
    (PRE + "الدوا ده بيقلل", PRE + "الدوا ده بيقللوش الضغط عند الكبار.", "بيقللوش"),
    (PRE + "المريض ده عنده", PRE + "المريض ده عندهوش سكر خالص.", "عندهوش"),
    (PRE + "العيال دول بياكل", PRE + "العيال دول بياكلوش سكريات خالص.", "بياكلوش"),
    (PRE + "انتوا يا جماعة تاخد", PRE + "انتوا يا جماعة تاخدوش الحباية دي خالص.", "تاخدوش"),
)
# not in the review: «…هاش», «…كش», «…ليش», «…وهاش», «…وشي». The later words carry no meaning the reader knows (no
# timing, modal or medical word), so only this round's rule keeps them safe (each is pre-ticked on the parent, except
# «عندهاش», whose ending is exactly «ش»: the old rule caught it, kept here as the class's anchor)
OWN_FORMS = (
    (PRE + "البنت دي عندها", PRE + "البنت دي عندهاش عربية خالص.", "عندهاش"),
    (PRE + "الكلام ده يهم", PRE + "الكلام ده يهمكش خالص يا ستي.", "يهمكش"),
    (PRE + "الصداع ده بيجي", PRE + "الصداع ده بيجيليش أنا خالص.", "بيجيليش"),
    (PRE + "انتوا يا جماعة تاخد", PRE + "انتوا يا جماعة تاخدوهاش خالص.", "تاخدوهاش"),
    (PRE + "الحباية دي بتعالج", PRE + "الحباية دي بتعالجوشي الصداع النصفي.", "بتعالجوشي"),
)


class TestAnEndingInShinIsANegation(Base):
    def test_n1_the_review_forms(self):
        for a, b, said in REVIEW_FORMS:
            self.safe(a, b, said)

    def test_n2_forms_not_in_the_review(self):
        for a, b, said in OWN_FORMS:
            self.safe(a, b, said)

    def test_n3_the_negated_word_alone(self):
        for a, b, said in ((PRE + "الدوا ده بيقلل", PRE + "الدوا ده بيقللوش.", "بيقللوش"),
                           (PRE + "المريض ده عنده", PRE + "المريض ده عندهوش.", "عندهوش")):
            self.safe(a, b, said)

    def test_n4_the_helpers(self):
        for frag, word in (("بيقلل", "بيقللوش"), ("عنده", "عندهوش"), ("بياكل", "بياكلوش"), ("تاخد", "تاخدوش"),
                           ("عندها", "عندهاش"), ("ينفع", "ينفعكش"), ("يهم", "يهمكش"), ("بيجي", "بيجيليش"),
                           ("تاخد", "تاخدوهاش"),
                           ("بتعالج", "بتعالجوشي"), ("بيقلل", "بيقللش"), ("بيقلل", "بيقللشي"), ("بيقلل", "بيقللوشى"),
                           ("وبيقلل", "وبيقللوش"), ("بيقلل", "«بيقللوش».")):
            with self.subTest(frag=frag, word=word):
                self.assertFalse(C._completes(NU.fold(frag), NU.fold(word)))
                self.assertFalse(C.cut_off(frag, [word]))
        for frag, word in (("تعرفي", "تعرفيها"), ("آم", "آمنة"), ("بتق", "بتقلل"), ("preg", "pregnant"),
                           ("بيقل", "بيقللوا"), ("الشه", "الشهور")):
            with self.subTest(frag=frag, word=word):
                self.assertTrue(C._completes(NU.fold(frag), NU.fold(word)))
                self.assertTrue(C.cut_off(frag, [word]))

    def test_n4b_english_negation_tails_the_negation_reader_does_not_list(self):
        # the English tails stay ("n't", "nt", "not"): "amn't", "usedn't" are no word the negation reader lists
        for frag, word in (("am", "amn't"), ("used", "usedn't"), ("used", "usednt")):
            with self.subTest(word=word):
                self.assertFalse(C._completes(NU.fold(frag), NU.fold(word)))
                self.assertFalse(C.cut_off(frag, [word]))

    def test_n5_a_real_cut_off_with_ordinary_letters_is_still_proposed(self):
        # (K-T7 does not group this short pair as one line: Task 25 only)
        self.proposed("أول حاجة لازم تعرفي", "أول حاجة لازم تعرفيها كويس.", kt7=False)
        self.proposed(PRE + "الحباية دي بتق", PRE + "الحباية دي بتقلل الضغط عند الكبار.")
        self.proposed(PRE + "الحباية دي آم", PRE + "الحباية دي آمنة للحامل.")

    def test_n6_the_eg_doctor_fixture_is_still_proposed(self):
        doc = json.loads((SK / "tests/fixtures/cut_proposals/eg_doctor.json").read_text(encoding="utf-8"))
        got = [p for p in C.compute(doc["words"], lang="ar", rule=GENERAL)["proposals"] if p["kind"] == "retake"]
        self.assertEqual([p["default"] for p in got], ["proposed"])
        self.assertEqual(got[0]["words"][-1], "تعرفي")


class ClientProject(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t25r5_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        self.root = self.tmp / "د. تجربة Dr Test"
        (self.root / "data/Raw").mkdir(parents=True)
        (self.root / ".whynot-client").write_text("{}", encoding="utf-8")
        self.p = Paths(self.root, "C0001")
        common.set_context(self.root)
        write_json(self.p.p("01_analysis/edit-decisions.json"), {"global": {}, "decisions": []})


class TestNegationThroughTheClientsSettings(ClientProject):
    """The same pairs through propose(), with the client's own profile.json (general, then medical)."""

    def test_n7_general_and_medical_profiles(self):
        prof = self.root / common.CLIENT_PROFILE_REL / "profile.json"
        prof.parent.mkdir(parents=True, exist_ok=True)
        for dom in ("general", "medical"):
            write_json(prof, {"domain": dom})
            for a, b, said in REVIEW_FORMS:
                with self.subTest(domain=dom, said=said):
                    write_json(self.p.p("02_transcription/words.json"),
                               {"meta": {"language": "ar"}, "words": two_takes(a, b)})
                    doc = C.propose(self.p)
                    self.assertEqual(doc["retake_pretick"]["never"], dom == "medical")
                    [r] = [p for p in doc["proposals"] if p["kind"] == "retake"]
                    self.assertEqual(r["default"], "keep")
                    self.assertIn(f"«{said}»", r["reason"])


# --- P2: a later take longer than the cap ---------------------------------------------------------------------------------
L16 = "يا جماعة الدكتور قال إن الحباية دي للحامل في الشهور الأولى مش آمنة خالص ولازم تبطليها فورا."   # review a31ae0c
L13 = "الدكتور قال إن الحباية دي للحامل في الشهور الأولى والتانية مش آمنة خالص."                      # one word over
L12 = "الدكتور قال إن الحباية دي للحامل في الشهور الأولى مش آمنة خالص."                               # fits the cap
E16 = "the doctor said this pill is really not safe for pregnant women in the first months."


class TestALaterTakeLongerThanTheCap(Base):
    def test_c1_the_review_example_and_one_word_over(self):
        self.assertEqual(len(L13.split()), 13)
        for s in (L16, L13, E16):
            for name, rule in RULES:
                with self.subTest(s=s, client=name):
                    p = retake(s, s, rule)
                    self.assertEqual(p["default"], "keep", p["reason_en"])
                    self.assertIn(CAP_AR, p["reason"])
                    self.assertIn(CAP_EN, p["reason_en"])
                    self.assertLessEqual(p["confidence"], C.DEFAULTS["conf_on_purpose"])
                    # not extended on its own: the cut is the second take's first 12 words, as before
                    n = len(s.split())
                    self.assertEqual(p["word_ids"], list(range(n + 1, n + 13)))

    def test_c2_also_when_the_client_trusts_repeats(self):
        # a client whose conf_on_purpose is above keep_below: the cap line still unticks it
        for s in (L16, L13):
            with self.subTest(s=s):
                p = retake(s, s, GENERAL, cfg_with(conf_on_purpose=0.95))
                self.assertEqual(p["default"], "keep")
                self.assertIn(CAP_EN, p["reason_en"])

    def test_c3_a_take_that_fits_the_cap_has_no_cap_line(self):
        self.assertEqual(len(L12.split()), 12)
        p = retake(L12, L12, GENERAL)
        self.assertNotIn(CAP_AR, p["reason"])
        self.assertNotIn(CAP_EN, p["reason_en"])
        p = retake("أول حاجة لازم تعرفي", "أول حاجة لازم تعرفيها كويس.")
        self.assertNotIn(CAP_EN, p["reason_en"])
        # an earlier take dropped where the later one starts with no pause between: no cap line, still proposed
        ws = two_takes("أول حاجة لازم تعرفي", "أول حاجة لازم تعرفيها كويس.", gap_ms=60)
        [p] = [p for p in C.compute(ws, lang="ar", rule=GENERAL)["proposals"] if p["kind"] == "retake"]
        self.assertEqual(p["word_ids"], [1, 2, 3, 4])
        self.assertNotIn(CAP_EN, p["reason_en"])
        self.assertEqual(p["default"], "proposed")
        # a later take dropped that ends at the end of the clip with no mark: within the cap, no cap line
        p = retake("الحباية دي آمنة للحامل.", "الحباية دي آمنة للحامل")
        self.assertTrue(p["word_ids"] and min(p["word_ids"]) >= 5, p["word_ids"])      # the later take is cut
        self.assertNotIn(CAP_EN, p["reason_en"])


# --- P3: the mutants that survived review a31ae0c ---------------------------------------------------------------------------
class TestSurvivors(Base):
    def test_n8_h_m_d_are_no_time_words(self):
        # «vitamin D»: "d" is never a time word, nor "h" or "m" (a bare number, never a duration)
        for s in ("wait 5 m", "rest 2 d", "rest 3 h", "vitamin D 5 mg"):
            with self.subTest(s=s):
                q = NU.quantities([NU.fold(w) for w in s.split()])
                self.assertNotIn("duration", [x["kind"] for x in q], q)
        for w in ("h", "m", "d", "D"):
            self.assertFalse(NU.is_time(NU.fold(w)))
        self.assertEqual([x["unit"] for x in NU.quantities([NU.fold(w) for w in "vitamin D 5 mg".split()])], ["mg"])

    def test_t4_kt7_a_take_closed_by_a_semicolon_colon_or_quote_is_not_cut_short(self):
        for end in ("؛", ":", ".»"):
            a, b = PRE + "الحباية دي آم" + end, PRE + "الحباية دي آمنة للحامل."
            with self.subTest(end=end):
                g = group(a, b)
                self.assertIsNone(g["best"], g["differ"])
                self.assertIn("للحامل", g["differ"].get("words", []))
                self.assertEqual(retake(a, b)["default"], "keep")

    def test_c7_added_or_lost_words_untick_whatever_conf_on_purpose_is(self):
        cfg = cfg_with(conf_on_purpose=0.95)
        for a, b, said in (("الحباية دي آمنة", "الحباية دي آمنة للحامل.", "للحامل"),
                           ("الحباية دي آمنة للحامل.", "الحباية دي آمنة.", "للحامل")):
            with self.subTest(a=a):
                p = retake(a, b, GENERAL, cfg)
                self.assertEqual(p["default"], "keep", p["reason_en"])
                self.assertIn(f"«{said}»", p["reason"])

    def test_c2_a_one_letter_word_is_no_cut_off(self):
        for frag, word in (("ب", "بتقلل"), ("b", "bad"), ("و", "والضغط")):
            with self.subTest(frag=frag):
                self.assertFalse(C.cut_off(frag, [word]))
        a, b = PRE + "الحباية دي ب", PRE + "الحباية دي بتقلل الضغط عند الكبار."
        self.assertEqual(retake(a, b)["default"], "keep")
        self.assertIsNone(group(a, b)["best"])

    def test_c4_a_cut_mark_on_a_number_word_is_no_cut_off(self):
        for frag, word in (("ب٥-", "ب٥٠"), ("five-", "fifty"), ("خمس-", "خمستاشر"), ("بخمس-", "بخمستاشر"), ("5-", "50")):
            with self.subTest(frag=frag):
                self.assertFalse(C.cut_off(frag, [word]))
        self.assertTrue(C.cut_off("ba-", ["women"]))         # a cut mark on any other word still is

    def test_c13_a_word_with_a_digit_is_a_number_word(self):
        for w in ("b12", "b1", "covid19", "d3"):
            with self.subTest(w=w):
                self.assertTrue(C._number_word(w))
        self.assertFalse(C.cut_off("b1", ["b12"]))
        a, b = "the doctor said take vitamin b1", "the doctor said take vitamin b12 every day."
        self.assertEqual(retake(a, b)["default"], "keep")
        self.assertIsNone(group(a, b)["best"])


class TestProfileNotAnObject(ClientProject):
    def test_c10_a_profile_that_is_no_object_is_unclear_and_named(self):
        # load_config already refuses a profile.json that is no object, so retake_rule's own check behind it is a
        # second guard that today's reader never reaches (mutant C10 is equivalent): this pins what the editor gets
        prof = self.root / common.CLIENT_PROFILE_REL / "profile.json"
        prof.parent.mkdir(parents=True, exist_ok=True)
        for raw in ('["medical"]', '"general"', "3"):
            with self.subTest(raw=raw):
                prof.write_text(raw, encoding="utf-8")
                rule = C.retake_rule()
                self.assertTrue(rule["never"])
                self.assertTrue(rule["unclear"])
                self.assertIn("profile.json could not be read", rule["problem"])
                self.assertIn("ملف profile.json مش مقروء", rule["problem_ar"])
                self.assertIn("مجال العميل مش واضح", C._rule_reason(rule)[0])


if __name__ == "__main__":
    unittest.main()
