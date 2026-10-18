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

    def test_key_without_the_always_on_domains_is_refused(self):
        """Review 79c5bf7 P3: a raw profile list must never silently drop medical or ai from the key."""
        for ids, missing in ((["religious"], ("ai", "medical")), (["business", "ai"], ("medical",)),
                             (["medical"], ("ai",))):
            with self.assertRaises(Guidance, msg=repr(ids)) as cm:
                RD.review_domain_key(ids)
            for d in missing:
                self.assertIn(d, str(cm.exception), ids)


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

    def test_unknown_legacy_domain_refused_naming_it(self):
        """Review 79c5bf7 P3: an unknown legacy `domain` was silently general."""
        for bad, name in (({"domain": "dental"}, "dental"), ({"domain": ["religious"]}, "religious"),
                          ({"domain": 3}, "3"), ({"review_domains": ["business"], "domain": "Dentistry"}, "Dentistry"),
                          ({"domain": "business"}, "business"), ({"domain": "ai"}, "'ai'")):
            self.profile(bad)
            with self.assertRaises(Guidance, msg=repr(bad)) as cm:
                RD.client_set()
            self.assertIn(name, str(cm.exception), bad)
        for ok, key in (({"domain": ""}, "ai+medical"), ({"domain": "  "}, "ai+medical"),
                        ({"domain": "medical | religious | general"}, "ai+medical"),     # the shipped template
                        ({"domain": " Medical  |  Religious | general "}, "ai+medical"),
                        ({"domain": "Religious"}, "ai+medical+religious")):
            self.assertEqual(self.key(ok), key, ok)

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

    def test_quoted_scripture_after_a_citation_hides_nothing(self):
        """Executor follow-up (review 79c5bf7 P2-1): only a ﴿﴾ verse hides plain business words; a «» or “” quotation
        after a citation still counts as religious but hides nothing («ربنا قال» is everyday speech)."""
        for t in ("قال تعالى: «فما ربحت تجارتهم»", "قال تعالى في كتابه «فما ربحت تجارتهم»",
                  "قال رسول الله ﷺ «التاجر الصدوق الأمين مع النبيين» ربح", "قال تعالى “فما ربحت تجارتهم”"):
            hit = RD.detect(t)
            self.assertIn("religious", hit, t)
            self.assertTrue([m for m in hit.get("business", []) if "ربح" in m["match"]], (t, hit))
        for t in ("قال تعالى «الكورس بـ ٥٠٠ جنيه ونتيجة مضمونة ١٠٠٪»", "ربنا قال «اللي يشترك معانا هيكسب ٢٠ ألف في الشهر»",
                  "قال الله تعالى في كتابه «فما ربحت تجارتهم بـ ٥٠٠ جنيه»"):
            hit = RD.detect(t)
            self.assertIn("religious", hit, t)
            self.assertIn("business", hit, t)
        rules = {m["rule"] for m in RD.detect("قال تعالى «الكورس بـ ٥٠٠ جنيه ونتيجة مضمونة ١٠٠٪»")["business"]}
        self.assertTrue({"currency-amount", "guarantee-hundred", "guarantee-word"} <= rules, rules)

    def test_amounts_are_never_hidden_inside_a_verse(self):
        for t in ("﴿ الجلسة بـ ٥٠٠ جنيه ﴾", "﴿ نتيجة ١٠٠٪ ﴾", "﴿ بس بـ ٩٩ ﴾", "﴿ خمسين جنيه ﴾", "﴿ هتكسب عشرين ألف ﴾",
                  "﴿ #1 ﴾", "﴿ $99 ﴾"):
            hit = RD.detect(t)
            self.assertIn("religious", hit, t)
            self.assertIn("business", hit, t)

    def test_zone_hiding_is_data_with_a_code_floor(self):
        """A pattern rule hides inside ﴿﴾ only when the lexicon says `zone_hideable: true`; a hit holding a digit, % or
        a currency sign is never hidden, whatever the lexicon says."""
        lex = RD.lexicon("business")
        loose = {**lex, "rules": [dict(r, zone_hideable=True) for r in lex["rules"]]}
        strict = {**lex, "rules": [{k: v for k, v in r.items() if k != "zone_hideable"} for r in lex["rules"]]}
        with mock.patch.object(RD, "lexicon", side_effect=lambda d: loose if d == "business" else lex_of(d)):
            self.assertIn("business", domains("﴿ الجلسة بـ ٥٠٠ جنيه ﴾"))
            self.assertIn("business", domains("﴿ نتيجة ١٠٠٪ ﴾"))
            self.assertNotIn("business", domains("﴿ بثمن بخس ﴾"))
        with mock.patch.object(RD, "lexicon", side_effect=lambda d: strict if d == "business" else lex_of(d)):
            self.assertIn("business", domains("﴿ بثمن بخس ﴾"))                   # price-word pattern: shown
        self.assertNotIn("business", domains("﴿وَشَرَوْهُ بِثَمَنٍ بَخْسٍ دَرَاهِمَ مَعْدُودَةٍ﴾"))    # shipped: hidden word

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


class TestRecallFollowUp(unittest.TestCase):
    """Executor follow-up to review 79c5bf7 (P2-2…P2-6, P3): missing a claim is worse than a false alarm, but normal
    speech is not over-flagged."""

    def assert_hits(self, domain: str, texts):
        for t in texts:
            self.assertIn(domain, domains(t), (t, RD.detect(t)))

    def assert_clean(self, domain: str, texts):
        for t in texts:
            self.assertNotIn(domain, domains(t), (t, RD.detect(t)))

    def test_percent_sign_before_the_number(self):
        self.assert_hits("business", ("نتيجة ٪١٠٠", "٪100 results", "نتيجة %100", "عرض ٥٠٪", "عرض ٪٥٠", "خصم ٪٣٠"))
        rules = {m["rule"] for m in RD.detect("نتيجة ٪١٠٠")["business"]}
        self.assertIn("guarantee-hundred", rules)
        self.assertIn("ai-accuracy-number", {m["rule"] for m in RD.detect("الـ AI دقته ٪٩٥")["ai"]})
        self.assert_clean("business", ("٪٥٠ من المرضى بيتحسنوا", "٥٠٪ من المرضى بيتحسنوا"))

    def test_zero_width_characters_are_stripped(self):
        for t in ("مض\u200bمون", "مض\u2060مون", "ض\u200bمان", "مضم\u2061ون", "مض\u034fمون", "مض\u180eمون",
                  "ب\u200bكام"):
            self.assertIn("business", domains(t), repr(t))
        self.assertEqual(RD.normalize("مض\u200bمون"), "مضمون")
        self.assertEqual(RD.normalize("a\u2060b"), "ab")
        self.assertIn("ai", domains("AI" + chr(0x200b) + "tools"))           # the space reading is still tried

    def test_english_currency_words(self):
        self.assert_hits("business", ("only 99 pounds", "99 dollars", "just 20 bucks", "500 Egyptian pounds",
                                      "costs 1,500 pounds", "100 euros", "50 riyals"))
        self.assert_clean("business", ("lose 10 pounds", "I lost 5 pounds in a month", "gained 3 pounds",
                                       "weighs 150 pounds", "10 pounds of fat", "shed 4 pounds fast"))

    def test_offers_and_refunds(self):
        self.assert_hits("business", ("50% off", "%50 off", "٥٠٪ اوف", "special offer", "a special offer today",
                                      "full refund", "refundable", "refunds within 30 days", "فلوسك راجعة",
                                      "استرداد الفلوس"))
        self.assert_clean("business", ("we offer care", "50% of patients", "turn it off", "١٠ ٪ من الحالات"))

    def test_amounts_after_a_price_noun(self):
        self.assert_hits("business", ("الكشف ٣٠٠ ألف", "الكورس ٥٠٠", "الجلسة بـ٢٠٠", "الكشف ب ٣٠٠",
                                      "الاشتراك ٢٠٠٠.", "الكورس كله ١٥٠٠", "العملية ٥٠ ألف", "الباقة بخمسمية"))
        self.assert_clean("business", ("الكشف ٥ دقايق", "الجلسة ٤٥ دقيقة", "٣٠٠ ألف مريض في مصر",
                                       "العملية بتاخد ٣ ساعات", "الكشف ٣ مرات في السنة"))

    def test_amounts_after_bi(self):
        self.assert_hits("business", ("بخمسمية", "بميتين", "بعشرين ألف", "بألفين", "بخمس تلاف", "بتلات آلاف",
                                      "بخمسميت جنيه", "بمية وخمسين"))
        self.assert_clean("business", ("بألف سلامة", "اغسل وشك بمية ساقعة", "بخمس دقايق", "بعشرين سنة",
                                       "بالف هنا", "بمية مقطرة"))

    def test_spelled_out_numbers(self):
        self.assert_hits("business", ("هتكسب عشرين ألف في الشهر", "خمسين جنيه", "ألف جنيه بس", "تلاتين ألف دولار",
                                      "هتقبض خمس تلاف", "مية وخمسين جنيه", "ميتين ريال"))
        self.assert_clean("business", ("عنده خمسين سنة", "خمسين ألف سنة", "عشرين ألف خطوة في اليوم",
                                       "ألف سلامة عليك", "خمسين ألف مريض"))

    def test_guarantee_before_al(self):
        self.assert_hits("business", ("مضمون النتيجة", "مضمونة النتايج", "مضمون الربح", "النتيجة مضمونة"))
        self.assert_clean("business", ("مضمون الفيديو", "مضمون الرسالة", "مضمون الكلام ده"))

    def test_rank_and_comparison(self):
        self.assert_hits("business", ("number 1", "Number 1 in Egypt", "نمبر 1", "نمبر ون", "نمبر ١ في مصر",
                                      "cheaper than", "cheaper than any clinic", "the lowest price"))
        self.assert_clean("business", ("room number 12", "نمبر 15 في الطابور"))

    def test_common_unbracketed_verses(self):
        self.assert_hits("religious", ("إن الله مع الصابرين", "واصبروا إن الله مع الصابرين", "إن مع العسر يسرا",
                                       "فإن مع العسر يسرا", "ألا بذكر الله تطمئن القلوب", "لا يكلف الله نفسا إلا وسعها",
                                       "إنا لله وإنا إليه راجعون", "حسبنا الله ونعم الوكيل",
                                       "ومن يتق الله يجعل له مخرجا", "وقل رب زدني علما", "الحمد لله رب العالمين",
                                       "بسم الله الرحمن الرحيم", "إِنَّ اللَّهَ مَعَ الصَّابِرِينَ"))
        self.assert_clean("religious", ("الحمد لله", "إن شاء الله", "بسم الله", "ربنا يسهل", "الحمد لله على كل حال"))
        hit = RD.detect("إن الله مع الصابرين والكورس بـ ٥٠٠ جنيه")                 # no zone: hides nothing
        self.assertIn("business", hit)
        self.assertIn("religious", hit)

    def test_medical_egyptian_and_ai_spellings(self):
        self.assert_hits("medical", ("الدكتور كتبلي الدوا ده", "خد الدوا بعد الأكل"))
        self.assert_hits("ai", ("gpt-4 قال كده", "GenAI tools", "ai diagnoses cancer", "Ai tools", "ai-generated image",
                                "AI-powered app"))
        self.assert_clean("ai", ("aI", "Aida came", "AIDS awareness", "he said it", "ai", "the ai of the story"))

    # ---- fix round 1 (fresh review of this follow-up)
    def test_price_after_a_price_noun_whatever_follows(self):
        self.assert_hits("business", ("الكشف ٣٠٠ بس", "(الكشف ٣٠٠)", "الكشف ٣٠٠ 🔥", "الكشف هيكون ٣٠٠ بدل ٥٠٠",
                                      "الاشتراك ٢٠٠ شهري", "الكشف النهارده بقى ٢٠٠ بس", "﴿ الجلسة بـ ٥٠٠ ﴾",
                                      "قال الله “الكشف ٣٠٠”", "بـ٩٩ بس", "بـ٩٩ فقط", "الكشف ب٥٠"))
        self.assert_clean("business", ("الجلسة ٤٥", "عدد الجلسات ٦", "عدد الجلسات ست", "الكورس مدته سبعة",
                                       "الدورة الشهرية ٢٨", "المتابعة بعد اتنين", "الحجز رقم ٥", "الكشف بتاعك يوم ١٥",
                                       "العملية نجحت في عشرين ألف حالة", "عملنا العملية لأكتر من عشرين ألف مريض",
                                       "العملية ٢٠ ألف حالة", "بميتين مل", "خد بميتين ملي مية"))

    def test_a_verse_holding_a_number_hides_nothing(self):
        for t in ("﴿ السعر ٩٩ ﴾", "﴿ ارباح ٥٠ الف ﴾", "﴿ اربح ٥٠٠٠ ﴾", "﴿ عائد شهري ٢٠٪ ﴾", "﴿ ربح ٢٠٪ ﴾",
                  "﴿ خصم ٣٠ ﴾", "﴿ مية في المية ﴾", "﴿ مئة بالمئة ﴾", "﴿ نمبر ون ﴾", "﴿ رقم واحد في مصر ﴾",
                  "﴿ number one ﴾"):
            hit = RD.detect(t)
            self.assertIn("religious", hit, t)
            self.assertIn("business", hit, t)

    def test_hundred_percent_spellings(self):
        self.assert_hits("business", ("نسبة النجاح ١٠٠ بالمئة", "١٠٠ في المئة", "١٠٠٫٠٪", "100.0%", "مئة في المئة"))

    def test_doctor_speech_is_not_earnings(self):
        self.assert_clean("business", ("مضاعفات السكر دخلت على الكلى", "مضاعفات السكر بتصيب ٣ مليون مصري",
                                       "مضاعفات العملية بتحصل في خمس آلاف حالة", "المريض دخل المستشفى",
                                       "الضغط بيضاعف الخطر"))
        self.assert_hits("business", ("هيضاعف دخلك", "هتكسب ٢٠ ألف", "بيكسب مليون", "اكسب خمس تلاف"))

    def test_quran_app_spelling(self):
        self.assert_hits("religious", ("ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَٰلَمِينَ", "إِنَّ ٱللَّهَ مَعَ ٱلصَّٰبِرِينَ",
                                       "إِنَّا لِلَّٰهِ وَإِنَّآ إِلَيْهِ رَٰجِعُونَ",
                                       "ٱللَّهُ لَآ إِلَٰهَ إِلَّا هُوَ ٱلْحَىُّ ٱلْقَيُّومُ"))

    def test_split_readings_add_no_partial_rows(self):
        zw, wj = chr(0x200b), chr(0x2060)
        for t, want in (("٥" + zw + "٠٠ جنيه", "500 جنيه"), ("5" + zw + "0% off", "50% off"),
                        ("٥٠٠ ج" + wj + "نيه", "500 جنيه")):
            rows = RD.detect(t)["business"]
            matches = [m["match"] for m in rows if m["rule"] in ("currency-amount", "percent-off")]
            self.assertIn(want, matches, t)
            self.assertFalse([m for m in matches if m != want and m in want], (t, matches))

    def test_more_invisible_characters(self):
        for ch in (0xfe0f, 0xfe00, 0xe0020, 0x3164, 0x115f, 0x17b4, 0xffa0):
            for t in ("ض" + chr(ch) + "مان", "مض" + chr(ch) + "مون"):
                self.assertIn("business", domains(t), hex(ch))
        self.assertIn("currency-amount", {m["rule"] for m in RD.detect("٥٠٠" + chr(0xfe0f) + " جنيه")["business"]})

    def test_pounds_need_a_price_cue(self):
        self.assert_hits("business", ("only 99 pounds", "costs 1,500 pounds", "500 Egyptian pounds", "for 200 pounds",
                                      "100 GBP", "L.E 500", "LE 500", "costs 300", "٥٠٠ ر.س", "٢٠٠ د.إ", "١٠٠ دينار",
                                      "100 dollars", "20 bucks"))
        self.assert_clean("business", ("a 10 pound baby", "the baby was 8 pounds", "weight loss of 20 pounds",
                                       "lost about 20 pounds", "down 20 pounds", "lose 10-20 pounds", "the costs of care",
                                       "he left the clinic"))

    def test_more_claim_forms(self):
        self.assert_hits("business", ("دخلك هيبقى ٥٠ ألف في الشهر", "هتعمل ٥٠ ألف في الشهر", "مرتبك هيبقى عشرين ألف",
                                      "عائد ٢٠٪ شهريا", "الكشف فري", "كاش باك", "cash back", "العرض لحد آخر الشهر",
                                      "نتيجة أكيدة", "30 percent off", "save 30%", "free consultation"))
        self.assert_clean("business", ("عشرين ألف خطوة في اليوم", "دخل الحمام", "الدخل الحراري"))

    # ---- fix round 2
    def test_earnings_with_plain_digits(self):
        self.assert_hits("business", ("هتكسب ٥٠٠٠ في الشهر", "هتكسب ٥٠٬٠٠٠ في الشهر", "هتعمل ٥٠٠٠٠ في الشهر",
                                      "مرتبك هيبقى ٣٠٠٠٠", "دخلك هيبقى ٢٠٠٠٠ شهريا", "make 5000 a month",
                                      "earn $3,000 per month", "هتعمل ٥٠ ألف شهريا", "دخلك هيتضاعف", "فلوسك هتتضاعف"))
        hit = RD.detect("﴿ فما ربحت تجارتهم ﴾ هتكسب ٥٠٠٠ في الشهر")
        self.assertIn("business", hit)
        self.assert_clean("business", ("هتاخد ١٠٠٠ في اليوم", "بتاخد ٢ حباية في اليوم", "خد ٥٠٠ مجم في اليوم",
                                       "هتعمل ١٠٠٠ خطوة في اليوم", "بيكسب ٥٠٠ سعر حراري"))

    def test_phone_numbers_and_years_after_a_price_noun(self):
        self.assert_clean("business", ("الحجز ٠١٠١٢٣٤٥٦٧٨", "الحجز ٠١٠١٢٣٤٥٦٧٨ - ٠١١٢٣٤٥٦٧٨٩", "الحجز ١٩٧٧٧",
                                       "والحجز ١٦٦٧٦", "الكشف ٢٠٢٤", "المتابعة ٢٠٢٤.", "الكشف عندنا ٢٠٢٤",
                                       "الحجز ٢٠٢٤/١٠/٢٠", "الجلسات ١٠٠", "الجلسات عشرين"))
        self.assertEqual([m["rule"] for m in RD.detect("العملية ١٠٠٪ آمنة")["business"]], ["guarantee-hundred"])
        self.assert_hits("business", ("الكشف ١٥٠٠", "الكشف ٢٠٠٠٠ بس", "الحجز ب ٢٠٠", "الجلسات ب ٥٠٠", "الكشف ٢٠٠٠",
                                      "الكشف ٢٥٠٠", "الكشف ١٩٠٠"))      # 2010-2039 and 1950-1999 read as years

    def test_price_noun_forms(self):
        self.assert_hits("business", ("للكشف ٣٠٠ بس", "كشف ٣٠٠ بس", "جلسة الليزر ب ٥٠٠", "باقة ٦ جلسات ب ٢٠٠٠",
                                      "الكشف في العيادة ب ٢٥٠", "الكشف هنا ب ٢٥٠", "الاستشارة اونلاين ب ٢٠٠",
                                      "the session is 500", "consultation is only 300", "the visit costs 400"))
        self.assert_clean("business", ("الدورة الشهرية ب ٢٨ يوم", "الجلسة بتاخد ساعتين ب ٣٠ دقيقة",
                                       "the session is 45 minutes", "consultation lasts 30 minutes"))

    def test_only_for_with_a_unit_is_not_a_price(self):
        self.assert_clean("business", ("بس ب ١٠ دقايق في اليوم", "بس ب ٢ حباية", "بس ب ٢٠ مل", "بس ب ١٠٠ مجم"))
        self.assert_hits("business", ("بس ب ٢٠٠", "بس بـ ٩٩ جنيه"))

    def test_rank_of_a_cause_is_not_a_business_claim(self):
        self.assert_clean("business", ("السبب رقم واحد في الوفيات", "number one cause of death", "رقم ١ في أسباب الوفاة",
                                       "السبب رقم ١ للوفاة", "السبب رقم واحد للجلطات",
                                       "the number 1 risk factor"))
        self.assert_hits("business", ("رقم واحد في مصر", "number one in Egypt", "نمبر وان", "رقم ١ في مصر"))

    def test_match_shows_the_whole_amount(self):
        self.assertIn("costs 300", [m["match"] for m in RD.detect("costs 300")["business"]])

    def test_mongolian_and_musical_invisibles(self):
        for ch in (0x180b, 0x180c, 0x180d, 0x180f, 0x1d173, 0x1d17a):
            self.assertIn("business", domains("ر" + chr(ch) + "بح"), hex(ch))

    # ---- fix round 3
    def test_clinic_numbers_after_a_price_noun_are_not_prices(self):
        self.assert_clean("business", ("نسبة نجاح العملية ب ٩٥٪", "العملية بتنجح ب ٩٠٪ من الحالات", "الكشف ب ١٠:٣٠",
                                       "الكشف الساعة ب ١٠:٣٠", "العيادة بتفتح الساعة ١٠، والكشف ب ١٠:٣٠",
                                       "العملية ب ١٠-١٥ دقيقة", "الدورة ب ٢٨، وده طبيعي", "دورة الطمث ب ٢٨",
                                       "الدورة جت ب ٣٥!", "العملية لمريض ب ٦٥، وكانت ناجحة", "الكشف على مريض ب ٧٠؟",
                                       "المتابعة بعد العملية ب ١٤.", "الحجز قبل الكشف ب ٤٨", "الجرعة في الجلسة ب ١٠",
                                       "كورس العلاج بيكون ب ٢٠", "كورس المضاد الحيوي ب ٥٠٠ مجم",
                                       "the session is 20-30 minutes", "the visit is 2023",
                                       "الضغط في المتابعة ب ١٢٠/٨٠", "العملية ب ١٢٠-١٥٠ دقيقة"))

    def test_strong_price_followed_by_any_word(self):
        self.assert_hits("business", ("الكشف ب ٣٠٠ لحد اخر الشهر", "الكشف ب ٣٠٠ للمريض", "الكشف ب ٣٠٠ في العيادة",
                                      "الكشف ب ٣٠٠ وبس", "الكشف ب ٣٠٠ يا جماعة", "الكشف ب ٣٠٠ مصري",
                                      "الباقة ب ١٥٠٠ ل ٦ جلسات", "عملية الليزك ب ١٥ الف", "عملية التكميم ب ٦٠ الف بس",
                                      "عملية التكميم ٦٠ الف", "العملية كلها على بعضها ب ٦٠ الف", "الكشف ب٥٠",
                                      "احجز ب ٢٠٠", "الفيلر ب ٣٠٠٠", "البوتوكس ب ٢٥٠٠", "الليزر ب ١٠٠٠ للجلسة",
                                      "only 300 for the session", "packages start at 1500", "earn up to 5000 monthly",
                                      "دخلك هيزيد للضعف"))

    def test_gains_doses_and_body_numbers_are_not_earnings(self):
        self.assert_clean("business", ("الطفل بيكسب ٢٠٠ إلى ٣٠٠ جرام في الأسبوع", "الطفل بيكسب ١٥٠-٢٠٠ جرام في الاسبوع",
                                       "الطفل كسب ٨٠٠", "ضاعف الجرعة ل ٤٠٠", "هنضاعف الجرعة ل ١٠٠٠ وحدة",
                                       "ضاعفنا الجرعة لـ ٢٠٠٠", "ضاعف المجهود ٢٠٠٪", "قبض الرحم بيبدأ بعد ٢٠٠",
                                       "دخلنا سنة ٢٠٢٠", "دخلنا ٢٠٢٤ وعندنا", "دخلك العيادة ٢٠١٩",
                                       "هتعمل ١٥٠ في الاسبوع رياضة", "الكلى بتعمل ١٨٠ في اليوم",
                                       "الكبد بيعمل ١٠٠٠ في اليوم", "هتعمل ١٠٠ في اليوم"))

    def test_rank_needs_a_place(self):
        self.assert_clean("business", ("الخطوة رقم ١", "المريض رقم ١", "عامل الخطر رقم ١", "القاتل رقم ١",
                                       "السبب رقم ١ في الجلطات", "السبب رقم واحد في الجلطات"))
        self.assert_hits("business", ("رقم ١ في مصر", "احنا رقم ١", "إحنا رقم واحد", "#1 in Egypt"))

    def test_only_for_with_more_units(self):
        self.assert_clean("business", ("بس ب ٣ شهور", "بس ب ١٠ ثواني", "بس ب ٢ ملعقة", "بس ب ٣ كوبايات", "بس ب ٥ غرز",
                                       "بس ب ٢ فتحة", "بس ب ١٠٠٠ وحدة", "بس ب ٢٪"))

    def test_lexicon_flags_are_type_checked(self):
        lex = RD.lexicon("business")
        bad_rule = {**lex, "rules": [dict(lex["rules"][0], zone_hideable="false")] + lex["rules"][1:]}
        rel = RD.lexicon("religious")
        bad_zone = {**rel, "zones": [dict(rel["zones"][0], hides="false")] + rel["zones"][1:]}
        for name, doc in (("business", bad_rule), ("religious", bad_zone)):
            real = RD.read_json
            with mock.patch.object(RD, "read_json",
                                   side_effect=lambda f, *a, d=doc, r=real: d if f.parent.name == "lexicons" else r(f, *a)):
                with self.assertRaises(Guidance, msg=name) as cm:
                    RD.lexicon(name)
                self.assertIn("false", str(cm.exception))
    # ---- review e4d68dc (round 2)
    def test_only_a_closed_verse_hides_a_plain_word(self):
        """P2-1: word-only cases (no digit, no currency) so the digit floor cannot hide the guard."""
        hit = RD.detect("﴿ خصم للمشتركين")                                     # never closed
        self.assertIn("religious", hit)
        self.assertEqual([m["match"] for m in hit["business"]], ["خصم"])
        hit = RD.detect("﴿ خصم ﴿ ربح ﴾")                                       # opened again before it closed
        self.assertEqual([m["match"] for m in hit["business"]], ["خصم"])       # ربح sits in the closed zone
        self.assertNotIn("business", domains("﴿ خصم للمشتركين ﴾"))

    def test_a_year_shaped_price_after_bi_or_a_price_cue(self):
        """P2-2: after «ب» or only/just/costs the number is a price even when it looks like a year."""
        self.assert_hits("business", ("الكورس ب ١٩٩٩", "الباقة ب ٢٠٢٥", "الكشف بـ 1999", "the package is only 1999",
                                      "the course costs 2025", "consultation for only 2020", "the session is just 1999"))
        for t in ("الكورس ب ١٩٩٩", "الباقة ب ٢٠٢٥", "the package is only 1999", "the course costs 2025"):
            self.assertIn(RD.detect(t)["business"][0]["rule"], ("priced-amount", "priced-amount-en"), t)
        self.assert_clean("business", ("الكشف ٢٠٢٤", "the visit is 2023", "the course for 2025", "the package in 2024",
                                       "the session is 1999"))
        for t in ("احجز ب 01001234567", "الحجز ب ٠١٠١٢٣٤٥٦٧٨", "الكشف ب ٠٥٠٠"):   # a leading 0 is a phone, not a price
            self.assertNotIn("priced-amount", [m["rule"] for m in RD.detect(t).get("business", [])], t)

    def test_egyptian_clinic_fee_and_guarantee_words(self):
        """P2-3."""
        self.assert_hits("business", ("فيزيتا ٣٠٠", "الفيزيتا ب ٣٠٠", "كشفية ٣٠٠", "الفيزيتا ٥٠٠ بس", "والكشفية ب ٤٠٠"))
        for t in ("بنضمنلك النتيجة", "نضمنلك", "هنضمنلك ده", "أضمنلك النتيجة", "بنضمنها"):
            self.assertIn("guarantee", [m["rule"] for m in RD.detect(t).get("business", [])], t)
        self.assert_clean("business", ("الفيزيتا كانت طويلة", "ضمن الخطة العلاج بالأكل", "الفيزيتا ٣٠ دقيقة"))

    def test_a_zone_with_latin_letters_or_any_currency_sign_hides_nothing(self):
        """P3-1, P3-4: the code floor covers %, every currency sign (Unicode Sc) and Latin letters."""
        for t in ("﴿ guaranteed results ﴾", "﴿ خصم ¥ ﴾", "﴿ خصم ₤ ﴾", "﴿ خصم ﷼ ﴾", "﴿ خصم ₺ ﴾", "﴿ خصم % ﴾",
                  "﴿ خصم € ﴾", "﴿ خصم £ ﴾", "﴿ خصم $ ﴾", "﴿ خصم ٪ ﴾", "﴿ خصم EGP ﴾"):
            hit = RD.detect(t)
            self.assertIn("religious", hit, t)
            self.assertIn("business", hit, t)
        self.assertNotIn("business", domains("﴿وَشَرَوْهُ بِثَمَنٍ بَخْسٍ دَرَاهِمَ مَعْدُودَةٍ﴾"))
        self.assertNotIn("business", domains("﴿ وَمِنْهُم مَّنْ إِن تَأْمَنْهُ بِدِينَارٍ لَّا يُؤَدِّهِ إِلَيْكَ ﴾"))
        for t in ("٥٠٠ ﷼", "﷼ ٥٠٠", "¥500", "₤ 300"):
            self.assertIn("currency-amount", [m["rule"] for m in RD.detect(t).get("business", [])], t)

    def test_more_recall_words(self):
        """P3-2."""
        self.assert_hits("business", (
            "three hundred dollars", "five hundred pounds only", "only five hundred pounds", "two thousand euros",
            "fifty bucks", "twenty five dollars", "99 pounds only", "first session free", "the first visit is free",
            "a free session", "ادفع ٥٠٠", "هتدفع ٣٠٠ بس", "قسط ٥٠٠ في الشهر", "القسط ب ٧٠٠", "مقدم ١٠ آلاف", "عربون ٥٠٠",
            "وفر ٢٠٠", "هتوفر ٢٠٠٠", "الشقة بمليون.", "بمليون", "الجهاز بألفين بس", "عرض ١+١", "offer 1+1",
            "buy one get one free", "you can make five thousand a month", "earn two thousand dollars a week"))
        self.assert_clean("business", (
            "lost twenty pounds", "I gained five pounds", "ادفع ٣ مرات", "وفر ١٠ دقايق", "هتوفر ٣٠ دقيقة",
            "الدفعة ٢٠٢٠", "مقدم البرنامج", "خد قسط من الراحة", "بألف خير", "بمليون طريقة", "بالفعل", "١+١=٢",
            "make five friends a month", "five hundred people"))

    def test_wavelengths_and_percent_of_are_not_claims(self):
        """P3-3."""
        self.assert_clean("business", ("الليزر ١٠٦٤", "ليزر ٧٥٥", "the session is 1064 nm", "الليزر ١٠٦٤ نانو",
                                       "I lost 100 percent of my hearing", "100 percent of patients recover"))
        self.assert_hits("business", ("الليزر ب ١٠٠٠", "جلسة الليزر ب ٥٠٠", "100 percent guaranteed", "١٠٠٪",
                                      "results are 100 percent", "الليزر ٣٠٠٠ بس"))

    def test_cashback_spellings(self):
        """P3-5: each spelling on its own."""
        for t in ("cashback", "cash back", "كاش باك"):
            self.assertEqual([m["rule"] for m in RD.detect(t)["business"]], ["pricing"], t)

    def test_hostile_long_lines_stay_fast_and_lose_nothing(self):
        """P3-6: a long line is scanned in overlapping windows (never cut short), so cost stays linear."""
        import time
        for t in ("1" * 50_000, "1 " * 10_000, "١٠٠٪" * 5_000, "ب " * 20_000, "الكشف " * 8_000):
            t0 = time.monotonic()
            RD.detect(t)
            self.assertLess(time.monotonic() - t0, 10.0, t[:12])
        filler = "كلام عادي جدا " * 2_000
        for claim in ("الكشف ب ٥٠٠ جنيه", "نتيجة مضمونة", "AI generated"):
            hit = RD.detect(filler + claim)
            self.assertTrue(hit.get("business") or hit.get("ai"), claim)
        for pad in range(RD.WINDOW - 60, RD.WINDOW + 20, 7):                    # a claim across every window cut
            t = "س" * pad + " الكشف ب ٥٠٠ جنيه " + "ص" * 30
            rules = [m["rule"] for m in RD.detect(t).get("business", [])]
            self.assertEqual(rules.count("currency-amount"), 1, pad)              # seen in two windows, one row
        self.assertEqual(len(RD._windows("كلام " * 1_000)), 6)                    # 5,000 chars: 1,000 a window, 200 shared
        self.assertTrue(all(len(w) <= RD.WINDOW for w in RD._windows("كلام " * 1_000 + "س" * 3_000)))
        short = "الكورس ب ١٥٠٠ جنيه ونتيجة مضمونة ﴿ فما ربحت تجارتهم ﴾"
        self.assertEqual(RD.detect(short), RD.detect(short + " "))

    def test_rial_sign_is_a_sign_and_still_reads_as_rial(self):
        """Self-review r1 P1-1: ﷼ stays a currency sign (the zone floor sees it) and a further reading spells it
        «ريال», so every rule that knew the word still hits."""
        for t in ("خمسين ﷼ بس", "عشرة ﷼", "الكشف ب ﷼", "﷼", "﴿وَشَرَوْهُ بِثَمَنٍ بَخْسٍ دَرَاهِمَ﴾ ﷼", "fifty ﷼"):
            self.assertIn("business", domains(t), t)
        self.assertIn("currency-amount-words", [m["rule"] for m in RD.detect("خمسين ﷼ بس")["business"]])
        self.assertEqual(RD.normalize("٥٠٠ ﷼"), "500 ﷼")

    def test_pay_save_and_instalment_words(self):
        """Self-review r1 P2-1, P2-2: counts of exercise, diet and media are not money; a saving in % is."""
        self.assert_clean("business", ("ادفع ١٥ تكرار", "ادفعي الحيطة ١٠ تكرارات", "ادفع ٢٠ عدة", "ادفع ١٠ ضغطات",
                                       "ادفع ٢٠ نفس", "ادفع ١٠ كجم", "هتوفري ٣٠٠ سعرة حرارية", "وفر ٥٠٠ كالوري في اليوم",
                                       "وفر ٢٠ لتر", "مقدم ٢٠ حلقة", "مقدم ١٠٠ فيديو"))
        self.assert_hits("business", ("وفر ٤٠٪", "هتوفر ٥٠٪", "على ١٢ قسط", "ب ٦ اقساط"))

    def test_more_recall_forms_round_two(self):
        """Self-review r1 P3-3, P3-6."""
        self.assert_hits("business", ("first visit free", "free first visit", "the consultation is free", "2 for 1",
                                      "two for one", "كشفيتي ٣٠٠", "pay only five hundred", "the course is 1999 pounds",
                                      "consultation 500 pounds", "300 pounds for the session", "500 ₪", "500 ₽", "฿500",
                                      "٥٠٠ ر.ق", "٥٠٠ د.ك", "500 SR", "نضمن ان المريض يخف"))
        self.assert_clean("business", ("take 2 for 3 days", "خد ٢ كل ٨ ساعات", "pay five visits", "the course is 10 days",
                                       "I weighed 300 pounds", "كشفيتي كانت طويلة"))

    def test_supporting_rows_reach_every_window(self):
        """Self-review r1 P3-1: on a long text, a domain found in one window gets its supporting rows from all."""
        t = "خصم " + "كلام عادي جدا " * 150 + "استثمار"
        self.assertGreater(len(t), RD.WINDOW)
        rules = [m["rule"] for m in RD.detect(t)["business"]]
        self.assertIn("pricing", rules)
        self.assertIn("earnings-word", rules)
        self.assertNotIn("business", domains("كلام عادي جدا " * 150 + "استثمار"))     # supporting alone flags nothing

    def test_windows_count_the_nfkc_form(self):
        """Self-review r1 P3-2: ﷺ is one char that NFKC spells out in 18, so windows are cut after NFKC."""
        import time
        t0 = time.monotonic()
        RD.detect("ﷺ" * 5_000)                                      # 90,000 chars after NFKC
        self.assertLess(time.monotonic() - t0, 10.0)
        self.assertEqual(RD.detect("ﷺ " * 10 + "الكشف ب ٥٠٠ جنيه"), RD.detect(RD._nfkc("ﷺ " * 10) + "الكشف ب ٥٠٠ جنيه"))
        seen = []
        real = RD._windows
        with mock.patch.object(RD, "_windows", side_effect=lambda t: seen.extend(real(t)) or real(t)):
            RD.detect("ﷺ" * 3_000)
        self.assertTrue(seen and all(len(RD._nfkc(p)) <= RD.WINDOW for p in seen), max(map(len, seen)))

    def test_a_zone_holding_the_rial_sign_hides_nothing_in_any_reading(self):
        """Self-review r2 P1-1: the spelled reading keeps the sign, so the zone floor holds and its words never reach
        the recitation list."""
        self.assertIn("business", domains("﴿ ﷼ ﴾"))
        ms = RD.matchers()
        for screen in ("﴿ ﷼ خصم ﴾", "﴿ خصم ﷼ ﴾"):
            _found, zone_words = RD._detect(screen, ms)
            self.assertEqual(zone_words, {}, screen)
            for speech in ("خصم ريال", "خصم"):
                self.assertIn("business", RD._detect(speech, ms, zone_words)[0], (screen, speech))

    def test_weight_efficacy_and_code_words_are_not_prices(self):
        """Self-review r2 P2-1, P2-2, P2-3, P3-1, P3-2, P3-3, P3-5."""
        self.assert_clean("business", (
            "lose 10 pounds a month", "you can lose 5 pounds a week", "I lost 20 pounds a month", "drop 4 pounds a month",
            "baby gains 2 pounds a month", "losing 3 pounds per session", "the course is 10 pounds of weight loss",
            "session 2 pounds", "visit 5 pounds down", "التطعيم بيوفر ٩٠٪ حماية", "الدوا ده بيوفر ٥٠٪ حماية",
            "وفر ٤٠٪ من وقتك", "هتوفري ٣٠٪ من السعرات", "scan the 2 QR codes", "scan 1 QR code below", "a 70 kD protein",
            "10 kd protein", "stage 3 KD", "patient 3 SR negative", "2 for 3 reps", "do 3 for 5 sets", "1 for 2 tablets",
            "take 1 for 2 nights", "3 for 2 cycles", "it costs five hundred calories", "paid a thousand visits",
            "you pay two hundred times more attention", "two for one reason", "first visit free of pain",
            "ب ٣ اقساط من النوم", "الدوا ده بيوفر ٥٠٠", "الجهاز بيوفر ٣٠٪ من الكهربا", "I lost 20 pounds only"))
        self.assert_hits("business", ("SR 500", "QR 500", "KD 500", "ر.س ٥٠٠", "500 SR", "250 QR", "وفر ٤٠٪", "وفري ٢٠٪",
                                      "هتوفر ٥٠٪", "2 for 1", "2 for 1 offer", "two for one", "the visit is free",
                                      "consultations are free", "free of charge", "first session free",
                                      "300 pounds for the session", "consultation 500 pounds", "pay only five hundred"))


class TestPhrases(unittest.TestCase):
    """Pre-mortem T50 item 2: every reported miss or false alarm is one line of fixtures/review_domains/phrases.tsv."""

    def test_phrases_table(self):
        rows = []
        for n, line in enumerate((FIXTURES / "phrases.tsv").read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip() or line.startswith("#"):
                continue
            text, *wants = line.split("\t")
            self.assertTrue(wants and all(w[:1] in "+-" and w[1:] in SHIPPED for w in wants), (n, line))
            rows.append((n, text, wants))
        self.assertGreaterEqual(len(rows), 40)
        for n, text, wants in rows:
            found = domains(text)
            for w in wants:
                self.assertEqual(w[1:] in found, w[0] == "+", (n, text, w, RD.detect(text)))


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

    def test_recitation_hides_only_verse_words_never_amounts_or_quotes(self):
        """Executor follow-up (79c5bf7 P2-1): speech repeating a «» quotation is not hidden; an amount said inside a
        recited ﴿﴾ verse is still business."""
        self.profile({"domain": "religious"})
        self.put(event("G1", 0, 3000, evidence="ربنا قال اللي يشترك معانا هيكسب ارباح",
                       text="ربنا قال «اللي يشترك معانا هيكسب ارباح»"),
                 event("G2", 3000, 6000, evidence="الجلسة بـ ٥٠٠ جنيه فما ربحت تجارتهم",
                       text="﴿ الجلسة بـ ٥٠٠ جنيه فَمَا رَبِحَت تِّجَارَتُهُمْ ﴾"))
        s = RD.scan(self.p)
        g1, g2 = self.line(s, "G1"), self.line(s, "G2")
        self.assertIn("speech", {m["in"] for m in g1["detected"]["business"]})
        self.assertIn("screen", {m["in"] for m in g1["detected"]["business"]})
        speech = [m for m in g2["detected"]["business"] if m["in"] == "speech"]
        self.assertIn("currency-amount", {m["rule"] for m in speech})              # recited, still shown
        self.assertTrue([m for m in speech if "ربح" in m["match"]], speech)       # a "verse" with a number hides nothing
        self.put(event("G3", 0, 3000, evidence="فما ربحت تجارتهم بس الكورس بـ ٥٠٠ جنيه",
                       text="﴿فَمَا رَبِحَت تِّجَارَتُهُمْ﴾"))
        g3 = self.line(RD.scan(self.p), "G3")
        self.assertEqual({m["rule"] for m in g3["detected"]["business"]} & {"earnings-roi"}, set(), g3)  # verse word
        self.assertIn("currency-amount", {m["rule"] for m in g3["detected"]["business"]})
        self.assertIn("business", g2["required"])

    def test_lexicon_update_that_drops_a_detection(self):
        before = RD.scan(self.p)
        lex = RD.lexicon("business")
        thin = {**lex, "rules": [r for r in lex["rules"] if r["id"] not in ("currency-amount", "only-for-price",
                                                                           "pricing", "priced-amount")]}
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

    def test_ai_asset_path_matches_across_unicode_forms(self):
        """Review 79c5bf7 P3: macOS folder names come back in NFD; the manifest may hold NFC (or the other way)."""
        import unicodedata
        nfc = unicodedata.normalize("NFC", "data/Broll/café صورة/gen.png")
        nfd = unicodedata.normalize("NFD", nfc)
        self.assertNotEqual(nfc, nfd)
        for platform in ("darwin", "win32", "linux"):
            for man, shown in ((nfc, nfd), (nfd, nfc)):
                write_json(self.p.client_db / "asset-manifest.json", {"assets": [{"rel": man, "ai_generated": True}]})
                self.put(event("G1", 0, 1000, text="الملح", image=shown))
                with mock.patch.object(RD.sys, "platform", platform):
                    s = RD.scan(self.p)
                self.assertEqual([a["event_id"] for a in s["ai_assets"]], ["G1"], (platform, man == nfc))
        write_json(self.p.client_db / "asset-manifest.json", {"assets": [{"rel": "data/Broll/Gen.PNG",
                                                                          "ai_generated": True}]})
        self.put(event("G1", 0, 1000, text="الملح", image="data/broll/gen.png"))
        for platform, want in (("darwin", ["G1"]), ("win32", ["G1"]), ("linux", [])):   # case rules per OS
            with mock.patch.object(RD.sys, "platform", platform):
                self.assertEqual([a["event_id"] for a in RD.scan(self.p)["ai_assets"]], want, platform)

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
