---
max_turns: 10
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
append_system_prompt: 'Evaluation note: this session cannot run shell commands, so the WhyNot Cut engine cannot run here. Still answer the editor fully: the exact plan you would carry out (the steps, the concrete reel commands in order, each in a code block, and where you would stop for the editor), and say plainly that nothing has run yet.'
---

My editor wants to send the example-clinic clip C0238 to the client today. Is it done and ready to send?
