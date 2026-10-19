# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Manual verse slot, the other outputs: NEEDS-YOU (one line per span, the schema twin), previews, burned captions and
publish never hold the span's words; plus the executor's additions to needs_you.py: business and ai review rows get
their own kinds with the registry's approver, an unknown flag fails closed to medical.
The fixture verse is a placeholder (tests/fixtures/manual_verse/speech.json). Case ids: work/manual-verse/cases.md.
Run:  bash tools/test.sh -p test_manual_verse_outputs.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import common  # noqa: E402
from lib import schemas  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402
from test_manual_verse import (SC, VERSE, Base, build_words, decision, has_verse, verse_project,  # noqa: E402
                               verse_window, word_at)

LINE_AR = "أضف الآية يدويًا من مصحف موثوق ودقّق التشكيل"


def NY():
    from lib import needs_you
    return needs_you


class TestNeedsYouVerse(Base):
    def planned(self, words, **kw):
        root, p = verse_project(self.tmp, words, **kw)
        self.compile(p)
        return root, p

    def test_N1_one_line_per_span_and_the_twin_validates(self):
        w = build_words(SC["recited"])
        root, p = self.planned(w, flags={"سحاب", "مفتاح"})
        doc = NY().write(root)
        items = [i for i in doc["items"] if i["kind"] == "verse"]
        self.assertEqual(len(items), 1, doc["items"])
        it = items[0]
        self.assertIn(LINE_AR, it["text_ar"])
        self.assertIn("بعد: قال تعالى", it["text_ar"])
        self.assertIn("CLIP1", it["text_ar"])
        self.assertEqual((it["ref"], it["item"]), ("MV01", "CLIP1"))
        a, b = verse_window(w)
        self.assertEqual(it["span"]["src_start_ms"], a)
        self.assertEqual(it["span"]["src_end_ms"], b)
        self.assertFalse(it["span"]["guessed_end"])
        js = read_json(root / "output/needs-you.json")
        self.assertEqual(schemas.validate(js, "needs-you"), [])
        md = (root / "output/NEEDS-YOU.md").read_text(encoding="utf-8")
        self.assertLess(md.index("آيات يضيفها المونتير"), md.index("# Needs you"))     # Arabic first
        for text in (md, json.dumps(js, ensure_ascii=False)):
            self.assertEqual(has_verse(text), [])
        # N3: a flagged word inside the span is not listed to confirm by ear; one outside still is
        words_item = [i for i in doc["items"] if i["kind"] == "words"]
        self.assertEqual(len(words_item), 1, doc["items"])
        self.assertIn("مفتاح", words_item[0]["text_ar"])

    def test_N2_guessed_end(self):
        w = build_words("اهلا بيكم قال تعالى " + " ".join(VERSE * 8) + " |900 وده كلام جميل")
        root, _p = self.planned(w)
        it = [i for i in NY().collect(root)["items"] if i["kind"] == "verse"][0]
        self.assertTrue(it["span"]["guessed_end"])
        self.assertIn("متخمّنة", it["text_ar"])
        self.assertIn("guess", it["text"])

    def test_N3b_words_before_any_plan_skip_detected_spans(self):
        w = build_words(SC["recited"])
        root, p = verse_project(self.tmp, w, flags={"سحاب"})                 # transcribed, not planned yet
        doc = NY().collect(root)
        self.assertEqual([i for i in doc["items"] if i["kind"] == "words"], [])
        self.assertEqual(has_verse(json.dumps(doc, ensure_ascii=False)), [])

    def test_plain_client_no_verse_kind(self):
        root, _p = self.planned(build_words(SC["plain"]), domain=None)
        self.assertEqual([i for i in NY().collect(root)["items"] if i["kind"] == "verse"], [])


class TestNeedsYouReviewKinds(unittest.TestCase):
    """Executor addition A: needs_you mapped every review flag that was not medical or religious to «موافقة طبية»."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = Path(self._td.name) / "CL"
        for d in ("assets", "data"):
            (self.root / d).mkdir(parents=True)
        common.set_context(self.root)
        self.addCleanup(common.set_context, None)
        self.p = Paths(self.root, "C0001")
        self.p.ensure_project()
        write_json(self.p.p("review-flags.json"), {})

    def rows(self, flag):
        row = {"event_id": "G1", "flag": flag, "verdict": "needs-approval", "text": "كلام على الشاشة",
               "start_s": 1.0, "reason": ""}
        with mock.patch.object(NY(), "_review_rows", return_value=[row]):
            return NY().collect(self.root)["items"]

    def test_N4_business_row(self):
        from lib import review_domains
        appr = review_domains.registry()["business"]["approver"]
        items = self.rows("business")
        self.assertEqual([i["kind"] for i in items], ["business"])
        self.assertIn(appr["ar"], items[0]["text_ar"])
        self.assertIn(appr["en"], items[0]["text"])
        self.assertNotIn("طبية", items[0]["text_ar"])

    def test_N5_ai_row_and_approver_comes_from_the_registry(self):
        from lib import review_domains
        reg = review_domains.registry()
        items = self.rows("ai")
        self.assertEqual([i["kind"] for i in items], ["ai"])
        self.assertIn(reg["ai"]["approver"]["ar"], items[0]["text_ar"])
        changed = json.loads(json.dumps(reg))
        changed["ai"]["approver"] = {"ar": "المسؤول التجريبي", "en": "the test owner"}
        with mock.patch.object(review_domains, "registry", return_value=changed):
            items = self.rows("ai")
        self.assertIn("المسؤول التجريبي", items[0]["text_ar"])
        self.assertIn("the test owner", items[0]["text"])

    def test_N6_unknown_flag_fails_closed(self):
        items = self.rows("legal")
        self.assertEqual([i["kind"] for i in items], ["medical"])
        self.assertIn("موافقة طبية", items[0]["text_ar"])
        self.assertIn("legal", items[0]["why"])
        self.assertIn("legal", items[0]["why_ar"])

    def test_registry_unreadable_fails_closed(self):
        from lib import review_domains
        with mock.patch.object(review_domains, "registry", side_effect=ValueError("broken")):
            items = self.rows("business")
        self.assertEqual([i["kind"] for i in items], ["medical"])

    def test_schema_takes_the_new_kinds(self):
        for kind in ("business", "ai"):
            with mock.patch.object(NY(), "_review_rows", return_value=[
                    {"event_id": "G1", "flag": kind, "verdict": "needs-approval", "text": "x", "start_s": 1}]):
                doc = NY().write(self.root)
            self.assertEqual(schemas.validate(read_json(self.root / "output/needs-you.json"), "needs-you"), [])
            self.assertEqual(doc["counts"], {kind: 1})


class TestNeedsYouSchema(unittest.TestCase):
    def item(self, **kw):
        it = {"id": "0123456789ab", "kind": "verse", "text": "t", "why": "w", "ref": "MV01", "item": "C1",
              "source": "output/projects/C1/01_analysis/timeline-spec.json",
              "span": {"start_ms": 1, "end_ms": 2, "src_start_ms": 1, "src_end_ms": 2, "cue_ar": "بعد: قال تعالى",
                       "cue_en": "after «قال تعالى»", "guessed_end": False}}
        it.update(kw)
        return {"schema_version": 1, "client": "c", "items": [it], "counts": {"verse": 1}, "total": 1, "unread": [],
                "skipped": []}

    def test_verse_item_validates(self):
        self.assertEqual(schemas.validate(self.item(), "needs-you"), [])

    def test_span_is_closed(self):
        bad = self.item()
        bad["items"][0]["span"]["words"] = "x"
        self.assertNotEqual(schemas.validate(bad, "needs-you"), [])
        self.assertNotEqual(schemas.validate(self.item(kind="quran"), "needs-you"), [])


class TestPreviews(Base):
    def test_R1_caption_stills_hold_no_verse(self):
        w = build_words(SC["recited"])
        _root, p = verse_project(self.tmp, w)
        _res, spec = self.compile(p)
        from lib import previews
        caps = previews.render_captions(p, [])
        self.assertTrue(caps)
        for c in caps:
            self.assertEqual(has_verse(c["text"]), [], c)
        man = p.p("03_broll/captions/captions-manifest.json").read_text(encoding="utf-8")
        self.assertEqual(has_verse(man), [])

    def test_R1b_caption_looks_get_the_span_as_hidden(self):
        w = build_words(SC["recited"])
        _root, p = verse_project(self.tmp, w)
        _res, spec = self.compile(p)
        from lib import looks, looks_captions, previews
        seen = {}

        def fake(paths, res, hidden_ms, avoid=None, warnings=None):
            seen["hidden"] = list(hidden_ms)
            return []
        with mock.patch.object(looks, "resolve", return_value={"look": "clean", "source": "client"}), \
                mock.patch.object(looks_captions, "render_captions", side_effect=fake):
            previews.render_captions(p, [(1, 2)])
        mv = spec["manual_verse"][0]
        self.assertIn((1, 2), seen["hidden"])
        self.assertIn((mv["start_ms"], mv["end_ms"]), seen["hidden"])


class TestBurnedCaptions(Base):
    def test_R2_burned_caption_scan_writes_no_verse(self):
        import numpy as np
        from lib import burned_captions as bc
        w = build_words(SC["recited"])
        _root, p = verse_project(self.tmp, w)
        frames = np.zeros((8, 90, 160, 3), dtype=np.uint8)
        res = bc.detect(frames, w)
        f = bc.write_result(p, res, frames)
        self.assertEqual(has_verse(f.read_text(encoding="utf-8")), [])


class TestPublish(Base):
    def episode(self, pub: dict):
        from lib.episode import EpisodePaths
        from lib.transcribe import finalize
        w = build_words(SC["recited"])
        root = self.tmp / "CLIENT"
        for d in ("assets", "data"):
            (root / d).mkdir(parents=True, exist_ok=True)
        write_json(root / common.CLIENT_PROFILE_REL / "profile.json", {"domain": "religious"})
        common.set_context(root)
        ep = EpisodePaths(root, "EP12")
        ep.ensure_project()
        segs = [{"id": 1, "start_ms": w[0]["start_ms"], "end_ms": w[-1]["end_ms"], "text": " ".join(x["word"] for x in w),
                 "avg_logprob": -0.2, "no_speech_prob": 0.01, "compression_ratio": 1.2, "words": [x["id"] for x in w]}]
        finalize(ep, {"source_video": "x", "backend": "test", "model": "none", "language": "ar",
                      "language_probability": 1.0, "duration_ms": 60000}, segs, [dict(x) for x in w])
        write_json(ep.p("publish/publish.json"), pub)
        return ep

    def test_R3_episode_srt_and_copy(self):
        pub = {"youtube": {"titles": ["عنوان أول عن الصبر", "عنوان تاني «شجرة نهر جبل»", "عنوان تالت"],
                           "chapters": [{"at": "00:00", "title": "البداية"}, {"at": "00:20", "title": "الصبر"},
                                        {"at": "00:40", "title": "الخاتمة"}],
                           "description": {"hook": "حلقة عن الصبر", "summary": "كلام عن شجرة نهر جبل سحاب في الحلقة"}}}
        ep = self.episode(pub)
        from lib import publish
        res = publish.check(ep)
        verse_errs = [e for e in res["errors"] if "verse" in e]
        self.assertEqual(len(verse_errs), 2, res["errors"])
        self.assertTrue(any(e.startswith("title 2") for e in verse_errs), verse_errs)
        self.assertTrue(any(e.startswith("description") for e in verse_errs), verse_errs)
        for e in verse_errs:
            self.assertEqual(has_verse(e), [], e)
        srt = ep.p("publish/EP12.srt").read_text(encoding="utf-8")
        self.assertTrue(srt.strip())
        self.assertEqual(has_verse(srt), [])
        self.assertIn("الصبر", srt)

    def test_R3b_plain_copy_passes(self):
        pub = {"youtube": {"titles": ["عنوان أول عن الصبر", "عنوان تاني", "عنوان تالت"],
                           "description": {"hook": "حلقة عن «الصبر مفتاح كل خير»"}}}
        ep = self.episode(pub)
        from lib import publish
        res = publish.check(ep)
        self.assertEqual([e for e in res["errors"] if "verse" in e], [])


class TestGoldenUnchanged(unittest.TestCase):
    """A non-religious clip with no cue: `reel plan` output byte for byte as before (the golden plan of T2.17)."""

    def test_golden(self):
        import test_long_lived
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(test_long_lived.TestGoldenPlan)
        r = unittest.TestResult()
        suite.run(r)
        self.assertEqual((r.testsRun, r.failures, r.errors), (1, [], []))


if __name__ == "__main__":
    unittest.main()
