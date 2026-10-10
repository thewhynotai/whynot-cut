---
type: llm
weight: 1
---

Pass if the response finds the new clips with `reel inbox` (not by guessing), runs the lead-editor pipeline per clip with agents fanned out per stage, renders the preview videos, and then STOPS at one combined Gate 1 approval (because approval is ask) listing each clip with its preview path, before any Premiere build. It must not claim any clip is done without qc passing. Fail if it builds in Premiere before approval or invents clip names.
