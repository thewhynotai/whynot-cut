# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""The K1 switches (config/defaults/safety.json `switches`, with the client's reel-profile/safety.json on top).

A switch is on only when its value is exactly JSON `true`: a missing file, a damaged file, a missing key, "true", 1 or
null all mean off, so today's behaviour never changes by accident. Settings read here never raise (G10)."""
from ..common import load_config

PLAN_BLOCK = "k_t1_plan_block"           # K-T1: risk-first words block a graphic in `reel plan` (+ review/needs-you order)
QC_SAFEZONE_HARD_FAIL = "k_t4_qc_safezone_hard_fail"   # K-T4: `reel qc` fails on a safe-zone intrusion
HOOK_CHECK_IN_PLAN = "k_t6_hook_check_in_plan"         # K-T6: the hook rules run inside `plan` / `reels-plan`
BUILDER_FADES = "k_t3_builder_fades"                   # K-T3: short audio fades at every cut in the builder
# K-T5: the Arabic integrity line in `reel motion-qc` (Gate 4 is unchanged by K: K5; the standalone check always runs)
ARABIC_QC_IN_MOTION_QC = "k_t5_arabic_qc_in_motion_qc"
# Task 25: cut proposals inside the plan (an accepted take cut whole, the "Proposed cuts" table in edit-plan.md, the
# Premiere markers); `reel cut-proposals` itself always runs
TASK25_PLAN_PROPOSALS = "task25_plan_proposals"
ALL = (PLAN_BLOCK, QC_SAFEZONE_HARD_FAIL, HOOK_CHECK_IN_PLAN, BUILDER_FADES, ARABIC_QC_IN_MOTION_QC, TASK25_PLAN_PROPOSALS)


def config(ctx=None) -> dict:
    try:
        cfg = load_config("safety.json", ctx)
    except Exception:  # noqa: BLE001  (an unreadable profile never changes behaviour)
        return {}
    return cfg if isinstance(cfg, dict) else {}


def layers(name: str, ctx=None) -> list:
    """Each layer of a config file on its own, lowest first: config/defaults, the shipped profile, the client's
    reel-profile. A missing or damaged layer is skipped."""
    from ..common import CONFIG_DIR, current_context, read_json
    out = []
    try:
        dirs = [CONFIG_DIR] + list((ctx or current_context()).profile_dirs())
    except Exception:  # noqa: BLE001
        dirs = [CONFIG_DIR]
    for d in dirs:
        try:
            doc = read_json(d / name)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(doc, dict):
            out.append(doc)
    return out


def enabled(name: str, ctx=None) -> bool:
    sw = config(ctx).get("switches")
    return isinstance(sw, dict) and sw.get(name) is True


def section(name: str, ctx=None) -> dict:
    s = config(ctx).get(name)
    return s if isinstance(s, dict) else {}
