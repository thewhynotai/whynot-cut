"""WhyNot Cut per-user installer core (3.0, Phase 7).

Stdlib only: it runs on the python-build-standalone interpreter the bootstrap (install.ps1 / install.sh) has just put
in ~/.whynot-cut/python, before any package is installed. Entry point: installer/core/wnc_install.py.
  base.py  paths, logging, components.json, downloads, extraction, state.json, safe deletes, the step runner
  cli.py   install / uninstall / plan, and the STEPS registry the step modules append to
"""
