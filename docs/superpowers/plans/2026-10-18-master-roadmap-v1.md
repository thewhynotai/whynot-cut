# WhyNot Cut: master roadmap to V1 and beyond (PDR) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to carry out each stage plan task by task. Steps use checkbox (`- [ ]`) syntax.
>
> This is the **master** plan: an ordered list of stages. Each stage, when it starts, gets its own detailed TDD plan in `docs/superpowers/plans/`. Where an existing phase plan already holds the detail (Phase 4, 6, 6B, 7, 9, 10, 12), the stage points at it. The owner says only «كمل»; the next unfinished stage is always the work.

**Goal:** ship WhyNot Cut V1:
- a solid Premiere + After Effects extension with in-panel chat, one-click tools, beat sync, multicam, tracking and the Liquid Glass looks;
- installed with one click from a USB folder (Windows folder + Mac folder);
- built on everything already made for 3.0, then continued monthly.

**Architecture:**
- **One engine** (Python, `reel serve` daemon, contract v4) serves every front: the Claude Code chat, the UXP Premiere panel, the CEP After Effects panel, and later a standalone app.
- **New features** are engine commands plus contract messages, with thin panel UI on top.
- **Who builds:**
  - API lanes build the engine and test-heavy parts;
  - the Adobe session does the live host integration;
  - the executor accepts and integrates.

**Tech stack:**
- Python engine (pinned runtime locks);
- TypeScript panel-ui kit;
- UXP (Premiere 26.5+);
- CEP / ExtendScript (After Effects, and older Premiere as fallback);
- Rust/Tauri installer;
- FFmpeg; Whisper (local);
- Claude Code CLI (headless, stream-json).

**Spec:** `docs/superpowers/specs/2026-10-18-v1-premiere-panel-design.md` (F1–F12). The owner-facing context is in `Editing Plugin/PROJECT-PLAN-AR.md`, `V1-SCOPE-AR.md`, `COMPETITORS-AR.md` and `NEW-PLAN-BRIEF-AR.md`.

## Global constraints
- **Windows 11 AND macOS** for every change. The lane BRIEF section "Solid, cross-platform, no shortcuts" applies to sessions too.
- **Premiere:** UXP minVersion **26.5.0** only in V1 (owner 2026-10-18). Older Premiere via CEP comes in a later version. **After Effects:** CEP.
- **Open source; no licence/lock/pricing code in V1.** It is distributed **privately on a USB stick** (owner 2026-10-18). The repo stays private and nothing is published.
- **No code signing in V1** (owner). The unsigned-install steps are documented with screenshots.
- **Dependencies:**
  - free, pinned, available on both OSes;
  - never paid, NC or AGPL;
  - never name audited third-party projects in the repo;
  - the Source-R naming rule stays.
- **Never** write to `D:\WhyNot Clients` or edit Adobe prefs. Medical and religious sign-off stays human (the approval gates stay ON).
- **Every AI edit to a timeline:** it runs on a duplicated sequence (`<name> – WhyNot copy`), is one undo group, and is shown as a plan first.
- **API key:** OS credential store only (Windows Credential Manager / macOS Keychain); never on disk in clear; never logged.
- **Daemon:** localhost-only, a per-session token, message size caps, no run-arbitrary-script endpoint.
- **Every task:**
  - TDD (red first);
  - an independent review (lane 5 or a fresh reviewer);
  - one full suite through heavy.sh;
  - explicit-path commits;
  - the close-out rule (CLOSED only on a clean PASS).
- **Models:**
  - Opus 5.5 high for judgement, design, security, Adobe and Arabic writing;
  - Sonnet 5.5 high for routine tracks;
  - every new session is checked for the right model at start.
- **Budget:** monthly cycle. When the month's API cap gets close, the guard flips to "release cut" (Stage R). Thresholds follow the real situation, not fixed numbers.

## Review focus (failure modes no single task's tests own; each is pinned in the stage named)
1. **The editor closes Premiere, or the CLI dies, mid-job:** the original sequence is untouched; the copy is either complete or removed; the panel says what happened. (Stage 3, F1 tests)
2. **Arabic plus English mixed text, Arabic-Indic digits and long words in every new UI and render:** correct order, no broken letters. (Stages 3–7, each UI test set has an RTL case)
3. **A client folder on a path with spaces, Arabic characters, OneDrive/iCloud, or an external drive:** every new command works or refuses clearly. (Stages 4–6 engine tests)
4. **The machine is offline, or Claude is not logged in / the key is wrong:** the guided setup appears; nothing hangs. (Stage 3)
5. **Re-running any one-click tool on a sequence it already changed:** idempotent (no duplicate markers, captions or cuts). (Stages 4–6)

---

## Stage 0: Organise and start (now, 2026-10-18)
**Owner:** plan session. **Exit:** everything below is ticked.
- [ ] Remove the watchdog planning hold. ACTIVE = executor, adobe, plan. The other sessions join at their stage.
- [ ] API lanes: **3 building lanes (1, 2, 4) + lane 5 review**. Lane 3 pauses after its current run (STOP); its security items move to the BACKLOG for Stage 8.
- [ ] Lane queues: mark the non-V1 items "deferred by owner, do not start" (K-T11, K-T16, K-T15, K-T9, K-T12, K-T17, M4-T1/T4, and the Magnific BL items).
- [ ] Budget guard: its integration step becomes the **release cut** (Stage R). Lane 5's task C and the executor's part are updated.
- [ ] Send the executor this roadmap. It records Stage 1's exact open list in PROGRESS.md.
- [ ] Update `Editing Plugin/PROJECT-PLAN-AR.md` with the stage list (owner view).

## Stage 1: Close Phase 4 (Gate 4)
**Plan:** `plans/2026-10-11-3.0-phase-4.md` (and the addenda blocks).

**Owners:**
- executor (acceptance and gate);
- lanes 1, 2, 4;
- Adobe (T4.1).

**Entry:** now.

**Open work (from PROGRESS f9c38a9 and the status map):**
- [ ] T4.1 smooth zoom and fades (Adobe), plus its executor patches.
- [ ] T4.2 minors, T4.5 part B (BL-14).
- [ ] T4.3 learning loop (lane 2).
- [ ] T4.8 early warnings, then T4.15 `reel clean` on linksafe (lane 1).
- [ ] Task 25 fix (round 2) and K-T7 fix (lane 2); Task 29 emphasis (lane 2, after T4.1).
- [ ] Tasks 53, 55–60 (lane 4); the Task 54 follow-ups; the Task 52 patch applied.
- [ ] BL-01 to BL-04 (read-once hook, licence files, GPL notices, run-state/resume).
- [ ] Accept the committed work: T4.9, Tasks 23, 26, 28, 54.
- [ ] Owners for the out-of-lane suite failures: installer r5_1 (installer track); identity gate (executor); `serve/security.py` (Adobe).
- [ ] **BL-15 lead-step approval token** (Gate 4; executor design in PROGRESS d1b3009): the engine-side fix for the subagent guard hole. Together with the guard commits it forms the Gate 4 security line. **L-T8, the engine write gate, stays at Gate 5** (Stage 8).

**Exit (Gate 4, as in the phase plan):**
- independent review 0 Critical / 0 Important;
- full suite 0 failures (snapshot);
- `validate --strict` ×2;
- evals (bulk grading on the Batch API);
- **full** macOS CI;
- live PODCAST-TEST check;
- security line;
- T4.14 budgets;
- PROGRESS + gate record;
- tag `v3.0.0-p4`.

After the tag, the K1 safety switches turn on.

**Deliverable to Yunus:** the Gate 4 tag report; the release cut after it is made in the attended sessions, one at a time (owner 2026-10-18).

## Stage R: Release cut (recurring; first one at the October budget limit)
**Trigger:** the budget guard flips (the month's API cap is near), or a stage's exit gate passes.

**Owners:**
- lane 5 (close-out, release notes draft);
- executor (accept, push, build);
- plan session (report).
- [ ] Lanes finish or park their current task (the existing integration mode); lane 5 writes `API-PAUSE-HANDOFF.md`.
- [ ] The executor accepts and pushes what is ready, then runs:
  ```
  python tools/release.py handoff --out "<Editing Plugin>/Releases/<version>"
  ```
  That builds:
  - `Windows/` — the plugin zip and the shipped Adobe parts;
  - `Mac/` — the repo clone and `دليل-الماك.md`;
  - `WHAT-WORKS-NOW-AR.md`, which says what works, what is new, and what is not verified.
- [ ] The plan session checks both folders open and install on this PC (the Windows path) and tells Yunus where they are.

**Exit:** `Releases/<version>/Windows` and `Releases/<version>/Mac` exist, are built from a clean clone, and are reported.

**First cut (October): CANCELLED by the owner (2026-10-18).** The whole remaining October API limit goes to closing Gate 4. Phase 4 has no deadline; quality first. At the budget switch (now about 100 USD left) the lanes finish and get reviewed their current task, lane 5 writes the pause handoff, and no release is built. Release cuts are made later, one at a time, in the attended sessions.

## Stage 2: Plan the V1 build (start of November, once the new monthly cap is available)
**Owner:** executor (Opus). **Entry:** Stage 1 tag, or the 1st of the month.
- [ ] Write the detailed TDD plans for Stages 3–9: files, interfaces, tests. Reuse the Phase 6 / 6B / 7 / 10 plan tasks wherever they already specify the work (T6.1–T6.16, E-T*, B-T*).
- [ ] Load the BACKLOG with the engine-side items (`[V1]` tag), each with its owned files, and register them in LOCKED-AREAS.
- [ ] Wake the sessions needed for Stage 3 with the right models.

**Exit:** the stage plans are committed, the BACKLOG is filled, and the plan session has reported to Yunus.

## Stage 3: Panel foundation: chat, status and the install skeleton (spec F1, F10, F11-skeleton)
**Owners:**
- Adobe (UXP and CEP panels, live);
- lanes (chat bridge, contract messages, credential store, tests);
- installer track (skeleton).

**Existing work to build on:**
- the daemon and contract v4 (T6.1 / T6.2, done);
- the panel-ui kit and mockups;
- the UXP spike (`dist/uxp/WhyNotCut-Spike.ccx`);
- CEP bridge 3.1;
- installer Tasks 1–9.
- [ ] The daemon chat bridge: runs `claude -p --output-format stream-json` with the plugin, `cwd` = the client folder, and relays events. A CLI crash leaves the original untouched (Review focus 1).
- [ ] Auth: the user's login, OR an API key in the OS credential store. The guided setup when neither works (Review focus 4).
- [ ] The UXP Premiere panel shell: the chat pane, approval buttons and the status light. RTL (Review focus 2).
- [ ] The CEP After Effects panel shell; T6.3 / T6.8 (signed-or-self-signed ZXP, PlayerDebugMode OFF).
- [ ] The copy-sequence + single-undo wrapper for every timeline edit (T6.6 approval safety, fingerprint).
- [ ] The installer skeleton: installs the engine, the plugin and both panels per user; uninstall.

**Exit:**
- a raw-clip job and a podcast reels-plan job run end to end from the panel chat, on Windows (live) and with the macOS CI green;
- independent review clean.

**Deliverable:** a Stage R cut, «أول نسخة فيها شات جوه Premiere».

## Stage 4: One-click tools (F2, F3, F3b, F10)
**Owners:** tools track (Sonnet; host glue), Adobe (live), lanes (engine tests).

**Existing:** the Kalam / Hush / Tidy engines (Phase 6B port, Kalam fix rounds), Task 25 proposals, K-T7 takes.
- [ ] Kalam tab: captions to a track (MOGRT/text), SRT export, words per card, one-word mode.
- [ ] Hush tab: silence and filler detection with a sensitivity slider, results into the cut review list.
- [ ] The cut review list: each row has a timecode, ▶ preview, a checkbox and the reason. Meaning-different takes are never pre-ticked. Apply on a copy, as one undo.
- [ ] Tidy tab: a plan first, then the bins; never moves files on disk.
- [ ] F3b client rules card + learning from the review list and from hand edits on the built copy (builds on T4.3; owner 2026-10-18).
- [ ] Buttons: safe-zone preview, search-to-word, chapters.
- [ ] Idempotency tests (Review focus 5) and odd-path tests (Review focus 3).

**Exit:** each tab works on a real clip on Windows, the macOS CI is green, review clean. **Deliverable:** a Stage R cut.

## Stage 5: Captions and audio (F4, F5)
**Owners:** looks track (Opus), lanes, Adobe.

**Existing:** Task 23 (8 caption looks), Task 28 (recommender), the audio-clean pipeline, T4.14 precision.
- [ ] The caption look gallery: preview stills, per-sentence or whole-sequence apply, apply to all. Stills match the rendered frames (QC).
- [ ] Non-destructive audio: the cleaned track goes above the original (the original is muted); per-platform loudness targets; A/B measured.
- [ ] Dialect picker (Egyptian, Gulf, Levantine, Maghrebi, MSA, English): primes Whisper; measured WER per dialect goes into the external doc.

**Exit / deliverable:** as in Stage 4.

## Stage 6: Beat sync, multicam, tracking (F6, F7, F8)
**Owners:** lanes (engine: Opus for design, Sonnet for routine), Adobe (host operations).
- [ ] Beat sync:
  - local beat detection (a licence-clean library, e.g. librosa ISC);
  - Premiere markers, plus optional snapping of cuts or captions;
  - AE shake / zoom / flash on beats;
  - ±1 frame on the reference set; idempotent.
- [ ] Multicam:
  - 2–4 cameras, audio cross-correlation sync (reuse Tidy's podcast sync);
  - speaker-based switching plan with a minimum shot length and a wide shot on overlap;
  - review, then build as a copy;
  - ≤1 frame sync; late-start and early-stop cameras.
- [ ] Tracking:
  - the user draws a box;
  - a local tracker (OpenCV, Apache-2.0/BSD) produces positions;
  - Position (and Scale) keyframes on the chosen overlay;
  - low-confidence frames flagged; re-anchor a frame;
  - ≤8 px at 1080p on the reference clips; works on 4K and vertical.

**Exit / deliverable:** as in Stage 4.

## Stage 7: Liquid Glass and the AE looks (F9)
**Owners:** looks track (Opus), Adobe.

**Existing:** AE motion pipeline, AE scenes wave 1 (BL-13 patch), the R-6.x look system plan.
- [ ] A Liquid Glass family for cards, captions and titles, from native AE effects only. Arabic RTL. Contrast check over busy backgrounds.
- [ ] Exposed in the AE panel and in the caption look gallery.
- [ ] AE scenes wave 1 (BL-13), finished.

**Exit:** renders on both OSes, frame QC passes. **Deliverable:** a Stage R cut.

## Stage 8: Hardening (Phase 8 structure review + security + Phase 9 live QA)
**Owners:**
- executor;
- lane 3 (resumes for security);
- lane 5;
- Adobe for the live E1–E20+ scenarios.

**Existing plans:** Phase 8 and Phase 9 (T9.2), Addendum L.
- [ ] Security items: L-T8 (the engine write gate), L-T4, L-T5, L-T6, L-T16, L-T17; L-T10 fuzzing rework; the daemon auth tests; a red-team review (H32 needs the owner's OK before it runs).
- [ ] Structure, code and security reviews: 0 Critical / 0 Important.
- [ ] Windows live end-to-end on a full episode, fault injection, a soak run, and a timed edit (G-04).

**Exit:** the Phase 8 + 9 gates (Windows). **Deliverable:** a Stage R cut, release candidate.

## Stage 9: The V1 USB package and the docs (F11 complete, F12)
**Owners:** installer track (Opus), guide track (Opus, Arabic), plan session.

**Existing:** the installer track (Tauri app, Tasks 1–9), the 69-page Arabic guide PDF, `release.py handoff`.
- [ ] One-click installers:
  - `Windows/WhyNotCut-Setup.exe`;
  - `Mac/WhyNotCut.dmg` (or `.pkg`);
  - models copied from the stick (`models/`); no download;
  - `reel doctor` at the end;
  - uninstall;
  - re-install keeps client data.
- [ ] The external Arabic doc (`اقرأني-التسطيب.pdf` + the user guide): install with the unsigned-app steps and screenshots, the first job in 10 minutes, every tool, FAQ, WhatsApp support, and the API-key guide.
- [ ] The internal doc: architecture, building the USB folder, development, the release cycle.
- [ ] The final layout:
  - `Editing Plugin/Releases/V1/Windows/` and `.../Mac/` — the folders that go on the USB stick;
  - `Editing Plugin/Releases/V1/models/`.

**Exit:** clean Windows and clean macOS accounts install offline in under 10 minutes from the folders. **Deliverable: V1 on USB.**

## Stage 10: Real-world test and the Mac live test (Phase 12)
**Owners:** Yunus and the editors (real client clips), executor, plan session.
- [ ] Yunus and the editors run V1 on real client work. Findings go to `MAC-INBOX.md` / the feedback file and are fixed in the next monthly cycle.
- [ ] The agency Mac live test (H18): zero core-job failures on the Mac, and the Windows suite still passes.

**Exit:** the Phase 12 gate; V1 is used daily at the agency.

## Stage 11+: Later versions (monthly cycles; each one starts at Stage 2's pattern)
In this order unless the owner reorders:
1. Our own API connection (owner).
2. The standalone app (.exe/.dmg) on the same engine and UI kit.
3. Magnific (Phase 5; BL-05 … BL-12).
4. Client branding from a website (Addendum J; J-T1/T2 already committed).
4b. A CEP panel for Premiere older than 26.5.
5. The K extras: topic search, beat-synced montage generation, the DaVinci export, cover readability, the signed decision log.
6. Licensing and signed updates (`Editing Plugin/SAVED-LATER-licensing-updates-AR.md`), code signing, distribution.
7. Other model providers.

---

## Who runs what (standing)

| Who | Model | When |
|---|---|---|
| Executor | Opus 5.5 high | Always (acceptance, gates, shared files, stage plans) |
| Plan session | Opus 5.5 high | Always (order, reports, the watchdog) |
| Adobe / panels | Opus 5.5 high | Stages 1, 3–8 |
| Tools | Sonnet 5.5 high | Stage 4 |
| Looks / motion | Opus 5.5 high | Stages 5, 7 |
| Installer | Opus 5.5 high | Stages 1 (r5_1 fix), 3, 9 |
| Guide | Opus 5.5 high | Stage 9 |
| wnc-queue | Sonnet 5.5 high | Only if the heavy.sh runner needs work |
| API lanes 1, 2, 4 | per step (Opus design / Sonnet routine) | Every stage's engine and test work |
| API lane 3 | Sonnet / Opus | Stage 8 (security) |
| API lane 5 | Opus | Reviews, BACKLOG refill, release cut |

At most 4–5 sessions at once (RAM). The watchdog's ACTIVE list follows the current stage.
