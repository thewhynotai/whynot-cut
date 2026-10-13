"""Session messages of `reel serve` (3.0 T6.2): the type-dispatching validator and the builders of daemon messages.

Every WebSocket message is one JSON object tagged by `type` (contract/session.schema.json). validate_message checks it
against that type's own definition, so a schema error names what is wrong with THAT message instead of the 13-branch
`oneOf` dump of the whole `message` union. Pure: no I/O, no state.
"""
from __future__ import annotations

import re

from contract import validate
from contract.validator import load

__all__ = ["TYPES", "CLIENT_TYPES", "DAEMON_TYPES", "ID_RE", "MESSAGE_MAX", "PANEL_UPDATES", "validate_message",
           "message_id", "error", "reply", "welcome", "state", "clip", "compare_builds", "BUILD_ID_RE"]

TYPES = tuple(ref["$ref"].rsplit("/", 1)[1] for ref in load("session")["$defs"]["message"]["oneOf"])
DAEMON_TYPES = frozenset({"welcome", "state", "reply", "error"})            # only the daemon sends these
CLIENT_TYPES = frozenset(TYPES) - DAEMON_TYPES
ID_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")                                 # session.schema.json $defs/id
MESSAGE_MAX = 2000                                                          # error.message / reply.error maxLength
PANEL_UPDATES = ("ok", "stale", "newer", "unknown")                         # welcome.update.panel
BUILD_ID_RE = re.compile(r"[0-9]{8}T[0-9]{6}Z")                             # the build id: 20261013T142530Z (UTC)
BUILD_MAX = 64                                                              # hello client.build maxLength


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


def _build_ok(b) -> bool:
    """A usable build value: a string of 1-64 characters with no control character."""
    return isinstance(b, str) and 0 < len(b) <= BUILD_MAX and not any(ord(c) < 32 or ord(c) == 127 for c in b)


def compare_builds(panel, expected) -> str:
    """welcome.update.panel (C1.8 / C2.3): the hello's client.build against expected.json `build`.
    The build id is the UTC time of the build, YYYYMMDDTHHMMSSZ (premiere-uxp/scripts/build.mjs buildId): the panel's
    __WNC_BUILD__ and the .ccx's build.json `build` are one id, and release.py writes the shipped ccx's id into
    expected.json. Two ids compare as text, which is time order: equal "ok", older "stale" (restart Premiere), newer
    "newer". Two usable values that differ in any other way (a panel stamped before the shared id, a hand-written
    expected.json) are "stale": expected.json is the authority, so the editor is told to restart. The same text is
    "ok" whatever its shape. Missing or malformed (not a string, empty, over 64 characters, a control character) is
    "unknown"."""
    if not _build_ok(panel) or not _build_ok(expected):
        return "unknown"
    if panel == expected:
        return "ok"
    if BUILD_ID_RE.fullmatch(panel) and BUILD_ID_RE.fullmatch(expected):
        return "stale" if panel < expected else "newer"
    return "stale"


def welcome(session_id: str, daemon_version: str, update: str = "unknown") -> dict:
    return {"type": "welcome", "session_id": session_id, "protocol": 4, "daemon_version": daemon_version,
            "update": {"panel": update if update in PANEL_UPDATES else "unknown"}}


def state(host_state: str, host_detail: str | None = None, id: str | None = None, item: dict | None = None) -> dict:
    """The daemon's `state`: the connection (engine connected, which host path is live; the Claude pill stays "unknown"
    until the T6.2b probe exists) and, from engine_state.panel_fields, the item's client, item, pipeline, approval and
    QC tiles. Language, editor name, context and log are the panel's own."""
    host: dict = {"state": host_state}
    if host_detail:
        host["detail"] = clip(host_detail, 256)
    out: dict = {"type": "state", "state": {
        "connection": {"engine": "connected", "claude": "unknown", "host": host},
        "client": "", "item": "", "language": "en", "editor_name": "",
        "context": {"project_path": None, "sequence_name": None, "folder": None, "out_dir": None, "review_mp4": None},
        "pipeline": [], "approval": None, "qc": [], "log": []}}
    for key in ("client", "item", "pipeline", "approval", "qc"):
        if item and key in item:
            out["state"][key] = item[key]
    if isinstance(id, str) and ID_RE.fullmatch(id):
        out["id"] = id
    return out
