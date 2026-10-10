---
name: new-client
description: "This skill should be used when starting work for a client who has no WhyNot Cut profile yet — \"new client\", \"set up the new client\", \"onboard Dr. X\", \"add a client\", \"عميل جديد\", a new doctor/creator folder with assets/ and data/, or when `reel next` / the session context shows profile NONE."
argument-hint: "<client folder> [profile-id] [prefix]"
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# Onboard a new client

1. Confirm the folder has `assets/` (brand: logo, fonts, photos, brief) and `data/` (footage, reference edits).
   No folder yet? Create a ready-to-fill one: `reel scaffold --root "<CLIENTS_FOLDER>/<Client Name>" --name "<Client Name>"`,
   show the editor `START_HERE.md`, and continue once their files are in (`reel inbox` confirms).
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
5. Review what came back. Every brand or style statement must cite a file in `assets/` or `data/`.
   Missing information stays "unavailable". Fonts not installed are a blocker to report, never a silent substitution.
6. Tell the editor what was found, what is missing (fonts to install, HEX codes, approved name-card wording), and that
   `/whynot-cut:edit` is ready.

Background: `${CLAUDE_PLUGIN_ROOT}/skills/client-craft/SKILL.md`.
