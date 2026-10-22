# SETUP BASELINE — recovery checkpoint for the AI-infrastructure restart

- Taken: 2026-10-22 03:57 Cairo, Phase 0, main seat. Read-only for the product: no commit, branch, push, stash,
  reset or checkout was made in any repo.
- **Important:** the system was live while this was taken (SETUP_AUDIT F1). The checkpoint is a consistent copy of
  git objects and refs, plus a point-in-time copy of uncommitted files; work that running sessions write after 03:58
  is not in it.

## 1. Where it is

`D:\ClaudeData\backups\setup-phase0-20261022-0357\` (on D, outside every repo and outside TEMP). 235 files, 68.8 MB.
Integrity list: `SHA256SUMS.txt` in that folder. Older baselines are kept as they are:
`D:\ClaudeData\backups\2026-10-20-baseline\` (D-003) and `D:\ClaudeData\backups\omc-preflight-20261022-0326\` (OMC).

| Path in the backup | Content | Verified |
|---|---|---|
| `git/whynot-cut-all.bundle` | `git bundle --all` of `WhyNotCut` (every local branch, tag and remote-tracking ref) | `git bundle verify` → **okay**; contains `refs/heads/release/3.0` |
| `git/refs.txt` | every ref with its SHA at 03:57 | — |
| `git/worktrees.txt` | `git worktree list --porcelain` (12 worktrees) | — |
| `git/main-checkout-tracked.patch` | `git diff --binary HEAD` of the main checkout (19 modified files) | 120 KB |
| `git/main-checkout-untracked.tar` | the 23 untracked files/folders (`--exclude-standard`) | 297 KB |
| `git/main-checkout-status.txt` | `git status --short` | 42 lines |
| `worktrees/*.patch`, `*.status.txt`, `summary.txt` | diffs of the dirty worktrees: `D:\WNC-work\h1` (9), `Temp\bl24-f3` (8), `bl24-mut3` (14), `fix3-wt` (10), `t26r6-wt` (4) | summary lists all 12 |
| `worktrees/*.untracked.tar` | untracked files of those worktrees (h1 1, bl24-f3 1, bl24-mut3 2), added ~04:15 after review | in SHA256SUMS (238 lines) |
| `files/00-HQ/` | full copy of 00-HQ (no `__pycache__`); 0 links found before copying (`dir /AL /S`) | robocopy `/XJ` |
| `files/project-dot-claude/` | `Editing Plugin/.claude` | |
| `files/root/` | every `.md` and `.cmd` at the project root (PROJECT_PLAN_AR.md, CLAUDE.md, …) | |
| `files/config-*` | global `CLAUDE.md`, `settings.json`, `installed_plugins.json`, `known_marketplaces.json`; h1/h2 `settings.json`; h1 `CLAUDE.md` | no credential file copied |

## 2. Baseline state (the numbers to compare against)

| Item | Value at 03:57 |
|---|---|
| `release/3.0` | c963132 local · 322d8a5 on GitHub (local ahead 114) |
| `main` · `ops/hq` | 4831de5 · 1b1c836 (both = GitHub) |
| Off-PC backup of 3.0 | GitHub `ops/backup-release-3.0-20261020` = 4c1e59c |
| Latest tag | `v3.0.0-p3.1` |
| Installed plugins (main seat) | superpowers 6.4.2 · whynot-cut 3.0.0 · cloudflare 1.0.2 · karpathy 1.0.0 · experiment-coach · plugin-dev af59ee3a (project) · oh-my-claudecode 5.7.6 (projects `omc-pilot`, `omc-lab`) |
| Global `~/.claude/CLAUDE.md` / `settings.json` | copies in `files/config-*` (hashes in SHA256SUMS) |
| Enabled automation | 3 routines + 1 one-time task; 3 Windows tasks; Startup lanes script; helper `AUTO-ON` ×2 |
| Free space | C: 201 GB · D: 235 GB |

## 3. How to restore (copy-safe; never through junctions)

1. **Check first:** `certutil -hashfile <file> SHA256` against `SHA256SUMS.txt` for the file you need.
2. **Lost commits or branches:** in a **fresh clone outside the shared repo** (e.g. `git clone <bundle> D:\ClaudeData\Temp\restore-clone`; never from the main checkout or its worktrees, which share one `.git`), `git fetch "D:\ClaudeData\backups\setup-phase0-20261022-0357\git\whynot-cut-all.bundle" "refs/heads/*:refs/remotes/phase0/*"`, then inspect `phase0/<branch>` and recover with a new branch. Do not `reset` a shared checkout.
3. **Lost uncommitted work in the main checkout:** on a clean worktree at c963132, `git apply --binary main-checkout-tracked.patch`, then `tar -xf main-checkout-untracked.tar` from the repo root. Same for a worktree patch (base = that worktree's HEAD in `worktrees.txt`).
4. **00-HQ or project config:** copy back the single file you need from `files\` (robocopy `/XJ`, copy, never `/MOVE`). Compare with the live file first; the live system keeps writing to 00-HQ.
5. **Global Claude config:** copy the single `files\config-*` file back with Claude closed. Names are flattened:
   `config-C__Users_LOQ_.claude_settings.json` → `C:\Users\LOQ\.claude\settings.json` (same pattern for the others;
   `D__ClaudeData_accounts_h1_…` → `D:\ClaudeData\accounts\h1\…`). `~\.claude` is a junction to `D:\Claude\dot-claude`:
   copy the file in, never robocopy or delete the folder.

## 4. Not covered by this checkpoint

- An off-PC copy of the 114 unpushed commits (F3). Pushing is outward-facing and belongs to the executor's flow
  (D-003 did it with an `ops/backup-*` branch); proposed as a Phase 1 step, needs the owner's yes.
- The helper profiles' transcripts and sessions, the app's own data, client folders, `D:\Claude\whynot-cut-home`
  runtimes (re-creatable by the installer), and `D:\ClaudeData\accounts` scripts (their `.bak-*` copies exist in place).
