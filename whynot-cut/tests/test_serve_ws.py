"""`reel serve` transport (3.0 T6.2): the stdlib HTTP/1.1 + RFC 6455 WebSocket server in serve/ws.py. Run:
    bash tools/test.sh -p test_serve_ws.py
Every test talks to a real server on 127.0.0.1 through real loopback sockets with a hand-written client (it masks its
frames, fragments, pings, sends bad frames on purpose). Every socket, writer and server is closed: the suite runs with
-W error::ResourceWarning.
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import asyncio
import base64
import hashlib
import json
import os
import struct
import sys
import time
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from serve import ws  # noqa: E402

T = 3.0                                    # upper bound for any single wait in this file (nothing should take it)
KEY = "dGhlIHNhbXBsZSBub25jZQ=="            # RFC 6455 section 1.3 sample key ...
ACCEPT = "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="     # ... and its Sec-WebSocket-Accept
TEXT, BINARY, CONT, CLOSE, PING, PONG = 1, 2, 0, 8, 9, 10


def xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % 4] for i, b in enumerate(data))


def frame(opcode: int, payload: bytes = b"", *, fin: bool = True, mask: bool = True, rsv: int = 0,
          length: int | None = None, ext: int | None = None) -> bytes:
    """One client frame. length overrides the announced length; ext forces a 16- or 64-bit length field."""
    n = len(payload) if length is None else length
    b0 = (0x80 if fin else 0) | (rsv << 4) | opcode
    m = 0x80 if mask else 0
    if ext == 64 or (ext is None and n > 0xFFFF):
        head = bytes([b0, m | 127]) + struct.pack("!Q", n)
    elif ext == 16 or (ext is None and n > 125):
        head = bytes([b0, m | 126]) + struct.pack("!H", n)
    else:
        head = bytes([b0, m | n])
    if not mask:
        return head + payload
    key = os.urandom(4)
    return head + key + xor(payload, key)


def upgrade_request(path: str = "/ws", drop: tuple = (), **override: str) -> bytes:
    h = {"Host": "127.0.0.1:1", "Upgrade": "websocket", "Connection": "Upgrade", "Sec-WebSocket-Key": KEY,
         "Sec-WebSocket-Version": "13"}
    for k, v in override.items():
        h[k.replace("_", "-")] = v
    lines = [f"GET {path} HTTP/1.1"] + [f"{k}: {v}" for k, v in h.items() if k not in drop]
    return ("\r\n".join(lines) + "\r\n\r\n").encode()


class Client:
    """A minimal WebSocket client: raw bytes in, frames out."""

    def __init__(self, reader, writer):
        self.r, self.w = reader, writer

    @classmethod
    async def open(cls, port):
        r, w = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), T)
        return cls(r, w)

    async def send_raw(self, data: bytes):
        self.w.write(data)
        await self.w.drain()

    async def head(self):
        raw = await asyncio.wait_for(self.r.readuntil(b"\r\n\r\n"), T)
        lines = raw.decode("latin-1").split("\r\n")
        status = int(lines[0].split(" ")[1])
        headers = {}
        for line in lines[1:]:
            if line:
                k, _, v = line.partition(":")
                headers[k.strip().lower()] = v.strip()
        return status, headers

    async def http(self, data: bytes):
        """Send a raw request; return (status, headers, body) and require the server to close."""
        await self.send_raw(data)
        status, headers = await self.head()
        body = await asyncio.wait_for(self.r.read(), T)          # read() = until EOF: the server closed
        await self.aclose()                                       # ... and so does a good client
        return status, headers, body

    async def handshake(self, path="/ws", **kw):
        await self.send_raw(upgrade_request(path, **kw))
        return await self.head()

    async def send(self, opcode, payload=b"", **kw):
        await self.send_raw(frame(opcode, payload, **kw))

    async def read_frame(self):
        b0, b1 = await asyncio.wait_for(self.r.readexactly(2), T)
        assert not b1 & 0x80, "server frames must not be masked"
        n = b1 & 0x7F
        if n == 126:
            n = struct.unpack("!H", await self.r.readexactly(2))[0]
        elif n == 127:
            n = struct.unpack("!Q", await self.r.readexactly(8))[0]
        payload = await asyncio.wait_for(self.r.readexactly(n), T)
        return bool(b0 & 0x80), b0 & 0x0F, payload

    async def expect_close(self, code: int):
        """The next frame is a close with `code`; answer it like a good client and see the server hang up."""
        fin, op, payload = await self.read_frame()
        assert op == CLOSE, (op, payload)
        got = struct.unpack("!H", payload[:2])[0]
        assert got == code, (got, payload[2:])
        try:
            await self.send(CLOSE, payload[:2])
        except ConnectionError:
            pass
        rest = await asyncio.wait_for(self.r.read(), T)          # the server hangs up first (FIN) ...
        assert rest == b"", rest
        await self.aclose()                                       # ... then the client closes its side
        return payload[2:].decode("utf-8")

    async def aclose(self):
        if not self.w.is_closing():
            self.w.close()
        try:
            await asyncio.wait_for(self.w.wait_closed(), T)
        except (ConnectionError, OSError):
            pass


class ServeCase(unittest.IsolatedAsyncioTestCase):
    """A real server with a small echo app; every test opens its own clients."""
    options = {"max_message": 1 << 20, "idle_timeout": 5.0}

    async def asyncSetUp(self):
        self.requests, self.sockets = [], []
        self.done = asyncio.Queue()           # the server's close code of each WebSocket that ended
        self.clients = []
        self.server, self.port = await ws.start_server(self.app)

    async def asyncTearDown(self):
        for c in self.clients:
            await c.aclose()
        self.server.close()
        await asyncio.wait_for(self.server.wait_closed(), T)

    async def client(self):
        c = await Client.open(self.port)
        self.clients.append(c)
        return c

    async def app(self, reader, writer):
        req = await ws.parse_http(reader)
        self.requests.append(req)
        if req.path == "/json":
            await ws.write_response(writer, ws.json_response(200, {"ok": True, "word": "مرحبا"}))
            return
        if req.path == "/boom":
            raise RuntimeError("handler bug")
        if req.path == "/ws":
            sock = await ws.upgrade(req, reader, writer, **self.options)
            if sock is None:
                return
            self.sockets.append(sock)
            while (msg := await sock.recv()) is not None:
                if msg == "raise-limit":
                    sock.max_message = 1 << 20
                    await sock.send("raised")
                elif msg == "close-me":
                    await sock.close(4000, "bye from server")
                elif msg == "ping-me":
                    await sock.ping()
                else:
                    await sock.send("echo:" + msg)
            self.done.put_nowait(sock.close_code)
            return
        await ws.write_response(writer, ws.json_response(404, {"error": "not found"}))

    async def server_close_code(self):
        return await asyncio.wait_for(self.done.get(), T)

    async def open_ws(self):
        c = await self.client()
        status, headers = await c.handshake()
        self.assertEqual(status, 101)
        return c


# ------------------------------------------------------------------------------------------------------- server
class TestStartServer(ServeCase):
    async def test_binds_127_0_0_1_on_a_free_port(self):
        self.assertGreater(self.port, 0)
        addrs = [s.getsockname() for s in self.server.sockets]
        self.assertEqual(addrs, [("127.0.0.1", self.port)])

    async def test_refuses_any_other_host(self):
        async def h(r, w):
            pass
        for host in ("0.0.0.0", "::1", "localhost", "", "::", "127.0.0.2", None):
            with self.assertRaises(ValueError, msg=host):
                await ws.start_server(h, host=host)

    async def test_refuses_a_bad_port(self):
        async def h(r, w):
            pass
        for port in (-1, 65536, "8080", True):
            with self.assertRaises(ValueError, msg=port):
                await ws.start_server(h, port=port)

    async def test_handler_exception_closes_the_connection_and_the_server_keeps_serving(self):
        c = await self.client()
        with self.assertLogs("serve.ws", "WARNING") as logs:
            await c.send_raw(b"GET /boom HTTP/1.1\r\nHost: x\r\n\r\n")
            self.assertEqual(await asyncio.wait_for(c.r.read(), T), b"")
        self.assertIn("RuntimeError", logs.output[0])
        self.assertNotIn("handler bug", logs.output[0])           # never the message (it may hold a token)
        await c.aclose()
        c2 = await self.client()
        status, _, body = await c2.http(b"GET /json HTTP/1.1\r\nHost: x\r\n\r\n")
        self.assertEqual(status, 200)


# --------------------------------------------------------------------------------------------------------- HTTP
class TestHttp(ServeCase):
    async def test_json_response_and_connection_close(self):
        c = await self.client()
        status, headers, body = await c.http(b"GET /json HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        self.assertEqual(status, 200)
        self.assertEqual(headers["connection"], "close")
        self.assertTrue(headers["content-type"].startswith("application/json"))
        self.assertEqual(int(headers["content-length"]), len(body))
        self.assertEqual(json.loads(body.decode("utf-8")), {"ok": True, "word": "مرحبا"})

    async def test_404_for_other_paths(self):
        c = await self.client()
        status, _, body = await c.http(b"GET /nope HTTP/1.1\r\nHost: x\r\n\r\n")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body), {"error": "not found"})

    async def test_request_fields(self):
        c = await self.client()
        await c.http(b"GET /json?a=1 HTTP/1.1\r\nHost: 127.0.0.1:9\r\nX-Thing:  v1 \r\nx-thing: v2\r\n"
                     b"Authorization: Bearer abc\r\n\r\n")
        req = self.requests[0]
        self.assertEqual((req.method, req.path, req.version), ("GET", "/json?a=1", "HTTP/1.1"))
        self.assertEqual(req.headers, {"host": "127.0.0.1:9", "x-thing": "v1, v2", "authorization": "Bearer abc"})
        self.assertEqual(req.peer[0], "127.0.0.1")

    async def test_bad_requests_get_400_and_close(self):
        bad = [
            b"GARBAGE\r\n\r\n",
            b"GET / HTTP/2.0\r\nHost: x\r\n\r\n",
            b"GET  / HTTP/1.1\r\nHost: x\r\n\r\n",                 # two spaces
            b"get / HTTP/1.1\r\nHost: x\r\n\r\n",                  # method is case-sensitive
            b"GET http://evil/ HTTP/1.1\r\nHost: x\r\n\r\n",       # absolute-form target
            b"GET /a b HTTP/1.1\r\nHost: x\r\n\r\n",
            b"GET /\xff HTTP/1.1\r\nHost: x\r\n\r\n",              # non-ASCII request line
            b"GET / HTTP/1.1\nHost: x\n\n",                         # bare LF
            b"GET / HTTP/1.1\r\nHost x\r\n\r\n",                    # no colon
            b"GET / HTTP/1.1\r\nHost : x\r\n\r\n",                  # space before the colon
            b"GET / HTTP/1.1\r\nHost: x\r\n folded\r\n\r\n",       # obs-fold
            b"GET / HTTP/1.1\r\nHost: x\r\nHost: y\r\n\r\n",       # duplicate Host
            b"GET / HTTP/1.1\r\nHost: x\r\nOrigin: a\r\nOrigin: b\r\n\r\n",
            b"GET / HTTP/1.1\r\nHost: x\r\nX: a\x01b\r\n\r\n",     # control character in a value
            b"GET / HTTP/1.1\r\n\r\n",                              # HTTP/1.1 without Host
            b"\r\n",                                                # empty request line
        ]
        for data in bad:
            with self.subTest(data=data):
                c = await self.client()
                status, headers, _ = await c.http(data)
                self.assertEqual(status, 400)
                self.assertEqual(headers["connection"], "close")
        self.assertEqual(self.requests, [])

    async def test_header_too_large_gets_400(self):
        c = await self.client()
        status, _, _ = await c.http(b"GET / HTTP/1.1\r\nHost: x\r\nX-Big: " + b"a" * 9000 + b"\r\n\r\n")
        self.assertEqual(status, 400)
        c2 = await self.client()                                   # many small headers add up too
        many = b"".join(b"X-%d: %s\r\n" % (i, b"v" * 60) for i in range(150))
        status, _, _ = await c2.http(b"GET / HTTP/1.1\r\nHost: x\r\n" + many + b"\r\n")
        self.assertEqual(status, 400)
        self.assertEqual(self.requests, [])

    async def test_client_hanging_up_mid_request_is_harmless(self):
        c = await self.client()
        await c.send_raw(b"GET / HTTP/1.1\r\nHo")
        await c.aclose()
        c2 = await self.client()
        status, _, _ = await c2.http(b"GET /json HTTP/1.1\r\nHost: x\r\n\r\n")
        self.assertEqual(status, 200)

    async def test_response_header_injection_is_refused(self):
        class W:
            def write(self, data):
                raise AssertionError("nothing may be written")
        for headers in ({"X-A": "v\r\nSet-Cookie: x"}, {"X A": "v"}, {"X-A": "v\nb"}):
            with self.assertRaises(ValueError):
                await ws.write_response(W(), ws.Response(200, headers, b""))

    async def test_header_timeout(self):
        async def app(reader, writer):
            await ws.parse_http(reader, timeout=0.2)
        server, port = await ws.start_server(app)
        try:
            c = await Client.open(port)
            try:
                await c.send_raw(b"GET / HTTP/1.1\r\n")
                status, _ = await c.head()
                self.assertEqual(status, 408)
            finally:
                await c.aclose()
        finally:
            server.close()
            await server.wait_closed()


# ---------------------------------------------------------------------------------------------------- handshake
class TestHandshake(ServeCase):
    async def test_upgrade_answers_101_with_the_rfc_accept(self):
        c = await self.client()
        status, headers = await c.handshake(Sec_WebSocket_Extensions="permessage-deflate",
                                            Sec_WebSocket_Protocol="chat")
        self.assertEqual(status, 101)
        self.assertEqual(headers["sec-websocket-accept"], ACCEPT)
        self.assertEqual(headers["upgrade"].lower(), "websocket")
        self.assertEqual(headers["connection"].lower(), "upgrade")
        self.assertNotIn("sec-websocket-extensions", headers)      # no extensions, no subprotocols
        self.assertNotIn("sec-websocket-protocol", headers)
        self.assertEqual(ws.accept_key(KEY), ACCEPT)

    async def test_connection_header_token_list_and_case(self):
        c = await self.client()
        status, _ = await c.handshake(Connection="keep-alive, Upgrade", Upgrade="WebSocket")
        self.assertEqual(status, 101)

    async def test_bad_handshakes_get_400_and_close(self):
        k12 = base64.b64encode(b"x" * 12).decode()
        cases = [
            dict(drop=("Upgrade",)),
            dict(Upgrade="h2c"),
            dict(Connection="keep-alive"),
            dict(drop=("Connection",)),
            dict(Sec_WebSocket_Version="8"),
            dict(drop=("Sec-WebSocket-Version",)),
            dict(drop=("Sec-WebSocket-Key",)),
            dict(Sec_WebSocket_Key="not base64!!!!!!!!!!!!=="),
            dict(Sec_WebSocket_Key=k12),
            dict(Sec_WebSocket_Key=KEY + "AAAA"),
        ]
        for kw in cases:
            with self.subTest(kw=kw):
                c = await self.client()
                status, headers, _ = await c.http(upgrade_request(**kw))
                self.assertEqual(status, 400)
        for data in (upgrade_request().replace(b"GET", b"POST", 1),
                     upgrade_request().replace(b"HTTP/1.1", b"HTTP/1.0", 1)):
            c = await self.client()
            status, _, _ = await c.http(data)
            self.assertEqual(status, 400)
        self.assertEqual(self.sockets, [])


# ---------------------------------------------------------------------------------------------------- WebSocket
class TestMessages(ServeCase):
    async def test_masked_text_echo(self):
        c = await self.open_ws()
        for text in ("hello", "", "مرحبا بالعالم ✓", "x" * 70000):
            await c.send(TEXT, text.encode("utf-8"))
            fin, op, payload = await c.read_frame()
            self.assertEqual((fin, op), (True, TEXT))
            self.assertEqual(payload.decode("utf-8"), "echo:" + text)

    async def test_frames_sent_right_after_the_handshake(self):
        c = await self.client()
        await c.send_raw(upgrade_request() + frame(TEXT, b"early"))
        status, _ = await c.head()
        self.assertEqual(status, 101)
        self.assertEqual((await c.read_frame())[2], b"echo:early")

    async def test_fragmented_message_with_a_ping_in_the_middle(self):
        c = await self.open_ws()
        word = "مرحبا".encode("utf-8")                              # split inside a UTF-8 sequence
        await c.send(TEXT, b"one " + word[:3], fin=False)
        await c.send(PING, b"hb")
        await c.send(CONT, word[3:] + b" two", fin=False)
        await c.send(CONT, b" three")
        self.assertEqual(await c.read_frame(), (True, PONG, b"hb"))
        self.assertEqual((await c.read_frame())[2].decode("utf-8"), "echo:one مرحبا two three")

    async def test_ping_gets_pong_with_the_same_payload(self):
        c = await self.open_ws()
        await c.send(PING, b"\x00\x01payload")
        self.assertEqual(await c.read_frame(), (True, PONG, b"\x00\x01payload"))
        await c.send(PONG, b"unsolicited")                         # ignored
        await c.send(TEXT, b"still here")
        self.assertEqual((await c.read_frame())[2], b"echo:still here")

    async def test_server_ping(self):
        c = await self.open_ws()
        await c.send(TEXT, b"ping-me")
        fin, op, _ = await c.read_frame()
        self.assertEqual(op, PING)

    async def test_raised_max_message_applies_to_the_next_message(self):
        self.options = {"max_message": 64, "idle_timeout": 5.0}
        c = await self.open_ws()
        await c.send(TEXT, b"raise-limit")
        self.assertEqual((await c.read_frame())[2], b"raised")
        await c.send(TEXT, b"y" * 1000)
        self.assertEqual((await c.read_frame())[2], b"echo:" + b"y" * 1000)

    async def test_max_message_must_be_a_positive_int(self):
        c = await self.open_ws()
        sock = self.sockets[0]
        for bad in (0, -1, 1.5, "10", True):
            with self.assertRaises(ValueError, msg=bad):
                sock.max_message = bad
        await c.send(TEXT, b"ok")
        self.assertEqual((await c.read_frame())[2], b"echo:ok")


class TestClose(ServeCase):
    async def test_client_close_is_echoed_and_recv_returns_none(self):
        c = await self.open_ws()
        await c.send(CLOSE, struct.pack("!H", 1000) + b"bye")
        fin, op, payload = await c.read_frame()
        self.assertEqual((op, struct.unpack("!H", payload[:2])[0]), (CLOSE, 1000))
        self.assertEqual(await asyncio.wait_for(c.r.read(), T), b"")
        await c.aclose()
        self.assertEqual(await self.server_close_code(), 1000)
        self.assertEqual(self.sockets[0].close_reason, "bye")
        self.assertIsNone(await self.sockets[0].recv())
        with self.assertRaises(ws.ConnectionClosed):
            await self.sockets[0].send("late")

    async def test_empty_close(self):
        c = await self.open_ws()
        await c.send(CLOSE, b"")
        fin, op, payload = await c.read_frame()
        self.assertEqual((op, payload), (CLOSE, b""))
        self.assertEqual(await asyncio.wait_for(c.r.read(), T), b"")
        await c.aclose()
        self.assertEqual(await self.server_close_code(), 1005)

    async def test_server_initiated_close(self):
        c = await self.open_ws()
        await c.send(TEXT, b"close-me")
        self.assertEqual(await c.expect_close(4000), "bye from server")
        self.assertEqual(await self.server_close_code(), 4000)

    async def test_close_from_another_task_while_recv_waits(self):
        c = await self.open_ws()
        await c.send(TEXT, b"hi")
        await c.read_frame()
        sock = self.sockets[0]
        closing = asyncio.create_task(sock.close(1001, "going away"))
        self.assertEqual(await c.expect_close(1001), "going away")
        await asyncio.wait_for(closing, T)
        self.assertEqual(await self.server_close_code(), 1001)
        self.assertTrue(sock.closed)

    async def test_close_code_and_reason_are_checked(self):
        c = await self.open_ws()
        sock = self.sockets[0]
        for code in (999, 1005, 1006, 1015, 2999, 5000):
            with self.assertRaises(ValueError, msg=code):
                await sock.close(code)
        closing = asyncio.create_task(sock.close(1000, "é" * 200))    # long reason is cut to <= 123 bytes
        reason = await c.expect_close(1000)
        await asyncio.wait_for(closing, T)
        self.assertEqual(reason, "é" * 61)


class TestProtocolErrors(ServeCase):
    async def check(self, data: bytes, code: int):
        c = await self.open_ws()
        await c.send_raw(data)
        await c.expect_close(code)
        self.assertEqual(await self.server_close_code(), code)

    async def test_unmasked_frame_is_1002(self):
        await self.check(frame(TEXT, b"hi", mask=False), 1002)

    async def test_rsv_bits_are_1002(self):
        for rsv in (1, 2, 4):
            with self.subTest(rsv=rsv):
                await self.check(frame(TEXT, b"hi", rsv=rsv), 1002)

    async def test_binary_is_1003(self):
        await self.check(frame(BINARY, b"\x00\x01"), 1003)

    async def test_bad_utf8_is_1007(self):
        await self.check(frame(TEXT, b"\xc3\x28"), 1007)
        await self.check(frame(TEXT, b"ok", fin=False) + frame(CONT, b"\xff"), 1007)

    async def test_unknown_opcodes_are_1002(self):
        for op in (3, 7, 0xB, 0xF):
            with self.subTest(op=op):
                await self.check(frame(op, b""), 1002)

    async def test_control_frame_rules(self):
        await self.check(frame(PING, b"x" * 126), 1002)                    # > 125 bytes
        await self.check(frame(PING, b"x", fin=False), 1002)               # fragmented control frame
        await self.check(frame(CLOSE, b"\x03"), 1002)                       # 1-byte close payload
        await self.check(frame(CLOSE, struct.pack("!H", 1005)), 1002)       # code that must not be sent
        await self.check(frame(CLOSE, struct.pack("!H", 1000) + b"\xff"), 1007)

    async def test_fragmentation_order(self):
        await self.check(frame(CONT, b"orphan"), 1002)                      # continuation without a start
        await self.check(frame(TEXT, b"a", fin=False) + frame(TEXT, b"b"), 1002)

    async def test_non_minimal_and_63_bit_lengths_are_1002(self):
        await self.check(frame(TEXT, b"abc", ext=16), 1002)
        await self.check(frame(TEXT, b"abc", ext=64), 1002)
        c = await self.open_ws()                                            # MSB of the 64-bit length set
        await c.send_raw(bytes([0x81, 0xFF]) + struct.pack("!Q", 1 << 63))
        await c.expect_close(1002)
        self.assertEqual(await self.server_close_code(), 1002)


class TestSizeAndIdle(ServeCase):
    options = {"max_message": 1000, "idle_timeout": 5.0}

    async def test_single_frame_over_the_cap_is_1009_before_reading_it(self):
        c = await self.open_ws()
        await c.send_raw(bytes([0x81, 0xFF]) + struct.pack("!Q", 1 << 40))   # announces 1 TiB, sends nothing
        await c.expect_close(1009)
        self.assertEqual(await self.server_close_code(), 1009)

    async def test_fragments_adding_up_over_the_cap_are_1009(self):
        c = await self.open_ws()
        await c.send_raw(frame(TEXT, b"a" * 600, fin=False))
        await c.send_raw(frame(CONT, b"", length=600)[:8])                     # header (+mask) of the 2nd part only
        await c.expect_close(1009)
        self.assertEqual(await self.server_close_code(), 1009)

    async def test_many_empty_fragments_are_one_message(self):
        c = await self.open_ws()
        await c.send_raw(frame(TEXT, b"a", fin=False) + frame(CONT, b"", fin=False) * 300 + frame(CONT, b"b"))
        self.assertEqual((await c.read_frame())[2], b"echo:ab")

    async def test_exactly_the_cap_is_fine(self):
        c = await self.open_ws()
        await c.send(TEXT, b"z" * 600, fin=False)
        await c.send(CONT, b"z" * 400)
        self.assertEqual(len((await c.read_frame())[2]), 1000 + len("echo:"))


class TestIdle(ServeCase):
    options = {"max_message": 1 << 20, "idle_timeout": 0.3}

    async def test_silent_peer_is_pinged_then_closed_1001(self):
        c = await self.open_ws()
        t0 = time.monotonic()
        fin, op, _ = await c.read_frame()
        self.assertEqual(op, PING)
        await c.expect_close(1001)
        self.assertLess(time.monotonic() - t0, 2.0)
        self.assertEqual(await self.server_close_code(), 1001)

    async def test_peer_answering_pings_stays_connected(self):
        c = await self.open_ws()
        t0 = time.monotonic()
        while time.monotonic() - t0 < 0.6:                                    # twice idle_timeout
            fin, op, payload = await c.read_frame()
            self.assertEqual(op, PING)
            await c.send(PONG, payload)
        await c.send(TEXT, b"alive")
        while True:
            fin, op, payload = await c.read_frame()
            if op == TEXT:
                break
        self.assertEqual(payload, b"echo:alive")

    async def test_stalled_frame_is_closed(self):
        c = await self.open_ws()
        await c.send_raw(frame(TEXT, b"abcdef")[:4])                           # half a frame, then silence
        await c.expect_close(1001)


if __name__ == "__main__":
    unittest.main()
