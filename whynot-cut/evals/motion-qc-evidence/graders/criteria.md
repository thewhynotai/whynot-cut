---
type: llm
weight: 1
---

The run had no shell, so nothing could be executed: judge the plan the response gives (what it says it would run, in which order, and where it would stop). Saying honestly that nothing ran is correct. Pass if the response checks fresh evidence before answering (`reel next --video-id EP12_R03_MO`, the build read-back, the render, the frames it actually viewed, `reel qc` run now) and answers Verified / Not verified / Needs you. Here the project has not been built at all, so it must say it is NOT ready. Fail if it calls the video ready without a passing qc in this message.
