# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 25 + K-T7, round 4 (EXECUTOR RULINGS 2026-10-18 (2), the final bounded round):
- the cut-off prefix rule only for the LAST word of an ABANDONED take, never for a negated form («بيقلل» / «بيقللش») or
  a word that holds a number («بخمس» / «بخمستاشر»);
- the abandoned-take exemption only at a real cut-off (the last word is a strict prefix of a kept word, a hesitation
  sound, or a word written as cut): every other word the kept or longer take adds is a difference (Task 25 leaves the
  retake unticked, K-T7 gives no best and names the words);
- a closing quote after the mark, «؛» and «:» close a take;
- the lost/added word check runs over the whole retake match, not only the part that is cut;
- a number word the reader did not read as a number («بربع», «ب٥») is never left out as "read";
- the domain switch fails closed: `domain: null` (or unset, or the template's placeholder) never pre-ticks, with the
  line that says so; a typo or an unknown entry is "unclear" and names the bad value; only [] turns the rule off.
Run:  bash tools/test.sh -p test_safety_meaning_round4.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
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


def retake(a, b, lang=None):
    lang = lang or ("en" if a.isascii() else "ar")
    got = [p for p in C.compute(two_takes(a, b), lang=lang)["proposals"] if p["kind"] == "retake"]
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


class Base(unittest.TestCase):
    def unticked(self, a, b, *named):
        p = retake(a, b)
        self.assertEqual(p["default"], "keep", (a, b, p))
        said = [w for side in ("a", "b") for w in ((p.get("differs") or {}).get("words") or {}).get(side, [])]
        for w in named:
            self.assertIn(w, said, (a, b, p.get("differs")))
        return p

    def proposed(self, a, b):
        p = retake(a, b)
        self.assertEqual(p["default"], "proposed", (a, b, p.get("differs"), p["reason_en"]))
        self.assertNotIn("differs", p)
        return p

    def no_best(self, a, b, *named):
        g = group(a, b)
        self.assertIsNone(g["best"], (a, b, g["differ"]))
        for w in named:
            self.assertIn(w, g["differ"].get("words", []), (a, b, g["differ"]))
        self.assertIn("⚠", g["line_ar"])
        return g


# --- P1-a ---------------------------------------------------------------------------------------------------------------
class TestCutOffOnlyForTheLastWordOfAnAbandonedTake(Base):
    def test_a1_bitwgaa_bitwgaash(self):
        p = self.unticked("الحقنة دي بتوجع العيال الصغيرين.", "الحقنة دي بتوجعش العيال الصغيرين.", "بتوجع", "بتوجعش")
        self.assertEqual(p["differs"]["words"], {"a": ["بتوجع"], "b": ["بتوجعش"]})
        self.no_best("الحقنة دي بتوجع العيال الصغيرين.", "الحقنة دي بتوجعش العيال الصغيرين.")

    def test_a2_biqallel_biqallelsh_both_orders(self):
        for a, b in (("الدوا ده بيقلل الضغط عند الكبار.", "الدوا ده بيقللش الضغط عند الكبار."),
                     ("الدوا ده بيقللش الضغط عند الكبار.", "الدوا ده بيقلل الضغط عند الكبار.")):
            with self.subTest(a=a):
                self.unticked(a, b, "بيقلل", "بيقللش")
                self.no_best(a, b)

    def test_a3_an_abandoned_take_ending_in_the_plain_form_of_a_negated_word(self):
        a, b = "الدكتور قال إن الدوا ده بيقلل", "الدكتور قال إن الدوا ده بيقللش الضغط عند الكبار."
        self.unticked(a, b, "بيقللش")
        self.no_best(a, b)

    def test_a4_a_closed_take_whose_last_word_starts_a_kept_word(self):
        self.unticked("أول حاجة لازم تعرفي.", "أول حاجة لازم تعرفيها.", "تعرفي", "تعرفيها")

    def test_a5_the_cut_off_helper(self):
        for frag, kept in (("بيقلل", ["بيقللش"]), ("بتوجع", ["بتوجعش"]), ("do", ["don't"]), ("is", ["isnt"]),
                           ("بخمس", ["بخمستاشر"]), ("خمس", ["خمستاشر"]), ("four", ["fourteen"]), ("ب٥", ["ب٥٠"]),
                           ("آمنة", ["آمنة"]), ("women", ["women"]), ("ba", ["women"])):
            with self.subTest(frag=frag):
                self.assertFalse(C.cut_off(frag, kept))
        for frag, kept in (("آم", ["آمنة"]), ("preg", ["pregnant"]), ("تعرفي", ["تعرفيها"]), ("ba-", ["women"]),
                           ("اممم", ["للحامل"]), ("um", ["women"])):
            with self.subTest(frag=frag):
                self.assertTrue(C.cut_off(frag, kept))


# --- ruling 2: the exemption only at a real cut-off ----------------------------------------------------------------------
class TestExemptionOnlyAtARealCutOff(Base):
    def test_r1_a_complete_word_then_more_words_is_a_difference(self):
        a, b = "الحباية دي آمنة", "الحباية دي آمنة للحامل."
        p = self.unticked(a, b, "للحامل")
        self.assertEqual(p["differs"]["words"], {"a": [], "b": ["للحامل"]})
        self.assertIn("«للحامل»", p["reason"])
        self.no_best(a, b, "للحامل")

    def test_r2_a_word_cut_off_mid_way_is_still_proposed(self):
        a, b = "الدكتور قال إن الحباية دي آم", "الدكتور قال إن الحباية دي آمنة للحامل."
        self.proposed(a, b)
        g = group(a, b)
        self.assertEqual(g["best"], 2)
        self.assertNotIn("words", g["differ"])

    def test_r3_nope(self):
        a, b = "this drug is safe for pregnant women", "this drug is safe for pregnant women nope."
        p = self.unticked(a, b, "nope")
        self.assertIn("(nope)", p["reason_en"])
        self.no_best(a, b, "nope")

    def test_r4_a_take_that_ends_in_a_hesitation_sound(self):
        # (K-T7 counts a take as stopped early only when it has fewer words, the hesitation sound included)
        a, b = "الدكتور قال إن الحباية دي آمنة اممم", "الدكتور قال إن الحباية دي آمنة جدا وكويسة للحامل."
        self.proposed(a, b)
        self.assertEqual(group(a, b)["best"], 2)

    def test_r5_a_word_written_as_cut_and_the_same_word_without_the_mark(self):
        self.proposed("this drug is safe for pregnant ba-", "this drug is safe for pregnant women.")
        self.unticked("this drug is safe for pregnant ba", "this drug is safe for pregnant women.", "women")

    def test_r6_a_cut_off_word_that_holds_a_number_is_no_cut_off(self):
        a, b = "يا جماعة الدكتور قال وقفي الدوا قبل العملية بخمس", "يا جماعة الدكتور قال وقفي الدوا قبل العملية بخمستاشر يوم."
        self.assertEqual(retake(a, b)["default"], "keep")
        self.assertIsNone(group(a, b)["best"])

    def test_r7_takes_a_full_longer_take_adds_words_past_the_overlap(self):
        g = self.no_best("this drug is safe.", "this drug is safe for most pregnant women.")
        self.assertEqual(g["differ"]["words"], ["for", "most", "pregnant", "women"])

    def test_r8_takes_a_word_before_the_cut_still_counts(self):
        a = "الدكتور قال لنا النهاردة إن الدوا ده الجديد مفيد للكب"
        b = "الدكتور قال لنا النهاردة إن الدوا ده مفيد للكبد والقلب والكلى."
        g = self.no_best(a, b, "الجديد")
        self.assertNotIn("والقلب", g["differ"]["words"])        # past the cut: where the later take goes on
        self.assertEqual(retake(a, b)["differs"]["words"], {"a": ["الجديد"], "b": []})


# --- P2-d ---------------------------------------------------------------------------------------------------------------
class TestClosingMarks(Base):
    def test_q1_q3_a_quote_after_the_mark_a_semicolon_or_a_colon_close_the_take(self):
        for end in (".»", "؛", ":", '."', ";"):
            a, b = "الحباية دي آمنة" + end, "الحباية دي آمنة للحامل."
            with self.subTest(end=end):
                self.unticked(a, b, "للحامل")
                self.no_best(a, b, "للحامل")

    def test_q4_closed(self):
        for w in ("آمنة.»", "آمنة؛", "safe:", 'safe."', "safe;", "آمنة؟”", "آمنة…»", "safe.)"):
            with self.subTest(w=w):
                self.assertTrue(C._closed(w))
        for w in ("آمنة", "آمنة،", "safe", "safe,", "«آمنة", "ba-"):
            with self.subTest(w=w):
                self.assertFalse(C._closed(w))


# --- lane 5 P2-1 ----------------------------------------------------------------------------------------------------------
LONG = "يا جماعة النهاردة الدكتور شرح لنا كلنا في العيادة إن الصيام في رمضان لمريض السكر "


class TestTheWholeRetakeMatch(Base):
    def test_w1_a_difference_past_the_twelfth_word(self):
        p = self.unticked(LONG + "حلال", LONG + "حرام", "حلال", "حرام")
        self.assertEqual(sorted(p["differs"]["words"]["a"] + p["differs"]["words"]["b"]), ["حرام", "حلال"])

    def test_w2_the_same_long_take_twice_names_nothing(self):
        p = retake(LONG + "حلال.", LONG + "حلال.")
        self.assertNotIn("differs", p)


# --- lane 5 P1-4, the cut-proposal side -------------------------------------------------------------------------------------
PRE = "يا جماعة الدكتور قال "


class TestNumberWordsTheReaderMissed(Base):
    def both(self, x, y):
        for a, b in ((PRE + x, PRE + y), (PRE + y, PRE + x)):
            with self.subTest(a=a, b=b):
                self.assertEqual(retake(a, b)["default"], "keep")
                self.assertIsNone(group(a, b)["best"])

    def test_m1_case_a_birub_saa(self):
        self.both("الأنسولين قبل الأكل بربع ساعة وده مهم جدا للمريض", "الأنسولين قبل الأكل بساعة وده مهم جدا للمريض")

    def test_m2_binus_saa(self):
        self.both("الأنسولين قبل الأكل بنص ساعة وده مهم جدا للمريض", "الأنسولين قبل الأكل بساعة وده مهم جدا للمريض")

    def test_m3_case_b_bikhamastashar_yom(self):
        self.both("وقفي الدوا قبل العملية بخمستاشر يوم وده مهم جدا للمريض",
                  "وقفي الدوا قبل العملية بخمس أيام وده مهم جدا للمريض")

    def test_m4_glued_digits(self):
        self.both("الأنسولين قبل الأكل ب٥ دقايق وده مهم جدا للمريض", "الأنسولين قبل الأكل ب٥٠ دقيقة وده مهم جدا للمريض")

    def test_m5_english_short_units(self):
        for a, b in (("wait 2 hrs before eating", "wait 2 mins before eating."),
                     ("wait 5 min before eating", "wait 5 hr before eating."),
                     ("wait 2 mins before eating", "wait 2 hrs before eating.")):
            with self.subTest(a=a):
                self.assertEqual(retake(a, b)["default"], "keep")
                self.assertIsNone(group(a, b)["best"])

    def test_m6_the_same_glued_number_twice_names_no_word(self):
        x = PRE + "الأنسولين قبل الأكل بربع ساعة وده مهم جدا للمريض."
        self.assertNotIn("differs", retake(x, x))

    def test_m8_a_read_number_word_counts_unless_the_reader_read_it_as_a_number(self):
        # the guard itself (owner pre-mortem item 2): a word the reader consumed is left out only when it read it as
        # a number; today's reader never consumes «بربع», a future one might (timing «بربع ساعة» as "hour")
        ws = C.clean_words(two_takes("الأنسولين قبل الأكل بربع ساعة", "الأنسولين قبل الأكل ساعة."))
        toks = [C.norm_word(w["word"]) for w in ws]
        k = [w["word"] for w in ws].index("بربع")
        args = (ws, toks, (0, 5), (5, 4), C.settings()["fillers"], {k}, set())
        self.assertEqual(C._word_changes(*args, set())[0], ["بربع"])
        self.assertEqual(C._word_changes(*args, {k})[0], [])

    def test_m7_number_word(self):
        for w in ("بربع", "بنص", "ب٥", "لعشرة", "فخمسة", "كتسعة", "بخمستاشر", "fourteen", "خمس", "٥٠", "وتلاتة"):
            with self.subTest(w=w):
                self.assertTrue(C._number_word(w))
        for w in ("بساعة", "بالليل", "الضغط", "women", "بيقلل", "كويس"):
            with self.subTest(w=w):
                self.assertFalse(C._number_word(w))


# --- P3 -----------------------------------------------------------------------------------------------------------------
class TestNamedWords(Base):
    def test_p1_named_words_carry_no_quotes(self):
        p = self.unticked("الحباية دي آمنة.", 'الحباية دي آمنة "للحامل".')
        self.assertEqual(p["differs"]["words"]["b"], ["للحامل"])
        p = self.unticked("الحباية دي آمنة.", "الحباية دي آمنة «للحامل».")
        self.assertEqual(p["differs"]["words"]["b"], ["للحامل"])


# --- ruling 4, P2-a, P2-b: the domain switch fails closed ---------------------------------------------------------------
A_TAKE, B_TAKE = "أول حاجة لازم تعرفي", "أول حاجة لازم تعرفيها كويس."
UNSET_AR = "حدّد مجال العميل (domain) في reel-profile عشان نقدر نعلّم الإعادات تلقائي"
UNSET_EN = "set the client's domain in reel-profile to allow pre-ticked retakes"


class DomainProject(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t25r4_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        self.root = self.tmp / "د. تجربة Dr Test"
        (self.root / "data/Raw").mkdir(parents=True)
        (self.root / ".whynot-client").write_text("{}", encoding="utf-8")
        self.p = Paths(self.root, "C0001")
        common.set_context(self.root)
        write_json(self.p.p("02_transcription/words.json"),
                   {"meta": {"language": "ar"}, "words": two_takes(A_TAKE, B_TAKE)})
        write_json(self.p.p("01_analysis/edit-decisions.json"), {"global": {}, "decisions": []})

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

    def retake(self):
        doc = C.propose(self.p)
        [r] = [p for p in doc["proposals"] if p["kind"] == "retake"]
        return doc, r


class TestDomainFailsClosed(DomainProject):
    def test_d1_an_unset_domain_never_pre_ticks_and_says_how_to_allow_it(self):
        for doc in (None, {"domain": None}, {}, {"domain": ""}, {"domain": "  "},
                    {"domain": "medical | religious | general"}):
            with self.subTest(doc=doc):
                if doc is not None:                            # None: no profile.json at all
                    self.profile(doc)
                d, r = self.retake()
                self.assertEqual(r["default"], "keep")
                self.assertIn(UNSET_AR, r["reason"])
                self.assertIn(UNSET_EN, r["reason_en"])
                self.assertTrue(d["retake_pretick"]["never"])
                self.assertTrue(d["retake_pretick"]["unset"])
                self.assertIn({"ar": UNSET_AR, "en": UNSET_EN}, d["notes"])

    def test_d2_an_explicit_general_domain_allows_pre_ticks(self):
        for dom in ("general", " General ", "GENERAL"):
            with self.subTest(dom=dom):
                self.profile({"domain": dom})
                d, r = self.retake()
                self.assertEqual(r["default"], "proposed")
                self.assertFalse(d["retake_pretick"]["never"])
                self.assertNotIn(UNSET_AR, r["reason"])

    def test_d3_a_typo_in_the_setting_is_unclear_and_named(self):
        self.profile({"domain": "general"})
        for bad, named in ((["religous"], "religous"), (["طبي"], "طبي"), ([""], "''"),
                           (["medical", "religous"], "religous"), ([" "], "' '")):
            with self.subTest(bad=bad):
                self.setting(bad)
                rule = C.retake_rule()
                self.assertTrue(rule["never"])
                self.assertTrue(rule["unclear"])
                self.assertIn(named, rule["problem"])
                d, r = self.retake()
                self.assertEqual(r["default"], "keep")
                self.assertIn(named, r["reason"])
                self.assertIn(named, r["reason_en"])
                self.assertIn("مجال العميل مش واضح", r["reason"])

    def test_d4_a_damaged_setting_or_file_is_unclear(self):
        self.profile({"domain": "general"})
        for bad in ("none", "[]", {"medical": False}, None, False, ["medical", 3], 0):
            with self.subTest(bad=bad):
                self.setting(bad)
                rule = C.retake_rule()
                self.assertTrue(rule["never"])
                self.assertTrue(rule["unclear"])
                self.assertIn("retakes_never_preticked_for", rule["problem"])
                self.assertEqual(self.retake()[1]["default"], "keep")
        self.setting(None, raw="{broken")
        rule = C.retake_rule()
        self.assertTrue(rule["never"])
        self.assertIn("cut-proposals.json", rule["problem"])

    def test_d5_review_domains(self):
        self.profile({"domain": "general", "review_domains": ["islamic"]})
        rule = C.retake_rule()
        self.assertTrue(rule["never"])
        self.assertTrue(rule["unclear"])
        self.assertIn("islamic", rule["problem"])
        self.profile({"domain": "general", "review_domains": ["business", "ai"]})
        self.assertFalse(C.retake_rule()["never"])
        self.profile({"domain": "general", "review_domains": [" Religious "]})
        rule = C.retake_rule()
        self.assertTrue(rule["never"])
        self.assertFalse(rule["unclear"])
        self.assertEqual(rule["client"], ["general", "religious"])

    def test_d6_only_an_empty_list_turns_the_rule_off(self):
        self.setting([])
        for doc in ({"domain": "medical"}, {"domain": None}, {}):
            with self.subTest(doc=doc):
                self.profile(doc)
                d, r = self.retake()
                self.assertEqual(r["default"], "proposed")
                self.assertFalse(d["retake_pretick"]["never"])
        self.setting(["religious"])
        self.profile({"domain": None})
        self.assertTrue(C.retake_rule()["never"])            # unset: may be religious, so fail closed

    def test_d7_setting_the_domain_makes_the_old_list_stale(self):
        _, r = self.retake()                                   # unset: never
        self.profile({"domain": "general"})
        with self.assertRaises(Guidance):
            C.accept(self.p, [r["id"]])
        _, r = self.retake()
        self.setting(["religous"])                             # unclear now
        with self.assertRaises(Guidance):
            C.accept(self.p, [r["id"]])
        # P3: "unclear" alone is in the hash too (never, the lists and the client stay the same here)
        self.profile({"domain": None})
        self.setting(["medical", "religious"])
        d1, r = self.retake()
        self.setting(["medical", "religious", "religous"])
        d2 = C.propose(self.p)
        self.assertEqual([d1["retake_pretick"][k] for k in ("never", "domains", "client", "unset")],
                         [d2["retake_pretick"][k] for k in ("never", "domains", "client", "unset")])
        self.assertNotEqual(d1["inputs_sha1"], d2["inputs_sha1"])

    def test_ruling_3_the_default_stays_in_code(self):
        self.assertEqual(C.NEVER_PRETICK_DEFAULT, ("medical", "religious"))
        self.profile({"domain": "medical"})
        self.assertEqual(C.retake_rule()["domains"], ["medical", "religious"])


if __name__ == "__main__":
    unittest.main()
