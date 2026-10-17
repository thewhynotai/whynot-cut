# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.2: style knobs that `reel plan` reads.

The client's `reel-profile/style.json` (defaults in config/defaults/style.json) and the reel's edit-decisions `global`
set four knobs that compile_plan resolves into the timeline-spec's `style` block:
  caption_size_px       caption size in px (reel > client > the highlight_caption template's size)
  captions_during_hook  "hide" (default: captions stay hidden under the hook title) | "show" (client level)
  hook_title_sfx        true (default: the hook title's own sound) | false (no sound on the hook title)
  highlight_colour      "brand" (default) | "accent" | "ink" | "#RRGGBB", checked for contrast (G68)
Defaults keep every output byte-identical (no `style` key). Adversarial case list: D:/ClaudeData/Temp/wnc-p4/t42/cases.md.
Run:  bash tools/test.sh -p test_t42_style_knobs.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import common  # noqa: E402
from lib.common import CLIENT_PROFILE_REL, read_json, write_json  # noqa: E402

TOKENS = {"roles": {"primary": {"hex": "#20ACAF"}, "neutral_light": {"hex": "#FFFFFF"}},
          "derived": {"paper_tint": {"hex": "#E6EEF8"}, "ink": {"hex": "#1E2A3B"}}}


def spec_body(spec: dict) -> dict:
    return {k: v for k, v in spec.items() if k not in ("generated", "engine_version")}


class KnobCase(unittest.TestCase):
    """One synthetic client (test_pipeline's fixture: Arabic speech, a hook_title, a checklist, a name card), compiled
    again for every test with its own style.json / edit-decisions."""

    @classmethod
    def setUpClass(cls):
        import test_pipeline as T
        from lib.client_db import build
        from lib.discover import run_discovery
        from lib.media import preflight
        cls._tmp = Path(tempfile.mkdtemp())
        cls.root, cls.p, _ = T.make_project(cls._tmp)
        build(cls.p, run_discovery(cls.p)["inventory"])
        preflight(cls.p, [cls.root / "data/Raw/CLIP1.mov"])
        write_json(cls.p.client_db / "branding/brand-tokens.json", TOKENS)
        cls.tc = T.TestPlanToXML()
        cls.tc.p = cls.p
        cls.tc._semantic_stub()
        cls.prof = cls.root / CLIENT_PROFILE_REL
        cls.prof.mkdir(parents=True, exist_ok=True)
        common.set_context(cls.root)

    @classmethod
    def tearDownClass(cls):
        common.set_context(None)
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def setUp(self):
        common.set_context(self.root)
        for f in ("style.json", "graphics-templates.json"):
            (self.prof / f).unlink(missing_ok=True)
        write_json(self.p.client_db / "branding/brand-tokens.json", TOKENS)

    # ------------------------------------------------------------------ helpers
    def style(self, data):
        write_json(self.prof / "style.json", data)

    def style_raw(self, raw: bytes):
        (self.prof / "style.json").write_bytes(raw)

    def compile(self, glob: dict | None = None, mutate=None) -> dict:
        from lib.plan import compile_plan
        ed = self.tc.decisions()
        ed["global"].update(glob or {})
        if mutate:
            mutate(ed)
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed)
        for f in ("01_analysis/timeline-spec.json", "06_audio/audio-cue-sheet.json"):
            self.p.p(f).unlink(missing_ok=True)
        return compile_plan(self.p)

    def spec(self) -> dict:
        return read_json(self.p.p("01_analysis/timeline-spec.json"))

    def cues(self) -> list:
        return read_json(self.p.p("06_audio/audio-cue-sheet.json"))["cues"]

    def ok(self, r):
        self.assertTrue(r["ok"], r.get("errors"))
        return r

    def baseline(self) -> dict:
        (self.prof / "style.json").unlink(missing_ok=True)
        self.ok(self.compile())
        return spec_body(self.spec())


# ====================================================================== A. defaults byte-identical
class TestDefaultsUnchanged(KnobCase):
    def test_a1_no_style_json_no_style_block_and_the_hook_pop_stays(self):
        self.ok(self.compile())
        self.assertNotIn("style", self.spec())
        self.assertTrue(any(c.get("related_visual") == "GFX_001" for c in self.cues()))

    def test_a2_every_knob_at_its_default_changes_nothing(self):
        from lib.plan import plan_fingerprint
        base = self.baseline()
        fp = plan_fingerprint(self.p)
        warn0 = read_json(self.p.p("01_analysis/plan-validation.json"))["warnings"]
        self.style({"caption_size_px": None, "captions_during_hook": "hide", "hook_title_sfx": True,
                    "highlight_colour": "brand"})
        r = self.ok(self.compile())
        self.assertEqual(spec_body(self.spec()), base)
        self.assertEqual(plan_fingerprint(self.p), fp)
        self.assertEqual(r["warnings"], warn0)

    def test_a2b_shipped_defaults_file_holds_the_knobs_at_their_defaults(self):
        d = read_json(SK / "config/defaults/style.json")
        self.assertIsNone(d["caption_size_px"])
        self.assertEqual(d["captions_during_hook"], "hide")
        self.assertIs(d["hook_title_sfx"], True)
        self.assertEqual(d["highlight_colour"], "brand")

    def test_a3_caption_size_equal_to_the_template_size_is_no_change(self):
        base = self.baseline()
        size = common.load_config("graphics-templates.json")["templates"]["highlight_caption"]["size"]
        self.style({"caption_size_px": size})
        self.ok(self.compile())
        self.assertEqual(spec_body(self.spec()), base)

    def test_a4_default_caption_stills_identical_with_and_without_a_default_style_json(self):
        from lib.previews import render_captions
        self.ok(self.compile())
        before = {Path(c[k]).name: Path(c[k]).read_bytes() for c in render_captions(self.p, []) for k in ("fg", "bar")
                  if c.get(k)}
        self.style({"caption_size_px": None, "highlight_colour": "brand"})
        self.ok(self.compile())
        after = {Path(c[k]).name: Path(c[k]).read_bytes() for c in render_captions(self.p, []) for k in ("fg", "bar")
                 if c.get(k)}
        self.assertEqual(before, after)

    def test_a5_caption_hide_default_unchanged_without_the_knob(self):
        today = list(read_json(SK / "config/defaults/style.json")["captions_hidden_during"])
        self.assertEqual(common.caption_hide_default(), today)
        self.style({"captions_during_hook": "hide"})
        self.assertEqual(common.caption_hide_default(), today)
        self.assertIn("hook_title", common.caption_hide_default())


# ====================================================================== B. each knob -> a different spec
class TestEachKnobChangesTheSpec(KnobCase):
    def test_b1_caption_size(self):
        self.style({"caption_size_px": 80})
        self.ok(self.compile())
        st = self.spec()["style"]
        self.assertEqual(st["caption_size_px"], 80)
        self.assertEqual(st["sources"]["caption_size_px"], "client")

    def test_b2_captions_during_hook_show(self):
        self.style({"captions_during_hook": "show"})
        self.ok(self.compile())
        self.assertEqual(self.spec()["style"]["captions_during_hook"], "show")
        self.assertNotIn("hook_title", common.caption_hide_default(self.spec()))
        self.assertIn("checklist", common.caption_hide_default(self.spec()))   # the other graphics still hide captions

    def test_b3_hook_title_sfx_off(self):
        base_cues = (self.baseline(), self.cues())[1]
        self.style({"hook_title_sfx": False})
        self.ok(self.compile())
        self.assertIs(self.spec()["style"]["hook_title_sfx"], False)
        cues = self.cues()
        self.assertFalse(any(c.get("related_visual") == "GFX_001" for c in cues))
        others = [c["cue_id"] for c in base_cues if c.get("related_visual") != "GFX_001"]
        self.assertEqual([c["cue_id"] for c in cues], others)                 # every other cue is kept

    def test_b4_highlight_colour(self):
        self.style({"highlight_colour": "#1E2A3B"})
        self.ok(self.compile())
        hl = self.spec()["style"]["highlight"]
        self.assertEqual(hl["policy"], "#1E2A3B")
        self.assertEqual(hl["hex"], "#1E2A3B")
        self.assertFalse(hl["adjusted"])

    def test_b5_four_knobs_four_different_specs_and_fingerprints(self):
        from lib.plan import plan_fingerprint
        self.baseline()
        seen = {plan_fingerprint(self.p)}
        for st in ({"caption_size_px": 80}, {"captions_during_hook": "show"}, {"hook_title_sfx": False},
                   {"highlight_colour": "#1E2A3B"}):
            self.style(st)
            self.ok(self.compile())
            seen.add(plan_fingerprint(self.p))
        self.assertEqual(len(seen), 5)


# ====================================================================== C. precedence
class TestPrecedence(KnobCase):
    def test_c1_reel_size_beats_client(self):
        self.style({"caption_size_px": 80})
        self.ok(self.compile({"caption_size_px": 90}))
        st = self.spec()["style"]
        self.assertEqual((st["caption_size_px"], st["sources"]["caption_size_px"]), (90, "reel"))

    def test_c2_reel_size_alone(self):
        self.ok(self.compile({"caption_size_px": 90}))
        self.assertEqual(self.spec()["style"]["caption_size_px"], 90)

    def test_c3_reel_sfx_on_beats_client_off(self):
        self.style({"hook_title_sfx": False})
        self.ok(self.compile({"hook_title_sfx": True}))
        self.assertNotIn("style", self.spec())
        self.assertTrue(any(c.get("related_visual") == "GFX_001" for c in self.cues()))

    def test_c4_the_graphics_own_sfx_beats_the_knob(self):
        self.style({"hook_title_sfx": False})

        def own(ed):
            ed["decisions"][0]["graphics"][0]["sfx"] = "whoosh"
        self.ok(self.compile(mutate=own))
        hook = [c for c in self.cues() if c.get("related_visual") == "GFX_001"]
        self.assertEqual([c["kind"] for c in hook], ["whoosh"])

    def test_c5_reel_highlight_beats_client(self):
        self.style({"highlight_colour": "#1E2A3B"})
        self.ok(self.compile({"highlight_colour": "#000000"}))
        hl = self.spec()["style"]["highlight"]
        self.assertEqual((hl["policy"], self.spec()["style"]["sources"]["highlight_colour"]), ("#000000", "reel"))

    def test_c6_client_file_beats_the_shipped_profile(self):
        from unittest import mock
        shipped = self._tmp / "shipped-profiles"                               # never the plugin's own profiles/
        (shipped / "t42-probe").mkdir(parents=True, exist_ok=True)
        write_json(shipped / "t42-probe" / "style.json", {"caption_size_px": 70, "hook_title_sfx": False})
        write_json(self.prof / "profile.json", {"id": "t42-probe"})
        self.addCleanup((self.prof / "profile.json").unlink, True)
        patch = mock.patch.object(common, "PROFILES_DIR", shipped)
        patch.start()
        self.addCleanup(patch.stop)
        self.ok(self.compile())
        st = self.spec()["style"]
        self.assertEqual(st["caption_size_px"], 70)                       # from the shipped profile
        self.assertIs(st["hook_title_sfx"], False)
        self.style({"caption_size_px": 84})
        self.ok(self.compile())
        self.assertEqual(self.spec()["style"]["caption_size_px"], 84)     # the client's own file wins

    def test_c7_a_reel_hide_list_with_the_hook_wins_over_client_show(self):
        self.style({"captions_during_hook": "show"})
        r = self.ok(self.compile({"captions_hidden_during": ["hook_title", "checklist"]}))
        self.assertNotIn("captions_during_hook", self.spec().get("style", {}))
        self.assertEqual(sum("captions_during_hook" in w for w in r["warnings"]), 1, r["warnings"])


# ====================================================================== D. missing / empty / damaged
class TestDamagedStyleFile(KnobCase):
    def test_d1_empty_object_is_the_defaults(self):
        base = self.baseline()
        self.style({})
        self.ok(self.compile())
        self.assertEqual(spec_body(self.spec()), base)

    def test_d2_d3_empty_or_invalid_json_is_a_file_format_refusal_naming_style_json(self):
        from lib.errors import FileFormatError
        for raw in (b"", b'{"caption_size_px": 80,}'):
            self.style_raw(raw)
            with self.assertRaises(FileFormatError) as cm:
                self.compile()
            self.assertIn("style.json", cm.exception.path)

    def test_d4_utf8_bom_and_crlf_are_read(self):
        self.style_raw(b"\xef\xbb\xbf{\r\n  \"caption_size_px\": 76\r\n}\r\n")
        self.ok(self.compile())
        self.assertEqual(self.spec()["style"]["caption_size_px"], 76)

    def test_d5_not_an_object_warns_and_compiles_with_defaults(self):
        base = self.baseline()
        for bad in ([], "big", 5):
            self.style(bad)
            r = self.ok(self.compile())
            self.assertTrue(any("style.json" in w and "not an object" in w for w in r["warnings"]), (bad, r["warnings"]))
            self.assertEqual(spec_body(self.spec()), base)

    def test_d6_caption_hide_default_with_a_non_object_style(self):
        self.style([1, 2])
        self.assertEqual(common.caption_hide_default(), list(common.CAPTION_HIDE_SAFE))
        self.assertEqual(common.caption_hide_default({"style": "junk"}), list(common.CAPTION_HIDE_SAFE))


# ====================================================================== E. unknown keys / types / ranges
class TestBadValues(KnobCase):
    def test_e1_other_tracks_keys_are_ignored_silently(self):
        base = self.baseline()
        warn0 = read_json(self.p.p("01_analysis/plan-validation.json"))["warnings"]
        self.style({"camera": {"ease_ms": 250}, "fades": {"video_in_ms": 0}, "export": {"name": "x"},
                    "captions": {"digits": "western"}, "remove_pauses": None, "zz_future": 1})
        r = self.ok(self.compile())
        self.assertEqual(spec_body(self.spec()), base)
        self.assertEqual(r["warnings"], warn0)

    def test_e2_a_near_miss_of_a_knob_name_gets_a_hint(self):
        self.style({"caption_size": 80})
        r = self.ok(self.compile())
        self.assertTrue(any("caption_size" in w and "caption_size_px" in w for w in r["warnings"]), r["warnings"])
        self.assertNotIn("style", self.spec())

    def test_e2b_american_spelling_is_accepted(self):
        self.style({"highlight_color": "#1E2A3B"})
        self.ok(self.compile())
        self.assertEqual(self.spec()["style"]["highlight"]["hex"], "#1E2A3B")

    def test_e3_e4_e5_bad_sizes_warn_in_style_json_and_fail_in_edit_decisions(self):
        base = self.baseline()
        for bad in ("big", True, 10, 500, -5, 0, [], {"px": 80}):
            self.style({"caption_size_px": bad})
            r = self.ok(self.compile())
            self.assertTrue(any("caption_size_px" in w and "style.json" in w for w in r["warnings"]), (bad, r["warnings"]))
            self.assertEqual(spec_body(self.spec()), base, bad)
            (self.prof / "style.json").unlink()
            r = self.compile({"caption_size_px": bad})
            self.assertFalse(r["ok"], bad)
            self.assertTrue(any("global.caption_size_px" in e for e in r["errors"]), (bad, r["errors"]))
        r = self.compile({"caption_size_px": 500})
        self.assertTrue(any("32" in e and "140" in e for e in r["errors"]), r["errors"])     # the range is named

    def test_e6_size_is_a_whole_number_like_the_schema(self):
        """Review #6: the engine says what `reel validate` says: an integer (72.0 counts), never a string or 72.5."""
        from lib import schemas
        self.style({"caption_size_px": 72.0})
        self.ok(self.compile())
        self.assertEqual(self.spec()["style"]["caption_size_px"], 72)
        for bad in (72.5, "88"):
            self.style({"caption_size_px": bad})
            r = self.ok(self.compile())
            self.assertTrue(any("caption_size_px" in w and "whole number" in w for w in r["warnings"]), (bad, r["warnings"]))
            self.assertNotIn("style", self.spec())
            (self.prof / "style.json").unlink()
            r = self.compile({"caption_size_px": bad})
            self.assertFalse(r["ok"], bad)
            self.assertTrue(schemas.validate({"global": {"caption_size_px": bad}, "decisions": []}, "edit-decisions"),
                            bad)

    def test_e6b_nan_and_infinity_are_refused(self):
        self.style_raw(b'{"caption_size_px": NaN}')
        r = self.ok(self.compile())
        self.assertTrue(any("caption_size_px" in w for w in r["warnings"]))
        self.style_raw(b'{"caption_size_px": Infinity}')
        r = self.ok(self.compile())
        self.assertTrue(any("caption_size_px" in w for w in r["warnings"]))

    def test_e7_bad_hook_mode_warns_and_hides(self):
        for bad in ("maybe", 1, []):
            self.style({"captions_during_hook": bad})
            r = self.ok(self.compile())
            self.assertTrue(any("captions_during_hook" in w for w in r["warnings"]), (bad, r["warnings"]))
            self.assertNotIn("style", self.spec())
            self.assertIn("hook_title", common.caption_hide_default(self.spec()))

    def test_e7b_show_is_case_insensitive(self):
        self.style({"captions_during_hook": " Show "})
        self.ok(self.compile())
        self.assertEqual(self.spec()["style"]["captions_during_hook"], "show")
        self.assertNotIn("hook_title", common.caption_hide_default(self.spec()))

    def test_e7c_a_reel_value_for_the_hook_mode_is_not_read_and_says_how(self):
        r = self.ok(self.compile({"captions_during_hook": "show"}))
        self.assertTrue(any("captions_hidden_during" in w for w in r["warnings"]), r["warnings"])
        self.assertNotIn("style", self.spec())

    def test_e8_sound_is_true_or_false_only(self):
        """Review #6: a bool, like the schema; "on" / "off" are refused too."""
        for word, on in ((False, False), (True, True)):
            self.style({"hook_title_sfx": word})
            self.ok(self.compile())
            self.assertEqual("style" not in self.spec(), on, word)
        for bad in ("off", "on", "yes", 0, 1, "nope"):
            self.style({"hook_title_sfx": bad})
            r = self.ok(self.compile())
            self.assertTrue(any("hook_title_sfx" in w for w in r["warnings"]), bad)
            self.assertNotIn("style", self.spec())
            (self.prof / "style.json").unlink()
            r = self.compile({"hook_title_sfx": bad})
            self.assertFalse(r["ok"], bad)
            self.assertTrue(any("global.hook_title_sfx" in e for e in r["errors"]), r["errors"])

    def test_e9_e10_bad_colours(self):
        for bad in ("gold", "#12345", "#GGGGGG", 7, "ذهبي", "", [], "bad", "facade", "ABCDEF", "000"):
            self.style({"highlight_colour": bad})
            r = self.ok(self.compile())
            self.assertTrue(any("highlight_colour" in w and "#RRGGBB" in w for w in r["warnings"]), (bad, r["warnings"]))
            self.assertNotIn("style", self.spec())
            (self.prof / "style.json").unlink()
            r = self.compile({"highlight_colour": bad})
            self.assertFalse(r["ok"], bad)
            self.assertTrue(any("global.highlight_colour" in e for e in r["errors"]), r["errors"])

    def test_e9b_short_and_lower_case_hex_are_normalised(self):
        self.style({"highlight_colour": "#1e2a3b"})
        self.ok(self.compile())
        self.assertEqual(self.spec()["style"]["highlight"]["hex"], "#1E2A3B")
        self.style({"highlight_colour": "#000"})
        self.ok(self.compile())
        self.assertEqual(self.spec()["style"]["highlight"]["policy"], "#000000")

    def test_e9c_schema_accepts_the_reel_knobs(self):
        from lib import schemas
        good = {"global": {"caption_size_px": 90, "hook_title_sfx": False, "highlight_colour": "#1E2A3B"},
                "decisions": []}
        self.assertEqual(schemas.validate(good, "edit-decisions"), [])
        bad = schemas.validate({"global": {"caption_size_px": 900}, "decisions": []}, "edit-decisions")
        self.assertEqual([e["path"] for e in bad], ["/global/caption_size_px"])


# ====================================================================== F. hook cases
class TestHookCases(KnobCase):
    @staticmethod
    def no_hook(ed):
        ed["decisions"][0]["graphics"] = []

    def test_f1_no_hook_title_compiles_and_records_the_client_choice(self):
        self.style({"captions_during_hook": "show", "hook_title_sfx": False})
        self.ok(self.compile(mutate=self.no_hook))
        st = self.spec()["style"]
        self.assertEqual((st["captions_during_hook"], st["hook_title_sfx"]), ("show", False))
        self.assertTrue(self.cues())                                            # the checklist's cues stay

    def test_f2_hook_with_no_caption_under_it(self):
        self.style({"captions_during_hook": "show"})

        def late_hook(ed):                                                      # a hook over a silent stretch
            g = ed["decisions"][0]["graphics"][0]
            g["start"], g["end"] = "00:00:00.000", "00:00:00.150"
        self.ok(self.compile(mutate=late_hook))
        self.assertEqual(self.spec()["style"]["captions_during_hook"], "show")

    def test_f3_hook_longer_than_the_reel_is_the_existing_duration_error(self):
        self.style({"hook_title_sfx": False, "captions_during_hook": "show"})

        def long_hook(ed):
            ed["decisions"][0]["graphics"][0]["end"] = "00:00:30.000"
        r = self.compile(mutate=long_hook)
        self.assertFalse(r["ok"])
        self.assertTrue(any("GFX_001" in e and "outside media duration" in e for e in r["errors"]), r["errors"])

    def test_f4_two_hook_titles_both_lose_their_sound(self):
        self.style({"hook_title_sfx": False})

        def two(ed):
            ed["decisions"][1]["graphics"][0] = {"id": "GFX_002", "template": "hook_title", "start": "00:00:05.000",
                                                 "end": "00:00:08.000", "text": "أول حاجة"}
        self.ok(self.compile(mutate=two))
        self.assertFalse(any(c.get("related_visual") in ("GFX_001", "GFX_002") for c in self.cues()))

    def test_f5_sfx_off_with_words_cut_on_the_sequence_clock(self):
        self.style({"hook_title_sfx": False})
        self.ok(self.compile({"cut_words": [3]}))
        self.assertIsNotNone(self.spec()["time_map"])
        self.assertFalse(any(c.get("related_visual") == "GFX_001" for c in self.cues()))


# ====================================================================== G. highlight colour + G68
class TestHighlightContrast(KnobCase):
    def test_g1_gold_behind_white_text_is_adjusted_with_a_warning(self):
        self.style({"highlight_colour": "#E0B76B"})
        r = self.ok(self.compile())
        hl = self.spec()["style"]["highlight"]
        self.assertTrue(hl["adjusted"])
        self.assertEqual(hl["from_hex"], "#E0B76B")
        self.assertEqual(hl["hex"], "#1E2A3B")                                  # brand ink reads best behind white
        self.assertGreaterEqual(hl["contrast"], hl["need"])
        w = [x for x in r["warnings"] if "#E0B76B" in x]
        self.assertEqual(len(w), 1, r["warnings"])
        self.assertIn("contrast", w[0])
        self.assertIn("#1E2A3B", w[0])

    def test_g2_a_dark_colour_passes_without_a_warning(self):
        self.style({"highlight_colour": "#1E2A3B"})
        r = self.ok(self.compile())
        self.assertFalse(any("#1E2A3B" in w for w in r["warnings"]))

    def test_g3_the_threshold_follows_the_caption_size(self):
        grey = "#898989"                                                        # about 3.5:1 against white
        self.style({"highlight_colour": grey, "caption_size_px": 80})            # large text: 3:1 is enough
        self.ok(self.compile())
        self.assertFalse(self.spec()["style"]["highlight"]["adjusted"])
        self.style({"highlight_colour": grey, "caption_size_px": 52})            # 52 px needs 4.5:1
        self.ok(self.compile())
        self.assertTrue(self.spec()["style"]["highlight"]["adjusted"])

    def test_g4_nothing_better_keeps_the_colour_and_says_it_is_low(self):
        grey = {"hex": "#777777"}
        write_json(self.p.client_db / "branding/brand-tokens.json",
                   {"roles": {"primary": grey, "neutral_light": grey}, "derived": {"paper_tint": grey, "ink": grey}})
        self.style({"highlight_colour": "#787878"})
        r = self.ok(self.compile())
        hl = self.spec()["style"]["highlight"]
        self.assertFalse(hl["adjusted"])
        self.assertEqual(hl["hex"], "#787878")
        self.assertTrue(any("#787878" in w and "below" in w for w in r["warnings"]), r["warnings"])

    def test_g5_accent_and_ink_roles(self):
        self.style({"highlight_colour": "accent"})
        r = self.ok(self.compile())
        self.assertEqual(self.spec()["style"]["highlight"]["policy"], "accent")
        self.assertTrue(any("accent" in w and "primary" in w for w in r["warnings"]), r["warnings"])  # no accent role
        tok = copy.deepcopy(TOKENS)
        tok["roles"]["accent"] = {"hex": "#0B3D2E"}
        write_json(self.p.client_db / "branding/brand-tokens.json", tok)
        self.ok(self.compile())
        self.assertEqual(self.spec()["style"]["highlight"]["hex"], "#0B3D2E")
        self.style({"highlight_colour": "ink"})
        self.ok(self.compile())
        self.assertEqual(self.spec()["style"]["highlight"]["hex"], "#1E2A3B")

    def test_g6_the_check_uses_the_templates_caption_text_colour(self):
        write_json(self.prof / "graphics-templates.json", {"templates": {"highlight_caption": {"text_role": "ink"}}})
        self.style({"highlight_colour": "#1E2A3B"})                             # ink text on an ink box: unreadable
        r = self.ok(self.compile())
        hl = self.spec()["style"]["highlight"]
        self.assertEqual(hl["text_hex"], "#1E2A3B")
        self.assertTrue(hl["adjusted"])
        self.assertNotEqual(hl["hex"], "#1E2A3B")

    def test_g7_default_brand_is_never_checked(self):
        warn0 = (self.baseline(), read_json(self.p.p("01_analysis/plan-validation.json"))["warnings"])[1]
        self.style({"highlight_colour": "brand"})              # the teal primary is only 2.8:1 behind white
        r = self.ok(self.compile())
        self.assertEqual(r["warnings"], warn0)


# ====================================================================== H. Arabic captions drawn with the knobs
def _bbox_h(png: Path) -> int:
    from PIL import Image
    with Image.open(png) as im:
        bb = im.getchannel("A").getbbox()
    return 0 if not bb else bb[3] - bb[1]


class TestArabicCaptionStills(KnobCase):
    def setUp(self):
        super().setUp()
        import test_motion as M
        font = M.test_font()                     # a machine font with Arabic glyphs (the sandbox has no fallback)
        if font is None:
            self.skipTest("no Arabic-capable test font on this machine")
        typ = self.p.client_db / "branding/typography.json"
        old = typ.read_bytes() if typ.exists() else None
        self.addCleanup(lambda: typ.write_bytes(old) if old is not None else typ.unlink(missing_ok=True))
        write_json(typ, {"families": {"Test": {"weights": [
            {"style": s, "file": str(font), "postscript_name": "ArialMT"} for s in ("black", "bold", "medium", "regular")]}},
            "roles": {r: {"postscript_name": "ArialMT"} for r in ("caption", "headline", "body", "term", "small")}})

    def render(self):
        from lib.previews import render_captions
        return render_captions(self.p, [])

    def test_h1_arabic_caption_still_grows_with_the_caption_size(self):
        self.ok(self.compile())
        caps = self.render()
        h0 = _bbox_h(Path(caps[0]["fg"]))
        if h0 < 20:                                # Pillow's bitmap font does not scale: nothing to measure
            self.skipTest("no scalable font drew the caption on this machine")
        words0 = " ".join(c["text"] for c in caps).split()
        h0 = max(_bbox_h(Path(c["fg"])) for c in caps)
        self.style({"caption_size_px": 110})                    # the captions are regrouped into shorter lines
        self.ok(self.compile())
        caps = self.render()
        self.assertEqual(" ".join(c["text"] for c in caps).split(), words0)     # logical order, same words
        self.assertGreater(max(_bbox_h(Path(c["fg"])) for c in caps), h0 * 1.4)

    def test_h2_the_keyword_box_takes_the_highlight_colour(self):
        from PIL import Image
        self.style({"highlight_colour": "#0B3D2E"})
        self.ok(self.compile())
        bars = [Path(c["bar"]) for c in self.render() if c.get("highlight") and c.get("bar")]
        self.assertTrue(bars)
        with Image.open(bars[0]) as im:
            px = [p[:3] for p in im.convert("RGBA").getdata() if p[3] == 255]
        self.assertTrue(px)
        self.assertGreater(sum(1 for p in px if p == (0x0B, 0x3D, 0x2E)) / len(px), 0.9)

    def test_h3_ae_caption_data_carries_the_size(self):
        from lib.ae_builder import caption_data
        self.style({"caption_size_px": 96})
        self.ok(self.compile())
        self.assertEqual(caption_data(self.p, self.spec(), read_json(self.p.p("01_analysis/edit-decisions.json")))["size"], 96)

    # ---------------------------------------------------------------- review #2: size vs wrapping
    LINES = {"ar": ["هل في حاجات معينة لازم أبقى عارفاها قبل الليزر", "أول حاجة التشخيص الصحيح قبل أي علاج"],
             "en": ["Laser is not permanent hair removal it is reduction", "First comes the right diagnosis always"]}

    def caption_srt(self, lines):
        from lib import srt as srtlib
        f = self.p.p("02_transcription/captions-short.srt")
        old = f.read_bytes()
        self.addCleanup(f.write_bytes, old)
        srtlib.write_srt(f, [{"start_ms": 4000 + i * 2000, "end_ms": 5800 + i * 2000, "text": t}
                             for i, t in enumerate(lines)])

    def test_r2a_max_chars_scale_with_the_size(self):
        self.style({"caption_size_px": 140})
        self.ok(self.compile())
        st = self.spec()["style"]
        self.assertEqual(st["caption_max_chars"], 13)                          # floor(30 * 62 / 140)
        self.assertEqual(st["caption_short_max_chars"], 8)                     # floor(18 * 62 / 140) = 7 -> minimum 8
        self.style({"caption_size_px": 100})
        self.ok(self.compile())
        self.assertEqual(self.spec()["style"]["caption_max_chars"], 18)        # floor(30 * 62 / 100)

    def test_r2b_arabic_and_english_lines_stay_in_the_frame_at_62_100_140(self):
        W, safe = 1080, (90, 990)
        for lang, lines in self.LINES.items():
            self.caption_srt(lines)                              # 62 px (the template's size) keeps this file
            self.words(" ".join(lines))                          # a chosen size rebuilds captions from the words
            for size in (62, 100, 140):
                self.style({"caption_size_px": size})
                r = self.ok(self.compile())
                caps = self.render()
                self.assertTrue(caps, (lang, size))
                warned = any("safe width" in w and not w.startswith("After Effects") for w in r["warnings"])
                for c in caps:
                    from PIL import Image
                    with Image.open(c["fg"]) as im:
                        bb = im.getchannel("A").getbbox()
                    self.assertGreaterEqual(bb[0], 0, (lang, size, c["text"]))
                    self.assertLessEqual(bb[2], W, (lang, size, c["text"]))
                    if not warned:                                              # no warning: it fits the safe width
                        self.assertGreaterEqual(bb[0], safe[0] - 6, (lang, size, c["text"], bb))
                        self.assertLessEqual(bb[2], safe[1] + 6, (lang, size, c["text"], bb))

    def test_r2c_a_line_wider_than_the_safe_width_is_a_plan_warning(self):
        self.words("Isotretinoin-hydrochloride-solution هل في حاجات")
        self.style({"caption_size_px": 140})
        r = self.ok(self.compile())
        w = [x for x in r["warnings"] if "safe width" in x and not x.startswith("After Effects")]
        self.assertEqual(len(w), 1, r["warnings"])
        self.assertIn("Isotretinoin", w[0])
        self.assertIn("caption_size_px", w[0])

    def test_r2d_rebuilt_short_captions_use_the_scaled_length(self):
        from lib import srt as srtlib

        def n_cues(style):
            self.style(style)
            self.ok(self.compile({"cut_words": [3]}))
            return len(srtlib.read_srt(self.p.p("02_transcription/captions-short-seq.srt")))
        self.assertGreater(n_cues({"caption_size_px": 140}), n_cues({}))

    # ---------------------------------------------------------------- follow-up: every build, and After Effects
    WORDS = {"ar": "هل في حاجات معينة لازم أبقى عارفاها قبل الليزر أول حاجة التشخيص الصحيح قبل أي علاج",
             "en": "Laser is not permanent hair removal it is reduction first comes the right diagnosis always"}

    def words(self, text):
        import test_pipeline as T
        f = self.p.p("02_transcription/words.json")
        old = f.read_bytes()
        self.addCleanup(f.write_bytes, old)
        write_json(f, {"words": T.words_from(text.split(), 200, 600)})

    def test_r2e_short_captions_scale_without_cut_words_ar_and_en_at_140(self):
        from lib import srt as srtlib
        for lang, text in self.WORDS.items():
            self.words(text)
            self.style({})
            self.ok(self.compile())
            self.assertEqual(self.spec()["caption_source"], "02_transcription/captions-short.srt")   # default: as today
            from lib.transcribe import caption_cues
            n0 = len(caption_cues(read_json(self.p.p("02_transcription/words.json"))["words"],
                                  common.load_config("subtitle-style.json"))[1])   # these words at today's length
            self.style({"caption_size_px": 140})
            self.ok(self.compile())                                              # no cut words, no pause removal
            spec = self.spec()
            self.assertIsNone(spec["time_map"])
            self.assertEqual(spec["caption_source"], "02_transcription/captions-short-seq.srt", lang)
            cues = srtlib.read_srt(self.p.p(spec["caption_source"]))
            self.assertGreater(len(cues), n0, lang)
            for c in cues:                                                       # 8 chars, or one longer word
                self.assertTrue(len(c["text"]) <= 8 + 6 or len(c["text"].split()) == 1, (lang, c["text"]))
            from lib.ae_builder import caption_data                              # After Effects gets the same cues
            ae = caption_data(self.p, spec, read_json(self.p.p("01_analysis/edit-decisions.json")))
            self.assertEqual(ae["size"], 140)
            words = read_json(self.p.p("02_transcription/words.json"))["words"]
            expected = [q["text"] for q in caption_cues(words, dict(common.load_config("subtitle-style.json"),
                                                                     short_max_chars=8))[1]]
            self.assertEqual([c["text"] for c in cues], expected, lang)         # the SRT = the words at 8 chars
            ae_texts = [c["text"].replace("\r", "\n") for c in ae["cues"]]
            self.assertTrue(ae_texts, lang)
            rest = iter(c["text"] for c in cues)                                 # AE: the same cues, in order (those
            self.assertTrue(all(t in rest for t in ae_texts), (lang, ae_texts))  # under a graphic are left out)

    # ---------------------------------------------------------------- review e0bf821 minors
    def test_m1_after_effects_width_is_measured_on_the_raw_line(self):
        # After Effects draws the SRT text as it is: punctuation the Premiere stills strip still takes room there
        write_json(self.prof / "graphics-templates.json", {"templates": {"highlight_caption": {
            "strip_punctuation": "abcdefghijklmnopqrstuvwxyz"}}})
        self.words("Isotretinoin-hydrochloride-solution works")
        self.style({"caption_size_px": 140})
        r = self.ok(self.compile())
        ae = [w for w in r["warnings"] if w.startswith("After Effects") and "safe width" in w]
        self.assertEqual(len(ae), 1, r["warnings"])
        self.assertIn("Isotretinoin-hydrochloride-solution", ae[0])

    def hand_edit(self):
        from lib import srt as srtlib
        f = self.p.p("02_transcription/captions-short.srt")
        old = f.read_bytes()
        self.addCleanup(f.write_bytes, old)
        cues = srtlib.read_srt(f)
        cues[0]["text"] = cues[0]["text"] + " تصحيح"                            # the editor fixed a word by hand
        srtlib.write_srt(f, cues)

    def test_m2_hand_edited_short_captions_replaced_by_a_rebuild_are_a_warning(self):
        r = self.ok(self.compile())                                               # no size: the file is used, no warning
        self.assertFalse([w for w in r["warnings"] if "captions-short.srt" in w])
        self.style({"caption_size_px": 140})
        r = self.ok(self.compile())                                               # unedited file: nothing lost
        self.assertFalse([w for w in r["warnings"] if "captions-short.srt" in w], r["warnings"])
        self.hand_edit()
        r = self.ok(self.compile())
        w = [x for x in r["warnings"] if "captions-short.srt" in x]
        self.assertEqual(len(w), 1, r["warnings"])
        self.assertTrue(w[0].startswith("تعديلاتك"), w[0])                       # Arabic first, then English
        self.assertIn("your hand edits in captions-short.srt are not used", w[0])
        self.assertIn("transcript", w[0])
        self.style({})                                                            # the cut-words path too
        r = self.ok(self.compile({"cut_words": [3]}))
        self.assertEqual(len([x for x in r["warnings"] if "captions-short.srt" in x]), 1, r["warnings"])

    def test_m2b_a_spelling_only_hand_fix_is_seen_too(self):
        # «اللى»→«اللي», «ة»→«ه», a hamza seat: the plan's matching normaliser folds these, the hand-edit check must not
        from lib import srt as srtlib
        f = self.p.p("02_transcription/captions-short.srt")
        old = f.read_bytes()
        self.addCleanup(f.write_bytes, old)
        cues = srtlib.read_srt(f)
        swap = {"ي": "ى", "ى": "ي", "ة": "ه", "ه": "ة", "أ": "ا", "إ": "ا", "ا": "أ"}
        i, t = next((i, c["text"]) for i, c in enumerate(cues) if any(ch in swap for ch in c["text"]))
        k = next(j for j, ch in enumerate(t) if ch in swap)
        cues[i]["text"] = t[:k] + swap[t[k]] + t[k + 1:]
        srtlib.write_srt(f, cues)
        self.style({"caption_size_px": 140})
        r = self.ok(self.compile())
        self.assertEqual(len([x for x in r["warnings"] if "captions-short.srt" in x]), 1, r["warnings"])

    def test_m3a_empty_words_with_a_size_falls_back_to_the_srt(self):
        f = self.p.p("02_transcription/words.json")
        old = f.read_bytes()
        self.addCleanup(f.write_bytes, old)
        write_json(f, {"words": []})
        self.style({"caption_size_px": 140})
        self.ok(self.compile())
        self.assertEqual(self.spec()["caption_source"], "02_transcription/captions-short.srt")
        self.assertEqual(self.spec()["style"]["caption_size_px"], 140)
        self.assertTrue(self.render())                                            # today's captions still drawn

    def test_m3b_pause_removal_only_with_a_size(self):
        from lib import srt as srtlib
        f = self.p.p("06_audio/dialogue/pauses.json")
        f.parent.mkdir(parents=True, exist_ok=True)
        self.addCleanup(f.unlink, True)
        write_json(f, {"keep_ms": [[0, 5000], [6000, 12000]], "cuts_ms": [[5000, 6000]], "removed_ms": 1000,
                       "source_duration_ms": 12000})
        glob = {"remove_pauses": {"min_pause_ms": 250, "pad_ms": 80}}
        from lib.transcribe import caption_cues
        self.ok(self.compile(glob))
        texts0 = [c["text"] for c in srtlib.read_srt(self.p.p("02_transcription/captions-short-seq.srt"))]
        self.style({"caption_size_px": 140})
        self.ok(self.compile(glob))
        spec = self.spec()
        self.assertEqual(spec["caption_source"], "02_transcription/captions-short-seq.srt")
        self.assertEqual(spec["time_map"]["removed_ms"], 1000)
        cues = srtlib.read_srt(self.p.p(spec["caption_source"]))
        words = read_json(self.p.p("02_transcription/words.json"))["words"]
        scaled = caption_cues(words, dict(common.load_config("subtitle-style.json"), short_max_chars=8))[1]
        expected = [q["text"] for q in scaled if not (5000 <= q["start_ms"] and q["end_ms"] <= 6000)]
        self.assertEqual([c["text"] for c in cues], expected)                     # rebuilt at 8 chars, pause cut out
        self.assertNotEqual([c["text"] for c in cues], texts0)
        self.assertLessEqual(max(c["end_ms"] for c in cues), spec["duration_ms"] + 40)   # on the sequence clock

    def test_m3c_mixed_arabic_and_english_line(self):
        from lib import srt as srtlib
        self.words("التشخيص الصحيح قبل Isotretinoin مهم جداً للبشرة")
        self.style({"caption_size_px": 140})
        r = self.ok(self.compile())
        cues = srtlib.read_srt(self.p.p(self.spec()["caption_source"]))
        self.assertIn("Isotretinoin", [w for c in cues for w in c["text"].split()])   # the Latin term stays whole
        self.assertEqual(" ".join(c["text"] for c in cues).split(),
                         "التشخيص الصحيح قبل Isotretinoin مهم جداً للبشرة".split())  # logical order kept
        for c in self.render():
            from PIL import Image
            with Image.open(c["fg"]) as im:
                bb = im.getchannel("A").getbbox()
            self.assertTrue(0 <= bb[0] and bb[2] <= 1080, (c["text"], bb))
        self.assertTrue(isinstance(r["warnings"], list))

    def test_m3d_a_word_without_id_or_start_is_skipped_with_a_warning(self):
        import test_pipeline as T
        f = self.p.p("02_transcription/words.json")
        old = f.read_bytes()
        self.addCleanup(f.write_bytes, old)
        ws = T.words_from("هل في حاجات معينة لازم أبقى".split(), 200, 600)
        del ws[1]["id"]
        del ws[3]["start_ms"]
        write_json(f, {"words": ws})
        for style in ({}, {"caption_size_px": 140}):
            self.style(style)
            r = self.ok(self.compile())                                           # no KeyError, with or without a size
            w = [x for x in r["warnings"] if "words.json" in x]
            self.assertEqual(len(w), 1, r["warnings"])
            self.assertIn(": 2 word(s)", w[0])                                    # two words skipped
            self.assertTrue(w[0].startswith("في 2 كلمة في words.json ناقصة (من غير رقم أو الكلمة أو التوقيت)، "
                                            "ومش هتتحسب في الكابشن ولا في القص"), w[0])  # Arabic first, whole sentence
            unchecked = [x for x in r["warnings"] if "can't be checked" in x]
            # only a rebuild (a chosen size) replaces captions-short.srt, so only then is the skipped check worth saying
            self.assertEqual(len(unchecked), 1 if style else 0, r["warnings"])

    def test_r2f_after_effects_one_line_wider_than_the_safe_width_is_a_plan_warning(self):
        self.words("Isotretinoin-hydrochloride-solution works")
        self.style({"caption_size_px": 140})
        r = self.ok(self.compile())
        ae = [w for w in r["warnings"] if "After Effects" in w and "safe width" in w]
        self.assertEqual(len(ae), 1, r["warnings"])
        self.assertIn("Isotretinoin", ae[0])
        self.words(self.WORDS["ar"])
        r = self.ok(self.compile())
        self.assertFalse([w for w in r["warnings"] if "After Effects" in w and "safe width" in w], r["warnings"])


# ====================================================================== I/K. motion plans and caption looks
class TestOtherTracks(KnobCase):
    def test_k1_knobs_never_switch_on_a_caption_look(self):
        try:
            from lib import looks
        except ImportError:
            self.skipTest("caption looks (Task 23) not in this tree")
        st = {"caption_size_px": 80, "captions_during_hook": "show", "hook_title_sfx": False, "highlight_colour": "#000000"}
        self.assertIsNone(looks.resolve(style=st)["look"])

    def test_k2_spec_key_is_style_never_captions(self):
        self.style({"caption_size_px": 80})
        self.ok(self.compile())
        self.assertIn("style", self.spec())
        self.assertNotIn("captions", self.spec())


class TestReviewFixes(KnobCase):
    def test_r1_builders_take_the_hook_mode_from_the_compiled_spec(self):
        from lib.ae_builder import caption_data
        self.style({"captions_during_hook": "show"})
        self.ok(self.compile())
        spec = self.spec()
        ed = read_json(self.p.p("01_analysis/edit-decisions.json"))
        self.style({"captions_during_hook": "hide"})                          # changed after the plan: no re-plan
        self.assertNotIn("hook_title", common.caption_hide_default(spec))
        self.style({"captions_during_hook": "show"})
        self.assertIn("hook_title", common.caption_hide_default())            # no spec: never the live knob
        self.assertIn("hook_title", common.caption_hide_default({}))
        show = caption_data(self.p, spec, ed)
        self.style({})
        self.ok(self.compile())
        hide = caption_data(self.p, self.spec(), ed)
        under = lambda d: [c for c in d["cues"] if c["start_frame"] < 84]      # the hook title ends at frame 84
        self.assertGreater(len(under(show)), len(under(hide)))
        self.assertEqual(under(hide), [])

    def test_r4_alias_only_when_the_same_file_has_no_highlight_colour(self):
        self.style({"highlight_colour": "#000000", "highlight_color": "#1E2A3B"})
        self.ok(self.compile())
        self.assertEqual(self.spec()["style"]["highlight"]["hex"], "#000000")

    def test_r4b_an_explicit_null_is_not_set_and_still_blocks_the_alias_in_that_file(self):
        self.style({"highlight_colour": None, "highlight_color": "#1E2A3B"})
        r = self.ok(self.compile())
        self.assertNotIn("style", self.spec())                                  # null = not set; the alias is ignored
        self.assertTrue(any("highlight_color" in w and "highlight_colour" in w for w in r["warnings"]), r["warnings"])
        self.style({"highlight_color": None})
        r = self.ok(self.compile())
        self.assertNotIn("style", self.spec())
        self.style({"caption_size_px": None, "hook_title_sfx": None})            # null = not set for every knob
        self.ok(self.compile())
        self.assertNotIn("style", self.spec())

    def test_r7_the_contrast_warning_names_the_file_the_colour_came_from(self):
        self.style({"highlight_colour": "#E0B76B"})
        r = self.ok(self.compile())
        w = [x for x in r["warnings"] if "#E0B76B" in x]
        self.assertTrue(w and "reel-profile/style.json" in w[0], r["warnings"])
        (self.prof / "style.json").unlink()
        r = self.ok(self.compile({"highlight_colour": "#E0B76B"}))
        w = [x for x in r["warnings"] if "#E0B76B" in x]
        self.assertTrue(w and "edit-decisions" in w[0] and "style.json" not in w[0], r["warnings"])

    def test_r9_show_is_recorded_only_when_the_hook_title_was_hidden(self):
        self.style({"captions_hidden_during": ["checklist", "broll_card"], "captions_during_hook": "show"})
        self.ok(self.compile())
        self.assertNotIn("style", self.spec())                                  # nothing changes: no stale approval


class TestSkillText(unittest.TestCase):
    """L1: the knobs are reachable from the skills (client-craft for the client, the story-craft reference for one
    reel, revise for a standing comment)."""
    KNOBS = ("caption_size_px", "captions_during_hook", "hook_title_sfx", "highlight_colour")

    def read(self, rel):
        return " ".join((SK / "skills" / rel).read_text(encoding="utf-8").split())

    def test_client_craft_explains_every_knob(self):
        s = self.read("client-craft/SKILL.md")
        for k in self.KNOBS:
            self.assertIn(f"`{k}`", s, k)
        self.assertIn("never inside its `captions` block", s)

    def test_story_craft_names_the_reel_overrides(self):
        s = self.read("story-craft/references/edit-decision-engine.md")
        for k in ("caption_size_px", "hook_title_sfx", "highlight_colour"):
            self.assertIn(f"`{k}`", s, k)
        self.assertIn("captions_hidden_during", s)

    def test_revise_maps_standing_comments_to_the_knobs_in_both_languages(self):
        s = self.read("revise/SKILL.md")
        for k in self.KNOBS:
            self.assertIn(k, s, k)
        self.assertIn("«الكابشن أكبر»", s)

    def test_r10_show_under_the_hook_is_honest_about_premiere(self):
        for rel in ("client-craft/SKILL.md", "revise/SKILL.md"):
            s = self.read(rel)
            self.assertIn("After Effects captions follow it now", s, rel)
            self.assertIn("Premiere captions follow it after the next WhyNot Cut update", s, rel)

    def test_m2b_a_chosen_size_rebuilds_captions_from_the_transcript_words(self):
        self.assertIn("A chosen caption size rebuilds the captions from the transcript words",
                      self.read("client-craft/SKILL.md"))

    def test_r3_the_highlight_colour_is_premiere_only_for_now(self):
        for rel in ("client-craft/SKILL.md", "story-craft/references/edit-decision-engine.md"):
            s = self.read(rel)
            self.assertIn("After Effects captions use the brand colour for now", s, rel)

    def test_r8_hook_knob_client_only_and_the_reel_list_replaces_the_whole_list(self):
        self.assertIn("client setting only", self.read("revise/SKILL.md"))
        s = self.read("story-craft/references/edit-decision-engine.md")
        self.assertIn("replaces the client's whole list", s)
        self.assertIn("an empty `[]` falls back to the client's list", s)


class TestMotionPlansIgnoreTheKnobs(unittest.TestCase):
    def test_i1_motion_plan_output_is_unchanged(self):
        import test_motion as M
        if M.test_font() is None:
            self.skipTest("no test font for HarfBuzz fitting")
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.addCleanup(common.set_context, None)
        root, ep, reel = M.motion_plan_fixture(tmp)
        common.set_context(root)
        from lib.motion_plan import compile_motion
        write_json(reel.p("01_analysis/motion-script.json"), M.good_script())

        def body():
            compile_motion(reel)
            d = read_json(reel.p("01_analysis/motion-plan.json")) or {}
            return json.dumps({k: v for k, v in d.items() if k not in ("generated", "engine_version")}, sort_keys=True)
        before = body()
        write_json(root / CLIENT_PROFILE_REL / "style.json", {"caption_size_px": 110, "captions_during_hook": "show",
                                                               "hook_title_sfx": False, "highlight_colour": "#E0B76B"})
        self.assertEqual(body(), before)


if __name__ == "__main__":
    unittest.main()
