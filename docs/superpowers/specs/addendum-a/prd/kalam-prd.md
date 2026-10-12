# PRD: Kalam — voice-timed, corrected captions for Premiere Pro

| | |
|---|---|
| Status | Shipped v1.1: macOS (Apple GPU) and Windows (NVIDIA GPU, CPU fallback) |
| Owner | Hoka |
| Source | `kalam/` (panel + `engine/`), `install_kalam.sh`, `build_windows.sh`, `windows/` |
| Panel id | `com.hoka.kalam` (CEP 11) |
| ExtendScript namespace | `KALAM`, public functions `kalam_*` |
| Design history | `docs/superpowers/specs/2026-10-12-kalam-captions-design.md`, `…-kalam-windows-design.md` |

## 1. Summary
Kalam turns the speech in a Premiere range into finished captions in one click: it picks the best speech model
for the language, places every word exactly on the audio, corrects the text with Claude using the client's
spelling rules, splits it into short single-line captions that follow the meaning, and places them in the
sequence as a native captions track, as MOGRT clips (template chosen from a visual gallery), or as an SRT file.
"One press, no manual fixes" is the bar.

## 2. Problem and goals
Arabic (Egyptian dialect) captions from generic tools are badly spelled, break sentences in the wrong places,
appear before the words are spoken, leave gaps, and mangle English/medical terms. Goals:
- G1. Best accuracy per language: Egyptian Arabic, English, other languages.
- G2. Timing that matches the voice: no caption before its first word is spoken, no gaps between captions.
- G3. Captions are meaning units (a whole clause per caption), one line, never split inside a term.
- G4. Text follows the client's rules (spelling, hamzas, Capital Case English terms, glossary) without rewriting.
- G5. Output where the editor needs it: captions track, MOGRT, or SRT in sequence time.
- G6. Correction on the user's Claude subscription (no paid API required).

Non-goals: translation, burned-in styling beyond the chosen MOGRT, speaker diarisation.

## 3. Users and use cases
Arabic content editors (medical and business reels, podcasts). U1: "Caption this reel in Egyptian Arabic onto a
captions track." U2: "Same, but as my 9:16 Comic Subtitles MOGRT." U3: "Give me only an SRT of the In/Out part."
U4: "English interview, one line per caption."

## 4. Functional requirements

### 4.1 Mode (language)
| Mode | Model (macOS) | Model (Windows) | Notes |
|---|---|---|---|
| Arabic (default) | Egyptian dialect Whisper large-v3-turbo (`oddadmix/whisper-large-v3-turbo-arabic-dialectal`, converted to MLX fp16) | same model, CTranslate2 fp16 (faster-whisper) | best on Egyptian speech |
| English | Parakeet TDT 0.6B v2 (parakeet-mlx) | Parakeet ONNX (onnx-asr), ≤25 s chunks cut in the quietest 200 ms | |
| Other | Whisper large-v3-turbo | same, CTranslate2 | language auto-detected |
- FR-1 Every mode then runs forced alignment (MMS-300m CTC aligner, custom Arabic romanisation); windows whose
  script cannot be romanised keep the transcriber's times.

### 4.2 Range
- FR-2 Four choices: In/Out, whole sequence, from the playhead to the end, selected clips (their span).
  Errors: no In/Out, nothing selected, playhead at the end.
- FR-3 Audio tracks: chips per audio track; only ticked tracks are exported (others muted during export).

### 4.3 Cleaning (after alignment)
- FR-4 Drop non-speech tags ("[music]"), Whisper junk (Arabic glued to Latin, symbol-only tokens; in Arabic mode
  short Latin fragments), decoding loops (> 3 repeats), credit hallucinations, and words lying on silence
  (speech threshold = floor + 10 dB from the clip's own envelope).

### 4.4 Correction (Claude)
- FR-5 Phrases (split at pauses ≥ 0.22 s) are sent in batches of 60 with 3 lines of context before/after; only
  text leaves the machine, never times or audio.
- FR-6 Backend "subscription" (default): Claude Code CLI headless — `claude -p --safe-mode --tools "" --json-schema
  … --system-prompt-file … --no-session-persistence --model opus` with stdin input. Backend "api": Anthropic SDK,
  model `claude-opus-5-5`, structured JSON output. Missing CLI → captions without correction + notice.
- FR-7 Rules: per mode, editable in the panel; Arabic defaults = the client's rules (full spelling, hamzas, "انت"
  without hamza, future with ه not ح, Egyptian dialect kept, English terms in Capital Case, "الـ Term" article,
  medical term correction from context, no punctuation, no diacritics except natural tanween, never shorten /
  add / rephrase / merge / split / move words). Glossary: "Correct = wrong, other wrong" lines.
- FR-8 Contract: one output line per input line; Claude marks meaning-unit ends with "|".
- FR-9 Faithfulness gate per line: rejected (source kept, rules applied in code) when shortened below 60 %,
  rewritten, translated, or with added words (SequenceMatcher + Arabic↔Latin skeleton comparison).
- FR-10 Code-enforced rules after Claude (`rules.enforce`): punctuation and diacritics stripped (tanween kept),
  glossary, Capital Case of Latin terms in Arabic mode only.

### 4.5 Caption building
- FR-11 Corrected words are mapped back to spoken words (token alignment), so every caption starts at a real
  word onset.
- FR-12 A line that does not end its sentence is joined to the next when the pause is short (< 0.6 s).
- FR-13 Phrases are split to fit by dynamic programming over all break points of the phrase: never inside a term
  ("الـ | Reputation" forbidden), breaks preferred at meaning-unit ends, a whole unit may run 25 % over the line
  length, tiny one-word pieces penalised (no lone "ف").
- FR-14 Packing (DP): max line length 32 characters, max lines per caption (user setting, the client uses 1),
  max duration 4.5 s, breaks at sentence ends and pauses ≥ 0.6 s.
- FR-15 Timing: caption start = first word onset; captions run back to back with no gaps; the last caption ends
  0.3 s after its last word.
- FR-16 Settings: max characters/line, max lines, max seconds, min pause.

### 4.6 Output
- FR-17 Captions track: SRT imported and placed with `createCaptionTrack` (subtitle format) at sequence time.
- FR-18 MOGRT: one clip per caption on the chosen video track (`importMGT`), text written into the template's text
  field (chosen by name, default = first real text field). A template without editable text → clear error and all
  clips placed so far removed (all-or-nothing).
- FR-19 MOGRT gallery: every `.mogrt` in Premiere's Local Templates folder (macOS
  `~/Library/Application Support/Adobe/Common/Motion Graphics Templates`, Windows
  `%APPDATA%\Adobe\Common\Motion Graphics Templates`) with its thumbnail, name and folder; search by name, filter by
  top folder; click to choose; the text-field list shows the template's own text controls (`clientControls`
  type 6); "From a file…" still available. Thumbnails and metadata cached by path + mtime.
- FR-20 SRT only: saved next to the project in "Kalam Captions/<sequence> HHMMSS.srt" (Windows-safe file name), in
  sequence time (offset by the range start).
- FR-21 An SRT is always written (also for track/MOGRT outputs).
- FR-22 Result list: every caption with its time; click moves the playhead. Undo for MOGRT removes the placed clips
  in the range; the captions track is removed by the user (Premiere has no API for it).

### 4.7 Support
- FR-23 Progress stages (loading, transcribing, aligning + device, correcting, captions, done/error) and Stop.
- FR-24 Menu: open logs, open Kalam folder, "Save a report for the developer" (Desktop text file with OS,
  Premiere/panel versions, engine doctor output and the last 200 log lines; never settings or keys), reset settings.

## 5. UX
Dark panel, Arabic default (RTL) with English toggle. Cards: Mode (Arabic / English / Other) → Range (2×2 grid) +
audio chips → Output (Captions track / MOGRT / SRT only; MOGRT shows the chosen template card with thumbnail, track
and text-field selects) → Caption settings → Correction (toggle, backend, rules, glossary) → Start → progress →
results.

## 6. Architecture
| Layer | Files | Role |
|---|---|---|
| CEP panel | `index.html`, `css/kalam.css`, `js/main.js`, `js/i18n.js` | UI and flow |
| Pure panel logic | `js/range.js`, `js/platform.js`, `js/mogrt.js` (zip/definition parsing, filter) | testable in jsc |
| Node services | `js/engine.js` | settings (owner-only file), jobs, engine process, report, OS paths |
| Bridge | `js/cep.js` | `evalScript('kalam_<fn>(json)')`, extension path (handles `file:///C:/…`) |
| ExtendScript host | `jsx/host.jsx` | info, WAV export, captions track, MOGRT placement/text, undo |
| Python engine | `engine/kalam_engine.py`, `engine/kalam/*.py` | transcribe, align, clean, correct, units, captions |

Python modules: `transcribe` (backend per OS), `align`, `audio`, `clean`, `phrases`, `correct`, `rules`, `units`,
`captions`, `similar`, `platform`, `device`. Data dir: macOS `~/Library/Application Support/Kalam/`, Windows
`%LOCALAPPDATA%\Kalam\` (`venv`/`python`, `models`, `hf`, `cache`, `logs`, `settings.json`).

## 7. Interfaces

### 7.1 Host functions
| Function | Args | Returns |
|---|---|---|
| `kalam_info` | – | `{sequence:{name,id,fps,end,inPoint,outPoint,playhead,video:[…],audio:[…],selection:[{name,type,start,end}]},projectPath}` |
| `kalam_exportAudio` | `{outPath,start,end,audioTracks:[idx]}` | `{path,start,end}` |
| `kalam_captionsTrack` | `{srtPath,start,name}` | `{item,nodeId}` |
| `kalam_mogrt` | `{mogrtPath,videoTrack,start,textParam|null,captions:[{s,e,text}]}` | `{added,field}` |
| `kalam_removeClips` | `{videoTrack,from,to}` | `{removed}` |
| `kalam_setPlayhead` | `{t}` | `{}` |
| `kalam_version` | – | `{version,os,panel}` |

### 7.2 Engine CLI
- `kalam_engine.py run --wav W --mode ar|en|other --out DIR --settings S.json [--models DIR]`; stdout JSON lines
  `{"stage": loading|transcribing|aligning|correcting|captions|done|error, …}`; writes `captions.srt`,
  `captions.json` `[{n,s,e,text}]`, `words.json`, `corrected.json` `[{raw,line,kept_source}]`. The settings file
  (may hold an API key) is deleted by the panel as soon as the engine reports `loading`.
- `kalam_engine.py doctor [--models DIR] [--quick]` → one JSON line `{python,platform,backend,device,gpu,
  devices:{arabic,english,other,aligner},models:{…:true|error},claude,ok}`; non-quick runs transcribe + align like a
  real run.
- Env: `HF_HOME`, `HF_HUB_OFFLINE=1`, `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`; `KALAM_BACKEND=mlx|portable`
  forces a backend.

### 7.3 Settings (panel)
`lang, mode, range, output, mogrtPath, mogrtName, mogrtThumb, mogrtFields, mogrtTrack, mogrtField, max_line (32),
max_lines (2; client uses 1), max_dur (4.5), min_pause (0.22), correct (true), backend (subscription|api), api_key,
rules_ar|en|other, glossary`.

## 8. Safety and privacy
- Only caption text goes to Claude; audio and times stay local. API key only in an owner-only settings file and a
  job file deleted at engine start; never in argv or logs or reports.
- Claude Code runs in safe mode with no tools, no plugins/hooks/MCP, no session persistence.
- Faithfulness gate: a bad correction can never shorten or rewrite a caption; the source is kept.
- MOGRT placement is all-or-nothing.

## 9. Platforms and dependencies
- macOS: Apple Silicon, Python 3.12 venv (uv) with mlx, mlx-whisper, parakeet-mlx, torch/torchaudio, transformers,
  anthropic; `install_kalam.sh`.
- Windows: one folder (~13 GB) built on a Mac by `build_windows.sh`: portable CPython 3.12, torch 2.11 cu128
  (RTX 20–50 series), faster-whisper/CTranslate2 4.8, onnxruntime-gpu 1.24.4 (CUDA 12.8), models, panel,
  VC++ redistributable; `install.bat` → `install.ps1` (copy runtime when its content VERSION changes, copy panel,
  PlayerDebugMode, install/login/test Claude Code, self-check). NVIDIA driver ≥ 570; CPU fallback everywhere
  (load, transcribe, align) with the device reported.
- Both: Premiere Pro 2024+, CEP 11 with Node, PlayerDebugMode, Claude subscription or API key for correction.

## 10. Performance (Apple M-series)
~15 s for an 80 s Arabic clip without correction; correction adds roughly 20–60 s per 60 phrases (Claude). Windows
GPU expected similar; CPU 2–4× slower.

## 11. Acceptance tests (in repo)
- Engine (pytest, 101): rules, captions DP (no term splits, one-letter penalty, unit costs), units, cleaning, correction
  contract and gate (fake clients), alignment fallbacks, CLI, doctor, platform (Claude discovery incl. npm `.cmd`,
  UTF-8), portable backends (GPU→CPU fallbacks, chunk cuts), bundle checker (DLL imports, Windows-only binaries),
  slow tests on real clips.
- Panel (jsc): ranges and SRT shift, platform paths, Windows extension path, safe names, MOGRT zip/definition
  parsing and filter, every wired element present before the scripts.
- Premiere (13 host checks) and real-panel end-to-end via CEP remote debugging on test projects only.
- Backend parity: portable vs MLX on three real clips — text ≥ 96 % (spelling-normalised), onsets within 15 ms.

## 12. Known limitations
- The captions track cannot be read back or removed by script (Premiere API).
- "Basic Title" in Premiere 26 exposes no MGT text component (clear error).
- Windows build not yet run on real Windows hardware (developer report closes the loop).

## 13. Integration notes for the combined plugin
- Shared services worth extracting: audio export (also in Hush/Tidy), the Python engine process runner and progress
  protocol (JSON lines), the CEP bridge, platform paths, settings, i18n/RTL, developer report, doctor.
- One Python environment can serve Kalam and Hush (Hush's Whisper = Kalam's "other" model); word timings from
  Kalam can feed Hush's filler detection.
- Keep the engine a separate process (models need GBs of RAM/VRAM; isolates crashes). Keep the JSON-lines protocol.
- The MOGRT gallery (`js/mogrt.js`) is generic: any feature that places templates can reuse it.
- ExtendScript rules: ASCII only, ES3, namespaced globals, parenthesised nested conditionals.
