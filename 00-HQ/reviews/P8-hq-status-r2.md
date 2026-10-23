# P8 hq_status r2 — the FIX-verdict reading (finding F5), LIGHT tier, 2026-10-23

- **Change under review:** `tools/hq_status.py` `render_report` (section 5 "reports waiting for intake"): a verdict is read by
  its first word, so `FIX r1` / `FIX r2` count as decided (snapshot a8a1282 in the ops/hq mirror) + test
  `test_a_fix_round_verdict_is_not_waiting_for_intake`.
- **Review:** one fresh independent sub-agent (Opus, code-reviewer, no history), read-only. Verdict **PASS-WITH-MINORS**.
  It checked every verdict now in `intake/state.json` (noted, ACCEPTED, FIX r1, answered, processing): all handled as
  intended; the test fails on the old line.
- **P2 (fixed):** a JSON `null` verdict crashed the whole report (`None.split`). **P3 (fixed):** a leading space hid the
  word. Fix: `verdict = (… .get("verdict") or "").strip()`. Test first: `test_a_null_or_spaced_verdict_does_not_break_the_report`
  red (AttributeError), then green; `test_hq_status` + `test_agency_live` 55/55 OK; dry run
  `D:\ClaudeData\setup-phase8\hq_status-dryrun3.txt` lists only BL-02 (verdict `processing`) as waiting, which is right.
- **P3 (known limit, not fixed):** MASTER-INTAKE §2.3 does not list the allowed verdict words; if the intake ever wrote
  READY, BLOCKED or PARKED as a verdict, the report would show that report as waiting (a visible false alarm, not a hidden
  one). The intake writes ACCEPTED / FIX rN / answered / noted / awaiting-peer / processing today.
