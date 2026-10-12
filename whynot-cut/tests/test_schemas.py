"""3.0 T2.3 — schemas of the authored files, `reel validate`, engine_version stamps (engine MI-11).

  * whynot-cut/schemas/*.schema.json: every file fits the contract validator's keyword subset (self-validation), carries
    its version in `$id` and `schema_version`, and is a kind of lib/schemas.py
  * tests/fixtures/schemas/<kind>.json: {"valid": [docs], "invalid": [{"why", "path", "doc"}]}; the valid documents are
    the shapes the engine's own tests author (edit-decisions compiled by `reel plan`, reels plans, motion scripts,
    publish copy, transcript corrections), the invalid ones must fail at `path`
  * the JSON examples of the skills validate (placeholders such as "high|medium|low" read as their first choice)
  * `reel validate <file> [--kind K]`: kind from the file name, {ok, kind, errors[{path, msg}]}, exit 1 when not ok
  * compiled artefacts carry engine_version; a consumer warns on another minor version or no stamp (2.x) and refuses
    another major version with a "re-run" hint
Run:  bash tools/test.sh -p test_schemas.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from contract import check_schema  # noqa: E402
from lib import common, schemas, stamps  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402
from lib.errors import Guidance  # noqa: E402

CLI = SK / "engine/reel/cli.py"
FIX = SK / "tests/fixtures/schemas"


def reel(*argv, cwd=None):
    r = subprocess.run([sys.executable, "-B", str(CLI), *argv], capture_output=True, text=True, encoding="utf-8",
                       cwd=cwd, env=dict(os.environ))
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        doc = r.stdout
    return r.returncode, doc, r.stderr


class TempDir(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)


# --------------------------------------------------------------------------- the schema files
class TestSchemaFiles(unittest.TestCase):
    def test_every_schema_fits_the_validator_and_is_versioned(self):
        files = sorted(schemas.SCHEMA_DIR.glob("*.schema.json"))
        self.assertEqual({f.name[:-len(".schema.json")] for f in files}, {n for n, _ in schemas.KINDS.values()})
        for f in files:
            raw = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(raw["$schema"], "https://json-schema.org/draft/2020-12/schema", f.name)
            self.assertEqual(check_schema(schemas.bundled(f.name[:-len(".schema.json")])), [], f.name)
            v = raw["properties"]["schema_version"]["const"]
            self.assertIsInstance(v, int)
            self.assertTrue(raw["$id"].endswith(f":{v}"), raw["$id"])
        for kind in schemas.KINDS:
            self.assertEqual(check_schema(schemas.schema_for(kind)), [], kind)
            self.assertEqual(schemas.schema_version(kind), 1)

    def test_asset_needs_is_shared_by_edit_decisions_and_motion_script(self):
        for kind in ("edit-decisions", "motion-script"):
            s = schemas.schema_for(kind)
            self.assertEqual(s["properties"]["asset_needs"], {"$ref": "#/$defs/asset-needs.list"})
            self.assertIn("asset-needs.need", s["$defs"])
            self.assertNotIn("asset_needs", s.get("required", []))            # optional
        need = schemas.bundled("asset-needs")["$defs"]["need"]
        self.assertEqual(need["properties"]["kind"]["enum"], ["upscale", "vectorize", "cutout", "icon", "background",
                                                              "broll_still", "broll_video"])
        self.assertEqual(set(need["properties"]["anchor"]["properties"]), {"segment", "start", "end", "phrase"})

    def test_kind_from_the_file_name(self):
        k = schemas.kind_for
        self.assertEqual(k("x/01_analysis/edit-decisions.json"), "edit-decisions")
        self.assertEqual(k("reels-plan.json"), "reels-plan")
        self.assertEqual(k("motion-script.json"), "motion-script")
        self.assertEqual(k("EP12/publish/publish.json"), "publish")
        self.assertEqual(k("EP12/publish/reels/EP12_R03.json"), "publish-reel")
        self.assertEqual(k("transcript-corrections.json"), "transcript-corrections")
        self.assertEqual(k("asset_needs.json"), "asset-needs")
        self.assertIsNone(k("timeline-spec.json"))
        self.assertIsNone(k("publish-reel.json"))
        self.assertIsNone(k("edit-decisions.md"))
        self.assertEqual(schemas.kind_name("Asset_Needs"), "asset-needs")


# --------------------------------------------------------------------------- valid / invalid fixtures
class TestFixtures(unittest.TestCase):
    def test_valid_and_invalid_fixtures_per_kind(self):
        for kind in schemas.KINDS:
            fx = json.loads((FIX / f"{kind}.json").read_text(encoding="utf-8"))
            self.assertGreater(len(fx["valid"]), 0, kind)
            self.assertGreater(len(fx["invalid"]), 0, kind)
            for i, doc in enumerate(fx["valid"]):
                self.assertEqual(schemas.validate(doc, kind), [], f"{kind} valid[{i}]")
            for case in fx["invalid"]:
                errs = schemas.validate(case["doc"], kind)
                self.assertTrue(errs, f"{kind}: {case['why']} passed")
                self.assertIn(case["path"], [e["path"] for e in errs], f"{kind}: {case['why']}: {errs}")

    def test_schema_version_of_another_version_is_rejected(self):
        self.assertEqual(schemas.validate({"decisions": [], "schema_version": 1}, "edit-decisions"), [])
        errs = schemas.validate({"decisions": [], "schema_version": 2}, "edit-decisions")
        self.assertEqual([e["path"] for e in errs], ["/schema_version"])

    def test_sound_kinds_are_safe_names_not_the_recipe_list(self):
        """T2.7: a client's 06_audio/sfx-map.json adds kinds; `reel plan` checks membership, the schema the name."""
        def ed(sound, sfx):
            return {"decisions": [{"decision_id": "EDIT_001", "segment_id": "S1", "evidence": "x", "start": 0,
                                   "end": 1000, "semantic_intent": "i", "visual_treatment": "v", "confidence": "high",
                                   "sound": [{"type": sound}], "graphics": [{"id": "G1", "template": "cta", "sfx": sfx}]}]}
        self.assertEqual(schemas.validate(ed("door_slam", "none"), "edit-decisions"), [])
        self.assertEqual(schemas.validate(ed("whoosh", None), "edit-decisions"), [])
        paths = [e["path"] for e in schemas.validate(ed("../evil", "a b"), "edit-decisions")]
        self.assertIn("/decisions/0/sound/0/type", paths)
        self.assertIn("/decisions/0/graphics/0/sfx", paths)


    def test_optional_fields_the_engine_reads_as_missing_accept_null(self):
        """T2.3 review: the engine treats null like a field left out (plan.py: main_footage, camera.until/scale/offsets,
        caption_highlights.at, graphics image/video/sfx ""/null; reels.py: context_line ...); camera.at / graphics
        start null are engine errors and stay invalid (fixtures edit-decisions.json / reels-plan.json)."""
        fx = json.loads((FIX / "edit-decisions.json").read_text(encoding="utf-8"))
        nulls = next(d for d in fx["valid"] if "written as null" in d.get("note", ""))
        self.assertIsNone(nulls["global"]["main_footage"])
        self.assertIsNone(nulls["decisions"][0]["camera"]["until"])
        self.assertEqual(nulls["decisions"][0]["graphics"][0]["sfx"], "")
        self.assertEqual(schemas.validate(nulls, "edit-decisions"), [])
        rp = json.loads((FIX / "reels-plan.json").read_text(encoding="utf-8"))["valid"][-1]
        self.assertIsNone(rp["candidates"][0]["context_line"])
        self.assertEqual(schemas.validate(rp, "reels-plan"), [])

    def test_framing_agrees_with_the_engine_window(self):
        """schema and plan.window_rect: 4:5, 4x5, "4 : 5" give a window; 4X5 does not (the engine would skip it
        silently, so the schema rejects it); framing_window_y may be a float (the engine int()s it)."""
        from lib.plan import window_rect

        def errs(framing, y=None):
            g = {"framing": framing, **({"framing_window_y": y} if y is not None else {})}
            return schemas.validate({"global": g, "decisions": []}, "edit-decisions")
        for ok in ("4:5", "4x5", " 4 : 5 ", "4.5:5", "full", "9:16", ""):
            self.assertEqual(errs(ok), [], ok)
        for framing in ("4:5", "4x5", " 4 : 5 "):
            self.assertIsNotNone(window_rect(framing))
        self.assertIsNone(window_rect("4X5"))
        self.assertEqual([e["path"] for e in errs("4X5")], ["/global/framing"])
        self.assertEqual(errs("4:5", 120.5), [])
        self.assertEqual(window_rect("4:5", 120.5)["y"], 120)
        self.assertEqual([e["path"] for e in errs("4:5", "high")], ["/global/framing_window_y"])

    def test_time_grammar_is_the_engines_parser(self):
        """One pattern in every schema, and a string is a valid time exactly when media_util.parse_time reads it
        (leading tab, trailing newline, Arabic-Indic digits, "," fractions)."""
        from contract import validate as contract_validate
        from lib.media_util import parse_time
        names = ("edit-decisions", "reels-plan", "publish", "asset-needs")
        pats = {schemas.bundled(n)["$defs"]["time"]["pattern"] for n in names}
        self.assertEqual(len(pats), 1)
        sch = {"$defs": {"time": schemas.bundled("reels-plan")["$defs"]["time"]}, "$ref": "#/$defs/time"}
        cases = ["12", "12.5", "1:02", "1:02:03.500", "1:02,5", "00:00:12.500", "\t12", " 12 ", "12\n", "٤٠", "٠١:٣٠",
                 "٠٠:٠٠:١٢.٥٠٠", " 12", "", " ", "12s", "1:2:3:4", "-5", "1e3", ".5", "5.", "1:", ":30", "a:b"]
        for t in cases:
            try:
                parse_time(t)
                engine = True
            except ValueError:
                engine = False
            self.assertEqual(not contract_validate(t, sch), engine, repr(t))


def _json_blocks(md: Path) -> list:
    return re.findall(r"```json\n(.*?)```", md.read_text(encoding="utf-8"), re.S)


class TestSkillExamples(unittest.TestCase):
    """The examples the agents copy from must fit the schemas they are checked against."""

    def first(self, md, key):
        for b in _json_blocks(SK / md):
            if key in b:
                # "a | b" / "a|b|c" placeholders in the edit-decisions example read as their first choice
                return json.loads(re.sub(r'"([^"|]+?) ?\| ?[^"]*"', r'"\1"', b))
        self.fail(f"no JSON example with {key} in {md}")

    def test_examples(self):
        cases = [("skills/story-craft/references/edit-decision-engine.md", '"decisions"', "edit-decisions"),
                 ("skills/episode-craft/SKILL.md", '"candidates"', "reels-plan"),
                 ("skills/motion-craft/references/motion-scenes.md", '"scenes"', "motion-script"),
                 ("skills/publish-craft/SKILL.md", '"youtube"', "publish"),
                 ("skills/publish-craft/SKILL.md", '"instagram"', "publish-reel"),
                 ("skills/transcript-craft/SKILL.md", '"corrections"', "transcript-corrections")]
        for md, key, kind in cases:
            self.assertEqual(schemas.validate(self.first(md, key), kind), [], f"{md} ({kind})")


# --------------------------------------------------------------------------- reel validate
class TestReelValidate(TempDir):
    def write(self, rel, doc):
        f = self.tmp / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return f

    def test_valid_file_kind_from_name(self):
        fx = json.loads((FIX / "reels-plan.json").read_text(encoding="utf-8"))
        f = self.write("01_analysis/reels-plan.json", fx["valid"][0])
        code, doc, err = reel("validate", str(f))
        self.assertEqual(code, 0, (doc, err))
        self.assertEqual((doc["ok"], doc["kind"], doc["errors"], doc["schema_version"]), (True, "reels-plan", [], 1))
        self.assertEqual(err, "")

    def test_invalid_file_exits_1_with_paths(self):
        f = self.write("01_analysis/edit-decisions.json",
                       {"decisions": [{"decision_id": "EDIT_001", "segment_id": "S1", "evidence": "x",
                                       "semantic_intent": "i", "visual_treatment": "v", "confidence": "sure"}]})
        code, doc, err = reel("validate", str(f))
        self.assertEqual(code, 1, doc)
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["kind"], "edit-decisions")
        self.assertIn({"path": "/decisions/0", "msg": "required property 'start' is missing"}, doc["errors"])
        self.assertIn("/decisions/0/confidence", [e["path"] for e in doc["errors"]])
        self.assertNotIn("Traceback", err)

    def test_kind_option_and_root_relative_path(self):
        self.write("publish/reels/EP12_R03.json", {"reel_id": "EP12_R03", "instagram": {"caption": "x", "hashtags": []}})
        f = self.write("copy.json", {"reel_id": "EP12_R03", "instagram": {"hashtags": "#x"}})
        code, doc, _ = reel("--root", str(self.tmp), "validate", "publish/reels/EP12_R03.json")
        self.assertEqual((code, doc["kind"], doc["ok"]), (0, "publish-reel", True))
        code, doc, _ = reel("validate", str(f), "--kind", "publish_reel")
        self.assertEqual((code, doc["kind"]), (1, "publish-reel"))
        self.assertEqual([e["path"] for e in doc["errors"]], ["/instagram/hashtags"])

    def test_relative_path_is_found_in_the_project_the_episode_then_the_root(self):
        """T2.3 review I1: the story-editor runs `reel --root C --video-id CLIP1 validate 01_analysis/edit-decisions.json`."""
        ed = json.loads((FIX / "edit-decisions.json").read_text(encoding="utf-8"))["valid"][0]
        rp = json.loads((FIX / "reels-plan.json").read_text(encoding="utf-8"))["valid"][0]
        proj = self.write("output/projects/CLIP1/01_analysis/edit-decisions.json", ed)
        epi = self.write("output/episodes/EP12/01_analysis/reels-plan.json", rp)
        code, doc, err = reel("--root", str(self.tmp), "--video-id", "CLIP1", "validate", "01_analysis/edit-decisions.json")
        self.assertEqual((code, doc["ok"], doc["kind"]), (0, True, "edit-decisions"), (doc, err))
        self.assertEqual(Path(doc["file"]), proj.resolve())
        code, doc, err = reel("--root", str(self.tmp), "--episode", "EP12", "validate", "01_analysis/reels-plan.json")
        self.assertEqual((code, doc["ok"], doc["kind"]), (0, True, "reels-plan"), (doc, err))
        self.assertEqual(Path(doc["file"]), epi.resolve())
        # a file in the current folder wins over the project's; a --root relative file still works without ids
        here = self.write("here/01_analysis/edit-decisions.json", {"decisions": "no"})
        code, doc, _ = reel("--root", str(self.tmp), "--video-id", "CLIP1", "validate", "01_analysis/edit-decisions.json",
                            cwd=str(self.tmp / "here"))
        self.assertEqual((code, doc["ok"]), (1, False))
        self.assertEqual(Path(doc["file"]), Path("01_analysis/edit-decisions.json"))
        self.write("publish/reels/EP12_R03.json", {"reel_id": "EP12_R03"})
        code, doc, _ = reel("--root", str(self.tmp), "--video-id", "CLIP1", "validate", "publish/reels/EP12_R03.json")
        self.assertEqual((code, doc["kind"], doc["ok"]), (0, "publish-reel", True))
        self.assertTrue(here.exists())

    def test_missing_relative_path_lists_the_places_tried(self):
        code, doc, _ = reel("--root", str(self.tmp), "--video-id", "CLIP1", "--episode", "EP12", "validate",
                            "01_analysis/edit-decisions.json")
        self.assertEqual(code, 1)
        self.assertIn("not found", doc["error"])
        tried = [Path(x).as_posix() for x in doc["tried"]]
        self.assertEqual(len(tried), 4)
        self.assertEqual(tried[0], "01_analysis/edit-decisions.json")
        self.assertTrue(tried[1].endswith("output/projects/CLIP1/01_analysis/edit-decisions.json"), tried)
        self.assertTrue(tried[2].endswith("output/episodes/EP12/01_analysis/edit-decisions.json"), tried)
        self.assertTrue(tried[3].endswith("/01_analysis/edit-decisions.json") and "output" not in tried[3], tried)
        self.assertIn("output/projects/CLIP1", doc["how"].replace("\\", "/"))

    def test_unknown_kind_bad_json_missing_file(self):
        f = self.write("notes.json", {})
        code, doc, _ = reel("validate", str(f))
        self.assertEqual(code, 1)
        self.assertIn("--kind", doc["how"])
        code, doc, _ = reel("validate", str(f), "--kind", "storyboard")
        self.assertEqual(code, 1)
        self.assertIn("edit-decisions", doc["how"])
        bad = self.tmp / "motion-script.json"
        bad.write_text('{"scenes": [}', encoding="utf-8")
        code, doc, _ = reel("validate", str(bad))
        self.assertEqual((code, doc["kind"]), (1, "motion-script"))
        self.assertIn("line 1", doc["errors"][0]["msg"])
        code, doc, _ = reel("validate", str(self.tmp / "missing" / "edit-decisions.json"))
        self.assertEqual(code, 1)
        self.assertIn("not found", doc["error"])


# --------------------------------------------------------------------------- engine_version stamps
class TestVersionRule(unittest.TestCase):
    def test_compare(self):
        c = stamps.compare
        self.assertEqual(c("3.0.0", "3.0.7"), "same")
        self.assertEqual(c("3.1.0", "3.0.0"), "minor")
        self.assertEqual(c("3.0.2", "3.2.0"), "minor")
        self.assertEqual(c("2.2.1", "3.0.0"), "major")
        self.assertEqual(c("4.0.0", "3.9.9"), "major")
        self.assertEqual(c(None, "3.0.0"), "missing")
        self.assertEqual(c("", "3.0.0"), "missing")
        self.assertEqual(c("dev", "3.0.0"), "unknown")

    def test_engine_version_is_the_plugin_version(self):
        pj = json.loads((SK / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(stamps.engine_version(), pj["version"])
        self.assertEqual(stamps.stamp({"a": 1}), {"a": 1, "engine_version": pj["version"]})


class TestStampCheck(TempDir):
    def setUp(self):
        super().setUp()
        self.ctx = common.Context()
        cm = common.use_context(self.ctx)
        cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(stamps, "engine_version", return_value="3.0.0").start()

    def spec(self, version=None, name="timeline-spec.json"):
        f = self.tmp / "01_analysis" / name
        f.parent.mkdir(parents=True, exist_ok=True)
        write_json(f, {"video_id": "CLIP1", **({"engine_version": version} if version else {})})
        return f

    def test_same_major_minor_is_silent(self):
        self.assertEqual(stamps.read_compiled(self.spec("3.0.4"))["video_id"], "CLIP1")
        self.assertFalse(getattr(self.ctx, "version_warnings", None))

    def test_minor_mismatch_warns_once(self):
        f = self.spec("3.1.0")
        stamps.read_compiled(f)
        stamps.read_compiled(f)
        self.assertEqual(len(self.ctx.version_warnings), 1)
        self.assertIn("3.1.0", self.ctx.version_warnings[0])
        self.assertIn("reel plan", self.ctx.version_warnings[0])

    def test_unstamped_2x_artefact_warns_only(self):
        w = stamps.check(read_json(self.spec(None, "motion-plan.json")), self.tmp / "motion-plan.json")
        self.assertIn("no engine_version", w)
        self.assertIn("reel motion-plan", w)

    def test_major_mismatch_refuses_with_rerun_hint(self):
        with self.assertRaises(Guidance) as cm:
            stamps.read_compiled(self.spec("2.2.1"))
        self.assertIn("2.2.1", cm.exception.error)
        self.assertIn("Re-run `reel plan`", cm.exception.how)
        with self.assertRaises(Guidance) as cm:
            stamps.read_compiled(self.spec("4.0.0", "reels-plan-validated.json"), rerun="reel reels-plan --episode EP12")
        self.assertIn("reel reels-plan --episode EP12", cm.exception.how)

    def test_emit_prints_the_warnings_once(self):
        from lib.errors import emit
        stamps.read_compiled(self.spec("3.2.0"))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            emit({"ok": True})
            emit({"ok": True})
        first, second = (json.loads(d) for d in re.split(r"(?<=})\n(?={)", buf.getvalue().strip()))
        self.assertEqual(len(first["version_warnings"]), 1)
        self.assertNotIn("version_warnings", second)

    def test_consumers_refuse_a_major_mismatch(self):
        """verify / previews / XML / ppro job / preview video / qc read the timeline spec; motion steps the motion
        plan; reels-select / reels-preview the validated reels plan: each refuses before doing anything."""
        from lib import (motion_animatic, motion_build, motion_render, ppro_build, premiere_xml, preview_video,
                         previews, qc, reels, verify)

        class P:
            root, video_id, episode_id = self.tmp, "CLIP1", "EP12"

            def p(_s, rel):
                return self.tmp / rel
        self.spec("2.2.1")
        self.spec("2.2.1", "motion-plan.json")
        self.spec("2.2.1", "reels-plan-validated.json")
        calls = [lambda: verify.build(P()), lambda: previews.render_all(P()), lambda: premiere_xml.build_xml(P()),
                 lambda: ppro_build.job_data(P()), lambda: preview_video.render(P()), lambda: qc.run_qc(P()),
                 lambda: motion_build.job_data(P()), lambda: motion_render.render(P()),
                 lambda: motion_animatic.render(P()), lambda: reels.fresh_validated(P())]
        for call in calls:
            with self.assertRaises(Guidance, msg=call):
                call()


class TestCompilersStamp(TempDir):
    def test_reel_plan_stamps_and_the_fingerprint_ignores_it(self):
        from lib import plan
        from test_pipeline import make_project
        root, p, _ = make_project(self.tmp)
        write_json(p.p("01_analysis/edit-decisions.json"), {
            "video_id": "CLIP1", "global": {"main_footage": "data/Raw/CLIP1.mov"},
            "decisions": [{"decision_id": "EDIT_001", "segment_id": "SEG_001", "evidence": "هل في حاجات معينة",
                           "start": "00:00:00.200", "end": "00:00:04.000", "semantic_intent": "hook",
                           "visual_treatment": "hook", "confidence": "high"}]})
        self.assertEqual(schemas.validate(read_json(p.p("01_analysis/edit-decisions.json")), "edit-decisions"), [])
        common.set_context(root)
        self.addCleanup(common.set_context, None)
        res = plan.compile_plan(p)
        self.assertTrue(res["ok"], res["errors"])
        f = p.p("01_analysis/timeline-spec.json")
        spec = read_json(f)
        self.assertEqual(spec["engine_version"], stamps.engine_version())
        fp = plan.plan_fingerprint(p)
        write_json(f, dict(spec, engine_version="3.9.0"))
        self.assertEqual(plan.plan_fingerprint(p), fp)

    def test_reels_plan_stamps(self):
        from lib.episode import EpisodePaths
        from lib.reels import compile_reels_plan, fresh_validated
        from test_podcast import cand, synthetic_episode_transcript
        root = self.tmp / "C"
        (root / "assets").mkdir(parents=True)
        (root / "data").mkdir()
        ep = EpisodePaths(root, "EP12")
        words = synthetic_episode_transcript(ep)
        write_json(ep.p("00_inputs/episode.json"), {"episode_id": "EP12", "duration_ms": 121000})
        plan = {"episode_id": "EP12", "candidates": [cand(words, 39, 149)]}
        self.assertEqual(schemas.validate(plan, "reels-plan"), [])
        write_json(ep.p("01_analysis/reels-plan.json"), plan)
        res = compile_reels_plan(ep)
        self.assertTrue(res["ok"], res["errors"])
        self.assertEqual(read_json(ep.p("01_analysis/reels-plan-validated.json"))["engine_version"],
                         stamps.engine_version())
        self.assertEqual(fresh_validated(ep)["fingerprint"], res["fingerprint"])

    def test_motion_plan_stamps(self):
        from lib.motion_plan import compile_motion
        from test_motion import good_script, motion_plan_fixture, test_font
        if test_font() is None:
            self.skipTest("no test font for HarfBuzz fitting")
        self.addCleanup(common.set_context, None)
        _root, _ep, reel_p = motion_plan_fixture(self.tmp)
        write_json(reel_p.p("01_analysis/motion-script.json"), good_script())
        self.assertEqual(schemas.validate(good_script(), "motion-script"), [])
        r = compile_motion(reel_p)
        self.assertTrue(r["ok"], r["errors"])
        self.assertEqual(read_json(reel_p.p("01_analysis/motion-plan.json"))["engine_version"], stamps.engine_version())

if __name__ == "__main__":
    unittest.main()
