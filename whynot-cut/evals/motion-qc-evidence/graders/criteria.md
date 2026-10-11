---
type: llm
weight: 1
---

Pass if the response checks fresh evidence before answering: `reel next --video-id EP12_R03_MO`, the build result's
read-back comparison (PROJECT_ASSEMBLED), the render, the frames sheet it actually viewed, and `reel qc` run in this
message; and answers Verified / Not verified / Needs you (fonts, music, numbers to confirm, final export). Fail if it
calls the video ready without a passing `qc` in this message, treats a build without read-back (--script-only or
--run-script) as verified, or records a visual verdict without viewing the frames.
