# WhyNot Cut 3.0 — Addendum B: UI/UX like thewhynot.ai, Arabic + English, easy to use

| | |
|---|---|
| Date | 2026-10-12 |
| Requested by | Yunus, in his words: «عاوز البلاجن ان ui and ux تكون زي الويبسايت وعربي وانجليزي وتكون سهله الاستخدام» ("I want the plugin's UI and UX to be like the website, in Arabic and English, and easy to use") |
| Replaces | Master plan D13's "panel follows the host theme with brand accents only". Every WhyNot surface now uses the **website's look** |
| Brand source | `docs/review/2026-10-11/magnific-brand.md` §2, `brand/logo.svg`, and https://thewhynot.ai/ (Framer site: black, glass cards, Syne + Inter, pink→violet gradient) |
| Commit | The executor commits this to `docs/superpowers/specs/addendum-b/` (single writer) |

## B1. Where it applies
Every surface the editor sees gets one design system (`brand/tokens.css` + `adobe/panel-ui/` components):
1. The **WhyNot Cut panel in Premiere** (UXP): home, pipeline, approvals, QC frames, and the three tool tabs
   (Kalam / Hush / Tidy, restyled only; their flows and controls stay exactly as their PRDs, per Addendum A).
2. The **After Effects panel** (signed CEP): same components.
3. The **installer** checklist/progress screens (Windows and macOS front ends; the one-liner prints the same brand
   colours where the terminal allows).
4. The **Arabic/English PDF guide**, already on brand (Phase 10). Keep it consistent with the panel's screenshots.
5. **Generated HTML/MD reports** opened by the editor (handoff README, `NEEDS-YOU.md`, publish package preview), where
   rendered.

## B2. The look (from the website)
- **Surfaces:**
  - background **#000000**;
  - cards **#121212**, with a glass layer `rgba(255,255,255,.08)` and border `rgba(255,255,255,.14)`;
  - radius 16 px for cards, pills 999 px (like the site's nav pill).
- **Brand colours:**
  - primary violet **#5400FB** for button fills (white text 7.6:1);
  - violet text/links on dark **#9D6BFF** (raw #5400FB fails as text);
  - pink **#D95C9B** for eyebrow labels and the active tab underline;
  - deep **#390796**;
  - gradient `linear-gradient(90deg,#D95C9B,#5400FB)` for the header hairline, progress bars and the main CTA border
    glow.
- **Status colours:** ok #3DD68C, warn #FFB020, error #FF5C5C, each with an icon (never colour alone).
- **Type:**
  - **Syne** 600/700 for titles and section labels (uppercase eyebrows, like "The TWN Method" on the site);
  - **Inter** 300/400/600 for UI text;
  - **IBM Plex Sans Arabic** for all Arabic (the site has no Arabic font);
  - **IBM Plex Mono** for commands and timecodes.

  All are OFL, bundled in the panel (no network fonts).
- **Logo and voice:**
  - the TWN monogram + "WhyNot Cut" in the header, with the footer «Powered by thewhynot.ai»;
  - website tone: short, calm, confident. "Clarity first."
- **Always dark** like the site. Premiere's own UI is dark, so it sits well. Check contrast on Premiere's Light theme
  too; the panel stays dark.

## B3. Arabic + English
- A language switch (ع / EN) in the header. It's remembered per editor, and the first-run default comes from
  preferences `language`.
- Arabic is fully **RTL**: layout mirrored (tabs, steps, progress direction, icons with direction), CSS `direction`
  (not `sp-theme dir`, which is broken in UXP). Commands, paths, timecodes and numbers sit in `<bdi dir="ltr">` with
  Western digits.
- **One string table** (`panel-ui/i18n/{ar,en}.json`) for all tabs including the three tools. The tools' existing
  i18n files are merged into it with their keys kept. No hard-coded strings; a test fails on any untranslated key.
- Arabic copy is written in clear Egyptian-friendly Modern Standard Arabic, with English UI terms in parentheses the
  first time (e.g. «التسلسل (Sequence)»).

## B4. Easy to use (UX rules)
1. **Home screen = three big actions**, the plugin's three verbs: **Drop files / Make my edit / Approve**, plus the
   tools (Organise · Cut silences · Captions) as cards. Each shows its one-line purpose and its last result.
2. **One primary button per screen**, violet. Secondary actions are glass buttons. Destructive actions (cut, remove,
   rebuild) always show what will change and the backup name, and ask for a confirm.
3. **Progress you can read:** a step strip (Transcript › Plan › Approve › Build › Frames › QC › Handoff), the current
   step's progress bar with elapsed time and Cancel, plain-language status ("Building your sequence… 23/47
   graphics").
4. **Errors say what to do:** every error shows the cause in one line, the fix button or the exact step, and "Copy
   diagnostics". No raw codes on screen; they go in the log drawer.
5. **Empty states teach:** when there's no client, no clip or no engine, show what to do next with one button. No
   blank panels.
6. **"Needs you" badge:** a count of things only the editor can do (approve, listen to flagged words, fonts, music).
   Opens `NEEDS-YOU.md` in the panel.
7. **Narrow-panel first:** everything works at 280–360 px docked width. Nothing scrolls sideways. Hit targets ≥ 32 px.
8. **Keyboard and accessibility:** visible focus ring (#9D6BFF), tab order follows the visual order (mirrored in
   RTL), labels on every control. Contrast ≥ 4.5:1 for text, 3:1 for large text and icons.
9. **Same patterns everywhere:** Kalam, Hush and Tidy keep their own steps (scan → preview → apply → undo) but use the
   same cards, buttons, chips, waveform/preview styles and progress strip as the main pipeline.

## B5. Tasks and phase placement (no new parallel track)

| Task | Phase | What |
|---|---|---|
| B-T1 | **6, now** (Adobe track, before more panel screens are built) | `brand/tokens.css` + `panel-ui` component kit: header, tabs, card, button (primary/secondary/danger), pill/chip, step strip, progress, toast, dialog, empty state, log drawer, frame grid, waveform frame. AR/EN i18n + RTL. Bundled fonts. A live style-guide page in the spike plugin |
| B-T2 | 6 | Restyle the existing panel screens (header, pipeline, approvals, QC grid, actions) to the kit. Home screen per B4.1 |
| B-T3 | 6B | Kalam/Hush/Tidy tabs restyled to the kit, flows unchanged; their i18n merged |
| B-T4 | 6 (AE) | The After Effects panel uses the same kit |
| B-T5 | 7 | Installer front-end screens in the same look (checklist rows green/amber/red with icons, AR/EN) |
| B-T6 | 8 | Design review by the `brand-systems-designer` agent against the website: screenshots of every screen in **AR and EN**, at 280 / 340 / 480 px, on Premiere Dark and Light. Fix every finding |
| B-T7 | 9 | **Usability run:** 8 scripted tasks done only through the panel, in Arabic, then English ("set up a client", "edit a clip and approve", "cut silences", "caption this sequence as a MOGRT", "organise the project", "undo the last cut", "find why the engine isn't running", "open what needs me"). Each must be finishable with no Claude chat help, and every friction point gets fixed |
| B-T8 | 10 | Guide screenshots retaken from the final UI, in both languages |

## B6. Tests and gates
- **Automated:**
  - a token test (every colour used comes from `tokens.css`);
  - contrast checks for every text/background pair in the kit;
  - an i18n completeness test (no missing AR/EN keys, no hard-coded strings in panel source);
  - an RTL snapshot test (the mirrored layout's order);
  - a font-bundle test (fonts load offline).
- **Visual QA in the Phase 6 and Phase 8 gates:** screenshots of every screen in AR and EN, viewed one by one, plus
  the designer review. No overlapping or clipped text, Arabic shaping correct, and no horizontal scroll at 280 px.
- **Usability (B-T7) in the Phase 9 gate:** all 8 tasks completed in both languages, with the time per task recorded.
- **Not allowed:** changing the behaviour or the steps of Kalam/Hush/Tidy (Addendum A). Only their look changes.
