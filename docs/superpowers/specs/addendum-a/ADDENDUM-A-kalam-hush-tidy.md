# WhyNot Cut 3.0 — Addendum A: Kalam, Hush and Tidy inside WhyNot Cut

| | |
|---|---|
| Date | 2026-10-12 |
| Requested by | Yunus. He wants the three tools added to the plugin, usable everywhere, developed **without changing them or their idea**, only so they are easier and stronger to use, and fully tested |
| Inputs | `prd/kalam-prd.md` (v1.1), `prd/hush-prd.md` (v1.0), `prd/tidy-prd.md` (v2). Owner field "Hoka". Panels `com.hoka.kalam/hush/tidy` (CEP 11) |
| Applies to | Master plan `docs/superpowers/specs/2026-10-11-whynot-cut-3.0-master-plan.md`. This addendum adds tasks; it removes none |
| Commit | The executor commits this folder to `WhyNotCut/docs/superpowers/specs/addendum-a/` (single writer rule) |

## A0. The rule from the owner (binding)
- **Same tools, same idea.** Keep every PRD requirement:
  - Kalam FR-1…FR-24;
  - Hush FR-1…FR-24;
  - Tidy FR-1…FR-23;
  - each PRD's §8 safety rules (verbatim);
  - each PRD's §11 acceptance tests.

  Nothing in a PRD is dropped, renamed away or weakened.
- **Allowed changes** are only those that make the tools easier or stronger to use without changing what they do
  (A3).
- **Tests.** Every PRD acceptance test is reproduced and passes. New tests cover every A3 improvement and every port.

## A1. Source code (decides "port" vs "rebuild")
The PRDs point to existing code (`kalam/`, `hush/`, `tidy/`, `install_kalam.sh`, `build_windows.sh`, `windows/`, with
101 pytest + jsc suites). **None of it is on this PC** (searched `C:\Users\LOQ` and `D:\`).
- **Preferred: port the real code.** Yunus supplies the three folders (and their `docs/superpowers/specs` design
  files). The executor copies them into `WhyNotCut/adobe/tools/<tool>/_upstream/` unchanged (a read-only reference)
  and ports from there. Behaviour parity is proved by running the upstream test suites against the ported modules.
- **Fallback if the code can't be supplied:** rebuild from the PRDs, requirement by requirement. Every FR becomes a
  test before its code exists. Record "rebuilt from PRD, not ported" in CHANGELOG and the guide. Tuned constants
  (thresholds, DP costs, prompts) come from the PRDs. Where a PRD doesn't state a value, the executor asks Yunus once
  rather than inventing it.
- **Ownership:** confirm that the WhyNot Cut owner has the right to ship "Hoka"'s code inside WhyNot Cut (H12 below).

## A2. Where the tools live (architecture, consistent with master plan D4/D5)

| Layer | Kalam | Hush | Tidy |
|---|---|---|---|
| **Panel UI** | A tab in the **WhyNot Cut panel** (UXP, Premiere). Same cards and flow as each PRD's §5. TWN brand tokens, AR default / EN, RTL. Shared code in `adobe/panel-ui/tools/<tool>/` | same | same |
| **Pure logic** (dependency-free JS) | `range.js`, `platform.js`, `mogrt.js` reused as is | `detect.js`, `fillers.js`, `wav.js` reused as is | `media.js`, `classify.js`, `plan.js`, `sync.js` reused as is |
| **Node services → engine** | Process spawning, settings, report: move to `reel serve` (UXP can't spawn) | Settings/presets/cache/Whisper spawn → engine | Disk info, byte sniffing (UXP fs may read), WAV power streaming, backup copy → engine |
| **Host operations** | `createCaptionTrack`, `importMGT` + text, remove clips, export WAV: **CEP compat ops** in the signed bridge (`WNC_KALAM`) until UXP covers them; `setPlayhead`/info via UXP when green | razor (QE), ripple, link, clone sequence, markers: **CEP compat** (`WNC_HUSH`). UXP has no razor | scan tree, moves, colours, bins, rename, save/open, `addTracks` (QE), temp sequences: CEP compat (`WNC_TIDY`); bin/move ops via UXP only where the T6.4 parity matrix is green |
| **Shared host service** | `WNC_AUDIO.exportRange` / `exportClipAudio`, one implementation (all three PRDs ask for it), with mute/restore of unticked tracks and In/Out restore | same | same |
| **Python** | Kalam engine as its own process (PRD §13: keep the separate process and the JSON-lines protocol): `engine/reel/kalam/` + `reel kalam run|doctor` | Whisper words from Kalam's "other" model (PRD §13), or WhyNot Cut's faster-whisper with Hush's disfluency prompt. Model override kept | none (pure JS + host) |
| **CLI** (so Claude can drive them from chat, and the panel calls the same code through `reel serve`) | `reel kalam run --range in-out|sequence|playhead|selection --mode ar|en|other --output track|mogrt|srt …`, `reel kalam doctor` | `reel hush scan|plan|apply --mode cut|markers|undo|clear-markers` | `reel tidy scan|plan|apply|undo|sync` |
| **Claude skills** (Phase 3 budget ≤ 200 chars each) | `/whynot-cut:captions`: «ترجم/كابشن الريل ده» | `/whynot-cut:cut-silence`: «شيل السكتات والآآ» | `/whynot-cut:tidy`: «رتّب البروجكت», «سنك البودكاست» |

ExtendScript rules from all three PRDs are enforced by a lint test over every `wnc_*.jsx`: ASCII-only source, ES3
(no `map`/`forEach`/`filter`), namespaced globals, every nested conditional parenthesised.

## A3. Allowed improvements (stronger and easier, same idea)
1. **Windows + macOS for all three.** Hush and Tidy are macOS-only today. Use Kalam's portable backend (faster-whisper,
   CUDA, CPU fallback) and Windows paths (`%LOCALAPPDATA%`, `explorer`, preset paths). Kalam Windows is "not yet run
   on real Windows hardware" (PRD §12); it is verified live on this PC.
2. **No PlayerDebugMode, one install.** The tools ship inside the signed WhyNot Cut bridge and the UXP plugin. The
   installer installs them, and `reel doctor` checks them, including Kalam's `doctor`. The diagnostics bundle includes
   their logs (redacted; Kalam's "never settings or keys" rule is kept).
3. **One audio export and one transcription per range.** If Kalam already transcribed a range, Hush uses those word
   timings for fillers (both PRDs propose this). The cache is keyed by sequence id + range + track set + audio hash.
4. **"Organise → Cut → Caption" flow.** One button runs Tidy → Hush → Kalam in order. Each step still shows its own
   preview and needs its own confirm, and each keeps its backup and undo. Nothing is merged silently.
5. **Client-aware.** When the sequence belongs to a WhyNot Cut client folder:
   - Kalam's glossary and rules start from the client profile (medical glossary, names, `people[]` gender and
     honorifics from master-plan T1.7), and the editor can still edit them in the panel.
   - Hush starts from the client's pause style.
   - Outside a client folder, each tool uses its own PRD defaults.
6. **Chat and panel give the same result.** Every run writes a report (what changed, backup name, how to undo) that
   Claude reads and repeats under Verified / Not verified / Needs you.
7. **Close Tidy's listed limitations without changing behaviour:**
   - a 44.1 kHz drift guard (resample to 48 kHz before matching);
   - a second sync gets a numbered name ("- Synced 2") instead of a duplicate;
   - leftover "Tidy sync temp" sequences are removed at the start of the next run;
   - the skip reason is shown for very short clips.
8. **Podcast link.** Tidy's synced multicam sequence can be handed to podcast mode as the episode source (optional;
   the podcast pipeline is unchanged when it isn't used).
9. **Model packs with sizes shown.** Kalam's models (Egyptian Whisper turbo, Parakeet, MMS aligner, torch) are an
   optional "Kalam pack" in `components.json`, with its own runtime lock so the core runtime stays light. Following
   Yunus's installer rule, the pack is **ticked by default** and its size is shown. Hush's Whisper reuses the pack or
   the core model.
10. **Correction backend inside Claude Code.** Kalam's default `claude -p --safe-mode …` (PRD FR-6) stays the default
    in the panel. When Kalam runs from chat, the lead session may instead run the same correction contract through a
    small read-only agent. The code-side faithfulness gate (FR-9) and `rules.enforce` (FR-10) run either way, so the
    result rules are identical.

## A4. Phase placement (no new parallel track; Yunus chose to keep 4 tracks)

| Phase | What is added |
|---|---|
| **3 (plugin layer)** | Three skills (A2), their evals (mocked host, `tool_used` graders, Arabic prompts), the skill-budget test updated. The guard allows these tools to edit the editor's **own Premiere project** (never `assets/` or `data/`), and only after the backup step has written its record |
| **6 (native Adobe)**, new sub-phase **6B "Editor tools"** after T6.7 (routing exists) | **T6.11** shared host services + `WNC_AUDIO` + lint. **T6.12 Hush.** **T6.13 Tidy** (+ sync). **T6.14 Kalam** (engine package, pack, MOGRT gallery, three outputs). **T6.15** "Organise → Cut → Caption" flow + client-aware defaults. **T6.16** live acceptance on test projects (A5) |
| **7 (installer)** | The Kalam pack (optional, ticked, sizes shown), Windows CUDA/ONNX runtime parity, uninstall of pack data dirs (`%LOCALAPPDATA%\Kalam` style dirs move under `~/.whynot-cut/tools/`) |
| **9 (QA)** | The A5 tests on Windows live; on macOS if H6 |
| **10 (Arabic guide)** | Three chapters (Tidy, Hush, Kalam) + the combined flow, with screenshots from the live runs |

Size: XL. Expect roughly 1–2 extra days of execution on top of the current estimate.

## A5. Tests that must pass (PRD §11 ×3 + new)
- **Kalam:**
  - the engine suite (101 tests or their PRD-derived equivalents): rules, caption DP (no term splits, one-letter
    penalty, unit costs), units, cleaning, correction contract + faithfulness gate (fake clients), alignment
    fallbacks, CLI, doctor, platform (Claude discovery incl. npm `.cmd`, UTF-8), portable backends (GPU→CPU fallbacks,
    chunk cuts);
  - panel logic: ranges + SRT shift, platform paths, safe names, MOGRT zip/definition parsing and filter;
  - **13 host checks**;
  - **backend parity** portable vs MLX on 3 real clips: text ≥ 96 %, onsets within 15 ms (MLX part needs H6).
- **Hush:**
  - pure tests: envelope/percentiles, silences with 30 ms blips, pads at range edges, filler-gap join, inward frame
    snap, intensity mapping, filler matching (Arabic normalisation, two-word phrases, elongated hesitations);
  - Premiere: cut → removed count, **no gaps**, linked items, backup exists; restore swaps names; markers
    added/removed; a locked track aborts with nothing changed.
- **Tidy:**
  - media (renamed DJI, AE render with source tags, RAW, AVCHD, iPhone, identical cameras, image sizes, icons), classify,
    plan (backup usage, nests, duplicates, offline, opt-ins, same-name old bins, nest names), sync (± offsets, refine
    ≤ 2 ms, stranger skipped, WAV header, layout overlaps), lint;
  - **host 11/11**, **synced 3 cams + 2 mics 4/4**;
  - the read-only dry run on a real project's files.
- **New:**
  - every test above also runs on Windows;
  - shared export parity (the three old exports vs `WNC_AUDIO`, byte-identical WAV for the same range);
  - Hush using Kalam's words gives the same filler list as its own run on 3 clips;
  - the "Organise → Cut → Caption" flow on a test project: each step's backup exists and each undo works in reverse
    order;
  - client-aware glossary applied, and the faithfulness gate still rejects rewrites;
  - the 44.1 kHz sync drift guard; the second-sync name; temp-sequence cleanup;
  - UXP ↔ CEP routing for every tool op;
  - skill evals (chat → same report as the panel).
- **Test media:** test projects and copies under `whynot-test/` only. Never the editor's real projects or
  `D:\WhyNot Clients`.

## A6. New human items
- **H12:** supply the source folders of Kalam, Hush and Tidy (and their design specs), and confirm WhyNot Cut may
  ship them (owner "Hoka"). Without them, use the A1 fallback.
- **H13:** two or three short real test clips per language (Egyptian Arabic, English) for the parity and filler tests,
  as copies in `whynot-test/`. EP02 excerpts can serve for Arabic.
