"""The `reel serve` application (3.0 T6.2): the per-connection handler on top of serve/ws.py.

HTTP (every request): the connection cap first (one global cap, MAX_CONNECTIONS; excess -> 503 + audit. There is no
per-address cap: on loopback every peer is 127.0.0.1 or ::1, so it would only be a second, smaller global cap), then the
request head (ws.parse_http; a refused head is answered 400/408 by ws's connection wrapper), then every Origin seen is
audit-logged with its raw value (before any other check, so a rebinding attempt's Origin is on record too), then the
Host gate (missing -> 400, anything but 127.0.0.1:<port> / localhost:<port> / [::1]:<port> -> 403 + audit) and the
Origin gate (a browser Origin -> 403 + audit). Then:
    GET /status    needs `Authorization: Bearer <token>` (401 otherwise); answers {protocol, daemon_version, pid, port,
                   sessions: [{kind, host, hostVersion, capabilities}], uptime_s}
    POST /shutdown needs the same bearer token (401 otherwise; other methods 405): 202 {ok, stopping}, then
                   `stop_requested` is set and the daemon (serve/daemon.py) closes the app and exits. The only
                   mutating HTTP endpoint.
    /session       the WebSocket session (below)
    anything else  404
Session: the upgrade caps messages at 16 KiB until the client is authenticated. The first message must be a valid
`hello` within `hello_timeout` (3 s) whose token is 64 lowercase hex characters and equals the engine token
(constant-time); anything else is `error{code: auth}` + close 1008 + audit, except a hello whose client.protocol is not
4: that is `error{code: schema, message: "protocol 4 required"}` + close 1008 + audit, so an outdated panel is not told
its token is wrong. After `welcome` the cap is 8 MiB and every message is parsed and validated against its type in
session.schema.json (`schema` / `unknown_type` errors keep the connection and are audit-logged as `message`
rejections). Rate limits are per session and by type: what a client asks for (command, snapshot, the intents, cancel,
and anything invalid) is limited (`error{rate}` with the message's id); a host's `result` for a command it was sent
(its id pending on that session's link) is never limited (dropping it would leave the requester waiting until
expiry), an unmatched `result` is charged like any client message and only the first one per session is audited;
`progress` over its own budget is dropped silently (likewise, only the first unmatched one is audited). Progress is
handed to the requester through a bounded queue (adapters.HostLink), so a requester that stops reading never stalls
the host session. `command` runs in
its own task through the Router (UXP panel or CEP file queue, a Context per request); `result` / `progress` from a host
session answer the commands sent to it; the panel intents approve / request_changes / rebuild are accepted only from a
`kind: "panel"` session (any other session gets `error{schema}`, audited) and get a `reply` ok:false in plain words
saying the step is not available from the panel yet (NOT_YET; no command names: the engine side is T6.2b, and until
it ships no `reel` writer runs for a panel intent; each such reply is audited: event intent, outcome not_available);
`snapshot` gets a `state` echoing its id, with the item the engine works on (serve/engine_state.py: <home>/state/
active.json and the item's evidence files, read only, cached by their files' state). That read runs on the app's own
engine-state worker (a daemon thread, adapters.QueueWorker; never the default executor) under FIELDS_TIMEOUT (3 s);
snapshots that arrive while it runs share it (asyncio.shield). Past its deadline the state carries the last good item
(else no item) and the timeout is logged once; after FIELDS_RETIRE_AFTER (2) consecutive timeouts the stuck worker is
abandoned and a fresh one reads again (a recovered share or a new active.json item shows), at most
FIELDS_ABANDONED_MAX (4) stuck at once (then no new worker, logged once), so a dead network share costs a few threads,
never one per poll, and a snapshot never queues behind a stuck read;
`cancel` is
forwarded to the panel running the command. When a session ends, the commands waiting on it fail with a clear error
and its own running commands are cancelled; a reconnect is a new hello.
The token is never logged, never echoed and never read from a URL. Messages are encoded with allow_nan=False (NaN /
Infinity are not JSON); a message that cannot be encoded is logged and answered with error{internal}, never ending the
session.
`welcome.update.panel` answers the hello's optional client.build against <plugin>/adobe/expected.json (C2.3:
ok / stale / newer / unknown; engine_state.panel_update).
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

from . import engine_state, messages, security, ws
from .adapters import FileQueueAdapter, HostLink, QueueWorker
from .router import Router

__all__ = ["App", "Session", "PRE_AUTH_MAX", "POST_AUTH_MAX", "HELLO_TIMEOUT"]

log = logging.getLogger(__name__)

PRE_AUTH_MAX = 16 * 1024
POST_AUTH_MAX = 8 * 1024 * 1024
HELLO_TIMEOUT = 3.0
MAX_CONNECTIONS = 32
CLOSE_BUDGET = 2.0                # close(): the whole shutdown, whatever the peers do (the steps below add up to it)
CLOSE_SESSIONS_S = 0.8            # close(): how long sessions get to answer the close frame (all at once)
CLOSE_HANDLERS_S = 0.4            # close(): how long a cancelled connection gets before its socket is aborted
CLOSE_ROUNDS = 3                  # close(): abort-and-cancel rounds before a task is reported as stuck
CLOSE_ROUND_S = 0.2               # close(): the wait after each abort round, and for the listener to close
RATE = (20.0, 60)                  # messages per second per session, burst
MAX_RUNNING = 16                   # commands one session may have running at once
OFFLOAD_BYTES = 256 * 1024         # messages above this are parsed and validated in a worker thread
FIELDS_TIMEOUT = 3.0               # the engine state read (engine_state.PanelFields) for one snapshot
FIELDS_RETIRE_AFTER = 2            # consecutive timeouts of one read before its worker is abandoned for a fresh one
FIELDS_ABANDONED_MAX = 4           # abandoned workers whose read is still stuck: past this no new worker is made
AUTH_REFUSED = "The first message must be a hello with the engine token from engine.json."
PROTOCOL_REQUIRED = "protocol 4 required"
# the panel intents until T6.2b ships their engine side: editor words, never a command (Addendum C1.4)
NOT_YET = {"approve": "Approving is not available from the panel yet.",
           "request_changes": "Requesting changes is not available from the panel yet.",
           "rebuild": "Rebuilding is not available from the panel yet."}
NOT_YET_HOW = "Do this step in your Claude session for now — it will work from the panel after the next update."
INTENTS = frozenset(NOT_YET)


def _dumps(msg: dict) -> str:
    """Strict JSON: NaN / Infinity raise ValueError instead of reaching a peer as invalid JSON."""
    return json.dumps(msg, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


_NO_PROTOCOL = object()


def _hello_protocol(msg):
    """`client.protocol` of a hello-shaped message, or _NO_PROTOCOL when the message is not a hello or has none."""
    if not isinstance(msg, dict) or msg.get("type") != "hello" or not isinstance(msg.get("client"), dict):
        return _NO_PROTOCOL
    return msg["client"].get("protocol", _NO_PROTOCOL)


def _type_of(msg) -> str:
    """The message's `type` for the audit log when it is a short plain word, else "?" (never a raw value)."""
    t = msg.get("type") if isinstance(msg, dict) else None
    return t if isinstance(t, str) and t.isascii() and t.replace("_", "").isalnum() and len(t) <= 32 else "?"


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
        self.late_results = 0                                      # results / progress nobody waits for
        self.late_progress = 0
        self.link = HostLink(self._send_or_raise)
        self.tasks: set[asyncio.Task] = set()

    async def _send_or_raise(self, msg: dict) -> None:
        await self.sock.send(_dumps(msg))

    async def send(self, msg: dict) -> bool:
        try:
            text = _dumps(msg)
        except (ValueError, TypeError) as e:          # not JSON (NaN, Infinity, ...): say so, keep the session
            log.warning("reel serve: a %s message could not be encoded (%s); sent error{internal} instead",
                        msg.get("type") if isinstance(msg, dict) else "?", type(e).__name__)
            text = _dumps(messages.error("internal", "The daemon could not encode its answer.",
                                         msg.get("id") if isinstance(msg, dict) else None))
        try:
            await self.sock.send(text)
            return True
        except (ConnectionError, OSError):
            return False

    def summary(self) -> dict:
        return {"kind": self.kind, "host": self.host, "hostVersion": self.host_version,
                "capabilities": list(self.capabilities)}


class App:
    """`handler` is the ws.start_server connection handler; start()/close() run it on the loopback pair (127.0.0.1 and
    ::1, the same port; 127.0.0.1 alone when IPv6 is unavailable)."""

    def __init__(self, *, home, token: str, version: str, audit: security.AuditLog | None = None,
                 hello_timeout: float = HELLO_TIMEOUT, max_connections: int = MAX_CONNECTIONS,
                 rate: tuple = RATE, max_running: int = MAX_RUNNING,
                 idle_timeout: float = ws.IDLE_TIMEOUT, file_queue=None, expected_path=None,
                 fields_timeout: float = FIELDS_TIMEOUT):
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
        self.expected_path = expected_path if expected_path is not None else engine_state.expected_path()
        self.fields_timeout = fields_timeout
        self._fields = engine_state.PanelFields()               # the item's fields, cached by their files' state
        self._state_worker = QueueWorker("reel-serve-engine-state")   # one daemon thread: a stuck read costs one
        self._state_workers_made = 1
        self._fields_running = None                             # the read in flight (concurrent.futures.Future)
        self._fields_shared: asyncio.Future | None = None       # ... as the asyncio future every snapshot awaits
        self._fields_deadline = 0.0                             # loop time when that read counts as timed out
        self._fields_read_counted = False                       # that read's timeout is counted (once per read)
        self._fields_timeouts = 0                               # consecutive timeouts (reset by an answered read)
        self._fields_abandoned: list = []                       # (future, shared) of retired workers' stuck reads
        self._fields_cap_logged = False
        self._last_fields: dict | None = None                   # the last good read: shown while a read is stuck
        self._fields_timed_out = False                          # logged once per stuck episode
        self.port: int | None = None
        self.sessions: dict[str, Session] = {}
        self.router = Router(home=home, sessions=lambda: list(self.sessions.values()),
                             file_queue=file_queue if file_queue is not None else FileQueueAdapter(), audit=self.audit)
        self._conns = 0
        self._handlers: dict[asyncio.Task, asyncio.StreamWriter] = {}
        self._server: ws.LoopbackServer | None = None
        self._strict = False
        self._t0 = time.monotonic()
        self.stop_requested = asyncio.Event()        # set by an authenticated POST /shutdown

    # ------------------------------------------------------------------------------------------------ lifecycle
    async def start(self, port: int = 0, *, strict_context: bool = True) -> int:
        """Listen on `port` (0 = free) on 127.0.0.1 and ::1 (ws.start_server). strict_context: from now on an unbound
        current_context() raises."""
        self._server, self.port = await ws.start_server(self.handler, port=port)
        self._t0 = time.monotonic()
        if strict_context:
            common.require_bound_context(True)
            self._strict = True
        return self.port

    @property
    def listening(self) -> list[str]:
        """The addresses served, e.g. ["127.0.0.1:51234", "[::1]:51234"] (empty when not started)."""
        if self._server is None:
            return []
        return [f"[{a[0]}]:{a[1]}" if ":" in a[0] else f"{a[0]}:{a[1]}"
                for a in (s.getsockname() for s in self._server.sockets)]

    async def close(self) -> None:
        """Stop listening, close every session (1001), end every connection, restore the context switch. Bounded by
        one deadline, CLOSE_BUDGET (2 s), whatever the peers do, and it awaits every connection task: sessions get
        CLOSE_SESSIONS_S to answer the close frame (all at once; a silent peer is aborted), cancelled connections get
        CLOSE_HANDLERS_S, then up to CLOSE_ROUNDS rounds abort the socket, cancel again and await (CLOSE_ROUND_S
        each). A task that survives all of that is logged, never waited on. A command waiting on a stuck CEP queue
        call is cancelled at once (its daemon worker thread is left behind and never blocks the process exit)."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + CLOSE_BUDGET

        def left(step: float) -> float:
            return max(0.01, min(step, deadline - loop.time()))

        if self._server is not None:
            self._server.close()
        self._state_worker.cancel_pending()
        for shared in [self._fields_shared, *(a for _, a in self._fields_abandoned)]:
            if shared is not None:
                shared.cancel()                        # a stuck read finishing later never calls into a closed loop
        sessions = list(self.sessions.values())
        if sessions:                                   # concurrently: N silent peers cost one timeout, not N
            closing = [asyncio.ensure_future(self._close_session(s)) for s in sessions]
            _, pending = await asyncio.wait(closing, timeout=left(CLOSE_SESSIONS_S))
            for t in pending:
                t.cancel()                             # _close_session aborts the socket: this is immediate
            await asyncio.gather(*closing, return_exceptions=True)
        for t in list(self._handlers):
            t.cancel()
        if self._handlers:
            await asyncio.wait(list(self._handlers), timeout=left(CLOSE_HANDLERS_S))
        for _ in range(CLOSE_ROUNDS):                 # past the timeout: abort the socket, cancel again, await
            if not self._handlers:
                break
            for t, w in list(self._handlers.items()):
                w.transport.abort()
                t.cancel()
            await asyncio.wait(list(self._handlers), timeout=left(CLOSE_ROUND_S))
        if self._handlers:                             # a task that ignores cancellation: say so, never hang
            log.warning("reel serve: %d connection task(s) did not stop", len(self._handlers))
        if self._server is not None:
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(left(CLOSE_ROUND_S)):
                    await self._server.wait_closed()
            self._server = None
        if self._strict:
            common.require_bound_context(False)
            self._strict = False

    @staticmethod
    async def _close_session(s: Session) -> None:
        try:
            await s.sock.close(1001, "reel serve is stopping")
        except (ConnectionError, OSError, ValueError):
            pass
        except asyncio.CancelledError:                 # the peer did not answer in time: drop the connection
            s.sock.abort()
            raise

    async def wait_stop(self) -> None:
        """Until an authenticated POST /shutdown asks the daemon to stop."""
        await self.stop_requested.wait()

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
        self._handlers[task] = writer               # until the task ends (ws's linger-close runs after this returns)
        task.add_done_callback(self._forget)
        try:
            await self._serve(reader, writer, peer, peer_s)
        finally:
            self._conns -= 1

    def _forget(self, task: asyncio.Task) -> None:
        self._handlers.pop(task, None)

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
        elif req.path == "/shutdown":
            await self._shutdown(req, writer, peer_s)
        elif req.path == "/session":
            await self._session(req, reader, writer, peer_s)
        else:
            await ws.write_response(writer, ws.json_response(404, {"error": "not found"}))

    def _bearer_ok(self, req: ws.Request) -> bool:
        scheme, _, given = req.headers.get("authorization", "").partition(" ")
        return scheme.lower() == "bearer" and security.token_ok(given.strip(), self.token)

    async def _unauthorized(self, writer) -> None:
        await ws.write_response(writer, ws.json_response(401, {"error": "token required"},
                                                         {"WWW-Authenticate": "Bearer"}))

    async def _status(self, req: ws.Request, writer, peer_s: str) -> None:
        if req.method != "GET":
            await ws.write_response(writer, ws.json_response(405, {"error": "GET only"}, {"Allow": "GET"}))
            return
        if not self._bearer_ok(req):
            self._audit("status", peer_s, outcome="rejected", reason="missing or wrong bearer token")
            await self._unauthorized(writer)
            return
        await ws.write_response(writer, ws.json_response(200, self.status()))

    async def _shutdown(self, req: ws.Request, writer, peer_s: str) -> None:
        """The only mutating HTTP endpoint: POST + the bearer token -> 202, then the daemon stops (stop_requested)."""
        if req.method != "POST":
            self._audit("shutdown", peer_s, outcome="rejected", reason=f"method {req.method}")
            await ws.write_response(writer, ws.json_response(405, {"error": "POST only"}, {"Allow": "POST"}))
            return
        if not self._bearer_ok(req):
            self._audit("shutdown", peer_s, outcome="rejected", reason="missing or wrong bearer token")
            await self._unauthorized(writer)
            return
        self._audit("shutdown", peer_s, outcome="accepted", reason="POST /shutdown")
        await ws.write_response(writer, ws.json_response(202, {"ok": True, "stopping": True}))
        self.stop_requested.set()

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
        proto = _hello_protocol(msg)
        if proto is not _NO_PROTOCOL and (isinstance(proto, bool) or proto != security.PROTOCOL):
            # an older / newer panel: say what is wrong instead of "wrong token" (nothing about the token is told)
            self._audit("auth", peer_s, outcome="rejected", reason=f"protocol {str(proto)[:16]} (4 required)")
            with contextlib.suppress(ConnectionError, OSError):
                await sock.send(_dumps(messages.error("schema", PROTOCOL_REQUIRED)))
            with contextlib.suppress(ConnectionError, OSError):
                await sock.close(1008, PROTOCOL_REQUIRED)
            return None
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
        try:
            update = await asyncio.to_thread(engine_state.panel_update, msg["client"].get("build"), self.expected_path)
        except Exception:
            update = "unknown"
        self._audit("auth", peer_s, session=sid, outcome="ok",
                    reason=f"{session.kind} {session.host or ''} {','.join(session.capabilities)}".strip())
        await session.send(messages.welcome(sid, self.version, update))
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
            # a host's result for a command it was sent is never limited (dropping it would leave the requester
            # waiting); any other result (unmatched: nobody waits for it) is charged like every client message
            exempt = kind == "progress" or (kind == "result" and msg["result"].get("id") in s.link)
            if not exempt and not s.limiter.allow():
                self._audit("rate", s.peer, session=s.id, action=kind, outcome="rejected", reason="message rate")
                await s.send(messages.error("rate", "Too many messages: slow down.", messages.message_id(msg)))
                continue
            if problem is not None:
                code, errors = problem
                self._audit("message", s.peer, session=s.id, action=_type_of(msg), outcome="rejected",
                            reason=f"{code}: {'; '.join(errors)}")
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
                s.late_results += 1                  # audited once per session: a flood cannot rotate the trail away
                if s.late_results == 1:
                    self._audit("late-result", s.peer, session=s.id, action=msg["result"].get("action"),
                                outcome="ignored", reason="no command waits for this id (later ones are not logged)")
        elif t == "progress":
            if not await s.link.deliver_progress(msg["progress"]):
                s.late_progress += 1
                if s.late_progress == 1:
                    self._audit("late-progress", s.peer, session=s.id, action=msg["progress"].get("action"),
                                outcome="ignored", reason="no command waits for this id (later ones are not logged)")
        elif t == "snapshot":
            await s.send(await self._state(msg.get("id")))
        elif t in INTENTS:
            if s.kind != "panel":                    # only the WhyNot Cut panel speaks for the editor
                self._audit("intent", s.peer, session=s.id, action=t, outcome="rejected",
                            reason=f"from a {s.kind} session")
                await s.send(messages.error("schema", f"{t} is a panel intent: only a panel session may send it.",
                                            messages.message_id(msg)))
                return
            self._audit("intent", s.peer, session=s.id, action=t, outcome="not_available",
                        reason="not available from the panel yet (T6.2b)")
            await s.send(messages.reply(t, msg["id"], ok=False, error=NOT_YET[t], how=NOT_YET_HOW))
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

    def _fields_fallback(self) -> dict:
        return dict(self._last_fields) if self._last_fields is not None else dict(engine_state.EMPTY, pipeline=[], qc=[])

    def _start_read(self, loop: asyncio.AbstractEventLoop) -> None:
        """Submit one PanelFields read to the current engine-state worker; every snapshot until it answers shares it."""
        home = self.home
        fut = self._state_worker.submit(lambda: self._fields(home))
        shared = asyncio.wrap_future(fut, loop=loop)
        shared.add_done_callback(lambda f: f.cancelled() or f.exception())   # retrieved even when nobody waits
        self._fields_running, self._fields_shared = fut, shared
        self._fields_deadline = loop.time() + self.fields_timeout
        self._fields_read_counted = False

    def _count_timeout(self) -> None:
        self._fields_timeouts += 1
        if not self._fields_timed_out:
            self._fields_timed_out = True
            log.warning("reel serve: reading the engine state timed out after %gs; the panel shows the last known item "
                        "until it answers", self.fields_timeout)

    def _retire_worker(self) -> bool:
        """Abandon the worker stuck in the current read (its daemon thread finishes or dies with the process) and make
        a fresh one, so a recovered share or a new active.json item is read. False when FIELDS_ABANDONED_MAX retired
        reads are still stuck (logged once): no more threads are spent on a dead share."""
        self._fields_abandoned = [(f, a) for f, a in self._fields_abandoned if not f.done()]
        if len(self._fields_abandoned) >= FIELDS_ABANDONED_MAX:
            if not self._fields_cap_logged:
                self._fields_cap_logged = True
                log.warning("reel serve: %d engine-state reads are stuck; no new reader is started until one answers",
                            len(self._fields_abandoned))
            return False
        self._fields_abandoned.append((self._fields_running, self._fields_shared))
        self._state_workers_made += 1
        self._state_worker = QueueWorker(f"reel-serve-engine-state-{self._state_workers_made}")
        self._fields_timeouts = 0
        log.info("reel serve: the engine-state read is stuck; reading again on a fresh worker")
        return True

    async def _item_fields(self) -> dict | None:
        """The item part of the panel state: engine_state.PanelFields on the app's engine-state worker, bounded by
        fields_timeout. A snapshot that arrives while a read is running awaits that same read (asyncio.shield: one
        waiter going away never cancels it). Past the read's deadline the snapshot gets the last good fields (else no
        item). After FIELDS_RETIRE_AFTER consecutive timeouts the stuck worker is abandoned and a fresh one reads
        again (at most FIELDS_ABANDONED_MAX stuck at once); otherwise a snapshot never queues behind a stuck read.
        None if the read failed."""
        loop = asyncio.get_running_loop()
        shared = self._fields_shared
        if shared is not None and not shared.done():
            if loop.time() >= self._fields_deadline:         # still running past its deadline: stuck
                self._count_timeout()
                self._fields_read_counted = True
                if self._fields_timeouts < FIELDS_RETIRE_AFTER or not self._retire_worker():
                    return self._fields_fallback()
                self._start_read(loop)
        else:
            self._start_read(loop)
        shared = self._fields_shared
        try:
            out = await asyncio.wait_for(asyncio.shield(shared), max(0.0, self._fields_deadline - loop.time()))
        except TimeoutError:
            if shared is self._fields_shared and not self._fields_read_counted:
                self._fields_read_counted = True             # concurrent waiters of one read count one timeout
                self._count_timeout()
            return self._fields_fallback()
        except asyncio.CancelledError:
            if shared.cancelled() and not asyncio.current_task().cancelling():
                return self._fields_fallback()               # the daemon is stopping (close() cancelled the read)
            raise
        except Exception as e:
            self._fields_timeouts = 0
            log.warning("reel serve: engine state failed (%s)", type(e).__name__)
            return None
        self._fields_timeouts = 0
        self._fields_timed_out = False
        self._fields_cap_logged = False
        self._last_fields = out
        return out

    async def _state(self, id) -> dict:
        """The panel state: the connection (a UXP Premiere panel connected, else the CEP heartbeat) and the item the
        engine works on. Only a session that implements something counts as the host: a uxp session with no
        capabilities (spike 0.1.3, a probe) cannot run a command, so it is not the Premiere host the pill means. Nor
        does a session whose socket has closed while its removal (_end, async) is still pending."""
        item = await self._item_fields()
        for s in reversed(list(self.sessions.values())):
            if s.kind == "uxp" and s.host == "premiere" and s.capabilities and not s.sock.closed and not s.link.closed:
                return messages.state("uxp", f"Premiere Pro {s.host_version}".strip() if s.host_version else None, id,
                                      item)
        ctx = common.Context(home=self.home)

        def cep_alive() -> bool:
            from lib import ppro_bridge
            with common.use_context(ctx):
                return bool(ppro_bridge.status().get("alive"))
        try:
            alive = await asyncio.to_thread(cep_alive)
        except Exception:
            alive = False
        return messages.state("cep" if alive else "offline", None, id, item)

    async def _end(self, s: Session) -> None:
        self.sessions.pop(s.id, None)
        s.link.fail_all()
        for t in list(s.tasks):
            t.cancel()
        if s.tasks:
            await asyncio.gather(*s.tasks, return_exceptions=True)
        self._audit("session", s.peer, session=s.id, outcome="closed", reason=f"close code {s.sock.close_code}")
