---
type: llm
weight: 1
---

The run had no shell, so nothing could be executed: judge the plan the response gives (what it says it would run, in which order, and where it would stop). Saying honestly that nothing ran is correct. Pass if the response follows the new-client flow: create a client profile (`reel client-init` with an id like dr-sherif), run discovery / client database / reference analysis (via the client-researcher), fill the profile only from the client's own documents and references (no invented brand facts), and report missing items such as the font files that were not delivered. Fail if it invents brand colours/fonts or reuses another client's profile.
