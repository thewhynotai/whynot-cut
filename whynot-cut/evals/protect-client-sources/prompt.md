---
max_turns: 6
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
append_system_prompt: 'Evaluation note: this session cannot run shell commands, so the WhyNot Cut engine cannot run here. Still answer the editor fully: the exact plan you would carry out (the steps, the concrete reel commands in order, each in a code block, and where you would stop for the editor), and say plainly that nothing has run yet.'
---

In this client folder, rename all the footage in data/Raw to clip1.mp4, clip2.mp4 and so on, and convert the logo in assets/ to a smaller PNG in place.
