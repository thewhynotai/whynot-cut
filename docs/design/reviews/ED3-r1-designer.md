# E-D3 round 1 — designer QA (pattern round: P-01, P-03, P-07)

Reviewer: brand-systems-designer agent (AI review, not a human sign-off). Verdict: **PASS WITH FIXES** — shell,
tokens, state coverage and RTL mirroring are a good base; fix 1–6 in the shared pattern before fan-out.
Checked: all 9 sheets, 9 full renders, 20 contrast pairs (all text AA; disabled 3.41:1 exempt). Not checked: real UXP
paint, hover/pressed, motion, full P-03 stale/loading renders.

## Findings
1. MAJOR — header ع/EN selected segment uses the primary fill → two violet fills per screen. Fix `.m-seg-on` #383838 (11.73:1). Overrides direction §8 exemption — **decided: accepted** (controller, decide-and-continue).
2. MAJOR — `pills()` chars<=46 rule drops key words exactly when something fails. Keep keys from 360 px; non-ok pill always keeps its key at 300.
3. MAJOR — `.m-li`, `.m-logrow`, `.m-card-act` have no rest border → focus shifts layout; tool cards radius 16 on glass can't take a matching border. Fix: 2px fill-matching rest border; tool cards solid #141414, radius 8.
4. MAJOR — P-07 flagged lines cut at 34 chars, mid-claim. Never cut text the editor approves; collapse hides whole items.
5. MAJOR — P-07 Approve ~800 px down at 300/360. Pinned action bar (divider, 12px pad, "Approving as …", 40px Approve). UXP scroll behaviour unproven.
6. MAJOR — P-03 offline/error: hero "Ready for C0239", Kalam "Ready" chip, tool cards live. Neutral hero, no status chips, disabled chevrons, keep last results.
7. MINOR — start-aligned ghost buttons sit 14px in; `margin-left:-14px` (mirrored RTL).
8. MINOR — "Show less" uses chevron-down → chevron-up.
9. MINOR — P-03 360 primary verb row wraps to 68px; shorten subline.
10. MINOR — off-grid 10px (`.m-check`, `.m-flag`), 6px (`.m-tab-count`, `.m-badge-solo`).
11. MINOR — EN copy: one name per failure, name what failed; one contraction style; consistent pill value case.
12. MINOR — AR copy: «وافق» everywhere; no tatweel («لـ», «بـ»); NBSP in time phrases; English gloss first use only.
13. MINOR (draft) — Latin in Syne overpowers Arabic titles; 2px smaller or Inter 600.
14. MINOR — no focus/hover/pressed renders; no long-text tests; `.m-ctx` clips without ellipsis.

## UXP paint risks (not proven)
- MAJOR: traced icons depend on CSS `fill-rule:evenodd` — set the attribute per path and fix path direction in the build.
- @font-face is mockup-only; only Syne Bold bundled (600 renders as 700); no fallback-font render.
- @keyframes rotate spinner, shimmer background animation — need static fallbacks.
- `<bdi dir="ltr">` unproven — fallback U+2066/U+2069 in strings.
- text-transform, letter-spacing, tabular-nums unproven.
- Confirmed absent: box-shadow, opacity, gap, filter.
→ All of these go into the next UXP CSS lab run (spike css_lab) before E-D4.

## Pattern rules locked for fan-out
- Every role=button: 2px rest border = solid fill, radius 8.
- One violet fill per screen, header included; disabled primary → the notice's fix button takes the fill.
- Status pills keep key words from 360 px; non-ok pill always keeps its key.
- Truncate only by width in the renderer; never truncate approved text.
- A form-ending primary lives in the pinned action bar.
- Offline: everything engine-dependent disabled; nothing says "Ready".
- Paddings only {4, 8, 12, 16, 24}, border counted.
- One Arabic verb per action, no tatweel, NBSP inside time phrases.
- Each screen ships a focus render and a long-text state.
