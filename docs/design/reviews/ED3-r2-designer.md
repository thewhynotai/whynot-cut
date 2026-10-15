# E-D3 round 2 — designer critique, all 35 screens (Addendum G2 bar)

Reviewer: brand-systems-designer agent. This is an AI review, not a human designer's sign-off. Arabic copy notes are
draft; a native writer approves them.

**Method.**
- **Measured.** A read-only DOM audit of all 2,188 renders (35 screens × every state × EN/AR × 300/360/480, installer
  760/640). Scripts and results are in the session scratchpad (`ed3r2/audit.js`, `run_audit.py`, `audit.json`).
- **Viewed.** Every state sheet in EN and AR, the widths sheets and the 280 px AE sheet. Readable 1× sheets were
  rebuilt for this, and 7 parallel visual passes ran.
- **Spot-checked at full size.** P-03, P-07, P-01, P-06 offline, P-09 confirm-nobackup and P-03 AR long.
- **Not checked.** Real UXP or CEP paint, hover/pressed, motion, the Windows keycaps (`?os=win`; the renders default to
  macOS by design), real pinned-bar scrolling (renders are full height), and NBSP in Arabic time phrases.

## 1. Verdict: NOT YET at the $1,000 bar

The system level is close. Across all 2,188 renders the audit found:
- 0 controls off radius 8 or the 2 px border;
- 0 screens with more than one violet fill;
- 0 box-shadow, gap, `<button>`, filter or SVG `fill=` attributes in any group file;
- 0 "engine" or «المحرك» in the UI;
- 0 tatweel;
- every text contrast pair at AA or better (the only fail is the mock macOS dialog's own blue button);
- `mock-motion` and `mock-keys` on every screen.

The shell, notices, empty states and skeletons now read as one product, and P-03/P-07 hold their own next to Frame.io.
Three things keep it below the bar:
1. **The status header lies.** "All set" shows above a warn or error card in **53 states across 25 screens** (EN 360,
   strict count). In 23 `long` states "All set" also sits next to "Needs you 99+". This is one bug in `mockup.js`
   `pills()`: it collapses on pill values only and never looks at the body.
2. **Destructive no-backup actions sit on ⌘↵.** Both group helpers bind the shared primary shortcut to the danger fill.
3. **Arabic is let down by bidi.** Latin names truncate from the wrong end, file names and paths scramble, drive
   letters reverse and the lockup is mirrored.

Below those sits a long tail of state-logic slips: stale screens that keep the main action live, paused work still
drawn as running, dead-end fixes, and a mock poster that is a person glyph. Fix the 3 P0s and the 12 P1 groups and I
expect the next round to pass.

## 2. Round-1 findings: status

**ED3-r1 (pattern):**
1. ع/EN selected = #383838 — **fixed** (verified: 0 renders with more than one violet).
2. Pills keep key words — **fixed** in code (`showKey = W>=360 || not ok`). Residual: P-10 normal at 300 shows bare
   "✓ running ✓ ready" (uncollapsed pillx).
3. Rest border on every control, tool cards solid radius 8 — **fixed** (verified: 0 role=button off 8 px/2 px).
4. P-07 flagged lines never cut — **fixed** (viewed).
5. Pinned action bar — **fixed in the mockup** (`.m-actionbar`). UXP scroll is **not proven** (lab).
6. P-03 offline neutral hero, nothing "Ready" — **fixed** (viewed). Regression: *stale* still keeps the primary live (P1-1).
7. Ghost buttons flush start — **fixed** (`.m-btn-flush`, used by back rows). Not measured.
8. Show less chevron-up — **fixed** (viewed).
9. P-03 verb row wrap at 360 — **not fixed**. The primary row's subline still wraps to 2 lines once the keycap is in
   it (P-03 stale/success).
10. Off-grid 10/6 px — **partly fixed**. New off-grid values come from the 1 px divider being counted (P2-1).
11. EN copy, one name per failure — **mostly fixed**. Drift: "Start the service" (tools) vs "Start WhyNot Cut"
    (shared), and "Open guide" vs "Open install guide".
12. AR: «وافق» everywhere, no tatweel — **fixed** (verified: «اعتمد» 0, U+0640 0). NBSP is **not checked**. Verb drift
    in other actions remains (P1-9).
13. Latin in Syne inside Arabic titles — **fixed**. Latin runs render as Inter 600 at the Arabic size (measured).
14. Focus and long renders on every screen — **fixed**. `.m-ctx` ellipsis now exists, but cuts the wrong end in AR
    (P1-4).

**G2-r1 (premium):**
1. P-07 no-Claude — **fixed** (viewed). It drops the Needs-you badge (P1-11).
2. P-01 no-Claude rows — **fixed**. Severity drift: the signed-out row is red ✕ while the pill is amber (P1-3).
3. P-03 no-Claude — **fixed**, but `no-claude-missing` still says "Sign in to Claude first" (P1-6).
4. Shortcut layer — **partly fixed**. `.m-kbd` sits on every panel primary. The installer uses a different keycap
   (`.i-kbd`), and primaries without a keycap remain in I-02, I-05 and I-08 (measured, 20 renders).
5. P-07 edit map — **fixed** (viewed). In `stale` the map isn't rebuilt (0:52 vs the 48 s reel).
6. Seeking timecodes — **fixed in design**. The UXP playhead API is pending the lab.
7. P-03 hero (poster, duration, step, done verbs) — **partly fixed**. Duration, step and done results are in, but the
   poster is a generic person glyph (P1-7).
8. Header collapse to "All set" — **implemented, rule broken** (P0-1).
9. P-01 sample clip — **fixed**.
10. Motion table per screen — **fixed** (`mock-motion` on all 35).
11. One Arabic register — **mostly fixed** (Egyptian). MSA remains in the privacy footnote and no-Claude cards
    («لا تُرفع أبدًا؛ يقرأ») (P1-9).
12. P-03 Settings row solid radius 8 — **fixed**.
13. P-07 footer hint as the expand control — **fixed**. It is 24 px tall, below the 32 px hit target (measured), and a
    second grey hint style exists in another state (P2).
14. P-01 "3 of 4 ready" bar — **fixed**.
15. No "Log" row — **fixed**.
16. C0239 twice on Home — **fixed**.

## 3. Findings

### P0 (a paying agency would cancel, or work can be lost)

**P0-1 · Header says "All set" over a problem.**
- **Where:** 25 screens / 53 states (EN 360, measured):
  - A-01 blocked, error, stale;
  - A-02 error;
  - A-03 normal, focus, fonts, unsaved, edited, edited-confirm, script-only, long;
  - A-04 error, stale;
  - P-01 stale;
  - P-03 stale;
  - P-04 error;
  - P-05 normal, several, focus, long;
  - P-06 failed;
  - P-07 error;
  - P-08 error;
  - P-09 confirm-nobackup, error;
  - P-10 error;
  - P-11 normal, link-refused, command, panel, held, update, tools, focus, long;
  - P-12 error;
  - P-13 stale;
  - P-14 unsaved, error, stale;
  - P-15 error;
  - P-16 confirm-nobackup, locked, stale;
  - P-17 error;
  - P-18 error-inout, error-selection;
  - P-19 no-text, stale;
  - P-20 error;
  - P-21 error;
  - P-22 error.

  Also "All set" + "Needs you 99+" together in 23 `long` states.
- **Wrong:** a warn or error card on screen, and the header says everything is fine.
- **Fix:**
  - In `M.mount`, compute `view.problem` = any visible `.m-notice-warn` / `.m-notice-error` / danger dialog / failed
    tile, OR a disabled primary, OR `view.needs > 0`.
  - `pills()` collapses only when the pills are OK **and** there is no problem.
  - Otherwise show one pill in the notice's kind, naming it ("Premiere restart needed", "1 problem"). When Needs-you
    is the only reason, show no status pill (the badge is enough).
  - The P-11 catalogue sets matching pills per card.

**P0-2 · Installer headline contradicts the state.**
- **Where:**
  - I-06 error: "WhyNot Cut is ready" above a red panel failure;
  - I-08 error: "WhyNot Cut 3.0.1 is ready" above "We didn't install the update";
  - I-05 loading, checking, waiting, timeout and success: the title stays "Claude isn't installed" above "Claude is
    ready".
- **Fix:** the title follows the state:
  - I-06 error: "One step needs you";
  - I-08 error: "Update not installed";
  - I-05: "Installing Claude…" → "Sign in to Claude" → "Claude is ready". Keep the I-05 rail step active until
    Continue.

**P0-3 · A destructive, non-undoable action carries ⌘↵.**
- **Where:**
  - P-09 `confirm-nobackup`: "Rebuild without backup ⌘↵" (viewed);
  - P-16 `confirm-nobackup`, via the same shared rule;
  - I-09 normal: Uninstall is the violet primary with ↵.
- **Cause:** `js/tools-ae.js:39` binds `.m-btn-danger` to the primary keycap; `js/premiere-core.js:117` does the
  same through `PC.kbtn(..., "enter")`.
- **Fix:**
  - Never put a keycap on danger.
  - In any confirm, Return = "Keep my project" (the safe button, focused by default).
  - Danger needs a click or Tab+Space.
  - I-09 first screen: a neutral "Continue" leads to the red confirm.

### P1 (a buyer would notice)

**P1-1 · Stale keeps the main action live.**
- **Where:** P-01, P-03, P-05, P-06, P-13, A-01 stale. P-02, P-14 and P-16 already do it right.
- **Wrong:** the notice says to restart Premiere/AE, its fix is grey, and "Make my edit" / "Start the build" stays
  violet.
- **Fix:** promote one `M.stale()`:
  - the notice's "Check again" takes the violet;
  - the main action is disabled with the reason "Restart Premiere first".

**P1-2 · Paused or blocked work is drawn as running.**
- **Where:**
  - P-06 offline (viewed): "Building your sequence… 23 of 47", a 49% bar, "Claude is working on it";
  - A-04 stale: live spinners and an old "Fix" chip;
  - A-03 no-claude: the Arabic-check card is still spinning;
  - P-08 stale: a missing frame is counted as "fail";
  - P-19 no-text: the failing template is shown as a normal selected tile.
- **Fix:**
  - A "paused" variant for progress and stage cards: amber pending icon, no spinner, "Paused at 23 of 47, resumes when
    the service is back", the trust line hidden.
  - Missing counts as "missing", not fail.
  - A failing selected tile gets an error border and reason.

**P1-3 · One condition, three severities.**
- **Where:**
  - P-01 signed-out: row red ✕, pill and step bar amber;
  - P-02 restart-once: pill red "not linked", card amber;
  - P-03 and P-05 error: pill amber, notice red;
  - P-13 to P-20 no-claude: pill "Claude signed out", notice "Claude isn't open".
- **Fix:** one status model in `mockup.js`. Each condition maps to one kind, one icon and one name, used by the pill,
  the notice and the row.

**P1-4 · Arabic bidi.**
- **Where:**
  - Header row 2 in AR `long` (viewed P-03): the client truncates from the start ("…staqbal Family…") and the item
    code disappears.
  - Tools/AE file names are plain `div.t-mono`, not `<bdi>` (measured: about 30 unisolated Latin runs per P-14 state).
  - Paths and drive letters reverse: «:C», «.Users/…/log», "After Effects 25.4" → "25.4 After Effects".
  - I-06 menu path chevrons run against reading order.
- **Fix:**
  - Every Latin, mono, path, version and menu run goes through `M.ltr`/`M.mono` (`<bdi dir=ltr>`,
    `unicode-bidi:isolate`).
  - Ellipsis per run, client name first, item code never dropped.
  - Paths no-wrap with a middle ellipsis.
  - Menu path as one LTR chip.

**P1-5 · The AR lockup is mirrored.**
- **Where:** every AR header and installer. The monogram sits to the right of the wordmark.
- **Wrong:** direction §9 says the logo never mirrors.
- **Fix:** the lockup (monogram + 8 px + wordmark) is a fixed LTR unit that moves as a whole to the right edge. Update
  the render self-check (`mono=right` still holds).

**P1-6 · The fix button doesn't fix it (dead ends).**
- **Where:**
  - P-11 normal: "Start WhyNot Cut" offered for damaged settings and a rejected panel;
  - P-11 panel: the text says reopen, the button is Contact support;
  - P-03 `no-claude-missing`: "Sign in to Claude first";
  - I-05 error: Check again before any install path is offered;
  - P-20 offline: no Try again after start;
  - A-01 offline: a second notice without a button;
  - I-03 offline and I-07 nointernet: "use the offline download" with no button;
  - P-21 skipped: Download all is enabled with too little space;
  - I-07 manifest: copy a shell-script URL.
- **Fix:** one named fix per card that resolves *that* cause, e.g. "Repair WhyNot Cut", "Reload panel",
  "Install Claude", "Open claude.ai/download", "Get the offline installer", "Choose another drive",
  "Open download page". Never a script URL.

**P1-7 · The media is a placeholder.**
- **Where:**
  - P-03 hero poster: a person glyph at 36 px, still 36 px at 480;
  - A-02 storyboard: 5 empty numbered boxes;
  - A-04 frames: landscape tiles for a 9:16 reel, one an empty black box;
  - P-08: every thumb is the same gradient, and the failed frame doesn't show the safe area.
- **Fix:** one promoted `m-media` tile:
  - 9:16 by default, a #0D0D0D well, a clapperboard fallback glyph (not a person);
  - 48×84 at 480;
  - a safe-area outline and the offending box on failed frames.

  Mock real-looking frames.

**P1-8 · The primary after an action is wrong.**
- **Where:**
  - P-15 and P-17: Undo is violet with ⌘↵ right after success, so a habitual ⌘↵ reverses the work;
  - P-08 normal: Re-export is violet while the fail's fix is grey at about 1,470 px;
  - P-01 success: the title is still "Let's get WhyNot Cut ready" and there is no next step;
  - P-08 success: a dead end at step 6.
- **Fix:**
  - Done / "Show in project" takes the violet. Undo goes secondary with no keycap.
  - Sort failed frames first, and the fail's fix takes the violet.
  - P-01 success: "You're ready" plus a violet "Go to Home".
  - P-08 success: advance to step 7 with "Open project".

**P1-9 · Arabic copy drift.**
- **Where:**
  - "Try again" is «حاول تاني» (core, 19 uses) vs «جرّب تاني» (tools/installer, 13);
  - "Check again" is «افحص تاني» vs «اتأكد تاني» (tools, 6);
  - Undo is «تراجع» vs «رجّعهم»;
  - «رندر/ريندر», «موديل/نموذج»;
  - MSA privacy lines;
  - glued strings «سطّبClaude» (I-05) and «افتحClaude» (I-06);
  - «سيب مشروعي» (reads as "abandon") and «سيبك منه» (slang on Discard);
  - «متحفوظ».
- **Fix:** move every action label to shared `strings.js` (`action.retry`, `action.check_again`, `action.undo`, ...)
  and delete the group copies. Native-writer pass. Proposed: «خلّي مشروعي زي ما هو», «تجاهل التعديلات»,
  «عمرها ما بتترفع؛ Claude بيقرا…».

**P1-10 · Developer words and paths a user sees** (G2 clarity rule).
- **Where:**
  - I-01, I-04, I-06, I-07, I-08 and I-09: `…/LaunchAgents/ai.thewhynot.cut.plist`, `settings.json.bak-…`
    (measured: 32 renders), the log path in every error card (breaking mid-word), "github.com/thewhynotai";
  - P-22 support: "heartbeat", "code=timeout request=r-8f21", "FAILED export_frames";
  - P-11 link-refused: "a message was too large".
- **Fix:** plain locations ("In Login Items", "Claude settings backed up today 10:32"). Raw paths and log lines only
  behind "Show details" / "Copy details". Drop the log line from error cards; "Save a report" covers it.

**P1-11 · The Needs-you count is not one truth.**
- **Where:**
  - A-02 empty shows "Needs you 1" with "No plan is waiting";
  - A-03 counts a "nothing to do" card (4, should be 3);
  - P-10 long: header 99+, list 7;
  - P-07 no-claude drops the badge while the build is blocked.
- **Fix:** the badge = the count of actionable items from one source. Empty/loading = 0. A blocked approval still
  counts.

**P1-12 · Trust and security copy.**
- **Where:**
  - I-01 "Nothing is sent from your computer" vs I-05 and P-07 "Claude reads the transcript, the plan and frames";
  - I-01 offline: "No internet needed";
  - I-02: "Don't ask me each time Claude uses WhyNot Cut" is ticked by default;
  - no-Claude cards on P-01, P-08, P-11, P-12 and P-22 are 6–8 lines and bury the fix (the P-01 primary lands about
    700 px down at 360).
- **Fix:**
  - "Your video and audio never leave this computer."
  - "Installs without internet; Claude and sign-in need it later."
  - Leave the permission box unticked, with one line on what it skips.
  - No-Claude card = one sentence + one button + a "What Claude sees" link.

### P2 (polish)
- **P2-1 · Grid.** Off-grid because the 1 px divider is counted (measured):
  - `pc-row`, `m-actionbar`, `i-bar`, `pc-model`, `pc-diff`, `m-check` pad 13;
  - `i-step` pad 6/7 (2,800+ instances);
  - `pc-step` pad 9.

  Fix: padding 11 + 1 px border = 12; `i-step` 8 + border → 7 + 1.
- **P2-2 · Type off-scale** (measured):
  - pill text Inter 400 11/16 (caption is 600 11/16);
  - stat numbers Inter 600 15/20 (P-14) and 20/28 (A-04);
  - AR `m-linkbtn` 600 13/20 (AR meta is 13/20 at 400; label is 14/24).

  Fix: add `--twn-type-stat` (Inter 600 20/28, AR 600 20/32). The pill uses caption 600, or document 400 as
  `pill`.
- **P2-3 · Hit target.** P-07 `.m-linkbtn` is 24 px tall (EN) / 28 px (AR) (measured). Fix: min-height 32.
- **P2-4 · Step-strip icon semantics.** triangle-alert means "waiting for you" in P-03, P-07, A-02 and P-08, info
  circle in A-01, dashed in P-01. Fix: `waiting` = the pink accent dot (the Needs-you colour); warn only for problems.
  The same applies to "In progress" chips in amber (P-04/P-05) and P-12 "Kept your original line".
- **P2-5 · Back affordance drift.** chevron (216 renders) vs arrow (213) (measured). Fix: one `M.back()` with the
  chevron. P-04 puts the notice above Back + title, and P-02 below. Fix: Back + title first, then the notice slot.
- **P2-6 · Confirm bullets.** "What will change" uses dashed-pending icons (P-14, P-16, A-03) or ticks (P-09, P-21).
  P-21 remove-confirm uses violet for a destructive action. Fix: neutral 4 px dots; Remove is danger without a
  keycap.
- **P2-7 · Two competing fixes.** P-07, A-02 and P-05 error (Try again + live Approve/Make my edit); P-21 error (Try
  again + row Download); P-14/P-16 stale (two Scan again). Fix: while the notice is up the bar button is disabled, or
  the notice's button is the only fix.
- **P2-8 · Mock data contradicts itself.**
  - P-15: 112 removed vs 4 kept; 7 of 8 with 2 out;
  - P-14: 4 bins = 120 vs 214;
  - P-17: 18 vs 20/24;
  - P-07 stale: 48 s vs a 0:52 map;
  - I-03: 6.0 vs 3.6 GB;
  - I-08 success: footer 3.0.0;
  - I-04 macOS prompt names Documents, not the clients folder.

  Builders copy mocks, so fix them.
- **P2-9 · Wrapping.** Orphans and mid-token breaks ("C0239_interview_ / final_v2", "2026- / 10-13", "Why / Not").
  Fix: NBSP before the last word and inside "The Why Not"; break file names only at `_`, with a middle ellipsis.
  `text-wrap` is unproven in UXP, so don't rely on it.
- **P2-10 · Glyphs.** The mono colon gap ("6 :40"). "⌘ O" reads as zero. I-08 Syne old-style digits ("3.o.ı"). Fix:
  set keycap letters and versions in Inter.
- **P2-11 · 300 px header.** Needs-you collapses to a bare "1 ›". Fix: keep the label and drop the ع/EN text to the
  glyph.
- **P2-12 · Installer.**
  - Close has 3 looks (ghost / grey / violet), and Back is filled in I-02 but ghost elsewhere.
  - "Genuine Setup from The Why / Not" orphan.
  - "1 to know" chip.
  - I-04 sidebar spinner while "Needs you".
- **P2-13 · AR template previews mirror** (P-19 lower third moves right). Fix: media previews `dir=ltr`.
- **P2-14 · Dismissable blocking errors** (P-02 link-off/claude-missing, P-18 errors): the ✕ hides the only fix.
  Fix: no ✕ on blocking notices.
- **P2-15 · `check_css.py` misses the group files.** It scans only `design/*.css|*.js` and `screens/`, never `css/`
  or `js/`, and never `@font-face`. My grep of those folders found no violations. `@font-face` sits only in
  `mockup.css:17-23` (mockup-only, commented). Fix: scan `css/**` and `js/**`, and fail on `@font-face` outside
  `mockup.css`.
- **P2-16 · P-16 AR 300.** The label «الإعداد المحفوظ:» is truncated (measured, 11 renders). Fix: let it wrap.

**Dropped from the passes (not defects):**
- ⌘ on keycaps: `M.OS` defaults to macOS per G11; `?os=win` shows Ctrl.
- Approve "below the fold": renders are full height, and the bar is pinned. UXP proof is a lab item.
- The violet ring on secondary focus: it follows spec §7 (white only on primary and danger).

## 4. Components to promote into mockup.css / mockup.js

| Promote | Today | Drift found |
|---|---|---|
| Status header logic (`view.problem`, one status model) | `pills()` | P0-1, P1-3 |
| `M.notice` with a disabled/busy button + reserved slot | `PC.notice`, `TA.slot` | two notice builders |
| `M.offline()`, `M.noClaude(kind)`, `M.stale()` | `TA.offline/noClaude/stale`, `PC.noClaude`, inline core notices | labels ("Start the service" vs "Start WhyNot Cut"), icons (log-in vs external-link), primary vs secondary, ✕ vs none |
| `m-dialog` (confirm sheet) + keycap policy | `.pc-dialog` (16/12 px pad), `.ta-dialog` (12 px at every width) | padding, bullets, ⌘↵ on danger |
| `m-radio` + `m-dot` | `.pc-radio` (top-aligned, 2px pad), `.ta-radio` (centred, 0), `.i-radio` | alignment, padding |
| `m-seg` control | `.ta-seg` + header `.m-seg` | two implementations of one control |
| `m-toggle`, `m-select`, `m-slider`, `m-sechead` | `.ta-tog`, `.ta-select`, `.ta-slider`, `.ta-sechead` (marked PROMOTE) | tools-only today; core and installer will need them |
| `m-tile` | `.pc-tile` (flex 1 1 0), `.ta-tile` (1 1 auto, deep selected) | sizing, selected state |
| `m-media` (poster / frame / thumb, 9:16) | `.m-poster`, `.pc-thumb*`, `.ta-frame`, `.ta-th*` | P1-7 |
| `m-listrow` (+ dense) | `.pc-row` 12, `.pc-step` 8, `.i-step` 6, `.ta-checkrow`, `.m-li` | 4 paddings, divider counting |
| `m-stages` (stage list) + step-strip status map | `.pc-step`, TA stage list, `.i-step`, `.m-steps` | icons per status (P2-4) |
| `m-bullet` | `.pc-bullet`, `.ta-bullet` | margin-top only |
| `m-kbd` (one keycap; retire `.i-kbd`) | `.m-kbd` outlined mono; `.i-kbd` filled sans; danger-kbd rule copied in pc + ta css | three looks in the installer |
| `M.back()` | `TA.back` (chevron), core (arrow) | P2-5 |
| `M.trust()` / `M.saved()` | `PC.trust/saved`, `TA.trust/saved` | icon colour (info vs ok) |
| `m-logline` | `.pc-logline`, `.i-logline` | truncation vs wrap |
| Shared action strings | `p13.start_service`, `p13.check_again`, `p13.open_claude`, group retry/undo keys | P1-9 |
