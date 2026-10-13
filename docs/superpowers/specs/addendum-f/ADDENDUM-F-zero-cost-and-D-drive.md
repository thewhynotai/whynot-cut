# WhyNot Cut 3.0 — Addendum F: zero-cost policy + everything on drive D

| | |
|---|---|
| Date | 2026-10-13 |
| Requested by | Yunus, in his words: «مش عاوز اي حاجه ادفع فيها فلوس شوف الحلول المناسبه واعملها علي طول وحطها في الخطه ورتب كل حاجه» ("I don't want anything I have to pay for. Find the suitable solutions, do them right away, put them in the plan and organise everything"). Also: «عاوز كلود يشتغل علي ال d … لو دا مش هينفع يبقي لما تخلص البروجكت تنقل كل حاجه وتسيب الداتا الضروريه علي ال c» ("I want Claude to work on D… if that's not possible, move everything when the project is finished and leave only the essential data on C") |
| Overrides | H4 (paid certificates) is **dropped**. Addendum E's "public builds must be signed" becomes the F1 distribution rules below |
| Commit | The executor commits this to `docs/superpowers/specs/addendum-f/` |

## F1. Zero-cost policy: nothing in 3.0 needs a payment
| Need | Free solution (decided) |
|---|---|
| **Windows install without a scary warning** | **Primary: the one-line installer** (`irm … \| iex` from `dl.thewhynot.ai`); it doesn't trigger SmartScreen. **Double-click option: Microsoft Store** (MSIX: Microsoft signs it, and individual developer registration is free). The Store build is a P1 investigation: does it fit the full-trust Store rules for installing per-user runtimes, fonts and Adobe panels? If it doesn't fit, it's dropped. The unsigned Tauri exe stays **internal only** (agency PCs), labelled "internal" |
| **macOS install** | **The one-line installer** in Terminal (no Gatekeeper prompt). There is no free notarization. The unsigned `.app`/`.dmg` is internal only (developer test). The Arabic guide explains the Terminal step with screenshots |
| **Update integrity** | Our own ed25519 keys (primary + backup), free (Addendum E3) |
| **Hosting** | GitHub: a private source repo + a public releases-only repo + a `dl` CNAME (free) |
| **CI on Mac and Windows** | GitHub Actions free minutes. macOS jobs cost 10× minutes, so the macOS suite runs **only on phase tags and release candidates** (stays within the free 2,000 minutes a month). Windows tests run locally |
| **Security scanning** | Microsoft Defender (built in), `pip-audit`/`npm audit`/`cargo audit`/`semgrep`/`bandit` (free), VirusTotal by hash (free; uploading only with Yunus's OK on release day) |
| **AI buttons in the panel** | Default backend = the open Claude Code session on Yunus's existing subscription. The API-key backend exists but is off unless he adds a key |
| **Magnific** | His existing account. Auto-spend = 0; spending only with the approval gate |
| **Models, fonts, libraries** | All free and open (Whisper/MIT, Parakeet, MMS, OFL fonts, Lucide ISC) |
| **Cloudflare** | Not used |

**Release rule:** `release.py` publishes **one-liners + plugin zip + the PDF** publicly. The exe/dmg are attached as
"internal" builds only, until a free signing route exists (the Store for Windows) or Yunus decides otherwise later.

## F2. Drive D: Claude and the project live on D
**Done now by the plan session (2026-10-13), per user and reversible.** Script: `D:\ClaudeData\move-caches-to-D.ps1`
(with `-Undo`); log: `D:\ClaudeData\move-caches.log`.
- These user environment variables now point to `D:\ClaudeData\…`: `HF_HOME`, `PIP_CACHE_DIR`, `UV_CACHE_DIR`,
  `npm_config_cache`, **`TEMP` and `TMP`** (`D:\ClaudeData\Temp`).
- They take effect for apps started from now on. **The Claude desktop app keeps the old TEMP until it restarts**;
  after a restart, Claude's own temp and scratch files go to D. The watchdog resumes the sessions after a restart.
- The existing caches were moved to D. The Hugging Face snapshot links don't survive a move, so the two old faster-whisper
  snapshots (duplicates of the engine's models) were parked in `D:\ClaudeData\DevCache\_hf-broken-snapshots-2026-10-13`
  and will be re-downloaded only if something needs them.
- C free: 54.8 → 61.4 GB.

**F2-T1 (executor, at the next phase boundary, i.e. the Phase 3 gate close):** move the engine home to D.
1. Stop `reel serve`. Make sure no tests or Adobe jobs are running.
2. `robocopy /E /MOVE` `C:\Users\LOQ\.whynot-cut` → `D:\ClaudeData\whynot-cut-home`.
3. Create a **directory junction** `C:\Users\LOQ\.whynot-cut` → `D:\ClaudeData\whynot-cut-home`. Every existing path
   keeps working: the CEP bridge config, plugin-options, login items, the installed plugin cache. No config edits, no
   duplicate data.
4. Restart the daemon, then run `reel doctor`, the bridge heartbeat, and the full suite.

About 4.7 GB today, about 15 GB after the Kalam pack.

**F2-T2 (executor, now):** the test runners (`tools/test.ps1`/`.sh`) and subagent test commands set
`TEMP`/`TMP` = `D:\ClaudeData\Temp\wnc-tests` for their own process, so test temp goes to D immediately without waiting
for an app restart.

**F2-T3 (product):** the installer's engine-home default prefers a **non-system drive** when the system drive has less
than 30 GB free and another fixed drive has more. It's shown under Customise, and the reason is explained in one line.
This is added to Addendum D (D-T4).

**F2-T4 (at project end, Phase 11):** move Claude's own data with Claude **closed**, using a one-click script that
runs at the next logon before Claude starts (a scheduled task, one-shot):
- move `C:\Users\LOQ\.claude` (about 1.2 GB), `%APPDATA%\Claude` (about 1.3 GB) and the old
  `%LOCALAPPDATA%\Temp\claude` (about 7 GB) to `D:\ClaudeData\…`, with junctions back at the original paths;
- only Windows/app essentials stay on C;
- verify that Claude starts and the sessions list is intact; keep a rollback (junction removal + move back).

## F3. What only Yunus can do (it's about 2 minutes, and it frees ~34 GB)
After Effects' disk cache is **33.7 GB** in `%LOCALAPPDATA%\Temp\Adobe\After Effects` (it filled up during the motion
tests). Adobe preferences are Yunus's own (Claude never edits Adobe preferences):
- **After Effects:** Edit ▸ Preferences ▸ Media & Disk Cache ▸ Disk Cache folder → `D:\ClaudeData\AdobeCache\AE`,
  then **Empty Disk Cache**.
- **Premiere:** Edit ▸ Preferences ▸ Media Cache → location `D:\ClaudeData\AdobeCache\Premiere`, then **Delete**
  unused cache files.
