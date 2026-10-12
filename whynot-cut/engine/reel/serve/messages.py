"""Session messages of `reel serve` (3.0 T6.2): the type-dispatching validator and the builders of daemon messages.

Every WebSocket message is one JSON object tagged by `type` (contract/session.schema.json). validate_message checks it
against that type's own definition, so a schema error names what is wrong with THAT message instead of the 13-branch
`oneOf` dump of the whole `message` union. Pure: no I/O, no state.
"""
from __future__ import annotations

import re

from contract import validate
from contract.validator import load

__all__ = ["TYPES", "CLIENT_TYPES", "DAEMON_TYPES", "ID_RE", "MESSAGE_MAX", "validate_message", "message_id", "error",
           "reply", "welcome", "state", "clip"]

TYPES = tuple(ref["$ref"].rsplit("/", 1)[1] for ref in load("session")["$defs"]["message"]["oneOf"])
DAEMON_TYPES = frozenset({"welcome", "state", "reply", "error"})            # only the daemon sends these
CLIENT_TYPES = frozenset(TYPES) - DAEMON_TYPES
ID_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")                                 # session.schema.json $defs/id
MESSAGE_MAX = 2000                                                          # error.message / reply.error maxLength


def validate_message(msg) -> tuple[str, list[str]] | None:
    """None when `msg` is a valid session message, else (code, errors): `unknown_type` when `type` is missing or not a
    session type, `schema` when the object breaks its type's definition (or is not an object at all)."""
    if not isinstance(msg, dict):
        return "schema", ["/: a session message is a JSON object"]
    t = msg.get("type")
    if not isinstance(t, str) or t not in TYPES:
        return "unknown_type", [f"/type: expected one of {', '.join(TYPES)}"]
    errors = validate(msg, f"session#/$defs/{t}")
    return ("schema", errors) if errors else None


def message_id(msg) -> str | None:
    """The id a reply may echo: the message's `id` (or its request's id) when it is a valid correlation id."""
    if not isinstance(msg, dict):
        return None
    mid = msg.get("id")
    if mid is None and isinstance(msg.get("request"), dict):
        mid = msg["request"].get("id")
    return mid if isinstance(mid, str) and ID_RE.fullmatch(mid) else None


def clip(text, n: int = MESSAGE_MAX) -> str:
    text = str(text) if text is not None else ""
    return text if len(text) <= n else text[:n - 1] + "…"


def error(code: str, message: str, id: str | None = None) -> dict:
    """An `error` message; an id that is not a valid correlation id is left out (it could not be echoed)."""
    out = {"type": "error", "code": code, "message": clip(message) or code}
    if isinstance(id, str) and ID_RE.fullmatch(id):
        out["id"] = id
    return out


def reply(intent: str, id: str, *, ok: bool, error: str | None = None, how: str | None = None,
          readback: dict | None = None) -> dict:
    out: dict = {"type": "reply", "id": id, "intent": intent, "ok": ok}
    if readback is not None:
        out["readback"] = readback
    if not ok:
        out["error"] = clip(error or "failed")
        if how:
            out["how"] = clip(how)
    return out


def welcome(session_id: str, daemon_version: str) -> dict:
    return {"type": "welcome", "session_id": session_id, "protocol": 4, "daemon_version": daemon_version}


def state(host_state: str, host_detail: str | None = None, id: str | None = None) -> dict:
    """The serve core's `state`: the connection only (engine connected, which host path is live); client, item,
    pipeline, approval, QC and log stay empty until the engine-state task fills them."""
    host: dict = {"state": host_state}
    if host_detail:
        host["detail"] = clip(host_detail, 256)
    out: dict = {"type": "state", "state": {
        "connection": {"engine": "connected", "claude": "unknown", "host": host},
        "client": "", "item": "", "language": "en", "editor_name": "",
        "context": {"project_path": None, "sequence_name": None, "folder": None, "out_dir": None, "review_mp4": None},
        "pipeline": [], "approval": None, "qc": [], "log": []}}
    if isinstance(id, str) and ID_RE.fullmatch(id):
        out["id"] = id
    return out
