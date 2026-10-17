---
name: transcript-craft
description: "Reference for the transcript-editor agent (preloaded). Not for direct use."
user-invocable: false
---

# Transcript craft

The transcript is the clock and the source of truth for the whole edit. Every graphic, cut and caption cites it.

## Run
```bash
reel transcribe --root "<CLIENT>" --video-id <ID>          # faster-whisper large-v3 + word timestamps; NVIDIA GPU when usable, else CPU
```
Outputs in `02_transcription/`:
- `transcript.{txt,json}`
- `words.json` (word id, start_ms, end_ms, probability)
- `subtitles.srt` and `captions-short.srt`
- `subtitle-review.md`: low-confidence words, **profile vocabulary not heard verbatim** (e.g. hint `نادال`, heard `نضال`,
  often at high confidence), and glossary hits labelled by the profile's `domain` (medical / religious / general)
- With the K-T1 switch on (`safety.json`), `subtitle-review.md` opens with «راجع دول الأول — Check these first»: the
  words to confirm ranked by risk × doubt (doses, numbers, drug names, a negation next to a claim, durations first).
  Proofread that block first and tell the editor these words first; NEEDS-YOU lists them in the same order. There is
  no new command: the editor confirms with `reel transcript-verify` as below, and until then `reel plan` refuses any
  graphic that shows one of these words (the error names the word and its time). A subagent never records the
  editor's confirmation: it reports, or records `--by claude`, which does not unblock these words.

The vocabulary hint (`initial_prompt`) and the glossary come from the client profile. The hint biases spelling only and never inserts content.

A clip longer than 10 minutes (`long_clip_minutes` in transcription.json) is transcribed like an episode: chunks cut in
silence, VAD, checkpoints in `02_transcription/chunks/` (run again to resume; `--force` restarts). A checkpoint is
reused only if the same model, hint, backend and decoder (device, batched or one by one, VAD) made it; a chunk done
after a GPU fallback is marked, and the review lists "Decoders … MIXED" — `--force` redoes every chunk with one.
Backends: faster-whisper (NVIDIA GPU, batched on long audio; else the CPU on every physical core) or mlx-whisper on
Apple Silicon (`backend: mlx` / `--backend mlx`; `auto` picks it only once `mlx_verified` is true after the Mac parity
test). With batching, a segment that repeats itself, is probably silence or holds a known hallucination phrase is
decoded again one by one (the 2.x way) and the review counts those. `reel bench --audio <speech file>` measures the
speed on this computer; `reel doctor` shows it.

## Correct
Write `02_transcription/transcript-corrections.json`, then run `reel transcript-correct`. This step is idempotent: it always starts again from `*.machine.json`.
```json
{"corrections": [
  {"word_id": 42, "from": "هايبر ترافيك", "to": "Hypertrophic", "reason": "medical term; context: scar types", "confidence": "medium"},
  {"word_id": 43, "from": "ك", "to": "", "reason": "split artefact, merged into previous word", "confidence": "high"}
]}
```
- Check the file's shape any time with `reel validate 02_transcription/transcript-corrections.json --root "<CLIENT>" --video-id <ID>`
  (schema errors with their JSON path; episodes: `--episode <EP>` instead of `--video-id`).
- `from` must equal the current machine word, or the correction is refused. An empty `to` merges the word's timing into the previous word.
- Correct only what the audio or the context makes clear (misheard terms, split words, Latin terms written in Arabic letters).
  **Never** add words the speaker didn't say, smooth their grammar, or "fix" a medical claim.
- Anything you're unsure of goes in `"flags"` in the same file: `{"word_id": 79, "note": "unclear", "suggest": "هغيّر"}`.
  Flagged words stay in the captions as heard; `reel plan` refuses them on any graphic, and QC lists them, until the
  editor verifies the transcript (`reel transcript-verify`). A word may be corrected AND flagged ("confirm by ear").
- **Second listen** for unclear words: `reel transcript-relisten` (all flagged words, or `--words 79,80`) re-decodes a few
  seconds around each one three ways (no hint, profile hint, warmer) into `relisten.json`. When the alternatives agree
  and the context makes sense, correct it (cite "relisten: 3 of 3"); when they disagree, keep the flag. Drop a flag
  only with a reason (move it to `"resolved_flags"`).
- Confidence isn't proof. "Hypertrophic" came out as "هايبر ترافيك" at p=0.66.

## Human transcripts the client already has
People wrote down this speech before you: use them as evidence for corrections (cite them).
- `subtitle-review.md` → "Quotes in the client's documents": quotes («…», "…", “…”) from a reels plan or brief matched
  against the transcript; `≠` lines show where the writer heard something else.
- A finished reel of the same clip in `data/References` (the editor's own cut): its burned captions are a human
  transcript. View frames of the caption zone (ffmpeg `-ss T -frames:v 1 -vf crop=...`) where Whisper is unsure.
  On a real reel both sources agreed on «إيمانهم» where Whisper heard «آمانه» and context suggested «آمنوا».
- Re-transcribing (a new range, a new model) renumbers words: `transcript-correct` re-anchors each correction to the
  nearest word that still reads `from`, and skips one the new transcript already gets right.

## Before transcribing a reel from a plan
Put the names and special terms of THIS video in `00_inputs/vocabulary.txt` (one per line, or comma-separated): the
people, places and words the client's plan mentions for it. They join the client-wide hint for this video only, and the
review checks them closely. Client-wide names (the speaker, the show) stay in the profile's `transcription.json`.

## Hallucinations
Whisper invents end-screen phrases on silence or music («اشتركوا في القناة», "Thanks for watching"). A segment that
matches one and cannot be speech (no-speech probability ≥ 0.5, or more than 6 words a second) is dropped and listed in
the review under "Dropped Whisper hallucinations". The same phrase inside a longer segment is dropped only on its own
evidence: more than 6 words a second, or a short run (≤ 1.5 s) the model was unsure of (mean p < 0.4) with silence on
both sides. A real outro said at a normal pace stays, even under music.
The filter looks inside one segment at a time: a phrase whose words fall in two segments (the boundary in the middle
of «اشتركوا | في القناة») is never dropped, so it needs neither `restore` nor a `keep_phrases` entry.
If the speaker really said a dropped phrase (check by ear): put its word ids (listed in the review and in
`02_transcription/dropped-hallucinations.json`) in transcript-corrections.json as `"restore": [ids]` (or `"all"`) and
run `reel transcript-correct`; restored words are never dropped again. `"restore"` must be a list (or `"all"`):
`false`, `""`, `0`, `{}` or `null` stop `transcript-correct` with an error instead of being skipped; `[]` (or no
`"restore"` key) restores nothing. Only ids from this transcript's own drop list
count (a reel cut from an episode lists only the drops inside its window, on its own ids); an unknown or stale id is
reported under PROBLEM and not applied (`{"word_id": N, "word": "..."}` also checks the word). For a phrase this client really uses (a host who
always says «اشتركوا في القناة»), add it to `keep_phrases` in the client's reel-profile `transcription.json`.

## Cues and RTL
- Text is stored in logical (spoken) order. Never pre-reverse it.
- Captions: at most 2 lines, about 18–32 characters per line, and no cue longer than 5.5 s. Cues break on segment boundaries, and a single orphan word is merged into its neighbour.
- Never split a Latin term, a number and its unit, or "الـ" from the Latin term it attaches to.

## Verification
Only the editor can confirm the transcript by ear. Then: `reel transcript-verify --by editor --note "<what they checked>"`.
The verification records the transcript's fingerprint: any later correction or re-transcription makes it stale.

## Episodes (podcast mode)
`reel episode-transcribe --episode <EP>` runs the whole episode in ~10-minute chunks (checkpoints in
`02_transcription/chunks/`; run again to resume; `--force` restarts), with VAD, the language detected once on chunk 1.
Same files and correction flow as a clip, with `--episode <EP>`. Reels are sliced from the episode transcript, so
correct the episode and let the lead `reels-select --resync`.

## Fan-out
For long clips, spawn `whynot-cut:segment-proofreader` sub-agents in parallel, one per ~20 s chunk. Give each the chunk's word ids, times and text, plus the glossary.
Merge their proposals and resolve conflicts yourself. They propose; you write the corrections file.

If the Agent tool is unavailable (some Claude Code versions don't let subagents start subagents), do the batches in this agent one after another, with the same rows and format, and say "checked sequentially" in your report.
