"""`reel serve` app + router (3.0 T6.2): sessions, hello/token auth, the Host/Origin gate before the upgrade, schema-checked
messages, routing to a connected UXP panel or to the CEP file queue, result validation, progress relay and a Context per
request. Run:
    bash tools/test.sh -p test_serve_app.py
Every test runs a real in-process server on 127.0.0.1 with a temp engine home and talks to it through real loopback
sockets: a hand-written WebSocket client plays the CLI and a fake UXP panel. The CEP file queue is never reached
(lib.ppro_bridge.submit / lib.ae_bridge.submit are patched). Every socket, task and server is closed: the suite runs
with -W error::ResourceWarning.
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import asyncio
import base64
import json
import os
import shutil
import struct
import sys
import tempfile
import threading
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

import contract  # noqa: E402
from lib import common  # noqa: E402
from serve import adapters, app as serve_app, messages, router, security  # noqa: E402

T = 5.0                                    # upper bound for any single wait in this file
TEXT, CLOSE, PING, PONG = 1, 8, 9, 10
PING_READBACK = {"version": "26.0", "project": "", "projects_open": 0}


def frame(opcode: int, payload: bytes) -> bytes:
    n = len(payload)
    if n > 0xFFFF:
        head = bytes([0x80 | opcode, 0x80 | 127]) + struct.pack("!Q", n)
    elif n > 125:
        head = bytes([0x80 | opcode, 0x80 | 126]) + struct.pack("!H", n)
    else:
        head = bytes([0x80 | opcode, 0x80 | n])
    key = os.urandom(4)
    return head + key + bytes(b ^ key[i % 4] for i, b in enumerate(payload))


async def read_head(r):
    raw = await asyncio.wait_for(r.readuntil(b"\r\n\r\n"), T)
    lines = raw.decode("latin-1").split("\r\n")
    status = int(lines[0].split(" ")[1])
    headers = {}
    for line in lines[1:]:
        if line:
            k, _, v = line.partition(":")
            headers[k.strip().lower()] = v.strip()
    return status, headers


async def close_writer(w):
    if not w.is_closing():
        w.close()
    try:
        await asyncio.wait_for(w.wait_closed(), T)
    except (ConnectionError, OSError):
        pass


async def http(port, raw: bytes):
    """Send a raw HTTP request; return (status, headers, body) once the server has closed."""
    r, w = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), T)
    try:
        w.write(raw)
        await w.drain()
        status, headers = await read_head(r)
        body = await asyncio.wait_for(r.read(), T)
        return status, headers, body
    finally:
        await close_writer(w)


class WsClient:
    """A minimal WebSocket client speaking JSON messages; every message the daemon sends must validate."""

    def __init__(self, r, w):
        self.r, self.w = r, w
        self.status, self.headers, self.body = None, {}, b""
        self.close_code = None

    @classmethod
    async def connect(cls, port, *, path="/session", host=None, origin=None, drop_host=False, version="HTTP/1.1"):
        r, w = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), T)
        c = cls(r, w)
        h = {"Host": host or f"127.0.0.1:{port}", "Upgrade": "websocket", "Connection": "Upgrade",
             "Sec-WebSocket-Key": base64.b64encode(os.urandom(16)).decode(), "Sec-WebSocket-Version": "13"}
        if drop_host:
            del h["Host"]
        if origin is not None:
            h["Origin"] = origin
        raw = "\r\n".join([f"GET {path} {version}"] + [f"{k}: {v}" for k, v in h.items()]) + "\r\n\r\n"
        w.write(raw.encode())
        await w.drain()
        c.status, c.headers = await read_head(r)
        if c.status != 101:
            c.body = await asyncio.wait_for(r.read(), T)
            await c.aclose()
        return c

    async def send_text(self, text: str):
        self.w.write(frame(TEXT, text.encode("utf-8")))
        await self.w.drain()

    async def send(self, obj):
        await self.send_text(json.dumps(obj))

    async def recv(self):
        """The next JSON message (pings answered), or None once the server closed (close_code set)."""
        while True:
            try:
                b0, b1 = await asyncio.wait_for(self.r.readexactly(2), T)
            except asyncio.IncompleteReadError:
                await self.aclose()
                return None
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack("!H", await self.r.readexactly(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", await self.r.readexactly(8))[0]
            payload = await asyncio.wait_for(self.r.readexactly(n), T)
            op = b0 & 0x0F
            if op == TEXT:
                msg = json.loads(payload.decode("utf-8"))
                problem = messages.validate_message(msg)
                assert problem is None, (msg, problem)              # the daemon only ever sends contract messages
                return msg
            if op == PING:
                self.w.write(frame(PONG, payload))
                await self.w.drain()
                continue
            if op == CLOSE:
                self.close_code = struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else 1005
                try:
                    self.w.write(frame(CLOSE, payload[:2]))
                    await self.w.drain()
                    await asyncio.wait_for(self.r.read(), T)
                except (ConnectionError, OSError):
                    pass
                await self.aclose()
                return None

    async def recv_type(self, *types):
        """The next message of one of `types`, skipping others (e.g. progress when only the result matters)."""
        while True:
            msg = await self.recv()
            if msg is None or msg["type"] in types:
                return msg

    async def aclose(self):
        await close_writer(self.w)


def request(action="ping", data=None, *, id=None, expires_in=60.0):
    exp = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return {"protocol": 4, "id": id or uuid.uuid4().hex[:12], "action": action, "data": {} if data is None else data,
            "expires_at": exp.isoformat()}


def command(action="ping", data=None, *, id=None, expires_in=60.0, root=None, profile=None):
    msg = {"type": "command", "request": request(action, data, id=id, expires_in=expires_in)}
    ctx = {}
    if root is not None:
        ctx["root"] = str(root)
    if profile is not None:
        ctx["profile"] = profile
    if ctx:
        msg["context"] = ctx
    return msg


def cep_ok(action, result):
    return {"ok": True, "bridge_ok": True, "response": {"ok": True, "action": action, "result": result}, "job": "j1"}


class AppCase(unittest.IsolatedAsyncioTestCase):
    app_options: dict = {}

    async def asyncSetUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="wnc-serve-"))
        self.token = security.make_token()
        opts = {"hello_timeout": 1.0, **self.app_options}
        self.app = serve_app.App(home=self.home, token=self.token, version="3.0.0-test", **opts)
        self.port = await self.app.start()
        self.clients = []

    async def asyncTearDown(self):
        for c in self.clients:
            await c.aclose()
        await self.app.close()
        shutil.rmtree(self.home, ignore_errors=True)

    async def connect(self, **kw):
        c = await WsClient.connect(self.port, **kw)
        self.clients.append(c)
        return c

    async def hello(self, *, kind="cli", host=None, caps=(), token=None, host_version="26.0"):
        c = await self.connect()
        self.assertEqual(c.status, 101)
        client = {"kind": kind, "version": "3.0.0", "protocol": 4, "capabilities": list(caps)}
        if host:
            client["host"] = host
            client["hostVersion"] = host_version
        await c.send({"type": "hello", "token": token or self.token, "client": client})
        return c

    async def cli(self):
        c = await self.hello()
        welcome = await c.recv()
        self.assertEqual(welcome["type"], "welcome", welcome)
        return c

    async def panel(self, caps=("ping",), host="premiere"):
        c = await self.hello(kind="uxp", host=host, caps=caps)
        welcome = await c.recv()
        self.assertEqual(welcome["type"], "welcome", welcome)
        return c

    def audit(self):
        p = security.audit_log_path(self.home)
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

    def events(self, event):
        return [r for r in self.audit() if r["event"] == event]


# ------------------------------------------------------------------------------------------------------ messages
class ValidateMessage(unittest.TestCase):
    def test_missing_or_unknown_type_is_unknown_type(self):
        for msg in ({}, {"type": "nope"}, {"type": 3}, {"token": "x"}):
            with self.subTest(msg=msg):
                code, errors = messages.validate_message(msg)
                self.assertEqual(code, "unknown_type")

    def test_non_object_is_schema(self):
        for msg in ([], "hello", 3, None):
            self.assertEqual(messages.validate_message(msg)[0], "schema")

    def test_schema_errors_come_from_that_type_only(self):
        code, errors = messages.validate_message({"type": "command"})
        self.assertEqual(code, "schema")
        self.assertTrue(any("request" in e for e in errors), errors)
        self.assertFalse(any("oneOf" in e or "token" in e for e in errors), errors)   # not the 13-branch dump

    def test_valid_messages(self):
        self.assertIsNone(messages.validate_message({"type": "snapshot"}))
        self.assertIsNone(messages.validate_message(command()))

    def test_error_message_builder_validates(self):
        m = messages.error("schema", "x" * 5000, id="abc")
        self.assertIsNone(messages.validate_message(m))
        self.assertEqual(len(m["message"]), 2000)
        m = messages.error("schema", "bad", id="not a valid id!")          # an id that could not be echoed is dropped
        self.assertNotIn("id", m)


# ---------------------------------------------------------------------------------------------- strict context
class StrictContext(unittest.TestCase):
    def test_unbound_current_context_raises_when_required(self):
        home = Path(tempfile.mkdtemp(prefix="wnc-ctx-"))
        self.addCleanup(shutil.rmtree, home, True)
        common.require_bound_context(True)
        try:
            with self.assertRaisesRegex(RuntimeError, "no request context bound — reel serve must bind one per request"):
                common.current_context()
            ctx = common.Context(home=home)
            with common.use_context(ctx):
                self.assertIs(common.current_context(), ctx)
            with self.assertRaises(RuntimeError):
                common.current_context()
        finally:
            common.require_bound_context(False)
        self.assertIsInstance(common.current_context(), common.Context)        # the CLI's process context again

    def test_default_is_off(self):
        self.assertIsInstance(common.current_context(), common.Context)


class AppStrictContext(AppCase):
    async def test_start_turns_strict_context_on_and_close_restores(self):
        with self.assertRaises(RuntimeError):
            common.current_context()
        await self.app.close()
        self.assertIsInstance(common.current_context(), common.Context)


# ---------------------------------------------------------------------------------------------------------- HTTP
class Status(AppCase):
    async def test_status_needs_the_bearer_token(self):
        for auth in ("", "Authorization: Bearer nope\r\n", f"Authorization: Bearer {self.token[:-1]}\r\n",
                     f"Authorization: Basic {self.token}\r\n", f"Authorization: Bearer {self.token.upper()}\r\n"):
            with self.subTest(auth=auth):
                status, headers, body = await http(self.port, f"GET /status HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                                                              f"{auth}\r\n".encode())
                self.assertEqual(status, 401)
                self.assertNotIn(self.token.encode(), body)
        self.assertTrue(self.events("status"))

    async def test_status_fields_and_sessions(self):
        p = await self.panel(caps=("ping", "probe"))
        status, headers, body = await http(self.port, f"GET /status HTTP/1.1\r\nHost: localhost:{self.port}\r\n"
                                                      f"Authorization: Bearer {self.token}\r\n\r\n".encode())
        self.assertEqual(status, 200)
        d = json.loads(body)
        self.assertEqual(set(d), {"protocol", "daemon_version", "pid", "port", "sessions", "uptime_s"})
        self.assertEqual((d["protocol"], d["daemon_version"], d["pid"], d["port"]), (4, "3.0.0-test", os.getpid(), self.port))
        self.assertEqual(d["sessions"], [{"kind": "uxp", "host": "premiere", "hostVersion": "26.0",
                                          "capabilities": ["ping", "probe"]}])
        self.assertGreaterEqual(d["uptime_s"], 0)
        self.assertNotIn(self.token, body.decode())

    async def test_other_paths_are_404(self):
        for path in ("/", "/status/", "/status?x=1", "/session2", "/token"):
            with self.subTest(path=path):
                status, _, _ = await http(self.port, f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                                                     f"Authorization: Bearer {self.token}\r\n\r\n".encode())
                self.assertEqual(status, 404)

    async def test_wrong_host_is_403_and_audited(self):
        for host in ("evil.example:%d" % self.port, "127.0.0.1:1", "127.0.0.1", "[::1]:%d" % self.port):
            with self.subTest(host=host):
                status, _, _ = await http(self.port, f"GET /status HTTP/1.1\r\nHost: {host}\r\n"
                                                     f"Authorization: Bearer {self.token}\r\n\r\n".encode())
                self.assertEqual(status, 403)
        self.assertTrue(any(r["outcome"] == "rejected" and r["reason"] == "host" for r in self.events("http")))

    async def test_origin_is_audited_even_when_the_host_is_wrong(self):
        status, _, _ = await http(self.port, f"GET /session HTTP/1.1\r\nHost: evil.example:{self.port}\r\n"
                                             f"Origin: https://rebind.example\r\n\r\n".encode())
        self.assertEqual(status, 403)
        self.assertIn("https://rebind.example", [r["reason"] for r in self.events("origin")])

    async def test_missing_host_is_refused_even_over_http_1_0(self):
        status, _, _ = await http(self.port, f"GET /status HTTP/1.0\r\nAuthorization: Bearer {self.token}\r\n\r\n".encode())
        self.assertEqual(status, 400)
        c = await self.connect(drop_host=True, version="HTTP/1.0")
        self.assertEqual(c.status, 400)

    async def test_bad_request_heads_still_answered(self):
        status, _, _ = await http(self.port, b"GARBAGE\r\n\r\n")
        self.assertEqual(status, 400)
        status, _, _ = await http(self.port, f"GET /status HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                                             f"Content-Length: 3\r\n\r\nabc".encode())
        self.assertEqual(status, 400)


class ConnectionCaps(AppCase):
    app_options = {"max_connections": 2}

    async def test_global_cap_is_503_and_audited_and_frees_on_hang_up(self):
        """One global cap: on loopback every peer is 127.0.0.1, so a per-address cap would only be a second, smaller
        global cap (review fix round 1)."""
        self.assertFalse(hasattr(self.app, "max_per_peer"))
        a = await self.connect()
        b = await self.connect()
        self.assertEqual((a.status, b.status), (101, 101))
        c = await self.connect()
        self.assertEqual(c.status, 503)
        self.assertTrue(any(r["outcome"] == "rejected" for r in self.events("connection")))
        await a.aclose()
        for _ in range(50):                                    # the slot frees once the server sees the hang-up
            d = await self.connect()
            if d.status == 101:
                break
            await asyncio.sleep(0.05)
        self.assertEqual(d.status, 101)

    def test_defaults(self):
        self.assertEqual(serve_app.MAX_CONNECTIONS, 32)
        self.assertFalse(hasattr(serve_app, "MAX_PER_PEER"))


# --------------------------------------------------------------------------------------------- handshake + auth
class Handshake(AppCase):
    async def test_browser_origins_are_403_before_the_upgrade(self):
        # bare "file://" is UXP's measured Origin (allowed, below); every other file form stays a browser Origin
        for origin in ("https://evil.example", "http://127.0.0.1", "null", "file:///x", "file://host", "FILE://",
                       "chrome-extension://abc"):
            with self.subTest(origin=origin):
                c = await self.connect(origin=origin)
                self.assertEqual(c.status, 403)
        rows = self.events("origin")
        self.assertIn("https://evil.example", [r["reason"] for r in rows])     # the raw value is audited
        self.assertTrue(any(r["outcome"] == "rejected" for r in rows))
        self.assertFalse(any(r["reason"] == "file:///x" and r["outcome"] == "allowed" for r in rows))

    async def test_uxp_file_origin_reaches_the_hello_and_needs_the_token(self):
        """Premiere 26.5.2's UXP WebSocket sends exactly `Origin: file://` (measured live): it passes the Origin
        gate, and the token still decides."""
        client = {"kind": "uxp", "version": "3.0.0", "protocol": 4, "capabilities": [], "host": "premiere",
                  "hostVersion": "26.5.2"}
        c = await self.connect(origin="file://")
        self.assertEqual(c.status, 101)
        await c.send({"type": "hello", "token": self.token, "client": client})
        self.assertEqual((await c.recv())["type"], "welcome")
        bad = await self.connect(origin="file://")
        self.assertEqual(bad.status, 101)
        await bad.send({"type": "hello", "token": "f" * 64, "client": client})
        msg = await bad.recv()
        self.assertEqual((msg["type"], msg["code"]), ("error", "auth"))
        self.assertTrue(any(r["reason"] == "file://" and r["outcome"] == "allowed" for r in self.events("origin")))

    async def test_uxp_origin_is_allowed_and_audited(self):
        c = await self.connect(origin="uxp://ai.thewhynot.cut")
        self.assertEqual(c.status, 101)
        self.assertTrue(any(r["reason"] == "uxp://ai.thewhynot.cut" and r["outcome"] == "allowed"
                            for r in self.events("origin")))

    async def test_wrong_host_on_session_is_403(self):
        c = await self.connect(host="attacker.example:%d" % self.port)
        self.assertEqual(c.status, 403)

    async def test_good_hello_gets_welcome(self):
        c = await self.hello()
        w = await c.recv()
        self.assertEqual(w["type"], "welcome")
        self.assertEqual((w["protocol"], w["daemon_version"]), (4, "3.0.0-test"))
        self.assertTrue(any(r["outcome"] == "ok" for r in self.events("auth")))

    async def _refused(self, c):
        msg = await c.recv()
        self.assertEqual((msg["type"], msg["code"]), ("error", "auth"), msg)
        self.assertIsNone(await c.recv())
        self.assertEqual(c.close_code, 1008)

    async def test_wrong_token(self):
        await self._refused(await self.hello(token=security.make_token()))
        self.assertTrue(any(r["outcome"] == "rejected" for r in self.events("auth")))

    async def test_token_of_the_wrong_shape(self):
        await self._refused(await self.hello(token=self.token.upper()))
        await self._refused(await self.hello(token=self.token + "0"))

    async def test_first_message_must_be_hello(self):
        c = await self.connect()
        await c.send(command())
        await self._refused(c)
        c = await self.connect()
        await c.send_text("{not json")
        await self._refused(c)
        c = await self.connect()
        await c.send({"type": "hello", "token": self.token, "client": {"kind": "cli"}})   # schema-invalid hello
        await self._refused(c)

    async def test_hello_timeout(self):
        c = await self.connect()
        await self._refused(c)

    async def test_pre_auth_cap_is_16_kib(self):
        c = await self.connect()
        await c.send_text(" " * (16 * 1024 + 1))
        self.assertIsNone(await c.recv())
        self.assertEqual(c.close_code, 1009)

    async def test_post_auth_cap_is_8_mib(self):
        c = await self.cli()
        big = {"type": "snapshot", "id": "big"}
        text = json.dumps(big)[:-1] + " " * (300 * 1024) + "}"       # 300 KiB: over the pre-auth cap (and parsed off-loop)
        await c.send_text(text)
        msg = await c.recv()
        self.assertEqual((msg["type"], msg.get("id")), ("state", "big"))

    async def test_token_never_reaches_the_audit_log(self):
        await self.cli()
        await self._refused(await self.hello(token=security.make_token()))
        raw = security.audit_log_path(self.home).read_text(encoding="utf-8")
        self.assertNotIn(self.token, raw)


# --------------------------------------------------------------------------------------------- session messages
class SessionMessages(AppCase):
    async def test_schema_error_keeps_the_connection(self):
        c = await self.cli()
        await c.send({"type": "command", "id": "x"})
        err = await c.recv()
        self.assertEqual((err["type"], err["code"]), ("error", "schema"))
        self.assertIn("request", err["message"])
        await c.send({"type": "snapshot", "id": "s1"})
        self.assertEqual((await c.recv())["type"], "state")

    async def test_unknown_and_missing_type(self):
        c = await self.cli()
        for msg in ({"type": "eval", "code": "1+1"}, {"id": "x"}):
            await c.send(msg)
            err = await c.recv()
            self.assertEqual((err["type"], err["code"]), ("error", "unknown_type"))

    async def test_invalid_json_is_schema(self):
        c = await self.cli()
        await c.send_text("[1,")
        err = await c.recv()
        self.assertEqual(err["code"], "schema")

    async def test_daemon_only_types_are_refused(self):
        c = await self.cli()
        await c.send({"type": "welcome", "session_id": "x", "protocol": 4, "daemon_version": "1"})
        self.assertEqual((await c.recv())["code"], "schema")

    async def test_second_hello_is_refused(self):
        c = await self.cli()
        await c.send({"type": "hello", "token": self.token,
                      "client": {"kind": "cli", "version": "1", "protocol": 4, "capabilities": []}})
        self.assertEqual((await c.recv())["code"], "schema")

    INTENTS = [
        {"type": "approve", "id": "a1", "item": "C0239", "editor_name": "Y", "fingerprint": "f"},
        {"type": "request_changes", "id": "a2", "item": "C0239", "editor_name": "Y", "text": "shorter"},
        {"type": "rebuild", "id": "a3", "item": "C0239", "project_path": "x.prproj", "replace_edited": False},
        {"type": "rebuild", "id": "a4", "item": "C0239", "replace_edited": True},        # C2.4: project_path optional
    ]

    async def panel_session(self):
        c = await self.hello(kind="panel")
        self.assertEqual((await c.recv())["type"], "welcome")
        return c

    async def test_panel_intents_reply_not_available_yet_in_editor_words(self):
        c = await self.panel_session()
        for msg in self.INTENTS:
            await c.send(msg)
            reply = await c.recv()
            self.assertEqual((reply["type"], reply["id"], reply["intent"], reply["ok"]),
                             ("reply", msg["id"], msg["type"], False))
            self.assertEqual(reply["error"], serve_app.NOT_YET[msg["type"]])
            self.assertIn("not available from the panel yet", reply["error"])
            self.assertEqual(reply["how"], serve_app.NOT_YET_HOW)

    async def test_no_reply_text_names_a_command(self):
        """Addendum C1.4: what the panel shows the editor never holds a command. Every reply's error / how, as sent."""
        texts = list(serve_app.NOT_YET.values()) + [serve_app.NOT_YET_HOW]
        c = await self.panel_session()
        for msg in self.INTENTS:
            await c.send(msg)
            reply = await c.recv()
            texts += [reply.get("error", ""), reply.get("how", "")]
        for text in texts:
            self.assertNotIn("reel ", text.lower())
            self.assertNotIn("`", text)
            self.assertNotRegex(text.lower(), r"claude\s*code")

    async def test_intents_from_a_session_that_is_not_the_panel_are_refused(self):
        """Only a `kind: "panel"` session speaks for the editor: the CLI and a host (uxp / cep) get error{schema}."""
        for kind, host in (("cli", None), ("uxp", "premiere"), ("cep", "aftereffects")):
            c = await self.hello(kind=kind, host=host)
            self.assertEqual((await c.recv())["type"], "welcome")
            for msg in self.INTENTS:
                await c.send(msg)
                err = await c.recv()
                self.assertEqual((err["type"], err["code"], err.get("id")), ("error", "schema", msg["id"]), (kind, err))
                self.assertIn("panel", err["message"])
        rejected = [r for r in self.events("intent") if r["outcome"] == "rejected"]
        self.assertEqual(len(rejected), 3 * len(self.INTENTS))
        self.assertEqual({r["action"] for r in rejected}, {"approve", "request_changes", "rebuild"})

    async def test_snapshot_is_answered_by_state_echoing_id(self):
        c = await self.cli()
        await c.send({"type": "snapshot", "id": "snap-1"})
        st = await c.recv()
        self.assertEqual((st["type"], st["id"]), ("state", "snap-1"))
        self.assertEqual(st["state"]["connection"]["engine"], "connected")
        await self.panel()
        await c.send({"type": "snapshot"})
        st = await c.recv()
        self.assertNotIn("id", st)
        self.assertEqual(st["state"]["connection"]["host"]["state"], "uxp")

    async def test_snapshot_carries_the_item_from_active_json(self):
        """C2.4: <home>/state/active.json names the item; the state shows its client, item, pipeline and approval
        card (serve/engine_state.py; its own tests cover the evidence files)."""
        root = self.home / "clients" / "د. نور"
        for d in ("assets", "data", "output/projects/C0239/01_analysis"):
            (root / d).mkdir(parents=True)
        (root / "output/projects/C0239/01_analysis/timeline-spec.json").write_text('{"fps": 30}', encoding="utf-8")
        state_dir = self.home / "state"
        state_dir.mkdir()
        rec = {"client_root": str(root), "item": "C0239", "stage": "plan", "session_id": None, "claude_pid": None,
               "at": datetime.now(timezone.utc).isoformat()}
        (state_dir / "active.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        c = await self.cli()
        await c.send({"type": "snapshot", "id": "item-1"})
        st = (await c.recv())["state"]
        self.assertEqual((st["client"], st["item"]), ("د. نور", "C0239"))
        self.assertEqual({p["id"]: p["state"] for p in st["pipeline"]}["approve"], "waiting")
        self.assertTrue(st["approval"]["fingerprint"])
        self.assertEqual(st["connection"]["claude"], "unknown")             # no probe until T6.2b
        (state_dir / "active.json").write_text(json.dumps(dict(rec, item="../C0239"), ensure_ascii=False), encoding="utf-8")
        await c.send({"type": "snapshot", "id": "item-2"})
        st = (await c.recv())["state"]
        self.assertEqual((st["client"], st["item"], st["pipeline"], st["approval"]), ("", "", [], None))

    async def test_panel_intent_replies_are_audited(self):
        """Every answered panel intent leaves an audit row (event intent, outcome not_available), like the refused ones."""
        c = await self.panel_session()
        for msg in self.INTENTS:
            await c.send(msg)
            self.assertEqual((await c.recv())["type"], "reply")
        rows = [r for r in self.events("intent") if r["outcome"] == "not_available"]
        self.assertEqual([r["action"] for r in rows], [m["type"] for m in self.INTENTS])
        self.assertTrue(all(r.get("session") for r in rows))

    async def test_a_state_that_cannot_be_encoded_does_not_end_the_session(self):
        """_dumps refuses NaN / Infinity (allow_nan=False: not JSON); a message it cannot encode is logged and answered
        with error{internal} carrying the id, and the session goes on."""
        bad = {"client": "", "item": "x", "pipeline": [], "approval": None,
               "qc": [{"t_s": float("nan"), "tc": "00:00:00:00", "file": "f.png", "label": "", "verdict": "pending"}]}
        self.assertRaises(ValueError, serve_app._dumps, {"x": float("inf")})
        c = await self.cli()
        with mock.patch.object(self.app, "_fields", return_value=bad), self.assertLogs("serve.app", "WARNING") as logs:
            await c.send({"type": "snapshot", "id": "nan-1"})
            err = await c.recv()
        self.assertEqual((err["type"], err["code"], err.get("id")), ("error", "internal", "nan-1"), err)
        self.assertTrue(any("could not be encoded" in line for line in logs.output), logs.output)
        await c.send({"type": "snapshot", "id": "ok-1"})
        self.assertEqual((await c.recv())["id"], "ok-1")

    async def test_a_stuck_engine_state_read_times_out_on_one_bounded_worker(self):
        """A read that never returns (a dead network share, a FIFO swapped in) cannot stall a snapshot or leak a thread
        per poll: panel_fields runs on the app's one engine-state worker with FIELDS_TIMEOUT; past it the snapshot
        gets the last good item (else no item), the timeout is logged once, and while the read is still stuck later
        snapshots do not queue behind it."""
        self.app.fields_timeout = 0.2
        good = {"client": "Dr Nour", "item": "C0239", "pipeline": [], "approval": None, "qc": []}
        release = threading.Event()
        calls = []

        def stuck(home):
            calls.append(threading.current_thread().name)
            release.wait(T)
            return good
        c = await self.cli()
        try:
            with mock.patch.object(self.app, "_fields", side_effect=stuck), \
                    self.assertLogs("serve.app", "WARNING") as logs:
                t0 = time.monotonic()
                await c.send({"type": "snapshot", "id": "s1"})
                st = (await c.recv())["state"]
                self.assertLess(time.monotonic() - t0, 0.2 + 2.0)
                self.assertEqual((st["client"], st["item"]), ("", ""))          # nothing good yet: no item
                self.app.fields_timeout = 3.0           # a snapshot that queued behind the stuck read would wait this
                t1 = time.monotonic()
                for i in range(3):
                    await c.send({"type": "snapshot", "id": f"s{i + 2}"})
                    self.assertEqual((await c.recv())["state"]["item"], "")
                self.assertLess(time.monotonic() - t1, 1.5, "a snapshot waited behind the stuck read")
                self.assertEqual(len(calls), 1, "one read at a time")
                self.app.fields_timeout = 0.2
                release.set()
                deadline = time.monotonic() + T
                while self.app._fields_running is not None and not self.app._fields_running.done() \
                        and time.monotonic() < deadline:
                    await asyncio.sleep(0.01)
                await c.send({"type": "snapshot", "id": "s9"})
                self.assertEqual((await c.recv())["state"]["item"], "C0239")
            self.assertEqual(len([x for x in logs.output if "timed out" in x]), 1, logs.output)
            self.assertTrue(all(n.startswith("reel-serve-engine-state") for n in calls), calls)
            # stuck again: now the last good item is shown
            release.clear()
            with mock.patch.object(self.app, "_fields", side_effect=stuck), self.assertLogs("serve.app", "WARNING"):
                await c.send({"type": "snapshot", "id": "s10"})
                self.assertEqual((await c.recv())["state"]["item"], "C0239")
        finally:
            release.set()

    async def status_sessions(self) -> list:
        status, _, body = await http(self.port, f"GET /status HTTP/1.1\r\nHost: localhost:{self.port}\r\n"
                                                f"Authorization: Bearer {self.token}\r\n\r\n".encode())
        self.assertEqual(status, 200)
        return json.loads(body)["sessions"]

    async def pill(self, c, sid: str, *, cep_alive=False) -> dict:
        """The host part of the state the daemon answers to a snapshot (the CEP heartbeat fixed by the test)."""
        with mock.patch("lib.ppro_bridge.status", return_value={"alive": cep_alive}):
            await c.send({"type": "snapshot", "id": sid})
            st = await c.recv()
        self.assertEqual((st["type"], st.get("id")), ("state", sid), st)
        return st["state"]["connection"]["host"]

    async def test_host_pill_counts_only_a_uxp_premiere_session_with_capabilities(self):
        """A uxp session that implements nothing (spike 0.1.3, an old probe) is not the product host: the pill falls
        back to the CEP heartbeat instead of saying uxp while no Premiere host can run a command (review M7). Each step
        first checks the daemon's registry (/status) holds exactly the sessions the step expects, so the snapshot never
        races a session that is still being added or removed."""
        c = await self.cli()
        await self.panel(caps=())
        self.assertEqual(sorted((s["kind"], s["host"], tuple(s["capabilities"])) for s in await self.status_sessions()),
                         [("cli", None, ()), ("uxp", "premiere", ())])
        self.assertEqual((await self.pill(c, "no-caps"))["state"], "offline")
        await self.panel(caps=("ping",), host="aftereffects")      # an AE host is not the Premiere pill either
        self.assertEqual(len(await self.status_sessions()), 3)
        self.assertEqual((await self.pill(c, "cep", cep_alive=True))["state"], "cep")
        await self.panel(caps=("ping",))
        self.assertEqual(len(await self.status_sessions()), 4)
        self.assertEqual(await self.pill(c, "product"), {"state": "uxp", "detail": "Premiere Pro 26.0"})

    async def test_a_closed_host_session_no_longer_lights_the_pill_while_its_removal_is_pending(self):
        """Race fix: between a host's socket closing and the session leaving the registry (App._end, async) the
        session must not count. _end is held here so the window stays open for the assertion."""
        release = asyncio.Event()
        orig_end = self.app._end

        async def held_end(s):
            await release.wait()
            await orig_end(s)
        self.app._end = held_end
        try:
            c = await self.cli()
            p = await self.panel(caps=("ping",))
            self.assertEqual(await self.pill(c, "up"), {"state": "uxp", "detail": "Premiere Pro 26.0"})
            sess = next(s for s in self.app.sessions.values() if s.kind == "uxp")
            await p.aclose()
            deadline = time.monotonic() + T
            while not sess.sock.closed and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            self.assertTrue(sess.sock.closed)
            self.assertIn(sess.id, self.app.sessions, "the removal is still pending (held)")
            self.assertEqual((await self.pill(c, "closing"))["state"], "offline")
        finally:
            release.set()



class Rate(AppCase):
    app_options = {"rate": (1.0, 3)}

    async def test_rate_limit(self):
        c = await self.cli()
        for i in range(4):
            await c.send({"type": "snapshot", "id": f"s{i}"})
        got = [await c.recv() for _ in range(4)]
        self.assertEqual([m["type"] for m in got[:3]], ["state"] * 3)
        self.assertEqual((got[3]["type"], got[3]["code"], got[3]["id"]), ("error", "rate", "s3"))
        self.assertTrue(self.events("rate"))

    async def test_progress_burst_never_drops_the_result(self):
        """A panel bursting progress over the limit still delivers its result; excess progress is dropped silently
        (no id-less rate error to the panel), results are never rate-limited (review fix round 1)."""
        p = await self.panel(caps=("ping",))
        c = await self.cli()
        msg = command("ping")
        rid = msg["request"]["id"]
        await c.send(msg)
        await p.recv()
        for i in range(10):
            await p.send({"type": "progress", "progress": {"event": "progress", "id": rid, "action": "ping",
                                                            "step": f"step {i}", "n": i, "of": 10}})
        await p.send({"type": "result", "result": {"ok": True, "action": "ping", "id": rid, "readback": PING_READBACK}})
        got = []
        while True:
            m = await c.recv()
            got.append(m)
            if m["type"] == "result":
                break
        self.assertTrue(got[-1]["result"]["ok"], got[-1])
        self.assertLess(len(got) - 1, 10)                      # some progress was dropped ...
        self.assertTrue(all(m["type"] == "progress" for m in got[:-1]))
        await asyncio.sleep(1.1)                              # ... and the panel got no rate error for it
        await p.send({"type": "snapshot", "id": "after"})
        self.assertEqual((await p.recv())["type"], "state")


# ------------------------------------------------------------------------------------------------------- routing
class Routing(AppCase):
    async def test_unknown_action_is_rejected_by_schema(self):
        c = await self.cli()
        msg = command()
        msg["request"]["action"] = "eval_script"
        await c.send(msg)
        err = await c.recv()
        self.assertEqual((err["type"], err["code"], err["id"]), ("error", "schema", msg["request"]["id"]))

    async def test_no_action_evaluates_code(self):
        words = ("eval", "exec", "script", "run", "shell", "jsx", "code")
        self.assertFalse([a for a in contract.ACTIONS if any(w in a for w in words)])
        with mock.patch("lib.ppro_bridge.submit", return_value=cep_ok("ping", PING_READBACK)) as sub:
            c = await self.cli()
            await c.send(command("ping"))
            await c.recv()
        args, kwargs = sub.call_args
        self.assertNotIn("script", kwargs)                     # the router never names a script
        self.assertEqual(len(args), 2)

    async def test_bad_data_is_schema(self):
        c = await self.cli()
        await c.send(command("ping", {"extra": 1}))
        err = await c.recv()
        self.assertEqual(err["code"], "schema")

    async def test_expired_request_is_timeout(self):
        c = await self.cli()
        msg = command("ping", expires_in=-1)
        await c.send(msg)
        err = await c.recv()
        self.assertEqual((err["code"], err["id"]), ("timeout", msg["request"]["id"]))

    async def test_uxp_session_with_the_capability_wins(self):
        p = await self.panel(caps=("ping",))
        c = await self.cli()
        with mock.patch("lib.ppro_bridge.submit", side_effect=AssertionError("CEP must not be used")):
            msg = command("ping")
            await c.send(msg)
            cmd = await p.recv()
            self.assertEqual(cmd["type"], "command")
            self.assertEqual(cmd["request"], msg["request"])
            await p.send({"type": "result", "result": {"ok": True, "action": "ping", "id": msg["request"]["id"],
                                                       "readback": PING_READBACK}})
            res = await c.recv()
        self.assertEqual(res["type"], "result")
        self.assertEqual(res["result"], {"ok": True, "action": "ping", "id": msg["request"]["id"],
                                         "readback": PING_READBACK})
        self.assertTrue(any(r["action"] == "ping" and "uxp" in r["reason"] for r in self.events("command")))

    async def test_cep_fallback_without_a_capable_session(self):
        await self.panel(caps=("probe",))                     # connected, but without ping
        c = await self.cli()
        with mock.patch("lib.ppro_bridge.submit", return_value=cep_ok("ping", PING_READBACK)) as sub:
            msg = command("ping")
            await c.send(msg)
            res = await c.recv()
        sub.assert_called_once()
        self.assertEqual(sub.call_args.args[0], "ping")
        self.assertEqual(res["result"], {"ok": True, "action": "ping", "id": msg["request"]["id"],
                                         "readback": PING_READBACK})

    async def test_host_must_match(self):
        """A Premiere panel claiming an After Effects action is not chosen: the AE CEP queue runs it."""
        await self.panel(caps=("ae_fonts",), host="premiere")
        c = await self.cli()
        fonts = {"fonts": {}, "missing_or_substituted": []}
        with mock.patch("lib.ae_bridge.submit", return_value=cep_ok("fonts", fonts)) as ae, \
                mock.patch("lib.ppro_bridge.submit", side_effect=AssertionError("wrong bridge")):
            await c.send(command("ae_fonts", {"postscript_names": []}))
            res = await c.recv()
        ae.assert_called_once()
        self.assertEqual(ae.call_args.args[0], "fonts")
        self.assertEqual(res["type"], "result")

    async def test_no_route(self):
        c = await self.cli()
        msg = command("open_project", {"path": "C:/x.prproj"})     # uxp-only action, no panel connected
        if contract.validate_request(msg["request"]):
            self.skipTest("open_project data shape changed")
        await c.send(msg)
        err = await c.recv()
        self.assertEqual((err["type"], err["code"], err["id"]), ("error", "no_route", msg["request"]["id"]))

    async def test_invalid_host_result_becomes_outside_the_contract(self):
        p = await self.panel(caps=("ping",))
        c = await self.cli()
        msg = command("ping")
        await c.send(msg)
        await p.recv()
        await p.send({"type": "result", "result": {"ok": True, "action": "ping", "id": msg["request"]["id"],
                                                   "readback": {"version": 26}}})
        res = await c.recv()
        self.assertEqual(res["result"]["ok"], False)
        self.assertEqual(res["result"]["error"], "host answered outside the contract")
        self.assertEqual(res["result"]["id"], msg["request"]["id"])
        self.assertTrue(self.events("result-invalid"))

    async def test_result_for_another_action_is_outside_the_contract(self):
        p = await self.panel(caps=("ping",))
        c = await self.cli()
        msg = command("ping")
        await c.send(msg)
        await p.recv()
        await p.send({"type": "result", "result": {"ok": False, "action": "probe", "id": msg["request"]["id"],
                                                   "error": "x"}})
        res = await c.recv()
        self.assertEqual(res["result"]["error"], "host answered outside the contract")
        self.assertEqual(res["result"]["action"], "ping")

    async def test_invalid_cep_answer_becomes_outside_the_contract(self):
        c = await self.cli()
        with mock.patch("lib.ppro_bridge.submit", return_value=cep_ok("ping", {"version": 26})):
            await c.send(command("ping"))
            res = await c.recv()
        self.assertEqual(res["result"]["error"], "host answered outside the contract")

    async def test_progress_relay(self):
        p = await self.panel(caps=("ping",))
        c = await self.cli()
        msg = command("ping")
        rid = msg["request"]["id"]
        await c.send(msg)
        await p.recv()
        await p.send({"type": "progress", "progress": {"event": "progress", "id": rid, "action": "ping",
                                                        "step": "looking", "n": 1, "of": 2}})
        prog = await c.recv()
        self.assertEqual(prog["type"], "progress")
        self.assertEqual(prog["progress"]["step"], "looking")
        await p.send({"type": "result", "result": {"ok": True, "action": "ping", "id": rid, "readback": PING_READBACK}})
        self.assertEqual((await c.recv())["type"], "result")

    async def test_progress_for_an_unknown_id_is_not_relayed(self):
        p = await self.panel(caps=("ping",))
        c = await self.cli()
        await p.send({"type": "progress", "progress": {"event": "progress", "id": "nope", "action": "ping",
                                                        "step": "x"}})
        await c.send({"type": "snapshot", "id": "after"})
        self.assertEqual((await c.recv())["id"], "after")              # nothing was relayed before it

    async def test_panel_disconnect_fails_pending_commands(self):
        p = await self.panel(caps=("ping",))
        c = await self.cli()
        msg = command("ping")
        await c.send(msg)
        await p.recv()
        await p.aclose()
        res = await c.recv()
        self.assertEqual(res["type"], "result")
        self.assertFalse(res["result"]["ok"])
        self.assertIn("disconnected", res["result"]["error"])
        self.assertTrue(res["result"]["how"])
        # reconnect = a new hello; routing uses the new session
        p2 = await self.panel(caps=("ping",))
        msg2 = command("ping")
        await c.send(msg2)
        cmd = await p2.recv()
        self.assertEqual(cmd["request"]["id"], msg2["request"]["id"])
        await p2.send({"type": "result", "result": {"ok": True, "action": "ping", "id": msg2["request"]["id"],
                                                    "readback": PING_READBACK}})
        self.assertTrue((await c.recv())["result"]["ok"])

    async def test_duplicate_running_id_is_refused(self):
        p = await self.panel(caps=("ping",))
        c = await self.cli()
        msg = command("ping", id="same-id")
        await c.send(msg)
        await p.recv()
        await c.send(command("ping", id="same-id"))
        err = await c.recv()
        self.assertEqual((err["type"], err["code"], err["id"]), ("error", "schema", "same-id"))
        await p.send({"type": "result", "result": {"ok": True, "action": "ping", "id": "same-id",
                                                   "readback": PING_READBACK}})
        self.assertTrue((await c.recv())["result"]["ok"])


RESERVED_TOOL = {"audio": "WNC_AUDIO shared audio export", "hush": "Hush", "tidy": "Tidy", "kalam": "Kalam"}


class ReservedRouting(AppCase):
    """Round 4: a Phase 6B reserved action is never routed. The router answers ok:false itself (no adapter, no queue,
    no panel), with a `how`, and audits it."""

    def no_bridge(self):
        boom = AssertionError("a reserved action must not reach a CEP queue")
        return mock.patch("lib.ppro_bridge.submit", side_effect=boom), mock.patch("lib.ae_bridge.submit", side_effect=boom)

    async def test_every_reserved_action_is_answered_reserved(self):
        self.assertEqual(len(contract.RESERVED), 20)
        c = await self.cli()
        pp, ae = self.no_bridge()
        with pp, ae, mock.patch.object(adapters.FileQueueAdapter, "run", side_effect=AssertionError("adapter used")), \
                mock.patch.object(adapters.UxpAdapter, "run", side_effect=AssertionError("adapter used")):
            for action in contract.RESERVED:
                msg = command(action, {})
                await c.send(msg)
                res = await c.recv()
                self.assertEqual(res["type"], "result", (action, res))
                r = res["result"]
                tool = RESERVED_TOOL[action.split("_", 1)[0]]
                self.assertEqual(r["ok"], False, action)
                self.assertEqual(r["action"], action)
                self.assertEqual(r["id"], msg["request"]["id"])
                self.assertEqual(r["error"], f"reserved for Phase 6B ({tool}), not available yet")
                self.assertTrue(r["how"].strip(), action)
                self.assertNotIn("readback", r)
                self.assertEqual(contract.validate_result(r), [], action)
        rows = [r for r in self.events("command") if r["action"] in contract.RESERVED]
        self.assertEqual(sorted(r["action"] for r in rows), sorted(contract.RESERVED))
        for row in rows:
            self.assertEqual(row["outcome"], "reserved", row)
            self.assertIn("Phase 6B", row["reason"], row)

    async def test_a_panel_claiming_a_reserved_capability_is_not_asked(self):
        p = await self.panel(caps=("ping", "hush_markers", "tidy_save"))
        c = await self.cli()
        pp, ae = self.no_bridge()
        with pp, ae:
            msg = command("hush_markers", {"ranges": [{"s": 1.0, "e": 2.0, "kind": "silence", "label": "x"}]})
            self.assertEqual(contract.validate_request(msg["request"]), [])
            await c.send(msg)
            res = await c.recv()
            self.assertEqual(res["result"]["error"], "reserved for Phase 6B (Hush), not available yet")
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(p.recv(), 0.3)                  # the panel never saw the command
        self.assertFalse([r for r in self.events("command") if r.get("outcome") == "routed"
                          and r["action"] in contract.RESERVED])

    async def test_reserved_wins_over_bad_data_and_expiry(self):
        """The reserved answer comes first: a schema or expiry error would send the caller fixing a command that
        cannot run anyway (the envelope itself was already checked by the session schema)."""
        c = await self.cli()
        pp, ae = self.no_bridge()
        with pp, ae:
            for msg in (command("kalam_mogrt", {"surprise": 1}), command("tidy_scan", expires_in=-1)):
                await c.send(msg)
                res = await c.recv()
                self.assertEqual(res["type"], "result", res)
                self.assertFalse(res["result"]["ok"])
                self.assertIn("reserved for Phase 6B", res["result"]["error"])

    async def test_existing_routing_is_unchanged(self):
        await self.panel(caps=("probe",))
        c = await self.cli()
        with mock.patch("lib.ppro_bridge.submit", return_value=cep_ok("ping", PING_READBACK)) as sub:
            msg = command("ping")
            await c.send(msg)
            res = await c.recv()
        sub.assert_called_once()
        self.assertEqual(res["result"], {"ok": True, "action": "ping", "id": msg["request"]["id"], "readback": PING_READBACK})
        await c.send(command("open_project", {"path": "C:/x.prproj"}))
        err = await c.recv()
        self.assertEqual((err["type"], err["code"]), ("error", "no_route"))


class RouterReservedUnit(unittest.TestCase):
    def test_pick_never_returns_an_adapter_for_a_reserved_action(self):
        class Link:
            closed = False

        class S:
            id, kind, host, link = "s1", "uxp", "premiere", Link()
            capabilities = list(contract.ACTIONS)

        r = router.Router(home=Path(tempfile.gettempdir()), sessions=lambda: [S()])
        for action in contract.RESERVED:
            adapter, why = r.pick(action)
            self.assertIsNone(adapter, action)
            self.assertIn("reserved for Phase 6B", why, action)
        self.assertIsNotNone(r.pick("ping")[0])                         # a routed action still finds the panel

    def test_reserved_answer_names_the_tool_and_the_task(self):
        for action, tool, task in (("audio_export_range", "WNC_AUDIO shared audio export", "T6.11"),
                                   ("hush_cut", "Hush", "T6.12"), ("tidy_build_synced", "Tidy", "T6.13"),
                                   ("kalam_mogrt", "Kalam", "T6.14")):
            res = router.reserved_result(action, "r-1")
            self.assertEqual(res["error"], f"reserved for Phase 6B ({tool}), not available yet")
            self.assertIn(task, res["how"])
            self.assertEqual(contract.validate_result(res), [])
        with self.assertRaises(ValueError):
            router.reserved_result("ping", "r-1")


class UxpTimeout(AppCase):
    async def test_panel_that_never_answers_times_out_at_expires_at(self):
        p = await self.panel(caps=("ping",))
        c = await self.cli()
        msg = command("ping", expires_in=0.5)
        await c.send(msg)
        await p.recv()
        res = await c.recv()
        self.assertFalse(res["result"]["ok"])
        self.assertIn("did not answer", res["result"]["error"])
        cancel = await p.recv()                               # sent to the panel before the requester was failed
        self.assertEqual(cancel, {"type": "cancel", "id": msg["request"]["id"]})


# ------------------------------------------------------------------------------------------------------- context
class RequestContext(AppCase):
    async def test_two_concurrent_commands_see_their_own_context(self):
        roots = [Path(tempfile.mkdtemp(prefix="wnc-root-")) for _ in range(2)]
        for r in roots:
            self.addCleanup(shutil.rmtree, r, True)
        barrier = threading.Barrier(2, timeout=T)
        seen = []

        def fake_submit(action, data=None, timeout=600):
            ctx = common.current_context()          # strict mode: raises unless the router bound one
            barrier.wait()                          # both commands are inside a queue call at the same time
            seen.append((ctx.root, ctx.profile, ctx.engine_home))
            if action == "ping":
                return cep_ok("ping", PING_READBACK)
            return cep_ok("fonts", {"fonts": {}, "missing_or_substituted": []})

        c = await self.cli()                        # Premiere and After Effects queues run side by side
        with mock.patch("lib.ppro_bridge.submit", fake_submit), mock.patch("lib.ae_bridge.submit", fake_submit):
            await c.send(command("ping", root=roots[0], profile="p0"))
            await c.send(command("ae_fonts", {"postscript_names": []}, root=roots[1], profile="p1"))
            res = [await c.recv(), await c.recv()]
        self.assertTrue(all(r["result"]["ok"] for r in res), res)
        self.assertEqual(sorted(seen), sorted([(roots[0].resolve(), "p0", self.home), (roots[1].resolve(), "p1", self.home)]))


    async def test_queue_calls_of_one_bridge_never_overlap(self):
        """bridge.submit shares files (sync_scripts' fixed temp path): one call per bridge at a time."""
        active, peak, lock = [0], [0], threading.Lock()

        def fake_submit(action, data=None, timeout=600):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            try:
                threading.Event().wait(0.2)
            finally:
                with lock:
                    active[0] -= 1
            return cep_ok("ping", PING_READBACK)

        c = await self.cli()
        with mock.patch("lib.ppro_bridge.submit", fake_submit):
            for _ in range(3):
                await c.send(command("ping"))
            res = [await c.recv() for _ in range(3)]
        self.assertTrue(all(r["result"]["ok"] for r in res), res)
        self.assertEqual(peak[0], 1)


# ------------------------------------------------------------------------------------------------------ adapters
class FileQueue(unittest.IsolatedAsyncioTestCase):
    async def test_outer_error_is_forwarded_when_there_is_no_response(self):
        out = {"ok": False, "error": "bridge not running", "status": {"alive": False, "detail": "no heartbeat: start Premiere"}}
        with mock.patch("lib.ppro_bridge.submit", return_value=out):
            res = await adapters.FileQueueAdapter().run(request("ping", id="r1"))
        self.assertEqual(res, {"ok": False, "action": "ping", "id": "r1", "error": "bridge not running",
                               "how": "no heartbeat: start Premiere"})
        self.assertEqual(contract.validate_result(res), [])

    async def test_ae_actions_use_the_ae_bridge(self):
        with mock.patch("lib.ae_bridge.submit", return_value=cep_ok("probe_text", {"x": 1})) as ae:
            await adapters.FileQueueAdapter().run(request("ae_probe_text", id="r2"))
        self.assertEqual(ae.call_args.args[0], "probe_text")

    async def test_timeout_follows_expires_at(self):
        with mock.patch("lib.ppro_bridge.submit", return_value=cep_ok("ping", PING_READBACK)) as sub:
            await adapters.FileQueueAdapter().run(request("ping", id="r3", expires_in=30))
        self.assertLessEqual(sub.call_args.kwargs["timeout"], 30)
        self.assertGreater(sub.call_args.kwargs["timeout"], 20)

    async def test_queue_failure_shapes_map_to_ok_false_with_error_and_how(self):
        """Bridge 3.1.1 (T2.9) queue answers without a parsed response: each is ok:false with a sentence and a fix."""
        st = {"alive": True, "bridge_version": "3.1.0", "detail": "ok"}
        shapes = {
            "version mismatch": {"ok": False, "error": "the WhyNot Cut Bridge running in Premiere is 3.1.0; this engine "
                                 "needs bridge 3.1.1", "how": "Restart Premiere to load bridge 3.1.1.", "status": st},
            "expired": {"ok": False, "error": "timeout: the job expired before Premiere could start it",
                        "how": "Premiere was busy.", "expired": True, "job": "j"},
            "cancelled": {"ok": False, "error": "timeout: Premiere did not start the job within 30s; it was cancelled "
                          "and will not run", "how": "Premiere is busy.", "cancelled": True, "job": "j"},
            "bridge stopped": {"ok": False, "error": "bridge stopped before it started the job (cancelled)",
                               "status": {"alive": False, "detail": "heartbeat 9s old: panel closed or Premiere busy/quit"},
                               "cancelled": True, "job": "j"},
            "claimed timeout": {"ok": False, "error": "timeout after 30s (Premiere may show a dialog)", "claimed": True,
                                "job": "j"},
            "bridge refusal": {"ok": False, "bridge_ok": False, "response": None, "error": "script not whitelisted",
                               "job": "j"},
            "build lock held": {"blocked": "another build is running in Premiere: ppro-build (process 1 on pc)",
                                "how": "Let it finish (one build at a time per Premiere), then run the command again."},
            "test sandbox": {"ok": False, "refused": "test-sandbox", "error": "test sandbox: refused", "how": "mock it"},
            "not a dict": None,
        }
        for name, out in shapes.items():
            with self.subTest(name), mock.patch("lib.ppro_bridge.submit", return_value=out):
                res = await adapters.FileQueueAdapter().run(request("ping", id="r9"))
                self.assertEqual(contract.validate_result(res), [], res)
                self.assertEqual((res["ok"], res["id"], res["action"]), (False, "r9", "ping"))
                self.assertTrue(res["error"].strip(), res)
                self.assertTrue(res.get("how", "").strip(), res)
        with mock.patch("lib.ppro_bridge.submit", return_value=shapes["build lock held"]):
            res = await adapters.FileQueueAdapter().run(request("ping", id="r9"))
        self.assertIn("another build is running", res["error"])
        with mock.patch("lib.ppro_bridge.submit", return_value=shapes["version mismatch"]):
            res = await adapters.FileQueueAdapter().run(request("ping", id="r9"))
        self.assertEqual(res["how"], "Restart Premiere to load bridge 3.1.1.")

    async def test_worker_binds_the_request_context_explicitly(self):
        """The queue call sees the request's Context on its QueueWorker thread, a plain thread that does not copy
        contextvars by itself (Task 5: queue calls left asyncio.to_thread for their own daemon workers)."""
        home = Path(tempfile.mkdtemp(prefix="wnc-ctx-"))
        self.addCleanup(shutil.rmtree, home, True)
        ctx = common.Context(home=home)
        seen = []

        def fake_submit(action, data=None, timeout=600):
            t = threading.current_thread()
            seen.append((common.current_context(), t is not threading.main_thread(), t.name))
            return cep_ok("ping", PING_READBACK)

        common.require_bound_context(True)
        try:
            with mock.patch("lib.ppro_bridge.submit", fake_submit):
                with common.use_context(ctx):
                    res = await adapters.FileQueueAdapter().run(request("ping", id="r10"))
        finally:
            common.require_bound_context(False)
        self.assertTrue(res["ok"], res)
        self.assertEqual(seen, [(ctx, True, "reel-serve-queue-premiere")])

    async def test_actions_without_a_cep_name_are_refused(self):
        with self.assertRaises(ValueError):
            await adapters.FileQueueAdapter().run(request("open_project", {"path": "x"}, id="r4"))

    async def test_reserved_actions_are_refused_by_the_queue_adapter_too(self):
        """Defence in depth: even if something bypassed the router, the CEP queue never submits a reserved action."""
        with mock.patch("lib.ppro_bridge.submit", side_effect=AssertionError("queued")):
            for action in contract.RESERVED:
                self.assertIn(action, adapters.CEP_NAME)                 # it has a (future) WNC_* name ...
                with self.assertRaisesRegex(ValueError, "reserved for Phase 6B"):
                    await adapters.FileQueueAdapter().run(request(action, {}, id="r5"))   # ... and is still refused


class RouterUnit(unittest.TestCase):
    def test_router_has_no_eval_path(self):
        import inspect
        for mod in (serve_app, router, adapters, messages):
            src = inspect.getsource(mod)
            for word in ("eval(", "exec(", "evalScript", "subprocess", "script="):
                self.assertNotIn(word, src, (mod.__name__, word))


if __name__ == "__main__":
    unittest.main()


class BuildStamp(AppCase):
    """C2.3: hello.client.build against <plugin>/adobe/expected.json -> welcome.update.panel."""

    async def asyncSetUp(self):
        self.expected = Path(tempfile.mkdtemp(prefix="wnc-exp-")) / "expected.json"
        self.app_options = {"expected_path": self.expected}
        await super().asyncSetUp()

    async def asyncTearDown(self):
        await super().asyncTearDown()
        shutil.rmtree(self.expected.parent, ignore_errors=True)

    async def welcome_for(self, build):
        c = await self.connect()
        client = {"kind": "panel", "version": "3.0.0", "protocol": 4, "capabilities": []}
        if build is not None:
            client["build"] = build
        await c.send({"type": "hello", "token": self.token, "client": client})
        w = await c.recv()
        self.assertEqual(w["type"], "welcome", w)
        return w["update"]["panel"]

    async def test_without_expected_json_every_panel_is_unknown(self):
        self.assertEqual(await self.welcome_for("142"), "unknown")
        self.assertEqual(await self.welcome_for(None), "unknown")

    async def test_ok_stale_newer_unknown(self):
        """C1.8: both are the build id YYYYMMDDTHHMMSSZ (build.json's); an older panel is stale (restart Premiere), any
        other differing value too (expected.json is the authority); no build or no expected.json is unknown."""
        a = "20261013T142530Z"
        self.expected.write_text(json.dumps({"product": "3.0.0", "build": a, "sha": "abc1234"}), encoding="utf-8")
        for build, want in ((a, "ok"), ("20261013T142529Z", "stale"), ("20261013T142531Z", "newer"),
                            ("abc1234 2026-10-13T10:00Z", "stale"), (None, "unknown")):
            self.assertEqual(await self.welcome_for(build), want, build)
        self.expected.write_text("{broken", encoding="utf-8")
        self.assertEqual(await self.welcome_for(a), "unknown")

    async def test_an_invalid_build_is_a_refused_hello(self):
        for bad in ("", "x" * 65):
            c = await self.connect()
            await c.send({"type": "hello", "token": self.token,
                          "client": {"kind": "panel", "version": "3.0.0", "build": bad, "protocol": 4, "capabilities": []}})
            msg = await c.recv()
            self.assertEqual((msg["type"], msg["code"]), ("error", "auth"), msg)

