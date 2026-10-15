# R2 fix list: round-2 reviews of the 35 panel mockups (triage, SHARED bucket done, group work listed)

Author: the shared-layer worker of the R2 pass (AI; not a human designer's sign-off). Date 2026-10-15. Branch release/3.0.
Inputs, read in full: `docs/design/reviews/ED3-r2-designer.md` (ids `D-P0-1` ... `D-P2-16`), `ED3-r2-first-time-editor.md` (`E-P1-01` ... `E-P2-19`),
`G2-r2-agency-owner.md` (`G-F-01` ... `G-F-18`, and the five pricing objections of its section 4 as `G-Q1` ... `G-Q5`), plus `docs/design/direction.md`.

**Status words:** DONE = changed and rendered in this commit (all 35 screens re-rendered, the page self-checks pass); verified = measured or viewed.
**Not checked:** real UXP or CEP paint, hover and pressed states, motion, Windows keycaps in the sheets (`?os=win` is supported), real pinned-bar scrolling, NBSP in Arabic time phrases. Arabic copy is draft until a native writer approves it (D-08).

## 0. Counts and how to read this file

Every finding id sits in exactly ONE bucket (its **lead** bucket). Duplicates across the three reviewers are merged into one row with several ids.
Rule for the lead bucket: a finding is in SHARED when anything of it is done now in `mockup.js` / `mockup.css` / `strings.js` / P-01 / P-03 / P-07 (the rest of that finding is then listed as a **group follow-up** on the same row); otherwise it is in the group bucket that owns its screens, or in OWNER DECISION or PRODUCT BACKLOG.

| Bucket | Findings (ids) | Rows |
|---|---|---|
| 1 SHARED | 44 | 34 |
| 2 PREMIERE-CORE | 8 | 8 |
| 3 TOOLS-AE | 7 | 7 |
| 4 INSTALLER | 5 | 5 |
| 5 OWNER DECISION | 11 | 7 |
| 6 PRODUCT BACKLOG | 4 | 4 |
| **Total** | **79** | 65 |

Total ids: 79 = designer 31 + editor 25 + owner 18 + pricing objections 5.

**Pick-up index for the group workers** (each worker: do sections 2 / 3 / 4 below, then the follow-ups of section 1 listed for the group, then the group's screens named in sections 5 and 6):

- **premiere-core (P-02, P-04 to P-06, P-08 to P-12, P-21, P-22).** Lead rows: 8. Follow-ups in other rows: D-P0-1, G-F-06; D-P0-3; D-P1-2; D-P1-3; D-P1-4; D-P1-6, G-F-10; D-P1-7, E-P2-08, G-F-13; D-P1-8, E-P2-15; D-P1-9, E-P2-02, E-P2-03; D-P1-11; D-P1-12, G-F-14; D-P2-1; D-P2-4; D-P2-5; D-P2-6; D-P2-7; D-P2-8, G-F-03, E-P2-06; D-P2-9; D-P2-14; E-P1-03; E-P2-19; G-F-05; G-F-17; D-P1-10; E-P2-01; G-F-12; G-F-18; G-F-07; G-F-08; G-F-09, G-Q4.
- **tools-ae (P-13 to P-20, A-01 to A-04).** Lead rows: 7. Follow-ups in other rows: D-P0-3; D-P1-2; D-P1-3; D-P1-4; D-P1-6, G-F-10; D-P1-7, E-P2-08, G-F-13; D-P1-8, E-P2-15; D-P1-9, E-P2-02, E-P2-03; D-P1-11; D-P2-2; D-P2-4; D-P2-5; D-P2-6; D-P2-7; D-P2-8, G-F-03, E-P2-06; D-P2-14; E-P2-19.
- **installer (I-01 to I-09).** Lead rows: 5. Follow-ups in other rows: D-P0-3; D-P1-4; D-P1-5; D-P1-6, G-F-10; D-P1-9, E-P2-02, E-P2-03; D-P1-12, G-F-14; D-P2-1; D-P2-8, G-F-03, E-P2-06; D-P2-9; D-P2-10; G-F-16; G-F-04; G-F-09, G-Q4.

---

## 1. SHARED bucket (done now)

What changed, in `adobe/panel-ui/design/`: `mockup.js` (runtime and components), `mockup.css`, `strings.js`, `screens/P-01`, `P-03`, `P-07`, `_build/check_css.py`, `_build/render_all.py`, and two mechanical group edits (`js/tools-ae.js` post-mount keycap, `js/installer.js` Return keycap guard, lockup wrap and the self-check fields). Group screens re-rendered unchanged apart from what the shell now does for them.

### 1.1 Findings in this bucket

| Id | Screens | What | Done now | Group follow-up |
|---|---|---|---|---|
| D-P0-1, G-F-06 | 25 screens, 53 states (list in ED3-r2-designer P0-1), long states | Header status follows the worst live state; "All set" only when nothing is open. | DONE. mockup.js statusRow()/liveState(): an error card or danger confirm = red "Needs attention"; a restart notice = amber "{host} needs a restart"; any other warn card = amber "Needs a look"; Needs-you the only reason = no status pill (the badge says it); view.status {kind,text} names a state, view.pillx / noCollapse keep the three pills; a notice may carry its own short text (M.notice o.pill). Page self-check statuslie=0 fails render_all. | **PC** P-11 sets matching pills per card (view.status or pills) and P-10 normal drops its all-ok pillx so it collapses instead of "running ready" at 300 |
| D-P0-3 | P-09 and P-16 confirm-nobackup, I-09 normal | A danger or destructive action never binds Mod+Enter and never shows the primary keycap; in a confirm Return lands on the safe button. | DONE. M.btn refuses o.kbd on kind danger or o.destructive; M.dialog (danger) puts no keycap on the red button, focuses "Keep" and gives it Esc; keys() sends Mod+Enter to the safe button under a danger dialog; self-check dangerkbd; tools-ae.js post-mount keycap skips danger/destructive; installer I.btn refuses the Return keycap on danger/destructive. | **PC** PC.dialog keep button focused by default (use M.dialog); P-09, P-21 remove-confirm (red Remove, no keycap) ; **TA** TA.dialog same; P-16 confirm-nobackup ; **IN** I-09 first screen = neutral "Continue" leading to the red confirm, Uninstall carries destructive:true |
| D-P1-1 | P-01, P-03, P-05, P-06, P-13, A-01 stale | Under a restart notice the main action is off with the reason and the notice's "Check again" takes the violet. | DONE. M.stale() and shell stalePass() on EVERY screen (matches the stale strings): the notice button becomes primary with the keycap, every other primary / verb primary is disabled, the reason "Restart Premiere first." replaces the verb subline or sits under the button. | none |
| D-P1-2 | P-06 offline, A-04 stale, A-03 no-claude, P-08 stale, P-19 no-text | Paused or blocked work is never drawn as running. | DONE (helpers). M.status "paused" (amber circle-pause, no spinner), M.stages kind paused, M.progress(pct,{paused:true}) = solid amber fill, M.tile fail/reason. | **PC** P-06 offline = "Paused at 23 of 47, resumes when the service is back", amber icon, no spinner, trust line hidden; P-08 stale: a missing frame counts as "missing", not "fail" ; **TA** A-04 stale: no live spinners, drop the old Fix chip; A-03 no-claude: the Arabic-check card stops spinning; P-19 no-text: the failing template tile gets the error border and its reason (M.tile fail + reason) |
| D-P1-3 | P-01, P-02, P-03, P-05, P-13 to P-20 | One condition, one kind, one icon, one name. | DONE. M.COND map; PILL engine.noanswer is now error (matches the red notice); P-01 signed-out row, step bar and pill are amber, only "not installed" is red; P-03/P-07 no-Claude use M.noClaude. | **PC** P-02 restart-once card kind follows M.COND (host unlinked = error, not amber); P-05 error now consistent ; **TA** P-13 to P-20 no-Claude: pill, notice and button all say "Claude isn't signed in" (not "isn't open") and use M.noClaude |
| D-P1-4 | header row 2 (AR long), tools/AE file names, paths, I-06 menu path | Arabic bidi: every Latin, mono, path, version and menu run is an LTR isolate; ellipsis per run; client first. | DONE. Header row 2: the client name is an LTR run cut at its END, the item code keeps its width; txt() isolates paths and drive letters (m-path); M.path (wraps after a separator), M.mid (middle ellipsis), M.lri (LRI/PDI for aria and plain text), M.menuPath (one LTR chip, chevrons never mirror). | **PC** paths in P-22 and P-09 backup names via M.path ; **TA** tools/AE file names (div.t-mono) go through M.path or <bdi>; paths no-wrap with M.mid ; **IN** I-06 menu path = M.menuPath; log and file paths via M.path |
| D-P1-5 | every AR header and installer | The logo lockup never mirrors (direction §9). | DONE. m-lockup: monogram + 8 px + wordmark is one fixed LTR unit that moves to the right edge as a whole; the self-check mono=right still holds; installer header (js/installer.js) wrapped the same way, mechanical. | **IN** check I-01 to I-09 AR heads after the re-render |
| D-P1-6, G-F-10 | P-03 no-claude-missing, P-11 normal/panel, I-03 offline, I-05 error, I-07 nointernet/manifest, P-20 offline, A-01 offline, P-21 skipped | The fix button fixes THAT cause; one named fix per card; never a script URL. | DONE for P-03 (missing Claude says "Install Claude first", the button is "Install Claude"); shared M.offline / M.noClaude / M.stale use one label each. | **PC** P-11 one cause and one button per fault ("Repair settings (keeps your clients)", "Update the panel", "Reload panel", "Show what to allow"), merge faults whose fix is the same; P-21 skipped: Download all disabled with too little space + "Choose another drive" ; **TA** P-20 offline: Try again after Start; A-01 offline: drop the second notice or give it a button ; **IN** I-05 error shows the install path first ("Install Claude" / "Open claude.ai/download"), I-03 offline and I-07 nointernet get "Get the offline installer", I-07 manifest: "Open download page" (never a shell-script URL) |
| D-P1-7, E-P2-08, G-F-13 | P-03 hero, A-02 storyboard, A-04 frames, P-08 thumbs | The media is a real 9:16 tile with a fallback glyph that is not a person; failed frames show the safe area. | DONE (component + P-03). M.media / M.poster: 9:16, #0D0D0D well, clapperboard glyph, 36 x 64 (48 x 84 at 480), safe-area outline (o.safe) and offending box (.m-media-bad); M.tile fail. | **PC** P-08 mock real-looking frames, the failed frame shows the safe-area box, sort failed frames first, the failed tile gets its own "Fix this" ; **TA** A-04 9:16 frames, no empty black box, while QC is open the primary is "Wait for QC" with "Open anyway" secondary (G-F-13); A-02 storyboard frames with content |
| D-P1-8, E-P2-15 | P-15, P-17, P-08, P-01 success | The primary after an action is the safe next step, never Undo. | DONE for P-01 (success = "You're ready" + violet "Go to Home"). | **PC** P-08 normal: sort failed first and the fail's fix takes the violet; P-08 success advances to step 7 with "Open project" ; **TA** P-15 and P-17 "Done"/"Show in project" is the violet, Undo is secondary with no keycap |
| D-P1-9, E-P2-02, E-P2-03 | all screens, P-12 ready, I-05, I-06 | One Arabic word list; no glued strings. | DONE in strings.js: «جرّب تاني», «افحص تاني», «تراجع», «دوس», «شباك», «نموذج», «المتكلم», «إنت», «ريندر»; shared strings migrated. | **PC** replace «حاول تاني» (19 uses), «موديل», «رندر», «اضغط», «نافذة»; P-12 «سيبك منه» -> «ماتطبّقش»; «سيب مشروعي» -> «خلّي مشروعي زي ما هو»; «متحفوظ» typo ; **TA** «جرّب تاني» is canonical; replace «اتأكد تاني» with «افحص تاني», «رجّعهم» with «تراجع», «ريندر/رندر» one spelling ; **IN** glued «سطّبClaude» (I-05) and «افتحClaude» (I-06): wrap the Latin name with M.t / <bdi>; same list |
| D-P1-11 | A-02 empty, A-03, P-10 long, P-07 no-claude | The Needs-you badge is the count of actionable items from one source; empty and loading are 0; a blocked approval still counts. | DONE for P-07 (loading 0, no-claude and success-later 1). | **PC** P-10 long: header and list show the same number ; **TA** A-02 empty = 0; A-03 does not count the "nothing to do" card (3, not 4) |
| D-P1-12, G-F-14 | I-01, I-02, no-Claude cards on P-01, P-03, P-07, P-08, P-11, P-12, P-22 | Trust copy is scoped and the no-Claude card is short. | DONE for P-01, P-03, P-07: no-Claude card = one sentence + one button + "What Claude sees" link (M.noClaude); the account, cost and privacy lines show only on the healthy P-01 row. | **PC** P-08, P-11, P-12, P-22 no-Claude cards use M.noClaude ; **IN** I-01 "Setup sends nothing from your computer" (G-F-14), offline state: "Installs without internet; Claude and sign-in need it later"; I-02 "Don't ask me each time Claude uses WhyNot Cut" UNTICKED by default with one line on what it skips |
| D-P2-1 | pc-row, m-actionbar, i-bar, pc-model, pc-diff, m-check, i-step, pc-step | Paddings count the 1 px divider (11 + 1 = 12). | DONE in mockup.css: m-check, m-flag, m-actionbar; new m-lrow / m-lrow-dense / m-stage follow the rule. | **PC** pc-row, pc-model, pc-diff, pc-step -> padding 12 with 11 + 1 on the second row, or move to M.listrow / M.stages ; **IN** i-bar, i-step (8 + border -> 7 + 1) |
| D-P2-2 | P-14 and A-04 stat numbers, pills, AR links | Type roles on the scale. | DONE: --mk-type-stat (Inter 600 20/28, AR 20/32) and .t-stat; the header pill is documented as its own role (Inter 400 11/16, AR 12/20). | **TA** ta-num (15/20 and 20/28) -> t-stat |
| D-P2-3 | P-07 .m-linkbtn | Hit target 32 px. | DONE: .m-linkbtn min-height 32. | none |
| D-P2-4 | P-03, P-07, A-02, P-08, A-01, P-01, P-04, P-05, P-12 | waiting = the pink Needs-you dot; warn only for problems. | DONE: STATUS "waiting"; M.steps turns warn + a wait segment into waiting; the wait segment is the accent colour. | **PC** P-04/P-05 "In progress" chips, P-12 "Kept your original line" chip: neutral or info, not amber ; **TA** A-01 info circle -> waiting; A-02 status icon |
| D-P2-5 | P-04, P-02, TA.back, core back | One back affordance with the chevron; Back + title first, then the notice slot. | DONE: M.back(label). | **PC** PC.back (arrow) -> M.back; P-04 puts Back + title above the notice (P-02 already does) ; **TA** TA.back -> M.back |
| D-P2-6 | P-14, P-16, A-03, P-09, P-21 | Confirm bullets are neutral 4 px dots; Remove is danger with no keycap. | DONE: M.bullet, M.dialog. | **PC** P-21 remove-confirm: red Remove, no keycap, no violet; P-09 bullets ; **TA** P-14, P-16, A-03 dashed-pending icons -> M.bullet |
| D-P2-7 | P-07, A-02, P-05, P-21, P-14, P-16 | Never two competing fixes. | DONE for P-07 error (the notice's Try again is the violet, Approve is off with "Try again first"). | **PC** P-05 error, P-21 error: bar/row button disabled while the notice is up ; **TA** A-02 error; P-14 and P-16 stale: one "Scan again" only |
| D-P2-8, G-F-03, E-P2-06 | P-03, P-04, P-07, P-13, P-14, P-15, P-17, P-20, A-04, P-12, P-22, I-03, I-04, I-08 | Mock data agrees with itself; every time-saved figure comes from one formula, says "estimate", is never below 0. | DONE for P-07 stale (map 0:48, "48 s reel", diff "48 s instead of 52 s"), P-07 saved line in the future tense, P-03 Home line states its scope (client, this week), links "How is this worked out?" (G-F-03). Canonical numbers: table in section 1.2. | **PC** P-04 rows use the canonical numbers; P-12 "about 3 min" and always end with "estimate"; P-22 "How is this worked out?" formula, shows "Set by your agency" ; **TA** P-13 "about 1 h 10 min" from tools; P-15 (112 removed vs 4 kept; 7 of 8 with 2 out), P-14 (4 bins add up), P-17 (18 vs 20/24; Hush "about 4 min"), P-20, A-04 say "· estimate" ; **IN** I-03 6.0 vs 3.6 GB, I-08 success footer 3.0.1 (not 3.0.0), I-04 macOS prompt names the clients folder, not Documents |
| D-P2-9 | P-05 file names, I-01 "Genuine Setup from The Why / Not", P-03 | No orphans or mid-token breaks. | DONE: nbLast() binds the last two short words of every string with a no-break space. | **PC** P-05 break file names only at "_" with a middle ellipsis (M.mid) ; **IN** "The Why Not" inside one no-break run |
| D-P2-10 | keycaps, times, I-08 versions | Glyphs: no "6 :40", no mono "O". | DONE: .m-kbd in Inter; M.mono pulls the colon of a pure time in. | **IN** I-08 version digits (Syne old-style "3.o.ı") set in Inter (.lat / .code) |
| D-P2-11 | 300 px header | Needs-you keeps its label at 300. | DONE: at 300 the language switch is one 32 px control showing the language you would switch TO, the badge keeps "Needs you"; long "99+" fits (checked). | none |
| D-P2-14 | P-02 link-off/claude-missing, P-18 errors | No close button on a blocking notice. | DONE in M.notice: an error notice (or dismiss:false) has no ✕. | **PC** PC.notice (own builder) -> M.notice, P-02 ; **TA** P-18 follows M.notice automatically |
| D-P2-15 | _build/check_css.py | The checker scans css/, js/, strings/ and @font-face. | DONE: scans css/*.css, js/*.js, screens, strings values ("engine", "Claude Code", link allowlist), @font-face outside mockup.css. 0 hits. | none |
| E-P1-01 | P-03, header on every screen | Client or video can be switched. | DONE: header row 2 is one control "client · item" with a chevron and aria-label "Change client or video"; Home has "Change video" under the hero. | none |
| E-P1-03 | P-02, P-05, P-06, P-12, pills | An internet-down state exists. | DONE (helper): pill "no internet" (view.pills {claude:"offline"}) and M.noNet() ("No internet. Claude needs it to make the plan." + what keeps working, no button). | **PC** P-02 add the state; P-05 failed sub when offline: "The internet dropped, so Claude didn't get the request. Nothing started; we'll send it again when the internet is back."; P-06 and P-12 use M.noNet |
| E-P1-04 | P-07 stale | Every number on the card comes from the new plan. | DONE: D.plan2, map end 0:48, "48 s reel", diff "48 s instead of 52 s · 7 cuts instead of 6 · 1 B-roll clip instead of 2". | none |
| E-P2-12 | P-01, P-03 Claude signed out | The text and the buttons agree. | DONE: the hint no longer says "press Check again": "WhyNot Cut notices as soon as you sign in"; P-01 keeps its Check again row. | none |
| E-P2-13 | P-07 flagged | One tick per flagged line. | DONE: each flagged line has its own tick; Approve needs every line. | none |
| E-P2-19 | A-02 normal, P-01 | No licence jargon; one verb for what Claude does. | DONE for P-01 («بيخطّط المونتاج»). | **PC** P-02 already says «بيخطّط»; keep ; **TA** A-02 "6 free icons, we may use them"; "Music: Calm Pulse. Credit the artist in the post (it's in the publish pack)"; number row "2 (twice in a row) · 00:14"; use «بيخطّط المونتاج» everywhere |
| G-F-05 | P-07, P-22 | The approval record is audit-grade. | DONE in P-07: "Confirmed with" is required (not optional), shown with a line saying why; the approved card has "Export sign-off". | **PC** P-22 per-client setting "Require 'Confirmed with' for medical and religious clients" (default on), approver name locked after first setup with "Changed by…" log line; P-07 already shows the result. Backlog B-01. |
| G-F-17 | P-03, P-22 | Reels this week and average turnaround next to the minutes. | DONE on Home ("Average turnaround: 6 h from raw to approved"). | **PC** P-04 client rows may show turnaround; P-22 "Export my week" includes both. Backlog B-03. |

### 1.2 Canonical mock numbers (one source of truth; owner F-03, designer P2-8, editor P2-06)

Every group screen uses these. Every time-saved line ends with "estimate" («تقدير»), is never below 0 and never above raw time x rate. P-22 shows the formula per job type and "How is this worked out?" opens it.

| Where | Value | Note |
|---|---|---|
| Home (P-03), scope "This week · Sahha Clinic" | about 4 h 30 min saved, 7 reels, average turnaround 6 h (raw to approved) | `MOCK_DATA.week` {items 7, est_saved_min 270}; = the Sahha row of P-04 |
| P-04 picker rows, this week | Sahha Clinic 4 h 30 (270 min) · Nour Dental 2 h 50 (170) · Dr. Hesham Podcast 3 h (180) | the three add up to 10 h 20 (620 min), stated as "All clients, this week" |
| P-13 tools hub, this week | about 1 h 10 min from the three tools | Tidy 25 + Hush 4 + Kalam 40 = 69 min, part of the 270 above |
| P-06 / P-07 reel | 6:40 raw, 52 s reel, 45 min (formula: raw min x 9 - 15) | P-07 says "will save" (future tense); stale plan: 48 s reel, 7 cuts, 1 B-roll |
| Hush (P-17, P-20) | 24 pauses, 14 s of silence in a 1:12 clip: about 4 min | by hand 3 to 5 min |
| P-12 | 3 typo fixes: about 3 min | not 10 min |
| Tidy (P-15) | 214 files sorted, about 25 min; counts add up (removed + kept = total) | P-14 4 bins add up to 214 |
| A-04 | about 3 h of motion work, "estimate" | |
| Installer (I-03) | one size per item that adds up to the total | I-08 success footer 3.0.1 |

### 1.3 New shared API (group workers: use it, delete your copy when a screen is moved)

| Shared (new) | Replaces | Notes |
|---|---|---|
| `M.slot(html)` | `PC.slot`/`TA.slot`/local `slot()` | notice + the 16 px reserved gap |
| `M.notice(kind, text, {btn:{disabled,busy,primary,kbd}, extra, pill, dismiss})` | `PC.notice`, `TA` notices | error notices and `dismiss:false` have no close button |
| `M.offline()`, `M.noClaude('signed_out'|'missing', o)`, `M.stale()`, `M.noNet()` | `TA.offline/noClaude/stale`, `PC.noClaude`, inline core notices | one label each: "Start WhyNot Cut", "Sign in to Claude" / "Install Claude", "Check again"; stale switches the screen's other primaries off (shell) |
| `M.dialog(o)` + `.m-dialog` | `PC.dialog` (`.pc-dialog`), `TA.dialog` (`.ta-dialog`) | danger = no backup and not reversible: red button, NO keycap, "Keep" focused with Esc |
| `M.radio`, `M.segmented`, `M.toggle`, `M.select`, `M.slider`, `M.sechead` | `PC.radio`, `TA.radio/seg/tog/select/slider/sechead` | tools-ae classes `ta-*` stay until moved |
| `M.tile(o)` + `M.media(o)` / `M.poster` | `.pc-tile`, `.ta-tile`, `.pc-thumb*`, `.ta-frame`, `.ta-th*`, `.m-poster` | 9:16, clapperboard glyph, `safe` outline, `fail` + `reason` |
| `M.listrow`, `M.stages`, `M.bullet` | `.pc-row`, `.pc-step`, `.ta-stage`, `.ta-bullet`, `.pc-bullet` | padding counts the divider |
| `M.back`, `M.trust`, `M.saved`, `M.logline` | `PC.back`/`TA.back`, `PC.trust/saved`, `TA.trust/saved`, `PC.logBody` | chevron back; ok-green icons; log lines wrap |
| `M.path`, `M.mid`, `M.lri`, `M.menuPath`, `M.mono` (time) | `PC.monoWrap`, `I.path`, `I.monoBox`, `TA.mono` | bidi-safe runs |
| `M.status(kind)` kinds `waiting`, `paused`; `M.COND`; `M.steps` | local icon choices | one status model |
| `view.status`, `view.pillx`, `view.noCollapse`, `M.notice o.pill` | `PC.mount` pill patch | `pillx` still overrides |
| `.t-stat`, `--mk-type-stat` | `.ta-num` | Inter 600 20/28 (AR 20/32) |
| Shared word list in `strings.js` (`action.retry`, `action.undo`, `action.check_again`, `action.start_app`, `action.install_guide`, `privacy.link`, `net.off`) | group copies | delete the group copies when the group moves |

Self-check fields added to every page (`<meta name="mock-check">`, failed by `render_all.py`): `statuslie` (All set over an open card or a Needs-you badge), `dangerkbd` (keycap on a danger or destructive button), `violet` (more than one live violet fill).

### 1.4 Spec notes to carry into direction.md (not edited here)

- Status model: add kinds `waiting` (pink dot, waiting for the person) and `paused` (amber pause) to §6 and §9; the header status is derived from the screen body (new rule).
- Type roles: add `stat` (Inter 600 20/28, AR 20/32) and `pill` (Inter 400 11/16, AR 12/20); keycaps are Inter 400 11/16.
- §3 anatomy: header row 2 is a control (client · item + chevron); the lockup is one fixed LTR unit (§9 clarified); at 300 px the language switch is one glyph.
- §12: error and blocking notices have no close button; a danger action never carries a keycap; Return in a confirm is the safe button.
- Timecodes stay mono; the colon is pulled in (`mo-c`) so a time never reads "6 :40".

---

## 2. PREMIERE-CORE

Screens: P-02, P-04, P-05, P-06, P-08 to P-12, P-21, P-22. A later worker does these; read the Arabic fixes as draft copy for the native writer.

### Lead rows

| Id | Screens | What | Exact fix | Also touches |
|---|---|---|---|---|
| E-P1-02 | P-06 running | Say what is safe while the sequence builds. | EN: "Claude is building the new sequence {seq}. You can work in any other sequence, but don't open {seq} until the build finishes." AR: «Claude بيبني السيكوينس الجديد {seq}. تقدر تشتغل في أي سيكوينس تاني عادي، بس ماتفتحش {seq} لحد ما البناء يخلص.» Under Cancel: "Cancel stops the build and removes the unfinished sequence. The plan and your approval are kept." (engine behaviour to confirm, B-07). | - |
| E-P1-05 | P-22 "Claude and AI buttons" | Editors see one default; the paid option is not offered to them. | Show only the default mode to editors; the other two under a collapsed "Advanced settings (for the owner)"; options named "Use the Claude that's open on my computer (no extra cost)", "Work with Claude closed, on my subscription", "API key (paid, from Anthropic)". Keep every cost/billing sentence as it is now, marked MOCK-VERIFY (D-01). | - |
| E-P2-09 | P-05 normal | The clip that will be edited is the clip the editor chose. | Each "New" row is a radio row; when the selection differs from the header the bar says "You'll edit C0241 (not C0239)". | - |
| E-P2-10 | P-06 steps | No two steps that sound the same. | Steps: "Export frames" -> "Quality check" -> "Ready for you"; done sub: "Built and checked. Open the project and carry on editing." | - |
| E-P2-11 | P-06 done | Opening the project is safe. | One line under "Open project": "Opens the new project in Premiere next to your work; it doesn't close anything." | - |
| E-P2-14 | P-12 ready | Review each change before applying. | A tick on every change (all ticked); button "Apply the ones I ticked ({n})". Backlog B-08. | - |
| E-P2-16 | P-09 confirm-nobackup | Say how much space to free. | "Free about {gb} so a backup copy can be saved." Keep "Build without a backup" as a red glass button below "Keep my project". | - |
| G-F-15 | P-22 time-saved rate | The rate cannot be edited by any editor to inflate numbers. | Show "Set by your agency" (read-only for editors); the editable field only in the owner-only file/section. Backlog B-10. | - |

### Follow-ups from the other rows (PC)

| From | Screens | Exact work |
|---|---|---|
| D-P0-1, G-F-06 (Shared) | 25 screens, 53 states (list in ED3-r2-designer P0-1), long states | P-11 sets matching pills per card (view.status or pills) and P-10 normal drops its all-ok pillx so it collapses instead of "running ready" at 300 |
| D-P0-3 (Shared) | P-09 and P-16 confirm-nobackup, I-09 normal | PC.dialog keep button focused by default (use M.dialog); P-09, P-21 remove-confirm (red Remove, no keycap) |
| D-P1-2 (Shared) | P-06 offline, A-04 stale, A-03 no-claude, P-08 stale, P-19 no-text | P-06 offline = "Paused at 23 of 47, resumes when the service is back", amber icon, no spinner, trust line hidden; P-08 stale: a missing frame counts as "missing", not "fail" |
| D-P1-3 (Shared) | P-01, P-02, P-03, P-05, P-13 to P-20 | P-02 restart-once card kind follows M.COND (host unlinked = error, not amber); P-05 error now consistent |
| D-P1-4 (Shared) | header row 2 (AR long), tools/AE file names, paths, I-06 menu path | paths in P-22 and P-09 backup names via M.path |
| D-P1-6, G-F-10 (Shared) | P-03 no-claude-missing, P-11 normal/panel, I-03 offline, I-05 error, I-07 nointernet/manifest, P-20 offline, A-01 offline, P-21 skipped | P-11 one cause and one button per fault ("Repair settings (keeps your clients)", "Update the panel", "Reload panel", "Show what to allow"), merge faults whose fix is the same; P-21 skipped: Download all disabled with too little space + "Choose another drive" |
| D-P1-7, E-P2-08, G-F-13 (Shared) | P-03 hero, A-02 storyboard, A-04 frames, P-08 thumbs | P-08 mock real-looking frames, the failed frame shows the safe-area box, sort failed frames first, the failed tile gets its own "Fix this" |
| D-P1-8, E-P2-15 (Shared) | P-15, P-17, P-08, P-01 success | P-08 normal: sort failed first and the fail's fix takes the violet; P-08 success advances to step 7 with "Open project" |
| D-P1-9, E-P2-02, E-P2-03 (Shared) | all screens, P-12 ready, I-05, I-06 | replace «حاول تاني» (19 uses), «موديل», «رندر», «اضغط», «نافذة»; P-12 «سيبك منه» -> «ماتطبّقش»; «سيب مشروعي» -> «خلّي مشروعي زي ما هو»; «متحفوظ» typo |
| D-P1-11 (Shared) | A-02 empty, A-03, P-10 long, P-07 no-claude | P-10 long: header and list show the same number |
| D-P1-12, G-F-14 (Shared) | I-01, I-02, no-Claude cards on P-01, P-03, P-07, P-08, P-11, P-12, P-22 | P-08, P-11, P-12, P-22 no-Claude cards use M.noClaude |
| D-P2-1 (Shared) | pc-row, m-actionbar, i-bar, pc-model, pc-diff, m-check, i-step, pc-step | pc-row, pc-model, pc-diff, pc-step -> padding 12 with 11 + 1 on the second row, or move to M.listrow / M.stages |
| D-P2-4 (Shared) | P-03, P-07, A-02, P-08, A-01, P-01, P-04, P-05, P-12 | P-04/P-05 "In progress" chips, P-12 "Kept your original line" chip: neutral or info, not amber |
| D-P2-5 (Shared) | P-04, P-02, TA.back, core back | PC.back (arrow) -> M.back; P-04 puts Back + title above the notice (P-02 already does) |
| D-P2-6 (Shared) | P-14, P-16, A-03, P-09, P-21 | P-21 remove-confirm: red Remove, no keycap, no violet; P-09 bullets |
| D-P2-7 (Shared) | P-07, A-02, P-05, P-21, P-14, P-16 | P-05 error, P-21 error: bar/row button disabled while the notice is up |
| D-P2-8, G-F-03, E-P2-06 (Shared) | P-03, P-04, P-07, P-13, P-14, P-15, P-17, P-20, A-04, P-12, P-22, I-03, I-04, I-08 | P-04 rows use the canonical numbers; P-12 "about 3 min" and always end with "estimate"; P-22 "How is this worked out?" formula, shows "Set by your agency" |
| D-P2-9 (Shared) | P-05 file names, I-01 "Genuine Setup from The Why / Not", P-03 | P-05 break file names only at "_" with a middle ellipsis (M.mid) |
| D-P2-14 (Shared) | P-02 link-off/claude-missing, P-18 errors | PC.notice (own builder) -> M.notice, P-02 |
| E-P1-03 (Shared) | P-02, P-05, P-06, P-12, pills | P-02 add the state; P-05 failed sub when offline: "The internet dropped, so Claude didn't get the request. Nothing started; we'll send it again when the internet is back."; P-06 and P-12 use M.noNet |
| E-P2-19 (Shared) | A-02 normal, P-01 | P-02 already says «بيخطّط»; keep |
| G-F-05 (Shared) | P-07, P-22 | P-22 per-client setting "Require 'Confirmed with' for medical and religious clients" (default on), approver name locked after first setup with "Changed by…" log line; P-07 already shows the result. Backlog B-01. |
| G-F-17 (Shared) | P-03, P-22 | P-04 client rows may show turnaround; P-22 "Export my week" includes both. Backlog B-03. |
| D-P1-10 (Installer) | I-01, I-04, I-06, I-07, I-08, I-09, P-22 support, P-11 link-refused | P-22 support text (no heartbeat, request ids, FAILED lines) and P-11 link-refused (no 'message too large') |
| E-P2-01 (Tools-Ae) | P-14, P-15, P-17, P-21, P-11 | P-21 and P-11 same rule |
| G-F-12 (Tools-Ae) | P-16, P-17 (+P-22 PC) | P-22 offers it only under "Advanced, not recommended". |
| G-F-18 (Tools-Ae) | A-04, P-08 (PC) | P-08 same chips |
| G-F-07 (Product Backlog) | P-03, P-04, P-13, P-22 | add the row and a success note "Saved to the client folder" |
| G-F-08 (Product Backlog) | P-04, P-05, P-07 | P-04, P-05 |
| G-F-09, G-Q4 (Owner Decision) | P-11, P-15, P-22, I-07 | P-22 Support block shows a MOCK-VERIFY slot; one click "Copy details and open support" replaces "copy them if support asks" |

## 3. TOOLS-AE

Screens: P-13 to P-20, A-01 to A-04. A later worker does these; read the Arabic fixes as draft copy for the native writer.

### Lead rows

| Id | Screens | What | Exact fix | Also touches |
|---|---|---|---|---|
| E-P2-01 | P-14, P-15, P-17, P-21, P-11 | Arabic sentences use Arabic verbs; one pack name. | «اللي هيحصل في المشروع» (not "Tidy هيعمل إيه"), «الترتيب ماقدرش يقرا عنصرين», «امسح ماركرز شيل السكتات»; one name «حزمة الكابشن»; the brand stays only as the small grey sublabel. | **PC** P-21 and P-11 same rule |
| E-P2-04 | A-02 normal and blocked | Not an accusation. | «مراجعة الجمل الطبية» (and «الجمل الحساسة» for religious clients) instead of «مراجعة الادعاءات». | - |
| E-P2-05 | P-13 normal | Correct Arabic. | «حوالي ساعتين و10 دقايق». | - |
| D-P2-13 | P-19 AR | Media previews do not mirror. | Template previews are dir=ltr (the lower third stays on the left). | - |
| D-P2-16 | P-16 AR 300 | A label is never cut. | The label «الإعداد المحفوظ:» wraps at 300. | - |
| G-F-12 | P-16, P-17 (+P-22 PC) | Backups cannot be switched off. | Remove the "Keep a backup copy of the sequence" checkbox in P-16 (backup always on for client projects; show it as a fixed trust line); | **PC** P-22 offers it only under "Advanced, not recommended". |
| G-F-18 | A-04, P-08 (PC) | A chip says who acts. | "Claude is fixing" / "Needs your editor" on the "Fix" and "Checking" chips, consistently. | **PC** P-08 same chips |

### Follow-ups from the other rows (TA)

| From | Screens | Exact work |
|---|---|---|
| D-P0-3 (Shared) | P-09 and P-16 confirm-nobackup, I-09 normal | TA.dialog same; P-16 confirm-nobackup |
| D-P1-2 (Shared) | P-06 offline, A-04 stale, A-03 no-claude, P-08 stale, P-19 no-text | A-04 stale: no live spinners, drop the old Fix chip; A-03 no-claude: the Arabic-check card stops spinning; P-19 no-text: the failing template tile gets the error border and its reason (M.tile fail + reason) |
| D-P1-3 (Shared) | P-01, P-02, P-03, P-05, P-13 to P-20 | P-13 to P-20 no-Claude: pill, notice and button all say "Claude isn't signed in" (not "isn't open") and use M.noClaude |
| D-P1-4 (Shared) | header row 2 (AR long), tools/AE file names, paths, I-06 menu path | tools/AE file names (div.t-mono) go through M.path or <bdi>; paths no-wrap with M.mid |
| D-P1-6, G-F-10 (Shared) | P-03 no-claude-missing, P-11 normal/panel, I-03 offline, I-05 error, I-07 nointernet/manifest, P-20 offline, A-01 offline, P-21 skipped | P-20 offline: Try again after Start; A-01 offline: drop the second notice or give it a button |
| D-P1-7, E-P2-08, G-F-13 (Shared) | P-03 hero, A-02 storyboard, A-04 frames, P-08 thumbs | A-04 9:16 frames, no empty black box, while QC is open the primary is "Wait for QC" with "Open anyway" secondary (G-F-13); A-02 storyboard frames with content |
| D-P1-8, E-P2-15 (Shared) | P-15, P-17, P-08, P-01 success | P-15 and P-17 "Done"/"Show in project" is the violet, Undo is secondary with no keycap |
| D-P1-9, E-P2-02, E-P2-03 (Shared) | all screens, P-12 ready, I-05, I-06 | «جرّب تاني» is canonical; replace «اتأكد تاني» with «افحص تاني», «رجّعهم» with «تراجع», «ريندر/رندر» one spelling |
| D-P1-11 (Shared) | A-02 empty, A-03, P-10 long, P-07 no-claude | A-02 empty = 0; A-03 does not count the "nothing to do" card (3, not 4) |
| D-P2-2 (Shared) | P-14 and A-04 stat numbers, pills, AR links | ta-num (15/20 and 20/28) -> t-stat |
| D-P2-4 (Shared) | P-03, P-07, A-02, P-08, A-01, P-01, P-04, P-05, P-12 | A-01 info circle -> waiting; A-02 status icon |
| D-P2-5 (Shared) | P-04, P-02, TA.back, core back | TA.back -> M.back |
| D-P2-6 (Shared) | P-14, P-16, A-03, P-09, P-21 | P-14, P-16, A-03 dashed-pending icons -> M.bullet |
| D-P2-7 (Shared) | P-07, A-02, P-05, P-21, P-14, P-16 | A-02 error; P-14 and P-16 stale: one "Scan again" only |
| D-P2-8, G-F-03, E-P2-06 (Shared) | P-03, P-04, P-07, P-13, P-14, P-15, P-17, P-20, A-04, P-12, P-22, I-03, I-04, I-08 | P-13 "about 1 h 10 min" from tools; P-15 (112 removed vs 4 kept; 7 of 8 with 2 out), P-14 (4 bins add up), P-17 (18 vs 20/24; Hush "about 4 min"), P-20, A-04 say "· estimate" |
| D-P2-14 (Shared) | P-02 link-off/claude-missing, P-18 errors | P-18 follows M.notice automatically |
| E-P2-19 (Shared) | A-02 normal, P-01 | A-02 "6 free icons, we may use them"; "Music: Calm Pulse. Credit the artist in the post (it's in the publish pack)"; number row "2 (twice in a row) · 00:14"; use «بيخطّط المونتاج» everywhere |

## 4. INSTALLER

Screens: I-01 to I-09. A later worker does these; read the Arabic fixes as draft copy for the native writer.

### Lead rows

| Id | Screens | What | Exact fix | Also touches |
|---|---|---|---|---|
| D-P0-2 | I-06 error, I-08 error, I-05 loading/checking/waiting/timeout/success | The headline follows the state. | I-06 error: "One step needs you"; I-08 error: "Update not installed"; I-05 title: "Installing Claude…" -> "Sign in to Claude" -> "Claude is ready", and the rail step stays active until Continue. | - |
| D-P1-10 | I-01, I-04, I-06, I-07, I-08, I-09, P-22 support, P-11 link-refused | No developer words or raw paths in the primary text. | Plain locations ("In Login Items", "Claude settings backed up today 10:32"); raw paths and log lines only behind "Show details" / "Copy details"; drop the log line from error cards ("Save a report" covers it); no github.com/thewhynotai text. P-22 support: no "heartbeat", "code=timeout request=r-8f21", "FAILED export_frames"; P-11 link-refused: no "a message was too large". | **PC** P-22 support text (no heartbeat, request ids, FAILED lines) and P-11 link-refused (no 'message too large') |
| D-P2-12 | I-01 to I-09 | Installer polish. | One Close look (ghost / grey / violet today); Back the same in I-02 as elsewhere; remove the "Genuine Setup from The Why / Not" orphan (use the no-break rule); "1 to know" chip wording; I-04 sidebar spinner while "Needs you" becomes the waiting dot. | - |
| E-P2-17 | I-01, I-03, I-02 | No jargon the editor cannot decode. | I-01: "Just for you. No admin password and no developer tools." (no Homebrew / Xcode); I-03: "macOS protection is still on." (no Gatekeeper); I-02 sub: "Claude won't stop to ask permission before every editing step. Anything outside WhyNot Cut still asks." | - |
| E-P2-18 | I-06 finish (Windows) | One numbered next path. | "1. Open Premiere, then Window > UXP Plugins > WhyNot Cut (M.menuPath). 2. In the panel press 'Set up my first client'." "Open Claude" is secondary; the Latin name wrapped so the button never reads «Claudeافتح». | - |

### Follow-ups from the other rows (IN)

| From | Screens | Exact work |
|---|---|---|
| D-P0-3 (Shared) | P-09 and P-16 confirm-nobackup, I-09 normal | I-09 first screen = neutral "Continue" leading to the red confirm, Uninstall carries destructive:true |
| D-P1-4 (Shared) | header row 2 (AR long), tools/AE file names, paths, I-06 menu path | I-06 menu path = M.menuPath; log and file paths via M.path |
| D-P1-5 (Shared) | every AR header and installer | check I-01 to I-09 AR heads after the re-render |
| D-P1-6, G-F-10 (Shared) | P-03 no-claude-missing, P-11 normal/panel, I-03 offline, I-05 error, I-07 nointernet/manifest, P-20 offline, A-01 offline, P-21 skipped | I-05 error shows the install path first ("Install Claude" / "Open claude.ai/download"), I-03 offline and I-07 nointernet get "Get the offline installer", I-07 manifest: "Open download page" (never a shell-script URL) |
| D-P1-9, E-P2-02, E-P2-03 (Shared) | all screens, P-12 ready, I-05, I-06 | glued «سطّبClaude» (I-05) and «افتحClaude» (I-06): wrap the Latin name with M.t / <bdi>; same list |
| D-P1-12, G-F-14 (Shared) | I-01, I-02, no-Claude cards on P-01, P-03, P-07, P-08, P-11, P-12, P-22 | I-01 "Setup sends nothing from your computer" (G-F-14), offline state: "Installs without internet; Claude and sign-in need it later"; I-02 "Don't ask me each time Claude uses WhyNot Cut" UNTICKED by default with one line on what it skips |
| D-P2-1 (Shared) | pc-row, m-actionbar, i-bar, pc-model, pc-diff, m-check, i-step, pc-step | i-bar, i-step (8 + border -> 7 + 1) |
| D-P2-8, G-F-03, E-P2-06 (Shared) | P-03, P-04, P-07, P-13, P-14, P-15, P-17, P-20, A-04, P-12, P-22, I-03, I-04, I-08 | I-03 6.0 vs 3.6 GB, I-08 success footer 3.0.1 (not 3.0.0), I-04 macOS prompt names the clients folder, not Documents |
| D-P2-9 (Shared) | P-05 file names, I-01 "Genuine Setup from The Why / Not", P-03 | "The Why Not" inside one no-break run |
| D-P2-10 (Shared) | keycaps, times, I-08 versions | I-08 version digits (Syne old-style "3.o.ı") set in Inter (.lat / .code) |
| G-F-16 (Product Backlog) | I-08 | I-08 shows it |
| G-F-04 (Owner Decision) | I-01 "internal", I-07, I-08 | keep it out of sales frames; paid-edition frames use the signed state |
| G-F-09, G-Q4 (Owner Decision) | P-11, P-15, P-22, I-07 | I-07 same one-click wording |

Also for every group: replace the local copies of the promoted components (section 1.3) screen by screen, re-run `render_all.py` and `render_280.py` (AE), read the contact sheets, and keep `check_css.py` at 0 hits.

---

## 5. OWNER DECISION (needs Yunus)

In the screens the CURRENT APPROVED wording stays; every slot that depends on these decisions is marked MOCK-VERIFY in the strings. Nothing here is paid for or published by this pass.

| Id | Findings | Screens | Decision | Options | Recommendation |
|---|---|---|---|---|---|
| D-01 | G-F-01, G-Q1 | I-05, P-01, P-12, P-22 | Which Claude plan each editor needs, what it costs, and how the line is worded. Also every sentence that says who bills (P-22 «Anthropic بتحاسبك على حسابك», "Billed by Anthropic"). | (a) Keep "your own Claude account, no extra charge from WhyNot Cut" and add nothing (the buyer finds the cost out later: reads as bait). (b) Name the plan and the price, verified at claude.ai and support.claude.com on the day of the release: "Each editor needs Claude [plan] (paid to Anthropic, about $X a month). WhyNot Cut adds nothing on top." (c) A "cost and data" sheet page linked from I-05, P-01, P-22 that states the plan, the price and who pays. | (b) plus (c), after Yunus verifies the current plan names and prices himself; the mockups keep (a) with MOCK-VERIFY until then. I cannot verify Anthropic prices from here. |
| D-02 | G-F-02, G-Q5 | I-05, P-01, P-07, P-12, P-22 | What is said about how Anthropic handles what Claude receives (retention, training), which plan keeps client data out of training, and the one-page data sheet for clinic lawyers. | (a) Say nothing more (clinic compliance officers stop the project). (b) One line next to the approved privacy line: "What Claude receives is handled under your Claude plan's terms. For client work use [business plan]." plus a data sheet (what is sent, where, retention, how to remove it). (c) b plus a per-client "Sensitive client" switch that warns on a personal plan. | (b) now, (c) later (backlog B-11). The wording of any Anthropic fact must be checked against Anthropic's own terms by Yunus before it is written; the screens keep the approved line only. |
| D-03 | E-P1-06 (and the MSA remainder of D-P1-9) | P-01, P-02, P-07, P-12, P-22, I-05 | Re-approve the privacy line in Egyptian Arabic (it is executor-APPROVED in MSA: «لا تُرفع أبدًا؛ يقرأ Claude…», and has no final period on P-12, P-22, I-05). | (a) Keep MSA (reads like a legal disclaimer). (b) Egyptian with the same facts: «ملفات الفيديو والصوت عمرها ما بتترفع. Claude بيقرا نصوص بس (التفريغ والخطة) وشوية صور ثابتة: لقطات قليلة من التايملاين عشان المراجعة، وصور البراند.» | (b), plus the final period everywhere. Needs Yunus's re-approval of the Arabic wording (the English wording is unchanged). |
| D-04 | G-F-04 | I-01 internal, I-07, I-08 | Signing and notarization cost and timing: the paid edition ships signed (Apple notarization, H4-Mac, about $99 a year per the owner review) and Windows signing. | (a) Ship unsigned and keep the "hasn't been checked by Apple or Microsoft" warning (fine for the beta, not for a paying agency). (b) Sign and notarize the paid edition only. (c) Sign and notarize everything from the first external tester. | (b). It is a paid item: nothing is bought; the free path (internal state, beta only) stays until Yunus decides. |
| D-05 | G-F-09, G-Q4 | P-11, P-15, P-22, I-07 | The support channel, hours (Cairo GMT+2 / Dubai GMT+4) and the reply-time promise. | (a) Web page only (today). (b) WhatsApp or email in Arabic, working hours, target "within 4 working hours". (c) b plus a named person for the first paying agencies. | (b) once Yunus confirms the channel, the hours and that he can keep the promise; the mock shows a MOCK-VERIFY slot and a one-click "Copy details and open support". |
| D-06 | G-F-11 | P-07 success-later, P-01, P-04, P-12, P-22 | How the build runs without a person opening Claude: the default mode (background mode, the person's own sign-in, or the panel opening Claude itself). | (a) Today: the build waits until someone opens Claude. (b) Default to the mode that needs no open window. (c) The panel opens Claude itself and shows "Claude opened. Building…". The API-key mode costs money and is never a default. | (b) or (c), after the engine proves it works for the customer's plan (backlog B-12); the mock keeps today's wording and P-07 success-live already reads "Claude is building the sequence now". |
| D-07 | G-Q2, G-Q3 | (pricing; not on a screen) | Tiers: one flat price today. The owner asks for a team tier, a per-seat add-on and a pilot discount (about 40 % off if the pilot's hours stay estimates). | (a) One flat price. (b) A team tier by editor count (up to 5, up to 12, 20+) plus a per-seat add-on. (c) b plus a 30-day paid pilot that measures real raw-to-approved times (backlog B-03). | (c). Prices are Yunus's; nothing is written into a screen. |
| D-08 | (all Arabic) | all | A native Arabic writer approves the whole Arabic UI (professional Egyptian) and the word list in strings.js. | (a) Yunus. (b) An outside native writer. | (a) first, because he reads Arabic and knows the editors; then (b) for the sales material. |

---

## 6. PRODUCT BACKLOG (real features beyond the mockups)

Lead findings: G-F-07, G-F-08, G-F-16, E-P2-07. The mockups SHOW some of these where the reviews ask; each needs engine or contract data.

| Item | From | What the mockup shows now | What the product needs (engine / contract data) |
|---|---|---|---|
| B-01 Sign-off export and audit-grade approval | G-F-05 | P-07: "Confirmed with" required, "Export sign-off" link on the approved card | `approval_record` extended: `flagged_lines[{tc,text,kind,checked_at}]`, `confirmed_with` (required when client `signoff_required`), `approver_locked`, `change_log[]`, `plan_version`, `reel_file`; an export (PDF or CSV) written into the client folder; per-client setting `signoff_required` (medical, religious) |
| B-02 Per-clip lock file | G-F-08 | P-04 and P-05 (group): "Mona is working on C0239 (since 14:10)", Open read-only / Take over | a lock file per clip in `data/` `{holder, host, since, heartbeat}` written when the pipeline starts, read by the status; take-over rules; works on a shared NAS |
| B-03 Owner CSV and metrics | G-F-07, G-F-17, G-Q2 | P-22 "Export my week" row (group); Home shows turnaround | CSV `{clip, client, raw_s, reel_s, steps, est_saved_min, approver, approved_at, turnaround_s}` into the client folder; `turnaround_s = approved_at - raw_in_at`; reels per week; one combined sheet from the shared clients drive |
| B-04 Update rollback | G-F-16 | I-08 "Previous version" under Repair (group) | keep the last good version on disk; `repair --previous`; contract `versions.previous` |
| B-05 Signing and notarization (the H plan) | G-F-04, D-04 | I-01 internal state stays beta-only | the Addendum H items already scheduled in the executor plan (H4-Mac signing and notarization, Windows signing); nothing is duplicated here, see D-04 |
| B-06 Network state | E-P1-03 | pill "no internet", `M.noNet()` | status contract `net {online}`; queue the request and resume by itself when the internet returns ("nothing started; we'll send it again") |
| B-07 Cancel semantics | E-P1-02 | P-06 (group) says what Cancel does | the build cancel removes the unfinished sequence and keeps the plan and the approval; contract `build.cancel` result |
| B-08 Partial apply | E-P2-14 | P-12 ticks per change (group) | `apply` accepts a subset of change ids |
| B-09 OS-aware keycaps | E-P2-07 | sheets render macOS; `?os=win` renders Ctrl | the real panel reads the OS and shows Ctrl or Command; no chip if keydown capture is not proven in UXP (lab) |
| B-10 Time-saved formulas and the rate | F-03, F-15 | P-22 "How is this worked out?", "Set by your agency" (group) | one formula per job type in the engine (`basis`), clamped to [0, raw x rate]; the rate in an owner-only file in the clients folder |
| B-11 Sensitive-client switch | G-F-02 | none (needs D-02) | per-client flag; the panel warns when the active Claude mode is a personal plan |
| B-12 Run mode and Claude auto-open | G-F-11 | none (needs D-06) | status of the chosen mode; the panel opens Claude itself; sign-in detection without a manual "Check again" |
| B-13 Real frames and poster | D-P1-7, G-F-13 | `M.media` with a clapperboard fallback; failed-frame safe-area box | `item_meta.poster` image; `qc.frames[]` stills with `issue_box {x,y,w,h}` and `issue` text; the item's own frame |
| B-14 Needs-you single source | D-P1-11 | P-07 uses 0 / 1 per state | the status `needs` = the count of actionable items, one source for the badge, the tab and the list |
| B-15 Data sheet page | G-F-02 | none | a thewhynot.ai page (what is sent, where, retention, removal); content needs D-01 and D-02 |

---

## 7. Verification of this pass

- `check_css.py`: 0 hits (now scans `css/`, `js/`, `strings/` values and `@font-face`).
- `render_all.py --jobs 6` through `heavy.sh`: all 35 screens, 2,188 renders, 0 failures, `statuslie=0`, `dangerkbd=0`, no screen with more than one live violet fill; `render_280.py`: AE screens at 280 px.
- Sheets viewed for P-01, P-03, P-07 (EN and AR, states normal, stale, no-Claude, error, long) and spot-checked on 10 other screens (pill and keycap regressions); see the commit message.
- Not verified: UXP or CEP paint, motion, Windows keycaps in the sheets, native-writer approval.
