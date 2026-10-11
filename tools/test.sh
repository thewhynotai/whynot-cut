#!/usr/bin/env bash
# Run the WhyNot Cut unit suite with the engine runtime (never system Python: it silently skips HarfBuzz tests).
# Usage: tools/test.sh [extra unittest args]   e.g. tools/test.sh -k guard
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="${WHYNOT_HOME:-$HOME/.whynot-cut}"
PY=""
for c in "$HOME_DIR/current/python/bin/python3" "$HOME_DIR/current/python/python.exe" \
         "$HOME_DIR/venv/bin/python" "$HOME_DIR/venv/Scripts/python.exe"; do
  [ -x "$c" ] || [ -f "$c" ] && { PY="$c"; break; }
done
[ -n "$PY" ] || { echo "engine runtime not found under $HOME_DIR (run reel setup)" >&2; exit 2; }
cd "$ROOT"
PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 exec "$PY" -B -m unittest discover -s whynot-cut/tests "$@"
