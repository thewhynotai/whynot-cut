# Adobe track against Addendum G2/G10: reliability, speed and fault gaps

Date: 2026-10-14. Method: a read-only code analysis, with no tests or live runs. The `file:line` references point at
`release/3.0` @ 17314a5.

**Summary:**
- R1 (undo or backup) holds only on the CLI build path.
- R2 (crash and reboot) and the speed budgets have structural gaps.
- Two of those gaps can cost user work today.

## R1: one-step undo or a backup

| Item | Today | Gap | Fix |
|---|---|---|---|
| `build_project`, CLI | Old .prproj renamed `_prev_*`; restored if nothing was claimed (`ppro_build.py:341-364`) | no | — |
| `build_project` via `reel serve` | `app.newProject(path)` over the existing file, no backup (`wnc_ppro_lib.jsx:240-241`). The error text says "kept as a backup" (`contract/cep.py:133`), which isn't true here | **yes** | Route it through `ppro_build.build` (lock, dirty check, `_prev_`), or refuse `overwrite_existing:true` from serve |
| `_prev_` stills | `stage_stills` keeps only 2 still folders (`ppro_build.py:199-200`), so older `_prev_` projects go offline | yes | Keep stills per backup, or prune them together |
| `ae_build_motion`, CLI | Backup only when the editor changed the .aep (`motion_build.py:243-246`) | minor | Always copy the .aep to `backups/` before overwriting |
| `ae_build_motion` via serve | No `editor_changed` check; a clean editor .aep is overwritten (`wnc_ae_bridge.jsx:169-180`, `wnc_motion_lib.jsx:593`) | **yes** | Route it through `motion_build.build` |
| AE extras `WNC.build` / mogrts | The undo group wraps `newProject`, so it has no effect. No backup or dirty check before overwriting `_GFX.aep` (`wnc_ae_lib.jsx:490-519, 602-632`; `ae_builder.py:198`) | yes | `mayDiscard` check plus an .aep backup |
| UXP ops | None of them change the project; a one-step `transact()` is ready (`transaction.ts`) | no | — |
| Leftover JSX actions | `close_project` with `save:false` discards (`wnc_ppro_lib.jsx:586-590`); `test_crop` and `new_project_import` can be reached from the queue | yes | Delete them, or gate them behind `WHYNOT_BRIDGE_DEV` |
| Kalam / Hush / Tidy | Reserved, not routed (`router.py:85-88`) | n/a | Phase 6B: each write is one undo group |

## R2: crash and reboot

| Item | Today | Gap | Fix |
|---|---|---|---|
| Premiere/AE dies after claiming a job | The engine stops checking the heartbeat once a job is claimed and waits 900 s (`cep_queue.py:377-379`) | **yes** | While claimed, check every 2 s; if the host is dead or `current≠jid`, return a `host_lost` result at once |
| Bridge restart | Orphaned `*.running` jobs are ignored and only noticed after about 21 min (`cep_queue.py:98-108`) | yes | At start, write `{ok:false, error:"interrupted"}` for each orphan (`bridge.js:361`) |
| Result write fails (disk full) | The job is deleted with no result, and the engine waits until timeout (`bridge.js:164-167`) | yes | Retry, then write an error marker; the engine treats a vanished `.running` with no result as a failure |
| Panel reconnect or close | The session's command tasks are cancelled (`app.py:644-650`) while Premiere keeps going. The result is dropped, the panel shows "lost" (`daemon-source.ts:799-803`), and Try again builds twice | **yes** | Don't cancel CEP tasks when a session ends. Keep a job journal `<home>/serve/jobs/<rid>.json`; the snapshot carries `jobs[]`, and the panel reattaches by request_id |
| Daemon crash | In-flight state is held only in memory (`router.py:62`), so a finished id can run again | **yes** | The same journal. At start, reconcile with the queue files; on a repeated id, replay the stored result |
| Engine crash mid-build | `_prev_` stays parked; the next run refuses and explains how to fix it (`ppro_build.py:229-245`) | no | — |
| Reboot | The build lock is taken over by pid + start time (`cep_queue.py:405-422`) | no | — |
| Engine auto-restart | Tries every 30 s and gives up for good after 5 failures (`bridge.js:180, 247`) | yes | After that, keep retrying slowly (every 5 min) |
| Long clip | Fixed 900 s timeout (`ppro_build.py:347`) and a 20 min bridge timeout (`bridge.js:121`) | yes | Scale the timeout with `duration_s` and use heartbeat liveness |

Nothing resumes mid-job. "Restart safely" (the journal above) is the reachable bar.

## Speed budgets S1–S3

Polling, from the code:

| Component | Interval |
|---|---|
| Bridge queue tick | 1 s |
| Bridge engine check | 30 s |
| Engine result poll | 0.5 s |
| Pre-claim status check | 2 s |
| Panel snapshot poll | 2 s |
| Panel hello timeout | 5 s |
| Panel reconnect | 1→15 s |
| Daemon engine-state read timeout | 3 s |
| UXP keepalive | 20 s |

| Budget | Risk | Hooks |
|---|---|---|
| S1: open → usable ≤ 1.5 s | **yes.** A snapshot can take up to 3 s; there is no push, so a change can be up to 2 s late; with the engine down, recovery can take about 45 s | `panel.boot` (main.ts), `panel.first_paint`, `panel.usable` (mount.ts:446), `link.welcome`, `link.first_state` |
| S2: click → paint ≤ 100 ms | medium. Every paint is a full `innerHTML` re-render plus a 200-line log sort (mount.ts:97-163) | `ui.click` (mount.ts:288) → `ui.paint` (mount.ts:163) |
| S3: first progress ≤ 2 s | **yes.** CEP jobs emit no progress (adapters.py:146); the panel shows "running" for up to 15 min | Synthetic `queued` / `claimed` / `elapsed` (every 2 s) progress from FileQueueAdapter; marks `cmd.received`, `cmd.queued`, `cmd.claimed`, `cmd.first_progress`, `cmd.result` |

**Measurement:**
- Both sides append local JSON lines to `<home>/logs/perf.jsonl`, with no telemetry:
  - engine side: `serve/perf.py`;
  - panel side: UXP fs, also included in Copy diagnostics.
- `reel perf-report --since` computes p95 against the budgets and exits 1 on a miss.
- Gate 6 runs it.

## Fault injection

| Fault | Today | Gap |
|---|---|---|
| No internet | Everything is localhost | OK |
| Premiere closed mid-job | The job hangs for 15 min, the backup stays parked, an orphaned `.running` is left, and the panel loses the job | **gap** (R2 fixes) |
| Disk full | No work is lost, but the message is wrong; there's no free-space check; serve says only "engine failed (OSError)" | **gap**: free-space check, plain ENOSPC message |
| Missing font | AE refuses with a how-to; Premiere warns | OK |
| Missing model | Not on the Adobe path | engine track |
| Claude not signed in | The pill is hard-coded "unknown" (messages.py:110); Start-engine only writes a log line (mount.ts:375-381) | **gap** (Claude-link / installer track) |
| Corrupt clip | ok:false "sequence not found after XML import" | OK; the message doesn't name the clip |
| Very long clip | Fixed 900 s with no progress | **gap** (R2/S3) |
| Arabic / space paths | Spaces work. `% ! ^ & \| < > "` in the engine home blocks auto-start, shown only in the heartbeat. Arabic paths not verified through evalScript, the cmd launcher or QE export | **gap**: fixture or live test, and show it in the panel |

## Prioritised fixes and owners

| P | Fix | Files | Owner |
|---|---|---|---|
| P0 | Serve build routes go through `ppro_build` / `motion_build`; fix the false backup text | serve/adapters.py, contract/cep.py (Adobe) + ppro_build/motion_build entry points (executor-owned) | Adobe track, plus executor hunks |
| P0 | Liveness check after claim; `interrupted` results for orphans | cep_queue.py (executor-owned), bridge.js (Adobe) | Adobe track, plus executor hunk |
| P0 | Job journal, reattach, idempotent replay; CEP tasks are not cancelled on session end | serve/*, panel daemon-source.ts (Adobe) | Adobe track |
| P0 | Synthetic CEP progress (S3) | serve/adapters.py, cep_queue.py | Adobe track, plus executor hunk |
| P1 | Disk full: bridge result marker, free-space check, plain message | bridge.js, ppro_build/motion_build | Adobe track, plus executor hunks |
| P1 | Timeout scaled to clip length | ppro_build.py, bridge.js | Adobe track, plus executor hunk |
| P1 | Perf hooks + `reel perf-report` | serve/perf.py, panel; `perf-report` in cli.py (executor) | Adobe track, plus executor CLI hunk |
| P1 | Snapshot read timeout < 1.5 s, or push state | serve/app.py, engine_state.py | Adobe track |
| P1 | Remove or gate the leftover JSX actions | wnc_ppro_lib.jsx | Adobe track |
| P1 | Always back up the .aep | motion_build.py | executor |
| P2 | Stills pruning vs `_prev_`; AE extras dirty check; slow-retry engine auto-restart; Arabic-path test; S2 re-render cost | various | mixed |
| — | Claude-not-signed-in pill + Start-engine launcher | Claude-link / installer | other tracks |
| — | Missing models | engine | other track |
| — | One-step undo for Kalam/Hush/Tidy writes | Phase 6B | other track |
