# PRD: Hush — silence and filler-word cutter for Premiere Pro

| | |
|---|---|
| Status | Shipped (v1.0), macOS, Premiere Pro 2024+ (tested on 26.5) |
| Owner | Hoka |
| Source | `hush/` (panel), `install.sh` / `uninstall.sh` |
| Panel id | `com.hoka.hush` (CEP 11) |
| ExtendScript namespace | `HUSH`, public functions `hush_*` |

## 1. Summary
Hush removes dead air and filler words ("um", "uh", "اممم", "آه") from a Premiere timeline in one click. The editor
scans a range, sees a waveform with every planned cut drawn on it, tunes how aggressive it is, and then either cuts
(ripple delete, keeping video and audio linked) or only drops markers. A backup copy of the sequence is made before
any cut, and Undo brings it back.

## 2. Problem and goals
Talking-head reels and podcasts need every pause and hesitation removed. Doing it by hand takes 20–40 minutes per
minute of content. Goals:
- G1. Cut silences with frame accuracy and never cut into speech (not even part of a frame).
- G2. Remove filler words in English and Arabic (Egyptian), including elongated ones ("ummmm", "اممممم").
- G3. Keep the edit usable: gaps closed, video stays linked to its audio, other tracks untouched unless chosen.
- G4. Fully reversible: backup sequence + one-click restore.
- G5. Simple by default (one slider), precise when needed (Advanced numbers).

Non-goals: noise reduction, loudness, multicam, captions (that is Kalam), cloud processing.

## 3. Users and use cases
- Social-media editors cutting reels from a single camera with lav/mic audio (main case).
- Podcast editors removing long pauses before fine editing.
- U1: "Cut all pauses in this clip, tight, no padding." U2: "Cut pauses and 'um/uh' in the whole sequence."
  U3: "Only mark them, I'll decide." U4: "That was too much, undo."

## 4. Functional requirements

### 4.1 Target (what is analysed)
- FR-1 Range = selected clips (union of their time span) if any are selected, else In/Out if set, else the whole
  sequence. The panel shows the target label ("3 clips", "In/Out", "Whole sequence").
- FR-2 Track chips: every video/audio track appears as a chip (V1…, A1…). Tracks with clips and not locked are
  on by default. Only ticked tracks are cut and moved; the panel warns which tracks with clips will NOT move.
- FR-3 Only the ticked audio tracks are analysed (others are muted during the analysis export, then restored).

### 4.2 Scan
- FR-4 Export the range's audio to WAV (48 kHz mono 16-bit preset `Wave48mono16.epr` from the Premiere bundle,
  via `exportAsMediaDirect`, In/Out temporarily set and restored).
- FR-5 Build an RMS envelope at 10 ms hops (dBFS, floor −100) in the panel (`wav.js`, `detect.js`).
- FR-6 Clip statistics: noise floor = 10th percentile (≥ −70 dB), speech level = 90th percentile.
- FR-7 If filler removal is on: transcribe the WAV with Whisper large-v3-turbo (mlx-whisper, Apple GPU), word
  timestamps, with a disfluency prompt per language (`auto` / `en` / `ar`) so Whisper writes the fillers down.

### 4.3 Detection
- FR-8 Silence = run below threshold lasting ≥ minSilence; clicks shorter than 30 ms inside a silence are ignored.
- FR-9 Cut range = silence minus padBefore/padAfter next to speech; a silence touching the range edge gets no pad
  on that side; cuts shorter than 80 ms are dropped.
- FR-10 Simple mode: one intensity 0–100 (presets Soft 25 / Medium 50 / Strong 80) mapped per clip:
  threshold = floor + span × (0.15 + 0.30·t), minSilence = 0.9 − 0.65·t s, pad = 0.18 − 0.12·t s, with
  t = intensity/100 and span = max(6, speech − floor).
- FR-11 Tight (default on): padding 0 — cut right up to speech (the user asked for no margin).
- FR-12 Advanced mode: threshold (dB), min silence (s), pad before/after (s, can be linked).
- FR-13 Fillers: two editable lists. "Strong" (ticked by default: um, uh, erm, ah, hmm, mm, اممم، آه، اوه…) and
  "Soft" (listed unticked: like, you know, basically, actually, I mean, يعني، طيب، أصلًا، بقى…). Two-word phrases
  match. Elongated hesitations always match. Normalisation: lower case, no punctuation, no Arabic diacritics,
  unified alef/yeh forms.
- FR-14 Optional "Unclear sounds": loud runs (0.15–1.2 s) with no transcribed word near them are listed unticked.
- FR-15 Every filler is a row with a tick box and a play button (moves the playhead 0.5 s before it).
- FR-16 Plan = union of silence cuts and ticked fillers; filler cuts swallow a neighbouring gap up to
  padBefore + padAfter + 50 ms (no slivers); everything snapped inward to whole frames; pieces under 2 frames
  dropped.

### 4.4 Preview
- FR-17 Waveform canvas with cuts drawn (silence vs filler colours), hover tooltip with time and cut kind, click to
  move the playhead.
- FR-18 Summary: duration before / after / saved, "N silences + M fillers", and the active numbers
  (threshold | min silence | pads).

### 4.5 Apply
- FR-19 Mode "Cut": razor every ticked track at every cut boundary (QE DOM `razor`), remove the pieces inside cuts,
  close gaps in one pass (each clip moves left by the total cut time before it), then relink video pieces with the
  audio pieces mostly under them (`linkSelection`).
- FR-20 Backup (default on): clone the sequence as "<name> (Hush backup HH:MM:SS)" before cutting and switch back to
  the original; abort if the original cannot be made active.
- FR-21 Locked ticked track → abort with a clear message, nothing cut.
- FR-22 Mode "Markers": add a marker per cut (name = kind/label), no edit. "Remove all Hush markers" in the menu.
- FR-23 Undo: the backup becomes the open sequence under the original name; the cut version is kept, renamed
  "<name> (Hush cut HH:MM:SS)".
- FR-24 Presets: save the current settings under a name, reload later.

## 5. UX
- Single dark panel, Arabic/English toggle (RTL in Arabic). Sections: Target + track chips → Scan button →
  Simple/Advanced tabs → Fillers (toggle, language, lists, rows) → Waveform → Summary → Cut/Markers + Go → Undo.
- Progress bar with stage text (Exporting audio…, Finding filler words…) and Stop.
- Settings persist between sessions.

## 6. Architecture
| Layer | Files | Role |
|---|---|---|
| CEP panel (Chromium + Node) | `index.html`, `css/hush.css`, `js/main.js` | UI, flow, state |
| Pure logic (no DOM/Node) | `js/detect.js`, `js/fillers.js`, `js/wav.js` | envelope, silences, plan, fillers, WAV parse |
| Node services | `js/engine.js` | settings/presets/logs, cache, spawning Whisper |
| Bridge | `js/cep.js` | `evalScript('hush_<fn>(json)')` → parsed `{ok, ...}` |
| ExtendScript host | `jsx/host.jsx` | Premiere DOM + QE: export, razor, remove, ripple, link, markers, restore |
| Python | `py/hush_whisper.py` | mlx-whisper word timestamps |

Data dir: `~/Library/Application Support/Hush/` (`settings.json`, `presets.json`, `logs/`, `cache/` scans and words,
`venv/`, `hf/` model cache). Cache keeps the last 3 scans.

## 7. Interfaces

### 7.1 Host functions (argument and result are JSON strings; result always has `ok`, else `error`)
| Function | Args | Returns |
|---|---|---|
| `hush_info` | – | `{sequence:{name,id,fps,end,inPoint,outPoint,video:[{kind,index,name,clips,locked}],audio:[…],selection:[{name,start,end,type}]}}` |
| `hush_exportAudio` | `{outPath,start,end,audioTracks:[idx],extDir}` | `{path}` |
| `hush_clipSources` | – | `{clips:[{path,start,end,inPoint}]}` for selected audio clips |
| `hush_cut` | `{cuts:[[s,e],…] (sequence seconds, frame aligned), video:[idx], audio:[idx], ripple, backup, link}` | `{removed,cuts,backup:{id,name}|null,sequence,sequenceId,linked}` |
| `hush_markers` | `{ranges:[{s,e,kind,label}]}` | `{added}` |
| `hush_clearMarkers` | – | `{removed}` |
| `hush_setPlayhead` | `{t}` | `{}` |
| `hush_restore` | `{backupId,cutId,originalName}` | `{restored}` |

### 7.2 Whisper process
`python hush_whisper.py <wav> <out.json> <auto|en|ar>`; stdout JSON lines `{"stage":…}` then `{"stage":"done"}`;
`out.json` = `{language, duration, words:[{w,s,e,p}]}`. Env: `HF_HOME`, `HF_HUB_OFFLINE=1`. Model override:
`HUSH_WHISPER_MODEL`.

## 8. Safety rules (must survive any refactor)
- Never cut into speech: boundaries rounded inward to frames.
- Backup before cutting (default on); verify the original is the active sequence before QE edits.
- Re-read track objects after every razor (Premiere collections go stale after QE edits).
- Gap closing in one pass (an O(n²) per-cut ripple was too slow and drifted).
- Untouched: unticked tracks, locked tracks (abort), media on disk.

## 9. Dependencies and platform
macOS (Apple Silicon for Whisper), Premiere Pro 2024+, CEP 11 with Node (`--enable-nodejs --mixed-context`),
PlayerDebugMode=1 (unsigned panel). Whisper: Python venv + `mlx-whisper`, model ~1.6 GB (optional: silence cutting
works without it). No ffmpeg (WAV read with numpy / in JS).

## 10. Performance
Scan of a 1-minute range: export ~2–4 s + envelope < 0.2 s; Whisper turbo ~0.1× real time on M-series. Cut of
~100 ranges on 3 tracks: a few seconds.

## 11. Acceptance tests
- Pure: envelope/percentiles, silences with 30 ms blips, pads at range edges, combine/join of filler gaps, inward
  frame snap, intensity mapping, filler matching (Arabic normalisation, two-word phrases, elongated hesitations).
- Premiere: cut on a test sequence → removed count, no gaps, linked items, backup exists; restore swaps names;
  markers added/removed; locked track aborts with nothing changed.

## 12. Known limitations
- macOS only (Whisper via MLX). A Windows build would reuse Kalam's portable faster-whisper backend.
- Filler detection depends on Whisper writing fillers; "Unclear sounds" is the fallback.
- Ripple on tracks the user did not tick is not done by design (the panel warns).

## 13. Integration notes for the combined plugin
- Reuse across plugins: the CEP bridge (`cep.js`), audio export (`exportAudio` is duplicated in Hush, Kalam and
  Tidy — make one shared host service), settings/log helpers, i18n with RTL, the Whisper process (Kalam's engine
  already returns word timings for the same audio — Hush fillers could take Kalam's words instead of its own run).
- Keep each feature's ExtendScript in its own namespace (`HUSH`, `KALAM`, `TIDY`) inside one host file or
  `$.evalFile` modules; ExtendScript is one global scope per panel.
- ExtendScript rules: ASCII source only, ES3 (no `map/forEach/filter` on host side), and parenthesise nested
  conditionals (`a ? x : (b ? y : z)`) — ExtendScript evaluates the unparenthesised form wrongly.
- Hush's output (cut sequence) is a good input for Kalam (captions after cutting) — one "Cut → Caption" flow.
