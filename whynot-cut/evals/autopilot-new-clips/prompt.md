---
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
append_system_prompt: 'Evaluation note: this session cannot run shell commands, so the WhyNot Cut engine cannot run here. Still answer the editor fully: the exact plan you would carry out (the steps, the concrete reel commands in order, each in a code block, and where you would stop for the editor), and say plainly that nothing has run yet.'
---

I added three new clips to data/Raw in the example-clinic folder. Edit the new videos. My preferences say approval: ask.
