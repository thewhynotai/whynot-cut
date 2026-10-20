<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- © 2026 The Why Not AI (thewhynot.ai) -->

# K1 switches: the switches-on dry run before the Gate 4 tag (executor)

PROGRESS gate item: "one switches-on dry run before the tag (suite subsets + one live plan). Flip only the switches
of accepted tasks; K-T3's cut fades must compose with T4.1's multiplicative fades." The switches live in
`config/defaults/safety.json` `switches` (all `false` today); `lib/safety/switches.py` reads a switch as on only when
it is exactly JSON `true`, with the client's `reel-profile/safety.json` on top.

## Which switches turn on at the tag
| Switch | Task | State | At the tag |
|---|---|---|---|
| `k_t1_plan_block` | K-T1 risky words first | accepted 2026-10-17 | **on** |
| `k_t5_arabic_qc_in_motion_qc` | K-T5 Arabic integrity in motion QC | accepted 2026-10-17 | **on** |
| `task25_plan_proposals` | Task 25 cut proposals in the plan | closed 2026-10-20 (813e560); its plan/cli/guard hooks are being ported | **on** once the port lands; else stays off |
| `k_t4_qc_safezone_hard_fail` | K-T4 safe zones | accepted 2026-10-17; `safezone-check` hooks not applied yet | **on** once the K-T4 hooks land; else stays off |
| `k_t3_builder_fades` | K-T3 cut fades | NOT BUILT (name reserved) | off |
| `k_t6_hook_check_in_plan` | K-T6 hook check | NOT BUILT | off |

K-T3 is not built, so the "compose with T4.1's fades" condition does not arise at this tag. It is recorded for when
K-T3 lands.

## Method
1. **Suite subsets with the switches on.** A full `git archive` snapshot of the tag candidate, with
   `config/defaults/safety.json` flipped (only the "on" rows above), never the repo. Then `bash tools/test.sh -p` on:
   - test_safety_*, test_plan*, test_t47_needs_you, test_review_*;
   - test_cut_proposals*, test_takes*, test_qc*, test_safezone*, test_motion*, test_manual_verse*;
   - the golden plan tests.

   Every failure is read: either a test that pins switch-off behaviour (expected, listed by name) or a real defect
   (fixed before the tag).
2. **One live plan** on a copy of the whynot-test client (R02, Dr Sherin Helmy) in the scratch area, never
   `D:\WhyNot Clients`, with the same switches on through the copy's `reel-profile/safety.json`. Run `reel plan`, then
   `reel needs-you --write`, and compare edit-plan.md and NEEDS-YOU.md against the switches-off run. Record each
   difference and whether it is the intended effect: blocked graphics, a reordered review, the proposed cuts table.
3. **The flip itself** is one commit after the tag: `config/defaults/safety.json` to the "on" rows, with the dry-run
   results below as its evidence.

## Results
Not run yet: it runs on the tag candidate, after the last code commit (switch hooks included).
