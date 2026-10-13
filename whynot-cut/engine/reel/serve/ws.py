"""Stdlib HTTP/1.1 + RFC 6455 WebSocket transport for `reel serve` (3.0 T6.2).

The hash-locked runtime has no `websockets` package, so this is a small, strict server written against the RFCs and
kept behind a narrow interface (start_server, parse_http, Request, Response, json_response, write_response, upgrade,
WebSocket) so it can be swapped for `websockets` later in this one module.

Rules it enforces, all bounded:
  * listens on the loopback pair only, the same port on 127.0.0.1 AND ::1 (3.0 network-"all" closure: Premiere's UXP
    allows only `ws://localhost:*` / `http://localhost:*`, and Windows resolves `localhost` to ::1 first, so a
    127.0.0.1-only daemon cost every panel connect a ~2 s fallback; docs/adobe/uxp-parity.md, spike 0.1.6). Never
    0.0.0.0, ::, or a LAN address; any `host` argument other than HOST is a ValueError. When IPv6 is unavailable
    (no AF_INET6, or ::1 not configured) it says so once in the log and serves on 127.0.0.1 alone; ::1 being IN USE
    is never that case (another process would get the panel's localhost connects), so it picks another free port or,
    for a fixed port, fails. On Windows both sockets are bound with SO_EXCLUSIVEADDRUSE so no other local process
    can bind the same address and port; the ::1 socket is IPV6_V6ONLY;
  * request head: one request line `METHOD SP /origin-form SP HTTP/1.x`, CRLF line ends, header names are tokens, no
    obs-fold, no control characters, security-relevant headers (Host, Origin, Authorization, Sec-WebSocket-*, ...)
    may not repeat, HTTP/1.1 needs Host, at most `limit` bytes and MAX_HEADERS lines within HEADER_TIMEOUT seconds;
    anything else is HttpError(400) (408 on the timeout), answered by the connection wrapper, then closed;
  * every HTTP response carries Content-Length and `Connection: close`; there is no keep-alive and no request body
    (any Transfer-Encoding, or a Content-Length other than 0, is 400);
  * WebSocket: GET + HTTP/1.1, `Upgrade: websocket`, `Connection` lists `upgrade`, `Sec-WebSocket-Version: 13`, a
    24-character base64 `Sec-WebSocket-Key` of 16 bytes; no extensions and no subprotocols are ever accepted;
  * frames: client frames masked (else 1002), RSV bits clear (1002), known opcodes (1002), binary refused (1003),
    text valid UTF-8 (1007), fragments reassembled in order (1002 otherwise), control frames <= 125 bytes and never
    fragmented (1002), lengths minimally encoded with the 64-bit MSB clear (1002), each message capped at
    `max_message` bytes, checked from the announced length before any payload is read (1009);
  * idle: a peer silent for idle_timeout/2 gets a ping; silent for another idle_timeout/2 it is closed with 1001; a
    frame that stalls half-way for idle_timeout is closed with 1001; a write that cannot drain within idle_timeout
    aborts the connection;
  * closing: the close frame goes out, then the server half-closes and discards what the peer still sends (at most
    LINGER_BYTES, at most CLOSE_TIMEOUT seconds) before closing the socket, so the peer reads the close frame instead
    of a TCP reset.
Nothing here logs request contents (tokens travel in headers and messages).
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import errno
import hashlib
import http
import json
import logging
import re
import socket
import struct
from dataclasses import dataclass, field

__all__ = ["HOST", "HOST6", "LOOPBACK", "MAX_MESSAGE", "IDLE_TIMEOUT", "HttpError", "ConnectionClosed", "Request", "Response",
           "json_response", "parse_http", "write_response", "upgrade", "accept_key", "WebSocket", "LoopbackServer", "start_server"]

log = logging.getLogger(__name__)

HOST = "127.0.0.1"
HOST6 = "::1"
LOOPBACK = (HOST, HOST6)       # every address reel serve may listen on; nothing else, ever
BIND_TRIES = 20                # free-port picks tried when ::1 of the picked port is taken
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
HEADER_LIMIT = 8192            # bytes of request line + headers
HEADER_TIMEOUT = 10.0          # seconds to receive the whole request head
MAX_HEADERS = 100
MAX_MESSAGE = 1 << 20          # default per-message cap (the app lowers it pre-auth, raises it post-auth)
IDLE_TIMEOUT = 60.0
CLOSE_TIMEOUT = 1.0            # how long a closing connection waits for the peer
LINGER_BYTES = 1 << 16         # how much a closing connection reads and discards at most
STREAM_LIMIT = 1 << 16         # StreamReader line limit (parse_http applies its own, smaller, limit)

_METHOD = re.compile(r"[A-Z]{1,16}")
_TARGET = re.compile(r"/[\x21-\x7e]{0,4095}")                  # origin-form, visible ASCII only
_TOKEN = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]{1,64}")
_BAD_VALUE = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")             # control characters except HT
_VERSIONS = ("HTTP/1.1", "HTTP/1.0")
_SINGLETONS = frozenset({"host", "origin", "authorization", "upgrade", "content-length", "transfer-encoding",
                         "sec-websocket-key", "sec-websocket-version"})

OP_CONT, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA
_OPEN, _CLOSING, _CLOSED = "open", "closing", "closed"


class HttpError(Exception):
    """A request the transport refuses; the connection wrapper answers `status` and closes."""

    def __init__(self, status: int = 400, reason: str = "bad request"):
        super().__init__(f"{status} {reason}")
        self.status = status
        self.reason = reason


class ConnectionClosed(ConnectionError):
    """send/ping on a WebSocket that is closing or closed."""

    def __init__(self, code: int | None = None):
        super().__init__(f"websocket closed ({code})")
        self.code = code


class _ProtocolError(Exception):
    def __init__(self, code: int, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


# ------------------------------------------------------------------------------------------------------- HTTP
@dataclass(frozen=True)
class Request:
    method: str
    path: str
    version: str
    headers: dict[str, str]                 # lower-cased names; repeated non-singleton headers joined with ", "
    peer: tuple | None = None


@dataclass
class Response:
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""


def json_response(status: int, obj, headers: dict[str, str] | None = None) -> Response:
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return Response(status, {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store",
                             **(headers or {})}, body)


def _error_response(status: int, reason: str, extra: dict[str, str] | None = None) -> Response:
    return Response(status, {"Content-Type": "text/plain; charset=utf-8", **(extra or {})}, reason.encode("utf-8"))


async def parse_http(reader: asyncio.StreamReader, limit: int = HEADER_LIMIT, *, peer: tuple | None = None,
                     timeout: float = HEADER_TIMEOUT) -> Request:
    """Read and check one request head. Raises HttpError (400; 408 when it takes longer than `timeout`)."""
    if peer is None:
        transport = getattr(reader, "_transport", None)
        peer = transport.get_extra_info("peername") if transport is not None else None
    try:
        async with asyncio.timeout(timeout):
            lines = await _read_head(reader, limit)
    except TimeoutError:
        raise HttpError(408, "request head timeout") from None
    try:
        start = lines[0].decode("ascii")
    except UnicodeDecodeError:
        raise HttpError(400, "non-ASCII request line") from None
    parts = start.split(" ")
    if (len(parts) != 3 or not _METHOD.fullmatch(parts[0]) or not _TARGET.fullmatch(parts[1])
            or parts[2] not in _VERSIONS):
        raise HttpError(400, "bad request line")
    method, path, version = parts
    headers: dict[str, str] = {}
    for raw in lines[1:]:
        text = raw.decode("latin-1")
        name, sep, value = text.partition(":")
        if not sep or not _TOKEN.fullmatch(name):          # also refuses obs-fold and space before the colon
            raise HttpError(400, "bad header line")
        value = value.strip(" \t")
        if _BAD_VALUE.search(value):
            raise HttpError(400, "control character in a header")
        key = name.lower()
        if key in headers:
            if key in _SINGLETONS:
                raise HttpError(400, f"repeated {key} header")
            headers[key] += ", " + value
        else:
            headers[key] = value
    if version == "HTTP/1.1" and "host" not in headers:
        raise HttpError(400, "missing Host header")
    if "transfer-encoding" in headers:                    # no request has a body: one never read could be smuggled
        raise HttpError(400, "Transfer-Encoding is not accepted")
    if headers.get("content-length", "0") != "0":
        raise HttpError(400, "a request body is not accepted")
    return Request(method, path, version, headers, peer)


async def _read_head(reader: asyncio.StreamReader, limit: int) -> list[bytes]:
    lines: list[bytes] = []
    total = 0
    while True:
        try:
            line = await reader.readuntil(b"\n")
        except asyncio.IncompleteReadError:
            raise HttpError(400, "incomplete request") from None
        except asyncio.LimitOverrunError:
            raise HttpError(400, "request head too large") from None
        total += len(line)
        if total > limit:
            raise HttpError(400, "request head too large")
        if not line.endswith(b"\r\n"):
            raise HttpError(400, "lines must end with CRLF")
        line = line[:-2]
        if not line:
            if not lines:
                raise HttpError(400, "empty request line")
            return lines
        if len(lines) > MAX_HEADERS:
            raise HttpError(400, "too many headers")
        lines.append(line)


async def write_response(writer: asyncio.StreamWriter, response: Response) -> None:
    """Write a complete response (Content-Length, Connection: close) and half-close; the connection is finished.
    Header names must be tokens and values free of control characters (ValueError, nothing written)."""
    body = response.body.encode("utf-8") if isinstance(response.body, str) else bytes(response.body)
    try:
        phrase = http.HTTPStatus(response.status).phrase
    except ValueError:
        phrase = "Unknown"
    head = [f"HTTP/1.1 {int(response.status)} {phrase}"]
    for name, value in response.headers.items():
        value = str(value)
        if not _TOKEN.fullmatch(name) or _BAD_VALUE.search(value):
            raise ValueError(f"refused response header {name!r}")
        if name.lower() not in ("content-length", "connection", "transfer-encoding"):
            head.append(f"{name}: {value}")
    head += [f"Content-Length: {len(body)}", "Connection: close", "", ""]
    writer.write("\r\n".join(head).encode("latin-1") + body)
    await _drain(writer, HEADER_TIMEOUT)
    if writer.can_write_eof():
        writer.write_eof()


async def _drain(writer: asyncio.StreamWriter, timeout: float) -> None:
    try:
        async with asyncio.timeout(timeout):
            await writer.drain()
    except TimeoutError:
        writer.transport.abort()
        raise ConnectionClosed(1006) from None
    except (ConnectionError, OSError):
        raise ConnectionClosed(1006) from None


async def _linger_close(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, timeout: float) -> None:
    """Half-close, read and discard what the peer still sends (bounded), then close the socket."""
    try:
        if not writer.is_closing():
            if writer.can_write_eof():
                writer.write_eof()
            async with asyncio.timeout(timeout):
                budget = LINGER_BYTES
                while budget > 0:
                    chunk = await reader.read(min(budget, 16384))
                    if not chunk:
                        break
                    budget -= len(chunk)
    except (TimeoutError, ConnectionError, OSError, RuntimeError):
        pass
    finally:
        writer.close()
        try:
            async with asyncio.timeout(timeout):
                await writer.wait_closed()
        except TimeoutError:
            writer.transport.abort()
        except (ConnectionError, OSError):
            pass


# -------------------------------------------------------------------------------------------------- handshake
def accept_key(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + WS_GUID).encode("ascii")).digest()).decode("ascii")


def _tokens(value: str) -> set[str]:
    return {t.strip().lower() for t in value.split(",") if t.strip()}


def _handshake_problem(request: Request) -> str | None:
    h = request.headers
    if request.method != "GET" or request.version != "HTTP/1.1":
        return "websocket handshake needs GET over HTTP/1.1"
    if "websocket" not in _tokens(h.get("upgrade", "")):
        return "Upgrade: websocket required"
    if "upgrade" not in _tokens(h.get("connection", "")):
        return "Connection: upgrade required"
    if h.get("sec-websocket-version", "") != "13":
        return "Sec-WebSocket-Version 13 required"
    key = h.get("sec-websocket-key", "")
    try:
        if len(key) != 24 or len(base64.b64decode(key, validate=True)) != 16:
            return "bad Sec-WebSocket-Key"
    except (binascii.Error, ValueError):
        return "bad Sec-WebSocket-Key"
    return None


async def upgrade(request: Request, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, *,
                  max_message: int = MAX_MESSAGE, idle_timeout: float = IDLE_TIMEOUT) -> WebSocket | None:
    """Complete the RFC 6455 handshake and return the WebSocket, or answer 400 and return None."""
    problem = _handshake_problem(request)
    if problem:
        extra = {"Sec-WebSocket-Version": "13"} if "Version" in problem else None
        with contextlib.suppress(ConnectionError, OSError):
            await write_response(writer, _error_response(400, problem, extra))
        return None
    sock = WebSocket(reader, writer, max_message=max_message, idle_timeout=idle_timeout)
    writer.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                  f"Sec-WebSocket-Accept: {accept_key(request.headers['sec-websocket-key'])}\r\n\r\n").encode("ascii"))
    await _drain(writer, sock.idle_timeout)
    return sock


# -------------------------------------------------------------------------------------------------- WebSocket
def _valid_code(code: int) -> bool:
    return 1000 <= code <= 1003 or 1007 <= code <= 1014 or 3000 <= code <= 4999


def _unmask(data: bytes, mask: bytes) -> bytes:
    n = len(data)
    key = (mask * (n // 4 + 1))[:n]
    return (int.from_bytes(data, "little") ^ int.from_bytes(key, "little")).to_bytes(n, "little")


def _close_payload(code: int, reason: str) -> bytes:
    raw = reason.encode("utf-8")[:123].decode("utf-8", "ignore").encode("utf-8")
    return struct.pack("!H", code) + raw


class WebSocket:
    """A server-side RFC 6455 connection. One task may call recv() at a time; send/ping/close may come from others."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, *,
                 max_message: int = MAX_MESSAGE, idle_timeout: float = IDLE_TIMEOUT):
        if isinstance(idle_timeout, bool) or not isinstance(idle_timeout, (int, float)) or idle_timeout <= 0:
            raise ValueError("idle_timeout must be a positive number of seconds")
        self._reader, self._writer = reader, writer
        self.max_message = max_message
        self.idle_timeout = float(idle_timeout)
        self.close_code: int | None = None
        self.close_reason = ""
        self._state = _OPEN
        self._reading = False
        self._wlock = asyncio.Lock()
        self._done = asyncio.Event()

    @property
    def max_message(self) -> int:
        return self._max_message

    @max_message.setter
    def max_message(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("max_message must be a positive int")
        self._max_message = value

    @property
    def closed(self) -> bool:
        return self._state != _OPEN

    # ---------------------------------------------------------------------------------------------- public
    async def recv(self) -> str | None:
        """The next text message, or None once the connection is closed (by either side, an error or idle)."""
        if self._reading:
            raise RuntimeError("recv() is already running on this WebSocket")
        if self._state == _CLOSED:
            return None
        self._reading = True
        try:
            return await self._recv()
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            await self._abort()
            return None
        finally:
            self._reading = False

    async def send(self, text: str) -> None:
        if not isinstance(text, str):
            raise TypeError("send() takes str")
        if self._state != _OPEN:
            raise ConnectionClosed(self.close_code)
        await self._send_frame(OP_TEXT, text.encode("utf-8"))

    async def ping(self, payload: bytes = b"") -> None:
        if len(payload) > 125:
            raise ValueError("ping payload is at most 125 bytes")
        if self._state != _OPEN:
            raise ConnectionClosed(self.close_code)
        await self._send_frame(OP_PING, bytes(payload))

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Send a close frame, wait (bounded) for the peer's answer, close the socket. Idempotent."""
        if isinstance(code, bool) or not isinstance(code, int) or not _valid_code(code):
            raise ValueError(f"close code {code!r} may not be sent")
        if self._state != _OPEN:
            if self._reading:
                await self._wait_done()
            return
        self._state = _CLOSING
        self.close_code, self.close_reason = code, reason
        with contextlib.suppress(ConnectionClosed):
            await self._send_frame(OP_CLOSE, _close_payload(code, reason))
        if self._reading:                 # the recv() task reads the peer's close and finishes the connection
            await self._wait_done()
        else:
            await self._finish()

    def abort(self) -> None:
        """Drop the connection now, without a close handshake (a peer that does not answer while the server stops).
        A running recv() then returns None."""
        if self.close_code is None:
            self.close_code = 1006
        self._writer.transport.abort()

    # ---------------------------------------------------------------------------------------------- internals
    async def _wait_done(self) -> None:
        try:
            async with asyncio.timeout(CLOSE_TIMEOUT * 2):
                await self._done.wait()
        except TimeoutError:
            self._writer.transport.abort()

    async def _recv(self) -> str | None:
        buf: bytearray | None = None      # the message being reassembled: one buffer, never above max_message
        pinged = False
        try:
            while self._state != _CLOSED:
                try:
                    async with asyncio.timeout(self.idle_timeout / 2):
                        head = await self._reader.readexactly(2)
                except TimeoutError:
                    if pinged or self._state != _OPEN:
                        raise _ProtocolError(1001, "idle timeout") from None
                    pinged = True
                    await self._send_frame(OP_PING, b"")
                    continue
                pinged = False
                async with asyncio.timeout(self.idle_timeout):
                    fin, opcode, payload = await self._read_frame(head, buf is not None, len(buf or b""))
                if opcode == OP_CLOSE:
                    await self._on_close(payload)
                    return None
                if opcode == OP_PING:
                    if self._state == _OPEN:
                        await self._send_frame(OP_PONG, payload)
                    continue
                if opcode == OP_PONG:
                    continue
                if opcode == OP_TEXT:
                    buf = bytearray(payload)
                else:
                    buf += payload
                if fin:
                    data, buf = buf, None
                    try:
                        text = data.decode("utf-8")
                    except UnicodeDecodeError:
                        raise _ProtocolError(1007, "invalid UTF-8 in a text message") from None
                    if self._state == _OPEN:          # after our close frame, data is discarded (RFC 6455 1.4)
                        return text
        except _ProtocolError as e:
            await self._fail(e.code, e.reason)
        except TimeoutError:
            await self._fail(1001, "idle timeout")
        return None

    async def _read_frame(self, head: bytes, in_message: bool, size: int) -> tuple[bool, int, bytes]:
        b0, b1 = head
        fin, opcode, length = bool(b0 & 0x80), b0 & 0x0F, b1 & 0x7F
        if b0 & 0x70:
            raise _ProtocolError(1002, "reserved bits set")
        if not b1 & 0x80:
            raise _ProtocolError(1002, "client frames must be masked")
        if opcode >= 0x8:
            if opcode not in (OP_CLOSE, OP_PING, OP_PONG):
                raise _ProtocolError(1002, "unknown opcode")
            if not fin:
                raise _ProtocolError(1002, "fragmented control frame")
            if length > 125:
                raise _ProtocolError(1002, "control frame over 125 bytes")
        else:
            if opcode == OP_BINARY:
                raise _ProtocolError(1003, "binary messages are not accepted")
            if opcode not in (OP_CONT, OP_TEXT):
                raise _ProtocolError(1002, "unknown opcode")
            if opcode == OP_CONT and not in_message:
                raise _ProtocolError(1002, "continuation without a message")
            if opcode == OP_TEXT and in_message:
                raise _ProtocolError(1002, "new message before the last one finished")
            if length == 126:
                length = struct.unpack("!H", await self._reader.readexactly(2))[0]
                if length < 126:
                    raise _ProtocolError(1002, "length not minimally encoded")
            elif length == 127:
                length = struct.unpack("!Q", await self._reader.readexactly(8))[0]
                if length >> 63:
                    raise _ProtocolError(1002, "64-bit length with the high bit set")
                if length <= 0xFFFF:
                    raise _ProtocolError(1002, "length not minimally encoded")
            if size + length > self._max_message:
                raise _ProtocolError(1009, "message too big")
        mask = await self._reader.readexactly(4)
        payload = _unmask(await self._reader.readexactly(length), mask) if length else b""
        return fin, opcode, payload

    async def _on_close(self, payload: bytes) -> None:
        if len(payload) == 1:
            raise _ProtocolError(1002, "1-byte close payload")
        if payload:
            code = struct.unpack("!H", payload[:2])[0]
            if not _valid_code(code):
                raise _ProtocolError(1002, "invalid close code")
            try:
                reason = payload[2:].decode("utf-8")
            except UnicodeDecodeError:
                raise _ProtocolError(1007, "invalid UTF-8 in the close reason") from None
        else:
            code, reason = 1005, ""
        if self._state == _OPEN:          # the peer started the close: answer it with the same code
            self._state = _CLOSING
            self.close_code, self.close_reason = code, reason
            with contextlib.suppress(ConnectionClosed):
                await self._send_frame(OP_CLOSE, payload[:2])
        await self._finish()

    async def _fail(self, code: int, reason: str) -> None:
        if self._state == _OPEN:
            self._state = _CLOSING
            self.close_code, self.close_reason = code, reason
            with contextlib.suppress(ConnectionClosed):
                await self._send_frame(OP_CLOSE, _close_payload(code, reason))
        await self._finish()

    async def _finish(self) -> None:
        if self._state != _CLOSED:
            self._state = _CLOSED
            await _linger_close(self._reader, self._writer, CLOSE_TIMEOUT)
        self._done.set()

    async def _abort(self) -> None:
        if self.close_code is None:
            self.close_code = 1006
        self._state = _CLOSED
        self._writer.close()
        with contextlib.suppress(ConnectionError, OSError, TimeoutError):
            async with asyncio.timeout(CLOSE_TIMEOUT):
                await self._writer.wait_closed()
        self._done.set()

    async def _send_frame(self, opcode: int, payload: bytes) -> None:
        n = len(payload)
        if n < 126:
            head = struct.pack("!BB", 0x80 | opcode, n)
        elif n <= 0xFFFF:
            head = struct.pack("!BBH", 0x80 | opcode, 126, n)
        else:
            head = struct.pack("!BBQ", 0x80 | opcode, 127, n)
        async with self._wlock:
            if self._writer.is_closing():
                raise ConnectionClosed(self.close_code or 1006)
            self._writer.write(head)
            self._writer.write(payload)
            await _drain(self._writer, self.idle_timeout)


# ------------------------------------------------------------------------------------------------------ server
async def _serve_connection(handler, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        await handler(reader, writer)
    except HttpError as e:
        with contextlib.suppress(Exception):
            await write_response(writer, _error_response(e.status, e.reason))
    except (ConnectionError, OSError, asyncio.IncompleteReadError):
        pass
    except Exception as e:                       # never the message: it may hold a token
        log.warning("reel serve: connection handler failed (%s)", type(e).__name__)
    finally:
        await _linger_close(reader, writer, CLOSE_TIMEOUT)


def _errnos(*names: str) -> frozenset:
    return frozenset(v for v in (getattr(errno, n, None) for n in names) if isinstance(v, int))


# ::1 cannot exist here: IPv6 is off, or the loopback address is not configured. Anything else (in use, access
# denied) is NOT "unavailable" and never falls back to 127.0.0.1 alone.
_V6_UNAVAILABLE = _errnos("EAFNOSUPPORT", "EPFNOSUPPORT", "EPROTONOSUPPORT", "EADDRNOTAVAIL",
                          "WSAEAFNOSUPPORT", "WSAEPFNOSUPPORT", "WSAEPROTONOSUPPORT", "WSAEADDRNOTAVAIL")
_IN_USE = _errnos("EADDRINUSE", "EACCES", "WSAEADDRINUSE", "WSAEACCES")
_v6_noted = False              # the "IPv6 unavailable" line is logged once per process


def _bind(family: int, host: str, port: int) -> socket.socket:
    """A TCP socket bound to (host, port), exclusive on Windows, IPV6_V6ONLY for IPv6. Closed again on any error."""
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        if family == socket.AF_INET6 and hasattr(socket, "IPV6_V6ONLY"):
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind((host, port))
    except BaseException:
        sock.close()
        raise
    return sock


def _v6_unavailable(e: OSError) -> bool:
    return e.errno in _V6_UNAVAILABLE or getattr(e, "winerror", None) in _V6_UNAVAILABLE


def _note_v6_unavailable(why: str) -> None:
    global _v6_noted
    if not _v6_noted:
        _v6_noted = True
        log.warning("reel serve: IPv6 loopback ::1 is unavailable (%s); listening on 127.0.0.1 only", why)


def _bind_loopback(port: int) -> list:
    """[127.0.0.1 socket, ::1 socket] on one port (just the first when IPv6 is unavailable). Port 0 picks a free
    port on 127.0.0.1 and retries (BIND_TRIES) when ::1 of that port is taken; a fixed port taken on ::1 raises."""
    tries = BIND_TRIES if port == 0 else 1
    for attempt in range(tries):
        s4 = _bind(socket.AF_INET, HOST, port)
        picked = s4.getsockname()[1]
        if not socket.has_ipv6:
            _note_v6_unavailable("no IPv6 support in this Python")
            return [s4]
        try:
            s6 = _bind(socket.AF_INET6, HOST6, picked)
        except OSError as e:
            if _v6_unavailable(e):
                _note_v6_unavailable(type(e).__name__ + (f" {e.errno}" if e.errno is not None else ""))
                return [s4]
            s4.close()
            if attempt + 1 < tries and (e.errno in _IN_USE or getattr(e, "winerror", None) in _IN_USE):
                continue                               # ::1 of this free port is someone else's: pick another
            raise
        except BaseException:
            s4.close()
            raise
        return [s4, s6]
    raise OSError(errno.EADDRINUSE, "no free port on both 127.0.0.1 and ::1")   # unreachable: the loop raises


class LoopbackServer:
    """The one listener of reel serve: one asyncio.Server per loopback socket (asyncio takes one socket per server),
    behaving as one server: `sockets`, `close()`, `wait_closed()`, `is_serving()`."""

    def __init__(self, servers):
        self._servers = tuple(servers)

    @property
    def sockets(self) -> tuple:
        return tuple(sock for srv in self._servers for sock in srv.sockets)

    @property
    def addresses(self) -> tuple:
        """("127.0.0.1", "::1") or ("127.0.0.1",): the hosts actually listened on."""
        return tuple(sock.getsockname()[0] for sock in self.sockets)

    def is_serving(self) -> bool:
        return any(srv.is_serving() for srv in self._servers)

    def close(self) -> None:
        for srv in self._servers:
            srv.close()

    async def wait_closed(self) -> None:
        for srv in self._servers:
            await srv.wait_closed()


async def start_server(handler, host: str = HOST, port: int = 0) -> tuple[LoopbackServer, int]:
    """Listen on `port` (0 = a free port) on 127.0.0.1 and ::1 (127.0.0.1 alone when IPv6 is unavailable; see the
    module doc); `handler(reader, writer)` runs per connection. `host` exists only to be refused: anything but HOST is
    a ValueError. A HttpError the handler raises is answered with its status; the connection is always closed
    afterwards. Returns (server, port)."""
    if host != HOST:
        raise ValueError(f"reel serve listens on the loopback pair {LOOPBACK} only, not {host!r}")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError(f"bad port {port!r}")
    if not callable(handler):
        raise TypeError("handler must be a coroutine function (reader, writer)")
    socks = _bind_loopback(port)

    async def on_connect(reader, writer):
        await _serve_connection(handler, reader, writer)

    servers = []
    try:
        for sock in socks:
            servers.append(await asyncio.start_server(on_connect, sock=sock, limit=STREAM_LIMIT))
    except BaseException:
        for srv in servers:
            srv.close()
        for sock in socks[len(servers):]:
            sock.close()
        raise
    server = LoopbackServer(servers)
    return server, server.sockets[0].getsockname()[1]
