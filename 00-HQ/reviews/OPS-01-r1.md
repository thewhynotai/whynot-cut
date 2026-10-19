reviewer: fresh Opus subagent (Command Center review)
sha: 5e2e65f98d9294ced1dd51b4cccdabf93966d5e7
suite: Ran 11 tests in 1.447s — OK
verdict: PASS-WITH-MINORS

# OPS-01 review r1 (LIGHT tier)

Scope read: `tasks/OPS-01.md`, `tools/hq_status.py`, `tools/test_hq_status.py`, real outputs of run 2026-10-20-0136
(TASK_QUEUE.yaml, reports/2026-10-20-0136.md, reports/.last-snapshot.json, PRIMARY_ACCOUNT_INBOX.md, the AUTO block of
PROJECT_PLAN_AR.md), worktree `D:\WNC-work\ops` (read-only git), inputs BOARD.md, intake/state.json, h1/h2 status.json.
I also ran the tool once without `--write` (exit 0, the product repo `.git/index` mtime did not change on that run)
and probed `parse_board` / `render_queue_yaml` in memory on synthetic rows. Nothing else was written.

## Acceptance

1. **OK.** `parse_board` (hq_status.py:28-45) reads only the `| ID |` table; test `test_rows_parse_from_the_task_table_only`.
   Real run: 20 rows, the old-tracks table is skipped. Caveats in P3-1 (bold or em-dash status words, pipes in cells).
2. **OK.** `helper_state` (:52-59), test `test_heartbeat_and_flags`. Real report: H1 running / AUTO-ON, H2 stopped / STOP,
   matching `D:\ClaudeData\accounts\h*\auto\`. No staleness check (P3-4).
3. **Partly OK.** `sync_label` is tested; `git_state` (:81-98) is not. Real label `LOCAL_AHEAD 50` checked by hand:
   local 4c1e59c3, ls-remote 322d8a5d, `rev-list --left-right --count` = `50 0`. The untested branch where the remote
   tip is not fetched invents a count (P2-2).
4. **OK.** `api_state` (:101-107) reads `BUDGET-API.md`, UNKNOWN when it is missing or has no match; tested. The real
   value PLANNED_NOT_AUTHORIZED matches the BOARD row.
5. **OK in logic, not at byte level.** `replace_block` (:170-174) is tested, and missing markers raise before the
   write (:334). But the read and write in text mode rewrite every line ending of the owner's file (P2-4).
6. **OK.** `append_inbox` (:177-188) is tested (idempotent, FILED). The real row `R-2026-10-20-0136` is present once.
   The appended row is CRLF in an LF file (P2-4).
7. **OK with a hole.** `status_changes` (:163-167) is tested. The first run (no snapshot) prints "no change" (P3-2).
   Tasks removed from the BOARD are never reported.
8. **OK.** `test_commit_push_verify_and_no_change_no_commit` runs against a temp bare remote: commit + SYNCED, no
   change → no commit, bad remote → PUSH_FAILED. Hangs and the branch guard are not covered (P2-3).
9. **OK.** All outputs exist. `git ls-remote origin refs/heads/ops/hq` = 5e2e65f9… = local HEAD. ops/hq is an orphan
   branch (2 commits, a283ed6 has no parent), 61 files. The GitHub repo answers 404 without auth, so it is private.

## Findings

**P2-1 — intake verdict is keyed by task, not by report file** (hq_status.py:131-142, used at :276-277 and :206).
SETUP-H1's verdict "noted" belongs to `2026-10-19-SETUP-H1.md` (r1), yet TASK_QUEUE pairs it with the newest report
`-r2.md` (BLOCKED). If r1 had been ACCEPTED or answered, the waiting r2 would be hidden from §5. When one task has
several entries, the last dict entry wins, not the newest.
Fix: return verdicts keyed by the report path (`inbox/h1/<file>`). For "waiting", look up `verdicts.get(v["file"])`.
Test it with r1 ACCEPTED and r2 DONE: r2 must still be listed as waiting.

**P2-2 — invented git count** (:94-95). When the remote tip is not in the local object store, the code sets
`ahead, behind = 0, 1` and the label becomes `REMOTE_AHEAD 1`. That number is not read from anywhere, and the real
state may also be DIVERGED. This breaks "never manufacture progress".
Fix: return a distinct label such as `REMOTE_MOVED (not fetched)`, with no count. Do not fetch: that would write to
the product repo. Add a `git_state` test with a temp repo plus a bare remote that has an unfetched commit.

**P2-3 — sync crashes instead of reporting, and has no branch guard** (:210-230).
(a) `push` (timeout 180) and `ls-remote` (:226, timeout 90) raise `TimeoutExpired`, and `add`/`commit` use
`check=True`. A network hang or a stale `index.lock` crashes the run instead of recording PUSH_FAILED. A crash
during pass 1 leaves no report, no inbox row and no snapshot.
(b) Nothing checks that the worktree is on `ops/hq` before the copy and commit. If someone checks out another branch
there (the ops worktree shares WhyNotCut's `.git`), the HQ files get committed onto that product branch. The push is
then pointed at `ops/hq`.
Fix: first `rev-parse --abbrev-ref HEAD == branch`, else return state `WRONG_BRANCH` without touching anything.
Wrap the subprocess calls in try/except (`CalledProcessError`, `TimeoutExpired`) → PUSH_FAILED with the error text.
Set `env GIT_TERMINAL_PROMPT=0` so a credential prompt cannot block a scheduled run.

**P2-4 — line endings rewritten** (:327, :333, :334 `write_text`; :184 `open(p, "a")`).
On Windows, text mode writes `\r\n`. PROJECT_PLAN_AR.md is now 168/168 CRLF, while its sibling CLAUDE.md and the
inbox are LF. So the whole owner file very likely changed byte-wise. PRIMARY_ACCOUNT_INBOX.md is now mixed:
24 LF lines plus 1 CRLF line (the new row).
Fix: read with `newline=""`, detect the file's newline, and write with `newline=""` (Python 3.13: `write_text(...,
newline="")`). Add a test that LF input stays LF outside the block.

**P2-5 — fixed claims inside a report that says every figure is read from its source** (:267-268, :285, :291).
- "آخر نسخة متجرّبة … v2.2.1 (+ 3.0 live round-trip 14–15 أكتوبر)" is a literal string, not read from anywhere.
- "مصروف عليها: 0" is also a literal.
- §6 does not read the OPEN `Q-` rows of PRIMARY_ACCOUNT_INBOX.md, which has 4 OPEN items now.

Fix:
- read the verified-build line from a named file (STATUS.md, or a one-line `VERIFIED_BUILD.txt`) or drop it;
- read the spent figure from BUDGET-API.md;
- list the `| Q-… | … | OPEN… |` rows in §6.

**P3-1 — parser edge cases** (:40, :204).
- `**ACCEPTED**` and `READY — note` parse as UNKNOWN (probed).
- A `|` inside a backticked cell shifts the columns.
- An empty Assigned cell crashes `render_queue_yaml`: `''.split()[0]` → IndexError (probed).

Fix: strip `*`, also split on ` — `, and use `(r['owner'].split() or [''])[0]`. Rows whose status is UNKNOWN (BL-14,
API-500 today) appear nowhere in the report: list them under §5.

**P3-2 — first run claims "no change"** (:163-165, :259). With `prev is None` the report says
"مفيش تغيير", although there was no baseline. Fix: print "أول تقرير — مفيش snapshot سابق" when there is no previous
snapshot, and report tasks that are in `prev` but missing from `now` (removed from the BOARD).

**P3-3 — `git status` on the executor tree can take index.lock** (:96). Fix: `git --no-optional-locks status
--porcelain`, so the tool stays strictly read-only beside the executor's private-index commits.

**P3-4 — stale heartbeat reads as RUNNING** (:58-59, :300). H1 `at` = 00:46:11, still "running" at the 01:36 report
and at my later dry run. Fix: compute the age and show it in the report. Treat the heartbeat as stale above N minutes
(for example 30) and mark it `STALE`, not RUNNING.

**P3-5 — what the mirror holds** (mirror_files :233-242). The real list (61 files) is:
- every `.md/.py/.yaml/.jsonl/.txt/.patch` under 00-HQ except `intake/` and `__pycache__`;
- PROJECT_PLAN_AR.md and CLAUDE.md.

`.last-snapshot.json` and `intake/state.json` are excluded. I found no secrets or tokens (grep). The mirror does
hold staff e-mails (DECISIONS.md, STATUS.md, roles/) and executor patches. That is fine while the product repo stays
private, but the branch lives in the **product** repo: if the repo is ever made public, so is the HQ.

The filter goes by file extension only, with no size cap. Files deleted from HQ are never removed from the mirror.
Fix: add a 1 MB cap and an explicit deny list (e.g. `*.log`, `run-*.jsonl`, anything under `inbox/**/raw`). Mirror
deletions with `git rm` for files that are tracked but no longer in the list.

**P3-6 — the report cites the pass-1 SHA** (:331-338). The report and the plan block state SYNCED/VERIFIED for
a283ed66. Pass 2 (5e2e65f) is only printed. If pass 2 fails, the files on disk still say "verified". Fix: write
"snapshot SHA" in the text, or append the pass-2 state to `.last-snapshot.json` so the next report shows it.

Nothing writes into the WhyNotCut working tree. Git calls there are rev-parse, ls-remote, rev-list, status and
describe; the card's fence lists only the first three, so `describe` and `status` are worth a line in the card.
