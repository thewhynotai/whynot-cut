#!/usr/bin/env bash
# GitHub Actions minutes this month: used and remaining against the free plan (G-T13; Addendum F zero-cost rule).
# Read-only: only GET calls through `gh api`. Never writes to GitHub.
#
# Usage:  bash tools/ci/minutes.sh [owner/repo]        (default: thewhynotai/whynot-cut)
# Env:    WNC_CI_FREE_MINUTES  the plan's included minutes (default 2000, GitHub Free for a personal account)
#         WNC_CI_WARN_LEFT     warn and exit 3 when fewer weighted minutes than this remain (default 400)
#
# Weighting: GitHub counts a macOS minute as 10 and a Windows minute as 2 against the included minutes; a Linux minute
# as 1. Every job is billed in whole minutes, rounded up.
#
# Two sources, the first that answers wins:
#   1. the account's billing usage report (GET /users/<owner>/settings/billing/usage?year=&month=). Exact, covers every
#      repository of the account. Needs the token's `user` scope (once: gh auth refresh -h github.com -s user).
#   2. otherwise an estimate from this repository's own workflow runs this month (GET .../actions/runs and .../jobs):
#      each job's wall time rounded up to a minute, weighted by its runner label. Counts this repository only.
#
# Exit: 0 fine, 3 below WNC_CI_WARN_LEFT (or over the plan), 2 gh missing / not logged in / nothing answered.
# bash 3.2 safe; works with BSD and GNU date (no date -d); JSON is read with gh's built-in --jq (no jq needed).
set -euo pipefail

REPO="${1:-thewhynotai/whynot-cut}"
OWNER="${REPO%%/*}"
FREE="${WNC_CI_FREE_MINUTES:-2000}"
WARN="${WNC_CI_WARN_LEFT:-400}"
YEAR="$(date -u +%Y)"
MON="$(date -u +%m)"
MONTH_START="$YEAR-$MON-01"
MON_N=$((10#$MON))

command -v gh >/dev/null 2>&1 || { echo "minutes: gh (GitHub CLI) is not installed" >&2; exit 2; }
gh auth status >/dev/null 2>&1 || { echo "minutes: gh is not logged in (gh auth login)" >&2; exit 2; }

linux=0 windows=0 macos=0 source=""

# --------------------------------------------------------------------------- 1. billing usage report (exact)
# One line per usage item: "<sku>\t<quantity>"; only Actions minutes.
JQ_USAGE='.usageItems[]? | select((.product|ascii_downcase)=="actions") | select((.unitType|ascii_downcase)=="minutes") | "\(.sku)\t\(.quantity)"'
if usage="$(gh api -X GET "users/$OWNER/settings/billing/usage" -f year="$YEAR" -f month="$MON_N" --jq "$JQ_USAGE" 2>/dev/null)"; then
  source="billing usage report (account $OWNER, all repositories)"
  while IFS="$(printf '\t')" read -r sku qty; do
    [ -n "${sku:-}" ] || continue
    q="${qty%%.*}"                                  # whole minutes (the report may give decimals)
    case "$qty" in *.*) [ "${qty#*.}" = "0" ] || [ -z "${qty#*.}" ] || q=$((q + 1)) ;; esac
    lsku="$(printf '%s' "$sku" | tr '[:upper:]' '[:lower:]')"
    case "$lsku" in
      *macos*) macos=$((macos + q)) ;;
      *windows*) windows=$((windows + q)) ;;
      *) linux=$((linux + q)) ;;
    esac
  done <<EOF
$usage
EOF
fi

# --------------------------------------------------------------------------- 2. estimate from this repo's runs
if [ -z "$source" ]; then
  # one line per finished job: "<os>\t<whole minutes>"; os from the runner labels (macos / windows / other)
  JQ_JOBS='.jobs[] | select(.started_at != null and .completed_at != null)
    | ((.completed_at|fromdateiso8601) - (.started_at|fromdateiso8601)) as $s
    | (if $s <= 0 then 0 else (($s + 59) / 60 | floor) end) as $m
    | ((.labels // []) | map(ascii_downcase) | join(" ")) as $l
    | (if ($l|test("macos")) then "macos" elif ($l|test("windows")) then "windows" else "linux" end) + "\t\($m)"'
  if ids="$(gh api --paginate -X GET "repos/$REPO/actions/runs" -f created=">=$MONTH_START" -f per_page=100 \
              --jq '.workflow_runs[].id' 2>/dev/null)"; then
    source="estimate from $REPO workflow runs since $MONTH_START (this repository only; add the gh 'user' scope for the exact account figure)"
    for id in $ids; do
      jobs="$(gh api --paginate "repos/$REPO/actions/runs/$id/jobs?per_page=100" --jq "$JQ_JOBS" 2>/dev/null)" || continue
      while IFS="$(printf '\t')" read -r os m; do
        [ -n "${os:-}" ] || continue
        case "$os" in
          macos) macos=$((macos + m)) ;;
          windows) windows=$((windows + m)) ;;
          *) linux=$((linux + m)) ;;
        esac
      done <<EOF
$jobs
EOF
    done
  fi
fi

[ -n "$source" ] || { echo "minutes: GitHub did not answer (network, or no access to $REPO)" >&2; exit 2; }

used=$((linux + windows * 2 + macos * 10))
left=$((FREE - used))
echo "Actions minutes, $YEAR-$MON (UTC month), from the $source"
echo "  macOS   $macos min  x10 = $((macos * 10))"
echo "  Windows $windows min  x2  = $((windows * 2))"
echo "  Linux   $linux min  x1  = $linux"
echo "  used    $used of $FREE weighted minutes"
echo "  left    $left  (= about $(( (left > 0 ? left : 0) / 10 )) macOS minutes: ~$(( (left > 0 ? left : 0) / 60 )) smoke runs or ~$(( (left > 0 ? left : 0) / 300 )) full runs)"
if [ "$left" -lt "$WARN" ]; then
  echo "WARNING: fewer than $WARN weighted minutes left this month. Push release/3.0 and mac/dev batches with [skip ci]"
  echo "         (each push runs the smoke job) and skip the full run until the 1st; see docs/ci.md." >&2
  exit 3
fi
exit 0
