# R3 fix list: round-3 reviews of the 35 panel and installer mockups (triage; SHARED layer done, group work listed)

Author: the design lead of the R3 pass (AI; not a human designer's sign-off). Date 2026-10-16. Branch release/3.0.

Inputs, read in full:
- `R3-designer.md` (ids `D-F-01` … `D-F-25`);
- `R3-first-time-editor.md` (`E-P1-01` … `E-P1-06`, `E-P2-01` … `E-P2-17`);
- `R3-agency-owner.md` (`O-N-01` … `O-N-18`);
- `R2-owner-decisions.md` (D-05 WhatsApp update 2026-10-16, D-01 round-3 note), `docs/adobe/eng-data-contract.md` §2.5, §2.10.

**Status words.** DONE = changed in this commit and re-rendered (all 35 screens, one `--only` run each, plus
`render_280.py`). Arabic is draft until the D-08 native pass. **Not checked:** real UXP / CEP paint, hover and pressed
states, motion, Windows keycaps, the real docked panel height.

**Decisions applied (not re-asked):**
1. Support = WhatsApp, live, shown by default ("Copy details and open WhatsApp" / «انسخ التفاصيل وافتح واتساب», one
   action, details never in the link, D-05 promise always with it). Not-live = `?support=off` only. Data page and guide
   stay gated with ONE "coming soon" line («… هتنزل قريب»).
2. P-22: "WhyNot Cut trains on nothing" + the D-02 line; "never train any model" removed (EN and AR).
3. D-01 AR opens on «(اشتراك Pro …».
4. P-07 previous approval: `panel_state.previous_approval` (contract §2.5 row added).
5. A-02 = "Sensitive lines review" / «مراجعة الجمل الحسّاسة», Claude flags and a person signs off (TA).
6. The header never says "All set" over a problem; `liveState()` and the self-check share one signal list and the
   self-check judges the rendered header against the rendered body.
7. P-06 stale: never "restart now" while a build runs.

## 0. Counts

Every finding id sits in exactly ONE row (its lead owner). Duplicates are merged into one row with several ids. A row
is SHARED when anything of it was done in the shared layer now; the rest of it is then a group follow-up (sections 2–4
list them per group).

| Owner | Ids | Rows |
|---|---|---|
| shared (done) | 31 | 23 |
| PC (premiere-core) | 11 | 9 |
| TA (tools-ae) | 6 | 4 |
| IN (installer) | 12 | 9 |
| engine | 0 as lead (8 items ride on rows above, §5) | – |
| backlog | 6 | 7 |
| **Total** | **66** | 52 |

66 ids = designer 25 + editor 23 + owner 18. "engine" leads no review id: every engine item rides on a row above and is
listed in §5.

---

## 1. SHARED (done in this commit)

Files: `mockup.js`, `mockup.css`, `strings.js`, `screens/P-01`, `P-03`, `P-07`, `_build/check_css.py`,
`_build/render_all.py`, `_build/render_280.py`, `docs/adobe/eng-data-contract.md`; support / privacy strings and their
call sites in group files (the decisions name them): `strings/premiere-core.js` (`p11.copied.live`, `p22.support.*`,
`p22.privacy.training`), `strings/installer.js` (comment), `screens/P-11`, `P-22`, `I-05`, `I-07` (support lines and
comments), `js/installer.js` (`I.fail` support block, AR footer), `js/tools-ae.js` (no keycap on a confirm button).

| Id | Source · sev | Screen / state | Fix (done) | Owner | Group follow-up |
|---|---|---|---|---|---|
| S-01 = D-F-03, E-P1-03, O-N-02 | designer P1 · editor P1 · owner **P0** | every error card + support row: P-01, P-02, P-03, P-07, P-11, P-15, P-22, A-01, I-01..I-09 | Decision 1. `M.supportLive` (default on, `?support=off` = alternate). `M.supportParts` → "Copy details and open WhatsApp" (`message-square` icon) + the D-05 promise ALWAYS under it; off = "Copy details for support" + ONE `M.soonLine` (12 px info icon, under the buttons, mt-2). `M.notice`, `M.supportRow`, installer `I.fail` use the same block. `MOCK_DATA.support.url` = `https://wa.me/20XXXXXXXXXX?text=WhyNot%20Cut%20support`; `check_css` allows `wa.me` only on that line. AR soon lines: «شات الدعم هيتفتح قريب.», «صفحة التحميل هتنزل قريب.», «الدليل هينزل قريب.» P-11 "copied" and P-22 "Opens …" say WhatsApp (no URL in the copy). Contract §2.10 updated. | shared | **IN** I-07 manifest: the download page is still gated, so add the next step "Ask us on WhatsApp for the installer" (the card's support button) instead of the bare soon line. **PC** P-22: with support live the support card shows the guide soon line under the WhatsApp block; check spacing. `-live` twin states now differ only by "Cost and data" / guide / download: prune or keep, group's call |
| S-02 = D-F-01, O-N-13, E-P2-01 | designer **P0** · owner P2 · editor P2 | ~12 states: P-15 sync-done, P-08 stale, A-03 probe, P-05 locked, P-09/P-14/P-16 confirm, P-18 model-busy, P-01 normal | Decision 6. One signal list `M.SIG` (confirm, error, warn card, paused bar, running work, warn chip / amber icon, open setup `.m-steps-open`, disabled main `.m-main-off`) feeds `liveState()`; precedence: confirm → no pill; error → red; restart → amber; warn card → amber; warn chip → "Needs a look" (unless Needs-you); running → "Working…"; setup → "Setting up · 3 of 4"; Needs-you → none; disabled main → "Waiting"; else "All set". `M.btn` / `M.verb` mark a disabled primary `m-main-off`. Self-check `statuslie` now reads the RENDERED header (any single ok pill, incl. a screen's own `view.status`) against the rendered body, so it fails on every such state. Measured after: P-15 sync-done / P-08 stale / A-03 probe "Needs a look", P-05 locked "Waiting", confirms no pill, P-18 model-busy "Working…", P-01 normal "Setting up · 3 of 4". | shared | **PC / TA** name the reason where the generic word is weak: `view.status` or `M.notice o.pill` (P-05 locked "Waiting for Mona", P-18 model-busy "Model downloading", A-03 probe "Checking Arabic text"). Fix the states in §7 |
| S-03 = D-F-02 | designer **P0** | P-06 stale | Decision 7. `stalePass()` finds running work (spinner, indeterminate bar, running fill) and then rewrites the restart notice to "WhyNot Cut was updated. Let the running job finish, or stop it first. Then close Premiere, open it again and press Check again." Its Check again is grey; pill "Premiere: restart after this job". Self-check `stalerun` fails a live restart button over running work. | shared | none |
| S-04 = D-F-04 | designer P1 | I-05 error / error-live / long AR (violet «افتح /downloadclaude.ai») | `LATIN` keeps a slash inside a run: "claude.ai/download" and "mg/dL" are one isolate. | shared | **IN** re-check I-05 AR sheet |
| S-05 = D-F-06, E-P1-06 | designer P1 · editor P1 | P-01 normal / focus / normal-live / stale | Healthy Claude row = "Signed in" + "Needs a Claude Pro or Max plan, paid to Anthropic." + See plans · What Claude sees · "Cost and privacy" (collapsed). D-01, D-03, D-02 words unchanged, behind the disclosure (new state `cost-open`; `normal-live` opens it with "Cost and data"). Part (c) of E-P1-06 done here; (a) who pays and (b) the per-client medical rule are backlog B-R3-2 / B-R3-3. | shared | none |
| S-06 = D-F-07 | designer P1 | A-03 probe, A-04 no-claude / offline, A-02 no-claude, P-08 offline / error / no-claude | Shared rule enforced: the header pill marks a stopped service (`m-pill-stop`), self-check `spinoff` fails any spinner while the service is off. `M.COND` unchanged for kinds. | shared | **PC** P-08 offline / error / no-claude: step 6 paused ("Paused · {reason}"), no spinner. **TA** A-03 probe: a running check draws busy, not the pause icon; A-04 no-claude: main action "Sign in to Claude", "Wait for QC" disabled with a reason, no spinner, no "Claude is fixing"; A-02 no-claude: no spinner; A-04 offline: keep the last verdicts greyed, never "Out of date" |
| S-07 = D-F-08 | designer P1 | P-11 update, P-13 error, P-08 stale, I-04/I-06/I-07 panel-not-installed, P-02 restart-once | `M.COND` gains `restart_needed` (warn), `panel_not_installed` (error), `frame_missing` (warn). | shared | **PC** P-11 update: ONE restart card (amber), one Check again, no red header; P-02 restart-once vs stale: same `restart_needed` kind; P-13 error is TA; P-08 stale: one missing frame = amber chip + amber tile, no violet info icon. **TA** P-13 error: pill and card name the same condition. **IN** "Adobe didn't install the panel" red on I-04, I-06, I-07 (`panel_not_installed`) |
| S-08 = D-F-09 | designer P1 | I-02/I-03 AR paths, A-03 «25.4 After Effects», P-10 long «126 /dLmg», P-15 sequence names | `t()` substitutes plain-text vars BEFORE Latin isolation ("After Effects 25.4" is one run); a unit with a slash is one run. | shared | **IN** I-02 / I-03 paths through `M.path` (one LTR isolate, drive colon inside, left-aligned). **TA** P-15 "Sahha_C0239 - Synced" and «Cam 3 – C0007.mp4» through `M.mid` + nowrap; re-check A-03 at 280. **PC** P-10 long: re-check "126 mg/dL" |
| S-09 = D-F-10 | designer P1 | P-19 selected / focus / long | `.m-tile-on` = neutral card + 2 px violet border (the caller keeps "Selected" + check). Self-check `violet` reads the computed fill and counts the whole family (#5400FB, #4800D8, #6A1FFF, #390796), outermost only. | shared | none (P-19 now 1 violet) |
| S-10 = D-F-12, O-N-15 | designer P1 · owner P2 | P-03 every state with stats | One run "This week · {client}" (`home.week.scope` takes `{client}`), cut with an ellipsis (`.m-trunc`). | shared | **TA** P-13 week line: same scope ("This week · Sahha Clinic", O-N-08) |
| S-11 = D-F-15 | designer P2 | P-01, P-12, P-22, I-05 (D-01 / D-02 in AR) | Decision 3: «(اشتراك Pro بيبدأ من 20 دولار …» with a no-break space in «20 دولار» (strings.js; nowhere else). D-02 quotes stay straight: the owner text is locked (backlog B-R3-7). | shared | none |
| S-12 = D-F-16 | designer P2 | P-03 error / offline; P-13 offline / error, P-18 offline, A-02 offline, P-12 empty | P-03: the disabled Make my edit says "Press Try again first." / "Start WhyNot Cut first."; the header counts every disabled main (S-02). | shared | **TA** P-13, P-18, A-02 offline: one reason line under the disabled main ("Start WhyNot Cut first."). **PC** P-12 empty: "Pick a task first." |
| S-13 = D-F-17 | designer P2 | `long` and 300 px: file and sequence names, "· estimate", «ما», «و» | `t()` binds "· estimate" / "(estimate)" with no-break spaces; AR `txt()` binds «ما» and a standalone «و» to the next word. | shared | **PC** P-06 "C0239_reel_v3", P-07/P-03/P-11 AR long names: `M.mid` + nowrap. **TA** "seque/nce_for_reels" (P-14, P-18, P-20), "IBM Plex / Sans Arabic" (A-03): `M.mid` + nowrap. **IN** I-03 «Premiere Pro و After Effects», I-07 «ما اتسطّبش»: re-check after the shared rule |
| S-14 = D-F-19 | designer P2 | P-08 stale, P-14 unsaved / stale, P-16 stale, A-04 stale | `M.notice`: a notice whose button is primary has no ✕; `dismissPass()` removes ✕ from warn notices while the screen's main action is off. | shared | **PC / TA** re-check the four screens; a notice built outside `M.notice` must follow the same rule |
| S-15 = D-F-20 | designer P2 | P-01 stale | `stalePass()` also switches off `.m-needs-host` buttons; P-01 "Try the sample clip" carries it. | shared | **PC / TA** mark other host-only secondaries `m-needs-host` |
| S-16 = D-F-21 | designer P2 | P-09 confirm, A-03 edited-confirm | `M.dialog`: no keycap on any confirm button; the safe button keeps Esc and focus; Mod+Enter in any confirm lands on the safe button; `tools-ae.js` no longer adds the keycap inside a confirm card; self-check `confirmkbd`. | shared | **TA** `TA.dialog` / A-03 edited-confirm if it does not use `M.dialog` |
| S-17 = D-F-23 | designer P2 | A-01..A-04 at 280 | The badge keeps "Needs you 1" and drops the chevron at 280. | shared | **TA** A-01 at 280: the "Plan approved" pill on its own row so "After Effects 25.4" never wraps alone |
| S-18 = E-P1-01 | editor P1 | P-07 older (and stale); P-10 older | Decision 4. The notice says who, when, with whom ("Approved by Yunus · Tue 14 Oct 2026, 14:32 · Confirmed with د. هناء مصطفى at the time") and what was kept. A line keeps its tick only with the same graphic id AND text, marked "From the earlier approval" / «من الموافقة اللي قبل كده»; a changed line stays empty with "The wording changed, so this line needs a fresh look." P-07 stale uses the same rule (`reason: plan_changed`, all three kept, "Confirmed with" asked again). Contract §2.5 row `previous_approval`. **Engine data.** | shared | **PC** P-10 older: the same who / when line and the "{n} of {of} unchanged" count. **engine** see §5 E-1, E-2 |
| S-19 = E-P1-04 | editor P1 | P-07 (all) vs P-06 running, P-09, P-10 | P-07 names the new sequence once, from `plan.sequence_name` (mock `C0239_v1`), as one no-break mono run. **Engine data** (§5 E-6). | shared | **PC** P-06, P-09, P-10 use `plan.sequence_name` ("C0239_v1"), never "C0239_reel_v3", one no-break run (middle ellipsis when too long). Tools keep the SOURCE sequence (C0239_main): that is a different sequence, say so once |
| S-20 = E-P2-04, O-N-07, O-N-08 | editor P2 · owner P1 · owner P1 | P-03 vs P-13 vs P-17; P-22 formulas; P-13, P-20, A-04 | Home: Hush "Last: 24 pieces cut" / «اتقطّع 24 قطعة» (= P-13 and P-17: 18 pauses + 6 filler words); Kalam "Last: 64 captions placed · 3 d ago" (its 40 min is part of the tools' 1 h 10 min). | shared | **PC** P-22 Hush formula "10 s by hand per pause or filler word; 24 pieces ≈ 4 min"; add "Captions: N s per caption" and "Motion: per finished second" formulas. **TA** P-13 Kalam last run (not "Nothing yet"), P-13 scope "This week · Sahha Clinic", P-20 "about 40 min" and A-04 "about 3 h" computed from those formulas and never above raw time × 9 |
| S-21 = E-P2-17 | editor P2 | footer on every AR screen; P-08 bottom card | AR footer «من thewhynot.ai», set RTL with the domain isolated (panel `footer()` and installer header). | shared | **PC** the P-08 card icon is row P-1 |
| S-22 = O-N-01 | owner **P0** | P-22 Privacy (EN + AR `p22.privacy.training`) | Decision 2: "WhyNot Cut trains on nothing." / «WhyNot Cut نفسه مش بيدرّب أي نموذج.»; "your footage and edits never train any model" removed; the D-02 line under it keeps the neutral info icon. Every strings file grepped for a similar over-claim ("never", "train", «عمره ما», "secure", "private"): none left (the rest are scoped to WhyNot Cut or to setup, e.g. "Setup sends nothing from your computer"). | shared | none |
| S-23 = D-F-24 | designer P2 | P-02, P-09, P-22, P-07 demo summary, I-04 / I-07, A-02 | Shared part: «و2 لقطة B-roll» → «ولقطتين B-roll» (strings.js `demo.summary`). | shared | **PC** «خدمة WhyNot Cut محتاجة تحديث» (P-02 engine-older); «مش هينفع ترجع عنها» (P-09 confirm-nobackup); P-22 quotes the field exactly as P-07 shows it («اتأكدت مع مين؟»). **IN** «خلصنا {n} من {of} خطوات» (I-04, I-07). **TA** A-02 success date «13 أكتوبر 2026» |


---

## 2. PREMIERE-CORE (P-02, P-04 to P-06, P-08 to P-12, P-21, P-22)

### Lead rows

| Id | Source · sev | Screen / state | Fix | Owner |
|---|---|---|---|---|
| P-1 = D-F-13 | designer P1 | P-08 normal, focus, aspect-4x5, fixing, error, offline, no-claude, long, stale, success | The footnote ("Fix this asks Claude…") is helper text with a muted info icon, never the red ✕. Tile title = element + time ("Caption · 00:00:14:08"); the defect text shows only while the tile fails. | PC |
| P-2 = E-P1-05 | editor P1 | P-08 normal (failed tile) | Chip «فيها مشكلة» / "Has a problem"; button «خلّي Claude يصلّحها» / "Let Claude fix it". «محتاجة تدخّل منك» only when the fix really is the editor's, with one line saying what to do. Same chips on A-04 (**TA**). | PC |
| P-3 = E-P2-02 | editor P2 | P-06 running | "Building the sequence… 23 of 47 pieces" / «23 من 47 حتة». | PC |
| P-4 = E-P2-03 | editor P2 | P-12 no-internet | The sheet's own subject: «مفيش نت. «صحّح الكابشن» محتاج نت. كابشنك زي ما هو.» (EN "No internet. Fix captions needs it. Your captions stay as they are."). | PC |
| P-5 = E-P2-13 | editor P2 | P-10 normal / older | «الدكتور أو الشيخ لازم يأكّد الجمل دي.» | PC |
| P-7 = E-P2-14, E-P2-16 | editor P2 | P-22 advanced API key; P-22 sign-off setting | Drop the repeated billing sentence (D-01's «مدفوع لـ Anthropic على حسب الاستخدام» covers it). Sign-off: «الموافقة على الجمل الطبية والدينية ما بتتسجّلش من غيره.» | PC |
| P-8 = O-N-05 | owner P1 | P-11 Claude group (and P-06) | New card: "Claude's usage limit is reached until {time}. That's your Claude plan's limit, not WhyNot Cut. The build carries on at {time}." + See plans. **Engine data** (§5 E-4). | PC |
| P-9 = O-N-11 | owner P1 | P-22 Advanced (owner) | "Combine the team's weeks": reads every `*-week.csv` in the clients drive, writes one sheet (reels, turnaround, estimated vs logged hours per editor). **Engine data** (§5 E-5, B-03). | PC |
| P-10 = O-N-14, O-N-18 | owner P2 | P-11 claude; P-12, P-22 (+ P-20 TA) | P-11: "Claude's own page shows how to install it." (the guide is still gated). One name "Fix captions (Claude)" in P-12, P-22 (and P-20, **TA**); P-12 saved line "of caption fixing saved". | PC |

### Follow-ups from shared rows (PC)

| From | Work |
|---|---|
| S-01 | P-22 support card spacing with the live WhatsApp block + guide soon line; `-live` twins of P-11 / P-22 now differ only by the gated pages |
| S-02 | P-05 locked: `view.status` "Waiting for Mona" (the generic is "Waiting"); P-08 / P-21 own `view.status` must never be ok over a problem (the self-check now fails it); §7 states |
| S-06 | P-08 offline / error / no-claude: step 6 paused, no spinner |
| S-07 | P-11 update: one restart card; P-02 restart-once = `restart_needed`; P-08 stale missing frame = `frame_missing` (amber chip + tile, no violet info icon) |
| S-08 | P-10 long: check "126 mg/dL" renders as one run |
| S-12 | P-12 empty: reason under the disabled main |
| S-13 | P-06 / P-11 long names: `M.mid` + nowrap |
| S-14, S-15 | P-08 stale: no ✕; host-only secondaries `m-needs-host` |
| S-18 | P-10 older: who / when / kept count |
| S-19 | P-06, P-09, P-10 sequence name from `plan.sequence_name`, one no-break run |
| S-20 | P-22 Hush formula wording; P-22 Captions and Motion formulas |
| S-23 | «محتاجة تحديث» (P-02); «مش هينفع ترجع عنها» (P-09); P-22 field quote |

## 3. TOOLS-AE (P-13 to P-20, A-01 to A-04)

### Lead rows

| Id | Source · sev | Screen / state | Fix | Owner |
|---|---|---|---|---|
| T-1 = E-P1-02 | editor P1 | A-02 normal / checked (medical or religious client) | Decision 5. Title "Sensitive lines review" / «مراجعة الجمل الحسّاسة», one chip per line («طبي» / «ديني»). Body: "Claude flagged {n} lines and softened one. A person still signs them off." / «Claude راجع 5 جمل وخفّف واحدة. لسه لازم تأكّدها مع الدكتور أو الشيخ.» Per-line ticks + "Confirmed with" exactly like P-07 (`M.checkbox` per line, the who field, Approve off until done, the same strings `approval.checked`, `approval.who*`). **Engine data** (§5 E-3). | TA |
| T-2 = D-F-11 | designer P1 | A-04 normal, focus, long, no-claude | "Open anyway" becomes a ghost link under the hint ("Open without the check"); Re-render stays secondary; "Wait for QC" disabled with its reason. | TA |
| T-3 = D-F-22 | designer P2 | P-20 normal; P-17 normal | P-20: violet "Done" (back to Tools). P-17: Undo at auto width, start-aligned. | TA |
| T-4 = E-P2-10, E-P2-11, E-P2-12 | editor P2 | P-16 first use; P-14; P-16 confirm | «اللزمات (إممم، آآ، يعني)» once on P-16; «هيتنقل لفولدرات جوه المشروع (Bins)» on first use; «الفراغات هتتقفل، وكل اللي بعد القطع هيتسحب لقدّام.» | TA |

### Follow-ups from shared rows (TA)

| From | Work |
|---|---|
| S-02 | A-03 probe: name it ("Checking Arabic text"); P-18 model-busy "Model downloading"; §7 states |
| S-06 | A-03 probe busy not paused; A-04 no-claude main = Sign in, no spinner; A-02 no-claude no spinner; A-04 offline keeps verdicts greyed |
| S-07 | P-13 error: pill and card name one condition |
| S-08, S-13 | P-15 sequence and file names, P-14/P-18/P-20 sequence names, A-03 font name: `M.mid` + nowrap; re-check A-03 "After Effects 25.4" at 280 |
| S-10, S-19 | P-13: scope line, Kalam last run (not "Nothing yet"), 1 h 10 min = Tidy 25 + Hush 4 + Kalam 40; P-20 and A-04 minutes from formulas under the cap; P-20 "Fix captions (Claude)" (P-10) |
| S-12 | P-13 offline / error, P-18 offline, A-02 offline: reason under the disabled main |
| S-14 | P-14 unsaved / stale, P-16 stale, A-04 stale: no ✕ (check) |
| S-16 | A-03 edited-confirm keycap on the safe button (if `TA.dialog`) |
| S-17 | A-01 at 280: pill on its own row |
| P-2 | A-04 chips: «فيها مشكلة» / «خلّي Claude يصلّحها» |
| S-23 | A-02 success date «13 أكتوبر 2026» |

## 4. INSTALLER (I-01 to I-09)

### Lead rows

| Id | Source · sev | Screen / state | Fix | Owner |
|---|---|---|---|---|
| I-1 = D-F-05 | designer P1 | I-06 amber / long, I-08 loading / checking / offline, I-09 error, I-01 upgrade, I-03 success | One `I.title(state)` table with the panel's rule: I-06 amber "Almost ready" (`i06.title.almost`) + amber Finish step; I-08 busy "Updating to 3.0.1…"; I-09 error "Not fully removed"; I-01 upgrade "Update WhyNot Cut"; I-03 done "This computer is ready"; I-08 offline "Update can't download". | IN |
| I-2 = D-F-14 | designer P1 | I-03 error / offline / nosignin / success; I-01 offline | Chips computed from the rows; I-01 offline = an info notice naming the offline installer; a blocking row is never "Good to know". | IN |
| I-3 = D-F-18 | designer P2 | I-07 nointernet AR 640 | Second button wraps, or «النسخة اللي من غير نت». | IN |
| I-4 = D-F-25 | designer P2 | I-05 / I-08 offline, I-08 normal, I-09 confirm / empty | Notice keycap "↵" through `M.notice`; Update icon `download`; the confirm card below the H1; I-09 empty rail neutral. | IN |
| I-5 = E-P2-05 | editor P2 | I-04 progress (Windows) | «أدوات بيحتاجها Claude على Windows (Git)», not «أدوات أمان». | IN |
| I-6 = E-P2-06, E-P2-07 | editor P2 | I-04 progress; I-09 confirm | «شغّل WhyNot Cut مع الجهاز»; «عدّى 0:42»; safe button «لا، سيبه متسطّب». | IN |
| I-7 = E-P2-08, E-P2-09 | editor P2 | I-07 manifest; I-03 preflight | Failed row «فحص ملفات التسطيب»; «فولدر المستندات عليه سينك مع OneDrive، فهنحط العملاء في فولدر برّه السينك.» | IN |
| I-8 = O-N-09 | owner P1 | I-03 macOS row, I-01 internal (beta) | Beta only: «macOS نبّه مرة لأن نسخة التجربة لسه ما اتعملهاش notarization؛ الحماية فاضلة شغّالة.» / "macOS warned once because this beta isn't notarized yet; protection stays on." The "Opening the beta" note file and the pilot-build decision are backlog B-R3-6. | IN |
| I-9 = O-N-16, O-N-17 | owner P2 | I-01 internal; I-05 / I-07 rail | One name "Beta test build" / «نسخة تجربة» in chip, rail and copy; "The Why Not" in one no-break run. | IN |

### Follow-ups from shared rows (IN)

| From | Work |
|---|---|
| S-01 | I-07 manifest: the next step is WhatsApp support (ask for the installer), the download page stays gated |
| S-04 | re-check I-05 AR error / error-live / long |
| S-07 | `panel_not_installed` red on I-04, I-06, I-07 |
| S-08 | I-02 / I-03 paths through `M.path` |
| S-13 | I-03 «و After Effects», I-07 «ما اتسطّبش»: re-check |
| S-23 | «خلصنا {n} من {of} خطوات» (I-04, I-07) |

---

## 5. Engine data (executor; the mockups already show these)

| # | Rides on | Needs |
|---|---|---|
| E-1 | S-18 (E-P1-01) | `panel_state.previous_approval {by, at, via, format, reason, confirmed_with?, lines?[{graphic_id, text, checked}]}` (contract §2.5, new row); flagged lines need a stable `graphic_id` (`plan` flagged spans) |
| E-2 | S-18 | engine behaviour to confirm: re-approving after "older" does not touch the sequence already built (the editor asked for the line «السيكوينس اللي اتبنى قبل كده مش هيتلمس») |
| E-3 | T-1 (E-P1-02) | motion plans (A-02) carry flagged lines with kind medical / religious, and `approval_record` takes per-line `checked` + `confirmed_with` for a motion approval, like P-07 |
| E-4 | P-8 (O-N-05) | `claude.state = "limited"` with `until` (date-time) when the plan's usage limit is hit |
| E-5 | P-9 (O-N-11), B-R3-4 (O-N-12) | week CSV per editor (B-03) and a combine step; `raw_in_at`, `approved_at` per item; optional manual estimate at approval |
| E-6 | S-19 (E-P1-04) | the build names the new sequence exactly `plan.sequence_name` (one name on P-06, P-07, P-09, P-10) |
| E-7 | S-01 | `support.url` sent by default (the WhatsApp link, contract §2.10 updated); `data_url` / download / guide stay absent until published |
| E-8 | B-R3-3 (O-N-06) | per-client `sensitive` flag and a per-editor acknowledgement store |

## 6. Backlog

| Id | Source · sev | What | Why backlog |
|---|---|---|---|
| B-R3-1 = O-N-03 | owner P1 | "Cost and data" sheet as a local PDF next to the installer and in Settings (what is sent, retention per plan, removal, plan per client type) | content needs the D-02 facts re-checked on release day; a document, not a mockup change (B-15) |
| B-R3-2 = O-N-04 | owner P1 | The Team / Enterprise cost for medical work in the cost line, with a link | Anthropic facts to verify (does a Team seat include Claude Code, which seat); D-01 wording is the owner's |
| B-R3-3 = O-N-06 | owner P1 | First "Make my edit" per editor per medical client: one-time tick "I'm on a Team or Enterprise plan, or 'Help improve' is off" | B-11 lite; engine data E-8; editor E-P1-06 (b) is the same ask |
| B-R3-4 = O-N-12 | owner P1 | Measured raw-to-approved time and an optional "How long by hand?" at approval; "Measured" beside "estimate" after 10 samples | B-03 pilot measurement; engine data E-5; adds a field to P-07 only when the pilot is set up |
| B-R3-5 = O-N-10 | owner P1 | Same-working-day support with Cairo and Dubai hours for the paid edition | phase 2; the D-05 promise now shows in every state (S-01) |
| B-R3-6 = (O-N-09 rest) + E-P2-15 | owner P1 · editor P2 | "Opening the beta" note in the zip (macOS / Windows steps, checksum) and the pilot-build decision (beta vs signed); OS-aware keycaps (Ctrl on Windows) | D-04 phase 2 / B-09 (keydown capture not proven in UXP) |
| B-R3-7 = (D-F-15 rest) | designer P2 | D-02 in Arabic quoted as «Help improve our AI models»; E-P1-06 (a) "ask your company who pays" | locked owner text (D-01 / D-02): Yunus's call |

## 7. States the stricter self-check now fails (for the group workers)

The new fields (`statuslie` on the rendered header, `confirmkbd`, computed `violet`, `stalerun`, `spinoff`) are in
`mockup.js M.selfCheckExtras` and fail `render_all.py` and `render_280.py` (`rule_checks()`). The ~12 "All set" states of
D-F-01 no longer fail: the shared `liveState()` now names them (S-02). What the stricter check still catches:

| Group | Screen · state | Check | What to fix |
|---|---|---|---|
| PC | P-08 offline (EN + AR, 300 / 360 / 480: 6 renders) | `spinoff=2` | the service is off, but step 6 and its card still spin: draw them paused ("Paused · WhyNot Cut isn't running", amber pause icon, no spinner); row S-06 |

No TA or IN state fails. `statuslie`, `confirmkbd`, `violet`, `stalerun`: 0 everywhere.

## 8. Verification of this pass

- `check_css.py`: 0 hits (43 code files, 4 copy files; `wa.me` allowed only on `MOCK_DATA.support`).
- `render_all.py`, one `--only` per screen (35 runs through `heavy.sh job r3-shared`): 2,356 renders, 2,350 ok, 6 failed
  (P-08 offline, §7). P-01 rendered twice (a link-row spacing fix after the first look). `manifest.csv` is not rewritten by
  `--only` runs.
- `render_280.py --states <every A-0x state>`: 100 renders, 100 ok (after keeping the label: "99+" in `long` hides the label
  at 280 only, it had overflowed by 2 elements).
- Header pill measured on the D-F-01 states (EN 360): P-15 sync-done, P-08 stale, A-03 probe "Needs a look"; P-05 locked
  "Waiting"; P-09 / P-14 / P-16 confirm no pill; P-18 model-busy "Working…"; P-01 normal "Setting up · 3 of 4";
  P-06 stale "Premiere: restart after this job"; P-19 selected 1 violet fill.
- Viewed (full size): P-01 normal EN 360 and error AR 360; P-07 older EN 360 and AR 360; P-06 stale EN 360; P-11 normal
  and held AR 360; P-22 normal EN and AR 360 (privacy and support cards); I-07 checksum AR 760; I-05 error AR 760 (the
  violet now reads «افتح claude.ai/download»).
- P-01: "Set up my first client" now starts at about 630 css px at 360 (was about 870; target 600: close, not met).
- Not viewed: any `?support=off` render (not in the sheets; the alternate state is a URL param), P-22 support / support-empty,
  the sheets of the other 27 screens, the 280 sheet.
