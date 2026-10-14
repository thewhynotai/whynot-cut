# FFmpeg in WhyNot Cut: notice, source and how we run it

WhyNot Cut uses **FFmpeg** (https://ffmpeg.org), a program by the FFmpeg developers. The builds WhyNot Cut uses
include GPL components (libx264, libx265 and others), so those binaries are licensed under the
**GNU General Public License, version 3 or later** (GPL-3.0-or-later). The licence text is in `COPYING.GPLv3`
next to this file. It is the unmodified text from https://www.gnu.org/licenses/gpl-3.0.txt, sha256
`3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`. It is byte-identical to
`whynot-cut/installer/licenses/GPL-3.0.txt`, which the installer copies next to the binaries.

FFmpeg is free software. WhyNot Cut doesn't modify it. You may get, change and share FFmpeg under the GPL; nothing in the
WhyNot Cut licence limits that.

## 1. Which build

The pin lives in `whynot-cut/setup/components.json` (`ffmpeg`). That file is the source of truth: version, URL, size
and sha256 per platform.

| Platform | Build | Provider page | Licence |
|---|---|---|---|
| Windows x64 | **FFmpeg 9.0.2, gyan.dev static build.** HEAD pins the `essentials_build` zip: `https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip`, sha256 `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba`, 114,768,076 bytes. **Addendum G8 target:** the `full_build` zip of the same release, `https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-full_build.zip`, sha256 `759d0a9831c436a0eb331ad36f236c06cb04aaa0005da46571f0e9d3d9206f6b` (GitHub's asset digest), 257,736,868 bytes. Re-check the digest when the pin is switched | https://www.gyan.dev/ffmpeg/builds/ ("All builds are 64-bit, static and licensed as GPLv3") | GPL-3.0-or-later |
| macOS arm64 | FFmpeg 9.0.2, Martin Riedl static build: `https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2/ffmpeg.zip` (sha256 `c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924`) and `.../ffprobe.zip` (sha256 `fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6`) | https://ffmpeg.martin-riedl.de/ (build includes x264 and x265) | GPL-3.0-or-later (it includes GPL libraries) |
| macOS x64 | FFmpeg 9.0.2, Martin Riedl static build: `https://ffmpeg.martin-riedl.de/download/macos/amd64/1789931006_9.0.2/ffmpeg.zip` (sha256 `7c6b4125b191cbf773832dc51f424cf2b6bb7da43007d1e066f95909e47cacd4`) and `.../ffprobe.zip` (sha256 `2322438ed2f6319a691291b247d09c69dcaa3a982460d1f269a7e1af335cfdfd`) | https://ffmpeg.martin-riedl.de/ | GPL-3.0-or-later |

Other FFmpeg copies in the engine runtime:
- `imageio-ffmpeg` 0.6.0 brings `ffmpeg-win-x86_64-v7.1.exe`, a gyan.dev 7.1 essentials build with `--enable-gpl --enable-version3`. It's the last-but-one fallback in `ffmpeg_choice()`.
- `av` (PyAV) 19.0.1 brings FFmpeg shared libraries (`av.libs/avcodec-63*.dll` etc., reporting "LGPL version 3 or later") together with `libx264` and `libx265` DLLs, which are GPL-2.0-or-later.

Both come from PyPI, installed on the user's machine by uv from the hash lock.

## 2. Corresponding source code

- **FFmpeg 9.0.2 source:** https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz. Checked 2026-10-14: HTTP 200. The same URL is `ffmpeg.source` in `components.json`.
- **Exact commit of the gyan.dev 9.0.2 release build:** https://github.com/FFmpeg/FFmpeg/commit/946fcce07b, linked as "source code" from https://www.gyan.dev/ffmpeg/builds/.
- **Library versions and configure flags of each build:** run `ffmpeg -version` and `ffmpeg -buildconf` on the installed binary. The gyan.dev page lists the external libraries and links to each one's source. The macOS build script is at https://git.martin-riedl.de/ffmpeg/build-script.
- **Written offer (GPLv3 §6):** for three years from the last time we distribute a given build, The Why Not AI (info@thewhynot.ai) will send the complete corresponding source of that build on request, for no more than the cost of physically performing the distribution. This offer applies whenever we host or bundle the binary ourselves, not only when the installer fetches it from the provider.

## 3. How WhyNot Cut runs FFmpeg

- **Installed as a separate program.** The installer step `ffmpeg` (`whynot-cut/installer/core/wnc_installer/runtime.py`) downloads the pinned archive from the provider URL above. It checks size and sha256, then extracts only `ffmpeg` and `ffprobe` into `~/.whynot-cut/ffmpeg/<version>/`. It writes the GPL text and a `SOURCE.txt` (version, licence, source URL) next to them. The step refuses to install without the GPL text.
- **Run as a subprocess, never linked.** The engine calls the binary with `subprocess` (`reel/lib/common.py: run()`), passing command-line arguments and reading its output and files. No WhyNot Cut code is linked into FFmpeg, and FFmpeg isn't linked into WhyNot Cut. This is "mere aggregation" of separate programs (GPLv3 §5, last paragraph).
- **Which binary runs** (`ffmpeg_choice()`):
  1. the override `WHYNOT_FFMPEG` / `NH_FFMPEG`, so the user can point to their own build;
  2. the pinned build in the engine home;
  3. the 2.x engine-home copy;
  4. the `imageio-ffmpeg` binary;
  5. `ffmpeg` on PATH.
- **The user can always replace it.** Set `WHYNOT_FFMPEG` to any FFmpeg build. Nothing checks for a specific binary beyond the installer's download integrity check.
- **Exception: PyAV is in-process.** `av` is imported into the engine's Python process (`reel/lib/media.py`, `media_util.py`, `audio_clean.py`, `premiere_xml.py`, and faster-whisper's audio decoding). See `docs/legal/third-party-licences.md` §2 and §5 for what that means for the commercial edition.

## 4. What the GPL asks of us (3.0 trial and later)

1. Keep this notice, `COPYING.GPLv3` and the source links with every build that installs FFmpeg. The installer already writes the GPL text and `SOURCE.txt` beside the binaries.
2. Name FFmpeg and its licence in the About screen and in `THIRD_PARTY_NOTICES.md`. The exact text is in `third-party-licences.md` §7.
3. If we ever **host or bundle** the binary ourselves (a mirror, an offline installer, a model or runtime pack), ship the source alongside it or honour the written offer in §2 for that exact build.
4. Don't add any technical or contractual restriction on the user running, studying, replacing or sharing the FFmpeg binary.
5. Never link FFmpeg's GPL build into WhyNot Cut code. Keep it a separate process.
