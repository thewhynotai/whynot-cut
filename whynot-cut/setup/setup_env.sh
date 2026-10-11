#!/usr/bin/env bash
# WhyNot Cut machine setup (macOS / Linux / Git Bash). Thin wrapper around the cross-platform setup_env.py.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for py in "${PYTHON:-}" python3 python py; do
  [ -n "$py" ] || continue
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' </dev/null >/dev/null 2>&1; then
    exec "$py" "$HERE/setup_env.py" "$@"
  fi
done
echo "WhyNot Cut: Python 3.9+ not found. macOS: xcode-select --install (or python.org); Windows: winget install Python.Python.3.12" >&2
exit 1
