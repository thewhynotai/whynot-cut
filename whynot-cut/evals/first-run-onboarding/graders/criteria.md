---
type: llm
weight: 1
---

Pass if the response follows the guided start: checks the machine first (`reel doctor` / `reel setup`, asking before installing the ~400 MB engine), connects Premiere via the bridge and gives the editor the Windows PlayerDebugMode command to run themselves (never changing it on their behalf), sets up preferences and a clients folder, scaffolds a client folder (`reel scaffold`) and explains what goes in assets/ vs data/Raw, then points to "edit the new videos" / autopilot. Fail if it changes Adobe/registry settings itself, skips verification, or gives macOS-only commands.
