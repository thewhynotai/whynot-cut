"""Push on change (3.0 Addendum G2 hardening H3; H6 builds the idle budget on it): `reel serve` keeps every connected
panel's state current instead of the panel finding out on its next snapshot poll.

StatePusher looks every `interval` seconds through `probe()` -> (fingerprint, payload, stale) and keeps each panel up to
date, not a single server-wide "last": `behind(fp)` says whether any panel's last state differs from fp, and
`publish(fp, payload, stale)` sends it to every such panel and returns how many got it. So a panel that fell behind (a
failed send, a stale first snapshot that outlived its read, a snapshot answer that went out after a newer push) is
caught up on the next look even though nothing changed. The fingerprint is cheap: the App builds it from the PanelFields
cache generation (engine_state.PanelFields.generation: it moves only when the fields served change, and an unchanged
item is a cache hit that re-reads nothing), whether the read was stale, the host connection and the job journal's
in-memory summaries; a stuck item read still has a fingerprint, so host and job changes go through (marked stale).
A CHANGED fingerprint is debounced: the pusher looks again every `debounce` seconds until two looks agree or
`debounce_max` has passed, then publishes the last state once, so a burst of engine writes is one push. A stale look
during that wait never takes a fresh change back: the fresh one is sent at once. A panel that is merely behind (no
change) is sent the state without waiting. A probe that fails is logged once and the loop goes on: the panel's poll is
the fallback. The clock and the sleep are injected (tests drive it on a fake clock, with no wall-clock wait).
"""
from __future__ import annotations

import asyncio
import logging
import time

__all__ = ["StatePusher", "PUSH_INTERVAL_S", "DEBOUNCE_S", "DEBOUNCE_MAX_S"]

log = logging.getLogger(__name__)

PUSH_INTERVAL_S = 1.0     # how often the engine state is looked at while a panel is connected
DEBOUNCE_S = 0.25         # a change is looked at again after this, until it holds still
DEBOUNCE_MAX_S = 1.0      # ... but never longer: a state that keeps changing is pushed after this

_UNSET = object()


class StatePusher:
    def __init__(self, probe, publish, behind, *, interval: float = PUSH_INTERVAL_S, debounce: float = DEBOUNCE_S,
                 debounce_max: float = DEBOUNCE_MAX_S, sleep=asyncio.sleep, clock=time.monotonic):
        self.probe = probe                  # async () -> (fingerprint, payload, stale)
        self.publish = publish              # async (fingerprint, payload, stale) -> how many panels got it
        self.behind = behind                # (fingerprint) -> does any panel lack it
        self.interval = interval
        self.debounce = debounce
        self.debounce_max = debounce_max
        self.sleep = sleep
        self.clock = clock
        self.last = _UNSET                  # the last fingerprint looked at (only to tell a change from a lag)
        self._failed = False

    def _fail(self, what: str, e: BaseException) -> None:
        if not self._failed:
            self._failed = True
            log.warning("reel serve: the state push %s failed (%s); the panel's poll still works", what,
                        type(e).__name__)

    async def _look(self):
        try:
            return await self.probe()
        except asyncio.CancelledError:
            raise
        except Exception as e:                       # noqa: BLE001
            self._fail("look", e)
            return None

    async def tick(self) -> bool:
        """One look: True when a state reached at least one panel."""
        look = await self._look()
        if look is None:
            return False
        fp, payload, stale = look
        changed = fp != self.last
        self.last = fp
        if not self.behind(fp):
            return False
        if changed:
            start = self.clock()
            while self.debounce > 0 and self.clock() - start + self.debounce <= self.debounce_max:
                await self.sleep(self.debounce)
                again = await self._look()
                if again is None or (again[2] and not stale):
                    break                            # no look, or a stale one: never take the fresh change back
                if again[0] == fp:
                    break
                fp, payload, stale = again
            self.last = fp
        try:
            sent = await self.publish(fp, payload, stale)
        except asyncio.CancelledError:
            raise
        except Exception as e:                       # noqa: BLE001
            self._fail("send", e)
            return False
        if sent:
            self._failed = False
        return bool(sent)

    async def run(self, active) -> None:
        """Look every `interval` while active() is true."""
        while active():
            await self.tick()
            if not active():
                break
            await self.sleep(self.interval)
