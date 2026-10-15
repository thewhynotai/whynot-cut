<!-- interim (G3 review I2); the installer track replaces this with its D-T2 text -->
# Installing WhyNot Cut from inside Claude

Use this when `reel doctor` (or `reel setup`) answers `engine not installed` or `no Python 3.9+ found` on a machine
where WhyNot Cut was never installed. `<ROOT>` is the plugin folder the start skill named (it holds `installer/` and
`bin/`).

The installer that ships with the plugin brings everything itself: a pinned uv and a private Python 3.12 (downloaded
over HTTPS and checked against their sha256), the engine, ffmpeg, the panel fonts and the Whisper model. It installs
for this user only. **Never** send the editor to Xcode tools (`xcode-select`), Homebrew, winget or python.org, and never
pipe a downloaded script into a shell.

## 1. Ask once
One AskUserQuestion, Arabic first when the editor writes Arabic:
- question: «أثبّت WhyNot Cut على الجهاز دلوقتي؟ حوالي 4 جيجا (أغلبها نموذج التفريغ) و5 لـ20 دقيقة، من غير صلاحيات
  أدمن.» / "Install WhyNot Cut on this computer now? About 4 GB (mostly the transcription model), 5 to 20 minutes, no
  admin rights."
- options: «ثبّت دلوقتي (موصى به)» / "Install now (recommended)" · «مش دلوقتي» / "Not now".

Ask them to quit Premiere Pro and After Effects first (the panel files are replaced). "Not now": stop here.

## 2. Run the installer in the background
Run it with `run_in_background` (downloads take longer than a tool call may wait). macOS, with the Bash tool:
```bash
bash "<ROOT>/installer/core/bootstrap.sh" --plugin-root "<ROOT>" --yes --skip claude </dev/null
```
Windows, with the PowerShell tool:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<ROOT>\installer\core\bootstrap.ps1" -PluginRoot "<ROOT>" -Yes -Skip claude
```
Exactly these flags. `claude` is always skipped (the plugin is already installed, and that step could replace the
folder the installer runs from). Never add `--customise`, `--home`, `--uninstall` or any `WNC_TEST_*` variable.

While it runs, read its output about every 30 seconds and post one short line per new `== step ==` (Arabic first), not
one per check. The full log is `<engine home>/logs/install-YYYYmmdd-HHMMSS.log` (engine home: normally
`~/.whynot-cut`, on Windows `%USERPROFILE%\.whynot-cut`).

## 3. When it ends: what to tell the editor
- **0, done:** «التثبيت خلص.» Show the checklist it printed (amber rows say what is left). Run `reel doctor` and go on
  with Step 1 of the start skill; green steps are ticked, not repeated.
- **1, a step failed:** show the red rows and the log path in plain words; offer to run it again once (a re-run repairs
  and skips what is done). Twice red: spawn `whynot-cut:setup-doctor` with the output.
- **2, could not start (nothing was downloaded):** show the installer's message exactly as printed, English and
  Arabic: it names the one fix (free disk space, another folder for the engine, …). Run it again after the fix.
- **3, a download or check failed:** «التحميل وقف أو الملف اللي نزل مش مطابق.» Ask them to check the internet, then run
  it again once; give the log path.

Afterwards `reel` works in this session. Premiere needs one restart to load the panel. If `reel doctor` shows
`guard_active: false` (Windows that had no Git Bash before), ask the editor to restart Claude Code once.
