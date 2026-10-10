#!/usr/bin/env bash
# Runs a WhyNot Cut hook script with the first working Python 3 on this machine (macOS, Linux or Windows).
# Skips stubs such as the Windows Store "python3" alias, which exists on PATH but is not a real interpreter.
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1   # never write __pycache__ into the installed plugin folder
for py in python3 python py; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' </dev/null >/dev/null 2>&1; then
    exec "$py" "$@"
  fi
done
echo "WhyNot Cut: no Python 3.8+ found on PATH; hook skipped" >&2
exit 0
