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
SESSION = "session"           # the daemon-link WebSocket message schema: neither an action nor a host envelope
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
        files = {p.name[:-len(".schema.json")] for p in schema_files()} - ENVELOPES - {SESSION}
        self.assertEqual(set(proto["actions"]), files)
        self.assertEqual(set(contract.ACTIONS), files)
        self.assertEqual(sorted(contract.ACTIONS), sorted(V4_ACTIONS))
        self.assertEqual(len(contract.ACTIONS), 15)
        self.assertTrue(ENVELOPES | {SESSION} <= {p.name[:-len(".schema.json")] for p in schema_files()})

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

    def test_uxp_flag_is_the_planned_target_not_a_measurement(self):
        """Final review C2: `uxp` says what the plugin is meant to implement; routing uses what the plugin reports."""
        proto = json.loads((contract.CONTRACT_DIR / "protocol.json").read_text(encoding="utf-8"))
        d = proto["description"]
        self.assertIn("planned", d)
        self.assertIn("meant to implement", d)
        self.assertIn("runtime", d)
        self.assertIn("uxp-parity.md", d)
        self.assertNotIn("whether the UXP plugin implements it", d)

    def test_final_review_descriptions(self):
        """C1, C3, C4, C5, C8: the facts the UXP adapter relies on are written where a reader looks."""
        bp = V.load("build_project")
        for text in (bp["$defs"]["data"]["properties"]["settings"]["properties"]["previewCodec"]["description"],
                     bp["$defs"]["settings_after"]["properties"]["previewCodec"]["description"]):
            self.assertIn("FourCC", text)
            self.assertIn("Apple ProRes 422 LT", text)
            self.assertIn("UXP adapter", text)
            self.assertIn("pass through", text)
        paths = [V.load("open_project")["$defs"]["readback"]["properties"]["project"],
                 V.load("status")["$defs"]["readback"]["properties"]["project"],
                 V.load("probe")["$defs"]["readback"]["properties"]["project"],
                 V.load("ping")["$defs"]["premiere"]["properties"]["project"]]
        for prop in paths:
            self.assertIn("native OS path", prop["description"])
            self.assertIn("\\?\\", prop["description"])
        self.assertIn("native OS path", bp["$defs"]["readback"]["properties"]["project"]["description"])
        ef = V.load("export_frames")["$defs"]["readback"]["properties"]["frames"]["items"]["oneOf"][0]
        self.assertNotIn("tc", ef["required"])
        self.assertIn("tc", ef["properties"])
        self.assertIn("the export call reported success", ef["properties"]["called"]["description"])
        pr = V.load("ping")["$defs"]["premiere"]
        self.assertNotIn("build", pr["required"])
        self.assertIn("build", pr["properties"])
        self.assertIn("REFUSED", V.load("ae_render")["$defs"]["readback"]["properties"]["status"]["enum"])

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

    def test_result_ok_forbids_error_and_failure_requires_it(self):
        """Final review C6: the envelope is one shape per outcome, the schema says so."""
        self.assertTrue(V.validate_result(self.res(error="x")))                       # ok:true with an error
        self.assertTrue(V.validate_result({"ok": False, "action": "ping"}))           # ok:false without one
        self.assertTrue(V.validate_result({"ok": False, "action": "export_frames", "how": "y", "readback": {"frames": []}}))
        self.assertTrue(V.validate_result({"ok": False, "action": "ping", "readback": {"version": "1"}}))
        self.assertEqual(V.validate_result({"ok": False, "action": "ping", "error": "x"}), [])
        self.assertEqual(V.validate_result(self.res()), [])
        schema = V.load("result")
        self.assertEqual(V.check_schema(schema), [])
        self.assertEqual(V.validate({"ok": True, "action": "ping", "readback": {}, "error": "x"}, "result") != [], True)

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
        for k in ("name", "kind", "in", "out", "comment", "text", "font_ps", "substitute", "composer", "direction"):
            self.assertIn(k, text)                   # motion_readback.compare reads every one of these on a text layer
        self.assertNotIn("rect", text)               # optional: rect_error stands in for it
        self.assertNotIn("direction_pr", text)       # optional: an alternative to direction, omitted by the JSX on AE 25.2
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

    def test_export_frames_without_a_timecode_and_ping_without_a_build(self):
        """Final review C4/C5: UXP exports by TickTime (no timecode string) and has no build number."""
        rb = "export_frames#/$defs/readback"
        self.assertEqual(V.validate({"frames": [{"t": 1.0, "file": "C:/f.png", "called": True}]}, rb), [])
        self.assertTrue(V.validate({"frames": [{"t": 1.0, "tc": 5, "file": "C:/f.png", "called": True}]}, rb))
        self.assertEqual(V.validate({"version": "26.5.2", "project": "", "projects_open": 1}, "ping#/$defs/readback"), [])
        self.assertTrue(V.validate({"version": "26.5.2", "build": 5, "project": "", "projects_open": 1}, "ping#/$defs/readback"))

    def test_ae_render_can_be_refused(self):
        """Final review C8: lib/ae_render.py reports REFUSED (G79)."""
        rb = dict(SAMPLES["ae_render"]["readback"], status="REFUSED", returncode=None, msg="no render under the sandbox")
        self.assertEqual(V.validate(rb, "ae_render#/$defs/readback"), [])
        self.assertTrue(V.validate(dict(rb, status="DENIED"), "ae_render#/$defs/readback"))

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
        for k in ("text", "font_ps", "substitute", "composer", "direction"):
            errs = V.validate(with_layer({x: v for x, v in LAYER_TEXT.items() if x != k}), rb)
            self.assertTrue(errs and any("/scenes/0/layers/0" in e for e in errs), (k, errs))
        self.assertTrue(V.validate(with_layer({"name": "S01_text_1", "kind": "text", "in": 0, "out": 9, "comment": ""}), rb))
        for k, v in (("text", 5), ("font_ps", None), ("substitute", "no"), ("composer", 1), ("direction", 3),
                     ("direction_pr", 3), ("direction_pr", 5)):
            self.assertTrue(V.validate(with_layer(dict(LAYER_TEXT, **{k: v})), rb), k)
        # nullable direction fields, the measured box optional (rect_error stands in), shapes carry no text fields
        self.assertEqual(V.validate(with_layer(dict(LAYER_TEXT, composer=None, direction=None, direction_pr="RTL")), rb), [])
        self.assertEqual(V.validate(with_layer({x: v for x, v in dict(LAYER_TEXT, rect_error="x").items() if x != "rect"}), rb), [])
        # direction_pr is optional: the JSX omits it when paragraphRange(0).direction throws (After Effects 25.2 path)
        self.assertEqual(V.validate(with_layer({x: v for x, v in LAYER_TEXT.items() if x != "direction_pr"}), rb), [])
        self.assertEqual(V.validate(with_layer(dict(LAYER_TEXT, direction_pr="LTR")), rb), [])
        self.assertTrue(V.validate(with_layer(dict(LAYER_TEXT, direction_pr=5)), rb))
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

    def test_the_docstring_records_the_date_time_differences_from_ajv(self):
        """Final review C9: the Python subset and ajv-formats 3.0.1 disagree on exotic date-times; the module says where."""
        doc = V.__doc__
        for frag in ("ajv-formats 3.0.1", "space separator", "+0300", "+03", ":60", "23:59:60", "expires_at",
                     "isoformat()", "toISOString()"):
            self.assertIn(frag, doc)
        from datetime import datetime, timezone
        self.assertEqual(V.validate(datetime.now(timezone.utc).isoformat(), {"type": "string", "format": "date-time"}), [])
        self.assertEqual(V.validate(datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                                    {"type": "string", "format": "date-time"}), [])

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



# ================================================================================================ golden fixtures (T6.1)
# Real Premiere 26.5.2 / After Effects 26.5 answers (PODCAST-TEST recordings) pin the contract; cep.py is the pure adapter
# between the CEP queue's parsed response and a v4 result.
import ast  # noqa: E402
import contextlib  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
from unittest import mock  # noqa: E402

from contract import cep  # noqa: E402

FIXTURES = SK / "tests" / "fixtures" / "contract"
CEP_ENVELOPE = ("action", "job_id", "submitted")


def fixture_json(action, name):
    return json.loads((FIXTURES / action / name).read_text(encoding="utf-8"))


def fixture_name(variant, base):
    """The main pair is request.json / result.json / cep-data.json / cep-result.json; a variant is <variant>.<base>."""
    return f"{variant}.{base}" if variant else base


def fixture_variants(action):
    """"" (the main pair) and one name per <variant>.request.json next to it."""
    return [""] + sorted(p.name[:-len(".request.json")] for p in (FIXTURES / action).glob("*.request.json"))


def every_fixture():
    """(action, variant) for every golden pair."""
    return [(a, v) for a in V4_ACTIONS for v in fixture_variants(a)]


def parse_cep_result(outer):
    """What cep_queue.submit does with the panel's `<id>.result.json`: {ok, result: <JSON string or object>, at}."""
    inner = outer.get("result")
    return json.loads(inner) if isinstance(inner, str) else inner


def real_client_tokens():
    """test_plugin's own list of real-client words, read from its source (this file must not spell them out)."""
    tree = ast.parse((SK / "tests" / "test_plugin.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "REAL_CLIENT_TOKENS" for t in node.targets):
            return [t.lower() for t in ast.literal_eval(node.value)]
    raise AssertionError("REAL_CLIENT_TOKENS not found in test_plugin.py")


def strings_in(obj):
    """Every string in a JSON value, looking inside strings that hold JSON (the CEP queue's `result`)."""
    if isinstance(obj, str):
        yield obj
        if obj[:1] in "{[":
            try:
                yield from strings_in(json.loads(obj))
            except ValueError:
                pass
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from strings_in(k)
            yield from strings_in(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings_in(v)


def wrong_kind(v):
    """A JSON value of a different kind than v (what a host bug would send)."""
    if isinstance(v, bool):
        return "yes"
    if isinstance(v, (int, float)):
        return "n/a"
    if isinstance(v, str):
        return 7
    if isinstance(v, list):
        return "nope"
    if isinstance(v, dict):
        return [1]
    return 7


def edited(obj, path, new=None, drop=False):
    """A deep copy of obj with the value at path replaced (or the key removed)."""
    out = copy.deepcopy(obj)
    node = out
    for step in path[:-1]:
        node = node[step]
    if drop:
        del node[path[-1]]
    else:
        node[path[-1]] = new
    return out


def readback_required(action, readback):
    """The required keys of the readback schema (for ping: of the host form the readback matches)."""
    d = V.load(action)["$defs"]["readback"]
    if "required" in d:
        return d["required"]
    for alt in d.get("anyOf", []):
        sub = V.load(action)["$defs"][alt["$ref"].rsplit("/", 1)[-1]]
        if not V.validate(readback, sub):
            return sub.get("required", [])
    return []


# ------------------------------------------------------------------------------------------------ the fixture folder
class GoldenFixtureFilesTests(unittest.TestCase):
    def test_every_action_has_a_folder_and_nothing_else_is_there(self):
        self.assertTrue(FIXTURES.is_dir(), FIXTURES)
        self.assertEqual(sorted(p.name for p in FIXTURES.iterdir() if p.is_dir()), sorted(V4_ACTIONS))
        for a in V4_ACTIONS:
            for base in ("request.json", "result.json"):
                self.assertTrue((FIXTURES / a / base).is_file(), f"{a}/{base}")

    def test_index_says_what_was_recorded(self):
        index = json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(index), sorted(V4_ACTIONS))
        for a, e in index.items():
            self.assertIs(type(e["recorded"]), bool, a)
            self.assertTrue(isinstance(e["source"], str) and e["source"], a)
            self.assertIsInstance(e["host_version"], str, a)
            self.assertTrue(e["recorded"] is False or e["host_version"], f"{a}: a recording names its host version")
            self.assertTrue(set(e) <= {"recorded", "source", "host_version", "variants"}, a)
        # the actions that were never run against a live host (T6.9 records them)
        for a in ("status", "probe", "open_project", "set_player_position", "render_review", "ae_render"):
            self.assertIs(index[a]["recorded"], False, a)
        for a in ("ping", "build_project", "export_frames", "close_project_path", "clip_components", "ae_build_motion",
                  "ae_readback", "ae_fonts", "ae_probe_text"):
            self.assertIs(index[a]["recorded"], True, a)

    def test_a_recording_keeps_its_raw_cep_pair(self):
        index = json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))
        for a in V4_ACTIONS:
            have = (FIXTURES / a / "cep-result.json").is_file()
            self.assertEqual(have, index[a]["recorded"], a)
            if have:
                self.assertTrue((FIXTURES / a / "cep-data.json").is_file(), a)
        for a in V4_ACTIONS:
            for v in index[a].get("variants", {}):
                self.assertIn(v, fixture_variants(a), f"{a}: index names variant {v!r} that has no fixture")
        for a, v in every_fixture():
            if v:
                self.assertIn(v, index[a].get("variants", {}), f"{a}: variant {v!r} is not described in index.json")

    def test_readme_names_every_action_and_variant(self):
        text = (FIXTURES / "README.md").read_text(encoding="utf-8")
        for a, v in every_fixture():
            self.assertIn(a, text)
            if v:
                self.assertIn(v, text, f"{a}/{v}")
        for word in ("_trimmed_from", "PODCAST-TEST", "recorded"):
            self.assertIn(word, text)

    def test_no_real_client_name_and_no_machine_user_in_any_fixture(self):
        tokens = real_client_tokens()
        self.assertGreaterEqual(len(tokens), 4)
        files = [p for p in FIXTURES.rglob("*") if p.is_file()]
        self.assertGreater(len(files), 30)
        for p in files:
            raw = p.read_text(encoding="utf-8")
            texts = [raw]
            if p.suffix == ".json":
                texts = list(strings_in(json.loads(raw)))
            for t in texts:
                low = t.lower()
                self.assertEqual([k for k in tokens if k in low], [], p.name)
                for evil in ("loq", "pegasus"):
                    self.assertNotIn(evil, low, f"{p.relative_to(FIXTURES)} names the machine owner")


# ------------------------------------------------------------------------------------------------ golden pairs validate
class GoldenFixtureValidationTests(unittest.TestCase):
    def test_every_request_validates(self):
        for a, v in every_fixture():
            req = fixture_json(a, fixture_name(v, "request.json"))
            self.assertEqual(V.validate_request(req), [], (a, v))
            self.assertEqual((req["protocol"], req["action"]), (4, a), (a, v))

    def test_every_result_validates(self):
        for a, v in every_fixture():
            res = fixture_json(a, fixture_name(v, "result.json"))
            self.assertEqual(V.validate_result(res), [], (a, v))
            self.assertEqual(res["action"], a, (a, v))

    def test_a_result_echoes_its_request_id(self):
        for a, v in every_fixture():
            req = fixture_json(a, fixture_name(v, "request.json"))
            res = fixture_json(a, fixture_name(v, "result.json"))
            self.assertEqual(res.get("id"), req["id"], (a, v))

    def test_ok_results_carry_a_readback_failures_carry_error(self):
        seen = set()
        for a, v in every_fixture():
            res = fixture_json(a, fixture_name(v, "result.json"))
            seen.add(res["ok"])
            if res["ok"]:
                self.assertTrue(res["readback"], (a, v))
                self.assertNotIn("error", res, (a, v))
            else:
                self.assertTrue(isinstance(res.get("error"), str) and res["error"].strip(), (a, v))
        self.assertEqual(seen, {True, False})

    def test_failure_variants_of_the_recorded_runs(self):
        """What the host really said when it failed: a script error, a refusal, a half-built project, a project that exists."""
        shapes = {("build_project", "exists"), ("export_frames", "error"), ("ae_build_motion", "failed_scenes"),
                  ("ae_build_motion", "dirty"), ("close_project_path", "not_open"), ("ping", "aftereffects")}
        self.assertTrue(shapes <= set(every_fixture()), shapes - set(every_fixture()))
        for a, v in shapes - {("close_project_path", "not_open"), ("ping", "aftereffects")}:
            self.assertIs(fixture_json(a, fixture_name(v, "result.json"))["ok"], False, (a, v))

    def test_the_dirty_refusal_keeps_what_motion_build_decides_on(self):
        res = fixture_json("ae_build_motion", "dirty.result.json")
        self.assertIs(res["ok"], False)
        self.assertEqual(res["readback"]["reason"], "dirty")
        self.assertTrue(res["readback"]["project"])
        self.assertNotIn("ok", res["readback"])
        self.assertEqual(V.validate_result(res), [])
        self.assertTrue(V.validate_result(edited(res, ("readback", "reason"), 5)))     # readback_failure checks the types

    def test_build_project_that_exists_is_a_failure_not_an_ok_with_a_lone_error(self):
        raw = parse_cep_result(fixture_json("build_project", "exists.cep-result.json"))
        self.assertEqual(raw["ok"], True)                                        # what Premiere's CEP bridge really answered
        self.assertEqual(raw["result"], {"error": "project exists (set overwrite_existing)"})
        res = fixture_json("build_project", "exists.result.json")
        self.assertIs(res["ok"], False)
        self.assertIn("project exists", res["error"])
        self.assertTrue(res["how"])
        self.assertNotIn("readback", res)


# ------------------------------------------------------------------------------------------------ cep.py against the recordings
class CepAdapterFixtureTests(unittest.TestCase):
    def test_every_raw_cep_result_converts_to_its_golden_result(self):
        n = 0
        for a, v in every_fixture():
            p = FIXTURES / a / fixture_name(v, "cep-result.json")
            if not p.is_file():
                continue
            n += 1
            inner = parse_cep_result(json.loads(p.read_text(encoding="utf-8")))
            req = fixture_json(a, fixture_name(v, "request.json"))
            want = fixture_json(a, fixture_name(v, "result.json"))
            got = cep.from_cep(a, inner, id=req["id"])
            self.assertEqual(got, want, (a, v))
            self.assertEqual(V.validate_result(got), [], (a, v))
        self.assertGreaterEqual(n, 13)

    def test_every_raw_cep_request_converts_to_its_golden_request(self):
        n = 0
        for a, v in every_fixture():
            p = FIXTURES / a / fixture_name(v, "cep-data.json")
            if not p.is_file():
                continue
            n += 1
            data = json.loads(p.read_text(encoding="utf-8"))
            req = fixture_json(a, fixture_name(v, "request.json"))
            self.assertEqual(data["action"], cep.CEP_NAME[a], (a, v))
            self.assertTrue(set(CEP_ENVELOPE) <= set(data), (a, v))
            got = cep.to_request(a, cep.data_from_cep(data), id=req["id"], expires_at=req["expires_at"])
            self.assertEqual(got, req, (a, v))
            self.assertEqual(V.validate_request(got), [], (a, v))
        self.assertGreaterEqual(n, 10)

    def test_the_raw_pairs_have_the_queue_shape(self):
        for a, v in every_fixture():
            p = FIXTURES / a / fixture_name(v, "cep-result.json")
            if not p.is_file():
                continue
            outer = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(set(outer), {"ok", "result", "at"}, (a, v))
            self.assertIsInstance(outer["result"], str, (a, v))                  # as the panel writes it
            inner = parse_cep_result(outer)
            self.assertEqual(inner["action"], cep.CEP_NAME[a], (a, v))
            self.assertIn("ok", inner)


# ------------------------------------------------------------------------------------------------ cep.py, by itself
class CepAdapterTests(unittest.TestCase):
    EXPIRES = "2026-10-11T12:15:00Z"

    def test_cep_names_come_from_protocol_json(self):
        proto = V.load("protocol")["actions"]
        self.assertEqual(cep.CEP_NAME, {a: e["cep"] for a, e in proto.items() if e["cep"]})
        self.assertEqual(cep.CEP_NAME["ae_build_motion"], "build_motion")
        self.assertEqual(cep.CEP_NAME["ae_readback"], "readback")
        self.assertEqual(cep.CEP_NAME["ae_fonts"], "fonts")
        self.assertEqual(cep.CEP_NAME["ae_probe_text"], "probe_text")
        for a in ("status", "open_project", "set_player_position", "render_review", "ae_render"):
            self.assertNotIn(a, cep.CEP_NAME)
        self.assertEqual({cep.V4_NAME[c]: c for c in cep.V4_NAME}, {a: c for c, a in cep.V4_NAME.items()})
        self.assertEqual(cep.V4_NAME["probe_text"], "ae_probe_text")
        self.assertNotIn("probe_frame_paths", cep.V4_NAME)

    def test_to_request_builds_the_envelope_and_copies_the_data(self):
        data = {"sequence_name": "EP02TEST_R02_RE_EDIT", "times": [1.5, 2.5], "out_dir": "D:/p/frames"}
        req = cep.to_request("export_frames", data, id="job-1", expires_at=self.EXPIRES)
        self.assertEqual(req, {"protocol": 4, "id": "job-1", "action": "export_frames", "data": data,
                               "expires_at": self.EXPIRES})
        self.assertEqual(V.validate_request(req), [])
        data["times"].append(3.5)
        data["out_dir"] = "changed"
        self.assertEqual(req["data"], {"sequence_name": "EP02TEST_R02_RE_EDIT", "times": [1.5, 2.5], "out_dir": "D:/p/frames"})  # not shared
        self.assertEqual(cep.to_request("ping", None, id="j", expires_at=self.EXPIRES)["data"], {})

    def test_to_request_refuses_an_unknown_action_and_needs_id_and_expiry(self):
        with self.assertRaises(ValueError):
            cep.to_request("nope", {}, id="j", expires_at=self.EXPIRES)
        with self.assertRaises(TypeError):
            cep.to_request("ping", {})
        with self.assertRaises(TypeError):
            cep.to_request("ping", {}, "j", self.EXPIRES)                  # keyword-only
        for a in V4_ACTIONS:
            self.assertEqual(cep.to_request(a, {}, id="j", expires_at=self.EXPIRES)["action"], a)

    def test_data_from_cep_drops_only_the_queue_bookkeeping(self):
        raw = {"path": "D:/p.prproj", "action": "close_project_path", "job_id": "j", "submitted": "2026-10-11T01:00:00+03:00"}
        self.assertEqual(cep.data_from_cep(raw), {"path": "D:/p.prproj"})
        self.assertIn("job_id", raw)                                         # the input is untouched

    def test_ok_answer_becomes_ok_with_the_readback(self):
        inner = {"ok": True, "action": "ping", "result": {"version": "26.5.2", "build": "5", "project": "", "projects_open": 1}}
        res = cep.from_cep("ping", inner)
        self.assertEqual(res, {"ok": True, "action": "ping", "readback": inner["result"]})
        self.assertEqual(V.validate_result(res), [])
        self.assertEqual(cep.from_cep("ping", inner, id="req-9")["id"], "req-9")
        self.assertNotIn("id", res)
        self.assertEqual(inner["result"], {"version": "26.5.2", "build": "5", "project": "", "projects_open": 1})   # not consumed
        self.assertIsNot(res["readback"], inner["result"])                                  # not shared either

    def test_the_hosts_own_ok_flag_is_the_envelopes_not_the_readbacks(self):
        inner = {"ok": True, "action": "build_motion", "result": {"made": ["S01"], "failed": [], "warnings": [], "saved": "a.aep",
                                                               "main": "MAIN_x", "ae_version": "26.5x89", "ok": True}}
        self.assertNotIn("ok", cep.from_cep("ae_build_motion", inner)["readback"])

    def test_a_lone_error_inside_an_ok_answer_is_a_failure(self):
        """Premiere's CEP build_project said ok:true with {error: "project exists (set overwrite_existing)"}."""
        inner = {"ok": True, "action": "build_project", "result": {"error": "project exists (set overwrite_existing)"}}
        res = cep.from_cep("build_project", inner, id="b-1")
        self.assertIs(res["ok"], False)
        self.assertEqual(res["error"], "project exists (set overwrite_existing)")
        self.assertIn("overwrite_existing", res["how"])
        self.assertNotIn("readback", res)
        self.assertEqual(res["id"], "b-1")
        self.assertEqual(V.validate_result(res), [])
        other = cep.from_cep("build_project", {"ok": True, "action": "build_project", "result": {"error": "something new"}})
        self.assertEqual((other["ok"], other["error"]), (False, "something new"))
        self.assertEqual(V.validate_result(other), [])

    def test_the_second_build_project_failure_return_is_a_failure_too(self):
        """nh_ppro_lib.jsx build_project returns {error, log} when the XML import made no sequence (ok:true on the wire)."""
        inner = {"ok": True, "action": "build_project", "result": {"error": "sequence not found after XML import", "log": ["a"]}}
        res = cep.from_cep("build_project", inner, id="b-2")
        self.assertEqual(res, {"ok": False, "action": "build_project", "id": "b-2", "error": "sequence not found after XML import",
                               "readback": {"log": ["a"]}})
        self.assertEqual(V.validate_result(res), [])
        self.assertIs(cep.from_cep("build_project", dict(inner, result={"error": "x", "log": []}))["ok"], False)
        self.assertNotIn("how", res)

    def test_any_ok_answer_with_a_text_error_is_a_failure_and_the_readback_must_fit(self):
        res = cep.from_cep("ae_build_motion", {"ok": True, "action": "build_motion",
                                               "result": {"error": "boom", "made": ["S01"], "failed": []}})
        self.assertEqual((res["ok"], res["error"], res["readback"]), (False, "boom", {"made": ["S01"], "failed": []}))
        self.assertEqual(V.validate_result(res), [])
        wrong = cep.from_cep("ae_build_motion", {"ok": True, "action": "build_motion", "result": {"error": "boom", "made": "S01"}})
        self.assertEqual((wrong["ok"], wrong["error"]), (False, "boom"))
        self.assertNotIn("readback", wrong)                                    # does not fit readback_failure: left out
        self.assertEqual(V.validate_result(wrong), [])
        for empty in ("", "   ", None, 5):                                     # not an error sentence: an ok result
            self.assertIs(cep.from_cep("probe", {"ok": True, "action": "probe", "result": {"version": "1", "project": "",
                                                                                          "sequences": [], "error": empty}})["ok"], True, empty)

    def test_the_host_script_failing_is_quoted_and_points_at_the_host(self):
        """The panel writes {ok:false, result:"EvalScript error."} when the script dies in the host; cep_queue passes the string on."""
        for given in ("EvalScript error.", {"ok": False, "result": "EvalScript error."},
                      {"ok": False, "action": "ping", "result": "EvalScript error."}):
            res = cep.from_cep("ping", given, id="p-1")
            self.assertEqual(res["error"], "The bridge script failed in the host (EvalScript error.)")
            self.assertIs(res["ok"], False)
            self.assertEqual(res["id"], "p-1")
            self.assertIn("host", res["how"])
            self.assertNotIn("panel is open", res["how"])
            self.assertEqual(V.validate_result(res), [])
        other = cep.from_cep("ae_fonts", "ReferenceError: x is not defined")
        self.assertEqual(other["error"], "The bridge script failed in the host (ReferenceError: x is not defined)")

    def test_every_failure_the_legacy_bridge_can_report_gives_a_valid_result(self):
        """Property: each CEP shape known from the JSX, the panel and cep_queue, for every action that has a CEP name."""
        shapes = [
            {"ok": True, "action": "{n}", "result": {"error": "project exists (set overwrite_existing)"}},
            {"ok": True, "action": "{n}", "result": {"error": "sequence not found after XML import", "log": []}},
            {"ok": True, "action": "{n}", "result": {"error": "imported item not found", "log": ["a"], "made": "bad"}},
            {"ok": False, "action": "{n}", "error": "ReferenceError: x", "line": 12},
            {"ok": False, "error": "bad data file: SyntaxError"}, {"ok": False, "error": "unknown action x"},
            {"ok": False, "error": "script not in whitelisted folder", "script": "C:/x.jsx", "at": 1},
            {"ok": False, "error": "no reply from PPRO within 15 min", "at": 1},
            {"ok": False, "error": "bridge not running", "status": {"alive": False, "host": None, "detail": "no heartbeat"}},
            {"ok": False, "error": "timeout after 600s (Premiere may show a dialog)", "job": "j"},
            {"ok": False, "action": "{n}", "result": {"ok": False, "reason": "dirty", "project": None, "project_path": None}},
            {"ok": False, "action": "{n}", "result": {"ok": False, "reason": "dirty_target", "project": "a.aep", "project_path": "D:/a.aep"}},
            {"ok": False, "action": "{n}", "result": {"ok": False, "reason": "MAIN_x not found in the open project"}},
            {"ok": False, "action": "{n}", "result": {"ok": False, "reason": 5, "project": 7}},
            {"ok": False, "action": "{n}", "result": {"ok": False, "failed": [{"scene": "S01", "error": "e", "line": 1}], "made": []}},
            {"ok": False, "action": "{n}", "result": {"ok": False, "failed": "bad"}},
            {"ok": False, "action": "{n}", "result": {"ok": False}}, {"ok": False, "action": "{n}", "result": {}},
            {"ok": False, "action": "{n}", "result": "EvalScript error."}, "EvalScript error.", "",
            {"ok": True, "action": "{n}"}, {"ok": True, "action": "{n}", "result": "text"}, {"ok": True, "action": "other"},
            {"ok": False}, {}, None, 7, [],
        ]
        n = 0
        for a, name in cep.CEP_NAME.items():
            for shape in shapes:
                given = json.loads(json.dumps(shape).replace("{n}", name))
                res = cep.from_cep(a, given, id="prop-1")
                n += 1
                self.assertEqual(V.validate_result(res), [], (a, shape))
                self.assertIs(res["ok"], False, (a, shape))
                self.assertTrue(res["error"].strip(), (a, shape))
        self.assertEqual(n, len(shapes) * len(cep.CEP_NAME))

    def test_a_script_error_becomes_a_failure_with_the_line(self):
        inner = {"ok": False, "action": "export_frames", "error": "TypeError: null is not an object", "line": 337}
        res = cep.from_cep("export_frames", inner, id="e-1")
        self.assertEqual(res, {"ok": False, "action": "export_frames", "id": "e-1",
                               "error": "TypeError: null is not an object (script line 337)"})
        self.assertEqual(V.validate_result(res), [])
        self.assertEqual(cep.from_cep("export_frames", {"ok": False, "action": "export_frames", "error": "boom"})["error"], "boom")

    def test_refusals_keep_their_reason_in_the_readback(self):
        """motion_build.build tells REFUSED from FAILED by readback.reason ("dirty" / "dirty_target")."""
        for reason in ("dirty", "dirty_target"):
            inner = {"ok": False, "action": "build_motion",
                     "result": {"ok": False, "reason": reason, "project": "x.aep", "project_path": "D:/p/x.aep"}}
            res = cep.from_cep("ae_build_motion", inner)
            self.assertIs(res["ok"], False)
            self.assertEqual(res["readback"], {"reason": reason, "project": "x.aep", "project_path": "D:/p/x.aep"})
            self.assertIn("unsaved changes", res["error"])
            self.assertIn("x.aep", res["error"])
            self.assertTrue(res["how"])
            self.assertEqual(V.validate_result(res), [])
        untitled = cep.from_cep("ae_probe_text", {"ok": False, "action": "probe_text",
                                                  "result": {"ok": False, "reason": "dirty", "project": None}})
        self.assertIn("an untitled project", untitled["error"])
        self.assertEqual(V.validate_result(untitled), [])

    def test_an_unknown_reason_is_passed_through_as_the_error(self):
        inner = {"ok": False, "action": "readback", "result": {"ok": False, "reason": "MAIN_EP01_R01_MO not found in the open project"}}
        res = cep.from_cep("ae_readback", inner)
        self.assertEqual(res["error"], "MAIN_EP01_R01_MO not found in the open project")
        self.assertEqual(res["readback"], {"reason": "MAIN_EP01_R01_MO not found in the open project"})
        self.assertEqual(V.validate_result(res), [])

    def test_scenes_that_did_not_build_are_a_failure_with_the_partial_readback(self):
        inner = {"ok": False, "action": "build_motion",
                 "result": {"made": ["S04"], "failed": [{"scene": "S01", "error": "Error: font", "line": 23},
                                                        {"scene": "S02", "error": "Error: font", "line": 23}],
                            "warnings": [], "saved": "a.aep", "main": "MAIN_x", "ae_version": "26.5x89", "ok": False}}
        res = cep.from_cep("ae_build_motion", inner)
        self.assertIs(res["ok"], False)
        self.assertEqual(res["readback"]["made"], ["S04"])
        self.assertEqual(len(res["readback"]["failed"]), 2)
        self.assertNotIn("ok", res["readback"])
        self.assertIn("2 scenes", res["error"])
        self.assertIn("S01", res["error"])
        self.assertEqual(V.validate_result(res), [])

    def test_an_outer_how_is_forwarded(self):
        """Final review C7: a bridge answer that already carries a `how` keeps it over the derived one."""
        res = cep.from_cep("ping", {"ok": False, "error": "bridge not running", "how": "Open the panel.",
                                    "status": {"alive": False, "detail": "no heartbeat"}})
        self.assertEqual(res["how"], "Open the panel.")
        res = cep.from_cep("build_project", {"ok": False, "error": "timeout after 9s", "how": "Wait for the dialog."})
        self.assertEqual(res["how"], "Wait for the dialog.")
        res = cep.from_cep("build_project", {"ok": False, "error": "timeout after 9s", "how": ""})
        self.assertIn("dialog", res["how"])                                   # empty outer how: the derivation stays
        self.assertEqual(V.validate_result(res), [])

    def test_when_the_bridge_never_answered(self):
        """cep_queue.submit's own failures: no bridge, a timeout (the response is not an {ok, action, result} at all)."""
        down = cep.from_cep("ping", {"ok": False, "error": "bridge not running",
                                     "status": {"alive": False, "host": None, "detail": "no heartbeat: start Premiere"}})
        self.assertEqual((down["ok"], down["error"], down["how"]), (False, "bridge not running", "no heartbeat: start Premiere"))
        late = cep.from_cep("build_project", {"ok": False, "error": "timeout after 900s (Premiere may show a dialog)", "job": "j"})
        self.assertIs(late["ok"], False)
        self.assertIn("timeout", late["error"])
        self.assertTrue(late["how"])
        for bad in (None, "", [], 7, "nonsense"):
            res = cep.from_cep("ping", bad)
            self.assertIs(res["ok"], False, bad)
            self.assertTrue(res["error"] and res["how"], bad)
            self.assertEqual(V.validate_result(res), [], bad)
        for res in (down, late):
            self.assertEqual(V.validate_result(res), [])

    def test_an_answer_to_a_different_action_is_not_taken_for_this_one(self):
        res = cep.from_cep("export_frames", {"ok": True, "action": "probe", "result": {"version": "1", "project": "", "sequences": []}})
        self.assertIs(res["ok"], False)
        self.assertIn("probe", res["error"])
        self.assertIn("export_frames", res["error"])
        self.assertEqual(V.validate_result(res), [])
        self.assertIs(cep.from_cep("ping", {"ok": True, "result": {"version": "1", "build": "1", "project": "", "projects_open": 0}})["ok"],
                      True)                                              # an answer that names no action is accepted

    def test_ok_without_a_result_object_is_a_failure(self):
        for inner in ({"ok": True, "action": "ping"}, {"ok": True, "action": "ping", "result": "text"},
                      {"ok": True, "action": "ping", "result": None}, {"ok": True, "action": "ping", "result": [1]}):
            res = cep.from_cep("ping", inner)
            self.assertIs(res["ok"], False, inner)
            self.assertEqual(V.validate_result(res), [], inner)

    def test_only_actions_with_a_cep_name_can_be_converted(self):
        for a in ("status", "open_project", "set_player_position", "render_review", "ae_render"):
            with self.assertRaises(ValueError, msg=a):
                cep.from_cep(a, {"ok": True, "action": a, "result": {}})
        with self.assertRaises(ValueError):
            cep.from_cep("nope", {"ok": True})

    def test_adapter_is_pure(self):
        src = (SK / "engine" / "reel" / "contract" / "cep.py").read_text(encoding="utf-8")
        for evil in ("open(", "subprocess", "socket", "os.environ", "Path(", "write_text", "read_text", "time.sleep"):
            self.assertNotIn(evil, src, evil)


# ------------------------------------------------------------------------------------------------ mutations of the goldens
class GoldenNegativeTests(unittest.TestCase):
    """Dropping or mistyping what the engine reads must be rejected, on the real recorded shapes."""

    # (action, path into the readback): read by ppro_build.build, motion_build.build, motion_readback.compare, ae_probe
    ENGINE_READS = [
        ("build_project", ("settings_after", "previewCodec")), ("build_project", ("settings_after", "videoFrameWidth")),
        ("build_project", ("settings_after", "videoFrameHeight")), ("build_project", ("settings_after", "videoFrameRate")),
        ("build_project", ("settings_after", "videoFrameRate", "seconds")),
        ("build_project", ("settings_after", "compositeLinearColor")), ("build_project", ("settings_after", "maximumBitDepth")),
        ("build_project", ("settings_after", "maximumRenderQuality")),
        ("build_project", ("placed",)), ("build_project", ("placed", 0, "id")), ("build_project", ("sharpened", 0, "ok")),
        ("build_project", ("tracks", "audio")), ("build_project", ("tracks", "audio", 0, "clips")),
        ("build_project", ("tracks", "video", 0, "name")),
        ("export_frames", ("frames",)), ("export_frames", ("frames", 0, "t")), ("export_frames", ("frames", 0, "file")),
        ("close_project_path", ("closed",)),
        ("ae_build_motion", ("failed",)), ("ae_build_motion", ("saved",)), ("ae_build_motion", ("main",)),
        ("ae_build_motion", ("made",)), ("ae_build_motion", ("ae_version",)),
        ("ae_readback", ("scenes",)), ("ae_readback", ("scenes", 0, "layers")), ("ae_readback", ("scenes", 0, "in_frame")),
        ("ae_readback", ("scenes", 0, "out_frame")), ("ae_readback", ("scenes", 0, "id")),
        ("ae_readback", ("scenes", 0, "layers", 0, "text")), ("ae_readback", ("scenes", 0, "layers", 0, "font_ps")),
        ("ae_readback", ("scenes", 0, "layers", 0, "substitute")), ("ae_readback", ("scenes", 0, "layers", 0, "composer")),
        ("ae_readback", ("scenes", 0, "layers", 0, "direction")), ("ae_readback", ("missing_or_substituted",)),
        ("ae_readback", ("main", "name")),
        ("ae_fonts", ("fonts",)), ("ae_fonts", ("missing_or_substituted",)),
        ("ae_probe_text", ("ae_version",)), ("ae_probe_text", ("comps",)), ("ae_probe_text", ("om_templates",)),
        ("ping", ("version",)), ("ping", ("project",)),
    ]

    def test_dropping_a_required_readback_key_is_rejected(self):
        n = 0
        for a, v in every_fixture():
            res = fixture_json(a, fixture_name(v, "result.json"))
            if not res["ok"] or not res.get("readback"):
                continue
            for k in readback_required(a, res["readback"]):
                n += 1
                bad = edited(res, ("readback", k), drop=True)
                errs = V.validate_result(bad)
                self.assertTrue(errs, f"{a}/{v or 'main'}: readback without {k} was accepted")
        self.assertGreater(n, 40)

    def test_a_required_readback_key_of_the_wrong_type_is_rejected(self):
        for a, v in every_fixture():
            res = fixture_json(a, fixture_name(v, "result.json"))
            if not res["ok"] or not res.get("readback"):
                continue
            for k in readback_required(a, res["readback"]):
                bad = edited(res, ("readback", k), wrong_kind(res["readback"][k]))
                self.assertTrue(V.validate_result(bad), f"{a}/{v or 'main'}: readback.{k} = {bad['readback'][k]!r} was accepted")

    def test_what_the_engine_reads_is_checked_in_the_recorded_readbacks(self):
        for a, path in self.ENGINE_READS:
            res = fixture_json(a, "result.json")
            node = res["readback"]
            for step in path:
                node = node[step]                                  # the golden has it (KeyError/IndexError: fixture too small)
            errs = V.validate_result(edited(res, ("readback",) + path, drop=True)) if isinstance(path[-1], str) else None
            if errs is not None:
                self.assertTrue(errs, f"{a}: dropping readback.{'.'.join(map(str, path))} was accepted")
            errs = V.validate_result(edited(res, ("readback",) + path, wrong_kind(node)))
            self.assertTrue(errs, f"{a}: readback.{'.'.join(map(str, path))} = {wrong_kind(node)!r} was accepted")

    def test_a_readback_that_is_not_an_object_is_rejected(self):
        for a in V4_ACTIONS:
            res = fixture_json(a, "result.json")
            if res["ok"]:
                for junk in ("done", [res["readback"]], 3, None):
                    self.assertTrue(V.validate_result(dict(res, readback=junk)), (a, junk))

    def test_the_failure_readbacks_are_typed(self):
        for a in ("ae_build_motion", "ae_probe_text", "ae_readback"):
            res = {"ok": False, "action": a, "error": "x", "readback": {"reason": "dirty"}}
            self.assertEqual(V.validate_result(res), [], a)
            self.assertTrue(V.validate_result(dict(res, readback={"reason": 3})), a)
        for a in ("ae_build_motion", "ae_probe_text"):
            res = {"ok": False, "action": a, "error": "x", "readback": {"reason": "dirty", "project": None}}
            self.assertEqual(V.validate_result(res), [], a)
            self.assertTrue(V.validate_result(dict(res, readback={"reason": "dirty", "project": 3})), a)
        bm = fixture_json("ae_build_motion", "failed_scenes.result.json")
        self.assertEqual(V.validate_result(bm), [])
        self.assertTrue(V.validate_result(edited(bm, ("readback", "failed", 0, "scene"), 5)))
        self.assertTrue(V.validate_result(edited(bm, ("readback", "failed"), "S01")))

    def test_a_request_without_a_required_data_key_is_rejected(self):
        n = 0
        for a, v in every_fixture():
            req = fixture_json(a, fixture_name(v, "request.json"))
            for k in V.load(a)["$defs"]["data"].get("required", []):
                n += 1
                self.assertTrue(V.validate_request(edited(req, ("data", k), drop=True)), f"{a}/{v or 'main'}: data without {k}")
        self.assertGreater(n, 15)

    def test_a_request_with_a_mistyped_or_unknown_data_key_is_rejected(self):
        for a, v in every_fixture():
            req = fixture_json(a, fixture_name(v, "request.json"))
            sch = V.load(a)["$defs"]["data"]
            if sch.get("additionalProperties") is False:
                self.assertTrue(V.validate_request(edited(req, ("data", "mystery_key"), 1)), (a, v))
            for k, val in req["data"].items():
                if "type" in (sch.get("properties", {}).get(k) or {}) or "$ref" in (sch.get("properties", {}).get(k) or {}):
                    bad = edited(req, ("data", k), wrong_kind(val))
                    self.assertTrue(V.validate_request(bad), f"{a}/{v or 'main'}: data.{k} = {bad['data'][k]!r} was accepted")

    def test_the_envelope_is_checked_around_a_golden_request(self):
        req = fixture_json("build_project", "request.json")
        for bad in (dict(req, protocol=3), dict(req, action="build"), dict(req, id=""), dict(req, expires_at="soon"),
                    dict(req, extra=1), {k: v for k, v in req.items() if k != "data"}):
            self.assertTrue(V.validate_request(bad), bad.keys())


# ------------------------------------------------------------------------------------------------ engine requests validate
def cep_call_to_request(cep_action, data):
    """The engine's CEP call (action name + data) as the v4 request it would become."""
    return cep.to_request(cep.V4_NAME[cep_action], data, id="engine-test", expires_at=NOW)


class RecordingAE:
    """motion_build.build's bridge, mocked: answers like After Effects and remembers every (action, data) it was sent."""
    def __init__(self, build_answer=None):
        self.calls = []
        self.build_answer = build_answer
        self.project_path = None

    @staticmethod
    def answer(result):
        ok = result.get("ok", True) is not False
        return {"ok": ok, "response": {"ok": ok, "result": result}}

    def status(self, max_age_s=5.0):
        return {"alive": True, "busy": False, "host": "AEFT", "detail": "ok"}

    def submit(self, action, data=None, timeout=900):
        self.calls.append((action, copy.deepcopy(data if data is not None else {})))
        if action == "ping":
            return self.answer({"ae_version": "26.5x89", "dirty": False, "project_path": self.project_path, "num_items": 0})
        if action == "fonts":
            return self.answer({"fonts": {n: {"found": True, "substitute": False} for n in data["postscript_names"]},
                                "missing_or_substituted": []})
        if action == "build_motion":
            if self.build_answer is not None:
                return self.build_answer(data)
            Path(data["job"]["aep_path"]).write_bytes(b"AEP")
            return self.answer({"made": [s["id"] for s in data["job"]["plan"]["scenes"]], "failed": [], "warnings": [],
                                "saved": data["job"]["aep_path"], "main": "MAIN_" + data["job"]["plan"]["reel_id"],
                                "ae_version": "26.5x89"})
        if action == "readback":
            from test_motion import rb_from_plan
            return self.answer(rb_from_plan(data["job"]))
        return {"ok": False, "error": f"unexpected {action}"}


class EngineMotionRequestTests(unittest.TestCase):
    """motion_build.build, ae_probe.run_probe: every command they queue is a valid v4 request."""

    @classmethod
    def setUpClass(cls):
        from test_motion import good_script, motion_plan_fixture, test_font
        if test_font() is None:
            raise unittest.SkipTest("no test font for HarfBuzz fitting")
        from lib import common
        from lib.common import write_json
        from lib.motion_plan import compile_motion
        cls.common = common
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root, cls.ep, cls.reel = motion_plan_fixture(cls.tmp)
        write_json(cls.reel.p("01_analysis/motion-script.json"), good_script())
        r = compile_motion(cls.reel)
        assert r["ok"], r["errors"]
        cls.write_json = staticmethod(write_json)

    @classmethod
    def tearDownClass(cls):
        cls.common.set_context(None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def build(self, ae, replace_edited=False):
        from lib import ae_bridge, ae_probe, motion_build, plat
        from lib.motion_plan import fingerprint
        self.write_json(self.reel.p("01_analysis/plan-approval.json"),
                        {"approved": True, "by": "editor", "plan_fingerprint": fingerprint(self.reel)})
        for f in (motion_build.aep_path(self.reel), self.reel.p("04_after_effects/motion-build-result.json")):
            f.unlink(missing_ok=True)
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(ae_bridge, "submit", ae.submit))
            st.enter_context(mock.patch.object(ae_bridge, "status", ae.status))
            st.enter_context(mock.patch.object(ae_probe, "verdict_ok", lambda v: True))
            st.enter_context(mock.patch.object(plat, "newest_app", lambda key: {"name": "After Effects", "exe": "AfterFX.exe"}))
            st.enter_context(self.common.use_context(self.common.Context(self.root, home=self.tmp / "home")))
            return motion_build.build(self.reel, replace_edited=replace_edited)

    def test_the_build_sends_valid_ping_fonts_build_motion_and_readback_requests(self):
        ae = RecordingAE()
        r = self.build(ae)
        self.assertEqual(r["status"], "PROJECT_ASSEMBLED", r)
        sent = [a for a, _ in ae.calls]
        self.assertEqual(sent, ["ping", "fonts", "build_motion", "readback"])
        for a, data in ae.calls:
            req = cep_call_to_request(a, data)
            self.assertEqual(V.validate_request(req), [], a)
            json.dumps(req["data"], ensure_ascii=True).encode("ascii")                   # what the queue writes
        build_job = dict(ae.calls[2][1]["job"])
        self.assertEqual(V.validate(build_job["plan"], "ae_build_motion#/$defs/plan"), [])
        self.assertEqual(ae.calls[2][1]["job"], ae.calls[3][1]["job"])                   # the read-back checks the same job

    def test_a_refusal_from_after_effects_reaches_motion_build_through_the_v4_readback(self):
        """AE answers {ok:false, reason:"dirty"}; v4 carries it as readback.reason; handing that back gives REFUSED, not FAILED."""
        raw = parse_cep_result(fixture_json("ae_build_motion", "dirty.cep-result.json"))
        v4 = cep.from_cep("ae_build_motion", raw)
        self.assertEqual(V.validate_result(v4), [])
        legacy = lambda data: {"ok": v4["ok"], "response": {"ok": v4["ok"], "result": v4["readback"]}}   # noqa: E731
        ae = RecordingAE(build_answer=legacy)
        r = self.build(ae)
        self.assertEqual(r["status"], "REFUSED", r)
        self.assertTrue(any("unsaved changes" in x for x in r["reasons"]), r["reasons"])
        self.assertEqual([a for a, _ in ae.calls], ["ping", "fonts", "build_motion"])

    def test_a_half_built_project_reaches_motion_build_as_failed(self):
        raw = parse_cep_result(fixture_json("ae_build_motion", "failed_scenes.cep-result.json"))
        v4 = cep.from_cep("ae_build_motion", raw)
        self.assertEqual(V.validate_result(v4), [])

        def answer(data):
            Path(data["job"]["aep_path"]).write_bytes(b"AEP")                              # saved, but scenes failed
            return {"ok": v4["ok"], "response": {"ok": v4["ok"], "result": v4["readback"]}}
        r = self.build(RecordingAE(build_answer=answer))
        self.assertEqual(r["status"], "FAILED", r)
        self.assertNotEqual(r["status"], "REFUSED")

    def test_the_arabic_probe_sends_a_valid_probe_text_request(self):
        from lib import ae_bridge, ae_probe
        sent = []

        def submit(action, data=None, timeout=900):
            sent.append((action, copy.deepcopy(data)))
            return {"ok": False}                                     # the probe stops at the first answer
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {"WHYNOT_HOME": home}), \
                mock.patch.object(ae_bridge, "submit", submit):
            r = ae_probe.run_probe()
        self.assertIs(r["ok"], False)
        self.assertEqual([a for a, _ in sent], ["probe_text"])
        req = cep_call_to_request("probe_text", sent[0][1])
        self.assertEqual(V.validate_request(req), [])
        self.assertEqual(req["action"], "ae_probe_text")


class EnginePremiereRequestTests(unittest.TestCase):
    """ppro_build.build / export_frames and the CLI's ping / probe, with the Premiere bridge mocked: valid v4 requests."""

    @classmethod
    def setUpClass(cls):
        from test_podcast import decision, reel_fixture, shot
        from lib import common
        from lib.common import read_json, write_json
        from lib.plan import compile_plan
        cls.common = common
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root, cls.reel, _ = reel_fixture(cls.tmp, "storytelling", music=False)
        pre = read_json(cls.reel.p("00_inputs/preflight.json"))
        pre["shots"] = {"window": {"offset_ms": 1000, "duration_ms": 10000}, "method": "test",
                        "shots": [shot(0, 3000, 0.5), shot(3000, 8000), shot(8000, 10000, 0.5)]}
        write_json(cls.reel.p("00_inputs/preflight.json"), pre)
        write_json(cls.reel.p("01_analysis/edit-decisions.json"), {"global": {}, "decisions": [
            decision("EDIT_001", "00:00:04.000", "00:00:06.000", "كلمه8 كلمه9",
                     graphics=[{"id": "GFX_001", "template": "statement_highlight", "start": "00:00:04.500",
                                "end": "00:00:05.500", "text": "كلمه9"}])]})
        assert compile_plan(cls.reel)["ok"]
        from lib.previews import render_all
        render_all(cls.reel, composite_preview=False)
        cls.prj = cls.reel.p(f"07_premiere/project/{cls.reel.video_id}_{common.project_prefix()}_EDIT.prproj")

    @classmethod
    def tearDownClass(cls):
        cls.common.set_context(None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.calls = []
        self.prj.unlink(missing_ok=True)

    def bridge(self, action, data=None, timeout=60, **kw):
        self.calls.append((action, copy.deepcopy(data if data is not None else {})))
        return {"ok": True, "response": {"ok": True, "result": {}}}

    def run_engine(self, fn):
        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                mock.patch("lib.ppro_bridge.submit", self.bridge), \
                self.common.use_context(self.common.Context(self.root, home=self.tmp / "home")):
            return fn()

    def check_calls(self, wanted):
        self.assertEqual([a for a, _ in self.calls], wanted)
        for a, data in self.calls:
            req = cep_call_to_request(a, data)
            self.assertEqual(V.validate_request(req), [], a)
            json.dumps(req["data"], ensure_ascii=True).encode("ascii")

    def test_build_sends_a_valid_build_project_request(self):
        from lib import ppro_build
        self.run_engine(lambda: ppro_build.build(self.reel))
        self.check_calls(["build_project"])
        data = self.calls[0][1]
        self.assertTrue(data["graphics"] and data["markers"] and data["track_names"]["video"])
        self.assertNotIn("_missing", data)                                      # the engine's private keys never travel

    def test_a_rebuild_closes_the_old_project_first_with_a_valid_request(self):
        from lib import ppro_build
        self.prj.parent.mkdir(parents=True, exist_ok=True)
        self.prj.write_text("built", encoding="utf-8")
        self.run_engine(lambda: ppro_build.build(self.reel, overwrite=True))
        self.check_calls(["close_project_path", "build_project"])
        self.assertTrue(self.calls[1][1]["overwrite_existing"])

    def test_export_frames_sends_valid_requests_with_and_without_a_project_file(self):
        from lib import ppro_build
        self.run_engine(lambda: ppro_build.export_frames(self.reel, times=None, retries=0, wait_s=0))
        self.assertIsNone(self.calls[0][1]["project_path"])                      # no .prproj yet: null, which the schema allows
        self.prj.parent.mkdir(parents=True, exist_ok=True)
        self.prj.write_text("built", encoding="utf-8")
        self.run_engine(lambda: ppro_build.export_frames(self.reel, times=[1.5, 2.5], retries=0, wait_s=0))
        self.check_calls(["export_frames", "export_frames"])
        self.assertEqual(self.calls[1][1]["project_path"], str(self.prj))
        self.assertEqual(self.calls[1][1]["times"], [1.5, 2.5])

    def test_the_cli_ping_and_probe_send_empty_data(self):
        import io
        import cli
        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), mock.patch("lib.ppro_bridge.submit", self.bridge), \
                contextlib.redirect_stdout(io.StringIO()):
            cli.cmd_ppro_status(None)
            cli.cmd_ppro_probe(None)
        self.check_calls(["ping", "probe"])
        self.assertEqual([d for _, d in self.calls], [{}, {}])



# ------------------------------------------------------------------------------------------------ session (daemon link)
TS_SOURCE = SK.parent / "adobe" / "panel-ui" / "src" / "source.ts"
TOKEN = "ab" * 32
SESSION_REQUEST = {"protocol": 4, "id": "r-1", "action": "ping", "data": {}, "expires_at": "2026-10-12T10:00:00Z"}
SESSION_RESULT = {"ok": True, "action": "ping", "readback": {"version": "26.5.2", "project": None, "projects_open": 1}, "id": "r-1"}
SESSION_PROGRESS = {"event": "progress", "id": "r-1", "action": "build_project", "step": "tracks", "n": 1, "of": 4}
PANEL_STATE = {
    "connection": {"engine": "connected", "claude": "idle", "host": {"state": "uxp", "detail": "Premiere Pro 26.5.2"}},
    "client": "Dr Nour", "item": "C0239", "language": "ar", "editor_name": "Yunus",
    "context": {"project_path": "D:/p/C0239.prproj", "sequence_name": "C0239", "folder": "D:/c", "out_dir": None, "review_mp4": None},
    "pipeline": [{"id": "transcript", "state": "done"},
                 {"id": "build", "state": "running", "progress": {"n": 1, "of": 4, "step": "tracks"}, "elapsed_s": 3.5,
                  "request_id": "r-1"},
                 {"id": "qc", "state": "pending", "progress": None, "elapsed_s": None, "request_id": None}],
    "approval": {"summary": "plan", "preview_mp4": None, "flagged": [{"kind": "medical", "text": "x", "tc": "00:00:01:00"}],
                 "fingerprint": "abc123"},
    "qc": [{"t_s": 1.5, "tc": "00:00:01:15", "file": "D:/f.png", "label": "hook", "verdict": "pass", "w": 1080, "h": 1920,
            "thumb": None}],
    "log": [{"ts": "2026-10-12T10:00:00Z", "level": "info", "text": "hi"}],
}
MINIMAL_STATE = {"connection": {"engine": "offline", "claude": "unknown", "host": {"state": "offline"}}, "client": "", "item": "",
                 "language": "en", "editor_name": "",
                 "context": {"project_path": None, "sequence_name": None, "folder": None, "out_dir": None, "review_mp4": None},
                 "pipeline": [], "approval": None, "qc": [], "log": []}
SESSION_SAMPLES = {
    "hello": {"type": "hello", "token": TOKEN,
              "client": {"kind": "uxp", "version": "3.0.0", "host": "premiere", "hostVersion": "26.5.2", "protocol": 4,
                         "capabilities": ["ping", "status", "build_project"]}},
    "welcome": {"type": "welcome", "session_id": "s-1a2b", "protocol": 4, "daemon_version": "3.0.0"},
    "command": {"type": "command", "request": SESSION_REQUEST, "context": {"root": "D:/c", "profile": "nour"}},
    "result": {"type": "result", "result": SESSION_RESULT},
    "progress": {"type": "progress", "progress": SESSION_PROGRESS},
    "state": {"type": "state", "state": PANEL_STATE, "id": "p-1"},
    "approve": {"type": "approve", "id": "p-2", "item": "C0239", "editor_name": "Yunus", "fingerprint": "abc123"},
    "request_changes": {"type": "request_changes", "id": "p-3", "item": "C0239", "editor_name": "Yunus", "text": "shorter"},
    "rebuild": {"type": "rebuild", "id": "p-4", "item": "C0239", "project_path": "D:/p/C0239.prproj", "replace_edited": False},
    "snapshot": {"type": "snapshot", "id": "p-5"},
    "cancel": {"type": "cancel", "id": "r-1"},
    "reply": {"type": "reply", "id": "p-2", "intent": "approve", "ok": True},
    "error": {"type": "error", "code": "schema", "message": "bad hello", "id": "r-9"},
}


def session_errors(instance, name=None):
    return V.validate(instance, f"session#/$defs/{name}" if name else "session")


def ts_text():
    return TS_SOURCE.read_text(encoding="utf-8")


def ts_interface(name):
    """{key: required?} of a top-level `export interface name { ... }` in source.ts (one `key: type;` per 2-space line)."""
    m = re.search(r"export interface " + name + r"\s*\{\n(.*?)\n\}", ts_text(), re.S)
    assert m, name
    out = {}
    for line in m.group(1).splitlines():
        k = re.match(r"  ([A-Za-z_][A-Za-z0-9_]*)(\?)?:", line)
        if k:
            out[k.group(1)] = k.group(2) is None
    return out


def ts_union(name):
    m = re.search(r"export type " + name + r"\s*=\s*([^;]+);", ts_text())
    assert m, name
    return re.findall(r'"([^"]+)"', m.group(1))


class SessionContractTests(unittest.TestCase):
    """3.0 T6.2: every WebSocket message between `reel serve` and its clients (UXP panel, CEP panel, CLI)."""

    def test_schema_file_header_and_messages(self):
        doc = V.load(SESSION)
        self.assertEqual(V.check_schema(doc), [])
        self.assertEqual(doc["$id"], ID_BASE + "session.schema.json")
        self.assertTrue((set(SESSION_SAMPLES) | {"message", "panel_state"}) <= set(doc["$defs"]))
        self.assertTrue(session_errors(None))

    def test_every_message_def_is_a_closed_typed_object(self):
        defs = V.load(SESSION)["$defs"]
        for name in SESSION_SAMPLES:
            d = defs[name]
            self.assertEqual(d["type"], "object", name)
            self.assertIs(d["additionalProperties"], False, name)
            self.assertEqual(d["properties"]["type"]["const"], name, name)
            self.assertIn("type", d["required"], name)

    def test_message_is_the_oneof_of_every_message_def(self):
        doc = V.load(SESSION)
        refs = [b["$ref"] for b in doc["$defs"]["message"]["oneOf"]]
        self.assertEqual(refs, [f"#/$defs/{n}" for n in SESSION_SAMPLES])
        self.assertEqual(doc["$ref"], "#/$defs/message")

    def test_every_message_def_accepts_its_sample(self):
        for name, sample in SESSION_SAMPLES.items():
            self.assertEqual(session_errors(sample, name), [], name)
            self.assertEqual(session_errors(sample), [], f"message/{name}")

    def test_every_def_rejects_extra_properties_a_wrong_type_const_and_a_missing_required_key(self):
        defs = V.load(SESSION)["$defs"]
        for name, sample in SESSION_SAMPLES.items():
            self.assertTrue(session_errors(dict(sample, extra=1), name), name)
            self.assertTrue(session_errors(dict(sample, extra=1)), f"message/{name}")
            self.assertTrue(session_errors(dict(sample, type="nope"), name), name)
            self.assertTrue(session_errors(dict(sample, type="nope")), f"message/{name}")
            for key in defs[name]["required"]:
                self.assertTrue(session_errors({k: v for k, v in sample.items() if k != key}, name), f"{name}/{key}")

    def test_a_message_matches_exactly_one_def(self):
        for name, sample in SESSION_SAMPLES.items():
            matching = [n for n in SESSION_SAMPLES if not session_errors(sample, n)]
            self.assertEqual(matching, [name], name)
        for bad in ([], "hello", 1, None, {}, {"type": 4}, {"type": "hello"}, {"type": "run_script", "code": "x"}):
            self.assertTrue(session_errors(bad), repr(bad))

    # ---- hello / welcome
    def test_hello_wrong_protocol_or_missing_token_is_rejected(self):
        h = SESSION_SAMPLES["hello"]
        for proto in (3, 5, "4", 4.5, None, True):
            bad = copy.deepcopy(h)
            bad["client"]["protocol"] = proto
            self.assertTrue(session_errors(bad, "hello"), repr(proto))
            self.assertTrue(session_errors(bad), repr(proto))
        no_proto = copy.deepcopy(h)
        del no_proto["client"]["protocol"]
        self.assertTrue(session_errors(no_proto, "hello"))
        for bad in ({k: v for k, v in h.items() if k != "token"}, dict(h, token=""), dict(h, token=5), dict(h, token=None),
                    dict(h, token="x" * 257)):
            self.assertTrue(session_errors(bad, "hello"), repr(bad.get("token")))
            self.assertTrue(session_errors(bad), repr(bad.get("token")))

    def test_hello_client_fields(self):
        h = SESSION_SAMPLES["hello"]
        for kind in ("uxp", "cep", "cli", "panel"):
            ok = copy.deepcopy(h)
            ok["client"]["kind"] = kind
            self.assertEqual(session_errors(ok, "hello"), [], kind)
        for host in ("premiere", "aftereffects"):
            ok = copy.deepcopy(h)
            ok["client"]["host"] = host
            self.assertEqual(session_errors(ok, "hello"), [], host)
        minimal = {"type": "hello", "token": TOKEN, "client": {"kind": "cli", "version": "3.0.0", "protocol": 4, "capabilities": []}}
        self.assertEqual(session_errors(minimal, "hello"), [])
        cases = [("kind", "browser"), ("kind", None), ("version", ""), ("version", 3), ("host", "photoshop"),
                 ("hostVersion", 26), ("capabilities", "ping"), ("capabilities", ["ping", "rm_rf"]),
                 ("capabilities", ["ping"] * 16), ("capabilities", [3])]
        for key, value in cases:
            bad = copy.deepcopy(h)
            bad["client"][key] = value
            self.assertTrue(session_errors(bad, "hello"), f"{key}={value!r}")
        for key in ("kind", "version", "protocol", "capabilities"):
            bad = copy.deepcopy(h)
            del bad["client"][key]
            self.assertTrue(session_errors(bad, "hello"), key)
        bad = copy.deepcopy(h)
        bad["client"]["extra"] = 1
        self.assertTrue(session_errors(bad, "hello"))
        self.assertTrue(session_errors(dict(h, client="uxp"), "hello"))

    def test_hello_capabilities_are_the_contract_actions(self):
        caps = V.load(SESSION)["$defs"]["hello"]["properties"]["client"]["properties"]["capabilities"]
        self.assertEqual(caps["items"], {"$ref": "request.schema.json#/properties/action"})
        every = copy.deepcopy(SESSION_SAMPLES["hello"])
        every["client"]["capabilities"] = list(contract.ACTIONS)
        self.assertEqual(session_errors(every, "hello"), [])

    def test_welcome(self):
        w = SESSION_SAMPLES["welcome"]
        for bad in (dict(w, protocol=3), dict(w, protocol="4"), dict(w, session_id=""), dict(w, session_id="a b"),
                    dict(w, daemon_version=""), dict(w, daemon_version=3)):
            self.assertTrue(session_errors(bad, "welcome"), repr(bad))

    # ---- command / result / progress
    def test_command_wraps_a_v4_request_and_validates_it(self):
        c = SESSION_SAMPLES["command"]
        self.assertEqual(session_errors({"type": "command", "request": SESSION_REQUEST}, "command"), [])
        self.assertEqual(session_errors({"type": "command", "request": SESSION_REQUEST, "context": {}}, "command"), [])
        for bad_req in (dict(SESSION_REQUEST, protocol=3), dict(SESSION_REQUEST, action="run_script"),
                        dict(SESSION_REQUEST, id="has space"), {k: v for k, v in SESSION_REQUEST.items() if k != "expires_at"},
                        dict(SESSION_REQUEST, extra=1), "ping", None):
            self.assertTrue(session_errors(dict(c, request=bad_req), "command"), repr(bad_req))
            self.assertTrue(session_errors(dict(c, request=bad_req)), repr(bad_req))
        for bad_ctx in ({"root": 3}, {"profile": None}, {"extra": "x"}, "D:/c", {"root": "x" * 1025}):
            self.assertTrue(session_errors(dict(c, context=bad_ctx), "command"), repr(bad_ctx))
        self.assertTrue(session_errors({"type": "command"}, "command"))

    def test_command_data_is_checked_by_the_action_schema_not_here(self):
        """The message schema checks the envelope; the daemon then runs contract.validate_request for `data`."""
        c = {"type": "command", "request": dict(SESSION_REQUEST, action="open_project", data={"path": "D:/x.prproj"})}
        self.assertEqual(session_errors(c, "command"), [])
        self.assertEqual(V.validate_request(c["request"]), [])
        self.assertTrue(V.validate_request(dict(c["request"], data={})))

    def test_result_wraps_a_v4_result(self):
        r = SESSION_SAMPLES["result"]
        failed = {"type": "result", "result": {"ok": False, "action": "ping", "error": "x", "how": "y", "id": "r-1"}}
        self.assertEqual(session_errors(failed, "result"), [])
        for bad in ({"ok": True, "action": "ping"}, {"ok": True, "action": "ping", "readback": {}, "error": "x"},
                    {"ok": False, "action": "ping"}, {"ok": True, "action": "nope", "readback": {}}, [], None):
            self.assertTrue(session_errors(dict(r, result=bad), "result"), repr(bad))
            self.assertTrue(session_errors(dict(r, result=bad)), repr(bad))
        self.assertTrue(session_errors({"type": "result"}, "result"))

    def test_progress_wraps_a_v4_progress_event(self):
        p = SESSION_SAMPLES["progress"]
        for bad in (dict(SESSION_PROGRESS, event="done"), {k: v for k, v in SESSION_PROGRESS.items() if k != "step"},
                    dict(SESSION_PROGRESS, action="nope"), dict(SESSION_PROGRESS, n=-1), dict(SESSION_PROGRESS, extra=1), 1):
            self.assertTrue(session_errors(dict(p, progress=bad), "progress"), repr(bad))
            self.assertTrue(session_errors(dict(p, progress=bad)), repr(bad))
        self.assertTrue(session_errors({"type": "progress"}, "progress"))

    # ---- panel state + intents
    def test_state_accepts_a_full_and_a_minimal_panel_state(self):
        self.assertEqual(session_errors(MINIMAL_STATE, "panel_state"), [])
        self.assertEqual(session_errors({"type": "state", "state": MINIMAL_STATE}, "state"), [])
        self.assertEqual(session_errors({"type": "state", "state": PANEL_STATE}), [])

    def test_state_rejects_each_broken_part(self):
        def broken(path, value):
            s = copy.deepcopy(PANEL_STATE)
            target = s
            for k in path[:-1]:
                target = target[k]
            if value is KeyError:
                del target[path[-1]]
            else:
                target[path[-1]] = value
            return s

        cases = [(("language",), "fr"), (("language",), KeyError), (("approval",), KeyError), (("approval", "fingerprint"), KeyError),
                 (("approval", "flagged", 0, "kind"), "legal"), (("connection", "engine"), "up"), (("connection", "claude"), "maybe"),
                 (("connection", "host", "state"), "photoshop"), (("pipeline", 0, "id"), "deliver"), (("pipeline", 0, "state"), "ok"),
                 (("pipeline", 1, "progress", "of"), 0), (("pipeline", 1, "progress", "n"), -1), (("pipeline", 1, "progress"), 3),
                 (("qc", 0, "verdict"), "maybe"), (("qc", 0, "t_s"), "1"), (("qc", 0, "file"), KeyError), (("log", 0, "level"), "debug"),
                 (("context", "folder"), KeyError), (("context", "folder"), 3), (("client",), 4), (("pipeline",), {}), (("qc",), None)]
        for path, value in cases:
            self.assertTrue(session_errors(broken(path, value), "panel_state"), f"{path}={value!r}")
        extra = copy.deepcopy(PANEL_STATE)
        extra["extra"] = 1
        self.assertTrue(session_errors(extra, "panel_state"))
        extra = copy.deepcopy(PANEL_STATE)
        extra["connection"]["host"]["extra"] = 1
        self.assertTrue(session_errors(extra, "panel_state"))
        self.assertTrue(session_errors({"type": "state"}, "state"))
        self.assertTrue(session_errors({"type": "state", "state": {}}, "state"))

    def test_intents(self):
        for name in ("approve", "request_changes", "rebuild"):
            self.assertTrue(session_errors(dict(SESSION_SAMPLES[name], id="has space"), name), name)
            self.assertTrue(session_errors(dict(SESSION_SAMPLES[name], item=""), name), name)
        for bad in (dict(SESSION_SAMPLES["approve"], fingerprint=""), dict(SESSION_SAMPLES["approve"], fingerprint=3),
                    dict(SESSION_SAMPLES["approve"], editor_name=3)):
            self.assertTrue(session_errors(bad, "approve"))
        self.assertEqual(session_errors(dict(SESSION_SAMPLES["approve"], editor_name=""), "approve"), [])   # the panel asks, the engine decides
        self.assertTrue(session_errors(dict(SESSION_SAMPLES["request_changes"], text=""), "request_changes"))
        self.assertTrue(session_errors(dict(SESSION_SAMPLES["request_changes"], text="x" * 20001), "request_changes"))
        self.assertTrue(session_errors(dict(SESSION_SAMPLES["rebuild"], replace_edited="yes"), "rebuild"))
        self.assertTrue(session_errors(dict(SESSION_SAMPLES["rebuild"], project_path=None), "rebuild"))
        self.assertEqual(session_errors({"type": "snapshot"}, "snapshot"), [])
        self.assertTrue(session_errors({"type": "snapshot", "id": ""}, "snapshot"))
        self.assertTrue(session_errors({"type": "cancel"}, "cancel"))
        self.assertTrue(session_errors({"type": "cancel", "id": "x y"}, "cancel"))

    def test_reply_answers_an_intent_like_the_panel_result_type(self):
        ok = {"type": "reply", "id": "p-2", "intent": "approve", "ok": True}
        self.assertEqual(session_errors(dict(ok, readback={"approved": True}), "reply"), [])
        no = {"type": "reply", "id": "p-3", "intent": "rebuild", "ok": False, "error": "x", "how": "y"}
        self.assertEqual(session_errors(no, "reply"), [])
        for bad in (dict(ok, intent="run"), dict(ok, intent="snapshot"), dict(ok, ok="yes"), {k: v for k, v in ok.items() if k != "id"},
                    dict(ok, error="x"), {k: v for k, v in no.items() if k != "error"}, dict(ok, readback=[])):
            self.assertTrue(session_errors(bad, "reply"), repr(bad))
        self.assertEqual(V.load(SESSION)["$defs"]["reply"]["properties"]["intent"]["enum"], ["approve", "request_changes", "rebuild"])

    def test_error(self):
        codes = ["auth", "origin", "host", "too_large", "rate", "schema", "unknown_type", "no_route", "timeout", "internal"]
        self.assertEqual(V.load(SESSION)["$defs"]["error"]["properties"]["code"]["enum"], codes)
        for code in codes:
            self.assertEqual(session_errors({"type": "error", "code": code, "message": "m"}, "error"), [], code)
        for bad in ({"type": "error", "code": "oops", "message": "m"}, {"type": "error", "code": "auth"},
                    {"type": "error", "message": "m"}, {"type": "error", "code": "auth", "message": ""},
                    {"type": "error", "code": "auth", "message": "m", "id": ""},
                    {"type": "error", "code": "auth", "message": "m" * 2001}):
            self.assertTrue(session_errors(bad, "error"), repr(bad))

    # ---- source.ts parity
    def test_panel_state_keys_equal_source_ts(self):
        defs = V.load(SESSION)["$defs"]
        pairs = {"PanelState": defs["panel_state"], "ConnectionState": defs["connection"], "PipelineStep": defs["pipeline_step"],
                 "Approval": defs["approval"], "FlaggedItem": defs["flagged_item"], "QcFrame": defs["qc_frame"],
                 "LogLine": defs["log_line"], "ItemContext": defs["item_context"]}
        for ts_name, schema in pairs.items():
            ts = ts_interface(ts_name)
            self.assertEqual(set(schema["properties"]), set(ts), ts_name)
            self.assertEqual(set(schema["required"]), {k for k, req in ts.items() if req}, ts_name)
            self.assertIs(schema["additionalProperties"], False, ts_name)
        self.assertRegex(ts_text(), r"host: \{ state: HostState; /\*\*[^*]*\*/ detail\?: string \}")
        host = defs["connection"]["properties"]["host"]
        self.assertEqual(set(host["properties"]), {"state", "detail"})
        self.assertEqual(host["required"], ["state"])

    def test_panel_state_enums_equal_source_ts(self):
        defs = V.load(SESSION)["$defs"]
        self.assertEqual(defs["panel_state"]["properties"]["language"]["enum"], ts_union("Language"))
        self.assertEqual(defs["pipeline_step"]["properties"]["state"]["enum"], ts_union("StepStatus"))
        self.assertEqual(defs["connection"]["properties"]["claude"]["enum"], ts_union("ClaudeState"))
        self.assertEqual(defs["connection"]["properties"]["engine"]["enum"], ts_union("EngineState"))
        self.assertEqual(defs["connection"]["properties"]["host"]["properties"]["state"]["enum"], ts_union("HostState"))
        self.assertEqual(defs["qc_frame"]["properties"]["verdict"]["enum"], ts_union("QcVerdict"))
        self.assertEqual(defs["flagged_item"]["properties"]["kind"]["enum"], ["medical", "religious"])
        self.assertEqual(defs["log_line"]["properties"]["level"]["enum"], ["info", "warn", "error"])
        steps = re.search(r"STEP_IDS = \[([^\]]+)\]", ts_text()).group(1)
        self.assertEqual(defs["pipeline_step"]["properties"]["id"]["enum"], re.findall(r'"([^"]+)"', steps))

    def test_intent_inputs_equal_the_panel_data_source_methods(self):
        text = ts_text()
        defs = V.load(SESSION)["$defs"]
        for method, name in (("approve", "approve"), ("requestChanges", "request_changes"), ("rebuild", "rebuild")):
            m = re.search(method + r"\(input: \{ ([^}]*) \}\)", text)
            self.assertTrue(m, method)
            keys = set(re.findall(r"([a-z_]+): ", m.group(1)))
            self.assertEqual(set(defs[name]["properties"]) - {"type", "id"}, keys, name)
            self.assertEqual(set(defs[name]["required"]) - {"type", "id"}, keys, name)
        self.assertIn("cancel(id: string): Promise<void>;", text)
        self.assertIn("snapshot(): Promise<PanelState>;", text)


if __name__ == "__main__":
    unittest.main()
