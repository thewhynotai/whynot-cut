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
- **podcast mode** (2.1): a finished 16:9 episode → a reels plan with timecodes, content type and score → you pick →
  each reel framed per shot for 9:16 and edited by its content-type recipe → plus the YouTube/Instagram/TikTok copy
  (titles, description, chapters, tags, captions, hashtags, SRT) and thumbnail designs, checked against platform limits
- **motion mode** (2.2): a window of an episode's audio → an animated motion-graphics video (word-by-word Arabic
  kinetic type, icons, counters, steps, timelines) built as a **native After Effects project**, read back and QC'd

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
| `data/Episodes` | finished podcast episodes (16:9) to cut into reels, each with an optional `<name>.md` sheet |
| `data/References` | reference edits you want to look like (optional) |
| `data/Music`, `data/SFX` | licensed music, your SFX library (optional) |

Then say **"edit the new videos"**. Or use the commands:

| Command | What it does |
|---|---|
| `/whynot-cut:start` | guided first-time setup |
| `/whynot-cut:autopilot` | edits every new clip (one combined approval) |
| `/whynot-cut:edit C0239` | full edit of one clip |
| `/whynot-cut:podcast EP12` | podcast episode → reels plan → you pick → reels in Premiere + publish package |
| `/whynot-cut:motion EP12 R03` | an episode window's audio → animated motion video built in After Effects |
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

## Podcast mode
Put the finished episode in `data/Episodes/EP12.mp4` and, ideally, `data/Episodes/EP12.md`:
```
---
show: …
episode: 12
host: …
guest: "Name — role"
links:
  - https://…
sponsor: ""
avoid: [topics not to cut]
---
```
Say **"make reels from this episode"** (`/whynot-cut:podcast`):
1. `episode-prep` + `episode-transcribe` (resumable 10-minute chunks), intake check (burned subtitles, layout).
2. The episode-analyst writes the topic map (= YouTube chapters), speaker turns and **reel candidates** with exact
   timecodes snapped to sentences, a content type (storytelling, drama, success story, advice, bold opinion, emotional,
   comedy), a hook, a score and risks; `reels-plan` validates them and `reels-preview` renders a quick preview of each.
3. **Gate 0: you pick** (`reels-select --by editor`). Each pick becomes a clip project (`EP12_R03`) cut from a window
   of the original episode file: framed **per shot** for 9:16 (wide shots follow the speaker; cards shown whole),
   edited by its **content-type recipe** (pauses, zooms, graphics, SFX, licensed music mood, copy tone).
4. One combined Gate 1, Premiere builds, QC — as for any clip.
5. The **publish package**: `publish/youtube.md` (titles, description, chapters, tags), `EP12.srt`, per-reel captions
   for Instagram/TikTok/Shorts and thumbnail designs, checked by `publish-check` (platform limits, links only from the
   sheet, quotes only the speaker's words). Nothing is uploaded.

| Command | What it does |
|---|---|
| `reel episodes` / `reel episode-next --episode EP12` | episodes and what each needs next |
| `reel episode-prep` · `episode-transcribe` | probe, intake frames, time estimate · chunked Whisper with checkpoints |
| `reel reels-plan` · `reels-preview` | validate the analyst's plan · preview MP4 per candidate |
| `reel reels-select --pick R01,R03 --by editor` | Gate 0 (the editor's choice only; subagents are blocked) |
| `reel publish-check` · `publish-thumbnail --candidates/--render` | check + render the publish package · thumbnails |
| `reel music --list` | licensed tracks in `data/Music` with mood tags |

Results: `output/episodes/EP12/` (transcript, `01_analysis/reels-plan.md`, `03_candidates/`, `publish/`) and one
`output/projects/EP12_Rxx/` per reel.

## Motion mode
Pick a reel candidate (or a topic from the topic map) **as motion** at Gate 0 and get an animated video built from the
audio only — no camera picture needed, so audio-only podcasts work too (`data/Episodes/*.m4a|mp3|wav`).
1. `reel reels-select --episode EP12 --pick R03 --as motion --by editor` → project `EP12_R03_MO` (15–180 s).
2. `audio-clean`, then the **motion-director** turns what is said into beats and scenes following the content-type
   recipe (kinetic quote synced word by word, stat counter, steps, comparison, timeline, quote/context/person cards,
   licensed illustrations, outro) → `reel motion-plan` checks every word, number and name → `reel motion-animatic`.
3. **Gate 1**: you approve `motion-plan.md` + the animatic (editorial lines are marked as Claude's words).
4. After Effects: `reel ae-status` (the same bridge; restart After Effects once after `reel ppro-install`),
   `reel ae-probe` once per AE version, `reel motion-build` (native .aep, read back), `reel motion-render`,
   `reel motion-frames`, `qc`, `handoff`. Brand fonts must be installed for After Effects.

| Command | What it does |
|---|---|
| `reel motion-icons --search "money, growth"` · `motion-library` | icon names (Lucide, ISC) · licensed illustration packs |
| `reel motion-plan` · `motion-animatic` | compile + check the motion script · storyboard + preview MP4 |
| `reel ae-status` · `ae-probe [--record …]` | After Effects bridge · Arabic capability probe |
| `reel motion-build [--script-only]` · `motion-render [--scenes S03]` · `motion-frames` | build + read back · render · QC frames |

Results in `output/projects/EP12_R03_MO/`: `04_after_effects/project/*.aep`, `04_after_effects/render/*_motion.mp4`,
`08_quality_control/ae_frames/`, `09_handoff/README.md`.

## Quick start بالعربي
١. ثبّت الإضافة من مجلد `whynot-cut-marketplace` ثم اكتب في Claude Code: **`/whynot-cut:start`**.
٢. سيتم تجهيز الجهاز وربط Premiere Pro وإنشاء مجلد للعميل خطوة بخطوة.
٣. ضع الشعار والخطوط والصور وملف الألوان في `assets/`، والفيديوهات الخام في `data/Raw/`.
٤. قل: **"عدّل الفيديوهات الجديدة"** — ستحصل على مشروع Premiere كامل وفيديو معاينة وتقرير جودة.
٥. **البودكاست:** حط الحلقة الكاملة في `data/Episodes/` (ومعاها ملف `.md` بالضيف واللينكات) وقول **"طلّع ريلز من الحلقة"**:
توصلك خطة ريلز بالتايم كود ونوع المحتوى (حكاية، دراما، قصة نجاح…) ومعاينة لكل ريل، تختار منها، وكل ريل يتعمل
مشروع Premiere بإيقاع نوعه، ومعاه العناوين والديسكربشن والشابترز والتاجز والكابشن والثمبنيل.
٦. **الموشن:** في Gate 0 قول «R03 موشن» (`--as motion`): بيتعمل فيديو موشن جرافيك من **صوت** الجزء ده بس (كلام
بيظهر كلمة بكلمة، أرقام، خطوات، تايم لاين، أيقونات)، بتوافق على الخطة والـ animatic، وبعدها مشروع After Effects جاهز
ومتراجع من فريمات After Effects نفسه.
لا يتم تعديل ملفاتك الأصلية أبداً؛ كل النتائج في مجلد `output/`.

## How it works
The **lead editor** is the main conversation: it runs the pipeline, talks to you, and is the only one allowed to approve
the plan or record a verdict. Specialist agents do the stages; some fan out parallel sub-agents.

```
intake-inspector ─── what was dropped, what's missing (read-only)
client-researcher ── discover, client DB, reference style            (sub: —)
episode-analyst ──── podcast: topics, speakers, reels plan           (sub: moment-scout ×N)
        ▼  Gate 0 (podcast): you pick the reels
publish-writer ───── podcast: YouTube/social copy, thumbnails, publish-check
motion-director ──── motion: beats → scenes → motion-script.json, plan, animatic
ae-builder ───────── motion: After Effects build through the bridge, read-back, render, frames
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
- Subagents can't approve plans, pick reels (Gate 0), record verdicts or change preferences; reviewers are read-only.
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
