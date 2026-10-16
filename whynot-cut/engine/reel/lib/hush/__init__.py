# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Hush engine twins: the pure silence / filler logic of adobe/tools/hush/src/js in Python (numpy only).

`reel hush` (chat) must give what the panel's JavaScript gives, so these modules mirror the JS functions one to one
(wav, detect, fillers, settings; snake_case names, same dict keys) and tests/test_hush_twins.py runs both on the same
inputs. The JavaScript is the reference.
"""
