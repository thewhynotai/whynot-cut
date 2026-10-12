"""The `reel serve` application (3.0 T6.2): the per-connection handler on top of serve/ws.py.

HTTP (every request): the connection cap first (one global cap, MAX_CONNECTIONS; excess -> 503 + audit. There is no
per-address cap: on loopback every peer is 127.0.0.1, so it would only be a second, smaller global cap), then the
request head (ws.parse_http; a refused head is answered 400/408 by ws's connection wrapper), then every Origin seen is
audit-logged with its raw value (before any other check, so a rebinding attempt's Origin is on record too), then the
Host gate (missing -> 400, anything but 127.0.0.1:<port> / localhost:<port> -> 403 + audit) and the Origin gate (a
browser Origin -> 403 + audit). Then:
    GET /status    needs `Authorization: Bearer <token>` (401 otherwise); answers {protocol, daemon_version, pid, port,
                   sessions: [{kind, host, hostVersion, capabilities}], uptime_s}
    /session       the WebSocket session (below)
    anything else  404
Session: the upgrade caps messages at 16 KiB until the client is authenticated. The first message must be a valid
`hello` within `hello_timeout` (3 s) whose token is 64 lowercase hex characters and equals the engine token
(constant-time); anything else is `error{code: auth}` + close 1008 + audit. After `welcome` the cap is 8 MiB and every
message is parsed and validated against its type in session.schema.json (`schema` / `unknown_type` errors keep the
connection). Rate limits are per session and by type: what a client asks for (command, snapshot, the intents, cancel,
and anything invalid) is limited (`error{rate}` with the message's id); a host's `result` is never limited (dropping it
would leave the requester waiting until expiry); `progress` over its own budget is dropped silently. `command` runs in
its own task through the Router (UXP panel or CEP file queue, a Context per request); `result` / `progress` from a host
session answer the commands sent to it; the panel intents approve / request_changes / rebuild get a `reply` saying they
are not implemented in the serve core yet; `snapshot` gets a `state` echoing its id; `cancel` is forwarded to the panel running the command. When a session ends, the commands
waiting on it fail with a clear error and its own running commands are cancelled; a reconnect is a new hello.
The token is never logged, never echoed and never read from a URL.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import secrets
import time

from lib import common

from . import messages, security, ws
from .adapters import FileQueueAdapter, HostLink
from .router import Router

__all__ = ["App", "Session", "PRE_AUTH_MAX", "POST_AUTH_MAX", "HELLO_TIMEOUT"]

log = logging.getLogger(__name__)

PRE_AUTH_MAX = 16 * 1024
POST_AUTH_MAX = 8 * 1024 * 1024
HELLO_TIMEOUT = 3.0
MAX_CONNECTIONS = 32
RATE = (20.0, 60)                  # messages per second per session, burst
MAX_RUNNING = 16                   # commands one session may have running at once
OFFLOAD_BYTES = 256 * 1024         # messages above this are parsed and validated in a worker thread
AUTH_REFUSED = "The first message must be a hello with the engine token from engine.json."
NOT_YET = "not implemented in the serve core yet"
NOT_YET_HOW = ("Use the reel CLI for this step for now (e.g. `reel approve` / `reel build`); the panel will do it "
               "once the engine-state part of reel serve ships.")


def _dumps(msg: dict) -> str:
    return json.dumps(msg, ensure_ascii=False, separators=(",", ":"))


def _parse(raw: str):
    """(message, None) or (message-or-None, (code, errors)) for one received text message."""
    try:
        msg = json.loads(raw)
    except (ValueError, RecursionError):
        return None, ("schema", ["The message is not JSON."])
    return msg, messages.validate_message(msg)


class Session:
    """One authenticated WebSocket client."""

    def __init__(self, sid: str, sock: ws.WebSocket, client: dict, peer: str, limiter: security.RateLimiter):
        self.id = sid
        self.sock = sock
        self.peer = peer
        self.kind = client["kind"]
        self.version = client["version"]
        self.host = client.get("host")
        self.host_version = client.get("hostVersion")
        self.capabilities = tuple(dict.fromkeys(client.get("capabilities") or ()))
        self.limiter = limiter                                     # client requests (and invalid messages)
        self.progress_limiter = security.RateLimiter(limiter.rate, int(limiter.burst))   # a host's progress events
        self.progress_dropped = 0
        self.link = HostLink(self._send_or_raise)
        self.tasks: set[asyncio.Task] = set()

    async def _send_or_raise(self, msg: dict) -> None:
        await self.sock.send(_dumps(msg))

    async def send(self, msg: dict) -> bool:
        try:
            await self.sock.send(_dumps(msg))
            return True
        except (ConnectionError, OSError):
            return False

    def summary(self) -> dict:
        return {"kind": self.kind, "host": self.host, "hostVersion": self.host_version,
                "capabilities": list(self.capabilities)}


class App:
    """`handler` is the ws.start_server connection handler; start()/close() run it on 127.0.0.1."""

    def __init__(self, *, home, token: str, version: str, audit: security.AuditLog | None = None,
                 hello_timeout: float = HELLO_TIMEOUT, max_connections: int = MAX_CONNECTIONS,
                 rate: tuple = RATE, max_running: int = MAX_RUNNING,
                 idle_timeout: float = ws.IDLE_TIMEOUT, file_queue=None):
        if not security.token_shape_ok(token):
            raise ValueError("the engine token must be 64 lowercase hex characters (security.make_token)")
        self.home = home
        self.token = token
        self.version = version
        self.audit = audit if audit is not None else security.AuditLog(security.audit_log_path(home), token=token)
        self.hello_timeout = hello_timeout
        self.max_connections = max_connections
        self.rate = rate
        self.max_running = max_running
        self.idle_timeout = idle_timeout
        self.port: int | None = None
        self.sessions: dict[str, Session] = {}
        self.router = Router(home=home, sessions=lambda: list(self.sessions.values()),
                             file_queue=file_queue if file_queue is not None else FileQueueAdapter(), audit=self.audit)
        self._conns = 0
        self._handlers: set[asyncio.Task] = set()
        self._server: asyncio.Server | None = None
        self._strict = False
        self._t0 = time.monotonic()

    # ------------------------------------------------------------------------------------------------ lifecycle
    async def start(self, port: int = 0, *, strict_context: bool = True) -> int:
        """Listen on 127.0.0.1:`port` (0 = free). strict_context: from now on an unbound current_context() raises."""
        self._server, self.port = await ws.start_server(self.handler, port=port)
        self._t0 = time.monotonic()
        if strict_context:
            common.require_bound_context(True)
            self._strict = True
        return self.port

    async def close(self) -> None:
        """Stop listening, close every session (1001), end every connection, restore the context switch."""
        if self._server is not None:
            self._server.close()
        for s in list(self.sessions.values()):
            with contextlib.suppress(ConnectionError, OSError, ValueError):
                await s.sock.close(1001, "reel serve is stopping")
        for t in list(self._handlers):
            t.cancel()
        if self._handlers:
            await asyncio.wait(list(self._handlers), timeout=ws.CLOSE_TIMEOUT * 4)
        if self._server is not None:
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(ws.CLOSE_TIMEOUT * 4):
                    await self._server.wait_closed()
            self._server = None
        if self._strict:
            common.require_bound_context(False)
            self._strict = False

    def status(self) -> dict:
        return {"protocol": 4, "daemon_version": self.version, "pid": os.getpid(), "port": self.port,
                "sessions": [s.summary() for s in self.sessions.values()],
                "uptime_s": round(time.monotonic() - self._t0, 3)}

    def _audit(self, event, peer, **kw) -> None:
        self.audit.log(event, peer=peer, **kw)

    # ------------------------------------------------------------------------------------------------ HTTP
    async def handler(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        peer_s = f"{peer[0]}:{peer[1]}" if peer else "?"
        if self._conns >= self.max_connections:
            self._audit("connection", peer_s, outcome="rejected", reason=f"connection cap ({self.max_connections})")
            await ws.write_response(writer, ws.json_response(503, {"error": "too many connections"}))
            return
        self._conns += 1
        task = asyncio.current_task()
        self._handlers.add(task)
        try:
            await self._serve(reader, writer, peer, peer_s)
        finally:
            self._handlers.discard(task)
            self._conns -= 1

    async def _serve(self, reader, writer, peer, peer_s: str) -> None:
        try:
            req = await ws.parse_http(reader, peer=peer)
        except ws.HttpError as e:                           # ws's connection wrapper answers it
            self._audit("http", peer_s, outcome="rejected", reason=f"{e.status} {e.reason}")
            raise
        h = req.headers
        refused = None
        if "origin" in h:                                   # on record before any other check (rebinding attempts too)
            refused = security.origin_rejection(h)
            self._audit("origin", peer_s, action=req.path, outcome="rejected" if refused else "allowed",
                        reason=h["origin"])
        if "host" not in h:                                 # HTTP/1.0 may omit it; we never do without it
            self._audit("http", peer_s, action=req.path, outcome="rejected", reason="missing host")
            raise ws.HttpError(400, "missing Host header")
        if not security.check_host(h, self.port):
            self._audit("http", peer_s, action=req.path, outcome="rejected", reason="host")
            await ws.write_response(writer, ws.json_response(403, {"error": "Host not allowed"}))
            return
        if refused:
            self._audit("http", peer_s, action=req.path, outcome="rejected", reason=refused)
            await ws.write_response(writer, ws.json_response(403, {"error": "Origin not allowed"}))
            return
        if req.path == "/status":
            await self._status(req, writer, peer_s)
        elif req.path == "/session":
            await self._session(req, reader, writer, peer_s)
        else:
            await ws.write_response(writer, ws.json_response(404, {"error": "not found"}))

    async def _status(self, req: ws.Request, writer, peer_s: str) -> None:
        if req.method != "GET":
            await ws.write_response(writer, ws.json_response(405, {"error": "GET only"}, {"Allow": "GET"}))
            return
        scheme, _, given = req.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not security.token_ok(given.strip(), self.token):
            self._audit("status", peer_s, outcome="rejected", reason="missing or wrong bearer token")
            await ws.write_response(writer, ws.json_response(401, {"error": "token required"},
                                                             {"WWW-Authenticate": "Bearer"}))
            return
        await ws.write_response(writer, ws.json_response(200, self.status()))

    # ------------------------------------------------------------------------------------------------ session
    async def _session(self, req: ws.Request, reader, writer, peer_s: str) -> None:
        sock = await ws.upgrade(req, reader, writer, max_message=PRE_AUTH_MAX, idle_timeout=self.idle_timeout)
        if sock is None:
            self._audit("handshake", peer_s, outcome="rejected", reason="bad websocket handshake")
            return
        session = None
        try:
            session = await self._authenticate(sock, peer_s)
            if session is not None:
                await self._run(session)
        finally:
            if session is not None:
                await self._end(session)
            if not sock.closed:
                with contextlib.suppress(ConnectionError, OSError):
                    await sock.close(1000)

    async def _refuse(self, sock: ws.WebSocket, peer_s: str, reason: str) -> None:
        self._audit("auth", peer_s, outcome="rejected", reason=reason)
        if not sock.closed:
            with contextlib.suppress(ConnectionError, OSError):
                await sock.send(_dumps(messages.error("auth", AUTH_REFUSED)))
            with contextlib.suppress(ConnectionError, OSError):
                await sock.close(1008, "authentication required")

    async def _authenticate(self, sock: ws.WebSocket, peer_s: str) -> Session | None:
        try:
            async with asyncio.timeout(self.hello_timeout):
                raw = await sock.recv()
        except TimeoutError:
            await self._refuse(sock, peer_s, f"no hello within {self.hello_timeout:g}s")
            return None
        if raw is None:
            await self._refuse(sock, peer_s, f"closed before hello ({sock.close_code})")
            return None
        msg, problem = _parse(raw)
        if problem is not None or msg.get("type") != "hello":
            await self._refuse(sock, peer_s, "first message is not a valid hello")
            return None
        if not security.token_shape_ok(msg["token"]):
            await self._refuse(sock, peer_s, "token is not 64 lowercase hex")
            return None
        if not security.token_ok(msg["token"], self.token):
            await self._refuse(sock, peer_s, "wrong token")
            return None
        sock.max_message = POST_AUTH_MAX
        sid = "s-" + secrets.token_hex(8)
        session = Session(sid, sock, msg["client"], peer_s, security.RateLimiter(*self.rate))
        self.sessions[sid] = session
        self._audit("auth", peer_s, session=sid, outcome="ok",
                    reason=f"{session.kind} {session.host or ''} {','.join(session.capabilities)}".strip())
        await session.send(messages.welcome(sid, self.version))
        return session

    async def _run(self, s: Session) -> None:
        while (raw := await s.sock.recv()) is not None:
            if len(raw) > OFFLOAD_BYTES:                     # a big message must not stall the other sessions
                msg, problem = await asyncio.to_thread(_parse, raw)
            else:
                msg, problem = _parse(raw)
            kind = msg.get("type") if problem is None else None
            if kind == "progress" and not s.progress_limiter.allow():
                s.progress_dropped += 1                      # a burst of progress: drop silently, never the result
                if s.progress_dropped == 1:
                    self._audit("rate", s.peer, session=s.id, outcome="dropped", reason="progress over the rate")
                continue
            if kind not in ("result", "progress") and not s.limiter.allow():
                self._audit("rate", s.peer, session=s.id, action=kind, outcome="rejected", reason="message rate")
                await s.send(messages.error("rate", "Too many messages: slow down.", messages.message_id(msg)))
                continue
            if problem is not None:
                code, errors = problem
                await s.send(messages.error(code, "; ".join(errors), messages.message_id(msg)))
                continue
            try:
                await self._dispatch(s, msg)
            except (ConnectionError, OSError):
                raise
            except Exception as e:                           # one bad message must not end the session
                log.warning("reel serve: %s message failed (%s)", msg.get("type"), type(e).__name__)
                await s.send(messages.error("internal", f"The daemon failed on this message ({type(e).__name__}).",
                                            messages.message_id(msg)))

    async def _dispatch(self, s: Session, msg: dict) -> None:
        t = msg["type"]
        if t == "command":
            if len(s.tasks) >= self.max_running:
                await s.send(messages.error("rate", f"{self.max_running} commands are already running.",
                                            messages.message_id(msg)))
                return
            task = asyncio.create_task(self._command(s, msg))
            s.tasks.add(task)
            task.add_done_callback(s.tasks.discard)
        elif t == "result":
            if not s.link.deliver_result(msg["result"]):
                self._audit("late-result", s.peer, session=s.id, action=msg["result"].get("action"),
                            outcome="ignored", reason="no command waits for this id")
        elif t == "progress":
            if not await s.link.deliver_progress(msg["progress"]):
                self._audit("late-progress", s.peer, session=s.id, action=msg["progress"].get("action"),
                            outcome="ignored", reason="no command waits for this id")
        elif t == "snapshot":
            await s.send(await self._state(msg.get("id")))
        elif t in ("approve", "request_changes", "rebuild"):
            await s.send(messages.reply(t, msg["id"], ok=False, error=NOT_YET, how=NOT_YET_HOW))
        elif t == "cancel":
            answer = await self.router.cancel(msg["id"])
            if answer is not None:
                await s.send(answer)
        elif t == "hello":
            await s.send(messages.error("schema", "This session is already authenticated; a new hello needs a new "
                                                  "connection."))
        else:                                                # welcome, state, reply, error: daemon -> client only
            await s.send(messages.error("schema", f"{t} is sent by the daemon, not by clients.",
                                        messages.message_id(msg)))

    async def _command(self, s: Session, msg: dict) -> None:
        try:
            out = await self.router.handle(msg, send=s.send, peer=s.peer, session_id=s.id)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("reel serve: command failed (%s)", type(e).__name__)
            out = messages.error("internal", f"The daemon failed on this command ({type(e).__name__}).",
                                 messages.message_id(msg))
        await s.send(out)

    async def _state(self, id) -> dict:
        """The connection part of the panel state: a UXP Premiere panel connected, else the CEP heartbeat."""
        for s in reversed(list(self.sessions.values())):
            if s.kind == "uxp" and s.host == "premiere":
                return messages.state("uxp", f"Premiere Pro {s.host_version}".strip() if s.host_version else None, id)
        ctx = common.Context(home=self.home)

        def cep_alive() -> bool:
            from lib import ppro_bridge
            with common.use_context(ctx):
                return bool(ppro_bridge.status().get("alive"))
        try:
            alive = await asyncio.to_thread(cep_alive)
        except Exception:
            alive = False
        return messages.state("cep" if alive else "offline", None, id)

    async def _end(self, s: Session) -> None:
        self.sessions.pop(s.id, None)
        s.link.fail_all()
        for t in list(s.tasks):
            t.cancel()
        if s.tasks:
            await asyncio.gather(*s.tasks, return_exceptions=True)
        self._audit("session", s.peer, session=s.id, outcome="closed", reason=f"close code {s.sock.close_code}")
