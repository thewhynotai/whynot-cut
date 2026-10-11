---
name: transcript-craft
description: "This skill should be used when transcribing or correcting a whynot-cut transcript — Whisper runs, word timings, Arabic/English/mixed speech, correcting misheard medical terms, subtitle cues. Knowledge for the transcript-editor agent."
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

The vocabulary hint (`initial_prompt`) and the glossary come from the client profile. The hint biases spelling only and never inserts content.

## Correct
Write `02_transcription/transcript-corrections.json`, then run `reel transcript-correct`. This step is idempotent: it always starts again from `*.machine.json`.
```json
{"corrections": [
  {"word_id": 42, "from": "هايبر ترافيك", "to": "Hypertrophic", "reason": "medical term; context: scar types", "confidence": "medium"},
  {"word_id": 43, "from": "ك", "to": "", "reason": "split artefact, merged into previous word", "confidence": "high"}
]}
```
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
For long clips, spawn `segment-proofreader` sub-agents in parallel, one per ~20 s chunk. Give each the chunk's word ids, times and text, plus the glossary.
Merge their proposals and resolve conflicts yourself. They propose; you write the corrections file.

If the Agent tool is unavailable (some Claude Code versions don't let subagents start subagents), do the batches in this agent one after another, with the same rows and format, and say "checked sequentially" in your report.
