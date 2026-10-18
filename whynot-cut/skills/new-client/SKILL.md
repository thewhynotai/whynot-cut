---
name: new-client
description: "Onboard a client with no WhyNot Cut profile: \"new client\", \"onboard Dr. X\", \"add a client\", «عميل جديد», or when the session shows profile NONE."
argument-hint: "<client folder> [profile-id] [prefix]"
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# Onboard a new client

1. Confirm the folder has `assets/` (brand: logo, fonts, photos, brief) and `data/` (footage, reference edits).
   No folder yet? Create a ready-to-fill one: `reel scaffold --root "<CLIENTS_FOLDER>/<Client Name>" --name "<Client Name>"`,
   show the editor `START_HERE.md`, and continue once their files are in (`reel inbox` confirms). Say every item of
   its `warnings[]` to the editor in their language (`text_ar` + `why_ar`) before going on: misplaced or unread files
   and missing brand material are cheapest to fix now; the editor moves or adds the files, never you.
2. Choose a kebab-case profile id (e.g. `dr-sherif`) and a 2–3 letter file prefix (e.g. `SH` → `C0001_SH_EDIT.prproj`).
   If the editor hasn't named them, derive them from the folder name and tell them.
3. `reel client-init --root "<CLIENT_FOLDER>" --id <id> --prefix <XX>` creates `output/client_database/reel-profile/` from the blank template.
4. Spawn `client-researcher` (`subagent_type: "whynot-cut:client-researcher"`). Task:
   - run `discover`, `client-db` and `ref-analyze`
   - view every photo and contact sheet
   - write the client database profile docs
   - fill the reel-profile files from the client's own documents and references only: `transcription.json`
     initial prompt (name and specialty as spelled in the brief), the domain glossary, `style.json` (style seen in the
     references), and `notes.md`
   - write the client reference style once (`output/client_database/reference_style/`: editing-style-analysis.md,
     editing-style.json, editing-rules.json) and record it: `reel ref-style --record --by client-researcher`.
     Every video of this client reuses it; `reel next` flags it when the reference edits change.
5. Review what came back. Every brand or style statement must cite a file in `assets/` or `data/`.
   Missing information stays "unavailable". Fonts not installed are a blocker to report, never a silent substitution.
   In your own messages, tables and file names, «الدكتور/الدكتورة» and he/she come only from people[] (reel-profile
   `profile.json`). Until a person's gender is known write «د.» or the name, and ask the editor.
6. Tell the editor what was found, what is missing (fonts to install, HEX codes, approved name-card wording), and that
   `/whynot-cut:edit` is ready.

Background: `${CLAUDE_PLUGIN_ROOT}/skills/client-craft/SKILL.md`.
