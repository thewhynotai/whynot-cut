# WhyNot Cut V1: Premiere panel with in-panel chat and one-click tools (design spec)

Date: 2026-10-18. Owner: Yunus. Author: plan session.

Status: **APPROVED by the owner on 2026-10-18.** Open questions are answered in §8.

Inputs:
- `Editing Plugin/NEW-PLAN-BRIEF-AR.md` (owner's answers);
- `Editing Plugin/COMPETITORS-AR.md` (EditFast, MegaCut Studio);
- `Editing Plugin/V1-SCOPE-AR.md`;
- the Phase 6 plan (`docs/superpowers/plans/2026-10-11-3.0-phase-6*.md`);
- PROGRESS.md.

## 1. Purpose, users, success

**Purpose.** Give an editor everything **inside Premiere Pro (and After Effects)**:
- a chat that drives WhyNot Cut;
- one-click tool buttons;
- review lists with checkboxes;
- the motion looks.

All of it is installed with one click from a USB stick. This panel is also step one of a later standalone app (.exe/.dmg). The app will reuse the same engine and UI kit, so nothing built here is redone.

**Users.**
- The agency's editors, first.
- External editors who test it from a USB stick.

The product is **open source**. Nothing is sold in V1.

**Success criteria (V1 is "done" when all are true):**
1. On a clean Windows 11 PC and a clean macOS machine, a non-technical editor installs from the USB folder with one click (per OS), following the Arabic guide. Nothing is downloaded during install; the models ship on the stick.
2. Premiere → Window → Extensions → **WhyNot Cut** opens the panel. The status light shows the engine connected, and Claude connected (account or API key).
3. From the panel chat, the editor can run the existing core jobs end to end on a real clip:
   - raw clip → plan → approval → Premiere build → QC frames;
   - podcast → reels plan;
   - revise.
   Every AI edit runs on a **copy** of the sequence and is **one Undo step**.
4. Each one-click tool (§3, F2–F8) works on a real clip, with a review step wherever it deletes or moves media.
5. The After Effects panel applies the **Liquid Glass** looks to cards, captions and titles, and renders correctly.
6. Everything passes the repo bar:
   - full suite green on Windows and the macOS CI;
   - independent review with 0 Critical / 0 Important;
   - the security line (no new High; daemon auth tests green);
   - Arabic RTL and mixed Arabic/English checks.
7. The internal doc (developers and agency) and the external doc (editors) exist and match the build.

## 2. Scope

**In V1:**
- **The panel framework:**
  - Premiere panel (UXP on Premiere 26.5+ ONLY in V1; a CEP fallback for older Premiere comes in a later version, per the owner);
  - After Effects panel (CEP).
- **Inside the panels:**
  - in-panel chat;
  - Kalam / Hush / Tidy tabs;
  - cut review list;
  - caption look gallery with previews and "apply to all";
  - non-destructive audio clean-up;
  - dialect picker;
  - safe-zone preview;
  - search-to-word and chapters;
  - status light.
- **Tools:**
  - beat sync;
  - multicam (audio sync and speaker-based switching);
  - tracking (pin text, sticker or logo to a moving object);
  - Liquid Glass looks in After Effects.
- **Distribution:**
  - one-click installers (.exe and .dmg/.pkg), unsigned, from an offline USB folder;
  - an Arabic install guide;
  - an internal doc and an external doc.
- **Settings:**
  - the user's own Claude Code account, OR the user's own Anthropic API key;
  - a guide that lists the cheapest working options.

**Not in V1** (saved in `Editing Plugin/SAVED-LATER-licensing-updates-AR.md` or the later-phase plans):
- licences and locking;
- signed updates and update channels;
- code signing;
- pricing and Adobe Exchange;
- Magnific (Phase 5);
- client branding from a website (Addendum J);
- topic search;
- beat-synced *montage generation* (beat *sync* is in V1);
- the DaVinci export;
- other model providers (a later version adds "our own API").

**Prerequisite.** Gate 4 (Phase 4 editor features) closes first. V1 builds on those features, and the panel buttons call them.

## 3. Features and acceptance

Each feature is a thin panel UI over an engine command. Engine logic lives in `whynot-cut/engine` and is tested there. The panel never re-implements logic.

### F1. In-panel chat
- **UI:**
  - a chat pane in the Premiere panel (and a compact one in AE);
  - streaming replies;
  - step cards ("transcribing…", "building…");
  - approval prompts rendered as buttons (Approve / Change / Stop);
  - Arabic and English, RTL-correct.
- **Bridge:**
  - the panel connects to the local engine daemon (`reel serve`, contract v4, token-authenticated, localhost only);
  - the daemon runs **Claude Code headless** (`claude -p --output-format stream-json`), with the WhyNot Cut plugin loaded and `cwd` set to the active client folder;
  - the daemon relays events to the panel.
- **No arbitrary-script endpoint:** the chat can only reach Premiere through the existing whitelisted bridge operations.
- **Auth, two modes:**
  - (a) **the user's own Claude Code login**: whatever `claude` on that machine is logged into;
  - (b) **an API key** entered in Settings: stored in the OS credential store (Windows Credential Manager / macOS Keychain), passed to the CLI as `ANTHROPIC_API_KEY`, never written to disk in clear, never logged.
- **Edit safety:**
  - every AI change that touches a timeline first duplicates the sequence ("<name> – WhyNot copy");
  - the change is wrapped as one undo group;
  - the plan is shown before applying.
- **Acceptance:**
  - a full raw-clip job and a podcast reels-plan job run from the panel chat;
  - killing the CLI mid-job leaves the original sequence untouched and the panel shows a clear error;
  - the key never appears in logs or files (test greps the logs and the client folder);
  - with no Claude login and no key, the panel shows a guided setup instead of failing.

### F2. Tool tabs: Kalam (captions), Hush (silence and fillers), Tidy (project organiser)
- The three engines are already ported (tools track, Phase 6B). V1 adds the panel tabs and the host operations.
- **Kalam:**
  - captions straight to a track (MOGRT or text), plus SRT export;
  - words per card; one-word mode.
- **Hush:**
  - silence and filler detection with a sensitivity slider;
  - the result goes through the **cut review list** (F3), never straight to the timeline.
- **Tidy:**
  - shows a plan, then sorts the bins (Video / Audio / Images / Graphics / Music);
  - the podcast-sync mode is reused by F7.
- **Acceptance:** each tab works on a real clip on both OSes; Tidy never moves files on disk; a no-op runs cleanly.

### F3. Cut review list (from the competitor review)
- Retake, filler and silence proposals (Task 25 + Hush) appear as a list. Each row has:
  - a timecode;
  - a ▶ preview (plays that range in the source monitor);
  - a checkbox;
  - the reason, e.g. "repeated take".
- Proposals whose takes differ in meaning are never pre-ticked (existing K-T7 / Task 25 rule).
- "Apply" cuts on a copy, as one undo.
- **Acceptance:** the negation cases (e.g. «مخدتش») are never pre-ticked; the list round-trips (untick → no cut).

### F3b. Client rules: the learning loop in the panel (owner 2026-10-18)
Builds on T4.3 (Gate 4: rules from chat comments, grouped by meaning, confirmed by the editor, conflicts, list/remove, never weakening safety).
- A **"قواعد العميل" card**: the active rules (date, source, what it changes), with Remove, and the pending proposals with Confirm / Not now.
- **Two more sources** feed the same grouping (`source` = `review_list` | `hand_edit`):
  - the cut review list (F3): the same kind of proposal unticked on 2+ reels → a proposal («بتلغي قص التكرار دايمًا، أوقفه للعميل ده؟»);
  - the editor's hand edits on the built copy: when the editor finishes, the panel reads the sequence back and compares it with what was built (caption size/position, deleted graphics, removed zooms, changed cut points). The same change on 2+ reels → a proposal.
- **Agency default:** the same confirmed rule on 3+ clients → a suggestion to make it the agency default (the owner confirms).
- **Acceptance:** each source has a test where 2 reels produce one proposal and 1 reel produces none; a confirmed rule changes the next build; safety rules cannot be learned away (the T4.3 tests run against the panel path too).

### F4. Caption look gallery
- A grid of the 8 caption looks (Task 23) and the recommender (Task 28), with live preview stills.
- Per-sentence or whole-sequence apply, and "apply to all".
- Includes the **Liquid Glass** caption look (F9).
- **Acceptance:** preview stills match the rendered frames (QC frame check).

### F5. Audio clean-up (non-destructive) and dialect picker
- **Audio:** the existing audio-clean pipeline.
  - The cleaned audio goes on a new track **above** the original (the original is muted, never deleted).
  - Simple toggles: noise, hum, leveling; loudness target per platform.
- **Dialect picker:** before transcription, pick Egyptian, Gulf, Levantine, Maghrebi, MSA or English. It primes Whisper with a dialect prompt.
  - Measured accuracy per dialect is published in the external doc.
- **Acceptance:** A/B loudness measured; the original stays recoverable; the dialect prompt changes the measured WER on the test set.

### F6. Beat sync
- Detects beats locally in a music track, with a licence-clean library (e.g. librosa, ISC). **No NC/AGPL code or models.**
- **Premiere:** adds markers on beats, and optionally snaps the selected cuts or captions to the nearest beat (the review shows the moves).
- **AE:** adds shake, zoom or flash on beats to the selected layer (native effects).
- **Acceptance:**
  - beat times are within ±1 frame on a reference track set;
  - markers are idempotent: re-running does not duplicate them.

### F7. Multicam
- Syncs 2–4 camera files by audio cross-correlation (reuses Tidy's podcast-sync where possible).
- Builds a speaker-based switching plan from each camera's audio level (who is speaking), with a minimum shot length and a wide shot on overlap.
- The plan is shown for review, then a multicam (or cut) sequence is built **as a copy**.
- **Acceptance:**
  - sync error ≤ 1 frame on test pairs;
  - the plan never switches faster than the minimum shot length;
  - it handles a camera that starts late or stops early.

### F8. Tracking (pin an overlay to a moving object)
- The user selects a box on a frame in the panel preview.
- A local tracker (OpenCV CSRT or optical flow; Apache-2.0 / BSD only) produces per-frame positions.
- Those positions are applied as Position (and optionally Scale) keyframes to the chosen text, sticker or logo clip.
- Low-confidence frames are flagged for review.
- **Acceptance:**
  - mean error ≤ 8 px at 1080p (scaled for 4K) on the reference clips;
  - tracking loss is reported, never silently drifting;
  - it works on 4K and vertical footage.
- **Risk:** accuracy on fast motion. V1 ships with confidence flags and manual correction (re-anchor a frame).

### F9. Liquid Glass looks (After Effects)
- A family of AE looks in the style of Apple's "Liquid Glass" (translucent, frosted, refractive, soft highlight edge) for **cards, captions and titles**.
- Built only from native AE effects (no third-party plugins), with Arabic RTL text support.
- Exposed in the AE panel and in the caption look gallery (F4).
- **Acceptance:**
  - renders on both OSes;
  - the frame QC passes;
  - Arabic text stays shaped and readable over busy backgrounds (contrast check).

### F10. One-click tool buttons and status
- Buttons for the jobs people expect: safe-zone preview, search-to-word, chapters, plus every F2–F9 tool.
- A **status light** for engine connected / Claude connected / job running.
- **Acceptance:** each button has a visible result or a clear error; there are no dead buttons.

### F11. One-click install from USB (Windows and macOS)
- **The USB folder:**
  - `WhyNotCut-Setup/`
    - `Windows/WhyNotCut-Setup.exe`
    - `Mac/WhyNotCut.dmg` (or `.pkg`)
    - `models/`
    - `اقرأني-التسطيب.pdf`
- **The installer (existing Tauri installer track):**
  - installs the engine, the runtime, the Claude Code plugin, the UXP and CEP panels and the fonts, per user and with no admin where possible;
  - copies the models from the stick (no download);
  - runs `reel doctor`;
  - offers an uninstall.
- **Unsigned**, by owner decision: the Arabic guide shows the exact macOS Gatekeeper and Windows SmartScreen steps with screenshots.
- **Acceptance:**
  - a clean Windows user account and a clean macOS account install offline in under 10 minutes;
  - uninstall leaves no files outside the documented list;
  - re-install over an existing install keeps client data.

### F12. Documentation
- **External (editors), Arabic first:**
  - what the plugin does;
  - install from USB;
  - first job in 10 minutes;
  - each tool with a screenshot;
  - FAQ;
  - support on WhatsApp;
  - the API-key guide (the cheapest working options, honestly stated).
- **Internal (agency and developers):**
  - architecture (engine, daemon, panels, chat bridge);
  - how to build the USB folder;
  - how to develop and test;
  - the release cycle (§6);
  - where everything lives.

## 4. Architecture

```
Premiere (UXP panel, 26.5+)   AE (CEP panel)   [older Premiere: later version]
          \___________________|____________________/
                 shared panel-ui kit (adobe/panel-ui)
                              │  localhost, token, contract v4
                     reel serve (engine daemon, Python)
            ┌─────────────────┼──────────────────────────┐
     engine commands     chat bridge               host adapters
     (existing + F5–F8)  (claude -p stream-json,   (UXP adapter, CEP file
                         the user's login or key)  queue; whitelisted ops)
```

- **One engine, many fronts:** the chat, the panels and later the standalone app all speak contract v4. New features add engine commands plus contract messages, never panel-side logic.
- **Security:**
  - daemon on localhost only, with a per-session token;
  - message size caps; no run-arbitrary-script endpoint;
  - the client folder stays read-only except `output/`;
  - the L-T8 engine write gate applies to every new command;
  - the API key lives in the OS credential store.
- **Cross-platform:** every engine change follows the BRIEF rule "Solid, cross-platform, no shortcuts", with Windows and macOS tests.

## 5. Delivery: who builds what

**Subscription sessions** (owner rule: only the ones needed; models set 2026-10-18):

| Session | Model | Role |
|---|---|---|
| Executor | Opus 5.5 high | Acceptance, shared files, gates |
| Adobe / panels | Opus 5.5 high | Live Premiere/AE work, UXP/CEP host operations |
| Plan | Opus 5.5 high | Order, reports |
| Installer | Opus 5.5 high | USB installer, when F11 starts |
| Looks / motion | Opus 5.5 high | F4, F9, when they start |
| Tools | Sonnet 5.5 high | Kalam/Hush/Tidy host glue |
| Guide | Opus 5.5 high | Arabic external doc, near the end |

At most 4–5 run at once (RAM).

**API lanes:**
- **3 building lanes + 1 review lane** (down from 4 + 1, because full-suite capacity is the bottleneck).
- They take the engine-side and test-heavy parts (F5–F8 engines, the chat bridge, contract messages, panel components with unit tests) from the BACKLOG.
- The Adobe session does the live host integration.

## 6. Release cycle and budget (concept, not fixed numbers)
- **Each month:** a written plan → the work → when the month's API limit gets close (the budget guard flips), **cut a version**:
  - freeze new work;
  - assemble what is closed and reviewed;
  - write "what's new";
  - build the USB folder;
  - test it on the agency PCs.
- **The next month** starts with its plan prepared against the credit available.
- The guard's thresholds are adjusted to the real situation, not fixed amounts.
- **October:** close Phase 4's basics and cut an **internal preview** (chat-based, with the Phase 4 features).
- **November onward:** the V1 panel features, in this order:
  1. F1 + F10 + F11 skeleton (chat and install first);
  2. F2/F3;
  3. F4/F5;
  4. F6/F7/F8;
  5. F9;
  6. F12 last.

## 7. Testing
- **Unit and integration:**
  - engine tests per command;
  - contract tests for every new message;
  - panel component tests (existing panel-ui test setup).
- **Live:**
  - Premiere/AE parity scenarios on both OSes (the existing E1–E20 set, extended for F1–F9);
  - real client clips after V1 is assembled (owner: "test it after the first version").
- **Gate:** independent review, full suite, the macOS CI, the security line, and the installer test on clean accounts.

## 8. Owner decisions (2026-10-18)
1. **Distribution:** private, on a USB stick. The repo stays private, nothing is published, and source goes only with the stick.
2. **Premiere versions:** the NEW UXP panel only (26.5+) in V1. Older Premiere (CEP fallback) comes in a later version.
