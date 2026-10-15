# R3: agency-owner review (round 3)

Reviewer: an AI agent playing the owner of a 12-editor agency in Cairo with medical and corporate clients, deciding
whether to pay the premium price for WhyNot Cut. Read-only review at HEAD aa36352.

Inputs:
- `G2-r2-agency-owner.md` (my round 2), `R2-owner-decisions.md`, `R2-fix-list.md`;
- renders, EN and AR: I-05 normal / normal-live, P-01 normal, P-02 normal, P-03 normal, P-11 normal / held / claude,
  P-12 normal / success, P-13 normal, P-15 normal, P-17 normal, P-20 normal, P-22 normal / formula, I-01 internal,
  I-07 dlfail;
- the copy in `strings.js`, `strings/*.js`, and `M.supportParts` in `mockup.js`.

These are mockups with mock data. Nothing was tested live, and no Anthropic fact was re-checked by me.

## 1. Verdict: PAY AFTER PILOT (unchanged), and the pilot can start once two new P0s are fixed

Round 3 is a clear step up on the four things I asked for.
- **Cost.** The cost is now a plain sentence on I-05, P-01, P-12 and P-22 in both languages: "Each editor needs their own
  Claude Pro or Max plan, paid to Anthropic (Pro from $20 a month…). WhyNot Cut adds nothing on top." It has a live
  "See plans" link. My editors won't be surprised by the *first* bill.
- **Data.** The D-02 line ("turn off 'Help improve our AI models'… Medical clients: use a Team or Enterprise plan") is
  accurate and in the right four places.
- **Numbers.** There is now one formula per job type in P-22. Every figure says "estimate". Home states its scope, the
  P-04 rows add up to the stated total, and the rate is locked as "Set by your agency".
- **Beta warning.** The I-01 beta warning is honest and plain.

I would still not pay today. Two new problems stop me from even starting the pilot:
1. **P-22 promises something nobody can keep.** It ticks "your footage and edits never train any model" in green,
   directly above a line that says Anthropic may train on them unless a setting is off (N-01).
2. **The beta has no support channel at all.** Every error says "contact support". The only action copies text to
   the clipboard, beside "Support page coming soon". There's no address, no number and no reply promise (N-02).

Fix those two and I start a 30-day pilot. Section 5 lists what would still stop me from paying after it.

### Answers to the four questions

- **Will editors be surprised by a bill?** Not by the floor ($20 Pro). They can still be surprised by the ceiling.
  Medical work needs Team or Enterprise, which has no price on any screen (N-04). A full-time editor on Pro may hit
  usage limits and buy Max on their own, and no screen covers that (N-05).
- **Would I put a medical client through it?** Yes, but only on a Team plan that I set up and check myself, and only
  after N-01 is fixed. I couldn't hand my clinic's lawyer anything today, because the data sheet isn't live (N-03).
  Nothing in the product reminds an editor which plan to use on a medical client (N-06).
- **Do the numbers hold together?** The method does. The mock data still contradicts itself on the screens I would demo
  (N-07, N-08).
- **Is support credible without a live page?** No. Hiding a link to a page that doesn't exist yet is honest. But the
  copy-only state leaves the editor holding text with nowhere to send it (N-02). The reply promise appears only in the
  live state.

## 2. My round-2 P0s

| R2 id | Point | R3 status | Evidence / what's left |
|---|---|---|---|
| F-01 | Claude cost hidden | **Closed** (residual P1s) | The D-01 sentence is verbatim on I-05 (EN/AR), P-01's Claude row, P-12's AI card and P-22's "Claude and AI buttons". "See plans" goes to a live page. "No extra charge" never stands alone. The API-key mode sits under "Advanced settings (for the owner)" and says "Paid per use". Left: the Team-plan cost for medical work (N-04), and Pro limits (N-05). |
| F-02 | Anthropic data handling unclear | **Partly closed** | The D-02 line is correct and appears on I-05, P-01, P-12 and P-22, never on every screen. "Cost and data" is hidden while `data.url` isn't live (H24), which is correct. New problems: P-22 contradicts the line (N-01, P0). There's nothing a clinic lawyer can read (N-03). Nothing ties a medical client to the right plan (N-06). |
| F-03 | Time-saved numbers contradict | **Mechanism closed; data still open** (now P1) | P-22 "How is this worked out?" has four formulas, and each worked example matches its screen (6:40 → 45 min, 24 → 4 min, 214 files → 25 min, 3 fixes → 3 min). P-03 says "This week · Sahha Clinic · About 4 h 30 min saved (estimate) · 7 reels". P-04 adds to 10 h 20. P-15's bins add to 214, and 108 + 4 = 112. Left: Hush 18 vs 24, Kalam "Nothing yet" while it's counted in the total, and two figures with no formula that break the stated cap (N-07, N-08). |
| F-04 / D-04 | Unsigned build | **Deferral accepted; the beta state is honest** | I-01 internal: "This beta test build hasn't been checked by Apple or Microsoft. Use it for testing only; never send it to clients." There's a warn chip, and the rail swaps "Genuine Setup" for "Beta test build. For testing only." That's honest and beta-only. Left: the honesty arrives after macOS has already blocked the app. The wording also conflicts with a pilot on real client work (N-09). And the state has two names (N-16). I'm not re-asking for signing now. |

Score: 1 closed, 1 mechanism-closed, 1 partly, 1 accepted deferral.

## 3. New findings

P0 = I won't start the pilot. P1 = it blocks payment after the pilot, or I push back on price. P2 = polish.

| ID | Sev | Screen(s) | Objection (as the buyer) | Concrete fix |
|---|---|---|---|---|
| N-01 | **P0** | P-22 Privacy (EN + AR `p22.privacy.training`) | A green tick says "WhyNot Cut trains on nothing: your footage and edits never train any model." («الفيديو والمونتاج بتوعك عمرهم ما بيدرّبوا حاجة»). The very next line says Anthropic may train on what Claude reads unless a setting is off. A clinic's compliance officer reads the green tick as a guarantee, and it's false whenever an editor leaves "Help improve" on. One false promise voids every true one. | Scope it to what WhyNot Cut controls, as I-05 and P-01 already do: "No telemetry, and WhyNot Cut trains on nothing." AR: «WhyNot Cut نفسه مش بيدرّب أي نموذج.» Drop "never train any model". Put the neutral info icon, not a green tick, on the D-02 line beneath it. |
| N-02 | **P0** | P-11 (all cards), P-15, P-22 Support, I-07 (every `-live`-less state) | In the default not-live state, "contact support" leads to "Copy details for support" plus "Support page coming soon". The editor gets text with no address, no number and no promise. `support.promise` is drawn only when `M.live`. Twelve editors in a pilot will phone me, and I'll have no one to call. | Before any outside pilot, Yunus names one channel that needs no web page: a support email or a WhatsApp number. Showing it is public, so it's his call. In the not-live state, show "Copy details, then send them to support@… / WhatsApp …" and the reply promise. If he won't name a channel yet, the pilot waits until thewhynot.ai/support is live. |
| N-03 | P1 | I-05, P-01, P-22 (the "Cost and data" link is hidden while not live) | My clinic's lawyer asks for one page: what is sent, where, how long it's kept, how to delete it, and which plan. Today there's nothing to hand over. The D-02 line alone doesn't mention the 30-day retention with training off, or that the timeline frames can show patients' faces. | Ship the "Cost and data" sheet with the beta as a local PDF next to the installer, and in Settings, "Open the data sheet (on this computer)". A local file isn't a public page, so H24 isn't touched. Content per D-02: what is sent (text, a few frames that may include faces, brand photos), retention per plan (30 days with training off, up to 5 years de-identified with it on, Team/Enterprise not used for training), removal, and the plan per client type. Re-check against Anthropic on release day. |
| N-04 | P1 | I-05, P-01, P-12, P-22 (cost line vs data line) | The cost line says Pro or Max, from $20. The data line says medical clients need Team or Enterprise. Most of my revenue is medical, so my real per-editor cost is the Team price, which appears nowhere. That's the bill I'd find out about after signing. | Add to the cost line: "Medical clients: a Team or Enterprise plan, priced per seat by Anthropic. See plans." Link to the Team plan page. Before writing it, verify that a Team seat includes Claude Code and which seat type it needs, and put that fact in the data sheet. |
| N-05 | P1 | P-11 Claude group, P-06, P-22 | "Pro from $20" is the floor. Claude Code shares the plan's usage limits (D-01 facts). A full-time editor running 5+ reels a day may hit the limit mid-build, and no screen covers it. Editors will upgrade to Max on their own card, which is 12 × $100–200 on top of my fee. | (a) Add a P-11 card: "Claude's usage limit is reached until {time}. That's your Claude plan's limit, not WhyNot Cut. The build carries on at {time}," with "See plans". (b) Make the pilot record Claude usage per reel. After it, state "A full-time editor usually needs Pro / Max" in the data sheet. |
| N-06 | P1 | P-05 / P-07 (Make my edit, Approve) for a medical client | The product already knows a client is medical ("Require 'Confirmed with' for medical and religious clients" in P-22). Yet it sends that clinic's transcript and frames with no reminder of the plan rule. A junior on a personal Pro with "Help improve" on is the exact case I worry about. | B-11 lite, with no plan detection: on the first "Make my edit" per editor per medical client, show the D-02 sentence as a one-time tick, "I'm on a Team or Enterprise plan, or 'Help improve' is off", stored per editor. Keep the full "Sensitive client" switch in B-11. |
| N-07 | P1 | P-03 vs P-13 vs P-17; P-22 Hush formula | Hush shows "Last: 18 silences cut" on Home and "24 pieces cut" in Tools. P-17 says "24 pieces cut · 18 pauses + 6 filler words". P-22 says "24 pauses is about 4 min". Same run, three counts. In a demo the client spots this first. | Use one count everywhere: "24 pieces cut" on Home, Tools and P-17. In the formula: "10 seconds by hand per pause or filler word. 24 pieces is about 4 min." Home's last-run line reads the same field as P-13. |
| N-08 | P1 | P-13, P-20, A-04, P-22 formula, P-03 | P-13 says "This week the tools saved about 1 h 10 min". That includes Kalam's 40 min (`R2-fix-list` §1.2), but Home and P-13 both show Kalam "Nothing yet", so the visible tools add to 29 min. P-20's "About 40 min of typing saved" and A-04's "About 3 h of motion work saved" have no formula in P-22. They also break P-22's own rule, "never above the raw time × 9": the Hush sequence is 0:58–1:12, a cap of about 11 min. P-13 also doesn't state its scope. | Either show Kalam's last run on Home and P-13 ("Last: 64 captions placed"), or drop the 40 min from the 1 h 10. Add "Captions: N s by hand per caption" and "Motion: per finished second" formulas to P-22, and compute P-20 and A-04 from them under the cap. Give P-13 the Home scope: "This week · Sahha Clinic". |
| N-09 | P1 | I-01 internal, I-03 (macOS row), pilot plan (D-04, D-07) | Two problems: (a) On a Mac the unnotarized installer is blocked by macOS before the honest I-01 warning can show, so the first thing my editor sees is Apple's warning with no help from WhyNot Cut. Meanwhile I-03 says "macOS protection is still on" as a reassurance. (b) "Use it for testing only; never send it to clients" conflicts with a paid 30-day pilot on real client work. | (a) Put a one-page "Opening the beta" note next to the beta download. It's a file in the zip, not a web page. It gives the exact macOS and Windows steps, says "WhyNot Cut never asks you to turn protection off", and shows the beta's checksum. In the beta, I-03's macOS row says "macOS warned once because this beta isn't notarized yet; protection stays on." (b) Decide whether the pilot runs on the signed paid edition or on the beta. If it's the beta, reword to "Beta for your team. Don't share this installer outside your agency." |
| N-10 | P1 | P-22 Support, `support.promise` | "We reply within one working day (Sun–Thu, Cairo time)" means a Thursday-evening error before a Sunday clinic launch gets an answer Sunday. That's fine for a beta, but not for a premium monthly price. Our Dubai office works Mon–Fri, so Friday isn't covered either. | Keep it for the beta. For the paid edition (phase 2), promise same-working-day replies and name the hours for both Cairo and Dubai. Show the promise in both the live and not-live states (see N-02). |
| N-11 | P1 | P-22 "Export my week", owner view | "Export my week" writes one editor's CSV into the client folder. I still have twelve files and no team total, so I can't report value at renewal. | In the pilot build, add "Combine the team's weeks" in P-22 Advanced (owner). It reads every `*-week.csv` in the clients drive and writes one sheet: reels, turnaround and estimated vs logged hours per editor (B-03). |
| N-12 | P1 | P-03, P-06, P-07 (pilot measurement) | Every number is still an estimate. To pay full price I need real raw-to-approved times, as D-07 (c) says. Nothing in the UI records the editor's own time, so the pilot can't prove the estimates. | Record `raw_in_at` → `approved_at` per item (it's already in B-03), and add one optional field at approval: "How long would this have taken by hand?" Show "Measured" next to "estimate" in the export once there are 10 or more samples. |
| N-13 | P2 | P-01 normal | The header says "All set" while the body says "3 of 4 ready" and the Clients folder isn't set up. That's a small version of my R2 lying-status complaint. | During first run, the pill reads "Setup 3 of 4", or there's no pill. |
| N-14 | P2 | P-11 claude ("Claude isn't installed…") | The copy says "The guide shows how to install it", but the guide is "coming soon". The button opens Claude's own page. | "Claude's own page shows how to install it." Keep "the guide" for the live state. |
| N-15 | P2 | P-03 EN + AR | The scope line wraps as "This week ·" with "Sahha Clinic" on the next line. AR does the same: «الأسبوع ده ·» then the name. It looks broken. | Bind "This week · {client}" into one no-break run, or put the client first: "Sahha Clinic · this week". |
| N-16 | P2 | I-01 internal | One state has two names: the "Internal build" header chip and "Beta test build" in the rail and the warning. | Use one name, "Beta test build", in the chip, the rail and the copy (AR «نسخة تجربة»). |
| N-17 | P2 | I-05, I-07 rail | "Genuine Setup from / The Why Not" still breaks across lines at 760. | Keep "The Why Not" on one line with a no-break run, as D-P2-9 intended. |
| N-18 | P2 | P-12, P-20 | "Fix captions" names both the P-12 Claude action ("proofreading saved") and P-20's "Fix captions with Claude". P-22's formula is labelled "Fix captions" too. It's unclear which time is counted where. | One name and one formula: "Fix captions (Claude)" in P-12, P-20 and P-22, and the P-12 saved line says "of caption fixing saved". |

Counts: **P0 = 2** (N-01, N-02), **P1 = 10** (N-03 to N-12), **P2 = 6** (N-13 to N-18). 18 findings.

## 4. What I'd say in the next meeting

1. "The cost line is now honest. Now tell me the Team-plan cost for my clinic work, and whether Pro survives a full
   working day."
2. "Take the green tick off 'never train any model'. My clinic's lawyer will screenshot it."
3. "Give me an email or a WhatsApp number for the pilot. A clipboard isn't support."
4. "Make Hush and Kalam agree with themselves before you show this to anyone."

## 5. What would still stop me from paying after a 30-day pilot

1. **Measured hours.** If the pilot's real raw-to-approved times (N-12) come in well under the estimates, I pay about
   40% less or not at all.
2. **The true Claude bill per editor.** This means the Team cost for medical work (N-04) and whether Pro editors hit
   limits (N-05). If Claude costs more per editor than WhyNot Cut does, the premium price doesn't hold.
3. **A data sheet my clinic's lawyer signs off on** (N-03), with no over-promise left in the UI (N-01).
4. **Signed builds for the paid edition** (D-04, phase 2) and **same-day support** (N-10). Both are already
   planned for phase 2. I'd make them a condition of the contract.
5. **A team view** (N-11). If I can't report the team's value at renewal, I won't renew.
