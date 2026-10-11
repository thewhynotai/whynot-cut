# Changelog

## 2.1.0 — 2026-10-11 · Podcast mode
A finished podcast episode becomes a reels plan, the editor picks, and each pick goes through the normal pipeline —
plus the episode's publishing package. One plugin: after Gate 0 a reel is an ordinary clip project.

**New for users**
- `/whynot-cut:podcast` (lead playbook) and `data/Episodes/` (+ optional `<name>.md` episode sheet: host, guest,
  links, sponsor, topics to avoid). `reel inbox` lists episodes and flags long 16:9 files left in `data/Raw`.
- `reel episodes`, `episode-prep` (probe, 6 intake frames, time estimate), `episode-transcribe` (whole episode in
  ~10-minute chunks with checkpoints; resumes after an interruption; VAD; language detected once), `episode-next`.
- Reels plan: the `episode-analyst` (fans out `moment-scout` per chunk) writes the topic map (= YouTube chapters),
  speaker turns with seating, and candidates with timecodes, content type, hook, score and risks. `reel reels-plan`
  validates them against the transcript (evidence near start/end, Arabic-normalised), snaps in/out to sentence
  boundaries, checks duration/overlap/avoid topics and writes `reels-plan.md`; `reels-preview` renders a quick 9:16
  preview of each candidate.
- **Gate 0**: `reel reels-select --pick … --by editor` (subagents blocked by the guard). Each pick becomes
  `output/projects/<EP>_<RID>/`, a window of the original episode file (shared `00_inputs/source.json` range format)
  with the sliced transcript, 16 kHz audio, speaker turns and its recipe. Unchanged picks are no-ops; moved windows need
  `--force`; `--resync` re-slices after episode corrections; a changed episode file is refused.
- **Per-shot 9:16 reframe** for episode reels: hard cuts plus face-presence runs (catches dissolves to cards), one face
  → framed on it, two-shots → follow the speaker (turns + seating, 1.5 s minimum hold), no face or unknown speaker →
  shown whole over the blurred fill; story camera moves compose on top. Verified on a real excerpt.
- **Content-type recipes** (`recipes.json`: storytelling, drama, success_story, advice, bold_opinion, emotional,
  comedy): pause thresholds applied by `audio-clean` (explicit > recipe > profile style.json > 250/80), graphics/zoom
  limits checked by `plan` (with `recipe_note` reasons in edit-plan.md), music mood, SFX palette, copy tone.
- Licensed music bed: `music.file` (data/Music only) on A06 at the recipe level with a fade-out, mixed into the preview;
  `reel music --list` with mood tags. `global.remove_pauses.protect` keeps chosen pauses.
- Templates `stat_card` (a number the speaker says) and `context_card` (one editorial line at the top).
- **Publish package**: `publish-writer` + `reel publish-check` (YouTube titles/description/chapters/tags/hashtags
  limits, Instagram/TikTok/Shorts limits from `platform-limits.json`, links only from the episode sheet, quotes only
  the speaker's words, episode SRT) and `reel publish-thumbnail` (face/sharpness-scored candidates, 1280×720 designs).
- QC: "Reel starts at its episode in-point", "Reel window inside the episode"; preflight flags variable frame rate.

**Fixed**
- HarfBuzz text used one FreeType face per font file and set its size only when created, so two sizes of one font in a
  still (a big value + a label, or a name card's name + lines for a one-weight client) rendered at the wrong size.

## 2.0.0 — 2026-10-11 · WhyNot Cut (renamed from reel-editor)
By The Why Not AI (info@thewhynot.ai). One plugin for macOS **and Windows**, from install to "drop your footage here".

**New for users**
- `/whynot-cut:start`: guided onboarding (engine, Premiere bridge, preferences, first client folder), each step verified.
- `/whynot-cut:autopilot`: edits every new clip in a client folder or across the clients folder, one combined approval.
- `/whynot-cut:preview` + `reel preview-video`: a watchable MP4 of the planned edit (pause cuts, zoom masks, every
  graphic/caption with its Premiere animation preset, cleaned dialogue, SFX), rendered by the engine without Premiere.
- `/whynot-cut:preferences` + `.claude/whynot-cut.local.md`: approval `ask|auto`, chat language (en/ar), Whisper model,
  preview on/off, clients folder. `/whynot-cut:help` cheat sheet.
- `reel doctor` (read-only readiness report with per-OS fixes), `reel scaffold` (ready-to-fill client folder with
  START_HERE.md in English and Arabic), `reel inbox` (every clip: new / in progress / done, missing brand material).
- Agents: `intake-inspector` (checks dropped material), `setup-doctor` (diagnoses machine/Premiere problems).
  All 14 agents now have "When to invoke" scenarios; all 21 skills have third-person trigger descriptions (incl. Arabic).

**Windows support (all verified by the test suite on Windows 11 + Python 3.13)**
- FCP7 XML `pathurl` is `file://localhost/C:/…` (1.x wrote `C%3A%5C…`, so Premiere on Windows could not link media).
- Arabic graphics shaped with HarfBuzz + FreeType from the client's font file (1.x fell back to arabic_reshaper, which
  breaks fonts with few presentation forms such as Thmanyah). Visually checked: joining, lam-alef, RTL base, LTR digits.
- Engine home and venv layout per OS, `reel.cmd` wrapper, cross-platform `setup/setup_env.py` installer with
  platform-marked requirements (pyobjc on macOS only; numpy/av ranges with Python 3.10–3.13 wheels).
- Premiere bridge installs into `%APPDATA%\Adobe\CEP\extensions`; PlayerDebugMode read from the registry (never written);
  `bridge-config.json` lets the panel find a custom engine home; the old `com.nh.bridge` panel is replaced.
- After Effects via `AfterFX.exe -r` and Photoshop via COM; aerender.exe; camera RAW via rawpy when installed (no crash).
- Briefs in `.docx`, `.rtf` and `.pdf` are read without macOS tools; fonts detected in Windows font folders by PostScript name.
- Face-aware photo crops with OpenCV when macOS Vision isn't available.
- CLI output is UTF-8 (Arabic JSON crashed on Windows code pages). Office lock files and desktop.ini are ignored.
- Guard hook covers the PowerShell tool (cmdlets, aliases, comma lists, redirection, -Destination/-OutFile) and Git Bash
  `/d/...` paths.

**Verified live on Windows 11 + Premiere Pro 26.5.2** (bridge 3.0.0): ping, native build with all 10 read-back checks
(ProRes 422 LT preview codec included), Premiere frame export, visual verification, QC pass, a forced rebuild with
backup, and a full revision cycle (text change → re-plan → approval gate → re-render → rebuild → frames). Fixed on the way:
- Frame export on Windows: Premiere's `exportFramePNG` accepts only backslash paths; a run where every frame failed had
  been reported as success (now `ok: false` with the per-frame errors).
- Premiere on Windows keeps imported stills locked until it quits: it now gets per-build copies of the stills, and
  unchanged stills are never rewritten, so revisions and rebuilds don't fail on locked files.
- A pipeline save-and-close before a rebuild no longer looks like an editor edit (`EDITOR_CHANGES_PRESENT`).
- Dialogue tracks are named "camera, not cleaned" when cleanup hasn't run; `reel next` asks for reference analysis
  only when the client has reference videos; `setup_env.py --system-site-packages` reuses installed packages.

**Field test on a real client clip** (Dr. Sherin Helmy, «وتزودوا بالتقوى» EP02 R02, a horizontal finished episode, religious
content, Windows). Every gap found was analysed and fixed in the plugin:
- G1 Horizontal (16:9) sources were fitted tiny into the vertical frame → **face-centred auto-reframe** (`global.base_scale_percent:
  "auto"`; preflight measures cover scale + face offset; Premiere XML and preview use it).
- G2 Whisper caches on the machine were 3 MB partial downloads, undetected → `reel doctor` reports complete vs partial models;
  `reel model-download` fetches/resumes deliberately. G2b Hugging Face "Xet" transfers died on Windows (WinError 10038) →
  the engine uses plain HTTPS downloads by default (`WHYNOT_HF_XET=1` re-enables Xet).
- G3 `Profile.jpg` was classified as a client brief → name hints are kind-aware (images get image roles; brand images
  get `brand_image`; licence files next to B-roll get `broll_license`).
- G4 Faces turned sideways weren't detected → OpenCV profile detector (both directions) as fallback (4/9 → 7/9 frames).
- G6 No HEX codes in any document (brand colours only in a poster) → `measured_palettes` from brand images, cited, for
  the client-researcher to assign; client-db reports roles honestly.
- G7 "Fonts not installed" was a mandatory QC failure although the build uses rendered stills → advisory unless live
  text is used (AE/PS extras, native caption track).
- G8 Graphic cards burned into a finished episode were cropped to 9:16 (text cut) → per-frame speaker/cutaway detection
  (face OR similarity to speaker frames; dissolves handled; measured 0.89–0.93 speaker vs 0.17–0.38 card) and cutaways
  shown whole. G10 Like the agency's editor: **the whole card over a blurred fill** (Premiere: cover copy on V1 +
  Gaussian Blur added by the bridge, card on its own track; preview the same).
- G9 Generic texts said "her words"/"she" (first client) → neutral "the speaker".
- G11 **Licensed stock B-roll videos** (`data/Broll` + SOURCES/licence): new `broll_video` template, video-only XML clips
  (B-roll audio can never reach the dialogue), preview playback, QC coverage, licence warning.
- G12 Generic docs said "Thmanyah only" → the client's brand fonts. G13 **Religious content review** (Quran wording from
  the Mushaf between ﴿ ﴾, hadith/story attribution, no fatwa on screen): the content reviewer follows the profile
  `domain` (medical | religious | general). G14 Template colours were hard-wired (primary box + white text) →
  `box_role`/`text_role` per template (e.g. a cream hook box with dark text). G15 one still-folder mapping
  (`still_category`) instead of five copies that had drifted apart. G16 a second audio stream (AAC + AC3) is reported.

**Field test, round 2: reel R02 cut from the full 29.97 fps episode, through a live Premiere build** (G17–G45)
- *Transcription.*
  - G17 Whisper crashed with newer PyAV (`metadata_errors`): the engine decodes the audio itself.
  - G18 An NVIDIA GPU silently fell back to the CPU (missing `cublas64_12.dll`). The doctor now names the GPU and the
    missing library, and `reel gpu-enable` installs it with the editor's OK. The GPU is skipped up front instead of
    failing after loading 3 GB.
  - G19 Glossary hits use Arabic normalisation (آمنوا = امنوا) and phrases. Short terms keep their hamza, so the
    verse word «آية» no longer matches Egyptian «ايه».
  - G20 The review lists profile names that Whisper wrote differently (نادال → «نضال», ديوكوفيتش → «جيكوفيتش», at
    high confidence).
  - G21 "Uncertain words never on a graphic" is enforced: corrections carry `flags`, `reel plan` refuses them on
    graphics, QC lists them, and a verification goes stale when the transcript changes. `reel transcript-relisten`
    re-decodes flagged words three ways («حضار المدر» → «هغير المضرب», 2 of 3).
  - G28 Quotes in the client's documents (a reels plan) are matched against the transcript.
  - G35 The editor's finished reel is a human transcript too: its captions settled «إيمانهم».
  - G37 Corrections re-anchor by word text after a re-transcription renumbers the words.
- *Audio.*
  - G24 The cut check passed a 36 s stretch that came back as one word. It now decodes ≤ 20 s chunks split at the
    cuts, counts collapsed stretches as missing, and needs ≥ 85 % of the words matched.
  - G25–G27 audio-clean measures the source first: dual-mono → one channel; hum notches only on mains harmonics
    (50/60 Hz) that stand out in the pauses; no spectral denoise on an already-clean master (55 dB S/N).
  - G38 Pause settings come from the client's style.
- *Reels from long files.*
  - G30 A reel is a range of a longer raw file: `reel range --in --out --snap`, `00_inputs/source.json`. Transcript,
    audio, preflight, previews, preview video and QC all work on the reel's clock, and Premiere links into the
    original with handles. Podcast mode reuses it.
  - G31 `--video-id` silently processed the FIRST raw clip of a folder; it now picks its own clip, or refuses.
  - G36 A range snaps to the nearest pause (the reel started mid-word).
- *Frame rate.*
  - G32 The sequence frame rate follows the client (`sequence-settings.json`, NTSC aware) instead of a fixed 24 fps,
    which juddered on this 29.97 fps client.
  - G33 FCP7 XML wrote invalid fractional timebases for 29.97 media; it now writes timebase 30 + NTSC, with exact
    ticks.
  - Premiere built R02 at 29.97 fps, and all read-back checks passed.
- *Edit and graphics.*
  - G29 `global.cut_words` cuts fillers (the plan's repeated «يعني») from picture, sound and captions.
  - G39 edit-plan.md reads on the reel's timeline: real camera moves, auto zooms apart, coverage including cutaways.
  - G40 Preview backgrounds used timeline time as source time after pause removal.
  - G41 Captions can sit on a translucent box, as in the editor's reel.
  - G42 Captions jumped off-screen to dodge cards placed at the top; they now move only on overlap.
- *QC and handoff.*
  - G34 Re-running preflight no longer moves a clip's status back.
  - G43 Premiere frames include the cutaways and camera moves.
  - G44 QC failed every bridge build (it looked for the fallback XML's manifest).
  - G45 Handoff texts said 24 fps.
  - QC dialogue sync is range-aware.
- R02 ends READY_FOR_HUMAN_EDITOR: QC ok, cutaway blur confirmed in Premiere's frames.

**Pipeline**
- Whisper uses an NVIDIA GPU automatically (float16) and retries on CPU if the CUDA libraries fail at first inference.
- Default caption hiding now covers every text graphic (hook, statement, term, checklist) unless the profile says
  otherwise; the preview showed captions repeating the hook and crossing a checklist under the old default.
- `reel next` includes the preview video step and its staleness. `inbox`/session hook treat a clip as started only
  once it has a transcript (preflight alone no longer marks it "in progress").
- Pillow 13 compatibility (no `mode` argument to `Image.fromarray`).
- Hardening from the plugin-validator and skill-reviewer passes: every agent/skill frontmatter is strict YAML; hooks
  never write `__pycache__` into the plugin; plugin options reach `reel` through `CLAUDE_ENV_FILE`; the guard blocks
  any write to Adobe's CSXS preferences and subagents changing preferences; `reel settings --set` rejects unknown keys
  and invalid values; `clients_root` from the preferences file makes `--root "<name>"` work anywhere; fan-out agents fall
  back to sequential checks when nested subagents aren't available; preferences and approvals are resolved per client.
- Tests: 72 (new `test_crossplatform.py`: paths, HarfBuzz shaping/RTL, PowerShell guard, preferences, onboarding,
  document readers, animation presets; the full chain now renders and probes the preview MP4).

## 1.0.7 — 2026-10-11 (Windows test fixes)
- Windows: the test suite passes (48 tests). Discovery stores paths with `/` on every OS (on Windows `data/`
  documents were not seen as editing references); the QC composite closes its temporary PNG before deleting it;
  the AE/PS syntax tests use Node.js when `osascript` is missing; tests read files as UTF-8.

## 1.0.6 — 2026-10-11 (plugin-validator warnings, thewhynot.ai ownership, portable hooks)
- Guard hook: destinations that are not the last argument are checked — `cp/ln/install -t DIR`, ffmpeg outputs
  followed by options (`ffmpeg -i x data/out.mp4 -loglevel error`), `-progress`/`-passlogfile` files — and
  `find` with `-delete`, `-exec rm|mv|…` or `-fprint*` on a client's sources (or from the client folder itself).
- Hooks run through `hooks/run_python.sh`, which picks the first real Python 3.8+ (skips the Windows Store stub).
- `clients_root` setting is used: `--root` takes a bare client folder name, the "--root required" error lists the
  clients there, and a session opened in that folder is told which client folders it holds.
- Premiere bridge: a job whose script is missing gets an error result instead of hanging until the caller times
  out; a lost `evalScript` reply releases the queue after 20 min (a late reply is ignored).
- Helper agents get the colour of the agent that starts them (claim-checker red, frame-inspector pink,
  graphic-checker orange, segment-proofreader blue). Author is thewhynot.ai (http://thewhynot.ai/). Proprietary `LICENSE` file added.

## 1.0.5 — 2026-10-10 (fixes from the independent QC re-test, applied to C0238)
- Jump cuts: every cut after a removed pause changes the zoom, also inside a punch-in that spans the cut (steps one
  mask increment in, or out above 1.2). QC check "Every jump cut changes the zoom". C0238 had 3 unmasked cuts.
- Photo crops centre on the detected face (macOS Vision, `pyobjc-framework-Vision`); `crop_center` overrides.
  C0238 GFX_006 had cut through the eyes.
- Hook titles: `bar_style` `underline` | `box`; the Nahla profile uses `box` (white text on full teal boxes).
- QC check: every overlay still inside the safe area (C0238 name card crossed the bottom UI zone; moved up).
- Captions lift above a card (name card / glass / CTA) instead of overlapping it.
- `captions_hidden_ranges` (source time) are remapped to the sequence clock on the native caption track and the AE
  extra too (the animated-caption path already did); both read the sequence-clock captions.
- `reel next` reports STALE steps (inputs changed after a step ran) instead of "done".
- QC no longer warns about missing AE renders / .aep / PSDs unless the AE/PS extra was used.
- Profile notes: delivered-audio numbers corrected (22.8 dB, not the 23.7 dB denoise-only stage).

## 1.0.4 — 2026-10-10
- Arabic lines always get a right-to-left base direction (CoreText and fallback renderer). A line starting with a Latin word
  ("evidence إنها ممكن تساعد", C0238 GFX_003) was laid out left-to-right with the first word on the wrong side.

## 1.0.3 — 2026-10-10 (fixes from the live end-to-end test)
- Audio: removed compressor + dynamic loudnorm (they gave back most of the denoise gain: 23.7 → 16.5 dB S/N); now gain + true-peak limiter (C0238: 16.6 → 22.8 dB on the delivered file, −14.6 LUFS). `--nr`, `--expander` options.
- QC judges speech-to-noise on the DELIVERED file (was an intermediate stage).
- Cut verification maps every difference to source time: "missing" only when a removed pause touches the words; lists cut points to listen to.
- Editor's own saves in Premiere no longer invalidate visual verification; `ppro-build` refuses to rebuild over them without `--replace-edited`; QC reports them.
- Guard hook follows `cd` in a command chain, treats each line as a command, ignores heredoc bodies.
- `transcribe --force` refreshes the machine originals used by corrections.
- `ppro-frames` probe times stay inside the sequence. Music cue points follow the pause-removal remap.
- Agents that fan out sub-agents wait for every result before reporting.

## 1.0.2 — 2026-10-10
- `ppro-frames` writes each run to a fresh `premiere_frames/run-<time>/` folder with a labelled `_sheet.jpg` (stale frames from an earlier build had sat next to new ones).
- Verified live: bridge 2.0 ping from the installed plugin; C0238 test build PRPROJ_BUILT 10/10 checks, 47 graphics, 13/13 frames.

## 1.0.1 — 2026-10-10
- `reel` accepts `--root/--video-id/--profile` after the command too (as the skills write them).
- Wrapper never writes `__pycache__` into the plugin folder. README, eval cases (6).

## 1.0.0 — 2026-10-10
First plugin release. Ported from the `dr-nahla-hunter-editor` skill (v2).
- Generic engine with client profiles; Dr. Nahla Hunter is the first profile (output for C0238 is byte-identical to v2).
- 16 skills (lead-editor `edit`, `revise`, `status`, `fix-audio`, `new-client`, `setup`, `handoff`, `adobe-extras` + 8 craft skills).
- 12 agents: 8 stage specialists + 4 parallel sub-agents (segment-proofreader, frame-inspector, graphic-checker, claim-checker).
- Hooks: client `assets/` and `data/` read-only; AE/PS opt-in (`--extras`); subagents can't approve plans or record verdicts; client-folder session context.
- Premiere bridge 2.0: whitelists the stable `~/.reel-editor/ppro-scripts` folder (plugin path changes on update).
- `reel` CLI on PATH, `reel setup`, `reel profile`, `reel client-init`; pinned `setup/requirements.txt`.
