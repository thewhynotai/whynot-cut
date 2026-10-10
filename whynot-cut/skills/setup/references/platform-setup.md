# Platform setup reference (macOS and Windows)

## Where things live

| | macOS | Windows |
|---|---|---|
| Engine home (venv, models, queue) | `~/.whynot-cut` | `%USERPROFILE%\.whynot-cut` |
| Engine Python | `~/.whynot-cut/venv/bin/python` | `%USERPROFILE%\.whynot-cut\venv\Scripts\python.exe` |
| `reel` wrapper | `bin/reel` (bash) | `bin/reel` (Git Bash) and `bin/reel.cmd` (PowerShell/cmd) |
| Premiere bridge panel | `~/Library/Application Support/Adobe/CEP/extensions/ai.thewhynot.cut.bridge` | `%APPDATA%\Adobe\CEP\extensions\ai.thewhynot.cut.bridge` |
| Bridge logs | `~/Library/Logs/CSXS/CEPHtmlEngine*-PPRO-*.log` | `%TEMP%\CEPHtmlEngine*-PPRO-*.log` |
| PlayerDebugMode | `defaults read com.adobe.CSXS.12 PlayerDebugMode` | `reg query HKCU\Software\Adobe\CSXS.12 /v PlayerDebugMode` |
| Fonts checked | `~/Library/Fonts`, `/Library/Fonts`, `/System/Library/Fonts` | `C:\Windows\Fonts`, `%LOCALAPPDATA%\Microsoft\Windows\Fonts` |
| Adobe apps found in | `/Applications/Adobe <App> 20xx/` | `C:\Program Files\Adobe\Adobe <App> 20xx\` |
| Arabic text renderer for stills | CoreText (installed font), else HarfBuzz | HarfBuzz + FreeType from the client's font file |
| Face-aware photo crops | Vision framework | OpenCV face detector |
| AE / PS extras | AppleScript `DoScriptFile` | `AfterFX.exe -r`, Photoshop COM `DoJavaScriptFile` |
| Camera RAW photos | `sips` | `rawpy` if installed, else export JPEGs |

Set `WHYNOT_HOME` (or the plugin option `engine_home`) to move the engine home, e.g. to a bigger drive. The bridge
finds a moved home through `bridge-config.json`, which `reel setup` writes into the panel folder.

## Symptom → cause → fix

| Symptom | Cause | Fix |
|---|---|---|
| `"blocked": "WhyNot Cut engine not installed"` | No venv yet | `reel setup` (ask first: ~400 MB) |
| `no Python 3.9+ found` | Fresh machine | Windows: `winget install Python.Python.3.12`; macOS: `xcode-select --install` |
| Windows: `python3` opens the Microsoft Store | Store alias stub on PATH | The wrappers skip it; install real Python (above) or disable the alias in Settings › Apps › App execution aliases |
| pip fails building `numpy`/`av` | Python too new for the pinned wheels | Use Python 3.10–3.12 and run `reel setup` again |
| Bridge missing in Window › Extensions | Premiere was open during install, or PlayerDebugMode off | Editor sets PlayerDebugMode, quits and reopens Premiere |
| `ppro-status` alive false with a stale heartbeat | Panel closed or Premiere busy with a dialog | Bring Premiere to the front, dismiss dialogs; reopen Window › Extensions › WhyNot Cut Bridge |
| Transcription very slow on Windows | CPU only | NVIDIA GPU with CUDA 12 runtime makes it automatic; else set preferences `whisper_model: large-v3-turbo` |
| `GPU transcription failed … retrying on CPU` in the log | cuDNN/cuBLAS DLLs missing | Harmless (CPU used). For GPU speed install NVIDIA's CUDA 12 + cuDNN 9 runtime |
| Arabic letters isolated in a still | Pillow fallback used (no HarfBuzz and no exact CoreText font) | `reel doctor` → `uharfbuzz`/`freetype` must be True; `reel setup` |
| Brief `.docx`/`.pdf` read as empty | Older engine | Engine 2.x reads `.docx`, `.rtf`, `.pdf` on both systems (`pypdf`) |
| `Fonts not installed` in client-db | Brand fonts only in `assets/Fonts` | Editor installs them; previews still render from the files, Premiere needs them installed |
| Arabic in output shows as `?` in a terminal | Console code page | Engine forces UTF-8 output; use the Bash or PowerShell tool output, not an old cmd window |
