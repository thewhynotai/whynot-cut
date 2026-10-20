"""BL-01 (Addendum M §M5.4 technique 4, M5-T6): the read-once reminder hook (hooks/read_once.py).

A light PostToolUse hook notes the SECOND full read of the same large, unchanged file by the same (session, agent) in
one session: one `additionalContext` line, never a block. State: <engine home>/run/read-once/<sha256(session)>.<sha256(agent)>.json (one file per agent),
written and read through lib/linksafe (never through a link). Cases R1-R13 (work/BL-01/cases.md) plus the executor
ruling: the state is under WHYNOT_HOME, a link in that path means no reminder, the `if` filter has the guard's form.
Tests are generic: a file is big or small, changed or not; they never list real client paths.
Run:  bash tools/test.sh -p test_read_once.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import statistics
import subprocess
import tempfile
import textwrap
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
READ_ONCE = SK / "hooks" / "read_once.py"
HOOKS_JSON = SK / "hooks" / "hooks.json"
RUN_PYTHON = SK / "hooks" / "run_python.sh"
_sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import linksafe  # noqa: E402
import test_evals as te  # noqa: E402  (grader file parsing: the eval cases' own helpers)


def load_module():
    spec = importlib.util.spec_from_file_location("read_once_under_test", READ_ONCE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def p95(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(0.95 * len(xs))) - 1)]


def case_class(word: str) -> str:
    """A name spelled like the guard's if-filters: `assets` -> `[Aa][Ss][Ss][Ee][Tt][Ss]` (any case, also on macOS)."""
    return "".join(f"[{c.upper()}{c.lower()}]" for c in word)


def make_link(link: Path, target: Path):
    """A junction on Windows (no privilege needed), a symlink elsewhere; the target is a folder."""
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def remove_link(link: Path):
    if os.name == "nt":
        os.rmdir(link)
    else:
        os.unlink(link)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.home = base / "engine-home"
        self.home.mkdir()
        self.client = base / "example clinic"
        self.out = self.client / "output"
        self.out.mkdir(parents=True)
        self.env = mock.patch.dict(os.environ, {"WHYNOT_HOME": str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.m = load_module()
        self.sid = "sess-" + uuid.uuid4().hex

    def big(self, name="transcript.json", n=None, fill=b"x"):
        p = self.out / name
        p.write_bytes(fill * (n if n is not None else self.m.LARGE_BYTES + 5000))
        return p

    def read(self, path, agent=None, session=None, **tool_input):
        d = {"hook_event_name": "PostToolUse", "session_id": session or self.sid, "tool_name": "Read",
             "tool_input": {"file_path": str(path), **tool_input}, "cwd": str(self.client)}
        if agent:
            d["agent_id"] = agent
        return self.m.handle(d)

    def run_main(self, payload, raw=None, home=None):
        env = dict(os.environ)
        env["WHYNOT_HOME"] = str(home or self.home)
        r = subprocess.run([_sys.executable, str(READ_ONCE)], input=raw if raw is not None else json.dumps(payload),
                           capture_output=True, text=True, encoding="utf-8", env=env)
        return r.returncode, r.stdout, r.stderr

    def state(self, sid=None, agent="lead"):
        p = self.m.state_path(sid or self.sid, agent)
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


class TestReminder(Base):
    def test_r1_second_full_read_gets_one_line(self):
        p = self.big()
        self.assertIsNone(self.read(p))
        out = self.read(p)
        self.assertIsNotNone(out)
        obj = json.loads(out)
        self.assertEqual(list(obj), ["hookSpecificOutput"])
        hso = obj["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "PostToolUse")
        text = hso["additionalContext"]
        self.assertNotIn("\n", text)
        self.assertIn(p.name, text)
        self.assertIn("already read", text)
        self.assertIn("reel brief", text)
        self.assertIn("grep", text)
        self.assertEqual(self.read(p) is not None, True)        # and again: still reminded

    def test_r1_end_to_end_process_exit_0(self):
        p = self.big()
        payload = {"hook_event_name": "PostToolUse", "session_id": self.sid, "tool_name": "Read",
                   "tool_input": {"file_path": str(p)}, "cwd": str(self.client)}
        code, out, err = self.run_main(payload)
        self.assertEqual((code, out), (0, ""))
        code, out, err = self.run_main(payload)
        self.assertEqual(code, 0)
        self.assertEqual(out.count("\n"), 1)
        self.assertIn("already read", json.loads(out)["hookSpecificOutput"]["additionalContext"])

    def test_r2_changed_file(self):
        p = self.big()
        self.assertIsNone(self.read(p))
        p.write_bytes(b"y" * (self.m.LARGE_BYTES + 777))         # size changed
        self.assertIsNone(self.read(p))
        self.assertIsNotNone(self.read(p))                       # changed-then-unchanged: reminded
        st = p.stat()
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))   # same size, mtime changed
        self.assertIsNone(self.read(p))
        self.assertIsNotNone(self.read(p))

    def test_r3_ranged_read(self):
        p = self.big()
        for kw in ({"offset": 10}, {"limit": 50}, {"offset": 0, "limit": 20}):
            self.assertIsNone(self.read(p, **kw), kw)
            self.assertIsNone(self.read(p, **kw), kw)
        self.assertIsNone(self.state())                          # never recorded
        self.assertIsNone(self.read(p))                          # 1st FULL read after the ranged ones: no reminder
        self.assertIsNotNone(self.read(p))

    def test_pages_and_any_other_key_make_it_a_ranged_read(self):
        p = self.big("report.pdf")
        for kw in ({"pages": "1-5"}, {"pages": "6-10"}, {"some_future_key": 1}):
            self.assertIsNone(self.read(p, **kw), kw)
            self.assertIsNone(self.read(p, **kw), kw)
        self.assertIsNone(self.state())                          # never recorded
        self.assertIsNone(self.read(p, pages=None))              # a null value is no range: this is a full read
        self.assertIsNotNone(self.read(p, pages=None))

    def test_r3_ranged_read_between_full_reads_does_not_clear(self):
        p = self.big()
        self.assertIsNone(self.read(p))
        self.assertIsNone(self.read(p, offset=5, limit=5))
        self.assertIsNotNone(self.read(p))

    def test_r4_small_file(self):
        p = self.big("small.json", n=self.m.LARGE_BYTES - 1)
        for _ in range(3):
            self.assertIsNone(self.read(p))
        self.assertIsNone(self.state())
        edge = self.big("edge.json", n=self.m.LARGE_BYTES)       # the threshold is inclusive
        self.assertIsNone(self.read(edge))
        self.assertIsNotNone(self.read(edge))

    def test_r5_keys(self):
        p = self.big()
        self.assertIsNone(self.read(p))                          # lead
        self.assertIsNone(self.read(p, agent="sub-a"))           # a subagent: its own record
        self.assertIsNone(self.read(p, agent="sub-b"))           # another subagent
        self.assertIsNone(self.read(p, session="other-" + self.sid))   # another session
        self.assertIsNotNone(self.read(p))                       # lead again
        self.assertIsNotNone(self.read(p, agent="sub-a"))
        self.assertIsNotNone(self.read(p, agent="sub-b"))
        self.assertIsNotNone(self.read(p, session="other-" + self.sid))

    def test_r6_reset_clears_only_the_lead_and_forget_clears_the_session(self):
        p = self.big()
        other = "other-" + self.sid
        for s_ in (self.sid, other):
            self.read(p, session=s_)
            self.read(p, agent="sub", session=s_)
        self.m.reset(self.sid)                                   # the lead's own compaction
        self.assertIsNone(self.state())
        self.assertIsNotNone(self.state(agent="sub"))            # a subagent's file is not touched
        self.assertIsNone(self.read(p))                          # after the reset: a first read again
        self.assertIsNotNone(self.read(p, agent="sub"))          # the subagent keeps its record
        self.assertIsNotNone(self.read(p, session=other))        # the other session is untouched
        self.assertIsNotNone(self.read(p, agent="sub", session=other))
        self.m.forget(self.sid)                                  # SessionEnd: every file of the session
        self.assertIsNone(self.state())
        self.assertIsNone(self.state(agent="sub"))
        self.assertIsNone(self.read(p, agent="sub"))
        self.assertIsNotNone(self.read(p, session=other))

    def test_r6_session_events_through_main(self):
        p = self.big()
        payload = {"hook_event_name": "PostToolUse", "session_id": self.sid, "tool_name": "Read",
                   "tool_input": {"file_path": str(p)}, "cwd": str(self.client)}

        def event(name, **kw):
            return self.run_main({"hook_event_name": name, "session_id": self.sid, "cwd": str(self.client), **kw})

        self.run_main(payload)
        self.run_main({**payload, "agent_id": "sub"})
        self.assertEqual(event("SessionStart", source="startup")[:2], (0, ""))
        self.assertIsNotNone(self.state())                       # startup / resume / clear keep it
        self.assertEqual(event("SessionStart", source="resume")[:2], (0, ""))
        self.assertIsNotNone(self.state())
        self.assertEqual(event("SessionStart", source="compact")[:2], (0, ""))
        self.assertIsNone(self.state())                          # the lead's compaction clears the lead's file only
        self.assertIsNotNone(self.state(agent="sub"))
        self.assertEqual(self.run_main(payload)[1], "")          # a re-read after compaction: no reminder
        self.assertNotEqual(self.run_main(payload)[1], "")
        self.assertEqual(event("SessionEnd", reason="other")[:2], (0, ""))
        self.assertIsNone(self.state())                          # SessionEnd removes every file of the session
        self.assertIsNone(self.state(agent="sub"))

    def test_r8_not_read(self):
        p = self.big()
        for tool in ("Grep", "Write", "Edit", "Bash", "read", ""):
            d = {"hook_event_name": "PostToolUse", "session_id": self.sid, "tool_name": tool,
                 "tool_input": {"file_path": str(p)}, "cwd": str(self.client)}
            self.assertIsNone(self.m.handle(d), tool)
            self.assertIsNone(self.m.handle(d), tool)
        self.assertIsNone(self.state())

    def test_pre_tool_use_is_ignored(self):
        p = self.big()
        d = {"hook_event_name": "PreToolUse", "session_id": self.sid, "tool_name": "Read",
             "tool_input": {"file_path": str(p)}, "cwd": str(self.client)}
        self.assertIsNone(self.m.handle(d))
        self.assertIsNone(self.m.handle(d))
        self.assertIsNone(self.state())


class TestWholeFileOnly(Base):
    def test_truncated_read_is_not_a_full_read(self):
        p = self.big()

        def read(lines, total):
            d = {"hook_event_name": "PostToolUse", "session_id": self.sid, "tool_name": "Read",
                 "tool_input": {"file_path": str(p)}, "cwd": str(self.client),
                 "tool_response": {"type": "text", "file": {"filePath": str(p), "numLines": lines, "totalLines": total}}}
            return self.m.handle(d)

        self.assertIsNone(read(2000, 2402))                      # the CLI cut the read: not "in full"
        self.assertIsNone(read(2000, 2402))
        self.assertIsNone(self.state())
        self.assertIsNone(read(2402, 2402))                      # whole file: recorded
        self.assertIsNotNone(read(2402, 2402))
        self.assertIsNotNone(read("x", 3))                       # not numbers: no information, treated as whole


class TestLock(Base):
    def lock_file(self, agent="lead"):
        return self.m._lock_path(self.m.state_path(self.sid, agent))

    def test_lock_is_released_after_every_write_even_when_it_fails(self):
        p = self.big()
        self.read(p)
        self.read(p)
        self.assertFalse(self.lock_file().exists())
        with mock.patch.object(self.m.linksafe, "replace_atomic", side_effect=OSError("disk")):
            self.assertIsNone(self.read(p))
        self.assertFalse(self.lock_file().exists())              # released by the finally
        folder = self.m.state_path(self.sid).parent
        self.assertEqual([x.name for x in folder.iterdir() if x.suffix == ".lock"], [])

    def test_a_held_fresh_lock_means_no_reminder_no_write_and_the_lock_stays(self):
        p = self.big()
        self.read(p)                                             # the file is recorded
        lock = self.lock_file()
        lock.write_bytes(b"")                                    # another process holds it right now
        before = self.state()
        with mock.patch.object(self.m, "LOCK_WAIT_S", 0.15):
            t0 = time.monotonic()
            self.assertIsNone(self.read(p))                      # would be a reminder, but no lock: silence
            self.assertLess(time.monotonic() - t0, 2.0)
        self.assertTrue(lock.exists())                           # never removed by a waiter that gave up
        self.assertEqual(self.state(), before)                   # no write either

    def test_a_stale_lock_is_taken_over(self):
        p = self.big()
        self.read(p)
        lock = self.lock_file()
        lock.write_bytes(b"")
        old = time.time() - 3 * self.m.LOCK_STALE_S
        os.utime(lock, (old, old))                               # a crashed holder's lock
        with mock.patch.object(self.m, "LOCK_WAIT_S", 2.0):
            self.assertIsNotNone(self.read(p))                   # taken over, then the normal path
        self.assertFalse(lock.exists())

    def test_a_young_lock_is_not_taken_over(self):
        p = self.big()
        self.read(p)
        lock = self.lock_file()
        lock.write_bytes(b"")
        os.utime(lock, (time.time() - self.m.LOCK_STALE_S / 2,) * 2)
        with mock.patch.object(self.m, "LOCK_WAIT_S", 0.2):
            self.assertIsNone(self.read(p))
        self.assertTrue(lock.exists())

    def test_one_agent_parallel_reads_in_one_turn_keep_every_record(self):
        for trial in range(5):
            sid = f"{self.sid}-same-{trial}"
            files = [self.big(f"p{trial}-{i}.json") for i in range(6)]

            def one(f):
                payload = {"hook_event_name": "PostToolUse", "session_id": sid, "tool_name": "Read",
                           "tool_input": {"file_path": str(f)}, "cwd": str(self.client)}
                return self.run_main(payload)

            with ThreadPoolExecutor(6) as ex:
                outs = list(ex.map(one, files))
            self.assertTrue(all(o[:2] == (0, "") for o in outs), outs)
            self.assertEqual(len(self.state(sid)["files"]), 6, f"trial {trial}: a parallel record was lost")
            with ThreadPoolExecutor(6) as ex:                    # and the second full reads are all reminded
                outs = list(ex.map(one, files))
            self.assertTrue(all("already read" in o[1] for o in outs), outs)


class TestRobust(Base):
    def test_r7_never_fails(self):
        p = self.big()
        good = {"hook_event_name": "PostToolUse", "session_id": self.sid, "tool_name": "Read",
                "tool_input": {"file_path": str(p)}, "cwd": str(self.client)}

        def without(*keys):
            return {k: v for k, v in good.items() if k not in keys}

        bad_dicts = [
            {}, without("tool_input"), without("session_id"), without("tool_name"),
            {**good, "tool_input": {}}, {**good, "tool_input": "x"}, {**good, "tool_input": None},
            {**good, "tool_input": {"file_path": ""}}, {**good, "tool_input": {"file_path": 5}},
            {**good, "tool_input": {"file_path": str(self.out / "gone.json")}},
            {**good, "tool_input": {"file_path": str(self.out)}},                  # a folder
            {**good, "tool_input": {"file_path": "a\x00b"}},
            {**good, "session_id": ""}, {**good, "session_id": None}, {**good, "session_id": 7},
            {**good, "cwd": None}, {**good, "cwd": 5}, {**good, "agent_id": 5}, {**good, "agent_id": ["x"]},
            {"hook_event_name": "SessionStart"}, {"hook_event_name": "SessionStart", "source": "compact"},
            {"hook_event_name": "SessionEnd"}, {"hook_event_name": 5},
        ]
        for d in bad_dicts:
            self.m.reset(self.sid)
            self.assertIsNone(self.m.handle(d), d)
            self.m.reset(self.sid)
            code, out, err = self.run_main(d)
            self.assertEqual((code, out), (0, ""), d)
        for raw in ("", "not json", "[]", "null", "5", '"x"', "{", "﻿", "\xff\xfe", '{"a":'):
            code, out, err = self.run_main(None, raw=raw)
            self.assertEqual((code, out), (0, ""), raw)
        for obj in ([], None, 5, "x", [good]):
            self.assertIsNone(self.m.handle(obj))
        code, out, _ = self.run_main(None, raw=json.dumps(good, ensure_ascii=False).encode("utf-8").decode("latin-1"))
        self.assertEqual(code, 0)

    def test_r7_state_folder_unusable(self):
        p = self.big()
        (self.home / "run").write_text("a file where the folder should be", encoding="utf-8")
        for _ in range(3):
            self.assertIsNone(self.read(p))
        payload = {"hook_event_name": "PostToolUse", "session_id": self.sid, "tool_name": "Read",
                   "tool_input": {"file_path": str(p)}, "cwd": str(self.client)}
        self.assertEqual(self.run_main(payload)[:2], (0, ""))
        self.assertEqual(self.run_main(payload)[:2], (0, ""))
        # WHYNOT_HOME itself is a file
        bad_home = Path(self.tmp.name) / "home-is-a-file"
        bad_home.write_text("x", encoding="utf-8")
        self.assertEqual(self.run_main(payload, home=bad_home)[:2], (0, ""))
        self.assertEqual(self.run_main(payload, home=bad_home)[:2], (0, ""))

    def test_missing_engine_home_is_silence_by_design(self):
        """No engine home folder = the plugin is not set up: the hook stays silent and creates nothing."""
        p = self.big()
        missing = Path(self.tmp.name) / "no-such-home"
        with mock.patch.dict(os.environ, {"WHYNOT_HOME": str(missing)}):
            for _ in range(3):
                self.assertIsNone(self.read(p))
        self.assertFalse(missing.exists())
        payload = {"hook_event_name": "PostToolUse", "session_id": self.sid, "tool_name": "Read",
                   "tool_input": {"file_path": str(p)}, "cwd": str(self.client)}
        for _ in range(2):
            self.assertEqual(self.run_main(payload, home=missing)[:2], (0, ""))
        self.assertFalse(missing.exists())

    def test_r7_linksafe_errors_are_swallowed(self):
        p = self.big()
        self.read(p)
        for fn, exc in (("replace_atomic", OSError("disk")), ("replace_atomic", linksafe.Guidance("x", "y")),
                        ("makedirs", OSError("disk")), ("confine", linksafe.Guidance("x", "y")),
                        ("confine", PermissionError("no"))):
            with mock.patch.object(self.m.linksafe, fn, side_effect=exc):
                self.assertIsNone(self.read(p), fn)
        self.m.reset(self.sid)
        with mock.patch.object(self.m.linksafe, "remove", side_effect=OSError("busy")):
            self.m.reset(self.sid)                               # must not raise
            self.m.forget(self.sid)

    def test_r7_corrupt_state_is_empty_state(self):
        p = self.big()
        self.read(p)
        sp = self.m.state_path(self.sid)
        for junk in (b"not json", b"[]", b'{"v": 2, "files": 5}', b'{"v": 1, "files": {}}',
                     b'{"v": 2, "files": {"k": "bad"}}', b'{"v": 2, "files": {"k": [1, 2]}}', b"\xff\xfe\x00", b""):
            sp.write_bytes(junk)
            self.assertIsNone(self.read(p), junk)                # treated as empty: records, no reminder
            self.assertIsNotNone(self.read(p), junk)             # and the state is healthy again
            self.assertEqual(self.state()["v"], 2)

    def test_state_record_shape(self):
        p = self.big()
        self.read(p)
        self.read(p, agent="sub-a")
        st = self.state()
        self.assertEqual(st["v"], 2)
        (entry,) = st["files"].values()
        size, mtime_ns, seen = entry
        self.assertEqual(size, p.stat().st_size)
        self.assertEqual(mtime_ns, p.stat().st_mtime_ns)
        self.assertIsInstance(seen, (int, float))
        self.assertEqual(len(self.state(agent="sub-a")["files"]), 1)    # its own file

    def test_r11_cap_keeps_newest_500(self):
        with mock.patch.object(self.m, "LARGE_BYTES", 10):
            files = [self.big(f"f{i:03d}.json", n=20) for i in range(510)]
            for f in files:
                self.assertIsNone(self.read(f))
            self.assertEqual(len(self.state()["files"]), 500)
            self.assertIsNotNone(self.read(files[-1]))           # the newest is kept
            self.assertIsNone(self.read(files[0]))               # the oldest was dropped (and is recorded again)
            self.assertEqual(len(self.state()["files"]), 500)
            # another agent has its own 500
            for f in files[:3]:
                self.read(f, agent="sub")
            self.assertEqual(len(self.state(agent="sub")["files"]), 3)


class TestPaths(Base):
    def test_r9_relative_path_resolves_against_cwd(self):
        p = self.big()
        self.assertIsNone(self.read("output/" + p.name))         # cwd = the client folder
        self.assertIsNotNone(self.read(p))                       # the absolute spelling is the same file
        self.assertIsNotNone(self.read(Path("output") / ".." / "output" / p.name))
        d = {"hook_event_name": "PostToolUse", "session_id": self.sid, "tool_name": "Read",
             "tool_input": {"file_path": "transcript.json"}, "cwd": str(self.out)}
        self.assertIsNotNone(self.m.handle(d))                   # another cwd, same real file

    @unittest.skipUnless(os.name == "nt", "Windows spellings: drive-letter case, slashes, file-name case")
    def test_r9_windows_spellings_and_junction(self):
        p = self.big("A.JSON")
        s = str(p)
        drive = p.drive
        self.assertTrue(drive.endswith(":"), drive)
        spellings = [s,
                     drive.lower() + s[len(drive):],
                     (drive.lower() + s[len(drive):]).replace("\\", "/"),
                     drive.upper() + s[len(drive):].replace("\\", "/"),
                     s.lower(), s.replace("A.JSON", "a.json")]
        self.assertIsNone(self.read(spellings[0]))
        for sp in spellings:
            self.assertIsNotNone(self.read(sp), sp)
        link = Path(self.tmp.name) / "junction-to-output"
        make_link(link, self.out)
        try:
            self.assertIsNotNone(self.read(link / "A.JSON"))     # a junction to the folder: the same real file
            self.assertEqual(len(self.state()["files"]), 1)
        finally:
            remove_link(link)
        self.assertTrue(p.is_file())                             # removing the link kept the real file

    @unittest.skipIf(os.name == "nt", "POSIX symlink (the Windows junction branch runs on Windows)")
    def test_r9_posix_symlink(self):
        p = self.big("a.json")
        link = Path(self.tmp.name) / "link.json"
        os.symlink(p, link)
        dirlink = Path(self.tmp.name) / "dirlink"
        os.symlink(self.out, dirlink, target_is_directory=True)
        self.assertIsNone(self.read(p))
        self.assertIsNotNone(self.read(link))
        self.assertIsNotNone(self.read(dirlink / "a.json"))
        self.assertEqual(len(self.state()["files"]), 1)


class TestStateLocation(Base):
    def test_r10_state_is_under_the_engine_home_run_read_once(self):
        p = self.big()
        before = sorted(x.name for x in self.client.rglob("*"))
        self.read(p)
        sp = self.m.state_path(self.sid)
        self.assertTrue(sp.is_file())
        want = self.home / "run" / "read-once"
        self.assertEqual(os.path.realpath(sp.parent), os.path.realpath(want))
        h = lambda x: hashlib.sha256(x.encode("utf-8")).hexdigest()
        self.assertEqual(sp.name, h(self.sid) + "." + h("lead") + ".json")
        self.read(p, agent="sub-x")
        self.assertEqual(self.m.state_path(self.sid, "sub-x").name, h(self.sid) + "." + h("sub-x") + ".json")
        self.assertNotIn(self.sid, sp.name)
        self.assertNotIn(self.sid, sp.read_text(encoding="utf-8"))   # the session id is not stored either
        self.assertEqual(before, sorted(x.name for x in self.client.rglob("*")))   # nothing in the client folder
        self.assertEqual([x.name for x in self.out.iterdir()], [p.name])
        mine = (sp.name, self.m.state_path(self.sid, "sub-x").name)
        self.assertEqual([x.name for x in sp.parent.iterdir() if x.name not in mine], [])   # no temp file left
        # a second record of the same agent: still the same two files
        self.read(self.big("other.json"))
        self.assertEqual(len(list(sp.parent.iterdir())), 2)

    def test_r10_state_never_in_the_cwd_even_when_it_is_the_home(self):
        p = self.big()
        d = {"hook_event_name": "PostToolUse", "session_id": self.sid, "tool_name": "Read",
             "tool_input": {"file_path": str(p)}, "cwd": str(self.out)}
        self.m.handle(d)
        self.assertEqual([x.name for x in self.out.iterdir()], [p.name])

    def test_link_in_state_folder_means_no_reminder_and_no_write(self):
        p = self.big()
        elsewhere = Path(self.tmp.name) / "elsewhere"
        elsewhere.mkdir()
        (self.home / "run").mkdir()
        link = self.home / "run" / "read-once"
        make_link(link, elsewhere)
        try:
            for _ in range(3):
                self.assertIsNone(self.read(p))
            self.assertEqual(list(elsewhere.iterdir()), [])      # nothing was written through the link
            payload = {"hook_event_name": "PostToolUse", "session_id": self.sid, "tool_name": "Read",
                       "tool_input": {"file_path": str(p)}, "cwd": str(self.client)}
            self.assertEqual(self.run_main(payload)[:2], (0, ""))
            self.assertEqual(self.run_main(payload)[:2], (0, ""))
            self.assertEqual(list(elsewhere.iterdir()), [])
            # a state file already sitting in the link target is not trusted either
            sp = elsewhere / self.m.state_path(self.sid).name
            sp.write_text(json.dumps({"v": 2, "files": {
                os.path.normcase(os.path.realpath(p)): [p.stat().st_size, p.stat().st_mtime_ns, 1]}}), encoding="utf-8")
            self.assertIsNone(self.read(p))
            # SessionEnd / compact never delete through the link
            self.m.reset(self.sid)
            self.m.forget(self.sid)
            self.assertTrue(sp.is_file())
        finally:
            remove_link(link)

    def test_link_in_run_folder_means_no_reminder_and_no_write(self):
        p = self.big()
        elsewhere = Path(self.tmp.name) / "elsewhere2"
        (elsewhere / "read-once").mkdir(parents=True)
        link = self.home / "run"
        make_link(link, elsewhere)
        try:
            for _ in range(3):
                self.assertIsNone(self.read(p))
            self.assertEqual(list((elsewhere / "read-once").iterdir()), [])
        finally:
            remove_link(link)

    def test_junction_removed_state_works_again(self):
        p = self.big()
        elsewhere = Path(self.tmp.name) / "elsewhere3"
        elsewhere.mkdir()
        (self.home / "run").mkdir()
        link = self.home / "run" / "read-once"
        make_link(link, elsewhere)
        self.assertIsNone(self.read(p))
        remove_link(link)
        self.assertIsNone(self.read(p))
        self.assertIsNotNone(self.read(p))


class TestParallel(Base):
    def test_eight_parallel_subagent_processes_each_get_every_reminder(self):
        files = [self.big(f"f{i}.json") for i in range(4)]
        agents = [f"agent-{i}" for i in range(8)]

        def run_agent(a):
            res = []
            for rnd in range(2):                         # an agent's own reads are sequential
                for f in files:
                    payload = {"hook_event_name": "PostToolUse", "session_id": self.sid, "tool_name": "Read",
                               "tool_input": {"file_path": str(f)}, "cwd": str(self.client), "agent_id": a}
                    res.append((rnd, self.run_main(payload)))
            return a, res

        with ThreadPoolExecutor(8) as ex:
            results = list(ex.map(run_agent, agents))
        for a, res in results:
            for rnd, (code, out, _err) in res:
                self.assertEqual(code, 0)
                if rnd == 0:
                    self.assertEqual(out, "", a)
                else:
                    self.assertIn("already read", out, f"{a}: the second read lost its record")
            self.assertEqual(len(self.state(agent=a)["files"]), 4, a)    # every record survived

    def test_lead_reset_racing_subagent_writes(self):
        files = [self.big(f"g{i}.json") for i in range(3)]
        for trial in range(6):
            sid = f"{self.sid}-t{trial}"
            for f in files:
                self.read(f, session=sid)                    # the lead's records
            errors = []

            def worker(a):
                try:
                    for i in range(25):
                        self.read(files[i % 3], agent=a, session=sid)
                except Exception as e:                       # handle() never raises
                    errors.append(e)

            threads = [threading.Thread(target=worker, args=(f"w{k}",)) for k in range(4)]
            for t in threads:
                t.start()
            time.sleep(0.005 * trial)
            self.m.reset(sid)                                # the lead compacts while the subagents write
            for t in threads:
                t.join()
            self.assertEqual(errors, [])
            self.assertIsNone(self.state(sid), f"trial {trial}: a lead record came back")
            for k in range(4):                               # no subagent file was touched by the reset
                self.assertEqual(len(self.state(sid, f"w{k}")["files"]), 3, f"trial {trial} w{k}")
            self.assertIsNone(self.read(files[0], session=sid))    # the lead's re-read after compaction: no reminder


class TestFirstWriteAndStress(Base):
    def payload(self, f, agent, sid=None):
        return {"hook_event_name": "PostToolUse", "session_id": sid or self.sid, "tool_name": "Read",
                "tool_input": {"file_path": str(f)}, "cwd": str(self.client), "agent_id": agent}

    def test_parallel_first_writes_into_a_fresh_home_lose_nothing_20_times(self):
        f = self.big()
        for trial in range(20):
            home = Path(self.tmp.name) / f"fresh-home-{trial}"      # no run/read-once yet: the folder race
            home.mkdir()
            agents = [f"a{i}" for i in range(8)]
            with ThreadPoolExecutor(8) as ex:
                outs = list(ex.map(lambda a: self.run_main(self.payload(f, a), home=home), agents))
            self.assertTrue(all(o[:2] == (0, "") for o in outs), (trial, outs))
            with ThreadPoolExecutor(8) as ex:
                outs = list(ex.map(lambda a: self.run_main(self.payload(f, a), home=home), agents))
            for a, o in zip(agents, outs):
                self.assertIn("already read", o[1], f"trial {trial} {a}: the first write was lost")

    def test_stress_8_agents_50_reads_each_zero_lost(self):
        files = [self.big(f"s{i:02d}.json") for i in range(25)]
        agents = [f"agent-{i}" for i in range(8)]

        def run_agent(a):
            res = []
            for rnd in range(2):                                    # 25 first reads, then 25 second reads = 50
                for f in files:
                    res.append((rnd, self.run_main(self.payload(f, a))))
            return a, res

        with ThreadPoolExecutor(8) as ex:
            results = list(ex.map(run_agent, agents))
        for a, res in results:
            self.assertEqual(len(res), 50)
            for rnd, (code, out, _e) in res:
                self.assertEqual(code, 0)
                if rnd == 0:
                    self.assertEqual(out, "")
                else:
                    self.assertIn("already read", out, f"{a}: a second read lost its record")
            self.assertEqual(len(self.state(agent=a)["files"]), 25, a)

    def test_stress_one_agent_8_parallel_workers_50_reads_each_zero_lost(self):
        """The same-agent case: 8 parallel workers (parallel Reads of one agent) x 50 reads, all into ONE state file."""
        files = {w: [self.big(f"w{w}-{i:02d}.json") for i in range(25)] for w in range(8)}

        def worker(w):
            res = []
            for rnd in range(2):
                for f in files[w]:
                    res.append((rnd, self.run_main(self.payload(f, "the-lead-agent"))))
            return w, res

        with ThreadPoolExecutor(8) as ex:
            results = list(ex.map(worker, range(8)))
        for w, res in results:
            for rnd, (code, out, _e) in res:
                self.assertEqual(code, 0)
                if rnd == 0:
                    self.assertEqual(out, "")
                else:
                    self.assertIn("already read", out, f"worker {w}: a second read lost its record")
        self.assertEqual(len(self.state(agent="the-lead-agent")["files"]), 200)
        self.assertEqual([x.name for x in self.m.state_path(self.sid, "the-lead-agent").parent.iterdir()
                          if x.suffix == ".lock"], [])


class TestSweep(Base):
    def old(self, path: Path, days=3):
        t = time.time() - days * 86400
        os.utime(path, (t, t))

    def test_sweep_never_follows_or_removes_a_link_even_when_it_looks_old(self):
        """The clock is mocked, so the link named like a state file IS old: only the link handling can save it."""
        d = self.home / "run" / "read-once"
        d.mkdir(parents=True)
        a = "a" * 64
        outside = Path(self.tmp.name) / "outside2"
        outside.mkdir()
        (outside / "x.json").write_text("{}", encoding="utf-8")
        link = d / f"{'e' * 64}.{a}.json"
        make_link(link, outside)
        plain = d / f"{'f' * 64}.{a}.json"
        plain.write_text("{}", encoding="utf-8")
        try:
            with mock.patch.object(self.m.time, "time", return_value=time.time() + 10 * 86400):
                self.m._sweep(d, self.home)
            self.assertFalse(plain.exists())                     # a real old state file goes (the clock moved)
            self.assertTrue(os.path.lexists(link))               # the link name itself is not removed
            self.assertTrue((outside / "x.json").exists())       # and nothing behind it
        finally:
            remove_link(link)

    def test_state_files_older_than_two_days_are_swept_on_write_without_following_links(self):
        d = self.home / "run" / "read-once"
        d.mkdir(parents=True)
        a, b, c = "a" * 64, "b" * 64, "c" * 64
        old_agent, old_session = d / f"{a}.{a}.json", d / f"{b}.json"
        young, other_name = d / f"{c}.{a}.json", d / "notes.json"
        for f in (old_agent, old_session, young, other_name):
            f.write_text("{}", encoding="utf-8")
        for f in (old_agent, old_session, other_name):
            self.old(f)
        self.old(young, days=1)
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        (outside / "x.json").write_text("{}", encoding="utf-8")
        self.old(outside / "x.json")
        link = d / f"{'d' * 64}.{a}.json"                    # a link named like a state file
        make_link(link, outside)
        try:
            self.read(self.big())                            # a write triggers the sweep
            self.assertFalse(old_agent.exists())
            self.assertFalse(old_session.exists())           # the older one-file-per-session name goes too
            self.assertTrue(young.exists())
            self.assertTrue(other_name.exists())             # not a state file name: never touched
            self.assertTrue((outside / "x.json").exists())   # the link was not followed
            self.assertTrue(os.path.lexists(link))
            self.assertIsNotNone(self.state())               # and the new record is there
        finally:
            remove_link(link)


class TestEvalCases(unittest.TestCase):
    CASES = ("read-once", "read-once-natural")

    def test_scaffold_here_line_is_the_siblings_form(self):
        sib = (SK / "evals" / "handoff-for-editor" / "scaffold.sh").read_text(encoding="utf-8").splitlines()[2]
        self.assertTrue(sib.startswith("here="))
        for case in self.CASES:
            lines = (SK / "evals" / case / "scaffold.sh").read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[2], sib, f"{case}: scaffold.sh line 3 must be the sibling scaffolds' line")

    def test_scaffold_really_builds_the_big_file_under_output(self):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("no bash")
        for case in self.CASES:
            with tempfile.TemporaryDirectory() as tmp:
                stub = Path(tmp) / "bin"
                stub.mkdir()
                ff = stub / "ffmpeg"                          # the fixture only needs ffmpeg to create its output file
                ff.write_text("#!/bin/sh\nfor a; do last=$a; done\nprintf x > \"$last\"\n", encoding="utf-8", newline="\n")
                ff.chmod(0o755)
                work = Path(tmp) / "work"
                work.mkdir()
                env = dict(os.environ, PATH=str(stub) + os.pathsep + os.environ.get("PATH", ""))
                r = subprocess.run([bash, str(SK / "evals" / case / "scaffold.sh")], cwd=work, env=env,
                                   capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(r.returncode, 0, f"{case}: {r.stderr}")
                tr = work / "example-clinic" / "output" / "projects" / "C0238" / "02_transcription" / "transcript.json"
                self.assertTrue(tr.is_file(), f"{case}: the scaffold did not create {tr}")
                self.assertGreaterEqual(tr.stat().st_size, 20_000)       # over the hook's threshold
                data = json.loads(tr.read_text(encoding="utf-8"))
                self.assertEqual(len(data["segments"]), 60)
                brand = work / "example-clinic" / "output" / "client_database" / "reel-profile" / "brand.json"
                self.assertIn("Cairo", brand.read_text(encoding="utf-8"))    # the natural case asks for this file

    def grader(self, case, name):
        fm, body = te.split_md((SK / "evals" / case / "graders" / f"{name}.md").read_text(encoding="utf-8"))
        return fm, body

    def run_hook_twice(self):
        """A trace fixture built from the REAL hook: what a second full read adds, and what a missing hook adds."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            f = Path(tmp) / "client" / "output" / "projects" / "C0238" / "02_transcription" / "transcript.json"
            f.parent.mkdir(parents=True)
            f.write_bytes(b"x" * 30000)
            with mock.patch.dict(os.environ, {"WHYNOT_HOME": str(home)}):
                m = load_module()
                d = {"hook_event_name": "PostToolUse", "session_id": "s-" + uuid.uuid4().hex, "tool_name": "Read",
                     "tool_input": {"file_path": str(f)}, "cwd": str(f.parent)}
                self.assertIsNone(m.handle(d))
                return json.loads(m.handle(d))["hookSpecificOutput"]["additionalContext"]

    def test_plumbing_case_fails_without_the_reminder_and_passes_with_it(self):
        reminder = self.run_hook_twice()
        fm, body = self.grader("read-once", "reminder-appears")
        self.assertEqual((fm["type"], fm["target"], fm["match"]), ("regex", "trace", "contains"))
        rx = re.compile(body.strip())                            # JS RegExp, but this pattern is plain
        with_hook = f'Read -> (1st result)\nRead -> (2nd result)\n<hook additionalContext>{reminder}</hook>\nanswer'
        without_hook = "Read -> (1st result)\nRead -> (2nd result)\nanswer"
        broken_hook = with_hook.replace("already read", "read already")
        self.assertIsNotNone(rx.search(with_hook))
        self.assertIsNone(rx.search(without_hook), "the case would pass with the hook missing")
        self.assertIsNone(rx.search(broken_hook), "the case would pass with a changed reminder text")

    def test_plumbing_case_needs_two_full_reads_of_the_transcript(self):
        fm, body = self.grader("read-once", "two-full-reads")
        self.assertEqual((fm["tool"], fm["min"]), ("Read", 2))
        rx = re.compile(fm["input_match"])
        tr = "D:/x/output/projects/C0238/02_transcription/transcript.json"
        full = json.dumps({"file_path": tr})
        ranged = json.dumps({"file_path": tr, "offset": 10, "limit": 20})
        paged = json.dumps({"file_path": tr, "pages": "1-3"})
        other = json.dumps({"file_path": "D:/x/output/brand.json"})
        count = lambda calls: sum(1 for c in calls if rx.search(c))
        self.assertGreaterEqual(count([full, other, full]), fm["min"])
        self.assertLess(count([full, ranged, paged, other]), fm["min"])        # one full read is not enough

    def test_natural_case_has_no_reminder_requirement_and_the_plumbing_case_has(self):
        for name in ("reminder-appears", "two-full-reads"):
            self.assertTrue((SK / "evals" / "read-once" / "graders" / f"{name}.md").is_file())
            self.assertFalse((SK / "evals" / "read-once-natural" / "graders" / f"{name}.md").exists())
        fm, body = self.grader("read-once-natural", "full-read-happened")
        self.assertEqual(fm["min"], 1)
        self.assertNotIn("max", fm)                              # passes on ONE full read; never fails for a second


class TestLatency(Base):
    def test_r12_in_process_p95_under_50ms(self):
        p = self.big()
        self.read(p)
        times = []
        for i in range(200):
            t0 = time.perf_counter()
            out = self.read(p)
            times.append((time.perf_counter() - t0) * 1000)
            self.assertIsNotNone(out)
        got = p95(times)
        print(f"read_once handle() in-process: p50 {statistics.median(times):.2f} ms, p95 {got:.2f} ms "
              f"(200 runs, reminder path with a state write)", file=_sys.stderr)
        self.assertLess(got, 50, f"in-process p95 {got:.1f} ms")

    def test_r12_end_to_end_measured_not_asserted(self):
        bash = shutil.which("bash")
        if not bash or not RUN_PYTHON.is_file():
            self.skipTest("bash or run_python.sh not available")
        p = self.big()
        env = dict(os.environ)
        env.update({"WHYNOT_HOME": str(self.home), "CLAUDE_PLUGIN_DATA": str(Path(self.tmp.name) / "plugin-data")})
        payload = json.dumps({"hook_event_name": "PostToolUse", "session_id": self.sid, "tool_name": "Read",
                              "tool_input": {"file_path": str(p)}, "cwd": str(self.client)})
        cmd = [bash, str(RUN_PYTHON), str(READ_ONCE)]
        r = subprocess.run(cmd, input=payload, capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        times = []
        for _ in range(200):
            t0 = time.perf_counter()
            r = subprocess.run(cmd, input=payload, capture_output=True, text=True, encoding="utf-8", env=env)
            times.append((time.perf_counter() - t0) * 1000)
            self.assertEqual(r.returncode, 0, r.stderr)
        print(f"read_once end-to-end (bash run_python.sh + Python): p50 {statistics.median(times):.0f} ms, "
              f"p95 {p95(times):.0f} ms, max {max(times):.0f} ms (200 runs; measured, not asserted)", file=_sys.stderr)


class TestSourceAndRegistration(unittest.TestCase):
    def test_r13_stdlib_only(self):
        std = getattr(_sys, "stdlib_module_names", None)
        if std is None:
            self.skipTest("sys.stdlib_module_names needs Python 3.10+")

        def imports(path, nested=True):
            out = []
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in (ast.walk(tree) if nested else tree.body):
                if isinstance(node, ast.Import):
                    out += [(a.name.split(".")[0], None, 0) for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    out.append(((node.module or "").split(".")[0], [a.name for a in node.names], node.level))
            return out

        found = imports(READ_ONCE)
        self.assertTrue(found)
        lib_names = set()
        for top, names, level in found:
            if top == "__future__" or top in std:
                continue
            self.assertEqual((top, level), ("lib", 0), f"read_once.py imports a non-stdlib module: {top}")
            lib_names |= set(names or [])
        # the only engine modules it may reach (the executor's ruling); they must be stdlib only themselves
        self.assertLessEqual(lib_names, {"plat", "linksafe"})
        libdir = SK / "engine" / "reel" / "lib"
        for mod in ("plat", "linksafe", "errors"):
            # module level only: plat.py imports heavy engine packages lazily inside functions the hook never calls
            for top, names, level in imports(libdir / f"{mod}.py", nested=False):
                self.assertTrue(level > 0 or top == "__future__" or top in std, f"{mod}.py imports {top}")
        self.assertIn("sys.dont_write_bytecode = True", READ_ONCE.read_text(encoding="utf-8"))
        self.assertIn("from __future__ import annotations", READ_ONCE.read_text(encoding="utf-8"))

    @staticmethod
    def expected_registered():
        """Once hooks/README.md documents read_once.py (hooks-readme.patch), a missing registration is a failure."""
        readme = SK / "hooks" / "README.md"
        return readme.is_file() and "read_once.py" in readme.read_text(encoding="utf-8")

    def registered(self):
        if not HOOKS_JSON.is_file():
            return None
        cfg = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
        rows = []                                    # (event, matcher, hook dict)
        for event, blocks in cfg.get("hooks", {}).items():
            for block in blocks:
                for h in block.get("hooks", []):
                    if "read_once.py" in h.get("command", ""):
                        rows.append((event, block.get("matcher"), h))
        return cfg, rows

    IF_FORM = re.compile(r"^(?P<tool>[A-Z][A-Za-z]*)\(//\*\*/(?P<glob>(?:[^/()\[\]]|\[[^\]/]+\])+)/\*\*\)$")
    # the guard's own filters may also name files under the folder (BL-15: <claude config>/projects/**/*.jsonl)
    GUARD_FORM = re.compile(r"^(?P<tool>[A-Z][A-Za-z]*)\(//\*\*/(?:(?:[^/()\[\]]|\[[^\]/]+\])+)/\*\*"
                            r"(?:/(?:[^/()\[\]]|\[[^\]/]+\])+)?\)$")

    def test_if_filter_has_the_guards_form(self):
        got = self.registered()
        if got is None or not got[1]:
            if self.expected_registered():
                self.fail("hooks/README.md documents read_once.py but hooks.json does not register it")
            self.skipTest("hooks.json does not register read_once.py yet (executor applies hooks.json.patch)")
        cfg, rows = got
        guards = [h["if"] for blocks in cfg["hooks"].values() for b in blocks for h in b.get("hooks", [])
                  if "guard.py" in h.get("command", "") and "if" in h]
        self.assertTrue(guards)
        for g in guards:                             # the live-checked reference forms really match the pattern
            self.assertRegex(g, self.GUARD_FORM)
        self.assertIn(f"//**/{case_class('assets')}/**", "".join(guards))   # and "the guard's style" means this
        post = [(m, h) for ev, m, h in rows if ev == "PostToolUse"]
        self.assertTrue(post, "read_once.py needs a PostToolUse registration")
        for matcher, h in post:
            self.assertEqual(matcher, "Read")
            self.assertIn("if", h, "the Read hook must run only for reads under output/")
            m = self.IF_FORM.match(h["if"])
            self.assertIsNotNone(m, h["if"])
            self.assertEqual(m.group("tool"), "Read")
            self.assertEqual(m.group("glob"), case_class("output"), "the guard spells names with [Xx] classes")
            self.assertLessEqual(h.get("timeout", 10), 10)
            self.assertIn("run_python.sh", h["command"])
            self.assertIn("${CLAUDE_PLUGIN_ROOT}", h["command"])

    def test_session_events_registered(self):
        got = self.registered()
        if got is None or not got[1]:
            if self.expected_registered():
                self.fail("hooks/README.md documents read_once.py but hooks.json does not register it")
            self.skipTest("hooks.json does not register read_once.py yet (executor applies hooks.json.patch)")
        _cfg, rows = got
        starts = [(m, h) for ev, m, h in rows if ev == "SessionStart"]
        self.assertEqual([m for m, _ in starts], ["compact"])
        self.assertTrue(any(ev == "SessionEnd" for ev, _m, _h in rows))
        for ev, m, h in rows:
            if ev != "PostToolUse":
                self.assertNotIn("if", h)


if __name__ == "__main__":
    unittest.main()
