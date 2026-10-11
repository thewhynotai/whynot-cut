# WhyNot Cut — chat-history extraction: podcast mode, motion mode, integrator

Sources read in full: the three digests in `scratchpad/digests/` (9301b09f, e15d7086, 2d167d3a). The digest
generator cuts every message at 6,000 characters, so I recovered the cut parts from the original transcripts
(`~/.claude/projects/D--0-Work-0-...-Editing-Plugin/<id>.jsonl`). The recovered parts were the 2.1.0 review report,
the 2.1.0 final report, both compaction summaries, the 2.2.0 final report, the AskUserQuestion options and answers,
the integrator's helper-agent briefs and its 12:20 status reply. I also read the hand-over notes these sessions left in
`C:\Users\LOQ\AppData\Roaming\Claude\side-session-notes\local_520a891b-...\`. Those are
`motion-2.2.0-ledger.md`, `motion-from-audio-phase3.md` and `whynot-cut-2.1.1-podcast-minors.md`. I also read
`Editing Plugin\round4-gaps.md`, which holds the G62–G69 text. Times are UTC; Cairo time is UTC+3.

Session map (the peer names used in cross-session messages):
- 9301b09f = "منصة بودكاست متعددة الوظائف" ("multi-function podcast platform"), id local_520a891b. It designed and
  built podcast mode (2.1.0), then spawned Phase 3 and 2.1.1.
- e15d7086 = "Phase 3 spec: motion/animation from audio in AE", id local_982c28e5. It designed and built motion mode
  (2.2.0).
- 2d167d3a = "Running chat management", id local_74c8d6b7. This is the integrator: the only session that merges, tags
  and packages.
- Peers mentioned but not read here:
  - "Reel editing plugin enhancement" (local_b767610e): field tests, G46–G61, the 4:5/range code, and the real Dr
    Sherin EP02 run.
  - "WhyNot Cut 2.1.1: fix podcast-mode deferred minors" (local_7005d4ff).
  - "Client-level reference style guide + staleness check" (local_5477a071).
  - "WhyNot Cut 2.2.1: fix the 2.2.0 deferred minors" (local_de569d4d).
  - "Whynot cut start" (local_415983e0): onboarding/setup.
  - "Claude plugin comprehensive review and plan" (local_263cabbf): the 3.0 master-plan session.

Version timeline seen in these chats:
- 2.0.0 is the baseline. The design text cites "68 existing tests"; by implementation time the suite was about 188–190.
- 2.1.0: podcast mode. 197 OK, 4 skipped. Commit 1fdcb7c, fast-forwarded to main and tagged at about 07:10.
  The zip has 172 files.
- 2.1.1: the podcast minors. dad3f9d, 212 OK.
- feat/client-ref-style was merged next: e090994, 231 OK.
- 2.2.0: motion mode + client-level reference style. 39026fb, 350 OK, tagged, `whynot-cut-2.2.0.zip` built.
- 2.2.1 (motion minors + round-4 gaps G62–G69) was still in progress when these chats end, about 12:20 UTC on 11 Oct.

---

## SESSION 1 — 9301b09f: podcast mode design + build (2.1.0), then spawning Phase 3 / 2.1.1

**What it was.** The user started it with `/superpowers:brainstorming`. The session ran 2026-10-10 23:21 → 2026-10-11
12:08 UTC. The flow was:
1. Brainstorming: architectural path, AskUserQuestion, three alternatives, a design in 7 sections.
2. Spec and plan: `docs/superpowers/specs/2026-10-11-podcast-mode-design.md` and
   `docs/superpowers/plans/2026-10-11-podcast-mode.md` (15 tasks plus a Review Focus).
3. Inline execution with TDD and a ledger on branch `feat/podcast-mode`, while coordinating with the "Reel editing
   plugin enhancement" session in the same checkout.
4. An independent whole-branch review, then fixes.
5. The 2.1.0 zip and the final report in Arabic.
6. A compaction, then a merge to main tagged v2.1.0.
7. Proposal cards for Phase 3 (AE motion) and 2.1.1 (deferred minors). The user started both and relayed "don't stop"
   to them.
8. The session watched them and handed integration to "Running chat management".
9. Final line: 2.2.0 is merged and zipped, and 2.2.1 is in progress.

### 1. User requirements & wishes
- **Original ask:**
  - «دلوقتي انا نفس البلاجن دي بس بدل ما اعمل فيديوهات بيبقي عندي بودكاست»: the same plugin, but the input is a podcast
    instead of single videos.
  - «لازم اطلع الترانسكربشن ويحلل الكونتكست والسياق بتاعه»: it must produce the transcript and analyse the context.
  - «ويطلع منها ريلز بلان بالتايم كود وبنوع المحتوي هل هو ستوريتلينز ولا دراما ولا قصه نجاح»: a reels plan with
    timecodes and a content type per reel (storytelling, drama, success story…).
  - «و بعد كده بيكمل كل الخطوات عادي»: then it continues through all the normal pipeline steps.
  - «وانه احيانا يعمل فيديوهات موشن وانيميشن من اولها لاخرها هيحط الصوت بس والكلام عن طريقه فهمه للسياق هيعمل دا»:
    sometimes a full motion/animation video from start to end. The input is audio only; it builds the visuals from its
    understanding of the context.
  - «ف كله في مكان واحد ولا اعمل كل واحده منفصله»: should it all be in one place or separate?
  - «خصوصا اني عاوز اعملها بلاجن لبريمير وافترايفكت»: "I want it as a plugin for Premiere AND After Effects."
  - «وبرضو يطلع الكابشن والكونتنت والديسكربشن والشابترز والتاجز وكل حاجات اليوتيوب»: also captions, content,
    description, chapters, tags, "all the YouTube things".
- **Follow-up question:** «كله في بلاجن واحده ولا اخد اللي محتاحه من البلاجن الحاليه واعمل واحده للبودكاست فقط»: one
  plugin, or take what's needed from the current plugin and make a podcast-only one?
- **AskUserQuestion answers:**
  - "Adobe plugin" meaning → «Claude هو العقل، ويطلّع مشاريع Adobe (Recommended)»: Claude is the brain and outputs Adobe
    projects through bridge panels. The user did not choose «Panel جوه Premiere/AE فيه زراير», a button panel inside
    Premiere/AE needing an API key and per-use cost. They also did not choose «الاتنين: Claude دلوقتي والـ Panel
    بعدين» ("both: Claude now, panel later").
  - Input shape → «الحلقة بعد المونتاج (ملف واحد 16:9)»: the finished, edited episode as one 16:9 file. Not chosen:
    raw multicam with a mic per person, one wide raw camera, or "varies, must support all".
  - Who picks reels → «المونتير يختار من المرشحين (Recommended)»: the editor picks from candidates (8–15, each with
    timecode, type, hook, score). Not chosen: "auto-make top N", or "by preference (ask|auto)".
  - What content type changes → all four: labeling in the plan, pacing/cuts (pause removal), music/SFX (licensed client
    library only), and graphics/captions/copy tone.
  - Publish package → the full YouTube episode package (several titles, description, chapters, tags, SRT), plus a
    caption and hashtags per reel (IG/TikTok/Shorts plus a Short title), plus the episode thumbnail. The user did not
    choose «رفع مباشر على يوتيوب كـ Draft» (direct upload to YouTube as a draft via OAuth).
- **Approvals:** «موافق على A، كمّل» approved Approach A (a reel is a window of the original episode file).
- **Working style, stated repeatedly:**
  - «قولي احسن حاجه وكمل»: "tell me the best option and continue".
  - «كمل» (×2).
  - «كمل ومتوقفش انت فهمت كل حاجه - كمل للاخر ومتوقفش لحد ما تخلص كل حاجه»: "continue, don't stop, you understood
    everything; go to the end until everything is done". This waived the spec, plan and execution-method gates.
  - After compaction: "go with the best options don't stop".
  - "go with the best options don't stop based on the runnging chat when you will strart / go with you recommendation
    in the chat until the final result", which was relayed to the Phase 3 and 2.1.1 sessions.
  - "go with the best options don't stop untill you finish everyting".
- **Restart:** "I restarted After Effects and Premiere, go on", after being asked to restart for bridge 3.1.0.
- **Implied wishes, stated by the assistant and accepted:**
  - Premiere stays the real deliverable, and the editor can adjust framing and in/out.
  - Nothing is uploaded anywhere.
  - Names and links come only from the episode sheet.
  - Medical claims still need approval.

### 2. User complaints / dissatisfaction
- No explicit complaint in this session.
- The implicit friction was approval stops. The user waived the gates repeatedly («كمل ومتوقفش…», "don't stop") and
  wants decide-and-continue. Merges, pushes, destructive actions and Adobe security settings stayed the user's call.

### 3. Decisions made (with reasons)
- **One plugin with modes, not a separate podcast plugin.** Reasons given:
  - The modes share the costly parts: Whisper/transcript, brand profile, Arabic RTL rendering, the Adobe bridge, QC,
    the client folder and the gates.
  - Two plugins would mean two engines, two setups, and two bridge panels fighting over one job queue (or changed
    IDs). Every bug fix would be needed twice, including the Windows fixes for Premiere frames, locked stills and
    HarfBuzz.
  - After Gate 0 a podcast reel is just the normal pipeline.
  - If a podcast-only product is ever sold, `package.py` can emit a second zip with fewer skills from the same code.
- **Build order (phases):**
  1. Podcast → reels plan, with 9:16 reframe.
  2. YouTube/social publish package (merged into phase 1).
  3. Full motion video in AE (its own spec later).
- **Approach A — "virtual reel":**
  - Each reel is a window `source in/out` of the original episode, named like `EP12_R03`. The original file is never
    touched.
  - The transcript is sliced from the episode transcript, so there is no Whisper re-run.
  - The Premiere project uses the original episode in a 9:16 sequence, with reframe as Position/Scale keyframes, and
    handles so the editor can extend the in/out.
  - Rejected: B (pre-cut 9:16 files: re-encode, burned-in crop, no handles, intermediate media) and C (one Premiere
    project per episode with a sequence per reel: a rebuild of one reel risks manual edits in the others).
- **Folders:**
  - Episodes go in `data/Episodes/` (EP12.mp4 plus an optional EP12.md "episode sheet"). An explicit folder was
    chosen over auto-detection for predictability; `reel inbox` warns when a long 16:9 file sits in `data/Raw`.
  - Output goes to `output/episodes/EP12/`.
  - Each picked reel becomes `output/projects/EP12_R03/` with `00_inputs/source.json` (episode, offset, duration).
- **Episode sheet (optional YAML):** show, episode, host, guest «الاسم — الصفة», links, sponsor, avoid. It is the only
  source of names and links in the copy; anything missing is written as "unavailable", never invented.
- **Burned-in subs/logo:**
  - The intake-inspector checks 6 frames for burned subs, logo or lower thirds.
  - The preferred fix is a clean export requested by name. The fallback is a solid caption bar over the old subs, plus
    a warning.
  - Round 4 later showed 6 frames is too few (G65).
- **Transcription:**
  - The whole episode is transcribed once, in 10-minute chunks with checkpoints, so it resumes after a stop.
  - VAD is on only for episodes, so intro music doesn't produce fake words.
  - `reel doctor` warns that CPU transcription is slow and suggests `large-v3-turbo`.
  - Language is detected once and stored in plan.json; an explicit new language invalidates the checkpoints.
  - GPU→CPU retry happens at the first inference.
- **Speakers:**
  - Roles (host/guest) are inferred by the analyst from context and the sheet, and marked "inferred".
  - **No pyannote**: it needs torch (about 2 GB) and an HF token. Deferred.
- **Analysis:**
  - A new `episode-analyst` agent builds the topic map, which also becomes the YouTube chapters.
  - It fans out to `moment-scout` subagents (about 10 minutes each with 1 minute of overlap, in parallel), then
    dedupes, classifies and scores.
  - Each candidate has: ID and in/out; type and secondary type; hook (first spoken sentence plus suggested on-screen
    hook); why it works; a score out of 10; needs-context flag; risks.
- **Seven default content types:** storytelling, drama/confrontation, success story, advice/info, bold opinion, human
  moment, comedy. Clients can add or remove types.
- **Engine validation (`reel reels-plan`):**
  - Every quote must exist in the transcript at that time.
  - In/out snap to sentence boundaries.
  - Duration 30–90 s (a preference).
  - No large overlaps.
  - About one candidate per 5–8 minutes.
  - Each candidate gets a frame plus a fast low-quality 9:16 preview (ffmpeg).
- **Gate 0:**
  - `reel reels-select --pick R01,R03,R07 --adjust R03:in=00:12:04 --by editor`.
  - Only the editor picks. A hook (guard.py) blocks subagents from recording a pick, and words inside the transcript or
    files never count as a pick.
  - Adding reels later works; removing a reel never deletes its project unless asked.
  - Transcript corrections after picking re-slice the affected reels, and the fingerprint system cancels old approvals.
  - Picked reels then run in parallel, followed by one combined Gate 1, then build and QC per reel.
- **Recipes (`recipes.json`), layered like profiles:**
  - Hard numbers the engine applies: pause threshold, max zoom, graphics per 30 s, music level.
  - Guidance for the story-editor.
  - Per type: storytelling removes pauses ≥350 ms; drama ≥600 ms (dramatic pauses kept); success ≥300 ms; advice
    ≥250 ms; bold ≥250 ms; human moment ≥800 ms; comedy tight but keeps the pause before the punchline.
  - Camera, captions, graphics, SFX, music mood and post tone are set per type.
  - Two new templates: `stat_card` (big number plus a line) and `context_card` (one opening context line).
  - Priority order: the editor's fixed decisions in `notes.md` beat the recipe. The primary type drives the edit and the
    secondary type affects post tone only. The story-editor may override the recipe only with a written reason shown at
    Gate 1. Recipes never lift medical rules.
- **Music:** no generated or unlicensed music. The recipe sets the mood; a track is picked from tagged
  `data/Music`/`music.json`. Otherwise it stays "Needs you: music".
- **Per-shot reframe:**
  - ffmpeg scene cuts inside the reel window, plus OpenCV faces on frames per shot.
  - One face → crop on the face, eyes in the upper third, the caption off the chin.
  - No face → shown whole on a brand background (as cutaways are now).
  - Two or more faces (wide) → **camera follows the speaker** with a 1.5 s minimum hold.
  - Seating comes from `layout.json`, written by the intake-inspector.
  - When unsure who speaks, the shot is shown whole with a warning.
  - **Split-screen rejected as the default**: it is untested via the bridge and could become a recipe option later.
  - Implemented as an `AUTO_SHOT` base layer in the camera timeline, with story-editor punch-ins and jump masks layered
    on top. This was the main code change in `plan.py`.
  - Live tuning: sampling at 2 fps continuously, splitting by face presence, and a histogram "speaker-like" fallback
    (≥0.55) for faces Haar misses.
- **Single source window:** every media reader (preflight, audio, previews, preview MP4, XML) reads `source.json`.
  Plain clips have offset 0, so behaviour is unchanged.
- **Audio for episode reels** is "light" by default: no heavy denoise unless measured, social loudness, recipe pauses,
  and the no-word-lost proof stays.
- **Premiere:**
  - One project per reel (`EP12_R03_<PREFIX>_EDIT.prproj`) in a 1080×1920 sequence, using the original episode file
    with handles.
  - The 10 existing read-back checks plus 2 new ones: the first in-point equals the reel start, and the reframe
    keyframes match the plan.
- **QC (frame-inspector) adds three checks:** the face is inside the crop, no burned subtitle fragments show, and the
  person on screen is the transcript's speaker.
- **Publish package:**
  - A new `publish-writer` agent.
  - The episode package is produced right after analysis, in parallel with Gate 0. Each reel's post is written after
    its Gate 1 and rewritten after a revise.
  - Output: `output/episodes/EP12/publish/` with youtube.md (5 titles, description, chapters, tags), chapters.txt,
    tags.txt, EP12.srt, thumbnail/ (6 candidate frames plus 3 PNG designs in client fonts and colours; a PSD only when
    `thumbnail_psd: true`), reels/EP12_R03.md and publish.json.
  - Description order: 2-line hook, summary, guest intro, chapters, links/sponsor, CTA, 3 hashtags.
  - `reel publish-check`:
    - YouTube limits: title ≤100, description ≤5000, tags ≤500 total, chapters start at 00:00, at least 3, each ≥10 s,
      in order.
    - Limits live in `platform-limits.json`, so platform changes need no code edit.
    - Quotes must be in the transcript; links must be in the sheet.
    - For medical clients, claims in titles/captions go to approval.
    - The SRT is checked.
  - **Nothing is uploaded.**
- **Edge cases designed:**
  - A 2-hour episode on CPU: doctor estimates the time; chunk checkpoints.
  - Fake words in intro music: VAD plus a review list.
  - A mid-thought start: snap to the sentence and mark needs-context, which gets a context_card.
  - Burned subs: covered above.
  - Ambiguous wide shot: shown whole plus a warning.
  - Audio-only podcast (still image or waveform): shown whole, redirected to motion mode.
  - VFR (Zoom/Riverside): preflight detects it and asks for a CFR export, else a CFR intermediate in `output/`.
  - Episode file changed after picking: the hash refuses it.
  - «موافق» spoken inside the transcript is never an approval.
  - Non-medical client: medical-reviewer is off, but on-screen-text-in-transcript checks stay.
- **Test plan:** unit tests, regression of the existing suite, a synthetic 3-minute 16:9 "episode" (close-ups, a
  2-face hstack wide, a no-face shot), an analyst eval, and a live run on the user's machine.
- **Out of scope for 2.1:** AE motion mode, YouTube upload, split-screen, pyannote, a button panel inside Adobe, raw
  multicam.
- **Implementation rulings ("decisions I took for you", with cost if wrong):**
  1. Branch `feat/podcast-mode` in the same folder; main stayed at 2.0.0 until merged.
  2. Reused the other session's range mechanism (`source.json`, `common.source_range()`) instead of a second one.
  3. Podcast commands live in `lib/podcast_cli.py`; `cli.py` was touched in only 4 lines.
  4. `transcribe.py` untouched; decode duplicated in `episode.py`.
  5. `run_chunk` returns a dict; `chunk_ms` hook.
  6. Chunk-boundary search clamped to a quarter of a chunk.
  7. Speaker turns stored as ms ints on the reel clock.
  8. Hard duration limits re-checked only for adjusted windows.
  9. An episode-file change is refused only in preflight/plan (extended in 2.1.1).
  10. Dropped the 46-minute stub test, since tick math is absolute.
  11. Shot detection at 2 fps with presence runs (about +5 s of analysis per reel-minute).
  12. Added `remove_pauses.protect`, at the other session's request.
  13. `reel music` is client-level.
  14. `stat_card` value is white with a brand-colour bar, because the olive brand colour was unreadable.
  15. Thumbnail: zoom ×1.35, face in a third, text on the right.
  16. `episode-next` shows only each reel's status.
  17. Zip built last.
  18. Live-test picks and approvals recorded as "delegated".
  19. The other session's Snapshot commits (4:5/range) were **not** independently reviewed.
  20. Agent/skill prose reviewed only structurally.
  21. The whole episode's audio is held in RAM (about 350 MB per 90 minutes).
  22. A zoom inside a shown-whole card is dropped silently (old behaviour).
  23. Thumbnail PSD left out of 2.1 (PNG only).
- **Post-compaction:**
  - Chose option 1 (fast-forward merge to main, tag v2.1.0), because there is no git remote.
  - Proposed Phase 3 and 2.1.1 as separate sessions.
  - Of the 13 deferred minors, 11 went to 2.1.1. The mixed commit 63201e1 is history only, and caption contrast was
    already fixed by the other session's caption boxes.
  - Merge order decided: 2.1.1 first, then Phase 3, then one 2.2.0 zip. Integration was then handed to "Running chat
    management" to avoid two sessions merging into main.

### 4. Verified working (live, with evidence)
- **GPU Whisper on RTX 4060** after cuBLAS was installed (by the other session): about 90 Arabic words with corrections
  and flagged words.
- **Full live run on test client `whynot-test/PODCAST-TEST`** (a short episode cut from the Dr Sherin EP02_R02 example
  plus a TEST sheet):
  - reels-plan (2 candidates), previews, reels-select (delegated).
  - Per-shot preflight: face → card shown whole → face, matching what was seen by eye.
  - audio-clean with the storytelling recipe (350/100): 6 pauses removed, no word lost.
  - plan, previews, preview-video.
- **Premiere:** `ppro-build` PRPROJ_BUILT with 11/11 checks; `ppro-frames` 17/17 frames viewed; verify pass; QC ok,
  including both new reel checks; `publish-check` ok; thumbnails rendered and viewed.
- **Live-run issues found and fixed:**
  - Captions/statement sat over the burned-in card → `cutaway_bands` plus a plan warning.
  - An old engine bug: a shared FreeType face size shrank Arabic text when two sizes of one font sat in one graphic →
    `hb_text.render_line` sets the size each time.
  - stat_card contrast.
  - Thumbnail text overlapping the face.
  - "+0 jump-cut zooms" count → `masked` flag.
- **Independent whole-branch review:** 0 Critical, 4 Important, 13 Minor (see 5).
- **Final suite:** 197 OK, 4 skipped. Zip `whynot-cut-2.1.0.zip`: 172 files, no docs.
- **Peer fixes G60 and G61, live-verified by that session:**
  - The R05 signature equals the file after the next build.
  - Frames exported alternately R02→R05→R02, all ok.
  - Both reels QC ok and READY_FOR_HUMAN_EDITOR.
  - Suite 190 OK.
- **Merge:** main at 2.1.1 checked by this session: 212 OK, 4 skipped.

### 5. Failures, bugs, gaps
- **Errors hit during the build, all fixed:**
  - A CLI test mutated a shared fixture.
  - Chunk-boundary drift (±20 s search was wider than the 8 s test chunk).
  - `KeyError 'generated'/'warnings'` in the md writer.
  - The duration check ran on unadjusted picks.
  - A 20 s fixture vs `hard_min` → client override `podcast.json`.
  - Real footage: a dissolve to a card with no hard cut → split by face presence.
  - Haar missed a looking-down face → histogram fallback.
  - The stat_card size bug, poor contrast, and the thumbnail overlap.
  - QC sync check failed for range reels in the other session's `qc.py` (they fixed it).
  - Heredoc quoting broke the shell; commit-message backticks caused a harmless shell substitution.
- **2.1.0 review "Important" items, all fixed RED→GREEN before release:**
  1. The new QC check "Reel starts at its episode in-point" falsely failed when a leading pause was removed. It now
     compares `in_ms + main_segments[0].src_in_ms`.
  2. A scalar `avoid: السياسة` in the sheet silently disabled the avoid check (it iterated characters). Now coerced to
     a list.
  3. `reel transcribe --force` on an episode reel re-ran Whisper and lost the episode corrections. It now refuses and
     points to `reels-select --resync`, or re-slices when the transcript is missing.
  4. Symbol-only names (`###.mp4`) all became `VIDEO`, and duplicate ids had no warning. Now hash ids plus a warning.
- **Also fixed from the review's minors:** overlapping speaker turns, the guard missing the `python -B cli.py` form,
  and the language change on resume.
- **13 deferred minors from 2.1.0** (11 fixed in 2.1.1; see the extra note at the end of this section):
  - `plan.norm` didn't fold Arabic-Indic digits ٠-٩ or ؤ/ئ.
  - A bare `example.co.uk` was truncated.
  - The `pause_params` source was mislabelled.
  - Thumbnail candidates decoded the whole episode at full resolution (slow).
  - The thumbnail `highlight` was ignored and designs beyond 3 were dropped silently.
  - The plan's shot block used the first preflight file instead of the main footage.
  - Straight "…" counted as quotes.
  - `episode-next` didn't flag a plan re-validated after picking.
  - `inbox` probed every Raw clip on every call.
  - `window_stale` was enforced only in preflight/plan.
  - Commit 63201e1 mixed in the other session's 4:5 code (history only).
  - ResourceWarnings in the tests.
  - Caption contrast over the blurred fill (the other session added boxes; likely its G59).
- **Peer gaps reported into this session:**
  - **G60:** building one reel made Premiere save another open reel's project, so its next rebuild was refused as
    EDITOR_CHANGES_PRESENT with no human involved. Premiere auto-save can do the same. Fixed:
    `verify.prproj_signature`, the SHA-1 of the gunzipped XML minus save-time bookkeeping (BuildVersion.Modified,
    NextID, MasterClipChangeVersion, empty ID nodes, EditLine). `editor_modified()` now requires a newer mtime and a
    changed signature. The `content_signature` is stored in `ppro-build-result.json`.
  - **G61:** `ppro-frames` looked for the sequence only in the active project ("TypeError: null is not an object, line
    337"). Fixed: `NHPP.activateProject(path)` plus `project_path` passed to export_frames.
  - **G59:** fixed by the peer in the same batch. Its exact text isn't in this digest; the touched file list suggests
    caption boxes over AUTO_CUTAWAY fills (`render_captions on_fill`).
- **2.1.1 notes (hand-over file):**
  - The fresh review's Important #1 was fixed: ئو→ؤو before folding (مسئول = مسؤول).
  - Deferred there: `--resync` doesn't record the current plan fingerprint, so the episode-next flag needs a re-pick to
    clear; the hygiene test is a canary for third-party warnings; `main.co.ts` still reads as a site; the README "72
    tests" count is stale.

### 6. Open / deferred / unverified at the end
- **Not verified:**
  - A real full episode of 60–90 minutes.
  - Speaker-follow on a real two-person wide shot (the sample had one person).
  - The quality of plans and copy when the agents write them themselves. In the live test, Claude played the analyst
    and publish-writer by hand.
  - macOS.
- **Needs the user:**
  - Install WhyNot Cut instead of reel-editor 1.0.7 in the desktop app.
  - Run the first real episode with its sheet.
  - Real picks must come from the editor; test picks were recorded "delegated".
- **Not reviewed:** the other session's 4:5/range/sharpen "Snapshot" code (ruling 19). The reviewer recommended landing
  its own review before release.
- **Cost-if-wrong items still standing:** episode audio in RAM (pressure on 3-hour episodes); a zoom inside a
  shown-whole card silently dropped; agent prose needing tuning on the first real episode; the thumbnail PSD not built.
- **Handed to the integrator at 08:20:** a real 60–90 minute episode, speaker-follow on a real two-shot, macOS, and the
  plugin swap. Nobody owns these.

### 7. Environment facts
- **Repo:** `D:\0 Work\0 Pegasus IMC Agency\00 TWN\0 TWN AI\Editing Plugin\whynot-cut-marketplace`. The plugin is in
  `whynot-cut/`, the engine in `whynot-cut/engine/reel`, the CLI is `reel`. Local git, **no remote**.
- **Test command:** `~/.whynot-cut/venv/Scripts/python.exe -m unittest discover -s tests` from `whynot-cut/`, with
  `PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1`.
  - System python silently skips the 5 HarfBuzz/FreeType tests; "9 skipped" means the wrong interpreter.
  - The expected 4 skips are the brand font, 2 Whisper integration tests, and CoreText (macOS).
- **Packaging:** `python package.py` in the marketplace writes `../whynot-cut-<ver>.zip`. It skips `docs/` and
  `.superpowers/` (and `tools/` from 2.2.0). Bump the version in `whynot-cut/.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json` and CHANGELOG.
- **Premiere/XML:** FCP7 XML xmeml v4; Premiere ticks TPS = 254016000000; the in-point formula is
  `round((src_in_ms+offset_ms)*TPS/1000)`.
- **Range reels:** ffmpeg `-ss/-t` go before `-i` via `range_input_args()`.
- **Hooks:** `guard.py` (PreToolUse) and `session_context.py`.
- **Two Claude sessions shared one checkout.** They coordinated file by file over SendMessage ("bridge free"
  handshakes) and committed the peer's work as "Snapshot" commits.
- **Premiere can save other open projects during a build,** and auto-save can too (G60). Several open projects break
  frame export unless the project is activated (G61).
- **Engine bug class:** a shared FreeType face size between renders.
- **Live-test client** `whynot-test/PODCAST-TEST`, and the finished field-test projects
  `whynot-test/Dr Sherin Helmy` R02/R05, which must not be opened or saved.

### 8. Ideas floated but never implemented
- A button panel inside Premiere/AE, needing an API key and per-use cost. Declined for now; "Claude now, panel later"
  was offered. Note that the 3.0 master plan now mentions a "native Premiere/AE plugin".
- Raw multicam with per-mic sync and angle selection by speaker; one wide raw camera; auto-detecting the input type.
- Auto-making the top N reels, or picking by preference (`approval: ask|auto`).
- Direct YouTube upload as a draft (OAuth), "a separate phase later".
- pyannote diarization.
- Split-screen layout (host top, guest bottom) as a recipe option.
- A podcast-only product zip from the same code via `package.py`.
- A thumbnail PSD via `ps-build` (`thumbnail_psd: true`).
- A VFR→CFR intermediate file (designed; the digest only confirms the VFR warning).
- A solid caption bar over burned subs (designed; implementation not confirmed in the digest).
- An analyst eval on a hand-labelled real transcript (evals `podcast-reels-plan` and `publish-package` were added; a
  real labelled eval isn't confirmed).
- One shared `window_stale` call in every stage (partly done in 2.1.1 via `refuse_stale_window` in more commands).

---

## SESSION 2 — e15d7086: Phase 3, motion/animation from audio in After Effects (2.2.0), then 2.2.1 live checks

**What it was.** A child session started from the podcast session's proposal card. It ran 2026-10-11 07:12 → 12:08 UTC.
- The original brief was to design only (spec plus plan, no code).
- At 07:38 the user's relayed approval expanded the scope to the final result: implement, review, and live-verify in
  AE.
- It wrote the spec `docs/superpowers/specs/2026-10-11-motion-from-audio-design.md` and the 20-task plan
  `docs/superpowers/plans/2026-10-11-motion-from-audio.md`.
- It executed inline with TDD and a ledger in worktree `whynot-cut-marketplace-motion` on branch `feat/ae-motion`
  (renamed from `feat/motion-from-audio`).
- It installed bridge 3.1.0, asked for an app restart, ran the live AE gate, and ran a live end-to-end motion reel.
- A fresh reviewer graded the branch, the findings were fixed, and the branch was rebased onto main (e090994). The
  integrator merged it as 2.2.0 (39026fb).
- It then ran the 2.2.1 live AE checks (an Arabic-named client folder), which found two bugs.
- It ended waiting for the 2.2.1 session's review.

### 1. User requirements & wishes
- **Inherited:**
  - Full motion-graphics/animation videos from an episode's **audio only** (voice plus Claude's understanding of the
    context), as native AE projects that Claude Code builds.
  - One plugin with modes; Claude is the brain and builds Premiere AND AE projects.
  - Content type drives labeling, pacing, music/SFX and graphics/copy tone.
- **Questions the spec had to settle:** the input unit; story beats → scenes via the recipes; the visual vocabulary
  (kinetic Arabic RTL typography, icons, stat cards, illustrated scenes); licensed assets only (`assets/` and `data/`
  are read-only); the AE build path; Arabic in AE; QC from AE frames; integration with `episode-next` and the publish
  package.
- **User's relayed words:** "go with the best options don't stop based on the runnging chat when you will strart / go
  with you recommendation in the chat until the final result".
  - Meaning: decide and continue, with the spec, plan and execution-method gates waived; scope is the final result.
  - The only stops: never write Adobe security preferences (e.g. AE's "Allow Scripts to Write Files and Access
    Network", PlayerDebugMode); no destructive actions; `assets/` and `data/` are read-only; message "Reel editing
    plugin enhancement" before using the Premiere bridge.
  - Use version 2.2.0, no zip, no merge or push.
  - Final message format: Verified / Not verified / Needs you, plus exhaustive Rulings with cost, plus deferred minors.
- **Later relayed words** (via the integrator): «خليه يكمل و يخلص كل حاجه لحد ما تقفل النتيجة النهائية وكل حاجه
  اتصلحت»: "let it continue and finish everything until the final result is closed and everything is fixed". This made
  the 2.2.0 deferred minors go into 2.2.1 immediately.
- **Direct user messages here:** "Try again" (after a usage-limit stop), "tell me when the 2.2.1 session finishes",
  "tell me when the review finishes". The `[Image …1080x3060]` turns are frame contact sheets, not user text.

### 2. User complaints / dissatisfaction
- None explicit.
- A session/usage limit ("You've hit your session limit · resets 2:50pm (Africa/Cairo)") stopped this session and its
  2.2.1 child mid-work; the user had to say "Try again".

### 3. Decisions made (with reasons)
- **Input unit:**
  - A window of the episode picked at Gate 0 with `reels-select --as motion`: a reel candidate (`R03`) or a topic from
    the topic map (`T02`), 15–180 s (motion limits in `motion.json`).
  - Audio-only episodes are accepted (media kind from the file type).
  - Each pick becomes its own project `EP12_R03_MO`, so a video reel and a motion version of one moment coexist.
  - Formats 9x16 and 16x9.
  - **Whole-episode animation is deferred.**
- **Story beats → scenes:**
  - Each recipe gets a `motion` block: beats, scene_s, prefer, avoid, reveal, ease, transition, theme, captions,
    speaker_badge, progress, voice_pulse, max_words_on_screen, emphasis_per_scene, sfx_on_transition, plus a 16th key
    `sfx_rules`.
  - Some types avoid certain scenes: drama, bold_opinion and comedy avoid list_steps; emotional avoids list_steps,
    stat_counter and comparison.
  - A new `motion-director` agent (opus) writes `motion-script.json`; a new `ae-builder` agent (sonnet) builds.
- **Truth checks in the engine:**
  - Every on-screen word is in-order speech or marked editorial; text that replays speech (kinetic_quote, quote_card)
    has a max-drop ratio.
  - Every number must have been spoken (digit runs compared).
  - Names come only from the sheet: editorial lines use `{host}`, `{guest}`, `{show}` placeholders, because code can't
    spot names in free Arabic text.
  - Fields with no stated source count as speech (the strict check).
- **Visual vocabulary:**
  - A closed set of **12 parametric scene types**: kinetic_quote, title_card, stat_counter, icon_point, list_steps,
    comparison, timeline, quote_card, context_card, person_card, illustration_scene, outro.
  - **5 persistent layers**: background, captions, speaker_badge, progress, voice_pulse.
  - Implemented once in an ES3 JSX library (`nh_motion_lib.jsx`), so Claude composes data instead of writing free JSX
    per video.
  - In Arabic, anything meaning "next" moves right to left.
- **Assets:**
  - The client's brand files.
  - **Lucide icons** (ISC), shipped with the plugin (`lucide-static 1.47.0`, 2112 SVGs, checksum verified), converted
    to native AE shapes including arcs; RTL mirroring for directional icons.
  - Illustrations only from packs with a license file. SVG illustrations become **one-colour** shapes; colourful packs
    must be PNG.
  - Nothing generated or downloaded at run time.
  - CC-BY attribution is enforced in QC and in publish captions.
- **AE build path:**
  - Generate data plus a JSX library and run it inside AE through **the existing WhyNot Cut Bridge, made one CEP bundle
    for Premiere and AE** (`ai.thewhynot.cut.bridge` 3.1.0; hosts PPRO [22.0,99.9] and AEFT [24.0,99.9]; separate
    queues `ppro-queue`/`ae-queue`; whitelisted script dirs; heartbeat reports the host; ExtendScript never writes
    files).
  - Chosen over `AfterFX -r` alone, because `-r` returns nothing on Windows so the build can't be checked; `-r` stays as
    a fallback whose build is BUILT_UNVERIFIED and can't pass QC.
  - Chosen over designer-made `.aep` templates, because they are binary files Claude can't generate or review.
  - **CEP rather than UXP**, because UXP for AE is still beta; a future AE without CEP needs a UXP port.
- **Arabic in AE:**
  - An `ae-probe` command renders test comps once per AE version; Claude views the frames and records a verdict in
    `~/.whynot-cut/ae-capabilities.json`.
  - Building is blocked without an ok verdict for that exact version, and a missing brand font blocks the build.
  - Fallbacks are planned per known quirk, e.g. the AE 25.2 bug where text `direction` doesn't persist.
- **Word reveals:** **one text layer per word for all text** (with a non-rendering guide layer holding the full text),
  because AE 26.5's "Based On: Words" selector maps textIndex inconsistently for RTL Arabic. Cost: an editor changing a
  word edits its word layer, and scenes have more layers.
- **QC:**
  - After the build, AE reports back what it made (text, fonts, direction, box positions); this read-back is compared
    with the plan.
  - `aerender` renders, frames are pulled at planned "hero" moments, and frame-inspectors check them.
  - Audio sync (correlation ≥0.9 within ±1 frame), the no-word-cut proof, licenses, approvals.
- **Integration:**
  - An "animatic" (a 10 fps rough preview with audio) comes before Gate 1.
  - `episode-next` and `next` know motion projects.
  - The publish package gets motion reel captions (`publish/reels/EP02TEST_R02_MO.json`).
- **Safety:**
  - Unsaved AE work is checked twice (preconditions and inside `build_motion`); an unknown dirty state (null) is
    refused.
  - Rebuild protection via the `.aep` SHA-1 and `--replace-edited`.
- **Release:** `THIRD_PARTY_NOTICES.md` added; `tools/` is skipped by `package.py`.
- **Rulings with cost-if-wrong** (58 in the final report; the key ones):
  - The worktree folder name `whynot-cut-marketplace-motion` was kept instead of `-ae-motion`.
  - Default capabilities are used if there is no probe, but a real build still refuses.
  - The heartbeat read retries a torn file (≤200 ms lag).
  - All probe comps render in one aerender run.
  - Frame extraction seeks a quarter frame early.
  - ProRes preferred over Lossless for probe renders.
  - The probe keeps its diagnostic comps (about 10 s more).
  - `--type` only for topic picks.
  - The animatic is 10 fps (cuts quantised to 0.1 s).
  - Only colours equal to a brand colour follow the brand controls (others need manual recolour).
  - When the probe says word order isn't logical, reveals fall back to whole lines (never observed).
  - A text box overlapping the caption band is a warning.
  - Line breaking balances by character count.
  - The "too short" rule follows the spec literally (the last word may still be fading in at a cut).
  - Accent below 3:1 contrast falls back to the text colour.
  - Missing pauses data is an error; a missing brand font file triggers a measuring fallback with a warning.
  - The license check uses the plan.
  - The probe step counts as done machine-wide (no re-probe prompt after an AE update until a build refuses).
  - Plugin validation was not run (no `claude` CLI).
  - Gates 0/1 for the test reel were recorded delegated.
  - The live build used the fallback font.
  - Reviewer model "Fable 5.1".
  - The audio-sync thresholds stand (a loud music bed could fail falsely).
- **Bridge downgrade guard** (requested by the Reel session): `reel ppro-install` and `reel setup` keep a newer
  installed bridge unless `--force` (commit 39026fb).

### 4. Verified working (live, with evidence)
- **Environment:** AE 26.5x89 (AE 2026) with `aerender.exe`, and Premiere 26.5.2, on this Windows PC. Bridge 3.1.0
  answers in both apps. The `ae-probe` verdict "ok" is recorded.
- **Test reel `EP02TEST_R02_MO`** (PODCAST-TEST, storytelling, window 22.32–56.03 s), end to end:
  1. Gate 0 `--as motion`.
  2. audio-clean: 6 pauses removed (3.6 s), cut proof 62/62 words.
  3. A 9-scene motion script; motion-plan ok (warnings: S08 2.3 s, no music).
  4. Animatic viewed; approve-plan (delegated).
  5. motion-build with `--allow-fallback-font` (Segoe UI Bold, since IBM Plex Sans Arabic isn't installed):
     PROJECT_ASSEMBLED, read-back ok, 9/9 scenes.
  6. motion-render: RENDERED 1080×1920, 24 fps, 32.333 s, with audio, −14.3 LUFS.
  7. motion-frames 24/24 viewed: Arabic joined, RTL word order, mid-reveal frames show the first words in their final
     places, accent on emphasis words, nothing clipped, safe area respected.
  8. verify pass; QC 10/10 (audio correlation 0.999, offset 0); handoff READY_FOR_HUMAN_EDITOR; publish-check ok for
     EP02TEST_R02 and EP02TEST_R02_MO.
  9. Re-verified after the review fixes (ae38882): the approved plan keeps the IBM Plex fonts, only the job uses Segoe
     UI, and the README lists the fallback under "Needs you".
- **Premiere on bridge 3.1.0:** `ppro-frames` for podcast reel EP02TEST_R02 (PODCAST-TEST), 17/17 frames viewed. The
  first run showed "Media pending" on 4 frames (became G69); the second run was clean. QC passes, READY_FOR_HUMAN_EDITOR.
- **Suite progression:** 298 → 309 → 315 OK after the review fixes → 350 OK after the rebase (231 + 119 motion and
  bridge tests), 4 skipped.
- **Review (Fable 5.1), "with fixes": 1 Critical + 5 Important fixed RED→GREEN.**
  - Critical: `--allow-fallback-font` overwrote the approved plan, so later rebuilds and the handoff silently
    used/reported the wrong font.
  - Important:
    - An unknown AE dirty state was treated as safe to replace (now refused).
    - Topic picks skipped the sheet's avoid-topic check.
    - Digits in timeline dates were a hard error instead of an approval item.
    - Captions and speaker names were always RTL, which breaks English episodes.
    - The comparison divider was hidden behind a themed scene's background.
  - The 6th Important (a partial-scene render passing QC with a stale MP4) was not reproducible and is pinned by a
    test.
- **Arabic-named client folder (2.2.1 item 16):**
  - Copied PODCAST-TEST to `whynot-test/بودكاست-تجربة`. With minimal patches for items 17 and 18, the whole chain
    passed: plan, animatic, approval, build (AE handles Arabic paths itself), render 1080×1920 with audio, 24 frames
    identical to the PODCAST-TEST run, QC 10/10, READY_FOR_HUMAN_EDITOR.
  - The patch was saved as `arabic-path-probe.patch` in the shared notes and reverted; the real fix went to 2.2.1.
  - Evidence: `whynot-test/بودكاست-تجربة/output/projects/EP02TEST_R02_MO/08_quality_control/ae_frames/run-20261011-143335/`
    and `qc-results.json`.

### 5. Failures, bugs, gaps
- **Build-time and live AE findings, all fixed with tests:**
  - "NHM is undefined": `$.evalFile` inside a function keeps globals local, so the libraries now load at top level.
  - "Object is invalid": adding a property to a shape group invalidates sibling references, so the Trim Paths reference
    is re-acquired.
  - Inconsistent textIndex for RTL Arabic → per-word layers with scale-aware spacing.
  - Too-short false positives with push transitions → transitions play after the scene end (`nxt=0`).
  - Captions duplicated words in list/icon scenes → captions hide wherever speech is shown on screen.
  - A duplicate outro show line → skipped when the CTA names the show.
  - An empty PostScript name ("Unable to set font") for a brand without Black → nearest-weight font per role.
  - Safe-area overflow (9 px) with the fallback font → the plan is re-fitted with the fallback font for the job only.
  - PermissionError on `dialogue_motion_seq.wav`, because **AE on Windows locks imported audio** → content-addressed
    dialogue file names and SFX reuse.
  - Dialogue at −0.8 LUFS (noise), because **audio-clean writes 24-bit PCM** decoded as 16-bit → decode via ffmpeg
    (now −14.3 LUFS).
  - The hero QC frame of S04 came before 6 of its 8 words had appeared → `either()` texts feed the scene cues.
  - Flaky heartbeat reads; `extract_frames` lost the last frame.
  - Tooling: Bash heredocs mangled `\n`/`\r` and Arabic; Python `write_text` produced CRLF (use `newline="\n"`); huge
    `assertIn` output; one non-discriminating test was strengthened.
- **2.2.0 deferred minors, which became the 2.2.1 list:**
  1. Unknown values for transition/theme/captions/reveal aren't rejected (a typo becomes a cut or the dark theme).
  2. Per-scene `captions: "off"` isn't implemented.
  3. A comparison verdict failing the speech check also produces a bogus editorial error.
  4. On Windows, rendering while a player has the old MP4 open gives a raw PermissionError.
  5. QC doesn't check that the render has an audio stream.
  6. `audio_sync` compares the full mix (music/SFX) with dry dialogue, with no diagnostic.
  7. The LTR progress bar grows from the centre.
  8. The script-only fallback has no unsaved-changes check before `app.newProject()`.
  9. `--replace-edited` takes its backup before the preconditions.
  10. Old dialogue WAVs accumulate.
  11. The `guard.py` AE-preferences message is mis-worded.
  12. Unused `motion_qc.plan_fonts` and `sha1`.
  13. Two cosmetic nits.
  14. No live build yet from an Arabic-named folder.
  15. `nh_ae_bridge.jsx:17` has a raw U+FFFF where an ASCII escape was meant.
  16. The README singular/plural for fallback fonts.
- **Kept as rulings, not bugs:** the per-word fallback for AE versions whose probe says word order isn't logical, and
  the brand-font install (the user's job).
- **New bugs found live in 2.2.1 (items 17 and 18):**
  - **17:** FreeType can't open a font file under an Arabic path on Windows. Layout measuring crashes for any
    Arabic-named client folder, in podcast graphics too.
  - **18:** `aerender` turns Arabic letters in paths into `???`, so the render fails. It would also break the probe
    for a Windows user whose profile name isn't ASCII.
  - Fixed in 2.2.1 commit 574104b ("FreeType font paths, aerender paths"); the review commit 920b9ff added
    Windows-only aerender staging.
- **Coordination failure:** the "Reel editing plugin enhancement" session didn't answer two messages, so Premiere was
  first re-checked by ping only. It answered later with OK and rules: rollback via `reel ppro-install` from main tag
  v2.1.0 restores 3.0.0; ask the user to restart Premiere, never kill it; never set the registry; use PODCAST-TEST only;
  keep `NHPP.actions.clip_components` and `NHPP.activateProject` in bridge.js.

### 6. Open / deferred / unverified at the end
- **Not verified:**
  - A Premiere **`ppro-build`** on bridge 3.1.0. Only ppro-status ping and ppro-frames were run.
  - **macOS.**
  - A build in the **brand font** (IBM Plex Sans Arabic not installed).
  - An **audio-only episode**, live.
  - The new caption-direction and comparison-divider code inside AE (the live reel had no captions or comparison
    scene; tests only).
  - `claude plugin validate --strict`.
- **Needs the user:**
  - Install IBM Plex Sans Arabic from `assets/Fonts`, restart AE, rebuild without the fallback flag.
  - Add a licensed music bed (motion ships with dialogue plus SFX only).
  - Don't run `/whynot-cut:setup` from installed 2.1.1, which would downgrade bridge 3.1.0 → 3.0.0 and drop the AE host.
  - When closing Premiere, answer **No** to saving PODCAST-TEST (left open next to Dr Sherin R02).
- **2.2.1 status at the end (12:08 UTC):**
  - The child session (local_de569d4d, `fix/motion-minors`, worktree `whynot-cut-marketplace-motion-minors`) had 8–9
    commits, the version bumped to 2.2.1, and CHANGELOG "2.2.1 — Motion mode polish, client folders with Arabic names".
  - It reported the code, both live AE checks and the docs done (tip 89834af), but its fresh review was still running.
  - The parent hadn't re-run the checks.
  - The live check of item 14 (ASCII escape) on its tip was planned.
- The backup branch `backup/ae-motion-pre-rebase` was deleted by the integrator after the merge.

### 7. Environment facts
- **Installed apps:** After Effects 2026 (26.5x89) with `aerender.exe`; Illustrator 2026; Media Encoder; Premiere
  26.5.2.
- **CEP:** PlayerDebugMode=1 for **CSXS.12**, set by the user, not by Claude. CEP loads panels **only at app launch**,
  so a bridge reinstall needs the user to save and restart both apps.
- **Bridge:**
  - CEP bundle `ai.thewhynot.cut.bridge` 3.1.0 for PPRO and AEFT; `templates/premiere/cep_bridge/js/bridge.js`
    (HOSTS map, `hostId()`); `manifest.xml`.
  - AE side: `templates/after_effects/nh_ae_bridge.jsx` (actions ping/fonts/probe_text/build_motion/readback),
    `nh_ae_lib.jsx`, `nh_motion_lib.jsx`.
  - Python: `cep_queue.py`, `ae_bridge.py`, `ae_probe.py`, `ae_render.py`, `motion_*.py`.
- **AE scripting facts used:**
  - `composerEngine` UNIVERSAL and `ParagraphDirection` RTL.
  - `app.fonts` / fontObject; ParagraphRange (AE 24.3+); SVG import as shape layers (AE 26).
  - `sourceRectAtTime`, Trim Paths, keys at frame×frameDuration.
  - `app.beginSuppressDialogs`; `app.project.dirty` (can be null/unknown).
  - aerender flags `-comp -RStemplate -OMtemplate -output -s -e`.
  - UXP for AE is still beta.
- **AE quirks:**
  - RTL word selector unreliable (26.5).
  - The `direction` set doesn't persist on AE 25.2 (reported bug).
  - `$.evalFile` scope.
  - Shape-group property invalidation.
  - Windows locks imported audio.
  - aerender mangles non-ASCII paths.
  - FreeType (engine side) can't open fonts under Arabic paths on Windows.
- **Fallback fonts** (in `config/defaults/motion.json`): Windows "SegoeUI-Bold", Mac "GeezaPro-Bold".
- **Motion config:** formats 9x16/16x9 with safe areas; duration 15–180 s; themes; render templates;
  `licenses_allowed`.
- **Ledger:** `.superpowers/sdd/2026-10-11-motion-from-audio/progress.md`, deleted after the copy into the shared notes
  (`motion-2.2.0-ledger.md`).
- **Shared notes folder:** `C:\Users\LOQ\AppData\Roaming\Claude\side-session-notes\local_520a891b-6432-467e-9db0-3c268b359926`.
- **Test command:** `"C:/Users/LOQ/.whynot-cut/venv/Scripts/python.exe" -B -m unittest discover -s whynot-cut/tests`
  from the worktree root (about 3.5–5 min; run in the background).
- **Shell:** write scripts with the Write tool, not Bash heredocs; Arabic and backslashes break in Bash.

### 8. Ideas floated but never implemented
- Animating a **whole episode**; windows over 180 s; **4:5 and 1:1** motion formats (out of scope in spec §2).
- **Designer `.aep` templates with data replacement** (rejected); `AfterFX -r` as the main path (fallback only).
- A **UXP panel** (future port if CEP goes away).
- **Colour SVG illustration conversion** (only monochrome today).
- The **per-word-layer fallback** for AE versions where the probe says word order isn't logical (ruling, deferred).
- **Music for motion videos** (planned via a licensed bed; none placed).
- **Audio-only episode live test**, and the PODCAST-AUDIO-TEST client, which was mentioned but not run live.
- An `audio_sync` diagnostic that separates the music bed from dialogue (2.2.1 item 6).
- Re-probe prompting after an AE update (today only motion-build refuses).

---

## SESSION 3 — 2d167d3a: "Running chat management" (integrator/coordinator)

**What it was.** The user started it with: "manage the running chat and make them work together, no stop until they
finish everything and give me the final result". It ran 2026-10-11 08:15 → about 12:20 UTC (the digest stops at
12:13; the transcript continues to 12:20). It made itself the single owner of `main`:
- Merged `feat/client-ref-style` (e090994), then `feat/ae-motion` as 2.2.0 (39026fb).
- Tagged v2.2.0 and built `whynot-cut-2.2.0.zip`.
- Coordinated the 2.2.1 work, and dispatched three helper agents (worktrees `-r4a/-r4b/-r4c`) to fix the round-4 field
  gaps G62–G69 from the user's real Dr Sherin EP02 run.
- Ended by answering the 3.0 master-plan session with an open-items status.

### 1. User requirements & wishes
- Coordinate all running chats to the end without stopping, and deliver the final result.
- «كمل لحد ما تخلص كل حاجة ولو في شات واقف ومحتاج انه يشتغل خليه يكمل و يخلص كل حاجه لحد ما تقفل النتيجة النهائية وكل
  حاجه اتصلحت»: "continue until everything is done; if a chat is stopped and needs to work, make it continue until the
  final result is closed and **everything is fixed**". This is why deferred minors and field gaps are fixed now rather
  than left for later.
- «كمل لحد ما Phase 3 يخلص وابعتلي النتيجة النهائية», «كمل ومتوقفش لحد ما تبعتلي النتيجة», «كمل لحد ما تخلص وابعتلي
  النتيجة النهائية»: keep going, don't stop, send the final result.
- "I hit my usage limit while you were working, but it has reset now. Please continue from where you left off."
- **Real-use wish visible in this window:**
  - The user installed WhyNot Cut 2.1.1 and opened `/whynot-cut:start`, with settings clients_root
    `D:/WhyNot Clients`, editor_name Yunus, language ar, approval ask, whisper_model large-v3. A folder was scaffolded
    for `D:/WhyNot Clients/Dr Sherin Helmy`.
  - Yunus then **delegated the whole real Dr Sherin EP02 podcast run** (transcription, reels plan, several reels built
    in Premiere, QC, publish package) to the Reel session.
  - The user later **paused** that run mid-way.
- **The 3.0 master plan, per the planning session's message:** "WhyNot Cut 3.0: native Premiere/AE plugin, Magnific
  MCP, installer, one final folder, Arabic PDF guide".

### 2. User complaints / dissatisfaction
- None explicit.
- Implicit: repeated "don't stop / send me the final result" messages show impatience with partial reports and waiting.
- Usage limits interrupted work: the integrator, the 2.2.1 session and one helper agent all hit the session limit at
  about 11:31–11:34 UTC.
- The user paused the real EP02 run; the reason isn't stated in these chats.

### 3. Decisions made (with reasons)
- **One integrator:** only this session merges, tags and zips; everyone else reports to it. Two sessions merging into
  the same main was judged risky.
- **History is fast-forward only and linear.**
- **Merge order:** the smaller `feat/client-ref-style` first, then Phase 3 rebased over it. Phase 3 owns the 2.2.0
  bump and CHANGELOG, and folds ref-style's "## Unreleased" notes into one 2.2.0 entry with sub-headings.
- **Ownership:** Phase 3 owns `ppro_bridge.py`, the CEP bundle, `cli.py`/`qc.py`/`verify.py`/`handoff.py`/`publish.py`
  and the Premiere bridge. The Reel session was told to stay idle.
- **Gate 0/1 on TEST clients:** quote the user's standing words in `--note` as delegation.
- **Bridge-version protection:** the onboarding session was told not to run `reel setup`/`reel ppro-install` from
  2.1.1, since `cmd_setup` reinstalls bridge 3.0.0 unconditionally and drops AEFT. Use `reel setup --no-bridge` if
  needed. A watcher was put on the bridge version.
- **Premiere vs AE scheduling:** the Reel session may use Premiere for the real EP02 run, Phase 3 uses only the AE side,
  and nobody closes or restarts apps.
- **2.2.1 split:**
  - The 2.2.1 child session does code items 1–15 with TDD, the bump, the suite and a review, with no AE or Premiere.
  - Phase 3 does the AE live checks (item 14 escaper, item 16 Arabic folder), so two sessions never drive AE at once.
  - A duplicate fix pass was retracted.
- **Round-4 gaps G62–G69:**
  - First tried as a separate session (start_session "WhyNot Cut: fix field-test round 4 gaps G62–G69"), then as
    three background helper agents.
  - The first wave died at the session limit and was re-dispatched at 11:51 on **sonnet**.
  - Each has its own worktree and branch from 39026fb: `fix/r4-a` (G62, G68), `fix/r4-b` (G63, G64, G67), `fix/r4-c`
    (G65, G66, G69).
  - Rules for the helpers: TDD, one commit per gap, no CHANGELOG/version edits, no Adobe or bridge use, never touch
    `D:\WhyNot Clients\`.
  - Plan: fast-forward motion-minors, rebase r4-a/b/c on top, fold the notes into the 2.2.1 CHANGELOG, run the suite,
    one live `ppro-frames` check for G69 on PODCAST-TEST, then tag v2.2.1 and zip.
- **G67 ruling:**
  - The venv-without-`-I` note applies only because this PC's venv was built with `--system-site-packages`, with
    packages in the user site (`%APPDATA%\Python\Python313\site-packages`), as a deliberate slow-PyPI workaround. So it
    isn't a plugin bug.
  - The installer plan should make the venv self-contained.
- **Phase 0 wording agreed with the 3.0 planning session:** "integrator finishes 2.2.1 (motion minors + round-4
  r4-a/b/c), tags v2.2.1, builds the zip, removes all feature worktrees; 3.0 starts from main at v2.2.1". Addition:
  **also update the installed plugin to 2.2.1**, or 3.0 testing runs against 2.1.1 and the old bridge logic.

### 4. Verified working (live, with evidence)
- **main after ref-style:** 231 OK, 4 skipped, re-run by the integrator.
- **main after 2.2.0:** 350 OK, 4 skipped. Tagged v2.2.0; `whynot-cut-2.2.0.zip` built and checked.
- **Client-level reference style (from the ref-style session report):**
  - The reference style is analysed once per client in `output/client_database/reference_style/`
    (`editing-style-analysis.md`, `editing-style.json`, `editing-rules.json`, plus a `reference-set.json` fingerprint).
  - `reel ref-style --record/--apply`, plus `editing-style-overrides.json` per video.
  - Stale warnings when a reference is added, removed or edited, in `reel next`, discover, inbox, the session start and
    QC (advisory). `--apply` of a stale style is refused (exit 2).
  - Loose documents in `data/` without a "ref" path hint become `unclassified`, with a warning to move them to
    `data/References`.
  - Dry run on `whynot-test/_scratch-ref-style`.
- **Phase 3 AE results:** relayed (see Session 2).
- **Onboarding session:** `reel doctor` READY with bridge 3.1.0 alive and debug_mode_ok; `ppro-status` ping ok on
  Premiere 26.5.2.
- **r4-a (G62, G68):** 379 OK.
  - Visual check: thumbnails on a warm frame turn the highlight white (1.47:1 measured), and on a dark frame keep the
    brown.
- **r4-b (G63, G64, G67):** 380 OK.
  - G63 integration tests reproduced the field bug before the fix: in-point 4480 instead of 5680.
  - G67 checked against the real venv: `-I`, `-s` and `-E -s` all fail to import PIL/av/numpy; plain, `-E` and `-E -P`
    work.

### 5. Failures, bugs, gaps — the round-4 field test (installed 2.1.1, real Dr Sherin EP02 podcast)
- **G62** — previews ignore typography.json `roles`.
  - `Brand.role_style` was hard-coded {headline: black, small: regular}. A family without Black/Regular fell back to
    the **first file** (Medium), so hook titles rendered in Medium.
  - Workaround used: `brand.json font_roles_fallback.weights`.
  - **Fixed on r4-a** (1c1a1be): one resolver `lib/font_roles.py` (roles → brand.json → nearest weight, never first
    file), used by previews.Brand, motion_plan._fonts, ae_builder.fonts_map and thumbnails.
- **G63** — `reels-select --adjust Rxx:in=` snapped an explicit editor in-point back to a sentence start within
  ±1.5 s, so the editor couldn't skip one word (R07 11:46.95 → «طيب» 11:45.57).
  - Workaround: `global.cut_words`.
  - **Fixed on r4-b** (6019efa): an explicit adjust snaps to the nearest word with 120 ms lead-in and 250 ms tail, never
    backwards past the skipped word; automatic windows keep the sentence preference.
- **G64** — reels-plan evidence breaks after `transcript-correct` (the analyst ran in parallel with the
  transcript-editor), and the error listed only the quote.
  - **Fixed on r4-b** (b660d68): "did you mean: «…»" with the corrected words. Docs tell the analyst to copy it.
- **G65** — the intake sheet samples only 6 frames, so it missed the name supers at 01:27 and 16:55
  (`lower_thirds: false`).
  - **In progress on r4-c, uncommitted at the end** (new `lib/overlay_scan.py`, `episode.py` changed).
- **G66** — a Claude session started **before** the plugin install keeps the old plugin's `bin` on PATH, so `reel` is
  the old reel-editor ("environment not installed"), and subagents inherit it.
  - Fix plan: `reel` names itself in errors; doctor/start detect a foreign `reel`.
  - **In progress on r4-c.**
- **G67** — `python -I` with the engine venv loses site-packages on Windows.
  - **Docs fixed on r4-b** (d97696c): a note at the top of 13 agents, a platform-setup section, and a troubleshooting
    row. No guard hint, since guard.py is block-or-silent.
- **G68** — the profile said highlight in "brand gold", but the measured primary is brown #81613D, which was unreadable
  on a warm set (1.1–1.5:1).
  - **Fixed on r4-a** (bbd0699): `lib/legibility.py` measures WCAG contrast against the frame region (3.0 for ≥64 px,
    4.5 below) and falls back to white/paper with a warning, in publish-thumbnail and preview stills.
  - Remaining limits: caption stills not frame-checked; decorative bars and AE-builder highlight colours not checked;
    the region mean can pass a half-bright region.
- **G69** — `ppro-frames` right after a project opens exported 4 of 17 frames as the "Media pending" slate.
  - Fix plan: detect and re-export; QC treats such a frame as a re-export, not pass/fail.
  - **In progress on r4-c.** One live check is planned on PODCAST-TEST.
- **Also:** a hidden risk that onboarding's `reel setup` (2.1.1) would downgrade bridge 3.1.0. It was prevented by
  messaging, and the guard arrives only with 2.2.x installed.
- **Process failures:** the round-4 start_session attempt and the first helper agents were killed by the session limit
  (HTTP 429) and re-dispatched. Messages to a busy session queue until its turn ends, so the parent session was used to
  relay mid-turn.

### 6. Open / deferred / unverified at the end (the integrator's 12:20 status to the 3.0 planner)
- **main = 39026fb = v2.2.0**, zip built; 350 OK.
- **2.2.1 part 1:** `fix/motion-minors` is 9 commits ahead (tip 920b9ff, "final review of 2.2.1": Windows-only aerender
  staging, keep renders, safer pruning, planned-mix verdicts). Still pending there: its live AE checks in
  `whynot-test/بودكاست-تجربة` and its report.
- **2.2.1 part 2:** r4-a done, r4-b done, r4-c in progress.
- **Then:** fast-forward the minors, rebase r4-a/b/c (expected overlaps: `motion_plan.py`, `ae_builder.py`,
  `guard.py`, agent docs), fold the CHANGELOG, run the suite, one live G69 `ppro-frames`, tag v2.2.1, zip, remove
  worktrees.
- **Never verified:** macOS (nothing has run on a Mac); a real 60–90 minute episode end to end; speaker-follow on a real
  two-shot; a Premiere `ppro-build` on bridge 3.1.0.
- **Brand font** IBM Plex Sans Arabic not installed (live motion builds used Segoe UI). **Motion videos have no music.**
- **Deferred design items:** the per-word reveal fallback; the G68 limits; the region-mean contrast weakness.
- `claude plugin validate --strict` never run (the `claude` CLI isn't on PATH in these sessions).
- **Installed plugin on the PC is 2.1.1** (from the `~/.whynot-cut/marketplace` directory marketplace). Its setup would
  downgrade the bridge; it must be updated to 2.2.1.
- **Real Dr Sherin EP02 run** (`D:\WhyNot Clients\Dr Sherin Helmy`, Reel session) is PAUSED mid-way: the R03–R09
  story-editors were stopped with partial files.
- **Reel-session user items carried forward:** the plugin swap, listening to R02/R05, the doctor's approval, and the
  `R02_TEST` folder.
- **Ref-style user items:** the real client's R02/R05 still have per-video styles; the first new video will ask to
  record the client style once (it can be seeded from R02). `whynot-test/_scratch-ref-style` can be deleted.
- **The venv is not self-contained** (`--system-site-packages`); the installer should fix that.

### 7. Environment facts
- **Worktrees** (siblings of `whynot-cut-marketplace/`):
  - `-motion` (feat/ae-motion).
  - `-motion-minors` (fix/motion-minors).
  - `-r4a`, `-r4b`, `-r4c` (fix/r4-a/b/c).
  - Removed: `-podcast-minors` and `-ref-style`.
  - A requested `-round4` was never confirmed.
- **Test baseline:** 350 OK, 4 skipped, about 5 minutes. Always use `PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1` and the
  venv.
- **Packaging:** 172 files at 2.1.1, more at 2.2.0. Version in three places.
- **Apps open during the work:** Premiere on `whynot-test/Dr Sherin Helmy/.../R02_SH_EDIT.prproj` (later also
  PODCAST-TEST), and AE on an untitled project.
- **User settings file values:** clients_root `D:/WhyNot Clients`, editor_name Yunus, language ar, approval ask,
  whisper_model large-v3.
- **Field-gap list file:** `D:\0 Work\0 Pegasus IMC Agency\00 TWN\0 TWN AI\Editing Plugin\round4-gaps.md`.
- **Session/usage limits** reset at "2:50pm (Africa/Cairo)". Running many parallel sessions burns the limit at the
  same time.
- **Cross-session messaging:** a busy session reads messages only at the end of its turn; parents can reach children
  mid-turn.
- **Windows venv detail:** packages live in `%APPDATA%\Python\Python313\site-packages` (Python 3.13). `-s`, `-I` and
  `-E -s` break imports.

### 8. Ideas floated but never implemented
- The 3.0 master plan from the planning session: native Premiere/AE plugin, Magnific MCP, installer, one final folder,
  Arabic PDF guide.
- A self-contained installer venv.
- A G67 guard hint in guard.py, rejected because guard.py is block-or-silent.
- G68 extensions: frame-checking caption stills, decorative bars and AE-builder highlight colours; a better-than-mean
  region test.
- Seeding the real client's reference style from R02's per-video style.

---

## Cross-session roll-up (for the master plan)

**Top user requirements**
- One plugin with modes: talking-head edit, podcast → reels, audio → AE motion. Claude is the brain and builds native
  Premiere AND AE projects.
- Podcast: transcript, context analysis, a reels plan with timecodes and content type (storytelling, drama, success
  story…), the editor picks, then the normal pipeline.
- Content type drives pacing, music/SFX, graphics and copy tone.
- A full YouTube/social package: titles, description, chapters, tags, SRT, per-reel captions and hashtags, thumbnail.
  No upload.
- Arabic first (RTL correctness everywhere), Mac and Windows.
- Work style: decide the best option and continue to the final result. The only stops are merges/pushes, destructive
  actions, Adobe security settings and the registry, and app restarts. Fix everything now, not later.

**Still open when these chats end**
- Finish and merge 2.2.1 (motion minors + r4-a/b/c, with G65/G66/G69 unfinished). Tag, zip, remove worktrees.
- Update the installed plugin from 2.1.1 to 2.2.1. Replace the old reel-editor 1.0.7 if it's still installed.
- Never verified: macOS; a real 60–90 minute episode; speaker-follow on a real two-shot; Premiere `ppro-build` on bridge
  3.1.0; the brand font in AE; an audio-only episode; agent-written plans and copy (the tests used Claude acting by
  hand); `claude plugin validate --strict`; the 4:5/range Snapshot code (never independently reviewed).
- Resume or close the paused real Dr Sherin EP02 run; doctor's approval; listening to R02/R05.
- No music in motion videos; the font must be installed by the user.

**Ideas never built**
- A button panel inside Adobe, now on the 3.0 list as a "native plugin".
- YouTube draft upload (OAuth); pyannote diarization; split-screen; raw multicam/wide-camera input; auto top-N reels.
- Thumbnail PSD; a podcast-only zip.
- Whole-episode, 4:5 and 1:1 motion; colour SVG illustrations; a UXP port; designer `.aep` templates.
- A self-contained installer venv; Magnific MCP; an Arabic PDF guide; "one final folder".
