#!/usr/bin/env bash
# WhyNot Cut installer bootstrap for macOS (Apple silicon and Intel). Internal: installer/install.sh runs it as
#     bash installer/core/bootstrap.sh --plugin-root <plugin> [the install.sh options]
# It does only what a bare Mac needs before Python exists, then hands over to the installer core:
#   == uv ==      the pinned uv (components.json uv.assets.<platform>): curl into ~/.whynot-cut/downloads, sha256
#                 verified (a mismatch deletes the file and stops), unpacked to ~/.whynot-cut/bin/uv. Already there
#                 at the pinned version: no download.
#   == python ==  uv python install <runtime.python> --no-bin --no-registry into ~/.whynot-cut/python, then
#                 uv python find -> the python-build-standalone interpreter.
#   then          <python> -I -B -X utf8 installer/core/wnc_install.py install|uninstall --plugin-root ... --uv ...
#                 --python ... --log ... (the 14 steps).
# Log: ~/.whynot-cut/logs/install-YYYYmmdd-HHMMSS.log (uninstall-... for --uninstall), shared with the core (--log).
# Exit code: the core's; 2 = cannot start (not macOS, Git Bash/MSYS, unreadable components.json, missing core);
# 3 = a bootstrap step failed (download, sha256, uv, python), with a one-line message and the log path.
# --dry-run writes nothing (no log, no folder); it runs the core's dry run only when uv and Python are already there
# (or WNC_TEST_UV is set), otherwise it names the steps that would follow.
# Sandbox (--home <dir>): HOME, USERPROFILE, APPDATA, LOCALAPPDATA, CLAUDE_CONFIG_DIR and WHYNOT_HOME point into <dir>
# before anything is downloaded (as wnc_installer.base.Paths.child_env does), and --home is passed on. Only then are
# the test hooks honoured: WNC_TEST_PLATFORM (win-x64 | mac-arm64 | mac-x64; lets Git Bash run the macOS path) and
# WNC_TEST_UV (a uv stand-in used for `python install/find` after the real archive was still downloaded and
# verified; a .sh runs with bash, a .py with the JSON-reading python).
# bash 3.2 (the macOS default): no associative arrays, no ${var,,}, no mapfile. No `set -e`: every failure is handled.

STEP_NAMES="preflight questions runtime ffmpeg gitbash gpu claude adobe fonts settings model state doctor launch"
LOG=""
STEP="start"

log_line() { # level text: append to the log (no-op without a log)
  [ -n "$LOG" ] || return 0
  printf '%s %s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$1" "$2" >> "$LOG" 2>/dev/null || true
}
say() { printf '%s\n' "$*"; log_line INFO "$*"; }
step() { STEP="$1"; printf '== %s ==\n' "$1"; log_line STEP "== $1 =="; }
fail() { # one line naming the step, the file and the log; exit 3
  msg="WhyNot Cut bootstrap failed at step $STEP: $1"
  log_line ERROR "$msg"
  [ -n "$LOG" ] && msg="$msg Log: $LOG"
  printf 'ERROR: %s\n' "$msg" >&2
  exit 3
}
stop2() { printf 'ERROR: %s\n' "$1" >&2; exit 2; }
is_placeholder() { [ -z "$1" ] || [ "$1" = "null" ] || case "$1" in "<release"*) true ;; *) false ;; esac; }

pick_py() { # a python that can read JSON (non-macOS only: Git Bash in tests)
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import json' >/dev/null 2>&1 </dev/null; then
      printf '%s\n' "$c"
      return 0
    fi
  done
  return 1
}

# macOS: JavaScript for Automation (built in). Not plutil: it turns JSON into a plist, which has no null, and
# components.json holds nulls. The file and the key path arrive as run() arguments, never inside the script text.
# Prints the value; null, a missing key or an unreadable file print nothing.
JXA_JSON_GET='function run(argv) {
  ObjC.import("Foundation");
  var text = $.NSString.stringWithContentsOfFileEncodingError(argv[0], $.NSUTF8StringEncoding, null);
  if (text.isNil()) { return ""; }
  var v;
  try { v = JSON.parse(ObjC.unwrap(text).replace(/^﻿/, "")); } catch (e) { return ""; }
  var keys = argv[1].split(".");
  for (var i = 0; i < keys.length; i++) {
    if (v === null || typeof v !== "object" || !Object.prototype.hasOwnProperty.call(v, keys[i])) { return ""; }
    v = v[keys[i]];
  }
  if (v === null || v === undefined) { return ""; }
  return (typeof v === "object") ? JSON.stringify(v) : String(v);
}'

json_get() { # file dotted.path -> the value (a string; empty for null or missing)
  if [ "$OS_NAME" = "Darwin" ]; then
    osascript -l JavaScript -e "$JXA_JSON_GET" "$1" "$2" 2>/dev/null </dev/null
    return $?
  fi
  [ -n "$JSON_PY" ] || return 1  # non-macOS (Git Bash in tests) only
  "$JSON_PY" -I -c '
import json, sys
v = json.load(open(sys.argv[1], encoding="utf-8-sig"))
for k in sys.argv[2].split("."):
    v = v.get(k) if isinstance(v, dict) else None
print("" if v is None else v)' "$1" "$2" 2>/dev/null </dev/null | tr -d '\r'
}

file_sha() { # sha256 hex of a file (read on stdin: no path quirks)
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 < "$1" | awk '{print $1}'
  else
    sha256sum < "$1" | awk '{print $1}'
  fi
}

download() { # url sha256 dir -> DL_PATH (verified)
  url="$1"; want="$2"; dir="$3"
  name="${url##*/}"; name="${name%%\?*}"
  [ -n "$name" ] || fail "cannot name the download for $url"
  dest="$dir/$name"
  if [ -f "$dest" ]; then
    if [ "$(file_sha "$dest")" = "$want" ]; then
      say "cached $name (sha256 ok)"; DL_PATH="$dest"; return 0
    fi
    say "cached $name has the wrong sha256; fetching it again"
    rm -f "$dest"
  fi
  mkdir -p "$dir" || fail "cannot create $dir"
  rm -f "$dest.part"
  say "download $url"
  noproxy=""
  case "$url" in http://127.0.0.1[:/]*|http://localhost[:/]*) noproxy="--noproxy" ;; esac
  # curl writes a plain file name inside $dir: a native Windows curl (Git Bash tests) cannot open non-ASCII paths
  if [ -n "$noproxy" ]; then
    err=$( (cd "$dir" && curl -fL --retry 3 --retry-delay 1 -sS --noproxy '*' -o "$name.part" "$url") 2>&1 </dev/null )
  else
    err=$( (cd "$dir" && curl -fL --retry 3 --retry-delay 1 -sS -o "$name.part" "$url") 2>&1 </dev/null )
  fi
  rc=$?
  if [ $rc -ne 0 ]; then
    rm -f "$dest.part"
    fail "could not download $name from $url (curl exit $rc: $(printf '%s' "$err" | tail -n 1))"
  fi
  got="$(file_sha "$dest.part")"
  if [ "$got" != "$want" ]; then
    rm -f "$dest.part"
    fail "sha256 mismatch for $name (expected $want, got $got); the file was deleted"
  fi
  mv -f "$dest.part" "$dest" || fail "cannot move $dest.part into place"
  say "verified $name (sha256 ok)"
  DL_PATH="$dest"
}

unpack_zip() { # zip dir
  if command -v unzip >/dev/null 2>&1; then
    unzip -q -o "$1" -d "$2" </dev/null
  elif [ "$OS_NAME" = "Darwin" ]; then
    ditto -x -k "$1" "$2" </dev/null
  elif [ -n "$JSON_PY" ]; then
    "$JSON_PY" -I -m zipfile -e "$1" "$2" </dev/null
  else
    return 1
  fi
}

uv_run() { # the uv in use: the downloaded one, or the test stand-in
  case "$UV" in
    *.py) "$JSON_PY" -B "$UV" "$@" </dev/null ;;
    *.sh) bash "$UV" "$@" </dev/null ;;
    *) "$UV" "$@" </dev/null ;;
  esac
}

uv_version_ok() { # exe version
  [ -f "$1" ] || return 1
  v="$("$1" --version 2>/dev/null </dev/null | tr -d '\r' | head -n 1)"
  case "$v" in "uv $2" | "uv $2 "*) return 0 ;; *) return 1 ;; esac
}

find_python() { # -> PY (empty when uv has none)
  PY=""
  out="$(uv_run python find "$PY_VER" --python-preference only-managed 2>>"${LOG:-/dev/null}" | tr -d '\r')" || return 1
  last=""
  while IFS= read -r line; do
    [ -n "$line" ] && last="$line"
  done <<EOF
$out
EOF
  [ -n "$last" ] || return 1
  if command -v cygpath >/dev/null 2>&1; then last="$(cygpath -u "$last")"; fi
  [ -f "$last" ] || return 1
  PY="$last"
}

# ------------------------------------------------------------------------------------------- arguments
PLUGIN_ROOT="" HOME_OVR="" DRY="" YES="" CLIENTS="" LANG_OPT="" CHANNEL="" COMPONENTS="" SKIP=""
UNINSTALL="" REMOVE_ENGINE="" REMOVE_MODELS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --plugin-root) PLUGIN_ROOT="$2"; shift ;;
    --home) HOME_OVR="$2"; shift ;;
    --dry-run) DRY=1 ;;
    --yes|-y) YES=1 ;;
    --clients-folder) CLIENTS="$2"; shift ;;
    --language) LANG_OPT="$2"; shift ;;
    --channel) CHANNEL="$2"; shift ;;
    --components) COMPONENTS="$2"; shift ;;
    --skip) if [ -n "$SKIP" ]; then SKIP="$SKIP,$2"; else SKIP="$2"; fi; shift ;;
    --uninstall) UNINSTALL=1 ;;
    --remove-engine) REMOVE_ENGINE=1 ;;
    --remove-models) REMOVE_MODELS=1 ;;
    *) stop2 "bootstrap: unknown option $1" ;;
  esac
  shift
done
[ -n "$PLUGIN_ROOT" ] || stop2 "bootstrap: --plugin-root is required"

abs_path() { # an absolute path (POSIX /x or Windows C:/x stays as it is)
  case "$1" in
    /*|[A-Za-z]:*) printf '%s\n' "$1" ;;
    *) printf '%s/%s\n' "$PWD" "$1" ;;
  esac
}

# ------------------------------------------------------------------------------------------- platform and paths
OS_NAME="$(uname -s)"
PLAT=""
if [ -n "$HOME_OVR" ] && [ -n "${WNC_TEST_PLATFORM:-}" ]; then
  case "$WNC_TEST_PLATFORM" in
    win-x64|mac-arm64|mac-x64) PLAT="$WNC_TEST_PLATFORM" ;;
    *) stop2 "WNC_TEST_PLATFORM=$WNC_TEST_PLATFORM is not one of win-x64, mac-arm64, mac-x64" ;;
  esac
else
  case "$OS_NAME" in
    Darwin)
      if [ "$(uname -m)" = "arm64" ] || [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then
        PLAT="mac-arm64"  # also under Rosetta: the arm64 build is the right one
      else
        PLAT="mac-x64"
      fi ;;
    MINGW*|MSYS*|CYGWIN*) stop2 "this is Windows: use install.ps1 on Windows (PowerShell), not install.sh" ;;
    *) stop2 "WhyNot Cut runs on macOS and Windows x64; this is $OS_NAME $(uname -m)" ;;
  esac
fi

ROOT="$(abs_path "$PLUGIN_ROOT")"
if [ -n "$HOME_OVR" ]; then
  H="$(abs_path "$HOME_OVR")"
  ENGINE="$H/.whynot-cut"
  export HOME="$H" USERPROFILE="$H" APPDATA="$H/AppData/Roaming" LOCALAPPDATA="$H/AppData/Local"
  export CLAUDE_CONFIG_DIR="$H/.claude" WHYNOT_HOME="$ENGINE"
else
  ENGINE="${WHYNOT_HOME:-$HOME/.whynot-cut}"
fi
TEST_UV=""
[ -n "$HOME_OVR" ] && TEST_UV="${WNC_TEST_UV:-}"
JSON_PY=""
if [ "$OS_NAME" != "Darwin" ] || [ "${TEST_UV%.py}" != "$TEST_UV" ]; then JSON_PY="$(pick_py)"; fi

COMP="$ROOT/setup/components.json"
[ -n "$COMPONENTS" ] && COMP="$(abs_path "$COMPONENTS")"
[ -f "$COMP" ] || stop2 "cannot read $COMP"
UV_VER="$(json_get "$COMP" uv.version)"
UV_URL="$(json_get "$COMP" "uv.assets.$PLAT.url")"
UV_SHA="$(json_get "$COMP" "uv.assets.$PLAT.sha256" | tr 'A-F' 'a-f')"
UV_KIND="$(json_get "$COMP" "uv.assets.$PLAT.archive")"
UV_MEMBER="$(json_get "$COMP" "uv.assets.$PLAT.member")"
PY_VER="$(json_get "$COMP" runtime.python)"
if is_placeholder "$UV_URL" || is_placeholder "$UV_VER" || is_placeholder "$PY_VER" \
   || ! printf '%s' "$UV_SHA" | grep -Eq '^[0-9a-f]{64}$'; then
  stop2 "$COMP has no usable uv pin for $PLAT (url, sha256, version) or runtime.python"
fi
CORE="$ROOT/installer/core/wnc_install.py"
[ -f "$CORE" ] || stop2 "the installer core is missing: $CORE"
CMD="install"
[ -n "$UNINSTALL" ] && CMD="uninstall"
if [ -z "$DRY" ]; then
  mkdir -p "$ENGINE/logs" || fail "cannot create $ENGINE/logs"
  LOG="$ENGINE/logs/$CMD-$(date '+%Y%m%d-%H%M%S').log"
  : > "$LOG" || fail "cannot write $LOG"
fi
MODE=""
[ -n "$HOME_OVR" ] && MODE=" (sandbox)"
[ -n "$DRY" ] && MODE="$MODE (dry run: nothing is written)"
say "WhyNot Cut bootstrap: $CMD on $PLAT; engine home $ENGINE$MODE"

# ------------------------------------------------------------------------------------------- == uv ==
step uv
UV_NAME="uv"
case "$PLAT" in win-*) UV_NAME="uv.exe" ;; esac
UV_BIN="$ENGINE/bin/$UV_NAME"
HAVE_UV=""
if uv_version_ok "$UV_BIN" "$UV_VER"; then
  HAVE_UV=1
  say "uv $UV_VER is installed ($UV_BIN)"
elif [ -n "$DRY" ]; then
  say "dry run: would download uv $UV_VER from $UV_URL (sha256 $UV_SHA) and unpack it to $UV_BIN"
else
  download "$UV_URL" "$UV_SHA" "$ENGINE/downloads"
  STAGE="$ENGINE/downloads/uv-$UV_VER.staging"
  rm -rf "$STAGE"
  mkdir -p "$STAGE" || fail "cannot create $STAGE"
  case "$UV_KIND" in
    tar.gz) (cd "$STAGE" && tar -xzf -) < "$DL_PATH" || fail "cannot unpack ${DL_PATH##*/}" ;;
    zip) unpack_zip "$DL_PATH" "$STAGE" || fail "cannot unpack ${DL_PATH##*/}" ;;
    *) fail "uv archive type '$UV_KIND' is not tar.gz or zip" ;;
  esac
  FOUND=""
  if [ -n "$UV_MEMBER" ] && [ -f "$STAGE/$UV_MEMBER" ]; then
    FOUND="$STAGE/$UV_MEMBER"
  else  # anywhere inside the archive, like the Windows side (the layout of uv's archives is not a contract)
    FOUND="$(find "$STAGE" -type f -name "$UV_NAME" 2>/dev/null </dev/null | head -n 1)"
  fi
  [ -n "$FOUND" ] || fail "${DL_PATH##*/} holds no $UV_NAME"
  mkdir -p "$ENGINE/bin" || fail "cannot create $ENGINE/bin"
  if ! { cp "$FOUND" "$UV_BIN.new" && chmod 755 "$UV_BIN.new" && mv -f "$UV_BIN.new" "$UV_BIN"; }; then
    fail "cannot put uv into $UV_BIN"
  fi
  rm -rf "$STAGE"
  HAVE_UV=1
  say "uv $UV_VER unpacked to $UV_BIN"
fi
UV="$UV_BIN"
if [ -n "$TEST_UV" ]; then
  UV="$TEST_UV"
  say "test hook: WNC_TEST_UV=$TEST_UV stands in for uv"
fi

# ------------------------------------------------------------------------------------------- == python ==
step python
export UV_PYTHON_INSTALL_DIR="$ENGINE/python" UV_CACHE_DIR="$ENGINE/cache/uv" UV_NO_CONFIG=1
export UV_PYTHON_PREFERENCE=only-managed UV_NO_MODIFY_PATH=1
PY=""
if [ -n "$HAVE_UV" ] || [ -n "$TEST_UV" ]; then find_python; fi
if [ -z "$PY" ]; then
  if [ -n "$DRY" ]; then
    say "dry run: would install Python $PY_VER with uv into $UV_PYTHON_INSTALL_DIR (--no-bin --no-registry)"
    say "dry run: then the installer core would run these steps: $(printf '%s' "$STEP_NAMES" | sed 's/ /, /g')"
    exit 0
  fi
  say "installing Python $PY_VER into $UV_PYTHON_INSTALL_DIR"
  out="$(uv_run python install "$PY_VER" --no-bin --no-registry 2>&1)"
  rc=$?
  printf '%s\n' "$out" | while IFS= read -r line; do log_line INFO "  $line"; done
  [ $rc -eq 0 ] || fail "uv could not install Python $PY_VER (exit $rc): $(printf '%s' "$out" | tail -n 1)"
  find_python
  [ -n "$PY" ] || fail "uv installed Python $PY_VER but cannot find it"
fi
say "Python $PY_VER at $PY"

# ------------------------------------------------------------------------------------------- the core
set -- -I -B -X utf8 "$CORE" "$CMD" --plugin-root "$ROOT" --uv "$UV" --python "$PY"
[ -n "$LOG" ] && set -- "$@" --log "$LOG"
[ -n "$HOME_OVR" ] && set -- "$@" --home "$H"
[ -n "$COMPONENTS" ] && set -- "$@" --components "$COMP"
[ -n "$DRY" ] && set -- "$@" --dry-run
[ -n "$YES" ] && set -- "$@" --yes
[ -n "$SKIP" ] && set -- "$@" --skip "$SKIP"
[ -n "$CLIENTS" ] && set -- "$@" --clients-folder "$(abs_path "$CLIENTS")"
[ -n "$LANG_OPT" ] && set -- "$@" --language "$LANG_OPT"
[ -n "$CHANNEL" ] && set -- "$@" --channel "$CHANNEL"
[ -n "$UNINSTALL" ] && [ -n "$REMOVE_ENGINE" ] && set -- "$@" --remove-engine
[ -n "$UNINSTALL" ] && [ -n "$REMOVE_MODELS" ] && set -- "$@" --remove-models
log_line INFO "bootstrap: running the installer core: $PY $*"
if [ -t 0 ]; then
  "$PY" "$@"
else
  "$PY" "$@" </dev/null  # stdin may be the script itself (curl | bash): the core asks through /dev/tty instead
fi
exit $?
