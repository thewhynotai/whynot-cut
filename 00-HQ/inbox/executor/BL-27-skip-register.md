# BL-27: Gate 4 skip register (every `unknown` skip site, with a written reason)

- **Made on:** `release/3.0` @ **abdece5** (`abdece5ecb4bc3e401338acd776d0dc127b0f39b`), the card's pinned sha. Written 2026-10-23 by the executor sub-agent (read-only; no repo file touched).
- **How:** `git archive` of the sha into a work folder, then the real `tools/skip_audit.py --json --all` and the text run on that snapshot (python `r-6e4a68a292b4`, `-s -B`). A second read-only driver (`git show` of the same script, same AST code) added the `cond` text for each site and matched the real run: the `unknown` file:line sets are identical (200 = 200).
- **Summary line (pasted, text mode, abdece5):**

```
skip audit: 216 test files under whynot-cut/tests (fixtures excluded)
sites: dated 0, platform/tool 287, unknown 200
RESULT: clean (no dated skip), exit 0
```

  `--json --all` counts for abdece5: `{"dated": 0, "platform/tool": 287, "unknown": 200}`, exit 0. **Row count in this register = 200 = the run's `unknown` count.** The 200 sites sit in 59 files.
- **The card says 289 / 202 / 61 files.** The pinned sha does not give that: it gives 287 / 200 / 59. The card's numbers may have come from the executor's dirty working tree (38 uncommitted entries in `git status --short`, several new `tests/` files); this is a guess I did not verify. I register what the pinned sha says.
- **Newer HEAD (`5c2d7b3c`, local HEAD, 15 commits after abdece5):** `skip_audit.py` text run says `sites: dated 0, platform/tool 294, unknown 205` (218 files). Exactly **5 new rows**, all marked NEW at the end of this file; no abdece5 row went away.

## Classes at abdece5

| Class | Rows |
|---|---|
| ENV | 170 |
| PENDING | 3 |
| STALE | 13 |
| NO-REASON | 7 |
| OTHER | 7 |
| **Total** | **200** |

`NO-REASON` is by the card's definition: the classifier read an empty reason string. Where the reason is built at run time by a helper, the real reason is in the evidence column.

## ACT ON THESE (gate record): STALE and NO-REASON rows, with the file's owner (from LOCKED-AREAS)

Owner means the owner named in `LOCKED-AREAS.md` for that path. Tracks that have ended (tools, installer, J, wnc-queue, API lanes) hand their paths back to the executor.

### STALE (13): the patch has landed, the skip text is out of date; each is a one-line fix for the owner (drop the stale `skipTest`/condition, run the test)

| # | file:line | class | owner | alone-run on 5c2d7b3c snapshot (`bash tools/test.sh -v -p <file>`) |
|---|---|---|---|---|
| 12 | `test_brief.py:619` | STALE | BLD-A | TestEstimator.test_c11_one_named_function_shared_with_the_client_brief: ok |
| 14 | `test_client_brief.py:966` | STALE | BLD-A | TestProtectedOnTheWriterPath.test_p1_a_reel_client_db_refresh_through_the_cli_keeps_them: ok |
| 25 | `test_identity_scan.py:615` | STALE | looks & motion track; release-gate modes: executor | TestRealTree.test_repo_hash_file_is_hashes_only: ok |
| 90 | `test_lead_token_guard.py:303` | STALE | BLD-B (BL-15 / BL-01); guard + hooks.json hunks: executor | class TestGuardIssues: 19 ok |
| 93 | `test_lead_token_guard.py:552` | STALE | BLD-B (BL-15 / BL-01); guard + hooks.json hunks: executor | class TestHooksRouteTokenWrites: 2 ok |
| 94 | `test_lead_token_guard.py:606` | STALE | BLD-B (BL-15 / BL-01); guard + hooks.json hunks: executor | class TestDoctor: 1 ok |
| 95 | `test_lead_token_guard.py:626` | STALE | BLD-B (BL-15 / BL-01); guard + hooks.json hunks: executor | class TestHookAndEngine: 9 ok |
| 96 | `test_lead_token_guard.py:711` | STALE | BLD-B (BL-15 / BL-01); guard + hooks.json hunks: executor | class TestBackstopIgnoresFolderNames: 2 ok |
| 126 | `test_read_once.py:955` | STALE | BLD-B (BL-15 / BL-01); guard + hooks.json hunks: executor | TestSourceAndRegistration.test_if_filter_has_the_guards_form: ok |
| 127 | `test_read_once.py:981` | STALE | BLD-B (BL-15 / BL-01); guard + hooks.json hunks: executor | TestSourceAndRegistration.test_session_events_registered: ok |
| 146 | `test_runtime_locks.py:270` | STALE | executor | TestTls.test_loopback_self_signed_refused_and_accepted_through_a_temp_ca: ok |
| 178 | `test_t42_style_knobs.py:845` | STALE | executor | TestOtherTracks.test_k1_knobs_never_switch_on_a_caption_look: ok |
| 180 | `test_t43_rules_class.py:1219` | STALE | executor | class TestTheTextTheEditorAndAgentsRead: 6 ok |

Every STALE test ran and passed (none still skips). The skip text is stale, and the condition is now always false, so nothing is hidden today; the risk is only that the wording misleads the gate record.

### NO-REASON (7 at abdece5)

| # | file:line | owner | real reason (read from the code) |
|---|---|---|---|
| 1 | `security/fuzz/_hyp.py:71` | BLD-B (lane 3 security) | helper xfail_while_open(): expectedFailure for every id in a test file's OPEN set; test_fuzz_files OPEN holds 6 ids, test_fuzz_brandweb 2, test_fuzz_media >=2, security/fuzz/regressions.json has 13 entries, all status open |
| 76 | `test_installer.py:9748` | executor (installer track archived) | message is str(base.Unsupported) of platform_id(): raised only on an OS/CPU the installer core does not support; the class is also gated by WNC_INSTALLER_LIVE=1 |
| 83 | `test_kalam_engine_run.py:1935` | tools track (ended, back to executor) | reason is built at run time by slow_skip_reason() (test_kalam_engine_run.py:1775): opt-in WHYNOT_KALAM_SLOW=1, model pack missing, no clip, then 'Task 16: lib/kalam/align.py is not ported yet' |
| 84 | `test_kalam_engine_run.py:1950` | tools track (ended, back to executor) | same: reference_skip_reason() (:1792) chains slow_skip_reason() then needs WHYNOT_KALAM_REFERENCE=1 and the owner's clip sha256 |
| 85 | `test_kalam_engine_run.py:1983` | tools track (ended, back to executor) | same: reference_skip_reason() (:1792) |
| 86 | `test_kalam_engine_run.py:2396` | tools track (ended, back to executor) | same: slow_skip_reason() (:1775); without WHYNOT_KALAM_SLOW=1 it skips on the first line |
| 152 | `test_security_scan_findings.py:35` | BLD-B (lane 3 security) | helper open_issue(): OPEN = {'bootstrap-staging-delete'}; whynot-cut/installer/core/bootstrap.ps1 lines 349 and 356 still have `Remove-Item -Recurse` at abdece5 and 5c2d7b3c (git grep); the test is red-by-design, owner: installer track (now executor) |

### PENDING (3): still waiting, patch NOT on release/3.0

| # | file:line | owner | what it waits for |
|---|---|---|---|
| 77 | `test_j1_fetch.py:1101` | executor (BL-14 / J track ended) | cond find_spec('truststore'): False in this PC's runtime r-6e4a68a292b4 = lock runtime-win-x64.lock (sha 6e4a68a292b4), which has 0 truststore lines at abdece5 and HEAD; setup/requirements.txt:16 asks for it, only runtime-cpu/cuda/mps locks (366b0dea, 10-17, T4.12) carry it. Alone-run at 5c2d7b3c: this test SKIPS on this PC (confirmed). Waits for the executor's base-lock recompile (Task 12); NOT on release/3.0 |
| 82 | `test_kalam_engine_run.py:777` | tools track (ended, back to executor) | _align_or_skip(): import lib.kalam.align raises ModuleNotFoundError; `git ls-tree` shows no whynot-cut/engine/reel/lib/kalam/align.py at abdece5 or 5c2d7b3c (only adobe/tools/kalam/_upstream/.../align.py and the replacement lib/align_w2v.py, ff7110c7 Task 18b); Task 16 is NOT on release/3.0, and may be superseded by align_w2v |
| 147 | `test_runtime_locks.py:301` | executor | cond find_spec('truststore') None: same as test_j1_fetch.py:1101, the base lock runtime-win-x64.lock has no truststore; alone-run at 5c2d7b3c: SKIPS on this PC (confirmed); not on release/3.0 |

### New at 5c2d7b3c that also needs acting on: 1 NO-REASON row, `test_bl24_verse_guard.py:83` (the `expected_until` helper, HIGH tier, religious), see the NEW section at the end

## The register: 200 rows at abdece5

Columns: `file:line` (in `whynot-cut/tests/`), reason text as the audit reads it (an empty or trailing-blank text means the real text is built at run time, see evidence), class, one line of evidence (condition code or git fact).

| # | file:line | reason | class | evidence |
|---|---|---|---|---|
| 1 | `security/fuzz/_hyp.py:71` | (empty) | NO-REASON | helper xfail_while_open(): expectedFailure for every id in a test file's OPEN set; test_fuzz_files OPEN holds 6 ids, test_fuzz_brandweb 2, test_fuzz_media >=2, security/fuzz/regressions.json has 13 entries, all status open |
| 2 | `test_adobe_run_paths.py:133` | needs a test folder whose path -r accepts; this PC's is  | ENV | need_safe() (:130): r_safe(tmp) is False when the temp path has a space or non-ASCII letters that `aerender -r` refuses |
| 3 | `test_adobe_run_paths.py:607` | aerender roots are ASCII only; this PC's test folder is  | ENV | cond not str(tmp).isascii(): aerender roots must be ASCII; pure path fact |
| 4 | `test_adobe_run_paths_motion.py:168` | needs a test folder whose path -r accepts; this PC's is  | ENV | same r_safe() test-folder check as test_adobe_run_paths.py:133 |
| 5 | `test_ae_builder_assets.py:161` | mklink /J failed here | ENV | cond mklink /J returncode: `cmd /c mklink /J` in the block above; Windows-only (os.name != 'nt' skips earlier) |
| 6 | `test_ae_render_trust.py:69` | needs a test folder whose path -r accepts; this PC's is  | ENV | same r_safe() test-folder check |
| 7 | `test_ae_render_trust.py:97` | ctypes.wintypes unavailable here:  | ENV | `from ctypes import wintypes` raises: a non-Windows Python cannot load it |
| 8 | `test_ae_render_trust.py:120` | aerender roots are ASCII only; this PC's test folder is  | ENV | cond not str(tmp).isascii(): path fact |
| 9 | `test_bidi_lines_hosts.py:136` | no Arabic-capable system font found | ENV | cond not self.font: system font discovery found no Arabic-capable font |
| 10 | `test_bidi_lines_hosts.py:302` | arabic_reshaper missing (run with the engine runtime) | ENV | `import arabic_reshaper` fails; the engine runtime r-6e4a68a292b4 has it (find_spec True), so it runs there |
| 11 | `test_bidi_lines_hosts.py:490` | arabic_reshaper missing (run with the engine runtime) | ENV | same arabic_reshaper import |
| 12 | `test_brief.py:619` | lib/client_brief.py (Task 59, M5-T4) is not built yet | STALE | cond `not cb.exists()` with cb = lib/client_brief.py; file added 9835f7f2 (10-19, Task 59 / M5-T4), present at abdece5 and 5c2d7b3c |
| 13 | `test_cep_bridge.py:1345` | no links here:  | ENV | except OSError around _winapi.CreateJunction / symlink_to (:1340-1344): this account cannot make a link |
| 14 | `test_client_brief.py:966` | the cli.py hook (lane4\hooks\task59\01) is not applied in this tree | STALE | cond 'client_brief' not in cli.py text; cli.py has 12 hits at abdece5 (hook landed b9b0f2a9, 10-20, Task 58+59 hooks) |
| 15 | `test_contract.py:401` | jsonschema is not installed (it is not an engine dependency) | ENV | `import jsonschema` fails; jsonschema is NOT in this PC's runtime (find_spec False), so this test never runs on the engine runtime (coverage gap, by design: not an engine dependency) |
| 16 | `test_contract.py:2095` | no test font for HarfBuzz fitting | ENV | test_font() is None: test_motion.test_font() looks for arial / dejavu / notosansarabic / ibmplexsansarabic ttf in plat.font_dirs() |
| 17 | `test_crossplatform.py:94` | no Arabic-capable system font found | ENV | cond not self.font: no Arabic-capable system font |
| 18 | `test_eval_transcripts.py:210` | cannot make a directory link here:  | ENV | except OSError around _winapi.CreateJunction / os.symlink (:205-209) |
| 19 | `test_file_lock.py:474` | test_podcast fixture not importable | OTHER | cond _tp is None; _tp = `import test_podcast` under `except Exception` (:468-471), so ANY import error in test_podcast silently turns this class off. Alone-run at 5c2d7b3c: 32 tests, 0 skipped (class is on) |
| 20 | `test_guard_ps_direct.py:157` | no short name | ENV | GetShortPathNameW returns 0: this volume has no 8.3 name for the file (class is already IS_WIN only) |
| 21 | `test_guard_ps_direct.py:165` | no hard link:  | ENV | except OSError around os.link(): hard link refused (:163) |
| 22 | `test_housekeeping.py:805` | the OS refused a hard link here:  | ENV | except OSError around os.link(): the OS refused a hard link (:803) |
| 23 | `test_identity_scan.py:278` | git not available | ENV | cond `git init -q` returncode != 0: git missing or not runnable |
| 24 | `test_identity_scan.py:376` | git not available | ENV | same `git init` check |
| 25 | `test_identity_scan.py:615` | tools/identity_hashes.json not generated yet | STALE | cond `not tools/identity_hashes.json exists`; the file is tracked since 9dc10ee0 (10-16, Task 19 keyed identity scan), present at abdece5 |
| 26 | `test_installer.py:677` | Windows PowerShell is not available | ENV | find_powershell() (:3951): which('powershell') on Windows, else None |
| 27 | `test_installer.py:700` | bash is not available | ENV | find_bash() (:3956): Git Bash next to git.exe, else bash on PATH |
| 28 | `test_installer.py:757` | neither PowerShell nor bash is available | ENV | find_powershell() and find_bash() both None (:3951/:3956) |
| 29 | `test_installer.py:1814` | bash is not available | ENV | find_bash() (:3956): Git Bash next to git.exe, else bash on PATH |
| 30 | `test_installer.py:1831` | bash is not available | ENV | find_bash() (:3956): Git Bash next to git.exe, else bash on PATH |
| 31 | `test_installer.py:2709` | bash is not available | ENV | find_bash() (:3956): Git Bash next to git.exe, else bash on PATH |
| 32 | `test_installer.py:4120` | Windows PowerShell is not available | ENV | find_powershell() (:3951): which('powershell') on Windows, else None |
| 33 | `test_installer.py:4274` | Windows PowerShell is not available | ENV | find_powershell() (:3951): which('powershell') on Windows, else None |
| 34 | `test_installer.py:4415` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 35 | `test_installer.py:4472` | bash is not available | ENV | find_bash() (:3956): Git Bash next to git.exe, else bash on PATH |
| 36 | `test_installer.py:5244` | Windows PowerShell is not available | ENV | find_powershell() (:3951): which('powershell') on Windows, else None |
| 37 | `test_installer.py:5329` | bash is not available | ENV | find_bash() (:3956): Git Bash next to git.exe, else bash on PATH |
| 38 | `test_installer.py:5433` | Windows PowerShell is not available | ENV | find_powershell() (:3951): which('powershell') on Windows, else None |
| 39 | `test_installer.py:5643` | bash is not available | ENV | find_bash() (:3956): Git Bash next to git.exe, else bash on PATH |
| 40 | `test_installer.py:5854` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 41 | `test_installer.py:6172` | cannot make a directory link here | ENV | cond `not cases`: three make_dir_link() attempts (:6161-6169) all failed; only then it skips |
| 42 | `test_installer.py:6225` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 43 | `test_installer.py:6254` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 44 | `test_installer.py:6281` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 45 | `test_installer.py:6326` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 46 | `test_installer.py:6369` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 47 | `test_installer.py:6469` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 48 | `test_installer.py:6663` | this disk tells upper and lower case apart | ENV | cond os.path.lexists('.WhyNot-Cut') is False only on a case-sensitive disk |
| 49 | `test_installer.py:7084` | bash is not available | ENV | find_bash() (:3956): Git Bash next to git.exe, else bash on PATH |
| 50 | `test_installer.py:7411` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 51 | `test_installer.py:7539` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 52 | `test_installer.py:7652` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 53 | `test_installer.py:7684` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 54 | `test_installer.py:7840` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 55 | `test_installer.py:8410` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 56 | `test_installer.py:8443` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 57 | `test_installer.py:8478` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 58 | `test_installer.py:8525` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 59 | `test_installer.py:8555` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 60 | `test_installer.py:8590` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 61 | `test_installer.py:8683` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 62 | `test_installer.py:8709` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 63 | `test_installer.py:8960` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 64 | `test_installer.py:8964` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 65 | `test_installer.py:8989` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 66 | `test_installer.py:8994` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 67 | `test_installer.py:9014` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 68 | `test_installer.py:9047` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 69 | `test_installer.py:9109` | Windows PowerShell is not available | ENV | find_powershell() (:3951): which('powershell') on Windows, else None |
| 70 | `test_installer.py:9183` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 71 | `test_installer.py:9203` | bash is not available | ENV | find_bash() (:3956): Git Bash next to git.exe, else bash on PATH |
| 72 | `test_installer.py:9337` | cannot make a directory link here | ENV | make_dir_link() (:1299-1308): os.symlink, else `mklink /J`; False only when both fail |
| 73 | `test_installer.py:9639` | Windows PowerShell is not available | ENV | find_powershell() (:3951): which('powershell') on Windows, else None |
| 74 | `test_installer.py:9681` | bash is not available | ENV | find_bash() (:3956): Git Bash next to git.exe, else bash on PATH |
| 75 | `test_installer.py:9710` | PSScriptAnalyzer is not importable (set WHYNOTCUT_PSSA_PATH to its .psd1) | ENV | cond returncode 7 of the probe that imports PSScriptAnalyzer; the module is an optional tool (WHYNOTCUT_PSSA_PATH names its .psd1) |
| 76 | `test_installer.py:9748` | (empty) | NO-REASON | message is str(base.Unsupported) of platform_id(): raised only on an OS/CPU the installer core does not support; the class is also gated by WNC_INSTALLER_LIVE=1 |
| 77 | `test_j1_fetch.py:1101` | truststore not in this runtime yet (Task 12 lock) | PENDING | cond find_spec('truststore'): False in this PC's runtime r-6e4a68a292b4 = lock runtime-win-x64.lock (sha 6e4a68a292b4), which has 0 truststore lines at abdece5 and HEAD; setup/requirements.txt:16 asks for it, only runtime-cpu/cuda/mps locks (366b0dea, 10-17, T4.12) carry it. Alone-run at 5c2d7b3c: this test SKIPS on this PC (confirmed). Waits for the executor's base-lock recompile (Task 12); NOT on release/3.0 |
| 78 | `test_j5_linksafe.py:403` | this Windows refuses the name | ENV | mkdir('con.clinic files') raises OSError: a Windows name rule on this build |
| 79 | `test_kalam_baseline_js.py:172` | test_html.js checks the owner's index.html and main.js: upstream only, the UI is rebuilt by the Adobe track | OTHER | unconditional skipTest (cond empty): test_html.js checks the owner's upstream index.html/main.js, which the Adobe track rebuilds; a permanent, written skip, not a machine fact |
| 80 | `test_kalam_engine_correct.py:363` | wnc_installer cannot be imported here: %s | OTHER | `import wnc_installer.claude` ImportError is swallowed after the layout check passed (:359); any real import bug in installer/core/wnc_installer/claude.py also reads as a skip |
| 81 | `test_kalam_engine_run.py:242` | this account cannot create symbolic links | ENV | os.symlink raises OSError/NotImplementedError: this account has no symlink right |
| 82 | `test_kalam_engine_run.py:777` | Task 16: lib/kalam/align.py is not ported yet (this test runs unchanged once it is) | PENDING | _align_or_skip(): import lib.kalam.align raises ModuleNotFoundError; `git ls-tree` shows no whynot-cut/engine/reel/lib/kalam/align.py at abdece5 or 5c2d7b3c (only adobe/tools/kalam/_upstream/.../align.py and the replacement lib/align_w2v.py, ff7110c7 Task 18b); Task 16 is NOT on release/3.0, and may be superseded by align_w2v |
| 83 | `test_kalam_engine_run.py:1935` | (empty) | NO-REASON | reason is built at run time by slow_skip_reason() (test_kalam_engine_run.py:1775): opt-in WHYNOT_KALAM_SLOW=1, model pack missing, no clip, then 'Task 16: lib/kalam/align.py is not ported yet' |
| 84 | `test_kalam_engine_run.py:1950` | (empty) | NO-REASON | same: reference_skip_reason() (:1792) chains slow_skip_reason() then needs WHYNOT_KALAM_REFERENCE=1 and the owner's clip sha256 |
| 85 | `test_kalam_engine_run.py:1983` | (empty) | NO-REASON | same: reference_skip_reason() (:1792) |
| 86 | `test_kalam_engine_run.py:2396` | (empty) | NO-REASON | same: slow_skip_reason() (:1775); without WHYNOT_KALAM_SLOW=1 it skips on the first line |
| 87 | `test_lead_token.py:210` | links not available | ENV | except OSError around symlink_to / mklink junction (:203-209) |
| 88 | `test_lead_token.py:431` | links not available | ENV | except OSError around the same link helper |
| 89 | `test_lead_token_guard.py:193` | links not available | ENV | except OSError around the link helper |
| 90 | `test_lead_token_guard.py:303` | guard.py has no BL-15 token support yet (executor patch) | STALE | GUARD_HAS_TOKENS = 'lead_steps.hook_issue' in guard.py (:39); present at abdece5 (2 hits), added fcb78842 (BL-15 integration) |
| 91 | `test_lead_token_guard.py:364` | links not available | ENV | except OSError around the link helper |
| 92 | `test_lead_token_guard.py:484` | links not available | ENV | except OSError around the link helper |
| 93 | `test_lead_token_guard.py:552` | hooks.json does not route token-folder writes yet (executor patch) | STALE | HOOKS_COVER_TOKENS = '[Ll][Ee][Aa][Dd]-[Tt]' in hooks.json (:40); 6 hits at abdece5, added fcb78842 |
| 94 | `test_lead_token_guard.py:606` | reel doctor has no BL-15 check yet (executor patch) | STALE | DOCTOR_CHECKS_TOKENS = 'lead_steps.doctor_check' in lib/onboard.py (:42); 1 hit at abdece5, added fcb78842 |
| 95 | `test_lead_token_guard.py:626` | guard/cli have no BL-15 support yet (executor patches) | STALE | GUARD_HAS_TOKENS (:39) again; landed fcb78842 |
| 96 | `test_lead_token_guard.py:711` | guard.py has no BL-15 token support yet (executor patch) | STALE | GUARD_HAS_TOKENS (:39) again; landed fcb78842 |
| 97 | `test_legal_notices.py:162` | the owner's identity key is not on this machine: nothing was scanned | ENV | cond 'skipped' in doc: the identity scan reports itself skipped when the owner's key file is not on this machine (a secret, by design) |
| 98 | `test_long_lived.py:152` | no system font to copy | ENV | cond not src: no system font file to copy |
| 99 | `test_long_lived.py:174` | no system font to copy | ENV | same system-font lookup |
| 100 | `test_motion.py:984` | no test font for HarfBuzz fitting | ENV | test_font() None (test_motion.py:869): needs arial/dejavu/notosansarabic/ibmplexsansarabic .ttf in plat.font_dirs() |
| 101 | `test_motion.py:1194` | no test font for HarfBuzz fitting | ENV | same test_font() check |
| 102 | `test_motion.py:1323` | this computer's admin share is not reachable here | ENV | cond not os.path.exists(\\HOST\C$\...): the admin share of this computer is unreachable (:1320 builds the UNC path from socket.gethostname()) |
| 103 | `test_motion.py:1360` | no test font for HarfBuzz fitting | ENV | same test_font() check |
| 104 | `test_motion.py:2041` | no test font for HarfBuzz fitting | ENV | same test_font() check (raise SkipTest) |
| 105 | `test_motion.py:2334` | the configured fallback font   is not installed on this machine | ENV | cond: the configured Windows fallback font (motion_cfg fallback_fonts) is not found by find_font_face() |
| 106 | `test_motion.py:3369` | no test font for HarfBuzz fitting | ENV | same test_font() check |
| 107 | `test_motion.py:3443` | no test font | ENV | same test_font() check |
| 108 | `test_motion.py:3483` |  is not found by font discovery on this machine | ENV | find_font_file(ps) None: font discovery does not know that PostScript name here |
| 109 | `test_motion.py:3524` |  is not found by font discovery on this machine | ENV | find_font_face(ps) None: same font discovery |
| 110 | `test_motion.py:3550` |  is not found by font discovery on this machine | ENV | find_font_face(ps) None: same font discovery |
| 111 | `test_motion.py:3739` | no test font for HarfBuzz fitting | ENV | same test_font() check |
| 112 | `test_perf.py:383` | this filesystem reports no file ids | ENV | cond not st.st_ino: the filesystem reports no file ids |
| 113 | `test_perf.py:392` | the volume reused the file id | ENV | cond st2.st_ino == st.st_ino: the volume reused the id after os.replace |
| 114 | `test_perf.py:739` | one CPU: the preview is one pass | ENV | cond os.cpu_count() < 2: one-CPU machine |
| 115 | `test_plugin.py:441` | no bash | ENV | cond not self.bash_exe: no bash found |
| 116 | `test_plugin.py:1437` | package.py is not part of this layout | ENV | _load_package_module() None: package.py sits one level above the plugin (:1421) and is not in the plugin zip; present in a repo checkout |
| 117 | `test_plugin.py:1449` | package.py is not part of this layout | ENV | same _load_package_module() layout check |
| 118 | `test_plugin.py:1497` | git ls-files failed:  | ENV | git ls-files returncode != 0 (also skips when not a git checkout, e.g. a git archive snapshot or an unzipped release) |
| 119 | `test_plugin.py:1531` | package.py is not part of this layout | ENV | same _load_package_module() layout check |
| 120 | `test_podcast.py:1289` | no test font found | ENV | cond font is None: no test font found |
| 121 | `test_podcast.py:1554` | no Arabic test font found | ENV | cond font is None: no Arabic test font found |
| 122 | `test_portability.py:389` | no ffmpeg on this machine | ENV | cond not ff: no ffmpeg on this machine |
| 123 | `test_portability.py:854` | PIL / numpy not in this interpreter | ENV | `import PIL, numpy` fails in the running interpreter (the engine runtime has both: find_spec True) |
| 124 | `test_read_once.py:781` | no bash | ENV | cond not shutil.which('bash') |
| 125 | `test_read_once.py:897` | sys.stdlib_module_names needs Python 3.10+ | ENV | sys.stdlib_module_names is None below Python 3.10; the engine runtime is 3.12.15, so it runs |
| 126 | `test_read_once.py:955` | hooks.json does not register read_once.py yet (executor applies hooks.json.patch) | STALE | cond registered() has no read_once.py row in hooks.json; hooks.json:48/62/84 register it at abdece5; landed 074b85b0 (BL-01, ships ON) |
| 127 | `test_read_once.py:981` | hooks.json does not register read_once.py yet (executor applies hooks.json.patch) | STALE | same registered() check; landed 074b85b0 |
| 128 | `test_release_handoff.py:519` | no bash | ENV | rel.find_bash() raises HandoffError: no bash |
| 129 | `test_release_handoff.py:781` | cannot create a directory link here | ENV | cond not make_dir_link(): symlink/junction refused |
| 130 | `test_release_handoff.py:791` | cannot create a directory link here | ENV | cond not make_dir_link(): symlink/junction refused |
| 131 | `test_release_handoff.py:802` | cannot create a directory link here | ENV | cond not make_dir_link(): symlink/junction refused |
| 132 | `test_release_identity_gate.py:407` | git not on PATH | ENV | skipUnless(trh.GIT): git is not on PATH |
| 133 | `test_release_identity_gate.py:438` | git not on PATH | ENV | skipUnless(trh.GIT): git is not on PATH |
| 134 | `test_round4_brand.py:62` | no test font | ENV | test_font() None: no installed test font |
| 135 | `test_round4_brand.py:398` | no test font | ENV | test_font() None: no installed test font |
| 136 | `test_round4_intake.py:392` | no bash | ENV | cond not bash (shutil.which) |
| 137 | `test_runtime.py:310` | no shell for either wrapper | ENV | shells() (:302-310) returns nothing: reel.cmd needs Windows, bin/reel needs git_bash() |
| 138 | `test_runtime.py:377` | no bash | ENV | cond not bash |
| 139 | `test_runtime.py:876` | components.json has no ffmpeg version | OTHER | cond `not components()['ffmpeg']['version']`: setup/components.json has ffmpeg version 9.0.2 at abdece5, so the skip cannot fire; it is a guard against an edit of the file, not a machine fact |
| 140 | `test_runtime.py:924` | no bash | ENV | cond not bash |
| 141 | `test_runtime.py:980` | no bash | ENV | cond not bash |
| 142 | `test_runtime.py:1042` | no bash | ENV | cond not bash |
| 143 | `test_runtime.py:1076` | no shell for either wrapper | ENV | shells() returns nothing (see :310) |
| 144 | `test_runtime.py:1153` | no shell for either wrapper | ENV | no wrapper shell ran |
| 145 | `test_runtime.py:1264` | no shell for either wrapper | ENV | no wrapper shell ran |
| 146 | `test_runtime_locks.py:270` | tests/fixtures/brand_web/tls is not committed yet (J-T1) | STALE | cond cert/key file missing under tests/fixtures/brand_web/tls; both pem files are committed since 75484032 (J-T1, Task 31), present at abdece5 |
| 147 | `test_runtime_locks.py:301` | truststore is not in this runtime yet (the base locks are recompiled by the executor) | PENDING | cond find_spec('truststore') None: same as test_j1_fetch.py:1101, the base lock runtime-win-x64.lock has no truststore; alone-run at 5c2d7b3c: SKIPS on this PC (confirmed); not on release/3.0 |
| 148 | `test_safe_zones_encode.py:289` | this ffmpeg has no libx264:  | ENV | cond ffmpeg returncode: this ffmpeg has no libx264 |
| 149 | `test_schemas.py:450` | no test font for HarfBuzz fitting | ENV | same test_font() check |
| 150 | `test_security_scan.py:41` | scanners not installed: python tools/security/install_tools.py | ENV | skipUnless(TOOLS_OK): the security scanners are not installed (python tools/security/install_tools.py) |
| 151 | `test_security_scan.py:910` | offline: the degraded mode itself is covered by test_offline_deps_is_a_stated_degraded_mode_with_exit_3_throug | ENV | cond scan.is_offline(False): no network |
| 152 | `test_security_scan_findings.py:35` | (empty) | NO-REASON | helper open_issue(): OPEN = {'bootstrap-staging-delete'}; whynot-cut/installer/core/bootstrap.ps1 lines 349 and 356 still have `Remove-Item -Recurse` at abdece5 and 5c2d7b3c (git grep); the test is red-by-design, owner: installer track (now executor) |
| 153 | `test_security_scan_secrets.py:33` | scanners not installed: python tools/security/install_tools.py | ENV | skipUnless(TOOLS_OK): scanners not installed |
| 154 | `test_serve_app.py:371` | no IPv6 loopback on this machine | ENV | ipv6_loopback() (:75): socket.has_ipv6 and bind(('::1', 0)) must work |
| 155 | `test_serve_app.py:474` | no IPv6 loopback on this machine | ENV | same ipv6_loopback() |
| 156 | `test_serve_app.py:1059` | open_project data shape changed | OTHER | cond contract.validate_request(msg) returns errors: the test disables itself if the open_project request shape drifts, so a contract change turns it off silently instead of failing |
| 157 | `test_serve_daemon.py:354` | no IPv6 loopback on this machine | ENV | same ipv6_loopback() |
| 158 | `test_serve_engine_state.py:510` | no directory link here:  | ENV | except OSError/AttributeError around CreateJunction / os.symlink (:505-509) |
| 159 | `test_serve_engine_state.py:757` | FIFOs are POSIX | ENV | skipUnless(hasattr(os, 'mkfifo')): FIFOs are POSIX only |
| 160 | `test_serve_hardening.py:215` | POSIX mode bits | ENV | skipIf(WIN): POSIX mode bits (WIN = os.name == 'nt') |
| 161 | `test_serve_hardening.py:228` | POSIX mode bits | ENV | skipIf(WIN): POSIX mode bits |
| 162 | `test_serve_hardening.py:234` | Windows ACL | ENV | skipUnless(WIN): Windows ACL |
| 163 | `test_serve_hardening.py:243` | Windows ACL | ENV | skipUnless(WIN): Windows ACL |
| 164 | `test_serve_security_e2e.py:336` | no IPv6 on this machine (the daemon serves 127.0.0.1 alone) | ENV | cond not socket.has_ipv6 |
| 165 | `test_serve_security_e2e.py:341` | IPv6 loopback is not available here | ENV | except OSError binding ::1 |
| 166 | `test_serve_security_e2e.py:363` | this machine has no non-loopback IPv4 address to try | ENV | cond addr is None: no non-loopback IPv4 address to try |
| 167 | `test_serve_security_e2e.py:369` | this machine has no non-loopback IPv6 address to try | ENV | cond not addrs: no non-loopback IPv6 address |
| 168 | `test_serve_ws.py:233` | no IPv6 loopback on this machine | ENV | same ipv6_loopback() |
| 169 | `test_serve_ws.py:276` | no IPv6 loopback on this machine | ENV | same ipv6_loopback() |
| 170 | `test_t26_conform_wiring.py:232` | no link:  | ENV | except OSError/CalledProcessError around `mklink /J` / os.symlink (:226-231) |
| 171 | `test_t26_conform_wiring.py:1338` | no link:  | ENV | same link attempt |
| 172 | `test_t26_conform_wiring.py:1460` | this volume makes no 8.3 names | ENV | GetShortPathNameW gives no 8.3 name: the volume has 8.3 names off |
| 173 | `test_t26_conform_wiring.py:1862` | icacls:    | ENV | cond icacls /deny returncode: the ACL change was refused (deny_create(), :1856) |
| 174 | `test_t26_conform_wiring.py:1869` | the deny ACE does not stop this user | ENV | the probe write at :1865 succeeded after the deny-create ACE, so this user is not stopped by it (an account fact) |
| 175 | `test_t415_hooks.py:352` | no bash | ENV | cond not bash |
| 176 | `test_t42_style_knobs.py:555` | no Arabic-capable test font on this machine | ENV | cond font is None: no Arabic-capable test font |
| 177 | `test_t42_style_knobs.py:572` | no scalable font drew the caption on this machine | ENV | cond h0 < 20: no scalable font drew the caption (a rendering probe) |
| 178 | `test_t42_style_knobs.py:845` | caption looks (Task 23) not in this tree | STALE | `from lib import looks` ImportError; lib/looks.py exists since c3ba883a (10-17, Task 23 R-4.1 caption looks), present at abdece5 |
| 179 | `test_t42_style_knobs.py:961` | no test font for HarfBuzz fitting | ENV | M.test_font() is None: no test font |
| 180 | `test_t43_rules_class.py:1219` | the `reel rules` verb and the T43 text hunks are not applied yet (executor) | STALE | RULES_VERB = 'def cmd_rules' in cli.py (:1216); 1 hit at abdece5, added fcb78842 (S1-T4.3 client-rules hooks) |
| 181 | `test_t45_client_db_load.py:256` | no free drive letter for subst | ENV | no free drive letter among Q R S T U V W X Y P for `subst` |
| 182 | `test_t45_client_db_load.py:284` | this computer's admin share is not reachable here | ENV | cond not os.path.exists(\\localhost\C$\...): the admin share is unreachable |
| 183 | `test_t46_music.py:300` | this machine refuses to create a directory link | ENV | cond not make_link(): directory link refused |
| 184 | `test_t46_music.py:394` | no FIFOs on this OS | ENV | skipUnless(hasattr(os, 'mkfifo')): no FIFOs on Windows |
| 185 | `test_t46_music.py:417` | no FIFOs on this OS | ENV | skipUnless(hasattr(os, 'mkfifo')) |
| 186 | `test_t46_music.py:490` | no hard links here | ENV | except OSError around os.link() (:488) |
| 187 | `test_t46_music.py:566` | this machine refuses to create a directory link | ENV | cond not make_link() |
| 188 | `test_t46_music.py:652` | this machine refuses to create a directory link | ENV | cond not make_link() |
| 189 | `test_t46_music.py:1141` | no test font for HarfBuzz fitting | ENV | test_font() None |
| 190 | `test_t46_music.py:1382` | this machine refuses to create a directory link | ENV | cond not make_link(data, real) |
| 191 | `test_t46_music.py:1391` | this machine refuses to create a directory link | ENV | cond not make_link(music, real) |
| 192 | `test_t46_music.py:1478` | no hard links here | ENV | except OSError around os.link() |
| 193 | `test_test_parallel.py:571` | no bash | ENV | cond not bash |
| 194 | `test_tidy_engine.py:304` |  or test_media.js changed shape adobe/tools is not in this checkout (the plugin zip ships the tests but not ad | OTHER | need_fixtures(): fx is None when adobe/tools is absent (plugin zip layout, ENV) OR when test_media.js 'changed shape' (:303); the second cause hides a real drift behind the first reason text |
| 195 | `test_tidy_engine.py:573` | media.js has another shape than the guard reads | OTHER | cond js_literals() is None: media.js has another shape than the guard's parser reads; a drift guard, not a machine fact |
| 196 | `test_token_report.py:1103` | cannot make a directory link here:  | ENV | except OSError around dir_link() (:1101) |
| 197 | `test_wrappers.py:137` | no shell for either wrapper | ENV | wrapper shells() empty (no cmd + no git bash) |
| 198 | `test_wrappers.py:172` | no bash | ENV | cond not git_bash() |
| 199 | `test_wrappers.py:566` | no bash | ENV | cond not self.bash |
| 200 | `test_wrappers.py:660` | no bash | ENV | cond not bash |

## NEW rows on 5c2d7b3c (not in the abdece5 register; added only, as the card asks)

| NEW | file:line (at 5c2d7b3c) | reason | class | owner | evidence |
|---|---|---|---|---|---|
| NEW | `test_bl24_verse_guard.py:83` | (empty) | NO-REASON | executor (BL-24) | helper expected_until(feature) = expectedFailure only while pending(feature): the module lacks USES_VERSE_SOURCE = True. At 5c2d7b3c emphasis.py:50 declares it (task29 is a plain test), cut_proposals no longer uses it (:1033), but motion_plan.py has no USES_VERSE_SOURCE, so the 3 'motion' tests (:1050-1061) are expected failures; BL-24 motion fix NOT on release/3.0 (git grep 5c2d7b3c). HIGH tier, religious |
| NEW | `test_bl24_verse_guard.py:755` | (empty) | OTHER | executor (BL-24) | false positive: `self.assertIsNot(expected_until(feature), unittest.expectedFailure)` is an assertion that the switch turns OFF, not a skip site |
| NEW | `test_bl24_verse_guard.py:937` | no test font for HarfBuzz fitting (motion mode) | ENV | executor (BL-24) | test_font() None: no test font for HarfBuzz fitting (motion mode) |
| NEW | `test_t45_client_db_load.py:363` | this computer's admin share is not reachable here | ENV | executor (BL-14 / J track ended) | cond not os.path.exists(unc(root)): the admin share is unreachable |
| NEW | `test_t45_client_db_load.py:607` | mklink failed here:  | ENV | executor (BL-14 / J track ended) | cond mklink returncode: `cmd /c mklink /J` failed |

`test_bl24_verse_guard.py:755` is a classifier false positive (an assertion that names `unittest.expectedFailure`, not a skip); the audit counts it, so it stays in the 5.

## Optional follow-up (proposed, not built): let the classifier see in-body machine skips

Most of the 170 ENV rows are `self.skipTest(...)` inside an `if`/`try` whose condition is a call to a local helper (`make_dir_link`, `find_bash`, `test_font`, `ipv6_loopback`, `r_safe`) or an `except OSError` around a link or hard-link call, so `PLATFORM_RE` finds nothing it knows and the site falls to `unknown`. A small change in `tools/skip_audit.py` would fix this without loosening the 'for now' rule: (1) add an allow-list of helper names seen in this register (`make_dir_link|make_link|dir_link|find_bash|find_powershell|git_bash|test_font|ipv6_loopback|r_safe|find_font_\w+`) and of exception types (`except (OSError|NotImplementedError|ImportError)` whose try-body calls `os.symlink|os.link|mklink|CreateJunction` or is an import), and treat a match as platform/tool, still beaten by `TEMPORARY_RE`; (2) add one class `layout` for `X is None` / `.exists()` guards on files outside the plugin zip (package.py, adobe/tools). No test needs to change. The 13 STALE rows should stay `unknown` after it: their reasons say 'yet' or 'patch', which `TEMPORARY_RE` rightly keeps listed. Rough size: about 30 lines in `skip_audit.py` plus 6 to 8 unit cases in its test file, half a day for the owner of BL-20 (H2).
