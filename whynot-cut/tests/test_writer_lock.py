"""3.0 T1.8 one writer per client folder: output/.whynot-lock, `reel lock`, the guard rule and the SessionStart warning.
Two Claude sessions worked on one client folder at the same time in the field (chats-other: "Two sessions on one
client folder, no lock"); a session's writing commands now take and refresh a per-client session lease.
Run:  ~/.whynot-cut/venv/Scripts/python.exe -B -m unittest discover -s whynot-cut/tests -p test_writer_lock.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import writer_lock  # noqa: E402
from lib import lead_steps  # noqa: E402  BL-15: a lead-only step runs with the guard's token

CLI = SK / "engine/reel/cli.py"
GUARD = SK / "hooks" / "guard.py"
CTX = SK / "hooks" / "session_context.py"
END = SK / "hooks" / "session_end.py"
SESSION_ENV = ("WHYNOT_LOCK_SESSION", "CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID")
CLIENTS_ENV = ("WHYNOT_CLIENTS_ROOT", "CLAUDE_PLUGIN_OPTION_CLIENTS_ROOT", "REEL_CLIENTS_ROOT")


def env_for(session: str | None = "me-session", **extra) -> dict:
    """A process environment whose session id is exactly `session` (None: no session variable at all)."""
    e = {k: v for k, v in os.environ.items() if k not in SESSION_ENV + CLIENTS_ENV and k != "CLAUDE_PLUGIN_DATA"}
    e["WHYNOT_CLIENTS_ROOT"] = str(Path(tempfile.gettempdir()) / "whynot-test-clients-root-unset")
    if session:
        e["CLAUDE_CODE_SESSION_ID"] = session
    e.update(extra)
    return e


def cli_module():
    spec = importlib.util.spec_from_file_location("reel_cli_t18", CLI)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


class LockFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "lock clinic"
        for d in ("assets/Photos", "data/Raw", "output"):
            (self.root / d).mkdir(parents=True)
        (self.root / ".whynot-client").write_text('{"whynot_client": 1, "created": "test"}', encoding="utf-8")
        self.lock = self.root / "output/.whynot-lock"

    def tearDown(self):
        self.tmp.cleanup()

    def hold(self, session="other-session", pid=None, host=None, command="reel transcribe --video-id C0001",
             age_s=0):
        rec = {"session_id": session, "pid": os.getpid() if pid is None else pid,
               "host": host or socket.gethostname(), "started_at": "2026-10-11T10:00:00+03:00", "command": command}
        self.lock.write_text(json.dumps(rec), encoding="utf-8")
        if age_s:
            t = time.time() - age_s
            os.utime(self.lock, (t, t))
        return rec

    def reel(self, *args, session="me-session", **extra):
        e = env_for(session, **extra)
        lead_steps.issue_for(["--root", str(self.root), *args], e)     # BL-15: the lead's token
        return subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args], capture_output=True,
                              text=True, encoding="utf-8", env=e)

    def log_text(self) -> str:
        f = self.root / "output/logs/pipeline.log"
        return f.read_text(encoding="utf-8") if f.exists() else ""


class TestCommandClassification(unittest.TestCase):
    def test_every_command_is_classified_once(self):
        """Each subcommand chooses: writes the client folder, reads only, or writes depending on a flag."""
        cli = cli_module()
        from lib import motion_cli, podcast_cli
        groups = {"CORE_WRITES": cli.CORE_WRITES, "CORE_READS": cli.CORE_READS, "WRITES_IF": set(cli.WRITES_IF),
                  "podcast WRITES": podcast_cli.WRITES, "podcast READS": podcast_cli.READS,
                  "motion WRITES": motion_cli.WRITES, "motion READS": motion_cli.READS}
        for name in cli.registered_commands():
            hits = [g for g, s in groups.items() if name in s]
            self.assertEqual(len(hits), 1, f"{name}: classified in {hits or 'no group'}")
        every = set().union(*groups.values())
        self.assertEqual(every - set(cli.registered_commands()), set(), "classified commands that do not exist")
        self.assertEqual(set(podcast_cli.WRITES) | set(podcast_cli.READS), set(podcast_cli.ARGS))
        self.assertEqual(set(motion_cli.WRITES) | set(motion_cli.READS), set(motion_cli.ARGS))

    def test_read_only_examples(self):
        cli = cli_module()
        for name in ("next", "status", "ppro-status", "lock"):
            self.assertIn(name, cli.CORE_READS, name)
        from lib import motion_cli, podcast_cli
        self.assertIn("ae-status", motion_cli.READS)
        self.assertIn("episode-next", podcast_cli.READS)
        for name in ("transcribe", "plan", "ppro-build", "approve-plan", "discover"):
            self.assertIn(name, cli.CORE_WRITES, name)
        for name in ("episode-transcribe", "reels-select"):
            self.assertIn(name, podcast_cli.WRITES, name)
        self.assertIn("motion-build", motion_cli.WRITES)

    def test_flag_dependent_writers(self):
        import argparse
        cli = cli_module()
        ns = argparse.Namespace
        with tempfile.TemporaryDirectory() as d:
            # inbox --no-refresh only reads the last discovery; without one it runs discovery (a write)
            self.assertTrue(cli.writes(ns(cmd="inbox", no_refresh=True, root=d)))
            (Path(d) / "output/discovery").mkdir(parents=True)
            (Path(d) / "output/discovery/input-inventory.json").write_text('{"files": []}', encoding="utf-8")
            self.assertFalse(cli.writes(ns(cmd="inbox", no_refresh=True, root=d)))
            self.assertTrue(cli.writes(ns(cmd="inbox", no_refresh=False, root=d)))
        self.assertFalse(cli.writes(ns(cmd="doctor", fix=False)))
        self.assertFalse(cli.writes(ns(cmd="doctor", fix=True)))          # gate G2: the marker needs no lease
        self.assertFalse(cli.writes(ns(cmd="settings", init=None)))
        self.assertTrue(cli.writes(ns(cmd="settings", init="X")))
        self.assertFalse(cli.writes(ns(cmd="range", footage=None)))
        self.assertTrue(cli.writes(ns(cmd="range", footage="data/Raw/a.mp4")))
        self.assertFalse(cli.writes(ns(cmd="ref-style", record=False, apply=False)))
        self.assertTrue(cli.writes(ns(cmd="ref-style", record=True, apply=False)))
        self.assertTrue(cli.writes(ns(cmd="transcribe")))
        self.assertFalse(cli.writes(ns(cmd="next")))
        self.assertTrue(cli.writes(ns(cmd="episode-transcribe")))
        self.assertFalse(cli.writes(ns(cmd="motion-icons")))


class TestSessionId(unittest.TestCase):
    def test_precedence(self):
        sid = writer_lock.session_id
        self.assertEqual(sid({"WHYNOT_LOCK_SESSION": "parent", "CLAUDE_SESSION_ID": "a", "CLAUDE_CODE_SESSION_ID": "b"}),
                         "parent")
        self.assertEqual(sid({"CLAUDE_SESSION_ID": "a", "CLAUDE_CODE_SESSION_ID": "b"}), "a")
        self.assertEqual(sid({"CLAUDE_CODE_SESSION_ID": "b", "CLAUDE_PID": "77"}), "b")
        self.assertEqual(sid({"CLAUDE_PID": "77"}), "claude-pid-77")
        self.assertEqual(sid({}), f"pid-{os.getpid()}")

    def test_pid_alive(self):
        self.assertTrue(writer_lock.pid_alive(os.getpid()))
        self.assertFalse(writer_lock.pid_alive(dead_pid()))
        self.assertFalse(writer_lock.pid_alive(0))


class TestOneWriter(LockFixture):
    def test_foreign_live_lock_blocks_a_writer(self):
        rec = self.hold()
        r = self.reel("client-init", "--id", "lock-clinic")
        self.assertNotEqual(r.returncode, 0, r.stderr)
        res = json.loads(r.stdout)
        self.assertIn("blocked", res)
        self.assertIn("how", res)
        self.assertIn("reel transcribe --video-id C0001", res["blocked"])
        self.assertIn("reel lock --release", res["how"])
        self.assertFalse((self.root / "output/client_database/reel-profile").exists(), "the blocked command wrote")
        self.assertEqual(json.loads(self.lock.read_text(encoding="utf-8")), rec, "the holder's lock was touched")

    def test_two_processes(self):
        """A real second writer while the first one runs; the first one dies -> its lock is taken over and logged."""
        code = ("import sys, time; sys.path.insert(0, sys.argv[1]); from lib import writer_lock as w; "
                "l = w.acquire(sys.argv[2], 'reel episode-transcribe --episode EP02'); print('held', flush=True); "
                "time.sleep(120)")
        holder = subprocess.Popen([sys.executable, "-c", code, str(SK / "engine/reel"), str(self.root)],
                                  stdout=subprocess.PIPE, text=True, env=env_for("first-session"))
        try:
            self.assertEqual(holder.stdout.readline().strip(), "held")
            r = self.reel("client-init", "--id", "lock-clinic", session="second-session")
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("reel episode-transcribe --episode EP02", json.loads(r.stdout)["blocked"])
        finally:
            holder.kill()
            holder.wait()
            holder.stdout.close()
        r = self.reel("client-init", "--id", "lock-clinic", session="second-session")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.root / "output/client_database/reel-profile/profile.json").exists())
        self.assertIn("stale", self.log_text())
        self.assertIn("first-session", self.log_text())
        self.assertFalse(self.lock.exists(), "the writer's own lock is released when it ends")

    def test_dead_pid_is_taken_over_with_a_log_line(self):
        self.hold(pid=dead_pid())
        r = self.reel("client-init", "--id", "lock-clinic")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("took over", self.log_text())
        self.assertIn("no longer running", self.log_text())
        self.assertFalse(self.lock.exists())

    def test_old_lock_is_taken_over(self):
        self.hold(age_s=3 * 3600)
        r = self.reel("client-init", "--id", "lock-clinic")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("2 h", self.log_text())

    def test_other_host_lock_is_kept_until_it_is_old(self):
        self.hold(pid=dead_pid(), host="another-computer")
        self.assertEqual(self.reel("client-init", "--id", "lock-clinic").returncode, 2)
        self.hold(pid=dead_pid(), host="another-computer", age_s=3 * 3600)
        self.assertEqual(self.reel("client-init", "--id", "lock-clinic").returncode, 0)

    def test_same_session_is_reentrant(self):
        rec = self.hold(session="me-session")
        r = self.reel("client-init", "--id", "lock-clinic")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        now = json.loads(self.lock.read_text(encoding="utf-8"))
        self.assertEqual((now["session_id"], now["pid"], now["started_at"]),
                         (rec["session_id"], rec["pid"], rec["started_at"]), "a re-entrant command took the lock")
        self.assertEqual(now["command"], "reel client-init", "the lease shows the session's latest writing command")

    def test_writer_leaves_no_lock(self):
        r = self.reel("client-init", "--id", "lock-clinic")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.lock.exists())

    def test_read_only_commands_are_not_blocked(self):
        (self.root / "output/discovery").mkdir()
        (self.root / "output/discovery/input-inventory.json").write_text(
            '{"files": [], "warnings": [], "by_role": {}}', encoding="utf-8")
        self.hold()
        for args in (["next", "--video-id", "C0001"], ["status", "--video-id", "C0001"], ["lock", "--status"],
                     ["inbox", "--no-refresh"]):
            r = self.reel(*args)
            self.assertEqual(r.returncode, 0, f"{args}: {r.stdout} {r.stderr}")
            self.assertNotIn('"blocked"', r.stdout, args)

    def test_nested_reel_of_a_writer_is_the_same_writer(self):
        """A reel process started by a writing command (no Claude session id) inherits WHYNOT_LOCK_SESSION."""
        lk = writer_lock.acquire(self.root, "reel parent", env={})
        try:
            self.assertTrue(os.environ.get("WHYNOT_LOCK_SESSION", "").startswith("pid-"))
            r = self.reel("client-init", "--id", "lock-clinic", session=None,
                          WHYNOT_LOCK_SESSION=os.environ["WHYNOT_LOCK_SESSION"])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        finally:
            lk.release()
            os.environ.pop("WHYNOT_LOCK_SESSION", None)
        self.assertFalse(self.lock.exists())

    def test_lock_file_is_created_exclusively(self):
        lk = writer_lock.acquire(self.root, "reel plan", env={"CLAUDE_CODE_SESSION_ID": "s1"})
        try:
            rec = json.loads(self.lock.read_text(encoding="utf-8"))
            self.assertEqual(set(rec) >= {"session_id", "pid", "host", "started_at", "command"}, True, rec)
            self.assertEqual((rec["session_id"], rec["pid"], rec["command"]), ("s1", os.getpid(), "reel plan"))
            with self.assertRaises(writer_lock.Busy):
                writer_lock.acquire(self.root, "reel qc", env={"CLAUDE_CODE_SESSION_ID": "s2"})
        finally:
            lk.release()
            os.environ.pop("WHYNOT_LOCK_SESSION", None)
        self.assertFalse(self.lock.exists())


def sleeper() -> subprocess.Popen:
    """A stand-in for a session's long-lived Claude Code process (CLAUDE_PID)."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])


class TestSessionLease(LockFixture):
    """Review round 1: the lock is a SESSION LEASE. Two sessions taking turns on one client over minutes was the field
    problem, so a session keeps the client between its commands while its Claude Code process (CLAUDE_PID) lives."""

    def a(self, *args, claude=None):
        return self.reel(*args, session="session-A", CLAUDE_PID=str(claude or os.getpid()))

    def b(self, *args, claude=None):
        return self.reel(*args, session="session-B", CLAUDE_PID=str(claude or os.getpid()))

    def rec(self):
        return json.loads(self.lock.read_text(encoding="utf-8"))

    def test_two_sessions_alternating(self):
        self.assertEqual(self.a("client-init", "--id", "lock-clinic").returncode, 0)
        lease = self.rec()
        self.assertEqual((lease["session_id"], lease["pid"]), ("session-A", os.getpid()), "holder = CLAUDE_PID")
        self.assertTrue(lease.get("pid_created"), "the holder's creation time is recorded")
        other = sleeper()                    # B runs in its own Claude Code process (T3.4: the same process after
        self.addCleanup(other.wait)          # /clear is the same writer, see test_hooks_t34.TestLeaseAcrossClear)
        self.addCleanup(other.kill)
        r = self.b("client-init", "--id", "lock-clinic", "--force", claude=other.pid)
        self.assertEqual(r.returncode, 2, "B is blocked between A's commands")
        self.assertIn("never release another session's lock yourself", json.loads(r.stdout)["how"])
        self.assertEqual(self.a("client-init", "--id", "lock-clinic", "--force").returncode, 0, "A goes on")
        self.assertEqual(self.rec()["started_at"], lease["started_at"])
        self.assertEqual(self.b("client-init", "--id", "lock-clinic", "--force", claude=other.pid).returncode, 2)
        self.assertEqual(self.b("lock", "--status", claude=other.pid).returncode, 0, "B can still read")

    def test_same_session_parallel_and_sequential_never_blocked(self):
        code = ("import sys, time; sys.path.insert(0, sys.argv[1]); from lib import writer_lock as w; "
                "l = w.acquire(sys.argv[2], 'reel transcribe --video-id C0001'); print('held', flush=True); "
                "time.sleep(120)")
        sub = subprocess.Popen([sys.executable, "-c", code, str(SK / "engine/reel"), str(self.root)],
                               stdout=subprocess.PIPE, text=True,
                               env=env_for("session-A", CLAUDE_PID=str(os.getpid())))   # a subagent's long command
        try:
            self.assertEqual(sub.stdout.readline().strip(), "held")
            for _ in range(2):                                          # the lead, sequentially, meanwhile
                r = self.a("client-init", "--id", "lock-clinic", "--force")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        finally:
            sub.kill()
            sub.wait()
            sub.stdout.close()
        self.assertTrue(self.lock.exists(), "ending a command never ends the session's lease")
        self.assertEqual(self.rec()["session_id"], "session-A")
        import shutil
        shutil.rmtree(self.root / "output/client_database")       # client-init --force keeps one .bak per file
        self.assertEqual(self.a("client-init", "--id", "lock-clinic").returncode, 0)

    def test_stale_when_the_claude_process_is_gone(self):
        claude = sleeper()
        try:
            self.assertEqual(self.a("client-init", "--id", "lock-clinic", claude=claude.pid).returncode, 0)
            self.assertEqual(self.rec()["pid"], claude.pid)
            self.assertEqual(self.b("client-init", "--id", "lock-clinic", "--force").returncode, 2)
        finally:
            claude.kill()
            claude.wait()
        r = self.b("client-init", "--id", "lock-clinic", "--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("took over", self.log_text())
        self.assertIn("session-A", self.log_text())
        self.assertEqual(self.rec()["session_id"], "session-B")

    def test_stale_after_2_h_without_a_writing_command(self):
        self.assertEqual(self.a("client-init", "--id", "lock-clinic").returncode, 0)
        t = time.time() - 3 * 3600
        os.utime(self.lock, (t, t))
        self.assertEqual(self.b("client-init", "--id", "lock-clinic", "--force").returncode, 0)
        self.assertIn("2 h", self.log_text())

    def test_release_ends_the_lease(self):
        self.assertEqual(self.a("client-init", "--id", "lock-clinic").returncode, 0)
        r = self.b("lock", "--release")                                  # the lead of B, on the editor's word
        self.assertTrue(json.loads(r.stdout)["released"])
        self.assertEqual(self.b("client-init", "--id", "lock-clinic", "--force").returncode, 0)

    def test_reused_pid_is_dead(self):
        me = writer_lock.process_created(os.getpid())
        self.assertTrue(me)
        self.assertTrue(writer_lock.pid_alive(os.getpid(), me))
        self.assertFalse(writer_lock.pid_alive(os.getpid(), "12345"))
        rec = self.hold(session="session-A")
        rec["pid_created"] = "12345"                                     # same pid, another process start
        self.lock.write_text(json.dumps(rec), encoding="utf-8")
        r = self.b("client-init", "--id", "lock-clinic")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("another program", self.log_text())

    def test_plain_terminal_keeps_per_command_behaviour(self):
        r = self.reel("client-init", "--id", "lock-clinic", session=None)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.lock.exists())

    def test_session_end_releases_only_its_own_lease(self):
        self.assertEqual(self.a("client-init", "--id", "lock-clinic").returncode, 0)

        def end(session, cwd):
            p = {"session_id": session, "cwd": str(cwd), "hook_event_name": "SessionEnd", "reason": "exit"}
            return subprocess.run([sys.executable, str(END)], input=json.dumps(p), capture_output=True, text=True,
                                  encoding="utf-8", env=env_for(None)).returncode
        self.assertEqual(end("session-B", self.root), 0)
        self.assertTrue(self.lock.exists(), "another session's lease is never touched")
        self.assertEqual(end("session-A", self.root.parent), 0)          # session opened in the clients folder
        self.assertFalse(self.lock.exists())
        self.assertIn("end of session session-A", self.log_text())

    def test_takeover_never_loses_a_fresh_lock(self):
        """M3: the aside file is moved back when hard links are unavailable."""
        from unittest import mock
        fresh = self.hold(session="fresh")
        with mock.patch.object(writer_lock.os, "link", side_effect=OSError("no hard links")):
            self.assertFalse(writer_lock._remove_stale(self.lock, {"session_id": "old"}, "test", self.root))
        self.assertEqual(json.loads(self.lock.read_text(encoding="utf-8")), fresh)
        self.assertEqual([p.name for p in self.lock.parent.glob(".whynot-lock.stale-*")], [])

    def test_restore_never_overwrites_a_lock_created_meanwhile(self):
        """T11 (M3 fallback): without hard links the aside record goes back only through an exclusive create. Whenever
        a third writer takes the path while the stale lock is put back, its lock stays and the aside file is kept;
        otherwise the record is restored. Race windows: right after the failed link, and right after any look at
        whether the path is free."""
        from unittest import mock
        third = {"session_id": "third", "pid": os.getpid(), "host": socket.gethostname()}
        real_exists = Path.exists
        for window in ("after_link", "after_exists_check"):
            for f in self.lock.parent.glob(".whynot-lock*"):
                f.unlink()
            fresh = self.hold(session="fresh")
            taken = []

            def take():
                self.lock.write_text(json.dumps(third), encoding="utf-8")
                taken.append(True)

            def no_link(src, dst):
                if window == "after_link":
                    take()
                raise OSError("no hard links")

            def exists_then_race(path):
                free = not real_exists(path)
                if window == "after_exists_check" and path == self.lock and free and not taken:
                    take()                                   # free when looked at, taken right after
                return not free
            with mock.patch.object(writer_lock.os, "link", side_effect=no_link), \
                    mock.patch.object(writer_lock.Path, "exists", exists_then_race):
                self.assertFalse(writer_lock._remove_stale(self.lock, {"session_id": "old"}, "test", self.root))
            kept = list(self.lock.parent.glob(".whynot-lock.stale-*"))
            if taken:
                self.assertEqual(json.loads(self.lock.read_text(encoding="utf-8")), third, window)   # not overwritten
                self.assertEqual(len(kept), 1, window)
                self.assertEqual(json.loads(kept[0].read_text(encoding="utf-8")), fresh, window)   # not lost
            else:
                self.assertEqual(json.loads(self.lock.read_text(encoding="utf-8")), fresh, window)
                self.assertEqual(kept, [], window)


class TestGateFixes(LockFixture):
    def test_g2_doctor_fix_marks_a_client_another_session_holds(self):
        """Gate G2: the marker write is idempotent and outside output/, so `doctor --fix` takes no lease."""
        (self.root / ".whynot-client").unlink()
        self.hold()                                                      # another live session
        r = self.reel("doctor", "--fix", CLAUDE_CONFIG_DIR=str(self.root.parent / "cfg"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("client_markers", json.loads(r.stdout))
        self.assertTrue((self.root / ".whynot-client").is_file())
        self.assertEqual(json.loads(self.lock.read_text(encoding="utf-8"))["session_id"], "other-session")

    def test_g5_a_writing_command_marks_a_2x_client(self):
        """Gate G5: a 2.x client (assets/ + data/ + output/, no marker) gets `.whynot-client` on its first writing
        command, with a log line; a reader never writes it."""
        (self.root / ".whynot-client").unlink()
        prefs = Path(self.tmp.name) / "prefs"
        self.reel("settings", "--init", str(prefs))                     # a writer, but output/ has no WhyNot sign yet
        self.assertFalse((self.root / ".whynot-client").exists())
        (self.root / "output/logs").mkdir(parents=True)
        (self.root / "output/logs/pipeline.log").write_text("[2.x] discover\n", encoding="utf-8")
        self.assertEqual(self.reel("next", "--video-id", "C0001").returncode, 0)
        self.assertFalse((self.root / ".whynot-client").exists())
        r = self.reel("discover")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.root / ".whynot-client").is_file())
        self.assertIn(".whynot-client", self.log_text())
        bare = Path(self.tmp.name) / "no output"                        # no output/: not a 2.x client folder
        for d in ("assets", "data"):
            (bare / d).mkdir(parents=True)
        subprocess.run([sys.executable, str(CLI), "--root", str(bare), "settings", "--init", str(bare)],
                       capture_output=True, text=True, encoding="utf-8", env=env_for())
        self.assertFalse((bare / ".whynot-client").exists())


class TestLockStatusTimes(LockFixture):
    def test_status_shows_age_idle_and_how(self):
        self.hold(age_s=30 * 60)
        st = json.loads(self.reel("lock", "--status").stdout)
        self.assertIn("age_min", st)
        self.assertGreaterEqual(st["idle_min"], 29)
        self.assertLessEqual(st["idle_min"], 31)
        self.assertIn("ends when the holding session closes or after 2 h idle", st["how"])
        self.assertIn("reel lock --release", st["how"])
        self.assertIn("editor's word", st["how"])
        rec = json.loads(self.lock.read_text(encoding="utf-8"))
        rec["started_at"] = writer_lock.now_iso()
        self.lock.write_text(json.dumps(rec), encoding="utf-8")
        self.assertLessEqual(json.loads(self.reel("lock", "--status").stdout)["age_min"], 1)
        self.lock.unlink()
        st = json.loads(self.reel("lock", "--status").stdout)
        self.assertIsNone(st["age_min"])
        self.assertIsNone(st["idle_min"])


class TestLockCommand(LockFixture):
    def test_status(self):
        r = self.reel("lock", "--status")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(json.loads(r.stdout)["held"])
        self.hold()
        st = json.loads(self.reel("lock", "--status").stdout)
        self.assertTrue(st["held"])
        self.assertFalse(st["mine"])
        self.assertIsNone(st["stale"])
        self.assertEqual(st["holder"]["command"], "reel transcribe --video-id C0001")
        self.hold(pid=dead_pid())
        self.assertIn("no longer running", json.loads(self.reel("lock", "--status").stdout)["stale"])
        self.assertTrue(self.lock.exists(), "--status changes nothing")

    def test_release(self):
        self.hold()
        r = self.reel("lock", "--release")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["released"])
        self.assertFalse(self.lock.exists())
        self.assertIn("released", self.log_text())
        self.assertFalse(json.loads(self.reel("lock", "--release").stdout)["released"])


class TestGuardAndSessionStart(LockFixture):
    def guard(self, cmd, agent=None):
        p = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(self.root)}
        if agent:
            p["agent_type"] = agent
        r = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(p), capture_output=True, text=True,
                           encoding="utf-8", env=env_for())
        return r.returncode

    def test_subagents_cannot_release(self):
        for c in ("reel lock --release", "env FOO=1 reel lock --release", "timeout 60 reel lock --release",
                  f'reel --root "{self.root}" lock --release', "nohup reel lock --release"):
            self.assertEqual(self.guard(c, "whynot-cut:premiere-builder"), 2, c)
            self.assertEqual(self.guard(c, "other-plugin:helper"), 2, c)
            self.assertEqual(self.guard(c), 0, c)                         # the lead may
        self.assertEqual(self.guard("reel lock --status", "whynot-cut:qc-reviewer"), 0)

    def test_subagents_cannot_delete_or_overwrite_the_lock(self):
        """M7: output/ is writable, so the lock file itself needs a role rule."""
        sub = "whynot-cut:premiere-builder"
        for c in ("rm output/.whynot-lock", "rm -f output/.whynot-lock", "echo {} > output/.whynot-lock",
                  "mv output/.whynot-lock /tmp/x", "python -c \"import os; os.remove('output/.whynot-lock')\""):
            self.assertEqual(self.guard(c, sub), 2, c)
            self.assertEqual(self.guard(c), 0, c)                          # the lead is not stopped here
        self.assertEqual(self.guard("cat output/.whynot-lock", sub), 0)
        p = {"tool_name": "PowerShell", "tool_input": {"command": "Remove-Item output\\.whynot-lock"},
             "cwd": str(self.root), "agent_type": sub}
        self.assertEqual(subprocess.run([sys.executable, str(GUARD)], input=json.dumps(p), capture_output=True,
                                        text=True, encoding="utf-8", env=env_for()).returncode, 2)
        for tool in ("Write", "Edit"):
            p = {"tool_name": tool, "tool_input": {"file_path": str(self.lock)}, "cwd": str(self.root),
                 "agent_type": sub}
            self.assertEqual(subprocess.run([sys.executable, str(GUARD)], input=json.dumps(p), capture_output=True,
                                            text=True, encoding="utf-8", env=env_for()).returncode, 2, tool)

    def guard_tool(self, tool, text, agent="whynot-cut:premiere-builder"):
        key = "command" if tool in ("Bash", "PowerShell") else "file_path"
        p = {"tool_name": tool, "tool_input": {key: text}, "cwd": str(self.root), "agent_type": agent}
        r = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(p), capture_output=True, text=True,
                           encoding="utf-8", env=env_for())
        return r.returncode, r.stderr

    def test_lock_rule_reads_stay_open_and_globs_count(self):
        """T11 (T1.8 M7 follow-up): reads of the lock (Read tool, stderr redirects, a 2-letter word that is not the
        command) are allowed; find -delete and a glob that matches the lock are not."""
        self.assertEqual(self.guard_tool("Read", str(self.lock))[0], 0)
        for tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            self.assertEqual(self.guard_tool(tool, str(self.lock))[0], 2, tool)
        for c in ("cat output/.whynot-lock 2>/dev/null", "cat output/.whynot-lock 2>&1 | head -5",
                  "ls -la output/.whynot-lock >&2", "grep -c py output/.whynot-lock", "cat output/.whynot-lock | grep sh",
                  "find output -name .whynot-lock", "reel lock --status 2> output/err.txt # .whynot-lock"):
            self.assertEqual(self.guard_tool("Bash", c), (0, ""), c)
        for c in ("Get-Content output/.whynot-lock 2>$null", "Get-Item output/.whynot-lock | Select-Object Name, sc"):
            self.assertEqual(self.guard_tool("PowerShell", c)[0], 0, c)
        for c in ("find output -name .whynot-lock -delete", "rm output/.whynot-l*", "rm -f output/.whynot-?ock",
                  "cat x 2> output/.whynot-lock", "echo hi; py -c 1 output/.whynot-lock"):
            self.assertEqual(self.guard_tool("Bash", c)[0], 2, c)
        for c in ("sc output/.whynot-lock '{}'", "echo 1; ni output/.whynot-lock -Force", "Remove-Item output/.whynot-*"):
            self.assertEqual(self.guard_tool("PowerShell", c)[0], 2, c)
        msg = self.guard_tool("Bash", "rm output/.whynot-lock")[1]
        self.assertIn("may not change, move or delete", msg)
        self.assertIn("reading it is fine", msg)

    def context(self, session):
        p = {"cwd": str(self.root), "session_id": session, "hook_event_name": "SessionStart"}
        r = subprocess.run([sys.executable, str(CTX)], input=json.dumps(p), capture_output=True, text=True,
                           encoding="utf-8", env=env_for(None))
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_session_start_warns_about_another_writer(self):
        self.assertNotIn("another session", self.context("me-session"))
        self.hold(command="reel transcribe --video-id C0239")
        ctx = self.context("me-session")
        self.assertIn("another session is working in this client (reel transcribe --video-id C0239, since "
                      "2026-10-11T10:00:00+03:00)", ctx)
        self.assertNotIn("another session", self.context("other-session"))     # its own lock
        self.hold(pid=dead_pid())
        self.assertNotIn("another session", self.context("me-session"))         # stale: no warning


if __name__ == "__main__":
    unittest.main()
