# WhyNot Cut

**Raw footage in. Premiere project out. Why not?**

A Claude Code plugin by [The Why Not AI](https://thewhynot.ai/) · info@thewhynot.ai · macOS and Windows

WhyNot Cut edits vertical talking-head reels (Arabic, English or a mix) from a client folder into a **native Adobe
Premiere Pro project**:
- a word-timed transcript (Whisper large-v3; NVIDIA GPU used automatically when present)
- cleaned dialogue with pauses removed, with proof that no words were lost
- story-driven edit decisions: hook, statements, checklists, B-roll cards, punch-ins, SFX
- the client's own brand graphics and animated captions, with correct Arabic shaping and right-to-left order
- **a watchable preview MP4** of the edit before anything is built
- the Premiere build with exact sequence settings, then evidence-based QC from Premiere's own frames

A human editor finishes, mixes and renders.

## Install (2 minutes)
1. Get the marketplace folder `whynot-cut-marketplace` (from the zip, a shared drive or a git repo).
2. In Claude Code:
   ```
   /plugin marketplace add "<path to>/whynot-cut-marketplace"
   /plugin install whynot-cut@thewhynot-ai
   ```
   In the desktop app: **+ › Plugins › Add plugin** with the same folder.
3. Start a new session and run **`/whynot-cut:start`**. It walks you through everything, one checked step at a time:
   - installs the engine in `~/.whynot-cut` (a private Python environment, ~400 MB; Python 3.10–3.12 needed)
   - connects Premiere Pro (installs the WhyNot Cut Bridge panel; gives you the one command for Adobe's PlayerDebugMode)
   - asks three preferences (where clients live, approval mode, transcription speed)
   - creates your first client folder and tells you exactly what to drop where

## Use
Drop files into the client folder that `/whynot-cut:start` (or `reel scaffold`) created:

| Folder | Put here |
|---|---|
| `assets/Logo`, `assets/Fonts`, `assets/Photos`, `assets/Brand` | logo, brand fonts, approved photos, brief + colours (HEX) |
| `data/Raw` | the raw clips to edit |
| `data/References` | reference edits you want to look like (optional) |
| `data/Music`, `data/SFX` | licensed music, your SFX library (optional) |

Then say **"edit the new videos"**. Or use the commands:

| Command | What it does |
|---|---|
| `/whynot-cut:start` | guided first-time setup |
| `/whynot-cut:autopilot` | edits every new clip (one combined approval) |
| `/whynot-cut:edit C0239` | full edit of one clip |
| `/whynot-cut:preview` | watchable MP4 of the planned edit, no Premiere needed |
| `/whynot-cut:revise "1- … 2- …"` | applies your comments, rebuilds, re-verifies, reports per comment |
| `/whynot-cut:status` | "is it ready?", with fresh evidence: Verified / Not verified / Needs you |
| `/whynot-cut:fix-audio` | dialogue cleanup and pause removal only |
| `/whynot-cut:new-client` | a new client's profile from their brand files and references |
| `/whynot-cut:handoff` | handoff package for the editor or another computer |
| `/whynot-cut:preferences` | approval mode, language, transcription model, clients folder |
| `/whynot-cut:setup` | install or repair the engine and Premiere bridge |
| `/whynot-cut:help` | cheat sheet |
| `/whynot-cut:adobe-extras` | After Effects / Photoshop output, only when you ask |

## Quick start بالعربي
١. ثبّت الإضافة من مجلد `whynot-cut-marketplace` ثم اكتب في Claude Code: **`/whynot-cut:start`**.
٢. سيتم تجهيز الجهاز وربط Premiere Pro وإنشاء مجلد للعميل خطوة بخطوة.
٣. ضع الشعار والخطوط والصور وملف الألوان في `assets/`، والفيديوهات الخام في `data/Raw/`.
٤. قل: **"عدّل الفيديوهات الجديدة"** — ستحصل على مشروع Premiere كامل وفيديو معاينة وتقرير جودة.
لا يتم تعديل ملفاتك الأصلية أبداً؛ كل النتائج في مجلد `output/`.

## How it works
The **lead editor** is the main conversation: it runs the pipeline, talks to you, and is the only one allowed to approve
the plan or record a verdict. Specialist agents do the stages; some fan out parallel sub-agents.

```
intake-inspector ─── what was dropped, what's missing (read-only)
client-researcher ── discover, client DB, reference style            (sub: —)
transcript-editor ── Whisper, corrections, words to confirm           (sub: segment-proofreader ×N)
audio-engineer ───── mic choice, hum/noise cleanup, pause removal + proof
story-editor ─────── meaning → edit-decisions.json → plan
medical-reviewer ─── on-screen claims vs. transcript (read-only)      (sub: claim-checker ×N)
motion-designer ──── brand stills, captions, SFX, visual checks       (sub: graphic-checker ×N)
        ▼  preview MP4 → Gate 1: you approve the plan (or approval: auto)
premiere-builder ─── native .prproj through the bridge, settings read back
qc-reviewer ──────── Premiere's own frames inspected (independent)    (sub: frame-inspector ×N)
        ▼  Gate 2: lead views the evidence, records the verdict, qc must pass
setup-doctor ─────── diagnoses machine/Premiere problems (read-only)
```

**Guardrails** (hooks, enforced in code for Bash, PowerShell and file edits):
- `assets/` and `data/` can't be written, moved or deleted. Whole project folders can't be deleted by the agent.
- After Effects / Photoshop commands need `--extras`.
- Subagents can't approve plans, record verdicts or change preferences; reviewers are read-only.
- Adobe preferences (PlayerDebugMode) are never written by Claude: you get the command to run yourself.

## macOS and Windows
| | macOS | Windows |
|---|---|---|
| Engine | `~/.whynot-cut` | `%USERPROFILE%\.whynot-cut` |
| `reel` command | bash wrapper | Git Bash wrapper + `reel.cmd` for PowerShell |
| Arabic graphics | CoreText, else HarfBuzz | HarfBuzz + FreeType |
| Face-aware photo crops | Vision | OpenCV |
| Premiere bridge (CEP) | `~/Library/Application Support/Adobe/CEP/extensions` | `%APPDATA%\Adobe\CEP\extensions` |
| AE / PS extras | AppleScript | `AfterFX.exe -r` / Photoshop COM |
Details: `skills/setup/references/platform-setup.md`.

## Preferences
`.claude/whynot-cut.local.md` (YAML frontmatter) in the clients folder, a client folder or `~/.claude/`:
```markdown
---
editor_name: "Sara"
language: ar            # en | ar
approval: ask           # ask | auto
whisper_model: large-v3 # large-v3 | large-v3-turbo | medium | small
preview_video: true
clients_root: "D:/WhyNot Clients"
notify_done: true
---
```
Edit with `/whynot-cut:preferences` or `reel settings`. Keep it out of git (`.claude/*.local.md`). The session hook reads
it at session start; engine commands read it every time.

## Client profiles
The engine is generic; each client's look and rules come from layered profiles (later wins):
1. `config/defaults/` (house settings, e.g. the Premiere sequence spec)
2. `profiles/<id>/` (shipped profiles: `dr-nahla-hunter`)
3. `<client>/output/client_database/reel-profile/` (the client's own copy, created by `reel client-init`)

`reel profile --root "<client folder>"` shows which applies.

## Upgrading from reel-editor 1.x
Install `whynot-cut`, then run `/whynot-cut:setup`. An existing `~/.reel-editor` engine (and its 3 GB of models) is reused
automatically, the old "Reel Editor Bridge" panel is replaced by the WhyNot Cut Bridge, and existing client `output/`
folders keep working. Uninstall `reel-editor` afterwards so the two don't both answer.

## Develop
```bash
<engine python> -m unittest discover -s whynot-cut/tests      # 72 tests (macOS and Windows)
<engine python> whynot-cut/examples/make_demo.py <empty folder>  # end-to-end demo without footage, Whisper or Adobe
claude plugin validate whynot-cut --strict
```
Bump `version` in `whynot-cut/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, then
`/plugin marketplace update thewhynot-ai`. Eval cases: `evals/` (`claude plugin eval whynot-cut`).

© 2026 The Why Not AI. All rights reserved. See `LICENSE`.
