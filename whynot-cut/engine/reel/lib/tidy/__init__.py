# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Tidy engine services (N7): what the owner's panel did in Node, done by the engine.

A UXP panel cannot stat or read media files, stream a WAV or copy the project file, so `reel tidy` and the Tidy tab
ask the engine. Every function here gives what `adobe/tools/tidy/_upstream/js/engine.js` (and the pure modules of
`adobe/tools/tidy/src/js/`) give, with the same field names:

  disk.disk_info      E.diskInfo     exists / size of every item that points at a file
  sniff.sniff         E.sniff        camera or render, which camera, icon or not, from the first / last 2 MiB
  media               TidyMedia      the pure rules sniff applies (a twin of src/js/media.js)
  wavpower.wav_power  E.wavPower     mean power per 1 ms of a 16-bit WAV (+ the 44.1 kHz drift guard, A3 #7)
  backup.backup       E.backup       "<name> (WhyNot Tidy backup YYYY-MM-DD HHMMSS).prproj" next to the project
  store               E.HOME ...     engine-home tools/tidy/: settings, log, temporary sync WAVs

The JavaScript is the reference; tests/test_tidy_engine.py runs both on the same files. Media files are only ever read.
"""
