#!/usr/bin/env bash
# Test-only uv stand-in (see fake_uv.py). Runs fake_uv.py with $FAKE_UV_PYTHON (default: python3).
exec "${FAKE_UV_PYTHON:-python3}" -B "$(dirname "$0")/fake_uv.py" "$@"
