"""The command router of `reel serve` (3.0 T6.2): one `command` message in, one `result` (or `error`) message out.

    0. a RESERVED action (protocol.json status "reserved": the Phase 6B Kalam / Hush / Tidy / WNC_AUDIO host operations)
       is never routed: it is answered `ok: false` "reserved for Phase 6B (<tool>), not available yet" with a `how`,
       before data, expiry or adapters are looked at (the session schema already checked the envelope), and audited
       with outcome "reserved";
    1. contract.validate_request: the envelope and the action's data (`schema` error otherwise; an unknown action is
       already refused by the session schema's action enum);
    2. expires_at in the past -> `timeout` error; an id that is already running -> `schema` error;
    3. pick the adapter: a connected UXP session whose hello capabilities include the action and whose host matches
       the action's host (protocol.json; "any" matches every host) -> UxpAdapter; else the action has a CEP name ->
       FileQueueAdapter; else `no_route`;
    4. run it inside a fresh engine Context(root, profile, home=<daemon home>) bound with common.use_context, relaying
       the host's progress events to the requester;
    5. validate the answer (contract.validate_result, same action, same id): anything else becomes
       `ok: false, error: "host answered outside the contract"` and is audit-logged.
There is no action that evaluates code: the actions are the contract's closed list, and no adapter takes a script.

The job journal (serve/jobs.py, Addendum G2 hardening H1): before expiry and routing, the request id is looked up.
    * an id that cannot name a journal file (jobs.valid_id) is a `schema` error;
    * an id running in this daemon: the requester ATTACHES to it (its progress and its result), nothing runs again;
    * an id the journal holds as done / failed / interrupted: its stored result is REPLAYED, nothing runs again;
    * an id the journal holds as still active with nothing running it here: interrupted (and replayed so).
A routed command runs in a task the Router owns (_Job), never in the requester's: the requester only waits for it.
Ending a session cancels only the UXP-routed jobs it sent (session_ended; the panel is told to stop, the entry becomes
interrupted). CEP file-queue jobs keep running and their result lands in the journal, where a reconnect finds it.
While a CEP job runs, its queue files are watched (read only) for its job id and its queued / claimed state. At daemon
start recover() reconciles the journal with the queue files (jobs.reconcile) and follows the jobs still in a live
bridge's queue to their result.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging

from contract import RESERVED, validate_request, validate_result
from contract.cep import CEP_NAME
from lib.common import Context, use_context

from . import jobs, messages
from .adapters import ACTION_HOSTS, FileQueueAdapter, UxpAdapter, failure, seconds_left

__all__ = ["Router", "OUTSIDE_CONTRACT", "reserved_result"]

log = logging.getLogger(__name__)

OUTSIDE_CONTRACT = "host answered outside the contract"
OUTSIDE_HOW = ("The panel or bridge sent an answer this engine cannot check: update the WhyNot Cut panel and bridge "
               "to this engine's version, then run the command again.")

BAD_ID = ("The request id cannot be kept in the job journal: it must start with a letter or digit, use only letters, "
          "digits, '.', '_' and '-' (no '..'), and not be a device name such as CON or NUL.")
WATCH_S = 0.5                   # how often a running CEP job's queue files are looked at
FOLLOW_MAX_S = 1260.0           # a job adopted at start is given up after this (the bridge's own 20-minute limit + 1)
HOST_CHECK_S = 2.0              # how often an adopted job's bridge heartbeat is read
HOST_DEAD_CHECKS = 3            # this many dead heartbeats in a row: the adopted job is interrupted
UXP_GONE = ("The command was stopped: the session that sent it disconnected.",
            "Reopen the WhyNot Cut panel (it reconnects by itself), then press Try again.")
DAEMON_GONE = ("The command was stopped because reel serve shut down.",
               "Start the engine again from your Claude session, then press Try again.")


def lane_of(action: str) -> str:
    """The CEP queue an action runs on (FileQueueAdapter's rule: "any" (ping) runs on Premiere's)."""
    return "aftereffects" if ACTION_HOSTS.get(action) == "aftereffects" else "premiere"


def queue_dir(lane: str):
    """The lane's queue folder under the bound Context's engine home (the bridges' own rule)."""
    if lane == "aftereffects":
        from lib import ae_bridge
        return ae_bridge.queue_dir()
    from lib import ppro_bridge
    return ppro_bridge.queue_dir()


def bridge_alive(lane: str) -> bool:
    """The lane's bridge heartbeat is fresh (under the bound Context)."""
    if lane == "aftereffects":
        from lib import ae_bridge
        return bool(ae_bridge.status().get("alive"))
    from lib import ppro_bridge
    return bool(ppro_bridge.status().get("alive"))


class _Job:
    """One command in flight in this daemon: the Router's task that runs it and the requesters waiting for it."""
    __slots__ = ("rid", "action", "route", "owner", "task", "listeners")

    def __init__(self, rid: str, action: str, route: str, owner):
        self.rid, self.action, self.route, self.owner = rid, action, route, owner
        self.task: asyncio.Task | None = None
        self.listeners: list = []                     # the requesters' send(msg) coroutines (progress)


# Phase 6B (Addendum A2): the tool and the task that will make each reserved action prefix work
RESERVED_TOOLS = {"audio": ("WNC_AUDIO shared audio export", "T6.11"), "hush": ("Hush", "T6.12"),
                  "tidy": ("Tidy", "T6.13"), "kalam": ("Kalam", "T6.14")}


def reserved_result(action: str, rid: str) -> dict:
    """The `ok: false` answer to a reserved action (it validates with contract.validate_result)."""
    if action not in RESERVED:
        raise ValueError(f"{action!r} is not a reserved action")
    tool, task = RESERVED_TOOLS[action.split("_", 1)[0]]
    return failure(action, rid, f"reserved for Phase 6B ({tool}), not available yet",
                   f"This WhyNot Cut version only reserves {action}; Phase 6B ({task}) builds it. Nothing to fix on "
                   "your side: update WhyNot Cut when that version ships.")


class Router:
    """`sessions()` lists the connected, authenticated sessions (objects with id, kind, host, capabilities, link)."""

    def __init__(self, *, home, sessions, file_queue=None, audit=None, journal=None):
        self.home = home
        self._sessions = sessions
        self.file_queue = file_queue if file_queue is not None else FileQueueAdapter()
        self.audit = audit
        self.journal = journal if journal is not None else jobs.Journal(home)
        self._running: dict[str, object] = {}          # request id -> the adapter running it
        self._jobs: dict[str, _Job] = {}               # request id -> the job running it in this daemon
        self._closing = False
        self._journal_failed = False

    def _audit(self, event, **kw) -> None:
        if self.audit is not None:
            self.audit.log(event, **kw)

    def pick(self, action: str):
        """(adapter, label) for `action`, or (None, reason). The most recently connected capable session wins."""
        if action in RESERVED:                         # Phase 6B: no panel or queue runs it, whatever it claims
            return None, f"{action} is reserved for Phase 6B"
        host = ACTION_HOSTS.get(action)
        for s in reversed(list(self._sessions())):
            if (s.kind == "uxp" and not s.link.closed and action in s.capabilities
                    and (host == "any" or s.host == host)):
                return UxpAdapter(s.link, s.id), f"uxp:{s.id}"
        if action in CEP_NAME:
            return self.file_queue, "cep"
        return None, "no connected panel implements it and it has no CEP bridge action"

    async def handle(self, msg: dict, *, send=None, peer: str = "", session_id: str | None = None,
                     session_kind: str | None = None) -> dict:
        """The message answering a validated `command` message. `send(msg)` delivers progress to the requester."""
        req = msg["request"]
        rid, action = req["id"], req["action"]
        if action in RESERVED:
            self._audit("command", peer=peer, session=session_id, action=action, outcome="reserved",
                        reason="reserved for Phase 6B, not routed")
            return {"type": "result", "result": reserved_result(action, rid)}
        errors = validate_request(req)
        if errors:
            self._audit("command", peer=peer, session=session_id, action=action, outcome="rejected",
                        reason="schema: " + "; ".join(errors))
            return messages.error("schema", "; ".join(errors), rid)
        if not jobs.valid_id(rid):
            self._audit("command", peer=peer, session=session_id, action=action, outcome="rejected",
                        reason="request id not journalable")
            return messages.error("schema", BAD_ID, rid)
        job = self._jobs.get(rid)
        if job is not None:                                 # in flight here: attach, never run it twice
            if job.action != action:
                return messages.error("schema", f"The id {rid} belongs to another command ({job.action}): use a "
                                                "new id.", rid)
            self._audit("command", peer=peer, session=session_id, action=action, outcome="attached",
                        reason=f"already running ({job.route})")
            return await self._attach(job, send)
        entry = self._journal_get(rid)
        if entry is not None:                               # known: replay what it came to, never run it again
            if entry["action"] != action:
                return messages.error("schema", f"The id {rid} belongs to another command ({entry['action']}): use "
                                                "a new id.", rid)
            res = entry.get("result")
            if entry["state"] not in jobs.FINAL or not isinstance(res, dict):
                app = jobs.APP_NAMES.get(entry.get("lane") or "premiere", "Premiere")
                why = UXP_GONE if entry.get("route") == "uxp" else (jobs.GONE_WHY.format(app=app),
                                                                    jobs.GONE_HOW.format(app=app))
                res = failure(action, rid, *why)
                self._journal(self.journal.finish, rid, res, "interrupted")
                state = "interrupted"
            else:
                state = entry["state"]
            self._audit("command", peer=peer, session=session_id, action=action, outcome="replayed", reason=state)
            return {"type": "result", "result": {**res, "id": rid}}
        if seconds_left(req) <= 0:
            self._audit("command", peer=peer, session=session_id, action=action, outcome="rejected", reason="expired")
            return messages.error("timeout", "The request expired before it could run (expires_at is past).", rid)
        if rid in self._running:
            return messages.error("schema", f"A command with id {rid} is already running: use a new id.", rid)
        adapter, label = self.pick(action)
        if adapter is None:
            self._audit("command", peer=peer, session=session_id, action=action, outcome="rejected", reason="no_route")
            return messages.error("no_route", f"Nothing can run {action} now: {label}.", rid)
        ctx_in = msg.get("context") or {}
        try:
            ctx = Context(ctx_in.get("root") or None, ctx_in.get("profile") or None, home=self.home)
        except (OSError, ValueError, RuntimeError):
            return messages.error("schema", "context.root is not a usable folder path.", rid)

        route = "uxp" if isinstance(adapter, UxpAdapter) else "cep"
        job = _Job(rid, action, route, session_id)
        self._jobs[rid] = job
        self._running[rid] = adapter
        self._journal(self.journal.start, rid, action=action, session_kind=session_kind, route=route,
                      lane=lane_of(action) if route == "cep" else None, data=req.get("data"),
                      expires_at=req.get("expires_at"))
        self._audit("command", peer=peer, session=session_id, action=action, outcome="routed", reason=label)
        job.task = asyncio.create_task(self._run(job, adapter, req, ctx, label, peer, session_id))
        return await self._attach(job, send)

    # ------------------------------------------------------------------------------------------------ jobs
    def _journal(self, fn, *a, **kw):
        """A journal write; a failing disk is logged once and never fails the command (only the replay is lost)."""
        try:
            return fn(*a, **kw)
        except (OSError, ValueError) as e:
            if not self._journal_failed:
                self._journal_failed = True
                log.warning("reel serve: the job journal could not be written (%s); commands still run",
                            type(e).__name__)
            return None

    def _journal_get(self, rid: str):
        try:
            return self.journal.get(rid)
        except (OSError, ValueError):
            return None

    async def _attach(self, job: _Job, send) -> dict:
        """Wait for the job (this waiter going away never cancels it) and answer with its result."""
        if send is not None:
            job.listeners.append(send)
        try:
            await asyncio.wait({job.task})
        finally:
            with contextlib.suppress(ValueError):
                job.listeners.remove(send)
        if job.task.cancelled():
            entry = self._journal_get(job.rid) or {}
            res = entry.get("result") if entry.get("state") in jobs.FINAL else None
            if not isinstance(res, dict):
                res = failure(job.action, job.rid, *(DAEMON_GONE if self._closing else UXP_GONE))
            return {"type": "result", "result": {**res, "id": job.rid}}
        return {"type": "result", "result": job.task.result()}

    @staticmethod
    async def _relay(job: _Job, progress: dict) -> None:
        for send in list(job.listeners):
            try:
                await send({"type": "progress", "progress": progress})
            except (ConnectionError, OSError):
                pass

    async def _run(self, job: _Job, adapter, req: dict, ctx, label: str, peer: str, session_id) -> dict:
        rid, action = job.rid, job.action
        watcher = asyncio.create_task(self._watch(job, ctx, req)) if job.route == "cep" else None

        async def relay(progress: dict) -> None:
            await self._relay(job, progress)

        try:
            with use_context(ctx):
                res = await adapter.run(req, on_progress=relay)
        except asyncio.CancelledError:
            if job.route == "uxp":                         # its session ended (or the daemon stops): the host was told
                why = DAEMON_GONE if self._closing else UXP_GONE
                self._journal(self.journal.finish, rid, failure(action, rid, *why), "interrupted")
            # a CEP job is cancelled only when the daemon stops: its entry stays active for the next start's reconcile
            raise
        except Exception as e:                              # an adapter bug must not kill the session
            log.warning("reel serve: %s failed in the %s adapter (%s)", action, label, type(e).__name__)
            self._audit("command", peer=peer, session=session_id, action=action, outcome="failed",
                        reason=type(e).__name__)
            res = failure(action, rid, f"The engine failed while running {action} ({type(e).__name__}).",
                          "Run the command again; if it repeats, restart reel serve and send its log.")
        finally:
            if watcher is not None:
                watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await watcher
            self._running.pop(rid, None)
            self._jobs.pop(rid, None)
        res = self.checked(res, action, rid, peer=peer, session_id=session_id, label=label)
        self._journal(self.journal.finish, rid, res)
        return res

    async def _watch(self, job: _Job, ctx, req: dict) -> None:
        """While a CEP job runs: find its queue job (read only) and journal its job id and queued / claimed state."""
        cep_name = CEP_NAME.get(job.action)
        if not cep_name:
            return
        with use_context(ctx):
            try:
                queue = queue_dir(lane_of(job.action))
            except Exception:                               # noqa: BLE001 — no queue folder: nothing to watch
                return
        sha = jobs.data_sha(req.get("data"))
        since = float((self._journal_get(job.rid) or {}).get("_t") or 0.0)
        jid, state = None, "received"
        while True:
            await asyncio.sleep(WATCH_S)
            if jid is None:
                jid = await asyncio.to_thread(jobs.find_job, queue, cep_name, sha, since)
                if jid is None:
                    continue
                self._journal(self.journal.update, job.rid, job_id=jid)
            now = await asyncio.to_thread(jobs.job_state, queue, jid)
            if now in ("queued", "claimed") and now != state and not (state == "claimed" and now == "queued"):
                state = now
                self._journal(self.journal.update, job.rid, state=now)
            if now == "done":                               # _run cancels this watcher when the adapter answers
                return

    def session_ended(self, session_id) -> list:
        """A session went away: cancel the UXP-routed jobs it sent (CEP jobs keep running). Returns their tasks."""
        out = []
        for job in list(self._jobs.values()):
            if job.route == "uxp" and job.owner == session_id and job.task is not None and not job.task.done():
                job.task.cancel()
                out.append(job.task)
        return out

    async def close(self, timeout: float = 0.3) -> None:
        """The daemon stops: cancel every job task (a CEP job left in the queue is reconciled at the next start)."""
        self._closing = True
        tasks = [j.task for j in self._jobs.values() if j.task is not None and not j.task.done()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)

    async def recover(self) -> int:
        """Daemon start: reconcile the journal with the queue files (on a worker thread) and follow the jobs still in
        a live bridge's queue. Returns how many are followed."""
        ctx = Context(home=self.home)

        def in_ctx(fn):
            def call(*a):
                with use_context(ctx):
                    return fn(*a)
            return call

        try:
            live = await asyncio.to_thread(jobs.reconcile, self.journal, in_ctx(queue_dir), in_ctx(bridge_alive),
                                           lambda a: CEP_NAME.get(a, ""))
        except (OSError, ValueError) as e:
            log.warning("reel serve: the job journal could not be reconciled (%s)", type(e).__name__)
            return 0
        for entry in live:
            job = _Job(entry["request_id"], entry["action"], "cep", None)
            self._jobs[job.rid] = job
            job.task = asyncio.create_task(self._follow(job, entry, ctx))
        if live:
            log.info("reel serve: following %d job(s) a previous daemon left in the queue", len(live))
        return len(live)

    async def _follow(self, job: _Job, entry: dict, ctx) -> dict:
        """A job a previous daemon queued: poll its queue files until its result (done / failed), or until its job
        files are gone, its bridge stops beating or FOLLOW_MAX_S passes (interrupted)."""
        rid, action, jid = job.rid, job.action, entry["job_id"]
        lane = entry.get("lane") or "premiere"
        app = jobs.APP_NAMES.get(lane, "Premiere")
        with use_context(ctx):
            queue = queue_dir(lane)
        loop = asyncio.get_running_loop()
        deadline, checked, dead, missing = loop.time() + FOLLOW_MAX_S, loop.time(), 0, 0
        state = entry.get("state")

        def alive() -> bool:
            with use_context(ctx):
                return bridge_alive(lane)
        try:
            while True:
                now = await asyncio.to_thread(jobs.job_state, queue, jid)
                if now == "done":
                    res = await asyncio.to_thread(jobs.read_result, queue, jid, action, rid, app)
                    if res is not None:
                        res = self.checked(res, action, rid, label="cep (followed)")
                        self._journal(self.journal.finish, rid, res)
                        return res
                missing = missing + 1 if now is None else 0
                if now in ("queued", "claimed") and now != state:
                    state = now
                    self._journal(self.journal.update, rid, state=now)
                if loop.time() - checked >= HOST_CHECK_S:
                    checked = loop.time()
                    try:
                        dead = 0 if await asyncio.to_thread(alive) else dead + 1
                    except Exception:                       # noqa: BLE001
                        dead += 1
                if missing >= 3 or dead >= HOST_DEAD_CHECKS or loop.time() >= deadline:
                    res = failure(action, rid, jobs.GONE_WHY.format(app=app), jobs.GONE_HOW.format(app=app))
                    self._journal(self.journal.finish, rid, res, "interrupted")
                    return res
                await asyncio.sleep(WATCH_S)
        finally:
            self._jobs.pop(rid, None)

    def checked(self, res, action: str, rid: str, *, peer="", session_id=None, label="") -> dict:
        """`res` with the request id when it is a valid result for this action and id; else the contract failure."""
        problems = []
        if not isinstance(res, dict):
            problems.append("not an object")
        else:
            if res.get("action") != action:
                problems.append(f"/action: {res.get('action')!r} answers {action!r}")
            if res.get("id", rid) != rid:
                problems.append("/id: another request's id")
            if not problems:
                res = {**res, "id": rid}
                problems = validate_result(res)
        if not problems:
            return res
        self._audit("result-invalid", peer=peer, session=session_id, action=action, outcome="rejected",
                    reason=f"{label}: " + "; ".join(problems))
        return failure(action, rid, OUTSIDE_CONTRACT, OUTSIDE_HOW)

    async def cancel(self, rid: str) -> dict | None:
        """A client's cancel: forwarded to the panel running it (its result answers); else an error message."""
        adapter = self._running.get(rid)
        if isinstance(adapter, UxpAdapter) and await adapter.link.cancel(rid):
            return None
        if adapter is not None:
            return messages.error("no_route", "This command runs through the CEP bridge and cannot be cancelled.", rid)
        return messages.error("no_route", "No running command has this id.", rid)
