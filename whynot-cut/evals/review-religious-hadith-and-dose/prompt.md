---
max_turns: 14
timeout_seconds: 420
allowed_tools: [Read, Glob, Grep, Skill, Write]
append_system_prompt: 'Evaluation note: this session cannot run shell commands, so the WhyNot Cut engine cannot run here and no subagent is available. Do the content review yourself from the project''s files (01_analysis/edit-plan.md, 01_analysis/timeline-spec.json, 01_analysis/review-scan.json = the engine''s review-scan output for this plan: hints only, read every line; 02_transcription/transcript.md; the client profile in output/client_database/reel-profile/profile.json; output/client_database/asset-manifest.json when there is one). Then, instead of running `reel review-flags --from`, write the exact table that command takes with the Write tool to the project folder as review-input.json: {"items": [{"event_id": "<plan id>", "flag": "<check>", "verdict": "<verdict>", "reason": "<why>"}]}, one row per plan line and check (the ok ones too). Checks and their verdicts: medical: ok, reword-to-match, needs-doctor-approval, remove; religious: ok, reword-to-match, needs-approval, remove; business: ok, reword-to-match, needs-approval, needs-evidence, remove; ai: ok, reword-to-match, needs-approval, needs-disclosure, remove. Then answer the editor, and say plainly that review-flags has not run yet.'
---

راجعلي الكلام اللي على الشاشة في C0307 (example-clinic) قبل ما أبعته: إيه اللي محتاج موافقة، ومين لازم يوافق؟
