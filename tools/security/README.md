# tools/security: the local scan kit (Addendum L §L3, Phase 4 Tasks 39-41, 48)

One entry point, free scanners only, everything local first (CI runs the same command on tags).

```
python tools/security/install_tools.py          # once per PC: pinned, sha256-checked, per user under D:/ClaudeData/tools/security
python tools/security/install_tools.py --check  # verify only (no network): installed, unaltered (binaries + every wheel file)
python tools/security/scan.py --all [--history] [--gate <name>]
```

`scan.py --all` = Semgrep (our `.semgrep/` rules + the registry packs p/python p/javascript p/typescript p/secrets,
`--metrics=off`) + Bandit (4 folders, B404/B603 skipped by rule, `# nosec` needs a reason) + ESLint security plugins
(Adobe track patch) + gitleaks (tree, and with `--history` the full history) +
pip-audit (every lock, `--require-hashes --disable-pip --no-deps`) + OSV-Scanner (explicit lock types) + `npm audit`
(prod and full) + the lock-hash check + a CycloneDX SBOM. Summary: `docs/security/scan-<date>-<gate>.md`; raw JSON
(scrubbed of source text and secret values) under `dist/` (git-ignored).

**Gates:** run the suite with `WNC_REQUIRE_SCANNERS=1` (the executor sets it for a Gate suite): a missing or altered scanner then FAILS the
scan tests instead of skipping them. Nothing in the repo sets it by itself.

**Exit codes:** 0 clean, 1 a new High/Critical not in `docs/security/baseline.json`, 2 usage/baseline problem,
3 degraded (a database or rule pack was not checked, coverage partial), 4 a scanner is missing, the wrong version,
altered after install, or failed. Zero locks / zero files scanned is a failure, never a pass. A degraded scanner is
accepted only through a `known_gaps` entry in the baseline for that exact tool and reason code (offline, registry-skipped, scan-errors,
skipped-files, skipped-requirements, plugins-missing, parse-errors) with a reason, an owner task and a review date. Secret findings can never be
baselined: a real one is rotated by the owner (HL5/H35) and handed over without its value; a fake one gets an exact
allow rule in `.gitleaks.toml` (one file + one exact value + `targetRules`; see that file's header for the gitleaks quirk).

## What the Semgrep rules cannot see (so nobody trusts them more than they deserve)
| Rule | Sees | Does not see |
|---|---|---|
| wnc-tls-disabled | verify=False/0, ssl=False, CERT_NONE, check_hostname=False, unverified context, inject_into_ssl, PYTHONHTTPSVERIFY, `--insecure` | a flag held in a variable, `**kwargs` |
| wnc-shell-true | shell=<not False>, os.system/popen, getoutput, create_subprocess_shell | `**kwargs` carrying shell |
| wnc-remove-item-recurse / -recursive-delete-string / wnc-ps-* | the command on one line before any `#` (also -r/-rec, backtick continuation in scripts) | a literal split across two string pieces; a `#` earlier on the line (`Write-Host "#1"; Remove-Item -Recurse`); `Get-ChildItem -Recurse | Remove-Item`; a docstring that quotes the command fires (baseline it) |
| wnc-client-path-write(-nomode) | literal paths naming `WhyNot Clients`, also inside `Path(..) / ..` | a path held in a variable: that is the write gate (L-T8) |
| wnc-bare-executable(-string/-var) | `[ "x", ..]` / `("x",)` / `"x args"` first element a bare name; a literal list assigned then passed in the same block | a list built by other means; Mac-only programs also fire (baseline them) |
| wnc-which-system-tool | `shutil.which("icacls")` and the other Windows system tools (current-folder / PATH hijack, L-G11) | a tool name in a variable |
| wnc-js-shell-exec(-receiver) | child_process exec/execSync on `require("child_process")`, on receivers named cp/child_process/childProcess/proc/child/cproc/sh/shell (also `this.cp`), spawn with `shell: true` | another alias name; `util.promisify(cp.exec)`; a local function called `execSync` fires |
| wnc-raw-innerhtml | any assignment/sink whose whole right side is not a literal or ONE call to a named kit function | types: a correctly typed `Html` value held in a variable is flagged (baseline it) |

The write gate (L-T8), the executable audit (L-T4) and the escape lint (L-T7) are the real protections; these rules are
the tripwire that keeps new code from walking around them.
