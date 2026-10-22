# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 25 (R-4.3) — cut proposals v2: pauses, retakes (the better take kept), false starts, Egyptian
filler rules, repeated words, never past the sign-off, never applied without the editor.
Fixtures: tests/fixtures/cut_proposals/*.json, made-up transcripts with hand labels.
Run:  bash tools/test.sh -p test_cut_proposals.py
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
from lib import cut_proposals as C  # noqa: E402
from lib import cut_proposals_norm  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402
from lib.errors import Guidance  # noqa: E402

FIX = SK / "tests/fixtures/cut_proposals"
KIND = {"R": "retake", "S": "false_start", "F": "filler", "W": "repeat_word"}


def fixture(name):
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def words(spec):
    """[(word, duration_ms, gap_after_ms[, probability])] -> word records."""
    out, t = [], 0
    for i, (w, d, g, *p) in enumerate(spec, 1):
        out.append({"id": i, "segment_id": 1, "word": w, "start_ms": t, "end_ms": t + d,
                    "probability": p[0] if p else 0.95})
        t += d + g
    return out


def kinds(res, default="proposed"):
    return [(p["kind"], p["words"]) for p in res["proposals"] if default is None or p["default"] == default]


def sign_off_protect(doc):
    ws = doc["words"]
    q = [C.norm_word(x) for x in doc["sign_off"].split()]
    toks = [C.norm_word(w["word"]) for w in ws]
    return {"after_ms": next(ws[i]["start_ms"] for i in range(len(toks)) if toks[i:i + len(q)] == q)}


def precision_recall(doc):
    """(rows per kind {tp, fp, fn}, traps proposed) against the fixture's hand labels."""
    protect = sign_off_protect(doc) if doc.get("sign_off") else None
    res = C.compute(doc["words"], [], lang=doc["language"], protect=protect)
    labels = {lb["word_id"]: lb["label"] for lb in doc["labels"]}
    rows = {k: {"tp": 0, "fp": 0, "fn": 0} for k in KIND.values()}
    traps, hit = [], set()
    for p in res["proposals"]:
        if p["default"] != "proposed":
            continue
        lab = {labels.get(i) for i in p["word_ids"]}
        if "-" in lab:
            traps.append(p)
        ok = any(KIND.get(x) == p["kind"] for x in lab)
        rows[p["kind"]]["tp" if ok else "fp"] += 1
        if ok:
            hit.update(p["word_ids"])
    items, cur = [], None
    for wid in sorted(labels):
        lab = labels[wid]
        if lab == "-":
            cur = None
            continue
        if cur and cur[0] == lab and wid == cur[1][-1] + 1:
            cur[1].append(wid)
        else:
            cur = (lab, [wid])
            items.append(cur)
    for lab, ids in items:
        if not set(ids) & hit:
            rows[KIND[lab]]["fn"] += 1
    return rows, traps


class TestAcceptance(unittest.TestCase):
    def test_precision_targets_and_no_trap_on_the_labelled_fixtures(self):
        """R-4.3 acceptance: retake precision ≥ 0.8, filler precision ≥ 0.9, written laughter and the real words
        «اه», «إيه», «امم» (unstretched) never proposed, the sign-off never proposed."""
        tot = {k: {"tp": 0, "fp": 0, "fn": 0} for k in KIND.values()}
        for f in sorted(FIX.glob("*.json")):
            rows, traps = precision_recall(json.loads(f.read_text(encoding="utf-8")))
            self.assertEqual(traps, [], f.stem)
            for k, r in rows.items():
                for x in r:
                    tot[k][x] += r[x]
        for k, floor in (("retake", 0.8), ("filler", 0.9)):
            n = tot[k]["tp"] + tot[k]["fp"]
            self.assertGreater(n, 0)
            self.assertGreaterEqual(tot[k]["tp"] / n, floor, tot)

    def test_deterministic_output_for_the_same_input(self):
        for name in ("eg_doctor", "en_talk", "mixed"):
            doc = fixture(name)
            a = C.compute(doc["words"], [[100, 900]], lang=doc["language"])
            b = C.compute(list(reversed(doc["words"])), [[100, 900]], lang=doc["language"])
            self.assertEqual(json.dumps(a, ensure_ascii=False), json.dumps(b, ensure_ascii=False))


class TestRetakes(unittest.TestCase):
    RESTART = [("أول", 250, 60), ("حاجة", 300, 60), ("لازم", 300, 60), ("تعرفي", 350, 500),
               ("أول", 250, 60), ("حاجة", 300, 60), ("لازم", 300, 60), ("تعرفيها", 350, 60), ("كويس.", 300, 400)]

    def test_abandoned_take_is_dropped_the_full_one_kept(self):
        res = C.compute(words(self.RESTART))
        p = res["proposals"][0]
        self.assertEqual((p["kind"], p["word_ids"], p["default"]), ("retake", [1, 2, 3, 4], "proposed"))
        self.assertEqual(p["keep"]["word_ids"], [5, 6, 7, 8, 9])
        self.assertEqual(p["keep_ref"], p["id"] + "k")
        self.assertIn("اتقالت الجملة مرتين", p["reason"])

    def test_best_take_not_just_the_last(self):
        """The second take is cut off and mumbled: the first, complete one is kept."""
        spec = [("الأكل", 300, 60), ("الصحي", 400, 60), ("بيفرق", 400, 60), ("معاكي", 400, 60), ("جدا.", 300, 500),
                ("الأكل", 300, 60, 0.5), ("الصحي", 400, 60, 0.5), ("بيفرق", 400, 60, 0.5), ("يعني", 300, 60, 0.5),
                ("طيب", 300, 60)]
        p = C.compute(words(spec))["proposals"][0]
        self.assertEqual(p["kind"], "retake")
        self.assertEqual(p["word_ids"][0], 6)
        self.assertEqual(p["keep"]["word_ids"][0], 1)

    def test_retake_differing_by_one_word(self):
        spec = [("خدي", 300, 60), ("الدوا", 300, 60), ("بعد", 300, 60), ("الفطار", 400, 600),
                ("خدي", 300, 60), ("الدوا", 300, 60), ("بعد", 300, 60), ("الغدا", 400, 60), ("دايما.", 400, 300)]
        res = C.compute(words(spec))
        # the takes differ in timing (after breakfast / after lunch): found, never pre-ticked, the words named
        self.assertEqual(kinds(res), [])
        self.assertEqual(kinds(res, "keep"), [("retake", ["خدي", "الدوا", "بعد", "الفطار"])])
        p = res["proposals"][0]
        self.assertIn("«بعد الفطار» مقابل «بعد الغدا»", p["reason"])
        self.assertIn("timing", p["differs"])
        spec2 = [("أول", 250, 60), ("حاجة", 300, 60), ("لازم", 300, 60), ("تشربي", 350, 600),
                 ("أول", 250, 60), ("حاجة", 300, 60), ("لازم", 300, 60), ("تشربي", 350, 60), ("كتير.", 300, 400)]
        # Task 25 round 4 (EXECUTOR RULINGS 2026-10-18 (2) item 2): the first take stops on a whole word, not at a
        # real cut-off, so «كتير» is a word the kept take adds: found, never pre-ticked, named
        res = C.compute(words(spec2))
        self.assertEqual(kinds(res, "keep"), [("retake", ["أول", "حاجة", "لازم", "تشربي"])])
        self.assertEqual(res["proposals"][0]["differs"], {"words": {"a": [], "b": ["كتير"]}})
        spec3 = [("أول", 250, 60), ("حاجة", 300, 60), ("لازم", 300, 60), ("تشر", 350, 600),
                 ("أول", 250, 60), ("حاجة", 300, 60), ("لازم", 300, 60), ("تشربي", 350, 60), ("كتير.", 300, 400)]
        self.assertEqual(kinds(C.compute(words(spec3))), [("retake", ["أول", "حاجة", "لازم", "تشر"])])

    def test_retake_across_a_long_pause_but_not_past_the_window(self):
        near = [("لو", 200, 60), ("نمتي", 300, 60), ("بدري", 300, 60), ("هتصحي", 400, 1800),
                ("لو", 200, 60), ("نمتي", 300, 60), ("بدري", 300, 60), ("هتصحي", 400, 60), ("فايقة.", 400, 300)]
        # (found either way; since Task 25 round 4 «فايقة», added after a take that stopped on a whole word, leaves it
        # unticked: EXECUTOR RULINGS 2026-10-18 (2) item 2)
        self.assertEqual(kinds(C.compute(words(near)), None)[0][0], "retake")
        far = list(near)
        far[3] = ("هتصحي", 400, 25000)
        self.assertEqual(kinds(C.compute(words(far))), [])

    def test_emphasis_is_not_a_retake(self):
        for spec in ([("ده", 200, 60), ("مهم", 300, 60), ("جدا.", 300, 100), ("مهم", 300, 60), ("جدا.", 300, 500)],
                     [("it", 150, 60), ("was", 200, 60), ("very", 300, 60), ("very", 300, 60), ("good.", 300, 300)],
                     [("never,", 300, 60), ("never", 300, 60), ("again.", 300, 300)]):
            with self.subTest(spec=spec):
                self.assertEqual(kinds(C.compute(words(spec), lang="en")), [])

    def test_identical_complete_sentence_twice_is_left_unticked(self):
        spec = [("الصحة", 300, 60), ("أهم", 300, 60), ("حاجة", 300, 60), ("عندنا.", 400, 1200),
                ("الصحة", 300, 60), ("أهم", 300, 60), ("حاجة", 300, 60), ("عندنا.", 400, 300)]
        res = C.compute(words(spec))
        self.assertEqual([(p["kind"], p["default"]) for p in res["proposals"]], [("retake", "keep")])


class TestFillers(unittest.TestCase):
    def test_hesitation_sounds_always(self):
        for w in ("ممم", "اممم", "ااه", "آآه", "همم", "um", "uhh", "erm", "hmm"):
            with self.subTest(w=w):
                res = C.compute(words([("قال", 300, 60), (w, 500, 100), ("كده.", 300, 60)]), lang="ar")
                self.assertEqual(kinds(res), [("filler", [w])])
        self.assertEqual(kinds(C.compute(words([("so", 300, 60), ("er", 500, 100), ("yes.", 300, 60)]), lang="ar")),
                         [])
        self.assertEqual(kinds(C.compute(words([("so", 300, 60), ("er", 500, 100), ("yes.", 300, 60)]), lang="en")),
                         [("filler", ["er"])])

    def test_real_words_and_laughter_are_never_fillers(self):
        for w in ("اه", "آه", "ايه", "إيه", "امم", "هه", "هههه", "haha"):
            with self.subTest(w=w):
                res = C.compute(words([("هو", 300, 60), (w, 300, 60), ("قال", 300, 60), ("كده.", 300, 60)]))
                self.assertEqual(kinds(res, None), [])

    def test_context_word_only_stretched_between_pauses(self):
        base = [("الضغط", 400, 60), ("عالي.", 300, 450), None, ("ممكن", 300, 60), ("يكون", 300, 60), ("تعبان.", 400, 60)]

        def run(token):
            spec = [x if x else token for x in base]
            return kinds(C.compute(words(spec)))
        self.assertEqual(run(("يعني", 900, 400)), [("filler", ["يعني"])])
        self.assertEqual(run(("يعني", 300, 400)), [])                       # not stretched
        self.assertEqual(run(("يعني", 900, 60)), [])                        # no pause after it
        self.assertEqual(run(("يعني؟", 900, 400)), [])                      # a question
        self.assertEqual(run(("طب", 900, 400)), [("filler", ["طب"])])

    def test_bare_aah_stretched_is_soft(self):
        """Hush ruling: a bare «اه» is a real "yes" in Egyptian: detected, left unticked."""
        spec = [("الضغط", 400, 60), ("عالي.", 300, 450), ("اه", 900, 400), ("ممكن", 300, 60), ("يكون", 300, 60),
                ("تعبان.", 400, 60), ("طيب", 300, 60)]
        res = C.compute(words(spec))
        self.assertEqual([(p["kind"], p["default"]) for p in res["proposals"]], [("filler", "keep")])
        self.assertIn("أيوه", res["proposals"][0]["reason"])

    def test_per_client_filler_lists(self):
        cfg = C.settings()
        cfg["fillers"]["context"] = cfg["fillers"]["context"] + ["خلاص"]
        spec = [("الضغط", 400, 60), ("عالي.", 300, 450), ("خلاص", 1100, 400), ("ممكن", 300, 60), ("يكون", 300, 60),
                ("تعبان.", 400, 60), ("طيب", 300, 60), ("خلاص", 400, 60)]
        self.assertEqual(kinds(C.compute(words(spec), cfg=cfg))[0], ("filler", ["خلاص"]))
        self.assertEqual(kinds(C.compute(words(spec))), [])


class TestOtherKinds(unittest.TestCase):
    def test_false_start(self):
        spec = [("الدكت", 150, 100, 0.4), ("الدكتورة", 400, 60), ("قالت.", 300, 60)]
        self.assertEqual(kinds(C.compute(words(spec)), "keep"), [("false_start", ["الدكت"])])   # never ticked (round 6)

    def test_repeated_word_but_not_intensifiers_or_numbers(self):
        self.assertEqual(kinds(C.compute(words([("في", 200, 60), ("في", 200, 60), ("البيت.", 300, 60)]))),
                         [("repeat_word", ["في"])])
        self.assertEqual(kinds(C.compute(words([("لا", 200, 60), ("لا", 200, 60), ("خالص.", 300, 60)]))), [])
        res = C.compute(words([("٣", 300, 60), ("3", 300, 60), ("حبايات.", 300, 60)]))
        self.assertEqual([(p["kind"], p["default"]) for p in res["proposals"]], [("repeat_word", "keep")])

    def test_a_negation_said_twice_is_never_a_repeat(self):
        """Review 40ba427 P2-1: "you can not not take your insulin" lost one "not" (a ticked cut that flips the
        meaning), for a general and a medical client alike. Any word the negation reader reads is never proposed."""
        for sent in (["it's", "not", "not", "important."], ["you", "can", "not", "not", "take", "your", "insulin."],
                     ["don't", "don't", "stop."], ["مخدتش", "مخدتش", "الدوا."], ["ومش", "ومش", "كده."],
                     ["it's", "Not", "not", "safe."], ["it's", "not,", "not", "safe."]):     # review a26dfed P3-1
            for rule in (None, {"never": True}, {"never": False}):
                res = C.compute(words([(w, 200, 60) for w in sent]), rule=rule, lang="en" if sent[-1][0] < "ء" else "ar")
                self.assertNotIn("repeat_word", [p["kind"] for p in res["proposals"]], (sent, rule))

    def test_pauses_from_the_pause_map(self):
        res = C.compute(words([("قال", 300, 900), ("كده.", 300, 60)]), [[400, 1100], "junk", [5, 2], [1, "x"]])
        self.assertEqual([(p["kind"], p["start_ms"], p["end_ms"]) for p in res["proposals"]], [("pause", 400, 1100)])

    def test_no_speech_means_no_cuts_and_a_plain_line(self):
        res = C.compute([], [[0, 5000]])
        self.assertEqual(res["proposals"], [])
        self.assertTrue(res["notes"][0][0].startswith("مفيش كلام"))


class TestProtections(unittest.TestCase):
    def test_sign_off_and_everything_after_it_never_proposed(self):
        doc = fixture("signoff")
        res = C.compute(doc["words"], [[99000, 99500]], protect=sign_off_protect(doc))
        after = sign_off_protect(doc)["after_ms"]
        self.assertTrue(all(p["end_ms"] <= after for p in res["proposals"]))
        self.assertEqual(kinds(res), [("filler", ["اممم"])])

    def test_protected_words_anchors_and_speaker_changes(self):
        spec = [("قال", 300, 60), ("اممم", 600, 100), ("كده.", 300, 60), ("في", 200, 60), ("في", 200, 60),
                ("البيت.", 300, 60)]
        ws = words(spec)
        self.assertEqual(len(C.compute(ws)["proposals"]), 2)
        self.assertEqual(kinds(C.compute(ws, protect={"word_ids": {2}})), [("repeat_word", ["في"])])
        self.assertEqual(kinds(C.compute(ws, protect={"anchors": [ws[1]["start_ms"] + 10]})), [("repeat_word", ["في"])])
        self.assertEqual(kinds(C.compute(ws, protect={"turns": [ws[1]["start_ms"] + 10]})), [("repeat_word", ["في"])])
        ws[3]["speaker"], ws[4]["speaker"] = "A", "B"
        res = C.compute(ws)
        self.assertNotIn("repeat_word", [p["kind"] for p in res["proposals"]])

    def test_never_leaves_a_kept_piece_shorter_than_the_minimum(self):
        spec = [("قال", 300, 60), ("اممم", 600, 30), ("و", 100, 30), ("ممم", 600, 60), ("كده.", 300, 60)]
        res = C.compute(words(spec))
        defaults = [(p["words"], p["default"]) for p in res["proposals"]]
        self.assertEqual(defaults, [(["اممم"], "proposed"), (["ممم"], "keep")])
        self.assertIn("أقصر من", res["proposals"][1]["reason"])

    def test_cut_never_enters_a_neighbouring_word(self):
        ws = words([("قال", 300, 10), ("اممم", 600, 10), ("كده.", 300, 60)])
        p = C.compute(ws)["proposals"][0]
        self.assertGreaterEqual(p["start_ms"], ws[0]["end_ms"])
        self.assertLessEqual(p["end_ms"], ws[2]["start_ms"])


class TestAcceptanceFollowUps(unittest.TestCase):
    """Executor acceptance review 2026-10-17 (Task 25 P1/P2): a retake whose takes differ in a negation, a timing word
    or a dose is never pre-ticked; «آية» is never a filler; a false start holding a number is never ticked."""

    def retake(self, spec, lang="ar"):
        res = C.compute(words(spec), lang=lang)
        rt = [p for p in res["proposals"] if p["kind"] == "retake"]
        self.assertEqual(len(rt), 1, res["proposals"])
        return rt[0]

    def test_p1_negation_flip_is_kept_and_named(self):
        for neg in ("مش", "ما"):
            with self.subTest(neg=neg):
                spec = [("الدوا", 300, 60), ("ده", 200, 60), ("بيقلل", 400, 60), ("الضغط.", 400, 700),
                        ("الدوا", 300, 60), ("ده", 200, 60), (neg, 200, 60), ("بيقلل", 400, 60), ("الضغط.", 400, 300)]
                p = self.retake(spec)
                self.assertEqual(p["default"], "keep")
                self.assertIn(f"«{neg}»", p["reason"])
                self.assertIn("negation", p["differs"])
        spec = [("الدوا", 300, 60), ("ده", 200, 60), ("بيقلل", 400, 60), ("الضغط.", 400, 700),
                ("الدوا", 300, 60), ("ده", 200, 60), ("مبيقللش", 500, 60), ("الضغط.", 400, 300)]
        self.assertEqual(self.retake(spec)["default"], "keep")

    def test_p1_time_of_day_with_one_pill(self):
        spec = [("خدي", 300, 60), ("حباية", 300, 60), ("واحدة", 300, 60), ("الصبح.", 400, 700),
                ("خدي", 300, 60), ("حباية", 300, 60), ("واحدة", 300, 60), ("بالليل.", 400, 300)]
        p = self.retake(spec)
        self.assertEqual(p["default"], "keep")
        self.assertIn("«الصبح»", p["reason"])
        self.assertIn("«بالليل»", p["reason"])
        self.assertLess(p["confidence"], C.DEFAULTS["keep_below"])

    def test_p1_says_number_sees_an_everyday_number_word_next_to_a_unit(self):
        self.assertTrue(C._says_number([{"word": w} for w in ("خدي", "حباية", "واحدة")]))
        self.assertFalse(C._says_number([{"word": w} for w in ("جالي", "واحد", "امبارح")]))

    def test_p1_dose_and_english_negation(self):
        spec = [("take", 300, 60), ("five", 300, 60), ("hundred", 300, 60), ("milligrams", 500, 60), ("daily.", 400, 700),
                ("take", 300, 60), ("two", 300, 60), ("hundred", 300, 60), ("milligrams", 500, 60), ("daily.", 400, 300)]
        self.assertEqual(self.retake(spec, "en")["default"], "keep")
        spec = [("it", 150, 60), ("lowers", 300, 60), ("the", 150, 60), ("blood", 300, 60), ("pressure.", 400, 700),
                ("it", 150, 60), ("doesn't", 300, 60), ("lower", 300, 60), ("the", 150, 60), ("blood", 300, 60),
                ("pressure.", 400, 300)]
        res = C.compute(words(spec), lang="en")
        self.assertEqual([p for p in res["proposals"] if p["default"] == "proposed" and p["kind"] == "retake"], [])

    def test_p1_review_probes_how_often_ghair_and_relative_days(self):
        probes = [(["خدي", "الحقنة", "كل", "أسبوع."], ["خدي", "الحقنة", "كل", "شهر."]),
                  (["ده", "دوا", "آمن", "للأطفال."], ["ده", "دوا", "غير", "آمن", "للأطفال."]),
                  (["ابدأي", "الدوا", "النهارده", "الصبح."], ["ابدأي", "الدوا", "بكرة", "الصبح."])]
        for a, b in probes:
            with self.subTest(a=a, b=b):
                spec = [(w, 300, 60) for w in a[:-1]] + [(a[-1], 300, 700)] + [(w, 300, 60) for w in b[:-1]] + \
                    [(b[-1], 300, 300)]
                self.assertEqual(self.retake(spec)["default"], "keep")

    def test_review_r2_a_later_take_dropped_from_mid_sentence_is_never_ticked(self):
        """Dropping only the end of the later sentence («with water.») would leave a broken line: shown, unticked."""
        spec = [("take", 300, 60), ("it", 150, 60), ("daily", 300, 60), ("with", 200, 60), ("water.", 300, 700),
                ("take", 300, 60), ("it", 150, 60), ("every", 300, 60), ("day", 300, 60), ("with", 200, 60),
                ("water.", 300, 300)]
        res = C.compute(words(spec), lang="en")
        for p in res["proposals"]:
            if p["kind"] == "retake" and p["default"] == "proposed":
                first = p["word_ids"][0]
                self.assertTrue(first == 1 or spec[first - 2][0].endswith("."), p)

    def test_p2_aya_is_never_a_filler(self):
        base = [("الضغط", 400, 60), ("عالي.", 300, 450), None, ("ممكن", 300, 60), ("يكون", 300, 60), ("تعبان.", 400, 60)]
        for w in ("آية", "اية", "آيه", "آيَة"):
            with self.subTest(w=w):
                spec = [x if x else (w, 900, 400) for x in base]
                self.assertEqual(kinds(C.compute(words(spec)), None), [])
        spec = [x if x else ("إيه", 900, 400) for x in base]
        self.assertEqual(kinds(C.compute(words(spec))), [("filler", ["إيه"])])

    def test_p2_false_start_holding_a_number_is_never_ticked(self):
        for a, b in (("50", "500"), ("٥٠", "٥٠٠"), ("خمس", "خمسمية"), ("تلت", "تلتمية")):
            with self.subTest(a=a, b=b):
                spec = [("خدي", 300, 60), (a, 150, 100, 0.4), (b, 400, 60), ("مجم.", 300, 60)]
                res = C.compute(words(spec))
                fs = [p for p in res["proposals"] if p["kind"] == "false_start"]
                self.assertEqual([p["default"] for p in fs], ["keep"])
                self.assertIn("رقم", fs[0]["reason"])
        spec = [("الدكت", 150, 100, 0.4), ("الدكتورة", 400, 60), ("قالت.", 300, 60)]
        self.assertEqual(kinds(C.compute(words(spec)), "keep"), [("false_start", ["الدكت"])])   # never ticked (round 6)

    def test_p2_spelled_number_said_twice_is_never_ticked(self):
        res = C.compute(words([("خدي", 300, 60), ("خمسة", 300, 60), ("خمسة", 300, 60), ("مجم.", 300, 60)]))
        self.assertEqual([(p["kind"], p["default"]) for p in res["proposals"]], [("repeat_word", "keep")])


class TestText(unittest.TestCase):
    def test_egyptian_and_msa_spellings_and_digits_compare_equal(self):
        self.assertEqual(C.norm_word("الدكتورة"), C.norm_word("الدكتوره"))
        self.assertEqual(C.norm_word("إيه"), C.norm_word("ايه"))
        self.assertEqual(C.norm_word("٣"), C.norm_word("3"))
        self.assertEqual(C.norm_word("جـــدًا"), C.norm_word("جدا"))

    def test_shared_normaliser_is_unchanged(self):
        """The identity scan loads the same file: Task 25 extends around it, never changes it."""
        self.assertEqual(cut_proposals_norm.NORM_VERSION, 2)

    def test_similarity(self):
        self.assertEqual(C.similarity(["a", "b"], ["a", "b"]), 1.0)
        self.assertEqual(C.similarity([], ["a"]), 0.0)
        self.assertAlmostEqual(C.similarity(["a", "b", "c", "d"], ["a", "b", "c", "e"]), (3 / 5 + 3 / 4) / 2)

    def test_snap_to_the_quietest_frame(self):
        sr = 1000
        samples = [1.0] * 2000
        for k in range(1020, 1030):
            samples[k] = 0.0
        self.assertEqual(C.snap(1000, samples, sr, 50, 10), 1020)
        self.assertEqual(C.snap(1000, None, sr), 1000)
        self.assertEqual(C.snap(5, [1.0] * 100, sr, 50, 10), 5)          # flat audio: the cut point stays


class Project(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t25_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        self.root = self.tmp / "د. تجربة Dr Test"
        for d in ("assets", "data/Raw"):
            (self.root / d).mkdir(parents=True)
        (self.root / ".whynot-client").write_text("{}", encoding="utf-8")
        self.p = Paths(self.root, "C0001")
        common.set_context(self.root)
        doc = fixture("eg_doctor")
        write_json(self.p.p("02_transcription/words.json"), {"meta": {"language": "ar"}, "words": doc["words"]})
        write_json(self.p.p("01_analysis/edit-decisions.json"), {"global": {}, "decisions": []})

    def snapshot(self):
        return {str(f.relative_to(self.root)): f.read_bytes() for f in self.root.rglob("*") if f.is_file()}


class TestProject(Project):
    def test_propose_writes_one_file_and_changes_nothing_else(self):
        before = self.snapshot()
        doc = C.propose(self.p)
        after = self.snapshot()
        new = set(after) - set(before)
        self.assertEqual(new, {str(self.p.p(C.FILE).relative_to(self.root))})
        self.assertTrue(all(after[k] == v for k, v in before.items()))
        self.assertTrue(doc["proposals"])
        self.assertIn("لا شيء يتقص قبل موافقتك", doc["how"])
        first = self.p.p(C.FILE).read_bytes()
        C.propose(self.p)
        self.assertEqual(self.p.p(C.FILE).read_bytes(), first)       # re-run: byte-identical

    def test_missing_or_damaged_words_refused_and_nothing_written(self):
        f = self.p.p("02_transcription/words.json")
        for content in (None, "{broken", json.dumps({"words": "x"})):
            with self.subTest(content=content):
                if content is None:
                    f.unlink(missing_ok=True)
                else:
                    f.write_text(content, encoding="utf-8")
                with self.assertRaises(Guidance) as cm:
                    C.propose(self.p)
                self.assertTrue(str(cm.exception).startswith("مفيش تفريغ صالح"))
                self.assertFalse(self.p.p(C.FILE).exists())

    def test_quotes_highlights_and_drug_names_are_protected(self):
        write_json(self.p.p("01_analysis/edit-decisions.json"), {"global": {}, "caption_highlights": [
            {"text": "في في البيت", "at": "00:00:05.000"}], "decisions": []})
        doc = C.propose(self.p)
        self.assertNotIn("repeat_word", [p["kind"] for p in doc["proposals"]])

    def test_p3_drug_names_split_or_with_a_clitic_are_protected(self):
        """K-T1's drug reader: a name split over two words and the ل/ف/لل clitics."""
        spec = ["خدي", "ميت", "فورمين", "و", "للباراسيتامول", "فبنادول", "لبنادول", "بعد", "الأكل"]
        ws = [{"id": i, "word": w, "start_ms": i * 400, "end_ms": i * 400 + 300} for i, w in enumerate(spec, 1)]
        protect, _ = C._protections(self.p, ws, [C.norm_word(w["word"]) for w in ws], "ar")
        self.assertEqual(sorted(protect["word_ids"]), [2, 3, 5, 6, 7])

    def test_sign_off_from_the_profile_and_the_fallback_line(self):
        write_json(self.root / common.CLIENT_PROFILE_REL / "profile.json",
                   {"endings": {"sign_off": {"on": True, "phrase": "مع السلامة"}}})
        doc = C.propose(self.p)
        self.assertTrue(doc["notes"])
        self.assertTrue(doc["notes"][0]["ar"].startswith("جملة الختام"))
        end = max(w["end_ms"] for w in fixture("eg_doctor")["words"])
        self.assertTrue(all(p["end_ms"] <= end - 8000 for p in doc["proposals"]))

    def test_accept_writes_cut_words_only_with_ids_and_is_idempotent(self):
        doc = C.propose(self.p)
        ids = [p["id"] for p in doc["proposals"] if p["kind"] in C.WORD_KINDS][:2]
        before = self.p.p("01_analysis/edit-decisions.json").read_bytes()
        for bad in ([], ["CP-999"], ["nope"]):
            with self.subTest(bad=bad):
                with self.assertRaises(Guidance):
                    C.accept(self.p, bad)
                self.assertEqual(self.p.p("01_analysis/edit-decisions.json").read_bytes(), before)
        res = C.accept(self.p, [i.lower() for i in ids])
        self.assertEqual(res["added"], ids)
        ed = read_json(self.p.p("01_analysis/edit-decisions.json"))
        self.assertEqual([c["reason"].split(" ")[0] for c in ed["global"]["cut_words"]], ids)
        once = self.p.p("01_analysis/edit-decisions.json").read_bytes()
        self.assertEqual(C.accept(self.p, ids)["added"], [])
        self.assertEqual(self.p.p("01_analysis/edit-decisions.json").read_bytes(), once)

    def test_accept_refused_when_the_transcript_changed(self):
        C.propose(self.p)
        wf = self.p.p("02_transcription/words.json")
        d = read_json(wf)
        d["words"][0]["word"] = "تاني"
        write_json(wf, d)
        before = self.p.p("01_analysis/edit-decisions.json").read_bytes()
        with self.assertRaises(Guidance) as cm:
            C.accept(self.p, ["CP-001"])
        self.assertIn("اتغيرت بعد الاقتراحات", str(cm.exception))
        self.assertEqual(self.p.p("01_analysis/edit-decisions.json").read_bytes(), before)

    def test_nothing_is_cut_by_proposing(self):
        """The plan's own cut list changes only through accept()."""
        C.propose(self.p)
        self.assertEqual(read_json(self.p.p("01_analysis/edit-decisions.json")), {"global": {}, "decisions": []})

    def test_plan_table_and_markers(self):
        doc = C.propose(self.p)
        table = "\n".join(C.plan_table(doc))
        self.assertTrue(table.startswith("## اقتراحات القص — Proposed cuts"))
        self.assertIn("only ✔ rows are cut once you approve", table)        # r2: the footer never says pending
        ms = C.markers(doc, 25)
        self.assertEqual(len(ms), len(doc["proposals"]))
        self.assertEqual(ms[0]["frame"], round(doc["proposals"][0]["start_ms"] / 1000 * 25))
        self.assertEqual(C.plan_table(None), [])
        self.assertEqual(C.markers(None, 25), [])

    def test_markers_on_the_sequence_clock_after_removed_pauses(self):
        keep = [[0, 1000], [2000, 5000]]
        self.assertEqual([C.seq_ms(t, keep) for t in (500, 1500, 2500, 6000)], [500, 1000, 1500, 4000])
        doc = {"proposals": [{"id": "CP-001", "kind": "filler", "start_ms": 2500, "end_ms": 2900, "reason": "x"},
                             {"id": "CP-002", "kind": "pause", "start_ms": 1100, "end_ms": 1900, "reason": "y"}]}
        ms = C.markers(doc, 25, keep)
        self.assertEqual([(m["name"].split()[0], m["t"], m["frame"]) for m in ms], [("CP-001", 1.5, 38)])

    def test_settings_basis_and_damaged_config(self):
        s = C.settings()
        self.assertEqual(set(s["basis"].values()), {"starting"})
        write_json(self.root / common.CLIENT_PROFILE_REL / "cut-proposals.json",
                   {"thresholds": {"retake_score": {"value": 0.7, "basis": "measured: fixtures, 2026-10-17"},
                                   "pad_ms": True, "min_kept_ms": "x"}})
        s = C.settings()
        self.assertEqual((s["values"]["retake_score"], s["basis"]["retake_score"]),
                         (0.7, "measured: fixtures, 2026-10-17"))
        self.assertEqual(s["values"]["pad_ms"], C.DEFAULTS["pad_ms"])
        (self.root / common.CLIENT_PROFILE_REL / "cut-proposals.json").write_text("{x", encoding="utf-8")
        self.assertEqual(C.settings()["values"], C.DEFAULTS)

    def test_same_on_macos(self):
        a = C.propose(self.p)
        with mock.patch.object(sys, "platform", "darwin"):
            b = C.propose(self.p)
        self.assertEqual(a, b)


# --- review round 1 (independent reviewer, 2026-10-17): I1–I5, I7 and the Minors -------------------------------------
class TestReviewRound1(unittest.TestCase):
    def test_i1_snap_keeps_the_point_on_flat_audio(self):
        self.assertEqual(C.snap(1000, [0.5] * 3000, 1000, 50, 10), 1000)
        self.assertEqual(C.snap(1000, [0.0] * 3000, 1000, 50, 10), 1000)

    def test_i2_snap_never_moves_into_a_neighbouring_word(self):
        ws = words([("قال", 300, 300), ("اممم", 600, 300), ("كده.", 300, 60)])
        sr, n = 1000, ws[-1]["end_ms"] + 200
        samples = [0.5] * n
        for k in range(ws[0]["end_ms"] - 40, ws[0]["end_ms"] - 30):     # the quietest frame is inside «قال»
            samples[k] = 0.0
        p = C.compute(ws, samples=samples, sr=sr)["proposals"][0]
        self.assertGreaterEqual(p["start_ms"], ws[0]["end_ms"])
        self.assertLessEqual(p["end_ms"], ws[2]["start_ms"])

    def test_i5_no_retake_across_two_speakers(self):
        spec = [("لازم", 300, 60), ("تاخد", 300, 60), ("الدوا", 300, 60), ("بعد", 300, 60), ("الفطار.", 300, 800),
                ("لازم", 300, 60), ("تاخد", 300, 60), ("الدوا", 300, 60), ("بعد", 300, 60), ("الغدا.", 300, 300)]
        ws = words(spec)
        self.assertEqual(kinds(C.compute(ws), None)[0][0], "retake")
        for w in ws[5:]:
            w["speaker"] = "B"
        for w in ws[:5]:
            w["speaker"] = "A"
        self.assertEqual([p["kind"] for p in C.compute(ws)["proposals"]], [])

    def test_i7_quote_protection_tolerates_a_small_transcript_difference(self):
        toks = [C.norm_word(x) for x in "قال ان الصبر مفتاح ممم الفرج دايما".split()]
        q = [C.norm_word(x) for x in "الصبر مفتاح الفرج".split()]
        self.assertEqual(C._quote_spans(toks, q), [(2, 5)])
        q2 = [C.norm_word(x) for x in "الصبر مفتاخ الفرج".split()]            # one word heard differently
        self.assertEqual(C._quote_spans(toks, q2), [(2, 5)])
        self.assertEqual(C._quote_spans(toks, [C.norm_word(x) for x in "حاجة تانية خالص".split()]), [])

    def test_m_pause_inside_a_word_proposal_counts_once(self):
        ws = words([("قال", 300, 60), ("اممم", 600, 700), ("كده.", 300, 60)])
        res = C.compute(ws, [[ws[1]["end_ms"] + 50, ws[2]["start_ms"] - 50]])
        self.assertEqual([p["kind"] for p in res["proposals"]], ["filler"])

    def test_m_kept_piece_at_the_end_of_the_clip(self):
        ws = words([("قال", 300, 60), ("كده", 300, 60), ("اممم", 600, 60), ("آه.", 150, 0)])
        res = C.compute(ws, media_end_ms=ws[-1]["end_ms"])
        self.assertEqual([(p["kind"], p["default"]) for p in res["proposals"]], [("filler", "keep")])

    def test_m_best_take_is_not_penalised_for_a_normal_context_word(self):
        spec = [("الأكل", 300, 60), ("الصحي", 300, 60), ("يعني", 300, 60), ("بيفرق", 300, 60), ("جدا.", 300, 900),
                ("الأكل", 300, 60), ("الصحي", 300, 60), ("بيفرق", 300, 60), ("جدا", 300, 1200), ("طيب.", 300, 60)]
        p = C.compute(words(spec))["proposals"][0]
        self.assertEqual(p["word_ids"][0], 6)                     # the cut-off second take goes, not the first

    def test_m_every_number_has_a_basis(self):
        s = C.settings()
        self.assertEqual(set(s["basis"]), set(C.DEFAULTS))
        for k in ("conf_always_filler", "conf_retake_base", "emphasis_max_content", "fragment_min_letters"):
            self.assertIn(k, C.DEFAULTS)


class TestReviewRound1Project(Project):
    def test_i3_accept_carries_the_proposal_span(self):
        doc = C.propose(self.p)
        p = [x for x in doc["proposals"] if x["kind"] == "retake"][0]
        C.accept(self.p, [p["id"]])
        cw = read_json(self.p.p("01_analysis/edit-decisions.json"))["global"]["cut_words"]
        self.assertEqual(cw[0]["range_ms"], [p["start_ms"], p["end_ms"]])

    def test_i4_accept_is_keyed_on_words_and_refuses_a_list_made_with_other_inputs(self):
        doc = C.propose(self.p)
        p = [x for x in doc["proposals"] if x["kind"] in C.WORD_KINDS][0]
        C.accept(self.p, [p["id"]])
        C.propose(self.p)                                        # listed again: same words, maybe another id
        again = [x for x in C.load(self.p)["proposals"] if x["word_ids"] == p["word_ids"]][0]
        self.assertEqual(C.accept(self.p, [again["id"]])["already"], [again["id"]])
        ed = read_json(self.p.p("01_analysis/edit-decisions.json"))
        ed["caption_highlights"] = [{"text": "في في البيت", "at": "00:00:05.000"}]   # a new protection
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed)
        before = self.p.p("01_analysis/edit-decisions.json").read_bytes()
        with self.assertRaises(Guidance) as cm:
            C.accept(self.p, [again["id"]])
        self.assertIn("اتغيرت بعد الاقتراحات", str(cm.exception))
        self.assertEqual(self.p.p("01_analysis/edit-decisions.json").read_bytes(), before)

    def test_m_accepting_a_pause_says_where_it_goes_in_plain_words(self):
        write_json(self.p.p("06_audio/dialogue/pauses.json"), {"cuts_ms": [[50000, 50800]]})
        doc = C.propose(self.p)
        pid = [x["id"] for x in doc["proposals"] if x["kind"] == "pause"][0]
        res = C.accept(self.p, [pid])
        self.assertEqual(res["added"], [])
        self.assertTrue(res["pauses_note"].startswith("السكتات دي"))

    def test_m_sign_off_on_without_a_phrase_protects_the_end(self):
        write_json(self.root / common.CLIENT_PROFILE_REL / "profile.json", {"endings": {"sign_off": {"on": True}}})
        doc = C.propose(self.p)
        self.assertTrue(doc["notes"][0]["ar"].startswith("جملة الختام"))


if __name__ == "__main__":
    unittest.main()
