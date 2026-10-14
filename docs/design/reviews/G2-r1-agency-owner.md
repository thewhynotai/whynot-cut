# Addendum G round 1 — agency-owner persona (P-01, P-03, P-07)

Reviewer: AI agent role-playing a Cairo agency owner (6 editors) deciding on $1,000/month. Input: the post-E-D3-r1
sheets and renders, strings.js. Verdict: **would not pay yet**. The screens never show the hours saved, never promise
the client's project stays untouched, and "Claude" reads as a second account and cost.

## MAJOR
1. P-07 normal: the hint asks to tick a box that isn't visible until «اعرض الكل (3)» is pressed. Always show the box, or say to open the lines first.
2. P-07/P-03: no promise about the project. Under Approve say a NEW sequence is made and the original sequence and files are untouched. Tidy shows where files went and a "put them back" button.
3. P-01/P-07: Claude looks like a separate paid product. One line on whose account it is, what it costs, and where the footage goes. Step "4 of 7 · build" waits until someone opens another window.
4. P-03/P-07: no time saved shown. Show it, e.g. raw 6:40 → 52 s reel, about 45 min saved; weekly total on Home.
11. P-07 (medical clients): free-text approver name, no record of which doctor confirmed, no date. Add the full date and time, plus a "confirmed with: Dr. ___" field.

## MINOR
5. The Arabic register mixes formal MSA and Egyptian; use professional Egyptian everywhere.
6. Wording that sounds translated:
   - «التسلسل» → «السيكوينس»;
   - «قصّات» → «قطعات»;
   - «ولقطتا B-roll» → «و2 لقطة B-roll»;
   - «الإطارات» → «مراجعة الصور»;
   - the line count and log belong in Settings, as details for support.
7. P-03 empty state: code-style folder names. Explain them in plain words.
8. Errors:
   - "send the report to support": send it where? Add a support contact button.
   - "WhyNot Cut didn't respond" while the panel is also "WhyNot Cut": the background program needs a different name.
9. Header:
   - the Needs-you badge (99+) shows during first-run; hide it during setup;
   - at 300 px the status loses its subjects; collapse it to one "all good ✓" pill.
10. Polish:
    - remove the footer line count;
    - the brand sub-names stay in Latin script;
    - keep «و4» with the next word;
    - hide the Approve card on Home until a plan exists.
12. Team questions:
    - who is working on this video now;
    - who asked for the changes;
    - a client switcher on Home;
    - a history of approvals and change requests.

## Controller decisions (decide-and-continue)
- **Arabic register:** professional Egyptian in all UI copy (target users are Egyptian editors). This replaces the earlier "MSA-leaning". A native writer still polishes.
- **Names:**
  - the background program is "WhyNot Cut service" / «خدمة WhyNot Cut», never "engine";
  - the panel is just "WhyNot Cut".
- **Trust lines:**
  - P-07 states that a NEW sequence/version is created and the originals are untouched;
  - every destructive tool screen shows undo or the backup name.

  Facts to be verified by the executor before shipping the copy: the footage stays on the computer; Claude reads text (transcript and plan), not the video files; the customer uses their own Claude account with no extra WhyNot Cut charge.
- **Approval record:** full date and time, plus an optional "confirmed with" field for medical/religious lines. A team list and presence are deferred (G10 simplicity; 3.0 has no accounts).
- **Time saved:** shown on P-07 and Home, from mock data. This is an engine data request (raw duration, an estimated manual time).
- **Support:**
  - a "Contact support" button that opens the configured support link;
  - the channel itself is an owner item;
  - the line count and log move to Settings → "Details for support".
- **Moved to the backlog:**
  - presence ("X is working on this");
  - a "who requested changes" history;
  - a client switcher on Home (the P-04 picker covers it in 3.0).
