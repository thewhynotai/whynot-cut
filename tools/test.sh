#!/usr/bin/env bash
# Run the WhyNot Cut unit suite with the engine runtime (never system Python: it silently skips HarfBuzz tests).
# Usage: tools/test.sh [extra unittest args]   e.g. tools/test.sh -k guard
#        tools/test.sh --which                 print the interpreter it would use, then exit
# Interpreter, the wrappers' order (3.0 T2.1): the runtime named by the one-line text file <home>/current
# (runtimes/<id>/, run with -s: no user site), else the 2.x venv/.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="${WHYNOT_HOME:-$HOME/.whynot-cut}"
PY="" FLAG=""
ID="" BOM="" BASE=""
printf -v BOM '\357\273\277'      # a UTF-8 BOM (printf -v: a builtin, bash 3.2 safe)
if [ -f "$HOME_DIR/current" ]; then
  IFS= read -r ID < "$HOME_DIR/current" || true
  ID="${ID#"$BOM"}"
  ID="${ID//[[:space:]]/}"
  RID_RE='^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$'          # the id rule of lib/plat.py
  [[ $ID =~ $RID_RE ]] && [[ $ID != *..* ]] || ID=""
fi
if [ -n "$ID" ] && [ -f "$HOME_DIR/runtimes/$ID/pyvenv.cfg" ]; then   # can it start: plat.runtime_usable()
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in home*=*) BASE="${line#*=}"; BASE="${BASE#"${BASE%%[![:space:]]*}"}"; BASE="${BASE%"${BASE##*[![:space:]]}"}" ;; esac
  done < "$HOME_DIR/runtimes/$ID/pyvenv.cfg"
  if [ -n "$BASE" ] && { [ -f "$BASE/python.exe" ] || [ -f "$BASE/python3" ] || [ -f "$BASE/python" ]; }; then
    for c in "$HOME_DIR/runtimes/$ID/bin/python" "$HOME_DIR/runtimes/$ID/Scripts/python.exe"; do
      if [ -x "$c" ]; then PY="$c"; FLAG="-s"; break; fi
    done
  fi
fi
[ -z "$ID" ] || [ -n "$PY" ] || echo "note: runtime $ID cannot start (run reel setup); trying the 2.x venv" >&2
if [ -z "$PY" ]; then
  for c in "$HOME_DIR/venv/bin/python" "$HOME_DIR/venv/Scripts/python.exe"; do
    if [ -x "$c" ]; then PY="$c"; break; fi
  done
fi
[ -n "$PY" ] || { echo "engine runtime not found under $HOME_DIR (run reel setup)" >&2; exit 2; }
if [ "${1:-}" = "--which" ]; then echo "$PY $FLAG"; exit 0; fi
cd "$ROOT"
# -W error::ResourceWarning: an unclosed file / pipe / process anywhere fails the run (T2.17, MI-9;
# collected by tests/test_release_hygiene.py)
PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 exec "$PY" $FLAG -B -W error::ResourceWarning -m unittest discover -s whynot-cut/tests "$@"
