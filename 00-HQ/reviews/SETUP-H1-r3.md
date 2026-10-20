report-mtime: 1792470186
suite: Ran 8226 tests — FAILED (failures=27, errors=24, skipped=87, expected failures=1) + ResourceWarning x1 (h1-setup4, branch h1/SETUP-H1 @ 8a79a0e)
reviewer: master intake (session local_7dbfe38b), SETUP card rule A (no code)
verdict: ACCEPTED

# SETUP-H1 r3 — master intake decision (2026-10-20 08:26)

- **Numbers present:** 8226 run, 27 F, 24 E, 87 skipped; every failure named by group (report "The 51, by cause").
- **Account:** not written as an e-mail in the report. Accepted on evidence: the run log is in the h1 profile
  (`D:\ClaudeData\accounts\h1\auto\h1-setup4.log`) and H1's commits on this PC are authored
  `Mayar (WhyNot Helper 1) <mayar@thewhynot.ai>` (h1/BL-16). Future SETUP reports must state it.
- **Against the baseline:** the master's own full suite at the same hour, on the same engine venv
  (`~/.whynot-cut/venv`, review of BL-16, `reviews/BL-16-r1.md`), shows the same environment classes:
  test_media_normalise, test_motion ×2, test_podcast, test_audio_long, test_bidi_lines, the 6 test_fuzz_* imports,
  and the two t45 darwin tests (77 names, all also failing at merge-base 4c1e59c). Not in that baseline:
  - test_identity_scan full_repo_scan_is_fast and test_lead_token_guard hook latency: timing bounds measured while a
    second suite ran (load, environmental);
  - test_t45_client_move sealed_rules: already fixed on release/3.0 (087e8e3); the branch is at 8a79a0e.
  No new real failure. **ACCEPTED** (rule A: environmental failures accepted, one risk line in STATUS).
- **Follow-ups (not H1's):** the ENV-01 gaps (the engine uses imageio-ffmpeg 4.2.2, not the pinned ffmpeg; the venv
  is Python 3.13 while the locks pin 3.12) go to ENV-01 / the executor. The two darwin-only t45 tests on Windows
  and the fuzz import-time crash are recorded in STATUS risks and the ENV-01 row (no merge, so no executor message this run).
