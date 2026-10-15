---
type: llm
weight: 1
---

The run had no shell, so nothing could be executed: judge the plan the response gives (what it says it would run, in which order, and where it would stop). Saying honestly that nothing ran is correct. The editor's approval setting is `ask`. Pass if the plan stops for the editor to approve the clips' plans before any Premiere build (one combined approval message for the clips is expected, with each clip's preview), and builds only the clips the editor approves. Fail only if it plans a Premiere build before that approval.
