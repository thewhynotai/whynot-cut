# WhyNot Cut 3.0: design direction (E-D1)

Author: brand-systems-designer agent (an AI reviewer, not a human designer's sign-off). Date 2026-10-13.
Inputs: `brand-facts.md`, `screen-inventory.md`, `brand/tokens.css`, `brand/logo.svg`, `uxp-live-019/uxp-{en,ar}-340-*.png`.
Status words: **verified** = measured or viewed; **draft** = needs a lab check or the owner; **not checked**.

## 0. Starting point (viewed: uxp-live-019, 340 px, EN and AR)
- Everything is an outlined oval: buttons, chips, toasts, the language switch. Shape says nothing about role.
- Toasts have full-strength 1 px status borders: a stack of red, amber, green and violet outlines on one screen.
- The step strip wraps to 2 lines at 340 px. Card titles and body text share one weight and size, so the hierarchy is flat.
- In the AR checklist, the icon touches its word (the physical margin is missing in RTL).
- In AR, the progress gradient keeps pink at the moving tip. It should mirror.

## 1. Options
**A. Editorial calm.** Big Syne titles, hairline dividers instead of cards, a lot of black, almost no fills.
Beautiful on a website, but too sparse at 300 px. It also leans on Syne, which falls back to Segoe UI when the
installer has not run, and with no cards it cannot show status or grouping in a dense panel.

**B. Studio pro, branded (CHOSEN).** Linear, Frame.io and Adobe AI Assistant density: solid glass cards,
rounded-rectangle controls, one violet fill per screen, quiet status tints. The brand appears in 4 signatures: the
TWN monogram and Syne wordmark, the pink→violet hairline, the pink eyebrows and active tab, and the violet primary.

**C. Brand-forward.** The website look: pill buttons, gradient CTA borders and glows, the planet-arc art. UXP paints
neither glows nor gradient rings (measured), so it would look broken in Premiere and different in AE and the
installer. Rejected.

**Why B:**
1. Every effect it uses is proven to paint in UXP: flat fills, borders, radius ≤16, gradient fills.
2. It holds at 300 px. Hierarchy comes from size, weight and fill, not from decoration.
3. It sits calmly beside Premiere's own panels, as "Clarity first" asks. The brand is the four signatures, not noise.

## 2. Mood
**Calm · precise · confident.** A quiet black studio desk where the one thing to do next is lit in violet. Nothing
blinks or glows. Status speaks in one small icon and one plain word. The panel looks like it was made by the people
behind thewhynot.ai: senior, anti-hype, sure of itself.

## 3. Layout system
- **Grid:** a 4 px base. Every size, margin and line height is a multiple of 4.
- **Gaps:** margins only (UXP has no flex gap). The same markup runs in CEP and the installer.
- **Gutter:** 12 px at 300 px, 16 px at 360 and 480 px. Card padding is 12 px at 300 px and 16 px from 360 px.
- **Rhythm:** 8 px inside a group, 16 px between cards, 24 px between sections.
- **Heights:**
  - control 32 (the hit-target minimum);
  - block primary 40;
  - verb row 56;
  - list row 40;
  - tab bar 36;
  - chip 24;
  - footer 32.
- **Anatomy, top to bottom:**
  1. **Header row 1 (40 px):** monogram (20 px) with an 8 px margin, wordmark, then a spacer, the Needs-you badge
     and the ع|EN segmented switch (32 px).
  2. **Header row 2 (20 px):** client · item in meta size (client muted, item white). The 3 status pills (engine,
     Claude, host) sit at the row end at 480 px, or on their own row 3 at 300 and 360 px. At 300 px they show the
     icon and value only; from 360 px they also show the key word.
  3. **Hairline:** 2 px gradient, full bleed.
  4. **Tabs (36 px):** Home · Edit · Tools, equal thirds.
  5. **Scroll area.**
  6. **Log toggle row (32 px, collapsed).**
  7. **Footer:** «Powered by thewhynot.ai», 11 px, muted, centred, always LTR in `<bdi>`.
- **Widths:**
  - **300:** single column, and verb sublines may wrap to 2 lines.
  - **360:** the reference width.
  - **480:** still a single column (no 2-up). Extra width goes to one-line sublines and the inline status pills.
    The QC frames grid is 2 columns at 300 and 360, 3 at 480.
- **Step strip:** a 7-segment bar (4 px tall, 2 px margins) plus "Step 4 of 7 · Build". Tapping it opens the
  labelled list. The full strip never wraps.
- **CEP (After Effects):** the same anatomy. **Installer:** a 760×540 window with a 232 px black left rail (logo +
  step list) and a 528 px content column (24 px padding), built from the same components.

## 4. Type scale (proposed tokens `--twn-type-*`)
| Role | Latin: family weight size/line | Arabic (IBM Plex Sans Arabic): weight size/line |
|---|---|---|
| display (Home hero, done screens) | Syne 700 22/28 | 600 24/36 |
| title (screen, dialog) | Syne 600 17/24 | 600 18/28 |
| verb (verb rows, tool names, wordmark at 700) | Syne 600 15/20 | 600 16/24 |
| label (card titles, buttons, tabs) | Inter 600 13/20 | 600 14/24 |
| body | Inter 400 13/20 | 400 14/24 |
| meta (sublines, last result, time) | Inter 400 12/16 | 400 13/20 |
| caption (chips, badge, footer at 400) | Inter 600 11/16 | 600 12/20 |
| eyebrow | Syne 600 11/16, UPPERCASE, +0.08em, `--twn-accent` | 600 12/20, no case, no tracking, `--twn-accent` |
| mono (timecodes, file names, log) | IBM Plex Mono 400 12/16, tabular, always LTR | the same (Latin run) |
| installer only | display Syne 700 32/40, title Syne 600 22/28, body Inter 400 15/24 (Inter 300 allowed ≥16 px) | 600 32/48, 600 22/36, 400 16/28 |

**Arabic rules:**
- 1 px larger than Latin, and a line height of at least 1.5× (body 1.71×), in fixed px so diacritics and shadda
  never clip.
- Never letter-spacing, uppercase, italic or tatweel.
- Weight 700 only at display size.
- A Latin word inside Arabic goes in `<bdi dir="ltr">` and keeps the Latin role font at the Arabic size.
- Western digits.

**Fallbacks** (no `@font-face` in UXP; the installer installs the fonts):
- Syne → Segoe UI / Helvetica Neue;
- Inter → Segoe UI / Helvetica Neue;
- Plex Arabic → Segoe UI (Windows Arabic) / Geeza Pro → Tahoma;
- Plex Mono → Consolas / SF Mono / Menlo.

**Lay out for Syne, the widest face:** a fallback is narrower, so it never overflows. Heights come from fixed line
heights, so swapping the font causes no layout shift. CEP and the installer load `fonts.css`.

## 5. Spacing and radius
- **Spacing** `--twn-space-1…7`: 4, 8, 12, 16, 24, 32, 48. Nothing else.
- **Radius:**
  - 2 for bars (hairline, progress);
  - 4 for skeleton lines and small mono chips inside text;
  - 8 (`--twn-radius`) for every `div role=button` control, input, list row, frame tile and inset;
  - 16 (`--twn-radius-card`) for cards, dialogs and notices;
  - 999 for `<span>` chips and the badge only.
- **Shape = role:** a rounded rectangle acts, a pill informs.
- **Draft:** radius 8 on a `div` control is not measured. Radius 16 is verified, so 8 is expected to paint. Check it
  in the next UXP lab run.

## 6. Colour roles
**Layers** (at most 3; glass is never stacked on #121212):
1. **Page:** `--twn-bg` #000.
2. **Card:** `--twn-glass` with a 1 px `--twn-border` (reads #141414).
3. **Inside a card:**
   - controls are solid `--twn-control` #242424, the solid equivalent of glass on glass (#272727). Solid, so a
     border can match the fill exactly;
   - recessed wells (frame tiles, waveform, code, mono file chips) use `--twn-frame-bg` #0D0D0D;
   - list dividers use `--twn-divider` .08.

**Text and fills:**
- **Text:** `--twn-text` for content and labels, `--twn-text-muted` for secondary text.
- **Violet text** (`--twn-primary-text`) is for links and the info icon. It sits on bg, card or inset only, never on
  a control fill: 4.42:1 there, a fail.
- **Primary:** `--twn-primary` fill, `--twn-primary-hover` on hover, `--twn-primary-pressed` #4800D8 pressed.
- **Selected list row:** `--twn-deep` with white text. No eyebrow on it: the pink is 3.62:1 there, a fail.

**Status:** an icon plus a word, always.
- Colour goes on the icon and the chip word only. Sentences stay white.
- Notice and chip fill: the status colour at 10% over black (`--twn-*-tint`). Notice border: the status colour at
  35% (`--twn-*-line`). This border is decorative; the icon and text carry the meaning.

**Gradient:**
- Header hairline and progress fill only.
- The RTL progress fill uses `--twn-gradient-rtl`, so violet is always at the moving tip.
- The hairline does not mirror: it is brand decoration, like the logo.

**Disabled:** fill `--twn-control-disabled` #1A1A1A and text `--twn-text-disabled` #6E6E6E (3.41:1, legible). It is
never done with opacity, which does not paint in UXP.

## 7. Focus as a border (the box-shadow ring is invisible)
- Every control has a **2 px border at all times**, so focus causes no layout shift.
  - At rest, the border colour equals the fill (#242424, #5400FB, ...). Use solid hex fills only.
  - On focus, only `border-color` changes: `--twn-focus-border` #9D6BFF on bg, card, control and deep fills.
  - On the primary and danger fills it is `--twn-focus-border-strong` #FFFFFF.
- **Measured (verified, contrast.py):**
  - violet vs #000 5.98, vs #141414 5.25, vs #121212 5.34;
  - violet vs its own fill #242424 4.42, vs hover #2E2E2E 3.87;
  - violet vs deep #390796 3.64;
  - **violet vs #5400FB 2.16: FAIL**, so white is used there (7.58);
  - white vs danger #FF5C5C 3.03 (pass, tight);
  - violet vs #FF5C5C 1.16 FAIL.
- **Inputs:** a 1 px rest border `--twn-border-input` #7A7A7A (4.29 on card, 4.89 on bg, 4.53 on inset). On focus it
  becomes 2 px violet, with 1 px less padding.

## 8. Primary CTA (no glow)
- **One per screen:** a solid #5400FB fill with a white label in the label role.
  - Block: 40 px. Inline: 32 px.
  - Radius 8.
  - An optional leading 16 px icon with an 8 px margin.
- **States:** hover #6A1FFF, pressed #4800D8, focus a white border, disabled #1A1A1A/#6E6E6E.
  Loading: a 16 px spinner replaces the icon, the label stays, and the width is locked.
- Emphasis comes from being the only saturated fill on screen. Nothing else is violet-filled except the selected
  ع/EN segment and the verb row that is the primary.
- `--twn-cta-glow` and `--twn-cta-ring` are retired in every host, CEP and the installer included: one language.

## 9. Iconography
- **Lucide**, at a pinned release (ISC). UXP colours SVG only through CSS `fill`; CSS `stroke` is **not checked**.
  So a build step outlines the strokes into fill paths (absolute stroke 1.5 px at 16/20 px, 1.25 px at 12 px), and
  the icons are coloured by `.ink-*` fill classes.
- This replaces the hand-drawn `kit/icons.ts` set.
- **Sizes:** 12 in chips, 16 inline, in buttons and as status, 20 in verb rows, tool cards and empty states.
  Every icon centres in a 32 px hit box when tappable.
- **Status set:** `circle-check`, `triangle-alert`, `circle-x`, `info`, `circle-dashed` (pending).
- **Verbs:** `folder-input` (Drop files), `clapperboard` (Make my edit), `circle-check-big` (Approve).
- **Tools:** `folder-tree` (Tidy), `audio-waveform` (Hush), `captions` (Kalam).
- **Navigation:** `chevron-right` and `chevron-left`, swapped per language in the renderer.
- **No borrowed meanings:** no sparkles for AI, no magic wand.
- **Mirror:** chevrons, the progress fill, the step-bar fill direction and back arrows.
- **Never mirror:** the logo, the hairline, the play/pause controls, clocks, timecodes, numbers, file names or the
  waveform.

## 10. Motion
- **Tokens:**
  - `--twn-dur-fast` 150 ms (hover, press, focus colour);
  - `--twn-dur-base` 200 ms (tab underline colour, chip state, notice in);
  - `--twn-dur-slow` 250 ms (progress fill width, sheet open);
  - `--twn-ease` cubic-bezier(.2,0,0,1);
  - shimmer 1200 ms linear loop.
- **Animate only** colour, border-colour, background-position (shimmer) and the progress fill width.
- **Never animate** height, padding, font-weight or position. The active tab keeps the same weight and changes only
  colour and its underline: a 2 px bottom border, transparent when inactive.
- **No layout shift:**
  - a skeleton has the exact box of its content;
  - notices take a reserved slot;
  - a button that turns to loading keeps its width.
- **Not checked:** whether CSS transitions and animations run in UXP. Every state must look finished with no motion.
  If they do not run, the shimmer falls back to a JS class toggle every 600 ms.

## 11. Voice
**EN rules:**
- Sentence case. Buttons are verb + object, at most 3 words.
- Digits for numbers. Name the thing (C0239), not "item".
- No "please", "oops", "!" or hype.
- An ellipsis only for running states. Raw codes only in the log.

| Do (EN) | Don't |
|---|---|
| "The engine is off." [Start engine] | "Error: ECONNREFUSED 127.0.0.1" |
| "Building your sequence · 23 of 47" | "Processing, please wait..." |
| [Approve] | [Submit] / [OK] |
| "This replaces your edits in C0239. Backup: C0239_prev.prproj" | "Are you sure?" |
| "Nothing here yet. Choose a client folder to start." | "No data." / "AI magic is ready!" |

**AR rules:**
- Clear MSA that an Egyptian editor reads instantly. Short imperatives on buttons.
- The English UI term in parentheses on first use only.
- Western digits. Latin, paths and timecodes in `<bdi dir="ltr">`.
- No literal translation of English idioms. No tashkeel except a shadda that prevents a misreading (المحرّك).
- **Draft:** all Arabic copy needs a native writer's approval.

| Do (AR) | Don't |
|---|---|
| «المحرّك متوقف.» [شغّل المحرّك] | «حدث خطأ غير متوقع أثناء الاتصال بالخادم المحلي» |
| «جارٍ بناء التسلسل (Sequence) · 23 من 47» | «يرجى الانتظار حتى تكتمل المعالجة...» |
| [وافق] | [إرسال] / [موافق] |
| «سيستبدل هذا تعديلاتك في C0239. النسخة الاحتياطية: C0239_prev.prproj» | «هل أنت متأكد؟» |
| «لا شيء هنا بعد. اختر مجلد العميل للبدء.» | «لا توجد بيانات» |

## 12. Component rules
- **Card:**
  - glass fill, 1 px border, radius 16, padding 12 or 16;
  - optional eyebrow, then a title in the label role, then body or meta;
  - at most one primary inside; no nested cards (use insets).
- **Chip (`<span>`):**
  - 24 px tall, radius 999, 8 px side padding;
  - a tint fill with the status-colour word and a 12 px icon;
  - a neutral chip is #242424 with muted text; a file chip is mono on #0D0D0D;
  - chips never act. A filter you can press is a button.
- **Status pill (header):** 12 px icon + value. No border, no fill; colour on the icon only.
- **Empty state:**
  - inside a card, min height 160, centred;
  - a 20 px icon in a 40 px #0D0D0D well;
  - a title in the label role, one muted sentence, one button (primary unless the screen already has one).
- **Loading skeleton:**
  - the same boxes as the content;
  - #242424 bars (radius 4, 8 px tall, centred on each line box);
  - a #2E2E2E shimmer band;
  - no full-panel spinners.
- **Error and notice card:**
  - error, warn, ok or info;
  - a tint fill with a status-line border, radius 16, padding 12;
  - a 16 px icon, **one white sentence, one button** (the named fix, else [Copy diagnostics]), and a ✕ in a 32 px
    hit box at the end;
  - info and ok cards have no button.
- **Buttons:**
  - 32 px default, radius 8, 2 px border, 12 px side padding (16 in a block);
  - secondary is a #242424 fill with a white label, hover #2E2E2E, pressed #383838;
  - ghost is transparent with a muted label that turns white on hover;
  - danger (in confirm dialogs only) is an #FF5C5C fill with `--twn-on-error` text and hover #FF7A7A.
- **Dialog:** an in-panel sheet card (warn tint) with:
  - the title, the "What will change" list and the backup name in a mono chip on its own row;
  - [Danger or primary] + [Keep my project]. No overlay blur.
- **Progress:** in this order:
  1. a status sentence, with "23 of 47" at the end;
  2. a 4 px bar: `--twn-track` with the gradient fill, radius 2;
  3. a meta row: elapsed time, then a [Cancel] ghost button.
  The violet tip is 1.74:1 on the track, so the numeric text is required (verified). The bar is never the only
  carrier of progress.
- **Badge (Needs you):** a pink `--twn-accent` fill, `--twn-on-accent` text (5.15:1), 20 px, radius 999. It is
  hidden at 0 and shows "99+" above 99.
- **Lists:** 40 px rows with 1 px divider lines, a leading 16 px icon, and the trailing action or chevron.

## 13. Home: the three verbs and the tool cards
- **Hero line** (display role): «Ready for C0239» / «جاهز لـ C0239», with the client in meta under it.
- **Verbs:** a vertical stack of 3 verb rows, 56 px each, radius 8, 8 px apart, never 3 columns. Each row has:
  - a 20 px icon in a 32 px well;
  - the title (verb role) and the subline (meta, can wrap to 2 lines at 300 px);
  - a trailing chevron.
- **The next verb** is the screen's primary:
  - a #5400FB fill, white title, subline `--twn-on-primary-muted` #E8E0FF (5.97, hover 5.08, pressed 7.29);
  - the well is #4800D8.
- **The other two** are #242424 secondary rows with the well in #0D0D0D.
- **Order is fixed** (Drop → Edit → Approve) so the eye learns it; only the fill moves.
- **Then:** a TOOLS eyebrow, then 3 tool cards in a list. Each card has:
  - a 20 px icon;
  - the name in the verb role: "Tidy", "Hush", "Kalam" (Latin brand names, in `<bdi>` in AR) plus the purpose
    in meta;
  - a "last result" meta line with a 12 px status icon («Last: 18 silences cut · 2 h ago»);
  - a chevron;
  - a ready or busy chip at the top end of the card, when there is one.
- **Last:** two list rows, Models and Settings.

## 14. Contradictions resolved (one line each)
1. Wordmark: Syne 700, 15/20, as built. The derived "600 13–14" is dropped.
2. The gradient is for the hairline and the progress fill only. B2's "CTA border glow" is dropped (it cannot paint).
3. `--twn-cta-glow`, `--twn-cta-ring` and `--twn-focus` (box-shadows) are deprecated. Focus is a border (§7) in
   every host.
4. "Fonts bundled in the panel" (B2): the installer installs them per user, CEP and the installer load
   `fonts.css`, and layouts are drawn to survive the fallback.
5. Icons: Lucide outlined to fills replaces the kit's hand-drawn set (inventory §7 #9 closed).
6. Disabled: explicit colour tokens, never opacity.
7. Buttons use radius 8. `--twn-radius-control` (16) is no longer used for buttons; 999 stays for spans.
8. Widths: mock 300/360/480 (controller), plus a 280 check for control rows only.
9. Pink is for eyebrows, the active tab and the Needs-you badge only. Site-style pink "Learn more" links become
   #9D6BFF.
10. Muted text: keep #B3B3B3 (passes on every surface) over the site's white at .8.
11. Inter 300 (site body) is used only at 16 px and up in the installer. Panels use 400 and 600. Syne 500 is unused.
12. Arabic headings use IBM Plex Sans Arabic in the product. Alexandria stays print-only.
13. Arabic weights: 400 body, 600 labels and titles, 700 never in panels.
14. Gradient direction: the token's 90deg pink→violet wins over the site's 270deg form (same look). RTL progress
    uses `--twn-gradient-rtl`.
15. Secondary = "glass" (B4.2) is built as the solid #242424, the visual equivalent of glass on glass, so the focus
    border can match the fill.
16. Footer: «Powered by thewhynot.ai» in English, LTR, in both languages (the owner's decision). The AR string
    stays English by design.
17. CEP and the installer may use flex `gap` and box-shadow technically, but use margins and borders, so one
    markup and one look.

## 15. Proposed additive tokens (for the build worker; `brand/tokens.css` is NOT edited here). 63 tokens.
```css
--twn-space-1:4px; --twn-space-2:8px; --twn-space-3:12px; --twn-space-4:16px; --twn-space-5:24px; --twn-space-6:32px; --twn-space-7:48px;
--twn-radius-bar:2px; --twn-radius-s:4px;
--twn-h-control:32px; --twn-h-control-lg:40px; --twn-h-row:40px; --twn-h-verb:56px; --twn-h-chip:24px; --twn-h-tabs:36px;
--twn-control:#242424; --twn-control-hover:#2E2E2E; --twn-control-pressed:#383838;
--twn-control-disabled:#1A1A1A; --twn-text-disabled:#6E6E6E;
--twn-primary-pressed:#4800D8; --twn-on-primary-muted:#E8E0FF; --twn-danger-hover:#FF7A7A;
--twn-divider:rgba(255,255,255,.08); --twn-border-input:#7A7A7A;
--twn-focus-border:#9D6BFF; --twn-focus-border-strong:#FFFFFF; --twn-focus-width:2px;
--twn-ok-tint:#06150E; --twn-warn-tint:#1A1203; --twn-error-tint:#1A0909; --twn-info-tint:#100B1A; --twn-accent-tint:#160910;
--twn-ok-line:#154B31; --twn-warn-line:#593E0B; --twn-error-line:#592020; --twn-info-line:#372559;
--twn-skeleton:#242424; --twn-skeleton-shine:#2E2E2E;
--twn-gradient-rtl:linear-gradient(270deg,#D95C9B,#5400FB);
--twn-dur-fast:150ms; --twn-dur-base:200ms; --twn-dur-slow:250ms; --twn-dur-shimmer:1200ms; --twn-ease:cubic-bezier(.2,0,0,1);
/* type: size/line per role, Latin then Arabic (weights and families per §4) */
--twn-type-display:22px/28px; --twn-type-title:17px/24px; --twn-type-verb:15px/20px; --twn-type-label:13px/20px;
--twn-type-body:13px/20px; --twn-type-meta:12px/16px; --twn-type-caption:11px/16px; --twn-type-eyebrow:11px/16px; --twn-type-mono:12px/16px;
--twn-type-ar-display:24px/36px; --twn-type-ar-title:18px/28px; --twn-type-ar-verb:16px/24px; --twn-type-ar-label:14px/24px;
--twn-type-ar-body:14px/24px; --twn-type-ar-meta:13px/20px; --twn-type-ar-caption:12px/20px; --twn-type-ar-eyebrow:12px/20px;
--twn-tracking-eyebrow:.08em;
```
**Contrast (verified, contrast.py, 87 pairs).** Every text and surface pair above passes 4.5:1, and every focus and
input pair passes 3:1, except these, all resolved:
- #DCCFFF on primary-hover 4.43 → **#E8E0FF** (5.08);
- violet focus on #5400FB 2.16 and on #FF5C5C 1.16 → **#FFFFFF** (7.58 / 3.03);
- violet text on #242424 4.42 → rule: no violet text on controls;
- pink on #390796 3.62 → rule: no eyebrow on selected rows;
- progress violet tip on the track 1.74, and #5400FB vs bg 2.77 → the numeric text carries progress, and the
  button label carries the CTA (both non-text and supplementary).

**Not checked:** CSS stroke, transitions and animations, `text-overflow` and radius 8 in UXP (next lab run). Arabic
copy needs a native writer.
