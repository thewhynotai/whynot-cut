# WhyNot Cut 3.0 brand facts (digest for the design track)

Facts only, no interpretation. Each row carries its source. Written 2026-10-13. Paths are relative to the repo root.

Source keys:
- **TOK** `brand/tokens.css` (line numbers given)
- **LOGO** `brand/logo.svg`
- **MAG** `docs/review/2026-10-11/magnific-brand.md` (Part 2, the site read on 2026-10-11, raw HTML via curl)
- **B** `docs/superpowers/specs/addendum-b/ADDENDUM-B-ui-ux-website-look.md` (the copy in `Editing Plugin/WhyNot-Cut-3.0-Addendum/` was not needed)
- **E1** `docs/superpowers/specs/addendum-e/ADDENDUM-E-design-excellence-secure-installers.md` section E1
- **UXP** `docs/adobe/uxp-parity.md`
- **KIT** `adobe/panel-ui/styles/kit.css`, `adobe/panel-ui/src/kit/*.ts`

Live site check: https://thewhynot.ai could NOT be fetched in this task (WebFetch `ENOTFOUND`, curl DNS timeout, Browser pane denied). The "Website patterns" section is therefore taken from MAG, not re-observed today.

## 1. Surfaces and colour (HEX)

| Token | Value | Source / rule |
|---|---|---|
| `--twn-bg` | #000000 | TOK:30; B2 "background #000000"; MAG 2.2 site `html body` |
| `--twn-surface` | #121212 | TOK:31; B2 "cards #121212"; MAG 2.2 site card token. TOK:19: solid surface for non-glass panels only |
| `--twn-glass` | rgba(255,255,255,.08) | TOK:32; B2; MAG 2.2. TOK:17-18: a card is glass over the black bg (reads about #141414); glass is never stacked on #121212 |
| `--twn-border` | rgba(255,255,255,.14) | TOK:33; B2 |
| `--twn-surface-2` | #1E1E1E | TOK:34 (derived; `kit-code` bg per UXP 0.1.6 row) |
| `--twn-frame-bg` | #0D0D0D | TOK:35 |
| `--twn-track` | rgba(255,255,255,.12) | TOK:36 (progress track) |
| `--twn-text` | #FFFFFF | TOK:38 |
| `--twn-text-muted` | #B3B3B3 | TOK:39 (MAG 2.6: about the site's white at 80%) |
| `--twn-primary` | #5400FB | TOK:41. FILL only: white on it about 7.6:1 (TOK:6-8, B2). As text 2.77:1, forbidden |
| `--twn-primary-hover` | #6A1FFF | TOK:42 (MAG 2.6) |
| `--twn-primary-text` | #9D6BFF | TOK:43. Violet text, links, focus ring (B2, TOK:6-7) |
| `--twn-accent` | #D95C9B | TOK:44. Eyebrow labels and active tab underline only (TOK:8; B2) |
| `--twn-deep` | #390796 | TOK:45. Selected row / badges, white on it 12.8:1 (MAG 2.6) |
| `--twn-ok` / `--twn-warn` / `--twn-error` | #3DD68C / #FFB020 / #FF5C5C | TOK:48-50; B2. Always with an icon, never colour alone (TOK:15, B2) |
| `--twn-on-primary` | #FFFFFF | TOK:52 |
| `--twn-on-ok` / `--twn-on-accent` / `--twn-on-error` | #0B1F14 / #2A0A1A / #2A0808 | TOK:53-55 (text on a coloured fill) |
| `--twn-gradient` | `linear-gradient(90deg,#D95C9B,#5400FB)` | TOK:46. Use: header hairline and progress bars only (TOK:9). B2 also lists "main CTA border glow" |
| Site gradient (not a token) | `linear-gradient(270deg,#5300FB 0%,#D95C9B 100%)` and `(90deg,#D95C9B,#5400FB)` | MAG 2.2 |
| Hairline | 2 px tall, `--twn-gradient`, radius 1 px | KIT `.kit-hairline` |
| Focus ring | `0 0 0 2px #9D6BFF` | TOK:61; B4.8 |
| CTA glow / ring | glow `0 0 10px rgba(217,92,155,.6)`; ring `0 0 0 1px #D95C9B` | TOK:62-63 (both are box-shadows; see section 7) |
| Site-only values | #1C0E47, #3C19A5, #4422A9, #4800D8 (indigo stops); #7C0505 (logo detail); #0099FF (Framer default link, not brand) | MAG 2.2 |
| Site text / borders | body white at .8; nav pill border white at .5 (40 px radius, 5 px backdrop blur); other borders .3 / .25; glass gradient #ffffff03 to #ffffff1a | MAG 2.2 |
| Print (white pages, PDF guide) | headings #1C0E47; accent text #5400FB; secondary accent #B23A78; decorative #D95C9B (3.5:1, large only); tip bg #F1EAFF; warning bg #FCEAF3; body #1A1A1A; muted #5C5C66; paper #FFFFFF / #FAFAFC | MAG 2.6(b), marked [derived] there |
| Always dark | The panel stays dark, also on Premiere's Light theme | B2 |

Contrast (computed in MAG 2.2): #D95C9B on black 5.95:1; white on #D95C9B 3.53:1 (large text only); white on #390796 12.77:1; #5400FB on black 2.77:1. TOK:20-21: `adobe/panel-ui/test/contrast.test.ts` checks every text token on glass-over-black at 4.5:1 or more.

## 2. Logo

| Fact | Value | Source |
|---|---|---|
| File | `brand/logo.svg` (51 141 bytes), `brand/logo.png` (21 683 bytes) | LOGO |
| Canvas | `viewBox="0 0 109 32"`, width 109, height 32, 65 `<path>` elements | LOGO |
| Content | TWN monogram in a tilted outlined frame with a tail, fingerprint-heart "AI" icon inside viewfinder corners, then the wordmark "THE / WHY NOT" in heavy blocky capitals | MAG 2.1 |
| Colours in file | `fill="white"` x17; 47 linear gradients, stops #D95C9B to #390796; one #7C0505 path | LOGO (counted), MAG 2.1 |
| Variants | White-on-dark only. No dark or mono version, no Arabic logo | MAG 2.1 |
| Favicon / touch / OG | 64 px PNG on a gradient tile; 180 px touch icon; 1200x630 OG image (black, violet planet-arc glow, faint grid, wide caps headline, pink-to-violet gradient words) | MAG 2.1 |
| In the panel | TWN monogram + "WhyNot Cut" in the header; footer text "Powered by thewhynot.ai" | B2 |
| Header spec (derived) | 24 px favicon monogram, "WhyNot Cut" Syne 600 at 13-14 px, 2 px gradient hairline under it | MAG 2.6(a) |
| Header as built | wordmark Syne weight 700 (`--twn-weight-bold`), 15 px, letter-spacing .01em | KIT `.kit-wordmark` |

## 3. Type

| Role | Family stack (verbatim) | Weights | Source |
|---|---|---|---|
| Display / titles / uppercase eyebrows | `"Syne","Segoe UI","Helvetica Neue",Helvetica,Arial,sans-serif` | 600, 700 | TOK:66, B2 |
| UI text | `"Inter","Segoe UI","Helvetica Neue",Helvetica,Arial,sans-serif` | 300, 400, 600 | TOK:67, B2 |
| Arabic | `"IBM Plex Sans Arabic","Segoe UI",Tahoma,"Geeza Pro",sans-serif` | not stated | TOK:68, B2 |
| Mono (commands, timecodes) | `"IBM Plex Mono",Consolas,"SF Mono",Menlo,monospace` | not stated | TOK:69, B2 |
| Weight tokens | light 300, regular 400, semibold 600, bold 700 | | TOK:70-73 |

| Fact | Value | Source |
|---|---|---|
| Fonts licence / bundling | All OFL, "bundled in the panel (no network fonts)" | B2. TOK:24-27 and UXP 0.1.7: UXP loads none of them; installer installs them per user |
| Site: headings, nav, labels, buttons | Syne 500 (143 uses), 600 (244), 700 (505); sizes 14, 20, 24, 32, 40, 48, 64 px | MAG 2.3 |
| Site: body | Inter Light 300 (744 uses), accents 500, 600, 800 | MAG 2.3 |
| Site Arabic | No Arabic font loaded; falls back to system | MAG 2.3 |
| Panel sizes (derived) | section labels Syne 600, 10-11 px, uppercase, accent; UI 11-12 px Inter 400/600 | MAG 2.6(a) |
| Panel sizes (built) | root 12 px; badge 11 px; chip 10.5 px; wordmark 15 px; language switch 12 px, "ع" 14 px | KIT lines 42, 103, 120, 84, 148, 152 |
| PDF guide (derived) | Arabic headings Alexandria (alt. Cairo); Arabic body IBM Plex Sans Arabic 11-12 pt, line-height 1.7; Latin in Arabic: Inter; Syne 700 for English headings | MAG 2.6(b) |
| Arabic typography | line height and diacritics not clipped (no numbers given) | E1 E-D6 |

## 4. Spacing, radius, motion, sizes

| Fact | Value | Source |
|---|---|---|
| `--twn-radius` | 8px | TOK:57 |
| `--twn-radius-card` | 16px | TOK:58; B2 "radius 16 px for cards" |
| `--twn-radius-pill` | 999px; for `<span>` chips only | TOK:59, TOK:22-23 |
| `--twn-radius-control` | 16px (half of a 32 px control) | TOK:60 |
| Site nav pill | 40 px radius | MAG 2.2 |
| Hit target | 32 px minimum | B4.7; KIT `min-height: 32px` |
| Panel widths | works at 280-360 px docked, no sideways scroll | B4.7 |
| Mockup widths | 300 / 360 / 480 px, AR and EN | E1 E-D2 |
| Review widths | 280 / 340 / 480 px, Premiere Dark and Light | B5 B-T6 |
| Motion | 150-250 ms ease; progress shimmer; no layout shift; loading skeletons; hover and focus states | E1 E-D6 |
| Header padding / hairline margin | `padding: 8px 8px 0 8px`; hairline `margin: 8px 0 0 0` | KIT `.kit-hdr`, `.kit-hairline` |
| Gap helper | `.kit-gap-s` = physical `margin-left: 6px` (RTL: `margin-right: 6px`) | UXP 0.1.7 row W6 |
| Spacing scale, type scale, motion tokens | none defined as tokens | TOK (absent) |

## 5. Icons

| Fact | Value | Source |
|---|---|---|
| Icon set | "one set, Lucide, already licensed" | E1 E-D6 |
| Lucide licence | ISC; vendored at a pinned release for motion mode (`templates/motion/icons/lucide/`) | `docs/superpowers/specs/2026-10-11-motion-from-audio-design.md` 4.2; master plan line 115 |
| Kit icons as built | hand-drawn inline SVG, one 16x16 evenodd path each: `ok`, `warn`, `error`, `info`, `pending`, `chevron-start`, `chevron-end`, `chevron-down`, `close` | KIT `src/kit/icons.ts` (no Lucide reference in `adobe/panel-ui/`) |
| Status rule | status colour always paired with an icon | B2, B4, TOK:15 |
| Direction | directional icons resolved per language in the renderer, not by CSS transform | KIT `icons.ts` |
| Ink classes | `kit-ink-ok/-warn/-error/-info/-accent/-text/-muted/-on-primary/-on-ok/-on-error/-on-accent` | KIT `icons.ts` |

## 6. Voice and tone

| Fact | EN | AR | Source |
|---|---|---|---|
| Brand tone | short, calm, confident; "Clarity first." | none stated for the brand | B2 |
| Site tone | confident, direct, calm; short declarative sentences and fragments; anti-hype; senior and boutique; light wordplay in a "Why Not ...?" series | n/a (site is English only) | MAG 2.4 |
| Site slogan | "Clarity first. Consistency follows." | | MAG 2.4 |
| Site hero lines | "Monetize Your Presence"; "Personal Branding That Sounds Like You."; "Understand and Trust." | | MAG 2.4 |
| Site stance on AI | "using AI where it helps, and human judgment where it matters" (quote from the site's meta description as recorded in MAG) | | MAG 2.4 |
| Arabic register | | clear Egyptian-friendly Modern Standard Arabic; English UI term in parentheses the first time, e.g. «التسلسل (Sequence)» | B3 |
| Arabic digits / bidi | Western digits 0-9 for timecodes, versions, commands; commands, paths, timecodes, numbers in `<bdi dir="ltr">` | same | B3; MAG 2.6 |
| Error copy | cause in one line, fix button or exact step, "Copy diagnostics"; no raw codes on screen | | B4.4 |
| Status copy | plain language, e.g. "Building your sequence... 23/47 graphics" | | B4.3 |
| Micro-copy | "written as a product writer would", in both languages | | E1 E-D6 |
| Usability target | zero «مش فاهم» moments | | E1 gates |

## 7. UXP rendering constraints (measured live)

Host: Premiere Pro 26.5.2, UXP `uxp-9.3.0-local`, Windows 11 (UXP header). Evidence root `docs/adobe/evidence/ui-kit/`. "Computed" = `getComputedStyle` value; screenshots decide paint (UXP 0.1.7 intro).

| Technique | Paints? | Measured | Evidence |
|---|---|---|---|
| `<button>` with any background (flex / inline-block, radius 999 or 16, `appearance:none`) | NO | Premiere's native grey control, lens-shaped outline, computed colour correct but not painted | UXP "Spike 0.1.7 CSS lab" row 1; `uxp-lab-017/lab-01.png`..`lab-04.png`, `results-20261013-065447.json` |
| `<div role="button" tabindex="0">`, flex, radius 16 | YES | primary #5400FB, danger, glass all exact | lab row E, `uxp-lab-017/` |
| Disabled via `opacity` on that div | NO | computed `.45`, shown at full strength | lab row E |
| `sp-button` | YES, not on brand | Spectrum blue CTA / outline | lab row F |
| SVG `fill="currentColor"`, `fill="#hex"` attribute, `<img>` data URL, `<img>` bundled file | NO | nothing paints (chip, inline, row, block) | lab S1, S2, S5, S6 |
| SVG fill via CSS (`.x path {fill}` or `fill` on the svg) | YES | every context | lab S3, S4 |
| `box-shadow` (blur glow `0 0 10px`) | NO | no visible glow around Approve | `uxp-live-018/uxp-ar-280-02.png` etc. |
| `box-shadow` (1 px spread ring `0 0 0 1px`) | NO | invisible. The 0.1.6 "box-shadow ok" row proved the computed value only. Focus ring (`--twn-focus`) is a box-shadow and "almost certainly invisible too"; borders paint | UXP "Spike 0.1.9" bullet 3; `uxp-live-019/` |
| Gradient as fill (header hairline, progress fill) | YES | right across the kit | UXP "seen live in 0.1.8"; `uxp-live-019/uxp-*-*.png` |
| Gradient ring on a wrapper with radius (r999 + 1 px padding; r16; layer behind) | NO (square corners) | corners show square | lab rows GA, GB, GD |
| `border-image` gradient | NO | shows nothing | lab row GC |
| Radius 16 px on a `div` control | YES | clean | lab row E |
| Radius 999 px | YES on `<span>` chips only | not proven on a `div` | lab, "Radius on controls" |
| `@font-face` (relative, `plugin:/`, `./`, `.woff`, runtime `<style>`, FontFace API, bytes, data URI) | NO | every row equals the fallback; `FontFace` and `document.fonts` undefined | UXP "Spike 0.1.7" `@font-face` row; `uxp-lab-017/` |
| Product panel fonts | fallbacks | header crowded at floating width, system fonts | UXP "Product panel in real UXP"; `docs/adobe/evidence/2026-10-12-premiere-run3-panel-history.png` |
| Whitespace between two flex children | DROPPED | literal space, `&nbsp;` between or inside: all dropped (also in Chromium) | lab W1-W4 |
| Gap between flex children | use margins | `.kit-gap-s` physical margin | lab W6, W8 |
| `margin-inline-start`, `padding-inline-start` | NO effect | | lab W5, W7 |
| Physical margin / padding left / right, LTR and RTL | YES | | lab W6, W8 |
| Flex `gap`, grid, sticky, `:has()`, attribute selectors | not allowed by the kit | stated in KIT header comment ("UXP rules, from the live renders"); no row-by-row evidence in UXP | KIT lines 2-24 |
| CSS `var()` | YES | resolves in computed styles; box-shadow computed `#9D6BFF 0px 0px 0px 2px` | UXP "Spike 0.1.6" row "UI probes" |
| Arabic + a Latin word in one run | BREAKS shaping | wrap Latin in `<bdi dir="ltr">` | lab font rows |
| Arabic text and `direction` on the root | YES | `sp-theme dir` is broken in UXP | B3; UXP |
| Progress fill in RTL via `direction` only | NO (fills from left) | fixed with physical `direction: ltr; justify-content: flex-end; margin-left: auto`; fills from the right now | `uxp-live-018/uxp-ar-280-02.png`, `uxp-ar-340-02.png`; fixed, `uxp-live-019/` |
| Unknown elements | no browser default `display` | every kit element has explicit `display` | KIT line 5 |
| Header at floating width | crowded, title wraps, Host chip cut | | `docs/adobe/evidence/2026-10-12-premiere-run3-panel-history.png` |
| Full style guide (header, tabs, card, buttons, chips, steps, progress, toasts, checklist, dialog, empty, log, frames, waveform, footer) | paints | AR/EN x 280/340/480 | `uxp-live-019/` |
| Fonts on the real machine | Syne etc. not present | installer to install per user (request filed) | UXP 0.1.7 `@font-face` row |

## 8. Accessibility targets

| Target | Value | Source |
|---|---|---|
| Text contrast | at least 4.5:1; large text and icons 3:1 | B4.8 |
| Focus | visible ring #9D6BFF; tab order follows visual order, mirrored in RTL; labels on every control | B4.8 |
| Hit targets | at least 32 px | B4.7 |
| Status | never colour alone | B2, TOK:15 |
| Narrow | 280-360 px, no sideways scroll | B4.7, B6 |
| Keyboard | Enter and Space activate a `div role="button"`; disabled = `aria-disabled="true"` + `tabindex="-1"` | UXP 0.1.7 row 2; KIT `activate.ts` |
| Tests | token test, contrast test, i18n completeness, RTL snapshot, font-bundle test | B6 |
| Visual QA | AR and EN, 280 / 340 / 480 px, Dark and Light; no overlap, Arabic shaping correct | B6, B5 B-T6 |

## 9. UX rules (Addendum B4, verbatim intent)

| # | Rule | Source |
|---|---|---|
| 1 | Home = three big actions "Drop files / Make my edit / Approve", plus tool cards (Organise, Cut silences, Captions), each with one-line purpose and last result | B4.1 |
| 2 | One primary (violet) button per screen; secondary = glass; destructive actions show what changes and the backup name and ask confirm | B4.2 |
| 3 | Step strip Transcript > Plan > Approve > Build > Frames > QC > Handoff; progress bar with elapsed time and Cancel; plain status | B4.3 |
| 4 | Errors: one-line cause, fix button or exact step, "Copy diagnostics"; raw codes only in the log drawer | B4.4 |
| 5 | Empty states teach, one button; no blank panels | B4.5 |
| 6 | "Needs you" badge counts editor-only tasks; opens `NEEDS-YOU.md` in the panel | B4.6 |
| 7 | Narrow-panel first: 280-360 px, no sideways scroll, hit targets 32 px or more | B4.7 |
| 8 | Focus ring #9D6BFF, tab order = visual order (mirrored in RTL), labels, contrast 4.5:1 / 3:1 | B4.8 |
| 9 | Kalam, Hush, Tidy keep their steps (scan, preview, apply, undo) but use the same cards, buttons, chips, waveform / preview and progress strip; behaviour unchanged | B4.9, B6 |
| B3 | Language switch ع / EN in header, remembered per editor, first-run default from preference `language`; one string table `panel-ui/i18n/{ar,en}.json`; no hard-coded strings | B3 |

E1 design process facts: design first, then code; direction in `docs/design/direction.md` (mood, type scale, spacing, motion, iconography, voice, 2-3 options); mockups of every screen in `adobe/panel-ui/design/` at 300 / 360 / 480 px, AR and EN; at least 2 critique rounds (designer agent + "first-time editor" reviewer); screenshots of the real panel compared with mockups. Screens to mock: first-run checklist, home, client picker, pipeline progress, approvals, QC frames grid, Needs you, Kalam / Hush / Tidy tabs, models page, settings, Claude / engine status, every error card, After Effects motion panel, installer screens (E1 E-D2).

## 10. Component kit that exists (`adobe/panel-ui/src/kit/`, styles in `styles/kit.css`, `.kit-*` classes)

| File | Exports (component) | Notes from source |
|---|---|---|
| `button.ts` | `button`, `buttonRow`, `primaryCount` | variants primary / secondary / danger; block, glow class |
| `card.ts` | `card`, `section`, `eyebrow`, `paragraph` | tones neutral / ok / warn / error |
| `chip.ts` | `chip`, `chips` | tones neutral / ok / warn / error / info / accent |
| `checklist.ts` | `checklist`, `checklistItem` | states ok / warn / error / pending; rows engine, premiere, claude, clients |
| `dialog.ts` | `dialog` | change list, no-backup line |
| `empty.ts` | `emptyState` | |
| `frames.ts` | `frameGrid` | verdict pass / fail / pending tiles |
| `header.ts` | `header`, `langSwitch`, `needsYouBadge` | |
| `log.ts` | `logDrawer`, `buildStamp` | |
| `progress.ts` | `progress` | |
| `steps.ts` | `stepStrip` | states done / running / waiting / failed |
| `tabs.ts` | `tabs` | `role="tab"` |
| `toast.ts` | `toast`, `fixAction` | tones ok / warn / error / info; fixes start-engine, retry, copy-diagnostics |
| `waveform.ts` | `waveformFrame` | |
| `icons.ts` | `icon`, `statusIcon` | see section 5 |
| `root.ts` | `kitRoot`, `footer` | footer = "Powered by thewhynot.ai" string key `footer.powered` |
| `html.ts`, `activate.ts`, `gallery.ts`, `index.ts` | helpers: `esc`, `ltr`, `prose`, `auto`, `withCommands`, `cmdRow`, `control`; keyboard / pointer activation; `kitGallery` style guide | |

Style-guide renders: `docs/adobe/evidence/ui-kit/kit-{ar,en}-{280,340,480}.png`.

## 11. Website patterns (thewhynot.ai, from MAG Part 2; not re-fetched today)

| Pattern | Fact | Source |
|---|---|---|
| Platform | Framer site (`generator` meta "Framer 65a4904"), `lang="en"`, no `dir="rtl"`, English only | MAG 2 intro, 2.5 |
| Pages (sitemap) | `/`, `/about`, `/packages`, `/starter-package`, `/growth-package`, `/scale-package`, `/personal-brand-strategy`, `/media-production`, `/online-courses-management`, `/linkedin-ghostwriting`, `/content-system`, `/ai-training-workshops`, `/success-stories`, client case pages, `/contact`, `/privacy-policy`, `/terms-of-service`. No brand / press page | MAG 2 |
| Background | pure black; glass cards `rgba(255,255,255,.08)`; hero art on the OG image: violet planet-arc glow, faint grid | MAG 2.2, 2.1 |
| Nav | pill, 40 px radius, 5 px backdrop blur, white .5 border | MAG 2.2 |
| Headings | Syne 700 dominant, 32 / 40 / 48 / 64 px; highlighted words in #5400FB (fails contrast, 2.77:1) | MAG 2.3, 2.5 |
| Eyebrow labels | pink #D95C9B (about 113 uses): "The TWN Method", "Trusted By"; "Learn More" links pink | MAG 2.2 |
| Body | Inter Light 300, white at .8 | MAG 2.2, 2.3 |
| Buttons / highlights | pink-violet gradient; glass buttons | MAG 2.2 |
| Section lines seen | "The TWN Method"; "From guessing what to post to being known for what you do"; "Built for Real Work, Not Noise"; "About Clarity, Not Hype"; "Ready to Stop Guessing and Start Being Known?" | MAG 2.4 |
| "Why Not" series | "Why Not Begin? / Why Not Grow? / Why Not Stand Out? / Why Not Now?" | MAG 2.4 |
| About | "A Boutique, Strategy-Led Personal Branding Agency"; "No handoffs. No templates. Just experienced people doing focused work." | MAG 2.4 |
| Case studies | Arabic only as client show titles on case-study pages | MAG 2.5 |
| FAQ / footer | every FAQ answer ends with a leftover template credit link; footer slogan "Clarity first. Consistency follows." | MAG 2.5, 2.4 |
| Contact | Facebook, Instagram, LinkedIn, email, WhatsApp booking link; no YouTube, TikTok or X | MAG 2.5 |
| Imagery / icons | not described beyond logo and OG image; no icon set named for the site | MAG (absent) |
| Spacing, grid columns, breakpoints | not recorded | MAG (absent) |
