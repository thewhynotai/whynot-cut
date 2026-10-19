reviewer: fresh Opus subagent (Command Center delta review)
sha: 053688730312be3e0f8d17714d5add50ffc7d99b
suite: Ran 19 tests in 1.825s — OK
verdict: FAIL

# OPS-01 review r2: delta after fix round 1 (LIGHT tier)

What I read: `reviews/OPS-01-r1.md`, `tasks/OPS-01.md`, `tools/hq_status.py`, `tools/test_hq_status.py`, the real outputs of
run 2026-10-20-0150 (the report, TASK_QUEUE.yaml, inbox rows, the AUTO block, `.last-snapshot.json`) and the worktree
`D:\WNC-work\ops` (read-only git).

- The ops/hq HEAD is 0536887 and is the same as `ls-remote origin refs/heads/ops/hq`. The worktree is on `ops/hq` and is clean.
- `hq_status.py` and the tests on disk are byte-identical to the copies mirrored in 0536887, so the 0150 run used this code.
- I also ran three in-memory probes: `mirror_files` against `git ls-files`, which gives 64 = 64 and an empty "gone" set
  today; `open_requests`; and `git_state`. I ran one `sync_mirror` repro in a temp repo under `D:\ClaudeData\Temp`.
- I wrote nothing except this file.

## r1 findings

| r1 | Result | Evidence |
|---|---|---|
| P2-1 verdict keyed by task | **FIXED** (test is weak) | `intake_verdicts` is keyed by report path (:145-151). Queue lookup is at :260 and §5 lookup at :369. Real: TASK_QUEUE SETUP-H1 → `latest_report …-r2.md`, `intake_verdict: ""`, and §5 lists the r2 as waiting. The test (:147-161) exercises `report_verdict` (:154), which no production code calls. Nothing tests the render path for "r1 ACCEPTED, r2 DONE is still waiting" (P3-a). |
| P2-2 invented count | **FIXED** (test is partial) | :103-109 gives `None` counts, and :79-80 turns them into `REMOTE_MOVED (not fetched here)`. The test covers only `sync_label` (:163). There is no temp-repo `git_state` test as r1 asked. |
| P2-3 crash, no branch guard | **FIXED** | Guard at :272-274 (`symbolic-ref`; a detached HEAD is refused too). Errors are caught at :298 (`SubprocessError` includes `TimeoutExpired` and `CalledProcessError`). `GIT_TERMINAL_PROMPT=0` is set at :275. Test at :197-206. But see the new P2 and P3-b. |
| P2-4 line endings | **FIXED** in code | `_read`/`_write` use `newline=""` (:197-204). The block and the inbox row use the file's own newline (:211, :224). Test at :166-175 (LF stays LF). On disk now: PROJECT_PLAN_AR.md 168/168 CRLF, CLAUDE.md 98/98 CRLF, PRIMARY_ACCOUNT_INBOX.md 26/26 CRLF. That is uniform, no longer mixed. r1 saw CLAUDE.md and the inbox as LF, and this tool never writes CLAUDE.md, so something outside the tool normalised them to CRLF. The original LF bytes of the plan were not restored. This is only an observation; the files are consistent now. |
| P2-5 fixed literals | **FIXED** | The build line now points to `PROJECT_PLAN_AR.md` §5 (:356). The spend text is derived from the API state (:383-384), and the month figures are read from `budget_status.json` (:124-130). §6 reads the OPEN `Q-` rows (:159-169). The real report lists Q-001 to Q-004. |
| P3-1 parser | **PARTLY** | `**` is stripped and ` — ` is split (:40). The empty owner is safe (:254). UNKNOWN rows now go to §5 (:366). Still open: a `\|` inside backticks. |
| P3-2 first run / removed | **FIXED** | :335-339 and :194. Tested at :183-188. |
| P3-3 index.lock | **FIXED** | :110 `--no-optional-locks status`. |
| P3-4 stale heartbeat | **PARTLY** | The run-log mtime is now used as the heartbeat, with the age shown (:58-71, :343-347). `STALE` is only marked above 330 min (it matches the helper_loop kill, so it is acceptable). |
| P3-5 mirror contents | **PARTLY** | There is a 1 MB cap (:264, :308), and deletions are mirrored (:281-284). There is no deny list. Today nothing is large and there is no `run-*.jsonl`. |
| P3-6 pass-1 SHA | **FIXED** | The wording is "before this report was written" (:361). On a pass-2 failure, a note is appended and the plan block is rewritten to LOCAL_ONLY (:439-441). |

## New findings (regressions from the fix)

**P2-new: one non-ASCII file name breaks the mirror permanently** (:281-284).
`git ls-files` quotes non-ASCII paths (`core.quotepath` is unset, so it defaults to true, in `D:\WNC-work\ops`). Such a
quoted path never equals a key of `files`, so it lands in `gone`. Then `git rm` gets a pathspec that matches nothing,
exits 128, and every later `--sync` returns PUSH_FAILED.

I reproduced it in a temp repo:
1. The first sync with `hq/ملاحظة.md` returned SYNCED.
2. The next sync with one changed file returned PUSH_FAILED: `rm … "hq/\331\205…md" … exit status 128`.

Arabic names are realistic in this project (`T4.14-راجع-التفريغ`, Arabic reports). None exists in 00-HQ today, so the
real run is unaffected for now.

Fix: `git -c core.quotepath=off ls-files -z` and split on `\0`. Add a test with a non-ASCII file name that syncs twice.

**P3-a.** `report_verdict` (:154) is used only by the test. Either use it in `render_report` and `render_queue_yaml`,
or test those render paths directly.

**P3-b: errors swallowed without the cause** (:298-299). `str(CalledProcessError)` carries no stderr, so a real cause
such as `index.lock exists` or a pathspec error shows up only as a command line in the report. Append
`e.stderr` (decoded) when it is present.

**P3-c: a `gone` file that was edited inside the worktree** makes `git rm` refuse ("local modifications"). That would
also give a permanent PUSH_FAILED. Use `git rm -q --cached` plus an unlink, or `-f`. This is unlikely, since only the
tool writes there.

**P3-d: `git_state` is only half guarded** (:97, :105, :110, :322).
- `rev-parse`, `rev-list`, `status` and `describe` are not guarded against `TimeoutExpired`, so a timeout there still
  crashes the run before any output.
- `ls-remote` in `git_state`, and in `sync_mirror` through `_git`, runs without `GIT_TERMINAL_PROMPT=0`.

**P3-e: a one-off false "new tag" line.** The 0150 report says "tag جديد من آخر تقرير" because the 0136 snapshot had
no `tag` key. That is a manufactured "new" claim once per format change. Treat a missing `tag` key in `prev` as
"no baseline".

**P3-f: API-500's state shows as "not understood".** §5 lists API-500 as `حالة مش مفهومة`, because
`PLANNED_NOT_AUTHORIZED` is not in `CHARTER`. Map it to BLOCKED or BACKLOG. BL-14's free-text status is a BOARD
issue, not a tool issue.

**P3-g: the card's fence is out of date.** It still lists git as `rev-parse`, `rev-list`, `ls-remote` only. The code
also runs `status --no-optional-locks` and `describe` on the master repo. Add one line to the card (r1 noted this too).

**What I checked and found no regression in:**
- `mark_sent`: exact `| id |` match, so R-1 does not hit R-10; the first `| FILED |` only; `keepends` round-trip;
  returns 4 when no row is found.
- The WRONG_BRANCH guard runs before any copy.
- `append_inbox` idempotency, and its newline when the file has no final newline.
- The two-pass sync.
- `git rm` scope: only files tracked in the ops worktree. Nothing in the WhyNotCut working tree is written.

## Verdict

**FAIL**, because of one P2.

Every r1 P2 is fixed. But the new deletion mirroring adds a latent hard failure of acceptance item 8 for any
non-ASCII file name. The fix is one line plus one test, and it fits within the second fix round that the LIGHT tier
allows. The P3s can close as known limits.
