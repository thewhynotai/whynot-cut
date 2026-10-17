# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 23 (R-4.1), slice A: the caption-look catalog, the per-client preference and `pick`.
Spec: docs/superpowers/specs/addendum-h/source-r-specs/R-4.1-caption-looks.md (§1 Name, §5 Easier).
Run:  tools/test.sh -p test_looks.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib import looks  # noqa: E402
from lib.common import CLIENT_PROFILE_REL, read_json, write_json  # noqa: E402

EIGHT = {"word-clean", "word-boxed", "phrase-clean", "phrase-boxed", "phrase-highlight", "line-clean", "line-boxed",
         "line-highlight"}


def words_at(rate_wps: float, n: int = 30) -> list[dict]:
    """n spoken words at `rate_wps` words per second, no pauses."""
    step = 1000.0 / rate_wps
    return [{"id": i, "word": f"w{i}", "start_ms": int(i * step), "end_ms": int(i * step + step * 0.9)}
            for i in range(n)]


class ClientCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "CLIENT"
        (self.root / CLIENT_PROFILE_REL).mkdir(parents=True)
        common.set_context(self.root)
        self.addCleanup(common.set_context, None)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def style(self, data: dict):
        write_json(self.root / CLIENT_PROFILE_REL / "style.json", data)

    def style_file(self) -> Path:
        return self.root / CLIENT_PROFILE_REL / "style.json"


class TestCatalog(unittest.TestCase):
    def test_eight_looks_named_grouping_presentation(self):
        cat = looks.caption_catalog()
        self.assertEqual(set(cat["looks"]), EIGHT)
        for name, lk in cat["looks"].items():
            g, p = name.split("-")
            self.assertEqual((lk["grouping"], lk["presentation"]), (g, p))
            self.assertGreater(lk["size"], 0)

    def test_catalog_validates(self):
        self.assertEqual(looks.validate_catalog(looks.caption_catalog()), [])
        bad = looks.caption_catalog()
        bad["looks"]["phrase-clean"]["presentation"] = "outline"
        self.assertTrue(any("phrase-clean" in e for e in looks.validate_catalog(bad)))

    def test_word_highlight_resolves_to_word_boxed_with_a_note(self):
        r = looks.combine("word", "highlight", "colour")
        self.assertEqual(r["look"], "word-boxed")
        self.assertTrue(any("word-highlight" in n for n in r["notes"]))

    def test_colour_emphasis_on_the_moving_band_becomes_weight(self):
        r = looks.combine("phrase", "highlight", "colour")
        self.assertEqual(r["emphasis"], "weight")
        self.assertTrue(any("weight" in n for n in r["notes"]))
        self.assertEqual(looks.combine("phrase", "highlight", "tag")["emphasis"], "tag")

    def test_every_valid_combination_names_a_catalog_look(self):
        cat = looks.caption_catalog()
        for g in ("word", "phrase", "line"):
            for p in ("clean", "boxed", "highlight"):
                self.assertIn(looks.combine(g, p, "colour")["look"], cat["looks"])

    def test_task16_names_map_onto_the_new_looks(self):
        self.assertEqual(looks.legacy_look("clean"), "phrase-clean")
        self.assertEqual(looks.legacy_look("box"), "phrase-boxed")
        self.assertEqual(looks.legacy_look("highlight"), "phrase-highlight")
        self.assertEqual(looks.legacy_look("bold-large"), "line-clean")
        self.assertEqual(looks.legacy_look("line-boxed"), "line-boxed")      # a new name passes through
        with self.assertRaises(looks.LookError):
            looks.legacy_look("outline")

    def test_bold_large_keeps_its_large_size(self):
        cat = looks.caption_catalog()
        self.assertGreater(cat["looks"]["line-clean"]["size"], cat["looks"]["phrase-clean"]["size"])

    def test_motion_timings_are_ours(self):
        m = looks.caption_catalog()["motion"]
        self.assertEqual((m["enter_frames"], m["enter_scale_from"], m["exit_frames"], m["fps_base"]), (6, 0.96, 4, 30))
        self.assertEqual(m["enter_travel_px"], 0)          # a focus-in in place: never a vertical rise
        self.assertEqual(looks.frames(6, 60), 12)
        self.assertEqual(looks.frames(6, 24), 5)


class TestPalette(ClientCase):
    def tokens(self, roles: dict, derived: dict | None = None):
        write_json(self.root / "output/client_database/branding/brand-tokens.json",
                   {"roles": roles, "derived": derived or {}})

    def test_accent_falls_back_to_primary_and_highlight_to_accent(self):
        self.tokens({"primary": {"hex": "#123456"}})
        pal = looks.palette(self.root / "output/client_database")
        self.assertEqual(pal["accent"], (0x12, 0x34, 0x56))
        self.assertEqual(pal["highlight"], pal["accent"])

    def test_brand_roles_win(self):
        self.tokens({"primary": {"hex": "#123456"}, "accent": {"hex": "#E0A000"}, "highlight": {"hex": "#FFD400"}},
                    {"ink": {"hex": "#101010"}, "paper_tint": {"hex": "#F4F0E8"}})
        pal = looks.palette(self.root / "output/client_database")
        self.assertEqual((pal["accent"], pal["highlight"], pal["ink"], pal["paper"]),
                         ((0xE0, 0xA0, 0x00), (0xFF, 0xD4, 0x00), (0x10, 0x10, 0x10), (0xF4, 0xF0, 0xE8)))

    def test_no_database_uses_the_fallback_colours(self):
        pal = looks.palette(self.root / "output/client_database")
        self.assertEqual(set(pal), {"primary", "accent", "highlight", "ink", "paper", "white"})


class TestPreference(ClientCase):
    def test_no_saved_preference_means_todays_captions(self):
        r = looks.resolve(words=words_at(3.5))
        self.assertIsNone(r["look"])
        self.assertEqual(r["source"], "default")

    def test_fixed_values_win_over_auto(self):
        self.style({"captions": {"grouping": {"mode": "fixed", "value": "line"},
                                 "presentation": {"mode": "fixed", "value": "boxed"},
                                 "emphasis": {"mode": "fixed", "value": "tag"}}})
        r = looks.resolve(words=words_at(3.5))
        self.assertEqual((r["look"], r["emphasis"]), ("line-boxed", "tag"))
        self.assertEqual(r["sources"], {"grouping": "fixed", "presentation": "fixed", "emphasis": "fixed"})

    def test_auto_grouping_follows_the_speech_rate(self):
        self.style({"captions": {"grouping": {"mode": "auto"}}})
        self.assertEqual(looks.resolve(words=words_at(3.5))["grouping"], "phrase")
        self.assertEqual(looks.resolve(words=words_at(2.0))["grouping"], "line")
        self.assertEqual(looks.resolve(words=words_at(2.7))["grouping"], "phrase")
        r = looks.resolve(words=words_at(2.0))
        self.assertIn("2.0", r["reason"])                    # the one line says why
        self.assertEqual(r["sources"]["grouping"], "auto")

    def test_speech_rate_ignores_long_pauses(self):
        w = words_at(3.5, 10) + [dict(x, start_ms=x["start_ms"] + 20000, end_ms=x["end_ms"] + 20000)
                                 for x in words_at(3.5, 10)]
        self.assertAlmostEqual(looks.speech_rate(w), 3.5, delta=0.2)

    def test_reel_override_wins_and_never_changes_the_profile(self):
        self.style({"captions": {"grouping": {"mode": "fixed", "value": "line"}}})
        before = self.style_file().read_bytes()
        r = looks.resolve(words=words_at(3.5), override="word-boxed")
        self.assertEqual(r["look"], "word-boxed")
        self.assertEqual(r["sources"]["grouping"], "reel")
        r2 = looks.resolve(words=words_at(3.5), override={"emphasis": "weight"})
        self.assertEqual((r2["grouping"], r2["emphasis"]), ("line", "weight"))
        self.assertEqual(self.style_file().read_bytes(), before)

    def test_digit_set_is_a_client_choice(self):
        self.style({"captions": {"grouping": {"mode": "auto"}, "digits": "arabic_indic"}})
        self.assertEqual(looks.resolve(words=words_at(3.5))["digits"], "arabic_indic")
        self.style({"captions": {"grouping": {"mode": "auto"}}})
        self.assertEqual(looks.resolve(words=words_at(3.5))["digits"], "western")
        self.style({"captions": {"grouping": {"mode": "auto"}, "digits": "roman"}})
        r = looks.resolve(words=words_at(3.5))
        self.assertEqual(r["digits"], "western")
        self.assertTrue(any("roman" in n for n in r["notes"]))

    def test_a_whole_look_override_of_the_refused_combination_falls_back(self):
        self.style({"captions": {"grouping": {"mode": "auto"}}})
        r = looks.resolve(words=words_at(3.5), override="word-highlight")
        self.assertEqual(r["look"], "word-boxed")
        self.assertTrue(any("word-highlight" in n for n in r["notes"]))

    def test_unknown_values_are_reported_not_crashing(self):
        self.style({"captions": {"grouping": {"mode": "fixed", "value": "sentence"}}})
        r = looks.resolve(words=words_at(3.5))
        self.assertEqual(r["grouping"], "phrase")             # falls back to auto
        self.assertTrue(any("sentence" in n for n in r["notes"]))

    def test_motion_look_without_caption_motion(self):
        self.style({"captions": {"grouping": {"mode": "fixed", "value": "phrase"},
                                 "presentation": {"mode": "fixed", "value": "highlight"}}})
        r = looks.resolve(words=words_at(3.5), motion_look={"caption_motion": "none"})
        self.assertEqual(r["look"], "phrase-boxed")
        self.assertEqual(r["motion"]["entrance"], "none")
        r2 = looks.resolve(words=words_at(3.5))
        self.assertEqual((r2["look"], r2["motion"]["entrance"]), ("phrase-highlight", "focus_in"))


class TestPick(ClientCase):
    def test_pick_shows_a_diff_and_writes_only_with_yes(self):
        self.style({"native_caption_track": False, "captions_hidden_during": ["hook_title"]})
        before = self.style_file().read_bytes()
        res = looks.pick_preference("line-boxed", emphasis="tag", yes=False)
        self.assertFalse(res["written"])
        self.assertTrue(res["diff"])
        self.assertEqual(self.style_file().read_bytes(), before)
        res = looks.pick_preference("line-boxed", emphasis="tag", yes=True)
        self.assertTrue(res["written"])
        st = read_json(self.style_file())
        self.assertEqual(st["captions"]["grouping"], {"mode": "fixed", "value": "line"})
        self.assertEqual(st["captions"]["presentation"], {"mode": "fixed", "value": "boxed"})
        self.assertEqual(st["captions"]["emphasis"], {"mode": "fixed", "value": "tag"})
        self.assertEqual(st["captions_hidden_during"], ["hook_title"])      # other keys untouched
        self.assertIs(st["native_caption_track"], False)
        self.assertEqual(looks.resolve(words=words_at(3.5))["look"], "line-boxed")

    def test_pick_without_a_profile_file_creates_only_the_captions_block(self):
        res = looks.pick_preference("phrase-clean", yes=True)
        self.assertTrue(res["written"])
        self.assertEqual(set(read_json(self.style_file())), {"captions"})

    def test_pick_same_value_twice_has_no_diff(self):
        looks.pick_preference("phrase-clean", yes=True)
        res = looks.pick_preference("phrase-clean", yes=True)
        self.assertEqual(res["diff"], [])
        self.assertFalse(res["written"])

    def test_pick_accepts_task16_names_and_refuses_unknown(self):
        self.assertTrue(looks.pick_preference("box", yes=True)["written"])
        self.assertEqual(read_json(self.style_file())["captions"]["presentation"]["value"], "boxed")
        with self.assertRaises(looks.LookError):
            looks.pick_preference("outline", yes=True)

    def test_pick_never_writes_outside_the_reel_profile(self):
        looks.pick_preference("phrase-clean", yes=True)
        written = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())
        self.assertEqual(written, [f"{CLIENT_PROFILE_REL}/style.json"])

    def test_pick_keeps_json_readable_utf8(self):
        self.style({"note": "ستايل العميل"})
        looks.pick_preference("phrase-clean", yes=True)
        self.assertIn("ستايل العميل", self.style_file().read_text(encoding="utf-8"))
        json.loads(self.style_file().read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
