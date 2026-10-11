# WhyNot Cut: what the main enhancement session established (session 3e1731a4)

Source: digest of session `3e1731a4-7adf-4831-96e5-e45d3dc90401`, 2026-10-10T21:47Z to 2026-10-11T11:26Z (UTC; the user's local clock is UTC+3, so "01:36" local = 22:36Z).
Session title as seen by peers: "Reel editing plugin enhancement".

Notes on the source:
- Digest lines 2127–3989 are a replay of lines 5–1893 caused by the first `/compact`. They are identical except for one assistant line. New content resumes at 06:57Z, after the second compact.
- Most of the early "USER" blocks are plugin-dev skill bodies (plugin-settings, plugin-structure, hook-, skill-, agent-development, mcp-integration). They are not user words.
- "[Image …]" user turns at 23:10, 23:51, 00:55 and 00:56 have no text. They were probably contact sheets or frame strips.
- Gap list G62–G69 comes from `D:\0 Work\0 Pegasus IMC Agency\00 TWN\0 TWN AI\Editing Plugin\round4-gaps.md`, which the session wrote and linked at its end.

---

## 1. User requirements and wishes

### Original brief (21:47Z, via `/plugin-dev:plugin-settings`)
- **Understand the plugin first.** "check the last version, take a deep breath and understand this plugin very well, deep, in very technical way and check each file and check all data". The last version was `1.0.7.zip`, then called reel-editor.
- **Use the plugin-dev toolset.** "run all plugin dev skill and agents in logic flow one by one, agents and sub agents to enhance the plugin".
- **Branding.** The plugin is by "The Why Not AI", info@thewhynot.ai.
- **New components.** "create all need skill, agents, sub agents to make it easy to use".
- **Onboarding.** "any one install it make a steps with him until just add his raw material then edit everything based on the current structure". This means a guided first run that ends with "drop your raw footage here" and full automation after that.
- **Name.** "give it a cool name that related to the why not". Result: WhyNot Cut.
- **Platforms.** "make it work with mac and windows and work with adobe apps".
- **Self-checking.** "in each step check, evaluate, enhance what you did".
- **Scope.** "Don't stop until you finish make this plugin the most strongest version".

### Follow-up wishes, in order
- 22:23Z: "continue and finish everything".
- 22:32Z: "walk me through the first Premiere build and make sure it's working well".
- Autonomy, repeated many times:
  - "go with everyting and don't stop" (22:35Z)
  - "get accsee to everything and go" (22:38Z)
  - "go with the best and don't stop" (22:42Z)
  - "idk, plase check and go" (22:44Z)
- 22:56Z: "now test it on a real client clip".
- Mid-turn, in the summary: "now make while working you find gaps and things you miss, analyze it and add it". Every gap found in field use should be analysed and fixed in the plugin. This became the G-number gap log.
- Whisper model: the user picked **large-v3 (~3.1 GB)** when asked.
- R02 approval: "Approve, keep statement (Recommended)".
- 00:24Z: "run gpu-enable and go with everything".
- 07:08Z: «هو كده الشات التاني اللي شغال دلوقتي بيعمل ايه وهل محتاج مني اني اعمل حاجه هنا ولا اكمل هنا» ("what is the other chat doing now, and do I need to do anything here or continue here?"). He wants clear status across parallel chats and a clear statement of what is needed from him.
- 09:35Z: «مش عارف شوف كده واعملها انت» ("I don't know, look into it and do it yourself"). Said about uninstalling reel-editor and installing the WhyNot Cut zip. He wants Claude to do installation work, not him.
- 09:47Z: «تمام، هفتح شات جديد واجرب /whynot-cut:start … شوف الشات وتابع معاه» ("OK, I'll open a new chat and try /whynot-cut:start … watch that chat and follow it"). He wants a supervising chat that monitors and coaches the working chat.
- 09:55Z: «كمل تابع معاه وقولي لو محتاج حاجة» ("keep following it and tell me if you need anything").
- 09:56Z: «اعمل انت كل حاجه معاه وخلص كل حاجه — انا عاوز النتيجه النهائية — متسالش تاني» ("you do everything with it and finish everything; I want the final result; don't ask again"). This is a fully autonomous, no-questions mode that delivers a final result.
- 10:01Z: «تمام كمل لحد النهاية» ("OK, continue to the end").
- 11:09Z: "what you are doing", then "stop for now". He wants on-demand progress visibility and a clean pause/resume. The resume word is "continue".

### UX wishes that follow from the above
- **Any editor can use it.** Install, then guided steps, then just add raw material.
- **Arabic-first communication.** The user writes Egyptian Arabic. From 07:08Z the assistant answered in Egyptian Arabic and the saved preference is `language: ar`. Earlier technical reports were in English.
- **Few or no questions.** The user repeatedly overrides stops. The approval preference is `ask` per client, but he delegates in practice ("go with everything").
- **Claude does the machine work.** This includes installs, plugin swaps and diagnostics. The user does not know where commands run ("idk").
- **One short list of what only a human can do.** Requested at 09:56Z ("collect what isn't mine to decide in one list at the end").
- **Watching progress.** Monitoring another chat and reporting.
- **Speed.** GPU transcription was accepted immediately. The user stopped the run when told it needed 1–2 more hours.

---

## 2. User complaints and dissatisfaction (explicit or implied)

- **PlayerDebugMode setup friction (22:32–22:45Z), the biggest pain point.**
  - The user said "done" five times, but the registry never changed.
  - Cause 1: the assistant's first command used PowerShell-only `foreach`, which fails in Command Prompt. The assistant said "My fault for giving a PowerShell-only line".
  - Later causes: the paste never executed, the Terminal tab stayed empty, and the user may have used an admin window.
  - The user's answer was "idk, plase check and go".
  - What fixed it: a one-click **Run** code block, `powershell -NoProfile -Command "reg add 'HKCU\Software\Adobe\CSXS.12' /v PlayerDebugMode /t REG_SZ /d 1 /f"`.
  - Lesson: manual registry steps fail for this user. The plugin needs a one-click or self-verifying flow.
- **"get accsee to everything and go".** The user wanted Claude to have full access. Claude refused to set PlayerDebugMode itself, even in bypass mode, and the sandbox blocked even read-only checks once it tried to step outside. The user experienced this as stalling.
- **Confusion about parallel chats (07:08Z).** He did not know what the other chat was doing or whether he needed to act. Several peer sessions ran at once: podcast, 2.1.1 fixes, AE motion, chat management and start.
- **Manual plugin swap (09:35Z).** «مش عارف شوف كده واعملها انت»: he could not do the reel-editor → WhyNot Cut swap himself.
- **Too many questions (09:56Z).** «متسالش تاني» ("don't ask again"). The new start chat asked 4 onboarding questions, then a copy question, then a "start now?" question.
- **Low visibility, then a stop (11:09Z).** "what you are doing" followed 11 seconds later by "stop for now", after a 1–2 hour estimate. This suggests either a lack of visible progress or that the run was taking too long.

---

## 3. Decisions made, with reasons

### Identity and packaging
- **Name and manifest.** Renamed to **WhyNot Cut**: plugin `whynot-cut`, displayName "WhyNot Cut", version 2.0.0. Author `{"name":"The Why Not AI","email":"info@thewhynot.ai","url":"https://thewhynot.ai/"}`.
- **Marketplace.** Named `thewhynot-ai`, with plugin source `./whynot-cut`.
- **Install path.** `/plugin marketplace add`, then `/plugin install whynot-cut@thewhynot-ai`, or upload the zip in the desktop app's plugin settings.
- **Release builds.** `package.py` builds `whynot-cut-<ver>.zip`. It excludes junk and `__pycache__`, sets 0755 on scripts and tests the zip. The original `1.0.7.zip` is kept untouched.
- **Line endings.** `.gitattributes` sets LF everywhere and CRLF for `.cmd`.
- **Dr. Nahla's profile** is shipped in the package. Decision deferred to the user: remove it before sharing outside the agency.

### Engine and platform
- **Engine.** Python `reel` CLI in a venv at `~/.whynot-cut`, with legacy fallbacks `~/.reel-editor` and `~/.dr-nahla-editor`. Windows uses `venv\Scripts\python.exe` and `bin/reel.cmd`.
- **New module `plat.py`.** Holds platform logic: engine_home, native_path, font_dirs, Adobe app discovery, aerender, CEP extensions dir, read-only PlayerDebugMode check, debug_mode_commands and gpu_info.
- **Arabic on Windows.** HarfBuzz (uharfbuzz) plus FreeType gives real OpenType shaping and RTL. macOS keeps CoreText first, because it was already checked with Thmanyah.
- **Face detection.** OpenCV frontal plus profile, in both directions. macOS uses Vision.
- **Whisper.** faster-whisper with CUDA auto-detect and CPU retry.
  - `HF_HUB_DISABLE_XET=1` by default, because the Hugging Face Xet transfer fails on Windows with WinError 10038.
  - A model counts as complete only if `snapshots/*/model.bin` is over 50 MB. Partial copies are detected.
  - New command `reel model-download`.
- **UTF-8 stdio** is forced, because the engine crashed when its output contained Arabic.
- **GPU enabling (`reel gpu-enable`).** On Windows it pulls cuBLAS from NVIDIA's CUDA redist (`redistrib_12.9.1.json`, sha256-verified, extracts `cublas64_12.dll` and `cublasLt64_12.dll` into `engine_home/cuda/bin`), with a pip fallback. Reason: PyPI was crawling at about 40 KB/s.
- **Transcription concurrency.** One clip at a time on a GPU, because parallel jobs share its memory and four large-v3 jobs would OOM. At most 2 on CPU.
- **Download consent.** Ask before the first Whisper download (large-v3 ~3 GB, turbo ~1.6 GB), and transcribe one clip first so the model downloads once.

### Safety and guardrails
- **Guard hook coverage.** It covers Bash, **PowerShell** and the file tools.
  - Client `assets/` and `data/` are read-only.
  - Adobe preference (PlayerDebugMode) writes are blocked.
  - Subagents cannot approve plans, record verdicts or change preferences.
- **PlayerDebugMode is always set by the user**, even in bypass mode and even with the user's go-ahead. Reason: it disables Adobe's extension signature check, so it is a security setting that stays the user's decision.
- **Evidence gates.** Plan-approval fingerprint, so a changed plan is refused until re-approved. Visual verification of Premiere's own exported frames. QC.
- **Delegated approvals.** Recorded with `--by delegated --note "<user's words>"`. R05's approval and R02's re-approval were recorded from "go with everything".
- **Frontmatter.** YAML descriptions are quoted. `allowed-tools: Bash(reel *), PowerShell(reel *)` pre-approves for the invoking turn only.
- **No stray bytecode.** `PYTHONDONTWRITEBYTECODE=1` in hooks, because SessionStart was writing `.pyc` into the installed plugin.

### Preferences (plugin-settings pattern)
- **File.** `.claude/whynot-cut.local.md` with YAML frontmatter.
- **Keys.** `editor_name`, `language en|ar`, `approval ask|auto`, `whisper_model`, `preview_video`, `clients_root`, `notify_done`.
- **Lookup order.** Nearest file, then the clients-root env, then `~/.claude`.
- **Per-client resolution.** Use `reel settings --root "<CLIENT>"`. Reason: the skill reviewer found autopilot could apply one client's `approval: auto` to another.

### Premiere build
- **Native project.** Built through the CEP bridge panel: file queue, heartbeat, whitelisted scripts dir, `bridge-config.json`. CEP id `ai.thewhynot.cut.bridge`; legacy `com.nh.bridge` is only in LEGACY_EXT_IDS.
- **XML fallback.** FCP7 XML (xmeml v4), with `pathurl` = `file://localhost/C:/...` on Windows.
- **No hang.** The build stops with a clear "bridge not running" message instead of hanging, and the XML is offered as a manual-import fallback.
- **Locked stills.** Each build gets its own copies of the stills, and unchanged stills are never rewritten. Reason: Premiere on Windows locks imported stills until it quits.
- **Editor-change detection.** Uses a **content signature** of the .prproj, not the save time. Reason: auto-save, and saves of another open reel, caused false "editor changed it" refusals (G60).
- **Frame export.** Native backslash paths on Windows. Activate the right project first when several are open (G61).

### Pipeline and features added
- **New skills.** `start` (guided onboarding with a START_HERE in English and Arabic), `autopilot` (edit all new clips), `preview` (MP4 proxy without Premiere), `preferences`, `help`.
- **New agents.** `intake-inspector` and `setup-doctor`.
- **Captions vs graphics.** Captions hide while text graphics are on screen. Reason: the preview showed captions repeating the hook and overlapping the checklist. Later conflict: R01 and the client's V05 keep captions on during the hook.
- **Range reels.** `reel range --in --out --snap` cuts reels from a long episode without re-encoding and never mid-word. Uses `00_inputs/source.json`.
- **Frame rate.** Per-client sequence fps (`seq_rate`/`seq_fps`), because Dr Sherin's footage is 29.97.
- **Wide sources.** Auto-reframe: cover scale plus a face-centred offset.
- **Cutaways.** AUTO_CUTAWAY via 2 fps sampling, face OR histogram similarity ≥0.55. Cards and other people are shown whole over a blurred fill. A cut to another person is flagged for the editor.
- **B-roll.** Licensed stock videos via `broll_video` (video-only clips). B-roll can never overwrite the dialogue track.
- **Brand colours.** Measured from images when no HEX codes are given.
- **Content review is domain-aware** (medical, religious or general): exact Mushaf wording, attributed stories, nothing shown as a fatwa.
- **Uncertain words never go on graphics.** Enforced, with a GPU "second listen" (`transcript-relisten`).
- **Audio is measured first.** Denoise and hum notch only as needed. The "no speech cut" check compares two deterministic (temperature 0) readings.
- **Reference analysis** is cached once per client.
- **Other options.** 4:5 framing (AUTO_WINDOW over a blurred V1). Sharpen and grain on upscaled crops.
- **Caption rules.** `box_all`, `strip_punctuation`, `lead_in_ms` (0.2 s), boxes on fills, card avoidance.
- **Export naming** follows the client pattern, e.g. `EP02_R05_Traffic_Light_Shar_9x16_AR_v01.mp4`.
- **Series consistency.** R05 uses 9:16, not 4:5, so the series stays uniform, as the client plan says.
- **Out-points stop before another speaker.** R05 ends on Dr Sherin's «وعلى التعاون», because the plan's 14:51 out-point runs into the host.

### Coordination and workflow
- **No commits or zips without being asked.** This session never committed; the podcast peer made "Snapshot" commits. It did not rebuild the zip mid-feature, to avoid shipping half of the podcast feature.
- **Ownership.** Files were split between parallel sessions to avoid overwrites. One owner per client folder: the start chat handed EP02 to this session and stopped its own writers.
- **Copy only what is clean.** When moving test material to the real client folder, only `reel-profile/` was copied, because `client_database/` holds absolute whynot-test paths in 6 files. The client-db was rebuilt. `EP02.mp4` went into `data/Episodes` (podcast slot), not `data/Raw`. The test projects and the pre-cut R02 excerpt were not copied.
- **Clients root.** The user chose `D:\WhyNot Clients`. The assistant had suggested `00 TWN`, but the original Dr Sherin folder there was not in the plugin's layout.
- **Round 4 (EP02).**
  - The agency's `Reels_Plan_EP02.md` (10 reels, priority R02 ← R05 ← R01 ← R06 ← R03 ← R07 ← R04 ← R08 ← R09 ← R10) was the base. The analyst added R11 and R12 as extras (12 candidates).
  - **R02 was skipped**, because the agency had already edited it as V05.
  - 9 reels were made: R01 and R03–R10.
  - No music, because no licensed music was supplied, which matches the agency plan.
  - Hard cuts only.
  - Where the agency plan, the V05 reference and the profile conflicted, the profile won: no caption stroke, hook about 3 s, profile graphic positions, end card with the show name.
  - No verse, hadith or unverified poet name on any graphic.
- **G62 code fix deferred.** The font-roles fix was postponed until the AE session merged 2.2.0, to avoid concurrent edits. A profile workaround was applied instead ("headlines Bold").

---

## 4. Verified working (tested live, with evidence)

### Tests (Windows, this PC)
- 64 pass (4 skipped), then 65, 68, 72, 77, 144, 186 and 190.
- The podcast peer reached 197 at 2.1.0. The 2.1.1 branch reached 210, then **212 OK, 4 skipped**.
- Tests also pass from the unzipped release file (2.0.0).
- Tests must run under `~/.whynot-cut/venv`. System Python skips 5 HarfBuzz tests (9 skipped instead of 4).

### Onboarding commands
- Ran through the real wrapper on Windows. The 12-second test clip's preview MP4 rendered in under a second.

### Arabic rendering on Windows
- HarfBuzz output was checked by eye with **Arial**: joined letters, the لا ligature, RTL order. Thmanyah was not checked.

### First live Premiere build (22:45Z, synthetic demo client `whynot-test\CLIENT`, CLIP1)
- **Premiere 26.5.2** (Premiere Pro 2026) answered the bridge in about 1 s.
- The project was built and saved by Premiere, with **all 10 read-back checks passing**: 1080×1920, 24 fps, ProRes 422 LT preview format (previously unsure on Windows).
- Premiere rendered 7 frames of its timeline, all checked at full size: Arabic joined and RTL, zoom change at the cut, checklist slide-in, caption above the name card.
- QC passed with no blocking failures.
- **Revision flow verified.**
  - The hook text was changed, and the changed plan was refused until re-approved.
  - The stills were re-rendered and the project rebuilt, with the old version kept as a backup.
  - Premiere's frame shows the new text «لازم أبقى عارفاها», and the preview was refreshed.

### Real client field test (Dr Sherin Helmy, EP02, folder `whynot-test\Dr Sherin Helmy`)
- **G8.** Preflight found the burned-in card at 37.8–50.8 s.
- **R02 (tennis-racket reel).**
  - Cut from the full EP02 episode at 29.97 fps, 47.8 s, with pauses and the filler «يعني» removed.
  - Built in Premiere and passed QC. Premiere's frames were checked, including the card section.
  - Project: `whynot-test/Dr Sherin Helmy/output/projects/R02/07_premiere/project/R02_SH_EDIT.prproj`.
- **R05 (traffic-light joke).** 52 s at 29.97 fps, built and passed QC. Punch-ins on «120 كيلومتر» and «140 كيلومتر», comic pauses kept.
- **4:5 framing** verified in Premiere.
- **"No words cut" check reliability.** R05 1.0, R02 0.945.
- **GPU.** `reel gpu-enable` fetched cuBLAS from NVIDIA in about 3 minutes, checksum-verified. Whisper on the RTX 4060 runs about 10× faster than real time: one reel takes 20 s instead of 1 min 50 s.
- **G59–G61 verified.**
  - R02 frames during the card show captions boxed and above the card.
  - Frame export worked for R02, then R05, then R02 again, with several projects open.
- **Podcast peer run.** EP02TEST_R02: all 11 build checks true, 17/17 frames viewed, QC ok, publish-check ok.

### Install swap (09:35Z)
- The assistant removed reel-editor 1.0.7 and installed WhyNot Cut 2.1.1, after backing up the plugin settings.
- `doctor` reports READY: engine ready, Premiere responding, GPU working. The AE session's bridge 3.1.0 stayed installed.

### New chat running `/whynot-cut:start` (09:47–09:55Z)
- Machine READY on the RTX 4060. Bridge 3.1.0 answered ping.
- Preferences saved machine-wide: name Yunus, Arabic, `approval: ask`, `whisper_model: large-v3`.
- Client folder `D:\WhyNot Clients\Dr Sherin Helmy` scaffolded and opened in File Explorer.
- Test material copied with robocopy (exit 1 means success): 3 fonts, brand image, photo, EP02 into `data\Episodes`, 2 references, tuned profile.
- Profile `dr-sherin-helmy` recognised. EP02 (1.1 GB) detected in the podcast slot.

### Round 4 run on the installed 2.1.1 (10:00–11:09Z)
- Full 35-minute EP02 transcribed on the GPU with large-v3 in 4 chunks, about 4 minutes.
- **Reels plan.** `reels-plan` compiled 12 candidates with 0 errors and 1 warning (count above the 4–9 guide). Output: 17 chapters, 3 speakers, 32 turns.
- **Transcript.**
  - `transcript-correct` applied 132 corrections and left 23 flags.
  - `transcript-relisten` covered 19 windows and settled 5 flags.
  - All **29 segment-proofreaders returned**, so nested fan-out worked in this run.
  - Restorations include «والطيبات لله» (dropped by Whisper), «معراج المؤمن» and «قاب قوسين».
- **Publish package.** `publish-check` ok with 0 errors and 0 warnings: 5 titles, description, 17 chapters, 24 tags, 3 thumbnails (viewed, Arabic joined, readable at feed size).
- **Preflight** ran for all 9 reels plus the reference analysis.
- **Audio cleanup** passed for all 9 reels: -14.4 LUFS (the agency target is -14) with **0 missing words** in every reel.
- **Series style** authored from V05: 14 mandatory rules, 11 preferences, 5 optional, 9 conflicts.
- **R01.** `reel plan` gave 0 errors: 58.8 s, 3 graphics, 1.23 s of pauses removed, emotional pauses kept.
- **R10.** `reel plan` gave 0 errors: 55.12 s, 1652 frames at 29.97 fps, no cuts.

### Bridge 3.1.0 (two-host) on Premiere
- The AE session ran `ppro-frames` on PODCAST-TEST EP02TEST_R02: 17 frames, verify pass, QC ok, handoff READY_FOR_HUMAN_EDITOR.

---

## 5. Failures, bugs and gaps found

### Validator findings (plugin-validator, 22:25Z): all fixed except W4
- **C1.** Four frontmatter blocks were not valid YAML, because an unquoted `description:` contained `": "`. Files: client-researcher, motion-designer, story-editor and `skills/setup` ("reel: command not found"). Fixed by quoting.
- **C2.** `.pyc` files and `__pycache__` were in the tree, because SessionStart wrote bytecode into the installed plugin. Fixed with `PYTHONDONTWRITEBYTECODE`.
- **W1.** Old "reel-editor" branding remained in `hooks/run_python.sh`, including a user-visible message. Fixed.
- **W2.** Nested fan-out may not run, because subagents cannot spawn subagents. Affects qc-reviewer, medical-reviewer, motion-designer and transcript-editor. A fallback was requested. Reported resolved, but how is not stated. In round 4 the 29 proofreaders did run.
- **W3.** `engine_home`/`clients_root` user config may not reach `reel` (`CLAUDE_PLUGIN_OPTION_*`). Reported resolved.
- **W4.** The old reel-editor plugin was still enabled and clashed. Fixed only at 09:35Z by the swap.
- The official `claude plugin validate` was **not run**, because `claude` was not on the Bash PATH.

### Skill-reviewer findings (22:27Z): "30-plus issues, all fixed"
- **C1.** Autopilot applied one global `approval` to every client, and `approve-plan` lacked `--video-id` with several clips.
- **C2.** The edit skill read preferences from the current folder while the engine read them from the client folder.
- **C3.** No consent before the Whisper download in autopilot/edit. Up to 4 parallel large-v3 jobs would OOM the GPU and fall back to CPU silently.
- **C4.** `start` had no recovery when `reel` is not found. The plugin's bin/ is on PATH only in sessions started after install.
- **M1.** The preferences file could not be found from most sessions, and re-runs failed. The digest truncates here.

### Windows problems fixed in the 2.0 work
- XML media paths broke every Premiere import on Windows ("Link Media").
- No Arabic shaping on Windows. Fixed with HarfBuzz.
- The installer was Mac-only.
- The bridge panel installed only on Mac.
- AE and Photoshop automation now run on Windows.
- Word, RTF and PDF briefs are readable on Windows.
- Crash on Arabic output (UTF-8).
- The guard hook did not cover PowerShell.

### Bugs found by the first live Premiere run (fixed)
1. **Frame export on Windows** failed while reporting success. Premiere needs backslash paths.
2. **Rebuilds and revisions** would fail on Windows, because Premiere locks stills. Each build now gets its own copies.
3. **False "editor changed project"** caused by the plugin's own save on close.
4. **Dialogue tracks labelled "(clean)"** when not cleaned. They now say "camera, not cleaned".

### Real-client gaps G1–G16 (all fixed, 77 tests)
- G1 horizontal footage would show tiny with black bars. Fix: face-centred vertical reframe.
- G2 Whisper downloads failed on this PC (Xet) and left partial copies nobody noticed. Fix: plain downloads, partial detection, `reel model-download`.
- G3 a photo was classified as a client brief.
- G4 a speaker turned sideways was not detected. Fix: profile-face detection.
- G6 brand colours could only come from HEX codes. Fix: measured from the poster.
- G7 uninstalled fonts failed QC, although Premiere uses only rendered stills.
- G8/G10 a card burned into the episode would be cropped in half. Fix: detected and shown whole over a blurred copy, like the editor's V05.
- G9/G12 generic text still said "her" and "Thmanyah only" from the first client.
- G11 no licensed stock B-roll video support. Fix: `broll_video` template.
- G13 review knew only medical claims. Fix: domain-aware religious review.
- G14 graphic colours were fixed. Fix: cream box with dark text possible.
- G15 five copies of one folder mapping had drifted apart.
- G16 the episode's second audio stream was used silently.
- G5 is not described in the digest.

### G17–G45 (fixed, 144 tests; details in the CHANGELOG)
- One raw file was treated as one video. Fix: range reels from an episode (`reel range`).
- With several raw clips, every video silently used the first file.
- Frame rate was locked to 24 fps, which judders on 29.97 footage. Fix: per-profile fps.
- "Never put an uncertain word on a graphic" was only a written rule. Fix: enforced, plus second listen.
- Fixed denoise and hum filters ran on an already-mastered mix. Fix: measure first. The "no speech cut" check had missed a lost 36 s stretch.
- Client documents were not used as transcript evidence. Fix: the reels plan and the editor's captions now count; they settled «إيمانهم».
- QC failed every Premiere build, and captions jumped off-screen. Both fixed.
- The leftover test folder `R02_TEST` could not be deleted, because the old plugin's hook blocked it.

### G46–G58 (fixed, 186 tests)
- Sharpening and grain on the upscaled crop.
- 4:5 framing option.
- No commas in burned captions, and captions lead in by 0.2 s.
- Export filename pattern.
- Cuts to another person (host or wide shot) are detected, shown whole and flagged.
- Per-reel name list.
- Whisper's hallucinated «اشتركوا في القناة» is removed.
- Unclear words get a GPU second listen.
- False alarms from the "no words cut" check on fast speech. Fix: compare two consistent readings.
- Reference analysis ran once per reel. Fix: once per client.

### G59–G61 (fixed, 190 tests)
- **G59.** White captions on a bright blurred card fill were hard to read and sat on the card's text. Fix: soft dark box, placed above the card.
- **G60.** Building one reel made Premiere save another open reel, which caused a false "editor edited" refusal. Auto-save can do the same. Fix: content-signature comparison.
- **G61.** With several reels open, frame export failed for the non-active project. Fix: switch to the right project first.

### Peer podcast fixes touching shared code
- `cutaway_bands` adds the card bands to caption avoidance.
- `plan.py` warns when a graphic covers an AUTO_CUTAWAY range.
- `timemap` marks "masked" pieces, so zoom steps are counted (previously "+0").

### 2.1.1 fixes made by this session (committed by the peer as dad3f9d)
- **Range reel without `global.main_footage`.** Got "fit" instead of the face-centred reframe. Fixed with a `source_range` fallback.
- **`cutaway_bands` sized from the wrong file.** It used the first preflight file (5400 px instead of 607.5). Fixed via `main_video()`.
- **Vertical phone footage with a 4:5 profile.** Came out 9:16 silently. Fixed.
- **4:5 with the reel's video missing from preflight.** Now a hard error: "run `reel preflight` for this video first". Added by the 2.1.1 peer.

### PlayerDebugMode and sandbox issues (resolved for this PC; product gap remains)
- The first command was PowerShell-only and failed in cmd. Admin windows, unexecuted pastes and the empty Terminal tab each cost a round.
- The assistant's sandbox could not see the real registry, and read-only checks were blocked once it tried to step outside the sandbox.
- A watcher script ("bridge readiness: PlayerDebugMode, Premiere, heartbeat") eventually saw "PlayerDebugMode is now ON for CSXS.12" and "BRIDGE ALIVE".

### Monitoring script crash
- The assistant's `watch_session.py` crashed with `UnicodeEncodeError` (cp1252) on Arabic. It was a scratch tool, not plugin code, but it confirms that Windows consoles default to cp1252.

### Round-4 gaps G62–G69 (from `round4-gaps.md`): NOT fixed in code at session end
- **G62: previews ignore `typography.json` roles.**
  - `Brand.role_style` is hard-coded `{headline: black, small: regular}`. A family without Black or Regular falls back to the first file (here Medium), so hooks render in Medium.
  - Fix: take the style per role from typography.json, then the brand.json fallback, then the nearest weight, never "first file".
  - **Workaround in place:** `reel-profile/brand.json` `font_roles_fallback.weights {headline: bold, small: medium}`.
- **G63: an explicit editor in-point adjustment gets snapped away.**
  - `reels-select --adjust Rxx:in=` snaps to a sentence-like start within ±1.5 s, so an editor cannot skip one word. Example: R07 11:46.95 snapped back to «طيب» at 11:45.57.
  - Fix: explicit adjusts snap to the nearest word start.
  - Workaround: `global.cut_words`.
- **G64: reels-plan errors are hard to act on after a correction.**
  - `reels-plan` evidence strings break after `transcript-correct` (the analyst ran in parallel with the transcript-editor), and the errors list only the quote.
  - Fix: show "did you mean: <corrected words>".
- **G65: the intake sheet misses name supers.**
  - The sheet samples only 6 frames, so it missed the supers at 01:27 and 16:55 (`lower_thirds` was wrongly false).
  - Fix: sample densely in the first 3 minutes, or run text detection on 1 fps thumbnails.
- **G66: a session started before install keeps the old plugin's bin on PATH.**
  - `reel` then resolves to the old reel-editor ("environment not installed"), and subagents inherit it.
  - Fix: `reel` prints its plugin name and version in errors; doctor and start detect a foreign `reel` first on PATH.
- **G67: `python -I` loses site-packages.**
  - With the engine venv on Windows, `-I` drops site-packages (PIL/av not found). The start chat hit `ModuleNotFoundError: No module named 'av'`.
  - Fix: document using the venv Python without `-I` (or with `-E -s`).
- **G68: the brand highlight colour can be unreadable.**
  - The profile says highlight in "brand gold", but the measured primary is brown #81613D. On thumbnails it was unreadable (1.1–1.5:1 contrast).
  - Fix: check highlight contrast against the frame and fall back to white with a warning.
- **G69: frame export right after opening a project.**
  - `ppro-frames` exported 4 of 17 frames as "Media pending" because media was still loading. A second run was clean.
  - Fix: wait until media is online or retry pending frames, and qc-reviewer treats a pending frame as a re-export.
- **Bridge downgrade guard: done on a branch, not merged.**
  - `ppro_bridge.install(force=False)` skips when the installed bridge is newer. New flag `reel ppro-install --force`. On `feat/ae-motion` 39026fb.

### Engine limitations surfaced in round 4 (not fixed)
- **No continuous zoom.** The engine holds one scale per piece. Results: R01's push is stepped (1.00 → 1.04 → 1.08 on jump cuts), and R10's push is a static 108%. The editor must keyframe a smooth ramp by hand.
- **No picture fade-out.** R10 needs a manual 1 s fade to black.
- **No per-reel caption size.** The series is fixed at 52 px; the agency wanted larger captions for R10.
- **Captions hidden under the hook by default** (`captions_hidden_during` includes `hook_title`). The client style (V05, R01) keeps them on.
- **Hook-title click.** The profile's `graphics-templates.json` still puts a click on the hook title. Agents removed it per graphic.
- **Style files unused by the planner.** `editing-style.json` and `editing-rules.json` are not read by `reel plan`; the engine only checks that the file exists.
- **Caption cues split mid-line** (R10).
- **Caption timing drift.** In R01 «والطيبات لله» shows about 0.7 s early, followed by a 1.3 s gap.
- **Name-card readability.** The frosted name card is weak over a light wall (R01).
- **Cosmetic label.** `edit-plan.md` labels EDIT_004 "camera only" without a camera move.

---

## 6. Open, deferred or unverified items at session end (11:26Z, "Everything stays paused until you say continue")

### EP02 round 4 (folder `D:\WhyNot Clients\Dr Sherin Helmy\output`)
- **R03–R09.** The 7 story-editor agents were stopped mid-way, and their edit-plan files are incomplete. They must be redone.
- **Remaining steps for all 9 reels.** Graphics check, preview MP4s, approvals, 9 Premiere builds (one at a time), QC on Premiere's own frames, per-reel publish captions, then the final report.
- **R01 and R10** have plans and previews but are not approved or built.
  - R01 needs approval of the editorial hook «الصلاة… هدية المعراج».
  - R10 needs approval of GFX_001 (poem text and recitation rights).
- **23 flagged words** in the EP02 transcript need the editor's ear. `transcript-verify` was deliberately not run, because it is editor-only. R03 is the hardest window: the wife's line at 07:19–07:24 has to be rewritten by ear, and the plan's hadith «كم من عذق رداح» is not in the audio at all.
- **Speaker facts the plan got wrong.**
  - Dr Sherin is the left man in the black hoodie; the plan's feminine «صاحبة البرنامج» is wrong.
  - R07's first ~13.5 s and the "catalogue" idea belong to the moderator.
  - R05 must end by 14:46.85.
- **Publish package.**
  - Placeholders `[اسم المحاور]` and `[اسم الضيف]` need filling. Candidate names: «د/ عمرو فهمي» from the super, and possibly «عبد الخبير».
  - The show credit needs confirming.
  - `EP02.srt` is raw (0 of 764 segments corrected) and must not be uploaded.
  - Religious-review items need sign-off: Mi'raj and tashahhud, Abu al-Dahdah, «لا حول ولا قوة», the Shadhili five robes, the fasting line, and the Abu Yusuf attribution.
  - The episode number needs a decision.
- **Style conflicts C01–C09.** C02, the keyword highlight (gold #E0B76B vs a brown #81613D box), is still open. Standing rules await agreement before being recorded in the profile: captions on during the hook, no hook click, two-line end card at y 372 / size 52.
- **Missing client inputs.**
  - Logo (`assets\Logo` is empty) and official HEX codes.
  - The IBM Plex Sans Arabic fonts are not installed on this PC.
  - No Mushaf font.
  - No `EP02.md` episode sheet (names, seat roles, links).
  - An OK is needed on the "Noteb…" third-party corner mark on the cards.
  - `data/Broll`, `data/Music` and `data/SFX` are empty.
- **`intake.json`** has `lower_thirds: false`, which is wrong: name supers appear at 01:27 and 16:55.
- **Optional.** A soft background for R04 and R10 if licensed music is found.

### Earlier field-test leftovers
- R02 word #79 «هغير» is unconfirmed, and one cut at 1.1 s should be checked.
- R02's closing statement «آمنوا الأول وعملوا الصالحات» needs the content owner's approval, because it echoes a Quranic phrase.
- R05 has 9 unclear words in the punchline and phone line (e.g. «قطعي في كتاج», «كسل»).
- QC notes on R02: the speaker is on screen 74%; no music; the IBM Plex fonts are not installed.
- The `whynot-test/Dr Sherin Helmy/output/projects/R02_TEST` folder must be deleted by hand.

### Plugin and release state
- **main = v2.1.1** (dad3f9d, tagged). The podcast mode was merged as v2.1.0 (1fdcb7c). Nothing has been pushed to any remote.
- **2.2.0 (AE motion mode, bridge 3.1.0 two-host)** was on `feat/ae-motion`, with the "Running chat management" session about to merge it. A `whynot-cut-2.2.0.zip` existed on disk afterwards, but this session did not verify it.
- **Installed version is 2.1.1, which bundles bridge 3.0.0.**
  - Running `/whynot-cut:setup` or `reel ppro-install` would downgrade the live bridge 3.1.0 and drop AE support.
  - The user was told not to run setup until 2.2.0 is installed.
  - The downgrade guard is not merged.
- Fix G62–G69 after 2.2.0 merges (the memory notes list this as 2.2.1 work).
- Premiere has 2 projects open (Dr Sherin R02 test and PODCAST-TEST), unsaved.

### Unverified
- **macOS.** No live test in this session; the CoreText path was kept as is.
- **Thmanyah on Windows** with the HarfBuzz renderer (tested only with Arial).
- **A clean engine install with downloads** on another computer. This PC's engine reused already-installed Python packages, because downloads were slow.
- **Official `claude plugin validate`** was never run.
- **Nested fan-out reliability.** The validator raised W2; it worked in round 4, but no deliberate test was done.
- **First-run experience from a fresh session after install.** G66 showed old-PATH issues.
- **Dr. Nahla's profile** is still shipped in the package.

---

## 7. Environment facts a future implementer must know

### Machine and account
- Windows 11 Pro. User account `pegasus\loq`.
- NVIDIA **RTX 4060** laptop GPU, initially missing cuBLAS; fixed via `reel gpu-enable`.
- System Python 3.13 at `C:\Python313`. The console encoding is cp1252, so Arabic output needs UTF-8 handling.

### Paths
- Workspace: `D:\0 Work\0 Pegasus IMC Agency\00 TWN\0 TWN AI\Editing Plugin`.
  - `1.0.7.zip` is the original reel-editor.
  - Release zips: `whynot-cut-2.0.0.zip`, `2.1.0` (172 files), `2.1.1`, and later `2.2.0`.
  - Git repo: `whynot-cut-marketplace\` (plugin at `whynot-cut-marketplace\whynot-cut`).
  - Worktrees: `whynot-cut-marketplace-motion` (feat/ae-motion) and `-podcast-minors`. Later `-motion-minors` and `-r4a/b/c` also exist.
  - Test data: `whynot-test\CLIENT` (synthetic) and `whynot-test\Dr Sherin Helmy` (real).
  - Gap log: `round4-gaps.md`.
- Engine home: `C:\Users\LOQ\.whynot-cut` (`venv\Scripts\python.exe`).
- **The installed plugin runs from `C:\Users\LOQ\.whynot-cut\marketplace`. Do not delete it.**
- CEP panel: `%APPDATA%\Adobe\CEP\extensions\ai.thewhynot.cut.bridge` (`CSXS\manifest.xml`).
- Clients root (saved preference): `D:\WhyNot Clients`. First client: `D:\WhyNot Clients\Dr Sherin Helmy`.
  - Layout: `assets\{Brand,Fonts,Logo,Photos}`, `data\{Raw,Episodes,References,Broll,Music,SFX}`, `output\...`.
  - The original agency folder `D:\0 Work\0 Pegasus IMC Agency\00 TWN\...` is not in the plugin's layout.
- Episodes: `output\episodes\<EP>\{00_inputs,01_analysis,02_transcription,publish}`.
- Reels: `output\projects\<EP>_<RID>\{00_inputs,01_analysis,03_broll,06_audio,07_premiere,08_quality_control}`.

### Install
- Old reel-editor 1.0.7 had been installed through the **desktop app's plugin upload**. WhyNot Cut is installed the same way, or via marketplace add/install.
- **After installing, open a NEW session.** The plugin's `bin/` is on PATH only in sessions started after install (G66, C4).
- Preferences are saved "for the whole machine", i.e. in `~/.claude`.

### Adobe
- Premiere Pro 2026 = **26.5.2**. Only `HKCU\Software\Adobe\CSXS.12` `PlayerDebugMode=1` (REG_SZ) is needed.
- The command must run in a normal, non-admin window under the same user. Fully quit Premiere (check Task Manager), then reopen; the panel loads only at startup.
- Working one-liner for both shells: `powershell -NoProfile -Command "reg add 'HKCU\Software\Adobe\CSXS.12' /v PlayerDebugMode /t REG_SZ /d 1 /f"`.
- Verify with `reg query "HKCU\Software\Adobe\CSXS.12" /v PlayerDebugMode` (expect `REG_SZ 1`). Undo with `reg delete ... /f`.
- Panel status in Premiere: Window › Extensions › WhyNot Cut Bridge shows "idle — watching queue".
- **Bridge versions.**
  - 3.0.0 is Premiere-only and ships in 2.1.1.
  - 3.1.0 is two-host (Premiere + After Effects). Queues: `ppro-queue/ppro-scripts/NHPP` for Premiere and `ae-queue/ae-scripts/NHAE` for AE. Manifest host AEFT. Generic `lib/cep_queue.py`.
- **Premiere quirks.**
  - It locks imported stills on Windows until it quits.
  - QE `exportFramePNG` needs backslash paths.
  - Auto-save and other open projects re-save `.prproj` files.
  - With several projects open, activate the right one.
  - Frames exported right after opening may show "Media pending".
- **Premiere effects.** Premiere 26 "Noise" = `ADBE_Noise_FX` "Intensity" (default 50). Sharpen uses "Sharpen Amount".
- **ProRes 422 LT** preview format works on Windows.
- **FCP7 XML.** `pathurl` = `file://localhost/C:/...`. Ticks: TPS = 254016000000; 29.97 = timebase 30 + ntsc TRUE (8475667200 ticks per frame).

### Network
- PyPI is very slow from this PC (about 40 KB/s).
- The Hugging Face Xet transfer fails on Windows (WinError 10038), so `HF_HUB_DISABLE_XET=1`.
- NVIDIA's redist server is fast (cuBLAS about 3 minutes; the estimate was ~550 MB).
- The Whisper large-v3 download is ~3.1 GB.

### Sandbox
- The Claude sandbox may not see the real registry, and possibly not the real `%APPDATA%`.
- Stepping outside the sandbox triggered blocks, even on read-only checks.
- The Terminal tab of the desktop app runs as the user, and Claude can read it.

### Python and tooling quirks
- Run the tests with the engine venv. System Python skips 5 HarfBuzz tests.
- Don't use `python -I` with the venv on Windows (G67).
- Robocopy exit code 1 means success.

### Media facts (EP02)
- `EP02.mp4`: 1920×1080, 34.7 minutes, ~4.3 Mbps (a 9:16 crop looks soft).
- Two audio streams, AAC 2ch and AC3 2ch at 48 kHz. The engine takes the first (AAC).
- Switched multicam with 3 people. Full-frame 16:9 cards at 2:53 and 26:01 carry a "Noteb…" mark.
- Dr Sherin's footage and profile run at 29.97 fps.
- Loudness target -14 LUFS (agency); V05 measures -13.7 LUFS with a -1.0 dBTP true peak.

### Client style (from V05 and the profile)
- Captions: white on a translucent dark box, no stroke, at y ≈1300 (27% above the bottom). Keyword in gold #E0B76B, one line of 28–37 characters, no commas.
- Graphics: cream hook box with a gold underline (about 3 s), name card «د. شيرين حلمي» + «وتزودوا بالتقوى», end card «الحلقة كاملة على القناة».
- Keep top graphics out of the top 250 px platform zone.
- Measured brand brown #81613D.

### Parallel sessions seen
- **"منصة بودكاست متعددة الوظائف"**: podcast mode, released as 2.1.0.
- **"WhyNot Cut 2.1.1: fix podcast-mode deferred minors"**: worked in a worktree.
- **"Phase 3 spec: motion/animation from audio in AE"**: 2.2.0 and bridge 3.1.0.
- **"Running chat management"**: orchestrator. Rules while Phase 3 finished: no `reel setup` or `ppro-install`, don't restart Premiere or AE, don't edit the marketplace repos.
- **"Whynot cut start"**: the user's first real `/whynot-cut:start`.
- Coordination ran over SendMessage, with explicit file ownership.

---

## 8. Ideas floated but never implemented

### From the user
- **"get access to everything and go".** Full autonomy, including Adobe security settings. Not implemented by design. The plugin still requires the user to run the PlayerDebugMode command. Opportunity: a one-click, self-verifying "enable Premiere panel" step, e.g. a Run-button block plus an automatic `reg query` and heartbeat watcher.
- **"I want the final result, don't ask again" (09:56Z).** A true end-to-end no-questions run from episode to finished reels. It got as far as plans for 2 of 9 reels before "stop for now". It needs a productized autonomous mode with a single consolidated human-only checklist at the end, plus resumability. Resume worked conceptually ("say continue"), but partial agent outputs had to be redone.
- **A supervising "follow the other chat" mode** («شوف الشات وتابع معاه»). Done ad hoc with a scratch watcher script. Not a plugin feature.
- **"what you are doing".** On-demand progress and status. There is no plugin-level progress dashboard or status command for long multi-reel runs. A `whynot-cut:status` skill exists in the listing, but it is not referenced in this session.
- **"work with adobe apps"** beyond Premiere. AE motion mode was developed in a separate session (2.2.0). Photoshop thumbnail/PSD output exists only as the `adobe-extras` skill, not exercised here.
- **"make it work with mac"** was never verified live.

### Raised by agents or peers, not implemented (useful for the plan)
- Smooth zoom (scale ramp) and picture fade-out generated by the engine.
- Per-reel caption size override.
- Recording standing client rules in the profile: captions on during the hook, no hook click, two-line end-card geometry.
- Letting `reel plan` actually read `editing-style.json` / `editing-rules.json`.
- Re-cueing captions one half-line per cue for calm reels.
- An automatic contrast check for highlight colours (G68), name-super text detection (G65), `reel` self-identification on PATH (G66), media-online wait before frame export (G69), and "did you mean" for reels-plan evidence errors (G64).
- An episode sheet (`<EP>.md`) prompt or template, so names and links don't block publishing.
- Removing Dr. Nahla's (and generally any client's) profile from the distributable package.
- A soft music pad for calm reels when licensed music exists.
- A YouTube SRT from the corrected transcript, since the episode SRT stays uncorrected.
