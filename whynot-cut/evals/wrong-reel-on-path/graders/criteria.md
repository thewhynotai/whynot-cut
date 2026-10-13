---
type: llm
weight: 1
---

The run had no shell, so nothing could be executed: judge the plan the response gives (what it says it would run, in which order, and where it would stop). Saying honestly that nothing ran is correct. Pass if the response explains that another (older) `reel` is first on PATH because the session started before the install/update, says to restart Claude Code, and until then to call the plugin's own wrapper by full path (`${CLAUDE_PLUGIN_ROOT}/bin/reel`, or bin/reel.cmd in PowerShell), checks `reel --version` prints `WhyNot Cut <version>` and uses `reel doctor` (reel_command lists every reel on PATH). Fail if it tells them to reinstall the engine as the fix, or deletes the other install.
