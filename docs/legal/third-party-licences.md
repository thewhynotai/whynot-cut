# WhyNot Cut: third-party licences (G-T2, pre-sale checklist)

**Status:**
- Audit of `release/3.0`, done 2026-10-14 against HEAD `938da30`.
- Task G-T2 (Addendum G §G3, as changed by §G8 and §G10).
- **This is not legal advice.** Yunus or a lawyer approves before anything is sold (H17).

**How to read this file:**
- **v3.0.0 is the full trial edition (G8).** Every component below stays in 3.0, including the MMS-300m aligner and a full GPL FFmpeg. Nothing is swapped for licence reasons in 3.0.
- This file is the **pre-sale checklist** for the **commercial edition**, which starts only on Yunus's word.
  - Every row with *Commercial OK = no* or *unknown* is listed in §3 with its replacement or the licence needed. It must be closed before the commercial edition ships. G3's gate moved there.
  - Nothing here is a 3.0 blocker.
- **Commercial OK** means: may this be used in, or alongside, a product sold for money in our setup? It is yes, no or unknown.
- **Where from** is one of:
  - *bundled*: in our repo, plugin or ZXP/CCX;
  - *install*: downloaded by our installer;
  - *runtime*: downloaded by the engine on first use;
  - *runtime lock*: a PyPI wheel installed by uv from our hash lock on the user's machine;
  - *customer's own*: a service or app the customer brings;
  - *dev-only*: never shipped.
- **How licences were checked:**
  - Python wheels: the `METADATA` / `licenses/` of the installed runtime `~/.whynot-cut/runtimes/r-6e4a68a292b4` (built from `setup/locks/runtime-win-x64.lock`), plus the PyPI JSON API.
  - Models: the Hugging Face model API (`cardData.license`) and the model cards.
  - Other components: the GitHub `LICENSE` files and the build provider pages.
  - The FFmpeg licence and configure flags of the bundled libraries were read from the binaries themselves (`avutil_license()`, `ffmpeg -version`).
  - No model weights or binaries were downloaded for this audit.

## 1. Summary

| Rows in §2 | Commercial OK = yes | no | unknown |
|---|---|---|---|
| All 78 rows | 73 | 1 | 4 |
| The 71 rows that ship with or are used by the product (dev-only and absent rows left out) | 66 | 1 | 4 |

**The 5 open rows, in priority order (details in §3):**
1. The MMS-300m aligner is **CC-BY-NC-4.0**.
2. The training data of the Egyptian Whisper fine-tune is undisclosed.
3. Anthropic's/OpenAI's terms for a sold product driving Claude Code or Codex (H14) are unconfirmed.
4. The PyAV wheel puts GPL x264/x265 inside our engine process.
5. Magnific's terms are unverified.

## 2. Inventory

Licences are SPDX ids. `LicenseRef-*` marks a non-SPDX (proprietary or service) licence.

### 2.1 Models

| # | Component | Version | Where from | Licence | Commercial OK? | Attribution? | Action | Evidence |
|---|---|---|---|---|---|---|---|---|
| M1 | Whisper large-v3, CTranslate2 (`Systran/faster-whisper-large-v3`) | HF rev `edaa852e` (latest; `components.json` revision is `<release>`) | runtime (HF, `reel model-download` / first transcription) | MIT. The base `openai/whisper-large-v3` card says Apache-2.0; OpenAI's GitHub LICENSE is MIT. Both are permissive | yes | yes (MIT notice: Systran + OpenAI) | Pin the revision at release | https://huggingface.co/Systran/faster-whisper-large-v3 · https://huggingface.co/openai/whisper-large-v3 · https://github.com/openai/whisper/blob/main/LICENSE |
| M2 | Whisper large-v3-turbo, CTranslate2 (`mobiuslabsgmbh/faster-whisper-large-v3-turbo`) | HF rev `0a363e91` | runtime (HF) | MIT | yes | yes | **The repo moved.** The HF API now redirects it to `dropbox-dash/faster-whisper-large-v3-turbo`. Update the id in `components.json` / `whisper_backends.py` and pin the revision, so a dropped redirect never breaks downloads | https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo |
| M3 | Whisper large-v3, MLX (`mlx-community/whisper-large-v3-mlx`) | HF rev `49e6aa28` | runtime (HF, Apple Silicon) | MIT | yes | yes | Pin the revision | https://huggingface.co/mlx-community/whisper-large-v3-mlx |
| M4 | Whisper large-v3-turbo, MLX (`mlx-community/whisper-large-v3-turbo`), used by Hush and by Kalam "other" on Mac | HF rev `a4aaeec0` | runtime (HF, Apple Silicon) | MIT, inherited: the card states no licence, and it is a conversion of `openai/whisper-large-v3-turbo` (MIT) | yes | yes (OpenAI MIT notice) | Commercial edition: convert it ourselves from `openai/whisper-large-v3-turbo`, as `setup_models.py` already does for CT2, so the licence chain is explicit | https://huggingface.co/mlx-community/whisper-large-v3-turbo · https://huggingface.co/openai/whisper-large-v3-turbo |
| M5 | Whisper large-v3-turbo source weights (`openai/whisper-large-v3-turbo`), converted to CT2 by the Kalam setup | HF rev `41f01f3f` | install (Kalam pack build) | MIT | yes | yes | None | https://huggingface.co/openai/whisper-large-v3-turbo |
| M6 | Whisper medium / small fallbacks (`Systran/faster-whisper-{medium,small}`, `mlx-community/whisper-{medium,small}-mlx`) | HF revs `08e178d4`, `536b0662`, `7fc08c4e`, `45f39159` | runtime (only if chosen) | MIT. The Systran cards say MIT; the mlx-community cards state none and inherit OpenAI MIT | yes | yes | None | https://huggingface.co/Systran/faster-whisper-medium |
| M7 | **Egyptian-dialect Whisper turbo fine-tune** (`oddadmix/whisper-large-v3-turbo-arabic-dialectal`), Kalam Arabic default. Converted at release to CT2 fp16 and MLX fp16, so we redistribute derivatives | HF rev `cb15abb9` | install (Kalam pack) | Apache-2.0 per the card, on base `openai/whisper-large-v3-turbo` (MIT). **Training data:** `oddadmix/dialectal-arabic-lahgtna-v2-smaller-augmented`, which the card itself calls "**private**". The HF API returns 401 for it. The author's public audio collections built from named podcasts are tagged `license:other` | **unknown** | yes (Apache-2.0 NOTICE + OpenAI MIT) | See §3 #2 | https://huggingface.co/oddadmix/whisper-large-v3-turbo-arabic-dialectal · https://huggingface.co/api/datasets?author=oddadmix |
| M8 | **MMS-300m CTC forced aligner** (`MahmoudAshraf/mms-300m-1130-forced-aligner`), Kalam word timing for all languages, via `torchaudio.functional.forced_align` | HF rev `49402e95` | install (Kalam pack) | **CC-BY-NC-4.0**. The base `facebook/mms-300m` is also CC-BY-NC-4.0 | **no** | yes | Kept in 3.0 (G8). Commercial edition: replace it (§4) | https://huggingface.co/MahmoudAshraf/mms-300m-1130-forced-aligner · https://huggingface.co/facebook/mms-300m |
| M9 | Parakeet TDT 0.6B v2: `nvidia/parakeet-tdt-0.6b-v2`, `mlx-community/parakeet-tdt-0.6b-v2` (Mac) and `istupakov/parakeet-tdt-0.6b-v2-onnx` (portable), Kalam English | HF revs `ae9ad070` / `8ae15530` / `0bbb45a3` | install (Kalam pack) | CC-BY-4.0 on all three | yes | **yes**, required by CC-BY: credit NVIDIA, link the licence, state that the model was converted (MLX/ONNX) | Put it in the About screen + `THIRD_PARTY_NOTICES` (§7) | https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2 · https://huggingface.co/istupakov/parakeet-tdt-0.6b-v2-onnx |
| M10 | Silero VAD v6 (`faster_whisper/assets/silero_vad_v6.onnx`, inside the faster-whisper wheel), episode VAD | as shipped in faster-whisper 1.2.1 | runtime lock | MIT | yes | yes | None | https://github.com/snakers4/silero-vad/blob/master/LICENSE |

No other VAD or denoise models are used:
- Dialogue cleanup is FFmpeg DSP (`afftdn`, `agate`, `highpass`/`lowpass`, `alimiter`, `loudnorm`).
- RNNoise, DeepFilterNet, pyannote and Demucs are not referenced anywhere in the code (`git grep`).

### 2.2 Binaries and services

| # | Component | Version | Where from | Licence | Commercial OK? | Attribution? | Action | Evidence |
|---|---|---|---|---|---|---|---|---|
| B1 | **FFmpeg + ffprobe**. Windows: gyan.dev static (HEAD pins `essentials`; G8 target is `full`). macOS: Martin Riedl static | 9.0.2, pinned by sha256 | install (provider URL) | GPL-3.0-or-later. gyan.dev: "All builds are 64-bit, static and licensed as GPLv3"; the macOS builds include x264/x265 | yes, as a separate program with GPL obligations (copyleft note below) | yes | 3.0: switch the Windows pin to `full_build` per G8 (the sha256 is in `ffmpeg/NOTICE.md`); keep the GPL text + `SOURCE.txt`. Commercial edition: see §5 | https://www.gyan.dev/ffmpeg/builds/ · https://ffmpeg.martin-riedl.de/ · `docs/legal/ffmpeg/NOTICE.md` |
| B2 | FFmpeg inside the `imageio-ffmpeg` wheel (`ffmpeg-win-x86_64-v7.1.exe`, gyan.dev 7.1 essentials, `--enable-gpl --enable-version3`), a fallback binary | 7.1 (wheel 0.6.0) | runtime lock | GPL-3.0-or-later (binary); BSD-2-Clause (wrapper) | yes (subprocess) | yes | Commercial edition: optionally drop `imageio-ffmpeg` from the lock, since B1 is always installed; that's one GPL binary less to document | `ffmpeg -version` of the installed file · https://github.com/imageio/imageio-ffmpeg |
| B3 | uv | 0.13.0 | install (GitHub release, sha256-pinned) | MIT OR Apache-2.0 | yes | yes | None | https://github.com/astral-sh/uv/blob/main/LICENSE-MIT |
| B4 | CPython runtime (python-build-standalone, fetched by uv) | 3.12.15 | install | PSF-2.0, plus the licences of its bundled libraries (OpenSSL Apache-2.0, libffi MIT, SQLite blessing, zlib, bzip2, xz, Tcl/Tk; each distribution ships its licence files). The build scripts are MPL-2.0 and are not shipped | yes | yes (PSF notice) | Carry the Python licence in THIRD_PARTY_NOTICES | https://docs.python.org/3/license.html · https://github.com/astral-sh/python-build-standalone |
| B5 | Git for Windows (PortableGit), installed only when Git Bash is missing, for Claude Code on Windows | 2.56.0.windows.2 | install (upstream GitHub release, sha256-pinned) | GPL-2.0 (plus component licences) | yes. It is a separate program fetched from upstream, and we don't modify or host it | yes (name + licence) | If we ever host it: add the source offer. Otherwise none | https://github.com/git-for-windows/git/blob/main/COPYING |
| B6 | NVIDIA cuBLAS 12 (`reel gpu-enable`: the NVIDIA redist, or the `nvidia-cublas-cu12` wheel) | 12.9.1(.4) | runtime (on demand, from NVIDIA / PyPI) | LicenseRef-NVIDIA-CUDA-EULA (proprietary; cuBLAS is a listed redistributable) | yes | Notice per the EULA | Never host it ourselves without re-reading the EULA attachment A | https://docs.nvidia.com/cuda/eula/index.html |
| B7 | **Claude Code / Codex CLI** (the agent backend), and the Anthropic API that Kalam's correction step calls | customer's current version | customer's own account | LicenseRef-Anthropic-Terms / LicenseRef-OpenAI-Terms | **unknown** | n/a | §3 #3 (H14) | https://www.anthropic.com/legal/commercial-terms · https://www.anthropic.com/legal/consumer-terms |
| B8 | **Magnific** (image/video generation used by the plugin's motion/thumbnail features) | n/a | customer's own account | LicenseRef-Magnific-Terms | **unknown** | n/a | §3 #5 | Not yet read; Magnific's own terms page |
| B9 | Adobe Premiere Pro / After Effects with the UXP and CEP APIs | customer's own | customer's own licence | LicenseRef-Adobe-Terms | yes. Commercial third-party extensions are a normal Adobe use | no | Before an Adobe Marketplace (Exchange) listing, read the Adobe Developer Distribution terms | https://developer.adobe.com/ |
| B10 | ZXPSignCmd (signs the CEP bridge ZXP) | 4.1.3 (Adobe-CEP/CEP-Resources @ `8897cfaf`) | dev-only (release tooling) | LicenseRef-Adobe: the repo has **no LICENSE file** (GitHub API `license: null`) | yes. Adobe publishes it for exactly this purpose; we only run it and never redistribute it | no | None | https://github.com/Adobe-CEP/CEP-Resources |

### 2.3 Python engine runtime (`setup/locks/runtime-*.lock`, Python 3.12)

All of these are PyPI wheels installed on the user's machine by uv from the hash lock (*runtime lock*). WhyNot Cut does not host them (`components.json` `runtime.index_url: null`).

| # | Package | Version | Licence (wheel metadata) | Commercial OK? | Attribution? | Copyleft / bundled-native note |
|---|---|---|---|---|---|---|
| P1 | anyio | 4.15.1 | MIT | yes | yes | |
| P2 | arabic-reshaper | 3.0.0 | MIT | yes | yes | |
| P3 | **av (PyAV)** | 19.0.1 | BSD-3-Clause (bindings). The bundled `av.libs` FFmpeg DLLs report "LGPL version 3 or later", but the same wheel ships `libx264-165*.dll` and `libx265*.dll`, which are GPL-2.0-or-later, and avcodec is configured `--enable-libx264 --enable-libx265 --enable-version3` | **unknown** | yes | It is **in-process**: our engine imports `av`, so GPL code is loaded into the same process as proprietary code. See §3 #4 |
| P4 | certifi | 2026.7.22 | MPL-2.0 | yes | yes | MPL is file-level copyleft. We use it unmodified, so the only duty is to keep the notice and point to the source |
| P5 | click | 8.5.0 | BSD-3-Clause | yes | yes | |
| P6 | colorama (Windows) | 0.4.6 | BSD-3-Clause | yes | yes | |
| P7 | ctranslate2 | 4.8.2 | MIT | yes | yes | |
| P8 | faster-whisper | 1.2.1 | MIT | yes | yes | Contains Silero VAD (M10) |
| P9 | filelock | 4.1.1 | MIT | yes | yes | |
| P10 | flatbuffers | 25.12.19 | Apache-2.0 | yes | yes | |
| P11 | fonttools | 4.66.1 | MIT | yes | yes | |
| P12 | freetype-py | 2.5.1 | BSD-3-Clause; the bundled FreeType is FTL OR GPL-2.0-or-later | yes (we take FTL) | yes. The FTL requires the credit "Portions of this software are copyright © The FreeType Project (www.freetype.org)" | |
| P13 | fsspec | 2026.9.0 | BSD-3-Clause | yes | yes | |
| P14 | h11 | 0.16.0 | MIT | yes | yes | |
| P15 | hf-xet | 1.7.0 | Apache-2.0 | yes | yes | |
| P16 | httpcore | 1.0.9 | BSD-3-Clause | yes | yes | |
| P17 | httpx | 0.28.1 | BSD-3-Clause | yes | yes | |
| P18 | huggingface-hub | 1.33.0 | Apache-2.0 | yes | yes | |
| P19 | idna | 3.20 | BSD-3-Clause | yes | yes | |
| P20 | imageio-ffmpeg | 0.6.0 | BSD-2-Clause (wrapper) | yes | yes | Its GPL binary is row B2 |
| P21 | numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0, plus bundled OpenBLAS (BSD-3-Clause) and libgfortran (GPL-3.0-or-later WITH GCC-exception-3.1) | yes | yes | The GCC Runtime Library Exception allows proprietary use |
| P22 | onnxruntime | 1.31.0 | MIT | yes | yes | |
| P23 | opencv-python-headless (Windows/Linux) | 4.14.0.94 | Apache-2.0, plus `opencv_videoio_ffmpeg4140_64.dll` (FFmpeg, LGPL-2.1, per `LICENSE-3RD-PARTY.txt`) | yes | yes | LGPL as a separate replaceable DLL: compliant as shipped by PyPI |
| P24 | packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | yes | yes | |
| P25 | pillow | 12.3.0 | MIT-CMU | yes | yes | |
| P26 | protobuf | 7.36.2 | BSD-3-Clause | yes | yes | |
| P27 | pypdf | 6.20.0 | BSD-3-Clause | yes | yes | |
| P28 | python-bidi | 0.6.11 | LGPL-3.0-or-later (classifier LGPL; `COPYING.LESSER` v3) | yes | yes | LGPL: we use it unmodified as a separately installed module that the user can replace, and we don't distribute it. If we ever bundle it, ship the LGPL text and keep it replaceable |
| P29 | PyYAML | 6.0.3 | MIT | yes | yes | |
| P30 | tokenizers | 0.23.3 | Apache-2.0 | yes | yes | |
| P31 | tqdm | 4.70.1 | MPL-2.0 AND MIT | yes | yes | Same as certifi |
| P32 | typing_extensions | 4.16.0 | PSF-2.0 | yes | yes | |
| P33 | uharfbuzz | 0.56.3 | Apache-2.0 (bundled HarfBuzz: MIT-style "Old MIT") | yes | yes | |
| P34 | pyobjc-core + frameworks Cocoa, CoreML, CoreText, Quartz, Vision (macOS) | 11.1 | MIT | yes | yes | |

### 2.4 Kalam pack (planned lock `setup/locks/kalam-<platform>.lock`, portability audit N5; not locked yet)

These packages are not locked yet. The versions are the PyPI latest on 2026-10-14; lock them when N5 is built.

| # | Package | Version | Licence | Commercial OK? | Attribution? | Note |
|---|---|---|---|---|---|---|
| K1 | torch | 2.14.1 | Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT (PyPI) | yes | yes | The CUDA wheels carry NVIDIA redistributables (B6 terms) |
| K2 | torchaudio | 2.11.0 | BSD-2-Clause | yes | yes | **Not a licence issue but a blocker for N5:** `torchaudio.functional.forced_align`, which Kalam's `align.py` calls, was deprecated in 2.8 and **removed in 2.9**. Pin `torchaudio` 2.8.x or move the Viterbi out of torchaudio (§4) |
| K3 | transformers | 5.19.0 | Apache-2.0 | yes | yes | |
| K4 | soundfile | 0.14.0 | BSD-3-Clause; the bundled libsndfile is LGPL-2.1-or-later | yes | yes | LGPL as a separate shared library: fine |
| K5 | onnx-asr | 0.12.0 | MIT | yes | yes | |
| K6 | anthropic (SDK) | 1.13.0 | MIT | yes | yes | The API service itself is B7 |
| K7 | mlx + mlx-metal (macOS) | 0.32.3 | MIT | yes | yes | |
| K8 | mlx-whisper (macOS) | 0.4.3 | MIT | yes | yes | |
| K9 | parakeet-mlx (macOS) | 0.5.3 | Apache-2.0 | yes | yes | |

### 2.5 npm / TypeScript (`adobe/package-lock.json`, workspaces `panel-ui`, `premiere-uxp`)

The shipped UXP/CEP bundles contain **only our own code**. No npm package is imported by `adobe/*/src`. `adobe/cep-bridge` has no package.json and no third-party JS: it uses `window.__adobe_cep__` directly and does not ship `CSInterface.js`.

| # | Component | Version | Where from | Licence | Commercial OK? | Attribution? | Note |
|---|---|---|---|---|---|---|---|
| N1 | fflate | 0.8.3 | dev-only (it is a `dependency`, but it is imported only by `scripts/package-ccx.mjs` and `dev-install.mjs`, so it never lands in the CCX) | MIT | yes | no (not shipped) | If it is ever bundled into the panel, add its MIT notice |
| N2 | Dev group: typescript 7.0.2 (+ `@typescript/*` natives), `@adobe/premierepro` 26.5.0 (types), esbuild 0.28.2 (+ `@esbuild/*`), ajv 8.20.0, ajv-formats 3.0.1, fast-deep-equal 3.1.3, json-schema-traverse 1.0.0, require-from-string 2.0.2, `@types/node` 26.6.5, undici-types 8.9.0, fast-uri 3.1.8 | as listed | dev-only | Apache-2.0 (typescript, @adobe/premierepro); BSD-3-Clause (fast-uri); MIT (the rest) | yes | no | No copyleft in the npm tree |

### 2.6 Rust crates / Tauri installer app

| # | Component | Version | Where from | Licence | Commercial OK? | Attribution? | Note |
|---|---|---|---|---|---|---|---|
| R1 | Tauri installer app | none at HEAD | n/a | n/a | yes (nothing to audit) | n/a | The repo has no `Cargo.toml`, `Cargo.lock`, `tauri.conf.json` or installer `package.json` at `938da30`; the installer is Python + PowerShell/sh. Audit it with `cargo about` / `cargo deny check licenses` when it is added |

### 2.7 Fonts and icons

| # | Component | Version | Where from | Licence | Commercial OK? | Attribution? | Action | Evidence |
|---|---|---|---|---|---|---|---|---|
| F1 | Syne | static Bold (repo); variable `Syne[wght]` (install) | bundled (`adobe/panel-ui/fonts`, `guide-ar/fonts`) + install (google/fonts @ `bd8f81dd`) | OFL-1.1 | yes | yes (ship `OFL.txt`) | None | `guide-ar/fonts/syne/OFL.txt` · https://github.com/google/fonts/tree/main/ofl/syne |
| F2 | Inter | static Regular/SemiBold/Bold; variable (install) | bundled + install | OFL-1.1 | yes | yes | None | `guide-ar/fonts/inter/OFL.txt` |
| F3 | IBM Plex Sans Arabic | Thin–Bold | bundled + install | OFL-1.1, **Reserved Font Name "Plex"** | yes | yes | Never ship a subset or modified Plex under a name containing "Plex" | `guide-ar/fonts/ibmplexsansarabic/OFL.txt` |
| F4 | IBM Plex Mono | Regular–Bold | bundled + install | OFL-1.1, RFN "Plex" | yes | yes | As F3 | `guide-ar/fonts/ibmplexmono/OFL.txt` |
| F5 | Alexandria | SemiBold–Black | bundled (guide only) | OFL-1.1 | yes | yes | None | `guide-ar/fonts/alexandria/OFL.txt` |
| F6 | Lucide icons (+ Feather-derived icons) | lucide-static 1.47.0 | bundled (`templates/motion/icons/lucide`, 2,112 SVGs) | ISC (Lucide); MIT (Feather subset) | yes | yes; already in `whynot-cut/THIRD_PARTY_NOTICES.md` | Keep the notice | `whynot-cut/templates/motion/icons/lucide/LICENSE` |

### 2.8 Dev-only Python tooling (grouped; never shipped)

| # | Component | Version | Licence | Commercial OK? | Note |
|---|---|---|---|---|---|
| D1 | pytest (Kalam upstream tests) | 9.1.1 | MIT | yes | |
| D2 | pypdfium2 (`guide-ar/render_pages.py`) | 5.14.0 | Apache-2.0 OR BSD-3-Clause (+ PDFium BSD-3-Clause) | yes | |
| D3 | rawpy (optional engine extra; not in any lock) | 0.27.1 | MIT; the bundled LibRaw is LGPL-2.1 OR CDDL-1.0 | yes | If it is ever added to a lock, note LibRaw in the notices |

### 2.9 Our own code and assets

| # | Component | Where | Licence | Commercial OK? | Action |
|---|---|---|---|---|---|
| O1 | WhyNot Cut engine, skills, agents, panels, bridge, installer, guide | whole repo | LicenseRef-Proprietary (`whynot-cut/LICENSE`, © The Why Not AI) | yes | None |
| O2 | Kalam / Hush / Tidy original source (`adobe/tools/*/_upstream`) and their ports | bundled (ported) | LicenseRef-Proprietary, per the **owner's statement** (§6). Not independently verified | yes, per the owner's statement | §6: signed statement |
| O3 | Brand assets (`brand/logo.svg`, `logo.png`, `tokens.css`), synthesized SFX | bundled | LicenseRef-Proprietary | yes | None |

**Row count:**
- §2 has 78 rows: M1–M10, B1–B10, P1–P34, K1–K9, N1–N2, R1, F1–F6, D1–D3 and O1–O3. P34 counts the pyobjc group as one row, and N2 is one grouped dev row.
- **All 78 rows:** yes 73 · no 1 (M8) · unknown 4 (M7, B7, B8, P3).
- **The 71 rows that ship with or are used by the product** (excluding the dev-only or absent rows B10, N1, N2, R1 and D1–D3): yes 66 · no 1 · unknown 4.

### 2.10 Copyleft items: does our distribution trigger obligations?

| Item | Licence | In our setup | Obligation |
|---|---|---|---|
| FFmpeg (B1) | GPL-3.0-or-later | Separate program run by subprocess. The installer downloads it from the provider; in a commercial edition we may host it | Notice, licence text, source link/offer (`ffmpeg/NOTICE.md`). No obligation reaches our code, because it is mere aggregation |
| FFmpeg in imageio-ffmpeg (B2) | GPL-3.0-or-later | Separate program; the wheel comes from PyPI | Same as B1 if we ever host the wheel |
| PyAV wheel with libx264/libx265 (P3) | GPL-2.0-or-later (x264/x265) inside an LGPL-3.0 FFmpeg | **In-process** with proprietary Python. The wheel comes from PyPI on the user's machine, so we don't distribute it today | Unclear. GPL governs distribution, and a commercial "runtime pack" we host would distribute it. See §3 #4 |
| Git for Windows (B5) | GPL-2.0 | Separate program from upstream | None while we don't host it |
| python-bidi (P28) | LGPL-3.0-or-later | Separate replaceable module from PyPI | Keep it replaceable; ship the LGPL text if bundled |
| OpenCV's FFmpeg DLL (P23), libsndfile (K4), LibRaw (D3) | LGPL-2.1 | Separate shared libraries inside PyPI wheels | Fine as shipped; ship the notices if bundled |
| certifi, tqdm (P4, P31) | MPL-2.0 | Unmodified | Keep the notices; disclose source only for modified MPL files |
| libgfortran in numpy (P21) | GPL-3.0 WITH GCC-exception-3.1 | Runtime library | The exception removes copyleft for our use |
| whisper-timestamped (rejected candidate, §4) | AGPL-3.0 | Not used | Must **not** be adopted |

## 3. Pre-sale checklist: the open rows (priority order)

Close every item before the **commercial edition** ships (G8). None blocks 3.0.

1. **M8: MMS-300m aligner, CC-BY-NC-4.0 (no).**
   - Replace it with a permissively licensed aligner that proves equal or better word timing on the Kalam eval set (§4).
   - Plan: run the §4 bake-off as a Phase 6B eval task. Ship the winner in the commercial Kalam pack, and delete the MMS repo from `setup_models.py` / `align.py` / doctor in that edition.
   - Until then, the commercial edition can't ship Kalam word timing.
   - Fallback if no candidate passes: license MMS from Meta commercially. No public path is known; ask Meta.
2. **M7: Egyptian Whisper fine-tune (unknown).**
   - The weights are Apache-2.0 per the card, but the training set is private, and the author's sibling public datasets are scraped podcasts tagged `license:other`. A licence is only as good as the licensor's rights in the data.
   - Plan, in order:
     - (a) Ask oddadmix in writing to confirm the training data's provenance and commercial rights, and for a commercial grant or warranty. Pin revision `cb15abb9`.
     - (b) If there is no clear answer, replace it with our own Egyptian fine-tune of `openai/whisper-large-v3-turbo` (MIT), trained only on data we hold rights to: Yunus's client footage with consent, Common Voice Arabic (CC0-1.0), MASC (CC-BY-4.0), FLEURS (CC-BY-4.0). The card's own `train.py` / `FINETUNE.md` recipe applies.
     - (c) Interim fallback: `openai/whisper-large-v3-turbo` or large-v3 (MIT), at a known WER cost on Egyptian dialect. The card reports 0.590 zero-shot vs 0.344 fine-tuned on its own test set.
   - Gate: the commercial Egyptian model must be within 2 points WER of M7 on the Kalam eval set.
3. **B7: Claude Code / Codex driven by a sold product (unknown; H14).**
   - Each customer uses their own Claude (or Codex) account. WhyNot Cut never shares Yunus's subscription.
   - Plan:
     - Get a written answer from Anthropic (and OpenAI for Codex) on whether a paid third-party plugin may drive a customer's own Claude Code session, and whether consumer plans (Pro/Max) or only commercial plans (Team/Enterprise/API) are allowed for business use.
     - Write the result into the EULA and the setup guide.
   - Kalam's correction step calls `api.anthropic.com` with the customer's own key, which falls under Anthropic's Commercial Terms. Confirm that in the same H14 answer.
4. **P3: PyAV wheel bundles GPL x264/x265 in our process (unknown).**
   - Measured: `avcodec_configuration()` of the installed `av` 19.0.1 wheel shows `--enable-libx264 --enable-libx265`, and `av.libs` contains `libx264-165*.dll` and `libx265*.dll`.
   - Today PyPI distributes it, not us, but a commercial runtime pack hosted by us would.
   - Plan, preferred first:
     - (a) Remove `av` from the engine. Decode audio with the external FFmpeg (B1) into numpy (`ffmpeg -f f32le -ac 1 -ar 16000 -`) and pass arrays to faster-whisper (it accepts numpy input). Port `media.py`, `media_util.py`, `audio_clean.py` and `premiere_xml.py` probes to `ffprobe -print_format json`.
     - (b) Or pin an LGPL-only PyAV build without x264/x265. Either build it from source against an LGPL FFmpeg (`pip install av --no-binary av`), or use the separately published LGPL wheels (PyPI `pyav`); verify their `avcodec_configuration()` first.
   - Gate: `python -c "import av; ..."` is absent, or the configuration shows no GPL libraries.
5. **B8: Magnific terms (unknown).**
   - Each customer connects their own Magnific account; never Yunus's.
   - Plan: read Magnific's terms (API/MCP) to confirm that use from a third-party paid tool on the customer's own account is allowed, and record the URL and date here.

Not blockers, but do them in the commercial edition:
- M2: move to the `dropbox-dash` repo id.
- M4: self-convert the MLX turbo model.
- B2: drop `imageio-ffmpeg`.
- Pin every model revision (`components.json` still says `<release>`).
- K2: pin torchaudio 2.8.x or move the Viterbi out of torchaudio.

## 4. MMS aligner replacement (commercial edition)

**What MMS does today** (`adobe/tools/kalam/_upstream/engine/kalam/align.py`):
1. Every transcribed word (Arabic, English or other) is **romanized** with a hand table to MMS's Latin character vocabulary.
2. MMS-300m CTC emissions are computed on windows of 25 s or less.
3. `torchaudio.functional.forced_align` + `merge_tokens` place each word.
4. Scripts the romanizer can't read keep Whisper's own times.

So the replacement has to give Arabic word timing at least as good as MMS, and handle English and "other" too.

| Candidate | Licence chain (checked) | Arabic support | Expected word-timing quality | Integration |
|---|---|---|---|---|
| **A. `jonatasgrosman/wav2vec2-large-xlsr-53-arabic`** (recommended first) | Model Apache-2.0 (HF rev `af46c2d8`). Base `facebook/wav2vec2-large-xlsr-53` Apache-2.0. Fine-tune data: Common Voice 6.1 Arabic (CC0-1.0) + Arabic Speech Corpus (`halabi2016/arabic_speech_corpus`, CC-BY-4.0, needs a credit line). The XLSR-53 *pre-training* audio (MLS, Common Voice, BABEL per the XLSR paper) is covered by Meta's Apache-2.0 release of the weights | Arabic-script character vocabulary, so the romanization hack goes away (better for Egyptian words the table maps poorly, e.g. ق/ج). Trained on MSA; card WER 39.6 % / CER 18.2 % on CV, which matters less for alignment than for ASR | Character-level CTC like MMS: typically 20–50 ms median boundary error on clean speech. It is the default Arabic align model in WhisperX (BSD-2-Clause). Risk: dialectal or fast speech | Drop-in: same `Wav2Vec2ForCTC` loader and CTC Viterbi as today. Change `REPO`, replace `roman()` with Arabic normalization (strip tashkeel, unify alef/hamza/ta-marbuta) to the model vocab |
| A2. `elgeish/wav2vec2-large-xlsr-53-arabic` | Apache-2.0 (rev `b5e6df14`); same base; CV 6.1 + Arabic Speech Corpus | As A | As A | As A (second XLSR contender) |
| A3. `arbml/wav2vec2-large-xlsr-53-arabic-egyptian` | Apache-2.0 (rev `d21ab2f8`); card lists only `common_voice` | Claims Egyptian, but the card's eval block is a template ("Common Voice ???") | Unproven | As A; include only if A/A2 fail on Egyptian |
| *Rejected:* `omarxadel/wav2vec2-large-xlsr-53-arabic-egyptian` | **CC-BY-NC-4.0**, MGB-3 data | | | Non-commercial |
| *Rejected:* `IbrahimAmin/egyptian-arabic-wav2vec2-xlsr-53` | Tagged Apache-2.0, but its **base is omarxadel (CC-BY-NC-4.0)** and its data includes YouTube and MGB-3 | | | Licence chain broken |
| **B. NVIDIA FastConformer Arabic, CTC head** (`nvidia/stt_ar_fastconformer_hybrid_large_pc_v1.0`) + **NeMo Forced Aligner** | Model CC-BY-4.0 (rev `3e748b4d`; card: "ready for commercial and non-commercial use"). Data: MASC 690 h (CC-BY-4.0) + Common Voice 17 Arabic (CC0-1.0) + FLEURS (CC-BY-4.0). NeMo / NFA Apache-2.0. Avoid the `_pcd_` variant: it adds `tarteel-ai/everyayah`, whose licence is unstated | Arabic script with punctuation; 760 h. The card warns of weaker dialect performance | Strong acoustic model (CTC WER 11–12 %), but BPE tokens make boundaries coarser than characters. NFA gives word times from the CTC head. Expect parity with MMS, but it must be measured | Heavy: `nemo-toolkit` (large deps) or export the CTC head to ONNX and run our own Viterbi. Needs a CC-BY credit |
| **C. Whisper cross-attention + DTW: `stable-ts`** | MIT (GitHub LICENSE; PyPI 2.19.1). Works with faster-whisper, HF and MLX backends; `align()` aligns a known transcript | Any language Whisper speaks, so it covers English and "other" | Generally a bit coarser than CTC (Whisper's 20 ms frames plus attention smear); stable-ts adds silence snapping. Good as a **universal fallback** | Light: reuses the Whisper we already load. Pair it with the Whisper model whose licence is cleared (MIT turbo) |
| *Rejected:* `whisper-timestamped` | **AGPL-3.0** (GitHub LICENSE; PyPI metadata says GPLv3) | | | Copyleft would cover our engine |
| D. `torchaudio.functional.forced_align` with a permissive model | torchaudio BSD-2-Clause | Model-dependent (A/B) | Same as the model | **Deprecated in 2.8, removed in 2.9.** Pin `torchaudio==2.8.*`, or use the Viterbi from `ctc-forced-aligner` (BSD-2-Clause; its README warns its *default* model is CC-BY-NC, so use it with model A) |
| E. CTC-segmentation (`ctc-segmentation`) | Apache-2.0 (GitHub LICENSE) | Model-dependent (A/B) | Built for long audio with an imperfect transcript, and robust to Whisper errors; per-word confidence scores | Light (Cython). Good partner for A when windows are long |
| English | `facebook/wav2vec2-base-960h` (Apache-2.0, LibriSpeech CC-BY-4.0), or Parakeet's own word timestamps (CC-BY-4.0, already loaded) | | Character CTC (WhisperX default) | Replaces MMS for English |

**Recommended stack to test first:**
- Arabic: **A** (`jonatasgrosman/wav2vec2-large-xlsr-53-arabic`) through the existing CTC path, with D (pinned torchaudio 2.8, or ctc-forced-aligner's Viterbi).
- English: `wav2vec2-base-960h`.
- Other languages: stable-ts DTW.
- **B** (FastConformer + NFA) is the second Arabic contender in the bake-off.

A is first because:
- every link in its licence chain is permissive and verified (Apache-2.0 weights on an Apache-2.0 base; CC0 + CC-BY-4.0 data);
- it is a one-file change in `align.py` (same loader, same Viterbi);
- it removes the romanization step that is MMS's weakest point on Arabic;
- it is the WhisperX default, which is real-world evidence.

**Eval plan (Phase 6B task, commercial edition):**
1. **Eval set:**
   - The H13 clips plus at least 30 min of Egyptian Arabic talking-head (client footage with consent), 10 min of English, and 5 min of code-switched AR/EN.
   - Hand-label word onsets and offsets for at least 1,500 Arabic and 500 English words in Praat or Audacity label tracks. Two annotators label 10 % of the words to measure agreement; the target is a median disagreement of 20 ms or less.
   - Store the labels in `whynot-cut/evals/kalam-align/` (no client audio committed; reference by hash).
2. **Runs:** run the same Whisper transcript through MMS (baseline), A, A2, B, and C. Each run is a `KALAM_ALIGNER=<id>` switch in `align.py`.
3. **Metrics** per language:
   - median and p90 |onset error| and |offset error|;
   - % of words within 50 ms and within 100 ms;
   - % of captions whose in/out land within 1 frame (40 ms at 25 fps) of the label;
   - the share of words falling back to a score of 0 or 0.5;
   - CPU and GPU time per audio minute.
4. **Pass:** the candidate is **equal or better than MMS** on median *and* p90 onset error *and* % within 50 ms, for Arabic and English, with no caption-rule regressions.
   - It also keeps the existing `compare_backends.py` bar (median onset diff 0.08 s or less).
   - It stays within the Kalam speed budget on CPU-only Windows and on Apple Silicon.
5. **Decision:** the winner replaces MMS in the commercial Kalam pack. If none passes, ship B or A with the best score only after Yunus accepts the measured gap in writing; otherwise go to §3 #1's fallback.

## 5. FFmpeg

**3.0 (trial edition, G8):**
- The strongest full GPL build, pinned by version + sha256:
  - Windows: gyan.dev `full_build` 9.0.2. **Action:** HEAD still pins `essentials_build`; switch the pin to full, with the sha256 in `ffmpeg/NOTICE.md`.
  - macOS: Martin Riedl static 9.0.2 (arm64 / x64), which includes x264/x265.
- Run as a separate program by subprocess.
- The GPL obligations are in `docs/legal/ffmpeg/NOTICE.md`, with the licence text in `docs/legal/ffmpeg/COPYING.GPLv3`.

**What the engine uses from FFmpeg** (`git grep` of `whynot-cut/engine`):
- **Encoders:**
  - `libx264` (GPL): `preview_video.py`, `reels.py`, `motion_render.py`, `motion_animatic.py`;
  - `aac` (native, LGPL);
  - `pcm_s16le` / `pcm_s24le` (LGPL);
  - stream `copy`.
- **Audio filters (all native, LGPL):** `afftdn`, `agate`, `highpass`, `lowpass`, `alimiter`, `loudnorm`, `ebur128`, `astats`, `aformat`, `aresample`, `pan`.
- **Video filters:** `scale`, `fps`, `pad`, `crop`, `setpts`, `select`, `concat`, `overlay`, `unsharp` (LGPL), and `drawtext` (LGPL, needs libfreetype; `ref_analysis.py` already retries without it).
- **No GPL-only filter is used** (no `cropdetect`, `eq`, `hqdn3d`, `vidstab`, `frei0r`, …).
- **So the only GPL-only dependency is `libx264`.**

**Commercial-edition note (LGPL path, only if the lawyer prefers it over the subprocess-GPL setup):**
- **Windows:** BtbN `lgpl` variant (win64 and winarm64). It "omits GPL-only libraries, most notably libx264 and libx265" (https://github.com/BtbN/FFmpeg-Builds). Pin it by sha256 like today.
- **macOS:** BtbN doesn't build for macOS, and Martin Riedl offers no LGPL variant. evermeet.cx couldn't be reached on 2026-10-14 (DNS failure), and third-party READMEs describe it as Intel-only and GPL. So **we would build our own LGPL static arm64/x64 FFmpeg in CI** (configure without `--enable-gpl`/`--enable-nonfree`; with VideoToolbox, AudioToolbox and libfreetype) and pin it by sha256.
- **The user's own FFmpeg** via `WHYNOT_FFMPEG` stays supported in every edition.
- **Replacements for `libx264`** (encoder chosen per machine, falling back down this list):
  - Windows: `h264_nvenc` (NVIDIA), `h264_amf` (AMD), `h264_qsv` (Intel), `h264_mf` (Media Foundation, any Windows 10/11);
  - macOS: `h264_videotoolbox`;
  - anywhere: `libopenh264` (BSD-2-Clause; Cisco's binary carries the patent licence) as a last resort.
  - Our previews and reel proxies are viewing copies, so hardware encoders at a matched bitrate are acceptable. Re-check the preview-size and speed budgets.
- **Audio:** native `aac` stays. `libfdk_aac` is never used (nonfree).
- **Also needed in the commercial edition:** P3 (PyAV) and B2 (imageio-ffmpeg) must follow the same choice (§3 #4).

## 6. Fonts

| Font | Licence | App bundling / embedding terms |
|---|---|---|
| Syne, Inter, Alexandria | SIL OFL 1.1 | OFL §2: the font may be "bundled, embedded, redistributed and/or sold with any software", provided each copy carries the copyright notice and the licence. It may not be sold by itself. Embedding in PDFs (the guide) and in rendered stills is "document" use and isn't restricted |
| IBM Plex Sans Arabic, IBM Plex Mono | SIL OFL 1.1 with **Reserved Font Name "Plex"** | Same as above. A modified version, including a subset or webfont conversion we make, **must not use the name "Plex"**. We ship IBM's TTFs unmodified, so this is fine; keep it that way |

**thewhynot.ai brand fonts:**
- The brand type system (`brand/tokens.css`) is **Syne (display), Inter (UI), IBM Plex Sans Arabic (Arabic), IBM Plex Mono (mono)**. All are OFL-1.1 Google Fonts, installed per user by the installer from `google/fonts` @ `bd8f81dd` with their `OFL.txt` (sha256-pinned in `components.json`).
- **Software embedding is allowed.** No commercial or foundry brand font is in the product.
- The guide's `"WNC Head Num"` is a CSS alias of unmodified Inter files restricted with `unicode-range`. It is not a modified font, so OFL renaming does not apply.

**Client fonts** (for example `Cairo-*` in the fictional `profiles/example-clinic`) are supplied by the customer for their own client. The EULA should say the customer must hold the rights to fonts and assets they add.

## 7. Attribution

### 7.1 About screen (panel "About" and installer "About"; short form)

> WhyNot Cut © 2026 The Why Not AI. All rights reserved.
>
> Built with open-source software and models: FFmpeg (GPL-3.0-or-later, run as a separate program; source at
> ffmpeg.org), OpenAI Whisper (MIT), faster-whisper and CTranslate2 (MIT), NVIDIA Parakeet TDT 0.6B v2 (CC BY 4.0,
> © NVIDIA, converted to MLX/ONNX), Silero VAD (MIT), Python (PSF), uv (MIT/Apache-2.0), PyAV, NumPy, Pillow,
> OpenCV, HarfBuzz, FreeType, ONNX Runtime and Hugging Face libraries, fonts Syne, Inter, IBM Plex and Alexandria
> (SIL Open Font License 1.1) and Lucide icons (ISC). Portions of this software are copyright © The FreeType
> Project (www.freetype.org). Full notices: Settings → Licences (THIRD_PARTY_NOTICES).

3.0 only, while the MMS aligner ships, add:
> Word alignment uses MMS-300m (CC BY-NC 4.0, © Meta Platforms) — non-commercial use only; the trial edition is
> not sold.

### 7.2 `THIRD_PARTY_NOTICES` (full form)

**Build it with a script at release:**
- For every wheel in the platform lock, take `dist-info/licenses/*`.
- Add the `components.json` licences (the fonts' `OFL.txt` are already pinned there).
- Then add the sections below, each with its full licence text.

The current `whynot-cut/THIRD_PARTY_NOTICES.md` only covers Lucide; extend it with:

```text
FFmpeg 9.0.2 — GPL-3.0-or-later. Copyright (c) the FFmpeg developers. Run as a separate program.
  Source: https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz — details: docs/legal/ffmpeg/NOTICE.md;
  licence: docs/legal/ffmpeg/COPYING.GPLv3.
OpenAI Whisper (model weights large-v3, large-v3-turbo) — MIT. Copyright (c) 2022 OpenAI.
faster-whisper — MIT. Copyright (c) 2023 SYSTRAN. CTranslate2 — MIT (copyright line from its LICENSE file).
Whisper CTranslate2/MLX conversions (Systran, dropbox-dash/mobiuslabsgmbh, mlx-community) — MIT.
NVIDIA Parakeet TDT 0.6B v2 — CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). © NVIDIA Corporation.
  Source: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2 . Changes: converted to MLX (mlx-community) and ONNX
  (istupakov) formats; no other changes.
whisper-large-v3-turbo-arabic-dialectal (oddadmix) — Apache-2.0 [3.0 trial; see pre-sale item M7].
MMS-300m forced aligner (MahmoudAshraf, from facebook/mms-300m) — CC BY-NC 4.0 [3.0 trial only; not in the
  commercial edition].
Silero VAD — MIT. Copyright (c) 2020-present Silero Team.
Python 3.12 — PSF License Agreement. uv — MIT OR Apache-2.0, Copyright (c) Astral Software Inc.
PyAV — BSD-3-Clause (bundled FFmpeg libraries LGPL-3.0-or-later; x264/x265 GPL-2.0-or-later).
python-bidi — LGPL-3.0-or-later (installed unmodified as a separate, replaceable module).
certifi, tqdm — MPL-2.0 (source: https://github.com/certifi/python-certifi , https://github.com/tqdm/tqdm).
FreeType (via freetype-py) — FreeType License: "Portions of this software are copyright © The FreeType Project
  (www.freetype.org). All rights reserved."
HarfBuzz (via uharfbuzz) — MIT ("Old MIT"). OpenCV — Apache-2.0 (its FFmpeg DLL LGPL-2.1).
NumPy — BSD-3-Clause (OpenBLAS BSD-3-Clause; libgfortran GPL-3.0 with GCC Runtime Library Exception 3.1).
Pillow — MIT-CMU. ONNX Runtime — MIT. huggingface_hub, tokenizers, hf-xet, transformers — Apache-2.0.
[Kalam pack] PyTorch — BSD-style (see its LICENSE/NOTICE); torchaudio — BSD-2-Clause; soundfile — BSD-3-Clause
  (libsndfile LGPL-2.1-or-later); onnx-asr, mlx, mlx-whisper, anthropic — MIT; parakeet-mlx — Apache-2.0.
Git for Windows (installed only when missing) — GPL-2.0, https://github.com/git-for-windows/git .
NVIDIA cuBLAS (optional GPU support) — NVIDIA CUDA Toolkit EULA, https://docs.nvidia.com/cuda/eula/ .
Fonts: Syne © The Syne Project Authors; Inter © The Inter Project Authors; IBM Plex Sans Arabic and IBM Plex Mono
  © IBM Corp., Reserved Font Name "Plex"; Alexandria © The Alexandria Project Authors — SIL Open Font License 1.1.
Lucide icons — ISC, © Lucide Icons and Contributors; Feather-derived icons — MIT, © 2013-present Cole Bemis.
Arabic Speech Corpus (if aligner candidate A ships) — CC BY 4.0, Nawar Halabi.
```

Every Apache-2.0 component that ships a `NOTICE` file needs that file reproduced (Apache-2.0 §4(d)). The release
script should collect `NOTICE*` from each wheel's `dist-info`.

## 8. Owner's rights statement (record; action item)

Yunus (owner, The Why Not AI) **states** that he holds the rights to his own code, including WhyNot Kalam, WhyNot Hush and WhyNot Tidy (`adobe/tools/*/_upstream`, H12 "confirmed" in `adobe/tools/README.md`) and the rest of WhyNot Cut. Source: Addendum G §G8, 2026-10-14: «انا معايا حقوق كل حاجه» ("I hold the rights to everything").

This audit records that statement. **It has not been independently verified.**

**Action (before the commercial edition):** a signed and dated statement in `docs/legal/` by the rights holder, approved by a lawyer (H17). It must cover:
- authorship or ownership of Kalam/Hush/Tidy and any contractor contributions (assignments);
- that no third-party code was copied into them;
- the licence under which The Why Not AI uses them.

The statement does **not** cover third-party models or libraries. Those are settled by this file (G8).
