# API budget (Console org "TWN AI", prepaid credit)

Owner rule (Yunus, master charter 2026-10-20): **one** paid API job of at most **USD 500**, prepared now and
**activated only when Yunus writes «نفذ خطة الـ API»** (or the same in other words) in the Command Center chat. A
calendar date never activates it. Subscription seats (Yunus, H1, H2) are separate from API billing.

Sources of truth for money: the **Console** (Billing > Usage) for posted charges; `D:\ClaudeData\claude-api-lane\costs.tsv`
and `budget_status.json` are estimates (they ran about 2× high on 10-17).

## Current state

| Plan | State | Spend |
|---|---|---|
| A — October USD 200 (API-200) | **CLOSED** 2026-10-19 15:10 (lane 5 lost its Console login; plan ruling) | Lane 1 85.56 + lane 5 81.97 USD (estimate). Month estimate 962.33 of 1,000 (`budget_status.json` 2026-10-20 01:16) |
| B — November USD 450 (multi-lane) | **SUPERSEDED** 2026-10-20 by the owner rule above (it would have auto-started on 1 Nov) | 0 |
| **API-500 — single job below** | **PLANNED_NOT_AUTHORIZED** | 0 |

**Enforcement already in place (verified 2026-10-20 01:20):** every lane folder holds a STOP the monthly guard cannot
release. Lane 1 and lane 5 carry `HOLD by owner 2026-10-20 …` (old text kept in `STOP.before-owner-hold-20261020.txt`),
lanes 2/4 `HOLD by 00-HQ`, lane 3 the owner's Stage 8 STOP. `lane_reaper.py` only removes STOP files whose text starts
with "budget guard" (`check_budget()`, line 185 onward), so nothing restarts on 1 Nov. Check:
`python -X utf8 -c "import os;R=r'D:\ClaudeData\claude-api-lane';print([open(os.path.join(R,d,'STOP'),encoding='utf-8-sig').read()[:14] for d in ('','lane2','lane3','lane4','lane5')])"`.

## API-500: the one job

**Task:** Stage 3 of the master roadmap, "Panel foundation", **headless mechanical part only**: the UXP panel ↔ local
engine contract, the daemon side, the panel-ui state logic and their tests, each delivered as a card with a fence, plus
one independent review per delivery. This is the shortest path to the charter's first goal (a WhyNot Cut panel that
runs a real job inside Premiere). Live Premiere checks stay with the master's attended session (they can't run
headless).

**Why this one:** after the v3.0.0-p4 tag the critical path is Stage 2 (plans) → Stage 3 (panel). Stage 3 has many
small, test-covered, Adobe-free parts that a headless Opus lane does well, while the subscription seats keep the
design, live Adobe and review-gate work. Re-check at activation: if Gate 4 is still open, the same budget goes to
Gate 4's exit review instead (same rules).

**Cost model (from our own measured runs, `costs.tsv`, Opus 5.5, 17–19 Oct):** build run median 11.6–14.0 USD
(mean 12.5–15.4, max 33.8); review run median 6.6 USD (max 18.1).

| Bucket | Runs | USD |
|---|---|---|
| Build (lane 1, Opus, one card per run, fresh context) | ≈ 20 × 15 | 300 |
| Reviews (lane 5, Opus, one per delivery) | ≈ 20 × 7 | 140 |
| Retries / contingency | — | 40 |
| Close-out report | 1 | 20 |
| **Total ceiling (includes retries)** | | **500** |

**Stop rules (local, conservative, because Console prepaid credit is not a per-job cap):**
- Ledger base = Console "spent" figure at activation time (Yunus sends one screenshot; then one per week).
- Alerts to PRIMARY inbox at 250 / 400 / 475 USD cumulative (50 / 80 / 95 %).
- No new build run when less than 40 USD is left (above the 33.8 max run). No new review when less than 20 is left.
- Hard stop of all lanes at 480 estimated (20 USD safety margin for estimate error). Unused money stays unspent.
- One task per run, `--max-budget-usd 35` per run, no polling loops, no unattended retries beyond the lane
  supervisor's 3-quick-failures STALLED rule. No splitting across keys, accounts or providers.
- Provider-side: at activation Yunus sets a Console workspace spend limit of 500 USD for the month if the Console
  offers it (his account; steps given at activation). If it does not, the ceiling is enforced locally only, and the
  report says so.

**At activation (checklist, Command Center):** (1) re-read live model prices and the billing month; (2) Yunus redoes the
API-lane Console login (`Start-Claude-API-lane.cmd`) and we confirm one headless test run; (3) remove
`lane5\STALLED` if present; (4) write ≥ 6 READY `LANE` cards on the BOARD; (5) set `budget.json` (limit 500, base,
thresholds above); (6) replace the two `HOLD by owner` STOPs; (7) mark this section AUTHORIZED with date and Yunus's
words; (8) after every run: ledger row, checkpoint, cumulative vs ceiling.

**Ledger** (rows appended at activation): `date | task | provider | model | category | input/output tokens | est USD | billed USD | cumulative | left | stop-state`.

## Old plan text
Plans A/B as written on 2026-10-19 are in the baseline copy `D:\ClaudeData\backups\2026-10-20-baseline\00-HQ\BUDGET-API.md`.
