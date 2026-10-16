# STATE — WhyNot Cut 3.0 design track (Addendum E: E-D1 … E-D6)

Owner of the track: Adobe-track session. Spec: docs/superpowers/specs/addendum-e/ADDENDUM-E-design-excellence-secure-installers.md
(E1), Addendum B (website look), brand/ (tokens.css = single token source, logo.svg). Standing rule: decide and continue.

## Sources of truth
- Tokens: brand/tokens.css (read-only for this track except additive tokens through a kit commit)
- Kit (live-proven in UXP): adobe/panel-ui/src/kit/*, styles/kit.css; evidence docs/adobe/evidence/ui-kit/uxp-live-019/
- UXP limits (measured): docs/adobe/uxp-parity.md — flexbox only; no <button> (div role=button); svg colour only via
  CSS fill; box-shadow does NOT paint; @font-face does NOT load (system font stacks; installer installs brand fonts);
  physical margins for gaps; radius ok; gradients ok; Arabic text ok.

## Folders
- docs/design/: direction.md, brand-facts.md, screen-inventory.md, reviews/
- adobe/panel-ui/design/: mockups (HTML/CSS) + renders/ (PNG 300/360/480 × AR/EN) + manifest.csv

## Status (2026-10-16)
- E-D1 direction: DONE (docs/design/direction.md).
- E-D2 mockups: DONE. 35 screens (P-01..P-22, A-01..A-04, I-01..I-09) in 3 groups, plus the shared layer
  (mockup.js / mockup.css / strings.js / tokens):
  - after round 3, 2368 renders at 280/300/360/480 (installer at its own widths) × EN/AR, 0 failed;
  - the strict self-check runs on every render: the header never says "All set" over a problem;
  - render_280 covers every A-* state: 102/102;
  - check_css: 0 hits.
- E-D3 critique: rounds 1-3 DONE (docs/design/reviews/):
  - R2: owner decisions D-01..D-05 (R2-owner-decisions.md; D-05 update: support is WhatsApp) and the AR register pass.
  - R3 verdicts: designer NOT YET (2 P0, both fixed), first-time editor YES, agency owner PAY AFTER PILOT (2 P0, fixed:
    training claim, support channel).
  - R3-fix-list.md: 66 ids. Shared items in dae5a89; the group fixes, an opus diff review and an opus visual check are
    in the R3 group commit.
  - §5 lists 8 engine-data items (E-1..E-8), recorded by the executor in EXECUTOR-BRIEF §6. E-2 (re-approving leaves
    the built sequence untouched) is NOT promised in the copy until the executor confirms it.
- Not verified yet: nothing has run in real UXP (css_lab risks below). The `?support=off` alternate has no render.
  UXP paint risks to prove in a css_lab run before E-D4: icon fill-rule, @keyframes rotate/shimmer, <bdi> isolation,
  text-transform, letter-spacing, tabular-nums, pinned action bar scroll.
- Artifact (private, for Yunus's review): next.
- Installer mockups → installer track (E-T1): next.

## Decisions
- Footer «Powered by thewhynot.ai» (owner). Widths 300/360/480 (Addendum E). Installer = one Tauri app (E2).
- Inputs ready: docs/design/brand-facts.md (website not reachable: from magnific-brand.md), docs/design/screen-inventory.md (35 screens: UXP 22, AE 4, installer 9 + 9 globals).
- B-T2 screen code PAUSED (executor, 2026-10-13) until mockups exist.

## Open
- Decided 2026-10-13: language segment selected = #383838 (one violet fill incl. header; overrides direction §8 exemption). UI never says «المحرّك»/engine: «برنامج WhyNot Cut» / WhyNot Cut app. Flagged lines gate Approve behind an «اتأكدت» checkbox. Timecodes not clickable in 3.0. Models lives under Settings.
- Needs the executor/engine: a plan-diff summary for the P-07 stale state (what changed between plan versions); R3-fix-list §5 E-1..E-8.
