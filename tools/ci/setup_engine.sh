#!/usr/bin/env bash
# Build the engine runtime a CI Mac runs the suite on (G-T13): $HOME/.whynot-cut/venv (what tools/test.sh falls back to
# when no 3.0 runtime `current` exists) from the product's own hash lock, plus the product's pinned ffmpeg/ffprobe in
# $HOME/.whynot-cut/ffmpeg/<version>/ (where plat.engine_ffmpeg looks). CI only: on a real Mac the installer does this.
#
# Usage:  bash tools/ci/setup_engine.sh smoke|full
#   smoke  only the packages the smoke subset imports (graphics/text/media stack), closed over their locked deps by
#          tools/ci/lock_subset.py; no faster-whisper / ctranslate2 / onnxruntime / huggingface-hub / pypdf.
#   full   the whole lock, as the installer installs it.
# Every wheel is hash-checked (--require-hashes) and binary-only, exactly like the installer.
# Env: PYTHON (default python3: actions/setup-python's 3.12), WNC_CI_HOME (default $HOME/.whynot-cut).
# Homebrew is used ONLY as a fallback here if the pinned ffmpeg cannot be downloaded; the product never needs it.
# bash 3.2 safe.
set -euo pipefail

MODE="${1:-}"
case "$MODE" in smoke|full) ;; *) echo "usage: bash tools/ci/setup_engine.sh smoke|full" >&2; exit 2 ;; esac
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-python3}"
HOME_DIR="${WNC_CI_HOME:-$HOME/.whynot-cut}"
COMP="whynot-cut/setup/components.json"

case "$(uname -s)/$(uname -m)" in
  Darwin/arm64) PLAT="mac-arm64" ;;
  Darwin/x86_64) PLAT="mac-x64" ;;
  *) echo "setup_engine: this script is for the macOS CI runners (got $(uname -s)/$(uname -m))" >&2; exit 2 ;;
esac
LOCK="whynot-cut/setup/locks/runtime-$PLAT.lock"
[ -f "$LOCK" ] || { echo "setup_engine: $LOCK is missing" >&2; exit 2; }

echo "== engine venv ($MODE) in $HOME_DIR/venv from $LOCK"
"$PY" -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version' \
  || { echo "setup_engine: the runtime locks are for Python 3.12" >&2; exit 2; }
mkdir -p "$HOME_DIR"
[ -x "$HOME_DIR/venv/bin/python" ] || "$PY" -m venv "$HOME_DIR/venv"
VPY="$HOME_DIR/venv/bin/python"
REQ="$LOCK"
if [ "$MODE" = "smoke" ]; then
  REQ="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/wnc-smoke.lock"
  # PyYAML: test_structure; Pillow/numpy/PyAV/fonts/bidi/HarfBuzz/FreeType: test_crossplatform + test_portability
  # (stills, media probes, Arabic shaping); pyobjc CoreText/Quartz/Vision: the macOS text renderer and face finder;
  # imageio-ffmpeg: the engine's ffmpeg fallback, as in the product.
  "$PY" tools/ci/lock_subset.py "$LOCK" "$REQ" \
    pyyaml pillow numpy av fonttools arabic-reshaper python-bidi uharfbuzz freetype-py imageio-ffmpeg \
    pyobjc-framework-coretext pyobjc-framework-quartz pyobjc-framework-vision
fi
"$VPY" -m pip install --disable-pip-version-check --no-input --require-hashes --only-binary :all: -r "$REQ"

echo "== ffmpeg (the pinned build from $COMP)"
if ! "$PY" tools/ci/fetch_ffmpeg.py "$COMP" "$PLAT" "$HOME_DIR"; then
  echo "setup_engine: the pinned ffmpeg could not be fetched; CI-only fallback: Homebrew ffmpeg on PATH" >&2
  HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 brew install ffmpeg
fi

echo "== check"
bash tools/test.sh --which
"$VPY" -c 'import sys; sys.path.insert(0, "whynot-cut/engine/reel"); from lib.common import ffmpeg_choice; print("ffmpeg:", ffmpeg_choice())'
