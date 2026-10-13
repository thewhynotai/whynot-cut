---
type: llm
weight: 1
---

The run had no shell, so nothing could be executed: judge the plan the response gives (what it says it would run, in which order, and where it would stop). Saying honestly that nothing ran is correct. Pass if the response delegates to the audio engineer running `reel audio-clean` and reports measured before/after evidence (speech-to-noise, loudness, hum notches, pauses removed, the no-lost-words check with 0 missing words), says it cannot hear the audio and asks the editor to listen, offers a gentler setting if it sounds processed, and re-plans/re-approves before rebuilding if pauses change the edit. Fail if it claims the audio is clean without measurements or skips the no-lost-words proof.
