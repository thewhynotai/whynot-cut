# T3.9 Permissions convenience - report

`reel settings --allow-reel [--clients-root DIR] [--json]` (engine/reel/lib/claude_perms.py, cli.py hunk, tests/test_allow_reel.py).

- Rules added: `Bash(reel *)`, `PowerShell(reel *)`. Verified against https://code.claude.com/docs/en/permissions (2026-10-13): PowerShell(...) is a real rule
  name with the Bash shape; a trailing ` *` (with the space) also matches bare `reel` and not `reelx`; `:*` is an equivalent spelling (counted as present).
- Not added: the wrapper's absolute path form (bin/reel, bin\reel.cmd): it is in the plugin cache folder whose name changes per version, Claude Code strips only
  timeout/time/nice/nohup/stdbuf, and Claude writes `reel ...` (bin/ is on PATH); an absolute-path call simply prompts (safe default).
- Project allow rules apply only after the editor accepts the workspace-trust dialog for the folder (docs); note for T3.10.
- Merge: other keys/order/rules kept; no duplicates; backup `settings.json.whynot-backup-<stamp>` only before a change to an existing file (a no-op run writes nothing,
  so reruns never add backups); BOM tolerated (rewrite drops it); comments/trailing commas/wrong shapes -> Guidance, file untouched; never prompts.
- Root check: exists; not a client folder / inside one; accepted if empty (new), the configured clients folder, or it holds a client folder.
- Output: `{ok, file, added, backup, changed}`; failure `{ok:false, error, where, how}` exit 1.
- Tests: test_allow_reel.py 12 OK; test_isolation 18, test_errors 30, test_writer_lock 34, test_cli_consistency 57, test_structure 8 all OK.
