# PRIMARY_ACCOUNT_INBOX — messages for Yunus's account (PRIMARY)

Append-only. Written by `tools/hq_status.py` (reports) and by the Command Center (decisions and requests).
Delivery states: `CREATED` · `FILED` (written here and committed) · `SENT` (shown in Yunus's Claude app by the
scheduled task `whynot-cut-primary-report`; the run's session id is the receipt) · `ACKNOWLEDGED` (Yunus answered) ·
`FAILED`. A file here is **not** a delivered message by itself.

**Direct delivery channel:** the scheduled task in Yunus's Claude app (OPS-02). Until its first verified run the
channel state is `NOT_CONFIGURED`, and messages stay `FILED`.

## Requests waiting for Yunus

| ID | Since | What | Why it is his | State |
|---|---|---|---|---|
| Q-001 | 2026-10-19 | T4.14: correct the 60-second transcript in `Editing Plugin\T4.14-راجع-التفريغ\` | Client-visible words (HIGH tier, human gate) | OPEN |
| Q-002 | 2026-10-20 | Say «نفذ خطة الـ API» only when you want the 500 USD job to start (`00-HQ/BUDGET-API.md`) | Money | OPEN (no action needed until then) |
| Q-003 | 2026-10-20 | Optional: a ChatGPT account is named in the charter but none is connected here (D-002) | His accounts | OPEN |
| Q-004 | 2026-10-18 | H14: Anthropic's written OK for panel chat on an editor's own Claude login (only matters outside the agency) | Third-party permission | OPEN |

## Messages

| ID | Time | From | To | State | Summary | Evidence |
|---|---|---|---|---|---|---|
| M-20261020-0130 | 2026-10-20 01:30 | Command Center | PRIMARY | SENT (this chat) | Charter adopted on 00-HQ; baseline; 8 docs archived; paid API held; ENV-01 root cause | `reports/2026-10-20-audit.md` |
| R-2026-10-20-0136 | 2026-10-20 01:36 | hq_status | PRIMARY | FILED | تقرير حالة: 0 تغيير | `reports/2026-10-20-0136.md` |
| R-2026-10-20-0150 | 2026-10-20 01:50 | hq_status | PRIMARY | FILED | تقرير حالة: 0 تغيير | `reports/2026-10-20-0150.md` |
