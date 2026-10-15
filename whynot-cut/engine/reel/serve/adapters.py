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
                       answered ok:false without reaching the queue. build_project and ae_build_motion (SAFE_BUILDS,
                       Addendum G2 R1) never go to the queue as sent: they run the CLI's build (ppro_build /
                       motion_build.build_for_serve: Gate 1, the build lock, the editor and unsaved-changes checks, the
                       backup, free space) for the reel the request's output file names.
                       A CEP command is tracked while it runs (QueueTracker, H2): the queue's files are only READ, to
                       find its job (read only; no cep_queue change), and the journal moves received -> queued ->
                       claimed through jobs.Journal. The requester gets synthetic v4 progress with a `phase`
                       (docs/adobe/eng-data-contract.md 2.7): `queued` at once at submit, `claimed` when the bridge's
                       <id>.claimed / <id>.running appears, then an `elapsed` event every PROGRESS_TICK_S (2 s) with
                       `elapsed_s` until the result, so the first progress is never later than the click plus a moment
                       (budget S3). A job that ends with the bridge's <id>.error marker (it could not write its
                       result), or vanishes from the queue after it was seen with no result, is answered ok:false at
                       once instead of at the timeout.
    HostLink           the commands in flight to ONE connected host session: sends `command`, matches the `result`
                       by id, hands `progress` to the requester through a bounded per-command queue and its own relay
                       task (a requester that stops reading never stalls the host's receive loop; excess progress is
                       dropped, results never); on a timeout, and when the requester goes away (its task is
                       cancelled), it sends the host a best-effort `cancel` for that id; fail_all() when the host
                       session goes away.
    UxpAdapter         runs a command through a HostLink with the request's remaining time as the timeout.

Adapters return a v4 result dict; the router validates it (contract.validate_result) before anyone sees it.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import copy
import queue
import logging
import threading
import time
from datetime import datetime, timezone

from contract import RESERVED, load
from contract.cep import CEP_NAME, from_cep
from lib.common import current_context, use_context

from . import jobs

__all__ = ["ACTION_HOSTS", "HostGone", "FileQueueAdapter", "HostLink", "UxpAdapter", "QueueWorker", "QUEUE_WORKERS",
           "QueueTracker", "cancel_queued", "failure", "seconds_left"]

log = logging.getLogger(__name__)

ACTION_HOSTS: dict[str, str] = {a: e["host"] for a, e in load("protocol")["actions"].items()}
QUEUE_TIMEOUT_S = {"aftereffects": 900.0}          # the bridges' own defaults (ae_bridge 900 s, ppro_bridge 600 s)
QUEUE_TIMEOUT_DEFAULT_S = 600.0
UXP_TIMEOUT_MAX_S = 900.0
APP_NAMES = {"aftereffects": "After Effects"}       # everything else runs in Premiere
CANCEL_SEND_S = 1.0                                 # how long a best-effort cancel may take to send
PROGRESS_QUEUE = 32                                 # progress events waiting for one requester (more are dropped)
PROGRESS_FLUSH_S = 1.0                              # how long a finished command waits for its queued progress
SUBMIT_LOCKS = {"premiere": threading.Lock(), "aftereffects": threading.Lock()}   # one queue call per bridge
# G2 R1: builds run the CLI's build (lock, editor/unsaved checks, backup, Gate 1), not the raw bridge action
SAFE_BUILDS = {"build_project": ("lib.ppro_build", "PRPROJ_BUILT", "result"),
               "ae_build_motion": ("lib.motion_build", "PROJECT_ASSEMBLED", "report")}
TRACK_POLL_S = 0.5                                  # how often a running CEP job's queue files are looked at
PROGRESS_TICK_S = 2.0                               # the `elapsed` progress cadence (S3: first progress within 2 s)
VANISHED_POLLS = 3                                  # polls in a row with no file of a seen job and no result: gone
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
    """The legacy CEP bridge's file queue (Premiere's or After Effects'), run on that bridge's QueueWorker. `journal`
    (jobs.Journal) is the router's: the queue job's id and its queued / claimed state go there while the command runs
    (when none is given, the request's engine home's own)."""

    kind = "cep"

    def __init__(self, journal=None):
        self.journal = journal

    async def run(self, request: dict, on_progress=None) -> dict:
        action, rid = request["action"], request["id"]
        if action in RESERVED:                       # defence in depth: the router already answers these itself
            raise ValueError(f"{action!r} is reserved for Phase 6B and is never queued")
        if action not in CEP_NAME:
            raise ValueError(f"{action!r} has no CEP equivalent")
        name = CEP_NAME[action]
        host = ACTION_HOSTS.get(action)
        data = copy.deepcopy(request.get("data") or {})
        cap = QUEUE_TIMEOUT_S.get(host, QUEUE_TIMEOUT_DEFAULT_S)
        lane = "aftereffects" if host == "aftereffects" else "premiere"    # "any" (ping): Premiere is the primary
        app = APP_NAMES.get(host, "Premiere")

        ctx = current_context()                      # the request's (raises in reel serve when none is bound)
        began: dict = {}                             # when a safe build began (it holds the bridge's lock from then)

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
                    if action in SAFE_BUILDS:
                        began["t"] = time.time()
                        return _safe_build(action, data)
                    return bridge.submit(name, data, timeout=max(1.0, min(left, cap)))

        queue = bridge_queue(lane, ctx)
        if action in SAFE_BUILDS:                    # its queue job carries the approved plan's data, not the request's
            def locate():
                return _first_job(queue, name, began["t"]) if "t" in began else None
        else:
            sha, since = jobs.data_sha(data), time.time()

            def locate():
                return jobs.find_job(queue, name, sha, since)
        tracker = QueueTracker(rid, action, queue, locate, journal=self.journal or jobs.Journal(ctx.engine_home),
                               app=app)
        fut = asyncio.wrap_future(QUEUE_WORKERS[lane].submit(call))
        watch = asyncio.create_task(_track(tracker, on_progress))
        lost = None
        try:
            await asyncio.wait({fut, watch}, return_when=asyncio.FIRST_COMPLETED)
            if fut.done():                           # the queue's own answer wins over anything the watch saw
                r = fut.result()
            else:                                    # the bridge left an error marker, or the job vanished
                lost = watch.result()
        finally:
            watch.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await watch
            if not fut.done():                       # no answer needed: drop a call that has not started
                fut.cancel()
        if lost is not None:
            return lost
        if r is _EXPIRED:
            return failure(action, rid, "The request expired while it waited for the bridge queue (another command "
                                        "was running).",
                           "Run the command again once the running one has finished.")
        if action in SAFE_BUILDS:
            if r.get("ok"):
                return {"ok": True, "action": action, "id": rid, "readback": r["readback"]}
            return failure(action, rid, r["error"], r.get("how"))
        response = r.get("response") if isinstance(r, dict) else None
        if response is None and isinstance(r, dict) and r.get("error") == "interrupted":
            return jobs.bridge_restart_result(action, rid, app)        # a restarted bridge's own answer (H2)
        if response is not None:
            res = from_cep(action, response, id=rid)
        else:                                        # no parsed answer: the queue's own failure answers
            res = from_cep(action, _queue_failure(r), id=rid)
        if not res.get("ok") and not res.get("how"):
            res["how"] = (f"Check that WhyNot Cut runs in {app} (it starts by itself with {app}; restart {app} if "
                          "it does not answer), then run the command again.")
        return res


def _safe_build(action: str, data: dict) -> dict:
    """Addendum G2 R1: a build from serve is the CLI's build with all its gates (lib.*.build_for_serve), never the raw
    bridge action. {ok, readback} or {ok: false, error, how?} (lib.build_safety.serve_answer)."""
    from importlib import import_module
    from lib.build_safety import serve_answer
    mod, ok_status, readback = SAFE_BUILDS[action]
    try:
        r = import_module(mod).build_for_serve(data)
    except SystemExit as e:                          # an engine step that exits with a sentence (a missing plan)
        return {"ok": False, "error": str(e.code) if isinstance(e.code, str) else "The build stopped."}
    return serve_answer(r, ok_status, readback)


def bridge_queue(lane: str, ctx):
    """The lane's CEP queue folder under the request's engine home."""
    with use_context(ctx):
        if lane == "aftereffects":
            from lib import ae_bridge
            return ae_bridge.queue_dir()
        from lib import ppro_bridge
        return ppro_bridge.queue_dir()


def _first_job(queue, cep_name: str, since: float):
    """The first `cep_name` job written to `queue` at or after `since` (read only), else None."""
    import json
    from pathlib import Path
    best = None
    try:
        files = list(Path(queue).glob("*.data.json"))
    except OSError:
        return None
    for f in files:
        try:
            st = f.stat()
            if st.st_mtime < since - 1.0 or st.st_size > 8 * 1024 * 1024:
                continue
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict) and doc.get("action") == cep_name and (best is None or st.st_mtime < best[0]):
            best = (st.st_mtime, f.name[:-len(".data.json")])
    return best[1] if best else None


class QueueTracker:
    """H2: what a running CEP command looks like from the queue folder (read only; the bridge and cep_queue own the
    files). begin() gives the first progress event, `queued`, for the moment of submit. poll() (blocking file reads: run
    it on a thread) finds the command's queue job through `locate()`, journals its id and its queued / claimed state
    (jobs.Journal.update; a request with no journal entry writes nothing; the state never goes back from claimed),
    and returns `(events, failed)`:
        events   v4 progress events (progress.schema.json) with `phase` and `elapsed_s`: `claimed` once, when
                 <id>.claimed / <id>.running appears, and `elapsed` every `tick_s` (one event however long the poller
                 was starved) until the result;
        failed   None, or an ok:false v4 result when the job can no longer answer: the bridge left its `<id>.error`
                 marker with no result (it could not write one: jobs.error_marker_result), or a job seen in the queue
                 has had no file at all and no result for VANISHED_POLLS polls in a row (jobs.vanished_result; a
                 result that is read and removed by the caller looks the same for an instant, hence the grace).
    A result file always wins. `clock` is injectable (the tests' fake one)."""

    def __init__(self, rid: str, action: str, queue, locate, journal=None, clock=time.monotonic, tick_s=None,
                 app: str = "Premiere"):
        self.rid, self.action, self.queue, self.locate, self.journal = rid, action, queue, locate, journal
        self.clock, self.app = clock, app
        self.tick_s = PROGRESS_TICK_S if tick_s is None else tick_s
        self.t0 = clock()
        self.next_tick = self.t0 + self.tick_s
        self.phase = "queued"
        self.jid: str | None = None
        self.state = "received"                      # what the journal holds (the router started it as received)
        self.seen = False                            # a file of the job was seen in the queue
        self.missing = 0

    def _event(self, phase: str) -> dict:
        return {"event": "progress", "id": self.rid, "action": self.action, "step": phase, "phase": phase,
                "elapsed_s": round(max(0.0, self.clock() - self.t0), 1)}

    def begin(self) -> list[dict]:
        return [self._event("queued")]

    def _journal(self, **fields) -> None:
        if self.journal is None:
            return
        try:
            self.journal.update(self.rid, **fields)  # None: no entry for this request, nothing is written
        except (OSError, ValueError):
            self.journal = None                      # a journal that cannot be written never fails the command

    def poll(self) -> tuple[list[dict], dict | None]:
        events: list[dict] = []
        if self.jid is None:
            try:
                self.jid = self.locate()
            except Exception:                        # noqa: BLE001 — an unreadable queue is just "not found yet"
                self.jid = None
            if self.jid is not None:
                self._journal(job_id=self.jid)
        if self.jid is not None:
            now = jobs.job_state(self.queue, self.jid)
            if now in ("queued", "claimed", "done"):
                self.seen, self.missing = True, 0
            if now in ("claimed", "done") and self.phase == "queued":
                self.phase = "claimed"
                events.append(self._event("claimed"))
            if now in ("queued", "claimed") and now != self.state and not (self.state == "claimed" and now == "queued"):
                self.state = now
                self._journal(state=now)
            if now == "failed":
                return events, jobs.error_marker_result(self.action, self.rid, self.app)
            if now is None and self.seen:
                self.missing += 1
                if self.missing >= VANISHED_POLLS:
                    return events, jobs.vanished_result(self.action, self.rid, self.app)
        t = self.clock()
        if t >= self.next_tick:
            events.append(self._event("elapsed"))
            while self.next_tick <= t:
                self.next_tick += self.tick_s
        return events, None


async def _track(tracker: QueueTracker, on_progress) -> dict:
    """Run a QueueTracker beside the queue call: send `queued` now, then poll every TRACK_POLL_S on a thread and hand
    its events to the requester through a bounded relay (a requester that stops reading never stalls the poll; excess
    progress is dropped). Returns the ok:false result when the tracker finds the job failed; otherwise runs until it is
    cancelled (the queue call answered), and then lets what is queued reach the requester (bounded)."""
    pending = None
    if on_progress is not None:
        pending = _Pending(None, tracker.action, on_progress)
        pending.queue = asyncio.Queue(PROGRESS_QUEUE)
        pending.relay = asyncio.create_task(_relay(pending))

    def emit(events) -> None:
        for ev in events:
            if pending is not None:
                try:
                    pending.queue.put_nowait(ev)
                except asyncio.QueueFull:
                    pass

    try:
        emit(tracker.begin())
        while True:
            await asyncio.sleep(TRACK_POLL_S)
            events, failed = await asyncio.to_thread(tracker.poll)
            emit(events)
            if failed is not None:
                return failed
    finally:
        if pending is not None:
            await HostLink._stop_relay(pending, True)


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
    __slots__ = ("future", "action", "on_progress", "queue", "relay")

    def __init__(self, future, action, on_progress):
        self.future, self.action, self.on_progress = future, action, on_progress
        self.queue: asyncio.Queue | None = None      # progress waiting for the requester (bounded)
        self.relay: asyncio.Task | None = None       # the task that hands it over, one per command


async def _relay(p: _Pending) -> None:
    """Hand queued progress to the requester, in order. Runs in its own task, so a requester that stops reading
    stalls only this task, never the host session's receive loop."""
    while True:
        item = await p.queue.get()
        try:
            await p.on_progress(item)
        except (ConnectionError, OSError):
            pass                                     # the requester is gone: its command task ends soon
        except Exception as e:                       # noqa: BLE001 — a relay failure must not end the command
            log.warning("reel serve: progress relay failed (%s)", type(e).__name__)
        finally:
            p.queue.task_done()


class HostLink:
    """The commands in flight to one host session. `send(msg)` is the session's raising send coroutine."""

    def __init__(self, send):
        self._send = send
        self._pending: dict[str, _Pending] = {}
        self.closed = False
        self.progress_dropped = 0                    # progress events a slow requester never got

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
        pending = self._pending[rid] = _Pending(fut, request["action"], on_progress)
        flush = True
        try:
            await self._send({"type": "command", "request": request})
            try:
                async with asyncio.timeout(timeout):
                    return await asyncio.shield(fut)
            except TimeoutError:                     # tell the host to stop before the requester hears "no answer"
                await self._cancel_on_host(rid)
                raise
            except asyncio.CancelledError:           # the requester went away (or the daemon stops): same courtesy
                flush = False
                await self._cancel_on_host(rid)
                raise
        finally:
            self._pending.pop(rid, None)
            await self._stop_relay(pending, flush)
            if fut.done() and not fut.cancelled():
                fut.exception()                      # retrieved: never "Future exception was never retrieved"
            else:
                fut.cancel()

    async def _cancel_on_host(self, rid: str) -> None:
        """Best effort: tell the host to stop working on `rid` (bounded; never raises)."""
        if self.closed:
            return
        with contextlib.suppress(ConnectionError, OSError, TimeoutError):
            async with asyncio.timeout(CANCEL_SEND_S):
                await self._send({"type": "cancel", "id": rid})

    @staticmethod
    async def _stop_relay(p: _Pending, flush: bool) -> None:
        """Let the queued progress reach the requester before its result (bounded), then end the relay task."""
        if p.relay is None:
            return
        if flush:
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(PROGRESS_FLUSH_S):
                    await p.queue.join()
        p.relay.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await p.relay

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
        """Queue a progress event for the command's requester and return at once (never waits for the requester:
        the host session's receive loop calls this). When PROGRESS_QUEUE events already wait, it is dropped;
        results never take this path."""
        p = self._pending.get(progress.get("id")) if isinstance(progress, dict) else None
        if p is None or p.future.done() or progress.get("action") != p.action:
            return False
        if p.on_progress is None:
            return True
        if p.relay is None:
            p.queue = asyncio.Queue(PROGRESS_QUEUE)
            p.relay = asyncio.create_task(_relay(p))
        try:
            p.queue.put_nowait(progress)
        except asyncio.QueueFull:
            self.progress_dropped += 1
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
