# WhyNot Cut 3.0 — Addendum E: design excellence + secure native installers (Windows and macOS)

| | |
|---|---|
| Date | 2026-10-13 |
| Requested by | Yunus, in his words: «الديزاين بتاع البلاجن ان وحش اوي اوي محتاج يبقي احسن من كده بكتير … متناسش برنامج الويندوز برنامج للماك برضو نفس الكلام الاتنين شغالين معمول ليهم كودينج كويس وامان ومفهموش اي حاجه ضد السيكورتي او تضر الجهاز باي شكل ف شوف انهي احسن طريقه» ("the plugin's design is really, really bad and needs to be much better… and don't forget the Windows program and the Mac program, same thing: both well coded and secure, with nothing that works against security or harms the computer in any way, so find the best way to do it") |
| Changes | Strengthens Addendum B (UI/UX) and replaces the installer front-end choice in Addendum D7 (Inno Setup + SwiftUI → **one Tauri app for both OSes**) |
| Standing rules | No approvals from Yunus (decide and continue). Quality over speed |
| Commit | The executor commits this to `docs/superpowers/specs/addendum-e/` (single writer) |

## E1. Design: the problem, and the new bar
**Today:** only the B-T1 foundation exists (tokens, fonts, i18n table). The screens Yunus sees are the dev and spike
panels, never designed. B-T2 (screens) is still "planned", and the design review (B-T6) only happens in Phase 8, which
is too late to steer the design.

**New rule: design first, then code, then prove the code matches the design.**
1. **E-D1 Design direction (lead: the `brand-systems-designer` agent + the `brand-identity-pipeline` skill).**
   Inputs: thewhynot.ai, `brand/`, Addendum B, and the best AI-tool panels (Adobe's own AI Assistant, Frame.io,
   Descript, Runway, Linear-quality UI) as the quality reference only, never copied. Output: a one-page **design
   direction** in `docs/design/direction.md` (mood, type scale, spacing, motion, iconography, voice) with 2–3 visual
   options. The designer agent picks one and states why. No approval stop.
2. **E-D2 High-fidelity mockups of EVERY screen before any more screen code.** These are HTML/CSS prototypes using the
   real tokens and real Arabic/English copy, at 300 / 360 / 480 px wide, in AR and EN:
   - first-run checklist; home (three verbs + tool cards);
   - client picker; pipeline progress;
   - approvals (plan summary, preview, flagged medical/religious lines);
   - QC frames grid; "Needs you";
   - Kalam / Hush / Tidy tabs; models page; settings; Claude/engine status states; every error card;
   - After Effects motion panel;
   - the installer screens (E2).

   Stored in `adobe/panel-ui/design/` and rendered to PNG. They are also published as a private Artifact so Yunus
   can see the direction. That's for visibility only, not an approval gate.
3. **E-D3 Design critique loop:**
   - the designer agent reviews every mockup against a checklist: hierarchy, one primary action, contrast,
     RTL correctness, empty, loading and error states, spacing rhythm, icon consistency, copy clarity, brand fit;
   - at least 2 rounds;
   - a separate "first-time editor" reviewer agent role-plays a non-technical Arabic-speaking editor and flags
     anything confusing.

   Exit when both report no major issues.
4. **E-D4 Build to the mockups.** The B-T2/B-T3/B-T4 screens are implemented from the approved mockups.
5. **E-D5 Visual proof:**
   - automated screenshots of the REAL panel (UXP in Premiere, CEP in After Effects, the installer) at the same
     widths, AR and EN;
   - compared side by side with the mockups, with a visual-diff threshold plus the designer agent's review;
   - every mismatch fixed or written down;
   - the screenshots are viewed one by one.
6. **E-D6 Polish pass:**
   - motion: 150–250 ms ease; progress shimmer; no layout shift;
   - icons: one set, Lucide, already licensed;
   - focus states, hover states, the loading skeletons;
   - Arabic typography: line height, no clipped diacritics;
   - micro-copy in both languages, written as a product writer would.

**Gates.** Phase 6 cannot pass while any screen has no mockup, or any mockup ↔ implementation mismatch is open. The
Phase 8 design review (B-T6) stays as the final check. Usability (B-T7/E19) must show zero «مش فاهم» moments.

## E2. The installer program for Windows and macOS: the best way
**Decision: one native desktop app built with [Tauri 2](https://v2.tauri.app/) ("WhyNot Cut Setup"), the same code
for Windows and macOS. It replaces Inno Setup (Windows) and SwiftUI (macOS) from D7.**

Why Tauri:
- **The same website-look UI on both OSes:** HTML/CSS from `panel-ui` tokens and components. The installer looks like
  the plugin and the site; a stock Inno wizard can't.
- **Small** (~5–15 MB), a native WebView (WebView2 on Windows, WKWebView on macOS), with no bundled Chromium.
- **Security by design:**
  - a Rust core;
  - a capability allowlist (the UI can call only the named commands we define);
  - a strict CSP;
  - no remote content in the UI;
  - an IPC isolation pattern.
- **Packaging:**
  - Windows: an NSIS installer, per-user install, no admin, Authenticode-signed (H4).
  - macOS: a `.app` in a `.dmg`, hardened runtime, Developer ID-signed + notarized (H4).
  - Both: Tauri's updater is signed with our own update key.
- The Rust core runs the **same installer core** (Python bootstrap logic, already built and tested) as a child
  process and shows its JSON progress. No logic is duplicated.

### E2.1 Security rules (binding; verified by tests and a security review)
1. **Least privilege:**
   - per-user only; never asks for admin/root;
   - no services or daemons as SYSTEM/root;
   - no drivers, kernel extensions or browser extensions;
   - writes only under the user's home (`~/.whynot-cut`, per-user fonts, per-user Adobe/Claude folders), the
     HKCU registry (Windows) and `~/Library/LaunchAgents` (macOS).
2. **Never weaken the machine:**
   - never disables or adds exclusions to Defender, SmartScreen, Gatekeeper, SIP, the firewall or UAC;
   - never sets PlayerDebugMode on the normal path;
   - never changes system-wide settings, PATH for all users, or other apps' settings beyond the documented merge
     into `~/.claude/settings.json` (a backup is made first).
3. **Trusted downloads only:**
   - every file is fetched over HTTPS from a fixed allowlist: GitHub Releases of `thewhynotai`, PyPI,
     Hugging Face, NVIDIA's redist, claude.ai/download, Adobe's UPIA;
   - each file is verified against **sha256 in a `components.json` that is itself signed** (minisign/ed25519 key
     held offline by the owner);
   - publisher signatures are checked where they exist (Anthropic's installer, NVIDIA DLLs);
   - **no `curl | bash` or `irm | iex` inside the app.** The one-liners remain only as a documented developer and
     fallback path.
4. **No hidden behaviour:**
   - every action is shown in the checklist and logged to `~/.whynot-cut/logs/install-*.log`;
   - the login item is visible in Windows "Startup apps" / macOS "Login Items" and can be turned off;
   - no telemetry; diagnostics only when the user presses a button, saved locally and redacted.
5. **Clean uninstall:**
   - removes everything we added: plugin, panels, fonts, login item, URL scheme, engine (models only if ticked);
   - never touches client folders;
   - an uninstall test proves the before/after file and registry diff equals our own files only.
6. **Supply chain:**
   - pinned dependency versions + lockfiles (Cargo.lock, package-lock, uv locks with hashes);
   - `cargo audit`, `npm audit`, `pip-audit`, `semgrep` and `bandit` in CI;
   - a CycloneDX SBOM in every release;
   - a secrets scan;
   - reproducible build notes;
   - the release workflow runs on GitHub Actions (private repo), with Windows and macOS runners building and signing.
7. **Pre-release malware check:** every artefact (exe, dmg, ccx, zxp, zip) is scanned with Microsoft Defender locally
   and uploaded to VirusTotal by hash **only after Yunus's OK**, because uploading is publishing. Any detection blocks
   the release until it's explained (false positives get a vendor submission).
8. **Signing:**
   - public builds MUST be signed: Windows OV certificate, Apple Developer ID + notarization (H4);
   - unsigned builds are internal only and labelled "internal" in the UI;
   - `release.py` refuses a public channel without signatures.

### E2.2 Tasks (installer track, after D-T1…D-T9)

| Task | What |
|---|---|
| E-T1 | Tauri 2 app scaffold (`installer/app/`): capability allowlist, CSP, isolation pattern, AR/EN, panel-ui tokens. Screens from the E-D2 mockups |
| E-T2 | Rust ⇄ installer-core bridge (spawn, JSON progress, cancel, resume), no shell string building |
| E-T3 | Signed `components.json` (ed25519/minisign) + verification in core and app; the key stays offline; a CI check that refuses an unsigned manifest |
| E-T4 | "Install Claude for me" with publisher-signature verification (Authenticode / `codesign -dv`) |
| E-T5 | NSIS per-user bundle + uninstaller; macOS dmg + hardened runtime entitlements (no unnecessary entitlements) |
| E-T6 | GitHub Actions release workflow (Windows + macOS runners): build, test, audit, SBOM, sign (when H4), checksums |
| E-T7 | Security tests: a clean-VM install/uninstall diff, no admin prompt, no writes outside the allowlist (file watcher during install), tampered-download rejection, tampered-manifest rejection, offline mode, a Defender scan |
| E-T8 | An independent security review of the installer app + core (Phase 8 T8.2 scope extended) |

D7's Inno Setup and SwiftUI tasks (D-T10, D-T11) are **replaced** by E-T1…E-T5. D-T12…D-T14 stay, implemented inside
the Tauri app.

## E3. Human items
- **H4 (unchanged, now important):** Windows OV code-signing certificate + Apple Developer Program. Without them,
  installers are internal builds only.
- **H15 (new):** keep the update/manifest signing key offline. The executor generates it and stores the private key
  in the OS keychain/credential store. Yunus keeps a backup copy on a USB drive. It is never committed.
