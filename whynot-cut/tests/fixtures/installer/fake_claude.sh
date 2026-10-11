#!/usr/bin/env bash
# Test-only Claude Code CLI stand-in (see fake_claude.py). Runs fake_claude.py with $FAKE_CLAUDE_PYTHON (default: python3).
exec "${FAKE_CLAUDE_PYTHON:-python3}" -B "$(dirname "$0")/fake_claude.py" "$@"
