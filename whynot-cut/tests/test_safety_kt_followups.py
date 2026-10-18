# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4, Addendum K1 follow-ups on accepted items (owner pre-mortem 2026-10-18): a check that did not run, or
could not be read back, says so instead of looking clean.
- K-T2: the "what we removed" sheet says the meaning check did not run (K-T1 failing, no transcript words, a drug
  list not loaded) instead of «مفيش / none»;
- K-T4: with its switch on and no platform chosen, `reel qc` says the safe zones are not enforced (a warning), and the
  check names what it looked at (graphic and caption stills, Premiere frames recorded or not);
- K-T5: an Arabic text layer whose animator unit After Effects did not report is "Not verified", never passed.
Run:  bash tools/test.sh -p test_safety_kt_followups.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402
from lib.safety import arabic_integrity as AI  # noqa: E402
from lib.safety import removed_review as RR  # noqa: E402
from lib.safety import safezone_gate as G, switches  # noqa: E402
import test_safety_removed_review as RRT  # noqa: E402
import test_safety_safezone_gate as SZT  # noqa: E402


# --- K-T2 ------------------------------------------------------------------------------------------------------------
class TestRemovedReviewMeaningCheck(RRT.Project):
    def sheet(self):
        return RR.sheet(RR.plan(self.p))

    def test_a1_k_t1_failing_is_never_none(self):
        self.spec([[0, 2000], [4000, RRT.DUR]])
        with mock.patch("lib.safety.risk_words.classify", side_effect=RuntimeError("lexicon blew up")):
            doc = RR.plan(self.p)
        self.assertFalse(doc["meaning_check"]["ran"])
        self.assertIn("RuntimeError", doc["meaning_check"]["why"])
        text = RR.sheet(doc)
        part = text[text.index("## كلمات بتغيّر المعنى"):text.index("## كل اللي اتشال")]
        self.assertNotIn("مفيش / none", part)
        self.assertIn("فحص المعنى ماشتغلش", part)
        self.assertIn("the meaning check did not run", part)
        self.assertIn("اسمع الكليب كله", part)

    def test_a2_no_transcript_words_is_did_not_run(self):
        self.p.p("02_transcription/words.json").unlink()
        self.spec([[0, 2000], [4000, RRT.DUR]])
        doc = RR.plan(self.p)
        self.assertFalse(doc["meaning_check"]["ran"])
        self.assertIn("no transcript words", doc["meaning_check"]["why"])
        self.assertNotIn("مفيش / none", RR.sheet(doc))

    def test_a3_a_clean_check_still_says_none(self):
        self.spec([[0, 300], [400, RRT.DUR]])                 # only a sliver of «الدكتورة» removed: nothing risky
        doc = RR.plan(self.p)
        self.assertEqual(doc["meaning_check"], {"ran": True, "why": None, "partly": []})
        self.assertIn("- مفيش / none", RR.sheet(doc))

    def test_a4_a_drug_list_not_loaded_is_named(self):
        self.spec([[0, 300], [400, RRT.DUR]])
        refused = {"thr": 0.6, "basis": "x", "domain": "medical", "groups": [], "terms": [],
                   "lexicon_refused": [{"id": "drugs-eg", "reason": "sha256 mismatch", "reason_ar": "ملف الأدوية اتغير"}]}
        with mock.patch("lib.safety.risk_words.context", return_value=refused):
            doc = RR.plan(self.p)
        self.assertTrue(doc["meaning_check"]["ran"])
        self.assertEqual(doc["meaning_check"]["partly"], [{"ar": "ملف الأدوية اتغير", "en": "drugs-eg: sha256 mismatch"}])
        text = RR.sheet(doc)
        self.assertIn("أسماء الأدوية اتفحصت جزئيًا (ملف الأدوية اتغير)", text)
        self.assertIn("drug names partly checked (drugs-eg: sha256 mismatch)", text)
        self.assertIn("- مفيش / none", text)                 # what was checked found nothing; the gap is said too
        refused["lexicon_refused"] = "x"
        with mock.patch("lib.safety.risk_words.context", return_value=refused):
            doc = RR.plan(self.p)
        self.assertIn("the list of refused drug sources cannot be read", RR.sheet(doc))

    def test_r1_words_present_but_unusable_is_did_not_run(self):
        from lib.common import write_json as wj
        wj(self.p.p("02_transcription/words.json"), {"words": [{"id": 1, "word": " ", "start_ms": 0, "end_ms": 10},
                                                               {"id": 2, "word": 5, "start_ms": 0, "end_ms": 10}]})
        self.spec([[0, 2000], [4000, RRT.DUR]])
        doc = RR.plan(self.p)
        self.assertFalse(doc["meaning_check"]["ran"])
        self.assertNotIn("مفيش / none", RR.sheet(doc))

    def test_r1_garbage_from_k_t1_or_its_settings_failing_is_did_not_run(self):
        self.spec([[0, 2000], [4000, RRT.DUR]])
        for garbage in (None, "x", [{"text": 1, "risk": "dose", "word_ids": [6]}], [{"text": "لا", "risk": "negation"}]):
            with self.subTest(garbage=garbage):
                with mock.patch("lib.safety.risk_words.classify", return_value=garbage):
                    doc = RR.plan(self.p)
                self.assertFalse(doc["meaning_check"]["ran"])
                self.assertIn("cannot be read", doc["meaning_check"]["why"])
                self.assertIn("the meaning check did not run", RR.sheet(doc))
        with mock.patch("lib.safety.risk_words.context", side_effect=OSError("profile locked")):
            doc = RR.plan(self.p)
        self.assertIn("OSError: profile locked", doc["meaning_check"]["why"])

    def test_r1_a_doc_without_the_record_counts_as_not_run(self):
        self.spec([[0, 2000], [4000, RRT.DUR]])
        doc = RR.plan(self.p)
        del doc["meaning_check"]
        self.assertIn("did not run (no record of it)", RR.sheet(doc))

    def test_a5_the_render_message_says_it_too(self):
        self.spec([[0, 2000], [4000, RRT.DUR]])
        (self.root / "data/Raw/CLIP1.mov").write_bytes(b"x")

        def runner(cmd):
            Path(cmd[-1]).write_bytes(b"part")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        with mock.patch("lib.safety.risk_words.classify", side_effect=ValueError("bad")), \
                mock.patch.object(RR, "_probe", return_value=((406, 720), True)):
            res = RR.render(self.p, runner=runner)
        self.assertIn("فحص المعنى ماشتغلش", res["message"])
        self.assertIn("the meaning check did not run", res["message"])
        with mock.patch.object(RR, "_probe", return_value=((406, 720), True)):
            res = RR.render(self.p, runner=runner)
        self.assertNotIn("did not run", res["message"])

    def test_a6_found_words_unchanged(self):
        self.spec([[0, 2000], [4000, RRT.DUR]])
        doc = RR.plan(self.p)
        self.assertTrue(doc["meaning_check"]["ran"])
        self.assertIn("«لا»", RR.sheet(doc))


# --- K-T4 ------------------------------------------------------------------------------------------------------------
class TestSafeZoneLine(SZT.Project):
    def switch_on(self):
        write_json(self.root / common.CLIENT_PROFILE_REL / "safety.json",
                   {"switches": {switches.QC_SAFEZONE_HARD_FAIL: True}})

    def test_b1_no_platform_says_not_enforced(self):
        self.caption((200, 1500, 880, 1600))
        self.switch_on()
        item = G.qc_item(self.p)
        self.assertFalse(item["ok"])
        self.assertFalse(item["mandatory"])                  # a warning: a missing setting, not a defect
        self.assertIn("مناطق المنصة مااتفحصتش", item["detail"])
        self.assertIn("safe zones not enforced: no platform set", item["detail"])
        self.assertIn("global.platforms", item["detail"])

    def test_b2_switch_off_is_unchanged(self):
        self.caption((200, 1500, 880, 1600))
        self.assertIsNone(G.qc_item(self.p))

    def test_r1_a_4x5_reel_with_no_platform_is_checked_against_its_default(self):
        self.seq((1080, 1350))
        self.caption((200, 700, 880, 800), size=(1080, 1350))
        self.switch_on()
        item = G.qc_item(self.p)
        self.assertTrue(item["mandatory"])
        self.assertNotIn("not enforced", item["detail"])

    def seq(self, size):
        write_json(self.root / common.CLIENT_PROFILE_REL / "sequence-settings.json",
                   {"general": {"frame_width": size[0], "frame_height": size[1]}})

    def test_r1_nothing_to_check_and_an_empty_or_bad_premiere_list_are_named(self):
        res = G.check(self.p, ["ig_reels_organic"])
        self.assertTrue(res.get("nothing"))
        self.assertIn("checked: 0 graphic still(s), 0 caption still(s); Premiere frames: not recorded", res["message"])
        self.assertIn("1 event(s) have no still yet (G1)", res["message"])     # planned graphics, no stills: said
        self.caption((200, 1000, 880, 1100))
        write_json(self.p.p("08_quality_control/frames/boxes.json"), {"frame": [1080, 1920], "boxes": []})
        self.assertIn("Premiere frames: recorded but empty", G.check(self.p, ["ig_reels_organic"])["message"])
        write_json(self.p.p("08_quality_control/frames/boxes.json"),
                   {"frame": [1080, 1920], "boxes": [{"id": "PP1", "rect": [100, 300, 400, 400]}, {"id": "PP2"}, 7]})
        msg = G.check(self.p, ["ig_reels_organic"])["message"]
        self.assertIn("Premiere frames: 1 box(es) (2 unreadable, skipped)", msg)
        self.assertIn("فريمات بريمير: ١ صندوق (٢ مش مقروء)", msg)

    def test_b3_the_check_names_what_it_looked_at(self):
        self.caption((200, 1000, 880, 1100))
        self.still(f"03_broll/{common.still_category('glass_card')}/G1.png", (200, 300, 880, 500))
        res = G.check(self.p, ["ig_reels_organic"])
        self.assertEqual(res["exit_code"], G.EXIT_OK)
        self.assertIn("اتفحص: ١ صورة جرافيك و١ صورة كابشن؛ فريمات بريمير: مش متسجلة", res["message"])
        self.assertIn("checked: 1 graphic still(s), 1 caption still(s); Premiere frames: not recorded", res["message"])
        write_json(self.p.p("08_quality_control/frames/boxes.json"),
                   {"frame": [1080, 1920], "boxes": [{"id": "PP1", "rect": [100, 300, 400, 400]}]})
        res = G.check(self.p, ["ig_reels_organic"])
        self.assertIn("Premiere frames: 1 box(es)", res["message"])
        self.switch_on()
        write_json(self.p.p("01_analysis/edit-decisions.json"), {"global": {"platforms": ["ig_reels_organic"]}})
        self.assertIn("checked: 1 graphic still(s)", G.qc_item(self.p)["detail"])


# --- K-T5 ------------------------------------------------------------------------------------------------------------
def layer(name, text, **kw):
    return {"name": name, "kind": "text", "text": text, **kw}


class TestReadbackUnitNotVerified(unittest.TestCase):
    def test_c1_an_arabic_layer_without_animators_is_not_verified(self):
        rb = {"scenes": [{"id": "S01", "layers": [layer("S01_text_1", "الضغط العالي"), layer("S01_text_2", "مرض صامت")]}]}
        f = AI.check_readback(rb)
        self.assertEqual([x["rule"] for x in f], ["readback_unit_unread"])
        self.assertEqual(f[0]["level"], "warning")
        self.assertIn("Not verified", f[0]["en"])
        self.assertIn("S01_text_1, S01_text_2", f[0]["en"])
        self.assertIn("وحدة حركة النص العربي ماترجعتش من After Effects", f[0]["ar"])

    def test_c2_c3_an_empty_list_or_a_latin_layer_is_read(self):
        rb = {"scenes": [{"id": "S01", "layers": [layer("S01_text_1", "الضغط", animators=[]),
                                                  layer("S01_text_2", "Hello")]}]}
        self.assertEqual(AI.check_readback(rb), [])

    def test_r1_null_or_unreadable_animators_and_missing_text_are_not_verified(self):
        for anims in (None, "x", [5, None], [{"name": "T"}], [{"based_on": 99}], [{"based_on": "words"}, {}]):
            with self.subTest(animators=anims):
                rb = {"scenes": [{"id": "S01", "layers": [layer("S01_text_1", "الضغط", animators=anims)]}]}
                self.assertEqual([x["rule"] for x in AI.check_readback(rb)], ["readback_unit_unread"])
        for ly in ({"name": "S01_text_1", "kind": "text"}, {"name": "S01_text_1", "kind": "text", "text": None},
                   {"kind": "text", "text": None}):
            with self.subTest(layer=ly):
                f = AI.check_readback({"scenes": [{"id": "S01", "layers": [ly]}]})
                self.assertEqual([x["rule"] for x in f], ["readback_unit_unread"])
        f = AI.check_readback({"scenes": [{"id": "S01", "layers": [{"kind": "text"}]}]})
        self.assertIn("(no name)", f[0]["en"])
        ok = {"scenes": [{"id": "S01", "layers": [layer("S01_text_1", "الضغط", animators=[{"based_on": 3}])]}]}
        self.assertEqual(AI.check_readback(ok), [])

    def test_c4_a_warning_alone_keeps_ok_and_an_error_still_fails(self):
        tmp = Path(tempfile.mkdtemp(prefix="kt5f_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        self.addCleanup(common.set_context, None)
        root = tmp / "د. تجربة Dr Test"
        (root / "data/Raw").mkdir(parents=True)
        (root / ".whynot-client").write_text("{}", encoding="utf-8")
        p = Paths(root, "C0001")
        common.set_context(root)
        from lib.motion_build import RESULT
        write_json(p.p(RESULT), {"status": "PROJECT_ASSEMBLED", "readback": {"scenes": [{"id": "S01", "layers": [
            layer("S01_text_1", "الضغط العالي")]}]}})
        rep = AI.run(p)
        self.assertTrue(rep["ok"])
        self.assertEqual([x["rule"] for x in rep["findings"]], ["readback_unit_unread"])
        write_json(p.p(RESULT), {"status": "PROJECT_ASSEMBLED", "readback": {"scenes": [{"id": "S01", "layers": [
            layer("S01_text_1", "الضغط العالي", animators=[{"name": "T", "based_on": 1}]),
            layer("S01_text_2", "مرض صامت")]}]}})
        rep = AI.run(p)
        self.assertFalse(rep["ok"])
        self.assertEqual(sorted(x["rule"] for x in rep["findings"]), ["readback_unit", "readback_unit_unread"])


if __name__ == "__main__":
    unittest.main()
