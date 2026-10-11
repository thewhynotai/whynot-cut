---
name: episode-craft
description: "This skill should be used when analysing a whole podcast episode for whynot-cut podcast mode — topic map and YouTube chapters, speaker turns and seating, finding reel-worthy moments, choosing content types (storytelling, drama, success story, advice, bold opinion, emotional, comedy), scoring candidates and writing reels-plan.json. Knowledge for the episode-analyst and moment-scout agents."
user-invocable: false
---

# Episode craft

The reels plan is a promise to the editor: every candidate starts on a sentence, ends on a finished thought, makes
sense to a stranger, and quotes the speaker exactly. Read the whole transcript before writing anything.

## Files you write (output/episodes/<EP>/01_analysis/)
**topics.json** — the episode in parts; it is also the YouTube chapter list, so: the first topic starts at
`00:00:00.000`, at least 3 topics, each ≥ 10 s, in order, no overlaps, short titles (2–6 words) a viewer understands.
```json
{"topics": [{"id": "T01", "start": "00:00:00.000", "end": "00:04:10.000", "title": "…", "summary": "…"}]}
```
**speakers.json** — who speaks when (turn level, your inference) and where people sit in wide shots (from the
intake layout). Positions: left | right | center | unknown. Wide shots follow these turns, so be careful at turn
changes; leave a gap rather than guess.
```json
{"method": "inferred from context and the episode sheet",
 "people": {"host": {"name": "…", "position": "left"}, "guest": {"name": "…", "position": "right"}},
 "turns": [{"start": "00:00:00.000", "end": "00:00:41.200", "speaker": "host"}]}
```
**reels-plan.json** — the candidates (all fields required unless marked optional):
```json
{"episode_id": "EP12", "candidates": [{
  "id": "R01", "start": "00:12:01.240", "end": "00:13:05.880",
  "type": "success_story", "secondary_type": null,
  "title": "<internal, 3–6 words>", "hook_quote": "<first spoken line, verbatim>",
  "hook_text": "<suggested on-screen hook, the speaker's words shortened>",
  "evidence": "<first 4–12 words, verbatim>", "end_evidence": "<last 4–12 words, verbatim>",
  "why": "<one line: why a stranger would watch to the end>",
  "score": {"hook": 8, "standalone": 7, "payoff": 9, "ending": 8},
  "needs_context": false, "context_line": "", "speakers": ["guest"], "risks": []}]}
```
Then `reel reels-plan --root "<CLIENT>" --episode <EP>` until it compiles. The engine snaps start/end to the nearest
sentence-like boundary (lead-in 120 ms, tail 250 ms), checks evidence near those times (±3 s, Arabic-normalised),
checks 30–90 s (15–180 hard), overlaps, the sheet's avoid list, and computes the total score.
An evidence error ends with `did you mean: «…»`: those are the words the CURRENT transcript (after `transcript-correct`)
says at that time. Copy them into `evidence` / `end_evidence`; do not re-guess from memory of the uncorrected text.

## Finding moments
1. Map the episode first (topics), then walk it topic by topic.
2. Good reel shapes: a story with a turn and an ending; a conflict and its resolution; a before → after with a number;
   one piece of advice with its reason; a clear opinion said with conviction; a vulnerable moment; a joke that lands.
3. Start ON the hook: the first words must pull a stranger in. If the best line comes after 10 s of setup, start at
   the line and use a context card instead of the setup.
4. End on the payoff. Never end on "and…", a list that continues, or the host's next question.
5. Standalone test: read the candidate alone. Unclear "he/it/that"? Mentions "as I said"? → `needs_context` + a
   `context_line` written from the transcript (one line, ≤ 34 characters works best on screen).
6. 8–15 per hour, a spread of types (don't return 12 pieces of advice), no two candidates covering the same moment.

Types and their signals: `references/content-types.md`. Scoring anchors and red flags: `references/moment-scoring.md`.

## Rules
- Evidence is copied, never paraphrased. Hooks shorten the speaker's words; they never add claims.
- Host vs guest attribution comes from the turns; a reel whose key line is the host's is labelled so in `speakers`.
- Sensitive claims (medical, financial, legal, religious) → `risks: ["claim needs approval: …"]`.
- Topics in the sheet's `avoid` list → still allowed in the plan only with a `risks` note; the editor decides.
- You never pick the reels. Gate 0 is the editor's.

## Motion mode (2.2)
Mark `motion_fit`/`motion_why` on candidates that suit animation (numbers, steps, abstract ideas, no usable picture);
topics may carry a recipe `type` so they can be animated. See `/whynot-cut:motion`.
