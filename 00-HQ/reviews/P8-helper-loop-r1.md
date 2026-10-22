# Review r1 — Phase 8 per-card attempt limit (`D:\ClaudeData\accounts\helper_loop.py`) — 2026-10-22 ~18:30

Reviewer: fresh `oh-my-claudecode:code-reviewer` subagent (read-only, no Write tool), LIGHT tier. Saved here by the
master from the reviewer's returned text (findings kept in full, wording shortened only where marked "…").
Reviewer re-ran the staged tests (HELPER_LOOP_UNDER_TEST): 46/46 PASS.

**Verdict: PASS-WITH-MINORS.** No P1.

## P2
1. Yielded runs can still repeat forever: the agent may yield on a ticket that `yield_to()` (live `winpid` only) does
   not see, so the loop restarts at once (BL-04 yield reports 23:52 and 23:56). Fix: wait when the loop cannot
   confirm the yield.
2. "yielded" anywhere in the first 1,500 chars exempts the run (reports keep history, e.g. S6b-r2 "so I yielded
   again"). Fix: test only the Status line.
3. A run killed by the STOP file counts as a no-report run; after 3 STOP kills the loop STALLs and removes AUTO-ON.
   Fix: skip counting when `stopped()`.
4. An IDLE run does not break the "in a row" no-report count. Fix: clear it on IDLE.
5. Prompt rule 3 still claims a card with "no DONE report … newer than its last FIX/Answer", conflicting with rule 4;
   the loop report says "(not the agent…)", inviting "not a report of yours". Fix: rule 3 "no DONE or BLOCKED",
   rule 4 "including BLOCKED reports your auto loop wrote for you", report "on your behalf".

## P3 (known limits / notes)
1. Unblocks now need a `## Answer` header (rule 4 change); setting READY alone starves the card quietly. Fix: say so
   in MASTER-INTAKE §C / PLAYBOOK §2.
2. Reset on BLOCKED is mostly a bypass (a new FIX/Answer already changes the key). Option: reset only on DONE.
3. Intake may take the card id from the file name (`…-BL-77-loop.md`). Fix: add `**Card:** <ID>`.
4. Unusual report names (`-fix1`, lower-case ids) split the count: only lets a card escape, never blocks wrongly.
5. File errors kill the loop: `report_status` without `errors="replace"`; non-atomic `card-attempts.json` write.
6. Runs failing after > 2 min (API outage) now STALL after 3; acceptable escalation, write it down.
7. `LOOP_MARK` exclusion is almost dead code (mtime check already skips it); keep as a guard.

Test gaps named: STOP-killed runs, IDLE between silent runs, yield wording, unconfirmed yield, FIX-round reset end to
end, restart persistence, rule 3/4 consistency.

## Master disposition (fix round 1, same day ~18:35)
- P2-1 fixed: a yielded run that `yield_to()` cannot confirm → 15 min `sleep_until` before the next run (test).
- P2-2 fixed: only `**Status:** … yielded` counts as a yield (test `oldyield`).
- P2-3 fixed: no counting when `stopped()` (not unit-tested: the fake run cannot be STOP-killed mid-run; code path is
  one condition).
- P2-4 fixed: IDLE clears the no-report streak (test).
- P2-5 fixed: rule 3 and rule 4 wording, loop report says "your auto loop, on your behalf" (tests on prompt + report).
- P3-1 fixed: `roles/MASTER-INTAKE.md` §C "Reopening always adds `## Answer`" + how to handle a loop BLOCKED report.
- P3-2 adopted: only DONE resets; agent BLOCKED neither counts nor resets (tests).
- P3-3 fixed: `**Card:** <ID>` line (test). P3-5 fixed: `errors="replace"` + temp-file `os.replace` write with a
  logged `OSError`. P3-4, P3-6, P3-7: known limits (recorded in `setup/AUTOMATION_TEST_REPORT.md`).
- Restart persistence test added (`keep=True`). FIX-round reset stays unit-level (`card_round`).
- Result: staged tests **53/53 PASS** (`D:\ClaudeData\setup-phase8\helper-loop\green-run-r1.log`). No round 2 (LIGHT).
- Rollout 18:35: live backup `helper_loop.py.bak-p8`, live files sha256-identical to the tested staged files
  (953e3742… / e290df44…), `RELOAD-h1` + `RELOAD-h2` set: each loop re-execs onto the new file after its current
  run ends (OPS-06 method; no run stopped, no loop started).
