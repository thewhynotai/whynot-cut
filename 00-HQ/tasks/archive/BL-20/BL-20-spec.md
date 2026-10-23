<!-- Source: WhyNotCut PROGRESS.md (release/3.0 @ 746e834), section "Stage 1 = Gate 4 open list", "Gate 4 exit" list,
     line 80, copied verbatim 2026-10-20. This item is a roadmap Stage 1 (Gate 4 exit) item, not a BACKLOG.md section:
     every BACKLOG Gate 4 item is already carded, merged or held by a running track. PROGRESS.md stays the source if
     they differ. The "Design (master, binding)" block below is the master's, written for this card. -->

### Source line (verbatim)
- [ ] full suite on a snapshot, 0 failures, `WNC_REQUIRE_SCANNERS=1`, and ZERO temporary dated skips (plan session 2026-10-19). A gate check greps the tests for the executor's dated-skip markers ("an explicit, dated skip", `_PENDING`, "waits for … patch") and for any `skipIf`/`skipUnless` added since p3.1 that isn't a platform or tool skip. A religious-safety or medical-safety test is never green-by-skip at the tag. Today: test_manual_verse_handoff (61feeb2) is removed by the verse fix-round commit, and the manual verse slot is NOT accepted while the skip exists.

### Design (master, binding)
- **One read-only stdlib tool, `tools/skip_audit.py`.** It never edits a test, never runs one, and never writes inside
  the repo. Output: a human table on stdout, `--json` for a machine report.
- **What it finds (AST, not a text grep):** in every `*.py` under `whynot-cut/tests/` (recursive, `security/`
  included; `whynot-cut/tests/fixtures/**` excluded by default), every skip site:
  `@unittest.skip(...)`, `@unittest.skipIf(...)`, `@unittest.skipUnless(...)`, `@unittest.expectedFailure`,
  `self.skipTest(...)`, `raise unittest.SkipTest(...)` / `raise SkipTest(...)`, `pytest.mark.skip` / `skipif` /
  `xfail`, and a module-level `unittest.skip...` assigned to a name and used as a decorator (as in
  `requires_hypothesis = unittest.skipUnless(...)`, `tests/security/fuzz/_hyp.py:64`).
- **Three classes per site:**
  - `dated`: the skip's reason, its condition's names, or a comment on the skip line or the 3 lines above it, or the
    `except ImportError` block that sets the condition, carries a dated-skip marker: "dated skip" (any case, also
    "an explicit, dated skip"), a name containing `_PENDING`, "waits for … patch", "until … lands", or an ISO date
    (`20\d\d-\d\d-\d\d`) in the reason. **Always a FAIL.**
  - `platform/tool`: the condition is about the machine, not about unfinished work: `sys.platform`, `os.name`,
    `platform.system()`, Windows/macOS/darwin flags, `shutil.which`, a tool-presence flag (`NODE`, `*AVAILABLE`,
    `HAVE_*`, `*_PRESENT`, `TOOLS_PRESENT`), a file or folder that exists only in a repo checkout
    (`.is_file()`, `.is_dir()`, `.exists()`), free RAM/disk, or an explicit opt-in env var (`WHYNOT_SLOW_TESTS`
    style). Listed, never a FAIL.
  - `unknown`: everything else. Listed. A FAIL only in `--since` mode (below).
- **`--since <tag>` (gate mode, e.g. `--since v3.0.0-p3.1`):** only skip sites on lines added since that tag
  (`git diff --unified=0 <tag>..HEAD -- whynot-cut/tests`, read-only git) count; a new `unknown` site is a FAIL, a
  `dated` site is a FAIL wherever it is. Without `--since`, only `dated` sites fail.
- **Exit codes:** 0 = clean; 1 = at least one FAIL (each listed: file, line, class, reason text); 2 = the check could
  not run (a test file that does not parse, git missing, the tag missing, a path outside the repo). A check that did
  not run never prints "clean" and never exits 0.
- **Not in scope:** wiring it into `tools/release.py`, `tools/test.sh`, CI or PROGRESS.md (executor files). The
  builder writes the exact gate step text in the report for the executor.
