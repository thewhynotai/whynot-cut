#!/usr/bin/env bash
# WhyNot Cut machine setup (macOS / Linux / Git Bash). Thin wrapper around the cross-platform setup_env.py.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for py in "${PYTHON:-}" python3 python py; do
  [ -n "$py" ] || continue
  # macOS without the Command Line Tools: /usr/bin/python3 only opens Apple's install dialog; never start it
  case "$(command -v "$py" 2>/dev/null || true)" in
    /usr/bin/*) [ "$(uname -s 2>/dev/null)" = Darwin ] && ! xcode-select -p >/dev/null 2>&1 && continue ;;
  esac
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' </dev/null >/dev/null 2>&1; then
    exec "$py" "$HERE/setup_env.py" "$@"
  fi
done
# No usable Python: the installer that ships with the plugin brings its own (pinned uv + Python 3.12, sha256-checked,
# per user): no Xcode tools, Homebrew, winget or admin rights (G3 review I2).
echo "WhyNot Cut: no Python 3.9+ found. Run /whynot-cut:start in Claude Code: it installs the engine with the WhyNot Cut installer that ships with the plugin, which brings its own Python 3.12 (no Xcode tools, Homebrew, winget or admin rights needed)." >&2
exit 1
