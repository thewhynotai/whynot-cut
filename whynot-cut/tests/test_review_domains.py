# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 50 = Addendum M1-T1: review domains (medical, religious, business, ai) as data.

The registry (config/review-domains/registry.json) lists the domains; each has checker guidance, a trigger lexicon and
eval cases, so a fifth domain needs no engine change. The client set (profile domains + the always-on ones) is the
stable review key (`review_domain_key`); domains DETECTED in one line's words (on-screen text + the transcript evidence
it cites) add a required flag to that line only, and only under `review_detect: review`. `reel review-scan` is
deterministic and read-only.
Run:  bash tools/test.sh -p test_review_domains.py
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
from lib import review_domains as RD  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402
from lib.errors import Guidance  # noqa: E402

VID = "C0001"
FIXTURES = SK / "tests" / "fixtures" / "review_domains"
SHIPPED = ("ai", "business", "medical", "religious")

# A plain medical clip: none of these may trigger business, religious or ai.
PLAIN_MEDICAL = [
    "الملح الكتير بيرفع الضغط",
    "Take 500 mg daily / after food",
    "اشرب ٨ كوبايات مية في اليوم",
    "٥٠٪ من المرضى بيتحسنوا في أول أسبوع",
    "مضاعفات السكر خطيرة",
    "الجسم معتمد على الأنسولين",
    "علاج حديث للضغط",
    "إيه أعراض السكر؟",
    "والنبي اسمعوا الكلام ده",
    "حرام عليك تهمل صحتك",
    "الصورة دي بتوضح الشريان",
    "ضمن الخطة العلاج بالأكل",
    "السكر بيكسب الجسم وزن",                    # review round 1: everyday doctor talk that used to hit business
    "هتكسب وزن لو كملت كده",
    "مريض السكر كسب ثقته في نفسه",
    "التدخين بيضاعف خطر الجلطة",
    "السمنة بتضاعف احتمال السكر",
    "الدم العائد للقلب",
    "صحتك هي أهم استثمار",
    "السعر الحراري للأكل ده عالي",
    "ده حلال فيك",
    "في الحديث ده هنتكلم عن الضغط",
    "نام تمن ساعات",                            # review round 2: تمن = eight, جم = grams, everyday words
    "ثمن الكوب سكر كفاية",
    "30 جم بروتين في اليوم",
    "الوحيد في العيلة اللي عنده السكر",
    "أول عيادة على اليمين",
    "مكسب كبير لصحتك",
    "ضمانات السلامة في العملية",
    "مضمون الفيديو ده عن الضغط",                 # review round 3: مضمون = content
    "الوحيدين في العيلة",
    "الآية اتقلبت بعد العلاج",
]


def domains(text: str) -> set:
    return set(RD.detect(text))


def make_client(tmp: Path) -> Path:
    root = tmp / "Dr Test د. تجربة"
    for d in ("assets/Brand", "data/Raw"):
        (root / d).mkdir(parents=True)
    (root / ".whynot-client").write_text("{}", encoding="utf-8")
    return root


def event(eid: str, a: int, b: int, evidence: str | None = None, **params) -> dict:
    e = {"event_id": eid, "decision_id": "D" + eid[1:], "template": "glass_card", "start_ms": a, "end_ms": b,
         "src_start_ms": a, "src_end_ms": b, "params": params}
    if evidence is not None:
        e["evidence"] = evidence
    return e


def spec(*events) -> dict:
    return {"fps": 30, "duration_frames": 900, "generated": "2026-10-17T09:00:00+00:00", "main_segments": [],
            "events": list(events)}


def tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(root.rglob("*")):
        h.update(str(f.relative_to(root)).encode())
        if f.is_file():
            h.update(f.read_bytes())
    return h.hexdigest()


class Base(unittest.TestCase):
    PROFILE: dict | None = None

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m1t1_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        self.root = make_client(self.tmp)
        self.p = Paths(self.root, VID)
        if self.PROFILE is not None:
            self.profile(self.PROFILE)
        common.set_context(self.root)

    def profile(self, doc: dict):
        write_json(self.root / common.CLIENT_PROFILE_REL / "profile.json", doc)

    def put(self, *events):
        write_json(self.p.p("01_analysis/timeline-spec.json"), spec(*events))

    def line(self, scan: dict, eid: str) -> dict:
        return next(x for x in scan["lines"] if x["event_id"] == eid)


# ---------------------------------------------------------------- key and client set
class TestKey(unittest.TestCase):
    def test_domain_key_canonical(self):
        for ids in (["business", "medical", "ai"], ["ai", "business", "medical"], [" Medical ", "AI", "business"],
                    ["medical", "medical", "ai", "business", "BUSINESS"], ("business", "ai", "medical")):
            self.assertEqual(RD.review_domain_key(ids), "ai+business+medical", ids)
        self.assertEqual(RD.review_domain_key(["religious", "medical", "ai"]), "ai+medical+religious")
        self.assertEqual(RD.review_domain_key(["medical", "ai"]), "ai+medical")

    def test_unknown_id_refused_naming_it(self):
        with self.assertRaises(Guidance) as cm:
            RD.review_domain_key(["medical", "cooking"])
        self.assertIn("cooking", str(cm.exception))
        for bad in (["ai+medical"], [""], [None], [3], "medical"):
            with self.assertRaises(Guidance, msg=repr(bad)):
                RD.review_domain_key(bad)


class TestClientSet(Base):
    def key(self, doc: dict) -> str:
        self.profile(doc)
        return RD.review_domain_key(RD.client_set())

    def test_legacy_domains_map(self):
        self.assertEqual(self.key({}), "ai+medical")                       # no domain at all: general
        for d in ("general", "medical", None, "  General "):
            self.assertEqual(self.key({"domain": d}), "ai+medical", d)
        for d in ("religious", " Religious "):
            self.assertEqual(self.key({"domain": d}), "ai+medical+religious", d)

    def test_medical_and_ai_always_in_the_client_set(self):
        for doms in ([], ["business"], ["religious"], ["business", "religious"]):
            self.profile({"review_domains": doms})
            cs = RD.client_set()
            self.assertTrue({"medical", "ai"} <= set(cs), doms)

    def test_composite_key(self):
        self.assertEqual(self.key({"review_domains": ["business", "medical"]}), "ai+business+medical")
        self.assertEqual(self.key({"review_domains": ["Business"], "domain": "religious"}),
                         "ai+business+medical+religious")             # adding business never drops religious
        self.assertEqual(self.key({"review_domains": None, "domain": "religious"}), "ai+medical+religious")

    def test_unknown_profile_domain_refused_naming_it(self):
        for bad in ({"review_domains": ["business", "crypto"]}, {"review_domains": "business"},
                    {"review_domains": [7]}, {"review_domains": ["ai+business"]}):
            self.profile(bad)
            with self.assertRaises(Guidance, msg=repr(bad)) as cm:
                RD.client_set()
            if "crypto" in json.dumps(bad):
                self.assertIn("crypto", str(cm.exception))

    def test_review_detect(self):
        self.profile({})
        self.assertEqual(RD.detect_mode(), "review")
        for v, want in (("review", "review"), (" Suggest", "suggest"), ("OFF", "off"), (None, "review")):
            self.profile({"review_detect": v})
            self.assertEqual(RD.detect_mode(), want, v)
        for bad in ("sometimes", 1, True, ["review"]):
            self.profile({"review_detect": bad})
            with self.assertRaises(Guidance, msg=repr(bad)):
                RD.detect_mode()


# ---------------------------------------------------------------- detection on one text
class TestDetect(unittest.TestCase):
    def test_business_triggers_arabic_english_egyptian(self):
        for t in ("بس بـ ٩٩ جنيه", "EGP 500", "$99", "السعر 1500 ج.م", "هتكسب ٢٠ ألف في الشهر", "دخل شهري ثابت",
                  "ROI in 3 months", "guaranteed results", "النتيجة مضمونة", "نتيجة مضمونة ١٠٠٪", "١٠٠ ٪ من غير تعب",
                  "100% results", "مية في المية", "أحسن من أي عيادة تانية", "better than the rest", "#1 in Egypt",
                  "الأول في مصر", "معتمد من وزارة الصحة", "FDA approved", "لفترة محدودة", "آخر فرصة", "الكشف بكام؟",
                  "الاستشارة ببلاش", "خصم ٣٠٪", "هيضاعف دخلك", "بنضمن لك النتيجة", "مَضْمُون", "مضـــمون"):
            self.assertIn("business", domains(t), t)

    def test_business_claims_found_in_review(self):
        """Review round 1: claims the first lexicon missed (superiority without من/في, guarantees, earnings, prices,
        amounts glued to the prefix ب)."""
        for t in ("أحسن دكتور في مصر", "أول مركز في مصر", "إحنا الوحيدين في مصر", "best clinic in Cairo",
                  "Number 1 in Egypt", "نمبر وان", "cheapest in town", "أرخص من أي مكان", "أنا ضامنلك النتيجة",
                  "ضامن لك", "الضمان سنة", "هتعمل فلوس كتير", "هتقبض ١٠ آلاف", "هتكسب ٢٠ ألف في الشهر",
                  "100 بالمية", "مئة بالمئة", "money back", "التمن ٥٠٠", "الكشف مجاني", "الاشتراك الشهري ٢٠٠",
                  "بالتقسيط", "الأماكن محدودة", "التمن ٥٠٠", "بتمن رمزي", "1500 ج.م", "دكتور معتمد", "معتمدة دوليا", "الكورس بـ٥٠٠ ريال", "الكشف ب٣٠٠ج",
                  "الكورس ب500EGP", "3 آلاف دولار", "EGP500", "السعر.500 جنيه", "النتيجة مضمونة الأسبوع ده", "مضمونين النتيجة", "الـROI عالي", "السعر ٥٠٠"):
            self.assertIn("business", domains(t), t)
        self.assertEqual([m["match"] for m in RD.detect("$ 99")["business"] if m["rule"] == "currency-amount"],
                         ["$ 99"])

    def test_ai_triggers(self):
        for t in ("الذكاء الاصطناعي بيساعد الدكتور", "بنستخدم الـ AI", "A.I. diagnosis", "ChatGPT قال كده",
                  "artificial intelligence", "التطبيق ده ذكاء اصطناعي"):
            self.assertIn("ai", domains(t), t)

    def test_ai_capability_and_accuracy_only_with_an_ai_word(self):
        self.assertNotIn("ai", domains("الدكتور بيشخّص المرض بدقة ٩٥٪"))
        hit = RD.detect("الـ AI بيشخّص المرض بدقة ٩٥٪")["ai"]
        rules = {m["rule"] for m in hit}
        self.assertTrue({"ai-acronym", "ai-capability", "ai-accuracy-number"} <= rules, hit)

    def test_religious_triggers(self):
        for t in ("﴿وَعَمِلُوا الصَّالِحَاتِ﴾", "قال تعالى في كتابه", "النبي ﷺ", "صلى الله عليه وسلم", "hadith",
                  "الأكل ده حلال ولا حرام؟", "الرسول قال", "ربنا قال في كتابه", "قرآن كريم", "the Prophet said",
                  "Allah says", "صحيح البخاري", "حديث صحيح", "وتزودوا بالتقوى", "الشرائع نزلت لتنظيم حياة الناس",
                  "آمنوا وعملوا الصالحات"):
            self.assertIn("religious", domains(t), t)

    def test_medical_triggers(self):
        for t in ("الجرعة ٥٠٠ ملجم", "Take 500 mg", "العلاج الصح", "أعراض السكر", "treatment plan"):
            self.assertIn("medical", domains(t), t)

    def test_plain_medical_fixture_triggers_nothing_else(self):
        for t in PLAIN_MEDICAL:
            self.assertFalse(domains(t) & {"business", "religious", "ai"}, (t, RD.detect(t)))

    def test_word_boundaries(self):
        for t in ("بالـAI", "الـAI بيشخص", "AI" + chr(0x200b) + "tools"):
            self.assertIn("ai", domains(t), repr(t))
        for t in ("AIDS awareness", "he said it", "Aida came", "aI", "إيه الحكاية", "the bestseller list"):
            self.assertNotIn("ai", domains(t), t)
        self.assertNotIn("business", domains("the bestseller list"))     # "the best" as a word, not a prefix

    def test_business_word_inside_a_quran_verse_is_never_business(self):
        verse = "﴿فَمَا رَبِحَت تِّجَارَتُهُمْ﴾"
        hit = RD.detect(verse)
        self.assertIn("religious", hit)
        self.assertNotIn("business", hit)
        self.assertIn("business", domains("ربحت التجارة السنة دي"))     # the same word outside a verse
        self.assertIn("business", domains(verse + " والكورس بـ ٥٠٠ جنيه"))   # a price next to the verse still counts

    def test_an_unclosed_verse_or_quote_hides_nothing(self):
        for t in ("﴿فما ربحت تجارتهم والكورس بـ ٥٠٠ جنيه نتيجة مضمونة", "قال الله «فما ربحت والكورس بـ ٥٠٠ جنيه مضمون",
                  "﴿ ومن يتق الله الكشف 500 جنيه ﴿ ألا بذكر الله ﴾",                     # review round 2: re-opened
                  "قال الله «ومن يتق الله. الكشف 500 جنيه مضمون. قال تعالى «ألا بذكر الله»",
                  "ربنا قال نصبر، والكشف \"500 جنيه\"",
                  "قال تعالى \"إن الله غفور رحيم. والكشف بـ 500 جنيه \"عرض\""):             # review round 3: straight "                                 # a gap that is no connector
            hit = RD.detect(t)
            self.assertIn("religious", hit, t)
            self.assertIn("business", hit, t)

    def test_quoted_scripture_after_a_citation_is_not_business(self):
        for t in ("قال تعالى: «فما ربحت تجارتهم»", "قال تعالى في كتابه «فما ربحت تجارتهم»", "قال رسول الله ﷺ «التاجر الصدوق الأمين مع النبيين» ربح"):
            hit = RD.detect(t)
            self.assertIn("religious", hit, t)
            self.assertFalse([m for m in hit.get("business", []) if "تجار" in m["match"] or "ربحت" in m["match"]], t)
        self.assertIn("business", domains("قال الله «فما ربحت تجارتهم» وانا بقولك الكورس هيضاعف ربحك"))
        hit = RD.detect("قال الله تعالى في كتابه «فما ربحت تجارتهم بـ ٥٠٠ جنيه»")       # connector words, price inside
        self.assertIn("religious", hit)
        self.assertNotIn("business", hit)

    def test_invisible_characters_do_not_hide_a_trigger(self):
        for t in ("مضمو\u200fن", "\u2067مضمون\u2069", "\ufefb يوجد مثيل", "مضمون\u0651", "\ufeffEGP 500"):
            self.assertIn("business", domains(t), repr(t))

    def test_spelling_variants_match(self):
        for t in ("النتيجه مضمونه", "اخر فرصه", "آخر فرصة", "إخر فرصة", "الاول فى مصر"):    # ه for ة, bare alef, ى
            self.assertIn("business", domains(t), t)

    def test_matches_report_rule_and_words(self):
        hit = RD.detect("نتيجة مضمونة ١٠٠٪ بس بـ ٩٩ جنيه")["business"]
        rules = [m["rule"] for m in hit]
        self.assertEqual(rules, sorted(set(rules), key=rules.index))      # one row per rule+words, no repeats
        self.assertIn("guarantee-word", rules)
        self.assertIn("guarantee-hundred", rules)
        self.assertIn("only-for-price", rules)
        self.assertTrue(all(set(m) == {"rule", "match"} and m["match"] for m in hit), hit)

    def test_detect_is_deterministic_and_order_independent(self):
        t = "الـ AI هيضاعف أرباحك ١٠٠٪ بس بـ ٩٩ جنيه ﴿قل هو الله أحد﴾ dose 5 mg"
        first = json.dumps(RD.detect(t), ensure_ascii=False, sort_keys=True)
        self.assertEqual(json.dumps(RD.detect(t), ensure_ascii=False, sort_keys=True), first)
        lex = RD.lexicon("business")
        shuffled = {**lex, "rules": list(reversed([dict(r, terms=list(reversed(r["terms"]))) if "terms" in r else r
                                                    for r in lex["rules"]]))}
        with mock.patch.object(RD, "lexicon", side_effect=lambda d: shuffled if d == "business" else lex_of(d)):
            self.assertEqual(json.dumps(RD.detect(t), ensure_ascii=False, sort_keys=True), first)


_REAL_LEXICON = RD.lexicon


def lex_of(d):
    return _REAL_LEXICON(d)


# ---------------------------------------------------------------- per-line scan of a plan
class TestScan(Base):
    PROFILE = {"domain": "medical"}

    def setUp(self):
        super().setUp()
        self.put(event("G1", 1000, 3000, evidence="الملح الكتير بيرفع الضغط", text="الملح الكتير بيرفع الضغط"),
                 event("G2", 3000, 6000, evidence="والكشف عندنا بـ ٥٠٠ جنيه بس", text="الكشف في العيادة"),
                 event("G3", 6000, 7000, text="Take 500 mg daily"),
                 dict(event("G4", 7000, 7200), template="flash_transition"))

    def test_doctor_clip_that_mentions_a_price_needs_business_on_that_line_only(self):
        s = RD.scan(self.p)
        self.assertEqual(s["key"], "ai+medical")
        self.assertEqual([x["event_id"] for x in s["lines"]], ["G1", "G2", "G3"])     # no-text G4 is not a line
        g2 = self.line(s, "G2")
        self.assertEqual(g2["required"], ["ai", "business", "medical"])
        self.assertEqual(g2["extra"], ["business"])
        self.assertTrue(all(m["in"] == "speech" for m in g2["detected"]["business"]), g2)
        for eid in ("G1", "G3"):
            self.assertEqual(self.line(s, eid)["required"], ["ai", "medical"], eid)
        self.assertEqual(self.line(s, "G3")["detected"]["medical"][0]["in"], "screen")

    def test_detected_domain_never_enters_the_key_and_one_price_word_changes_one_line(self):
        before = RD.scan(self.p)
        self.put(event("G1", 1000, 3000, evidence="الملح الكتير بيرفع الضغط", text="الملح الكتير بيرفع الضغط"),
                 event("G2", 3000, 6000, evidence="والكشف عندنا", text="الكشف في العيادة"),
                 event("G3", 6000, 7000, text="Take 500 mg daily — only $5"))
        after = RD.scan(self.p)
        self.assertEqual((before["key"], before["client_set"]), (after["key"], after["client_set"]))
        self.assertEqual(self.line(after, "G2")["required"], ["ai", "medical"])
        self.assertEqual(self.line(after, "G3")["required"], ["ai", "business", "medical"])
        self.assertEqual(self.line(after, "G1"), self.line(before, "G1"))

    def test_review_detect_modes(self):
        self.profile({"domain": "medical", "review_detect": "suggest"})
        g2 = self.line(RD.scan(self.p), "G2")
        self.assertEqual((g2["required"], g2["suggested"]), (["ai", "medical"], ["business"]))
        self.profile({"domain": "medical", "review_detect": "off"})
        s = RD.scan(self.p)
        self.assertEqual(s["review_detect"], "off")
        for x in s["lines"]:
            self.assertEqual((x["detected"], x["extra"], x["suggested"], x["required"]), ({}, [], [], ["ai", "medical"]))
        self.profile({"domain": "medical", "review_detect": "review"})
        self.assertEqual(self.line(RD.scan(self.p), "G2")["suggested"], [])

    def test_required_flags_helper(self):
        self.assertEqual(RD.required_flags(self.p), {"G1": ["ai", "medical"], "G2": ["ai", "business", "medical"],
                                                     "G3": ["ai", "medical"]})
        self.assertEqual(RD.review_domains_detected(self.p)["G2"], ["business"])

    def test_composite_client_has_no_extra_for_its_own_domain(self):
        self.profile({"review_domains": ["business", "medical"]})
        s = RD.scan(self.p)
        self.assertEqual(s["key"], "ai+business+medical")
        g2 = self.line(s, "G2")
        self.assertEqual((g2["extra"], g2["required"]), ([], ["ai", "business", "medical"]))
        self.assertIn("business", g2["detected"])                     # still shown as a hint

    def test_general_client_health_claim_is_still_medical(self):
        self.profile({"domain": "general"})
        g3 = self.line(RD.scan(self.p), "G3")
        self.assertIn("medical", g3["required"])
        self.assertIn("medical", g3["detected"])

    def test_scan_is_deterministic_and_read_only(self):
        before = tree_digest(self.root)
        a = json.dumps(RD.scan(self.p), ensure_ascii=False, sort_keys=True)
        b = json.dumps(RD.scan(self.p), ensure_ascii=False, sort_keys=True)
        self.assertEqual(a, b)
        self.assertEqual(tree_digest(self.root), before)

    def test_scan_shape(self):
        s = RD.scan(self.p)
        self.assertEqual(set(s), {"schema", "plan_kind", "plan_fingerprint", "key", "client_set", "review_detect",
                                  "lines_total", "lines", "ai_assets", "note"})
        self.assertEqual((s["schema"], s["plan_kind"], s["lines_total"]), (1, "timeline", 3))
        g2 = self.line(s, "G2")
        self.assertEqual(set(g2), {"event_id", "text", "evidence", "start_s", "end_s", "detected", "extra",
                                   "required", "suggested"})
        self.assertEqual((g2["start_s"], g2["end_s"], g2["evidence"]), (3.0, 6.0, "والكشف عندنا بـ ٥٠٠ جنيه بس"))

    def test_verse_recited_in_speech_is_not_business(self):
        self.profile({"domain": "religious"})
        self.put(event("G1", 0, 3000, evidence="فما ربحت تجارتهم", text="﴿فَمَا رَبِحَت تِّجَارَتُهُمْ﴾ — البقرة: ١٦"))
        g1 = self.line(RD.scan(self.p), "G1")
        self.assertNotIn("business", g1["detected"])
        self.assertEqual(g1["required"], ["ai", "medical", "religious"])

    def test_a_short_evidence_that_is_all_verse_is_hidden(self):
        self.profile({"domain": "religious"})
        self.put(event("G1", 0, 3000, evidence="ربحت تجارتهم", text="﴿فَمَا رَبِحَت تِّجَارَتُهُمْ﴾"))
        self.assertNotIn("business", self.line(RD.scan(self.p), "G1")["detected"])

    def test_only_the_recited_stretch_of_speech_is_hidden(self):
        self.profile({"domain": "religious"})
        self.put(event("G1", 0, 3000, evidence="الشركة ربحت كتير السنة دي، فما ربحت تجارتهم",
                       text="﴿فَمَا رَبِحَت تِّجَارَتُهُمْ﴾"))
        g1 = self.line(RD.scan(self.p), "G1")
        self.assertEqual([m["match"] for m in g1["detected"]["business"]], ["ربحت"])
        self.assertEqual(g1["detected"]["business"][0]["in"], "speech")
        self.assertIn("business", g1["required"])

    def test_lexicon_update_that_drops_a_detection(self):
        before = RD.scan(self.p)
        lex = RD.lexicon("business")
        thin = {**lex, "rules": [r for r in lex["rules"] if r["id"] not in ("currency-amount", "only-for-price",
                                                                           "pricing")]}
        with mock.patch.object(RD, "lexicon", side_effect=lambda d: thin if d == "business" else lex_of(d)):
            after = RD.scan(self.p)
        self.assertEqual(after["key"], before["key"])
        self.assertEqual(self.line(after, "G2")["required"], ["ai", "medical"])
        self.assertEqual(self.line(before, "G2")["required"], ["ai", "business", "medical"])

    def test_ai_generated_asset(self):
        write_json(self.p.client_db / "asset-manifest.json", {"assets": [
            {"rel": "data/Broll/gen.png", "ai_generated": True}, {"rel": "data/Broll/real.png"}]})
        self.put(event("G1", 0, 1000, text="الملح", image="data/Broll/gen.png"),
                 event("G2", 1000, 2000, image="data/Broll/real.png", text="الضغط"),
                 dict(event("G3", 2000, 3000, video="data/Broll/gen.png"), template="broll_video"))
        s = RD.scan(self.p)
        self.assertEqual(s["ai_assets"], [{"event_id": "G1", "file": "data/Broll/gen.png", "line": True},
                                          {"event_id": "G3", "file": "data/Broll/gen.png", "line": False}])
        self.assertEqual(self.line(s, "G1")["detected"]["ai"], [{"rule": "ai-generated-asset",
                                                                "match": "data/Broll/gen.png", "in": "asset"}])
        self.assertNotIn("ai", self.line(s, "G2")["detected"])
        self.profile({"domain": "medical", "review_detect": "off"})
        s = RD.scan(self.p)
        self.assertEqual(self.line(s, "G1")["detected"], {})                  # off: no detection at all
        self.assertEqual(len(s["ai_assets"]), 2)                              # the manifest record is still listed

    def test_no_plan_is_refused_and_nothing_written(self):
        self.p.p("01_analysis/timeline-spec.json").unlink()
        before = tree_digest(self.root)
        with self.assertRaises(Guidance) as cm:
            RD.scan(self.p)
        self.assertIn("reel review-scan", cm.exception.how)
        self.assertEqual(tree_digest(self.root), before)

    def test_unknown_profile_domain_refuses_the_scan(self):
        self.profile({"review_domains": ["crypto"]})
        with self.assertRaises(Guidance) as cm:
            RD.scan(self.p)
        self.assertIn("crypto", str(cm.exception))


class TestMotionScan(Base):
    PROFILE = {}

    def test_motion_scenes_are_scanned(self):
        from lib import motion_plan
        write_json(self.p.p("00_inputs/source.json"), {"kind": "motion_reel", "language": "ar"})
        doc = {"reel_id": VID, "fps": 24, "duration_frames": 240, "scenes": [
            {"id": "S1", "type": "title", "start_frame": 0, "end_frame": 48,
             "elements": [{"kind": "text", "text": "الكورس بـ ٩٩ جنيه بس"}]},
            {"id": "S2", "type": "title", "start_frame": 48, "end_frame": 96,
             "elements": [{"kind": "icon", "icon": "heart"}]}],
            "fingerprint": motion_plan.fingerprint(self.p)}
        write_json(self.p.p("01_analysis/motion-plan.json"), doc)
        s = RD.scan(self.p)
        self.assertEqual(s["plan_kind"], "motion")
        self.assertEqual([x["event_id"] for x in s["lines"]], ["S1"])
        s1 = s["lines"][0]
        self.assertEqual((s1["evidence"], s1["required"]), (None, ["ai", "business", "medical"]))

    def test_motion_scene_ai_image(self):
        from lib import motion_plan
        write_json(self.p.p("00_inputs/source.json"), {"kind": "motion_reel", "language": "ar"})
        write_json(self.p.client_db / "asset-manifest.json", {"assets": [
            {"rel": "data/Broll/gen.png", "ai_generated": True}, {"rel": "data/Broll/real.png"}]})
        img = lambda f: {"kind": "image", "name": "x", "path": str(self.root / f)}   # noqa: E731
        doc = {"reel_id": VID, "fps": 24, "duration_frames": 240, "scenes": [
            {"id": "S1", "type": "title", "start_frame": 0, "end_frame": 48,
             "elements": [{"kind": "text", "text": "الضغط"}, img("data/Broll/gen.png")]},
            {"id": "S2", "type": "title", "start_frame": 48, "end_frame": 96, "elements": [img("data/Broll/gen.png")]},
            {"id": "S3", "type": "title", "start_frame": 96, "end_frame": 120, "elements": [img("data/Broll/real.png")]}],
            "fingerprint": motion_plan.fingerprint(self.p)}
        write_json(self.p.p("01_analysis/motion-plan.json"), doc)
        s = RD.scan(self.p)
        self.assertEqual([(a["event_id"], a["line"]) for a in s["ai_assets"]], [("S1", True), ("S2", False)])
        self.assertEqual(s["lines"][0]["detected"]["ai"][0]["in"], "asset")


# ---------------------------------------------------------------- registry structure and extensibility
class TestStructure(unittest.TestCase):
    # Items later tasks add: the business/ai checker guidance (M1-T3) and every eval case (M1-T5). When one lands,
    # this test fails until it is removed from the list (a ratchet, never a silent skip).
    PENDING = {("business", "reference"), ("ai", "reference"),
               ("medical", "eval"), ("religious", "eval"), ("business", "eval"), ("ai", "eval")}

    def test_shipped_registry(self):
        reg = RD.registry()
        self.assertEqual(sorted(reg), list(SHIPPED))
        self.assertEqual(sorted(d for d, e in reg.items() if e["always_on"]), ["ai", "medical"])
        self.assertEqual(reg["medical"]["verdicts"], ["ok", "reword-to-match", "needs-doctor-approval", "remove"])
        for d, e in reg.items():
            self.assertIn("ok", e["verdicts"], d)
            self.assertTrue(e["label"]["ar"] and e["label"]["en"] and e["approver"]["ar"] and e["approver"]["en"], d)

    def test_shipped_lexicons_parse_and_record_their_licence(self):
        for d in SHIPPED:
            lex = RD.lexicon(d)
            self.assertEqual(lex["domain"], d)
            self.assertIn("GPL-3.0-or-later", lex["licence"])
            self.assertIn("no third-party word list", lex["provenance"])
            self.assertTrue(lex["rules"], d)

    def test_shipped_structure_problems_are_exactly_the_pending_ones(self):
        got = {(p["domain"], p["missing"]) for p in RD.structure_problems()}
        self.assertEqual(got, self.PENDING)

    def test_missing_reference_lexicon_or_eval_is_named(self):
        base = Path(tempfile.mkdtemp(prefix="m1t1s_"))
        self.addCleanup(shutil.rmtree, base, True)
        shutil.copytree(FIXTURES / "fifth", base / "fifth")
        f = base / "fifth"
        with mock.patch.multiple(RD, REGISTRY_DIR=f / "registry", REFERENCES_DIR=f / "references",
                                 EVALS_DIR=f / "evals"):
            self.assertEqual(RD.structure_problems(), [])
            for rel, missing in (("references/legal-claims.md", "reference"), ("registry/lexicons/legal.json", "lexicon"),
                                 ("evals/review-legal-basic/case.yaml", "eval")):
                (f / rel).rename(f / (rel + ".off"))
                probs = RD.structure_problems()
                self.assertEqual([(p["domain"], p["missing"]) for p in probs], [("legal", missing)], rel)
                self.assertIn(Path(rel).name, probs[0]["path"], rel)
                (f / (rel + ".off")).rename(f / rel)
            case = f / "evals/review-legal-basic/case.yaml"           # a case.yaml not named after its folder
            case.write_text("name: something-else\n", encoding="utf-8")
            self.assertEqual([(p["domain"], p["missing"]) for p in RD.structure_problems()], [("legal", "eval")])

    def test_fifth_domain_needs_no_code_change(self):
        f = FIXTURES / "fifth"
        with mock.patch.multiple(RD, REGISTRY_DIR=f / "registry", REFERENCES_DIR=f / "references",
                                 EVALS_DIR=f / "evals"):
            self.assertIn("legal", RD.registry())
            self.assertEqual(RD.review_domain_key(["legal", "medical", "ai"]), "ai+legal+medical")
            self.assertIn("legal", domains("العقد ده ملزم قانونيا"))
            self.assertIn("legal", domains("this contract is legally binding"))
            self.assertNotIn("legal", domains("الملح الكتير بيرفع الضغط"))

    def test_bad_registry_refused(self):
        good = json.loads((RD.REGISTRY_DIR / "registry.json").read_text(encoding="utf-8"))
        med = good["domains"]["medical"]
        base = {"medical": med, "ai": good["domains"]["ai"]}
        bads = {"plus in id": {**base, "a+b": med}, "upper id": {**base, "Legal": med},
                "no lexicon": {**base, "x": {k: v for k, v in med.items() if k != "lexicon"}},
                "always_on text": {**base, "x": dict(med, always_on="yes")},
                "no ok verdict": {**base, "x": dict(med, verdicts=["remove"])},
                "medical switched off": {"medical": dict(med, always_on=False), "ai": good["domains"]["ai"]},
                "ai switched off": {"medical": med, "ai": dict(good["domains"]["ai"], always_on=False)},
                "no ai": {"medical": med}, "no medical": {"ai": good["domains"]["ai"]},
                "medical without needs-doctor-approval": {"medical": dict(med, verdicts=["ok", "remove"]),
                                                          "ai": good["domains"]["ai"]},
                "drive-relative lexicon": {"medical": dict(med, lexicon="C:evil.json"), "ai": good["domains"]["ai"]},
                "rooted lexicon": {"medical": dict(med, lexicon="\\evil.json"), "ai": good["domains"]["ai"]},
                "posix-absolute lexicon": {"medical": dict(med, lexicon="/etc/evil.json"), "ai": good["domains"]["ai"]},
                "empty": {}}
        for name, doms in bads.items():
            d = Path(tempfile.mkdtemp(prefix="m1t1r_"))
            self.addCleanup(shutil.rmtree, d, True)
            (d / "registry.json").write_text(json.dumps({"schema": 1, "domains": doms}), encoding="utf-8")
            with mock.patch.object(RD, "REGISTRY_DIR", d), self.assertRaises(Guidance, msg=name):
                RD.registry()
        d = Path(tempfile.mkdtemp(prefix="m1t1r_"))
        self.addCleanup(shutil.rmtree, d, True)
        (d / "registry.json").write_text(json.dumps({"schema": 2, "domains": good["domains"]}), encoding="utf-8")
        with mock.patch.object(RD, "REGISTRY_DIR", d), self.assertRaises(Guidance):
            RD.registry()


if __name__ == "__main__":
    unittest.main()
