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

## Status
- E-D1 direction: DONE — option B "Studio pro, branded" (docs/design/direction.md; 63 proposed tokens §15; 17 contradictions resolved §14; AI review, Arabic needs a native writer)
- E-D2 mockups: pattern round RENDERED — P-01 (6 states) / P-03 (7) / P-07 (11) x AR/EN x 300/360/480 = 144 PNGs, checks green (render_all.py, check_css.py; sheets in renders/_sheets/). Pattern QA (designer + first-time Arabic editor) running; fan-out to the other 32 screens after the fixes.
  Open from the worker: MOCK copy in strings.js needs the string-table owner + a native Arabic writer; icons traced from raster (production needs true stroke-to-path); only Syne Bold in repo; nothing checked in real UXP yet.
- E-D3 critique: round 1 DONE on the pattern (reviews/ED3-r1-designer.md PASS WITH FIXES; reviews/ED3-r1-first-time-editor.md 20 moments, 10 MAJOR). Pattern fix round running; round 2 after fan-out.
  UXP paint risks to prove in the next css_lab run before E-D4: icon fill-rule, @keyframes rotate/shimmer, <bdi> isolation, text-transform, letter-spacing, tabular-nums, pinned action bar scroll.
- Artifact (private, visibility only): TODO
- Installer mockups → installer track (E-T1): TODO

## Decisions
- Footer «Powered by thewhynot.ai» (owner). Widths 300/360/480 (Addendum E). Installer = one Tauri app (E2).
- Inputs ready: docs/design/brand-facts.md (website not reachable: from magnific-brand.md), docs/design/screen-inventory.md (35 screens: UXP 22, AE 4, installer 9 + 9 globals).
- B-T2 screen code PAUSED (executor, 2026-10-13) until mockups exist.

## Open
- Decided 2026-10-13: language segment selected = #383838 (one violet fill incl. header; overrides direction §8 exemption). UI never says «المحرّك»/engine: «برنامج WhyNot Cut» / WhyNot Cut app. Flagged lines gate Approve behind an «اتأكدت» checkbox. Timecodes not clickable in 3.0. Models lives under Settings.
- Needs the executor/engine: a plan-diff summary for the P-07 stale state (what changed between plan versions).
