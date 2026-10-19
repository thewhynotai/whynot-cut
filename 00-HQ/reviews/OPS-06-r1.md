reviewer: fresh Opus subagent (Command Center review)
suite: test_helper_loop.py 27/27 PASS (author's run, not re-run by the reviewer)
verdict: PASS-WITH-MINORS

# OPS-06 review r1 (2026-10-20), LIGHT tier

Scope read: `D:\ClaudeData\accounts\helper_loop.py` vs `.bak-ops06`, `test_helper_loop.py` vs `.bak-ops06`, PLAYBOOK.md:173-174, all 15 cards in `00-HQ\tasks\*.md` that have a tier (read-only), h1/h2 `auto\status.json` + `auto.log` (read-only). Nothing under `h1\`, `h2\` or `RELOAD-h1` was touched. The test was not run.

## Acceptance
1. **OK (with gaps, see P3-2).** Unit tests: `review_effort` HIGH -> high (test:120), LIGHT -> medium (test:121), no card -> high (test:122). Loop integration: first run with no file -> `effort=high`, the agent writes `medium` -> next run `effort=medium` (test:115-117). The peer review goes through `run_once` with `effort=high` (test:150). The loop cannot tell a SETUP card apart; the agent's prompt maps it to medium. Both real SETUP cards carry `**Tier:** LIGHT` anyway.
2. **OK (author's evidence).** 27/27 PASS. The new checks are isolated: `run_loop` wipes `profile\auto` before each run (test:89), so a leftover `next-effort.txt` cannot leak into later checks.
3. **OK.** h1 run 1 (started 00:46 on the old code) is still running and was not killed. `RELOAD-h1` (02:04) is in place, and the reload logic already exists in the old code (`.bak-ops06`:507), so the live loop re-execs onto the new file between runs. Its first new run has no `next-effort.txt`, so it runs at high (the safe side). h2 is stopped (STOP file) and loads the new file on its next start.

Regex check: `\*\*Tier:\*\*\s*(HIGH|LIGHT)` matches both real formats: the own-line `- **Tier:** LIGHT (...)` (BL-02/03/04/16/17/18, ENV-01, SETUP-H1/H2) and the combined line `... **Status:** READY    **Tier:** LIGHT    **Milestone:** M0` (OPS-02..06). The `-spec.md` files have no tier line and are never read by `review_effort`. If a card is archived or a report id does not match its card, the lookup falls back to high (safe). The helper `claude.exe` 2.1.299 (the one Start-Helper picks) lists `--effort`.

## Findings

**P2-1: a stale `next-effort.txt` survives IDLE, so a HIGH card can run at medium.** helper_loop.py:393 says "Before you stop, write ... effort ... If no card is left for you, write IDLE". It does not say what to do with effort in the IDLE case, so an IDLE run usually leaves the previous `medium` in place. When the BOARD changes, the loop wakes up (line 489) and the new card, possibly HIGH or a HIGH FIX round, runs at that stale `medium`. That breaks the owner rule. (`next-model.txt` has the same pre-existing gap.) Fix: in the IDLE branch next to `os.remove(IDLE)` (line 489), also remove `NEXT_EFFORT` (try/except OSError), so the next run defaults to high. Add a test: script `medium,idle,ok` with touch_after, then assert `effort=high` on run 3.

**P2-2: PLAYBOOK.md:173-174, the path is broken by a literal newline.** The `\n` in `auto\next-effort.txt` was written as a real newline. The line ends in `` `auto`` and line 174 starts `` ext-effort.txt` ``, so Markdown renders the wrong path "auto ext-effort.txt". Fix: join the two lines with `` `auto\next-effort.txt` ``.

**P3-1: the prompt contradicts PLAYBOOK on an unknown tier.** helper_loop.py:393 says "high if that card's **Tier:** is HIGH, otherwise medium", so a card with no or unknown tier gets medium. PLAYBOOK and `effort_for_run` (line 338) say unknown = high. Fix: change the prompt to "medium if that card's **Tier:** is LIGHT, otherwise high".

**P3-2: test gaps.** Missing checks:
- `next-effort.txt` = `high` -> `effort=high` (the HIGH path is only covered by the "no file" default);
- invalid values (`max`, `low`, `medium.`) fall back to high;
- `prompt()` contains `NEXT_EFFORT`;
- a peer review of a LIGHT card runs through argv at `effort=medium`.

Each is one or two lines next to test:115-122.

**P3-3 (known limit, no fix needed): the next card's effort is predicted.** The agent picks the next card's effort at the end of the previous run. A FIX round or BOARD reorder posted after that write still runs at the predicted effort. Record this as a known limit in the card's Evidence.
