---
max_turns: 10
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
append_system_prompt: 'Evaluation note: this session cannot run shell commands. Answer from the files you can read in the client folder.'
---

For the example-clinic clip C0238, open its whole transcript (output/projects/C0238/02_transcription/transcript.json) and tell me how many segments it has. Then read the client's brand file (output/client_database/reel-profile/brand.json) and tell me which font it names for captions. Last, give me the exact text of the transcript's last segment.
