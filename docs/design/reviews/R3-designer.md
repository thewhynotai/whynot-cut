# R3: designer re-review of the 35 panel and installer mockups

Reviewer: the brand-systems-designer agent (the same reviewer as round 2). This is an AI review, not a human designer's
sign-off. The Arabic notes are drafts; a native writer approves the Arabic.

Date: 2026-10-16. Source: HEAD aa36352 (branch release/3.0). This round was read-only: the only file written is this one.

**Method:**
- **Measured.** I ran a read-only DOM audit on the HEAD sources: 2,450 page loads. That covers all 35 screens × every state × EN/AR × 300/360/480, the installer at 760/640, and A-01..A-04 at 280 in **every** state. The audit records:
  - the header pill;
  - the problem signals (warn/error notices, chips, icons, disabled primaries);
  - keycaps on danger buttons;
  - the violet count;
  - titles and primaries;
  - the primary's y-position;
  - Latin isolation in AR;
  - truncation and contrast.

  I also measured the D-01/D-02 bracket and quote glyph positions with a Range-rect probe at 300/360/480 and 760/640. The scripts and `audit.json` are in the session scratchpad, under `ed3r3/`.
- **Viewed.** Seven parallel visual passes covered every state sheet in EN and AR, every widths sheet and the 280 renders. I opened these full-size myself:
  - P-01 normal (EN, and AR at 300/360/480);
  - P-03 normal and stale;
  - P-06 stale;
  - P-09 confirm-nobackup;
  - P-11 normal;
  - P-17 normal;
  - P-19 selected;
  - P-22 normal (EN and AR);
  - A-02 at 280 (AR), A-04 stale;
  - I-05 normal and error (AR), I-06 error, I-09 confirm (AR).
- **Not checked:**
  - real UXP/CEP paint, hover/pressed states and motion;
  - Windows keycaps;
  - the real docked panel height (fold claims assume 700–800 px);
  - grid and type scale (not re-measured this round);
  - native Arabic approval;
  - whether "Help improve our AI models" is Claude's exact settings label today.

**Stale renders.** `mockup.js`, `mockup.css` and `strings.js` changed at 01:31 in aa36352. That change covers:
- Arabic quote and bracket pairs;
- the 32-character no-wrap rule;
- binding «لـ» to the next word;
- the H24 gate on I-07 and P-22.

Only P-01, P-12, P-22, I-05, I-07 and the A-* 280 renders were made after it. The other 30 screens were rendered at 00:39–01:18, so their AR line wrapping may shift a little.

All logic findings below come from the DOM audit on HEAD, so they are current. Every visual finding I list was re-checked against the HEAD behaviour, or comes from code that aa36352 did not touch.

## 1. Verdict: NOT YET (close; one more shared pass)

The three round-2 P0s are fixed where they were named:
- **Keycap rule (P0-3): fully closed.** The audit found 0 keycaps on any danger or destructive button across 2,450 renders. Every danger confirm focuses the safe button. I-09 now leads with a neutral Continue.
- **Installer headlines (P0-2): closed** on I-05, I-06 error and I-08 error.
- **"All set" over a problem (P0-1): down from 53 states to about 12.**

Other round-2 items are closed too:
- the stale rule;
- the AR lockup;
- Undo never being the violet after success;
- the Needs-you count;
- the Back chevron;
- confirm bullets;
- 0 controls off radius or border.

What still blocks a beta:
1. **The header can still lie (P0-1, partly closed).** The shared `liveState()` reads only `.m-notice-warn/-error` and the danger dialogs. The page self-check `statuslie` uses the same blind spot, so `render_all.py` passes. It misses:
   - warn chips and rows;
   - blocking *info* notices;
   - amber (non-danger) confirms;
   - disabled main actions;
   - paused or running checks;
   - setup in progress.
2. **A new P0 introduced by the stale fix.** On P-06 stale, the notice tells the editor to quit Premiere while a build is drawn running inside Premiere.

Below these sit 12 P1 groups. Most of them are the same few component rules applied unevenly:
- status kinds;
- paused vs running;
- bidi runs;
- the H24 support line.

If the shared pass in §3 lands, I expect round 4 to pass for beta.

## 2. Round-2 items: closure

| R2 | Status | Evidence (screen · state · file) |
|---|---|---|
| **P0-1** "All set" over a problem | **PARTLY** | Gone from the 53 listed states. Still showing "All set" (audit, EN 360, every lang): P-15 sync-done (a clip "Left out"); P-08 stale (missing-frame notice + amber chip); A-03 probe (Start disabled, check running); P-05 locked (Make my edit disabled under "Mona is working"); P-09 confirm/focus, P-14 confirm and P-16 confirm (amber "Rebuild/Clean/Cut?" cards); P-18 model-busy (Start disabled); P-01 normal ("3 of 4 ready", one step open). Cause: `mockup.js liveState()` / `M.selfCheckExtras`. See F-01. |
| **P0-2** Installer title contradicts the state | **CLOSED** where named, **same class open** | I-05 runs "Installing Claude…" → "Sign in to Claude" → "Claude is ready"; I-06 error says "One step needs you"; I-08 error says "Update not installed". Other screens still have the problem: I-06 amber/long ("WhyNot Cut is ready" over an amber row, all-green rail), I-08 loading/checking ("3.0.1 is ready"), I-09 error ("Removing WhyNot Cut"), I-01 upgrade ("Install"), I-03 success ("Checking this computer"), I-08 offline (bare "Update"). See F-05. |
| **P0-3** Danger action on Mod+Enter | **CLOSED** | 0 danger keycaps (audit). Viewed: P-09 confirm-nobackup (EN/AR) shows "Keep my project · Esc" focused and red "Build without a backup" with no keycap; P-16, P-21 remove-confirm, I-04 confirm and I-09 confirm are the same. Residual P2: the amber, backed-up rebuild confirms (P-09 confirm, A-03 edited-confirm) keep ⌘↵ on "Rebuild", which replaces the editor's timeline changes (F-21). |
| P1-1 Stale keeps the main action live | **CLOSED** | P-01, P-03, P-05, P-13 and A-01 stale: the notice's Check again is violet, and the main action is disabled with "Restart Premiere first." New gaps: P-06 stale (F-02) and P-01 stale "Try the sample clip" stays live (F-20). |
| P1-2 Paused work drawn as running | **PARTLY** | Closed: P-06 offline (amber pause, "Paused at 23 of 47"), A-04 stale, P-19 no-text. Open: A-03 probe draws a *running* check as paused; A-04 no-claude has a spinning "Wait for QC" + "Claude is fixing"; A-02 no-claude has a spinner; P-08 offline/error/no-claude show a spinner on step 6; A-04 offline turns every frame "Out of date". See F-07. |
| P1-3 One condition, several kinds | **PARTLY** | P-01 rows/pill are fixed. Open: P-11 update (one restart drawn amber + red, two Check again buttons); P-13 error (pill "service not responding", card "couldn't read the project"); P-08 stale (one missing frame in 3 kinds); installer panel-not-installed (pink I-04 / amber I-07 / red I-06); P-02 restart-once red vs stale amber. See F-08. |
| P1-4 Arabic bidi | **PARTLY** | Closed: header row 2 (client first, item kept), panel paths, I-06 menu path. Open: I-05 error primary «افتح /downloadclaude.ai»; I-02/I-03 AR path segments reversed and «:D»; A-03 «25.4 After Effects»; P-10 long «126 /dLmg»; P-15 sequence names. See F-04, F-09. |
| P1-5 AR lockup mirrored | **CLOSED** | Every AR header (audit + viewed): the monogram is left of the wordmark and the unit sits at the right edge. |
| P1-6 Dead-end fixes | **PARTLY** | Closed: P-03 no-claude-missing, P-11, P-21 skipped, I-05 error ("Open claude.ai/download"), A-01 offline, P-20 offline. New dead end: every not-live error card offers "Copy details for support" with nowhere to send it (F-03). Also: I-07 manifest has no action; I-06 nosignin has no button in the card (footer "Open Claude" is grey); P-09 confirm-nobackup "Free about 2 GB" has no re-check. |
| P1-7 Placeholder media | **PARTLY** | Closed: P-03 poster (9:16 clapperboard), A-02 storyboard, A-04 9:16 tiles with safe area. Open: P-08 missing-frame fallback is an image-off glyph, not the clapperboard; A-04 has "≡" text-less tiles; the A-02 storyboard labels are about 7 px at 1×. |
| P1-8 Wrong primary after an action | **CLOSED** | P-15 and P-17: Done ⌘↵ is violet; Undo is grey with no keycap. P-08 success "Open project"; P-01 success "Go to Home". Residual: P-20 normal has no primary after success (F-22). |
| P1-9 Arabic copy drift | **PARTLY** | The D-08 pass applied the word list (225 changes). New slips: see F-24. |
| P1-10 Developer words and paths | **CLOSED** | No log paths or plist in the main copy. 0 "engine"/«المحرك» hits (audit). Residual P2: P-14 missing-files list shows raw "D:\Old drive\Sahha\C0198.mov". |
| P1-11 Needs-you count | **CLOSED** | A-02 empty 0; A-03 3 = 3 = 3; P-10 long 99+ = 99+; P-07 no-claude 1. |
| P1-12 Trust copy / no-Claude card | **PARTLY** | P-12 is exact (one sentence + link + button). P-06/07/08/10 and A-03/A-04 cards are still two sentences; P-14..P-19 lack the "What Claude sees" link. The healthy P-01 Claude row now carries the D-01 + privacy + D-02 copy (F-06). |
| P2-3 Hit targets | CLOSED | 0 targets under 32 px (audit). |
| P2-5 Back affordance | PARTLY | The panel is all chevron. Installer I-02/I-03 "Back [Esc]" has no chevron. |
| P2-6 Confirm bullets / red Remove | CLOSED | Neutral dots; P-21 Remove is red with no keycap. |
| P2-7 Two competing fixes | PARTLY | Still two fixes: P-14 unsaved (Check again + Scan again), A-04 stale (Render again + Re-render scenes), P-19 no-text (two "From a file…"). |
| P2-8 Mock data | PARTLY | Still inconsistent: P-18 error-inout footer timecode vs "No In/Out"; I-03 Ready chip counts; I-08 checking "100%" vs "64 of 180 MB"; P-17 "V2" vs P-16 "A2"; I-02 "1024.5 GB free". |
| P2-9 Wrapping | OPEN | Mid-token breaks in every `long` state; "· estimate" orphans; P-03 week line (F-12). |
| P2-11 300 px header | CLOSED at 300 | At 280 (A-*) the badge is a bare "1 ›" (F-23). |
| P2-12 Installer polish | CLOSED | One Close look (grey + Esc). The "The Why Not" orphan is fixed. |
| P2-14 ✕ on blocking notices | PARTLY | ✕ still shows on blocking warn notices: P-08 stale, P-14 unsaved/stale, P-16 stale, A-04 stale (F-19). |
| P2-15 check_css scope | CLOSED (per fix list) | Not re-run here. |
| One violet per screen | **REGRESSION FOUND** | The audit counts only #5400FB; P-19 selected uses a deep-violet tile fill as well (F-10). |

## 3. Findings (25, most important first)

Each finding gives its severity, where it appears, what is wrong and the fix. "New" means the round-2 fixes introduced it; "R2" means a residual round-2 item.

### P0

**F-01 · The header still says "All set" over a problem (R2 P0-1 residual).**
- **Where:** EN+AR, every width:
  - P-15 sync-done;
  - P-08 stale;
  - A-03 probe;
  - P-05 locked;
  - P-09 confirm/focus, P-14 confirm, P-16 confirm;
  - P-18 model-busy;
  - P-01 normal (3 of 4 ready).
- **Wrong:** a partial failure ("Left out: Mic 3"), a missing frame, a disabled main action or an open confirm all sit under a green "All set". The self-check passes because it has the same blind spot.
- **Fix:** in `liveState()`, count all of these:
  - `.m-chip-warn/-error`;
  - `main .ink-warn/.ink-error` status icons;
  - `.pc-dialog`/`.ta-dialog` (any confirm, not only `-danger`);
  - any `m-btn-disabled` / `m-verb-disabled` primary;
  - `M.stages` running/paused;
  - `view.setup` with steps open.

  Map them as follows:
  - a confirm → no pill (the card is the state);
  - a disabled main → amber, named for the reason ("Waiting for Mona", "Model downloading");
  - a partial result → amber "Needs a look";
  - setup → "Setting up · 3 of 4".

  Mirror the same selector in `M.selfCheckExtras` so `render_all.py` fails on it.

**F-02 · P-06 stale tells the editor to quit Premiere during a running build (new).**
- **Where:** P-06 stale, EN+AR, all widths (viewed at EN 360).
- **Wrong:** the restart notice ("Close Premiere and open it again") is the violet. Under it, "Building your sequence… 23 of 47" keeps running with a live Cancel ⌘. and "don't open C0239_reel_v3 until the build finishes". Following the notice kills the build. `stalePass()` disables primaries but never looks at running work.
- **Fix:** when a run is active, the stale notice says "WhyNot Cut was updated. Restart Premiere after this build finishes." Its Check again stays grey until the run ends. Alternatively, the shell pauses the run first: "Paused at 23 of 47. Restart Premiere, then press Check again." Add a stale + running state to the self-check: no violet restart while `.m-progress` is live.

### P1

**F-03 · The H24 not-live support line is a dead end and looks accidental (new).**
- **Where:** every error card and the support row, EN+AR: P-01..P-22, A-01..A-04, I-01..I-09. Viewed: P-22 normal, I-05 error, I-06 error.
- **Wrong, three ways:**
  1. "Copy details for support" copies to the clipboard, but the screen names nowhere to paste it.
  2. The grey "Support page coming soon" has three layouts. It sits *beside* the button (installer; AR 360/480), wraps *under* it with about 0 px gap (EN 300/360, P-22), or is its own line with mt-3 (notices). "Guide coming soon" then stacks a second grey line, with the version line under that. Side by side with live controls it reads like leftover placeholder text.
  3. The Arabic «صفحة الدعم قريب» / «صفحة التحميل قريب» / «الدليل قريب» reads as "the page is near", with the wrong gender for صفحة.
- **Fix:**
  - One `M.soonLine` placement: under the button, aligned to its text column, mt-2, with an `info` 12 px icon.
  - Merge the two lines into one: "The support page and guide are coming soon."
  - Until the page is live, name a destination Yunus approves ("Send them to whoever set up WhyNot Cut for you", or a support email). Otherwise drop "Copy details" from the not-live error cards and keep it only in Settings.
  - AR draft: «صفحة الدعم جاية قريب» / «صفحة التحميل جاية قريب» / «الدليل جاي قريب» (native writer to confirm).
  - The installer `.i-support` and the panel `M.supportRow` must use the same block.

**F-04 · I-05 error: the Arabic violet button is scrambled (new).**
- **Where:** I-05 error, error-live, long; AR 760/640 (viewed).
- **Wrong:** the primary reads «افتح /downloadclaude.ai». The `LATIN` regex in `mockup.js` stops at "/", so "claude.ai" and "/download" become two isolates that RTL reorders. The body line with the same URL renders correctly.
- **Fix:** let a URL be one run (allow `/` after a domain in `LATIN`), or pass the URL through `M.ltr` in `i05.open`.

**F-05 · Installer titles still contradict the state on screens round 2 did not list (R2 P0-2 class).**
- **Where (EN+AR):**
  - I-06 amber/long: "WhyNot Cut is ready" plus an all-green rail over an amber restart row;
  - I-08 loading/checking: "WhyNot Cut 3.0.1 is ready";
  - I-09 error: "Removing WhyNot Cut";
  - I-01 upgrade: "Install WhyNot Cut";
  - I-03 success: "Checking this computer";
  - I-08 offline: bare "Update".
- **Fix:** one `I.title(state)` table with the same rule as the panel header.
  - I-06 amber: "Almost ready" (`i06.title.almost` exists) and an amber Finish step.
  - I-08 busy: "Updating to 3.0.1…".
  - I-09 error: "Not fully removed".
  - I-01 upgrade: "Update WhyNot Cut".
  - I-03 done: "This computer is ready".
  - I-08 offline: "Update can't download".

**F-06 · P-01: the healthy Claude row buries the setup's primary (new).**
- **Where:** P-01 normal, focus, normal-live, stale; EN+AR 360 (measured).
- **Wrong:** "Set up my first client" starts at 870 css px (EN) and about 960 (AR). Most of that height is about 330 px of D-01 cost, the privacy line, "No telemetry" and the D-02 paragraph inside the Claude row. The row's own status ("Signed in") lands after 12 lines of text. Combined with F-01 ("All set" over "3 of 4 ready"), the first screenful says "done" and shows no next step.
- **Fix:**
  - The healthy row is title + "Signed in" + one line: "Pro or Max plan, paid to Anthropic · See plans · What Claude sees".
  - The D-01/D-02/privacy text goes in a disclosure ("Cost and privacy") or in P-22.
  - The D-01 and D-02 words stay as approved; only where they sit changes.
  - Target: the primary inside the first 600 px at 360.

**F-07 · Paused and running are still swapped in four places (R2 P1-2 residual, one partly new).**
- **Where:**
  - A-03 probe: a running check drawn with the amber *pause* icon (`one("probe")` passes `paused=true`);
  - A-04 no-claude: a spinning "Wait for QC" and "Claude is fixing it";
  - A-02 no-claude: a claims-review spinner and a "Waiting" chip;
  - P-08 offline/error/no-claude: a step-6 spinner (`head()` default "run");
  - A-04 offline: all 6 frames turn amber "Out of date".
- **Fix:** one rule in `M.stages` / `M.steps`. Use the busy spinner only when the service is running and the step is active. When the service is off or Claude is signed out, show `paused` with "Paused · {reason}". Keep the last QC verdicts greyed when offline, never "Out of date". On A-04 no-claude the main action is "Sign in to Claude", and "Wait for QC" is disabled with a reason, without a spinner.

**F-08 · One condition, several kinds (R2 P1-3 residual).**
- **Where:**
  - P-11 update: one Premiere restart drawn as an amber stale card *and* a red "Restart Premiere once to finish installing" card, with two Check again buttons and a red header;
  - P-13 error: pill "service not responding", card "Couldn't read the open project";
  - P-08 stale: one missing frame shown with a violet info icon, an amber chip and an amber tile;
  - "Adobe didn't install the panel": pink on I-04, amber on I-07, red on I-06;
  - P-02 restart-once red vs stale amber.
- **Fix:** add `restart_needed`, `panel_not_installed` and `frame_missing` to `M.COND`, each with one kind, icon and verb. Pills, notices and rows read only from `M.COND`. Merge the two P-11 restart cards into one.

**F-09 · Arabic bidi leftovers in values (R2 P1-4 residual).**
- **Where (AR):**
  - I-02 arabic/long/win and I-03 win: the path field reads `.whynot-cut/محمد عبد الرحمن/Users/` (segments reversed), and drive letters show as «:D» / «:C»;
  - A-03 normal/focus/probe/no-claude 280–480: «في 25.4 After Effects» (the version is outside the run, and wraps alone at 280/300);
  - P-10 long: «126 /dLmg»;
  - P-15 sync-done/error: "Sahha_C0239 - Synced" splits, so the hyphen jumps, and «Cam / 3 – C0007.mp4» breaks.
- **Fix:**
  - The installer uses the panel's `txt()` / `M.path` (whole path as one LTR isolate, drive colon inside, `text-align:left`).
  - Substitute `{version}` before Latin isolation, so "After Effects 25.4" is one `nb` run.
  - Units and values ("126 mg/dL") go through `M.ltr`.
  - File and sequence names use `M.mid` with `nowrap`.

**F-10 · P-19 has two violet fills (new finding; my R2 audit missed it).**
- **Where:** P-19 selected, focus, long; EN+AR, all widths (viewed at EN 360).
- **Wrong:** the selected template tile is a solid deep-violet fill, and "Use this template ⌘↵" is the violet primary. The audit counts only #5400FB, so the "one violet" self-check passes.
- **Fix:** selected tile = the neutral card + a 2 px violet border + the "Selected" check chip. Count every primary-family fill (#5400FB, #4800D8, #6A1FFF) in `selfCheckExtras` `violet`.

**F-11 · A-04: "Open anyway" outranks the rule it bypasses (new).**
- **Where:** A-04 normal, focus, long, no-claude; EN+AR.
- **Wrong:** "Open project turns on when the quality check passes." sits right above a full-width, enabled "Open anyway". That is the largest control on screen, bigger than Re-render.
- **Fix:** make "Open anyway" a ghost link under the hint ("Open without the check"). Re-render stays the secondary button and "Wait for QC" stays disabled with its reason.

**F-12 · P-03 Home: the week line breaks in every state (new).**
- **Where:** P-03, every state with stats; EN+AR 300/360/480 (viewed EN stale 360, AR normal 300).
- **Wrong:** "This week ·" ends its own line, and "Sahha Clinic" drops to the next one, indented by a space. It happens even at 480, so this is a layout break, not a wrap: `home.week.scope` sits in an `m-row` with the name as a separate flex child.
- **Fix:** one text run "This week · Sahha Clinic" with the name ellipsised (`min-width:0`). Or put the scope as an eyebrow line of its own.

**F-13 · P-08: the frames read as more failures than there are (new).**
- **Where:** P-08 normal, focus, aspect-4x5, fixing, error, offline, no-claude, long; plus stale and success.
- **Wrong:**
  - The footnote "Fix this asks Claude for a new version…" carries a red ✕ icon, so it reads as a second failure.
  - In stale and success, a *passing* tile is titled "Caption runs past the safe area" with a green Pass under it.
- **Fix:**
  - The footnote becomes helper text with a muted info icon.
  - Tile title = the element and time ("Caption · 00:00:14:08"). The defect text shows only while the tile fails.

**F-14 · Installer counts and offline state contradict themselves (new).**
- **Where:**
  - I-03 error/offline/nosignin/success, EN+AR: the "Ready" chip counts don't match the green rows (success 7 vs 6, error 5 vs 3, offline 4 vs 3, nosignin 6 vs 4);
  - I-01 offline: a green "Installs without internet", while I-03 offline blocks ("only the full offline download can install");
  - I-03 offline files the blocker under the amber "Good to know".
- **Fix:**
  - Compute the chips from the rows.
  - I-01 offline becomes an info notice that names the offline installer.
  - A blocking row is never "Good to know".

### P2

**F-15 · D-01 bracket and D-02 quotes in Arabic: correct, but they read awkwardly for a bilingual eye (asked directly).**
- **Measured:** P-01, P-12 and P-22 at 300/360/480; I-05 at 760/640.
- **What renders:**
  - **The brackets are a correct bidi pair.** The opener before "Pro" resolves RTL and draws as ")" immediately right of "Pro". The closer draws as "(" left of «للتاني». The full stop sits outside. Read right to left this is «… لـ Anthropic (Pro بيبدأ … للتاني).», which is right for an Arabic reader.
  - **What reads wrong:**
    - At 300/360 the visual run is "Pro) Anthropic لـ". At 480 (and I-05 760), "Pro)" ends or starts a line.
    - Any reader who scans Latin left to right sees "Pro)" as a *closing* bracket, so the parenthetical looks broken.
    - At 300 it also splits «20 / دولار».
  - **The D-02 quotes sit correctly** around one LTR isolate and never break. They are straight ASCII quotes, while every other Arabic quote in the UI is «…».
- **Fix:** D-01 is locked text, so this is Yunus's call.
  - Option 1: open the bracket on an Arabic word, «(اشتراك Pro بيبدأ من 20 دولار…)». Then the opener never touches a Latin word.
  - Option 2, keeping the words: bind «(Pro بيبدأ» and «20 دولار» with no-break spaces, so "(Pro" can never sit at a line end alone.
  - Quote D-02 as «Help improve our AI models».

**F-16 · Blocking or main actions disabled without a reason.**
- **Where:** P-13 offline and error, P-18 offline, A-02 offline, P-12 empty, P-03 error (EN+AR).
- **Fix:** every disabled main action carries one reason line, the same component as "Restart Premiere first." Examples: "Start WhyNot Cut first.", "Pick a task first."

**F-17 · Mid-token breaks and orphans in `long` and 300.**
- **Where:**
  - "C0239_reel_ / v3" (P-06), "C0239_interview_ / final_v2" (P-07, P-03 AR, P-11 AR);
  - "seque/nce_for_reels" (P-14, P-18, P-20);
  - "IBM Plex / Sans Arabic" (A-03);
  - "· estimate" alone on a line (P-04, P-06, P-12, P-13, P-15, P-17, P-20);
  - «ما / اتسطّبش» (I-07 AR 640);
  - «Premiere Pro و / After Effects» (I-03 AR).
- **Fix:**
  - `M.mid` with `nowrap` for every file, sequence and font name;
  - a no-break space before "· estimate", after «ما» and after «و» before a Latin word (as was done for «لـ»).

**F-18 · I-07 nointernet AR 640: the second button overflows the card by about 10 px.**
- **Fix:** let the row wrap, or shorten it to «النسخة اللي من غير نت».

**F-19 · ✕ on blocking notices (R2 P2-14 residual).**
- **Where:** P-08 stale, P-14 unsaved/stale, P-16 stale, A-04 stale.
- **Fix:** `M.notice` drops the ✕ whenever its button is the screen's only fix, or the main action is disabled.

**F-20 · P-01 stale: "Try the sample clip" stays live while the main action is disabled.**
- **Fix:** `stalePass()` also disables secondary verbs that need the host.

**F-21 · Backed-up rebuild confirms keep ⌘↵ on the overwrite.**
- **Where:** P-09 confirm, A-03 edited-confirm.
- **Wrong:** "Rebuild ⌘↵" replaces the editor's own timeline changes. A backup exists, so this is not a danger action, but a habitual ⌘↵ still discards work.
- **Fix:** in any confirm, the keycap goes on the safe button. Rebuild needs a click.

**F-22 · Hierarchy after success.**
- **Where:** P-20 normal (no primary at all); P-17 normal (the full-width grey Undo card is bigger than the violet Done).
- **Fix:**
  - P-20: a violet "Done" (back to Tools).
  - P-17: the Undo button goes to auto width, start-aligned.

**F-23 · 280 px header (A-01..A-04).**
- **Wrong:** the Needs-you badge shrinks to a bare pink "1 ›" or "3 ›", and the language switch shows one glyph. The A-01 "Plan approved" pill pushes "After Effects 25.4" to its own line. Otherwise the 280 fit is clean: the audit found 0 truncation and 0 overflow at 280 in every state.
- **Fix:** at 280, drop the chevron, not the label ("Needs you 1"). Put the A-01 pill on its own row.

**F-24 · Arabic copy slips after D-08 (native writer).**
- **Where:**
  - «خدمة WhyNot Cut محتاج تحديث» (P-02 engine-older: «محتاجة»);
  - «فمش هينفع ترجع في الخطوة دي» (P-09 confirm-nobackup: "can't be undone" is «مش هينفع ترجع عنها»);
  - «و2 لقطة B-roll» («ولقطتين»);
  - «1 من 10 خطوة» («خطوات»);
  - P-22 quotes the field as «اتأكدت مع» while the field says «اتأكدت مع مين؟» and the record says «أكّدها»;
  - the A-02 success date "13 Oct 2026" uses the English month («13 أكتوبر 2026»).
- **Fix:** apply the drafts, then the native-writer pass.

**F-25 · Installer small drifts.**
- **Where:**
  - I-05 and I-08 offline: the notice's Check again shows "⌘↵", while every other installer primary shows "↵";
  - I-08 normal: Update uses the `rotate-ccw` icon, the same as "Go back to 2.2.1";
  - I-09 confirm: the red card sits *above* the H1;
  - I-09 empty: an all-green rail although nothing ran.
- **Fix:**
  - Pass the installer keycap through `M.notice`.
  - Update gets `download`.
  - The confirm goes below the title.
  - The I-09 empty rail is neutral.

## 4. What changed for the better (for the record)

- **The confirm pattern is now one component.** It looks the same in P-09, P-16, P-21, I-04 and I-09: a red fill with dark text at 6.1:1, no keycap, the safe button focused with Esc. It is the strongest piece of the system.
- **Stale is solved by one shell rule.** It holds on every screen except where work is running (F-02).
- **Arabic structure is right everywhere checked:**
  - mirrored layout;
  - progress and sliders fill from the right;
  - chevrons point to the reading end;
  - media previews and waveforms are not mirrored;
  - timecodes stay LTR;
  - the lockup is a fixed LTR unit.
- **The measured baselines hold:**
  - 0 controls off radius 8 or the 2 px border;
  - 0 hit targets under 32 px;
  - 0 contrast fails (apart from the mock macOS dialog);
  - 0 "engine" in the UI;
  - 0 truncation at 280.

## 5. Suggested order for the next pass

1. **Shared work in `mockup.js`:** F-01 (`liveState` + self-check), F-02 (stale over running work), F-07 (one stage rule), F-08 (`M.COND` entries), F-04/F-09 (URL and version runs), F-10 (violet family in the self-check), F-03 (one soon-line block).
2. **Group work:** P-01 row (F-06), P-03 week line (F-12), P-08 tiles (F-13), A-04 Open anyway (F-11), installer titles and counts (F-05, F-14).
3. **Re-render all 35 screens** so every PNG is newer than aa36352, then re-run this audit (the scripts are in the scratchpad `ed3r3/`).
