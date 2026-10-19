# BL-16 patches (outside H1's fence)

Made with `git diff` against `h1/BL-16` (commit after the BL-16 feat commit). Apply on top of that branch, from the
repo root: `git apply --check <patch>` then `git apply <patch>`.

| Patch | For | What |
|---|---|---|
| `1-executor-setup_env-lock-on-create.patch` | executor | `reel setup` prepares the engine home through `home_acl.prepare_home` BEFORE `find_uv` (whose download writes `home\bin`): a new home outside the profile is locked; an existing one other accounts may write in, or a failed lock, stops setup with the Arabic-first line and the exact icacls command. Tests in `test_runtime.py`: `TestSetupLocksANewHome` (2, including the order prepare → find_uv) and the warning pin (names `<drive>:\WhyNotCut`, never `C:\whynot`). |
| `2-adobe-ae_render-suggested-home.patch` | ADOBE-G4 | the aerender `StageError` names `portability.suggested_home()` and `reel setup`; the old `setx TEMP C:\Temp` alternative is dropped (also a folder at the root of C:\). Test: `test_portability.TestAsciiAeStage.test_no_root_gives_a_precise_how`. |

Ticket for the installer track (not a patch here, `installer/**` is outside every BL-16 fence): `bootstrap.ps1`
(lines ~306, 353, 1885) creates `downloads`, `bin` and `logs` in the engine home before anything else. For a home
outside the profile it should create the home through the same lock (or call `home_acl.prepare_home`) first;
until then a later `reel setup` refuses such a home with the exact command, and doctor flags it.

No `cli.py` hunk is needed: doctor reaches the new check through `portability.doctor_checks` (owned file), which
`onboard.doctor()` already calls. No skill text other than `platform-setup.md` (owned) named `C:\whynot`.
