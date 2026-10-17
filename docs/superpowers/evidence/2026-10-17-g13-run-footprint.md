<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- © 2026 The Why Not AI (thewhynot.ai) -->

# G13-RUN: the engine's footprint while idle and while working (Phase 4 T4.11)

Measured on **2026-10-17** by the API-credit lane on the owner's PC: Lenovo LOQ, i7-14700HX, 32 GB, **RTX 4060 Laptop
8 GB** (driver idle VRAM 533 MB), Windows 11. Engine: the T4.11 commit (c6e80b5) plus its three hook patches
(`cli.py` `priority.apply()`, `episode.py` release, preferences skill), in a `git archive` snapshot. A scratch engine
home under `D:\ClaudeData\Temp\wnc-p4\apilane\` (never `~/.whynot-cut`), `HF_HUB_OFFLINE=1`, test media copied from
`../whynot-test` (client "Dr Sherin Helmy", EP02 and its reel R02). Tool: `tools/footprint.py` (from T4.10), every
run through `heavy.sh` (`job` for idle, `gpu` for the jobs). The machine was shared with other sessions' test suites.
**Premiere and After Effects were not running** (the process list was checked before every run), so the VRAM headroom
with Premiere open is **not measured**. Raw rows: the lane's `work/t411/measure.jsonl` (12 rows).

## Idle `reel serve`
`reel serve --foreground`, 30 s to settle, then `footprint.py watch` for 120 s (232 samples):

| Budget | Measured | Result |
|---|---|---|
| RSS < 100 MB (mean) | 42.3 MB mean, 42.4 MB peak | **PASS** |
| CPU ≤ 0.5 % (mean, G13 "~0 %") | 0.0 % mean, 0.0 % peak, 0 samples over 1 % | **PASS** |
| `serve` is never lowered | serve and its child at Windows base priority **8 (Normal)** | **PASS** |

## Jobs (product default: no `WHYNOT_PRIORITY`, so BelowNormal)
Priority is the Windows base priority of each process in the job's tree: 8 = Normal, 6 = BelowNormal. The first
process (8) is the launcher python that `footprint.py` starts; the engine python under it lowers itself at
`cli.main` and its FFmpeg children inherit that.

| Job | Wall | Peak RSS | Peak VRAM (machine) | Mean GPU | Engine / FFmpeg priority | VRAM before → after | Process left |
|---|---|---|---|---|---|---|---|
| `transcribe --force` R02 (54 s clip) | 10.0 s | 3224 MB | 4730 MB | 50.5 % | **6** | 533 → 533 MB | none |
| same, `WHYNOT_PRIORITY=normal` | 9.4 s | 2997 MB | 4732 MB | 50.2 % | **8** | 533 → 533 MB | none |
| `preflight` R02 | 12.8 s | 436 MB | 616 MB | 0.5 % | **6** / FFmpeg **6** | 535 → 533 MB | none |
| `preview-video` R02 | 43.6 s | 1348 MB | 1187 MB | 14.4 % | **6** / FFmpeg **6** | 533 → 533 MB | none |
| `episode-transcribe` EP02 (34:41) | 160.2 s | 3290 MB | 6153 MB | 74.2 % | **6** / FFmpeg **6** | 533 → 453 MB | none |

- **VRAM released** after every job: back to the pre-job value within ±100 MB (the plan's bar), and no process left.
- **Normal under the suite / the dev PC:** with `WHYNOT_PRIORITY=normal` (what `tests/_isolation.py` sets for the
  test suite) the engine stays at 8; the unit tests check BelowNormal with fakes, and one test lowers a child python
  for real and reads its grandchild's priority (BelowNormal is inherited).
- **The reel candidates job is not measured:** the test copy has no validated reels plan (it needs a reels-plan run
  with Claude's decisions first).
- Five earlier rows in `measure.jsonl` (11:15-11:16; rows 1, 2, 4, 5 and 6) are failed setup attempts, not
  measurements: a transcript that already existed (skipped without `--force`, twice), a missing preflight, the
  episode not yet in `data/Episodes`, and no reels plan. They are kept in the raw file and left out of this table.
  Row 3 is the Whisper load/release measurement below.

## Whisper load and release (one process, large-v3 float16, 54 s decode, batch 3)
533 MB before → **4392 MB** after the load (3.2 s) → **5018 MB** peak during a 3.5 s decode (90 words) →
**634 MB after `run.release()`** → 533 MB after the process ends. `release()` gives back all but about 100 MB while
the process lives (CUDA context and allocator cache); the rest goes when the process exits.

## VRAM headroom for Premiere
Not measured with Premiere open (it was not running). With the measured VRAM constants (T4.14 evidence) and the
plan's 1536 MB Premiere headroom, `fit_batch` gives an idle 8 GB card **batch 2** for large-v3 float16; the episode
above ran with the T4.11 starting constants, which fitted batch 3. A GPU already full (from Premiere or anything
else) gives the CPU with a message, never an out-of-memory loop (unit tests with fakes).

## Not verified
- VRAM headroom with Premiere open or exporting (Premiere was not running; the host-busy signal needs H6).
- The reel candidates job (no validated reels plan in the test copy).
- Mac: idle `reel serve` RSS/CPU with `footprint.py` and `nice` 10 visible during a preview-video (Step 6) need the
  agency Mac; the `os_name="posix"` paths are unit-tested with fakes only.
