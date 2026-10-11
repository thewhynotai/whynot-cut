---
type: llm
weight: 1
---

Pass if the response follows a new-client flow: create a client profile (`reel client-init` with an id like dr-sherif and a short prefix), run discovery / client database / reference analysis (via the client-researcher), fill the profile only from the client's own documents and references (no invented brand facts), and report missing items such as uninstalled fonts or HEX codes. Fail if it invents brand colours/fonts or reuses another client's profile (e.g. the shipped Example Clinic one).
