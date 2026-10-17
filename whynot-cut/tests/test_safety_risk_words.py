# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 61 (Addendum K1, K-T1) — the words to confirm, risk first.

Today's words-to-confirm list is re-ordered by risk × doubt (doses, numbers, drug names, negations next to a claim,
durations first); behind the K-T1 switch `reel plan` refuses a graphic that shows a high-risk word the editor has not
confirmed yet (`reel transcript-verify`, by ear). Fixtures are made-up transcripts (tests/fixtures/safety/kt1).
Run:  bash tools/test.sh -p test_safety_risk_words.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib
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
from lib.common import Paths, write_json  # noqa: E402
from lib.safety import lexicon, risk_words as RW, switches  # noqa: E402
from lib.safety.numbers import fold, quantities, values_in  # noqa: E402

FIX = SK / "tests/fixtures/safety/kt1"
VID = "C0001"


def fixture(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def words(spec, step=400) -> list:
    """[(word, probability)] -> words.json records."""
    return [{"id": i, "segment_id": 1, "word": w, "start_ms": (i - 1) * step, "end_ms": (i - 1) * step + step - 40,
             "probability": p} for i, (w, p) in enumerate(spec, 1)]


def rank(ws, **kw):
    kw.setdefault("groups", lexicon.load_sources()["groups"])
    return RW.rank(ws, {}, **kw)


def ids_in_order(entries) -> list:
    return [wid for e in entries for wid in e["word_ids"]]


class Project(unittest.TestCase):
    """A client folder with spaces and Arabic in its path, one item, the K-T1 switch as the test sets it."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kt1_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        self.root = self.tmp / "د. تجربة Dr Test"
        for d in ("assets", "data/Raw"):
            (self.root / d).mkdir(parents=True)
        (self.root / ".whynot-client").write_text("{}", encoding="utf-8")
        self.p = Paths(self.root, VID)
        self.profile("profile.json", {"domain": "medical"})
        common.set_context(self.root)

    def profile(self, name, doc):
        write_json(self.root / common.CLIENT_PROFILE_REL / name, doc)

    def switch(self, on=True, **extra):
        self.profile("safety.json", {"switches": {switches.PLAN_BLOCK: on}, **extra})

    def put_words(self, ws, meta=None):
        write_json(self.p.p("02_transcription/words.json"), {"meta": meta or {}, "words": ws})

    def verify(self, by="editor", sha=None):
        data = self.p.p("02_transcription/words.json").read_bytes()
        write_json(self.p.p("02_transcription/verification.json"),
                   {"verified": True, "by": by, "at": "2026-10-17T10:00:00+00:00", "note": "",
                    "words_sha1": sha if sha is not None else hashlib.sha1(data).hexdigest()})

    def snapshot(self) -> dict:
        return {str(f.relative_to(self.root)): f.read_bytes() for f in self.root.rglob("*") if f.is_file()}


def event(eid, text):
    return {"event_id": eid, "template": "glass_card", "start_ms": 0, "end_ms": 2000, "params": {"text": text}}


DOSE_WORDS = [("خد", 0.95), ("٣٫٥", 0.41), ("مجم", 0.62), ("بعد", 0.96), ("الأكل", 0.97)]


# --- the spec's named tests ------------------------------------------------------------------------------------------
class TestSpec(Project):
    def test_dose_with_low_prob_ranks_first(self):
        ws = words([("يعني", 0.20), ("خد", 0.95), ("٥٠٠", 0.55), ("مجم", 0.70), ("اه", 0.10)])
        out = rank(ws)
        self.assertEqual(out[0]["word_ids"], [3, 4])
        self.assertEqual(out[0]["risk"], "dose")
        self.assertEqual(out[0]["value"], 500)
        self.assertTrue(all(not e["high"] for e in out[1:]))

    def test_arabic_indic_and_spelled_numbers(self):
        cases = {"٣٫٥ مجم": (3.5, "dose"), "٥٠٠ ملجم": (500, "dose"), "خمسمية مجم": (500, "dose"),
                 "ميتين وخمسين وحدة": (250, "dose"), "five hundred mg": (500, "dose"), "۱۰ ml": (10, "dose"),
                 "ست حبايات": (6, "dose"), "تلاتة": (3, "number"), "١٢": (12, "number")}
        for text, (value, kind) in cases.items():
            with self.subTest(text=text):
                q = quantities([fold(t) for t in text.split()])
                self.assertEqual(len(q), 1, q)
                self.assertEqual((q[0]["value"], q[0]["kind"]), (value, kind))
        self.assertEqual(values_in("خد ٣٫٥ مجم"), {3.5})
        self.assertEqual(values_in("خمسمية"), {500})

    def test_negation_next_to_claim_is_high_risk(self):
        for spec, neg_id in (([("الدوا", 0.95), ("ده", 0.96), ("مش", 0.50), ("بيعالج", 0.95), ("البرد", 0.95)], 3),
                             ([("don't", 0.55), ("take", 0.96), ("it", 0.98), ("daily", 0.97)], 1),
                             ([("ماتاخدش", 0.6), ("الدوا", 0.96), ("ده", 0.97)], 1)):
            with self.subTest(spec=spec):
                out = rank(words(spec))
                neg = [e for e in out if e["word_ids"] == [neg_id]]
                self.assertEqual(neg[0]["risk"], "negation")
                self.assertTrue(neg[0]["high"])
                self.assertIs(out[0], neg[0])
        # small talk: no claim anywhere near the «مش»
        out = rank(words([("أنا", 0.97), ("مش", 0.5), ("فاكر", 0.95), ("اسمه", 0.96)]))
        self.assertEqual([e["risk"] for e in out], ["other"])

    def test_unconfirmed_high_risk_word_blocks_plan(self):
        self.switch()
        self.put_words(words(DOSE_WORDS))
        errs = RW.plan_errors(self.p, [event("G1", "خد ٣٫٥ مجم بعد الأكل")])
        self.assertEqual(len(errs), 1, errs)
        self.assertTrue(errs[0].startswith("G1: «٣٫٥ مجم» (00:00:00.4) جرعة"), errs[0])
        self.assertIn("word 2, 3", errs[0])
        self.assertIn("transcript-verify", errs[0])
        # the same dose written in Western digits on the graphic is the same dose
        self.assertEqual(len(RW.plan_errors(self.p, [event("G2", "3.5 mg")])), 1)

    def test_confirmed_word_unblocks(self):
        self.switch()
        self.put_words(words(DOSE_WORDS))
        ev = [event("G1", "خد ٣٫٥ مجم")]
        self.verify()
        self.assertEqual(RW.plan_errors(self.p, ev), [])
        for by in ("claude", "delegated", "auto", "agent", "Mostafa", "", " "):   # only `--by editor` is by ear
            with self.subTest(by=by):
                self.verify(by=by)
                self.assertEqual(len(RW.plan_errors(self.p, ev)), 1)
        self.verify(sha="0" * 40)                           # verified, then the words changed
        self.assertEqual(len(RW.plan_errors(self.p, ev)), 1)

    def test_threshold_comes_from_config_with_basis(self):
        self.assertEqual(RW.threshold(), (RW.DEFAULT_THRESHOLD, RW.DEFAULT_BASIS))
        self.assertIn("measured", RW.DEFAULT_BASIS)
        self.profile("safety.json", {"risk_words": {"low_probability_threshold": 0.7,
                                                    "low_probability_threshold_basis": "our test basis"}})
        self.assertEqual(RW.threshold(), (0.7, "our test basis"))
        for bad in ({"low_probability_threshold": 0.7},                                  # no basis
                    {"low_probability_threshold": True, "low_probability_threshold_basis": "x"},
                    {"low_probability_threshold": "0.7", "low_probability_threshold_basis": "x"},
                    {"low_probability_threshold": 1.5, "low_probability_threshold_basis": "x"},
                    {"low_probability_threshold": 0, "low_probability_threshold_basis": "x"}):
            with self.subTest(bad=bad):
                self.profile("safety.json", {"risk_words": bad})
                self.assertEqual(RW.threshold(), (RW.DEFAULT_THRESHOLD, RW.DEFAULT_BASIS))
        # the threshold decides doubt: p=0.8 is doubtful at 0.9, not at 0.7
        ws = words([("٥٠٠", 0.8), ("مجم", 0.95)])
        self.assertEqual(len(RW.rank(ws, {}, thr=0.9)), 1)
        self.assertEqual(RW.rank(ws, {}, thr=0.7), [])


# --- acceptance: planted items on Arabic, English and mixed fixtures ---------------------------------------------------
class TestAcceptance(unittest.TestCase):
    def test_every_planted_item_ranks_above_every_low_risk_item(self):
        groups = lexicon.load_sources()["groups"]
        for name in ("ar", "en", "mixed"):
            with self.subTest(fixture=name):
                fx = fixture(name)
                out = RW.rank(fx["words"], fx["meta"], domain="medical", groups=groups)
                order = ids_in_order(out)
                high, low = fx["planted"]["high"], fx["planted"]["low"]
                for h in high:
                    self.assertIn(h, order, f"planted word {h} missing")
                last_high = max(order.index(h) for h in high)
                first_low = min(order.index(lw) for lw in low)
                self.assertLess(last_high, first_low, out)

    def test_low_confidence_claim_word_ranks_above_low_confidence_filler(self):
        ws = words([("يعني", 0.30), ("الدوا", 0.80), ("ده", 0.97), ("بيعالج", 0.85), ("البرد", 0.96)])
        out = rank(ws)
        self.assertEqual([e["risk"] for e in out], ["claim", "claim", "filler"])
        self.assertEqual(out[-1]["word_ids"], [1])


# --- the assignment's adversarial cases --------------------------------------------------------------------------------
class TestDecimals(unittest.TestCase):
    def test_decimal_dose_keeps_the_decimal_however_whisper_splits_it(self):
        for spec in ([("3.5", 0.4), ("مجم", 0.9)], [("3", 0.4), (".", 0.5), ("5", 0.4), ("مجم", 0.9)],
                     [("3.", 0.4), ("5", 0.4), ("مجم", 0.9)], [("٣٫٥", 0.4), ("مجم", 0.9)],
                     [("3,5", 0.4), ("مجم", 0.9)], [("3.5مجم", 0.4)]):
            with self.subTest(spec=spec):
                out = rank(words(spec))
                self.assertEqual(out[0]["value"], 3.5)
                self.assertEqual(out[0]["risk"], "dose")
                self.assertEqual(out[0]["word_ids"], list(range(1, len(spec) + 1)))

    def test_shown_number_is_compared_by_value_not_by_digits_dropped(self):
        e = rank(words([("3.5", 0.4), ("مجم", 0.9)]))[0]
        self.assertTrue(RW._shown(e, "3.5 mg"))
        self.assertTrue(RW._shown(e, "٣٫٥ ملجم"))
        self.assertFalse(RW._shown(e, "35 مجم"))
        self.assertFalse(RW._shown(e, "3 مجم"))

    def test_thousands_comma_is_not_a_decimal(self):
        self.assertEqual(rank(words([("1,500", 0.4), ("mg", 0.9)]))[0]["value"], 1500)


class TestDrugNames(unittest.TestCase):
    def test_drug_name_split_across_two_words_is_one_item(self):
        for spec in ([("ميت", 0.5), ("فورمين", 0.6)], [("para", 0.5), ("cetamol", 0.5)]):
            with self.subTest(spec=spec):
                out = rank(words(spec))
                self.assertEqual(len(out), 1, out)
                self.assertEqual((out[0]["risk"], out[0]["word_ids"]), ("drug", [1, 2]))

    def test_lexicon_word_with_arabic_clitic(self):
        out = rank(words([("والباراسيتامول", 0.6)]))
        self.assertEqual(out[0]["risk"], "drug")

    def test_generic_name_ending_and_latin_word_in_arabic_medical_clip(self):
        out = rank(words([("زولبيكسازول", 0.6)]))                     # unknown name, generic ending
        self.assertEqual(out[0]["risk"], "drug")
        ar = [("الدكتور", 0.97), ("كتب", 0.96), ("Zentrix", 0.6), ("للمريض", 0.97), ("امبارح", 0.97)]
        self.assertEqual(rank(words(ar), domain="medical")[0]["risk"], "drug")
        self.assertNotEqual(rank(words(ar), domain="general")[0]["risk"], "drug")
        en = [("the", 0.97), ("Zentrix", 0.6), ("store", 0.96)]           # an English clip: Latin is normal
        self.assertNotEqual(rank(words(en), domain="medical")[0]["risk"], "drug")

    def test_client_glossary_term_is_a_product_name(self):
        out = rank(words([("نوفاسكين", 0.6)]), terms=["نوفاسكين"])
        self.assertEqual(out[0]["risk"], "drug")
        self.assertEqual(rank(words([("نوفاسكين", 0.6)]), terms=[], groups=[])[0]["risk"], "other")


class TestLexiconLicence(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kt1lex_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def source(self, sid, terms, licence, **kw):
        f = self.tmp / f"{sid}.json"
        f.write_text(json.dumps({"groups": [[t] for t in terms]}), encoding="utf-8")
        rec = {"id": sid, "file": f.name, "licence": licence, "commercial_redistribution": True,
               "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
        rec.update(kw)
        return rec

    def manifest(self, *sources):
        m = self.tmp / "sources.json"
        m.write_text(json.dumps({"sources": list(sources)}), encoding="utf-8")
        return m

    def test_failing_licence_is_replaced_never_used_for_now(self):
        for bad in ("CC-BY-NC-4.0", "CC BY-NC-SA 3.0", "AGPL-3.0-only", "UMLS licence", "unknown", "",
                    "Proprietary", "LicenseRef-custom"):
            with self.subTest(licence=bad):
                r = lexicon.load_sources(self.manifest(self.source("bad", ["badterm"], bad),
                                                       self.source("good", ["goodterm"], "CC0-1.0")))
                self.assertNotIn("badterm", r["terms"])
                self.assertIn("goodterm", r["terms"])
                self.assertEqual(r["used"], ["good"])
                self.assertEqual(r["refused"][0]["id"], "bad")
                self.assertTrue(r["refused"][0]["reason"])

    def test_sha_mismatch_and_unconfirmed_commercial_use_are_refused(self):
        r = lexicon.load_sources(self.manifest(self.source("a", ["aterm"], "MIT", sha256="0" * 64),
                                               self.source("b", ["bterm"], "MIT", commercial_redistribution=None)))
        self.assertEqual(r["terms"], [])
        self.assertEqual([x["id"] for x in r["refused"]], ["a", "b"])

    def test_damaged_or_missing_manifest_gives_no_terms_and_says_why(self):
        bad = self.tmp / "broken.json"
        bad.write_text("{not json", encoding="utf-8")
        for m in (bad, self.tmp / "missing.json"):
            r = lexicon.load_sources(m)
            self.assertEqual((r["terms"], r["used"]), ([], []))
            self.assertEqual(len(r["refused"]), 1)

    def test_shipped_lexicon_passes_its_own_check(self):
        r = lexicon.load_sources()
        self.assertEqual(r["refused"], [])
        self.assertEqual(r["used"], ["whynot-own-medical-v1"])
        self.assertIn("paracetamol", r["terms"])
        self.assertIn("ميتفورمين", r["terms"])
        doc = json.loads(lexicon.MANIFEST.read_text(encoding="utf-8"))
        for s in doc["sources"]:
            self.assertTrue(s["basis"] and s["licence"] and s["sha256"])
            self.assertTrue(lexicon.licence_ok(s["licence"])[0])


class TestDoubt(unittest.TestCase):
    def test_signals(self):
        ws = words([("٥٠٠", 0.99), ("مجم", 0.99), ("و", 0.99), ("٢٠", 0.99), ("مجم", 0.99), ("و", 0.99),
                    ("٧", 0.99), ("مجم", 0.99), ("و", 0.99), ("٩", 0.99), ("مجم", 0.99)])
        ws[0]["flagged"] = {"note": "unclear"}
        ws[3]["machine_word"], ws[3]["corrected"] = "٢", {"reason": "kalam", "confidence": "medium"}
        del ws[6]["probability"]
        meta = {"redecoded_segments": [{"start_ms": 3600, "end_ms": 3700, "reason": "repeat"}]}
        out = RW.rank(ws, meta)
        got = {e["word_ids"][0]: e for e in out}
        self.assertEqual(sorted(got), [1, 4, 7, 10])
        self.assertEqual(got[1]["doubt"], 1.0)
        self.assertIn("«٢»", got[4]["why"][0][0])
        self.assertEqual(got[7]["doubt"], 0.3)
        self.assertEqual(got[10]["doubt"], 0.5)

    def test_sure_words_are_not_listed(self):
        self.assertEqual(rank(words([("خد", 0.99), ("٥٠٠", 0.95), ("مجم", 0.97)])), [])

    def test_duration_and_frequency(self):
        for spec in ([("مرتين", 0.5), ("في", 0.9), ("اليوم", 0.95)], [("twice", 0.5), ("a", 0.9), ("day", 0.95)],
                     [("كل", 0.95), ("٨", 0.5), ("ساعات", 0.95)], [("يوميا", 0.5)]):
            with self.subTest(spec=spec):
                out = rank(words(spec))
                self.assertEqual(out[0]["risk"], "duration")

    def test_everyday_words_that_are_numbers(self):
        out = rank(words([("الست", 0.5), ("دي", 0.95), ("نص", 0.5), ("الكلام", 0.95)]))
        self.assertTrue(all(not e["high"] for e in out), out)

    def test_partial_and_odd_records_never_crash(self):
        ws = [{"id": 1, "word": "٥٠٠"}, {"id": 2}, "junk", None, {"id": 3, "word": "  "},
              {"id": 4, "word": "مجم", "probability": True, "start_ms": "x"}, {"word": "خد", "probability": 0.2}]
        out = RW.rank(ws, {"redecoded_segments": ["junk", {"start_ms": None}]})
        self.assertTrue(out)
        self.assertEqual(RW.rank([], None), [])
        self.assertEqual(RW.rank(None, "junk"), [])

    def test_stable_across_reruns(self):
        fx = fixture("mixed")
        g = lexicon.load_sources()["groups"]
        a = RW.rank(fx["words"], fx["meta"], domain="medical", groups=g)
        b = RW.rank(list(reversed(fx["words"])), fx["meta"], domain="medical", groups=g)
        self.assertEqual(a, b)


class TestSwitchAndSurfaces(Project):
    def test_switch_off_changes_nothing(self):
        self.put_words(words(DOSE_WORDS))
        ev = [event("G1", "خد ٣٫٥ مجم")]
        review = "# Subtitle Review\n\n**Status**\n\n## Low-confidence words\n- x\n"
        todo = [{"id": 5, "word": "الأكل"}, {"id": 2, "word": "٣٫٥"}]
        for sw in (None, {}, {"switches": {}}, {"switches": {switches.PLAN_BLOCK: "true"}},
                   {"switches": {switches.PLAN_BLOCK: 1}}, {"switches": {switches.PLAN_BLOCK: False}}):
            with self.subTest(safety=sw):
                f = self.root / common.CLIENT_PROFILE_REL / "safety.json"
                f.unlink(missing_ok=True)
                if sw is not None:
                    self.profile("safety.json", sw)
                self.assertFalse(switches.enabled(switches.PLAN_BLOCK))
                self.assertEqual(RW.plan_errors(self.p, ev), [])
                self.assertEqual(RW.with_review_block(review, self.p), review)
                self.assertIs(RW.needs_you_order(todo, self.p), todo)

    def test_damaged_safety_json_means_off(self):
        f = self.root / common.CLIENT_PROFILE_REL / "safety.json"
        f.write_text("{broken", encoding="utf-8")
        self.put_words(words(DOSE_WORDS))
        self.assertEqual(RW.plan_errors(self.p, [event("G1", "٣٫٥ مجم")]), [])

    def test_review_block_arabic_first_and_at_the_top(self):
        self.switch()
        self.put_words(words(DOSE_WORDS + [("يعني", 0.2)]))
        review = "# Subtitle Review — a.mp4\n\n**Status: MACHINE TRANSCRIPT**\n\n## Low-confidence words (p < 0.5) — 1\n"
        out = RW.with_review_block(review, self.p)
        k_block, k_old = out.index("## راجع دول الأول"), out.index("## Low-confidence words")
        self.assertLess(k_block, k_old)
        self.assertTrue(out.startswith("# Subtitle Review — a.mp4"))
        block = out[k_block:k_old]
        self.assertLess(block.index("دي كلمات"), block.index("These words"))
        self.assertIn("**٣٫٥ مجم**", block)
        self.assertNotIn("يعني", block)
        self.assertIn(RW.DEFAULT_BASIS, block)
        # nothing risky: a plain "none"
        self.put_words(words([("يعني", 0.2)]))
        self.assertIn("- مفيش / none", RW.with_review_block(review, self.p))

    def test_needs_you_order_risk_first_nothing_lost(self):
        self.switch()
        self.put_words(words([("يعني", 0.2), ("خد", 0.95), ("٥٠٠", 0.4), ("مجم", 0.6), ("اه", 0.1)]))
        # today's list (threshold 0.5) has «يعني», «٥٠٠», «اه» and a word K-T1 does not know; «مجم» (0.6) is not in it
        todo = [{"id": 1, "word": "يعني"}, {"id": 3, "word": "٥٠٠"}, {"id": 5, "word": "اه"}, {"id": 9, "word": "x"}]
        got = RW.needs_you_order(todo, self.p)
        self.assertEqual([w["id"] for w in got], [3, 4, 1, 5, 9])
        self.verify()                                         # confirmed: today's list as it was
        self.assertIs(RW.needs_you_order(todo, self.p), todo)

    def test_flagged_word_is_left_to_todays_check(self):
        self.switch()
        ws = words(DOSE_WORDS)
        for w in ws[1:3]:
            w["flagged"] = {"note": "unclear"}
        self.put_words(ws)
        self.assertEqual(RW.plan_errors(self.p, [event("G1", "خد ٣٫٥ مجم")]), [])

    def test_damaged_profile_never_crashes_the_check(self):
        self.switch()
        self.put_words(words(DOSE_WORDS))
        ev = [event("G1", "٣٫٥ مجم")]
        (self.root / common.CLIENT_PROFILE_REL / "medical-glossary.json").write_text("[", encoding="utf-8")
        self.assertEqual(len(RW.plan_errors(self.p, ev)), 1)          # a broken glossary: the shipped list still works
        # a broken profile.json breaks every client setting (today's `reel plan` refuses the file by name): no crash
        (self.root / common.CLIENT_PROFILE_REL / "profile.json").write_text("{broken", encoding="utf-8")
        self.assertEqual(RW.plan_errors(self.p, ev), [])

    def test_missing_or_damaged_words_file_adds_no_block(self):
        self.switch()
        ev = [event("G1", "٣٫٥ مجم")]
        self.assertEqual(RW.plan_errors(self.p, ev), [])
        f = self.p.p("02_transcription/words.json")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{broken", encoding="utf-8")
        self.assertEqual(RW.plan_errors(self.p, ev), [])
        write_json(f, {"words": "nope"})
        self.assertEqual(RW.plan_errors(self.p, ev), [])

    def test_a_refusal_writes_nothing_and_reruns_are_identical(self):
        self.switch()
        self.put_words(words(DOSE_WORDS))
        before = self.snapshot()
        ev = [event("G1", "خد ٣٫٥ مجم"), "junk", event("G2", "")]
        a = RW.plan_errors(self.p, ev)
        b = RW.plan_errors(self.p, ev)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 1)
        self.assertEqual(self.snapshot(), before)

    def test_same_result_on_macos(self):
        self.switch()
        self.put_words(words(DOSE_WORDS))
        ev = [event("G1", "خد ٣٫٥ مجم")]
        win = RW.plan_errors(self.p, ev)
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertEqual(RW.plan_errors(self.p, ev), win)

    def test_no_new_false_block_on_the_existing_transcript_fixture(self):
        """The plan fixture every pipeline test uses (test_pipeline.make_project) with its own graphics: the switch on
        adds no error."""
        from test_pipeline import make_project
        root, p, _ = make_project(self.tmp / "golden")
        write_json(root / common.CLIENT_PROFILE_REL / "safety.json", {"switches": {switches.PLAN_BLOCK: True}})
        write_json(root / common.CLIENT_PROFILE_REL / "profile.json", {"domain": "medical"})
        common.set_context(root)
        spec = json.loads((SK / "tests/fixtures/golden_plan/01_analysis__timeline-spec.json").read_text("utf-8"))
        self.assertTrue(spec["events"])
        self.assertEqual(RW.plan_errors(p, spec["events"]), [])


# --- review round 1 (independent reviewer, 2026-10-17): I1–I10, M5, M7, M8, N1, N2 -------------------------------------
class TestReviewRound1Numbers(unittest.TestCase):
    def q(self, text):
        from lib.safety.numbers import tokens
        return [(x["value"], x["kind"]) for x in quantities(tokens(text))]

    def test_i1_fractions_after_a_number_and_vulgar_fractions(self):
        self.assertEqual(self.q("٣ ونص مجم"), [(3.5, "dose")])
        self.assertEqual(self.q("3 و نص مجم"), [(3.5, "dose")])
        self.assertEqual(self.q("حباية ونص"), [(1.5, "dose")])
        self.assertEqual(self.q("½ حباية"), [(0.5, "dose")])
        self.assertEqual(self.q("3½ mg"), [(3.5, "dose")])
        self.assertEqual(self.q("3 and a half mg"), [(3.5, "dose")])
        self.assertEqual(self.q("تلاتة ونص"), [(3.5, "number")])

    def test_i2_egyptian_dose_and_frequency_forms(self):
        self.assertEqual(self.q("خمسميت مجم"), [(500, "dose")])
        self.assertEqual(self.q("حباية واحدة"), [(1, "dose")])
        self.assertEqual(self.q("حبايتين"), [(2, "dose")])
        self.assertEqual(self.q("بساعتين"), [(2, "duration")])
        self.assertEqual(self.q("مرة في اليوم"), [(1, "duration")])
        self.assertEqual(self.q("مرة كل يومين"), [(1, "duration")])
        self.assertEqual(self.q("٥ سي سي"), [(5, "dose")])
        self.assertEqual(self.q("%70"), [(70, "dose")])
        for spec in ([("يوم", 0.5), ("بعد", 0.9), ("يوم", 0.9)], [("قبل", 0.95), ("النوم", 0.5)]):
            with self.subTest(spec=spec):
                self.assertEqual(rank(words(spec))[0]["risk"], "duration")

    def test_i4_on_screen_values_with_context(self):
        self.assertEqual(values_in("١٢٠/٨٠"), {120, 80})
        self.assertEqual(values_in("نص حباية"), {0.5})
        self.assertEqual(values_in("ست حبايات"), {6})
        self.assertEqual(values_in("ست جميلة"), set())
        self.assertEqual(values_in("مرتين يوميًا"), {2})


class TestReviewRound1Ranking(Project):
    def test_i3_negations_that_change_a_dose_instruction(self):
        for spec in ([("لا", 0.5), ("تزيد", 0.95), ("عن", 0.95), ("4", 0.95)],
                     [("never", 0.5), ("more", 0.95), ("than", 0.95), ("4", 0.95)],
                     [("مش", 0.5), ("لازم", 0.95), ("تاخده", 0.95)],
                     [("ما", 0.5), ("تاخدهاش", 0.95), ("على", 0.95), ("الريق", 0.95)],
                     [("ماتاخديش", 0.5), ("المضاد", 0.95)],
                     [("مينفعش", 0.5), ("للحامل", 0.95)],
                     [("اوعى", 0.5), ("توقف", 0.95), ("الدوا", 0.95)]):
            with self.subTest(spec=spec):
                out = rank(words(spec))
                self.assertEqual(out[0]["risk"], "negation", out)
                self.assertTrue(out[0]["high"])

    def test_i5_drug_spelling_groups_and_near_misses(self):
        self.switch()
        self.put_words(words([("خد", 0.95), ("الميتفورمين", 0.5), ("بعد", 0.95), ("الأكل", 0.95)]))
        self.assertEqual(len(RW.plan_errors(self.p, [event("G1", "Metformin 500")])), 1)
        self.assertEqual(len(RW.plan_errors(self.p, [event("G1", "جلوكوفاج")])), 1)
        self.assertEqual(RW.plan_errors(self.p, [event("G1", "Insulin")]), [])
        for heard in ("البنادول", "اوزمبك", "Panadol", "Glucophage"):
            with self.subTest(heard=heard):
                self.assertEqual(rank(words([(heard, 0.5)]), domain="medical")[0]["risk"], "drug")

    def test_i6_one_unsure_negation_does_not_block_every_graphic_with_that_word(self):
        self.switch()
        self.put_words(words([("الدوا", 0.95), ("ده", 0.95), ("مش", 0.5), ("بيعالج", 0.95), ("البرد", 0.95)]))
        self.assertEqual(RW.plan_errors(self.p, [event("G1", "مش كل صداع خطير")]), [])
        self.assertEqual(len(RW.plan_errors(self.p, [event("G1", "الدوا مش بيعالج البرد")])), 1)

    def test_i8_episode_verification_counts_only_when_the_episode_was_verified_by_ear(self):
        self.switch()
        ep = self.root / "output/episodes/EP01/02_transcription"
        ep.mkdir(parents=True)
        write_json(ep / "words.json", {"words": []})
        self.put_words(words(DOSE_WORDS), meta={"episode_transcript": str(ep / "transcript.json")})
        self.verify(by="episode verification")
        ev = [event("G1", "٣٫٥ مجم")]
        data = (ep / "words.json").read_bytes()
        for by, blocked in (("claude", True), ("delegated", True), ("editor", False)):
            with self.subTest(episode_by=by):
                write_json(ep / "verification.json", {"verified": True, "by": by,
                                                      "words_sha1": hashlib.sha1(data).hexdigest()})
                self.assertEqual(bool(RW.plan_errors(self.p, ev)), blocked)
        (ep / "verification.json").unlink()
        self.assertTrue(RW.plan_errors(self.p, ev))
        # the reel's own copy names who checked the episode (reels.py patch): a "claude" check stays one
        write_json(ep / "verification.json", {"verified": True, "by": "editor",
                                              "words_sha1": hashlib.sha1(data).hexdigest()})
        self.assertEqual(RW.plan_errors(self.p, ev), [])
        data_r = self.p.p("02_transcription/words.json").read_bytes()
        write_json(self.p.p("02_transcription/verification.json"),
                   {"verified": True, "by": "episode verification", "episode_by": "claude",
                    "words_sha1": hashlib.sha1(data_r).hexdigest()})
        self.assertTrue(RW.plan_errors(self.p, ev))

    def test_i9_damaged_meta_never_crashes(self):
        self.switch()
        for meta in ({"redecoded_segments": 7}, {"redecoded_segments": "x"}, {"offset_ms": "x"}, []):
            with self.subTest(meta=meta):
                write_json(self.p.p("02_transcription/words.json"), {"meta": meta, "words": words(DOSE_WORDS)})
                self.assertEqual(len(RW.plan_errors(self.p, [event("G1", "٣٫٥ مجم")])), 1)

    def test_i9_an_unexpected_failure_is_one_plain_error(self):
        self.switch()
        self.put_words(words(DOSE_WORDS))
        with mock.patch.object(RW, "_errors", side_effect=RuntimeError("boom")):
            errs = RW.plan_errors(self.p, [event("G1", "٣٫٥ مجم")])
        self.assertEqual(len(errs), 1)
        self.assertTrue(errs[0].startswith("فحص الكلمات المهمة ما اشتغلش"))

    def test_i10_decoder_spans_move_with_a_reel_cut_from_an_episode(self):
        ws = words([("٥٠٠", 0.99), ("مجم", 0.99), ("و", 0.99), ("٧", 0.99), ("مجم", 0.99)])
        meta = {"offset_ms": 60000, "redecoded_segments": [{"start_ms": 61500, "end_ms": 61700}]}
        out = RW.rank(ws, meta)
        self.assertEqual([e["word_ids"] for e in out], [[4, 5]])

    def test_m5_social_and_clinic_words_are_not_drug_names(self):
        ar = [("تابعونا", 0.97), ("على", 0.97), ("Instagram", 0.6), ("و", 0.97), ("Keto", 0.6), ("دايت", 0.97)]
        self.assertTrue(all(e["risk"] != "drug" for e in rank(words(ar), domain="medical")))

    def test_religious_client_glossary_is_not_a_drug_list(self):
        """Measured on the whynot-test projects: a religious client's glossary holds verse words («آمنوا»)."""
        self.switch()
        self.profile("medical-glossary.json", {"terms": {"arabic": ["آمنوا"]}})
        self.put_words(words([("الذين", 0.95), ("آمنوا", 0.78)]))
        ev = [event("G1", "الذين آمنوا")]
        self.profile("profile.json", {"domain": "religious"})
        self.assertEqual(RW.plan_errors(self.p, ev), [])
        self.profile("profile.json", {"domain": "medical"})
        self.assertEqual(len(RW.plan_errors(self.p, ev)), 1)

    def test_r1_negation_by_a_number_is_matched_with_the_number_by_value(self):
        """Review round 2, R1: «لا اكتر من اربعة» heard, «لا أكتر من 4» shown: blocked (the dose limit is the claim)."""
        self.switch()
        for spoken, shown in (([("لا", 0.5), ("اكتر", 0.95), ("من", 0.95), ("اربعة", 0.95)], "لا أكتر من 4"),
                              ([("مش", 0.5), ("اكتر", 0.95), ("من", 0.95), ("حبايتين", 0.95)], "مش أكتر من 2 حباية"),
                              ([("never", 0.5), ("more", 0.95), ("than", 0.95), ("four", 0.95)], "never more than 4")):
            with self.subTest(spoken=spoken):
                self.put_words(words(spoken))
                self.assertEqual(len(RW.plan_errors(self.p, [event("G1", shown)])), 1)
                self.assertEqual(RW.plan_errors(self.p, [event("G1", "مش كل حاجة")]), [])

    def test_client_threshold_never_borrows_the_shipped_basis(self):
        """With config/defaults/safety.json shipped (value + basis), a client file giving only a number is not
        accepted: the shipped value and basis stay."""
        shipped = self.tmp / "defaults"
        shipped.mkdir()
        write_json(shipped / "safety.json", {"risk_words": {"low_probability_threshold": 0.85,
                                                            "low_probability_threshold_basis": "shipped basis"}})
        with mock.patch.object(common, "CONFIG_DIR", shipped):
            self.assertEqual(RW.threshold(), (0.85, "shipped basis"))
            self.profile("safety.json", {"risk_words": {"low_probability_threshold": 0.7}})
            self.assertEqual(RW.threshold(), (RW.DEFAULT_THRESHOLD, RW.DEFAULT_BASIS))
            self.profile("safety.json", {"risk_words": {"low_probability_threshold": 0.7,
                                                        "low_probability_threshold_basis": "client measured"}})
            self.assertEqual(RW.threshold(), (0.7, "client measured"))

    def test_n1_a_check_under_another_name_says_why_it_still_blocks(self):
        self.switch()
        self.put_words(words(DOSE_WORDS))
        ev = [event("G1", "٣٫٥ مجم")]
        self.assertNotIn("اتسجّلت باسم", RW.plan_errors(self.p, ev)[0])            # not verified at all
        self.verify(by="Mostafa")
        err = RW.plan_errors(self.p, ev)[0]
        self.assertIn("المراجعة اتسجّلت باسم «mostafa»", err)
        self.assertIn("--by editor", err)

    def test_r2_agent_is_a_subagent_name_not_the_editor(self):
        self.switch()
        self.put_words(words(DOSE_WORDS))
        self.verify(by=" Agent ")
        self.assertTrue(RW.plan_errors(self.p, [event("G1", "٣٫٥ مجم")]))

    def test_m1_near_miss_only_for_medical_and_not_everyday_words(self):
        self.assertNotEqual(rank(words([("بروتين", 0.5)]), domain="medical")[0]["risk"], "drug")
        self.assertNotEqual(rank(words([("aspiring", 0.5)]), domain="medical")[0]["risk"], "drug")
        self.assertEqual(rank(words([("اوزمبك", 0.5)]), domain="medical")[0]["risk"], "drug")
        self.assertNotEqual(rank(words([("اوزمبك", 0.5)]), domain="general")[0]["risk"], "drug")

    def test_m2_a_plain_number_blocks_only_for_a_medical_client(self):
        self.switch()
        self.put_words(words([("عندي", 0.95), ("٣", 0.5), ("عيال", 0.95)]))
        ev = [event("G1", "3 نصائح")]
        self.assertEqual(len(RW.plan_errors(self.p, ev)), 1)            # medical client (Project default)
        self.profile("profile.json", {"domain": "general"})
        self.assertEqual(RW.plan_errors(self.p, ev), [])

    def test_m6_dot_thousands_matches_both_readings(self):
        e = rank(words([("1.500", 0.4), ("mg", 0.9)]))[0]
        self.assertTrue(RW._shown(e, "1500 mg"))
        self.assertTrue(RW._shown(e, "1.5 mg"))
        self.assertFalse(RW._shown(e, "15 mg"))

    def test_m8_partly_flagged_dose_is_left_to_todays_check(self):
        self.switch()
        ws = words(DOSE_WORDS)
        ws[2]["flagged"] = {"note": "unclear"}
        self.put_words(ws)
        self.assertEqual(RW.plan_errors(self.p, [event("G1", "٣٫٥ مجم")]), [])

    def test_n1_nan_probability_is_no_confidence(self):
        out = RW.rank(words([("٥٠٠", float("nan")), ("مجم", 0.99)]), {})
        self.assertEqual(out[0]["doubt"], 0.3)

    def test_n2_lexicon_refusal_is_arabic_first(self):
        rep = {"items": [], "threshold": 0.9, "basis": "b",
               "lexicon_refused": [{"id": "x", "reason": "licence CC-BY-NC", "reason_ar": "مصدر اترفض"}]}
        line = [ln for ln in RW.review_block(rep).splitlines() if "refused" in ln][0]
        self.assertLess(line.index("مصدر"), line.index("refused"))


if __name__ == "__main__":
    unittest.main()
