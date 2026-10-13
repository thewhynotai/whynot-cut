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
- E-D2 mockups: pattern round building P-01 / P-03 / P-07 (adobe/panel-ui/design/)
- E-D3 critique (designer + first-time Arabic editor), ≥2 rounds: TODO
- Artifact (private, visibility only): TODO
- Installer mockups → installer track (E-T1): TODO

## Decisions
- Footer «Powered by thewhynot.ai» (owner). Widths 300/360/480 (Addendum E). Installer = one Tauri app (E2).
- Inputs ready: docs/design/brand-facts.md (website not reachable: from magnific-brand.md), docs/design/screen-inventory.md (35 screens: UXP 22, AE 4, installer 9 + 9 globals).
- B-T2 screen code PAUSED (executor, 2026-10-13) until mockups exist.

## Open
