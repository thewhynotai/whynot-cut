# Role: API LANES (headless, Console credit, company PC)

The lanes are the fourth pair of hands: they run without a person, on the prepaid Console credit, from
`D:\ClaudeData\claude-api-lane\`. They follow PLAYBOOK §2 exactly like a helper, with branch prefix `lane/` and
inbox folder `00-HQ/inbox/lane/`.

## What lanes get
- **Lane 5 (review, Opus):** first-pass review of every delivered branch (helpers, lanes, master's own release
  commits). Verdict file in `reviews/<sha>.md`; the master decides.
- **Lane 1 (build, Opus or Sonnet per card):** only cards marked `assigned: LANE`. Those are cards with a narrow
  fence, clear acceptance tests and no live-Adobe or owner step: mechanical refactors, test backfill, porting,
  fixtures, docs from specs.
- At most **2 building lanes + 1 review lane** at the same time (RAM brake 85%).

## What lanes never get
Design decisions, Arabic product wording, medical/religious content, security-sensitive changes without an Opus
review, live Adobe, anything that needs Yunus.

## Money
`BUDGET-API.md` sets each month's plan. The budget guard (`lane_reaper.py` + `budget.json`) stops building lanes
first and the review lane last. One task per run, a fresh context per run, `--max-budget-usd` per run.

## Simplification (part of the switch, MASTER-PLAN-AR §6, archived: `_archive/plans-2026-10/00-HQ/MASTER-PLAN-AR.md`)
**2026-10-20:** all lanes are held until the API-500 job is authorized (`BUDGET-API.md`).
The lanes commit in their own worktree `D:\WNC-work\lane` (no more commits in the master's shared tree), and they
read their next card from the same `00-HQ/BOARD.md` (rows `assigned: LANE`) instead of a separate
BACKLOG/claims system. Old supervisor copies (`run-lane-loop.cmd`, `-2`, `-3`, `.v1-buggy`, `run-lane.cmd`), the
duplicate logon launcher and the stale flags are archived (never deleted through junctions).
