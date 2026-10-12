#!/bin/bash
# run the Kalam engine tests: run_tests.sh [pytest args]
cd "$(dirname "$0")" && exec "$HOME/Library/Application Support/Kalam/venv/bin/pytest" -q "$@"
