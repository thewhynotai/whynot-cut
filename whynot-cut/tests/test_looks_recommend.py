# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 28 (R-4.6): the look recommender.

Caption looks: score = 3 x fit[content type][look] + 2 x reference match + 1 x delivery fit, no recent-use penalty and
no variety rule (the brand stays consistent). Motion looks (Phase 6 fills the catalogue): the same score minus the
recent-use penalty, the hard variety rule, only accepted looks auto-picked, playful looks never on medical or religious
content. Every table comes from config/defaults/looks/recommender.json; these tests read the numbers from it.
Adversarial case list: .superpowers/sdd/2026-10-16-3.0-track-looks/task-28-plan.md (R1-R15).
Run:  bash tools/test.sh -p test_looks_recommend.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import copy
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

import test_looks_captions as TLC  # noqa: E402  the client fixture with the repo fonts (ClipCase), W()
from lib import looks  # noqa: E402
from lib import looks_recommend as LR  # noqa: E402
from lib.common import CLIENT_PROFILE_REL, Paths, read_json, write_json  # noqa: E402

INTERNAL = ("score", "vector", "penalty", "cosine", "fit[", "ref_match", "delivery", "trait", "weight", "energy")


def words_at(rate: float, n: int = 24) -> list[dict]:
    """n words at `rate` words per second, no pauses."""
    step = int(round(1000 / rate))
    return [{"id": i, "word": "كلمة", "start_ms": i * step, "end_ms": i * step + step - 40} for i in range(n)]


class RecCase(TLC.ClipCase):
    """A client (repo fonts, brand roles) and one clip; helpers set its content type, speech, references, history."""

    def setUp(self):
        super().setUp()
        self.cat = LR.catalog()

    def content(self, ctype, paths=None):
        write_json((paths or self.paths).p("00_inputs/source.json"),
                   {"kind": "episode_reel", "content_type": ctype, "recipe": {"type": ctype}})

    def speech(self, rate, paths=None):
        write_json((paths or self.paths).p("02_transcription/words.json"), {"meta": {}, "words": words_at(rate)})

    def refs(self, cpms=None, raw=None, style=None):
        p = self.paths.client_db / "reference_analysis" / "reference-measurements.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        if raw is not None:
            p.write_text(raw, encoding="utf-8")
        elif cpms is not None:
            write_json(p, {"references": [{"video": f"r{i}.mp4", "cuts_per_minute": c} for i, c in enumerate(cpms)]})
        if style is not None:
            write_json(self.paths.client_db / "reference_style" / "editing-style.json", style)

    def style(self, captions):
        write_json(self.root / CLIENT_PROFILE_REL / "style.json", {"captions": captions})

    def reel(self, vid, created, choice=None, raw=None):
        """Another reel of this client, created at `created` (ISO), with its recorded look choice."""
        p = Paths(self.root, vid)
        p.ensure_project()
        write_json(p.p("08_quality_control/project-status.json"), {"video_id": vid, "created": created})
        if raw is not None:
            p.p("01_analysis/look-choice.json").write_text(raw, encoding="utf-8")
        elif choice is not None:
            write_json(p.p("01_analysis/look-choice.json"), choice)
        return p

    def rec(self, kind="caption", **kw):
        kw.setdefault("stills", False)
        return LR.recommend(self.paths, kind=kind, **kw)

    # an independent computation of the caption score from the catalogue (R2)
    def expected_caption(self, ctype, rate, energy=None, density=None, weight=None):
        c, w = self.cat["caption"], self.cat["weights"]
        band = "fast" if rate >= self.cat["rate_bands"]["fast"] else "slow" if rate <= self.cat["rate_bands"]["slow"] \
            else "medium"
        out = {}
        for name in c["order"]:
            fit = c["fit"].get(ctype, {}).get(name, self.cat["neutral"]) if ctype in c["fit"] else self.cat["neutral"]
            tr = c["traits"][name]
            if energy is None:
                ref = self.cat["neutral"]
            else:
                parts = [1 - abs(tr["energy"] - energy)]
                lv = {"low": 0, "medium": 1, "high": 2, "light": 0, "regular": 1, "heavy": 2}
                m = self.cat["match"]
                for key, want in (("caption_density", density), ("text_weight", weight)):
                    if want is not None:
                        d = abs(lv[tr[key]] - lv[want])
                        parts.append(m["same"] if d == 0 else m["next"] if d == 1 else m["far"])
                ref = sum(parts) / len(parts)
            grouping = looks.caption_catalog()["looks"][name]["grouping"]
            out[name] = (w["fit"] * fit + w["ref"] * ref + w["delivery"] * c["delivery"][grouping][band], fit)
        order = c["order"]
        return sorted(out, key=lambda n: (-round(out[n][0], 6), -out[n][1], order.index(n))), out


class TestCatalogue(unittest.TestCase):
    def test_the_tables_name_every_caption_look_and_only_those(self):
        cat = LR.catalog()
        names = set(looks.caption_catalog()["looks"])
        self.assertEqual(set(cat["caption"]["order"]), names)
        self.assertEqual(set(cat["caption"]["traits"]), names)
        self.assertEqual(set(cat["caption"]["display"]), names)
        for ctype, row in cat["caption"]["fit"].items():
            self.assertEqual(set(row), names, ctype)
            self.assertTrue(all(0 <= v <= 1 for v in row.values()), ctype)

    def test_an_unknown_look_in_a_table_is_reported_not_used(self):
        bad = copy.deepcopy(LR.catalog())
        bad["caption"]["fit"]["advice"]["phrase-glow"] = 1.0
        with self.assertRaises(LR.RecommendError) as e:
            LR.validate(bad)
        self.assertIn("phrase-glow", str(e.exception))

    def test_every_recipe_content_type_has_a_fit_row_and_both_languages_name_it(self):
        from lib import recipes
        cat = LR.catalog()
        for t in recipes.types():
            self.assertIn(t, cat["caption"]["fit"], t)
            for lang in ("ar", "en"):
                self.assertIn(t, cat["reason"][lang]["types"], (lang, t))


class TestCaption(RecCase):
    def test_same_inputs_give_the_same_answer_for_every_content_type(self):        # R1
        self.speech(2.8)
        for ctype in list(self.cat["caption"]["fit"]) + [None]:
            if ctype:
                self.content(ctype)
            else:
                self.paths.p("00_inputs/source.json").unlink(missing_ok=True)
            a, b = self.rec(), self.rec()
            self.assertEqual(a, b, ctype)
            self.assertIn(a["pick"], self.cat["caption"]["order"])

    def test_the_pick_and_top_three_follow_the_formula(self):                     # R2
        for ctype, rate in (("advice", 2.0), ("comedy", 3.6), ("emotional", 2.7), ("medical_claim", 3.4)):
            self.content(ctype)
            self.speech(rate)
            order, scores = self.expected_caption(ctype, rate)
            r = self.rec()
            self.assertEqual(r["pick"], order[0], ctype)
            self.assertEqual([t["look"] for t in r["top"]], order[:3], ctype)
            for t in r["top"]:
                self.assertAlmostEqual(t["score"], scores[t["look"]][0], places=3)

    def test_an_ordinary_clip_has_no_content_type_and_its_line_says_only_the_pace(self):   # R3
        self.speech(3.6)
        order, _ = self.expected_caption(None, 3.6)
        r = self.rec()
        self.assertEqual(r["pick"], order[0])
        ar = self.cat["reason"]["ar"]
        self.assertEqual(r["reason"], ar["caption_rate"].format(look=self.cat["caption"]["display"][r["pick"]],
                                                                  rate=ar["rates"]["fast"]))

    def test_an_unknown_content_type_is_neutral_and_never_named(self):            # R4
        self.content("cooking_show")
        self.speech(2.8)
        r = self.rec()
        order, _ = self.expected_caption(None, 2.8)
        self.assertEqual(r["pick"], order[0])
        self.assertNotIn("cooking", r["reason"])

    def test_reference_videos_move_the_pick_and_bad_files_are_neutral(self):      # R5
        self.content("advice")
        self.speech(2.8)
        neutral = self.rec()
        self.refs(cpms=[30, 32, 29])                    # fast cutting: energy 1
        order, _ = self.expected_caption("advice", 2.8, energy=1.0)
        self.assertEqual(self.rec()["pick"], order[0])
        self.refs(cpms=[30, 32, 29], style={"caption_density": "high", "text_weight": "heavy"})
        order, _ = self.expected_caption("advice", 2.8, energy=1.0, density="high", weight="heavy")
        self.assertEqual(self.rec()["pick"], order[0])
        for raw in ("{not json", json.dumps({"references": []}), json.dumps({"references": [{"video": "x"}]}),
                    json.dumps([1, 2])):
            self.refs(raw=raw)
            write_json(self.paths.client_db / "reference_style" / "editing-style.json", {})
            self.assertEqual(self.rec()["pick"], neutral["pick"], raw)

    def test_a_fixed_choice_or_a_reel_override_wins_with_no_scoring(self):        # R6
        self.content("comedy")
        self.speech(3.6)
        self.style({"grouping": {"mode": "fixed", "value": "line"}, "presentation": {"mode": "fixed", "value": "boxed"}})
        r = self.rec()
        self.assertEqual((r["pick"], r["source"]), ("line-boxed", "client"))
        self.assertIn("line-boxed", r["reason"])
        write_json(self.paths.p("01_analysis/edit-decisions.json"), {"global": {"caption_look": "box"}})
        r = self.rec()
        self.assertEqual((r["pick"], r["source"]), ("phrase-boxed", "reel"))
        write_json(self.paths.p("01_analysis/edit-decisions.json"), {"global": {"caption_look": "word-highlight"}})
        self.assertEqual(self.rec()["pick"], "word-boxed")

    def test_a_partly_fixed_choice_scores_only_the_looks_that_match_it(self):
        self.content("comedy")
        self.speech(3.6)
        self.style({"presentation": {"mode": "fixed", "value": "boxed"}})
        r = self.rec()
        self.assertTrue(all(t["look"].endswith("-boxed") for t in r["top"]), r["top"])
        order, _ = self.expected_caption("comedy", 3.6)
        self.assertEqual(r["pick"], [n for n in order if n.endswith("-boxed")][0])

    def test_caption_looks_stay_the_same_reel_after_reel(self):                    # R7
        self.content("advice")
        self.speech(2.8)
        picks = []
        for k in range(5):
            r = self.rec()
            picks.append(r["pick"])
            LR.record_choice(self.paths, "caption", r["pick"], "recommender")
            self.reel(f"PAST{k}", f"2026-10-0{k + 1}T10:00:00", {"caption": {"look": r["pick"]}})
        self.assertEqual(len(set(picks)), 1, picks)

    def test_the_line_is_plain_one_line_and_in_the_editors_language(self):        # R12
        self.content("advice")
        self.speech(2.0)
        r = self.rec()
        line = r["reason"]
        self.assertNotIn("\n", line)
        self.assertTrue(all(t not in line.lower() for t in INTERNAL), line)
        self.assertIn(self.cat["caption"]["display"][r["pick"]], line)
        self.assertIn(self.cat["reason"]["ar"]["types"]["advice"], line)
        en = self.rec(lang="en")["reason"]
        self.assertIn(self.cat["reason"]["en"]["types"]["advice"], en)
        self.assertTrue(all(t not in en.lower() for t in INTERNAL), en)
        self.assertFalse(any(ch.isdigit() for ch in line.replace(self.cat["caption"]["display"][r["pick"]], "")))

    def test_the_top_three_carry_a_still_each_and_never_touch_broll(self):        # R13
        self.content("advice")
        self.speech(2.8)
        before = sorted(p.name for p in self.paths.p("03_broll").rglob("*"))
        r = LR.recommend(self.paths, kind="caption", stills=True)
        self.assertEqual(len(r["top"]), 3)
        for t in r["top"]:
            self.assertTrue(Path(t["still"]).exists(), t)
            self.assertIn("caption-looks", Path(t["still"]).parts)
        self.assertEqual(sorted(p.name for p in self.paths.p("03_broll").rglob("*")), before)


class TestEntry(RecCase):
    def test_the_spec_entry_point_is_looks_recommend(self):
        self.content("advice")
        self.speech(2.8)
        self.assertEqual(looks.recommend(self.paths, kind="caption", stills=False), self.rec())


class TestCaptionRobust(RecCase):
    def test_malformed_inputs_count_as_absent(self):
        self.content("advice")
        self.speech(2.8)
        base = self.rec()["pick"]
        for raw in (json.dumps({"references": 5}), json.dumps({"references": "x"}), json.dumps({"references": [None, 3]})):
            self.refs(raw=raw)
            self.assertEqual(self.rec()["pick"], base, raw)
        write_json(self.paths.p("02_transcription/words.json"),
                   {"words": [{"word": "a"}, {"word": "b", "start_ms": None, "end_ms": 5}, {"word": "c", "start_ms": 0}]})
        r = self.rec()                                   # no usable timing: the pace is unknown, never "slow"
        self.assertEqual(r["reason"], self.cat["reason"]["ar"]["caption_type"].format(
            look=self.cat["caption"]["display"][r["pick"]], type=self.cat["reason"]["ar"]["types"]["advice"],
            rate=self.cat["reason"]["ar"]["rates"]["medium"]))

    def test_a_reel_override_given_as_axes_is_honoured(self):
        self.content("comedy")
        self.speech(3.6)
        write_json(self.paths.p("01_analysis/edit-decisions.json"),
                   {"global": {"caption_look": {"grouping": "line", "presentation": "boxed"}}})
        r = self.rec()
        self.assertEqual((r["pick"], r["source"]), ("line-boxed", "reel"))
        write_json(self.paths.p("01_analysis/edit-decisions.json"), {"global": {"caption_look": {"presentation": "boxed"}}})
        r = self.rec()
        self.assertTrue(all(t["look"].endswith("-boxed") for t in r["top"]), r["top"])

    def test_a_clients_own_look_or_content_type_scores_neutral_with_a_warning(self):
        self.content("cooking_show")
        self.speech(2.8)
        cc = copy.deepcopy(looks.caption_catalog())
        cc["looks"]["phrase-glow"] = dict(cc["looks"]["phrase-clean"])
        write_json(self.root / CLIENT_PROFILE_REL / "looks" / "recommender.json",
                   {"caption": {"fit": {"cooking_show": {"phrase-glow": 1.0}}}})
        with mock.patch.object(looks, "caption_catalog", return_value=cc):
            r = self.rec()
        self.assertEqual(r["pick"], "phrase-glow")                # the client's own look is scored, and can win
        self.assertTrue(any("phrase-glow" in w for w in r["warnings"]), r["warnings"])
        (self.root / CLIENT_PROFILE_REL / "looks" / "recommender.json").unlink()
        write_json(self.root / CLIENT_PROFILE_REL / "looks" / "recommender.json",       # a profile's partial row
                   {"caption": {"fit": {"cooking_show": {"phrase-clean": 1.0}}}})
        r = self.rec()
        self.assertEqual(r["pick"], "phrase-clean")
        self.assertTrue(any("cooking_show" in w for w in r["warnings"]), r["warnings"])

    def test_the_stills_never_overwrite_the_editors_gallery_sheet_and_pass_warnings_on(self):
        self.content("advice")
        self.speech(2.8)
        from lib import looks_captions
        res = looks_captions.render(self.paths)
        sheet = Path(res["sheet"])
        before = sheet.read_bytes()
        r = LR.recommend(self.paths, kind="caption", stills=True)
        self.assertEqual(sheet.read_bytes(), before)
        self.assertIn("warnings", r)
        with mock.patch.object(looks_captions, "render", return_value={"looks": [], "warnings": ["no text engine"]}):
            r = LR.recommend(self.paths, kind="caption", stills=True)
        self.assertIn("no text engine", r["warnings"])

    def test_an_unknown_reel_override_is_noted_and_scored_as_usual(self):
        self.content("advice")
        self.speech(2.8)
        r = self.rec(override="phrase-glow")
        self.assertEqual(r["source"], "recommender")
        self.assertIn(self.cat["reason"]["ar"]["override_unknown"].format(look="phrase-glow"), r["notes"])

    def test_an_invalid_axis_in_a_reel_override_is_noted_and_ignored(self):
        self.content("advice")
        self.speech(2.8)
        r = self.rec(override={"grouping": "huge", "presentation": "boxed"})
        self.assertIn(self.cat["reason"]["ar"]["override_unknown"].format(look="huge"), r["notes"])
        self.assertTrue(all(t["look"].endswith("-boxed") for t in r["top"]), r["top"])

    def test_a_clients_own_grouping_scores_a_neutral_delivery_with_a_warning(self):
        self.content("advice")
        self.speech(2.8)
        cc = copy.deepcopy(looks.caption_catalog())
        cc["looks"]["sentence-boxed"] = dict(cc["looks"]["phrase-boxed"], grouping="sentence")
        write_json(self.root / CLIENT_PROFILE_REL / "looks" / "recommender.json",
                   {"caption": {"fit": {"advice": {"sentence-boxed": 1.0}}}})
        with mock.patch.object(looks, "caption_catalog", return_value=cc):
            r = self.rec()
        self.assertIn(r["pick"], cc["looks"])
        self.assertTrue(any("delivery" in w and "sentence" in w for w in r["warnings"]), r["warnings"])
        got = {t["look"]: t["score"] for t in r["top"]}
        n = self.cat["neutral"]
        self.assertAlmostEqual(got["sentence-boxed"], 3 * 1.0 + 2 * n + 1 * n, 4)   # no traits, no delivery row

    def test_the_language_is_read_case_blind(self):
        self.content("advice")
        self.speech(2.8)
        self.assertEqual(self.rec(lang="EN")["reason"], self.rec(lang="en")["reason"])


class TestRecord(RecCase):
    def test_record_choice_keeps_the_other_kind_and_marks_an_editor_swap(self):  # R14
        LR.record_choice(self.paths, "caption", "phrase-boxed", "recommender")
        LR.record_choice(self.paths, "motion", "M-two", "editor")
        d = read_json(self.paths.p("01_analysis/look-choice.json"))
        self.assertEqual(d["caption"]["look"], "phrase-boxed")
        self.assertEqual((d["motion"]["look"], d["motion"]["source"]), ("M-two", "editor"))
        self.assertTrue(d["motion"].get("at"))
        self.assertFalse(list(self.paths.p("01_analysis").glob("*.tmp")))

    def test_record_choice_survives_a_garbled_file(self):
        self.paths.p("01_analysis").mkdir(parents=True, exist_ok=True)
        self.paths.p("01_analysis/look-choice.json").write_text("{bad", encoding="utf-8")
        LR.record_choice(self.paths, "caption", "line-clean", "editor")
        self.assertEqual(read_json(self.paths.p("01_analysis/look-choice.json"))["caption"]["look"], "line-clean")

    def test_record_choice_keeps_the_time_to_the_microsecond_with_its_zone(self):
        LR.record_choice(self.paths, "motion", "M-one", "recommender")
        at = read_json(self.paths.p("01_analysis/look-choice.json"))["motion"]["at"]
        self.assertIn(".", at)                           # reels picked in one loop still keep their order
        self.assertIsNotNone(datetime.fromisoformat(at).tzinfo)

    def test_choices_recorded_on_one_clock_tick_keep_the_order_they_were_made_in(self):
        tick = datetime.fromisoformat("2026-10-17T10:00:00.000000+03:00")     # Windows: one value for many calls
        with mock.patch.object(LR, "_now", return_value=tick):
            for vid, look in (("R0", "M-one"), ("R1", "M-two"), ("R2", "M-three"), ("R0", "M-swap")):
                LR.record_choice(self.reel(vid, "2026-10-17T09:00:00"), "motion", look, "recommender")
        self.assertEqual(LR.history(self.paths, "motion"), ["M-swap", "M-three", "M-two"])

    def test_history_follows_when_each_look_was_recorded_and_stops_at_this_reels_own_choice(self):
        self.reel("A", "2026-10-01T10:00:00", {"motion": {"look": "M-one", "at": "2026-10-02T10:00:00+00:00"}})
        self.reel("B", "2026-10-03T10:00:00", {"motion": {"look": "M-two", "at": "2026-10-01T10:00:00+00:00"}})
        self.reel("C", "yesterday", {"motion": {"look": "M-bad", "at": "soon"}})
        self.reel("D", "2026-10-01T10:00:00", {"motion": {"look": "M-late", "at": "2026-10-09T10:00:00+00:00"}})
        self.assertEqual(LR.history(self.paths, "motion"), ["M-late", "M-one", "M-two"])
        write_json(self.paths.p("01_analysis/look-choice.json"),          # re-recommending a reel already picked
                   {"motion": {"look": "M-own", "at": "2026-10-05T10:00:00+00:00"}})
        self.assertEqual(LR.history(self.paths, "motion"), ["M-one", "M-two"])
        self.reel("E", "2026-10-01T10:00:00", {"motion": {"look": "M-same", "at": "2026-10-05T13:00:00+03:00"}})
        self.assertEqual(LR.history(self.paths, "motion"), ["M-same", "M-one", "M-two"])     # up to it, inclusive

    def test_history_converts_time_zones_and_skips_this_reel_in_any_case(self):
        self.reel("A", "2026-10-01T00:00:00", {"motion": {"look": "M-two", "at": "2026-10-01T08:00:00+00:00"}})
        self.reel("B", "2026-10-01T00:00:00", {"motion": {"look": "M-one", "at": "2026-10-01T10:00:00+03:00"}})
        self.assertEqual(LR.history(self.paths, "motion"), ["M-two", "M-one"])   # 08:00Z is after 07:00Z
        self.reel(self.VID.lower(), "2026-10-01T00:00:00",
                  {"motion": {"look": "M-self", "at": "2026-10-08T10:00:00+00:00"}})
        self.assertEqual(LR.history(self.paths, "motion"), ["M-two", "M-one"])

    def test_history_is_newest_first_skips_bad_files_and_this_reel(self):        # R10
        self.reel("A", "2026-10-01T10:00:00", {"motion": {"look": "M-one"}})
        self.reel("B", "2026-10-03T10:00:00", {"motion": {"look": "M-two"}})
        self.reel("C", "2026-10-02T10:00:00", raw="{broken")
        self.reel("D", "2026-10-04T10:00:00", {"caption": {"look": "line-clean"}})       # no motion look recorded
        LR.record_choice(self.paths, "motion", "M-three", "recommender")
        write_json(self.paths.p("08_quality_control/project-status.json"), {"created": "2026-10-05T10:00:00"})
        self.assertEqual(LR.history(self.paths, "motion"), ["M-two", "M-one"])
        self.assertEqual(LR.history(self.paths, "caption"), ["line-clean"])


MOTION = [{"name": "M-one", "display": "M-one", "status": "accepted"},
          {"name": "M-two", "display": "M-two", "status": "accepted"},
          {"name": "M-play", "display": "M-play", "status": "accepted"},
          {"name": "M-gate", "display": "M-gate", "status": "preview_gate"},
          {"name": "M-plan", "display": "M-plan", "status": "planned"}]
MOTION_TABLES = {"order": ["M-one", "M-two", "M-play", "M-gate", "M-plan"],
                 "traits": {"M-one": {"energy": 0.5, "playful": False}, "M-two": {"energy": 0.5, "playful": False},
                            "M-play": {"energy": 0.5, "playful": True}, "M-gate": {"energy": 0.5, "playful": False},
                            "M-plan": {"energy": 0.5, "playful": False}},
                 "fit": {"advice": {"M-one": 0.9, "M-two": 0.6, "M-play": 0.2, "M-gate": 1.0, "M-plan": 1.0},
                         "comedy": {"M-one": 0.4, "M-two": 0.3, "M-play": 1.0, "M-gate": 0.2, "M-plan": 1.0},
                         "drama": {"M-one": 0.9, "M-two": 0.1, "M-play": 0.1, "M-gate": 0.1, "M-plan": 0.1}}}


class TestMotion(RecCase):
    def setUp(self):
        super().setUp()
        cat = copy.deepcopy(self.cat)
        cat["motion"].update(copy.deepcopy(MOTION_TABLES))
        p1 = mock.patch.object(LR, "catalog", return_value=cat)
        p2 = mock.patch.object(LR, "motion_looks", return_value=copy.deepcopy(MOTION))
        p1.start(), p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)
        self.cat = cat
        self.speech(2.8)

    def run_reels(self, ctype, n=5):
        picks = []
        for k in range(n):
            self.content(ctype)
            r = self.rec("motion")
            picks.append(r["pick"])
            if r["pick"]:
                self.reel(f"P{k:02d}", f"2026-10-{k + 1:02d}T10:00:00", {"motion": {"look": r["pick"]}})
        return picks

    def test_one_motion_look_never_three_times_in_a_row(self):                     # R8
        picks = self.run_reels("advice", 6)
        for a, b, c in zip(picks, picks[1:], picks[2:]):
            self.assertFalse(a == b == c, picks)
        self.assertIn("M-one", picks)
        self.assertNotIn("M-gate", picks)
        self.assertNotIn("M-plan", picks)

    def test_when_the_next_look_fits_too_little_there_is_no_look(self):            # R8
        picks = self.run_reels("drama", 3)
        self.assertEqual(picks[:2], ["M-one", "M-one"])
        self.assertIsNone(picks[2])

    def test_the_line_cites_the_last_two_reels_when_variety_steps_in(self):
        picks = self.run_reels("advice", 3)
        self.assertEqual(picks[2], "M-two")
        self.content("advice")
        line = self.rec("motion")["reason"]
        self.assertTrue(line)

    def test_only_accepted_looks_are_picked_preview_gate_is_listed_planned_never(self):   # R9
        self.content("advice")
        r = self.rec("motion")
        self.assertEqual(r["pick"], "M-one")
        self.assertIn("M-gate", r["hand_pick"])
        self.assertNotIn("M-plan", r["hand_pick"])
        self.assertNotIn("M-plan", [t["look"] for t in r["top"]])
        self.assertNotIn("M-gate", [t["look"] for t in r["top"]])

    def test_no_accepted_look_is_no_look_with_the_plain_line(self):                 # R9
        with mock.patch.object(LR, "motion_looks", return_value=[dict(MOTION[3]), dict(MOTION[4])]):
            self.content("advice")
            r = self.rec("motion")
        self.assertIsNone(r["pick"])
        self.assertEqual(r["reason"], self.cat["reason"]["ar"]["no_motion"])

    def test_today_the_catalogue_is_empty_so_the_usual_look_is_kept(self):
        mock.patch.stopall()
        self.content("advice")
        r = LR.recommend(self.paths, kind="motion", stills=False)
        self.assertIsNone(r["pick"])
        self.assertEqual(r["reason"], LR.catalog()["reason"]["ar"]["no_motion"])

    def test_the_recent_use_is_counted_with_its_age(self):                          # R10
        self.content("advice")
        self.reel("A", "2026-10-01T10:00:00", {"motion": {"look": "M-one"}})
        self.reel("B", "2026-10-02T10:00:00", {"motion": {"look": "M-two"}})
        self.reel("C", "2026-10-03T10:00:00", {"motion": {"look": "M-one"}})
        r = self.rec("motion")
        rc = self.cat["recent"]
        got = {t["look"]: t["score"] for t in r["top"]}
        base = {n: 3 * MOTION_TABLES["fit"]["advice"][n] + 2 * self.cat["neutral"] + 1 * self.cat["neutral"]
                for n in ("M-one", "M-two")}
        self.assertAlmostEqual(got["M-one"], base["M-one"] - rc["weight"] * (rc["decay"] ** 0 + rc["decay"] ** 2), 3)
        self.assertAlmostEqual(got["M-two"], base["M-two"] - rc["weight"] * rc["decay"] ** 1, 3)

    def test_a_playful_look_never_on_medical_or_religious_content(self):            # R11
        self.content("comedy")
        self.assertEqual(self.rec("motion")["pick"], "M-play")
        self.content("medical_claim")
        self.cat["motion"]["fit"]["medical_claim"] = {"M-one": 0.4, "M-two": 0.3, "M-play": 1.0, "M-gate": 0.2,
                                                      "M-plan": 0.1}
        r = self.rec("motion")
        self.assertNotEqual(r["pick"], "M-play")
        self.assertNotIn("M-play", [t["look"] for t in r["top"]])
        self.content("comedy")
        write_json(self.root / CLIENT_PROFILE_REL / "profile.json", {"review_domains": ["religious"]})
        r = self.rec("motion")
        self.assertNotEqual(r["pick"], "M-play")
        self.assertNotIn("M-play", [t["look"] for t in r["top"]])

    def test_a_look_that_fits_too_little_never_blocks_one_that_fits(self):
        self.refs(cpms=[30, 30, 30])                   # client energy 1
        self.cat["motion"]["traits"]["M-one"]["energy"] = 0.0
        self.cat["motion"]["traits"]["M-two"]["energy"] = 1.0
        self.cat["motion"]["fit"]["advice"].update({"M-one": 0.9, "M-two": 0.25})
        self.content("advice")
        self.assertEqual(self.rec("motion")["pick"], "M-one")

    def test_ordinary_clips_between_reels_never_break_the_variety_rule(self):
        picks = []
        for k in range(6):
            self.content("advice")
            r = self.rec("motion")
            picks.append(r["pick"])
            self.reel(f"R{k:02d}", f"2026-10-{2 * k + 1:02d}T10:00:00", {"motion": {"look": r["pick"]}})
            self.reel(f"O{k:02d}", f"2026-10-{2 * k + 2:02d}T10:00:00", {"caption": {"look": "line-clean"}})
        for a, b, c in zip(picks, picks[1:], picks[2:]):
            self.assertFalse(a == b == c, picks)

    def test_an_unreadable_profile_counts_as_sensitive(self):
        self.content("comedy")
        write_json(self.root / CLIENT_PROFILE_REL / "profile.json", {"review_domains": ["religous"]})
        r = self.rec("motion")
        self.assertNotEqual(r["pick"], "M-play")

    def test_a_playful_override_is_refused_on_sensitive_content_and_a_planned_one_is_noted(self):
        self.content("medical_claim")
        r = self.rec("motion", override="M-play")
        self.assertNotEqual(r["pick"], "M-play")
        self.assertTrue(r["notes"], r)
        self.content("advice")
        r = self.rec("motion", override="M-plan")
        self.assertNotEqual(r["pick"], "M-plan")
        self.assertTrue(any("M-plan" in n for n in r["notes"]), r["notes"])

    def test_when_variety_leaves_no_look_the_line_says_so(self):
        picks = self.run_reels("drama", 3)
        self.assertIsNone(picks[2])
        self.content("drama")
        r = self.rec("motion")
        self.assertEqual(r["reason"], self.cat["reason"]["ar"]["no_motion_variety"])

    def test_an_accepted_look_missing_from_the_order_is_still_considered_and_reported(self):
        del self.cat["motion"]["order"][0]               # M-one
        self.content("advice")
        r = self.rec("motion")
        self.assertEqual(r["pick"], "M-one")
        self.assertTrue(any("M-one" in w for w in r["warnings"]), r["warnings"])

    def build_siblings(self, order):
        """Reels picked at Gate 0 in one loop (the same `created` second), each built and its look recorded in turn."""
        picks = []
        for i, k in enumerate(order):
            p = self.reel(f"S{k}", "2026-10-17T10:00:00")
            self.content("advice", p)
            self.speech(2.8, p)
            r = LR.recommend(p, kind="motion", stills=False)
            picks.append(r["pick"])
            write_json(p.p("01_analysis/look-choice.json"),
                       {"motion": {"look": r["pick"], "source": "recommender", "at": f"2026-10-17T11:{i:02d}:00+03:00"}})
        return picks

    def test_reels_made_in_one_second_still_vary_when_built_in_order(self):
        picks = self.build_siblings(range(5))
        for a, b, c in zip(picks, picks[1:], picks[2:]):
            self.assertFalse(a == b == c, picks)

    def test_reels_made_in_one_second_still_vary_when_built_newest_first(self):
        picks = self.build_siblings(reversed(range(5)))
        for a, b, c in zip(picks, picks[1:], picks[2:]):
            self.assertFalse(a == b == c, picks)

    def test_a_playful_look_is_never_offered_by_hand_on_sensitive_content(self):
        self.content("medical_claim")
        r = self.rec("motion")
        self.assertNotIn("M-play", r["hand_pick"])
        self.assertIn("M-gate", r["hand_pick"])
        r = self.rec("motion", override="M-play")
        self.assertEqual(r["notes"], [self.cat["reason"]["ar"]["override_refused"].format(look="M-play")])

    def test_a_fixed_motion_look_always_wins(self):
        self.content("advice")
        r = self.rec("motion", override="M-two")
        self.assertEqual((r["pick"], r["source"]), ("M-two", "reel"))
        for k in range(3):
            self.reel(f"F{k}", f"2026-10-0{k + 1}T10:00:00", {"motion": {"look": "M-two"}})
        self.assertEqual(self.rec("motion", override="M-two")["pick"], "M-two")     # no variety rule over a choice


if __name__ == "__main__":
    unittest.main()
