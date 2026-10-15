# Addendum G round 2: agency-owner persona (all 35 screens)

Reviewer: AI agent role-playing the owner of a 12-editor agency (Cairo and Dubai) that makes reels and podcasts for
medical and corporate clients, deciding on $1,000/month. Input: the sheets in `adobe/panel-ui/design/renders/_sheets/`,
single renders of P-01, P-03, P-04, P-06, P-07, P-08, P-11, P-12, P-15, P-17, P-22, A-04 and I-01, plus the copy in
`strings.js` and `strings/*.js`. This is a design review of mockups with mock data. Nothing was tested live.

## 1. Verdict: would pay after a 30-day pilot, if four things are fixed first

Round 1 said "would not pay yet". Round 2 is a real step up. The product now answers the questions I asked in
round 1, mostly in the right place:
- what Claude sees;
- that a new sequence is made and the originals stay;
- backup names and undo on every destructive tool;
- dated approvals with a "confirmed with" field;
- time saved, labelled as an estimate.

The installer (I-01 to I-09) reads like a serious Mac product: what goes where, no admin password, genuine-file checks,
and a resume after a failed download. Next to Frame.io or DaVinci the panel no longer looks like a beta. It looks like
a focused, well-made tool.

I still would not sign a 12-month contract today, for four reasons:
1. **The real monthly cost is hidden.** "Your own Claude account, no extra charge from WhyNot Cut" means I also pay for
   12 Claude plans. No screen says which plan is needed or what it costs. The line is still marked MOCK-VERIFY in
   `strings/installer.js:208-209`.
2. **Medical transcripts go to Anthropic under each editor's personal account.** The trust line is honest about what
   is sent. It never says what Anthropic does with it (retention, training) or which Claude plan keeps clinic data out
   of training. My clinic clients will ask exactly that.
3. **The time-saved numbers don't add up** between screens. One number that looks invented makes every number look
   invented.
4. **There is nothing for me as the owner.** Twelve editors type their own name, keep their own weekly total, can turn
   backups off, and cannot export an approval record. I am paying, and I can see nothing.

Fix these four and I would start a paid pilot, at full price if the pilot proves the hours, or at about 40% off if
the hours stay estimates.

## 2. Round-1 points

| # | Round-1 point | Status | Evidence / what's left |
|---|---|---|---|
| 1 | P-07 box hidden behind "Show all 3" | **Addressed** | The tick box and "Confirmed with" sit below the collapsed list. The hint says "Approve stays off until you tick the box" |
| 2 | No promise about the project; Tidy put-back | **Addressed** | P-07: "A new sequence C0239_v1 is created; your original sequence and files aren't touched." P-15 has "Where things went" and "Put them back" with the backup file name. P-17 has Undo plus the backup name. A-01 has the AE equivalent |
| 3 | Claude looks like a separate paid product; build waits for another window | **Partly** | The account, cost and footage lines are on P-01, I-05, P-12 and P-22. Still open: the cost fact is unverified, no Claude plan is named, and the P-07 "success-later" state still says "Claude continues when you open it… outside Premiere". The build still waits for a person |
| 4 | No time saved shown | **Addressed, with a new defect** | Shown on P-03, P-04, P-06, P-07, P-12, P-13, P-15, P-17, P-20 and A-04, and the formula is in P-22. The numbers contradict each other (F-03) |
| 5 | Mixed MSA/Egyptian | **Addressed in the copy** | The strings are professional Egyptian. A native writer's pass is still pending |
| 6 | Translated-sounding words | **Addressed** | No «التسلسل», «قصّات», «الإطارات» or «ولقطتا» left. «سيكوينس», «قطعات» and «مراجعة الصور» are used. The log moved to P-22 "Details for support" |
| 7 | Code-style folder names in the P-03 empty state | **Addressed** | "Each client has one folder. Inside it, WhyNot Cut keeps…" |
| 8 | Support goes where? Two things named "WhyNot Cut" | **Addressed** | "Contact support" is on errors, P-15 and P-22. The background program is "WhyNot Cut service" everywhere. A new issue is the depth of support (F-09) |
| 9 | Needs-you badge during setup; status at 300 px | **Addressed** | No badge on P-01. The status is one "All set" pill. It now lies in some states (F-06) |
| 10 | Polish (footer count, Latin sub-names, Approve card on Home) | **Addressed** | The footer is only "Powered by". Tidy, Hush and Kalam stay in Latin script in AR. Approve shows on Home only when a plan is waiting. The «و4» line break was not checked |
| 11 | Approver record for medical clients | **Addressed, not enough for audit** | P-07 shows "Approved by Yunus · Tue 14 Oct 2026, 14:32 · Confirmed with Dr. Hana Mostafa". The name is free text and "Confirmed with" is optional. There is no export (F-05) |
| 12 | Team questions (presence, change history, client switcher) | **Deferred, not addressed** | P-04 covers switching clients. Presence and history are in the backlog per G10. For 12 editors this is now my main gap (F-07, F-08) |

Score: 9 of 12 addressed, 2 partly, 1 deferred.

## 3. Findings

P0 = I would cancel or not sign. P1 = I would notice and push back on price. P2 = polish.

| ID | Sev | Screen(s) | Objection (as the buyer) | Concrete change that removes it |
|---|---|---|---|---|
| F-01 | **P0** | I-05, P-01, P-12, P-22 | "No extra charge from WhyNot Cut" hides that every editor needs a paid Claude plan. 12 editors means 12 subscriptions on top of $1,000. Finding that out after signing feels like a bait. The fact is still MOCK-VERIFY. | Verify the fact, then state it plainly: "Each editor needs Claude [plan name] (paid to Anthropic, about $X/month). WhyNot Cut adds nothing on top." Put it on I-05, P-01's Claude row and the pricing page. In P-22, show which mode each AI button uses and what it costs. |
| F-02 | **P0** | I-05, P-01, P-07, P-12, P-22 | Medical clients: transcripts, on-screen claims and timeline frames (faces) go to Anthropic under an editor's personal login. "WhyNot Cut trains on nothing" says nothing about Anthropic. A clinic's compliance officer will stop the project. | Add a line next to the approved privacy line: "What Claude receives is handled under your Claude plan's terms. For client work, use [the business plan whose data is not used for training]." Link a one-page data sheet (what is sent, where, retention, how to remove it). In P-22, add a per-client "Sensitive client" switch that warns when the active Claude mode is a personal plan. |
| F-03 | **P0** | P-03, P-04, P-13, P-15, P-17, P-20, A-04, P-22 | The numbers contradict each other. Home says 4 h 30 this week. The picker says Sahha 3 h 20, and all clients add up to 10 h 20. Tools says 2 h 10. Hush claims "about 12 min saved" on a 72-second clip, but the P-22 formula (raw minutes × 9 − 15) gives less than zero. Tidy, Hush, Kalam and AE say "saved" without "estimate". In a sales demo, one wrong sum kills the whole value story. | One source of truth: every figure is computed by one formula per job type, shown in P-22, and labelled "· estimate" on every screen. Home = the sum of the picker rows for the same scope, with the scope stated ("Sahha Clinic, this week" or "All clients, this week"). Add a "How is this worked out?" link that opens the formula. Never show less than 0 or more than the raw time × the rate. |
| F-04 | **P0** | I-01 "internal" state, I-07, I-08 | A paid customer must never see "This test build hasn't been checked by Apple or Microsoft". Ninety percent of my editors are on Mac; one Gatekeeper warning and they call me, not you. | Ship the paid edition only notarized and signed (H4-Mac, $99/year, which is Yunus's decision). Keep the "internal" state only for the beta, and keep it out of all sales material. |
| F-05 | P1 | P-07, P-22 | The approval record isn't audit-grade. The name is free text from Settings (any editor can type "Dr. Hana"). "Confirmed with" is optional. The record can't leave the panel. | (a) A per-client setting makes "Confirmed with" required when the client is medical or religious. (b) Add an "Export sign-off" action on the approved card: a PDF or CSV with the flagged lines, timecodes, approver, confirmed-with, date and time, plan version, and the reel file name. (c) Lock the approver name after first setup, with a change log. |
| F-06 | P1 | P-06 failed, P-11, P-07 errors | The header says "All set" while the pipeline has failed, or while the errors catalogue shows the service down. A status light that lies costs more trust than no light. | Tie the header pill to the worst live state: red "Needs attention" on any failure card, amber while waiting on Claude. "All set" only when nothing is open. |
| F-07 | P1 | P-03, P-04, P-13, P-22 | There is no owner view. Each editor's "saved this week" lives on their machine. I can't see the team total, reels per editor, or turnaround. Value I can't report is value I can't renew. | Keep it simple (G10), with no accounts. Add "Export my week" (CSV: clip, client, raw, reel, steps, time saved, approver) in P-22, written into the client folder. Each Friday the owner opens one combined sheet from the shared clients drive. |
| F-08 | P1 | P-04, P-05, P-07 | Two editors on the same client folder (a shared NAS is normal for us) could both press "Make my edit" on C0239. Nothing warns them. | Write a lock file when a clip's pipeline starts. P-04 and P-05 show "Mona is working on C0239 (since 14:10)" with "Open read-only" or "Take over". This is a low-risk version of the presence feature from the backlog. |
| F-09 | P1 | P-11, P-15, P-22, I-07 | "Contact support" opens a web page. At $12k a year I expect a named channel and a promised response time, in Arabic, during Cairo and Dubai hours. | In P-22 → Support, show the channel (WhatsApp or email), hours (GMT+2/+4) and a target reply time ("within 4 working hours"). Add "Copy details and open support" in one click instead of "copy them if support asks". |
| F-10 | P1 | P-11 | The error catalogue breaks the "why + one fix" rule. Seven different faults share one "why" line and one fix ("Start WhyNot Cut"), including "settings file is damaged" and "didn't accept this panel", which a restart won't fix. | Give each fault its own cause and its own button: damaged settings → "Repair settings (keeps your clients)"; refused panel → "Update the panel"; blocked → "Show what to allow". Merge the faults whose fix really is the same into one card. |
| F-11 | P1 | P-07 success-later, P-01, P-04, P-12 | The build stops until someone opens Claude "in its own window, outside Premiere". Editors leave it waiting, and a reel isn't built overnight. Round-1 #3 is still half-open. | Make the P-22 mode "Use my Claude sign-in" (or the background mode) the default, so the build continues without a window. If a window is unavoidable, the panel opens it itself and shows "Claude opened. Building…" with no person needed. |
| F-12 | P1 | P-16, P-17 | An editor can untick "Keep a backup copy of the sequence" before Hush. One rushed junior on a client master and the only way back is Edit > Undo. | Backups are always on for client projects. Hide the switch, or move it to P-22 behind "Advanced, not recommended". The G2 rule "every edit is undoable or has a backup" should not depend on a checkbox. |
| F-13 | P1 | P-08, A-04 | The QC grid in the mockups has empty gradient tiles. I can't judge "Pass" without seeing the frame. In AE, "Open project" is the primary button while 2 frames are still checking and 1 shows "Fix". | Render real stills with the issue drawn on them (the safe-area box on the failed caption). While QC is open in A-04, the primary button is "Wait for QC" (or "Open anyway" as a secondary button). On P-08, the failed tile gets its own "Fix this" action. |
| F-14 | P2 | I-01 | "Nothing is sent from your computer" reads as a product-wide promise, which contradicts "Claude reads text…" | Scope it: "Setup sends nothing from your computer." |
| F-15 | P2 | P-22 | The time-saved rate (9 min per raw min) can be changed by any editor, which inflates the numbers. | Keep it in an owner-only file in the clients folder, or show "set by your agency". |
| F-16 | P2 | I-08 | An update has no rollback. On a deadline I need "go back to 3.0.1" if 3.0.2 breaks captions. | Add "Previous version" to Repair, keeping the last good version on disk. |
| F-17 | P2 | All Premiere screens | The value is in minutes. In Cairo, editor hours are cheap. What I sell to clients is turnaround and reels per week. | Add "reels this week" and "average turnaround (raw in → approved)" next to the minutes on Home and in the export. |
| F-18 | P2 | A-04, P-08 | The "Fix" and "Checking" chips don't say who acts: Claude, or my editor? | "Claude is fixing" or "Needs your editor", consistently. |

Counts: **P0 = 4** (F-01 to F-04), **P1 = 9** (F-05 to F-13), **P2 = 5**.

## 4. Pricing objections (what I'd say in the meeting)

1. **"$1,000 plus 12 Claude plans: what's the real number?"** Until F-01 is answered, I assume the worst and ask for a
   discount equal to the Claude bill.
2. **"Per-seat tools I already pay for cost tens of dollars per user."** $1,000 for 12 editors is about $83 per editor
   before Claude. That's fine if each editor ships 3–5 more reels a month. Prove it with a pilot that measures real
   raw-to-approved times, not the ×9 formula.
3. **"What if I have 5 editors next quarter, or 20?"** The single flat price has no tier. Offer a team tier and a
   per-seat add-on.
4. **"Who do I call at 11 pm before a clinic launch?"** No SLA means no premium.
5. **"Can my clinic's lawyer see the data sheet?"** If not, I can't use it on my best-paying clients, and the value
   halves.

## 5. The three things that would most raise my willingness to pay

1. **A one-page "cost and data" sheet, linked from I-05, P-01 and P-22** (F-01 + F-02): the exact Claude plan per
   editor and its price, what is sent and to whom, retention and training, and the recommended plan for medical
   clients. This turns my biggest fear into a selling point to my own clients.
2. **Believable, owner-level proof of value** (F-03 + F-07 + F-17): numbers that reconcile on every screen, a
   "How is this worked out?" link, and a weekly CSV per editor that I can roll up into one team report of reels,
   turnaround and hours. If the pilot's real numbers match the estimates, I renew without negotiating.
3. **An audit-grade medical sign-off** (F-05 + F-12): a required "confirmed with" field for medical clients, a locked
   approver, an exported sign-off PDF per reel, and backups that cannot be switched off. This is what lets me charge my
   clinic clients more, which is what really pays for WhyNot Cut.
