# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 48 (L-T10, Addendum L §L4.4): property tests for the file readers and plan checkers.

Targets: lib.srt.read_srt / validate_cues, lib.common.parse_ts / read_json (the transcript JSON loader), lib.schemas
validate / validate_file for every plan kind (edit-decisions, motion-script, reels-plan, ...), lib.motion_script
.check_fields, lib.reels.validate_topics. Property: a ValueError family error (FileFormatError, a bad timestamp) or a
returned error list; never an IndexError, KeyError, TypeError, RecursionError or a hang; never a write outside the temp
folder. The typed set for the SRT reader is the ValueError family (FileFormatError, UnicodeDecodeError and "Bad
timestamp" are all ValueErrors that errors.describe turns into the JSON error document).
Run:  tools/test.sh -p test_fuzz_files.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402
import json
import os
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
_sys.path.insert(0, str(HERE / "security" / "fuzz"))
_sys.path.insert(0, str(HERE.parent / "engine" / "reel"))

import _hyp  # noqa: E402
from _hyp import fuzz, given, requires_hypothesis, st  # noqa: E402

from lib import common, errors, motion_script, reels, schemas, srt, verify  # noqa: E402

# What the fuzzer found that the owner has not fixed yet (patches in lane3/hooks/L-T10/). While an id is in OPEN the
# property tolerates that exception class and the strict test for the id is an expected failure (`xfail_open`). When the
# owner applies the patch that test shows up as an UNEXPECTED SUCCESS: delete the id from OPEN (and set the finding to
# fixed in regressions.json) and the same test becomes an ordinary one.
OPEN = {
    "srt-empty-end": IndexError,                      # lib/srt.py read_srt: "00:00:01,000 -->" with nothing after the arrow
    "json-deep-recursion": RecursionError,            # lib/common.py read_json: JSON nested ~3000 deep
    "topics-non-object": (TypeError, AttributeError),  # lib/reels.py validate_topics: a topic that is not an object
    "motion-script-shape": (TypeError, AttributeError),  # lib/motion_script.py check_fields: beats/scenes/items of the wrong JSON type
    "device-name-hang": _hyp.Hang if _hyp.AVAILABLE else (),  # lib/srt.py read_srt / lib/common.py read_json: Path("CON") blocks on the console
    "device-name-hang-verify": _hyp.Hang if _hyp.AVAILABLE else (),  # lib/verify.py prproj_signature: the same hang
}


def xfail_open(id_):
    """The strict test of an open finding: an expected failure while `id_` is in OPEN, an ordinary test after."""
    return _hyp.xfail_while_open(id_, OPEN)


def open_exc(*ids):
    out = ()
    for i in ids:
        e = OPEN.get(i, ())
        out += e if isinstance(e, tuple) else (e,)
    return out


TYPED_SRT = (ValueError,) + open_exc("srt-empty-end")
TYPED_JSON = (errors.FileFormatError,) + open_exc("json-deep-recursion")
TS = st.from_regex(r"\d{1,3}:\d{2}:\d{2}[,.]\d{1,4}", fullmatch=True) if _hyp.AVAILABLE else None


def tmp_file(data: bytes, name="x.srt") -> Path:
    d = _hyp.scratch_dir()
    p = d / name
    p.write_bytes(data)
    return p


def listing(p: Path):
    return sorted(x.name for x in p.parent.iterdir())


@requires_hypothesis
class SrtReader(unittest.TestCase):
    @fuzz()
    @given(st.binary(max_size=4000))
    def test_random_bytes(self, data):
        p = tmp_file(data)
        before = listing(p)
        out = _hyp.only_typed(srt.read_srt, TYPED_SRT, p)
        self.assertTrue(isinstance(out, (list, ValueError)))
        self.assertEqual(listing(p), before)

    @fuzz()
    @given(st.lists(st.tuples(st.one_of(st.just(""), st.integers(-5, 99999).map(str), _hyp.hostile_text()),
                              st.one_of(TS, _hyp.hostile_text()), st.sampled_from([" --> ", "-->", " ->", "-->  ", " --> \t", "  -->"]),
                              st.one_of(TS, _hyp.hostile_text()), _hyp.hostile_text()), max_size=8),
           st.sampled_from(["\n", "\r\n", "\r", "\n\n\n"]))
    def test_structured_cues_with_hostile_pieces(self, blocks, nl):
        text = nl.join("%s%s%s%s%s%s" % (i, nl, a, arrow, b, nl + t) for i, a, arrow, b, t in blocks)
        p = tmp_file(text.encode("utf-8", "surrogatepass"))
        out = _hyp.only_typed(srt.read_srt, TYPED_SRT, p)
        if isinstance(out, list):
            for c in out:
                self.assertTrue({"index", "start_ms", "end_ms", "text"} <= set(c))
            self.assertIsInstance(srt.validate_cues(out), list)  # out-of-order, negative, overlapping, huge: errors, not crashes

    @fuzz()
    @given(st.lists(st.fixed_dictionaries({"index": st.integers(), "start_ms": st.integers(-10 ** 12, 10 ** 12),
                                           "end_ms": st.integers(-10 ** 12, 10 ** 12), "text": _hyp.hostile_text()}), max_size=12),
           st.one_of(st.none(), st.integers(-10 ** 6, 10 ** 12)))
    def test_validate_cues_on_out_of_order_negative_overlapping_huge(self, cues, media):
        self.assertIsInstance(srt.validate_cues(cues, media), list)

    @fuzz()
    @given(_hyp.hostile_text())
    def test_parse_ts_gives_ms_or_value_error(self, s):
        out = _hyp.only_typed(common.parse_ts, (ValueError,), s)
        self.assertTrue(isinstance(out, (int, ValueError)))

    EMPTY_END = b"1\n00:00:01,000 -->\nhello\n"

    @xfail_open("srt-empty-end")
    def test_empty_second_timestamp_is_a_value_error_not_an_index_error(self):
        with self.assertRaises(ValueError):
            srt.read_srt(tmp_file(self.EMPTY_END))


@requires_hypothesis
class JsonLoader(unittest.TestCase):
    @fuzz()
    @given(st.binary(max_size=4000))
    def test_read_json_random_bytes_only_file_format_error(self, data):
        p = tmp_file(data, "transcript.json")
        out = _hyp.only_typed(common.read_json, TYPED_JSON, p)
        self.assertTrue(out is None or isinstance(out, (errors.FileFormatError, dict, list, str, int, float, bool)))

    @fuzz()
    @given(_hyp.json_values())
    def test_read_json_round_trip_of_any_json_value(self, v):
        p = tmp_file(json.dumps(v).encode("ascii"), "t.json")   # ascii-escaped: a lone surrogate stays valid JSON text
        out = _hyp.only_typed(common.read_json, TYPED_JSON, p)
        self.assertFalse(isinstance(out, errors.FileFormatError), "valid JSON refused: %r" % (v,))

    @fuzz(unit_examples=30)
    @given(st.integers(500, 20000), st.sampled_from(["[", '{"a":']))
    def test_deeply_nested_json_file_is_a_typed_error_not_a_recursion_crash(self, depth, opener):
        close = "]" if opener == "[" else "}"
        p = tmp_file((opener * depth + "0" + close * depth).encode(), "deep.json")
        out = _hyp.only_typed(common.read_json, TYPED_JSON, p)
        self.assertTrue(isinstance(out, (errors.FileFormatError, RecursionError, list, dict)))

    DEEP = ("[" * 4000 + "0" + "]" * 4000).encode()

    @xfail_open("json-deep-recursion")
    def test_deep_json_file_is_a_file_format_error(self):
        with self.assertRaises(errors.FileFormatError):
            common.read_json(tmp_file(self.DEEP, "deep.json"))


@requires_hypothesis
class PlanChecks(unittest.TestCase):
    KINDS = list(schemas.KINDS)

    @fuzz()
    @given(st.sampled_from(list(schemas.KINDS)), _hyp.json_values())
    def test_schema_validate_returns_error_dicts_for_any_json(self, kind, doc):
        out = schemas.validate(doc, kind)
        self.assertIsInstance(out, list)
        for e in out:
            self.assertTrue({"path", "msg"} <= set(e))

    @fuzz(unit_examples=30)
    @given(st.sampled_from(list(schemas.KINDS)), _hyp.deep_json(1500))
    def test_schema_validate_on_deep_documents(self, kind, doc):
        out = _hyp.only_typed(schemas.validate, (RecursionError,), doc, kind)
        self.assertNotIsInstance(out, RecursionError, "deep nesting escapes schemas.validate (%s)" % kind)

    @fuzz()
    @given(st.sampled_from(list(schemas.KINDS)), st.binary(max_size=2000))
    def test_validate_file_never_raises_on_random_file_content(self, kind, data):
        d = _hyp.scratch_dir()
        p = d / "plan.json"
        p.write_bytes(data)
        out = schemas.validate_file(p, kind)
        self.assertIsInstance(out, dict)
        self.assertIn("ok", out)

    @fuzz()
    @given(_hyp.json_values(), st.none() | st.dictionaries(st.text(max_size=8), _hyp.json_values(), max_size=4))
    def test_motion_script_check_fields_returns_a_list(self, script, cfg):
        out = _hyp.only_typed(motion_script.check_fields, (), script, cfg) if isinstance(script, dict) else None
        self.assertTrue(out is None or isinstance(out, list))

    @fuzz()
    @given(st.lists(_hyp.json_values(), max_size=6), st.integers(-10, 10 ** 9), st.integers(-10, 10 ** 6))
    def test_reels_validate_topics_returns_a_list(self, topics, total_ms, min_ms):
        out = _hyp.only_typed(reels.validate_topics, open_exc("topics-non-object"), topics, total_ms, min_ms)
        self.assertTrue(isinstance(out, (list, TypeError, AttributeError)))

    @xfail_open("topics-non-object")
    def test_a_topic_that_is_not_an_object_is_a_problem_not_a_crash(self):
        out = reels.validate_topics([None, 3, "x", [], {"start": 0, "end": 20000, "title": "t"}], 60000)
        self.assertTrue(any("topic 1" in p for p in out), out)


# plan kinds whose valid-only generator cannot reach VALID_SHARE_MIN, each with the reason (empty today)
UNREACHABLE = {}


PLAN_SCHEMA = {k: schemas.schema_for(k) for k in schemas.KINDS}
PLAN_KEYS = {k: _hyp.schema_keys(PLAN_SCHEMA[k]) for k in schemas.KINDS}
PLAN_LITS = {k: _hyp.schema_literals(PLAN_SCHEMA[k]) for k in schemas.KINDS}
PLAN_ENUMS = {k: _hyp.schema_prop_enums(PLAN_SCHEMA[k]) for k in schemas.KINDS}
PLAN_HOSTILE = {k: _hyp.from_schema(PLAN_SCHEMA[k]) for k in schemas.KINDS} if _hyp.AVAILABLE else {}
PLAN_VALID = {k: _hyp.from_schema(PLAN_SCHEMA[k], hostile=False) for k in schemas.KINDS} if _hyp.AVAILABLE else {}


@requires_hypothesis
class SchemaShapedPlans(unittest.TestCase):
    """Plan documents built from each kind's own schema (the bundled one `schemas.validate` uses, so cross-file refs resolve),
    and topics with real start/end/title shapes."""
    def _keyed(self, kind):
        return _hyp.doc_from_keys(PLAN_KEYS[kind], literals=PLAN_LITS[kind], prop_enums=PLAN_ENUMS[kind])

    @fuzz()
    @given(st.data())
    def test_schema_validate_with_schema_shaped_documents_of_every_kind(self, data):
        kind = data.draw(st.sampled_from(sorted(schemas.KINDS)))
        doc = data.draw(st.one_of(PLAN_HOSTILE[kind], PLAN_VALID[kind], PLAN_VALID[kind], self._keyed(kind)))
        out = schemas.validate(doc, kind)
        self.assertIsInstance(out, list)
        for e in out:
            self.assertTrue({"path", "msg"} <= set(e))

    def test_valid_only_generator_reaches_valid_documents_for_every_plan_kind(self):
        """Per kind (motion-script, needs-you, ... all of lib.schemas.KINDS): at least VALID_SHARE_MIN of the valid-only
        documents pass `schemas.validate`. A kind that cannot is named in UNREACHABLE with the reason."""
        for kind in sorted(schemas.KINDS):
            ok, drawn, first = _hyp.valid_share(PLAN_VALID[kind], lambda d, k=kind: schemas.validate(d, k))
            self.assertGreater(drawn, 0, kind)
            share = ok / drawn
            if kind in UNREACHABLE:
                self.assertLess(share, _hyp.VALID_SHARE_MIN, "%s is listed as unreachable but reaches %.0f%%: delete it" % (kind, share * 100))
                self.assertGreater(len(UNREACHABLE[kind]), 20)
            else:
                self.assertGreaterEqual(share, _hyp.VALID_SHARE_MIN, "%s: only %d of %d generated documents validate (first error: %s)" % (kind, ok, drawn, first))

    def test_a_pattern_string_matches_as_a_whole_with_no_trailing_newline(self):
        """`$` also matches before a final newline: a valid-only string for ^[a-z]{1,3}$ must be the pattern's own match,
        never 'ab\\n' (that string passes a search but is not what the schema describes)."""
        node = {"type": "string", "pattern": "^[a-z]{1,3}$"}
        seen = []
        ok, drawn, first = _hyp.valid_share(_hyp.from_schema(node, hostile=False),
                                            lambda s: seen.append(s) or ([] if re.fullmatch(node["pattern"], s) else ["no"]),
                                            examples=200)
        self.assertEqual((ok, drawn), (200, 200), first)
        self.assertFalse([s for s in seen if s.endswith("\n")])

    @fuzz()
    @given(st.sampled_from(sorted(schemas.KINDS)), st.data())
    def test_a_valid_looking_document_is_never_a_crash_in_validate_file(self, kind, data):
        doc = data.draw(PLAN_VALID[kind])
        d = _hyp.scratch_dir()
        p = d / "plan.json"
        p.write_text(json.dumps(doc, ensure_ascii=True), encoding="utf-8")
        out = schemas.validate_file(p, kind)
        self.assertIsInstance(out, dict)
        if not schemas.validate(doc, kind):
            self.assertTrue(out.get("ok"), out)

    @fuzz()
    @given(st.one_of(_hyp.from_schema(schemas.schema_for("motion-script")),
                     _hyp.from_schema(schemas.schema_for("motion-script"), hostile=False),
                     _hyp.doc_from_keys(_hyp.schema_keys(schemas.schema_for("motion-script")),
                                        literals=_hyp.schema_literals(schemas.schema_for("motion-script")),
                                        prop_enums=_hyp.schema_prop_enums(schemas.schema_for("motion-script")))),
           st.none() | st.dictionaries(st.text(max_size=6), _hyp.json_values(), max_size=3))
    def test_motion_script_check_fields_with_schema_shaped_scripts(self, script, cfg):
        out = _hyp.only_typed(motion_script.check_fields, open_exc("motion-script-shape"), script, cfg)
        self.assertTrue(isinstance(out, (list, TypeError, AttributeError)), out)

    BAD_SCRIPT = {"scenes": [{"id": "S01", "type": "title", "at": "@start"}], "beats": True}

    @xfail_open("motion-script-shape")
    def test_a_motion_script_with_wrongly_typed_fields_is_a_list_of_problems_not_a_crash(self):
        for bad in (self.BAD_SCRIPT, {"scenes": "x"}, {"scenes": [1, None, "s"]}, {"scenes": [{"id": "S01", "type": "list_steps", "items": 5}]},
                    {"scenes": [{"id": "S01", "type": "comparison", "first": 3, "second": []}]}, [1, 2], "x",
                    {"scenes": [{"id": "S01", "type": []}]}, {"scenes": [{"id": "S01", "type": {}}]},        # unhashable `type`: TypeError
                    {"scenes": [{"id": "S01", "type": [[]]}]}, {"scenes": [{"id": "S01", "type": {"a": 1}}]}):
            out = motion_script.check_fields(bad, {})
            self.assertIsInstance(out, list)
            self.assertTrue(out, bad)

    TIMES = st.one_of(st.integers(-5, 10 ** 7), st.floats(allow_nan=True, allow_infinity=True), _hyp.hostile_text(),
                      st.sampled_from(["00:00:00", "00:01:05.5", "1:2:3", "-1", "NaN", "00:00:10", "99:99:99", "", "0"]))

    @fuzz()
    @given(st.lists(st.fixed_dictionaries({}, optional={"id": st.one_of(st.integers(), _hyp.hostile_text()), "start": TIMES, "end": TIMES,
                                                         "title": st.one_of(st.none(), _hyp.hostile_text(), st.integers())}), max_size=8),
           st.integers(-10, 10 ** 9), st.integers(-10, 10 ** 6))
    def test_validate_topics_with_real_topic_shapes(self, topics, total_ms, min_ms):
        out = _hyp.only_typed(reels.validate_topics, open_exc("topics-non-object"), topics, total_ms, min_ms)
        self.assertTrue(isinstance(out, list), out)
        self.assertTrue(all(isinstance(e, str) for e in out))


_DEV = r"(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9\u00b9\u00b2\u00b3]|LPT[1-9\u00b9\u00b2\u00b3])"
# What Windows opens as a device (and so blocks on or reads forever): the last path component, with a drive prefix and any
# directory removed, is a reserved name followed only by spaces, an extension or a stream (`CON`, `CON `, `CON:`, `con.txt`,
# `NUL.`, `COM1`, `CONIN$`), or the path starts with the device namespace (backslash-backslash-dot-backslash, or the same
# with slashes), or with the extended prefix (backslash-backslash-question-backslash) followed by anything but a drive letter
# or UNC (that prefix + CON, PhysicalDrive0, GLOBALROOT...).
# The NT prefix (backslash question question backslash) counts like the extended one, and trailing separators or a lone dot
# segment after the name (`CON/`, `CON/.`) are still the device.
DEVICE_RE = re.compile(r"^(?:[\\/]{2}[.][\\/]|[\\/]{2}[?][\\/](?![A-Za-z]:|UNC[\\/])|[\\/][?]{2}[\\/](?![A-Za-z]:|UNC[\\/]))"
                       r"|^(?:.*[\\/]|[A-Za-z]:)?" + _DEV + r" *(?:[.:][^\\/]*)?(?:[\\/]+[.]?)*\Z", re.I | re.S)
DEVICE_IDS = ("device-name-hang", "device-name-hang-verify")
# Names the strict tests send. The extended form with a drive letter (backslash-backslash-question-backslash C:\x) is an ordinary
# path and must NOT be refused.
DEVICE_NAMES = (["CON", "CON:", "CON ", "con.txt", "NUL.", "NUL", "aux", "PRN", "CONIN$", "CONOUT$", "C:CON", "x/CON", "x\\NUL.txt",
                 "con .txt", "COM1:", "COM\u00b9"]
                + ["COM%d" % i for i in range(1, 10)] + ["LPT%d" % i for i in range(1, 10)] + ["LPT9.log"]
                + ["\\\\.\\CON", "\\\\.\\PhysicalDrive0", "//./PhysicalDrive0", "//./CON", "\\\\?\\CON", "\\\\?\\PhysicalDrive0",
                   "\\\\?\\GLOBALROOT\\Device\\x", "//?/CON",
                   "CON/", "CON/.", "CON\\", "x/../CON", "CON /", "CONIN$ ", "CONIN$/", "\\??\\CON",
                   "\\??\\GLOBALROOT\\Device\\ConDrv\\Input", "\\\\.\\GLOBALROOT\\Device\\ConDrv\\Input"])
NOT_DEVICES = ["x", "console.srt", "CONX", "xCON", "COM0", "COM10", "LPT0", "C:x", "\\\\?\\C:\\x", "x.CON", "CON/../x", "\\??\\C:\\x"]


REL_NAMES = ["x.srt", "./x.srt", "sub/x.srt", "sub/../x.srt", "sub\\..\\x.srt", "ملف.srt", "x.srt ", "x."]


@requires_hypothesis
class RelativePaths(unittest.TestCase):
    """The working directory is a temp folder and the file names are relative (`x.srt`, `./x.srt`, `sub/../x.srt`): the file
    parsers must give the same answer as for the absolute path, and create nothing else."""

    @classmethod
    def setUpClass(cls):
        cls.dir = _hyp.scratch_dir()
        (cls.dir / "sub").mkdir()
        cls.old = os.getcwd()
        os.chdir(cls.dir)                  # one chdir for the class: the examples only write and read relative names

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.old)

    @fuzz(unit_examples=20)
    @given(st.binary(max_size=1500), st.sampled_from(REL_NAMES))
    def test_relative_names_behave_like_absolute_ones(self, data, rel):
        self.assertEqual(Path(os.getcwd()).resolve(), self.dir.resolve())
        try:
            Path(rel).write_bytes(data)
        except OSError:
            return                          # a name this platform cannot create (trailing dot / space)
        before = sorted(x.name for x in self.dir.iterdir())
        absolute = Path(os.path.abspath(rel))
        for fn, allowed in ((srt.read_srt, TYPED_SRT), (common.read_json, TYPED_JSON),
                            (lambda q: schemas.validate_file(q, "edit-decisions"), (OSError, ValueError))):
            r1 = _hyp.only_typed(fn, allowed, Path(rel))
            r2 = _hyp.only_typed(fn, allowed, absolute)
            self.assertEqual(type(r1), type(r2), (rel, r1, r2))
            if not isinstance(r1, BaseException):
                self.assertEqual(r1 if not isinstance(r1, dict) else r1.get("ok"), r2 if not isinstance(r2, dict) else r2.get("ok"))
        self.assertEqual(sorted(x.name for x in self.dir.iterdir()), before, "a reader created something")

    def test_the_working_directory_is_restored(self):
        d = _hyp.scratch_dir()
        old = os.getcwd()
        os.chdir(d)
        try:
            (d / "x.srt").write_bytes(b"1\n00:00:01,000 --> 00:00:02,000\nhi\n")
            cues = srt.read_srt(Path("x.srt"))
            self.assertEqual([c["text"] for c in cues], ["hi"])
        finally:
            os.chdir(old)
        self.assertEqual(os.getcwd(), old)


OPEN_DEVICES = os.name == "nt" and any(i in OPEN for i in DEVICE_IDS)
ODD_PATHS = [n for n in _hyp.path_oddities() if not (OPEN_DEVICES and DEVICE_RE.match(n))]


@requires_hypothesis
class DeviceNames(unittest.TestCase):
    def test_a_network_path_is_recognised_and_no_fixed_list_sends_one(self):
        B = chr(92)
        for n in (B * 2 + "server" + B + "share", "//evil/x", B + "/host" + B + "x", B * 2 + "?" + B + "UNC" + B + "h" + B + "s",
                  "//./UNC/h/s", B * 2 + "濼" + B + "x"):
            self.assertTrue(_hyp.is_network_path(n), n)
        for n in ("x", "C:" + B + "x", B * 2 + "?" + B + "C:" + B + "x", B * 2 + "." + B + "CON", "//./PhysicalDrive0", "a" + B + B + "b", ""):
            self.assertFalse(_hyp.is_network_path(n), n)
        for n in _hyp.path_oddities() + DEVICE_NAMES + NOT_DEVICES + list(_hyp.HOSTILE_PIECES):
            self.assertFalse(_hyp.is_network_path(n), n)

    def test_the_reference_pattern_agrees_with_the_name_lists(self):
        for n in DEVICE_NAMES:
            self.assertTrue(DEVICE_RE.match(n), n)
        for n in NOT_DEVICES:
            self.assertFalse(DEVICE_RE.match(n), n)

    @xfail_open("device-name-hang")
    @unittest.skipUnless(os.name == "nt", "Windows device names")
    def test_a_windows_device_name_is_refused_not_read(self):
        """lib/common.py refuse_device (device-names.patch): every device form is a ValueError, never a read (which blocks on CON)."""
        for name in DEVICE_NAMES:
            for fn in (srt.read_srt, common.read_json):
                for form in (Path(name), name):
                    self.assertRaises(ValueError, _hyp.within, 5, fn, form)

    @unittest.skipUnless(os.name == "nt", "Windows device names")
    def test_ordinary_paths_are_not_refused_as_devices(self):
        for name in NOT_DEVICES:
            out = _hyp.only_typed(srt.read_srt, (OSError,), Path(name))      # missing file: OSError, not the device ValueError
            self.assertIsInstance(out, OSError, name)
            self.assertFalse("device" in str(out).lower(), (name, out))

    @xfail_open("device-name-hang-verify")
    @unittest.skipUnless(os.name == "nt", "Windows device names")
    def test_prproj_signature_of_a_device_name_is_none_not_a_hang(self):
        for name in DEVICE_NAMES:
            self.assertIsNone(_hyp.within(5, verify.prproj_signature, Path(name)), name)


@requires_hypothesis
class PathOddities(unittest.TestCase):
    """Windows and POSIX path oddities (traversal, device names, ADS, UNC, 8.3, NUL, trailing dot/space, Arabic) into every
    reader that takes a path: a ValueError / OSError family error or a returned value, never another exception, and
    nothing created anywhere."""
    # while a device-name finding is open, reserved device names are left out of the property (they hang): DeviceNames pins them
    ODD = ODD_PATHS

    @fuzz(space=len(ODD_PATHS))
    @given(st.sampled_from(ODD))
    def test_readers_never_crash_on_an_oddly_named_path(self, name):
        base = _hyp.scratch_dir()
        before = sorted(x.name for x in base.parent.iterdir())
        for p in (Path(name), base / name):
            for fn, allowed in ((srt.read_srt, (ValueError, OSError)), (common.read_json, (errors.FileFormatError, OSError, ValueError)),
                                (lambda q: schemas.validate_file(q, "edit-decisions"), (OSError, ValueError)),
                                (lambda q: verify.prproj_signature(Path(q)), (OSError, ValueError))):
                out = _hyp.only_typed(fn, allowed, p)
                self.assertTrue(out is None or isinstance(out, (list, dict, str, Exception)), (name, out))
        self.assertEqual(sorted(x.name for x in base.parent.iterdir()), before, "a reader created something")

    @fuzz()
    @given(_hyp.hostile_text())
    def test_readers_on_hostile_text_used_as_a_path(self, name):
        if OPEN_DEVICES and DEVICE_RE.match(name):
            return                       # open device-name finding: those names hang, DeviceNames pins them
        if _hyp.is_network_path(name):
            return                       # Windows would look the host up (LAN / DNS traffic, multi-second stalls): never sent
        for fn, allowed in ((srt.read_srt, (ValueError, OSError)), (common.read_json, (errors.FileFormatError, OSError, ValueError))):
            out = _hyp.only_typed(fn, allowed, Path(name))
            self.assertTrue(out is None or isinstance(out, (list, dict, str, int, float, bool, Exception)))


if __name__ == "__main__":
    unittest.main()
