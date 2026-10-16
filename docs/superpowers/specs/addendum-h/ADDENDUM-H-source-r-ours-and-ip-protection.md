# WhyNot Cut 3.0 — Addendum H: the acquired reel tool ("Source-R") rebuilt as our own, and protecting our IP

| | |
|---|---|
| Date | 2026-10-15 |
| Requested by | Yunus: «خد حمل الفكره دي … دخلها باسمنا» · «انقل كل حاجه عندنا انا مش عاوز ريموشن وشيل كل التراخيص وخليها بتاعتنا» · «اعمل fine tuning للحاجات بتاعتها عشان متبقاش شبه 100% … بنفس الخطوات والستايل بس تكون متطورة واحسن واسهل» · «الرخص والحقوق والملكية الفكرية وان كل دا بتاعنا واللي يسرقه يعاقب قانونيا … اي حد يسرقه يوصلنا ايميل … او اللي يعدل في الكود من جيت هب» |
| Applies to | Phase 4 onward (motion styles, review editor, alignment), the licence files, the release pipeline and the beta |
| Section prefix | **R** (the prefix H is already used for human items) |
| Standing rules | Decide and continue. Nothing paid without Yunus's OK. G10 still applies: none of this may cause errors for real users |
| Commit | The executor commits this to `docs/superpowers/specs/addendum-h/` (single writer) |
| Inputs | The Source-R evidence report, kept **outside the repo forever** in the Addendum `evidence/` folder (it contains the original author's identity by design). **Never commit it.** The repo only gets name-free specs written from it (R-T1) |
| Naming rule | This addendum and everything in the repo call the tool **"Source-R"**. The original product name, the author's name and handle, and his style or file names never appear in the repo |

## R1. Decision: a clean rebuild in our own stack, with no Remotion
- **No Remotion.** We never ship or depend on any of these:
  - Remotion;
  - React (for this feature);
  - remotion-bits / remotion-ui;
  - headless Chrome rendering.

  Result: no Remotion company licence is needed, and the install is lighter (G13).
- **Clean rebuild.** The local read-only copy of Source-R (its path is in the evidence report) is never run and never accessed online.
  1. From it we write *behaviour specs*: what each feature does, its inputs, outputs, steps, timings and UX.
  2. Our implementers build from the specs only. They never open, copy or paste his code.

  Every line in our repo is written by us.
- **Where each feature lives:**

  | Feature | Built in |
  |---|---|
  | Motion styles | Native After Effects, through `motion-plan` → ae-builder |
  | Simple overlays | Premiere, through the UXP panel |
  | Review editor | Our panel, using the evidence-file loop from Addendum C |
  | Word alignment | Our engine (faster-whisper word timestamps on CUDA; our aligner) |
  | Face-aware framing | Our engine |
  | Previews | Python + FFmpeg on the GPU (NVENC), with a CPU fallback |

- **His verbatim assets** (sound files, presets, prompt texts, data tables):
  - They stay in a quarantine folder outside the repo until Yunus forwards the developer's written-assignment email and it is checked: rights to code, assets, name and derivatives, with a date and a signature.
  - Each one is then reviewed and either replaced by our own or adopted under our name.
- **The developer leaves no trace.** The identity-string list from the analysis (name, handle, emails, URLs, copyright lines, package metadata, asset metadata, distinctive strings) becomes a CI check (R5.4) that fails the build if any of them appears.

## R2. Evolve the styles, don't clone them
**Rule:** keep his *workflow steps and the family of each style*, but every result must be visibly **ours and better**:
- different and refined motion;
- easier to use;
- never a 1:1 copy.

For each of his styles, the spec gets an "Our version" block covering:
1. **Name.** A new WhyNot name; none of his style names.
2. **Motion.** Our own easing curves, timings and entrance/exit choreography, tuned on real client reels. At least the timing curves, layout grid and typography system differ from his.
3. **Brand-aware.** Colours, fonts and logo come from the client's reel-profile automatically; nothing is hard-coded.
4. **Arabic first.** Correct RTL, Arabic shaping, mixed AR/EN lines and Arabic numerals choice. This is where his tool is weakest and ours strongest.
5. **Easier.**
   - The style is auto-picked from the content type (story, advice, list, medical claim, etc.).
   - One click to swap the style; sensible defaults so zero settings are needed.
   - Live preview on the GPU.
6. **Better quality.**
   - Native AE layers the editor can still adjust (his output is a flat video).
   - Safe areas per platform.
   - Captions synced to word timing.
   - SFX matched to motion.
7. **Distinctiveness check (gate item).** The brand-systems-designer reviews our render next to his README/demo frames (images only, never running his code) and must answer "recognisably ours, clearly better". If the answer is no, it is a P1 defect.

**What we add that he doesn't have** (filled from the analysis, starting list):
- Podcast → reels selection.
- Medical and religious claim review before graphics.
- Client profiles and reference-style learning.
- Magnific assets.
- Native Premiere/AE round-trip.
- Mac first.

## R3. Feature map (from the evidence report; the full per-feature table goes into the repo name-free as R-T1)
- **His tool:**
  - an assistant-driven reel maker that renders a flat MP4 through Remotion and headless Chrome;
  - Windows-only and CPU-only;
  - 12 looks (only 2 proven by his own words, only 2 brand-aware), 15 motion concepts and 9 semantic scene families;
  - a live browser review editor;
  - strict gates: text fits or the render fails; safe-zone, face, loudness and encode checks.
- **Recommended route (D′):**
  - port the looks and scenes to our AE build and Premiere MOGRTs;
  - add a **Review tab** and a **Settings tab** to our panel, with Premiere's own timeline as the player;
  - rebuild his best engine checks in `reel`.

**3.0 scope:**

| Phase | Task | What we build (ours, evolved) |
|---|---|---|
| 4 | R-4.1 | Caption looks: 3 grouping modes × 3 presentations, word emphasis, per-client auto/fixed preference, HarfBuzz fit-or-fail |
| 4 | R-4.2 | Burned-in caption detection → hide our captions, keep the words for cuts |
| 4 | R-4.3 | Cut proposals v2 inside Hush: retakes, Egyptian filler rules, Arabic normalisation, Premiere markers and a panel list, never past the sign-off |
| 4 | R-4.4 | Intake: real motion rate, VFR→CFR, HDR→SDR, GPU decode |
| 4 | R-4.5 | Platform safe-zone profiles (IG organic and ads, TikTok, Shorts, 4:5), derived by us from official pages, with a basis per number |
| 4 | R-4.6 | Look recommender: content type + client reference + recent-use penalty, with a one-line reason |
| 4 | R-4.7 | Punch-in emphasis scoring (eased, face-safe) and endings-order rules |
| 4 | R-4.8 | Stricter publish-check: no repeating spoken sentences, no cross-platform duplicates, no filler hashtags |
| 6 | R-6.1 | Look system: one named motion law per look, brand-aware for all looks, contrast stepping. Looks LOOK-01, 02, 03, 06, 07, 10 in 3.0 |
| 6 | R-6.2 | AE scene set wave 1 (10 scenes), with AR/EN stills, read-back and face keep-out |
| 6 | R-6.4 | Head keep-out gate in QC read-back (AE and Premiere) |
| 6 | R-6.5 | Panel Review tab: lists → seek, follow mode, stale-save guard, history (in-place forms for every scene type are 3.1) |
| 6 | R-6.6 | Panel Settings/onboarding tab per client |
| 6 | R-6.7 | SFX cue palettes per look, driven by markers |
| 6B | R-6B.1 | Alignment contract in Kalam. Evaluate the Apache-2.0 Arabic wav2vec2 model as the **commercial replacement for the non-commercial MMS aligner** (G3) |
| 7 | R-7.1 | Installer step state machine (key, verify, resume), sha256 for every download, and a branded "proof render" in doctor |
| 9 | R-9.1–9.4 | Identity scan (R5.4), RTL lint, look × scene × AR/EN × brand still matrix, distinctiveness review |

**3.1:**
- LOOK-04, 05, 08, 09, 11, 12;
- scene wave 2;
- screen-recording scene and redaction;
- custom-scene JSON;
- no-recording motion videos;
- chunked NVENC preview cache;
- podcast verified-reuse resume.

**Never adopted:**
- his telemetry;
- his update-by-git-pull from a personal repo;
- the CPU-only paths;
- the Remotion, React and Chrome render path.

**Names:**
- LOOK-01..12 are working codes; the final look names are proposed by the brand-systems-designer and approved by Yunus.
- None of his style names, Arabic labels, font aliases or file names are reused.

## R4. Licence and ownership: everything is ours
1. **`LICENSE` (proprietary)**, at the repo root, in the plugin bundle and in the installers:
   - «Copyright © 2026 The Why Not AI. All rights reserved.»;
   - no copying, redistribution, resale, sublicensing, reverse engineering, removing notices, or bypassing protections;
   - licence to use is granted only by The Why Not AI;
   - governing law: Egypt, courts of Cairo.

   Replaces any open-source licence text of ours.
2. **`EULA.md` (Arabic + English).** Shown and accepted at install, and in the panel's About screen.
   - Pre-release builds add confidentiality: testers may not share builds, screenshots of unreleased features, or files.
   - One plain line mentions the update check (R5.2).
3. **Copyright header.** One short line at the top of every source file we own: «© 2026 The Why Not AI. Proprietary — see LICENSE». CI checks for it.
4. **`THIRD-PARTY-NOTICES.md`.** Only the global components we really ship, each with its licence text, for example:
   - FFmpeg;
   - fonts (OFL);
   - Whisper / CT2 models;
   - any icon set;
   - MediaPipe if used.

   This is legally required, cannot be removed, and names no individual developer of Source-R.
5. **About screen.** Product name, version, «© The Why Not AI», and a link to the EULA and notices.
6. **Legal registration** (recommendations only; Yunus decides, fees apply):
   - **software copyright deposit** in Egypt with ITIDA's software IP protection office (computer programs are protected under Law 82/2002), which gives dated official proof of ownership;
   - **trademark** "WhyNot Cut" and the logo at the Egyptian Trademarks Office; Madrid/WIPO later if selling abroad;
   - **a lawyer** reviews LICENSE/EULA before the sale edition (already H17).

   Until then, the private GitHub history (dated commits, tags and release hashes) is our proof of authorship.

## R5. Detect theft and get an email: free, honest, quiet, never breaks the product
**Update 2026-10-15** (Yunus: «فكك من موضوع الكود المخفي … فكك من فكرة 50 واحد … احنا هنجربها لحد ما نبيعها» · «اتأكد إن الإيميل … دا مش عند صاحب الكود ومن غير ما يبان إنك بتدور أو تعمل حاجة»):
- **Dropped:**
  - hidden code, invisible per-build fingerprints and canary strings;
  - per-tester builds.
- **Testing:** no fixed 50-person beta. We keep testing (internally and with whoever Yunus picks) until the sale edition.
- **G9 tasks:** keep the parts that help reliability (hardware matrix, onboarding sample, update channel, feedback); drop the head count and the invite/key logistics.

Goal: **detect, prove, take down.** Nothing stops a determined thief 100%.

0. **Quiet and independent (binding).**
   - Every alert runs only on **our** accounts and infrastructure: our private repo, our Google account, our PC. It sends only to info@thewhynot.ai. Nothing goes through, links to, or depends on the Source-R author or his repo.
   - Nobody gets notified that we are watching:
     - GitHub code search and Google Alerts notify no one;
     - the developer's GitHub repo is **never accessed online again**: no visit, clone, star, fork, watch, follow, issue or PR. The existing local read-only clone is all we use.
   - Nothing in our product, repo or alerts names him.
1. **GitHub (who touches our code).**
   - The repo stays private, and Yunus's account is the only owner.
   - Branch rules on `main` and `release/*`: no force-push, no deletion. Pushes are still allowed, so the Mac and the executor keep working.
   - Workflow `security-watch.yml`: on any push from an unexpected author, a new collaborator, a deploy key, or a visibility change, it opens an issue assigned to `thewhynotai`, so GitHub emails Yunus immediately.
   - Yunus checks that 2-factor login is on (his step).
2. **Update check that reports misuse.**
   - The normal update check (every serious app has one) sends only: version, OS, a random install ID, and a hash of the installed code. No personal data, files or content.
   - It is answered by a free endpoint (a Google Apps Script web app on the agency's Google account) that emails info@thewhynot.ai when:
     - the code hash doesn't match an official release (a modified copy);
     - installs appear from an unknown or unofficial version;
     - the install count jumps beyond what we handed out.
   - The EULA mentions the update check in one plain line, as every product does. That is required by privacy law, and it doesn't advertise the monitoring.
   - It is fail-open: offline or a timeout never blocks or slows the plugin.
   - This is the **only** exception to D17 (no telemetry). It has no usage stats and no content: just the update check, as decided by Yunus on 2026-10-15.
   - A modified copy shows a calm notice «هذه ليست نسخة رسمية». It never deletes anything or harms the user's machine (that would be illegal for us).
3. **Internet watch.**
   - A weekly wnc-queue job on our PC runs `gh search code` for our product name and our real distinctive module and identifier names (not hidden strings). On any hit outside our repo, it opens a private issue, so Yunus gets an email.
   - Yunus adds free Google Alerts for "WhyNot Cut", "ويناوت كت" and our style names (his step).
4. **Identity check.** A release gate (`tools/release.py`) and CI make sure none of Source-R's identity strings ever appear in our repo or release files.
   - The list is stored **only as salted sha256 hashes of normalised tokens**, so the repo never contains his name, even inside the check.
   - The plain list stays in the evidence folder, outside the repo.
5. **Takedown kit.** `docs/legal/takedown/` has ready templates:
   - a GitHub DMCA notice (free, usually removed in days);
   - a generic hosting/marketplace notice;
   - an Arabic cease-and-desist letter.

   Each lists the evidence to attach: R4.6 proof, commit history, and release hashes.
6. **Making the code harder to lift** (sale edition, only if reliability tests stay green):
   - panel JS bundled and minified;
   - selected engine modules compiled (Nuitka/Cython);
   - release files signed.

   Not in 3.0 if any of it risks errors (G10).

## R6. Tasks (executor schedules them; Phase 4 unless noted)
- **R-T1.** Write the behaviour specs from the analysis (read-only, no code copying). Fill R3.
- **R-T2.** For each style: write the "Our version" spec (R2), then build it natively, then run the distinctiveness gate.
- **R-T3.** Review-editor ideas → our panel and evidence loop.
- **R-T4.** Alignment and face-aware framing in the engine, GPU-first.
- **R-T5.** LICENSE, EULA (AR/EN), headers with a CI check, THIRD-PARTY-NOTICES, About screen.
- **R-T6.** Identity-string CI check.
- **R-T7.** Dropped (per-build fingerprint).
- **R-T8.** `security-watch.yml`, plus branch rules (no force-push or deletion).
- **R-T9.** Update-check misuse reporting, plus the free email endpoint (Phase 8, with the update channel).
- **R-T10.** Weekly wnc-queue internet watch.
- **R-T11.** Takedown kit.
- **R-T12** (sale edition). Minify, compile and sign hardening.
- **Verbatim assets (R1):** unblocked 2026-10-15 (H19 closed by Yunus). Rebuild-first still applies: adopt a verbatim asset only where it beats our own version; never his README or demo media.

## R7. Human items (new)
- **H19. CLOSED 2026-10-15.** Yunus: «فكك من الايميل اعتبره اتبعتلك والموضوع خلص». He holds the developer's assignment in his own records; it is not re-checked by Claude. Keep that email permanently (it is the proof if ownership is ever questioned).
- **H20.** GitHub 2-factor login: **DONE 2026-10-16** (Yunus enabled it; gh token still valid, verified). Branch rules: GitHub Free does not offer protected branches or rulesets on PRIVATE repos (needs GitHub Pro, about $4/month). Free path kept: `security-watch.yml` emails on every push, including force-pushes, plus full local and Mac clones as backups. Pro is optional, Yunus's call.
- **H21. DONE 2026-10-16:** Google Alerts on info@thewhynot.ai, daily digest, for "WhyNot Cut", "WhyNot Kalam", "WhyNot Hush", "WhyNot Tidy" and "thewhynot.ai" -site:thewhynot.ai.
- **H22. DECIDED 2026-10-15:** copyright deposit and trademark are registered in the name of The Why Not AI (thewhynot.ai). Filing (ITIDA, trademark office, lawyer, fees) stays Yunus's.
