"""`reel serve` lifecycle (3.0 T6.2 Task 5): serve/daemon.py run / ensure / status / stop, the instance lock, the
authenticated POST /shutdown, serve/cli.py, and the hardening carried from the Task 3-4 reviews (bounded App.close,
queue calls on their own daemon workers with the expiry re-checked after the wait, SID-based ACL, tombstone removal of
engine.json, bounded audit log when rotation fails).
Run:
    bash tools/test.sh -p test_serve_daemon.py
Daemons here run in-process on a background thread with a temp engine home (the real detached spawn is covered by
test_serve_security_e2e.py); every daemon, socket and thread is stopped in cleanup, even when a test fails.
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import asyncio
import contextlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from serve import adapters, cli as serve_cli, daemon, security  # noqa: E402
from test_serve_app import PING_READBACK, AppCase, cep_ok, command, http, request  # noqa: E402

T = 10.0
WIN = os.name == "nt"


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


def dead_pid() -> int:
    """The pid of a process that has exited (a short child, waited for)."""
    p = subprocess.Popen([sys.executable, "-c", "pass"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    p.wait(T)
    return p.pid


class InProcessDaemon:
    """daemon.run() on a background thread (its own event loop), stopped in cleanup whatever happens."""

    def __init__(self, home, **kw):
        self.home = home
        self.kw = {"version": "3.0.0-test", "install_signals": False, **kw}
        self.ready = threading.Event()
        self.stop_fn = None
        self.code = None
        self.thread = threading.Thread(target=self._main, name="test-reel-serve", daemon=True)

    def _main(self):
        def on_ready(stop):
            self.stop_fn = stop
            self.ready.set()
        self.code = daemon.run(self.home, ready=on_ready, **self.kw)
        self.ready.set()

    def start(self, case: unittest.TestCase):
        self.thread.start()
        case.addCleanup(self.kill)
        case.assertTrue(self.ready.wait(T), "the in-process daemon did not start")
        return self

    def kill(self):
        if self.stop_fn is not None and self.thread.is_alive():
            self.stop_fn()
        self.thread.join(T)
        if self.thread.is_alive():
            raise AssertionError("the in-process daemon did not stop")


class _Home(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="wnc-daemon-"))
        self.addCleanup(shutil.rmtree, self.home, True)

    def audit(self):
        p = security.audit_log_path(self.home)
        if not p.exists():
            return []
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]

    def start_daemon(self, **kw) -> InProcessDaemon:
        return InProcessDaemon(self.home, **kw).start(self)


# ------------------------------------------------------------------------------------------------- POST /shutdown
class Shutdown(AppCase):
    async def test_shutdown_needs_the_bearer_token(self):
        for auth in ("", "Authorization: Bearer nope\r\n", f"Authorization: Bearer {'0' * 64}\r\n",
                     f"Authorization: Basic {self.token}\r\n"):
            with self.subTest(auth=auth):
                status, _, body = await http(self.port, f"POST /shutdown HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                                                        f"Content-Length: 0\r\n{auth}\r\n".encode())
                self.assertEqual(status, 401)
                self.assertNotIn(self.token.encode(), body)
        self.assertFalse(self.app.stop_requested.is_set())
        rows = self.events("shutdown")
        self.assertTrue(rows and all(r["outcome"] == "rejected" for r in rows), rows)

    async def test_shutdown_is_post_only(self):
        status, headers, _ = await http(self.port, f"GET /shutdown HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                                                   f"Authorization: Bearer {self.token}\r\n\r\n".encode())
        self.assertEqual((status, headers.get("allow")), (405, "POST"))
        self.assertFalse(self.app.stop_requested.is_set())

    async def test_browser_origin_cannot_shut_down(self):
        status, _, _ = await http(self.port, f"POST /shutdown HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                                             f"Origin: https://evil.example\r\nAuthorization: Bearer {self.token}\r\n"
                                             f"Content-Length: 0\r\n\r\n".encode())
        self.assertEqual(status, 403)
        self.assertFalse(self.app.stop_requested.is_set())

    async def test_shutdown_with_token_is_accepted_and_audited(self):
        status, _, body = await http(self.port, f"POST /shutdown HTTP/1.1\r\nHost: localhost:{self.port}\r\n"
                                                f"Authorization: Bearer {self.token}\r\nContent-Length: 0\r\n\r\n".encode())
        self.assertEqual(status, 202)
        self.assertEqual(json.loads(body), {"ok": True, "stopping": True})
        self.assertTrue(self.app.stop_requested.is_set())
        self.assertTrue(any(r["outcome"] == "accepted" for r in self.events("shutdown")))
        self.assertNotIn(self.token, security.audit_log_path(self.home).read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------ App.close is bounded
class CloseBounded(AppCase):
    async def _silent_session(self):
        """Authenticated, then never reads or answers anything again (not even the close frame)."""
        return await self.cli()

    async def test_close_is_bounded_and_awaits_every_handler(self):
        for _ in range(3):
            await self._silent_session()
        r, w = await asyncio.open_connection("127.0.0.1", self.port)     # a connection that never sends its head
        self.addAsyncCleanup(self._drop, w)
        await asyncio.sleep(0.1)
        handlers = set(self.app._handlers)
        self.assertGreaterEqual(len(handlers), 4)
        t0 = time.monotonic()
        await self.app.close()
        took = time.monotonic() - t0
        self.assertLess(took, 2.5, f"close took {took:.2f}s")
        self.assertTrue(all(t.done() for t in handlers), [t for t in handlers if not t.done()])
        self.assertFalse(self.app._handlers)

    async def test_close_does_not_wait_for_a_stuck_queue_call(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        started = threading.Event()
        seen = {}

        def stuck_submit(action, data=None, timeout=600):
            seen["daemon"] = threading.current_thread().daemon
            started.set()
            gate.wait(60)
            return cep_ok("ping", PING_READBACK)

        c = await self.cli()
        with mock.patch("lib.ppro_bridge.submit", stuck_submit):
            await c.send(command("ping"))
            self.assertTrue(await asyncio.to_thread(started.wait, T))
            t0 = time.monotonic()
            await self.app.close()
            self.assertLess(time.monotonic() - t0, 2.5)
        self.assertTrue(seen["daemon"], "a queue worker must be a daemon thread (never blocks process exit)")

    @staticmethod
    async def _drop(w):
        w.close()
        with contextlib.suppress(ConnectionError, OSError):
            await w.wait_closed()


# --------------------------------------------------------------------------------------------- FileQueueAdapter
class QueueWorkers(unittest.IsolatedAsyncioTestCase):
    async def _hold_lock(self, seconds: float):
        lock = adapters.SUBMIT_LOCKS["premiere"]
        lock.acquire()
        threading.Timer(seconds, lock.release).start()

    async def test_expiry_is_rechecked_after_waiting_for_the_queue(self):
        await self._hold_lock(1.5)
        with mock.patch("lib.ppro_bridge.submit", return_value=cep_ok("ping", PING_READBACK)) as sub:
            res = await adapters.FileQueueAdapter().run(request("ping", id="q1", expires_in=1.0))
        sub.assert_not_called()
        self.assertEqual((res["ok"], res["id"], res["action"]), (False, "q1", "ping"))
        self.assertIn("expired", res["error"])
        self.assertTrue(res.get("how"))

    async def test_timeout_is_recomputed_after_the_wait(self):
        await self._hold_lock(1.5)
        with mock.patch("lib.ppro_bridge.submit", return_value=cep_ok("ping", PING_READBACK)) as sub:
            res = await adapters.FileQueueAdapter().run(request("ping", id="q2", expires_in=30))
        self.assertTrue(res["ok"], res)
        self.assertLessEqual(sub.call_args.kwargs["timeout"], 28.6)

    async def test_queue_calls_use_their_own_daemon_workers_not_the_default_executor(self):
        seen = []

        def fake_submit(action, data=None, timeout=600):
            t = threading.current_thread()
            seen.append((t.daemon, t.name))
            return cep_ok("ping", PING_READBACK)

        async def no_default_executor(*a, **k):
            raise AssertionError("queue calls must not use the default executor")

        with mock.patch("lib.ppro_bridge.submit", fake_submit), \
                mock.patch.object(adapters.asyncio, "to_thread", no_default_executor):
            res = await adapters.FileQueueAdapter().run(request("ping", id="q3"))
        self.assertTrue(res["ok"], res)
        self.assertTrue(seen[0][0])
        self.assertTrue(seen[0][1].startswith("reel-serve-queue"), seen)

    async def test_premiere_and_after_effects_queues_do_not_starve_each_other(self):
        gate = threading.Event()
        self.addCleanup(gate.set)

        def stuck(action, data=None, timeout=600):
            gate.wait(30)
            return cep_ok("ping", PING_READBACK)

        with mock.patch("lib.ppro_bridge.submit", stuck), \
                mock.patch("lib.ae_bridge.submit", return_value=cep_ok("probe_text", {"x": 1})):
            ppro = [asyncio.create_task(adapters.FileQueueAdapter().run(request("ping", id=f"p{i}")))
                    for i in range(6)]
            res = await asyncio.wait_for(adapters.FileQueueAdapter().run(request("ae_probe_text", id="ae1")), T)
            self.assertTrue(res["ok"], res)
            gate.set()
            done = await asyncio.wait_for(asyncio.gather(*ppro), T)
        self.assertTrue(all(r["ok"] for r in done))


# ------------------------------------------------------------------------------------------------- daemon.run
class Run(_Home):
    def test_run_writes_engine_json_and_cleans_up_on_stop(self):
        d = self.start_daemon()
        info = security.read_engine_json(self.home)
        self.assertTrue(security.token_shape_ok(info["token"]))
        self.assertEqual((info["pid"], info["version"], info["protocol"]), (os.getpid(), "3.0.0-test", 4))
        self.assertIsInstance(datetime.fromisoformat(info["started_at"]), datetime)
        self.assertIn("pid_created", info)
        self.assertTrue(port_open(info["port"]))
        st = daemon.status(self.home)
        self.assertEqual((st["ok"], st["running"], st["state"], st["pid"], st["port"]),
                         (True, True, "running", os.getpid(), info["port"]))
        self.assertNotIn(info["token"], json.dumps(st))
        res = daemon.stop(self.home)
        self.assertEqual((res["ok"], res["state"]), (True, "stopped"), res)
        self.assertNotIn(info["token"], json.dumps(res))
        d.thread.join(T)
        self.assertFalse(d.thread.is_alive())
        self.assertEqual(d.code, 0)
        self.assertFalse(security.engine_json_path(self.home).exists())
        self.assertFalse(port_open(info["port"]))
        rows = [r for r in self.audit() if r["event"] == "daemon"]
        self.assertEqual([r["outcome"] for r in rows], ["started", "stopped"], rows)
        text = security.audit_log_path(self.home).read_text(encoding="utf-8")
        self.assertNotIn(info["token"], text)

    def test_strict_context_while_running(self):
        self.start_daemon()
        with self.assertRaises(RuntimeError):
            common.current_context()
        daemon.stop(self.home)
        self.assertIsInstance(common.current_context(), common.Context)

    def test_a_second_daemon_on_the_same_home_refuses_and_leaves_the_file(self):
        self.start_daemon()
        before = security.read_engine_json(self.home)
        code = daemon.run(self.home, version="3.0.0-test", install_signals=False)
        self.assertEqual(code, daemon.EXIT_LOCKED)
        self.assertEqual(security.read_engine_json(self.home), before)
        self.assertTrue(any(r["event"] == "daemon" and r["outcome"] == "refused" for r in self.audit()))

    def test_clean_exit_never_removes_a_newer_daemons_file(self):
        d = self.start_daemon()
        info = security.read_engine_json(self.home)
        security.write_engine_json(self.home, port=info["port"], token=security.make_token(), pid=999999,
                                   version="newer")
        d.kill()
        self.assertEqual(security.read_engine_json(self.home)["pid"], 999999)

    def test_defaults(self):
        self.assertEqual(daemon.PROBE_TIMEOUT, 0.3)
        self.assertEqual(daemon.ENSURE_WAIT, 1.0)


# ---------------------------------------------------------------------------------------------- ensure / status
class Ensure(_Home):
    def test_ensure_returns_the_running_daemon_and_never_spawns_a_second(self):
        self.start_daemon()
        with mock.patch.object(daemon, "_spawn", side_effect=AssertionError("must not spawn")):
            a = daemon.ensure(self.home)
            b = daemon.ensure(self.home)
        self.assertEqual((a["ok"], a["state"], a["started"]), (True, "running", False), a)
        self.assertEqual(a["pid"], b["pid"])
        self.assertEqual(a["port"], b["port"])
        self.assertNotIn("token", a)

    def test_ensure_replaces_a_stale_file(self):
        security.write_engine_json(self.home, port=9, token=security.make_token(), pid=dead_pid(), version="old")
        started = []

        def fake_spawn(home):
            started.append(InProcessDaemon(home).start(self))
            return types.SimpleNamespace(pid=os.getpid(), poll=lambda: None)

        with mock.patch.object(daemon, "_spawn", fake_spawn):
            res = daemon.ensure(self.home, wait=T)
        self.assertEqual((res["ok"], res["state"], res["started"]), (True, "running", True), res)
        self.assertEqual(len(started), 1)
        self.assertEqual(security.read_engine_json(self.home)["version"], "3.0.0-test")

    def test_ensure_reports_a_child_that_exits(self):
        with mock.patch.object(daemon, "_spawn", return_value=types.SimpleNamespace(pid=1, poll=lambda: 3)):
            res = daemon.ensure(self.home, wait=1.0)
        self.assertFalse(res["ok"], res)
        self.assertTrue(res["error"] and res["how"])

    def test_ensure_says_starting_when_the_wait_is_over(self):
        with mock.patch.object(daemon, "_spawn", return_value=types.SimpleNamespace(pid=4242, poll=lambda: None)):
            t0 = time.monotonic()
            res = daemon.ensure(self.home, wait=0.3)
        self.assertLess(time.monotonic() - t0, 2.0)
        self.assertEqual((res["ok"], res["state"]), (True, "starting"), res)

    def test_status_without_a_daemon(self):
        self.assertEqual(daemon.status(self.home), {"ok": True, "running": False, "state": "stopped"})

    def test_status_of_a_stale_file_is_read_only(self):
        security.write_engine_json(self.home, port=9, token=security.make_token(), pid=dead_pid(), version="old")
        st = daemon.status(self.home)
        self.assertEqual((st["running"], st["state"]), (False, "stale"))
        self.assertTrue(security.engine_json_path(self.home).exists())

    def test_stop_without_a_daemon_and_with_a_stale_file(self):
        self.assertEqual(daemon.stop(self.home)["state"], "not_running")
        security.write_engine_json(self.home, port=9, token=security.make_token(), pid=dead_pid(), version="old")
        res = daemon.stop(self.home)
        self.assertEqual((res["ok"], res["state"]), (True, "stale_removed"), res)
        self.assertFalse(security.engine_json_path(self.home).exists())

    def test_stop_of_a_daemon_that_does_not_answer(self):
        with socket.socket() as s:                     # a port nothing listens on
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        security.write_engine_json(self.home, port=port, token=security.make_token(), pid=os.getpid(), version="v")
        res = daemon.stop(self.home)
        self.assertFalse(res["ok"], res)
        self.assertEqual(res["state"], "not_answering")
        self.assertTrue(res["how"])


class Spawn(_Home):
    def test_spawn_command_flags_and_environment(self):
        captured = {}

        class FakePopen:
            def __init__(self, cmd, **kw):
                captured["cmd"], captured["kw"] = cmd, kw
                self.pid = 4242

        with mock.patch.object(daemon.subprocess, "Popen", FakePopen):
            daemon._spawn(self.home)
        cmd, kw = captured["cmd"], captured["kw"]
        self.assertEqual(cmd[0], sys.executable)
        main = str(SK / "engine" / "reel" / "serve" / "__main__.py")
        self.assertEqual(cmd[-4:], [main, "--foreground", "--home", str(self.home)])
        self.assertIn("-P", cmd)                           # the engine home (cwd) is never on sys.path
        self.assertEqual(Path(kw["cwd"]), self.home)        # never the plugin folder (it is replaced on update)
        self.assertEqual(kw["env"]["WHYNOT_HOME"], str(self.home))
        self.assertEqual(kw["stdin"], subprocess.DEVNULL)
        if WIN:
            want = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            self.assertEqual(kw["creationflags"] & want, want)
        else:
            self.assertTrue(kw["start_new_session"])
        self.assertIn(4242, [p.pid for p in daemon._children])
        daemon._children.clear()


# --------------------------------------------------------------------------------------------------- serve.cli
class Cli(_Home):
    def run_cli(self, *args) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = serve_cli.main([*args, "--home", str(self.home)])
        return code, buf.getvalue()

    def test_build_parser_registers_serve(self):
        import argparse
        ap = argparse.ArgumentParser()
        sub = ap.add_subparsers(dest="cmd")
        serve_cli.build_parser(sub)
        a = ap.parse_args(["serve", "--ensure"])
        self.assertEqual((a.cmd, a.ensure, a.stop, a.status, a.foreground), ("serve", True, False, False, False))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ap.parse_args(["serve", "--ensure", "--stop"])

    def test_status_prints_one_json_document(self):
        code, out = self.run_cli("--status")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["state"], "stopped")

    def test_quiet_prints_nothing(self):
        code, out = self.run_cli("--status", "--quiet")
        self.assertEqual((code, out), (0, ""))

    def test_cmd_serve_takes_the_reel_cli_namespace(self):
        import argparse
        a = argparse.Namespace(cmd="serve", ensure=False, status=True, stop=False, foreground=False, quiet=False,
                               wait=1.0, home=str(self.home), root=None)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            serve_cli.cmd_serve(a)
        self.assertEqual(json.loads(buf.getvalue())["running"], False)

    def test_stop_and_status_against_a_running_daemon(self):
        self.start_daemon()
        code, out = self.run_cli("--status")
        self.assertEqual((code, json.loads(out)["state"]), (0, "running"))
        code, out = self.run_cli("--stop")
        self.assertEqual((code, json.loads(out)["state"]), (0, "stopped"))


# ------------------------------------------------------------------------------------------- carried: security
def _whoami_sid() -> str:
    r = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, timeout=30)
    return r.stdout.decode("utf-8", "replace").strip().split(",")[-1].strip().strip('"')


def _dacl(path):
    """[(ace type, ace flags, access mask, SID string)] of `path`'s DACL, read with the Win32 API."""
    import ctypes
    from ctypes import wintypes
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    vp = ctypes.c_void_p
    adv.GetNamedSecurityInfoW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, wintypes.DWORD, vp, vp,
                                          ctypes.POINTER(vp), vp, ctypes.POINTER(vp)]
    adv.GetNamedSecurityInfoW.restype = wintypes.DWORD
    adv.GetAce.argtypes = [vp, wintypes.DWORD, ctypes.POINTER(vp)]
    adv.ConvertSidToStringSidW.argtypes = [vp, ctypes.POINTER(vp)]
    k32.LocalFree.argtypes = [vp]
    k32.LocalFree.restype = vp
    dacl, sd = vp(), vp()
    rc = adv.GetNamedSecurityInfoW(str(path), 1, 4, None, None, ctypes.byref(dacl), None, ctypes.byref(sd))
    assert rc == 0, rc
    try:
        out = []
        for i in range(ctypes.c_uint16.from_address(dacl.value + 4).value):
            ace = vp()
            assert adv.GetAce(dacl, i, ctypes.byref(ace))
            s = vp()
            assert adv.ConvertSidToStringSidW(ace.value + 8, ctypes.byref(s))
            out.append((ctypes.c_ubyte.from_address(ace.value).value, ctypes.c_ubyte.from_address(ace.value + 1).value,
                        ctypes.c_uint32.from_address(ace.value + 4).value, ctypes.wstring_at(s.value)))
            k32.LocalFree(s)
        return out
    finally:
        k32.LocalFree(sd)


class SidAcl(_Home):
    @unittest.skipUnless(WIN, "Windows ACL")
    def test_current_user_sid_matches_whoami(self):
        self.assertEqual(security.current_user_sid(), _whoami_sid())
        self.assertRegex(security.current_user_sid(), r"^S-1-\d+(-\d+)+$")

    @unittest.skipUnless(WIN, "Windows ACL")
    def test_engine_json_acl_lists_exactly_the_process_sid(self):
        p = security.write_engine_json(self.home, port=1, token="a" * 64, pid=1, version="v")
        self.assertEqual(_dacl(p), [(0, 0, 0x1F01FF, _whoami_sid())])   # allow, not inherited, full control

    @unittest.skipUnless(WIN, "Windows ACL")
    def test_icacls_grants_the_sid_not_the_user_name(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, b"", b"")

        f = self.home / "f.txt"
        f.write_bytes(b"")
        with mock.patch.object(security.subprocess, "run", fake_run), \
                mock.patch.dict(os.environ, {"USERNAME": "mallory", "USERDOMAIN": "EVIL"}):
            security.restrict_to_user(f)
        self.assertEqual(calls[0][1:], [str(f), "/inheritance:r", "/grant:r", f"*{_whoami_sid()}:F"])
        self.assertNotIn("mallory", " ".join(calls[0]))

    @unittest.skipUnless(WIN, "Windows ACL")
    def test_no_sid_fails_closed(self):
        f = self.home / "f.txt"
        f.write_bytes(b"")
        with mock.patch.object(security, "current_user_sid", side_effect=OSError("no sid")):
            with self.assertRaises(OSError):
                security.restrict_to_user(f)


class TombstoneRemove(_Home):
    def _write(self, pid):
        return security.write_engine_json(self.home, port=1, token=security.make_token(), pid=pid, version="v")

    def _swap_after_first_parse(self, new_pid):
        """security.json whose first loads() writes a NEW engine.json (pid `new_pid`) right after the parse: the
        moment between the pid check and the delete."""
        real = json
        state = {"done": False}

        def loads(s, *a, **k):
            out = real.loads(s, *a, **k)
            if not state["done"]:
                state["done"] = True
                p = security.engine_json_path(self.home)
                p.write_text(real.dumps({"port": 2, "token": "b" * 64, "pid": new_pid, "version": "new",
                                         "protocol": 4}), encoding="utf-8")
            return out
        return mock.patch.object(security, "json", types.SimpleNamespace(loads=loads, dumps=real.dumps))

    def test_a_file_replaced_after_the_check_is_never_deleted(self):
        self._write(77)
        with self._swap_after_first_parse(88):
            removed = security.remove_engine_json(self.home, 77)
        self.assertTrue(removed)                                  # ours (pid 77) went
        self.assertEqual(security.read_engine_json(self.home)["pid"], 88)   # the newer one stayed

    def test_another_pid_is_restored_untouched(self):
        p = self._write(77)
        before = p.read_bytes()
        self.assertFalse(security.remove_engine_json(self.home, 78))
        self.assertEqual(p.read_bytes(), before)
        self.assertEqual(sorted(x.name for x in p.parent.iterdir()), ["engine.json"])    # no tombstone left

    def test_restore_never_overwrites_a_newer_file(self):
        self._write(77)
        with self._swap_after_first_parse(99):
            self.assertFalse(security.remove_engine_json(self.home, 78))
        self.assertEqual(security.read_engine_json(self.home)["pid"], 99)
        self.assertEqual(sorted(x.name for x in security.engine_json_path(self.home).parent.iterdir()),
                         ["engine.json"])

    @unittest.skipUnless(WIN, "Windows ACL")
    def test_restored_file_keeps_its_acl(self):
        p = self._write(77)
        self.assertFalse(security.remove_engine_json(self.home, 78))
        self.assertEqual(_dacl(p), [(0, 0, 0x1F01FF, _whoami_sid())])

    def test_missing_file(self):
        self.assertFalse(security.remove_engine_json(self.home, 1))

    def test_a_reader_holding_the_file_briefly_does_not_stop_the_removal(self):
        """Windows: a reader with engine.json open at that instant makes the rename fail (sharing violation)."""
        self._write(77)
        real, calls = os.replace, []

        def flaky(src, dst):
            calls.append(1)
            if len(calls) <= 2:
                raise PermissionError(32, "being used by another process")
            return real(src, dst)

        with mock.patch.object(security.os, "replace", flaky):
            self.assertTrue(security.remove_engine_json(self.home, 77))
        self.assertFalse(security.engine_json_path(self.home).exists())
        self.assertEqual(len(calls), 3)


class AuditBounded(_Home):
    def test_failed_rotation_never_grows_the_log_without_bound(self):
        a = security.AuditLog(security.audit_log_path(self.home), max_bytes=800, keep=2)
        with mock.patch.object(security.AuditLog, "_rotate", lambda self: None):     # rotation silently fails
            for i in range(200):
                a.log("e%d" % i, peer="p", outcome="ok", reason="y" * 40)
        size = a.path.stat().st_size
        self.assertLessEqual(size, 800 + 400, size)
        rows = [json.loads(x) for x in a.path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows[-1]["event"], "e199")
        self.assertTrue(any(r["event"] == "audit" and r["outcome"] == "truncated" for r in rows), rows[:2])


if __name__ == "__main__":
    unittest.main()
