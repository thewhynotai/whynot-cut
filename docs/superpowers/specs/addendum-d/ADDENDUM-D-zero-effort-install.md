# WhyNot Cut 3.0 — Addendum D: zero-effort install, everything included (macOS + Windows)

| | |
|---|---|
| Date | 2026-10-13 |
| Requested by | Yunus, in his words: «اللي هيستخدم البلاجن لما يحملها كل حاجه تشتغل علي كلود وبريمير والموديلز تكون موجوده بكل اشكالها يبقي مش محتاج اي حاجه وقت السيت اب او ال install وتبقي كلها حاجات بتتعمل اوتوماتيك او هو بيسطبها من علي كلود ب اختياريات او تبقي كلها متاحه … واعمله في النسخه الحاليه عشان تبقي بلاجن قويه جدا وتشتغل علي ال mac and windows» ("whoever downloads the plugin gets everything working on Claude and Premiere, with every model available in every form, so they need nothing during setup or install. It's either automatic, or installed from inside Claude with options, or all available… do it in the current version so it's a very strong plugin on Mac and Windows") |
| Builds on | Master plan Phase 7 (installer core T7.1–T7.9, already built: `whynot-cut/installer/`, `-Yes` defaults, location and model questions), Addendum C (one ecosystem: launcher, login item, one panel, first-run checklist) |
| Commit | The executor commits this to `docs/superpowers/specs/addendum-d/` (single writer) |

## D0. What "zero effort" means (and the honest limits)
**Zero required decisions, zero technical steps.** Every question has a default, and the default is the strongest
choice the machine can run, per Yunus's earlier rule. Options exist only on a "Customise" path the editor can ignore.

What can never be automatic. It's the platform, not us. Each item gets one clear screen with one button:
1. Installing the **Claude desktop app and signing in** (Anthropic's login; we may not offer it ourselves).
2. **Adobe Premiere Pro / After Effects** must already be installed with the editor's own licence. Creative Cloud
   desktop must be signed in; the installer starts it if it's closed.
3. **Downloads are big** (runtime + models, see D3). They run in the background with progress and resume. An
   **offline full bundle** covers studios with slow or no internet (D5).
4. **macOS asks once to allow folder access** (Documents or an external drive) when Claude first opens a client
   folder. That's an OS rule. Until the Apple certificate (H4) arrives, the one-liner replaces the double-click app.
5. **Premiere/AE must restart once** after the panels install. Claude or the installer does it under the standing
   permission (test projects or nothing unsaved); otherwise it asks with one button.

## D1. Two front doors, one core, same result
**Door 1: the installer** (one-liner now, double-click app/exe once H4 arrives):
- runs with **no questions by default** (the current `-Yes` behaviour becomes the default for an interactive install
  too). The screen shows "Installing everything WhyNot Cut needs (about N GB). [Customise]";
- Customise opens the existing questions: location, models, language, clients folder, packs. Every one is
  preselected.

**Door 2: from inside Claude** (new): the editor adds the WhyNot Cut marketplace in Claude, a single action
("+ › Plugins › Add plugin" with our URL, or the one command), then types «ثبّت WhyNot Cut» / "install WhyNot Cut" or
`/whynot-cut:start`.
- The start skill detects that nothing is installed and runs the **same installer core** through the shell Claude
  has. Windows uses the PowerShell tool, since Git Bash may not exist yet; the core installs PortableGit for later.
  macOS uses Bash.
- It shows **one** choice card (AskUserQuestion): **"Install everything (recommended)"** preselected, or "Choose
  what to install" (models and packs as a multi-select, all ticked).
- Progress is reported in chat stage by stage. At the end it says what's left (restart Premiere, open a new session)
  and does what it is allowed to.

**Both doors write the same `state.json`**, so `doctor`, the panel and the next session all see the same machine.
Running either door again repairs or updates.

## D2. "Everything works on Claude and Premiere": the checklist the installer finishes on its own
1. The engine runtime (uv + Python 3.12 + the hash-locked runtime for the OS/CPU), ffmpeg, and fonts per user.
2. The Claude plugin installed **and enabled**, the marketplace with `autoUpdate`, plus the permission rules for
   `reel` in the clients folder. The installer asks once ("allow WhyNot Cut to run its engine without asking each
   time?"), default yes. This removes repeated permission prompts.
3. **Windows:** Git Bash (PortableGit per user) + `CLAUDE_CODE_GIT_BASH_PATH`, so the hooks and the guard are always
   active.
4. **Adobe:** the UXP panel in Premiere, the signed CEP panel in After Effects, dev/spike panels removed, Creative
   Cloud started if needed, the UPIA result verified (Addendum C).
5. **The engine always on:** launcher + login item + URL scheme (Addendum C, T7.1 step 7b).
6. **Models: all of them** (D3), downloaded in the background, newest first by need. Editing can start while large
   packs keep downloading.
7. **The first client folder** created with the default clients folder: `D:\WhyNot Clients` when D: exists, else
   `Documents\WhyNot Clients`, outside OneDrive/iCloud. It opens with the "drop your files here" guide.
8. **A new Claude session** opened in the clients folder (deep link if it works, else one button: "Open Claude").
9. **A final `reel doctor`:** every row green, or an amber row with its one-click fix. The result shows in the
   installer, in Claude and in the panel's first-run checklist.

## D3. Models "in every form": all available, the right ones automatic

| Pack | What | Windows | macOS | Default |
|---|---|---|---|---|
| **Core transcription** | Whisper large-v3 (best accuracy) | CTranslate2, CUDA on NVIDIA, CPU otherwise | **MLX** on Apple Silicon, CTranslate2 CPU on Intel | **installed** |
| **Fast transcription** | large-v3-turbo | CT2 | MLX | **installed** (used for first passes and long episodes) |
| **Small models** | medium, small | CT2 | MLX | **available** on demand, auto-used only when disk/RAM is too small |
| **Kalam pack** (captions) | Egyptian-dialect Whisper turbo, Parakeet English, MMS-300m aligner, torch/transformers runtime | CT2 + ONNX + torch CUDA/CPU | MLX + parakeet-mlx + torch | **installed** (Yunus's rule: the strongest, ticked) |
| **Hush fillers** | reuses the Kalam "other" model or the core model | — | — | nothing extra |
| **Fonts** | IBM Plex Sans Arabic, Syne, Inter, IBM Plex Mono (OFL) | per user | per user | **installed** |

- **Every model is listed in a "Models" page** in the panel and in `reel models`, with its state (installed /
  downloading N% / available), size, used-for, Install and Remove buttons, and "Download all".
- **Automatic choice per machine:** the installer reads the GPU (NVIDIA/CUDA, Apple Silicon), RAM and free disk.
  It installs everything that fits. If space is short, it keeps the strongest that fits and says what was skipped and
  how to add it later; it never fails silently.
- **Integrity:** pinned revisions + sha256 in `components.json`. Downloads resume. Hugging Face first, the owner's
  mirror when H3 exists. **Kalam's MLX model is converted on device** by `setup_models.py`, the same as upstream,
  unless the mirror has the converted copy.
- **No model is ever needed at the moment of the editor's first click:** the engine reports "model downloading,
  N min left" and either waits or offers the smaller model that is already there.

## D4. macOS and Windows parity (must pass on both)
- **Per-OS locks** (win-x64, mac-arm64, mac-x64), backends (CUDA/CPU; MLX/CPU), font folders, Adobe paths,
  UPIA paths, the login item (Run key / LaunchAgent), the URL scheme (registry / LSSetDefaultHandler via a tiny
  app bundle).
- **macOS specifics:** no admin, no Xcode CLT, no Homebrew. Gatekeeper-safe one-liner now, a notarized app when H4
  arrives. The folder-access prompt is explained before it appears.
- **Windows specifics:**
  - no admin;
  - Smart App Control detected and explained;
  - Arabic and space usernames;
  - OneDrive-redirected Documents;
  - long paths;
  - PowerShell 5.1 and 7 both supported.
- **Gate:** the full install → first edit flow on Windows (a clean standard user, H10) and macOS (H6). Without a Mac:
  macOS is "Not verified live" in the release notes. Never claimed.

## D5. Offline full bundle (P1)
- `dist/WhyNotCut-3.0.0-full-<os-arch>.zip`: plugin + runtime wheels (wheelhouse) + ffmpeg + all models + fonts +
  panels. The installer core detects it next to itself and installs with **no internet**, except Claude's own login.
- Built by `tools/release.py --full`. Sizes are listed on the download page (H3 hosting, or shared by drive).
  Checksums are verified.

## D6. Tasks (Phase 7, extended; installer track owns them; no new parallel track)

| Task | What |
|---|---|
| D-T1 | Interactive install = no questions by default + a "Customise" path (keep `-Yes`; interactive no longer prompts unless Customise is chosen) |
| D-T2 | Install from inside Claude: the start skill detects "not installed" → runs the core via PowerShell (Windows) / Bash (macOS) → one AskUserQuestion card (Install everything / Choose) → staged progress in chat → final checklist. Works before Git Bash exists |
| D-T3 | Model packs in `components.json` (core, fast, small, Kalam pack) + `reel models list|install|remove|download-all` + panel "Models" page data via the engine |
| D-T4 | Hardware-aware selection + disk-space fallback + background download with resume + "use the model that is ready" logic in transcribe/Kalam |
| D-T5 | Permission rules for `reel` offered and written once (clients folder `.claude/settings.json` merge) |
| D-T6 | First client folder + a new Claude session opened at the end (deep link, measured; else a button) |
| D-T7 | Offline full bundle (`release.py --full`) + offline detection in the core (P1) |
| D-T8 | Tests: core in no-question mode end to end in a sandbox; the AskUserQuestion path mocked; model pack resolution per hardware matrix (NVIDIA / no GPU / M-series / Intel Mac / low disk); resume after an interrupted download; offline bundle install with the network blocked; both doors give an identical `state.json` |
| D-T9 | Live: clean Windows standard user via Door 1 and via Door 2; this PC upgrade 2.2.1 → 3.0; macOS when H6; time to "first edit possible" recorded (target: under 15 min of the editor's attention, downloads excluded) |

## D7. The download people get: `WhyNotCut-Setup.exe` (Windows) and `WhyNotCut.dmg` (macOS), P0 for 3.0
Yunus asked, in his words: «بفكر انه تبقي برنامج صيغه exe للويندوز وهو يعمل كل حاجه» ("I'm thinking it should be a
program in .exe format for Windows that does everything").
- **Windows, `WhyNotCut-Setup.exe`** (Inno Setup, per user, no admin, ~10 MB):
  - a branded wizard in the website look (Addendum B), AR/EN;
  - one screen "Install everything (recommended)" + Customise;
  - a progress/checklist page;
  - it embeds the same core and downloads the rest. With the offline bundle next to it, it installs offline;
  - it registers an uninstaller in Settings ▸ Apps.
- **macOS, `WhyNotCut.dmg`:** "Install WhyNot Cut.app", which runs the same core as the user and shows the same
  checklist. No `.pkg`.
- **"Install Claude for me":** if the Claude desktop app is missing, the installer downloads Anthropic's **official**
  installer from claude.ai/download (HTTPS, publisher signature checked) and launches it. Then it waits for the editor
  to sign in and continues. The sign-in itself stays the editor's.
- **The plugin inside Claude is added by the installer.** No Claude command is needed (Door 2 stays for people who
  start from Claude).
- **Signing:**
  - The exe is built now and works **unsigned for testing**. An unsigned public download shows Windows' "Windows
    protected your PC" (More info ▸ Run anyway) and never builds SmartScreen reputation.
  - For the public release: an **OV code-signing certificate** (H4). Azure Artifact Signing is not available for
    Egypt.
  - macOS needs the **Apple Developer Program** for a notarized app (H4). Until then, macOS users get the one-liner.
  - The release checklist blocks a "public" release of an unsigned exe/dmg; internal/agency builds may be unsigned.
- **Download page:** two buttons (Windows / Mac) on thewhynot.ai (Framer) linking to the hosted files with sha256
  (H3), plus the offline bundles and the Arabic guide PDF.
- **Tasks:**
  - **D-T10:** Inno Setup wizard + branding + an AR/EN checklist UI over the core's JSON progress + uninstaller entry.
  - **D-T11:** the macOS app wrapper (SwiftUI or AppleScript) + dmg layout.
  - **D-T12:** "Install Claude for me" (download, signature check, launch, wait for sign-in).
  - **D-T13:** signing hooks in `release.py` (signtool / codesign + notarytool), a no-op until certs exist.
  - **D-T14:** download page content.
  - **Tests:** a silent install mode for CI (`/VERYSILENT` equivalent → the core's `-Yes`), an uninstall leaves
    client folders untouched, and the unsigned-build warning is documented in the guide.

**Gates:** Phase 7 gate + Addendum C scenarios E1–E20 + D-T8/D-T9. A first-time editor follows the Arabic guide's
install chapter and never types a command except the one-liner (Door 1) or the one sentence in Claude (Door 2).
