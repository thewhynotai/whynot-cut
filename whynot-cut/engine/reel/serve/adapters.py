"""Where a v4 command runs (3.0 T6.2): a connected UXP panel, or the legacy CEP file queue.

    FileQueueAdapter   runs lib.ppro_bridge.submit / lib.ae_bridge.submit (the existing CEP queue) in a worker thread
                       that binds the request's Context itself (common.use_context inside the worker: a bound Context
                       does not reach a new thread by itself) and maps the answer with contract.cep.from_cep. Only the
                       action's legacy CEP name and its data travel: the bridge's own whitelisted script runs, never
                       one named by a client. The queue's own failures (bridge 3.1.1: not running, version mismatch,
                       expired, cancelled before the claim, timed out after it, refused by the bridge, build lock held,
                       test sandbox) all become ok:false with the queue's sentence and a `how`; their extra flags
                       (expired, cancelled, claimed, status, job, refused) do not cross the wire. The submit calls of
                       one bridge are serialized (SUBMIT_LOCKS): bridge.submit shares files between calls
                       (sync_scripts' fixed temp path), and the bridge runs one job at a time anyway; Premiere's and
                       After Effects' queues still run side by side, each on its own daemon QueueWorker (never the
                       event loop's default executor; a stuck submit never blocks process exit). The time left is
                       computed once the call holds its bridge's lock: a request that expired while it waited is
                       answered ok:false without reaching the queue.
    HostLink           the commands in flight to ONE connected host session: sends `command`, matches the `result`
                       by id, hands `progress` to the requester; on a timeout it sends the host a best-effort
                       `cancel` for that id first; fail_all() when the session goes away.
    UxpAdapter         runs a command through a HostLink with the request's remaining time as the timeout.

Adapters return a v4 result dict; the router validates it (contract.validate_result) before anyone sees it.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import copy
import queue
import threading
from datetime import datetime, timezone

from contract import load
from contract.cep import CEP_NAME, from_cep
from lib.common import current_context, use_context

__all__ = ["ACTION_HOSTS", "HostGone", "FileQueueAdapter", "HostLink", "UxpAdapter", "QueueWorker", "QUEUE_WORKERS",
           "cancel_queued", "failure", "seconds_left"]

ACTION_HOSTS: dict[str, str] = {a: e["host"] for a, e in load("protocol")["actions"].items()}
QUEUE_TIMEOUT_S = {"aftereffects": 900.0}          # the bridges' own defaults (ae_bridge 900 s, ppro_bridge 600 s)
QUEUE_TIMEOUT_DEFAULT_S = 600.0
UXP_TIMEOUT_MAX_S = 900.0
APP_NAMES = {"aftereffects": "After Effects"}       # everything else runs in Premiere
CANCEL_SEND_S = 1.0                                 # how long a best-effort cancel may take to send
SUBMIT_LOCKS = {"premiere": threading.Lock(), "aftereffects": threading.Lock()}   # one queue call per bridge
WORKER_IDLE_S = 2.0                                 # an idle queue worker thread ends after this
_EXPIRED = object()


class QueueWorker:
    """One daemon thread that runs one bridge's queue calls in order (the bridge runs one job at a time anyway), so
    queue calls never occupy the event loop's default executor (status checks, big parses) and Premiere's queue never
    starves After Effects'. Daemon: a call stuck in submit (a dialog in the Adobe app) never keeps the process alive.
    Started on demand, ends after WORKER_IDLE_S idle. A call whose requester went away before it started is skipped
    (its future was cancelled through asyncio.wrap_future); cancel_pending() drops every waiting call at shutdown."""

    def __init__(self, name: str):
        self.name = name
        self._q: queue.SimpleQueue = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def submit(self, fn) -> concurrent.futures.Future:
        fut: concurrent.futures.Future = concurrent.futures.Future()
        with self._lock:
            self._q.put((fut, fn))
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop, name=self.name, daemon=True)
                self._thread.start()
        return fut

    def _loop(self) -> None:
        while True:
            try:
                fut, fn = self._q.get(timeout=WORKER_IDLE_S)
            except queue.Empty:
                with self._lock:                     # submit() puts under the same lock: nothing is stranded
                    if self._q.empty():
                        self._thread = None
                        return
                continue
            if not fut.set_running_or_notify_cancel():
                continue
            try:
                fut.set_result(fn())
            except BaseException as e:               # noqa: BLE001 — handed to the awaiting task
                fut.set_exception(e)

    def cancel_pending(self) -> int:
        n = 0
        while True:
            try:
                fut, _ = self._q.get_nowait()
            except queue.Empty:
                return n
            n += bool(fut.cancel())


QUEUE_WORKERS = {lane: QueueWorker(f"reel-serve-queue-{lane}") for lane in SUBMIT_LOCKS}


def cancel_queued() -> int:
    """Drop every queue call that has not started (daemon shutdown). Running ones are left to their daemon thread."""
    return sum(w.cancel_pending() for w in QUEUE_WORKERS.values())


class HostGone(ConnectionError):
    """The host session a command was sent to disconnected before it answered."""


def failure(action: str, id: str, error: str, how: str | None = None) -> dict:
    """An `ok: false` v4 result (it validates with contract.validate_result)."""
    out = {"ok": False, "action": action, "id": id, "error": error}
    if how:
        out["how"] = how
    return out


def expires(request: dict) -> datetime:
    """`expires_at` as an aware datetime (the schema already checked it is RFC 3339 with a zone)."""
    return datetime.fromisoformat(str(request["expires_at"]).upper())


def seconds_left(request: dict, now: datetime | None = None) -> float:
    """Seconds until the request's expires_at (<= 0: already expired)."""
    now = now or datetime.now(timezone.utc)
    return (expires(request) - now).total_seconds()


# ------------------------------------------------------------------------------------------------- CEP file queue
class FileQueueAdapter:
    """The legacy CEP bridge's file queue (Premiere's or After Effects'), run on that bridge's QueueWorker."""

    kind = "cep"

    async def run(self, request: dict, on_progress=None) -> dict:
        action, rid = request["action"], request["id"]
        if action not in CEP_NAME:
            raise ValueError(f"{action!r} has no CEP equivalent")
        name = CEP_NAME[action]
        host = ACTION_HOSTS.get(action)
        data = copy.deepcopy(request.get("data") or {})
        cap = QUEUE_TIMEOUT_S.get(host, QUEUE_TIMEOUT_DEFAULT_S)
        lane = "aftereffects" if host == "aftereffects" else "premiere"    # "any" (ping): Premiere is the primary

        ctx = current_context()                      # the request's (raises in reel serve when none is bound)

        def call():                                  # the worker binds it: contextvars do not follow a thread
            with use_context(ctx):
                if lane == "aftereffects":
                    from lib import ae_bridge as bridge
                else:
                    from lib import ppro_bridge as bridge
                with SUBMIT_LOCKS[lane]:
                    left = seconds_left(request)     # now, after waiting for the worker and the lock
                    if left <= 0:
                        return _EXPIRED
                    return bridge.submit(name, data, timeout=max(1.0, min(left, cap)))

        r = await asyncio.wrap_future(QUEUE_WORKERS[lane].submit(call))
        if r is _EXPIRED:
            return failure(action, rid, "The request expired while it waited for the bridge queue (another command "
                                        "was running).",
                           "Run the command again once the running one has finished.")
        response = r.get("response") if isinstance(r, dict) else None
        if response is not None:
            res = from_cep(action, response, id=rid)
        else:                                        # no parsed answer: the queue's own failure answers
            res = from_cep(action, _queue_failure(r), id=rid)
        if not res.get("ok") and not res.get("how"):
            app = APP_NAMES.get(host, "Premiere")
            res["how"] = (f"Check that the WhyNot Cut Bridge runs in {app} (Window > Extensions > WhyNot Cut Bridge), "
                          "then run the command again.")
        return res


def _queue_failure(r):
    """The queue's own answer (no parsed host response) in the shape from_cep reads: {ok: false, error, how?, status?}.
    A build-lock refusal says `blocked` instead of `error`."""
    if not isinstance(r, dict):
        return r
    out = {k: r[k] for k in ("error", "how", "status", "line") if k in r}
    out["ok"] = False
    if not (isinstance(out.get("error"), str) and out["error"].strip()):
        blocked = r.get("blocked")
        ok_text = isinstance(blocked, str) and blocked.strip()
        out["error"] = blocked if ok_text else "The bridge queue reported a failure."
    return out


# ------------------------------------------------------------------------------------------------------------ UXP
class _Pending:
    __slots__ = ("future", "action", "on_progress")

    def __init__(self, future, action, on_progress):
        self.future, self.action, self.on_progress = future, action, on_progress


class HostLink:
    """The commands in flight to one host session. `send(msg)` is the session's raising send coroutine."""

    def __init__(self, send):
        self._send = send
        self._pending: dict[str, _Pending] = {}
        self.closed = False

    def __contains__(self, rid) -> bool:
        return rid in self._pending

    async def call(self, request: dict, on_progress, timeout: float) -> dict:
        """Send `command` and wait for the host's `result` with the same id. TimeoutError, HostGone or
        ConnectionError (the send failed) otherwise."""
        if self.closed:
            raise HostGone("the host session is closed")
        rid = request["id"]
        if rid in self._pending:
            raise ValueError(f"a command with id {rid} is already in flight to this host")
        fut = asyncio.get_running_loop().create_future()
        self._pending[rid] = _Pending(fut, request["action"], on_progress)
        try:
            await self._send({"type": "command", "request": request})
            try:
                async with asyncio.timeout(timeout):
                    return await asyncio.shield(fut)
            except TimeoutError:                     # tell the host to stop before the requester hears "no answer"
                with contextlib.suppress(ConnectionError, OSError, TimeoutError):
                    async with asyncio.timeout(CANCEL_SEND_S):
                        await self._send({"type": "cancel", "id": rid})
                raise
        finally:
            self._pending.pop(rid, None)
            if fut.done() and not fut.cancelled():
                fut.exception()                      # retrieved: never "Future exception was never retrieved"
            else:
                fut.cancel()

    async def cancel(self, rid: str) -> bool:
        """Forward a client's cancel to the host (its result then answers the command)."""
        if rid not in self._pending or self.closed:
            return False
        try:
            await self._send({"type": "cancel", "id": rid})
        except (ConnectionError, OSError):
            return False
        return True

    def deliver_result(self, result: dict) -> bool:
        p = self._pending.get(result.get("id")) if isinstance(result, dict) else None
        if p is None or p.future.done():
            return False
        p.future.set_result(result)
        return True

    async def deliver_progress(self, progress: dict) -> bool:
        p = self._pending.get(progress.get("id")) if isinstance(progress, dict) else None
        if p is None or p.future.done() or progress.get("action") != p.action:
            return False
        if p.on_progress is not None:
            await p.on_progress(progress)
        return True

    def fail_all(self) -> None:
        """The session is gone: every command waiting on it fails now (HostGone)."""
        self.closed = True
        for p in list(self._pending.values()):
            if not p.future.done():
                p.future.set_exception(HostGone("the host session disconnected"))


class UxpAdapter:
    """A connected UXP panel that declared the action in its hello capabilities."""

    kind = "uxp"

    def __init__(self, link: HostLink, session_id: str = ""):
        self.link = link
        self.session_id = session_id

    async def run(self, request: dict, on_progress=None) -> dict:
        action, rid = request["action"], request["id"]
        timeout = max(0.0, min(seconds_left(request), UXP_TIMEOUT_MAX_S))
        try:
            return await self.link.call(request, on_progress, timeout)
        except TimeoutError:
            return failure(action, rid, "The panel did not answer before the request expired.",
                           "Look for a dialog in the Adobe app, dismiss it, then run the command again.")
        except (HostGone, ConnectionError, OSError):
            return failure(action, rid, "The panel disconnected before it answered.",
                           "Reopen the WhyNot Cut panel in the Adobe app (it reconnects by itself), then run the "
                           "command again.")
