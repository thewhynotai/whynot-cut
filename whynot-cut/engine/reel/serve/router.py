"""The command router of `reel serve` (3.0 T6.2): one `command` message in, one `result` (or `error`) message out.

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
"""
from __future__ import annotations

import asyncio
import logging

from contract import validate_request, validate_result
from contract.cep import CEP_NAME
from lib.common import Context, use_context

from . import messages
from .adapters import ACTION_HOSTS, FileQueueAdapter, UxpAdapter, failure, seconds_left

__all__ = ["Router", "OUTSIDE_CONTRACT"]

log = logging.getLogger(__name__)

OUTSIDE_CONTRACT = "host answered outside the contract"
OUTSIDE_HOW = ("The panel or bridge sent an answer this engine cannot check: update the WhyNot Cut panel and bridge "
               "to this engine's version, then run the command again.")


class Router:
    """`sessions()` lists the connected, authenticated sessions (objects with id, kind, host, capabilities, link)."""

    def __init__(self, *, home, sessions, file_queue=None, audit=None):
        self.home = home
        self._sessions = sessions
        self.file_queue = file_queue if file_queue is not None else FileQueueAdapter()
        self.audit = audit
        self._running: dict[str, object] = {}          # request id -> the adapter running it

    def _audit(self, event, **kw) -> None:
        if self.audit is not None:
            self.audit.log(event, **kw)

    def pick(self, action: str):
        """(adapter, label) for `action`, or (None, reason). The most recently connected capable session wins."""
        host = ACTION_HOSTS.get(action)
        for s in reversed(list(self._sessions())):
            if (s.kind == "uxp" and not s.link.closed and action in s.capabilities
                    and (host == "any" or s.host == host)):
                return UxpAdapter(s.link, s.id), f"uxp:{s.id}"
        if action in CEP_NAME:
            return self.file_queue, "cep"
        return None, "no connected panel implements it and it has no CEP bridge action"

    async def handle(self, msg: dict, *, send=None, peer: str = "", session_id: str | None = None) -> dict:
        """The message answering a validated `command` message. `send(msg)` delivers progress to the requester."""
        req = msg["request"]
        rid, action = req["id"], req["action"]
        errors = validate_request(req)
        if errors:
            self._audit("command", peer=peer, session=session_id, action=action, outcome="rejected",
                        reason="schema: " + "; ".join(errors))
            return messages.error("schema", "; ".join(errors), rid)
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

        async def relay(progress: dict) -> None:
            if send is not None:
                await send({"type": "progress", "progress": progress})

        self._running[rid] = adapter
        self._audit("command", peer=peer, session=session_id, action=action, outcome="routed", reason=label)
        try:
            with use_context(ctx):
                res = await adapter.run(req, on_progress=relay)
        except asyncio.CancelledError:
            raise
        except Exception as e:                              # an adapter bug must not kill the session
            log.warning("reel serve: %s failed in the %s adapter (%s)", action, label, type(e).__name__)
            self._audit("command", peer=peer, session=session_id, action=action, outcome="failed",
                        reason=type(e).__name__)
            res = failure(action, rid, f"The engine failed while running {action} ({type(e).__name__}).",
                          "Run the command again; if it repeats, restart reel serve and send its log.")
        finally:
            self._running.pop(rid, None)
        return {"type": "result", "result": self.checked(res, action, rid, peer=peer, session_id=session_id,
                                                         label=label)}

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
