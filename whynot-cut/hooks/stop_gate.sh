#!/usr/bin/env bash
# Stop: the optional evidence gate (3.0 T3.4), OFF unless the preference `evidence_gate: on` (and approval is not
# auto). SessionStart writes ${CLAUDE_PLUGIN_DATA}/evidence-gate/<session id> when it is on; without that file this
# exits at once using bash builtins only (no Python, no other process), so a turn end costs one bash start.
f="${CLAUDE_PLUGIN_DATA:-}/evidence-gate/${CLAUDE_CODE_SESSION_ID:-}"
if [ -z "${CLAUDE_PLUGIN_DATA:-}" ] || [ -z "${CLAUDE_CODE_SESSION_ID:-}" ] || [ ! -f "$f" ]; then
  exit 0
fi
exec bash "$(dirname "$0")/run_python.sh" "$(dirname "$0")/stop_gate.py"
