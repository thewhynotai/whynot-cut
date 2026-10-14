#!/usr/bin/env bash
# The macOS CI smoke run (G-T13): shell checks + a fast unit subset. Also runs on Windows Git Bash for a local preview.
#
# Usage:  bash tools/ci/smoke.sh [shell|tests|all]        (default all)
#   shell  bash -n on the installer and the other shipped bash scripts (on macOS with /bin/bash, i.e. bash 3.2, the
#          shell a tester's Mac runs them with), then installer/install.sh --dry-run in a throwaway HOME with a space
#          and Arabic letters, checking it exits 0, says "dry run" and writes nothing.
#   tests  the unit subset below, one `bash tools/test.sh -p <file> [-k <name>]...` per file (test.sh picks the
#          engine runtime from $HOME/.whynot-cut, exactly as on a developer machine). Every file runs even after a
#          failure; a timing table and the failures are printed at the end.
# Exit: 0 all passed, 1 something failed.
# Tests never touch a real engine home: each test module imports tests/_isolation.py first (G79 sandbox).
# bash 3.2 safe (no arrays, no mapfile, no ${x,,}); BSD and GNU tools alike.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
WHAT="${1:-all}"
FAILED=""
SUMMARY=""

note() { printf '%s\n' "$*"; }
fail() { FAILED="${FAILED}  - $*
"; printf 'FAILED: %s\n' "$*" >&2; }

# On GitHub Actions, fold each part of the log.
group() { if [ -n "${GITHUB_ACTIONS:-}" ]; then echo "::group::$*"; else echo "== $*"; fi; }
endgroup() { if [ -n "${GITHUB_ACTIONS:-}" ]; then echo "::endgroup::"; fi; }

# --------------------------------------------------------------------------------------------- shell checks
SHELL_FILES="whynot-cut/installer/install.sh
whynot-cut/installer/core/bootstrap.sh
whynot-cut/setup/setup_env.sh
whynot-cut/bin/reel
whynot-cut/hooks/run_python.sh
whynot-cut/hooks/stop_gate.sh
tools/test.sh
tools/ci/smoke.sh
tools/ci/minutes.sh"

run_shell() {
  local bash_bin="bash" f sb h out rc left
  if [ "$(uname -s)" = "Darwin" ] && [ -x /bin/bash ]; then bash_bin="/bin/bash"; fi   # Apple's bash 3.2
  group "bash -n with $bash_bin ($("$bash_bin" -c 'echo $BASH_VERSION'))"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    if [ ! -f "$f" ]; then fail "bash -n: $f is missing"; continue; fi
    if "$bash_bin" -n "$f" </dev/null; then note "ok  $f"; else fail "bash -n $f"; fi
  done <<EOF
$SHELL_FILES
EOF
  endgroup

  group "install.sh --dry-run in a sandbox HOME"
  sb="$(mktemp -d "${TMPDIR:-/tmp}/wnc-ci-dry.XXXXXX")"
  h="$sb/Home dir عربي"
  mkdir -p "$h"
  # Git Bash (local preview only): install.sh refuses Windows unless the test hook names a platform AND --home is set
  case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) export WNC_TEST_PLATFORM=mac-arm64 ;; esac
  rc=0
  out="$(HOME="$h" bash whynot-cut/installer/install.sh --home "$h" --dry-run --yes </dev/null 2>&1)" || rc=$?
  printf '%s\n' "$out"
  if [ "$rc" -ne 0 ]; then
    fail "install.sh --dry-run exited $rc"
  else
    case "$out" in *"dry run"*) note "ok  install.sh --dry-run said what it would do" ;;
                   *) fail "install.sh --dry-run did not say 'dry run'" ;; esac
  fi
  left="$(find "$h" -mindepth 1 2>/dev/null | head -n 5)" || true   # pipefail: find may get SIGPIPE from head
  if [ -n "$left" ]; then fail "install.sh --dry-run wrote into the sandbox HOME: $left"; else note "ok  the sandbox HOME is still empty"; fi
  rm -rf "$sb"
  endgroup
}

# --------------------------------------------------------------------------------------------- unit subset
# <file pattern>|<-k filters, space separated, may be empty>|<why it is in the smoke run>   ('|': a tab is IFS
# whitespace, so an empty middle field between two tabs would vanish)
SUBSET="test_cli_consistency.py||engine CLI parsing: every command, alias, flag and exit code of reel
test_structure.py||plugin structure: skill/agent frontmatter, references, every reel flag a skill names exists
test_skill_text.py||what the skill texts must and must not say
test_hooks_t34.py||the hooks run on macOS bash/python (file filters, CwdChanged, stop gate)
test_guard_p2.py||the guard (shell command parsing and refusals)
test_crossplatform.py||macOS vs Windows paths, CoreText Arabic shaping, preferences, onboarding
test_portability.py||Arabic/space paths, ffmpeg choice, IS_MAC app and lock paths
test_wrappers.py||the bin/reel bash wrapper with odd paths and plugin options (bash 3.2 on macOS)
test_board.py||reel board and the start/help/status texts
test_isolation.py||the G79 sandbox itself: no test reaches the real engine home
test_installer.py|TestBash TestShellScripts TestStaticChecks TestInstallDryRun TestEngineHomeInTheShells|installer bash core: install.sh/bootstrap.sh on mac-arm64, uninstall, engine home, countdown, dry run"

run_tests() {
  local pat ks why k args start secs rc
  group "engine runtime: $(bash tools/test.sh --which)"
  endgroup
  while IFS='|' read -r pat ks why; do
    [ -n "$pat" ] || continue
    args="-p $pat"
    for k in $ks; do args="$args -k $k"; done
    group "$pat${ks:+ (-k $ks)}: $why"
    start=$SECONDS
    rc=0
    # shellcheck disable=SC2086  # args is a list of plain words (no spaces inside a pattern)
    bash tools/test.sh $args </dev/null || rc=$?   # stdin is the subset list: never hand it to a test
    secs=$((SECONDS - start))
    endgroup
    if [ "$rc" -eq 0 ]; then
      SUMMARY="${SUMMARY}$(printf '  %-24s %4ss  ok' "$pat" "$secs")
"
    else
      SUMMARY="${SUMMARY}$(printf '  %-24s %4ss  FAILED (exit %s)' "$pat" "$secs" "$rc")
"
      fail "$pat${ks:+ -k $ks} (exit $rc)"
    fi
  done <<EOF
$SUBSET
EOF
  printf 'smoke subset timing:\n%s' "$SUMMARY"
}

case "$WHAT" in
  shell) run_shell ;;
  tests) run_tests ;;
  all) run_shell; run_tests ;;
  *) echo "usage: bash tools/ci/smoke.sh [shell|tests|all]" >&2; exit 2 ;;
esac

if [ -n "$FAILED" ]; then
  printf 'smoke: failed:\n%s' "$FAILED" >&2
  exit 1
fi
echo "smoke: all passed"
