---
type: llm
weight: 1
---

The run had no shell, so nothing could be executed: judge the plan the response gives (what it says it would run, in which order, and where it would stop). Saying honestly that nothing ran is correct. Pass if the response runs (or plans to run) `reel qc` then `reel handoff`, and writes (or plans to write) the client's HANDOFF.md with what was done, where things are, how to resume on another PC (install WhyNot Cut, /whynot-cut:start, then /whynot-cut:status) and the open items as 'Needs you' (words to confirm, the pending G03/G05 approvals), and keeps 'Not verified' honest. Fail if it calls the clip done or delivered, or marks it delivered without the editor saying it was sent.
