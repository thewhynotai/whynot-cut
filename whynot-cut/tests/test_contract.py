"""Command contract v4 (3.0 T6.1): JSON Schemas, protocol constant, vendored stdlib validator. Run:
    bash tools/test.sh -p test_contract.py
The schemas describe the shape of every host command (Premiere / After Effects, through the CEP bridge today and the UXP
plugin + engine daemon later); the validator is the stdlib-only draft-2020-12 subset the engine uses (no jsonschema).
"""
import sys as _sys
_sys.dont_write_bytecode = True
import copy
import json
import re
import sys
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

import contract  # noqa: E402
from contract import validator as V  # noqa: E402

DRAFT = "https://json-schema.org/draft/2020-12/schema"
ID_BASE = "https://thewhynot.ai/whynot-cut/contract/4/"
ENVELOPES = {"request", "result", "progress"}
V4_ACTIONS = ["ping", "status", "probe", "build_project", "export_frames", "close_project_path", "clip_components",
              "open_project", "set_player_position", "render_review", "ae_build_motion", "ae_readback", "ae_render",
              "ae_fonts", "ae_probe_text"]
NOW = "2026-10-11T12:00:00Z"


def schema_files():
    return sorted(contract.CONTRACT_DIR.glob("*.schema.json"))


# ------------------------------------------------------------------------------------------------ sample instances
TRACKS = {"video": [{"i": 1, "name": "V1 Main Footage", "clips": 3}], "audio": [{"i": 1, "name": "A1 Dialogue L", "clips": 1}]}
SETTINGS_AFTER = {"previewCodec": "apcs", "previewFrameWidth": 1080, "previewFrameHeight": 1920, "videoFrameWidth": 1080,
                  "videoFrameHeight": 1920, "videoFrameRate": {"seconds": 0.0333667, "ticks": "8475667200"},
                  "compositeLinearColor": True, "maximumBitDepth": False, "maximumRenderQuality": False,
                  "audioSampleRate": {"seconds": 2.0833e-05, "ticks": "5292000"},
                  "workingColorSpace": {"name": "Rec. 709", "primaries": 1}, "gamutMappingControls": None}
PLAN = {"reel_id": "EP01_R01_MO", "format": "9x16", "w": 1080, "h": 1920, "fps": 30, "duration_frames": 900, "brand": {"controls": []},
        "scenes": [{"id": "S01", "type": "kinetic_quote", "start_frame": 0, "end_frame": 90, "layer_out_frame": 96,
                    "hero_frame": 45, "elements": []}],
        "persistent": {"captions": {"y": 1500, "size": 60}}, "word_reveal_s": 0.18}
JOB = {"plan": PLAN, "caps": {"composer_universal": True, "rtl_direction": "textdocument", "word_index_logical": True,
                              "fontobject": True, "emphasis_animator": True, "om_template": "High Quality"},
       "caps_source": "default", "aep_path": "C:/work/R01_MOTION.aep", "render_path": "C:/work/R01_MAIN.mov",
       "fallback_font": None, "generated": "2026-10-11T12:00:00+03:00"}
LAYER_TEXT = {"name": "S01_text_1", "kind": "text", "in": 0, "out": 96, "comment": "1f7fb70ab63b", "text": "hello",
              "font_ps": "SegoeUI-Bold", "substitute": False, "composer": "UNIVERSAL", "direction": "RTL",
              "direction_pr": None, "rect": [100.0, 400.0, 800.0, 200.0]}
LAYER_SHAPE = {"name": "S01_bar", "kind": "shape", "in": 0, "out": 96, "comment": ""}
SAMPLES = {
    "ping": {"data": {},
             "readback": {"version": "26.5.2", "build": "5", "project": "", "projects_open": 1}},
    "status": {"data": {},
               "readback": {"host": "premiere", "hostVersion": "26.5.2", "bundle": "1.0.0", "protocol": 4, "busy": False,
                            "project": None}},
    "probe": {"data": {},
              "readback": {"version": "26.5.2", "project": "C:/p/x.prproj",
                           "sequences": [{"name": "R01_EDIT", "settings": {"videoFrameWidth": 1080, "anything": [1]},
                                          "tracks": TRACKS}], "caption_constants": {"SUBTITLE": 1}}},
    "build_project": {
        "data": {"project_path": "C:/p/R01_EDIT.prproj", "overwrite_existing": False, "xml_path": "C:/p/base.xml",
                 "sequence_name": "R01_EDIT",
                 "settings": {"previewCodec": "apcs", "previewFrameWidth": 1080, "previewFrameHeight": 1920,
                              "maximumBitDepth": False, "maximumRenderQuality": False, "compositeLinearColor": True},
                 "graphics": [{"id": "GFX_1", "png": "C:/p/g1.png", "track_index": 3, "anim": "card", "start_s": 0.0,
                               "end_s": 2.5, "fade_in_s": 0.3, "fade_out_s": 0.2},
                              {"id": "CAP_1_bar", "png": "C:/p/c1.png", "track_index": 6, "anim": "bar_sweep", "start_s": 1,
                               "end_s": 2, "delay_f": 1, "sweep_f": 5}],
                 "srt_path": "C:/p/subs.srt", "native_caption_track": False,
                 "markers": [{"t": 0.5, "name": "GFX_1", "comment": "name_card | evidence"}],
                 "track_names": {"video": ["V1 Main Footage"], "audio": ["A1 Dialogue L"]}, "blur_v1_clips": [0, 2],
                 "sharpen_v1": {"amount": 20.0, "grain": 3.0}, "duration_s": 52.35},
        "readback": {"project": "C:/p/R01_EDIT.prproj", "saved": True, "newProject": True, "importXML": True,
                     "setSettings": True, "importGraphics": True, "settings_after": SETTINGS_AFTER,
                     "placed": [{"id": "GFX_1", "track": 4, "start": 0, "end": 2.5, "anim": "card"}],
                     "blurred": [{"clip": 0, "blurriness": None}], "sharpened": [{"clip": 0, "ok": True, "amount": 20}],
                     "renamed": ["V1 Main Footage"], "tracks": TRACKS, "log": []}},
    "export_frames": {
        "data": {"sequence_name": "R01_EDIT", "times": [2.5, 10.0], "out_dir": "C:/p/frames", "project_path": None},
        "readback": {"frames": [{"t": 2.5, "tc": "00:00:02:12", "file": "C:/p/frames/frame_002500.png", "called": True},
                                {"t": 10.0, "error": "Error: Unknown error exception"}]}},
    "close_project_path": {"data": {"path": "C:/p/R01_EDIT.prproj"},
                           "readback": {"closed": True, "path": "C:/p/R01_EDIT.prproj"}},
    "clip_components": {
        "data": {"sequence_name": "R01_EDIT", "track": 0, "clip": 1, "audio": False},
        "readback": {"clip": "EP01.mp4 [hold]",
                     "components": [{"name": "Opacity", "match": "AE.ADBE Opacity",
                                     "props": [{"name": "Opacity", "value": 100}, {"name": "Blend Mode", "value": "0"},
                                               {"name": "x", "value": None}]}]}},
    "open_project": {"data": {"path": "C:/p/R01_EDIT.prproj"},
                     "readback": {"opened": True, "project": "C:/p/R01_EDIT.prproj"}},
    "set_player_position": {"data": {"sequence_name": "R01_EDIT", "t_s": 12.5}, "readback": {"position_s": 12.5}},
    "render_review": {"data": {"sequence_name": "R01_EDIT", "out_path": "C:/p/review.mp4", "preset_path": "C:/p/p.epr"},
                      "readback": {"started": True, "out_path": "C:/p/review.mp4", "mode": "encoder"}},
    "ae_build_motion": {
        "data": {"job": JOB},
        "readback": {"ae_version": "26.5x89", "made": ["S01"], "failed": [{"scene": "S02", "error": "Error: x", "line": 12}],
                     "warnings": [], "saved": "C:/work/R01_MOTION.aep", "main": "MAIN_EP01_R01_MO"}},
    "ae_readback": {
        "data": {"job": JOB},
        "readback": {"main": {"name": "MAIN_EP01_R01_MO", "layers": 4, "duration_frames": 900},
                     "scenes": [{"id": "S01", "comp": "S01_kinetic_quote", "in_frame": 0, "out_frame": 96,
                                 "layers": [LAYER_TEXT, LAYER_SHAPE]}],
                     "missing_or_substituted": []}},
    "ae_render": {
        "data": {"aep_path": "C:/work/R01_MOTION.aep", "comp": "MAIN_EP01_R01_MO", "out_path": "C:/work/R01_MAIN.mov",
                 "render_settings_template": "Best Settings", "output_module_template": "High Quality",
                 "start_frame": 0, "end_frame": 95},
        "readback": {"status": "RENDERED", "returncode": 0, "output": "C:/work/R01_MAIN.mov", "elapsed_s": 41.2,
                     "log": None}},
    "ae_fonts": {
        "data": {"postscript_names": ["IBMPlexSansArabic-Bold"]},
        "readback": {"fonts": {"IBMPlexSansArabic-Bold": {"found": False, "substitute": False, "family": None,
                                                           "style": None}},
                     "missing_or_substituted": ["IBMPlexSansArabic-Bold"]}},
    "ae_probe_text": {
        "data": {"job": {"aep_path": "C:/probe/probe.aep", "w": 1080, "h": 1920, "fps": 30, "frames": 90,
                         "fonts": {"headline": "ArialMT"},
                         "comps": [{"name": "arabic_rtl", "font": "ArialMT", "size": 96, "text": "hello"},
                                   {"name": "word_layers", "font": "ArialMT", "size": 96, "text": "a b c", "word_layers": True,
                                    "cues": [15, 30, 45], "emphasis": [3]},
                                   {"name": "icon", "shapes": [{"vertices": [[0, 0], [1, 1]], "closed": False}],
                                    "stroke": 10}]}},
        "readback": {"ae_version": "26.5x89", "saved": "C:/probe/probe.aep", "om_templates": ["High Quality"],
                     "comps": [{"name": "arabic_rtl", "ok": True, "text": "hello", "composer": "UNIVERSAL",
                                "font_ps": "ArialMT", "requested_ps": "ArialMT", "substitute": False,
                                "direction_textdocument": "RTL", "direction_paragraph_range": "RTL",
                                "rect": [1.0, 2.0, 3.0, 4.0]},
                               {"name": "icon", "ok": False, "error": "Error: x", "line": 3}]}},
}
AE_PING = {"ae_version": "26.5x89", "project": None, "project_path": None, "dirty": None, "num_items": 0,
           "fonts_api": True, "libs_loaded": True, "scripts_dir": "C:/x/ae-scripts"}


def required_of(schema_name, defs_key):
    return V.load(schema_name)["$defs"][defs_key].get("required", [])


# ------------------------------------------------------------------------------------------------ files
class ContractFilesTests(unittest.TestCase):
    def test_protocol_is_4_and_exported(self):
        self.assertEqual(contract.PROTOCOL, 4)
        proto = json.loads((contract.CONTRACT_DIR / "protocol.json").read_text(encoding="utf-8"))
        self.assertEqual(proto["protocol"], 4)
        self.assertEqual(V.load("request")["properties"]["protocol"]["const"], 4)

    def test_protocol_lists_exactly_the_action_schema_files(self):
        proto = json.loads((contract.CONTRACT_DIR / "protocol.json").read_text(encoding="utf-8"))
        files = {p.name[:-len(".schema.json")] for p in schema_files()} - ENVELOPES
        self.assertEqual(set(proto["actions"]), files)
        self.assertEqual(set(contract.ACTIONS), files)
        self.assertEqual(sorted(contract.ACTIONS), sorted(V4_ACTIONS))
        self.assertEqual(len(contract.ACTIONS), 15)
        self.assertTrue(ENVELOPES <= {p.name[:-len(".schema.json")] for p in schema_files()})

    def test_protocol_entries_have_host_cep_uxp(self):
        proto = json.loads((contract.CONTRACT_DIR / "protocol.json").read_text(encoding="utf-8"))
        for name, e in proto["actions"].items():
            self.assertEqual(set(e), {"host", "cep", "uxp"}, name)
            self.assertIn(e["host"], ("premiere", "aftereffects", "engine", "any"), name)
            self.assertTrue(e["cep"] is None or (isinstance(e["cep"], str) and e["cep"]), name)
            self.assertIsInstance(e["uxp"], bool, name)
        self.assertEqual(proto["actions"]["ae_build_motion"]["cep"], "build_motion")
        self.assertEqual(proto["actions"]["ae_readback"]["cep"], "readback")
        self.assertEqual(proto["actions"]["ae_fonts"]["cep"], "fonts")
        self.assertEqual(proto["actions"]["ae_probe_text"]["cep"], "probe_text")
        self.assertIsNone(proto["actions"]["ae_render"]["cep"])
        self.assertEqual(proto["actions"]["ae_render"]["host"], "engine")
        for uxp_only in ("status", "open_project", "set_player_position", "render_review"):
            self.assertIsNone(proto["actions"][uxp_only]["cep"], uxp_only)
            self.assertTrue(proto["actions"][uxp_only]["uxp"], uxp_only)

    def test_cep_names_are_the_real_extendscript_actions(self):
        """No drift between protocol.json and what the CEP libraries actually register."""
        proto = json.loads((contract.CONTRACT_DIR / "protocol.json").read_text(encoding="utf-8"))
        pp = (SK / "templates/premiere/nh_ppro_lib.jsx").read_text(encoding="utf-8")
        ae = (SK / "templates/after_effects/nh_ae_bridge.jsx").read_text(encoding="utf-8")
        for name, e in proto["actions"].items():
            if not e["cep"]:
                continue
            if e["host"] == "aftereffects":
                self.assertIn(f"NHAE.actions.{e['cep']} =", ae, name)
            elif e["host"] == "premiere":
                self.assertIn(f"NHPP.actions.{e['cep']} =", pp, name)
            else:                                   # any: both hosts register it
                self.assertIn(f"NHPP.actions.{e['cep']} =", pp, name)
                self.assertIn(f"NHAE.actions.{e['cep']} =", ae, name)

    def test_every_schema_is_valid_json_with_the_right_header_and_checks(self):
        self.assertGreaterEqual(len(schema_files()), 18)
        for p in schema_files():
            doc = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(doc["$schema"], DRAFT, p.name)
            self.assertEqual(doc["$id"], ID_BASE + p.name, p.name)
            self.assertEqual(V.check_schema(doc), [], p.name)
            self.assertTrue(doc.get("title"), p.name)
            self.assertTrue(doc.get("description"), p.name)

    def test_schema_files_are_ascii(self):
        for p in list(schema_files()) + [contract.CONTRACT_DIR / "protocol.json"]:
            p.read_bytes().decode("ascii")

    def test_every_action_schema_has_data_and_readback(self):
        for a in contract.ACTIONS:
            defs = V.load(a)["$defs"]
            self.assertIn("data", defs, a)
            self.assertIn("readback", defs, a)
            self.assertTrue(defs["data"].get("description"), a)
            self.assertTrue(defs["readback"].get("description"), a)
            if defs["data"].get("type") == "object" and "properties" in defs["data"]:
                self.assertIs(defs["data"].get("additionalProperties"), False, f"{a} data must be closed")

    def test_request_schema_action_enum_is_the_registry(self):
        self.assertEqual(V.load("request")["properties"]["action"]["enum"], list(contract.ACTIONS))
        self.assertEqual(V.load("result")["properties"]["action"]["enum"], list(contract.ACTIONS))
        self.assertEqual(V.load("progress")["properties"]["action"]["enum"], list(contract.ACTIONS))

    def test_jsonschema_package_agrees_when_importable(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("jsonschema is not installed (it is not an engine dependency)")
        for p in schema_files():
            Draft202012Validator.check_schema(json.loads(p.read_text(encoding="utf-8")))

    def test_no_dependency_beyond_the_standard_library(self):
        for p in contract.CONTRACT_DIR.glob("*.py"):
            for line in p.read_text(encoding="utf-8").splitlines():
                m = re.match(r"\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", line)
                if m and m.group(1) not in ("__future__",):
                    self.assertIn(m.group(1), sys.stdlib_module_names, f"{p.name}: {line.strip()}")


# ------------------------------------------------------------------------------------------------ validator keywords
class ValidatorTests(unittest.TestCase):
    def ok(self, inst, schema):
        self.assertEqual(V.validate(inst, schema), [], (inst, schema))

    def bad(self, inst, schema, *contains):
        errs = V.validate(inst, schema)
        self.assertTrue(errs, (inst, schema))
        for c in contains:
            self.assertTrue(any(c in e for e in errs), (c, errs))
        return errs

    def test_type_single_and_list(self):
        for t, good, evil in [("string", "a", 1), ("object", {}, []), ("array", [], {}), ("boolean", False, 0),
                              ("null", None, 0), ("number", 1.5, "1"), ("integer", 3, "3")]:
            self.ok(good, {"type": t})
            self.bad(evil, {"type": t}, "expected " + t)
        self.ok(None, {"type": ["string", "null"]})
        self.ok("x", {"type": ["string", "null"]})
        self.bad(3, {"type": ["string", "null"]}, "string or null")

    def test_bool_is_not_a_number_or_integer(self):
        for v in (True, False):
            self.bad(v, {"type": "integer"})
            self.bad(v, {"type": "number"})
            self.bad(v, {"type": ["integer", "string"]})
        self.ok(True, {"type": "boolean"})
        self.bad(1, {"type": "boolean"})
        self.ok(3, {"type": "number"})
        self.ok(3.0, {"type": "integer"})            # 2020-12: 3.0 is an integer
        self.bad(3.5, {"type": "integer"})
        self.bad(float("nan"), {"type": "number"})
        self.bad(float("inf"), {"type": "number"})

    def test_properties_and_required(self):
        s = {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "string"}}, "required": ["a"]}
        self.ok({"a": 1}, s)
        self.ok({"a": 1, "b": "x", "extra": [1]}, s)
        self.bad({"b": "x"}, s, "required property 'a'")
        errs = self.bad({"a": "no"}, s)
        self.assertTrue(errs[0].startswith("/a:"), errs)

    def test_additional_properties_false_true_and_schema(self):
        closed = {"properties": {"a": {}}, "additionalProperties": False}
        self.ok({"a": 1}, closed)
        errs = self.bad({"a": 1, "zz": 2}, closed, "'zz'")
        self.assertTrue(errs[0].startswith("/zz:"), errs)
        self.ok({"a": 1, "zz": 2}, {"properties": {"a": {}}, "additionalProperties": True})
        typed = {"properties": {"a": {}}, "additionalProperties": {"type": "integer"}}
        self.ok({"a": "free", "n": 1}, typed)
        errs = self.bad({"a": "free", "n": "x"}, typed)
        self.assertTrue(errs[0].startswith("/n:"), errs)
        self.bad({"x": 1}, {"additionalProperties": False})

    def test_keywords_only_constrain_their_own_type(self):
        """A keyword for strings/numbers/arrays/objects says nothing about a value of another type (JSON Schema)."""
        self.ok(7, {"required": ["a"], "properties": {"a": {"type": "string"}}, "additionalProperties": False,
                    "minLength": 4, "maxLength": 1, "pattern": "z", "minItems": 2, "maxItems": 0, "items": {"type": "string"}})
        self.ok("text", {"minimum": 5, "maximum": 1, "minItems": 9, "required": ["a"], "additionalProperties": False})
        self.ok([1], {"minimum": 5, "minLength": 9, "required": ["a"], "pattern": "z", "additionalProperties": False})
        self.ok({"k": 1}, {"minimum": 5, "minLength": 9, "minItems": 9, "pattern": "z", "items": {"type": "string"}})

    def test_items_min_max_items_with_paths(self):
        s = {"type": "array", "items": {"type": "integer"}, "minItems": 1, "maxItems": 3}
        self.ok([1, 2, 3], s)
        self.bad([], s, "at least 1")
        self.bad([1, 2, 3, 4], s, "at most 3")
        errs = self.bad([1, "x", 3], s)
        self.assertTrue(errs[0].startswith("/1:"), errs)
        nested = {"properties": {"l": {"items": {"properties": {"n": {"type": "string"}}}}}}
        errs = self.bad({"l": [{"n": "a"}, {"n": 5}]}, nested)
        self.assertTrue(errs[0].startswith("/l/1/n:"), errs)

    def test_enum_and_const_are_type_exact(self):
        self.ok("a", {"enum": ["a", "b"]})
        self.bad("c", {"enum": ["a", "b"]}, "one of")
        self.bad(True, {"enum": [1, 2]})
        self.bad(1, {"enum": [True]})
        self.bad(0, {"const": False})
        self.ok(False, {"const": False})
        self.ok(4, {"const": 4})
        self.ok(4.0, {"const": 4})
        self.bad(5, {"const": 4}, "4")
        self.ok({"a": [1, {"b": None}]}, {"const": {"a": [1, {"b": None}]}})
        self.bad({"a": [True]}, {"const": {"a": [1]}})

    def test_numeric_bounds(self):
        s = {"minimum": 0, "maximum": 10}
        self.ok(0, s)
        self.ok(10, s)
        self.ok(5.5, s)
        self.bad(-0.1, s, "minimum")
        self.bad(10.1, s, "maximum")
        self.bad(True, {"type": "integer", "minimum": 0})

    def test_string_bounds_and_pattern(self):
        s = {"type": "string", "minLength": 2, "maxLength": 4, "pattern": "^[a-z]+$"}
        self.ok("abc", s)
        self.bad("a", s, "at least 2")
        self.bad("abcde", s, "at most 4")
        self.bad("ab1", s, "pattern")
        self.ok("xxabcxx", {"pattern": "abc"})                  # unanchored, as JSON Schema says
        self.ok("\u0639\u0631\u0628", {"maxLength": 3})         # code points, not bytes

    def test_any_of_and_one_of(self):
        a = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
        self.ok("x", a)
        self.ok(2, a)
        errs = self.bad(2.5, a, "anyOf")
        self.assertIn("expected", errs[0])                       # the failed branches are explained
        o = {"oneOf": [{"type": "number"}, {"type": "integer"}]}
        self.ok(1.5, o)
        self.bad(1, o, "exactly one")                           # both match
        self.bad("s", o, "oneOf")

    def test_date_time_format(self):
        s = {"type": "string", "format": "date-time"}
        for good in ("2026-10-11T12:00:00Z", "2026-10-11T12:00:00.123+03:00", "2026-10-11t12:00:00z",
                     "2026-02-28T23:59:59-05:30", "2024-02-29T00:00:00Z", "2026-12-31T23:59:60Z"):
            self.ok(good, s)
        for evil in ("2026-10-11", "2026-10-11T12:00:00", "2026-13-01T00:00:00Z", "2026-02-30T00:00:00Z",
                     "2026-10-11T25:00:00Z", "2026-10-11T12:61:00Z", "2026-10-11 12:00:00Z", "tomorrow", "", "2026-10-11T12:00Z",
                     "2026-10-11T12:00:00+3:00", "2023-02-29T00:00:00Z"):
            self.bad(evil, s, "date-time")
        self.ok(5, {"format": "date-time"})                      # format only constrains strings

    def test_annotations_are_ignored(self):
        self.ok(1, {"$schema": DRAFT, "$id": ID_BASE + "x.schema.json", "title": "t", "description": "d",
                    "examples": [1], "default": 1, "type": "integer"})

    def test_boolean_schemas(self):
        self.ok(1, True)
        self.bad(1, False)
        self.ok({"a": 1}, {"properties": {"a": True}})
        self.bad({"a": 1}, {"properties": {"a": False}})

    def test_ref_local(self):
        s = {"$defs": {"id": {"type": "string", "minLength": 1}},
             "properties": {"a": {"$ref": "#/$defs/id"}, "l": {"items": {"$ref": "#/$defs/id"}}}}
        self.ok({"a": "x", "l": ["y"]}, s)
        errs = self.bad({"a": "", "l": [3]}, s)
        self.assertTrue(any(e.startswith("/a:") for e in errs) and any(e.startswith("/l/0:") for e in errs), errs)

    def test_ref_root_and_siblings(self):
        tree = {"type": "object", "properties": {"kids": {"items": {"$ref": "#"}}, "n": {"type": "integer"}}}
        self.ok({"n": 1, "kids": [{"n": 2, "kids": [{}]}]}, tree)
        self.bad({"kids": [{"kids": [{"n": "x"}]}]}, tree)
        sib = {"$defs": {"a": {"type": "integer"}}, "$ref": "#/$defs/a", "minimum": 5}
        self.ok(7, sib)
        self.bad(3, sib, "minimum")
        self.bad("s", sib)

    def test_ref_across_files(self):
        s = {"properties": {"settings": {"$ref": "build_project.schema.json#/$defs/settings_after"}}}
        self.ok({"settings": SETTINGS_AFTER}, s)
        errs = self.bad({"settings": dict(SETTINGS_AFTER, previewCodec=5)}, s)
        self.assertTrue(errs[0].startswith("/settings/previewCodec:"), errs)
        # the file's own local refs keep resolving inside that file
        self.ok({"x": TRACKS}, {"properties": {"x": {"$ref": "build_project.schema.json#/$defs/tracks"}}})
        self.bad({"x": {"video": [{"i": "a"}], "audio": []}},
                 {"properties": {"x": {"$ref": "build_project.schema.json#/$defs/tracks"}}})

    def test_validate_by_name_and_pointer(self):
        self.ok({}, "ping#/$defs/data")
        self.ok(SAMPLES["build_project"]["data"], "build_project#/$defs/data")
        self.ok(SAMPLES["build_project"]["data"], "build_project.schema.json#/$defs/data")
        errs = self.bad(dict(SAMPLES["build_project"]["data"], sequence_name=5), "build_project#/$defs/data")
        self.assertTrue(errs[0].startswith("/sequence_name:"), errs)
        self.ok(PLAN, "ae_build_motion#/$defs/plan")
        self.ok(SAMPLES["ping"]["data"], "ping#/$defs/data")
        # a whole file with no pointer is valid input too (root keywords)
        self.ok({"protocol": 4, "id": "a", "action": "ping", "data": {}, "expires_at": NOW}, "request")
        self.bad({"protocol": 3}, "request")

    def test_unknown_schema_name_pointer_or_file_is_an_error_not_a_crash(self):
        with self.assertRaises(KeyError):
            V.load("no_such_action")
        with self.assertRaises(KeyError):
            V.validate({}, "no_such_action#/$defs/data")
        with self.assertRaises(KeyError):
            V.validate({}, "ping#/$defs/nope")
        for evil in ("../test_contract", "..\\x", "a/b", "ping.json", "", "C:/x"):
            with self.assertRaises(KeyError, msg=evil):
                V.load(evil)

    def test_ref_to_a_missing_target_is_a_validation_error(self):
        self.bad(1, {"$ref": "#/$defs/missing"}, "cannot resolve")
        self.bad(1, {"$ref": "nope.schema.json#/$defs/x"}, "cannot resolve")
        self.bad(1, {"$ref": "../../etc/passwd#/x"}, "cannot resolve")
        self.bad(1, {"$ref": "https://example.com/x.schema.json"}, "cannot resolve")

    def test_ref_loop_is_stopped(self):
        s = {"$defs": {"a": {"$ref": "#/$defs/b"}, "b": {"$ref": "#/$defs/a"}}, "$ref": "#/$defs/a"}
        self.bad(1, s, "too deep")

    def test_check_schema_accepts_every_supported_keyword(self):
        s = {"$schema": DRAFT, "$id": "x", "title": "t", "description": "d", "examples": [1], "default": 1,
             "$defs": {"d": {"type": "integer"}},
             "type": ["object"], "properties": {"a": {"$ref": "#/$defs/d"}}, "required": ["a"],
             "additionalProperties": {"type": "string"}, "items": {"type": "string"}, "minItems": 0, "maxItems": 3,
             "enum": [1, "a", None], "const": 1, "minimum": 0, "maximum": 1, "minLength": 0, "maxLength": 3,
             "pattern": "^a", "anyOf": [True, {"type": "null"}], "oneOf": [{"type": "string"}], "format": "date-time"}
        self.assertEqual(V.check_schema(s), [])
        self.assertEqual(V.check_schema(True), [])

    def test_check_schema_rejects_what_the_validator_does_not_support(self):
        for kw in ("allOf", "not", "if", "then", "else", "patternProperties", "prefixItems", "uniqueItems",
                   "multipleOf", "exclusiveMinimum", "dependentRequired", "contains", "$comment", "$anchor",
                   "propertyNames", "unevaluatedProperties", "minProperties", "$dynamicRef", "nullable"):
            errs = V.check_schema({kw: [] if kw in ("allOf",) else {}})
            self.assertTrue(any(kw in e and "unsupported" in e for e in errs), (kw, errs))
        errs = V.check_schema({"properties": {"a": {"items": {"allOf": []}}}})
        self.assertTrue(errs and errs[0].startswith("/properties/a/items:"), errs)
        errs = V.check_schema({"$defs": {"d": {"oneOf": [{"uniqueItems": True}]}}})
        self.assertTrue(errs and "/$defs/d/oneOf/0" in errs[0], errs)

    def test_check_schema_rejects_malformed_schemas(self):
        bad = [({"type": "strin"}, "type"), ({"type": []}, "type"), ({"type": 3}, "type"), ({"required": "a"}, "required"),
               ({"required": [1]}, "required"), ({"properties": []}, "properties"), ({"properties": {"a": 3}}, "properties/a"),
               ({"items": 3}, "items"), ({"minItems": -1}, "minItems"), ({"minItems": "1"}, "minItems"),
               ({"minItems": True}, "minItems"), ({"maxLength": 1.5}, "maxLength"), ({"minimum": "0"}, "minimum"),
               ({"enum": "ab"}, "enum"), ({"enum": []}, "enum"), ({"pattern": "("}, "pattern"), ({"pattern": 3}, "pattern"),
               ({"anyOf": []}, "anyOf"), ({"anyOf": {}}, "anyOf"), ({"oneOf": [3]}, "oneOf/0"),
               ({"format": "email"}, "format"), ({"additionalProperties": 3}, "additionalProperties"),
               ({"$ref": 3}, "$ref"), ({"$defs": []}, "$defs"), ({"$ref": "#/$defs/none"}, "cannot resolve"),
               ({"$ref": "ghost.schema.json#/$defs/x"}, "cannot resolve"), ({"$ref": "build_project.schema.json#/$defs/ghost"}, "cannot resolve"),
               ("string", "schema"), (3, "schema"), ([], "schema"), (None, "schema")]
        for schema, frag in bad:
            errs = V.check_schema(schema)
            self.assertTrue(errs and any(frag in e for e in errs), (schema, errs))

    def test_validate_never_mutates_the_instance_or_the_schema(self):
        inst, sch = copy.deepcopy(SAMPLES["build_project"]["data"]), copy.deepcopy(V.load("build_project"))
        before = (copy.deepcopy(inst), copy.deepcopy(sch))
        V.validate(inst, sch["$defs"]["data"])
        self.assertEqual((inst, sch), before)


# ------------------------------------------------------------------------------------------------ envelopes
class EnvelopeTests(unittest.TestCase):
    def req(self, **over):
        r = {"protocol": 4, "id": "20261011-120000-ab12cd", "action": "ping", "data": {}, "expires_at": NOW}
        r.update(over)
        return r

    def res(self, **over):
        r = {"ok": True, "action": "ping", "readback": copy.deepcopy(SAMPLES["ping"]["readback"])}
        r.update(over)
        return r

    def test_valid_request(self):
        self.assertEqual(V.validate_request(self.req()), [])
        self.assertEqual(V.validate_request(self.req(expires_at="2026-10-11T12:00:00+02:00")), [])
        self.assertEqual(V.validate_request(self.req(id="a")), [])
        self.assertEqual(V.validate_request(self.req(id="A._-9" * 12 + "xxxx")), [])        # 64 chars

    def test_request_wrong_protocol_unknown_action_bad_fields(self):
        for bad, frag in [(self.req(protocol=3), "/protocol"), (self.req(protocol=5), "/protocol"),
                          (self.req(protocol="4"), "/protocol"), (self.req(protocol=True), "/protocol"),
                          (self.req(action="delete_everything"), "/action"), (self.req(action="build_motion"), "/action"),
                          (self.req(action=None), "/action"), (self.req(id=""), "/id"), (self.req(id="x" * 65), "/id"),
                          (self.req(id="has space"), "/id"), (self.req(id="a/b"), "/id"), (self.req(id=5), "/id"),
                          (self.req(data=[]), "/data"), (self.req(data=None), "/data"), (self.req(data="x"), "/data"),
                          (self.req(expires_at="tomorrow"), "/expires_at"),
                          (self.req(expires_at="2026-10-11T12:00:00"), "/expires_at"),
                          (self.req(expires_at=1791720000), "/expires_at"), (self.req(extra=1), "/extra")]:
            errs = V.validate_request(bad)
            self.assertTrue(errs and any(e.startswith(frag + ":") for e in errs), (bad, errs))

    def test_request_missing_each_required_field(self):
        for k in ("protocol", "id", "action", "data", "expires_at"):
            r = self.req()
            del r[k]
            errs = V.validate_request(r)
            self.assertTrue(any(f"required property '{k}'" in e for e in errs), (k, errs))

    def test_request_not_an_object(self):
        for v in (None, [], "x", 4):
            self.assertTrue(V.validate_request(v))

    def test_request_data_is_validated_against_the_action(self):
        r = self.req(action="export_frames", data=copy.deepcopy(SAMPLES["export_frames"]["data"]))
        self.assertEqual(V.validate_request(r), [])
        r["data"]["times"] = ["x"]
        errs = V.validate_request(r)
        self.assertTrue(errs and errs[0].startswith("/data/times/0:"), errs)
        r = self.req(action="ping", data={"surprise": 1})
        self.assertTrue(any(e.startswith("/data/surprise:") for e in V.validate_request(r)))
        r = self.req(action="open_project", data={})
        self.assertTrue(any("required property 'path'" in e for e in V.validate_request(r)))

    def test_every_action_request_roundtrips(self):
        for a in contract.ACTIONS:
            r = self.req(action=a, data=copy.deepcopy(SAMPLES[a]["data"]))
            self.assertEqual(V.validate_request(r), [], a)

    def test_valid_results(self):
        self.assertEqual(V.validate_result(self.res()), [])
        self.assertEqual(V.validate_result(self.res(id="abc.1", how="Open a sequence first.")), [])
        self.assertEqual(V.validate_result({"ok": False, "action": "export_frames", "error": "sequence not found"}), [])
        self.assertEqual(V.validate_result({"ok": False, "action": "export_frames", "error": "x", "how": "y",
                                            "readback": {"frames": []}}), [])

    def test_result_ok_needs_a_readback_object(self):
        r = self.res()
        del r["readback"]
        errs = V.validate_result(r)
        self.assertTrue(errs, errs)
        self.assertTrue(V.validate_result(self.res(readback=None)))
        self.assertTrue(V.validate_result(self.res(readback=[])))
        self.assertTrue(V.validate_result(self.res(readback="done")))

    def test_result_bad_fields(self):
        for bad, frag in [(self.res(ok="true"), "/ok"), (self.res(ok=1), "/ok"), (self.res(action="nope"), "/action"),
                          (self.res(error=5), "/error"), (self.res(how=["x"]), "/how"), (self.res(id="a b"), "/id"),
                          (self.res(extra=1), "/extra")]:
            errs = V.validate_result(bad)
            self.assertTrue(errs and any(e.startswith(frag + ":") for e in errs), (bad, errs))
        for k in ("ok", "action"):
            r = self.res()
            del r[k]
            self.assertTrue(any(f"required property '{k}'" in e for e in V.validate_result(r)), k)
        self.assertTrue(V.validate_result(None))

    def test_result_readback_is_validated_against_the_action(self):
        r = {"ok": True, "action": "build_project", "readback": copy.deepcopy(SAMPLES["build_project"]["readback"])}
        self.assertEqual(V.validate_result(r), [])
        del r["readback"]["settings_after"]["previewCodec"]
        errs = V.validate_result(r)
        self.assertTrue(errs and errs[0].startswith("/readback/settings_after:"), errs)
        r = {"ok": True, "action": "export_frames", "readback": {"frames": [{"t": "x"}]}}
        self.assertTrue(any(e.startswith("/readback/frames/0") for e in V.validate_result(r)))

    def test_every_action_result_roundtrips(self):
        for a in contract.ACTIONS:
            r = {"ok": True, "action": a, "readback": copy.deepcopy(SAMPLES[a]["readback"])}
            self.assertEqual(V.validate_result(r), [], a)

    def test_failed_results_may_carry_a_partial_readback(self):
        dirty = {"ok": False, "action": "ae_build_motion", "error": "After Effects has unsaved changes",
                 "readback": {"reason": "dirty_target", "project": "x.aep", "project_path": "C:/x.aep"}}
        self.assertEqual(V.validate_result(dirty), [])
        dirty["readback"]["reason"] = 5
        self.assertTrue(V.validate_result(dirty))
        partial = {"ok": False, "action": "ae_build_motion", "error": "scene failed",
                   "readback": {"made": ["S01"], "failed": [{"scene": "S02", "error": "x", "line": None}], "warnings": []}}
        self.assertEqual(V.validate_result(partial), [])
        nf = {"ok": False, "action": "ae_readback", "error": "MAIN_x not found in the open project",
              "readback": {"reason": "MAIN_x not found in the open project"}}
        self.assertEqual(V.validate_result(nf), [])

    def test_progress(self):
        p = {"event": "progress", "id": "20261011-120000-ab12cd", "action": "build_project", "step": "placing graphics",
             "n": 3, "of": 58, "elapsed_s": 12.5}
        self.assertEqual(V.validate(p, "progress"), [])
        self.assertEqual(V.validate({k: p[k] for k in ("event", "id", "action", "step")}, "progress"), [])
        self.assertEqual(V.validate(dict(p, n=0), "progress"), [])
        for bad, frag in [(dict(p, event="done"), "/event"), (dict(p, id=""), "/id"), (dict(p, action="x"), "/action"),
                          (dict(p, step=3), "/step"), (dict(p, n=-1), "/n"), (dict(p, n=1.5), "/n"), (dict(p, of=0), "/of"),
                          (dict(p, elapsed_s="1"), "/elapsed_s"), (dict(p, elapsed_s=True), "/elapsed_s"),
                          (dict(p, extra=1), "/extra")]:
            errs = V.validate(bad, "progress")
            self.assertTrue(errs and any(e.startswith(frag + ":") for e in errs), (bad, errs))
        for k in ("event", "id", "action", "step"):
            q = dict(p)
            del q[k]
            self.assertTrue(any(f"required property '{k}'" in e for e in V.validate(q, "progress")), k)


# ------------------------------------------------------------------------------------------------ per-action shapes
class ActionShapeTests(unittest.TestCase):
    def test_samples_cover_every_action(self):
        self.assertEqual(set(SAMPLES), set(contract.ACTIONS))

    def test_valid_data_and_readback_per_action(self):
        for a in contract.ACTIONS:
            self.assertEqual(V.validate(SAMPLES[a]["data"], f"{a}#/$defs/data"), [], a)
            self.assertEqual(V.validate(SAMPLES[a]["readback"], f"{a}#/$defs/readback"), [], a)

    def test_data_is_closed_for_every_action(self):
        for a in contract.ACTIONS:
            d = copy.deepcopy(SAMPLES[a]["data"])
            d["surprise_field"] = 1
            errs = V.validate(d, f"{a}#/$defs/data")
            self.assertTrue(any(e.startswith("/surprise_field:") for e in errs), (a, errs))

    def test_data_required_fields_are_enforced(self):
        for a in contract.ACTIONS:
            for k in required_of(a, "data"):
                d = copy.deepcopy(SAMPLES[a]["data"])
                self.assertIn(k, d, f"{a}: sample lacks required {k}")
                del d[k]
                errs = V.validate(d, f"{a}#/$defs/data")
                self.assertTrue(any(f"required property '{k}'" in e for e in errs), (a, k, errs))

    def test_readback_required_fields_are_enforced(self):
        for a in contract.ACTIONS:
            req = required_of(a, "readback")
            if a == "ping":
                continue                                     # anyOf: covered by its own test
            self.assertTrue(req, f"{a}: readback has no required field")
            for k in req:
                rb = copy.deepcopy(SAMPLES[a]["readback"])
                self.assertIn(k, rb, f"{a}: sample lacks required {k}")
                del rb[k]
                errs = V.validate(rb, f"{a}#/$defs/readback")
                self.assertTrue(any(f"required property '{k}'" in e for e in errs), (a, k, errs))

    def test_the_engine_reads_are_required_in_readbacks(self):
        """Fields lib/ppro_build.py, motion_build.py, motion_readback.py and ae_probe.py read from a readback."""
        must = {"build_project": {"settings_after", "placed", "tracks", "sharpened"},
                "export_frames": {"frames"}, "close_project_path": {"closed"},
                "ae_build_motion": {"failed", "saved", "main"},
                "ae_readback": {"scenes", "missing_or_substituted", "main"},
                "ae_fonts": {"fonts"}, "ae_probe_text": {"ae_version", "comps", "om_templates"},
                "ae_render": {"status", "returncode", "output", "elapsed_s", "log"}}
        for a, fields in must.items():
            self.assertTrue(fields <= set(required_of(a, "readback")), (a, fields - set(required_of(a, "readback"))))
        sa = V.load("build_project")["$defs"]["settings_after"]["required"]
        for k in ("previewCodec", "videoFrameWidth", "videoFrameHeight", "videoFrameRate", "compositeLinearColor",
                  "maximumBitDepth", "maximumRenderQuality"):
            self.assertIn(k, sa)
        text = V.load("ae_readback")["$defs"]["text_layer"]["required"]
        for k in ("name", "kind", "in", "out", "comment", "text", "font_ps", "substitute", "composer", "direction",
                  "direction_pr"):                 # motion_readback.compare reads every one of these on a text layer
            self.assertIn(k, text)
        self.assertNotIn("rect", text)               # optional: rect_error stands in for it
        for k in ("name", "kind", "in", "out", "comment"):
            self.assertIn(k, V.load("ae_readback")["$defs"]["other_layer"]["required"])
        self.assertIn("format", V.load("ae_build_motion")["$defs"]["plan"]["required"])   # motion_build.build:239

    def test_ping_covers_both_hosts_and_rejects_neither(self):
        self.assertEqual(V.validate(SAMPLES["ping"]["readback"], "ping#/$defs/readback"), [])
        self.assertEqual(V.validate(AE_PING, "ping#/$defs/readback"), [])
        self.assertEqual(V.validate(dict(AE_PING, dirty=True, project="a.aep", project_path="C:/a.aep"), "ping#/$defs/readback"), [])
        self.assertEqual(V.validate({"version": "26.5.2", "build": "5", "project": None, "projects_open": None},
                                    "ping#/$defs/readback"), [])
        self.assertTrue(V.validate({}, "ping#/$defs/readback"))
        self.assertTrue(V.validate({"version": "26.5.2"}, "ping#/$defs/readback"))
        self.assertTrue(V.validate(dict(SAMPLES["ping"]["readback"], projects_open="2"), "ping#/$defs/readback"))
        self.assertTrue(V.validate(dict(AE_PING, dirty="no"), "ping#/$defs/readback"))
        self.assertTrue(V.validate({k: v for k, v in AE_PING.items() if k != "ae_version"}, "ping#/$defs/readback"))

    def test_status_is_uxp_only_minimal(self):
        rb = SAMPLES["status"]["readback"]
        self.assertEqual(set(required_of("status", "readback")), {"host", "hostVersion", "bundle", "protocol", "busy", "project"})
        for bad in (dict(rb, host="photoshop"), dict(rb, protocol="4"), dict(rb, busy=0), dict(rb, project=5), dict(rb, bundle=1)):
            self.assertTrue(V.validate(bad, "status#/$defs/readback"), bad)
        self.assertEqual(V.validate(dict(rb, host="aftereffects", project="C:/x.aep"), "status#/$defs/readback"), [])

    def test_build_project_data_negatives(self):
        base = SAMPLES["build_project"]["data"]
        bad = [("project_path", 5), ("overwrite_existing", "no"), ("graphics", {}), ("track_names", {"video": [1], "audio": []}),
               ("track_names", {"video": []}), ("markers", [{"t": "0", "name": "a", "comment": "b"}]),
               ("markers", [{"name": "a", "comment": "b"}]), ("native_caption_track", 1), ("blur_v1_clips", [-1]),
               ("blur_v1_clips", ["a"]), ("sharpen_v1", {"amount": "x", "grain": 1}), ("sharpen_v1", {"amount": 1}),
               ("duration_s", "52"), ("settings", {"previewCodec": 5}), ("settings", {"unknown": 1}),
               ("graphics", [{"id": "a", "png": "p", "track_index": 1, "anim": "wobble", "start_s": 0, "end_s": 1}]),
               ("graphics", [{"id": "a", "png": "p", "track_index": -1, "anim": "card", "start_s": 0, "end_s": 1}]),
               ("graphics", [{"id": "a", "png": "p", "track_index": 1, "anim": "card", "start_s": 0, "end_s": 1, "x": 1}]),
               ("graphics", [{"id": "a", "png": "p", "track_index": 1, "anim": "card", "start_s": 0}])]
        for k, v in bad:
            self.assertTrue(V.validate(dict(base, **{k: v}), "build_project#/$defs/data"), (k, v))
        ok = dict(base, sharpen_v1=None, graphics=[], markers=[], blur_v1_clips=[], native_caption_track=True)
        self.assertEqual(V.validate(ok, "build_project#/$defs/data"), [])
        for anim in ("flash", "text_pop", "bar_sweep", "slide", "push", "card", "fade"):
            g = [{"id": "a", "png": "p", "track_index": 1, "anim": anim, "start_s": 0, "end_s": 1}]
            self.assertEqual(V.validate(dict(base, graphics=g), "build_project#/$defs/data"), [], anim)

    def test_build_project_optional_fields_the_host_defaults(self):
        base = SAMPLES["build_project"]["data"]
        for k in ("overwrite_existing", "srt_path", "native_caption_track", "blur_v1_clips", "sharpen_v1", "duration_s"):
            self.assertEqual(V.validate({x: v for x, v in base.items() if x != k}, "build_project#/$defs/data"), [], k)
        for k in ("project_path", "xml_path", "sequence_name", "settings", "graphics", "markers", "track_names"):
            self.assertTrue(V.validate({x: v for x, v in base.items() if x != k}, "build_project#/$defs/data"), k)
        ef = SAMPLES["export_frames"]["data"]
        self.assertEqual(V.validate({k: v for k, v in ef.items() if k != "project_path"}, "export_frames#/$defs/data"), [])

    def test_build_project_readback_negatives(self):
        base = SAMPLES["build_project"]["readback"]
        for k, v in [("placed", [{"id": "a"}]), ("placed", "x"), ("tracks", {"video": []}), ("saved", "yes"),
                     ("sharpened", [{"clip": 0}]), ("blurred", [{"clip": "a", "blurriness": 1}]), ("log", [1]),
                     ("settings_after", {"previewCodec": "apcs"}), ("renamed", [1]),
                     ("tracks", {"video": [{"i": 1, "name": "x"}], "audio": []})]:
            self.assertTrue(V.validate(dict(base, **{k: v}), "build_project#/$defs/readback"), (k, v))
        # the Premiere dump is open: extra getSettings() fields are fine, wrong types of the checked ones are not
        sa = dict(SETTINGS_AFTER, newFutureField={"x": [1]}, vrLayout=0)
        self.assertEqual(V.validate(dict(base, settings_after=sa), "build_project#/$defs/readback"), [])
        for k, v in [("videoFrameRate", {"seconds": "1/30", "ticks": "1"}), ("videoFrameRate", 30),
                     ("videoFrameWidth", "1080"), ("compositeLinearColor", "true"), ("maximumBitDepth", 0)]:
            self.assertTrue(V.validate(dict(base, settings_after=dict(SETTINGS_AFTER, **{k: v})),
                                       "build_project#/$defs/readback"), (k, v))
        self.assertEqual(V.validate(dict(base, captionTrack=True), "build_project#/$defs/readback"), [])
        self.assertEqual(V.validate({k: v for k, v in base.items() if k not in ("blurred", "log", "renamed")},
                                    "build_project#/$defs/readback"), [])
        # the legacy CEP failure shape was an ok:true result carrying only {error}: not a valid v4 readback
        self.assertTrue(V.validate({"error": "project exists (set overwrite_existing)"}, "build_project#/$defs/readback"))

    def test_export_frames_shapes(self):
        rb = "export_frames#/$defs/readback"
        ok = {"t": 1.0, "tc": "00:00:01:00", "file": "C:/f.png", "called": True}
        self.assertEqual(V.validate({"frames": [ok, {"t": 2, "error": "boom"}]}, rb), [])
        self.assertEqual(V.validate({"frames": []}, rb), [])
        for bad in ({"frames": [{"t": 1.0, "tc": "x", "file": "f", "called": "yes"}]}, {"frames": [{"error": "x"}]},
                    {"frames": [{"t": 1, "tc": "x", "file": "f"}]}, {"frames": [dict(ok, error="x")]}, {"frames": {}}, {}):
            self.assertTrue(V.validate(bad, rb), bad)
        d = "export_frames#/$defs/data"
        base = SAMPLES["export_frames"]["data"]
        for k, v in [("times", []), ("times", [-1]), ("times", "1"), ("out_dir", ""), ("sequence_name", None),
                     ("project_path", 5)]:
            self.assertTrue(V.validate(dict(base, **{k: v}), d), (k, v))
        self.assertEqual(V.validate(dict(base, project_path="C:/p/x.prproj"), d), [])

    def test_small_premiere_actions_negatives(self):
        self.assertTrue(V.validate({"closed": "yes"}, "close_project_path#/$defs/readback"))
        self.assertEqual(V.validate({"closed": False, "reason": "not open"}, "close_project_path#/$defs/readback"), [])
        self.assertTrue(V.validate({"path": ""}, "close_project_path#/$defs/data"))
        self.assertTrue(V.validate({"sequence_name": "a", "track": -1}, "clip_components#/$defs/data"))
        self.assertTrue(V.validate({"sequence_name": "a", "audio": "x"}, "clip_components#/$defs/data"))
        self.assertEqual(V.validate({"sequence_name": "a"}, "clip_components#/$defs/data"), [])
        self.assertTrue(V.validate({"clip": "a", "components": [{"name": "Opacity", "match": "m"}]},
                                   "clip_components#/$defs/readback"))
        self.assertTrue(V.validate({"opened": 1, "project": "x"}, "open_project#/$defs/readback"))
        self.assertEqual(V.validate({"opened": False, "project": None}, "open_project#/$defs/readback"), [])
        self.assertTrue(V.validate({"sequence_name": "a", "t_s": "1"}, "set_player_position#/$defs/data"))
        self.assertTrue(V.validate({"sequence_name": "a", "t_s": -1}, "set_player_position#/$defs/data"))
        self.assertTrue(V.validate({"position_s": "1"}, "set_player_position#/$defs/readback"))
        self.assertEqual(V.validate({"sequence_name": "a", "out_path": "C:/o.mp4"}, "render_review#/$defs/data"), [])
        self.assertTrue(V.validate({"sequence_name": "a"}, "render_review#/$defs/data"))
        self.assertTrue(V.validate({"started": "y", "out_path": "p", "mode": "m"}, "render_review#/$defs/readback"))
        self.assertTrue(V.validate({"version": "1", "project": "x", "sequences": [{"name": "a"}]}, "probe#/$defs/readback"))

    def test_after_effects_job_negatives(self):
        d = "ae_build_motion#/$defs/data"
        self.assertTrue(V.validate({}, d))
        self.assertTrue(V.validate({"job": {k: v for k, v in JOB.items() if k != "plan"}}, d))
        self.assertTrue(V.validate({"job": dict(JOB, caps_source="guess")}, d))
        self.assertTrue(V.validate({"job": dict(JOB, aep_path=3)}, d))
        self.assertTrue(V.validate({"job": dict(JOB, mystery=1)}, d))                     # the job envelope is closed
        self.assertTrue(V.validate({"job": dict(JOB, plan={k: v for k, v in PLAN.items() if k != "scenes"})}, d))
        self.assertTrue(V.validate({"job": dict(JOB, plan=dict(PLAN, fps="30"))}, d))
        self.assertTrue(V.validate({"job": dict(JOB, plan=dict(PLAN, scenes=[{"id": "S01"}]))}, d))
        # the plan itself is the engine's open object: more fields are fine
        self.assertEqual(V.validate({"job": dict(JOB, plan=dict(PLAN, fingerprint="abc", theme={"x": 1}))}, d), [])
        self.assertEqual(V.validate({"job": dict(JOB, fallback_font="Arial", caps_source="probe")}, d), [])
        self.assertEqual(V.validate({"job": JOB}, "ae_readback#/$defs/data"), [])
        self.assertTrue(V.validate({"job": dict(JOB, caps="x")}, "ae_readback#/$defs/data"))

    def test_after_effects_readback_negatives(self):
        rb = "ae_readback#/$defs/readback"
        base = SAMPLES["ae_readback"]["readback"]
        self.assertTrue(V.validate(dict(base, main=None), rb))
        self.assertTrue(V.validate(dict(base, scenes=[{"id": "S01", "comp": "c", "in_frame": "0", "out_frame": 1, "layers": []}]), rb))
        self.assertTrue(V.validate(dict(base, scenes=[{"id": "S01", "comp": "c", "in_frame": 0, "out_frame": 1,
                                                      "layers": [dict(LAYER_TEXT, kind="video")]}]), rb))
        self.assertTrue(V.validate(dict(base, scenes=[{"id": "S01", "comp": "c", "in_frame": 0, "out_frame": 1,
                                                      "layers": [dict(LAYER_TEXT, rect=[1, 2, 3])]}]), rb))
        self.assertTrue(V.validate(dict(base, scenes=[{"id": "S01", "comp": "c", "in_frame": 0, "out_frame": 1,
                                                      "layers": [dict(LAYER_TEXT, substitute="no")]}]), rb))
        self.assertTrue(V.validate(dict(base, missing_or_substituted="Arial"), rb))
        text_with_error = dict(LAYER_TEXT, rect_error="Error: x")
        text_with_error.pop("rect")
        self.assertEqual(V.validate(dict(base, scenes=[{"id": "S01", "comp": "c", "in_frame": None, "out_frame": None,
                                                        "layers": [text_with_error]}]), rb), [])

    def test_after_effects_misc_negatives(self):
        self.assertTrue(V.validate({"status": "DONE", "returncode": 0, "output": "o", "elapsed_s": 1, "log": None},
                                   "ae_render#/$defs/readback"))
        self.assertEqual(V.validate({"status": "SKIPPED", "returncode": None, "output": "o", "elapsed_s": 0, "log": None,
                                     "msg": "aerender missing"}, "ae_render#/$defs/readback"), [])
        self.assertEqual(V.validate({"status": "FAILED", "returncode": 1, "output": "o", "elapsed_s": 2.5, "log": "C:/l.txt",
                                     "kept": "C:/stage/render.mov", "msg": "m"}, "ae_render#/$defs/readback"), [])
        d = "ae_render#/$defs/data"
        self.assertTrue(V.validate(dict(SAMPLES["ae_render"]["data"], start_frame=-1), d))
        self.assertTrue(V.validate(dict(SAMPLES["ae_render"]["data"], comp=""), d))
        self.assertEqual(V.validate({k: v for k, v in SAMPLES["ae_render"]["data"].items()
                                     if k not in ("start_frame", "end_frame")}, d), [])
        self.assertTrue(V.validate({"postscript_names": "Arial"}, "ae_fonts#/$defs/data"))
        self.assertTrue(V.validate({"postscript_names": [1]}, "ae_fonts#/$defs/data"))
        self.assertEqual(V.validate({"postscript_names": []}, "ae_fonts#/$defs/data"), [])
        self.assertTrue(V.validate({"fonts": {"A": {"found": True}}, "missing_or_substituted": []}, "ae_fonts#/$defs/readback"))
        self.assertEqual(V.validate({"fonts": {"A": {"found": True, "substitute": False, "family": "Arial", "style": "Bold"}},
                                     "missing_or_substituted": []}, "ae_fonts#/$defs/readback"), [])
        pt = SAMPLES["ae_probe_text"]["data"]
        self.assertTrue(V.validate({"job": dict(pt["job"], w="1080")}, "ae_probe_text#/$defs/data"))
        self.assertTrue(V.validate({"job": dict(pt["job"], comps=[{"text": "no name"}])}, "ae_probe_text#/$defs/data"))
        self.assertTrue(V.validate({"job": dict(pt["job"], comps=[{"name": "a", "cues": ["1"]}])}, "ae_probe_text#/$defs/data"))
        self.assertTrue(V.validate({"job": dict(pt["job"], comps=[{"name": "a", "mystery": 1}])}, "ae_probe_text#/$defs/data"))
        self.assertTrue(V.validate(dict(SAMPLES["ae_probe_text"]["readback"], comps=[{"name": "a"}]),
                                   "ae_probe_text#/$defs/readback"))
        self.assertTrue(V.validate(dict(SAMPLES["ae_probe_text"]["readback"], om_templates="High Quality"),
                                   "ae_probe_text#/$defs/readback"))
        self.assertTrue(V.validate(dict(SAMPLES["ae_build_motion"]["readback"], failed=[{"scene": "S1"}]),
                                   "ae_build_motion#/$defs/readback"))
        self.assertTrue(V.validate(dict(SAMPLES["ae_build_motion"]["readback"], made="S01"), "ae_build_motion#/$defs/readback"))

    def test_text_layer_needs_everything_the_comparison_reads(self):
        rb = "ae_readback#/$defs/readback"
        base = SAMPLES["ae_readback"]["readback"]

        def with_layer(layer):
            return dict(base, scenes=[{"id": "S01", "comp": "c", "in_frame": 0, "out_frame": 1, "layers": [layer]}])
        self.assertEqual(V.validate(with_layer(LAYER_TEXT), rb), [])
        for k in ("text", "font_ps", "substitute", "composer", "direction", "direction_pr"):
            errs = V.validate(with_layer({x: v for x, v in LAYER_TEXT.items() if x != k}), rb)
            self.assertTrue(errs and any("/scenes/0/layers/0" in e for e in errs), (k, errs))
        self.assertTrue(V.validate(with_layer({"name": "S01_text_1", "kind": "text", "in": 0, "out": 9, "comment": ""}), rb))
        for k, v in (("text", 5), ("font_ps", None), ("substitute", "no"), ("composer", 1), ("direction", 3),
                     ("direction_pr", 3)):
            self.assertTrue(V.validate(with_layer(dict(LAYER_TEXT, **{k: v})), rb), k)
        # nullable direction fields, the measured box optional (rect_error stands in), shapes carry no text fields
        self.assertEqual(V.validate(with_layer(dict(LAYER_TEXT, composer=None, direction=None, direction_pr="RTL")), rb), [])
        self.assertEqual(V.validate(with_layer({x: v for x, v in dict(LAYER_TEXT, rect_error="x").items() if x != "rect"}), rb), [])
        self.assertEqual(V.validate(with_layer(LAYER_SHAPE), rb), [])
        self.assertEqual(V.validate(with_layer(dict(LAYER_SHAPE, kind="other")), rb), [])
        self.assertTrue(V.validate(with_layer({k: v for k, v in LAYER_SHAPE.items() if k != "comment"}), rb))

    def test_plan_needs_its_format(self):
        d = "ae_build_motion#/$defs/data"
        self.assertTrue(any("'format'" in e for e in V.validate({"job": dict(JOB, plan={k: v for k, v in PLAN.items() if k != "format"})}, d)))
        self.assertTrue(V.validate({"job": dict(JOB, plan=dict(PLAN, format=""))}, d))
        self.assertTrue(V.validate({"job": dict(JOB, plan=dict(PLAN, format=916))}, d))
        self.assertTrue(any("'format'" in e for e in V.validate({"job": {k: v for k, v in JOB.items() if k != "plan"}
                                                                  | {"plan": {k: v for k, v in PLAN.items() if k != "format"}}},
                                                                 "ae_readback#/$defs/data")))


class EcmaParityTests(unittest.TestCase):
    """`$` and digits behave like ECMA-262 / ajv, not like Python: no match before a final newline, ASCII digits only."""

    def test_date_time_rejects_a_trailing_newline_and_non_ascii_digits(self):
        s = {"type": "string", "format": "date-time"}
        self.assertEqual(V.validate("2026-10-11T12:00:00Z", s), [])
        for evil in ("2026-10-11T12:00:00Z\n", "2026-10-11T12:00:00+03:00\n", "\n2026-10-11T12:00:00Z",
                     "2026-10-11T12:00:00Z ", "\u0662\u0660\u0662\u0666-10-11T12:00:00Z"):
            self.assertTrue(V.validate(evil, s), repr(evil))

    def test_request_expires_at_and_id_reject_a_trailing_newline(self):
        req = {"protocol": 4, "id": "abc", "action": "ping", "data": {}, "expires_at": NOW}
        self.assertEqual(V.validate_request(req), [])
        self.assertTrue(any(e.startswith("/id:") for e in V.validate_request(dict(req, id="abc\n"))))
        self.assertTrue(any(e.startswith("/expires_at:") for e in V.validate_request(dict(req, expires_at=NOW + "\n"))))
        res = {"ok": False, "action": "ping", "id": "abc\n"}
        self.assertTrue(any(e.startswith("/id:") for e in V.validate_result(res)))
        prog = {"event": "progress", "id": "abc\n", "action": "ping", "step": "x"}
        self.assertTrue(any(e.startswith("/id:") for e in V.validate(prog, "progress")))

    def test_pattern_dollar_means_end_of_input(self):
        s = {"type": "string", "pattern": "^[a-z]+$"}
        self.assertEqual(V.validate("abc", s), [])
        self.assertTrue(V.validate("abc\n", s))
        self.assertTrue(V.validate("abc\n\n", s))
        self.assertEqual(V.validate("abc\n", {"pattern": "^abc"}), [])                  # no `$`: unaffected
        self.assertEqual(V.validate("a$", {"pattern": r"^a\$$"}), [])                   # an escaped dollar is a literal
        self.assertTrue(V.validate("a$\n", {"pattern": r"^a\$$"}))
        self.assertEqual(V.validate("a$b", {"pattern": "^a[$]b$"}), [])                 # inside a class: a literal
        self.assertEqual(V.validate("a\\", {"pattern": r"^a\\$"}), [])                  # escaped backslash, then `$`
        self.assertTrue(V.validate("a\\\n", {"pattern": r"^a\\$"}))
        self.assertEqual(V.validate("b", {"pattern": "^(a$|b$)"}), [])
        self.assertTrue(V.validate("b\n", {"pattern": "^(a$|b$)"}))
        self.assertEqual(V.check_schema({"pattern": "^[A-Za-z0-9._-]+$"}), [])
        self.assertTrue(V.check_schema({"pattern": "[a-"}))

    def test_names_and_refs_reject_a_trailing_newline(self):
        for evil in ("ping\n", "ping.schema.json\n", "protocol\n", "\nping", "ping "):
            with self.assertRaises(KeyError, msg=repr(evil)):
                V.load(evil)
        with self.assertRaises(KeyError):
            V.validate({}, "ping\n#/$defs/data")
        self.assertTrue(V.validate(1, {"$ref": "ping.schema.json\n#/$defs/data"}))
        self.assertTrue(V.check_schema({"$ref": "ping.schema.json\n#/$defs/data"}))
        self.assertEqual(V.validate({}, {"$ref": "ping.schema.json#/$defs/data"}), [])


if __name__ == "__main__":
    unittest.main()
