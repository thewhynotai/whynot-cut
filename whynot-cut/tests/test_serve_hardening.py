"""`reel serve` final review wave (3.0 T6.2 Task 5): result flooding, stale-daemon restart on a plugin update,
protocol-mismatch hello, user-only files and folders, cancel on requester disconnect, progress relay that a slow
requester cannot stall, and the discovery record at ~/.whynot-cut/bridge/engine.json for the UXP panel.
Run:
    bash tools/test.sh -p test_serve_hardening.py
App tests run a real in-process server on 127.0.0.1 (test_serve_app.AppCase); daemon tests run daemon.run() on a
background thread with temp engine homes (and a temp user home where the discovery record is concerned). Everything
is stopped in cleanup.
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import asyncio
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import plat  # noqa: E402
from serve import app as serve_app, daemon, security  # noqa: E402
from test_serve_app import PING_READBACK, AppCase, command  # noqa: E402
from test_serve_daemon import WIN, InProcessDaemon, _dacl, _Home, _whoami_sid  # noqa: E402

T = 10.0


def ping_result(rid):
    return {"type": "result", "result": {"ok": True, "action": "ping", "id": rid, "readback": PING_READBACK}}


async def drain(c, quiet: float = 0.5) -> list:
    """Every message the server sends until it has been silent for `quiet` seconds."""
    got = []
    while True:
        try:
            m = await asyncio.wait_for(c.recv(), quiet)
        except TimeoutError:
            return got
        if m is None:
            return got
        got.append(m)


# ------------------------------------------------------------------------------------------- I1 result flooding
class ResultFlood(AppCase):
    app_options = {"rate": (1.0, 5)}

    async def test_unmatched_results_are_rate_limited_and_audited_once(self):
        p = await self.panel(caps=("ping",))
        for i in range(15):
            await p.send(ping_result(f"nobody-{i}"))
        got = await drain(p)
        rate = [m for m in got if m["type"] == "error" and m["code"] == "rate"]
        self.assertGreaterEqual(len(rate), 5, got)                     # ~10 over a burst of 5 at 1/s
        late = self.events("late-result")
        self.assertEqual(len(late), 1, late)                           # the first only: no audit-trail flood

    async def test_a_pending_result_is_never_limited(self):
        p = await self.panel(caps=("ping",))
        c = await self.cli()
        msg = command("ping")
        rid = msg["request"]["id"]
        await c.send(msg)
        self.assertEqual((await p.recv())["type"], "command")
        for i in range(15):                                            # exhaust the panel's budget
            await p.send(ping_result(f"nobody-{i}"))
        await p.send(ping_result(rid))
        res = await asyncio.wait_for(c.recv(), T)
        self.assertEqual((res["type"], res["result"]["ok"], res["result"]["id"]), ("result", True, rid), res)


# -------------------------------------------------------------------------------------------- M3 protocol hello
class ProtocolHello(AppCase):
    async def test_wrong_protocol_is_a_schema_error_not_a_wrong_token(self):
        c = await self.connect()
        await c.send({"type": "hello", "token": self.token,
                      "client": {"kind": "uxp", "version": "2.0.0", "protocol": 3, "capabilities": []}})
        err = await c.recv()
        self.assertEqual((err["type"], err["code"], err["message"]), ("error", "schema", "protocol 4 required"), err)
        self.assertIsNone(await c.recv())
        rows = self.events("auth")
        self.assertTrue(any(r["outcome"] == "rejected" and "protocol" in r["reason"] for r in rows), rows)
        self.assertFalse(any(r.get("reason") == "wrong token" for r in rows))

    async def test_right_protocol_still_gets_welcome(self):
        c = await self.cli()
        self.assertFalse(c.r.at_eof())


# ------------------------------------------------------------------------------------ M4 cancel on disconnect
class CancelOnDisconnect(AppCase):
    async def test_requester_disconnect_sends_cancel_to_the_panel(self):
        p = await self.panel(caps=("ping",))
        c = await self.cli()
        msg = command("ping")
        rid = msg["request"]["id"]
        await c.send(msg)
        self.assertEqual((await p.recv())["type"], "command")
        await c.aclose()
        m = await asyncio.wait_for(p.recv(), T)
        self.assertEqual(m, {"type": "cancel", "id": rid})


# ---------------------------------------------------------------------------------- M5 progress relay bounded
class SlowRequester(AppCase):
    app_options = {"rate": (50.0, 200)}

    async def test_a_requester_that_stops_reading_never_delays_the_panel(self):
        p = await self.panel(caps=("ping",))
        a = await self.cli()
        sa = list(self.app.sessions.values())[-1]
        gate = asyncio.Event()

        async def stuck(msg):                         # requester A never drains anything again
            await gate.wait()
            return False
        sa.send = stuck
        b = await self.cli()
        ma, mb = command("ping"), command("ping")
        await a.send(ma)
        await b.send(mb)
        ids = {(await p.recv())["request"]["id"] for _ in range(2)}
        self.assertEqual(ids, {ma["request"]["id"], mb["request"]["id"]})
        ra = ma["request"]["id"]
        for i in range(100):
            await p.send({"type": "progress", "progress": {"event": "progress", "id": ra, "action": "ping",
                                                            "step": f"s{i}", "n": i, "of": 100}})
        await p.send(ping_result(mb["request"]["id"]))
        res = await asyncio.wait_for(b.recv(), 3.0)
        self.assertEqual((res["type"], res["result"]["id"]), ("result", mb["request"]["id"]))
        gate.set()


# --------------------------------------------------------------------------------- I2 restart a stale daemon
class EnsureRestarts(_Home):
    def _spawn_new(self, started):
        def fake_spawn(home):
            started.append(InProcessDaemon(home).start(self))          # version 3.0.0-test
            return types.SimpleNamespace(pid=os.getpid(), poll=lambda: None)
        return fake_spawn

    def test_an_older_daemon_is_stopped_and_replaced(self):
        old = self.start_daemon(version="2.9.9-old")
        started = []
        with mock.patch.object(daemon, "_version", return_value="3.0.0-test"), \
                mock.patch.object(daemon, "_spawn", self._spawn_new(started)):
            res = daemon.ensure(self.home, wait=T)
        self.assertEqual((res["ok"], res["state"], res["started"]), (True, "restarted", True), res)
        self.assertEqual((res["version"], res["previous_version"]), ("3.0.0-test", "2.9.9-old"))
        old.thread.join(T)
        self.assertFalse(old.thread.is_alive())
        self.assertEqual(len(started), 1)
        self.assertEqual(security.read_engine_json(self.home)["version"], "3.0.0-test")

    def test_the_same_version_is_kept(self):
        self.start_daemon()
        with mock.patch.object(daemon, "_version", return_value="3.0.0-test"), \
                mock.patch.object(daemon, "_spawn", side_effect=AssertionError("must not spawn")):
            res = daemon.ensure(self.home)
        self.assertEqual((res["state"], res["started"]), ("running", False))

    def test_another_protocol_is_restarted_too(self):
        real = serve_app.App.status

        def status(app):
            d = real(app)
            return {**d, "protocol": 3} if app.version == "proto-3" else d

        with mock.patch.object(serve_app.App, "status", status):
            self.start_daemon(version="proto-3")
            started = []
            with mock.patch.object(daemon, "_version", return_value="proto-3"), \
                    mock.patch.object(daemon, "_spawn", self._spawn_new(started)):
                res = daemon.ensure(self.home, wait=T)
        self.assertEqual(res["state"], "restarted", res)
        self.assertEqual(res["previous_protocol"], 3)

    def test_an_old_daemon_that_will_not_stop_is_reported_never_killed(self):
        self.start_daemon(version="2.9.9-old")
        refused = {"ok": False, "running": False, "state": "not_answering", "error": "x", "how": "y"}
        with mock.patch.object(daemon, "_version", return_value="3.0.0-test"), \
                mock.patch.object(daemon, "stop", return_value=refused) as stop, \
                mock.patch.object(daemon, "_spawn", side_effect=AssertionError("must not spawn")):
            res = daemon.ensure(self.home)
        stop.assert_called_once()
        self.assertEqual((res["ok"], res["state"]), (False, "not_answering"), res)
        self.assertIn("2.9.9-old", res["error"])
        self.assertTrue(res["how"])


# ------------------------------------------------------------------------------------- M2 user-only files
class PrivateFiles(_Home):
    def _run_daemon_and_spawn_log(self):
        class FakePopen:
            def __init__(self, cmd, **kw):
                self.pid = 4242
        with mock.patch.object(daemon, "_popen", FakePopen):
            daemon._spawn(self.home)
        daemon._children.clear()
        self.start_daemon()
        return [self.home / "bridge" / "serve.lock", security.audit_log_path(self.home),
                self.home / "logs" / "serve.log"]

    @unittest.skipIf(WIN, "POSIX mode bits")
    def test_posix_folders_0700_and_files_0600_even_when_they_existed(self):
        for d in ("bridge", "logs"):
            (self.home / d).mkdir(mode=0o755)
            os.chmod(self.home / d, 0o755)
        (self.home / "bridge" / "serve.lock").touch(mode=0o644)
        os.chmod(self.home / "bridge" / "serve.lock", 0o644)
        files = self._run_daemon_and_spawn_log()
        for d in ("bridge", "logs"):
            self.assertEqual(stat.S_IMODE(os.stat(self.home / d).st_mode), 0o700, d)
        for f in files:
            self.assertEqual(stat.S_IMODE(os.stat(f).st_mode), 0o600, f)

    @unittest.skipIf(WIN, "POSIX mode bits")
    def test_posix_audit_log_created_0600(self):
        a = security.AuditLog(self.home / "logs" / "serve-audit.log")
        a.log("x", outcome="ok")
        self.assertEqual(stat.S_IMODE(os.stat(a.path).st_mode), 0o600)

    @unittest.skipUnless(WIN, "Windows ACL")
    def test_windows_lock_logs_and_audit_are_user_only(self):
        sid = _whoami_sid()
        for f in self._run_daemon_and_spawn_log():
            aces = _dacl(f)
            self.assertEqual([(t, m, s) for t, _, m, s in aces], [(0, 0x1F01FF, sid)], (f, aces))
        for d in ("bridge", "logs"):
            self.assertEqual({s for *_, s in _dacl(self.home / d)}, {sid}, d)

    @unittest.skipUnless(WIN, "Windows ACL")
    def test_windows_rotated_audit_files_stay_user_only(self):
        security.private_dir(self.home / "logs")
        a = security.AuditLog(self.home / "logs" / "serve-audit.log", max_bytes=300, keep=2)
        for i in range(20):
            a.log("e%d" % i, outcome="ok", reason="y" * 60)
        sid = _whoami_sid()
        for f in sorted((self.home / "logs").iterdir()):
            self.assertEqual({s for *_, s in _dacl(f)}, {sid}, f)


# ------------------------------------------------------------------------------- 7 discovery for the UXP panel
class Discovery(_Home):
    def setUp(self):
        super().setUp()
        self.user = Path(tempfile.mkdtemp(prefix="wnc-user-"))
        self.addCleanup(shutil.rmtree, self.user, True)
        env = mock.patch.dict(os.environ, {"HOME": str(self.user), "USERPROFILE": str(self.user)})
        env.start()
        self.addCleanup(env.stop)
        self.default = self.user / plat.HOME_NAME

    def test_another_home_writes_a_discovery_record_and_removes_it(self):
        d = self.start_daemon()
        real = security.read_engine_json(self.home)
        disc = security.read_engine_json(self.default)
        self.assertIsNotNone(disc, "no ~/.whynot-cut/bridge/engine.json")
        self.assertEqual(disc["home"], str(self.home))
        for k in ("port", "token", "pid", "version", "protocol"):
            self.assertEqual(disc[k], real[k], k)
        if WIN:
            self.assertEqual([(t, f, m, s) for t, f, m, s in _dacl(security.engine_json_path(self.default))],
                             [(0, 0, 0x1F01FF, _whoami_sid())])
        else:
            self.assertEqual(stat.S_IMODE(os.stat(security.engine_json_path(self.default)).st_mode), 0o600)
        res = daemon.stop(self.home)
        self.assertEqual(res["state"], "stopped", res)
        d.thread.join(T)
        self.assertFalse(security.engine_json_path(self.default).exists())
        self.assertFalse(security.engine_json_path(self.home).exists())

    def test_the_default_home_writes_only_its_own_file(self):
        self.home = self.default
        self.start_daemon()
        info = security.read_engine_json(self.default)
        self.assertNotIn("home", info)
        self.assertEqual([p.name for p in (self.default / "bridge").glob("*.json")], ["engine.json"])
        daemon.stop(self.default)
        self.assertFalse(security.engine_json_path(self.default).exists())

    def test_a_live_daemons_file_at_the_default_home_is_never_touched(self):
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdin=subprocess.DEVNULL)
        self.addCleanup(other.wait, T)
        self.addCleanup(other.kill)
        security.write_engine_json(self.default, port=1, token=security.make_token(), pid=other.pid, version="other")
        before = security.engine_json_path(self.default).read_bytes()
        self.start_daemon()
        self.assertEqual(security.engine_json_path(self.default).read_bytes(), before)
        daemon.stop(self.home)
        self.assertEqual(security.engine_json_path(self.default).read_bytes(), before)

    def test_a_stale_file_at_the_default_home_is_replaced(self):
        from test_serve_daemon import dead_pid
        security.write_engine_json(self.default, port=1, token=security.make_token(), pid=dead_pid(), version="old")
        self.start_daemon()
        self.assertEqual(security.read_engine_json(self.default)["home"], str(self.home))
        daemon.stop(self.home)
        self.assertFalse(security.engine_json_path(self.default).exists())

    def test_stop_returns_only_after_the_discovery_pointer_is_gone(self):
        """Gate 3 race: stop() answered "stopped" while ~/.whynot-cut/bridge/engine.json still pointed at the stopped
        daemon (it removed its own record first and the pointer second; stop() polled only its own record). Made
        deterministic, not load-based: the daemon's removal of the pointer blocks until stop() has polled this home's
        record three times while it is blocked; the pointer must be gone when stop() says "stopped"."""
        d = self.start_daemon()
        self.assertIsNotNone(security.read_engine_json(self.default))
        real_remove, real_read = security.remove_engine_json, security.read_engine_json
        blocked, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        polls = []

        def remove(home, pid, **kw):
            if Path(home) == self.default and threading.current_thread() is d.thread:
                blocked.set()
                release.wait(T)
            return real_remove(home, pid, **kw)

        def read(home):
            if blocked.is_set() and not release.is_set() and Path(home) == self.home \
                    and threading.current_thread() is threading.main_thread():
                polls.append(1)
                if len(polls) >= 3:
                    release.set()
            return real_read(home)
        with mock.patch.object(security, "remove_engine_json", remove), \
                mock.patch.object(security, "read_engine_json", read):
            res = daemon.stop(self.home, wait=T)
            pointer_left = security.engine_json_path(self.default).exists()
        self.assertEqual(res["state"], "stopped", res)
        self.assertTrue(blocked.is_set(), "the daemon never removed its discovery record")
        self.assertFalse(pointer_left, f"stop() returned {res['state']!r} while the discovery record still existed "
                                       f"(polled {len(polls)}x while it was being removed)")
        d.thread.join(T)
        self.assertFalse(security.engine_json_path(self.default).exists())
        self.assertFalse(security.engine_json_path(self.home).exists())

    def _stop_as_another_process(self, d, *, stop_fails_too: bool, wait: float):
        """stop() of `d` as if it were a separate process (exited once its thread ends) while the pointer cannot be
        renamed away from the daemon's thread (every _replace_retry try exhausted: a sharing violation), and from
        stop() too when `stop_fails_too`."""
        pointer = security.engine_json_path(self.default)
        real_replace = security._replace_retry

        def replace(src, dst):
            if Path(src) == pointer and (stop_fails_too or threading.current_thread() is d.thread):
                raise PermissionError(32, "sharing violation (test)")
            return real_replace(src, dst)
        with mock.patch.object(security, "_replace_retry", replace), \
                mock.patch.object(daemon, "_in_process", lambda pid: False), \
                mock.patch.object(daemon, "_alive", lambda info: d.thread.is_alive()):
            return daemon.stop(self.home, wait=wait)

    def test_a_pointer_the_exited_daemon_could_not_remove_is_removed_by_stop(self):
        d = self.start_daemon()
        res = self._stop_as_another_process(d, stop_fails_too=False, wait=T)
        self.assertEqual((res["ok"], res["state"], res["exited"]), (True, "stopped", True), res)
        self.assertNotIn("discovery_left", res)
        self.assertFalse(security.engine_json_path(self.default).exists())
        self.assertFalse(security.engine_json_path(self.home).exists())
        rows = [r for r in self.audit() if r["event"] == "discovery" and r["outcome"] == "failed"]
        self.assertEqual(len(rows), 1, self.audit())

    def test_a_pointer_nobody_can_remove_is_reported_not_hidden(self):
        d = self.start_daemon()
        pid = security.read_engine_json(self.home)["pid"]
        res = self._stop_as_another_process(d, stop_fails_too=True, wait=0.5)
        self.assertEqual((res["ok"], res["state"], res.get("discovery_left")), (True, "stopped", True), res)
        self.assertIn("could not be removed", res["warning"])
        self.assertIn("reel serve --ensure", res["how"])
        self.assertEqual(security.read_engine_json(self.default)["pid"], pid)    # still there: reported, as it is
        self.assertFalse(security.engine_json_path(self.home).exists())

    def test_a_stale_record_takes_its_pointer_with_it_never_another_daemons(self):
        from test_serve_daemon import dead_pid
        pid = dead_pid()
        security.write_engine_json(self.home, port=1, token=security.make_token(), pid=pid, version="old",
                                   pid_created=111)
        security.write_engine_json(self.default, port=1, token=security.make_token(), pid=pid, version="old",
                                   pid_created=222, home=str(self.home))          # same pid, another process
        res = daemon.stop(self.home)
        self.assertEqual(res["state"], "stale_removed", res)
        self.assertFalse(security.engine_json_path(self.home).exists())
        self.assertEqual(security.read_engine_json(self.default)["pid_created"], 222)
        security.write_engine_json(self.home, port=1, token=security.make_token(), pid=pid, version="old",
                                   pid_created=222)
        self.assertEqual(daemon.stop(self.home)["state"], "stale_removed")
        self.assertFalse(security.engine_json_path(self.default).exists())
        self.assertFalse(security.engine_json_path(self.home).exists())


if __name__ == "__main__":
    unittest.main()
