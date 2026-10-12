"""WhyNot Cut command contract v4: the versioned shape of every host command (Premiere / After Effects).

A request is `{protocol, id, action, data, expires_at}`, a result `{ok, action, readback, error?, how?}`, progress events
`{event: "progress", ...}`. The JSON Schemas in this folder (draft 2020-12) are the single source of truth; the Python
engine checks them with the stdlib-only validator in `validator.py`, the UXP plugin and the engine daemon share the
files. `protocol.json` maps every action to its host and to the legacy CEP action name it replaces, and gives its
`status`: ACTIVE actions are routed; RESERVED ones (Phase 6B: Kalam / Hush / Tidy / WNC_AUDIO) have a name and a schema
and are never routed (serve.router answers them "reserved for Phase 6B").
"""
from __future__ import annotations

from .validator import CONTRACT_DIR, check_schema, load, validate, validate_request, validate_result

PROTOCOL = 4
ACTIONS = tuple(load("protocol")["actions"])
ACTIVE = tuple(a for a, e in load("protocol")["actions"].items() if e["status"] == "active")
RESERVED = tuple(a for a, e in load("protocol")["actions"].items() if e["status"] == "reserved")

__all__ = ["PROTOCOL", "ACTIONS", "ACTIVE", "RESERVED", "CONTRACT_DIR", "load", "validate", "check_schema",
           "validate_request", "validate_result"]
