"""Is Adobe exporting or rendering? Read only (3.0 Addendum G2 hardening H6, G13).

The CEP bridge's hidden daemon puts `host_busy` in every heartbeat (adobe/cep-bridge/js/bridge.js, from memory, no host
call): "exporting" | "rendering" | "idle" | "unknown". Premiere counts app.encoder's job events, After Effects probes
app.project.renderQueue.rendering just before each job; anything the bridge cannot vouch for is "unknown". This module
reads it back, never writes anything and never touches Adobe:

    host_busy(home=None, *, now=None) -> {"premiere": v, "after_effects": v, "overall": v}

    per lane: one of HOST_BUSY, or "offline" when no bridge beats in that app (no heartbeat file, or one that stopped
              more than RECENT_S ago: the app is not running). A heartbeat that is not fresh (FRESH_S, the engine's own
              rule, cep_queue.status) but stopped less than RECENT_S ago is "unknown": the app may be frozen in a
              render rather than quit. An unreadable heartbeat, or a value outside HOST_BUSY, is "unknown".
    overall:  "exporting" if a lane exports, else "rendering" if a lane renders, else "unknown" if a lane is unknown,
              else "idle" (every lane idle or offline: no WhyNot Cut bridge sees Adobe busy).

The engine GPU lock (G-GPU, Phase 4) calls host_busy() before a GPU job and waits or yields on "exporting" /
"rendering"; what it does with "unknown" is its own policy. `home` defaults to the engine home of the bound Context.
`reel serve` shows the Premiere lane in panel_state.connection.host.busy (serve/app.py _host) through lane_value().
"""
from __future__ import annotations

import json
import time
from pathlib import Path

__all__ = ["HOST_BUSY", "LANES", "FRESH_S", "RECENT_S", "beat_value", "lane", "lane_value", "host_busy"]

HOST_BUSY = ("exporting", "rendering", "idle", "unknown")
LANES = {"premiere": "ppro-queue", "after_effects": "ae-queue"}
FRESH_S = 5.0          # cep_queue.status max_age_s: a beat older than this is not a running bridge
RECENT_S = 120.0       # a beat that stopped less than this ago: the app may be frozen (unknown), not quit (offline)
HEARTBEAT = "bridge.heartbeat"


def beat_value(beat) -> str:
    """The heartbeat dict's host_busy when it is one of HOST_BUSY, else "unknown" (an older bridge has none)."""
    v = beat.get("host_busy") if isinstance(beat, dict) else None
    return v if isinstance(v, str) and v in HOST_BUSY else "unknown"


def lane(queue, *, now: float | None = None) -> str:
    """One queue folder's value: HOST_BUSY or "offline" (one read of its heartbeat, nothing else)."""
    hb = Path(queue) / HEARTBEAT
    now = time.time() if now is None else now
    try:
        raw = hb.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "offline"
    except OSError:
        return "unknown"
    try:
        beat = json.loads(raw)
        age = now - float(beat["at"]) / 1000
    except (ValueError, TypeError, KeyError, OverflowError):
        return "unknown"                     # a torn or broken beat: something writes it, so not offline
    if age < FRESH_S:
        return beat_value(beat)
    return "unknown" if age < RECENT_S else "offline"


def lane_value(queue, *, now: float | None = None) -> str:
    """lane() for a bridge already known to be alive: HOST_BUSY only ("offline" -> "unknown")."""
    v = lane(queue, now=now)
    return "unknown" if v == "offline" else v


def _overall(values) -> str:
    for v in ("exporting", "rendering", "unknown"):
        if v in values:
            return v
    return "idle"


def host_busy(home=None, *, now: float | None = None) -> dict:
    """{"premiere", "after_effects", "overall"} (see the module doc). Read only; never raises for a missing home."""
    if home is None:
        from lib.common import current_context
        home = current_context().engine_home
    home = Path(home)
    out = {name: lane(home / folder, now=now) for name, folder in LANES.items()}
    out["overall"] = _overall(out.values())
    return out
