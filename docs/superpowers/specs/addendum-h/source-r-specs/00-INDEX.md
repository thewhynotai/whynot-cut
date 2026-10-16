<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- © 2026 The Why Not AI (thewhynot.ai) -->

# Source-R behaviour specs (Addendum H, R-T1 / Phase 4 Task 17)

| | |
|---|---|
| Date | 2026-10-16 |
| Written by | the looks & motion track, read-only, from the Source-R evidence report (kept outside the repo) |
| Status | Draft for review by the executor and the plan session. No build task starts before that review |
| Binding parents | Addendum H (R1 clean rebuild, R2 evolve don't clone, R3 feature map), Addendum I (GPL-3.0-or-later, no telemetry), Phase 4 plan "Addendum H tasks", R schedule (2026-10-15) |

## Why these files exist

Implementers build Addendum H features **from these files only**. They never open, run, copy or paste Source-R
code, never read the evidence report, and never visit Source-R's pages online. Everything a builder needs is here:
what Source-R does (behaviour, inputs, outputs, steps, timings, UX) and what **our version** does instead.

## Rules every spec follows

1. **Naming.** The acquired tool is only ever "Source-R". None of its product name, author, handles, URLs, style
   names, Arabic labels, font aliases, scene IDs, file names or UI copy appear here. Source-R's looks are numbered
   S1–S12 and its scenes are described in words. Our looks use working codes **LOOK-01..LOOK-12** until the
   brand-systems-designer proposes names and Yunus approves them. Our scenes use our own snake_case names.
2. **Behaviour, not code.** A spec says what happens and with which numbers. It never describes Source-R's source
   structure, function names or data layouts beyond what the behaviour needs.
3. **Evolve, don't clone (R2).** Every look and scene has an **"Our version"** block with the seven R2 points:
   name, motion, brand-aware, Arabic first, easier, better quality, distinctiveness check. Our motion timings, easing
   curves, layout grid and type system differ from Source-R's by design.
4. **No Source-R tuning numbers.** Source-R's thresholds, copy limits, frame counts and tracking parameters are
   described in words only (the repo becomes public). Every number in "Our version" is **ours**: a starting value
   chosen by us and then measured on our own fixtures, recorded with its basis (`starting` → `measured: <fixture,
   date>`) in the config that holds it.
5. **Platform facts** (safe zones, encode limits) come from the platforms' own official pages, fetched by us with a
   source and a date (`basis: official`). Where a platform publishes no number, we measure the platform's own
   downloadable template (`basis: template`); only if there is none, a current in-app screenshot that Yunus takes on
   his phone (`basis: screenshot`, a Yunus step, kept as evidence); `community` numbers are a last resort and
   flagged.
6. **Our stack only.** Native After Effects (motion-plan → ae-builder → `wnc_motion_lib.jsx`), Premiere (UXP panel,
   CEP compat ops, MOGRTs, `wnc_ppro_lib.jsx`), the `reel` Python engine with FFmpeg (GPU first: NVENC/NVDEC,
   VideoToolbox, CUDA/MLX; CPU fallback; each job on the processor a measurement shows faster and correct, as
   COORDINATION rule 16 says), and our panel. **Never** Remotion, React (for this feature), headless Chrome
   or a browser player.
7. **G10 wins.** Nothing here may cause an error, a slowdown or a blocked action for a real user. Every check that can
   fail for reasons outside the user's control is advisory with a plain-words line, never a crash.
8. **No telemetry** (D17, restored by Addendum I). Source-R's usage pings and its update-by-pull are never adopted.
9. **Mac parity (G11).** Every engine behaviour has a darwin path (CoreText, Vision, VideoToolbox, MLX) with
   fake-backed tests that run on Windows and on the Mac CI runner.
10. **Truth rules.** Nothing on screen is invented: numbers, quotes, offers, comments, maps and claims come from the
    transcript, the client database or the editor, and medical/religious statements pass medical-reviewer and
    claim-checker before they are drawn ("never show unreviewed").

## Map: every R3 row → one spec

| R3 row | Spec file | 3.0 owner (build) |
|---|---|---|
| R-4.1 Caption looks | [R-4.1-caption-looks.md](R-4.1-caption-looks.md) | looks track (Task 23, absorbs Task 16) |
| R-4.2 Burned-in captions | [R-4.2-burned-in-captions.md](R-4.2-burned-in-captions.md) | executor (Task 24) |
| R-4.3 Cut proposals v2 | [R-4.3-cut-proposals.md](R-4.3-cut-proposals.md) | looks track engine part (Task 25); Hush wiring: tools track, 6B |
| R-4.4 Intake normalisation | [R-4.4-intake-normalisation.md](R-4.4-intake-normalisation.md) | executor (Task 26) |
| R-4.5 Safe-zone profiles | [R-4.5-safe-zone-profiles.md](R-4.5-safe-zone-profiles.md) | looks track (Task 27) |
| R-4.6 Look recommender | [R-4.6-look-recommender.md](R-4.6-look-recommender.md) | looks track (Task 28) |
| R-4.7 Punch-in emphasis + endings | [R-4.7-punch-in-emphasis-and-endings.md](R-4.7-punch-in-emphasis-and-endings.md) | executor (Task 29) |
| R-4.8 Publish-check rules | [R-4.8-publish-check-rules.md](R-4.8-publish-check-rules.md) | executor (Task 30) |
| R-6.1 Look system (+ every look's "Our version") | [R-6.1-look-system.md](R-6.1-look-system.md) | executor engine side + looks track (look data, AE lib) + Adobe (picker) |
| R-6.2 AE scenes wave 1 (+ every scene's "Our version") | [R-6.2-ae-scenes-wave-1.md](R-6.2-ae-scenes-wave-1.md) | looks track (AE lib, look data) + executor (motion-plan scene types) |
| R-6.4 Head keep-out gate | [R-6.4-head-keep-out.md](R-6.4-head-keep-out.md) | executor (qc) + Adobe (read-back ops); safe-zone/face data from the looks track |
| R-6.5 Panel Review tab | [R-6.5-panel-review-tab.md](R-6.5-panel-review-tab.md) | Adobe |
| R-6.6 Panel Settings/onboarding tab | [R-6.6-panel-settings-tab.md](R-6.6-panel-settings-tab.md) | Adobe (+ engine `reel profile`) |
| R-6.7 SFX cue palettes per look | [R-6.7-sfx-cue-palettes.md](R-6.7-sfx-cue-palettes.md) | executor (sfx) + looks track (palette data) + Adobe (markers) |
| R-6B.1 Alignment contract + licence-clean aligner | [R-6B.1-alignment-contract.md](R-6B.1-alignment-contract.md) | tools track (Task 18b) / executor |
| R-7.1 Installer steps + proof render | [R-7.1-installer-steps-and-proof-render.md](R-7.1-installer-steps-and-proof-render.md) | installer track + executor (doctor) |
| R-9.1–9.4 Identity scan, RTL lint, still matrix, distinctiveness | [R-9-qa-identity-rtl-matrix-distinctiveness.md](R-9-qa-identity-rtl-matrix-distinctiveness.md) | looks track (scan tool, Task 19) + executor (gates) |
| 3.1 items (not built in 3.0) | [R-3.1-backlog.md](R-3.1-backlog.md) | later |

## Shared vocabulary (ours)

- **Look**: a small token set that styles every graphic of a reel: palette roles, type system, card, annotation,
  composition, caption look, one motion law, one SFX palette (R-6.1).
- **Motion law**: one named easing-and-timing preset that every element of a look obeys (R-6.1).
- **Caption look**: grouping × presentation (+ emphasis) for the spoken-word captions (R-4.1).
- **Scene**: one animated graphic beat in an AE motion video or a Premiere overlay (R-6.2). Scene text obeys the
  truth rules of `skills/motion-craft/references/motion-scenes.md`.
- **Safe-zone profile**: the platform UI areas a reel must keep clear, as data with a source per number (R-4.5).
- **Head envelope**: the measured head box of the presenter over a scene's time span, plus a margin (R-6.4).
- **Direction rule** (one rule for every look, scene and caption):
  (a) **progress** (order, drawing, filling, word-by-word or item-by-item appearance, wipes, sweeps, timelines) runs
  from the reading start to the reading end: right → left in Arabic, left → right in English;
  (b) **arrival** (a new scene or panel replacing the current one, or an element that slides in) comes in from the
  reading end and moves toward the reading start, like a page turn (from the left in Arabic, from the right in
  English); what it replaces leaves toward the reading start;
  (c) **exceptions**: digits are written left → right in both languages (digit rolls go by place value, units first);
  vertical, scale and depth moves have no reading direction; symmetric moves (two columns from opposite edges),
  face-driven docking (from the frame edge nearest the chosen slot) and speaker-anchored elements (from the speaker's
  seat side) follow the layout. A direction test checks every scene builder's resolved directions in AR and EN
  against this rule (it extends `skills/motion-craft/references/motion-beats.md` § "Direction (RTL vs LTR)").
- **Fit-or-fail**: text is measured with the real font (HarfBuzz on Windows, CoreText on Mac) before the build; it is
  re-grouped, then shrunk within a floor, then reported. It never overflows or clips silently.
- **Proposal**: something the engine suggests (a cut, a look, a punch-in, a fix). Proposals change nothing until the
  editor approves the plan.

## Acceptance of this task (Task 17)

- Every R3 row above maps to exactly one spec file.
- Every look (S1–S12 → LOOK-01..12) and every wave-1 scene has an "Our version" block with the seven R2 points.
- The identity scan (Task 19) passes on every file in this folder before it is committed.
- The executor and the plan session confirm the specs.

## Distinctiveness gate: image-based (Addendum H R2.7; plan-session ruling, 2026-10-16)
The R2 distinctiveness gate (R-4.1, R-6.1, R-6.2, R-9.4) compares our stills with **Source-R's own preview images**,
staged by the plan session in `WhyNot-Cut-3.0-Addendum/evidence/source-r-frames/` (outside the repo; copied from the local read-only copy, nothing run, nothing
fetched): `S01`–`S12` = the preview of each look S1–S12, plus before/after and scene stills. Only the
brand-systems-designer opens them, at the gate. They are **never** copied into the repo, a fixture, a test, a doc or
any page, and builders never fetch anything online.
