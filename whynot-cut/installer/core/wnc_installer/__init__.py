"""WhyNot Cut per-user installer core (3.0, Phase 7).

Stdlib only: it runs on the python-build-standalone interpreter the bootstrap (install.ps1 / install.sh) has just put
in ~/.whynot-cut/python, before any package is installed. Entry point: installer/core/wnc_install.py.
  base.py  paths, logging, components.json, downloads, extraction, state.json, safe deletes, the step runner
  cli.py   install / uninstall / plan, and the STEPS registry the step modules append to
  runtime.py  steps runtime (uv venv + pip sync from the hash lock), ffmpeg (pinned, GPL text) and gpu (NVIDIA)
  claude.py   steps gitbash (per-user Git Bash) and claude (marketplace + plugin, settings.json merge)
  system.py   steps preflight, questions, settings, model, state, doctor (+ the checklist), launch; registers
  adobe.py    step adobe (signed CEP ZXP per user, UXP .ccx through UPIA) and
  fonts.py    step fonts (OFL fonts per user, HKCU font values on Windows)
  uninstall.py  the uninstall steps plugin, adobe, fonts, marketplace, engine (--remove-engine / --remove-models)
"""
