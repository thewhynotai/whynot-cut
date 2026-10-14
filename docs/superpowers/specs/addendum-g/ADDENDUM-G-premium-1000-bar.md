# WhyNot Cut 3.0 — Addendum G: the $1,000-a-month bar (premium product + commercial readiness)

| | |
|---|---|
| Date | 2026-10-14 |
| Requested by | Yunus: «انا ناوي ابيعها ب 1000$ شهريا. حاول تخليها بالمستوي اللي يليق بالرقم دا وباقوي واشهر البلاجنز العالميه في الشغل و التنفيذ والديزاين وكل حاجه عمم علي كل حاجه» ("I plan to sell it for $1,000 a month. Make it worthy of that price, at the level of the strongest and best-known plugins in the world in function, execution, design and everything; apply it to everything") |
| Applies to | Every phase, track, gate, screen, installer, the guide and the release. Raises the bar set in Addenda B/C/D/E. Nothing already decided is cut |
| Standing rules | Decide and continue (no approval stops). The zero-cost rule (F1) still holds for Yunus's own spending; G5 is a recommendation only |
| Commit | The executor commits this to `docs/superpowers/specs/addendum-g/` (single writer) |

## G0. What $1,000 a month means
A buyer paying $12,000 a year compares us with tools they already trust. They expect:
- it never loses work;
- it is never confusing;
- it looks better than anything else in their Premiere;
- it saves them hours on every reel.

**Reference set** (quality bar only, never copied):
- Adobe's own Premiere/AE AI features (Media Intelligence, Generative Extend, Speech to Text);
- Descript; AutoCut; FireCut; Submagic/Captions; Excalibur; Frame.io; Runway;
- for UI craft: Linear, Raycast, Arc.

**Rule:** for every core job, WhyNot Cut is at least at parity with the best reference tool on four things:
- quality of result;
- speed;
- clarity;
- recovery from errors.

Where it isn't, the gap is a tracked defect, not a "nice to have".

Our core jobs:
- talking-head edit to Premiere project;
- podcast to reels;
- Arabic/English captions (Kalam);
- silence and pause removal (Hush);
- project cleanup (Tidy);
- motion graphics in After Effects;
- QC.

## G1. Benchmark study (new task G-T1, do now, read-only, parallel)
1. For each reference tool: features, onboarding steps, time-to-first-result, panel UX patterns, error handling, pricing tier, what reviewers praise and complain about. Use public docs, reviews and videos; **no sign-ups, no purchases, no downloads of their software**.
2. Output: `docs/benchmark/benchmark.md` with a **gap list**. Each gap has a severity and an owning phase:
   - severity P0: a buyer would cancel;
   - severity P1: a buyer would notice;
   - severity P2: polish.
3. P0/P1 gaps become tasks in their phase. Phase 8's review re-scores the full list. **Release requires zero open P0 gaps and zero open P1 gaps.**

## G2. Raised quality bar (binding, checked at every QC gate from now on)
**Reliability:**
- No action loses or overwrites user work. Every edit Claude makes in Premiere/AE is undoable as one step or has a backup.
- Crash-free sessions at least 99.5% in the Phase 9 soak.
- Every long job is resumable after a crash or reboot.

**Speed budgets** (measured on this PC and on the CI Mac; failing budgets block the gate):
- panel opens to usable in ≤ 1.5 s;
- UI response ≤ 100 ms;
- first visible progress on any job ≤ 2 s;
- Kalam captions on a 60 s clip ≤ real-time on GPU;
- Hush on a 10 min track ≤ 30 s.

**Design** (E-D bar raised):
- every screen is reviewed side by side against the two best reference panels;
- the designer agent must answer "does this look like a $1,000/month product?" with evidence.

Every screen also has:
- all states: empty, loading skeleton, success, error with a fix button, offline, and no-Claude;
- motion and micro-interactions;
- keyboard shortcuts;
- perfect Arabic RTL and typography.

The three mockups already made (P-01, P-03, P-07) get one more critique round against this bar.

**Clarity:**
- zero «مش فاهم» moments in usability (E-D3 first-time editor + a new "agency owner" persona);
- every error says what happened, why, and the one button that fixes it;
- no developer words (token, daemon, JSON, CLI) anywhere a user sees.

**Results quality:**
- caption word accuracy on the Arabic/Egyptian eval set reported per release with a minimum bar;
- the cut-quality and QC eval suites must hold or improve vs the previous phase tag.

**Every QC gate** adds a "Premium bar" section to its report covering:
- budgets;
- open benchmark gaps;
- design verdict;
- clarity findings.

## G3. Commercial readiness: blockers before anyone pays (new task G-T2, licence audit, do now)
Selling means every bundled or downloaded component must allow commercial use. The audit writes
`docs/legal/third-party-licences.md`: name, version, licence, commercial OK?, attribution needed?, action.

Known risks to resolve first:

| Component | Risk | Required action |
|---|---|---|
| **MMS-300m CTC forced aligner (Kalam)** | Meta's MMS weights are **CC-BY-NC 4.0 (non-commercial)** | Replace it with a commercially licensed aligner and prove equal or better word timing on the eval set before Kalam ships. Candidates: an Apache/MIT wav2vec2 Arabic CTC model; Whisper cross-attention alignment (stable-ts/MIT); torchaudio CTC with a permissive model. Verify each licence |
| Egyptian-dialect Whisper turbo fine-tune | Licence of the fine-tuned weights unknown | Verify on its model card; replace if not commercial |
| Parakeet TDT 0.6B v2 | CC-BY-4.0 | Commercial OK; attribution in About + licences file |
| FFmpeg | GPL builds can't ship inside a closed commercial product | Ship or download an **LGPL** build only, or use the user's own ffmpeg; document it |
| Fonts | OFL fine; thewhynot.ai brand fonts may forbid app embedding | Check each font's EULA for software embedding |
| Kalam / Hush / Tidy source | Yunus states he holds the rights | Record the statement in `docs/legal/` |
| Python/npm/Rust deps | Copyleft (GPL/AGPL) | Flag and replace any copyleft dependency that would be distributed |
| Magnific | It's Yunus's account | Customers must connect **their own** Magnific account; never share his |
| Claude / Codex | It's Yunus's subscription | Each customer uses **their own** Claude (or Codex) account. H14 matters more now: confirm Anthropic's terms for a commercial product driving Claude Code. Default backend stays the customer's own open session |

**Gate:** Phase 9 cannot pass with any "commercial OK = no" or "unknown" row still open.

## G4. Licensing and subscriptions (product)
- **G-T3: a provider-agnostic licence module in the engine.**
  - Signed licence tokens (ed25519, the same key infrastructure as E3) carry plan, seats and expiry.
  - Checked by `reel` and the panels.
  - 7-day offline grace; a clear "licence" page in settings (AR/EN).
  - Trial mode.
  - No phoning home beyond the licence check; no telemetry.
- **G-T4 (after H16):** wire the chosen billing provider's webhook → licence issuing. Build no provider-specific code before H16.
- **Honest limit:** a Python engine and text skills can be copied. Protection relies on:
  - the licence check;
  - signed updates;
  - model packs served only to licensed users;
  - value that lives in updates and support, not on secrecy.

  Don't add obfuscation that hurts debugging or trips antivirus.

## G5. What a premium buyer expects around the product
- **G-T5:**
  - Arabic/English docs site content, built from the guide;
  - release notes per version;
  - an in-app "What's new";
  - in-app updates (signed);
  - a one-button diagnostics bundle (local, redacted);
  - a support contact in the panel.
- **Legal documents:** EULA, Terms, Privacy Policy, Refund policy. Claude drafts them; **Yunus/a lawyer approves** (H17). Claude never publishes legal text on its own.
- **Signing (recommendation, not done):** at $1,000/month, a buyer double-clicking an unsigned exe or typing a Terminal command is below the bar. A Windows code-signing certificate plus Apple Developer ($99/yr) costs less than one customer's first week. **Recommended once the first customer pays.** Until Yunus decides, F1 (one-liners + Microsoft Store investigation) stays.

## G6. Process changes
- The Phase 8 review adds a **buyer panel** of 3 agents:
  - a senior agency editor who uses Premiere 8 hours a day;
  - an agency owner deciding on a $12k/year purchase;
  - a design critic.

  Each scores against the benchmark and writes "would I pay $1,000/month, and what stops me". All P0/P1 items are fixed before Phase 9.
- No phase tag passes with a known P0. Speed over quality is never the trade.
- The executor reports the premium-bar status in plain Arabic in each status update.

## G8. Editions: 3.0 is the full trial build; the sale edition comes only on Yunus's word (update 2026-10-14)
Yunus: «زود كل حاجه بس استخدم احسن نسخه من FFmpeg … انا معايا حقوق كل حاجه. في الاول هتبقي تجريبه ف النسخه لازم يكون
فيها كل حاجه وبعد كده هنطلع نسخه لما انا اقولك هتبقي للبيع. انا محتاج اقوي حاجه وبعد كده نعدل عليها» ("Increase everything,
but use the best FFmpeg version… I hold the rights to everything. At first it will be a trial, so the version must
have everything; later we'll release a version for sale when I tell you. I need the strongest thing, then we adjust it").

This section **overrides G3/G4 where they conflict:**
- **v3.0.0 = the trial/full edition.**
  - Everything is included, and the strongest component wins every choice. No feature is cut or weakened for licensing reasons.
  - All of G0–G2, G5 and G6 (the quality bar, the benchmark, the buyer panel) apply in full.
- **FFmpeg:** use the strongest **full build** (GPL, all codecs and filters: gyan.dev "full" / BtbN `gpl` on Windows; an equivalent full static build or Homebrew `ffmpeg` on macOS), pinned by version and sha256.
  - The engine already calls it as a separate program (subprocess), not linked, so even a later commercial edition can ship it.
  - That requires the GPL licence text and a source link in `docs/legal/`. Add those now.
- **Models:** keep the strongest models, including the MMS-300m aligner, in 3.0.
- **G-T2, the licence audit, still runs now**, but as the **pre-sale checklist**. It is not a 3.0 blocker.
  - Every non-commercial or unknown row gets its replacement, or the licence needed, written down. Nothing is swapped yet.
  - G3's gate moves from the Phase 9 gate to the **commercial edition release** (started only when Yunus says).
  - Yunus holds the rights to his own code (Kalam/Hush/Tidy and the rest). Third-party model licences are settled at sale time.
- **The licence module (G-T3)** is built and tested in 3.0 but **off by default** (no licence prompts in the trial build).
  - It is switched on only in the commercial edition.
  - Billing (G-T4/H16) and legal docs (H17) belong to the commercial edition.
- **The commercial edition** (later, on Yunus's word) runs:
  - the G3 audit fixes;
  - the licence switch-on;
  - billing;
  - legal;
  - signing (H4).

## G9. The 50-person beta (update 2026-10-14)
Yunus: «محتاج اقوي حاجه من كل حاجه عشان هعمل ليها تست ل 50 شخص زي الناس الناقدين … ف لازم تبقي قويه» ("I need the strongest
of everything because I'll test it with 50 people, critical people like the ones you described… so it has to be strong").

v3.0.0 goes to **50 external testers** on their own machines. That adds:

**G-T6 Hardware and software matrix** (Phase 9). Install and run the full pipeline on:
- Windows 10 and 11;
- an NVIDIA GPU, an AMD/Intel GPU, and CPU only;
- 8 GB and 16 GB+ RAM;
- macOS on Apple Silicon (M1–M4) and Intel where it is still supported;
- the oldest supported and the current Premiere/AE.

Then:
- publish the **minimum requirements** in the guide and the installer;
- the installer checks them first and explains in Arabic/English what's missing.

**G-T7 Beta invites.** Each tester gets a **personal install link** that carries a beta key. It uses the G-T3 licence module in "beta" mode:
- no prompts, no typing;
- expiry date set by Yunus;
- Yunus can revoke a key.

The trial build still has every feature. Keys are generated by a `release.py beta-invite <name>` command and listed in a private file, never committed with secrets.

**G-T8 Feedback in one click.** The panel and the installer get a "Feedback" button:
- it writes a redacted diagnostics bundle locally;
- it opens a prefilled form (Arabic/English) with the version, OS and step;
- the tester attaches the bundle if they want.

The free route is a Google Form under Yunus's account or a prefilled email to the support address; the executor picks the free option.

Optional crash reports:
- **off by default**, opt-in with a plain Arabic consent;
- a free tier only, or local-only if no free option respects privacy.

**G-T9 Beta updates.**
- A `beta` update channel (signed, as in E3), so fixes reach all 50 in one step.
- In-app "What's new" for each beta build.

**G-T10 Tester onboarding.**
- A short Arabic welcome page in the guide: what to test, how to report, what it needs (their own Claude account, optional Magnific).
- A first-run walkthrough that gets them to a finished reel on the bundled sample clip in under 10 minutes.
- A bundled **sample client folder** (our own test footage with rights, never a real client's footage).

**G-T11 Triage loop** (after release, before the commercial edition):
- feedback becomes a P0/P1/P2 list;
- 3.0.x beta updates follow;
- the buyer-panel review is re-run against the testers' top complaints.

**Gate:** the beta goes out only after Phase 9 passes. Release day still needs Yunus's OK for the `dl` CNAME and the public releases repo.

## G10. Keep it simple: error-free operation is the main goal (update 2026-10-14, overrides G4/G9 where they conflict)
Yunus: «متصعبش الموضوع بس في نفس الوقت اهم حاجه ان التشغيل يكون كويس من غير اي اخطاء دا الهدف الاساسي» ("Don't
complicate it, but at the same time the most important thing is that it runs well without any errors; that's the main
goal").

**Priority order for every decision:**
1. It works without errors.
2. It's the strongest.
3. It's easy.
4. Everything else.

**Cut or deferred to the commercial edition** (less to build means fewer things to break):
- G-T3 licence module and G-T7 beta keys/personal links. The beta uses the normal install one-liner. No keys, no licence code in 3.0.
- Optional crash-report service (G-T8). Feedback is only "save diagnostics + open a form/email".
- G-T1 benchmark study stays, but **lighter**: one short report, used to fix real gaps, not a research project.

**Kept, because they directly prevent errors:**
- G2 reliability (no lost work, undo, resume after a crash);
- the speed budgets;
- G-T6 hardware matrix + minimum-requirements pre-check;
- G-T9 signed update channel (fixes reach the testers);
- G-T10 sample clip + first reel in under 10 minutes;
- the G-T2 licence list (paperwork only).

**New emphasis: zero-error operation.** These are added to the Phase 9 gate.
- **End-to-end runs.** Every core job runs end to end many times on clean machines/VMs, from a fresh install, with zero unhandled errors:
  - edit, podcast, Kalam, Hush, Tidy and AE motion;
  - install, update, uninstall.
- **Fault injection.** For each of these, the product recovers or says clearly what to do, with no crash and no lost work:
  - no internet;
  - Premiere closed mid-job;
  - disk full;
  - a missing font or model;
  - Claude not signed in;
  - a corrupt or very long clip;
  - Arabic/space paths.
- **A soak run:** many clips back to back with no memory or handle leaks.
- **Gate:** any reproducible error in a core job blocks release.
- **Simplicity check:** before adding anything new, ask whether it adds a way to fail. If it does and it isn't essential, drop it.

## G11. macOS is the primary platform (update 2026-10-14)
Yunus: «اهم حاجه بتوع الماك يكون كويس معاهم لان 90% من الناس بيشتغلوا ايديتنج علي الماك … مينفعش يكون في مشكله في
التحميل او التسطيب» ("most important is that it's good for Mac users, because 90% of people edit on Mac… there can't be
any problem in downloading or installing").

**Rule:** macOS is treated as the **primary** platform, not a port. Every feature, screen, guide chapter and gate passes on macOS to the same bar as Windows (G10: zero errors). Any Mac failure blocks the gate exactly like a Windows failure.

**G-T12 Mac-native quality:**
- Apple Silicon native (arm64) everywhere; no Rosetta needed. MLX/Metal acceleration paths for Kalam (mlx-whisper, parakeet-mlx) are measured against the speed budgets on M-series.
- The installer needs **no Homebrew, no Xcode tools, no admin password**. It runs with the default zsh.
- It handles Gatekeeper/quarantine correctly: files fetched by the installer aren't quarantined, and nothing ever asks the user to disable Gatekeeper.
- It installs per-user into the right places:
  - `~/Library/Fonts`;
  - the Adobe CEP/UXP folders and UPIA on Mac;
  - `~/Library/LaunchAgents`.
- macOS privacy prompts (Files & Folders, Automation) are pre-explained in Arabic/English before they appear, with screenshots in the guide.
- Paths with spaces or Arabic and iCloud/external drives work. macOS 13 to current are supported (the exact minimum goes in the requirements).

**G-T13 Mac testing:**
- **CI.** GitHub Actions macOS runners (arm64):
  - a short smoke run (engine + installer) on every pushed batch;
  - the full suite on phase tags and release candidates.

  The free plan gives 2,000 minutes a month, and macOS minutes count ×10, so monitor the usage with `gh api` and keep within it.
- **Live Mac test with real Premiere/AE (required before the beta ships).** CI machines can't run Adobe apps, so this needs a **physical Mac** (H18). The preferred route is an agency Mac with Premiere/AE installed:
  - install Claude Code on it;
  - the executor runs a Mac test session over SSH (or Yunus runs one prepared test script that writes a report);
  - run the full G10 end-to-end + fault-injection list on it.
- **Gate:** no beta without a passing live-Mac end-to-end report.

**Mac install experience:**
- The beta path is the Terminal one-liner, with an Arabic step-by-step page and screenshots: copy, paste, Enter, done.
- **Strong recommendation (H4-Mac):** Apple Developer Program ($99/year) before the beta, because 90% of testers are on Mac. It gives a notarized `.dmg`: double-click to install, no Terminal, no warnings. It is the single paid item most worth it. Yunus decides; until then the one-liner path stays.

## G12. Final hand-off: a Windows folder and a Mac folder; the agency Mac finishes and tests the Mac side (update 2026-10-14, refines G11's live-Mac route)
Yunus: «عندنا ماك في الإيجنسي … وحط بعد ما تخلص فولدر فيه حاجه الويندز كلها وفولدر فيه حاجات الماك كلها هاخد الفولدر احطها
علي الماك وهربطه بكلود كود واختار الفولدر دا … دا بعد ما تخلص كل حاجه دي اخر مرحله خالص والماك هناك هو اللي يخلص حاجته
ويجرب كل حاجه ويعمل التست" ("we have a Mac at the agency… after you finish, make one folder with all the Windows things and one
with all the Mac things; I'll put the folder on the Mac, connect Claude Code, choose that folder… this is the very last
stage, and the Mac there finishes its part, tries everything and does the testing").

**When:** the very last stage, after everything else passes on Windows. It becomes **Phase 12, "Mac finish & test"**, before the 50-person beta (Phase 11 release-day items move after it).

**Output** (built by `release.py handoff`, never edited by hand) in `Editing Plugin\WhyNot-Cut-Final\`:
- **`Windows\`**:
  - the final Windows deliverables: installer/one-liner script, plugin zip, `.ccx` (Premiere), signed `.zxp` (AE), the Arabic PDF guide;
  - `README-AR.md` (install steps with screenshots);
  - `checksums.txt`.
- **`Mac\`**: self-contained, so a fresh Claude Code on the Mac can finish the Mac side alone.
  - `START-HERE.md` (English, for the Mac Claude): the mission, the rules and the exact checklist. In order:
    1. Set up the Mac build toolchain locally inside the folder or user home (no admin, no system changes).
    2. Build the Mac artefacts (arm64): installer, `.app`/`.dmg` (unsigned unless H4-Mac), `.ccx`, `.zxp`.
    3. Install from scratch exactly as a tester would (the Terminal one-liner, pointed at the local files).
    4. Run the full G10 list with real Premiere/AE: end-to-end runs of every core job, fault injection, a soak run, install/update/uninstall.
    5. Verify the G-T12 Mac-native items.
    6. Fix any Mac bug with tests, by the same TDD + review rules.
    7. Write `mac-test-report.md` (pass/fail table + evidence).
    8. Commit and push the fixes and the report to the private repo, so the Windows side gets them.
  - `دليل-الماك.md` (Arabic, for Yunus): the few steps he does by hand.
  - The full repo **with `.git` history**, so the Mac Claude can commit and push. Secrets, renders, caches and `.venv`s are excluded.
  - The same standing rules as here:
    - never touch client folders;
    - the private repo stays private;
    - Adobe restarts only on test projects;
    - nothing paid;
    - the sample clip is our own footage.
  - The bundled **sample client folder** and its test projects.

**Gate:** the beta ships only after `mac-test-report.md` shows zero failures in core jobs and the Windows suite still passes after the Mac fixes are merged.

## G13. Lean footprint: light on disk, light on the machine, GPU-first (update 2026-10-14)
Yunus: «لازم تبقي متطوره علي اعلي ليفل عشان تكون خفيفه مش تقيله وتخلي الجهاز تقيل … وتبقي البلاجن لما تشتغل تشتغل علي ال gpu»
("it must be at the highest level so it's light, not heavy, and doesn't make the machine heavy… and when the plugin runs
it should run on the GPU").

The strongest models stay (G8). Lightness comes from engineering, never from weaker results.

**Disk**

The measured 2026-10-14 engine home is 4.7 GB:

| Part | Size |
|---|---|
| whisper large-v3 | 2.9 GB |
| CUDA DLLs | 0.7 GB |
| runtime | 0.5 GB |
| cache | 0.5 GB |

Targets:
- **Essentials** (plugin + engine + panels + FFmpeg, no models): ≤ 1.5 GB.
- **Full strongest** (with the Kalam pack): ≤ 13 GB.

The installer shows both sizes before installing.

How to stay lean:
- **One shared CUDA library set.** torch and CTranslate2 must not each ship their own cuBLAS/cuDNN (the `nvidia-*` wheels are shared once), and nothing is duplicated.
- **One model store.** Use Hugging Face blobs plus snapshot links, never two copies of a model. Keep one precision per model: fp16 or int8_float16 where the eval set shows equal quality, never fp32 and fp16 side by side.
- **Install location.** The engine home goes on the drive with the most free space. A non-system drive is preferred when the system drive has less than 30 GB free (F2-T3). Show it under Customise.
- **Housekeeping.** Caches are auto-pruned (size cap), logs are rotated, and a "Free up space" button sits in settings (AR/EN). Uninstall can remove the models.

**Machine load on the customer's PC** (editors run Premiere at the same time; this differs from our dev-PC policy)
- **Idle engine:** about 0% CPU and under 100 MB RAM (measured today: 27 MB). Models load on demand and are released after the job; an optional "keep warm" setting is off by default.
- **GPU first** for every heavy step, with automatic CPU fallback:
  - transcription (CT2 CUDA fp16 / MLX on Mac);
  - Kalam alignment and Parakeet (torch CUDA / MPS);
  - Hush VAD where it helps;
  - FFmpeg decode/encode for intermediates (NVDEC/NVENC, VideoToolbox);
  - GPU rasterization for previews.
- **Premiere stays smooth.** Background engine jobs run at BelowNormal priority on customer machines. When Premiere or AE is exporting or rendering, GPU jobs wait or yield. VRAM-aware batch sizes; out-of-memory falls back to the CPU with a clear message.
- **Speed budgets (G2)** are measured on both GPU and CPU-only machines (G-T6 matrix). The doctor and the panel show which accelerator is in use.

**Gate:** Phase 9 reports install sizes (Essentials and Full), idle CPU and RAM, peak RAM and VRAM per job, GPU use per job, and Premiere playback smoothness while a job runs. Any regression blocks the gate.

## G7. Human items (new)
- **H16:** the billing provider and the business entity that receives money. Stripe isn't available to Egyptian businesses. The candidates are Paddle or Lemon Squeezy (merchant of record, they handle VAT, with fees taken from revenue and no upfront cost). Yunus picks once he knows his company/payout setup.
- **H17:** approve the EULA/Terms/Privacy/Refund drafts (a lawyer is recommended).
- **H4 (reopened as a recommendation):** code signing after the first sale (G5).
- **H14 (now higher priority):** Anthropic confirmation for a commercial product using customers' own Claude Code.
