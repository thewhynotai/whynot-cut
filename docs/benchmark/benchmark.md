# WhyNot Cut 3.0 — benchmark study (G-T1, Addendum G §G1)

| | |
|---|---|
| Date | 2026-10-14 |
| Task | G-T1 (read-only). Short report under G10: it is meant to fix real gaps, not to be a research project |
| Bar | Addendum G §G0–G2: for every core job, WhyNot Cut is at least at parity with the best reference tool on quality of result, speed, clarity and recovery from errors |
| Method | Public pages only, read on 2026-10-14 (vendor docs, pricing pages, help centres, Adobe community, Trustpilot/G2/Capterra, blogs). No sign-ups, logins, downloads, purchases or forms. Findings are summarised, not quoted. Our side comes from the repo at `release/3.0` (README, `reel --help`, PROGRESS.md, Addenda A–G, `docs/adobe/uxp-parity.md`, `docs/design/reviews/`, `docs/review/2026-10-11/`) |
| Evidence strength | **strong** = vendor documentation or our own measurement; **medium** = an independent review or test; **weak** = a vendor marketing claim, a single forum post, a competitor-run test, or our inference. Vendor speed claims are always marked as claims |
| Re-scored by | Phase 8 buyer panel (G6). Release needs zero open P0 and zero open P1 gaps (G1.3) |

---

## 1. One-page summary

**Where we really stand.** WhyNot Cut's built pipeline (talking-head edit → native Premiere project, podcast → reels plan → Premiere reels + publish copy, motion → native After Effects project, QC from Premiere's own frames) has **no direct equivalent among the reference tools**. None of them produces a branded, story-edited Premiere or After Effects project from raw footage with automated frame QC. On the result itself, and especially for Arabic, we are **ahead**.
- **Premiere's own Speech to Text still has no Arabic**, and its caption translation doesn't offer Arabic either (Adobe product page; Adobe community, Dec 2025 – Jan 2026).
- **Descript has no Arabic transcription**, and its users report Arabic caption words appearing in reversed order.
- **FireCut** inserts captions as PNG images, not editable text.
- **AutoCut and Submagic list Arabic**, but neither documents correct RTL display in Premiere or Egyptian-dialect quality.

**Where we are behind:** speed to first result, clarity of the first hour, and proven recovery in the user's own project.
1. **Kalam, Hush and Tidy aren't in the product yet.** The upstream code is imported and Phase 6B is planned, but nothing has been ported. AutoCut and FireCut ship silence removal and captions inside Premiere today, with an installer and a 7–14-day trial.
2. **Speed.**
   - The references report seconds to minutes. AutoCut cut a 30-minute clip's silences in about 80 s in a competitor-run test. Submagic claims about 30 s per minute of video.
   - Our main job has **no measured end-to-end time**. The one observation we have is a "1–2 hour" estimate, after which the owner stopped the run for lack of visible progress (`docs/review/2026-10-11/chats-main.md`).
3. **Clarity.**
   - The Premiere panel can't approve or run anything yet (Addendum C; the README says the approve button is "coming").
   - The first design critique found 20 «مش فاهم» ("I don't understand") moments, 10 of them MAJOR (`docs/design/reviews/ED3-r1-first-time-editor.md`).
   - The agency-owner persona said "would not pay yet" (`G2-r1-agency-owner.md`).
4. **Recovery.**
   - Building a *new* project is safe: originals are never touched, and a rebuild keeps the previous `.prproj` as a backup.
   - "One Ctrl+Z undoes the whole build" is still unproven (uxp-parity U3).
   - The Hush/Tidy/Kalam edits to the editor's *own* project have only a spec so far. FireCut copies the sequence before every operation and has its own Undo button. Descript has version history.
5. **macOS has never been run**, on any 2.x or 3.0 path, while 90% of our buyers edit on a Mac (G11). Every reference tool ships for Mac.

**Counts.** 24 gaps: **4 × P0, 13 × P1, 7 × P2** (section 4).

**Most P0/P1 gaps are already tasked** in a phase (6B, 6, 7, 9). This report adds the measurable bar and the evidence.

**New, untasked items worth adding:**
- an end-to-end time budget for the main job (G-04);
- an Arabic/Egyptian caption accuracy eval set (G-06);
- a Hush speed measurement against AutoCut/FireCut (G-07);
- Kalam's correction backend when no Claude session is open (G-08);
- a time-saved line plus the trust lines (G-12, G-13);
- a panel command palette with shortcuts (G-11).

**Price context** (for the commercial edition, not a 3.0 gap).

| Tool | Price |
|---|---|
| AutoCut | $9.90–19.80/mo |
| FireCut | $11–34/mo |
| Submagic | $19–69/mo |
| Descript | $16–65/mo |
| Captions | $25–280/mo |
| Runway | $15–95/mo |
| Premiere | ~$23/mo; CC Pro ~$70/mo |
| Excalibur | $120 one-time |

At $1,000/mo we are 15–50× the price of any one of them. The value has to be visible:
- hours saved per reel, shown;
- Arabic that works where theirs doesn't;
- a finished, branded Premiere/AE project;
- QC proof;
- zero lost work.

---

## 2. Per-tool findings

Each block: what matters for our jobs · onboarding / time to first result · UX pattern · recovery · Arabic/RTL · price · praise / complaints. URLs are inline.

### 2.1 Adobe Premiere Pro (26.x; 26.5 shipped Sept 2026)

**What matters for our jobs**
- **Text-Based Editing:** shows filler words and pauses, which you can delete in bulk (https://community.adobe.com/announcements-732/now-in-beta-filler-words-and-other-text-based-editing-updates-in-premiere-pro-313483/index1.html).
- **Paper Edit (26.5):** build a rough cut by selecting sentences in the transcript (https://community.adobe.com/announcements-727/what-s-new-in-adobe-premiere-26-5-september-2026-1641187).
- **Captions:** single-word captions arrived in 26.3. Caption translation covers 27 languages and runs in the cloud (https://www.adobe.com/products/premiere/speech-to-text.html).
- **Other tools:** Enhance Speech, Auto Reframe, and Scene Edit Detection.
- **Media Intelligence search:** runs on the device; English-only for visual search (https://helpx.adobe.com/premiere-pro/using/media-intelligence-and-search-panel-faq.html).
- **Sequence Index panel (26.2):** helps with cleanup. **Object Mask (26.0)** and the **Generative Media tool (26.5)** are also new (https://www.newsshooter.com/2026/01/20/whats-new-in-adobe-premiere-pro-26-0/).

**Onboarding:** English transcription works offline out of the box. Other language packs are over 500 MB each (Adobe staff, 2022). Some users get stuck at "initializing local transcription engine" (https://community.adobe.com/questions-729/inicializando-el-motor-de-transcripcion-local-1387929).

**UX:**
- Transcript and captions live in the Text panel. Filler words are highlighted and reviewed before deletion.
- The Properties panel replaced most of Essential Graphics, and some users can't find the caption settings there (https://community.adobe.com/t5/premiere-pro-discussions/essential-graphics-panel-2025/m-p/15185952/highlight/true).

**Recovery:**
- Edits are non-destructive, with native undo.
- A known bug: deleting fillers and then pauses removed the end of the audio. The workaround was to lock tracks first (https://community.adobe.com/t5/premiere-pro-bugs/remove-filler-word-function-oddities/idc-p/14763004).

**Arabic/RTL (strong):**
- **Arabic is not among the 18 speech-to-text languages** (https://www.adobe.com/products/premiere/speech-to-text.html). Users were still asking for it on Premiere 26 in Jan 2026 (https://community.adobe.com/feature-requests-730/speech-to-text-in-arabic-not-supported-in-premiere-pro-26-1621281).
- **No translation into Arabic.** The suggested workaround is SRT → LLM → re-import (https://community.adobe.com/questions-729/translation-into-arabic-1621797).
- Premiere 26 can import a JSON transcript. That lets an outside Whisper transcript drive Text-Based Editing (same thread as above; medium).
- RTL caption bugs have a long history: reversed SRT import, letters not joined, punctuation at the wrong end (https://community.adobe.com/t5/premiere-pro-discussions/srt-import-with-right-to-left-language-e-g-hebrew-arabic-text-is-reversed/m-p/13592853/highlight/true). Whether they still happen in 26.x is unconfirmed.

**Price:** single app about $23/mo; Creative Cloud Pro about $70/mo; Frame.io is included (https://www.adobe.com/products/premiere/plans.html; US figures are third-party).

**Praise and complaints:**
- Praise: text-based editing roughly halved a talking-head cut, 64 min vs 117 min (https://www.redsharknews.com/how-much-time-does-using-premiere-pros-text-based-editing-really-save).
- Complaints:
  - transcription errors on medical content (https://community.adobe.com/t5/premiere-pro-ideas/auto-transcribed-captions-needs-improvement/idi-p/15217800);
  - Enhance Speech inventing words;
  - Auto Reframe drifting off talking heads;
  - 26.5.2 freezing for minutes at a time.

### 2.2 Adobe After Effects (26.5)

**What matters:**
- Object Matte AI roto (26.2; cached to disk in 26.5).
- An **Assistant (beta)** agent that organises projects and writes expressions.
- Nothing new for MOGRTs (https://community.adobe.com/announcements-527/after-effects-26-5-is-here-1641108).

**Arabic:**
- Native RTL since 14.2; RTL text animation fixed in 22.5 (https://community.adobe.com/t5/after-effects-discussions/after-effects-22-5-is-now-live/m-p/13096969/highlight/true).
- A 2023 regression flipped RTL values (https://community.adobe.com/t5/after-effects-bugs/new-ae-update-flips-everything-for-rtl-languages/idc-p/13879301).

**Complaints:** regressions after 26.3, including broken expression editing and playback freezes (same 26.5 thread).

**Relevance:** no reference tool turns spoken content into an AE motion piece. AE is our host, not our competitor.

### 2.3 Frame.io (V4)

**What matters:**
- The Premiere 25.6+ panel turns comments into timeline markers, jumps to them on click, and offers to upload a new version when the sequence changes (https://help.frame.io/articles/12833113-adobe-premiere-frame-io-v4-panel-overview-25-6-and-later).
- Version stacks; natural-language search; Camera to Cloud.

**Arabic:** Arabic is among its 27 transcription languages, with SRT/VTT export and no translation (https://help.frame.io/en/articles/10966531-frame-io-transcription-overview).

**Speed:** transcripts take "a few minutes" (same page).

**Price:** Free (2 seats) · Pro $15 · Team $25 per member per month (https://frame.io/pricing).

**Complaints:** V4 felt slow and incomplete at launch (https://reddit.sudovanilla.org/r/editors/comments/1gc11fk/new_frameio_v4_sucks), and markers get overwritten or duplicated (https://community.adobe.com/bug-reports-728/frame-io-v4-keeps-overwriting-comments-markers-in-premiere-pro-pro-1332248).

**Relevance:** the human review loop with clients (our QC is machine-side).

### 2.4 Descript

**What matters:**
- Text-based editing.
- **Underlord**, an agentic chat co-editor that can run on Claude models (https://help.descript.com/hc/en-us/articles/36803785502221).
- Filler removal and "shorten word gaps" with per-item review (https://help.descript.com/hc/en-us/articles/21908864772493).
- Studio Sound.
- "Find good clips".
- **Export to Premiere XML** on the Creator plan and up (https://help.descript.com/hc/en-us/articles/10255813481613-Timeline-exports).

**Onboarding and speed:** one reviewer edited a 45-min podcast in under 20 min vs over an hour in Premiere (https://marcandrews.com/?p=3033; medium).

**UX:** the transcript is the timeline, and the chat agent sits in a sidebar. This is the closest analogue to our chat + plan approach.

**Recovery:**
- File > Version history restores the whole project. Pending versions are kept locally, and Help > Debug can make a backup (https://help.descript.com/working-in-projects/version-history, https://help.descript.com/app-troubleshooting/project-saving).
- A June 2026 sync incident lost edits (https://pulsetic.com/status/descript/incidents/4780/).

**Arabic:**
- **No Arabic transcription**; 26 Latin-script languages only (https://help.descript.com/hc/en-us/articles/10249408168845).
- Users report RTL caption words in reversed order (https://feedback.descript.com/feature-requests/p/captions-for-right-to-left-languages).

**Price:** Hobbyist $16–24 · Creator $24–35 · Business $50–65 per month, with media-hour and AI-credit caps (https://www.descript.com/pricing).

**Praise and complaints:** Trustpilot 2.6/5. Praise is for text editing. Complaints are credit burn, crashes and lost edits, and hard cancellation (https://www.trustpilot.com/review/descript.com).

### 2.5 AutoCut (Premiere + DaVinci extension)

**What matters:**
- The AI plan bundles Silences, AutoCaptions, Podcast multicam, Angles, AutoZoom, AutoViral (clips scored for viral potential), AutoB-Rolls, Repeat, Profanity and Chapters (https://www.autocut.com/en/pricing).
- No cleanup, After Effects or QC features.

**Onboarding:**
- Download the installer, restart Premiere, open Window ▸ Extensions.
- Enter an email; a 14-day trial key arrives with no card needed. One machine at a time (https://www.autocut.com/en/blogs/how-to-activate-autocut-free-trial/).

**UX:**
- dB threshold, minimum silence and speech, padding, and pacing presets from Calm to Jumpy (https://digitalproduction.com/2026/04/08/autocut-brings-ai-cleanup-inside-premiere-pro/).
- Preview before applying (https://www.autocut.com/en/autocutsilences/).
- Caption transcript review and saved style presets.

**Recovery:**
- A "backup system" is advertised but not explained.
- A third-party tutorial says cuts are irreversible by default, so keep a copy (https://aiindigo.com/tutorials/getting-started-with-autocut-automate-jump-cuts-and-silence-removal-in-premiere; medium).

**Arabic:**
- Arabic captions and translation among 80+ languages.
- **Since July 2026 the whole interface is localised to Arabic with RTL layout** (https://www.autocut.com/en/blogs/july-autocut-updates-2026/). An Arabic UI alone is no longer a differentiator.
- RTL display of the captions in Premiere is undocumented.

**Price:** Basic $9.90/mo · AI $19.80/mo ($178.80/yr), with no usage caps.

**Praise and complaints:** Trustpilot 4.8/5, praised for time saved. Complaints: caption timing needs correction, bugs on long footage, and soft word endings clipped (https://www.trustpilot.com/review/autocut.fr?page=4, https://www.getapp.com/all-software/a/autocut/).

**Speed:**
- Vendor claim: a 1-hour video cut in under 30 s.
- A competitor-run test (cutback.video, M4 Pro) measured 3 min → 60 s, 30 min → 80 s, and 120 min on 3 tracks → about 15 min (https://cutback.video/blog/the-best-auto-silence-removal-plugin-for-premiere-pro; weak, the tester is a competitor).

### 2.6 FireCut (Premiere extension + web)

**What matters:** silence removal (quick and advanced), captions in 50+ languages, podcast camera switching, removal of fillers, repeats and profanity, chapters, zooms, shorts, and B-roll (https://firecut.ai/premiere-pro).

**Onboarding:** an .exe/.pkg installer plus a licence key; activation needs internet and works on one device; 7-day trial (https://learn.firecut.ai/overview-premiere-pro/faq).

**UX:**
- A home screen of feature buttons and a top bar with Undo, "Reload plugin" and Update (https://learn.firecut.ai/overview-premiere-pro/using-firecut).
- Loose, default or tight presets, plus an advanced mode that lets you exclude individual silences.

**Recovery (strong):**
- **Copies the sequence before every operation.** The docs say to use the panel's Undo, not Ctrl+Z (same page).
- Known issues: "Unable to connect to Premiere Pro", and caption stripes after a project reopens.
- One user reported Premiere became unusably laggy after thousands of cuts (https://community.adobe.com/t5/premiere-pro-discussions/using-firecut-plugin-to-cut-silence-and-after-i-do-my-premiere-pro-is-unusably-laggy/m-p/14765054/highlight/true).

**Arabic:** listed. **Captions are PNG images, not editable text** (FAQ above). An Arabic creator asked for real text layers (https://firecut.ai/blog/cutting-edit-times-by-10x-with-firecut/).

**Price:** Starter $6–11 · Pro $12–20 (25 h a month) · Max $20–26 (100 h) · Team $34 per user (https://firecut.ai/pricing).

**Speed:** the competitor-run test measured 3 min → 30 s and 30 min → 105 s, and its 120-min 3-track test failed (cutback URL above; weak).

**Reviews:** no independent review base. G2 is empty, and the reviews on its own site are curated (https://www.g2.com/sellers/firecut-ai).

### 2.7 Excalibur (Knights of the Editing Table)

**What matters:** a keyboard command palette for Premiere: effects, presets and chained "user commands". No AI, captions or Arabic (https://knightsoftheeditingtable.com/excalibur).

**Onboarding:** licence key. On Mac you grant Accessibility and Input Monitoring; on Windows, antivirus may need to allow its helper programs. No trial (https://manuscript.knightsoftheeditingtable.com/llms-full.txt).

**UX:** a floating search bar on Option+Space. **On Windows it takes 1–3 s to open** (same doc).

**Recovery:** its own undo stack of up to 100 steps; mixing it with Premiere's native undo can lose that record.

**Price:** $120 one-time for 2 machines.

**Praise and complaints:** praised for speed over the mouse; criticised for a learning curve and limits of Premiere's API (https://www.provideocoalition.com/excalibur-adds-more-speed-and-less-mouse-to-adobe-premiere-pro/).

**Relevance:** the keyboard-speed bar for an Adobe panel.

### 2.8 Submagic

**What matters:**
- Animated caption templates, one-click silence and filler removal, auto-zooms and B-roll (https://submagic.co/features/trim-video).
- Magic Clips (long video to shorts) is an add-on.
- **No Premiere handoff.**

**Onboarding:** 3 steps: upload, edit, download. **Vendor claim: about 30 s per 1-minute video** (https://submagic.co/auto-subtitle-generator/arabic). A 2026 review says under 2 min from raw to clip (https://ucstrategies.com/news/submagic-review-2026-pricing-features-is-it-worth-it-for-creators/).

**UX:** the template gallery comes first. The AI Boost toggles turn features on or off, and words the AI is unsure of are highlighted orange for review.

**Recovery:** undo and versioning are unconfirmed. Stuck exports are reported.

**Arabic:** one of 44 languages, with a vendor claim of 99.5% accuracy and no method given (weak). No dialect or RTL documentation.

**Price:** Starter $12–19 · Pro $23–39 · Business $41–69 per month, with length caps of 2, 5 and 30 min (https://www.submagic.co/pricing).

**Reviews:** Trustpilot 4.5/5. Praise: time saved and support. Complaints: billing in Oct 2026 (https://www.trustpilot.com/review/submagic.co).

### 2.9 Captions (company renamed Mirage, Sept 2025)

**What matters:**
- **AI Edit:** pick a style, then review the cuts. It adds captions, B-roll and music.
- **Clips:** up to 3 h or 10 GB of input becomes **30+ clips ranked by a virality score** (https://captions.ai/help/docs/project/clips).
- Lipdub, Eye Contact, Denoise.
- No Premiere export documented.

**Onboarding:** upload, style, review, template, create. Clips sends a notification when ready. The older help page said it could take "up to an hour" (https://help.captions.ai/docs/project/ai-shorts).

**Recovery:** no version history documented. Caption sync drifts after edits, and exports crash (https://www.eesel.ai/blog/captions-ai).

**Arabic:** listed; dialect and RTL are undocumented.

**Price:** Max $24.99 · Frontier $70–280 per month (third-party).

**Reviews:** Trustpilot 4.4/5 with 19% 1-star. Complaints: the AI misreads prompts, and fixing its mistakes can take longer than editing by hand (https://www.trustpilot.com/review/captions.ai).

### 2.10 Runway (Aleph 2.0 / Edit Studio, May 2026)

**What matters:** prompt-based object removal, inpainting, relighting and restyling on clips up to 30 s, plus Gen-4.5 for B-roll (https://runway.com/news/introducing-aleph-2-and-edit-studio). No Premiere integration and no captions.

**Price:** Standard $12–15 · Pro $28–35 · Max $76–95 per month (https://runway.com/pricing).

**Relevance:** B-roll/asset generation only. That is Phase 5 (Magnific) territory, not a core-job competitor.

### 2.11 UI craft: Linear, Raycast, Arc

**Linear**
- **Keyboard:** Cmd/Ctrl+K runs any action, and Cmd+/ lists every shortcut (https://linear.app/enablement/guide/navigating-linear).
- **Speed:** local-first, so actions show at once. The "<50 ms page" figure is third-party (https://linear.app/blog/rebuilding-delta-sync-read-path).
- **Undo:** Cmd+Z covers almost every change (https://linear.app/changelog/undo-actions).
- **Theme:** colours generated from 3 inputs in LCH (https://linear.app/blog/how-we-redesigned-the-linear-ui).
- **Principle:** don't compete for attention you haven't earned (https://linear.app/blog/behind-the-latest-design-refresh).

**Raycast**
- **Principles:** fast, simple, delightful. Every action shows its shortcut beside it (https://www.raycast.com/blog/a-fresh-look-and-feel).
- **Toasts:** Success, Failure and Animated progress, with actions such as undo, cancel and copy error (https://developers.raycast.com/api-reference/feedback/toast).
- **Store rules:** never flash an empty "No results" list while loading; custom empty views (https://developers.raycast.com/basics/prepare-an-extension-for-store).
- **Cadence:** about one release a week, with a per-extension update report (https://www.raycast.com/changelog).

**Arc**
- In maintenance mode since May 2025. Its CEO said it asked too much learning for too little reward (https://engadget.com/ai/the-browser-company-stops-active-development-of-arc-in-favor-of-new-ai-focused-product-153045276.html).
- Praised for onboarding that explains what happens next, and for weekly release notes with one visual per feature (https://buildtogether.substack.com/p/arc-browser-release-notes-review).
- Criticised for a forced account (https://deceptive.design/articles/arc-browsers-pushy-account-requirements).

**RTL:** none of the three supports Arabic/RTL. Raycast's store even forbids custom localisation. Doing RTL perfectly is open ground for us.

---

## 3. Parity per core job (as specified and as built, 2026-10-14)

Legend:
- **Ahead / Parity / Behind / Not built** compares us with the best reference for that job and axis.
- "Spec" means the design covers it but it isn't built or measured yet.

| Core job | Best reference(s) | Quality of result | Speed | Clarity | Recovery from errors | Verdict |
|---|---|---|---|---|---|---|
| **Talking-head edit → Premiere project** | Descript (text edit + XML export), Premiere Text-Based Editing, Submagic (fast reels) | **Ahead.** Story-driven plan, brand graphics, correct Arabic shaping, preview MP4, native .prproj with settings read back. Verified live on Windows (2.x, real client reels). No reference outputs a finished branded Premiere project | **Behind / unmeasured.** Whisper about 10× real time on an RTX 4060, but no end-to-end figure; one observed "1–2 h" estimate. References: minutes (Submagic about 2 min; Descript 45-min podcast in <20 min) | **Behind.** Chat-driven with 3 verbs, but the panel can't approve or act yet; 20 «مش فاهم» moments in design round 1; 15 commands in the README | **Parity on new-build safety:** originals never touched; a rebuild keeps the previous .prproj; `reel next` resumes. **Unproven:** one Ctrl+Z (U3). Descript has version history | Behind on speed and clarity → G-03, G-04, G-05, G-10 |
| **Podcast → reels** | Captions Clips (30+ ranked clips from ≤3 h), AutoCut AutoViral, Descript clips | **Ahead in kind.** Content-type recipes, sentence-snapped timecodes, per-shot 9:16 framing, editor picks, Premiere builds plus a publish package checked against platform limits. Verified on a 35-min test episode | **Unmeasured** on a real 60–90-min episode (never run). Transcription of 35 min took about 4 min. Captions' older docs said "up to an hour" | Parity in the chat flow (Gate 0 pick); the panel pick isn't built | Resumable 10-min transcription chunks: **Ahead** of web tools that restart | Mostly parity or ahead; long episode unproven → G-14 |
| **Arabic/English captions (Kalam)** | AutoCut AutoCaptions, Submagic, Premiere captions (no Arabic), FireCut (PNG only) | **Spec: ahead.** Egyptian Whisper + alignment + Claude correction under client rules + meaning-unit DP; output as a captions track, MOGRT or SRT. Today only the pipeline's own caption stills ship; **Kalam isn't ported** and there's **no Arabic accuracy number** | Spec budget ≤ real time on GPU for 60 s; not measured inside WhyNot Cut. Submagic claims about 30 s per minute | Spec: one press, MOGRT gallery. Not built | Spec: SRT shift, range only. Not built | **Not built** → G-01, G-06, G-08 |
| **Silence & pause removal (Hush)** | AutoCut Silences, FireCut | **Spec: parity+.** Frame-accurate, never cuts speech, Arabic + English fillers, linked items, no gaps. The pipeline's `audio-clean` already removes pauses with proof that no words were lost. **Hush isn't ported** (upstream is macOS-only) | Budget 10 min ≤ 30 s. AutoCut: 30 min ≈ 80 s; FireCut: 30 min ≈ 105 s (competitor test). **Ours not measured** | Spec: waveform with the planned cuts, one slider + Advanced, markers-only mode (= AutoCut/FireCut) | Spec: backup sequence + one-click restore (= FireCut). Not built or proven | **Not built** → G-01, G-07, G-09 |
| **Project cleanup (Tidy)** | No real competitor (Premiere Sequence Index panel, AE Assistant beta, Excalibur's sibling Watchtower) | **Spec: ahead.** Unused-item removal (never from disk), numbered bins by real media type, nest naming, podcast sync à la PluralEyes. Not ported | Unmeasured | Spec: preview with tick boxes | Spec: save + backup before any change, undo by reopening the backup | **Not built**, but no reference does it → G-01 |
| **Motion graphics in After Effects** | None among the references (AE Assistant beta is generic) | **Ahead.** Spoken content → beats → native .aep with word-by-word Arabic kinetic type, read back and QC'd. Verified on AE 26.5 with the **fallback font only** | Unmeasured | Plan + animatic approval in chat | New project each time; rebuild safe | Ahead; brand-font run and audio-only run unproven → G-15 |
| **QC** | Frame.io (human review loop) | **Ahead on machine QC.** Premiere's own frames exported, frame-inspector fan-out, evidence verdict recorded only by the lead. No reference does automated frame QC | Unmeasured | Verified / Not verified / Needs you, in chat | Pass/fail table; rebuilds re-verified | Ahead; the client-review loop is missing → G-21 |

Cross-cutting:
- **Install and first result.** The references take minutes: installer, email key, no card. We need the Claude app plus sign-in, then a Terminal one-liner (unsigned), then a restart of Premiere. **Behind** → G-16.
- **Platform.** The references support macOS; we have never run there. **Behind (P0)** → G-02.

---

## 4. Gap list

Severity: **P0** a buyer would cancel · **P1** a buyer would notice · **P2** polish.

Phase numbers follow the master plan: 6 = Adobe panels/bridge, 6B = Kalam/Hush/Tidy port, 7 = installer, 8 = review, 9 = live soak/release prep, 10 = guide, 11 = release.

"Tasked" means an existing task already covers it; the suggested task adds the measurable bar.

| ID | Gap | Reference that does it better | Sev | Phase | Suggested task | Evidence |
|---|---|---|---|---|---|---|
| G-01 | Kalam, Hush and Tidy aren't in the product. The upstream code is imported unchanged (`adobe/tools/*/_upstream`), but nothing is ported, packaged or tested on Windows. 3 of our 7 core jobs can't be done today | AutoCut, FireCut (silences + captions inside Premiere, shipping today) | P0 | 6B | Tasked: T6.11–T6.16. Add a gate line: each tool's PRD §11 tests plus a G2 budget run, before 6B closes | strong: https://www.autocut.com/en/pricing ; https://firecut.ai/premiere-pro ; repo `adobe/tools/` |
| G-02 | macOS has never been run (no 2.x or 3.0 path, no MLX, no Mac Premiere/AE), yet 90% of buyers edit on a Mac (G11) | Every reference ships Mac builds (AutoCut Premiere 23–26 Mac/Win; FireCut .pkg) | P0 | 9 | Tasked: G-T12/G-T13 live Mac. Add: no beta without a live-Mac G10 end-to-end report (already the gate; keep it P0) | strong: https://www.autocut.com/en/download/ ; https://learn.firecut.ai/overview-premiere-pro/faq ; master plan §2.3 |
| G-03 | The Premiere panel can't approve or act. Its buttons were "not implemented", and the README says approve is "coming", so a real user must work in chat | AutoCut, FireCut: everything is done from the panel | P0 | 6 | Tasked: Addendum C C1 + T6.2b (intents). Add: the B-T7 usability run (8 tasks, panel only) is a hard gate line for G0 | strong: Addendum C §C0; `whynot-cut/README.md`; https://learn.firecut.ai/overview-premiere-pro/using-firecut |
| G-04 | No measured end-to-end time for the main job (raw clip → plan to approve → built project). The only data point is a "1–2 h" estimate, after which the owner stopped the run. G2 has no budget for it | Submagic (claims about 30 s per 1-min video; under 2 min raw→clip in a review); Descript (45-min podcast edited in <20 min) | P0 | 9 | New: add G2 budgets "raw 90 s clip → plan + preview ready" and "approve → built + QC'd", measured on this PC and on the CI Mac. Profile the agent fan-out, cut serial waits, and show time saved. Re-grade to P1 once measured within budget | medium: `docs/review/2026-10-11/chats-main.md` (11:09Z); weak (vendor claim): https://submagic.co/auto-subtitle-generator/arabic ; medium: https://marcandrews.com/?p=3033 |
| G-05 | Progress is hard to see during long jobs, in chat and in the panel: no ETA, no elapsed time, no "step 4 of 7" during agent work | Raycast animated progress toast with Cancel; Premiere Progress panel; Captions' notify-when-ready | P1 | 6 | Tasked: B4.3 step strip; T3.6 status line. Add: ETA from `reel bench` + stage history; first visible progress ≤ 2 s on every job (the G2 budget) | medium: chats-main.md; strong: https://developers.raycast.com/api-reference/feedback/toast |
| G-06 | No Arabic/Egyptian caption accuracy eval set and no published number. G2 requires a word-accuracy bar per release, and no eval exists in the repo | Submagic claims 99.5% for Arabic; FireCut claims 90%+ (both vendor claims, no method) | P1 | 6B | New: a held-out Egyptian/MSA/mixed clip set (our own rights, under `whynot-test/`) with WER/CER and onset error per release; bar set at Phase 6B; reported in the Phase 9 gate | weak (vendor): https://submagic.co/auto-subtitle-generator/arabic ; https://firecut.ai/pages/languages ; Addendum G §G2 |
| G-07 | Hush speed not measured. The budget is 10 min ≤ 30 s, and Hush's filler pass needs Whisper words, which on CPU would blow the budget | AutoCut (30 min ≈ 80 s; vendor claims 1 h < 30 s), FireCut (30 min ≈ 105 s) | P1 | 6B | New: measure silence-only and silence+filler on 10/30/120-min multitrack; reuse Kalam's cached words (A3 #3); fast silence-only path first, fillers streamed after | weak (competitor test): https://cutback.video/blog/the-best-auto-silence-removal-plugin-for-premiere-pro ; weak (vendor): https://www.autocut.com/en/autocutsilences/ |
| G-08 | Kalam's correction step needs a Claude backend. One-shot `claude -p` on the user's subscription is **off by default** until H14. With no open session and no API key, captions lose the correction, and the editor isn't told why | Submagic, AutoCut: self-contained, nothing else to sign in to | P1 | 6B | New: Kalam shows which backend corrected (session / key / none) and offers one button to open Claude. If uncorrected, it says so on the result and in the report; the faithfulness gate is unchanged | strong (internal): Addendum C §C1.7; Kalam PRD FR-6 |
| G-09 | One-step undo of a whole build is unproven. U3 (one Ctrl+Z reverts all three mutations) is unchecked. Hush and Tidy edits to the editor's own project have backup + restore only on paper | FireCut (sequence copy before every operation + panel Undo), Descript (version history) | P1 | 6 | Tasked partly (T6.16, G10 fault injection). Add: U3 live check; per-tool "undo in reverse order" test on a 60-min timeline; the backup name shown on every destructive screen | strong: `docs/adobe/uxp-parity.md` U3; https://learn.firecut.ai/overview-premiere-pro/using-firecut ; https://help.descript.com/working-in-projects/version-history |
| G-10 | First-use clarity: design round 1 found 20 «مش فاهم» moments (10 MAJOR) — engine, Claude, offline names, a contradictory error state, translated-sounding Arabic. The agency owner said "would not pay yet" | Linear / Raycast (one clear action, explicit errors with Copy error); AutoCut (Arabic RTL UI since July 2026) | P1 | 6 | Tasked: E-D3 round 2 + E-D4. Add: zero MAJOR findings at the Phase 6 gate; every error has one fix button (G2) | strong (internal): `docs/design/reviews/ED3-r1-first-time-editor.md`, `G2-r1-agency-owner.md`; https://www.autocut.com/en/blogs/july-autocut-updates-2026/ |
| G-11 | No command palette and no visible keyboard shortcuts in the panel; G2 requires shortcuts on every screen | Excalibur (Premiere command palette); Linear Cmd+K / Cmd+/; Raycast shortcut beside each action | P1 | 6 | New: Ctrl/Cmd+K palette (AR/EN action names) and Ctrl/Cmd+/ cheat sheet; each action shows its shortcut; open time ≤ 100 ms (Excalibur needs 1–3 s on Windows) | strong: https://knightsoftheeditingtable.com/excalibur ; https://linear.app/enablement/guide/navigating-linear ; https://www.raycast.com/blog/a-fresh-look-and-feel |
| G-12 | Hours saved aren't shown anywhere. At $12k/yr the buyer must see them (G0: "saves them hours on every reel") | FireCut sells on "10× faster / 3–5 h saved"; RedShark measured Premiere TBE at 64 vs 117 min | P1 | 6 | Tasked as an engine data request in `G2-r1-agency-owner.md`. Add: raw duration, estimated manual minutes and actual minutes per reel; weekly total on Home | medium: https://www.redsharknews.com/how-much-time-does-using-premiere-pros-text-based-editing-really-save ; weak: https://firecut.ai/blog/cutting-edit-times-by-10x-with-firecut/ |
| G-13 | The trust lines are missing: that a NEW sequence is made and originals are untouched, whose Claude account is used and what it costs, and that footage stays on the computer. The buyer reads "Claude" as a second paid product | Submagic, AutoCut: one account, one bill. Descript's lost-edit reviews show what happens without trust | P1 | 10 | Tasked in the design decisions. Add: one line per screen in the panel (Phase 6) plus a guide chapter "what leaves your computer" (Phase 10). The executor verifies each fact before shipping the copy | strong (internal): `G2-r1-agency-owner.md`; https://www.trustpilot.com/review/descript.com |
| G-14 | A real 60–90-min episode has never been run end to end, and speaker-follow has never run on a real two-shot | Captions Clips (≤3 h input, 30+ ranked clips); AutoCut Podcast multicam | P1 | 9 | Tasked: T9.2. Add: time it (G-04 budget) and view every reel frame sheet | strong (internal): master plan §2.3; https://captions.ai/help/docs/project/clips |
| G-15 | After Effects motion has only been built with the fallback font (Segoe UI); a brand-font build and the audio-only run have never been done | none (we lead); AE native RTL since 14.2 is the host bar | P1 | 9 | Tasked: T9.2. Add: brand-font install check before `motion-build`, with one fix button | strong (internal): PROGRESS integrator handover; https://community.adobe.com/t5/after-effects-discussions/after-effects-22-5-is-now-live/m-p/13096969/highlight/true |
| G-16 | Install to first result is slow and needs technical steps: Claude app + sign-in, an unsigned Terminal one-liner, a Premiere restart, background model downloads. Under G-T10 the goal is a first reel in < 10 min, not yet proven | AutoCut (installer → email trial key, no card, Window ▸ Extensions); Submagic (3 steps, < 2 min) | P1 | 7 | Tasked: D-T9, E-T1…, G-T10. Add: the stopwatch result in the Phase 7 gate, on Windows and Mac | strong: https://www.autocut.com/en/blogs/how-to-activate-autocut-free-trial/ ; master plan §5.4 |
| G-17 | Caption accuracy and correction on medical/religious terms isn't measured against Premiere's known weakness | Premiere is the weak bar (a medical captioner reports hundreds of errors per hour); nobody does it well | P1 | 6B | New: fold medical and religious terms into the G-06 eval set; report term accuracy separately | medium: https://community.adobe.com/t5/premiere-pro-ideas/auto-transcribed-captions-needs-improvement/idi-p/15217800 |
| G-18 | No visual "pick a look" for captions or the edit style. The style comes only from the client profile and `style.json` | Submagic template gallery + AI Boost toggles; AutoCut caption style presets; Captions AI Edit styles | P2 | 4 | Tasked partly: T4.2 style knobs; Kalam MOGRT gallery (T6.14). Add a preview-still gallery of 3–5 caption looks per client | strong: https://vantaige.io/ai-tool/submagic ; https://knowledge.autocut.com/en/category/autocaptions-uzkb1n/ |
| G-19 | Opportunity: Premiere has no Arabic speech-to-text, but it can import a JSON transcript. We could load our Whisper words into Premiere's Text panel, giving Arabic text-based editing that Adobe itself lacks | Premiere TBE (English only) | P2 | 6 | New: spike importing our transcript into the Text panel; if it works, add it to `ppro-build` | medium: https://community.adobe.com/feature-requests-730/speech-to-text-in-arabic-not-supported-in-premiere-pro-26-1621281 |
| G-20 | No toast system with Undo, no loading skeletons, no optimistic UI | Raycast toasts; Linear undo and optimistic writes | P2 | 6 | Fold into E-D6 polish: one toast component (progress → success/failure, Cancel, Undo, Copy details); never flash an empty list while loading | strong: https://developers.raycast.com/basics/prepare-an-extension-for-store ; https://linear.app/changelog/undo-actions |
| G-21 | No client-review loop (comments → timeline markers → new version) | Frame.io V4 panel in Premiere | P2 | 8 | Decide in Phase 8 (probably backlog). Optional: the handoff notes how to use Frame.io, which is included with Creative Cloud | strong: https://help.frame.io/articles/12833113-adobe-premiere-frame-io-v4-panel-overview-25-6-and-later |
| G-22 | No in-app "What's new" or update cadence yet | Raycast (about one release a week, per-extension update report); Arc (weekly notes, one visual per feature) | P2 | 7 | Tasked: G-T5 / G-T9 beta channel. Add a one-screen "What's new" per beta build | strong: https://www.raycast.com/changelog ; medium: https://buildtogether.substack.com/p/arc-browser-release-notes-review |
| G-23 | Automatic camera switching for multicam podcasts isn't in 3.0 (raw multicam is backlog; Tidy syncs only) | AutoCut Podcast / Angles; FireCut podcast switching | P2 | 8 | Phase 8 confirms it stays in the backlog; the guide says so | strong: https://www.autocut.com/en/blogs/july-autocut-updates-2026/ |
| G-24 | Risk: performance on long timelines after thousands of Hush cuts | FireCut user lag report; AutoCut admits long-timeline slowdowns (both show the risk; neither solves it) | P2 | 9 | Soak: a 60-min, 3-track Hush cut, then scrubbing and playback in Premiere, timed; checked in the G10 soak | weak: https://community.adobe.com/t5/premiere-pro-discussions/using-firecut-plugin-to-cut-silence-and-after-i-do-my-premiere-pro-is-unusably-laggy/m-p/14765054/highlight/true |

**Totals:**

| Severity | Count | Gaps |
|---|---|---|
| P0 | 4 | G-01–G-04 |
| P1 | 13 | G-05–G-17 |
| P2 | 7 | G-18–G-24 |

**Where we're at parity or better** (not gaps, so keep them true):
- Arabic STT, captions and RTL in Premiere: Adobe, Descript and FireCut fall short here.
- A native, branded Premiere and AE project as the output.
- Automated QC from Premiere's own frames.
- Resumable long jobs.
- Never touching the originals.
- Project cleanup (Tidy, once ported).
- Medical/religious claim review.
- Platform-checked publish copy.
- No credit burn or opaque billing: Descript's top complaint.

---

## 5. Speed budgets (G2) and reference numbers

### 5.1 G2 budgets and the nearest reference figures

| G2 budget | Our status | Reference numbers (time to result) |
|---|---|---|
| Panel open to usable ≤ 1.5 s | Not measured (panel-ui built; screens paused for mockups) | Excalibur search bar takes 1–3 s to open on Windows (https://manuscript.knightsoftheeditingtable.com/llms-full.txt). Raycast "<50 ms" launch is third-party, weak (https://blakecrosley.com/guides/design/raycast) |
| UI response ≤ 100 ms | Not measured | Linear: local-first, optimistic writes; "<50 ms pages" is third-party, weak (https://byteiota.com/local-first-architecture-linears-50ms-page-load-secret/) |
| First visible progress on any job ≤ 2 s | Not measured; low visibility was observed in the field (G-05) | Raycast animated toast appears straight away (pattern, no number). Premiere shows background analysis in the Progress panel |
| Kalam: 60 s clip ≤ real time on GPU | Not built. The pipeline's Whisper large-v3 runs about 10× real time on an RTX 4060 (one reel: 20 s on GPU vs 1 min 50 s on CPU; `chats-main.md`); a 35-min episode took about 4 min | Submagic claims about 30 s per 1-min video (vendor, weak). Premiere transcribed a 20-min clip in 6 min (RedShark 2023, medium). Frame.io transcripts take "a few minutes" (vendor). Captions Clips: older docs said "up to an hour" |
| Hush: 10-min track ≤ 30 s | Not built or measured | AutoCut claims 1 h < 30 s (vendor). Competitor test: AutoCut 3 min → 60 s, 30 min → 80 s, 120 min on 3 tracks → about 15 min; FireCut 3 min → 30 s, 30 min → 105 s, 120 min failed (cutback.video, weak). The 30-min figures imply about 27–35 s per 10 min, right at our budget |

### 5.2 Other time-to-result numbers

| Job | Reference figure | Ours |
|---|---|---|
| Talking-head edit, end to end | Descript: 45-min podcast in < 20 min (reviewer). Premiere TBE: 64 vs 117 min (RedShark). Submagic: < 2 min raw → clip (review) | **Unmeasured**; "1–2 h" estimate observed once (G-04) |
| Podcast → reels | Captions Clips: ≤ 3 h input, notifies when ready (older docs: up to 1 h) | Transcription of a 35-min episode took about 4 min; the analysis fans out to moment-scouts (about 10-min chunks in parallel); the whole run is unmeasured (G-14) |
| Auto reframe | Premiere Auto Reframe placed about 156 keyframes in < 10 s (https://www.streamingmediaglobal.com/Articles/Editorial/Featured-Articles/Review-Adobe-Premiere-Pro-Auto-Reframe-135118.aspx) | Per-shot reframe + shot detection adds about 5 s of analysis per reel-minute (`chats-podcast-motion.md`) |
| Intake scan | — | Overlay scan about 1.9 s per minute of video (about 2 min for 60 min; 300 s cap) (CHANGELOG G65) |
| Install → first result | AutoCut: installer + emailed trial key, minutes (no number). Submagic: 3 steps | Target < 10 min to a first reel (G-T10), < 15 min of attention (D-T9). Not yet measured (G-16) |

**Proposed new G2 budgets** (G-04). Phase 9 should settle the exact numbers.

| Measure | Proposed budget |
|---|---|
| A 90 s raw clip → plan + preview ready to approve, on an RTX-class PC and an M-series Mac | ≤ 15 min |
| Approve → built + QC-verified Premiere project | ≤ 10 min |
| A 60-min episode → reels plan | ≤ 20 min |
| Any agent stage | shows progress within 2 s and an ETA within 30 s |

---

*Sources were read on 2026-10-14 by read-only research passes. Any figure marked as a vendor claim or a competitor-run test is weak evidence and should be re-checked before it is quoted to a customer.*
