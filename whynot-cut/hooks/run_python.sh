#!/usr/bin/env bash
# Runs a WhyNot Cut hook script (guard.py, session_context.py) with a working Python 3 on macOS, Linux or Windows.
# Order: the engine interpreter ($WHYNOT_HOME or ~/.whynot-cut, the wrappers' rule: the isolated runtime named by the
# one-line text file <home>/current — runtimes/<id>/Scripts/python.exe or bin/python, run with -s — else the 2.x
# venv/Scripts/python.exe or venv/bin/python), then the interpreter cached in ${CLAUDE_PLUGIN_DATA}/python, then python3 / python / py on PATH, skipping the Windows Store
# stubs (*/WindowsApps/*) and, on macOS, /usr/bin/python3 when the Command Line Tools are missing (it only opens an
# install dialog). No separate version probe: the hook scripts check sys.version_info themselves.
# Every run that finds Python touches ${CLAUDE_PLUGIN_DATA}/hooks-ok (`reel doctor` reports guard_active from it).
# No Python: fail open (exit 0) but visibly — the SessionStart hook tells Claude that protection is OFF.
# Builtins only on the hot path (Git Bash forks are slow): every external command runs at most once per machine.
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1   # never write __pycache__ into the installed plugin folder

data="${CLAUDE_PLUGIN_DATA:-}"
py=""

usable() {   # $1 = candidate path
  case "$1" in
    */[Ww]indows[Aa]pps/*) return 1 ;;
    /usr/bin/python3) [ "$(uname -s 2>/dev/null)" = Darwin ] && ! xcode-select -p >/dev/null 2>&1 && return 1 ;;
  esac
  [ -f "$1" ] && [ -x "$1" ]
}

# 1. the engine runtime (same home as the engine: an explicit setting wins, then ~/.whynot-cut, then a legacy home)
home=""
for v in WHYNOT_HOME CLAUDE_PLUGIN_OPTION_ENGINE_HOME REEL_HOME CLAUDE_PLUGIN_OPTION_REEL_HOME NH_ENV_DIR; do
  if [ -n "${!v:-}" ]; then home="${!v}"; break; fi
done
if [ -z "$home" ]; then
  home="$HOME/.whynot-cut"
  if [ ! -e "$home/venv" ] && [ ! -f "$home/current" ]; then   # it may only hold plugin-options.json
    for old in "$HOME/.reel-editor" "$HOME/.dr-nahla-editor"; do
      [ -e "$old/venv" ] && { home="$old"; break; }
    done
  fi
fi
pyflag=""
if [ -f "$home/current" ]; then     # 3.0 T2.1: one runtime id (BOM / whitespace stripped; ids as in lib/plat.py)
  rid=""
  IFS= read -r rid < "$home/current" || true
  rid="${rid#$'\xef\xbb\xbf'}"
  rid="${rid//[[:space:]]/}"
  rid_re='^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$'
  if [[ $rid =~ $rid_re ]] && [[ $rid != *..* ]]; then
    for c in "$home/runtimes/$rid/Scripts/python.exe" "$home/runtimes/$rid/bin/python"; do
      if [ -f "$c" ] && [ -x "$c" ]; then py="$c"; pyflag="-s"; break; fi
    done
  fi
fi
if [ -z "$py" ]; then
  for c in "$home/venv/Scripts/python.exe" "$home/venv/bin/python"; do
    if [ -f "$c" ] && [ -x "$c" ]; then py="$c"; break; fi
  done
fi

# 2. the interpreter found on an earlier run
if [ -z "$py" ] && [ -n "$data" ] && [ -f "$data/python" ]; then
  IFS= read -r cached < "$data/python"
  usable "$cached" && py="$cached"
fi

# 3. PATH (first usable python3, then python, then py); remembered for the next run
if [ -z "$py" ]; then
  IFS=: read -r -a dirs <<< "$PATH"
  for name in python3 python py; do
    for d in "${dirs[@]}"; do
      [ -n "$d" ] || continue
      for c in "$d/$name" "$d/$name.exe"; do
        if usable "$c"; then py="$c"; break 3; fi
      done
    done
  done
  if [ -n "$py" ] && [ -n "$data" ]; then
    { [ -d "$data" ] || mkdir -p "$data"; printf '%s\n' "$py" > "$data/python"; } 2>/dev/null
  fi
fi

if [ -z "$py" ]; then
  case "$1" in
    *session_context.py)
      printf '%s\n' '{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "WhyNot Cut protection is OFF: no Python found — run reel doctor"}}' ;;
  esac
  echo "WhyNot Cut: no Python found (engine runtime or python3/python/py on PATH); hook skipped, protection is OFF — run reel doctor" >&2
  exit 0
fi

if [ -n "$data" ]; then   # heartbeat (its mtime is what counts; EPOCHSECONDS is bash 5+, empty on macOS bash 3.2)
  { [ -d "$data" ] || mkdir -p "$data"; printf '%s\n' "${EPOCHSECONDS:-}" > "$data/hooks-ok"; } 2>/dev/null
fi
exec "$py" $pyflag "$@"
