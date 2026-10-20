report-mtime: 1792485229
suite: Ran 8753 tests — FAILED (failures=43, errors=34, skipped=91, expected failures=1) + ResourceWarning x1 (h2-setup3, branch h2/SETUP-H2 = release/3.0 @ 074b85b)
reviewer: master intake (session local_27a4af61), SETUP card rule A (no code)
verdict: ACCEPTED

# SETUP-H2 r1 — master intake decision (2026-10-20 11:40)

- **Account:** stated: marketing@thewhynot.ai, git author "Marketing (WhyNot Helper 2)".
- **Numbers present:** 8753 run, 43 F, 34 E, 91 skipped; all 77 named by group (A ffmpeg 67, B py3.13 7, C darwin 2, D timing 1).
- **Against the baseline:** the same classes as `reviews/SETUP-H1-r3.md` and the master's own BL-16 suite
  (`reviews/BL-16-r1.md`): test_media_normalise, test_motion x2, test_podcast vfr, test_audio_long resample,
  test_bidi_lines, the 6 test_fuzz_* imports, the 2 darwin-only t45 tests. `test_t26_conform_wiring` (9 E + 14 F) is
  new to H1's r3 list only because H1 ran on 8a79a0e; the master's BL-16-r1 suite already lists the same t26 names
  (fps_mode / old imageio ffmpeg, ENV-01). `test_identity_scan` full_repo_scan_is_fast: timing under load (seen in H1 r3).
  No new real failure. **ACCEPTED** (rule A; risk 5 in STATUS already covers these classes).
- **Extras:** `npm ci` in adobe/ rc 0 (0 vulnerabilities); panel tests 296/296; one render P-03-home normal-en-360
  byte-identical to the manifest sha1. Not verified by the master: the render image itself (helper says it looked).
- **Notes kept:** esbuild 0.28.2 postinstall not in `allowScripts` (may matter for `dev:build`, unchecked);
  wait on `[heavy] suite '<label>' done`, not on "timed out" text.
