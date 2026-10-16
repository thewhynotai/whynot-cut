"""`reel serve` end-to-end security suite (3.0 T6.2 Task 5): a REAL daemon process, started the way the SessionStart
hook starts it (serve.daemon.ensure -> a detached `python -B -P serve/__main__.py --foreground --home <temp home>`), is
attacked over real loopback sockets. Every refusal must be (1) answered as a refusal and (2) on record in the audit log
`<home>/logs/serve-audit.log`, which must never hold the token.
Run:
    bash tools/test.sh -p test_serve_security_e2e.py
Each class starts its own daemon on its own temp engine home and kills it in a class cleanup (registered before the
daemon starts, so it runs even when a test or the start-up fails). Nothing reaches the real ~/.whynot-cut or an Adobe
app (the daemon inherits tests/_isolation.py's sandbox; the stuck-queue class replaces the bridge submit in the child).
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import asyncio
import json
import os
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
ENGINE = SK / "engine" / "reel"
sys.path.insert(0, str(ENGINE))

from lib import writer_lock  # noqa: E402
from serve import daemon, security  # noqa: E402
from test_serve_app import WsClient, command, http  # noqa: E402

WAIT = 30.0                       # the machine may be loaded: a cold daemon start can take seconds
START_BOUND = 120.0               # a daemon ensure left "starting" must answer --status as running within this
MAIN = ENGINE / "serve" / "__main__.py"
PHASES_RE = r"entry=0ms imports=\d+ms lock=\d+ms listening=\d+ms engine\.json=\d+ms"


def py_cmd(*args) -> list:
    cmd = [sys.executable]
    if sys.flags.no_user_site:
        cmd.append("-s")
    return cmd + ["-B", "-P", *map(str, args)]


def kill_daemons(home: Path, extra=()) -> None:
    """Kill every daemon a test started for `home` (ensure's children, `extra` Popens, the pid in engine.json)."""
    procs = [p for p in list(daemon._children) + list(extra)]
    info = security.read_engine_json(home) or {}
    pid = info.get("pid")
    if isinstance(pid, int) and pid != os.getpid() and writer_lock.pid_alive(pid, info.get("pid_created")):
        try:
            os.kill(pid, signal.SIGTERM)          # Windows: TerminateProcess
        except OSError:
            pass
        deadline = time.monotonic() + 10
        while writer_lock.pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
    for p in procs:
        if p.poll() is None:
            p.kill()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            pass
        if p in daemon._children:
            daemon._children.remove(p)


def audit_rows(home: Path) -> list:
    p = security.audit_log_path(home)
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def audit_text(home: Path) -> str:
    logs = security.audit_log_path(home).parent
    return "".join(f.read_text(encoding="utf-8") for f in sorted(logs.glob("serve-audit.log*")))


def diagnostics(home: Path) -> str:
    """serve.log (the daemon's stderr), the audit log and the start phase times of `home`, for a failure message. Read
    BEFORE the cleanup deletes the temp home. The token (the audit log never holds it) is masked anyway."""
    token = (security.read_engine_json(home) or {}).get("token")
    parts = []
    for label, read in (("serve.log", lambda: (home / "logs" / "serve.log").read_text("utf-8", "replace")[-4000:]),
                        ("serve-audit.log", lambda: "\n".join(audit_text(home).splitlines()[-60:])),
                        ("start phases", lambda: "\n".join(r.get("reason", "") for r in audit_rows(home)
                                                           if r.get("event") == "startup") or "(none yet)")):
        try:
            text = read()
        except (OSError, ValueError) as e:
            text = f"({type(e).__name__}: {e})"
        parts.append(f"--- {label} ---\n{text}")
    out = "\n".join(parts)
    return out.replace(token, "<token>") if token else out


def status_cli(home: Path) -> dict:
    """`reel serve --status` through the CLI entry; its JSON whatever the exit code (not_answering exits 1)."""
    r = subprocess.run(py_cmd(MAIN, "--status", "--home", home), capture_output=True, timeout=60,
                       stdin=subprocess.DEVNULL)
    try:
        return json.loads(r.stdout.decode("utf-8"))
    except ValueError:
        return {"state": None, "exit": r.returncode, "stderr": r.stderr.decode("utf-8", "replace")[-2000:]}


def until_running(get, bound: float = START_BOUND) -> dict:
    """Poll `get()` (a status document) until it says running, for at most `bound` seconds; the last document."""
    deadline = time.monotonic() + bound
    doc = get()
    while doc.get("state") != "running" and time.monotonic() < deadline:
        time.sleep(0.25)
        doc = get()
    return doc


def port_open(port: int, host: str = "127.0.0.1", family=socket.AF_INET) -> bool:
    with socket.socket(family, socket.SOCK_STREAM) as s:
        s.settimeout(2.0)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def non_loopback_ipv6() -> list:
    """This machine's IPv6 addresses that are not ::1 (link-local ones without a scope are skipped)."""
    out = []
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET6, socket.SOCK_STREAM)
    except OSError:
        return out
    for info in infos:
        a = info[4][0]
        if a and a not in ("::1", "::") and not a.lower().startswith("fe80") and a not in out:
            out.append(a)
    return out[:4]


def non_loopback_ipv4() -> str | None:
    """A local IPv4 address that is not loopback (the route to a TEST-NET address; no packet is sent)."""
    cands = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            cands.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        cands += socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    for a in cands:
        if a and not a.startswith("127.") and a != "0.0.0.0":
            return a
    return None


class LiveCase(unittest.IsolatedAsyncioTestCase):
    """One real daemon per class, started with daemon.ensure (the detached spawn path)."""

    @classmethod
    def setUpClass(cls):
        cls.home = Path(tempfile.mkdtemp(prefix="wnc-e2e-"))
        cls.addClassCleanup(shutil.rmtree, cls.home, True)       # runs last (cleanups are LIFO)
        cls.addClassCleanup(kill_daemons, cls.home)
        res = daemon.ensure(cls.home, wait=WAIT)
        # "starting" when the wait runs out is ensure's contract (daemon.ENSURE_WAIT: "Still starting after that is
        # {ok: true, state: starting}"), not a failure; the daemon must then answer --status within START_BOUND
        if res.get("ok") and res.get("state") == "starting":
            res = until_running(lambda: status_cli(cls.home))
        if not (res.get("ok") and res.get("state") == "running"):
            raise AssertionError(f"the daemon did not start: {res}\n{diagnostics(cls.home)}")
        info = security.read_engine_json(cls.home)
        cls.port, cls.token, cls.pid = info["port"], info["token"], info["pid"]

    def setUp(self):
        self.clients = []

    async def asyncTearDown(self):
        for c in self.clients:
            await c.aclose()
        self.assertNotIn(self.token, audit_text(self.home))      # never, after any test

    async def connect(self, **kw):
        c = await WsClient.connect(self.port, **kw)
        self.clients.append(c)
        return c

    async def hello(self, client=None, **fields):
        c = await self.connect()
        self.assertEqual(c.status, 101)
        msg = {"type": "hello", "token": self.token,
               "client": client or {"kind": "cli", "version": "3.0.0", "protocol": 4, "capabilities": []}}
        msg.update(fields)
        await c.send(msg)
        return c

    async def cli(self):
        c = await self.hello()
        w = await c.recv()
        self.assertEqual(w["type"], "welcome", w)
        return c

    def rows(self, event):
        return [r for r in audit_rows(self.home) if r["event"] == event]

    async def eventually(self, pred, what: str):
        for _ in range(100):
            if pred():
                return
            await asyncio.sleep(0.05)
        self.fail(f"not in the audit log: {what}")


class Attacks(LiveCase):
    async def test_wrong_token(self):
        c = await self.hello(token="f" * 64)
        msg = await c.recv()
        self.assertEqual((msg["type"], msg["code"]), ("error", "auth"))
        self.assertIsNone(await c.recv())
        self.assertEqual(c.close_code, 1008)
        await self.eventually(lambda: any(r["outcome"] == "rejected" and r["reason"] == "wrong token"
                                          for r in self.rows("auth")), "auth rejected: wrong token")

    async def test_missing_token(self):
        c = await self.connect()
        await c.send({"type": "hello", "client": {"kind": "cli", "version": "3.0.0", "protocol": 4,
                                                  "capabilities": []}})
        msg = await c.recv()
        self.assertEqual((msg["type"], msg["code"]), ("error", "auth"))
        self.assertIsNone(await c.recv())
        self.assertEqual(c.close_code, 1008)
        await self.eventually(lambda: any(r["outcome"] == "rejected" and "not a valid hello" in r["reason"]
                                          for r in self.rows("auth")), "auth rejected: no token")

    async def test_status_without_or_with_a_wrong_token(self):
        for auth in ("", f"Authorization: Bearer {'e' * 64}\r\n"):
            status, _, body = await http(self.port, f"GET /status HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                                                    f"{auth}\r\n".encode())
            self.assertEqual(status, 401)
            self.assertNotIn(self.token.encode(), body)
        await self.eventually(lambda: len([r for r in self.rows("status") if r["outcome"] == "rejected"]) >= 2,
                              "status rejected x2")

    async def test_wrong_host(self):
        for host in (f"evil.example:{self.port}", f"127.0.0.1:{self.port + 1}", "127.0.0.1"):
            status, _, _ = await http(self.port, f"GET /status HTTP/1.1\r\nHost: {host}\r\n"
                                                 f"Authorization: Bearer {self.token}\r\n\r\n".encode())
            self.assertEqual(status, 403, host)
        c = await self.connect(host=f"rebind.example:{self.port}")
        self.assertEqual(c.status, 403)
        await self.eventually(lambda: len([r for r in self.rows("http") if r["reason"] == "host"]) >= 4,
                              "http rejected: host x4")

    async def test_browser_origins(self):
        for origin in ("https://evil.example", "null", "chrome-extension://abcdefghijklmnop"):
            c = await self.connect(origin=origin)
            self.assertEqual(c.status, 403, origin)
            status, _, _ = await http(self.port, f"POST /shutdown HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                                                 f"Origin: {origin}\r\nAuthorization: Bearer {self.token}\r\n"
                                                 f"Content-Length: 0\r\n\r\n".encode())
            self.assertEqual(status, 403, origin)
        for origin in ("https://evil.example", "null", "chrome-extension://abcdefghijklmnop"):
            await self.eventually(lambda: any(r["reason"] == origin and r["outcome"] == "rejected"
                                              for r in self.rows("origin")), f"origin rejected: {origin}")
        self.assertTrue(port_open(self.port))                    # still running: no browser could stop it

    async def test_oversize_message_before_auth(self):
        c = await self.connect()
        await c.send_text("x" * (17 * 1024))
        self.assertIsNone(await c.recv())
        self.assertEqual(c.close_code, 1009)
        await self.eventually(lambda: any("1009" in r["reason"] for r in self.rows("auth")), "auth rejected: 1009")

    async def test_oversize_message_after_auth(self):
        c = await self.cli()
        n = 9 * 1024 * 1024                                      # announced only: refused before the payload is read
        c.w.write(bytes([0x81, 0x80 | 127]) + struct.pack("!Q", n) + os.urandom(4))
        await c.w.drain()
        self.assertIsNone(await c.recv())
        self.assertEqual(c.close_code, 1009)
        await self.eventually(lambda: any(r["reason"] == "close code 1009" for r in self.rows("session")),
                              "session closed 1009")

    async def test_rate_limit(self):
        c = await self.cli()
        for _ in range(80):
            await c.send({"type": "snapshot", "id": "rate-1"})
        codes = []
        for _ in range(80):
            msg = await c.recv()
            codes.append(msg["type"] if msg["type"] != "error" else msg["code"])
        self.assertIn("rate", codes)
        await self.eventually(lambda: any(r["outcome"] == "rejected" for r in self.rows("rate")), "rate rejected")

    async def test_unknown_action(self):
        c = await self.cli()
        msg = command("ping", id="unk-1")
        msg["request"]["action"] = "run_script"
        await c.send(msg)
        err = await c.recv()
        self.assertEqual((err["type"], err["code"], err.get("id")), ("error", "schema", "unk-1"), err)
        await self.eventually(lambda: any(r["outcome"] == "rejected" and r.get("action") == "command"
                                          for r in self.rows("message")), "message rejected: unknown action")

    async def test_schema_invalid_data(self):
        c = await self.cli()
        await c.send(command("open_project", {"no_path": 1}, id="bad-1"))
        err = await c.recv()
        self.assertEqual((err["type"], err["code"], err.get("id")), ("error", "schema", "bad-1"), err)
        await self.eventually(lambda: any(r["outcome"] == "rejected" and r.get("action") == "open_project"
                                          and r["reason"].startswith("schema") for r in self.rows("command")),
                              "command rejected: schema")

    async def test_reconnect_after_disconnect(self):
        a = await self.cli()
        await a.aclose()
        b = await self.cli()
        await b.send({"type": "snapshot", "id": "again"})
        st = await b.recv()
        self.assertEqual((st["type"], st.get("id")), ("state", "again"))

    # The Phase 6 acceptance line "IPv6 ::1 not bound" is superseded (network-"all" closure, docs/adobe/uxp-parity.md):
    # UXP may only dial `localhost`, which Windows resolves to ::1 first, so the daemon binds BOTH loopbacks. The
    # requirement that stays is loopback only: never 0.0.0.0, ::, or a LAN address.
    async def test_ipv6_loopback_is_bound_and_token_gated(self):
        if not socket.has_ipv6:
            self.skipTest("no IPv6 on this machine (the daemon serves 127.0.0.1 alone)")
        try:
            with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
                s.bind(("::1", 0))
        except OSError:
            self.skipTest("IPv6 loopback is not available here")
        self.assertTrue(port_open(self.port, "::1", socket.AF_INET6))
        self.assertTrue(port_open(self.port))
        ok = await http(self.port, f"GET /status HTTP/1.1\r\nHost: localhost:{self.port}\r\n"
                                   f"Authorization: Bearer {self.token}\r\n\r\n".encode(), addr="::1")
        no = await http(self.port, f"GET /status HTTP/1.1\r\nHost: [::1]:{self.port}\r\n\r\n".encode(), addr="::1")
        host = await http(self.port, f"GET /status HTTP/1.1\r\nHost: evil.example:{self.port}\r\n"
                                     f"Authorization: Bearer {self.token}\r\n\r\n".encode(), addr="::1")
        self.assertEqual((ok[0], no[0], host[0]), (200, 401, 403))
        client = {"kind": "cli", "version": "3.0.0", "protocol": 4, "capabilities": []}
        good = await self.connect(addr="::1", host=f"localhost:{self.port}")
        self.assertEqual(good.status, 101)
        await good.send({"type": "hello", "token": self.token, "client": client})
        self.assertEqual((await good.recv())["type"], "welcome")
        bad = await self.connect(addr="::1", host=f"localhost:{self.port}")
        await bad.send({"type": "hello", "token": security.make_token(), "client": client})
        msg = await bad.recv()
        self.assertEqual((msg["type"], msg["code"]), ("error", "auth"), msg)

    def test_wildcard_is_not_bound(self):
        addr = non_loopback_ipv4()
        if addr is None:
            self.skipTest("this machine has no non-loopback IPv4 address to try")
        self.assertFalse(port_open(self.port, addr), f"{addr}:{self.port} answered: the daemon is not loopback-only")

    def test_no_non_loopback_ipv6_is_bound(self):
        addrs = non_loopback_ipv6()
        if not addrs:
            self.skipTest("this machine has no non-loopback IPv6 address to try")
        for a in addrs:
            self.assertFalse(port_open(self.port, a, socket.AF_INET6), f"[{a}]:{self.port} answered: not loopback-only")

    def test_ensure_twice_is_the_same_daemon(self):
        pids = []
        for _ in range(2):
            r = subprocess.run(py_cmd(MAIN, "--ensure", "--wait", WAIT, "--home", self.home),
                               capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
            self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
            doc = json.loads(r.stdout.decode("utf-8"))
            self.assertEqual((doc["state"], doc["started"]), ("running", False), doc)
            self.assertNotIn(self.token, r.stdout.decode("utf-8"))
            pids.append(doc["pid"])
        self.assertEqual(pids, [self.pid, self.pid])


class UxpFileOrigin(LiveCase):
    """The Origin Premiere 26.5.2's UXP WebSocket really sends is exactly `file://` (spike 0.1.3 / 0.1.4, measured in
    the live serve-audit.log). It is let through the Origin gate and nothing more: the token, the Host check and the
    loopback bind still decide. Every other file form, `null` and any look-alike stay refused, and every Origin seen,
    allowed or refused, is on record in the audit log with its raw value."""

    PANEL = {"kind": "uxp", "version": "3.0.0", "protocol": 4, "capabilities": [], "host": "premiere",
             "hostVersion": "26.5.2"}

    def origin_rows(self, value, outcome):
        return [r for r in self.rows("origin") if r["reason"] == value and r["outcome"] == outcome]

    async def test_file_origin_with_the_token_gets_welcome(self):
        c = await self.connect(origin="file://")
        self.assertEqual(c.status, 101)
        await c.send({"type": "hello", "token": self.token, "client": self.PANEL})
        w = await c.recv()
        self.assertEqual(w["type"], "welcome", w)
        status, _, body = await http(self.port, f"GET /status HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                                                f"Origin: file://\r\nAuthorization: Bearer {self.token}\r\n\r\n"
                                                .encode())
        self.assertEqual(status, 200)
        self.assertNotIn(self.token.encode(), body)
        await self.eventually(lambda: len(self.origin_rows("file://", "allowed")) >= 2, "origin allowed: file:// x2")
        self.assertTrue(any(r["action"] == "/session" for r in self.origin_rows("file://", "allowed")))
        self.assertTrue(any(r["action"] == "/status" for r in self.origin_rows("file://", "allowed")))

    async def test_file_origin_without_or_with_a_wrong_token_is_refused(self):
        c = await self.connect(origin="file://")
        self.assertEqual(c.status, 101)
        await c.send({"type": "hello", "client": self.PANEL})                      # no token
        msg = await c.recv()
        self.assertEqual((msg["type"], msg["code"]), ("error", "auth"))
        self.assertIsNone(await c.recv())
        self.assertEqual(c.close_code, 1008)
        c = await self.connect(origin="file://")
        self.assertEqual(c.status, 101)
        await c.send({"type": "hello", "token": "f" * 64, "client": self.PANEL})   # wrong token
        msg = await c.recv()
        self.assertEqual((msg["type"], msg["code"]), ("error", "auth"))
        self.assertIsNone(await c.recv())
        self.assertEqual(c.close_code, 1008)
        for auth in ("", f"Authorization: Bearer {'e' * 64}\r\n"):
            status, _, _ = await http(self.port, f"GET /status HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                                                 f"Origin: file://\r\n{auth}\r\n".encode())
            self.assertEqual(status, 401)
            status, _, _ = await http(self.port, f"POST /shutdown HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                                                 f"Origin: file://\r\n{auth}Content-Length: 0\r\n\r\n".encode())
            self.assertEqual(status, 401)
        await self.eventually(lambda: any(r["outcome"] == "rejected" and r["reason"] == "wrong token"
                                          for r in self.rows("auth")), "auth rejected: wrong token")
        await self.eventually(lambda: any(r["outcome"] == "rejected" and "not a valid hello" in r["reason"]
                                          for r in self.rows("auth")), "auth rejected: no token")
        await self.eventually(lambda: len(self.origin_rows("file://", "allowed")) >= 6, "origin allowed: file:// x6")
        self.assertTrue(port_open(self.port))                    # still running: no token, no shutdown

    async def test_file_origin_still_needs_the_host(self):
        c = await self.connect(origin="file://", host=f"rebind.example:{self.port}")
        self.assertEqual(c.status, 403)
        status, _, _ = await http(self.port, f"GET /status HTTP/1.1\r\nHost: 127.0.0.1:{self.port + 1}\r\n"
                                             f"Origin: file://\r\nAuthorization: Bearer {self.token}\r\n\r\n".encode())
        self.assertEqual(status, 403)
        await self.eventually(lambda: len([r for r in self.rows("http") if r["reason"] == "host"]) >= 2,
                              "http rejected: host x2")

    async def test_every_other_file_form_and_null_are_refused(self):
        refused = ("null", "file:///x", "file://host", "FILE://", "File://", "file:///C:/Users/x/panel.html",
                   "file://localhost", "file:// x", "file://\t/")
        for origin in refused:
            c = await self.connect(origin=origin)
            self.assertEqual(c.status, 403, repr(origin))
            status, _, _ = await http(self.port, f"POST /shutdown HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                                                 f"Origin: {origin}\r\nAuthorization: Bearer {self.token}\r\n"
                                                 f"Content-Length: 0\r\n\r\n".encode())
            self.assertEqual(status, 403, repr(origin))
        for origin in refused:
            await self.eventually(lambda: len(self.origin_rows(origin, "rejected")) >= 2,
                                  f"origin rejected: {origin!r}")
            self.assertEqual(self.origin_rows(origin, "allowed"), [], repr(origin))
        self.assertTrue(port_open(self.port))                    # still running: no look-alike could stop it

    async def test_outer_whitespace_is_not_part_of_the_value(self):
        """RFC 9110 5.5: optional whitespace around a field value is not part of it, so the request parser strips
        it before the Origin gate. `Origin: file:// ` on the wire IS the value `file://`, so it reaches the hello
        like bare `file://` (UXP; Chromium-family browsers send `null` from a file page by default, `file://` only
        with file-URL access enabled) and the token still decides; whitespace inside the value is refused (above)."""
        for raw in ("file:// ", " file://", "file://\t"):
            c = await self.connect(origin=raw)
            self.assertEqual(c.status, 101, repr(raw))
            await c.send({"type": "hello", "token": "f" * 64, "client": self.PANEL})
            msg = await c.recv()
            self.assertEqual((msg["type"], msg["code"]), ("error", "auth"))      # the token still decides
        self.assertEqual([r for r in self.rows("origin") if r["reason"] != r["reason"].strip()], [])


class StopViaCli(unittest.TestCase):
    """`--ensure` then `--stop` through the CLI entry: the port closes, engine.json goes, the process exits."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="wnc-e2e-stop-"))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.addCleanup(kill_daemons, self.home)

    def run_cli(self, *args) -> dict:
        r = subprocess.run(py_cmd(MAIN, *args, "--home", self.home), capture_output=True, timeout=60,
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, (r.stdout, r.stderr))
        return json.loads(r.stdout.decode("utf-8"))

    def test_ensure_then_stop(self):
        try:
            self.ensure_then_stop()
        except Exception as e:           # serve.log, the audit log and the start phases, before cleanup deletes them
            raise self.failureException(f"{e}\n{diagnostics(self.home)}") from e

    def ensure_then_stop(self):
        up = self.run_cli("--ensure", "--wait", WAIT)
        # "starting" when --wait runs out is ensure's contract (daemon.ENSURE_WAIT: "Still starting after that is
        # {ok: true, state: starting}", which the SessionStart hook relies on), not a failure. The daemon it started
        # must then show as running through `--status` within START_BOUND.
        self.assertIn(up["state"], ("running", "starting"), up)
        self.assertIs(up["started"], True, up)
        if up["state"] == "starting":     # its pid may be a venv launcher's: the daemon's own pid comes from --status
            up = until_running(lambda: status_cli(self.home))
            self.assertEqual((up.get("ok"), up.get("state")), (True, "running"), up)
        info = security.read_engine_json(self.home)
        self.assertEqual(up["pid"], info["pid"])
        self.assertTrue(port_open(info["port"]))
        t0 = time.monotonic()
        down = self.run_cli("--stop")
        self.assertEqual((down["ok"], down["state"], down["exited"]), (True, "stopped", True), down)
        self.assertFalse(security.engine_json_path(self.home).exists())
        self.assertFalse(port_open(info["port"]))
        self.assertFalse(writer_lock.pid_alive(info["pid"]))
        self.assertLess(time.monotonic() - t0, 10.0)             # includes the CLI's own interpreter start
        rows = [r for r in audit_rows(self.home) if r["event"] == "daemon"]
        self.assertEqual([r["outcome"] for r in rows], ["started", "stopped"])
        self.assertTrue(any(r["event"] == "shutdown" and r["outcome"] == "accepted" for r in audit_rows(self.home)))
        self.assertNotIn(info["token"], audit_text(self.home))
        # the real detached start (__main__.py marks entry and imports): one startup row with every phase, no path
        startup = [r for r in audit_rows(self.home) if r["event"] == "startup"]
        self.assertEqual(len(startup), 1, startup)
        self.assertRegex(startup[0]["reason"], f"^{PHASES_RE}$")
        self.assertNotIn(str(self.home), json.dumps(startup[0]))


BOOT = r"""
import sys, time, pathlib
engine, mark, home = sys.argv[1:4]
sys.path.insert(0, engine)
from lib import ppro_bridge
def hang(*a, **k):
    pathlib.Path(mark).write_text("in", encoding="utf-8")
    time.sleep(600)
ppro_bridge.submit = hang
from serve.cli import main
sys.exit(main(["--foreground", "--home", home]))
"""


class StuckQueueDoesNotBlockExit(unittest.IsolatedAsyncioTestCase):
    """A CEP queue call stuck inside submit (Premiere showing a dialog) must not keep the daemon alive after --stop."""

    async def test_process_exits_quickly_with_a_stuck_worker(self):
        home = Path(tempfile.mkdtemp(prefix="wnc-e2e-stuck-"))
        self.addCleanup(shutil.rmtree, home, True)
        mark = home / "in-submit"
        proc = subprocess.Popen(py_cmd("-c", BOOT, ENGINE, mark, home), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                cwd=str(home))
        self.addCleanup(kill_daemons, home, [proc])
        for _ in range(int(WAIT / 0.05)):
            info = security.read_engine_json(home)
            if info and await asyncio.to_thread(port_open, info["port"]):
                break
            await asyncio.sleep(0.05)
        else:
            self.fail("the foreground daemon did not start")
        c = await WsClient.connect(info["port"])
        self.addAsyncCleanup(c.aclose)
        await c.send({"type": "hello", "token": info["token"],
                      "client": {"kind": "cli", "version": "3.0.0", "protocol": 4, "capabilities": []}})
        self.assertEqual((await c.recv())["type"], "welcome")
        await c.send(command("ping", id="stuck-1"))
        for _ in range(int(WAIT / 0.05)):
            if mark.exists():
                break
            await asyncio.sleep(0.05)
        else:
            self.fail("the queue call never started")
        t0 = time.monotonic()
        # Reap the daemon WHILE stop() waits for it to exit: it is this test's own child, and on POSIX an exited child
        # nobody has waited for is a zombie that os.kill(pid, 0) and `ps` still report as alive, so stop() would see
        # it "alive" for its whole STOP_WAIT (Mac CI: {state: stopping}). proc.pid is the daemon's pid there (a POSIX
        # venv python is a symlink, not a launcher). Windows has no zombies; the concurrent wait is harmless there.
        reaped = asyncio.ensure_future(asyncio.to_thread(proc.wait, 10))
        res = await asyncio.to_thread(daemon.stop, home)
        self.assertTrue(res["ok"], res)
        await reaped
        took = time.monotonic() - t0
        self.assertLess(took, 2.5, f"the daemon took {took:.2f}s to exit with a stuck queue call")
        self.assertFalse(security.engine_json_path(home).exists())


if __name__ == "__main__":
    unittest.main()
