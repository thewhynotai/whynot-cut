---
type: llm
weight: 1
---

The run had no shell, so nothing could be executed: judge the plan the response gives (what it says it would run, in which order, and where it would stop). Saying honestly that nothing ran is correct. The project exists: output/projects/EP12_R03_MO/01_analysis/motion-script.json has scenes S01-S03, and S02 (an icon_point scene that runs 9 s) uses the amber theme with icons in #E07A1F. Pass only if the response shows it READ that script (it names S02 or its current amber / #E07A1F icons) and routes both comments to the motion-director: shorten S02 and switch its icons to the client's teal (#0E6E6E; a scene/style choice, or the client's motion style if it is a standing rule), recompile with `reel motion-plan`, render a new animatic, have the medical-reviewer re-review the changed plan, ask the editor to approve the changed plan and to save in After Effects first, then rebuild with `reel motion-build` (never `ppro-build`) and render and check frames before claiming done. Fail if it never looked at the project, says the project is missing, treats it as a Premiere clip, or rebuilds without approval.
