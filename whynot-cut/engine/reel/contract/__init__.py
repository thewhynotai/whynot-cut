"""WhyNot Cut command contract v4: the versioned shape of every host command (Premiere / After Effects).

A request is `{protocol, id, action, data, expires_at}`, a result `{ok, action, readback, error?, how?}`, progress events
`{event: "progress", ...}`. The JSON Schemas in this folder (draft 2020-12) are the single source of truth; the Python
engine checks them with the stdlib-only validator in `validator.py`, the UXP plugin and the engine daemon share the
files. `protocol.json` maps every action to its host and to the legacy CEP action name it replaces.
"""
from __future__ import annotations

from .validator import CONTRACT_DIR, check_schema, load, validate, validate_request, validate_result

PROTOCOL = 4
ACTIONS = tuple(load("protocol")["actions"])

__all__ = ["PROTOCOL", "ACTIONS", "CONTRACT_DIR", "load", "validate", "check_schema", "validate_request",
           "validate_result"]
