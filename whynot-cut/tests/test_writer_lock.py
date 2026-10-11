"""3.0 T1.8 one writer per client folder: output/.whynot-lock, `reel lock`, the guard rule and the SessionStart warning.
Two Claude sessions worked on one client folder at the same time in the field (chats-other: "Two sessions on one
client folder, no lock"); writing commands now hold a per-client lock for their duration.
Run:  ~/.whynot-cut/venv/Scripts/python.exe -B -m unittest discover -s whynot-cut/tests -p test_writer_lock.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
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

CLI = SK / "engine/reel/cli.py"
GUARD = SK / "hooks" / "guard.py"
CTX = SK / "hooks" / "session_context.py"
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
        return subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args], capture_output=True,
                              text=True, encoding="utf-8", env=env_for(session, **extra))

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
        self.assertTrue(cli.writes(ns(cmd="doctor", fix=True)))
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
        self.assertEqual(json.loads(self.lock.read_text(encoding="utf-8")), rec, "a re-entrant command took the lock")

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
