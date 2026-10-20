"""BL-15 (Addendum L, L-G13): the lead-step approval token, engine side (lib/lead_steps.py).

The guard writes a single-use token when it allows the lead's own plain call of a lead-only step; the engine runs that
step only when it consumes a token for the same normalised call. These tests are generic: a token is present or
absent, right or wrong. They never list unusual shell spellings (the guard's own tests cover the text rules).
Run:  tools/test.sh -p test_lead_token.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import argparse
import json
import os
import shutil
import statistics
import tempfile
import threading
import time
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import lead_steps as ls  # noqa: E402

SESSION = "11111111-2222-3333-4444-555555555555"

# (argv, lead-only step or None): generic, one row per table entry with and without its option
STEP_ROWS = [
    (["approve-plan", "--by", "editor"], "approve-plan"),
    (["auto-approve"], "auto-approve"),
    (["reels-select", "--pick", "1"], "reels-select"),
    (["lock", "--release"], "lock --release"),
    (["lock", "--status"], None),
    (["lock"], None),
    (["settings", "--init", "X"], "settings --init"),
    (["settings", "--set", "a=b"], None),
    (["handoff", "--delivered"], "handoff --delivered"),
    (["handoff"], None),
    (["verify", "--record", "--verdict", "pass"], "verify --record"),
    (["verify"], None),
    (["ae-probe", "--record", "ok"], "ae-probe --record"),
    (["ae-probe"], None),
    (["ref-style", "--adopt", "C1", "--yes"], "ref-style --adopt --yes"),
    (["ref-style", "--adopt", "C1"], None),
    (["caption-looks", "--pick", "bold", "--yes"], "caption-looks --pick --yes"),
    (["caption-looks", "--pick", "bold"], None),
    (["caption-looks"], None),
    (["rules", "--add", "P1"], "rules --add"),
    (["rules", "--remove", "R1"], "rules --remove"),
    (["rules", "--propose"], None),
    (["rules", "--list"], None),
    (["rules", "--record"], "rules --record"),
    (["rules", "--dismiss", "P1"], "rules --dismiss"),
    (["clean", "--apply"], "clean --apply"),
    (["clean"], None),
    (["transcript-verify"], "transcript-verify"),
    (["transcript-verify", "--by", "editor"], "transcript-verify"),
    (["transcript-verify", "--by", "someone"], "transcript-verify"),
    (["transcript-verify", "--by", "agent"], None),
    (["transcript-verify", "--by", "claude"], None),
    (["transcript-verify", "--by", "transcript-editor"], None),
    (["plan"], None),
    (["status"], None),
]


class Home(unittest.TestCase):
    """A fresh engine home and cwd per test; the session id is fixed."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bl15_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.cwd = self.tmp / "client one"
        (self.cwd / "assets").mkdir(parents=True)
        (self.cwd / "data").mkdir()
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}
        env.update({"WHYNOT_HOME": str(self.home), "CLAUDE_CODE_SESSION_ID": SESSION})
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)

    def tokens(self):
        """Tokens and claimed tokens in the folder (other names are not ours: on Windows a scanner may briefly leave
        an upper-cased `*.tmp` copy of a file that was just deleted)."""
        d = self.home / "run" / "lead-tokens"
        return sorted(x.name for x in d.iterdir() if x.name.endswith((".tok", ".claim"))) if d.is_dir() else []

    def issue(self, argv, cwd=None, **kw):
        return ls.issue(argv, str(cwd or self.cwd), session=kw.pop("session", SESSION), **kw)

    def consume(self, argv, cwd=None, **kw):
        return ls.consume(argv, str(cwd or self.cwd), **kw)


class TestTable(unittest.TestCase):
    def test_step_detection_from_text(self):
        for argv, want in STEP_ROWS:
            with self.subTest(argv=argv):
                self.assertEqual(ls.lead_step(["--root", "X"] + argv), want)

    def test_global_options_anywhere_and_equals_form(self):
        self.assertEqual(ls.lead_step(["--root", "X", "--video-id", "C1", "handoff", "--delivered"]),
                         "handoff --delivered")
        self.assertEqual(ls.lead_step(["handoff", "--root=X", "--delivered"]), "handoff --delivered")
        self.assertEqual(ls.lead_step(["--root=handoff", "status"]), None)
        self.assertEqual(ls.lead_step(["--root", "approve-plan", "status"]), None)
        self.assertEqual(ls.lead_step(["ref-style", "--adopt=C1", "--yes"]), "ref-style --adopt --yes")

    def test_transcript_verify_last_by_wins(self):
        self.assertEqual(ls.lead_step(["transcript-verify", "--by", "agent", "--by", "editor"]), "transcript-verify")
        self.assertIsNone(ls.lead_step(["transcript-verify", "--by", "editor", "--by", "agent"]))
        self.assertIsNone(ls.lead_step(["transcript-verify", "--by=Claude"]))

    def test_agent_names_come_from_the_plugin(self):
        names = ls.subagent_verify_by()
        self.assertIn("agent", names)
        self.assertIn("transcript-editor", names)
        self.assertIn("whynot-cut:transcript-editor", names)
        self.assertNotIn("editor", names)

    def test_text_and_parsed_namespace_agree(self):
        """The engine reads the parsed namespace of the real CLI parser; the guard reads the text. Same answer."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("reel_cli_bl15", SK / "engine/reel/cli.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        seen = {}
        known = set(cli.registered_commands())

        def capture(a):
            seen["ns"] = a
        for argv, want in STEP_ROWS:
            if argv[0] not in known:                # a step whose CLI hunk has not landed yet (e.g. T4.3 `rules`)
                continue
            argv = ["--root", "X"] + argv
            seen.clear()
            with self.subTest(argv=argv), mock.patch.object(cli, "start", capture), \
                    mock.patch.object(cli.priority, "apply", lambda: None), \
                    mock.patch.object(ls, "engine_check", lambda *a, **k: None):
                cli.main(argv)
                self.assertIn("ns", seen)
                self.assertEqual(ls.lead_step_ns(seen["ns"]), want)
                self.assertEqual(ls.lead_step(argv), want)


class TestNormalise(Home):
    def key(self, argv, cwd=None):
        return ls.key(argv, str(cwd or self.cwd))

    def test_same_call_same_key(self):
        a = ["--root", str(self.cwd), "approve-plan", "--by", "editor"]
        self.assertEqual(self.key(a), self.key(["--root=" + str(self.cwd), "approve-plan", "--by", "editor"]))
        rel = os.path.relpath(self.cwd, self.tmp)
        self.assertEqual(self.key(a), self.key(["--root", rel, "approve-plan", "--by", "editor"], cwd=self.tmp))

    def test_any_difference_changes_the_key(self):
        base = ["--root", str(self.cwd), "--video-id", "C1", "approve-plan", "--by", "editor", "--note", "ok"]
        other = self.tmp / "client two"
        other.mkdir()
        variants = [
            ["--root", str(other)] + base[2:],
            base[:3] + ["C2"] + base[4:],
            base[:4] + ["auto-approve"] + base[5:],
            base[:6] + ["delegated"] + base[7:],
            base[:-1] + ["not ok"],
            base + ["--extra"],
        ]
        k = self.key(base)
        for v in variants:
            with self.subTest(v=v):
                self.assertNotEqual(k, self.key(v))

    def test_unicode_forms_are_one_key(self):
        word = "مراجعة نهائية é"
        a = ["approve-plan", "--by", "editor", "--note", unicodedata.normalize("NFC", word)]
        b = ["approve-plan", "--by", "editor", "--note", unicodedata.normalize("NFD", word)]
        self.assertEqual(self.key(a), self.key(b))

    def test_no_root_binds_the_cwd(self):
        other = self.tmp / "client two"
        other.mkdir()
        a = ["approve-plan", "--by", "editor"]
        self.assertNotEqual(self.key(a), self.key(a, cwd=other))
        self.assertEqual(self.key(a), self.key(a, cwd=str(self.cwd) + os.sep))

    def test_root_through_a_link_is_the_real_folder(self):
        link = self.tmp / "link"
        try:
            if os.name == "nt":
                import subprocess
                r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(self.cwd)], capture_output=True)
                if r.returncode:
                    self.skipTest("junction not available")
            else:
                link.symlink_to(self.cwd, target_is_directory=True)
        except OSError:
            self.skipTest("links not available")
        self.addCleanup(lambda: os.rmdir(link) if os.name == "nt" else link.unlink())
        a = ["--root", str(self.cwd), "verify", "--record"]
        self.assertEqual(self.key(a), self.key(["--root", str(link), "verify", "--record"]))

    def test_windows_drive_forms(self):
        with mock.patch.object(ls, "IS_WIN", True), \
                mock.patch.object(ls, "_realpath", lambda p: p.replace("\\", "/")), \
                mock.patch.object(ls, "_normcase", lambda p: p.lower()):
            k = ls.key(["--root", "/d/Clients/X", "verify", "--record", "--sheet", "/d/S.png"], "C:/w")
            self.assertEqual(k, ls.key(["--root", "D:/clients/x", "verify", "--record", "--sheet", "D:/S.png"], "C:/w"))
            self.assertEqual(k, ls.key(["--root", "d:\\Clients\\X", "verify", "--record", "--sheet", "D:/S.png"], "C:/w"))
            # Git Bash converts a `name=/d/x` value too
            self.assertEqual(ls.key(["settings", "--init", "X", "--set", "clients_root=/d/Clients"], "C:/w"),
                             ls.key(["settings", "--init", "X", "--set", "clients_root=D:/Clients"], "C:/w"))
        with mock.patch.object(ls, "IS_WIN", False):
            self.assertNotEqual(ls.key(["--root", "/d/x", "verify", "--record"], "/w"),
                                ls.key(["--root", "D:/x", "verify", "--record"], "/w"))


class TestToken(Home):
    A = ["approve-plan", "--by", "editor"]

    def test_issue_then_consume_once(self):
        self.issue(self.A)
        self.assertEqual(len(self.tokens()), 1)
        self.assertTrue(self.consume(self.A))
        self.assertEqual(self.tokens(), [])
        self.assertFalse(self.consume(self.A))

    def test_no_token_is_refused_without_creating_the_folder(self):
        self.assertFalse(self.consume(self.A))
        self.assertFalse((self.home / "run").exists())

    def test_wrong_call_is_refused_and_leaves_the_token(self):
        self.issue(self.A)
        other = self.tmp / "client two"
        other.mkdir()
        self.assertFalse(self.consume(["approve-plan", "--by", "delegated"]))
        self.assertFalse(self.consume(self.A, cwd=other))
        self.assertEqual(len(self.tokens()), 1)
        self.assertTrue(self.consume(self.A))

    def test_expired_token_is_refused_and_removed(self):
        self.issue(self.A)
        self.assertFalse(self.consume(self.A, now=time.time() + ls.TTL_S + 1))
        self.assertEqual(self.tokens(), [])

    def test_future_token_is_refused(self):
        self.issue(self.A)
        self.assertFalse(self.consume(self.A, now=time.time() - ls.SKEW_S - 5))

    def test_other_session_is_refused_and_its_token_put_back(self):
        """Another Claude Code session's token for the same call is not used up: it stays for that session."""
        self.issue(self.A, session="another-session")
        self.assertFalse(self.consume(self.A))
        self.assertEqual(len(self.tokens()), 1)
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "another-session"}):
            self.assertTrue(self.consume(self.A))

    def test_token_without_session_is_refused_inside_a_session(self):
        self.issue(self.A, session="")
        self.assertFalse(self.consume(self.A))

    def test_the_session_must_match_exactly(self):
        """An engine without a session id (the variable dropped) uses only a token issued without one."""
        self.issue(self.A, session=SESSION)
        with mock.patch.dict(os.environ):
            os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            self.assertFalse(self.consume(self.A))
            self.issue(self.A, session="")
            self.assertTrue(self.consume(self.A))
        self.assertTrue(self.consume(self.A))

    def test_a_briefly_locked_token_is_still_used(self):
        """Windows: a scanner may hold a fresh file open; the claim retries before it gives up."""
        self.issue(self.A)
        real, calls = os.rename, []

        def flaky(src, dst):
            calls.append(src)
            if len(calls) == 1:
                raise PermissionError(32, "in use")
            return real(src, dst)
        with mock.patch.object(ls.os, "rename", flaky), mock.patch.object(ls.time, "sleep", lambda s: None):
            self.assertTrue(self.consume(self.A))
        self.assertGreaterEqual(len(calls), 2)

    def test_a_token_that_stays_locked_is_left_alone(self):
        self.issue(self.A)

        def locked(src, dst):
            raise PermissionError(32, "in use")
        with mock.patch.object(ls.os, "rename", locked), mock.patch.object(ls.time, "sleep", lambda s: None):
            self.assertFalse(self.consume(self.A))
        self.assertEqual(len(self.tokens()), 1)

    def test_malformed_token_is_refused_and_removed(self):
        p = self.issue(self.A)
        for content in (b"not json", json.dumps({"v": 1}).encode(), b""):
            p.write_bytes(content)
            self.assertFalse(self.consume(self.A))
            self.assertFalse(p.exists())
            p = self.issue(self.A)

    def test_a_renamed_token_does_not_carry_another_key(self):
        """A token's file name and its content must name the same call."""
        p = self.issue(["auto-approve"])
        forged = p.with_name(ls.key(self.A, str(self.cwd)) + p.name[p.name.index("."):])
        p.rename(forged)
        self.assertFalse(self.consume(self.A))

    def test_two_tokens_for_one_call_are_two_uses(self):
        self.issue(self.A)
        self.issue(self.A)
        self.assertTrue(self.consume(self.A))
        self.assertTrue(self.consume(self.A))
        self.assertFalse(self.consume(self.A))

    def test_parallel_calls_each_consume_their_own(self):
        calls = [["verify", "--record", "--note", str(i)] for i in range(12)]
        for c in calls:
            self.issue(c)
        results = {}
        barrier = threading.Barrier(len(calls))

        def worker(i, c):
            barrier.wait()
            results[i] = self.consume(c)
        ts = [threading.Thread(target=worker, args=(i, c)) for i, c in enumerate(calls)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(30)
        self.assertEqual(results, {i: True for i in range(len(calls))})
        self.assertEqual(self.tokens(), [])

    def test_parallel_consumers_of_one_token_get_it_once(self):
        self.issue(self.A)
        results = []
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()
            results.append(self.consume(self.A))
        ts = [threading.Thread(target=worker) for _ in range(8)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(30)
        self.assertEqual(sorted(results), [False] * 7 + [True])

    def test_crash_leftovers_are_cleaned_on_the_next_issue(self):
        old = self.issue(self.A)
        claim = old.with_name(old.name + ".99.ab.claim")
        claim.write_text("{}", encoding="utf-8")
        later = time.time() + ls.TTL_S + 60
        os.utime(old, (later - ls.TTL_S - 30, later - ls.TTL_S - 30))
        os.utime(claim, (later - ls.TTL_S - 30, later - ls.TTL_S - 30))
        ls.issue(["auto-approve"], str(self.cwd), session=SESSION, now=later)
        self.assertEqual(len(self.tokens()), 1)
        self.assertFalse(old.exists())
        self.assertFalse(claim.exists())

    def test_cleanup_never_removes_other_files(self):
        d = self.home / "run" / "lead-tokens"
        d.mkdir(parents=True)
        keep = d / "README.txt"
        keep.write_text("x", encoding="utf-8")
        sub = d / "sub.tok"
        sub.mkdir()
        old = time.time() - 3600
        os.utime(keep, (old, old))
        self.issue(self.A)
        self.assertTrue(keep.exists())
        self.assertTrue(sub.is_dir())

    @unittest.skipIf(os.name == "nt", "POSIX file modes; on Windows the folder inherits the engine home's ACL (L-G16)")
    def test_posix_modes(self):
        p = self.issue(self.A)
        self.assertEqual(p.stat().st_mode & 0o777, 0o600)
        self.assertEqual(p.parent.stat().st_mode & 0o777, 0o700)

    def test_token_lives_under_the_engine_home(self):
        p = self.issue(self.A)
        self.assertEqual(p.parent, self.home / "run" / "lead-tokens")
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data["session"], SESSION)
        self.assertEqual(data["issuer"], "hook")
        self.assertLessEqual(data["expires"] - data["issued"], ls.TTL_S)

    def test_a_claim_is_judged_by_its_own_age(self):
        """A valid token near the end of its life is claimed: the claim gets a fresh time, so a cleanup running at
        that moment does not remove it before it is read."""
        p = self.issue(self.A)
        old = time.time() - ls.TTL_S - ls.SKEW_S - 2            # older than a claim may get
        os.utime(p, (old, old))
        real_read = ls._read

        def read_after_cleanup(path):
            ls.cleanup(path.parent, time.time() + 1)
            return real_read(path)
        with mock.patch.object(ls, "_read", read_after_cleanup):
            self.assertTrue(self.consume(self.A))

    def test_in_token_dir_judges_the_real_path(self):
        d = self.home / "run" / "lead-tokens"
        d.mkdir(parents=True)
        self.assertTrue(ls.in_token_dir(str(d / "x.tok")))
        self.assertTrue(ls.in_token_dir(str(self.home / "RUN" / "Lead-Tokens" / "y")))
        self.assertFalse(ls.in_token_dir(str(self.home / "run" / "x.tok")))
        link = self.tmp / "innocent"
        try:
            if os.name == "nt":
                import subprocess
                r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(d)], capture_output=True)
                if r.returncode:
                    self.skipTest("junction not available")
            else:
                link.symlink_to(d, target_is_directory=True)
        except OSError:
            self.skipTest("links not available")
        self.addCleanup(lambda: os.rmdir(link) if os.name == "nt" else link.unlink())
        self.assertTrue(ls.in_token_dir(str(link / "z.tok")))

    def test_issue_if_lead(self):
        self.assertIsNone(ls.issue_if_lead(["lock", "--status"], str(self.cwd)))
        self.assertEqual(self.tokens(), [])
        p = ls.issue_if_lead(self.A, str(self.cwd))
        self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["issuer"], "panel")
        self.assertTrue(self.consume(self.A))
        old = os.getcwd()
        os.chdir(self.cwd)
        try:
            ls.issue_if_lead(self.A)
            self.assertTrue(ls.consume(self.A, os.getcwd()))
        finally:
            os.chdir(old)

    def test_issue_for_an_engine_environment(self):
        """The token goes where the started engine will look: that environment's home and session."""
        other = self.tmp / "other home"
        env = {"WHYNOT_HOME": str(other), "CLAUDE_CODE_SESSION_ID": "s2"}
        self.assertIsNone(ls.issue_for(["lock", "--status"], env, cwd=str(self.cwd)))
        p = ls.issue_for(self.A, env, cwd=str(self.cwd))
        self.assertEqual(p.parent, other / "run" / "lead-tokens")
        with mock.patch.dict(os.environ, env):
            self.assertTrue(ls.consume(self.A, str(self.cwd)))
        p = ls.issue_for(self.A, {}, cwd=str(self.cwd))           # no session in that environment
        self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["session"], "")

    def test_issue_latency(self):
        times = []
        for i in range(200):
            t0 = time.perf_counter()
            self.issue(["verify", "--record", "--note", str(i)])
            times.append(time.perf_counter() - t0)
        p95 = statistics.quantiles(times, n=20)[18]
        self.assertLess(p95, 0.020, f"issue p95 {p95 * 1000:.1f} ms")


class TestEngineCheck(Home):
    def ns(self, argv):
        cmd = argv[0]
        a = argparse.Namespace(cmd=cmd)
        for k in ("release", "init", "delivered", "record", "adopt", "yes", "by"):
            setattr(a, k, None)
        i = 1
        while i < len(argv):
            t = argv[i]
            if t.startswith("--"):
                name = t[2:].replace("-", "_")
                val = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else True
                setattr(a, name, val)
                i += 1 if val is True else 2
                continue
            i += 1
        return a

    def test_not_a_lead_step_never_looks_for_a_token(self):
        self.assertIsNone(ls.engine_check(self.ns(["plan"]), ["plan"], str(self.cwd)))
        self.assertFalse((self.home / "run").exists())

    def test_lead_step_without_token_is_refused(self):
        argv = ["handoff", "--delivered"]
        r = ls.engine_check(self.ns(argv), argv, str(self.cwd))
        self.assertIsInstance(r, dict)
        self.assertTrue(r["blocked"].startswith("الخطوة دي للمحرر بس"))
        self.assertIn("handoff --delivered", r["blocked"])
        self.assertIn("one plain call", r["how"])
        self.assertIn("absolute --root", r["how"])
        self.assertIn("no cd", r["how"])
        self.assertIn("no variables", r["how"])

    def test_lead_step_with_token_runs(self):
        argv = ["handoff", "--delivered"]
        self.issue(argv)
        self.assertIsNone(ls.engine_check(self.ns(argv), argv, str(self.cwd)))
        self.assertEqual(self.tokens(), [])

    def test_an_expired_approval_says_so(self):
        argv = ["handoff", "--delivered"]
        self.issue(argv, now=time.time() - ls.TTL_S - 2)
        r = ls.engine_check(self.ns(argv), argv, str(self.cwd))
        self.assertIn("Run the same command again", r["blocked"])
        self.assertIn("خلص وقتها", r["blocked"])

    def test_the_refusal_names_its_cause(self):
        """A missing token is explained: the hook missing from hooks.json, not running, no plain lead call seen, the
        call not confirmed in the transcript, another call approved, the approval used or expired."""
        argv = ["handoff", "--delivered"]
        d = self.home / "run" / "lead-tokens"

        def stamp(result, k):
            d.mkdir(parents=True, exist_ok=True)
            (d / ls.SEEN_FILE).write_text(json.dumps({"time": time.time(), "result": result, "key": k}),
                                          encoding="utf-8")
        mine, other = ls.key(argv, str(self.cwd)), ls.key(["handoff", "--delivered", "--note", "x"], str(self.cwd))
        cases = [  # (registered, running, stamp, expected cause)
            (False, True, None, "missing"),
            (True, False, None, "not-running"),
            (True, True, None, "not-seen"),
            (True, None, ("not-plain", ""), "not-plain"),
            (True, True, ("not-confirmed", mine), "not-confirmed"),
            (True, True, ("issued", other), "other-call"),
            (True, True, ("issued", mine), "used"),
        ]
        for registered, running, seen, want in cases:
            with self.subTest(want=want), mock.patch.object(ls, "hook_registered", lambda: registered), \
                    mock.patch.object(ls, "guard_running", lambda: running):
                (d / ls.SEEN_FILE).unlink(missing_ok=True) if d.is_dir() else None
                if seen:
                    stamp(*seen)
                r = ls.engine_check(self.ns(argv), argv, str(self.cwd))
                self.assertEqual(r["cause"], want)
                self.assertTrue(r["blocked"].startswith("الخطوة دي للمحرر بس"))
                self.assertIn("لو انت المحرر: شغّلها من Claude نفسه، مكالمة واحدة بسيطة", r["blocked"])
                self.assertIn(ls.CAUSES[want], r["blocked"])
                self.assertIn("reel doctor", r["how"])
        with mock.patch.object(ls, "hook_registered", lambda: True), mock.patch.object(ls, "guard_running", lambda: True):
            stamp("issued", mine)
            old = time.time() - ls.TTL_S - ls.SKEW_S - 5            # a stale look explains nothing
            (d / ls.SEEN_FILE).write_text(json.dumps({"time": old, "result": "issued", "key": mine}), encoding="utf-8")
            self.assertEqual(ls.engine_check(self.ns(argv), argv, str(self.cwd))["cause"], "not-seen")

    def test_the_hook_registration_is_read_from_hooks_json(self):
        self.assertTrue(ls.hook_registered())                       # this plugin
        plugin = self.tmp / "plugin"
        (plugin / "hooks").mkdir(parents=True)
        self.assertFalse(ls.hook_registered(plugin))
        guard = {"type": "command", "command": "bash run_python.sh guard.py"}
        for blocks, want in (([{"matcher": "Bash|PowerShell", "hooks": [guard]}], True),
                             ([{"matcher": "Bash", "hooks": [guard]}], False),
                             ([{"matcher": "Bash|PowerShell", "hooks": [dict(guard, **{"if": "Bash(x)"})]}], False),
                             ([{"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "command": "other"}]}],
                              False)):
            (plugin / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {"PreToolUse": blocks}}),
                                                         encoding="utf-8")
            with self.subTest(blocks=blocks):
                self.assertEqual(ls.hook_registered(plugin), want)
        (plugin / "hooks" / "hooks.json").write_text("not json", encoding="utf-8")
        self.assertFalse(ls.hook_registered(plugin))

    def test_doctor_check(self):
        r = ls.doctor_check()
        self.assertEqual((r["ok"], r["registered"], r["round_trip"], r["fix"]), (True, True, True, None))
        self.assertEqual(self.tokens(), [])                         # the round trip leaves nothing behind
        with mock.patch.object(ls, "hook_registered", lambda: False):
            r = ls.doctor_check()
            self.assertFalse(r["ok"])
            self.assertIn("hooks.json", r["fix"])
        blocker = self.tmp / "not a folder"
        blocker.write_text("x", encoding="utf-8")                   # an engine home that cannot hold the folder
        r = ls.doctor_check(home=blocker)
        self.assertEqual((r["ok"], r["round_trip"]), (False, False))
        self.assertIn("run/lead-tokens", r["fix"])

    def test_another_sessions_token_is_named_as_such(self):
        argv = ["handoff", "--delivered"]
        self.issue(argv, session="another-session")
        with mock.patch.object(ls, "hook_registered", lambda: True), mock.patch.object(ls, "guard_running", lambda: True):
            self.assertEqual(ls.engine_check(self.ns(argv), argv, str(self.cwd))["cause"], "other-session")
        self.assertEqual(len(self.tokens()), 1)                    # still there for its own session

    def test_doctor_reports_an_unexpected_error_instead_of_crashing(self):
        with mock.patch.object(ls, "take", mock.Mock(side_effect=ValueError("broken"))):
            r = ls.doctor_check()
        self.assertEqual((r["ok"], r["round_trip"]), (False, False))
        self.assertIn("ValueError: broken", r["fix"])

    def test_the_transcript_store_is_judged_by_the_real_path(self):
        claude = self.tmp / "claude"
        (claude / "projects" / "p").mkdir(parents=True)
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(claude)}):
            self.assertTrue(ls.in_transcript_store(str(claude / "projects" / "p" / "s.jsonl")))
            self.assertFalse(ls.in_transcript_store(str(self.tmp / "projects" / "p" / "s.jsonl")))
            self.assertFalse(ls.in_transcript_store(str(claude / "projectsX" / "s.jsonl")))

    def test_no_environment_variable_opens_the_wall(self):
        """Without a token a lead-only step is refused, whatever the environment says (no TTY or variable escape)."""
        argv = ["approve-plan", "--by", "editor"]
        clean = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
        tty = mock.Mock(isatty=lambda: True, fileno=lambda: 0)
        for extra in ({}, {"WHYNOT_LEAD_TTY": "1"}, {"WHYNOT_LEAD": "1"}):
            with self.subTest(extra=extra), mock.patch.dict(os.environ, dict(clean, **extra), clear=True), \
                    mock.patch("sys.stdin", tty):
                self.assertIsNotNone(ls.engine_check(self.ns(argv), argv, str(self.cwd)))


if __name__ == "__main__":
    unittest.main()
