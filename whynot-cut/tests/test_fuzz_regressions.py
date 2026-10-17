# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 48 (L-T10): the list of fuzz findings (tests/security/fuzz/regressions.json), the tests that pin them, and a
replay of every recorded input.

Every finding the fuzzers made outside our typed errors is either `open` (a patch is with its owner; the test file that found
it keeps an OPEN / KNOWN_OPEN id, and the strict test named in the entry is an expected failure while the id is listed) or
`fixed` (the id is gone from the test file and the strict test is an ordinary one). Three things are checked:
  * the file and the OPEN / KNOWN_OPEN dicts agree (a finding cannot be added to one side only);
  * the strict test named by each entry exists and is an expected failure exactly while the finding is open;
  * every entry with an `input` is REPLAYED here through its route (the target function and its typed-error policy). An open
    entry's replay is an expected failure while its id is open (an UNEXPECTED SUCCESS tells the owner's patch is in: delete the
    id), so nothing is ever skipped. Entries whose input is too big to store (`synthetic`) are replayed by their named test.
Run:  tools/test.sh -p test_fuzz_regressions.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402
import importlib
import json
import os
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
_sys.path.insert(0, str(HERE / "security" / "fuzz"))
_sys.path.insert(0, str(HERE.parent / "engine" / "reel"))
_sys.path.insert(0, str(HERE))

import _hyp  # noqa: E402
from lib import common, errors, motion_script, reels, srt, verify  # noqa: E402
from lib.brand_web import robots  # noqa: E402

import test_fuzz_brandweb as bw  # noqa: E402
import test_fuzz_files as fl  # noqa: E402
import test_fuzz_media as me  # noqa: E402
import test_fuzz_xml as xm  # noqa: E402

REG = json.loads((HERE / "security" / "fuzz" / "regressions.json").read_text(encoding="utf-8"))
OPEN_IDS = set(fl.OPEN) | set(me.KNOWN_OPEN) | set(bw.KNOWN_OPEN) | set(xm.KNOWN_OPEN)
CAP = 10      # seconds per replayed call
PREFIXES = (verify.SIGNATURE_PREFIX, verify.RAW_PREFIX, verify.BYTES_PREFIX)


def open_ids():
    return set(OPEN_IDS)


# ---------------------------------------------------------------- routes: one per target function, each with its policy
def _file(data: bytes, name: str) -> Path:
    p = _hyp.scratch_dir() / name
    p.write_bytes(data)
    return p


def _as_bytes(v):
    return v if isinstance(v, bytes) else str(v).encode("utf-8", "surrogatepass")


def route_read_srt_bytes(v):
    out = _hyp.only_typed(srt.read_srt, (ValueError,), _file(_as_bytes(v), "x.srt"), seconds=CAP)
    assert isinstance(out, (list, ValueError)), out


def route_read_json_bytes(v):
    out = _hyp.only_typed(common.read_json, (errors.FileFormatError,), _file(_as_bytes(v), "x.json"), seconds=CAP)
    assert isinstance(out, (errors.FileFormatError, dict, list, str, int, float, bool, type(None))), out


def route_validate_topics(v):
    out = _hyp.within(CAP, reels.validate_topics, v, 60000)
    assert isinstance(out, list) and all(isinstance(e, str) for e in out), out


def route_check_fields(v):
    out = _hyp.within(CAP, motion_script.check_fields, v, {})
    assert isinstance(out, list) and out, out


def route_content_signature(v):
    out = _hyp.within(CAP, verify._content_signature, v)
    assert isinstance(out, str) and out.startswith(PREFIXES), out


def route_robots_parse_allowed(v):
    rules = _hyp.within(CAP, robots.parse, v["text"])
    out = _hyp.within(CAP, rules.allowed, v["path"])
    assert isinstance(out, bool), out


def route_robots_match_time(v):
    """Matching a many-star pattern is linear: the backtracking matcher took 4 s on 500 characters and holds the GIL, so the
    time is measured, not interrupted."""
    rules = robots.parse(v["text"])
    t0 = time.monotonic()
    out = rules.allowed(v["path"])
    took = time.monotonic() - t0
    assert isinstance(out, bool), out
    assert took < 0.5, "matching took %.1f s" % took


def route_read_srt_path(v):
    """A device name is refused with a ValueError, never read (reading CON blocks): both readers, str and Path forms. Off
    Windows the name is an ordinary missing file: a ValueError or an OSError, quickly."""
    for fn in (srt.read_srt, common.read_json):
        for form in (v, Path(v)):
            try:
                _hyp.within(5, fn, form)
            except ValueError:
                continue
            except OSError:
                if os.name != "nt":
                    continue
            else:
                if os.name != "nt":
                    continue          # a missing file: read_json answers its default, nothing to refuse off Windows
            raise AssertionError("%s(%r) was not refused" % (fn.__name__, form))


def route_prproj_signature_path(v):
    assert _hyp.within(5, verify.prproj_signature, Path(v)) is None


ROUTES = {name[len("route_"):]: fn for name, fn in globals().items() if name.startswith("route_")}


def decode(v):
    return _hyp.decode_input(v)


def replay(entry):
    fn = ROUTES[entry["call"]]
    for raw in [entry["input"]] + list(entry.get("more_inputs") or []):
        fn(decode(raw))


# ---------------------------------------------------------------- the checks
def _strict_test(entry):
    mod, cls, name = entry["test"].split(".")
    return getattr(getattr(importlib.import_module(mod), cls), name, None)


class FindingsAndTestsAgree(unittest.TestCase):
    def test_every_finding_has_the_fields_a_reader_needs(self):
        ids = [f["id"] for f in REG["findings"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate finding id")
        for f in REG["findings"]:
            for k in ("id", "target", "exception", "owner", "patch", "status", "test"):
                self.assertTrue(f.get(k), (f.get("id"), k))
            self.assertIn(f["status"], ("open", "fixed"))
            if f.get("call"):
                self.assertIn(f["call"], ROUTES, f["id"])
                self.assertIsNotNone(f.get("input"), f["id"])
            else:
                self.assertTrue(f.get("synthetic"), "%s: no replayable input and no `synthetic` text" % f["id"])

    def test_the_open_findings_are_exactly_the_open_ids_of_the_test_files(self):
        listed = {f["id"] for f in REG["findings"] if f["status"] == "open"}
        self.assertEqual(listed, open_ids(),
                         "regressions.json and the OPEN / KNOWN_OPEN dicts of the test files disagree: when an owner applies a patch, "
                         "delete the id from the test file AND set `status` to fixed here")

    def test_every_open_test_id_names_a_known_finding(self):
        self.assertLessEqual(open_ids(), {f["id"] for f in REG["findings"]})

    def test_every_strict_test_exists_and_is_an_expected_failure_exactly_while_open(self):
        for f in REG["findings"]:
            t = _strict_test(f)
            self.assertIsNotNone(t, "%s: the test %s does not exist" % (f["id"], f["test"]))
            self.assertEqual(bool(getattr(t, "__unittest_expecting_failure__", False)), f["id"] in open_ids(),
                             "%s: %s must be an expected failure while the id is open, and an ordinary test after" % (f["id"], f["test"]))

    def test_a_windows_only_finding_is_an_expected_failure_on_windows_only(self):
        win = {"id": "w", "only_on": "nt"}
        anywhere = {"id": "a"}
        self.assertEqual(open_here(win, "nt", {"w"}), {"w"})
        self.assertEqual(open_here(win, "posix", {"w"}), set(), "off Windows the replay passes: it must not be an expected failure")
        self.assertEqual(open_here(anywhere, "posix", {"a"}), {"a"})
        self.assertEqual({f["id"] for f in REG["findings"] if f.get("only_on")}, {"device-name-hang", "device-name-hang-verify"})

    def test_every_open_finding_that_can_run_here_has_a_replayable_input(self):
        """`serve` is gone, and an entry is `synthetic` (replayed by its named test) only when its input is built by that test
        because it is too big to store; every other entry has a call and a stored input."""
        self.assertNotIn("serve", REG)
        for f in REG["findings"]:
            if f.get("synthetic"):
                self.assertIsNone(f.get("call"), f["id"])
                self.assertIsNone(f.get("input"), f["id"])
                self.assertRegex(f["synthetic"], r"(?i)\b(MB|KB|\d{4,}x\d{4,})\b|built by the test", f["id"])
            else:
                self.assertTrue(f.get("call") and f.get("input") is not None, f["id"])

    def test_the_input_forms_decode(self):
        self.assertEqual(decode({"base64": "aGk="}), b"hi")
        self.assertEqual(decode({"repeat": [["a", 3], ["b", 1]]}), "aaab")
        self.assertEqual(decode([{"base64": "aGk="}, 1, {"x": {"repeat": [["z", 2]]}}]), [b"hi", 1, {"x": "zz"}])
        self.assertEqual(decode("plain"), "plain")
        self.assertEqual(decode(None), None)

    def test_a_replay_that_cannot_pass_is_noticed(self):
        """The replay routes can fail: a stand-in target that raises an untyped error, or answers wrongly, is reported."""
        def raises_index_error(*a, **k):
            raise IndexError("x")
        with mock.patch.object(srt, "read_srt", raises_index_error):
            with self.assertRaises(IndexError):
                ROUTES["read_srt_bytes"](b"x")
        with mock.patch.object(reels, "validate_topics", lambda *a, **k: None):
            with self.assertRaises(AssertionError):
                ROUTES["validate_topics"]([None])
        with mock.patch.object(motion_script, "check_fields", lambda *a, **k: []):
            with self.assertRaises(AssertionError):
                ROUTES["check_fields"]({})
        if os.name == "nt":          # the device route: a reader that returns (or an untyped error) instead of refusing is noticed
            with mock.patch.object(srt, "read_srt", lambda p, *a, **k: []):
                with self.assertRaises(AssertionError):
                    ROUTES["read_srt_path"]("CON")
            with mock.patch.object(srt, "read_srt", mock.Mock(side_effect=ValueError("device"))), \
                    mock.patch.object(common, "read_json", mock.Mock(side_effect=ValueError("device"))):
                ROUTES["read_srt_path"]("CON")
        slow = mock.Mock(allowed=lambda p: (time.sleep(0.6), True)[1])
        with mock.patch.object(robots, "parse", lambda t: slow):
            with self.assertRaises(AssertionError):
                ROUTES["robots_match_time"]({"text": "x", "path": "/"})


def open_here(entry, os_name=os.name, ids=None):
    """The ids whose replay is an expected failure on `os_name`: a finding with `only_on` exists only there (the Windows device
    names are ordinary missing files on macOS and Linux, so their replay passes and must not be an expected failure)."""
    ids = open_ids() if ids is None else ids
    return ids if entry.get("only_on") in (None, os_name) else set()


def _make_replay_test(entry):
    def test(self):
        replay(entry)
    test.__name__ = "test_replay_%s" % entry["id"].replace("-", "_")
    test.__doc__ = "replays %s (%s)" % (entry["id"], entry["target"])
    return _hyp.xfail_while_open(entry["id"], open_here(entry))(test)


class ReplayRecordedInputs(unittest.TestCase):
    """One test per recorded input: ordinary once the finding is fixed, an expected failure while its id is open."""


for _entry in REG["findings"]:
    if _entry.get("call"):
        _t = _make_replay_test(_entry)
        setattr(ReplayRecordedInputs, _t.__name__, _t)


if __name__ == "__main__":
    unittest.main()
