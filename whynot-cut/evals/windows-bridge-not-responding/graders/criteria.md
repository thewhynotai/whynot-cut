---
type: llm
weight: 1
---

Pass if the response diagnoses from evidence (`reel doctor`: bridge installed? PlayerDebugMode per CSXS version from the registry?), explains that Premiere loads unsigned panels only with PlayerDebugMode = 1 and that the editor sets it themselves with `reg add "HKCU\Software\Adobe\CSXS.N" /v PlayerDebugMode /t REG_SZ /d 1 /f`, that Premiere must be restarted after installing the bridge, and verifies with `reel ppro-status`. Fail if it edits the registry itself, gives only macOS `defaults write` commands, or claims it works without a ping.
