"""Push on change (3.0 Addendum G2 hardening H3; H6 builds the idle budget on it): `reel serve` sends the connected
panels a `state` when the engine state changes, instead of the panel finding out on its next snapshot poll.

StatePusher looks every `interval` seconds through `probe()` -> (fingerprint, payload). The fingerprint is cheap: the
App builds it from the PanelFields cache generation (engine_state.PanelFields.generation: it moves only when the fields
served change, and an unchanged item is a cache hit that re-reads nothing), the host connection and the job journal's
in-memory summaries. The first look is the baseline (nothing is pushed). A changed fingerprint is debounced: the pusher
looks again every `debounce` seconds until two looks agree or `debounce_max` has passed, then publishes the last
state once, so a burst of engine writes (a build writing a dozen evidence files) is one push.
A probe or publish that fails is logged once and the loop goes on: the panel's poll is the fallback.
The clock and the sleep are injected (tests drive it on a fake clock, with no wall-clock wait).
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
    def __init__(self, probe, publish, *, interval: float = PUSH_INTERVAL_S, debounce: float = DEBOUNCE_S,
                 debounce_max: float = DEBOUNCE_MAX_S, sleep=asyncio.sleep, clock=time.monotonic):
        self.probe = probe                  # async () -> (fingerprint, payload)
        self.publish = publish              # async (fingerprint, payload) -> None
        self.interval = interval
        self.debounce = debounce
        self.debounce_max = debounce_max
        self.sleep = sleep
        self.clock = clock
        self.last = _UNSET
        self._failed = False

    def _fail(self, what: str, e: BaseException) -> None:
        if not self._failed:
            self._failed = True
            log.warning("reel serve: the state push %s failed (%s); the panel's poll still works", what,
                        type(e).__name__)

    async def tick(self) -> bool:
        """One look: True when a changed state was published."""
        try:
            fp, payload = await self.probe()
        except asyncio.CancelledError:
            raise
        except Exception as e:                       # noqa: BLE001
            self._fail("look", e)
            return False
        if self.last is _UNSET:
            self.last = fp
            return False
        if fp == self.last:
            return False
        start = self.clock()
        while self.debounce > 0 and self.clock() - start + self.debounce <= self.debounce_max:
            await self.sleep(self.debounce)
            try:
                again, newer = await self.probe()
            except asyncio.CancelledError:
                raise
            except Exception as e:                   # noqa: BLE001
                self._fail("look", e)
                break
            if again == fp:
                break
            fp, payload = again, newer
        self.last = fp
        try:
            await self.publish(fp, payload)
        except asyncio.CancelledError:
            raise
        except Exception as e:                       # noqa: BLE001
            self._fail("send", e)
            return False
        self._failed = False
        return True

    async def run(self, active) -> None:
        """Look every `interval` while active() is true."""
        while active():
            await self.tick()
            if not active():
                break
            await self.sleep(self.interval)
