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
# --uninstall runs on the engine's own Python when it is there (uv python find with the uv in bin/, at any version,
# else python/cpython-<ver>*/bin/python3): nothing is downloaded; only without one are uv and Python fetched as above.
# --uninstall --remove-engine: the core leaves python/ and bin/ (the Python it runs on, and uv) and lists them, plus the
# engine home itself when nothing else is left, in <engine>/.delete-after-exit. Once the core has exited, this script
# deletes what that list names, but ONLY <engine>/python and <engine>/bin (every line normalised first; anything else
# is refused and reported), never through a link (a link is removed as a link), and the engine home itself only when
# it is then empty; then the list file. The log went with logs/, so the summary is on the console only. The newest
# engine Python is chosen by version number (3.12.15 before 3.12.9).
# Log: ~/.whynot-cut/logs/install-YYYYmmdd-HHMMSS.log (uninstall-... for --uninstall), shared with the core (--log).
# Exit code: the core's; 2 = cannot start (not macOS, Git Bash/MSYS, unreadable components.json, missing core);
# 3 = a bootstrap step failed (download, sha256, uv, python), with a one-line message and the log path.
# --dry-run writes nothing (no log, no folder); it runs the core's dry run only when uv and Python are already there
# (or WNC_TEST_UV is set), otherwise it names the steps that would follow.
# Engine home: resolved exactly like the engine (resolve_engine_home: WHYNOT_HOME and the other engine-home variables,
# else the plugin option engine_home from ~/.whynot-cut/plugin-options.json, else from settings.json pluginConfigs,
# else ~/.whynot-cut) BEFORE anything is downloaded. That folder is the default of the location question (owner
# decision 2026-10-12): --engine-home <folder> answers it, --yes takes the default, without a terminal the default is
# used; the answer is read from the terminal, or from /dev/tty when stdin is not one (never from stdin under
# `curl | bash`). It is checked (engine_home_problem: a full path, not a drive root, not inside the plugin folder,
# not the user folder or Claude's folder, not the clients folder or a folder marked .whynot-client, in a sandbox
# inside the sandbox; 6 GB free on its drive, 9 GB with the Whisper model, unless WhyNot Cut is already there; it can
# be created and written); a refused folder is asked again (with --yes: exit 2, nothing downloaded). uv, Python, the
# log and every later step land in that one folder: it is passed to the core as --engine-home (+ --engine-home-chosen
# when the editor chose it: the core then uses it as it is; otherwise the core stops with 2 if its own resolution,
# wnc_installer.base.resolve_engine_home, disagrees). The core remembers a chosen folder in settings.json pluginConfigs
# and the pointer file. --uninstall asks nothing: the resolved folder, or --engine-home. --model <large-v3 |
# large-v3-turbo | medium | small> goes to the core (its model question).
# Sandbox (--home <dir>): HOME, USERPROFILE, APPDATA, LOCALAPPDATA, CLAUDE_CONFIG_DIR and WHYNOT_HOME point into <dir>
# before anything is downloaded (as wnc_installer.base.Paths.child_env does), and --home is passed on; the engine home
# is resolved from the sandbox's own pointer / settings.json only. Only then are the test hooks honoured:
# WNC_TEST_PLATFORM (win-x64 | mac-arm64 | mac-x64; lets Git Bash run the macOS path), WNC_TEST_UV (a uv stand-in used
# for `python install/find` after the real archive was still downloaded and verified; a .sh runs with bash, a .py
# with the JSON-reading python), WNC_TEST_ANSWERS (a file: one answer per line for the location question) and
# WNC_TEST_FREE_GB (the free space the check sees).
# bash 3.2 (the macOS default): no associative arrays, no ${var,,}, no mapfile. No `set -e`: every failure is handled.

STEP_NAMES="preflight questions runtime ffmpeg gitbash gpu claude adobe fonts settings model state doctor launch"
UNINSTALL_STEP_NAMES="plugin adobe fonts marketplace engine"  # wnc_installer/uninstall.py STEP_NAMES
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

ver_key() { # "3.12.15" -> "000030001200015": versions compare as text, numerically (3.12.15 after 3.12.9)
  local IFS=. a b c
  set -f
  # shellcheck disable=SC2086  # split on dots on purpose
  set -- $1
  set +f
  a="${1:-0}" b="${2:-0}" c="${3:-0}"
  case "$a$b$c" in *[!0-9]*) printf '0'; return 0 ;; esac
  printf '%05d%05d%05d' "$((10#$a))" "$((10#$b))" "$((10#$c))"
}

engine_python() { # uninstall: the python-build-standalone already in the engine home -> PY (nothing is downloaded)
  PY=""
  if [ -n "$TEST_UV" ] || [ -f "$UV_BIN" ]; then
    UV="$UV_BIN"
    [ -n "$TEST_UV" ] && UV="$TEST_UV"
    if find_python; then return 0; fi
  fi
  PY=""
  best=""
  for cand in "$ENGINE"/python/cpython-"$PY_VER"*/bin/python3; do  # the newest version number that starts
    [ -f "$cand" ] || continue
    v="${cand#"$ENGINE"/python/cpython-}"
    k="$(ver_key "${v%%-*}")"
    if [ -n "$best" ] && ! [ "$k" \> "$best" ]; then continue; fi
    if "$cand" -I -B -c pass >/dev/null 2>&1 </dev/null; then PY="$cand"; best="$k"; fi
  done
  [ -n "$PY" ]
}

norm_path() { # lexical: \ (Git Bash), repeated /, . and .. resolved, no trailing / -> NORM; lower case on Windows
  local p="$1" out="" part lead=""
  case "$OS_NAME" in
    MINGW*|MSYS*|CYGWIN*)
      p="${p//\\//}"
      case "$p" in /[a-zA-Z]|/[a-zA-Z]/*) p="${p:1:1}:${p:2}" ;; esac ;;  # Git Bash /c/x is C:/x
  esac
  case "$p" in /*) lead="/" ;; esac
  local IFS=/
  set -f
  for part in $p; do
    case "$part" in
      ''|.) ;;
      ..) out="${out%/*}" ;;
      *) out="$out/$part" ;;
    esac
  done
  set +f
  if [ -n "$lead" ]; then NORM="${out:-/}"; else NORM="${out#/}"; fi
  case "$OS_NAME" in MINGW*|MSYS*|CYGWIN*) NORM="$(printf '%s' "$NORM" | tr '[:upper:]' '[:lower:]')" ;; esac
}

delete_deferred() { # after `uninstall --remove-engine`: $ENGINE/.delete-after-exit may name ONLY python/, bin/, $ENGINE
  list="$ENGINE/.delete-after-exit"
  [ -f "$list" ] || return 0
  root="$ENGINE"
  while [ "${root%/}" != "$root" ] && [ "$root" != "/" ]; do root="${root%/}"; done
  if [ -L "$root" ]; then
    printf 'WARNING: %s is a link; the paths in %s were left alone\n' "$root" "$list"
    return 0
  fi
  norm_path "$root"; nroot="$NORM"
  home_too="" failed=""
  while IFS= read -r p || [ -n "$p" ]; do
    p="${p%$'\r'}"
    [ -n "$p" ] || continue
    norm_path "$p"
    target=""
    case "$NORM" in
      "$nroot") home_too=1; continue ;;
      "$nroot/python") target="$root/python" ;;
      "$nroot/bin") target="$root/bin" ;;
    esac
    if [ -z "$target" ]; then
      printf "WARNING: refused '%s' in %s (only python/ and bin/ of %s may be listed)\n" "$p" "$list" "$root"
      continue
    fi
    if [ -L "$target" ]; then
      rm -f "$target"  # the link only, never its target
    else
      rm -rf "$target"  # rm removes a link inside as a link; it never follows one
    fi
    if [ -e "$target" ] || [ -L "$target" ]; then
      failed=1
      printf 'WARNING: could not delete %s; delete it by hand\n' "$target"
    else
      printf 'deleted %s\n' "$target"
    fi
  done < "$list"
  rm -f "$list"
  if [ -n "$home_too" ] && [ -z "$failed" ] && rmdir "$root" 2>/dev/null; then printf 'deleted %s\n' "$root"; fi
  return 0
}

# ------------------------------------------------------------------------------------------- arguments
PLUGIN_ROOT="" HOME_OVR="" DRY="" YES="" CLIENTS="" LANG_OPT="" CHANNEL="" COMPONENTS="" SKIP=""
UNINSTALL="" REMOVE_ENGINE="" REMOVE_MODELS="" ENGINE_OPT="" MODEL_OPT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --plugin-root) PLUGIN_ROOT="$2"; shift ;;
    --home) HOME_OVR="$2"; shift ;;
    --engine-home) ENGINE_OPT="$2"; shift ;;
    --model) MODEL_OPT="$2"; shift ;;
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
case "$MODEL_OPT" in
  ""|large-v3|large-v3-turbo|medium|small) ;;  # wnc_installer/system.py MODELS
  *) stop2 "--model $MODEL_OPT is not one of large-v3, large-v3-turbo, medium, small" ;;
esac

abs_path() { # an absolute path (POSIX /x or Windows C:/x stays as it is)
  case "$1" in
    /*|[A-Za-z]:*) printf '%s\n' "$1" ;;
    *) printf '%s/%s\n' "$PWD" "$1" ;;
  esac
}

home_path() { # a configured path: ~ and ~/x are under $HOME, a relative one is made absolute (the core's abspath)
  case "$1" in
    \~) abs_path "$HOME" ;;
    \~/*) abs_path "$HOME/${1#\~/}" ;;
    *) abs_path "$1" ;;
  esac
}

saved_engine_home() { # pointer-file settings-file -> "pointer<TAB>value", "settings<TAB>key<TAB>value" or "none"
  # the plugin option engine_home as the engine reads it (engine/reel/lib/plat.py saved_options): the pointer file
  # when it is a JSON object with an "engine_home" string ("" = not set), else settings.json pluginConfigs
  # ["whynot-cut@thewhynot-ai"].options, else the first other whynot-cut@* entry (file order) with options. Both
  # files are UTF-8 without a BOM (a BOM is not JSON, as for the engine). macOS: JXA; elsewhere (Git Bash in tests)
  # the same rules in Python.
  local js py
  js='function run(argv) {
    ObjC.import("Foundation");
    function isObj(v) { return v !== null && typeof v === "object" && !Array.isArray(v); }
    function own(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }
    function load(p) {
      var t = $.NSString.stringWithContentsOfFileEncodingError(p, $.NSUTF8StringEncoding, null);
      if (t.isNil()) { return null; }
      var s = ObjC.unwrap(t);
      if (s.charCodeAt(0) === 0xFEFF) { return null; }
      try { var v = JSON.parse(s); return isObj(v) ? v : null; } catch (e) { return null; }
    }
    var p = load(argv[0]);
    if (p !== null && own(p, "engine_home") && typeof p.engine_home === "string") {
      return "pointer\t" + p.engine_home;
    }
    var s = load(argv[1]);
    var c = (s !== null && own(s, "pluginConfigs")) ? s.pluginConfigs : null;
    if (!isObj(c)) { return "none"; }
    var keys = ["whynot-cut@thewhynot-ai"];
    Object.keys(c).forEach(function (k) { if (k.indexOf("whynot-cut@") === 0 && k !== keys[0]) { keys.push(k); } });
    for (var i = 0; i < keys.length; i++) {
      var e = own(c, keys[i]) ? c[keys[i]] : null;
      if (isObj(e) && own(e, "options") && isObj(e.options)) {
        var h = e.options.engine_home;
        return "settings\t" + keys[i] + "\t" + (typeof h === "string" ? h : "");
      }
    }
    return "none";
  }'
  py='import json, sys
def load(p):
    try:
        v = json.loads(open(p, encoding="utf-8").read())
    except (OSError, ValueError):
        return None
    return v if isinstance(v, dict) else None
p = load(sys.argv[1])
if p is not None and isinstance(p.get("engine_home"), str):
    print("pointer\t" + p["engine_home"])
    sys.exit(0)
c = (load(sys.argv[2]) or {}).get("pluginConfigs") or {}
ours = "whynot-cut@thewhynot-ai"
for k in ([ours] + [k for k in c if k.startswith("whynot-cut@") and k != ours]) if isinstance(c, dict) else []:
    e = c.get(k)
    if isinstance(e, dict) and isinstance(e.get("options"), dict):
        h = e["options"].get("engine_home")
        print("settings\t" + k + "\t" + (h if isinstance(h, str) else ""))
        sys.exit(0)
print("none")'
  if [ "$OS_NAME" = "Darwin" ]; then
    osascript -l JavaScript -e "$js" "$1" "$2" 2>/dev/null </dev/null
  elif [ -n "$JSON_PY" ]; then
    "$JSON_PY" -I -X utf8 -c "$py" "$1" "$2" 2>/dev/null </dev/null | tr -d '\r'
  else
    printf 'none\n'
  fi
}

resolve_engine_home() { # [sandbox]: the engine home the engine itself uses -> ENGINE, ENGINE_SRC
  # engine/reel/lib/plat.py engine_home (the core's wnc_installer.base.resolve_engine_home is the same): the first
  # engine-home variable that is set, else the saved plugin option (saved_engine_home), else ~/.whynot-cut. The
  # sources are named like the core's: env:<NAME>, pointer:<file>, settings:<file> <key>, default. "sandbox": no
  # variable at all, only $HOME/.whynot-cut/plugin-options.json and $HOME/.claude/settings.json.
  local n v pointer cfg out rest key src sandbox="${1:-}"
  if [ -z "$sandbox" ]; then
    for n in WHYNOT_HOME CLAUDE_PLUGIN_OPTION_ENGINE_HOME REEL_HOME CLAUDE_PLUGIN_OPTION_REEL_HOME NH_ENV_DIR; do
      v="${!n:-}"
      if [ -n "$v" ]; then ENGINE="$(home_path "$v")"; ENGINE_SRC="env:$n"; return 0; fi
    done
  fi
  pointer="$HOME/.whynot-cut/plugin-options.json"
  if [ -z "$sandbox" ] && [ -n "${WHYNOT_OPTIONS_FILE:-}" ]; then pointer="$(home_path "$WHYNOT_OPTIONS_FILE")"; fi
  cfg="$HOME/.claude"
  if [ -z "$sandbox" ] && [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then cfg="$(home_path "$CLAUDE_CONFIG_DIR")"; fi
  out="$(saved_engine_home "$pointer" "$cfg/settings.json")"
  v="" src=""
  case "$out" in
    pointer$'\t'*) v="${out#*$'\t'}"; src="pointer:$pointer" ;;
    settings$'\t'*)
      rest="${out#*$'\t'}"; key="${rest%%$'\t'*}"; v="${rest#*$'\t'}"
      src="settings:$cfg/settings.json $key" ;;
  esac
  if [ -n "$v" ]; then
    ENGINE="$(home_path "$v")"; ENGINE_SRC="$src"
  else
    ENGINE="$HOME/.whynot-cut"; ENGINE_SRC="default"
  fi
}

# ------------------------------------------------------------------------------------------- the location question
NEED_GB=6 MODEL_GB=3  # free space for the engine, + the Whisper model (wnc_installer/system.py RED_GB / AMBER_GB)

within() { # a b (both from norm_path): a is b or below it
  [ "$1" = "$2" ] && return 0
  case "$1" in "${2%/}"/*) return 0 ;; esac
  return 1
}

client_roots() { # -> CLIENT_ROOTS (one per line): clients_root of the preferences file and of the pointer file
  local prefs="$HOME/.claude/whynot-cut.local.md" v
  CLIENT_ROOTS=""
  if [ -f "$prefs" ]; then
    v="$(awk 'NR == 1 && !/^---/ { exit } NR > 1 && /^---/ { exit }
              NR > 1 && /^[[:space:]]*clients_root[[:space:]]*:/ {
                sub(/^[[:space:]]*clients_root[[:space:]]*:[[:space:]]*/, ""); print; exit }' "$prefs" 2>/dev/null \
         | tr -d '\r')"
    case "$v" in
      \"*\") v="${v#\"}"; v="${v%\"}" ;;
      \'*\') v="${v#\'}"; v="${v%\'}" ;;
      *) v="${v%% #*}" ;;
    esac
    [ -n "$v" ] && CLIENT_ROOTS="$(home_path "$v")"
  fi
  v="$(json_get "$POINTER" clients_root)"
  if [ -n "$v" ]; then CLIENT_ROOTS="$CLIENT_ROOTS"$'\n'"$(home_path "$v")"; fi
}

typed_path() { # text -> TYPED: quotes trimmed, ~ is the home folder, no trailing / (any other text stays as typed)
  local t="$1"
  t="${t#\"}"; t="${t%\"}"; t="${t#\'}"; t="${t%\'}"
  case "$t" in \~) t="$HOME" ;; \~/*) t="$HOME/${t#\~/}" ;; esac
  while [ "${t%/}" != "$t" ] && [ "${t%/}" != "" ] && [ "${t%/}" != "${t%%:*}:" ]; do t="${t%/}"; done
  TYPED="$t"
}

engine_home_problem() { # path -> PROBLEM (empty: fine); the core's base.engine_home_choice_problem, same order
  local p="$1" n c d up
  PROBLEM=""
  case "$p" in
    /*|[A-Za-z]:/*|[A-Za-z]:\\*) ;;
    *) PROBLEM="$p is not a full path (for example $HOME/WhyNotCut)"; return 0 ;;
  esac
  norm_path "$p"; n="$NORM"
  case "$n" in
    /|[A-Za-z]:|[A-Za-z]:/) PROBLEM="$p is a drive root; choose a folder on it"; return 0 ;;
  esac
  norm_path "$ROOT"
  if within "$n" "$NORM"; then
    PROBLEM="$p is inside the plugin folder $ROOT, which is replaced on every update"; return 0
  fi
  norm_path "$HOME"
  if within "$NORM" "$n"; then PROBLEM="$p is your user folder or holds it; choose a folder of its own"; return 0; fi
  norm_path "$HOME/.claude"
  if within "$n" "$NORM"; then PROBLEM="$p is inside Claude's folder $HOME/.claude"; return 0; fi
  while IFS= read -r c; do
    [ -n "$c" ] || continue
    norm_path "$c"
    if within "$n" "$NORM"; then
      PROBLEM="$p is your clients folder $c (or inside it); keep the engine apart from client footage"; return 0
    fi
  done <<EOF
$CLIENT_ROOTS
EOF
  d="$p"
  while [ -n "$d" ]; do
    if [ -e "$d/.whynot-client" ]; then PROBLEM="$p is inside a client folder ($d holds .whynot-client)"; return 0; fi
    up="${d%/*}"
    [ "$up" = "$d" ] && break
    d="$up"
  done
  if [ -n "$HOME_OVR" ]; then
    norm_path "$H"
    if [ "$n" = "$NORM" ] || ! within "$n" "$NORM"; then
      PROBLEM="$p is outside the sandbox home $H (--home: nothing outside it is used)"
    fi
  fi
  return 0
}

free_gb() { # path -> FREE: whole GB free on its drive (empty when unknown)
  local d="$1" up kb
  FREE=""
  if [ -n "$TEST_FREE" ]; then FREE="${TEST_FREE%%.*}"; return 0; fi
  while [ -n "$d" ] && [ ! -d "$d" ]; do
    up="${d%/*}"
    [ "$up" = "$d" ] && break
    d="$up"
  done
  [ -n "$d" ] || d="/"
  kb="$(df -Pk "$d" 2>/dev/null </dev/null | awk 'NR == 2 { print $4 }')"
  case "$kb" in ''|*[!0-9]*) return 0 ;; esac
  FREE=$((kb / 1048576))
}

can_ask() { # the location question: never with --yes or --uninstall; the test hook; else a terminal (or /dev/tty)
  [ -z "$YES" ] && [ -z "$UNINSTALL" ] || return 1
  [ -n "$ANSWERS" ] && return 0
  [ -t 0 ] && return 0
  { : </dev/tty; } 2>/dev/null
}

ask_line() { # default -> ANSWER (trimmed; empty = the default); status 1 when there is no more input
  printf 'Folder / المجلد [%s]: ' "$1"
  ANSWER=""
  if [ -n "$ANSWERS" ]; then
    if ! IFS= read -r ANSWER <&3 && [ -z "$ANSWER" ]; then printf '\n'; return 1; fi
    printf '%s\n' "$ANSWER"
  elif [ -t 0 ]; then
    IFS= read -r ANSWER || [ -n "$ANSWER" ] || return 1
  else
    IFS= read -r ANSWER </dev/tty || [ -n "$ANSWER" ] || return 1  # curl | bash: stdin is the script
  fi
  ANSWER="${ANSWER%$'\r'}"
  ANSWER="${ANSWER#"${ANSWER%%[![:space:]]*}"}"
  ANSWER="${ANSWER%"${ANSWER##*[![:space:]]}"}"
  return 0
}

select_engine_home() { # default with-model -> ENGINE, CHOSEN (exit 2 when no usable folder is given)
  local default="$1" with_model="$2" text ask="" tries=0 need p
  CHOSEN=""
  client_roots
  can_ask && ask=1
  text="$default"
  if [ -n "$ENGINE_OPT" ]; then
    text="$ENGINE_OPT"; CHOSEN=1
  elif [ -n "$ask" ]; then
    printf '%s %s GB, %s GB with the model. Enter keeps the folder in brackets.\n' \
      "Where should WhyNot Cut keep its engine (Python, ffmpeg, the Whisper model)? It needs about" \
      "$NEED_GB" "$((NEED_GB + MODEL_GB))"
    printf '%s\n' "أين يحفظ WhyNot Cut ملفات التشغيل (بايثون و ffmpeg ونموذج Whisper)؟ تحتاج حوالي 6 جيجابايت، و9 مع النموذج. اضغط Enter لاختيار المجلد بين القوسين."
    if [ -f "$default/state.json" ] || [ -f "$default/current" ]; then
      printf 'WhyNot Cut is already installed in %s; Enter keeps it there.\n' "$default"
      printf '%s\n' "WhyNot Cut مثبّت بالفعل في هذا المجلد؛ اضغط Enter لإبقائه."
    fi
    if ask_line "$default" && [ -n "$ANSWER" ]; then text="$ANSWER"; CHOSEN=1; fi
  fi
  while [ "$tries" -lt 8 ]; do
    tries=$((tries + 1))
    typed_path "$text"; p="$TYPED"
    engine_home_problem "$p"
    if [ -z "$PROBLEM" ] && [ ! -f "$p/state.json" ] && [ ! -f "$p/current" ]; then
      need="$NEED_GB"
      [ -n "$with_model" ] && need=$((NEED_GB + MODEL_GB))
      free_gb "$p"
      if [ -n "$FREE" ] && [ "$FREE" -lt "$need" ]; then
        PROBLEM="only $FREE GB free on its drive; WhyNot Cut needs $need GB there ($NEED_GB GB, plus $MODEL_GB GB"
        PROBLEM="$PROBLEM for the Whisper model unless you add --skip model)"
      fi
    fi
    if [ -z "$PROBLEM" ] && [ -z "$DRY" ]; then
      if ! { mkdir -p "$p" && : > "$p/.wnc-write-test.$$" && rm -f "$p/.wnc-write-test.$$"; } 2>/dev/null; then
        PROBLEM="it cannot be created or written"
      fi
    fi
    if [ -z "$PROBLEM" ]; then ENGINE="$p"; return 0; fi
    printf 'WhyNot Cut cannot use %s as its engine home: %s\n' "$p" "$PROBLEM"
    printf '%s\n' "لا يمكن استخدام هذا المجلد؛ اختر مجلدًا آخر."
    if [ -z "$ask" ]; then
      printf 'Nothing was downloaded. Run the installer again with --engine-home <folder>.\n'
      exit 2
    fi
    ask_line "$default" || exit 2
    if [ -n "$ANSWER" ]; then text="$ANSWER"; CHOSEN=1; else text="$default"; CHOSEN=""; fi
  done
  exit 2
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
TEST_UV="" ANSWERS="" TEST_FREE=""
if [ -n "$HOME_OVR" ]; then
  TEST_UV="${WNC_TEST_UV:-}" ANSWERS="${WNC_TEST_ANSWERS:-}" TEST_FREE="${WNC_TEST_FREE_GB:-}"
fi
JSON_PY=""
if [ "$OS_NAME" != "Darwin" ] || [ "${TEST_UV%.py}" != "$TEST_UV" ]; then JSON_PY="$(pick_py)"; fi
ENGINE="" ENGINE_SRC="" CHOSEN=""
if [ -n "$HOME_OVR" ]; then
  H="$(abs_path "$HOME_OVR")"
  export HOME="$H" USERPROFILE="$H" APPDATA="$H/AppData/Roaming" LOCALAPPDATA="$H/AppData/Local"
  export CLAUDE_CONFIG_DIR="$H/.claude"
  resolve_engine_home sandbox  # the sandbox's own pointer / settings.json only
  POINTER="$H/.whynot-cut/plugin-options.json"
else
  resolve_engine_home  # before any download: uv, Python, the log and the core all use this one folder
  POINTER="$HOME/.whynot-cut/plugin-options.json"
  if [ -n "${WHYNOT_OPTIONS_FILE:-}" ]; then POINTER="$(home_path "$WHYNOT_OPTIONS_FILE")"; fi
fi
DEFAULT_ENGINE="$ENGINE"
if [ -n "$UNINSTALL" ]; then  # no question: the folder the engine uses (or --engine-home; the core checks it)
  if [ -n "$ENGINE_OPT" ]; then typed_path "$ENGINE_OPT"; ENGINE="$TYPED"; CHOSEN=1; fi
else
  [ -n "$ANSWERS" ] && exec 3<"$ANSWERS"
  case ",$SKIP," in *,model,*) WITH_MODEL="" ;; *) WITH_MODEL=1 ;; esac
  select_engine_home "$DEFAULT_ENGINE" "$WITH_MODEL"
fi
[ -n "$HOME_OVR" ] && export WHYNOT_HOME="$ENGINE"

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
if [ -n "$CHOSEN" ]; then
  MODE=" (chosen)"
elif [ "$ENGINE_SRC" = "default" ]; then
  MODE=" (default)"
else
  MODE=" (from $ENGINE_SRC)"
fi
[ -n "$HOME_OVR" ] && MODE="$MODE (sandbox)"
[ -n "$DRY" ] && MODE="$MODE (dry run: nothing is written)"
say "WhyNot Cut bootstrap: $CMD on $PLAT; engine home $ENGINE$MODE"

export UV_PYTHON_INSTALL_DIR="$ENGINE/python" UV_CACHE_DIR="$ENGINE/cache/uv" UV_NO_CONFIG=1
export UV_PYTHON_PREFERENCE=only-managed UV_NO_MODIFY_PATH=1
UV_NAME="uv"
case "$PLAT" in win-*) UV_NAME="uv.exe" ;; esac
UV_BIN="$ENGINE/bin/$UV_NAME"
PY=""
if [ -n "$UNINSTALL" ]; then engine_python || PY=""; fi

# ------------------------------------------------------------------------------------------- == uv ==
step uv
HAVE_UV=""
if [ -n "$PY" ]; then
  say "uninstall: the engine's own Python is there; uv and Python are not downloaded"
elif uv_version_ok "$UV_BIN" "$UV_VER"; then
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
if [ -z "$PY" ] && { [ -n "$HAVE_UV" ] || [ -n "$TEST_UV" ]; }; then find_python; fi
if [ -z "$PY" ]; then
  if [ -n "$DRY" ]; then
    say "dry run: would install Python $PY_VER with uv into $UV_PYTHON_INSTALL_DIR (--no-bin --no-registry)"
    names="$STEP_NAMES"
    [ -n "$UNINSTALL" ] && names="$UNINSTALL_STEP_NAMES"
    say "dry run: then the installer core would run these steps: $(printf '%s' "$names" | sed 's/ /, /g')"
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
if [ -n "$HOME_OVR" ]; then
  set -- "$@" --home "$H"
  norm_path "$ENGINE"; n_engine="$NORM"
  norm_path "$H/.whynot-cut"
  if [ -n "$CHOSEN" ] || [ "$n_engine" != "$NORM" ]; then set -- "$@" --engine-home "$ENGINE"; fi
else
  set -- "$@" --engine-home "$ENGINE"
fi
[ -n "$CHOSEN" ] && set -- "$@" --engine-home-chosen
[ -n "$MODEL_OPT" ] && set -- "$@" --model "$MODEL_OPT"
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
RC=$?
if [ -n "$UNINSTALL" ] && [ -n "$REMOVE_ENGINE" ] && [ -z "$DRY" ]; then
  LOG=""  # it went with logs/
  delete_deferred
fi
exit $RC
