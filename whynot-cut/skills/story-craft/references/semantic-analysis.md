# SRT Semantic Analysis (Stage 6) — Claude's job

The SRT is not just captions: it decides the whole edit. Read **all** of `02_transcription/transcript.txt`
first, then `words.json` for exact word times. Work from complete statements in context, never isolated
keywords. If the transcript is unverified, note uncertain words (subtitle-review.md) and avoid putting them on screen.

## 1. `01_analysis/main-topic.md`
Sections (all required; write "not present in speech" if absent — never invent):
1. Main topic (one line) 2. Central message 3. Problem/question addressed 4. Intended audience (from speech + client DB)
5. Educational objective 6. Subtopics (ordered) 7. Important statements (quote + timestamp) 8. Technical terms
(term, timestamp, script: Arabic/Latin) 9. Strongest hook (quote + why) 10. Key takeaway 11. Conclusion
12. Spoken CTA (quote or "none") 13. **How the subject should shape the edit** (tone, density, sensitivity, graphic types).

## 2. `01_analysis/narrative-segments.json`
```json
{"video_id":"C0238","segments":[{
  "segment_id":"SEG_001","start":"00:00:00.000","end":"00:00:04.120",
  "transcript_excerpt":"<exact words>","main_topic":"…","subtopic":"…",
  "narrative_purpose":"hook|topic_introduction|problem|explanation|example|key_fact|important_term|process|misconception|warning|takeaway|conclusion|cta",
  "communication_objective":"what the viewer should understand","importance":"high|medium|low",
  "suggested_visual_treatment":"talking_head|caption_highlight|term_callout|glass_card|checklist|broll_card|photo_card|punch_in|name_card|cta"}]}
```
Segments must tile the speech in order with no overlaps; boundaries on word boundaries from words.json.
Only use purposes actually supported by what the speaker says.

## 3. `01_analysis/transcript-semantic-analysis.json`
Statement-level understanding. For each meaningful statement:
```json
{"statement_id":"ST_001","segment_id":"SEG_001","start":"…","end":"…","text":"<exact>",
 "meaning_in_context":"…","why_important":"…","viewer_should_understand":"…",
 "complexity":"simple|moderate|complex","needs_visual_reinforcement":true,
 "best_treatment":"keep_talking_head|text_highlight|term_callout|glass_card|checklist|diagram|broll|photo_card|punch_in|sound_cue_only",
 "keep_speaker_visible":true,"motion_graphic_appropriate":false,"sound_cue_useful":false,
 "misrepresentation_risk":"none|low|high — explain","rejected_options":["why B-roll would mislead…"]}
```
Plus top-level `"broll_opportunities"`: every place a visual was considered, accepted or rejected, with reason.
Choose by **communication value**, not a quota. Emotional/sensitive statements → keep the speaker, restrained text.

## 4. Decision principles (examples, not mandatory effects)
- Anatomy/process → sequential infographic only if accurate and approved; otherwise glass card with the speaker's words.
- Important term → `term_callout` synced to the word's start time.
- Enumeration of ≥3 items the speaker actually lists → `checklist` with each item's `at` = the first word of that item.
- Misconception vs. fact → glass card with the speaker's correction; keep the speaker's nuance/qualifiers.
- Strong hook → `hook_title` + optional 5–10 % punch-in + soft pop.
- Warnings/qualifiers ("under supervision", "not for everyone") must appear whenever the related claim appears on screen.
