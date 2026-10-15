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

## ابدأ في ٣ خطوات (Quick start بالعربي)
إنت بتعمل ٣ حاجات بس: **حط الملفات · قول عايز إيه · وافق على الخطة**. الباقي كله شغل WhyNot Cut.

١. **ثبّت وابدأ:** ضيف الإضافة من مجلد `whynot-cut-marketplace` (أو من الـ installer)، افتح سيشن جديدة واكتب:
```
/whynot-cut:start
```
هيجهز الجهاز ويربط Premiere Pro ويعملك مجلد للعميل خطوة بخطوة، ويتخطى أي حاجة جاهزة أصلاً.
بعد كده دايماً افتح Claude جوه مجلد العملاء (أو جوه مجلد عميل واحد)، مش في أي مجلد تاني: صلاحيات WhyNot Cut
بتشتغل بس في المجلد اللي Claude اتفتح فيه.
لما Claude يتفتح في مجلد العملاء أول مرة هيسألك «تثق في الملفات اللي في المجلد ده؟» (workspace trust): وافق، عشان
WhyNot Cut يشتغل من غير ما يستأذن في كل أمر.

٢. **حط الملفات:** اللوجو والخطوط والصور وملف الألوان في `assets/`، والفيديوهات الخام في `data/Raw/`،
والحلقات الكاملة في `data/Episodes/`.

٣. **قول عايز إيه، ووافق على الخطة:**
- «عدّل الفيديوهات الجديدة» ← خطة وفيديو معاينة، توافق عليهم، وبعدها مشروع Premiere كامل وتقرير جودة.
- «طلّع ريلز من الحلقة» ← خطة ريلز بالتايم كود ونوع المحتوى (حكاية، دراما، قصة نجاح…) ومعاينة لكل ريل؛ تختار
  الريلز، وكل ريل يتعمل مشروع Premiere، ومعاه العناوين والديسكربشن والشابترز والتاجز والكابشن والثمبنيل.
- «اعمل موشن من الجزء ده» ← فيديو موشن جرافيك من **صوت** الجزء (كلام بيظهر كلمة بكلمة، أرقام، خطوات، أيقونات):
  توافق على الخطة والـ animatic، وبعدها مشروع After Effects جاهز ومتراجع من فريماته.
- «جاهز؟» أو «إيه اللي مستنيني؟» ← جدول واحد بكل العملاء وكل فيديو: حالته والخطوة الجاية.

**لوحة WhyNot Cut في Premiere** (Window › UXP Plugins › WhyNot Cut) بتعرض نفس الفيديوهات وحالة كل واحد، ومش محتاج
تكتب أي أمر فيها. الموافقة على الخطة: وافق هنا في الشات مع Claude (زرار الموافقة في اللوحة جاي في تحديث قريب).
ملفاتك الأصلية مبتتعدلش أبداً؛ كل النتايج في مجلد `output/`.

## Install (2 minutes)
1. Get the marketplace folder `whynot-cut-marketplace` (from the zip, a shared drive or a git repo).
2. In Claude Code:
   ```
   /plugin marketplace add "<path to>/whynot-cut-marketplace"
   /plugin install whynot-cut@thewhynot-ai
   ```
   In the desktop app: **+ › Plugins › Add plugin** with the same folder.
3. Start a new session and run **`/whynot-cut:start`**. It walks you through everything, one checked step at a time:
   - installs the engine in `~/.whynot-cut` (a private Python environment on Python 3.12 (installed by WhyNot Cut),
     with ffmpeg and the Whisper model) by running the installer that ships with the plugin: no Python, Xcode
     tools, Homebrew, winget or admin rights needed on macOS or Windows
   - connects Premiere Pro (installs the WhyNot Cut Bridge panel; gives you the one command for Adobe's PlayerDebugMode)
   - asks three preferences (where clients live, approval mode, transcription speed)
   - lets WhyNot Cut run without a prompt per command (`reel settings --allow-reel`: the clients folder and every client
     folder; Claude Code applies these rules only in the folder it is started in, after you accept that folder's
     workspace-trust dialog)
   - creates your first client folder and tells you exactly what to drop where

You do three things: **drop files** · **say what you want** · **approve the plan** (here in the chat; the approve
button in the **WhyNot Cut panel in Premiere** is coming in a next update). The panel (Window › UXP Plugins › WhyNot
Cut) shows each video's state; you never type commands there.

**Claude Code version.** Agent fields `omitClaudeMd` need Claude Code 2.1.271 or newer and `mcp__*` entries in an agent's `disallowedTools` need 2.1.178 or newer. Older versions ignore these fields; nothing breaks, the safeguards are just weaker.

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
| `/whynot-cut:status` | "is it ready?", with fresh evidence: Verified / Not verified / Needs you; with no clip named, `reel board`: one table of every client's videos, state and next step |
| `/whynot-cut:fix-audio` | dialogue cleanup and pause removal only |
| `/whynot-cut:new-client` | a new client's profile from their brand files and references |
| `/whynot-cut:handoff` | handoff package for the editor or another computer |
| `/whynot-cut:preferences` | approval mode, language, transcription model, clients folder |
| `/whynot-cut:setup` | install or repair the engine and Premiere bridge |
| `/whynot-cut:help` | what to do next where you are, plus the cheat sheet |
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
3. **You pick the reels** (`reels-select --pick R01,R03 --by editor`). Each pick becomes a clip project (`EP12_R03`) cut from a window
   of the original episode file: framed **per shot** for 9:16 (wide shots follow the speaker; cards shown whole),
   edited by its **content-type recipe** (pauses, zooms, graphics, SFX, licensed music mood, copy tone).
4. You approve one combined plan, then the Premiere builds and the proof check, as for any clip.
5. The **publish package**: `publish/youtube.md` (titles, description, chapters, tags), `EP12.srt`, per-reel captions
   for Instagram/TikTok/Shorts and thumbnail designs, checked by `publish-check` (platform limits, links only from the
   sheet, quotes only the speaker's words). Nothing is uploaded.

| Command | What it does |
|---|---|
| `reel episodes` / `reel episode-next --episode EP12` | episodes and what each needs next |
| `reel episode-prep` · `episode-transcribe` | probe, intake frames, time estimate · chunked Whisper with checkpoints |
| `reel reels-plan` · `reels-preview` | validate the analyst's plan · preview MP4 per candidate |
| `reel reels-select --pick R01,R03 --by editor` | pick the reels (the editor's choice only; subagents are blocked) |
| `reel publish-check` · `publish-thumbnail --candidates/--render` | check + render the publish package · thumbnails |
| `reel music --list` | licensed tracks in `data/Music` with mood tags |

Results: `output/episodes/EP12/` (transcript, `01_analysis/reels-plan.md`, `03_candidates/`, `publish/`) and one
`output/projects/EP12_Rxx/` per reel.

## Motion mode
Pick a reel candidate (or a topic from the topic map) **as motion** when you pick the reels and get an animated video built from the
audio only — no camera picture needed, so audio-only podcasts work too (`data/Episodes/*.m4a|mp3|wav`).
1. `reel reels-select --episode EP12 --pick R03 --as motion --by editor` → project `EP12_R03_MO` (15–180 s).
2. `audio-clean`, then the **motion-director** turns what is said into beats and scenes following the content-type
   recipe (kinetic quote synced word by word, stat counter, steps, comparison, timeline, quote/context/person cards,
   licensed illustrations, outro) → `reel motion-plan` checks every word, number and name → `reel motion-animatic`.
3. **You approve the plan**: `motion-plan.md` + the animatic (editorial lines are marked as Claude's words).
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

## How it works
The **lead editor** is the main conversation: it runs the pipeline, talks to you, and is the only one allowed to approve
the plan or record a verdict. Specialist agents do the stages; some fan out parallel sub-agents.

```
intake-inspector ─── what was dropped, what's missing (read-only)
client-researcher ── discover, client DB, reference style            (sub: —)
episode-analyst ──── podcast: topics, speakers, reels plan           (sub: moment-scout ×N)
        ▼  podcast: you pick the reels
publish-writer ───── podcast: YouTube/social copy, thumbnails, publish-check
motion-director ──── motion: beats → scenes → motion-script.json, plan, animatic
ae-builder ───────── motion: After Effects build through the bridge, read-back, render, frames
transcript-editor ── Whisper, corrections, words to confirm           (sub: segment-proofreader ×N)
audio-engineer ───── mic choice, hum/noise cleanup, pause removal + proof
story-editor ─────── meaning → edit-decisions.json → plan
medical-reviewer ─── on-screen claims vs. transcript (read-only)      (sub: claim-checker ×N)
motion-designer ──── brand stills, captions, SFX, visual checks       (sub: graphic-checker ×N)
        ▼  preview MP4 → you approve the plan (or approval: auto)
premiere-builder ─── native .prproj through the bridge, settings read back
qc-reviewer ──────── Premiere's own frames inspected (independent)    (sub: frame-inspector ×N)
        ▼  proof check: lead views the evidence, records the verdict, qc must pass
setup-doctor ─────── diagnoses machine/Premiere problems (read-only)
```
Internal note (for developers reading engine logs and status codes): Gate 0 = pick the reels, Gate 1 = approve the
plan, Gate 2 = proof check. The editor only ever hears the plain words.

**Guardrails** (hooks, enforced in code for Bash, PowerShell and file edits):
- `assets/` and `data/` can't be written, moved or deleted. Whole project folders can't be deleted by the agent.
- After Effects / Photoshop commands need `--extras`.
- Subagents can't approve plans, pick reels, record verdicts or change preferences; reviewers are read-only.
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
Details: `skills/setup/references/platform-setup.md`. Optional environment variables (`WHYNOT_HOME`,
`WHYNOT_FFMPEG`, `WHYNOT_PREMIERE_APP`, …) are listed there under "Environment variables".

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
panel_link: true        # false: do not start the Premiere panel's engine at session start
---
```
A file holds only the keys someone set. Each key is decided by the strongest layer that sets it: the client folder's
file, then the machine's (clients folder, then `~/.claude/`), then the plugin options (`/plugin` > WhyNot Cut: language
`ar`|`en` (default `ar`), approval, whisper model, Magnific credit budget `magnific_budget_credits` (default 300; 0 = never
use Magnific) and the Magnific key, which lives only there), then the defaults. `reel settings` shows the result and where
each value came from; a bad value is ignored with a warning. Edit with `/whynot-cut:preferences` or `reel settings`.
Keep files out of git (`.claude/*.local.md`). The session hook reads them at session start; engine commands every time.

## Client profiles
The engine is generic; each client's look and rules come from layered profiles (later wins):
1. `config/defaults/` (house settings, e.g. the Premiere sequence spec)
2. `profiles/<id>/` (shipped seed profiles: the blank `_template` and the fictional `example-clinic`; a shipped profile applies only when named with `--profile <id>` or by the `id` in the client's own profile, never by folder name)
3. `<client>/output/client_database/reel-profile/` (the client's own copy, created by `reel client-init`)

`reel profile --root "<client folder>"` shows which applies.

File names carry the client's tag (`profile.json` `prefix`, e.g. `C0239_NH_EDIT.prproj`). It never changes under an
existing project: a stored prefix wins whenever it is safe in a file name (2.x values such as `N-H` included); else the
tag the client's existing projects already use (`.prproj`, the XML fallback in `07_premiere/interchange/`, `.aep`; a
2.x client keeps `RE`); else the initials of the client folder's ASCII words (a leading Dr/Prof/Eng skipped:
"Nour Hospital" → NH); else `WN` (an Arabic-only name). `reel scaffold` stores it when it creates the folder (renaming
the folder later keeps it) and `reel client-init` stores it in the profile (`--prefix` sets it: letters (Arabic too), digits, `.`, `-`,
`_`; `--force` keeps the stored one).

`reel board` prints one table of every client under the clients folder (each video: state, next step), in the
editor's language (finished videos folded into one "+N done" row per client; `--all` lists them);
`reel board --json` prints the same as a stable document (`board: 1`; documented in `engine/reel/lib/board.py`), the
data the Premiere panel shows.

## Upgrading from 2.x
Update the plugin, then run `reel setup` (it moves the engine to the isolated 3.0 runtime, and `reel ppro-install` plus a
restart of Premiere and After Effects loads the new bridge) and re-approve any plan that was approved before: approvals
made by 2.x are asked again. The exact steps are in the **Migration** section of the 3.0.0 entry in `CHANGELOG.md`.

## Upgrading from reel-editor 1.x
Install `whynot-cut`, then run `/whynot-cut:setup`. An existing `~/.reel-editor` engine (and its 3 GB of models) is reused
automatically, the old "Reel Editor Bridge" panel is replaced by the WhyNot Cut Bridge, and existing client `output/`
folders keep working. Uninstall `reel-editor` afterwards so the two don't both answer.

## Develop
```bash
bash tools/test.sh                      # the whole suite with the engine runtime (macOS and Windows); -p test_x.py for one file
reel py -m unittest discover -s whynot-cut/tests   # the same, by hand (run from the repo root)
reel py whynot-cut/examples/make_demo.py <empty folder>  # end-to-end demo without footage, Whisper or Adobe
claude plugin validate whynot-cut --strict
```
Bump `version` in `whynot-cut/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, then
`/plugin marketplace update thewhynot-ai`. Eval cases: `evals/`. From the repo root, with ffmpeg on PATH:
`claude plugin eval ./whynot-cut --scaffold --ablation none --judge-model sonnet --allow-tools Write Edit --runs 3`
(a path, so this tree is tested, not an installed copy), then `python tools/eval_summary.py <aggregate-result.json>`
for the per-case table (a case passes at 2 of 3 runs).

© 2026 The Why Not AI. All rights reserved. See `LICENSE`.
