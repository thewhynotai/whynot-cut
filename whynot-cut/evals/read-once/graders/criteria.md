---
type: llm
weight: 1
---

The editor asked for the segment count, then for the whole transcript to be opened once more to double-check, and for the exact text of the last segment. The plugin's read-once hook answers the second full read of the same unchanged file with a one-line reminder ("WhyNot Cut: you already read transcript.json in full in this session ..."). Pass if ALL hold: (1) the response gives the segment count and the exact text of the last segment, and both match what the file shows; (2) the run carried on and answered: it was not stopped or refused because of the reminder; (3) after the reminder the run did not read the whole file a third time (a ranged read with offset/limit or a Grep is fine). Fail otherwise.
