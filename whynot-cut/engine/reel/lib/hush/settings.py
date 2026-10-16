# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Hush: which detection settings are in force (Python twin of adobe/tools/hush/src/js/settings.js).

cfg = {tab, intensity, tight, adv} and the clip stats {floor, speech}; same rules as the panel: the Simple tab maps the
intensity to settings and Tight (default on) sets both pads to 0; anything else is the Advanced settings as they are.
"""
from __future__ import annotations

from ._js import js_num_str
from .detect import from_intensity
from .wav import js_round

__all__ = ["current", "adv_from_simple", "readout"]


def current(cfg, stats):
    if cfg.get("tab") == "simple" and stats is not None:  # a JS object is truthy even when empty
        st = from_intensity(cfg.get("intensity"), stats)
        if cfg.get("tight"):
            st["padBefore"] = 0
            st["padAfter"] = 0
        return st
    return cfg.get("adv")


def adv_from_simple(cfg, stats):
    """The Advanced fields as Simple would set them (same Tight rule); None when there are no stats."""
    if stats is None:
        return None
    s = from_intensity(cfg.get("intensity"), stats)
    if cfg.get("tight"):
        s["padBefore"] = 0
        s["padAfter"] = 0
    return {"threshold": s["threshold"], "minSilence": s["minSilence"], "padBefore": s["padBefore"],
            "padAfter": s["padAfter"]}


def readout(st):
    """The one-line summary under the Simple controls (two spaces around the bars)."""
    return (js_num_str(st["threshold"]) + " dB  |  " + str(js_round(st["minSilence"] * 1000)) + " ms min  |  "
            + str(js_round(st["padBefore"] * 1000)) + "/" + str(js_round(st["padAfter"] * 1000)) + " ms pad")
