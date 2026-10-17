# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 30 (R-4.8) — the stricter publish-check rules: no spoken-sentence repeat, no cross-platform
duplicate, no filler hashtags, the search phrase in the first line (warning).
Run:  bash tools/test.sh -p test_publish_rules.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib import publish_rules as PR  # noqa: E402

AR_MED = "النهارده هنتكلم عن ضغط الدم العالي وازاي تقيسه في البيت كل يوم الصبح. " \
         "لازم تاخد العلاج في ميعاده حتى لو حاسس انك كويس."
EN = "The most important thing is to take your medicine every single day. Sleep matters much more than most people think."
MIXED = "الـ blood pressure بيعلى لما تقلل النوم وده مهم جدا."
SEGS = [{"id": 1, "text": AR_MED}, {"id": 2, "text": EN}, {"id": 3, "text": MIXED},
        {"id": 4, "text": "and then we started the company in"}, {"id": 5, "text": "a tiny garage with two friends."}]


def reel(ig="", tt="", sh_title="عنوان قصير", sh_desc="", rid="EP1_R01", **extra):
    r = {"reel_id": rid, "instagram": {"caption": ig, "hashtags": []}, "tiktok": {"caption": tt, "hashtags": []},
         "shorts": {"title": sh_title, "description": sh_desc}}
    r.update(extra)
    return r


def run(reels=(), pub=None, segs=SEGS, cfg=None):
    rs = [(r["reel_id"], r) for r in reels]
    return PR.check(pub or {}, rs, segs, cfg or PR.config())


def errs_with(res, *needles):
    return [e for e in res["errors"] if all(n in e for n in needles)]


class TestSpokenRepeat(unittest.TestCase):
    def test_english_six_word_run_refused_and_quoted(self):
        r = run([reel(ig="Remember: take your medicine every single day, no excuses")])
        hit = errs_with(r, "EP1_R01 instagram", "take your medicine every single day")
        self.assertEqual(len(hit), 1, r["errors"])
        self.assertIn("قول الفكرة بكلام جديد", hit[0])           # the fix, Arabic first
        self.assertLess(hit[0].index("قول"), hit[0].index("say the idea"))

    def test_arabic_six_word_run_refused(self):
        r = run([reel(tt="نصيحة مهمة: هنتكلم عن ضغط الدم العالي وازاي تقيسه")])
        self.assertTrue(errs_with(r, "EP1_R01 tiktok", "ضغط الدم العالي"), r["errors"])

    def test_near_verbatim_diacritics_alef_variants_punctuation(self):
        r = run([reel(ig="لازِم تاخُد العِلاج، في ميعادُه حتى لو حاسس إنك كويـــس!")])
        hit = errs_with(r, "EP1_R01 instagram")
        self.assertEqual(len(hit), 1, r["errors"])
        self.assertIn("لازِم تاخُد", hit[0])                      # the caption's own raw words are quoted

    def test_single_changed_word_caught_by_sentence_overlap(self):
        r = run([reel(ig="Sleep matters much less than most people think")])
        self.assertTrue(errs_with(r, "EP1_R01 instagram"), r["errors"])

    def test_unpunctuated_segments_are_sentences(self):     # ASR text with no full stops: a segment is a sentence
        segs = [{"text": "النهارده هتعرفوا ازاي تبدأوا مشروعكم من الصفر"}, {"text": "وده مهم جدا لكل واحد فيكم"},
                {"text": "اول حاجه لازم تعرفوها هي الصبر"}]
        for cap in ("النهارده هتتعلموا ازاي تبدأوا مشروعكم من الصفر", "النهارده هتعرفوا ازاي تبدأوا مشروعك من الصفر"):
            r = run([reel(ig=cap)], segs=segs)
            self.assertTrue(errs_with(r, "EP1_R01 instagram"), (cap, r["errors"]))
        r = run([reel(ig="ازاي تبدأ مشروع صغير وانت لسه في الكلية")], segs=segs)
        self.assertEqual(r["errors"], [])

    def test_below_both_thresholds_allowed(self):
        r = run([reel(ig="The most important thing for kids is play")])
        self.assertEqual(r["errors"], [])

    def test_short_subset_of_a_long_sentence_allowed(self):
        r = run([reel(ig="Your medicine, every day.", tt="Take your medicine")])
        self.assertEqual(r["errors"], [])

    def test_marked_quote_allowed(self):
        r = run([reel(ig="«لازم تاخد العلاج في ميعاده حتى لو حاسس انك كويس» — نصيحة الدكتور",
                      tt="“take your medicine every single day” says the doctor")])
        self.assertEqual(r["errors"], [])

    def test_verse_in_ornate_brackets_is_a_quote(self):   # a verse is written ﴿…﴾, never reworded
        segs = [{"text": "ربنا قال في كتابه إِنَّ مَعَ الْعُسْرِ يُسْرًا إِنَّ مَعَ الْعُسْرِ يُسْرًا وده وعد."}]
        r = run([reel(ig="﴿إِنَّ مَعَ الْعُسْرِ يُسْرًا إِنَّ مَعَ الْعُسْرِ يُسْرًا﴾ تأملات في الحلقة",
                      tt="﴿إِنَّ مَعَ الْعُسْرِ يُسْرًا﴾ وعد ربنا ليك في الضيق")], segs=segs)
        self.assertEqual(r["errors"], [])
        r = run([reel(ig="إِنَّ مَعَ الْعُسْرِ يُسْرًا إِنَّ مَعَ الْعُسْرِ يُسْرًا تأملات")], segs=segs)
        self.assertTrue(errs_with(r, "EP1_R01 instagram", "﴿﴾"), r["errors"])     # unmarked: refused, fix names ﴿﴾

    def test_straight_quotes_are_not_a_quote_mark(self):
        r = run([reel(ig='"لازم تاخد العلاج في ميعاده حتى لو حاسس انك كويس"')])
        self.assertTrue(errs_with(r, "EP1_R01 instagram"), r["errors"])

    def test_mixed_arabic_english_repeat(self):
        r = run([reel(ig="خلي بالك: الـ Blood Pressure بيعلى لما تقلل النوم 😴")])
        self.assertTrue(errs_with(r, "EP1_R01 instagram", "Blood Pressure"), r["errors"])

    def test_inserted_hashtag_or_emoji_does_not_hide_a_repeat(self):
        r = run([reel(ig="we started the company #startup in a tiny garage", tt="take 💊 your medicine every single day")])
        self.assertTrue(errs_with(r, "EP1_R01 instagram"), r["errors"])
        self.assertTrue(errs_with(r, "EP1_R01 tiktok"), r["errors"])

    def test_link_is_a_break(self):
        r = run([reel(ig="the most important thing is https://x.com/a to take your medicine")])
        self.assertEqual(errs_with(r, "EP1_R01 instagram"), [])

    def test_run_across_two_transcript_segments(self):
        r = run([reel(sh_desc="we started the company in a tiny garage")])
        self.assertTrue(errs_with(r, "EP1_R01 shorts description"), r["errors"])

    def test_shorts_title_and_youtube_summary_checked(self):
        pub = {"youtube": {"description": {"hook": "حلقة جديدة", "summary": "Sleep matters much more than most people think"}}}
        r = run([reel(sh_title="take your medicine every single day")], pub=pub)
        self.assertTrue(errs_with(r, "EP1_R01 shorts title"), r["errors"])
        self.assertTrue(errs_with(r, "description summary"), r["errors"])
        self.assertFalse(errs_with(r, "description hook"), r["errors"])

    def test_medical_note_in_the_fix(self):
        r = run([reel(ig="take your medicine every single day")])
        self.assertIn("«»", r["errors"][0])                      # quote the exact words instead of rewording a claim

    def test_empty_or_missing_transcript(self):
        for segs in ([], [{"id": 1}], [{"id": 1, "text": None}], None):
            r = run([reel(ig="take your medicine every single day")], segs=segs)
            self.assertEqual(r["errors"], [], segs)

    def test_thresholds_from_config(self):
        cfg = PR.config()
        cfg["spoken_repeat"]["ngram"] = 4
        r = run([reel(ig="the most important thing for kids is play")], cfg=cfg)
        self.assertTrue(r["errors"])
        cfg = PR.config()
        cfg["spoken_repeat"]["sentence_overlap"] = 0.95
        r = run([reel(ig="Sleep matters much less than most people think")], cfg=cfg)
        self.assertEqual(r["errors"], [])


class TestCrossPlatform(unittest.TestCase):
    def test_same_caption_two_platforms(self):
        r = run([reel(ig="حلقة عن الفشل والبداية من جديد مع سارة", tt="حلقة عن الفشل والبداية من جديد مع سارة")])
        hit = errs_with(r, "EP1_R01", "instagram", "tiktok", "كل منصة محتاجة نص مختلف")
        self.assertEqual(len(hit), 1, r["errors"])
        self.assertIn("100%", hit[0])

    def test_hashtags_ignored_and_variants_unified(self):
        r = run([reel(ig="حلقة عن الفشل، والبداية من جديد مع سارة #بودكاست",
                      tt="حلقه عن الفَشل والبدايه من جديد مع ساره! #قصة_نجاح #ريادة")])
        self.assertEqual(len(errs_with(r, "كل منصة")), 1, r["errors"])

    def test_different_captions_allowed(self):
        r = run([reel(ig="حلقة عن الفشل والبداية من جديد مع سارة", tt="سارة خسرت أول شركة وقامت تاني")])
        self.assertEqual(errs_with(r, "كل منصة"), [])

    def test_empty_caption_not_compared(self):
        r = run([reel(ig="حلقة عن الفشل", tt="", sh_desc="")])
        self.assertEqual(errs_with(r, "كل منصة"), [])

    def test_title_is_not_a_caption(self):           # today's good_reel: tiktok caption == shorts title
        r = run([reel(ig="«انا قلت ان الشركه» — سارة عن أول خسارة", tt="سارة عن أول خسارة",
                      sh_title="سارة عن أول خسارة", sh_desc="من الحلقة 12")])
        self.assertEqual(errs_with(r, "كل منصة"), [])

    def test_three_platforms_each_pair_once_in_order(self):
        t = "Mixed كلام about the startup life and failure"
        r = run([reel(ig=t, tt=t, sh_desc=t)], segs=[])
        hit = errs_with(r, "كل منصة")
        self.assertEqual(len(hit), 3, r["errors"])
        self.assertIn("instagram", hit[0]); self.assertIn("tiktok", hit[0])
        self.assertIn("shorts", hit[2])
        self.assertEqual(run([reel(ig=t, tt=t, sh_desc=t)], segs=[]), r)          # deterministic

    def test_threshold_from_config(self):
        cfg = PR.config()
        cfg["cross_platform"]["jaccard"] = 0.5
        r = run([reel(ig="سارة خسرت أول شركة", tt="سارة خسرت أول شركة وقامت تاني بعد سنة")], cfg=cfg)
        self.assertTrue(errs_with(r, "كل منصة"))
        r = run([reel(ig="سارة خسرت أول شركة", tt="سارة خسرت أول شركة وقامت تاني بعد سنة")])
        self.assertFalse(errs_with(r, "كل منصة"))


class TestFillerHashtags(unittest.TestCase):
    def test_key_normalisation(self):
        for t in ("#fyp", "#FYP", "#fyp🔥", "fyp"):
            self.assertEqual(PR.hashtag_key(t), "fyp", t)
        self.assertEqual(PR.hashtag_key("#For_You"), PR.hashtag_key("#foryou"))
        self.assertEqual(PR.hashtag_key("#إكسبلور"), PR.hashtag_key("#اكسبلور"))
        self.assertEqual(PR.hashtag_key("#اكسبلوووور"), PR.hashtag_key("#اكسبلور"))      # stretched letters
        self.assertEqual(PR.hashtag_key("#fypppp"), "fyp")
        self.assertEqual(PR.hashtag_key("#fypシ"), "fyp")                                # decoration symbols
        self.assertEqual(PR.hashtag_key("#fypシ゚viral"), "fypviral")
        self.assertEqual(PR.hashtag_key("#explore_page"), PR.hashtag_key("#explorepage"))
        self.assertNotEqual(PR.hashtag_key("#بودكاست"), PR.hashtag_key("#بودكااست_x"))

    def test_named_without_trailing_punctuation(self):
        r = run([reel(ig="قصة جميلة #fyp، #explore. #viral!", tt="x")])
        for tag in ("#fyp ", "#explore ", "#viral "):
            self.assertEqual(len(errs_with(r, tag)), 1, (tag, r["errors"]))
        self.assertFalse(errs_with(r, "#fyp،"), r["errors"])

    def test_english_variants_refused_named_as_written(self):
        r0 = reel(ig="سارة عن أول خسارة #ForYou", tt="قصة مختلفة خالص")
        r0["tiktok"]["hashtags"] = ["#FYP", "#for_you", "#بودكاست"]
        r = run([r0])
        for tag in ("#ForYou", "#FYP", "#for_you"):
            self.assertEqual(len(errs_with(r, tag)), 1, (tag, r["errors"]))
        self.assertFalse(errs_with(r, "#بودكاست"))

    def test_arabic_fillers_refused(self):
        r0 = reel(ig="a", tt="b")
        r0["instagram"]["hashtags"] = ["#إكسبلور", "#ترند", "#قصة_نجاح"]
        r = run([r0])
        self.assertTrue(errs_with(r, "#إكسبلور"))
        self.assertTrue(errs_with(r, "#ترند"))
        self.assertFalse(errs_with(r, "#قصة_نجاح"))
        self.assertIn("هاشتاج", errs_with(r, "#ترند")[0])

    def test_youtube_description_hashtags(self):
        r = run([], pub={"youtube": {"description": {"hashtags": ["#viral", "#بودكاست"]}}})
        self.assertEqual(len(errs_with(r, "#viral")), 1, r["errors"])

    def test_same_tag_in_text_and_list_once_per_place(self):
        r0 = reel(ig="قصة #fyp", tt="x")
        r0["instagram"]["hashtags"] = ["#fyp"]
        r = run([r0])
        self.assertEqual(len(errs_with(r, "#fyp")), 1, r["errors"])

    def test_extra_filler_tags_add_to_the_list(self):       # a client adds tags without losing the defaults
        cfg = PR.config()
        cfg["extra_filler_hashtags"] = ["#عيادة"]
        r0 = reel(ig="x", tt="y")
        r0["instagram"]["hashtags"] = ["#عياده", "#fyp"]
        r = run([r0], cfg=cfg)
        self.assertTrue(errs_with(r, "#عياده"), r["errors"])
        self.assertTrue(errs_with(r, "#fyp"), r["errors"])

    def test_hashtags_written_as_one_string(self):
        r0 = reel(ig="x", tt="y")
        r0["instagram"]["hashtags"] = "#بودكاست #FYP"
        r = run([r0])
        self.assertEqual(len(errs_with(r, "#FYP")), 1, r["errors"])

    def test_client_override_list_and_allow(self):
        cfg = PR.config()
        cfg["filler_hashtags"].append("#عيادة")
        cfg["allowed_hashtags"] = ["#reels"]
        r0 = reel(ig="x", tt="y")
        r0["instagram"]["hashtags"] = ["#عياده", "#Reels"]
        r = run([r0], cfg=cfg)
        self.assertTrue(errs_with(r, "#عياده"))
        self.assertFalse(errs_with(r, "#Reels"))


class TestFirstLine(unittest.TestCase):
    def test_at_start_no_warning(self):
        r = run([reel(ig="ضغط الدم العالي: 3 حاجات لازم تعرفها\nالتفاصيل في الريل", tt="ضغط الدم بيعلى ليه؟",
                      sh_title="ضغط الدم في 30 ثانية", search_phrase="ضغط الدم")])
        self.assertEqual(r["warnings"], [])

    def test_empty_text_is_not_warned(self):          # an empty caption is the limits check's job, not rule 4's
        r = run([reel(ig="ضغط الدم", tt="", sh_title="", search_phrase="ضغط الدم")])
        self.assertEqual(r["warnings"], [])

    def test_second_line_warns(self):
        r = run([reel(ig="3 حاجات لازم تعرفها\nعن ضغط الدم", search_phrase="ضغط الدم")])
        w = [x for x in r["warnings"] if "EP1_R01 instagram" in x]
        self.assertEqual(len(w), 1, r["warnings"])
        self.assertIn("ضغط الدم", w[0])

    def test_past_the_limit_warns_with_position(self):
        long = "x" * 130 + " ضغط الدم"
        r = run([reel(ig=long, search_phrase="ضغط الدم")])
        w = [x for x in r["warnings"] if "EP1_R01 instagram" in x]
        self.assertEqual(len(w), 1, r["warnings"])
        self.assertIn("131", w[0])
        self.assertEqual(PR.first_line_position(long, "ضغط الدم"), 131)
        straddle = "x" * 120 + " ضغط الدم"                       # starts inside the limit, ends past it
        w = [x for x in run([reel(ig=straddle, search_phrase="ضغط الدم")])["warnings"] if "EP1_R01 instagram" in x]
        self.assertEqual(len(w), 1)
        self.assertIn("129", w[0])                                   # where it ends, said plainly
        self.assertNotIn("الcaption", w[0])
        self.assertNotIn("الtitle", " ".join(run([reel(sh_title="عنوان", search_phrase="ضغط الدم")])["warnings"]))

    def test_per_platform_phrase_overrides(self):
        r0 = reel(ig="Blood pressure: 3 facts", tt="3 facts about blood pressure", search_phrase="ضغط الدم")
        r0["instagram"]["search_phrase"] = "blood pressure"
        r0["tiktok"]["search_phrase"] = "3 facts"
        r = run([r0])
        self.assertFalse([x for x in r["warnings"] if "instagram" in x or "tiktok" in x], r["warnings"])
        self.assertTrue([x for x in r["warnings"] if "shorts" in x], r["warnings"])

    def test_no_phrase_no_warning(self):
        self.assertEqual(run([reel(ig="anything\nelse")])["warnings"], [])

    def test_normalised_match(self):
        self.assertEqual(PR.first_line_position("إزاي تقيس ضَغط الدم في البيت", "ازاي تقيس"), 0)
        self.assertEqual(PR.first_line_position("How to: BLOOD Pressure", "blood pressure"), 8)
        self.assertIsNone(PR.first_line_position("one\nblood pressure", "blood pressure"))

    def test_platform_without_limit_skipped(self):
        cfg = PR.config()
        cfg["first_line"].pop("instagram")
        r = run([reel(ig="x\nضغط الدم", search_phrase="ضغط الدم")], cfg=cfg)
        self.assertFalse([x for x in r["warnings"] if "instagram" in x])


class TestConfigAndRobustness(unittest.TestCase):
    def test_disabled_means_nothing(self):
        cfg = PR.config()
        cfg["enabled"] = False
        r0 = reel(ig="take your medicine every single day #fyp", tt="take your medicine every single day",
                  search_phrase="nowhere")
        self.assertEqual(run([r0], cfg=cfg), {"errors": [], "warnings": []})

    def test_todays_good_package_has_no_findings(self):
        words = {50: "انا", 51: "قلت", 52: "ان", 53: "الشركه", 80: "السياسة"}
        w = [words.get(i, f"كلمه{i}") + ("؟" if i == 38 else "") for i in range(300)]
        segs = [{"id": 1, "text": " ".join(w[:39])}, {"id": 2, "text": " ".join(w[39:150])},
                {"id": 3, "text": " ".join(w[150:])}]
        pub = {"youtube": {"titles": ["قصة سارة مع أول شركة"], "description": {
            "hook": "سارة بتحكي إزاي خسرت أول شركة.", "summary": "حلقة عن الفشل والبداية من جديد.",
            "cta": "اشترك في القناة", "hashtags": ["#بودكاست", "#قصة_نجاح"]}, "tags": ["بودكاست"]}}
        good = {"reel_id": "EP12_R01",
                "instagram": {"caption": "«انا قلت ان الشركه» — سارة عن أول خسارة", "hashtags": ["#بودكاست"]},
                "tiktok": {"caption": "سارة عن أول خسارة", "hashtags": ["#بودكاست"]},
                "shorts": {"title": "سارة عن أول خسارة", "description": "من الحلقة 12"}}
        self.assertEqual(run([good], pub=pub, segs=segs), {"errors": [], "warnings": []})

    def test_damaged_fields_do_not_crash(self):
        bad = [{"reel_id": "R1"}, {"reel_id": "R2", "instagram": "x", "tiktok": None, "shorts": []},
               {"reel_id": "R3", "instagram": {"caption": 5, "hashtags": "#fyp"}, "tiktok": {"hashtags": [None, 3]},
                "search_phrase": ["x"]}]
        r = run(bad, pub={"youtube": {"description": "x"}})
        self.assertEqual(r["warnings"], [])
        r = run(bad, pub={"youtube": None})
        self.assertIsInstance(r["errors"], list)

    def test_partial_cfg_takes_the_defaults(self):
        r = run([reel(ig="take your medicine every single day")], cfg={"enabled": True})
        self.assertTrue(errs_with(r, "EP1_R01 instagram"), r["errors"])
        for part in ({"spoken_repeat": {"ngram": 4}}, {"cross_platform": None}):
            r = run([reel(ig="take your medicine every single day")], cfg=part)
            self.assertTrue(errs_with(r, "EP1_R01 instagram"), (part, r["errors"]))

    def test_config_defaults_and_bad_values(self):
        cfg = PR.config()
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["spoken_repeat"]["ngram"], 6)
        self.assertEqual(cfg["spoken_repeat"]["sentence_overlap"], 0.7)
        self.assertEqual(cfg["cross_platform"]["jaccard"], 0.8)
        self.assertIn("#fyp", cfg["filler_hashtags"])
        self.assertTrue(any(PR.hashtag_key(t) == "اكسبلور" for t in cfg["filler_hashtags"]))
        self.assertEqual(cfg["first_line"]["instagram"], 125)

    def test_client_reel_profile_overrides_and_bad_values_fall_back(self):
        tmp = Path(tempfile.mkdtemp()) / "عميل تجربة"
        prof = tmp / common.CLIENT_PROFILE_REL
        prof.mkdir(parents=True)
        (tmp / "assets").mkdir()
        (tmp / "data").mkdir()
        try:
            common.set_context(tmp)
            (prof / "publish-rules.json").write_text(json.dumps(
                {"spoken_repeat": {"ngram": "six", "sentence_overlap": 0.9},
                 "cross_platform": {"jaccard": 7}, "allowed_hashtags": ["#reels"],
                 "extra_filler_hashtags": ["#عيادة", 5]}), encoding="utf-8")
            cfg = PR.config()
            self.assertEqual(cfg["spoken_repeat"]["ngram"], 6)                 # not a number -> default
            self.assertEqual(cfg["spoken_repeat"]["sentence_overlap"], 0.9)
            self.assertEqual(cfg["cross_platform"]["jaccard"], 0.8)           # out of 0..1 -> default
            self.assertEqual(cfg["allowed_hashtags"], ["#reels"])
            self.assertEqual(cfg["extra_filler_hashtags"], ["#عيادة"])
            self.assertIn("#fyp", cfg["filler_hashtags"])
            (prof / "publish-rules.json").write_text("{damaged", encoding="utf-8")
            self.assertEqual(PR.config()["spoken_repeat"]["ngram"], 6)
        finally:
            common.set_context(None)
            shutil.rmtree(tmp.parent, ignore_errors=True)

    def test_config_returns_a_fresh_copy(self):
        a = PR.config()
        a["filler_hashtags"].append("#zzz")
        a["spoken_repeat"]["ngram"] = 2
        b = PR.config()
        self.assertNotIn("#zzz", b["filler_hashtags"])
        self.assertEqual(b["spoken_repeat"]["ngram"], 6)

    def test_input_not_mutated_and_deterministic(self):
        r0 = reel(ig="take your medicine every single day #fyp", tt="take your medicine every single day")
        before = copy.deepcopy(r0)
        a, b = run([r0]), run([r0])
        self.assertEqual(a, b)
        self.assertEqual(r0, before)


class TestLabelledSet(unittest.TestCase):
    """tests/fixtures/publish_rules/*.json: 4 made-up episodes (medical AR, business AR+EN, English, religious AR with a
    verse in harakat), 32 reels written by a separate agent from the rule text only, half good copy (paraphrase, shared
    key terms, 4-5 shared words, «quotes», a shared opening hook), half with labelled mistakes. Measured 2026-10-17:
    precision and recall 1.00 for every rule (18 repeats, 8 duplicate pairs, 20 filler tags; 0 false refusals)."""

    def test_every_label_and_nothing_else(self):
        import re
        places = ("instagram", "tiktok", "shorts title", "shorts description")
        files = sorted((SK / "tests/fixtures/publish_rules").glob("*.json"))
        self.assertEqual(len(files), 4)
        for f in files:
            d = json.loads(f.read_text(encoding="utf-8"))
            for r in d["reels"]:
                rid, lab = r["reel_id"], r["labels"]
                errs = run([r], segs=d["segments"])["errors"]
                got_r = {p for p in places for e in errs if e.startswith(f"{rid} {p}: «")}
                got_d = {frozenset(m.groups()) for e in errs for m in [re.search(r"نص (\w+) ونص (\w+)", e)] if m}
                got_f = {PR.hashtag_key(m.group(1)) for e in errs for m in [re.search(r"الهاشتاج (\S+) عام", e)] if m}
                want_d = {frozenset("shorts" if x.startswith("shorts") else x for x in p) for p in lab["duplicate"]}
                self.assertEqual(got_r, set(lab["repeat"]), (f.name, rid, errs))
                self.assertEqual(got_d, want_d, (f.name, rid, errs))
                self.assertEqual(got_f, {PR.hashtag_key(t) for t in lab["filler"]}, (f.name, rid, errs))


if __name__ == "__main__":
    unittest.main()
