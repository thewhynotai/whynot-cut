# WhyNot Cut: feature → UI coverage map

Date: 2026-10-18. Owner: UI track (subscription session, owner request 2026-10-18: "design, extension and panel in
parallel, so every feature gets its place in the UI as it is built"). Status: **draft 2** (fresh Opus review
PASS-WITH-FIXES; every P1/P2 fixed), written from the sources below on `release/3.0` at a2554ae. The screen columns describe the screens
COMMITTED at a2554ae (40 screens, 505 states) plus the UI track's batch 1 (P-23 chat, P-24 episode and reels, P-26
client rules, and the Phase 4 states of P-05 / P-06 / P-07 / P-10), committed with this update after its renders and
its designer review (`designed (batch 1)`).

Sources:
- the `reel` CLI: `whynot-cut/engine/reel/cli.py` `CORE_COMMANDS` (:1532), `lib/podcast_cli.py`, `lib/motion_cli.py` (75 subcommands);
- contract v4: `whynot-cut/engine/reel/contract/session.schema.json`, `protocol.json`, `serve/app.py:554-622`,
  `adobe/panel-ui/src/{session,source,contract}.ts`, `docs/adobe/eng-data-contract.md`;
- the skills (`whynot-cut/skills/*/SKILL.md`), the Phase 1–4 plans, Addenda A–M, the podcast-mode and motion-from-audio specs;
- the V1 panel spec `docs/superpowers/specs/2026-10-18-v1-premiere-panel-design.md` (F1–F12) and the master roadmap
  `docs/superpowers/plans/2026-10-18-master-roadmap-v1.md`;
- PROGRESS.md (status truth) and the 2026-10-18 owner decisions (K-T8 cancelled → manual verse slot; J deferred);
- the design system `adobe/panel-ui/design/` (40 screens, 505 states) and `docs/design/screen-inventory.md`.

## 0. How to read this map

**Columns.** Feature · engine command · contract v4 message(s) · panel screen · UI state · stage · notes.

**Panel screen** names an existing file under `adobe/panel-ui/design/screens/` (`P-07` = `P-07-approval.html`), with the
state that shows the feature when only one state does (`P-10/older`). A feature counts as covered when an existing
screen or state shows it. **MISSING** = no screen or state shows it; **PARTIAL** = a screen exists but does not show
this feature's own data or decision. A proposed new screen is written `NEW P-2x`; a proposed new state `+state`.

**Contract v4.** `state` = read-only, inside the pushed `panel_state`; `intent` = one of the three panel intents
(`approve`, `request_changes`, `rebuild`), all of which the daemon answers today with `ok:false` "not available from
the panel yet" (`serve/app.py:123-127, 603-612`); `host:<action>` = a host action inside `command`; **NONE** = no
message exists. Gap ids `C-n` point to §3.

**Engine command.** A name in backticks is a registered `reel` subcommand. **NOT REGISTERED** = the module exists but
`reel` has no such verb yet (its CLI hook is pending). **NOT BUILT** = neither the verb nor the module exists yet.
**K1 switch off** = the behaviour is built and checks a `config/defaults/safety.json` switch that stays off until the
Gate 4 tag; a screen must not assume it before then.

**UI state** (the highest reached; each implies the ones before):
- `designed`: a mockup screen/state exists, rendered AR/EN at 300/360/480 and reviewed;
- `built`: panel code (`adobe/panel-ui/src`, `adobe/premiere-uxp/src`) renders it from `PanelState` / contract data;
- `unit-tested`: that code has `node --test` cases that run without Premiere;
- `live-tested`: seen working in real Premiere/AE (evidence file named).

**Stage** = roadmap stage: S1 = Gate 4 (Phase 4), S3 = F1/F10/F11 skeleton, S4 = F2/F3/F3b, S5 = F4/F5, S6 = F6–F8,
S7 = F9, S9 = USB + docs, later = Stage 11+. `base` = a 2.x/3.0 flow that already works through Claude chat.

## 1. Headline gaps (read this first)

Written against the screens at a2554ae. **Batch 1 (UI-P4) designs** the screens for gaps 2–6 and part of 8: P-23 chat,
P-24 episode and reels, the review domains and the verse slot on P-07 / P-10, P-26 client rules, removed-review,
risky words, autopilot and the intake warnings. Gap 1 (no wire) and gap 7 (the cut review list, NEW P-27, Stage 4) stay.

1. **The panel cannot run anything yet.** No panel-originated contract v4 message runs any of the 75 `reel` commands
   (a `command` / `build_project` sent through `reel serve` does run the engine's build, but only from the CLI side). The
   three panel intents are stubbed. No chat / `claude -p stream-json` message exists, and `connection.claude` is
   hard-coded `unknown`. Every row below whose contract column is NONE or `intent (stub)` is a screen with no wire.
   This is Stage 3 work (chat bridge, intents), owned by the executor + Adobe track; the UI track builds against
   fixtures until then (§4 A-4).
2. **No chat screen exists.** F1 (in-panel chat, step cards, Approve / Change / Stop buttons, status light) is the
   V1 centrepiece and has no mockup. → NEW P-23.
3. **No podcast screens exist.** Episode sheet, reels plan (Gate 0 pick), reels preview and the publish package run
   only through Claude chat today. → NEW P-24 (episode + reels plan) and NEW P-25 (publish package, later).
4. **Review domains beyond medical/religious are not drawn.** P-07 and P-10 show only medical and religious flags with
   "the doctor or the sheikh". Addendum M adds business (owner or legal adviser) and AI disclosure (client), each with
   its own approver role and verdict (`needs-approval`, `needs-evidence`, `needs-disclosure`). → +states on P-07/P-10.
5. **The manual verse slot (owner 2026-10-18) has no UI.** → +state `verse` on P-10 and a line in P-06 `done`.
6. **Client rules (T4.3 / F3b) has no screen.** → NEW P-26.
7. **The cut review list (F3: Task 25 proposals, K-T7 takes, Hush) has no screen of its own.** P-16 is Hush-only. → NEW
   P-27 (S4; designed after the Phase 4 batch).
8. Smaller: removed-review (K-T2) has no button; the risky-words-first block (K-T1) is only the `long` state of P-10;
   autopilot (T4.7) has no running/stopped look; intake warnings (T4.8) are not in P-05; `reel clean` (T4.15) is only
   partly drawn (P-21 `remove-confirm` covers model removal); the caption look gallery (F4), audio/dialect (F5), beat/multicam/tracking (F6–F8), Liquid Glass (F9) and
   the F10 buttons are all MISSING (their stages are later).

## 2. The map

### 2.1 Phase 4 / Gate 4 features (S1 engine; UI designed now, wired in S3/S4)

| Feature | Engine command | Contract v4 | Panel screen | UI state | Stage | Notes |
|---|---|---|---|---|---|---|
| Autopilot + one checklist (T4.7) | `auto-approve` (LEAD), `needs-you --write` | NONE (C-3); approval shows in `state.approval` | P-22 (approval setting), P-06 `autopilot`, `autopilot-stopped`, P-10 | designed (batch 1) | S1 → S3 | MISSING: a run in `approval: auto` (badge "approved automatically", `by:"auto"`), the stop at QC while a medical/religious line is open. → +states `autopilot`, `autopilot-stopped` on P-06 |
| NEEDS-YOU list (T4.7) | `needs-you --write` → `output/needs-you.json` | NONE (C-4): no `needs_you` field in `panel_state` | P-10 (+ `verse`, `risky`, `domains`, `podcast` states), header badge G3 | designed (batch 1) | S1 → S3 | engine kinds (`lib/needs_you.py:52`): pick, words, medical, religious, music, fonts, logo, website, final. P-10 draws rows words, claim, music, fonts, render, restart, plus `plan` (in the `older` state only) and `numbers` (in the `long` state only). MISSING rows: `pick` (Gate 0, not plan approval), `logo`, `website`, business, AI, verse (gaps 4, 5). Engine issue (UI track, 2026-10-18), confirmed by the executor: a business or AI review row is filed under `medical` with the doctor as approver (`needs_you.py:406`); its fix and the `verse` / `business` / `ai` kinds in `needs-you.schema` are in the manual-verse build scope Batch 1 draws `pick` and `logo` rows (P-10 `podcast`), business / AI rows (`domains`), verse rows (`verse`); `website` stays with the deferred Addendum J. |
| Manual verse slot (replaces K-T8, owner 2026-10-18) | executor-owned engine part, NOT BUILT (`lib/manual_verse.py` + plan/needs_you hunks; brief `D:\ClaudeData\claude-api-lane\work\manual-verse\BRIEF.md`): no captions or graphics in a recited-verse span, a timeline marker, one NEEDS-YOU line per span (`who: editor`) | NONE (C-4) | P-10 `verse`, P-06 `done-verse` | designed (batch 1); fixture field names provisional until the executor's manual-verse commit | S1 engine; panel wire S3 (C-4) | marker name final: «آية: يضيفها المونتير يدويًا»; NEEDS-YOU line «أضف الآية يدويًا من مصحف موثوق ودقّق التشكيل» with the source timecode; a guessed end (12 s cap) says so. The marker comment holds only the source timecodes and the cue phrase that opened the span (e.g. «بعد: قال تعالى»). No surface (marker, NEEDS-YOU, edit-plan, logs, P-10 rows) ever shows the span's transcript words: a misheard verse must never be written where it could be copied. The plugin never writes Quran text, not even in mock data: the P-10 `verse` fixture rows carry only the timecode, the cue phrase, the fixed line and the guessed-end flag. "Go to the marker" seeks only, and only if UXP proves it (else meta text). Until C-4 the editor sees the line in `output/NEEDS-YOU.md` through chat. + a count line on P-06 `done` |
| Risky words first (K-T1) | `transcript-verify`; with the K1 switch `k_t1_plan_block` on, `plan` refuses a graphic that shows an unconfirmed high-risk word (`lib/plan.py:909-913`; K1 switch off) | NONE | P-10 `risky` (+ the `words` and `numbers` rows) | designed (batch 1) | S1 | MISSING: the "check these first" block with dose / drug / negation / number reasons and Arabic-Indic digits as spoken. → +state `risky` on P-10 |
| Review flags as data (T4.13) | `review-flags --from -` | `state.approval.flagged` (medical/religious only) | P-07 (flagged lines), P-10 `claim` row | built + unit-tested (render.ts approval card); P-07 designed | S1 | `flagged` spans need `01_analysis/sensitive-review.json` (eng-data-contract §4) |
| Review domains: medical, religious, business, AI (M1-T1/T2/T3) | `review-scan` **NOT REGISTERED** (`lib/review_domains.py`), `review-flags` | NONE (C-5): no domain, verdict or approver role field | P-07 `domains`, `domains-checked`; P-10 `domains` | designed (batch 1) | S1 → S3/S4 | verdicts `needs-approval` / `needs-evidence` / `needs-disclosure`; approver per domain from `config/review-domains/registry.json`. → +states `domains`, `domains-checked` on P-07; +rows on P-10 |
| Approval with role (M1-T6, T6.6, E-1/E-3) | `approve-plan --by editor\|delegated`; BL-15 lead token | `intent approve` (stub, C-1) | P-07 `domains`, `domains-checked` (one approver per domain, one "Confirmed with" per group) | designed (batch 1); built approval card (medical/religious) | S1 → S3 | MISSING: the role per domain ("the business owner or their legal adviser", "the client") and one confirm per domain. Religious sign-off is never delegated, medical never auto |
| Per-domain gate (M1-T4) | `review-gate <item>` NOT BUILT (planned, P6) | NONE | MISSING | none | needs K-T9 (deferred) | stage unclear: depends on the deferred signed decision log. Drawn as P-07 `domains` only; the hard gate line waits |
| Removed-review clip (K-T2) | `removed-review <item>` (447ea2a) | NONE (C-3) | P-07 `removed` | designed (batch 1) | S1 → S3 | an MP4 of only what the plan removes, with slates. → secondary button "Watch what's removed" on P-07 + state `removed` (ready / making / failed) |
| Episode sheet (T4.4) | `episode-sheet --init EP` | NONE (C-6) | P-24 `normal`, `sheet-missing`, `sheet-made` | designed (batch 1) | S1 → S3 | → NEW P-24 (episode) |
| Client rules / learning loop (T4.3, F3b) | `rules --propose\|--add\|--remove\|--list` **NOT REGISTERED** (`lib/rules_loop.py`; CLI hooks held in lane2\hooks\T43; `--add/--remove` LEAD) | NONE (C-7) | P-26 | designed (batch 1) | S1 engine → S4 UI | sources `chat` now; `review_list`, `hand_edit` in S4; agency default at 3+ clients needs the owner. Safety rules can't be learned away. → NEW P-26 "Not now" needs an engine state (C-7); until then it only hides the proposal in the panel. |
| Intake early warnings (T4.8) | `inbox` returns `warnings[]` + `warnings_unread` (a2554ae: `lib/onboard.py:557-563` calls `intake_warnings.refresh`; `output/discovery/intake-warnings.json`) | NONE (C-3) | P-05 `intake` | designed (batch 1) | S1 → S3 | episode in Raw, docs in References, missing logo/HEX/fonts/sheet. → +state `warnings` on P-05 |
| Intake normalisation (Task 26) | (inbox) | NONE | P-05 `intake` (the frame-rate row) | designed (batch 1) | S1 → S3 | reported through the T4.8 warnings; same +state |
| Free up space (T4.15) | `clean` **NOT REGISTERED** (`lib/housekeeping.py`, 36cd6ad) | NONE | PARTIAL: P-21 `remove-confirm` (models only) | designed (models) | S1 → S4 | yes before apply; → +state `space` on P-21 Models (later batch) |
| Smooth zoom + fades (T4.1) | style.json, `ppro-build` | `host:build_project` (`camera_keys`, `fades`) | P-08 (frames show it) | n/a (no own UI; its live checks are the Adobe track's) | S1 | the K-T3 builder fades are NOT BUILT (only the switch name `k_t3_builder_fades` is reserved); the T4.2 knobs page is later (R-6.6) |
| Style knobs (T4.2) | style.json | NONE | MISSING | none | later (R-6.6 per-client settings) | |
| Licensed music in motion (T4.6) | `music --list`, motion-build | `host:ae_build_motion` | A-03 (gates), P-10 (`music`) | designed | S1 | |
| Adopt an old style (T4.9) | `ref-style --adopt ID --yes` (LEAD) | NONE | MISSING | none | S4 | diff first, then yes |
| Caption looks + recommender (Task 23, 28) | `caption-looks [--pick --yes]`, `looks recommend` | NONE | P-19 is the Kalam MOGRT gallery, not this | MISSING | S5 (F4) | |
| Cut proposals + takes (Task 25, K-T7) | plan markers NOT BUILT into the plan yet (Task 25 round 4 in review); `cut-proposals` (lands with the K-T7 hooks, before the tag) and `takes --drop --keep --undo` **NOT REGISTERED** (`lib/cut_proposals.py`, `lib/safety/takes.py`) | NONE | MISSING (P-16 is Hush-only) | none | S4 (F3) | meaning-different takes never pre-ticked; K-T7 follow-up open → design after Task 25 r4 closes. → NEW P-27 |
| Seam check (K-T3), hook check (K-T6) | `seam-check`, `hook-check` NOT BUILT (no module yet; K-T3 and K-T6 are open) | NONE | P-08 (QC) has no finding row for them | MISSING | S1 engine → S4 | findings with cut id and time; → +state on P-08 later |
| Safe zones (Task 27, K-T4) | `qc`; `safezone-check` **NOT REGISTERED** (`lib/safety/safezone_gate.py`; the K-T4 hard fail is a K1 switch, off) | NONE | P-08 (QC fail) | PARTIAL | S4 (F10 button) | |
| Burned-in captions (Task 24) | (plan) | NONE | MISSING | none | S3 | one-line notice; → a P-06 notice line later |
| Stricter publish-check (Task 30) | `publish-check` | NONE | MISSING | none | later (NEW P-25) | |
| Emphasis punch-ins + ending order (Task 29) | NOT BUILT (waits for T4.1) | NONE | P-08 (frames show it) | none | S1 | no own UI |
| Arabic integrity QC in motion (K-T5) | (motion-plan / qc; the motion-QC line is behind the K1 switch `k_t5_arabic_qc_in_motion_qc`, off) | `host:ae_*` | A-04 (frames) PARTIAL | designed | S1 | the refusal naming the scene id has no A-03 card yet |
| Move or clone a client (T4.5 part B) | `client-move`, `client-clone` **NOT REGISTERED** (BL-14, in flight) | NONE | MISSING | none | later | |

### 2.2 Base flows (work through Claude chat today)

| Feature | Engine command | Contract v4 | Panel screen | UI state | Stage | Notes |
|---|---|---|---|---|---|---|
| Edit a raw clip (12 stages) | `next`, `plan`, `preview-video`, `approve-plan`, `ppro-build`, `ppro-frames`, `qc`, `verify --record` | `state.pipeline[]`, `intent approve/rebuild` (stub), `host:build_project`, `host:export_frames` | P-03, P-05, P-06, P-07, P-08, P-09 | built + unit-tested (header, pipeline, approval card, QC frames, log: render.ts, mount.ts); live-tested: the panel's connection pills only (the UXP dev panel connected and showed the engine and Premiere 26.5.2; builds and frames ran from the CLI side through `reel serve` on the CEP bridge 3.1.1: `docs/adobe/live-roundtrip-2026-10-14.md`) | base → S3 | "Make my edit" needs the chat bridge (C-2) |
| Preview the edit | `preview-video`, `previews` | NONE | P-07 (Preview button) | designed | S3 | `host:render_review` exists for a Premiere render |
| Request changes / revise | (revise flow) | `intent request_changes` (stub) | P-07 changes card, P-08 | designed | S3 | |
| Rebuild | `ppro-build --force [--replace-edited]` | `intent rebuild` (stub) | P-09 | designed | S3 | |
| QC frames | `ppro-frames`, `qc` | `state.qc[]`, `host:export_frames` | P-08 | built + unit-tested (render.test.ts QC tiles) | base | R3 §7 recorded P-08 `offline` failing the self-check (`spinoff`); not re-run for this map |
| Handoff | `handoff [--delivered]` | `state.pipeline[handoff]` | P-06 `done` | designed | base | `--delivered` is LEAD |
| Status / board | `status`, `next`, `board --json` | `state` (one item only) | P-03, P-04 | designed | S3 | `board` across clients has no message (C-6) |
| Transcript words to confirm | `transcript-verify --by` | NONE | P-10 `words` row | designed | S1 | |
| Podcast: episodes, transcribe, reels plan, preview, pick (Gate 0) | `episodes`, `episode-prep`, `episode-transcribe`, `reels-plan`, `reels-preview`, `reels-select --pick --as video\|motion` (LEAD) | NONE (C-6) | P-24 | designed (batch 1) | S3 | → NEW P-24 |
| Podcast publish package | `publish-check`, `publish-thumbnail` | NONE | MISSING | none | later | → NEW P-25 (not in this round) |
| Motion video (AE) | `motion-plan`, `motion-animatic`, `motion-build`, `motion-render`, `motion-frames`, `ae-probe` | `host:ae_*` | A-01, A-02, A-03, A-04 | designed (+280 px) | base → S3 | A-02 needs medical/religious lines (E-3) |
| Fix audio only | `audio-clean` | NONE | MISSING | none | S5 (F5) | |
| AE/PS extras | `*-build --extras` | NONE | MISSING | none | later | on request only |
| AI one-shot text jobs | (Claude via engine) | NONE | P-12 | designed | S3 | overlaps with the chat; keep as the closed list |
| Cut a reel's in/out from long raw footage | `range --in --out --label` | NONE | MISSING | none | S3 | an editor decision; → P-05 +state later |
| XML fallback when the bridge fails | `premiere` (FCP7 XML) | NONE | P-11 (error card) PARTIAL | designed (error only) | S3 | the import steps for the XML have no screen |
| Writer lock (one session per client) | `lock --status\|--release` (release LEAD) | NONE | P-05 `locked` | designed | base | |
| Transcribe, correct, re-listen | `transcribe`, `transcript-correct`, `transcript-relisten` | `state.pipeline[transcript]` | P-06 (step), P-10 `words` row | designed (progress only) | base → S5 | the dialect picker (F5) adds the choice before transcription |
| Client onboarding: discover, database, reference style | `client-init`, `discover`, `client-db`, `ref-analyze`, `ref-style` (show / record / apply; `--adopt` LEAD) | NONE | P-04, J-01…J-05 (J deferred) | PARTIAL | S3 / later | no screen shows the reference-style result |
| Episode next step | `episode-next` | NONE | P-24 (the done state names the next step per reel) | designed (batch 1) | S3 | → P-24 |
| Sound effects map | `sfx` | NONE | none (internal, no UI planned) | n/a | n/a | |

### 2.3 V1 panel features (F1–F12)

| Feature | Engine command | Contract v4 | Panel screen | UI state | Stage | Notes |
|---|---|---|---|---|---|---|
| F1 in-panel chat: streaming, step cards, Approve / Change / Stop | chat bridge (`claude -p --output-format stream-json`), NOT BUILT | NONE (C-2) | P-23 | designed (batch 1); the F1 shell code is Stage 3 (track UI-S3; parked work in `D:\ClaudeData\claude-api-lane\tracks\UI-P4-parked\f1-shell\`) | S3 | → NEW P-23 + the F1 shell (§4 A-4) |
| F1 auth: own login or API key in the OS credential store; guided setup | `serve/claude_probe.py` NOT BUILT | `state.connection.claude` (hard-coded `unknown`, C-8) | P-01, P-02, P-22 `apikey`/`apikey-saved`, I-05 | designed | S3 | |
| F1 edit safety: copy sequence, one undo, plan first | T6.6 wrapper | NONE | P-07 trust line, P-09 | designed | S3 | Review focus 1: killed CLI → original untouched + clear error |
| F2 Kalam / Hush / Tidy tabs | `kalam/hush/tidy` verbs **NOT REGISTERED** (planned) | `host:kalam_*/hush_*/tidy_*` reserved | P-13…P-20 | designed | S4 | ~330 tools-ae keys still NEW/MOCK |
| F3 cut review list | Task 25 + Hush | NONE | MISSING | none | S4 | → NEW P-27 |
| F3b client rules card | `rules …` **NOT REGISTERED** | NONE (C-7) | P-26 | designed (batch 1) | S4 | → NEW P-26 |
| F4 caption look gallery (+ Liquid Glass) | `caption-looks`, `looks recommend` | NONE | MISSING (P-19 is MOGRT) | none | S5 | |
| F5 audio clean + dialect picker | `audio-clean`, transcribe prompt | NONE | MISSING | none | S5 | |
| F6 beat sync | `beats` NOT BUILT (planned, K-T20) | NONE | MISSING | none | S6 | |
| F7 multicam | NOT BUILT | NONE | MISSING | none | S6 | |
| F8 tracking | NOT BUILT | NONE | MISSING | none | S6 | |
| F9 Liquid Glass (AE) | NOT BUILT | NONE | MISSING | none | S7 | |
| F10 status light | `state.connection`, `state.jobs` | `state` | header G1 pills, P-02 | PARTIAL: engine and host pills built + unit-tested; the Claude pill maps only `active`/`idle` and shows everything else as "unknown" (`render.ts:107-110`; the daemon sends neither), `working` / `ready` / `waiting` are not rendered, and "job running" is not rendered (`panel_state.jobs` is read only to reattach commands after a reconnect, `daemon-source.ts:348, 853, 895`; never rendered) | S3 | the "status light" = the three pills. Built with C-8 and a `jobs` rendering item in the F1 shell (§4 A-4) |
| F10 buttons: safe-zone preview, search-to-word, chapters | `safezone-check` **NOT REGISTERED**, search-to-word NOT BUILT, episode chapters | NONE | MISSING | none | S4 | |
| F11 USB installer | installer track | n/a | I-01…I-09 | designed | S9 | |
| F12 docs | guide track | n/a | n/a | n/a | S9 | |

### 2.4 Machine and setup

| Feature | Engine command | Contract v4 | Panel screen | UI state | Stage |
|---|---|---|---|---|---|
| First run | `doctor`, `settings --init` (LEAD) | `state.connection` | P-01 | designed | S3 |
| Connection status | `serve status`, `ppro-status`, `ae-status` | `GET /status`, `state.connection` | P-02 | built (pills) + designed | base |
| Models | `model-download`, `gpu-enable` | NONE | P-21 | designed | S3 |
| Settings, language, approval mode | `settings --set` | `state.language` only | P-22 | designed | S3 |
| Errors | all | `error`, `result.error/how` | P-11 | built (notices) + designed | base |
| Client picker / new client | `scaffold`, `client-init`, `board` | NONE | P-04, J-01…J-05 (J deferred) | designed | S3 |

**Deferred or cancelled (no UI planned in V1):** K-T8 automatic verses (CANCELLED → manual verse slot above); Addendum J
website branding (J-01…J-05 designed, engine deferred); K-T9 decision log; K-T11, K-T12, K-T15, K-T16, K-T17; M4 /
Phase 5 Magnific (BL-05…12), including Addendum M's per-item card and single-use yes for each AI generation or
non-free stock download; M3 expressive style (S7 likely); K-T13/K-T14 (S7 likely).

## 3. Contract gaps (for the executor and the Adobe track; the UI track never edits the contract)

**Scope ruling (plan session, 2026-10-18):** none of C-1…C-9 goes into Gate 4 or the internal preview (in the preview
the panel is view-only; Claude chat drives the plugin, as in 2.2.1). Stage 3 = C-1…C-6, C-8, C-9; Stage 4 = C-7. **Executor per-gap rulings (2026-10-18): C-1…C-9 all ACCEPTED** at these stages (C-3: Stage 3 for the `tool_run` /
`flow_run` schema, each verb in its own feature's stage).

| Id | Gap | Blocks |
|---|---|---|
| C-1 | `approve`, `request_changes`, `rebuild` intents answered with NOT_YET | P-07, P-09 from the panel |
| C-2 | no chat / stream message (send a turn, stream events: text delta, step, tool, approval prompt, done, error; stop) | F1 (P-23) |
| C-3 | no message runs a `reel` verb (removed-review, auto-approve, inbox warnings, clean, …): the planned `tool_run` / `flow_run` intents have no schema | every one-click button |
| C-4 | no `needs_you` field in `panel_state` (the panel was to read `needs-you.json`) | P-10, the badge, the verse slot |
| C-5 | no review-domain fields (domain, verdict, approver role) in `approval.flagged` | P-07 `domains`, P-10 |
| C-6 | no podcast or cross-client data (episodes, reels plan candidates, `board`) | P-24, P-04 |
| C-7 | no rules data (active rules, proposals, conflicts) and no confirm / not-now / remove intent | P-26 |
| C-8 | `connection.claude` hard-coded `unknown`; `claude_probe.py` not built. Acceptance (plan session 2026-10-18): until it is wired the panel shows "not connected yet" or hides the Claude part; never `unknown` dressed up as a status | the status light's Claude part |
| C-9 | eng-data-contract §2 fields specified but not in the schema: `item_meta`, `plan.edit_map/diff`, `week`, `verbs[]`, `approval_record`, `previous_approval`, `setup[]`, `support` | P-03, P-06, P-07 data |

## 4. Pre-mortem → acceptance items for the UI track

**A-1 Coverage map (this doc).**
- Holes: a map rots the day after it is written; IDs drift; "state" means different things to different people.
- Fixes, as acceptance: the four UI states are defined in §0; every screen named here exists on disk; every row has
  a contract column (a message, or NONE + a gap id). The standing rule (§5) keeps it current. Cheap addition: a
  small check in `adobe/panel-ui` that every `P-/A-/I-/J-` ID in this file exists under `design/screens/` and every
  screen file appears here at least once (built with the first design batch). It expands ranges written `X-01…X-09`
  into each ID, and skips IDs written `NEW P-2x` (proposed, not drawn yet). Built with batch 1:
  `python adobe/panel-ui/design/_build/check_map.py` (and `--self-test`).

**A-2 Phase 4 screens (batch 1: P-07 domains + removed, P-10 verse + risky + domains, P-06 autopilot + verse line,
P-05 warnings, NEW P-24 episode/reels, NEW P-26 client rules).**
- Will it work for a real editor: each screen shows the engine's real fields (taken from the engine's output files and
  fixtures, not invented), one primary per screen, every state (empty, loading, normal, focus, error, offline,
  no-claude, stale, long, success where it applies).
- Arabic (review focus 2): every new state has an Arabic run with Latin terms inside (a drug name, "ROI", "AI"),
  Arabic-Indic digits as spoken inside quoted speech (UI numbers stay Latin, eng-data-contract §5.2), and a long word
  case at 300 px. No word breaks mid-token; mixed runs in `<bdi>`.
- Verse slot: never any Quran text, not even as sample data; the marker name is exactly «آية: يضيفها المونتير يدويًا»;
  the sheikh/content owner sign-off is never delegated and never auto.
- Approver roles: the role names come from the registry (doctor, content owner, business owner or legal adviser,
  client); the medical line can't be auto-approved; religious can't be delegated.
- Gates: `check_css.py` 0; `render_all.py --only <ID>` 0 failed for every new/changed screen (through heavy.sh);
  self-check extras 0 (`statuslie`, `confirmkbd`, `violet`, `stalerun`, `spinoff`); a fresh Opus visual reviewer per
  batch (brand-systems-designer) with an Arabic-copy pass; the review artifact updated with only the changed files.

**A-3 Contract.** The UI track writes a contract proposal (C-2 chat, C-4 needs_you, C-5 domains, C-7 rules) as a
written note to the executor and the Adobe track; it changes nothing until both agree.

**A-4 F1 shell (chat pane, approval buttons, status light).**
- Prerequisite missing: the chat bridge and its messages (C-2). The shell is built behind a `ChatSource` interface with
  a fixture/mock source and a contract adapter left for when C-2 lands, so nothing is redone.
- No panel-side business logic: the panel renders events and sends intents; it never decides an approval, never
  parses Claude text for meaning, never runs a command.
- Review focus 1: a stream that dies mid-turn shows a clear error and leaves the panel usable; Stop is always
  reachable; review focus 4: no Claude / no engine shows the guided setup, never a hang (timeouts tested).
- RTL: streamed text mixes Arabic and English; bidi isolation per message; the composer works in both directions.
- Security: chat text is escaped (no HTML from the stream reaches the DOM); one rendered message is capped at 8,000
  characters (the rest is folded behind "Show more") and the view keeps the last 200 turns (older ones behind "Earlier
  messages"); no key or token is ever rendered or logged (a test greps the rendered output and the panel log).
- Timeouts (UI constants, adjustable when C-2 lands): connecting to WhyNot Cut 10 s → the offline card; no stream event
  for 30 s during a turn → a "still working" line; 120 s → the died state with Try again. Each one has a test.
- Tests run under `node --test` without Premiere; a live-check request goes to the Adobe track as one batch.

## 5. Standing acceptance rule (ADOPTED by the executor 2026-10-18)

> From 2026-10-18, a new user-facing feature task is accepted only when its row in this map is filled: the engine
> command, the contract v4 message(s) that carry it (or NONE + a gap id the executor has accepted), and a panel screen
> (an existing screen/state, or a NEW one designed by the UI track). A feature with no screen yet is accepted only with
> a UI-track ticket that names the screen it will get.

**Executor ruling (2026-10-18): ADOPTED (option a), with these terms.** Record: the executor's message to the UI
track of 2026-10-18 and the `UI` lines of that day in `D:\ClaudeData\claude-api-lane\SUBSCRIPTION-LEDGER.md`; the
executor logs this map's commit.
1. **Scope.** It applies to every NEW user-facing feature task from 2026-10-18. Exempt: anything committed before
   that day, and anything already claimed or in flight on it (Builder A's lane-4 queue; Builder B's BL-15, T4.3 and
   BL-01; the open lane 1 and lane 2 tasks; the Adobe track's T4.1 and T4.6). The UI track fills the rows of the exempt
   items itself, so no owner loses time or is blocked by a missing row.
2. **A row needs** the engine command; the contract v4 message(s), or NONE plus a gap id the executor has accepted;
   and the screen, or a UI-track ticket that names it. The gap ids C-1…C-9 count as accepted only once the executor
   has ruled on each one (all nine accepted on 2026-10-18, see §3).
   Whether the panel should run `reel` verbs before Stage 3 is a scope question for the plan session; neither the
   executor nor the UI track widens Gate 4 alone.
3. **The manual verse slot** (Gate 4, executor-owned) is filled now: §2.1 row, P-10 `verse` state.
4. **Enforcement.** A consistency check inside `adobe/panel-ui` (map ↔ screen files only). It never touches
   `contract.ts`, `mock.test.ts`, `package.json`, `package-lock.json` or `tsconfig.base.json`, never fails
   `tools/test.sh` and never blocks an engine commit. The rule is enforced at the executor's acceptance, not by CI.
5. This map is committed only after its fresh Opus review is PASS or PASS-WITH-MINORS.
