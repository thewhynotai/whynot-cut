---
type: llm
weight: 1
---

Look at the Read calls on output/projects/C0238/02_transcription/transcript.json that have NO offset, NO limit and NO pages (full reads), and at what the tool results show after each. The plugin's read-once hook answers a SECOND full read of the same unchanged file with a one-line reminder that starts "WhyNot Cut: you already read transcript.json in full in this session and it has not changed". Pass if EITHER the file was read in full only once, OR every full read after the first is followed by that reminder (same wording, naming transcript.json). Fail if the file was read in full a second time and no such reminder follows that second read. A ranged read (offset/limit) or Grep of the file never counts as a full read. Also fail if the run was stopped or refused because of the reminder instead of carrying on to answer.
