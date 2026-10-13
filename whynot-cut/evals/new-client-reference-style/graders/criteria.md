---
type: llm
weight: 1
---

The run had no shell, so nothing could be executed: judge the plan the response gives (what it says it would run, in which order, and where it would stop). Saying honestly that nothing ran is correct. Pass if the response onboards the client (profile via `reel client-init` if none) and has the client-researcher analyse the two reference edits once at client level, writing the reference style (editing-style analysis and rules under output/client_database/reference_style/) and recording it with `reel ref-style --record`, so later clips reuse it instead of re-analysing; it reports only what the references show (no invented style facts). Fail if it plans to re-analyse the references for every clip or invents brand facts.
