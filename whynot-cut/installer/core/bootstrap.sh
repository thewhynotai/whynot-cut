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
# it is then empty; then the list file. The DEFAULT ~/.whynot-cut may be a symlink to a folder (Addendum F): python/
# and bin/ are deleted through it, never the link or its target. The log went with logs/, so the summary is on the console only. The newest
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
# `curl | bash`). It is placed and checked (engine_place, the core's base.choose_engine_home: a full path, not a drive
# root / mounted volume (/Volumes/<name>, a df mount point) / link, not inside the plugin folder; unless WhyNot Cut is
# already there also not holding the plugin, not the clients folder or holding / inside it, not inside or holding a
# folder marked .whynot-client; the user folder, Desktop, Documents, Downloads and any folder holding the editor's own
# files get a WhyNotCut subfolder (said in English and Arabic), so uninstall never empties a folder of the editor's
# files; in a sandbox inside the sandbox; 6 GB free on its drive, 9 GB with the Whisper model, unless WhyNot Cut is
# already there; it can be created and written); a refused folder is asked again (with --yes: exit 2, nothing
# downloaded). Choosing a folder other than an existing install's says (English + Arabic) that the old one is left
# behind, and where. uv, Python, the
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
# No questions by default (Addendum D, D-T1, task 9): an install prints "Installing everything WhyNot Cut needs (about N
# GB)" (English + Arabic; N from components.json `bytes` where present, the core's system.install_size_gb rule) and,
# with a person at the terminal, a 10-second line "Press C to customise (10)... / <Arabic>" that counts down in place
# (`read -t 1 -n 1` from the terminal: stdin when it is one, else /dev/tty when it can be opened and stdout or stderr is
# a terminal too - never the piped script - and only in the terminal's foreground process group; keys typed before the
# line appeared are drained first). C opens the Customise path; any other key or the end of the countdown installs with
# the strongest defaults, exactly like --yes (the core gets --yes: the same state.json, answers.mode "default").
# --customise (or C) asks the location question here and passes --customise, so the core asks the model, the language
# and the clients folder, every answer preselected. --yes: no countdown, no question. No terminal (curl | bash without
# /dev/tty, CI, Door 2): like --yes, never waiting. --yes with --customise: exit 2.
# A RESOLVED engine home other than ~/.whynot-cut (a variable, the pointer or settings.json named it) that is itself a
# link, a drive root or mount point, the home folder itself, Desktop / Documents / Downloads themselves, holds client
# data (the saved clients folder, or .whynot-client up to 3 levels below) or is too big to check for that (more than
# 5000 entries within 3 levels), or a network share / device path (//server/share) - compared as written and with links
# resolved (cd -P), case folded on macOS - is refused with exit 2 before the countdown and any download (fix round 1),
# also when --engine-home names that same folder (fix round 2), with the self-fix "run the installer again with
# -EngineHome <folder> / --engine-home <folder>" (English + Arabic); the core applies the same rule
# (base.resolved_home_problem). Sandbox-only test hooks for this: WNC_TEST_KEYS ("C", another key, or "none" = nobody
# presses), WNC_TEST_COUNTDOWN_S (the seconds the countdown waits with the hook; 0 = none); the core reads the
# WNC_TEST_ANSWERS lines after the ones used here (WNC_TEST_ANSWERS_AT). ~/.whynot-cut itself may be a link (Addendum
# F); then the same rules apply to where it points, at install, at uninstall and before the deferred delete (fix round
# 3).
# Fix round 5: a folder holding only models/ with WhyNot Cut's own model store (the "models--<repo>" folders of
# components.json models.*.repo: what `--uninstall --remove-engine` keeps) is WhyNot Cut's, at install and uninstall
# (our_home; never by the name `models` alone). --uninstall --engine-home naming the resolved home (the linked
# ~/.whynot-cut too) is that home, not a chosen folder; naming any other folder, it must exist, not be a link, pass the
# placement refusals and be WhyNot Cut's own - or hold WhyNot Cut's own WhyNotCut folder where an install would have
# made one (the user folder, Desktop, Documents, Downloads, a folder holding the editor's files) - checked before
# anything is written (uninstall_place, the core's base.uninstall_engine_home); else exit 2, "Nothing was changed".
# Every engine home path is normalised lexically (lex_path: ., .., repeated and trailing /) before any test. The deferred
# delete re-resolves a linked ~/.whynot-cut and deletes nothing when it points elsewhere than at the start (LINK_REAL).
# Fix round 6: what an uninstall keeps is recognised by content, never by name (is_kept_leftover): models/ counts only
# when EVERY entry is a store of ours (components.json models.*.repo, every model the installer offers) or Hugging
# Face's own bookkeeping (.locks, CACHEDIR.TAG, a marked blobs/ store, OS folder-view files), never with a link inside;
# library/ counts by its pack manifests (motion/<pack>/pack.json), or empty beside our models/. `..` never climbs above
# /, a drive (C:/) or //server/share (lex_path, norm_path). --release-stage (install.sh --source): the release staged
# under the OS temp dir; an install keeps it in <engine>/downloads/release-<sha8> only after every check above has
# passed (keep_release), an uninstall never writes it.
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
# Prints the value; null, a missing key or an unreadable file print nothing. Every JXA reader below reads the file as
# NSData and decodes it itself (never an NSString file reader: those strip a UTF-8 BOM before JS can see it,
# which is how the macOS CI found a BOM file accepted where the Python twin rejects it); this one and the state and
# size readers follow their twins' utf-8-sig and drop a leading BOM, saved_engine_home's reader refuses one.
JXA_JSON_GET='function run(argv) {
  ObjC.import("Foundation");
  var data = $.NSData.dataWithContentsOfFile(argv[0]);
  if (data.isNil()) { return ""; }
  var text = $.NSString.alloc.initWithDataEncoding(data, $.NSUTF8StringEncoding);
  if (text.isNil()) { return ""; }
  var v;
  try { v = JSON.parse(ObjC.unwrap(text).replace(/^\uFEFF/, "")); } catch (e) { return ""; }
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

lex_path() { # path -> LEX: its lexical normal form, the core's abspath (fix round 5, N4): \ as / and /c/x as C:/x (Git
  # Bash), repeated /, . and .. resolved, no trailing / - case kept. `..` never climbs above the root - /, a drive (C:/)
  # or //server/share (fix round 6, R5-6: C:/../x is C:/x, as in Python). A \\server path, or a // one without a share,
  # stays as it is (the guards refuse it by its spelling)
  local p="$1" out="" part root="" rest srv shr
  case "$p" in \\\\*) LEX="$p"; return 0 ;; esac
  case "$OS_NAME" in
    MINGW*|MSYS*|CYGWIN*)
      p="${p//\\//}"
      case "$p" in /[a-zA-Z]|/[a-zA-Z]/*) p="${p:1:1}:${p:2}" ;; esac ;;
  esac
  rest="$p"
  case "$p" in
    //*)
      rest="${p#//}"; srv="${rest%%/*}"; rest="${rest#"$srv"}"; rest="${rest#/}"; shr="${rest%%/*}"
      rest="${rest#"$shr"}"
      if [ -z "$srv" ] || [ -z "$shr" ]; then LEX="$p"; return 0; fi
      root="//$srv/$shr" ;;
    /*) root="/"; rest="${p#/}" ;;
    [A-Za-z]:*) root="${p:0:2}/"; rest="${p:2}" ;;
  esac
  local IFS=/
  set -f
  for part in $rest; do
    case "$part" in
      ''|.) ;;
      ..) out="${out%/*}" ;;
      *) out="$out/$part" ;;
    esac
  done
  set +f
  case "$root" in
    "") LEX="${out#/}"; [ -n "$LEX" ] || LEX="$1" ;;
    /) LEX="${out:-/}" ;;
    //*) LEX="$root$out" ;;
    *) LEX="${root%/}${out:-/}" ;;
  esac
}

norm_path() { # lexical: \ (Git Bash), repeated /, . and .. resolved, no trailing / -> NORM; lower case on Windows. `..`
  # never climbs above / or a drive (fix round 6, R5-6); a drive root is X: (as before); a leading // run is one /
  local p="$1" out="" part root="" rest
  case "$OS_NAME" in
    MINGW*|MSYS*|CYGWIN*)
      p="${p//\\//}"
      case "$p" in /[a-zA-Z]|/[a-zA-Z]/*) p="${p:1:1}:${p:2}" ;; esac ;;  # Git Bash /c/x is C:/x
  esac
  rest="$p"
  case "$p" in
    /*) root="/"; rest="${p#/}" ;;
    [A-Za-z]:*) root="${p:0:2}"; rest="${p:2}" ;;
  esac
  local IFS=/
  set -f
  for part in $rest; do
    case "$part" in
      ''|.) ;;
      ..) out="${out%/*}" ;;
      *) out="$out/$part" ;;
    esac
  done
  set +f
  case "$root" in
    "") NORM="${out#/}" ;;
    /) NORM="${out:-/}" ;;
    *) NORM="$root$out" ;;
  esac
  case "$OS_NAME" in MINGW*|MSYS*|CYGWIN*) NORM="$(printf '%s' "$NORM" | tr '[:upper:]' '[:lower:]')" ;; esac
}

exact_child() { # dir name -> EXACT: "exact" (an entry named exactly so), "other" (only in another case), "none"
  local e n low want
  EXACT="none"
  want="$(printf '%s' "$2" | tr '[:upper:]' '[:lower:]')"
  for e in "$1"/* "$1"/.[!.]* "$1"/..?*; do
    [ -e "$e" ] || [ -L "$e" ] || continue
    n="${e##*/}"
    if [ "$n" = "$2" ]; then EXACT="exact"; return 0; fi
    low="$(printf '%s' "$n" | tr '[:upper:]' '[:lower:]')"
    [ "$low" = "$want" ] && EXACT="other"
  done
  return 0
}

delete_deferred() { # after `uninstall --remove-engine`: $ENGINE/.delete-after-exit may name ONLY python/, bin/, $ENGINE
  list="$ENGINE/.delete-after-exit"
  [ -f "$list" ] || return 0
  root="$ENGINE"
  while [ "${root%/}" != "$root" ] && [ "$root" != "/" ]; do root="${root%/}"; done
  linked=""  # Addendum F: the DEFAULT ~/.whynot-cut may be a link to a folder: emptied through it, never removed
  if [ -L "$root" ] && [ -d "$root" ]; then
    guard_norm "$root"; nroot="$NORM"  # (fix round 5, N5: case folded on macOS too)
    guard_norm "$HOME/.whynot-cut"
    [ "$nroot" = "$NORM" ] && linked=1
  fi
  if [ -L "$root" ] && [ -z "$linked" ]; then
    printf 'WARNING: %s is a link; the paths in %s were left alone\n' "$root" "$list"
    return 0
  fi
  if [ -n "$linked" ]; then  # fix round 5 (N6): still pointing where it pointed when the run checked it (LINK_REAL)?
    real_path "$root"; now_real="$REAL"
    guard_norm "${now_real:-?}"; n_now="$NORM"
    n_then=""
    # the start AS RECORDED (real_path when it was recorded: one canonical form, /private/var on macOS too); never
    # resolved again - a recorded target replaced by a link must read as "moved" (round 9, R8-4)
    if [ -n "${LINK_REAL:-}" ]; then guard_norm "$LINK_REAL"; n_then="$NORM"; fi
    if [ -z "$now_real" ] || [ -z "$n_then" ] || [ "$n_now" != "$n_then" ]; then
      printf 'WARNING: %s now points to %s, not to %s as when this uninstall started; the paths in %s were left alone (nothing was deleted). Check the link, then run the uninstall again.\n' \
        "$root" "${now_real:-a folder that cannot be read}" "${LINK_REAL:-(unknown)}" "$list"
      printf '%s\n' "تغيّر المجلد الذي يشير إليه الرابط ~/.whynot-cut أثناء الإلغاء، لذلك لم يُحذف شيء آخر. تحقّق من الرابط ثم شغّل الإلغاء مرة أخرى."
      return 0
    fi
  fi
  if [ -n "$linked" ]; then  # fix round 3: where the link points is checked again (Documents, client data ...)
    client_roots
    resolved_home_problem "$root" deferred
    if [ -n "$WHY" ]; then
      printf 'WARNING: %s is %s; the paths in %s were left alone\n' "$root" "$WHY" "$list"
      return 0
    fi
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
    exact_child "$root" "${target##*/}"  # (fix round 2) never the editor's `Bin` on a case-insensitive disk
    case "$EXACT" in
      exact) ;;
      other) printf "WARNING: refused '%s' in %s (the folder there is not named exactly %s: not WhyNot Cut's)\n" \
               "$p" "$list" "${target##*/}"; continue ;;
      *) continue ;;
    esac
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
  if [ -n "$home_too" ] && [ -z "$failed" ] && [ -z "$linked" ] && [ -d "$root" ]; then
    # (task F1) an entry that looks like a transient copy of one of WhyNot Cut's own top-level names (<name>.tmp, case
    # ignored: STATE.JSON.tmp from an antivirus or indexer) is waited for, at most 2 s; it is never deleted (the
    # core's base.transient_copy; the same names, tests/test_installer.py)
    transient_names=".delete-after-exit ae-capabilities.json ae-probe ae-queue ae-scripts bench bin bridge cache cuda current downloads ffmpeg fonts library logs marketplace marketplace.new marketplace.prev models plugin-options.json ppro-queue ppro-scripts python runtimes serve state state.json tmp venv"
    i=0
    while [ $i -lt 10 ]; do  # x 0.2 s = 2 s, as the core
      copies=""
      for e in "$root"/* "$root"/.[!.]* "$root"/..?*; do
        [ -e "$e" ] || [ -L "$e" ] || continue
        low="$(printf '%s' "${e##*/}" | tr 'A-Z' 'a-z')"
        case "$low" in
          *.tmp)
            for t in $transient_names; do  # (round 8, N-3) the exact name, never a part of a longer one
              [ "${low%.tmp}" = "$t" ] && copies=1
            done ;;
        esac
      done
      [ -n "$copies" ] || break
      sleep 0.2
      i=$((i + 1))
    done
  fi
  if [ -n "$home_too" ] && [ -z "$failed" ] && [ -z "$linked" ] && rmdir "$root" 2>/dev/null; then
    # a program still holding the folder (an antivirus or indexer) can keep its name listed for a moment after the
    # delete succeeded: wait for it, at most 2 s (as the core's base.wait_gone and PowerShell; round 8, F1-b)
    i=0
    while { [ -e "$root" ] || [ -L "$root" ]; } && [ $i -lt 10 ]; do sleep 0.2; i=$((i + 1)); done
    if [ -e "$root" ] || [ -L "$root" ]; then
      printf 'WARNING: %s is still listed; it goes once the program holding it lets go\n' "$root"
    else
      printf 'deleted %s\n' "$root"
    fi
  fi
  return 0
}

# ------------------------------------------------------------------------------------------- arguments
PLUGIN_ROOT="" HOME_OVR="" DRY="" YES="" CLIENTS="" LANG_OPT="" CHANNEL="" COMPONENTS="" SKIP=""
UNINSTALL="" REMOVE_ENGINE="" REMOVE_MODELS="" ENGINE_OPT="" MODEL_OPT="" CUSTOMISE="" RELEASE_STAGE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --plugin-root) PLUGIN_ROOT="$2"; shift ;;
    --home) HOME_OVR="$2"; shift ;;
    --engine-home) ENGINE_OPT="$2"; shift ;;
    --model) MODEL_OPT="$2"; shift ;;
    --dry-run) DRY=1 ;;
    --yes|-y) YES=1 ;;
    --customise|--customize) CUSTOMISE=1 ;;
    --clients-folder) CLIENTS="$2"; shift ;;
    --language) LANG_OPT="$2"; shift ;;
    --channel) CHANNEL="$2"; shift ;;
    --components) COMPONENTS="$2"; shift ;;
    --skip) if [ -n "$SKIP" ]; then SKIP="$SKIP,$2"; else SKIP="$2"; fi; shift ;;
    --uninstall) UNINSTALL=1 ;;
    --remove-engine) REMOVE_ENGINE=1 ;;
    --remove-models) REMOVE_MODELS=1 ;;
    --release-stage) RELEASE_STAGE="$2"; shift ;;
    *) stop2 "bootstrap: unknown option $1" ;;
  esac
  shift
done
[ -n "$PLUGIN_ROOT" ] || stop2 "bootstrap: --plugin-root is required"
case "$MODEL_OPT" in
  ""|large-v3|large-v3-turbo|medium|small) ;;  # wnc_installer/system.py MODELS
  *) stop2 "--model $MODEL_OPT is not one of large-v3, large-v3-turbo, medium, small" ;;
esac
if [ -n "$CUSTOMISE" ] && [ -n "$YES" ] && [ -z "$UNINSTALL" ]; then
  stop2 "--yes and --customise cannot be used together (--yes asks nothing; --customise asks the questions)"
fi

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
  # files are UTF-8 without a BOM (a BOM is not JSON, as for the engine). macOS: JXA, which reads the BYTES: the first
  # three (EF BB BF = "77u/" in base64) are checked before decoding, and bytes that are not UTF-8 make the file
  # invalid too; elsewhere (Git Bash in tests) the same rules in Python.
  local js py
  js='function run(argv) {
    ObjC.import("Foundation");
    function isObj(v) { return v !== null && typeof v === "object" && !Array.isArray(v); }
    function own(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }
    function load(p) {
      var d = $.NSData.dataWithContentsOfFile(p);
      if (d.isNil()) { return null; }
      if (ObjC.unwrap(d.base64EncodedStringWithOptions(0)).indexOf("77u/") === 0) { return null; }
      var t = $.NSString.alloc.initWithDataEncoding(d, $.NSUTF8StringEncoding);
      if (t.isNil()) { return null; }
      try { var v = JSON.parse(ObjC.unwrap(t)); return isObj(v) ? v : null; } catch (e) { return null; }
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
  case "$t" in /*|[A-Za-z]:/*|[A-Za-z]:\\*) lex_path "$t"; t="$LEX" ;; esac  # (fix round 5, N4) x/nope/.. is x
  TYPED="$t"
}

# A GENUINE engine home (fix round 2; file names alone can be anyone's), the core's base.is_engine_home: state.json is a
# JSON object with schema 1 and a "plugin" key, or `current` names a valid runtime id whose runtimes/<id>/WHYNOT_RUNTIME
# is a JSON object with that same id. The file arrives as a run() argument, never inside the script text.
JXA_STATE_OK='function run(argv) {
  ObjC.import("Foundation");
  var d = $.NSData.dataWithContentsOfFile(argv[0]);
  if (d.isNil()) { return "no"; }
  var t = $.NSString.alloc.initWithDataEncoding(d, $.NSUTF8StringEncoding);
  if (t.isNil()) { return "no"; }
  var v;
  try { v = JSON.parse(ObjC.unwrap(t).replace(/^\uFEFF/, "")); } catch (e) { return "no"; }
  var ok = v !== null && typeof v === "object" && !Array.isArray(v) && Number.isInteger(v.schema) && v.schema === 1 &&
           Object.prototype.hasOwnProperty.call(v, "plugin");
  return ok ? "yes" : "no";
}'

state_is_ours() { # state.json: status 0 when WhyNot Cut wrote it (a JSON object, schema 1, a plugin key)
  [ -f "$1" ] || return 1
  if [ "$OS_NAME" = "Darwin" ]; then
    [ "$(osascript -l JavaScript -e "$JXA_STATE_OK" "$1" 2>/dev/null </dev/null)" = "yes" ]
    return $?
  fi
  [ -n "$JSON_PY" ] || return 1
  "$JSON_PY" -I -c '
import json, sys
try:
    v = json.loads(open(sys.argv[1], "rb").read(1 << 20).decode("utf-8-sig"))
except (OSError, ValueError):
    sys.exit(1)
ok = isinstance(v, dict) and type(v.get("schema")) is int and v.get("schema") == 1 and "plugin" in v
sys.exit(0 if ok else 1)' "$1" >/dev/null 2>&1 </dev/null
}

is_engine_home() { # dir: status 0 when it is a GENUINE WhyNot Cut engine home (see above)
  local rid
  state_is_ours "$1/state.json" && return 0
  [ -f "$1/current" ] || return 1
  IFS= read -r rid < "$1/current" || [ -n "$rid" ] || return 1
  rid="${rid%$'\r'}"
  rid="${rid#$'\xef\xbb\xbf'}"
  case "$rid" in ''|*[!A-Za-z0-9._-]*|[!A-Za-z0-9]*|*..*) return 1 ;; esac
  [ "${#rid}" -le 80 ] || return 1
  [ -f "$1/runtimes/$rid/WHYNOT_RUNTIME" ] || return 1
  [ "$(json_get "$1/runtimes/$rid/WHYNOT_RUNTIME" id)" = "$rid" ]
}

occupied_list() { # dir [pointer-ok] [ignore-view] -> OCCUPIED (one per line): every entry except the write probe, the
  # -Source cache (a downloads folder holding only release-* folders), with pointer-ok (~/.whynot-cut) the pointer, and
  # - only with ignore-view, when recognising a leftover that is already ours (fix round 8, R7-2) - the OS folder-view
  # files .DS_Store, Thumbs.db, desktop.ini when they are real files (view_file); for placement a folder holding only
  # those is NOT empty. Names compare exactly (the core's base.occupied_entries)
  local e n k only
  OCCUPIED=""
  [ -d "$1" ] || return 0
  for e in "$1"/* "$1"/.[!.]* "$1"/..?*; do
    [ -e "$e" ] || [ -L "$e" ] || continue
    n="${e##*/}"
    case "$n" in .wnc-write-test*) continue ;; esac
    if [ -n "${2:-}" ] && [ "$n" = "plugin-options.json" ]; then continue; fi
    if [ -n "${3:-}" ] && view_file "$e"; then continue; fi
    if [ "$n" = "downloads" ] && [ -d "$e" ] && [ ! -L "$e" ]; then
      only=1
      for k in "$e"/* "$e"/.[!.]* "$e"/..?*; do
        [ -e "$k" ] || [ -L "$k" ] || continue
        case "${k##*/}" in release-*) ;; *) only="" ;; esac
      done
      [ -n "$only" ] && continue
    fi
    if [ -n "$OCCUPIED" ]; then OCCUPIED="$OCCUPIED"$'\n'"$n"; else OCCUPIED="$n"; fi
  done
  return 0
}

has_occupied() { # dir [pointer-ok] [ignore-view]: status 0 when it holds anything that makes it the editor's
  # (occupied_list)
  occupied_list "$1" "${2:-}" "${3:-}"
  [ -n "$OCCUPIED" ]
}

# Fix round 5 (N1): the model store folders WhyNot Cut's model step writes into <engine home>/models ("models--" + every
# components.json models.<m>.repo with / as --; the core's base.model_store_names). The file arrives as a run() argument.
JXA_MODEL_STORES='function run(argv) {
  ObjC.import("Foundation");
  var d = $.NSData.dataWithContentsOfFile(argv[0]);
  if (d.isNil()) { return ""; }
  var t = $.NSString.alloc.initWithDataEncoding(d, $.NSUTF8StringEncoding);
  if (t.isNil()) { return ""; }
  var c;
  try { c = JSON.parse(ObjC.unwrap(t).replace(/^\uFEFF/, "")); } catch (e) { return ""; }
  var m = (c !== null && typeof c === "object" && !Array.isArray(c)) ? c.models : null;
  if (m === null || typeof m !== "object" || Array.isArray(m)) { return ""; }
  var re = /^[A-Za-z0-9][A-Za-z0-9._-]*\/[A-Za-z0-9][A-Za-z0-9._-]*$/, out = [];
  Object.keys(m).forEach(function (k) {
    var v = m[k], r = (v !== null && typeof v === "object" && !Array.isArray(v)) ? v.repo : null;
    if (typeof r === "string" && re.test(r) && r.indexOf("..") < 0) { out.push("models--" + r.split("/").join("--")); }
  });
  return out.join("\n");
}'
PY_MODEL_STORES='import json, re, sys
try:
    c = json.loads(open(sys.argv[1], "rb").read().decode("utf-8-sig"))
except (OSError, ValueError):
    c = None
m = c.get("models") if isinstance(c, dict) else None
rx = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
for v in (m.values() if isinstance(m, dict) else ()):
    r = v.get("repo") if isinstance(v, dict) else None
    if isinstance(r, str) and rx.match(r) and ".." not in r:
        print("models--" + r.replace("/", "--"))'

model_stores() { # -> MODEL_STORES (one per line), read once from the components.json in use ($COMP); none when unreadable
  [ -n "${MODEL_STORES_READ:-}" ] && return 0
  MODEL_STORES_READ=1 MODEL_STORES=""
  { [ -n "${COMP:-}" ] && [ -f "$COMP" ]; } || return 0
  if [ "$OS_NAME" = "Darwin" ]; then
    MODEL_STORES="$(osascript -l JavaScript -e "$JXA_MODEL_STORES" "$COMP" 2>/dev/null </dev/null)"
  elif [ -n "${JSON_PY:-}" ]; then
    MODEL_STORES="$("$JSON_PY" -I -c "$PY_MODEL_STORES" "$COMP" 2>/dev/null </dev/null | tr -d '\r')"
  fi
  return 0
}

model_entry_kind() { # models-dir name -> KIND: what one entry of <engine home>/models is (fix round 6, R5-2; the core's
  # base.model_entry_kind): store (a real folder named exactly as a model store of WhyNot Cut's), bookkeeping (Hugging
  # Face's own .locks folder, CACHEDIR.TAG, a blobs/ store holding its .huggingface-shared-blobs marker, or an OS
  # folder-view file) or "" (the editor's, or a link: never ours, never entered)
  local p="$1/$2" nl=$'\n'
  KIND=""
  model_stores
  case "$nl$MODEL_STORES$nl" in
    *"$nl$2$nl"*)
      if [ -d "$p" ] && [ ! -L "$p" ]; then KIND=store; fi
      return 0 ;;
  esac
  case "$2" in
    .locks) if [ -d "$p" ] && [ ! -L "$p" ]; then KIND=bookkeeping; fi ;;
    CACHEDIR.TAG|.DS_Store|Thumbs.db|desktop.ini) if [ -f "$p" ] && [ ! -L "$p" ]; then KIND=bookkeeping; fi ;;
    blobs)
      if [ -d "$p" ] && [ ! -L "$p" ] && [ -f "$p/.huggingface-shared-blobs" ] && [ ! -L "$p/.huggingface-shared-blobs" ]
      then KIND=bookkeeping; fi ;;
  esac
  return 0
}

our_models() { # dir: status 0 when <engine home>/models is WhyNot Cut's (fix round 6, R5-2; the core's base.is_our_models):
  # a real folder whose EVERY entry is a store of ours or Hugging Face's bookkeeping, at least one a store. One entry of
  # the editor's (their own model beside ours) or any link inside makes the whole folder the editor's. Fix round 7 (M6-1):
  # an EMPTY real folder (or one holding only OS folder-view files) is ours too - nothing in it can be lost
  local e store="" other=""
  { [ -d "$1" ] && [ ! -L "$1" ]; } || return 1
  for e in "$1"/* "$1"/.[!.]* "$1"/..?*; do
    [ -e "$e" ] || [ -L "$e" ] || continue
    model_entry_kind "$1" "${e##*/}"
    [ -n "$KIND" ] || return 1
    if [ "$KIND" = store ]; then store=1; elif ! view_file "$e"; then other=1; fi
  done
  [ -n "$store" ] || [ -z "$other" ]
}

view_file() { # path: status 0 for an OS folder-view file (.DS_Store, Thumbs.db, desktop.ini) that is a real file
  case "${1##*/}" in
    .DS_Store|Thumbs.db|desktop.ini) [ -f "$1" ] && [ ! -L "$1" ] ;;
    *) return 1 ;;
  esac
}

library_state() { # dir -> LIB: <engine home>/library (fix round 6; the core's base.library_state) - packs (only motion/,
  # holding only pack folders that each carry their pack.json, the engine's pack manifest; at least one), empty (nothing,
  # or only an empty motion/) or "" (anything else, any link). OS folder-view files are ignored at both levels
  local e top="" packs=""
  LIB=""
  { [ -d "$1" ] && [ ! -L "$1" ]; } || return 0
  for e in "$1"/* "$1"/.[!.]* "$1"/..?*; do
    [ -e "$e" ] || [ -L "$e" ] || continue
    view_file "$e" && continue
    if [ "${e##*/}" != "motion" ] || [ ! -d "$e" ] || [ -L "$e" ]; then return 0; fi
    top=1
  done
  if [ -z "$top" ]; then LIB=empty; return 0; fi
  for e in "$1/motion"/* "$1/motion"/.[!.]* "$1/motion"/..?*; do
    [ -e "$e" ] || [ -L "$e" ] || continue
    view_file "$e" && continue
    if [ ! -d "$e" ] || [ -L "$e" ] || [ ! -f "$e/pack.json" ] || [ -L "$e/pack.json" ]; then return 0; fi
    packs=1
  done
  if [ -n "$packs" ]; then LIB=packs; else LIB=empty; fi
  return 0
}

is_kept_leftover() { # dir [pointer-ok]: status 0 for what an uninstall keeps of an engine home, still WhyNot Cut's own
  # folder (fix round 5, N1; round 6: the core's base.is_kept_leftover): its only entries (occupied_list) are models/
  # that is ours (our_models) and/or library/ - recognised by its pack manifests, or empty beside our models/ (never
  # alone). Never by the names alone; a link is never ours
  local n has_models="" models="" has_lib=""
  occupied_list "$1" "${2:-}" view  # (round 8, R7-2) view files are ignored HERE only
  [ -n "$OCCUPIED" ] || return 1
  while IFS= read -r n; do
    case "$n" in
      models) has_models=1 ;;
      library) has_lib=1 ;;
      *) return 1 ;;
    esac
  done <<EOF
$OCCUPIED
EOF
  if [ -n "$has_models" ]; then
    our_models "$1/models" || return 1
    models=1
  fi
  if [ -z "$has_lib" ]; then [ -n "$models" ]; return $?; fi
  library_state "$1/library"
  [ "$LIB" = packs ] || { [ "$LIB" = empty ] && [ -n "$models" ]; }
}

our_home() { # dir [pointer-ok]: WhyNot Cut's own folder - a genuine engine home or the leftover of one (fix rounds 5, 6)
  is_engine_home "$1" || is_kept_leftover "$1" "${2:-}"
}

is_mount() { # path: /Volumes/<name>, or an existing folder that df reports as its own mount point
  local n m low rest item r="" keep="${REAL:-}"
  norm_path "$1"; n="$NORM"
  if [ -n "${TEST_MOUNTS:-}" ]; then  # sandbox-only test hook WNC_TEST_MOUNTS: folders that count as mount points
    # each item and the path, as written AND resolved (cd -P): macOS' /var is a link to /private/var (Mac CI run 2)
    real_path "$1"
    if [ -n "$REAL" ]; then norm_path "$REAL"; r="$NORM"; fi
    rest="$TEST_MOUNTS;"
    while [ -n "$rest" ]; do
      item="${rest%%;*}"; rest="${rest#*;}"
      [ -n "$item" ] || continue
      norm_path "$item"
      if [ "$NORM" = "$n" ] || [ "$NORM" = "$r" ]; then REAL="$keep"; return 0; fi
      real_path "$item"
      if [ -n "$REAL" ]; then
        norm_path "$REAL"
        if [ "$NORM" = "$n" ] || [ "$NORM" = "$r" ]; then REAL="$keep"; return 0; fi
      fi
    done
    REAL="$keep"
  fi
  low="$(printf '%s' "$n" | tr '[:upper:]' '[:lower:]')"
  case "$low" in /volumes/*/*) ;; /volumes/?*) return 0 ;; esac
  [ -d "$1" ] || return 1
  m="$(df -P "$1" 2>/dev/null </dev/null | awk 'NR == 2 { for (i = 6; i <= NF; i++) printf "%s%s", $i, (i < NF ? " " : "") }')"
  [ -n "$m" ] || return 1
  norm_path "$m"
  [ "$NORM" = "$n" ]
}

engine_place() { # path -> PLACED, PLACE_NOTE, PROBLEM (empty: fine); the core's base.choose_engine_home, same order
  local p="$1" n r c d up f nf d1 d2 lp root_like="" existing="" pointer_ok=""
  PLACED="" PLACE_NOTE="" PROBLEM=""
  case "$p" in
    /*|[A-Za-z]:/*|[A-Za-z]:\\*) ;;
    *) PROBLEM="$p is not a full path (for example $HOME/WhyNotCut)"; return 0 ;;
  esac
  lex_path "$p"; p="$LEX"  # (fix round 5, N4) before any test: x/nope/../y is x/y
  norm_path "$p"; n="$NORM"
  case "$n" in
    /|[A-Za-z]:|[A-Za-z]:/) PROBLEM="$p is a drive root or a mounted volume; choose a folder on it"; return 0 ;;
  esac
  if is_mount "$p"; then PROBLEM="$p is a drive root or a mounted volume; choose a folder on it"; return 0; fi
  if [ -L "$p" ]; then PROBLEM="$p is a link or mount point; choose a real folder"; return 0; fi
  norm_path "$ROOT"; r="$NORM"
  if within "$n" "$r"; then
    PROBLEM="$p is inside the plugin folder $ROOT, which is replaced on every update"; return 0
  fi
  norm_path "$HOME/.whynot-cut"
  [ "$NORM" = "$n" ] && pointer_ok=1  # the SessionStart hook's pointer lives there
  our_home "$p" "$pointer_ok" && existing=1  # (fix round 5, N1: also the leftover of an uninstall)
  if [ -z "$existing" ]; then
    # it holds the plugin (fine only in its downloads/: the -Source cache; fix round 6, R5-5: a --source stage in the
    # OS temp dir is no plugin folder of its own - deleted when the run ends, kept in <final>/downloads after the checks)
    if [ -z "$STAGE" ] && [ "$r" != "$n" ] && within "$r" "$n"; then
      norm_path "$p/downloads"; d1="$NORM"
      norm_path "$p/WhyNotCut/downloads"; d2="$NORM"
      if ! within "$r" "$d1" && ! within "$r" "$d2"; then
        PROBLEM="$p holds the plugin folder $ROOT; choose a folder of its own"; return 0
      fi
    fi
    while IFS= read -r c; do
      [ -n "$c" ] || continue
      norm_path "$c"
      if within "$n" "$NORM" || within "$NORM" "$n"; then
        PROBLEM="$p is, holds or is inside your clients folder $c; keep the engine apart from client footage"
        return 0
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
    if [ -d "$p" ]; then
      lp="$(find "$p" -maxdepth 4 -name .whynot-client 2>/dev/null </dev/null | head -n 1)"
      if [ -n "$lp" ]; then PROBLEM="$p holds a client folder (${lp%/*} holds .whynot-client)"; return 0; fi
    fi
  fi
  for d in "$HOME" "$HOME/Desktop" "$HOME/Documents" "$HOME/Downloads"; do
    norm_path "$d"
    [ "$NORM" = "$n" ] && root_like=1
  done
  f="$p"
  if [ -z "$existing" ] && { [ -n "$root_like" ] || has_occupied "$p" "$pointer_ok"; }; then
    f="${p%/}/WhyNotCut"
    PLACE_NOTE="$p already holds other files, so WhyNot Cut goes into its own folder $f (uninstall then never touches the rest)"
  fi
  norm_path "$f"; nf="$NORM"
  norm_path "$HOME"
  if within "$NORM" "$nf"; then PROBLEM="$f is your user folder or holds it; choose a folder of its own"; return 0; fi
  norm_path "$HOME/.claude"
  if within "$nf" "$NORM"; then PROBLEM="$f is inside Claude's folder $HOME/.claude"; return 0; fi
  # (round 9, R8-3) our own WhyNotCut subfolder that kept only the editor's view files (an icon's desktop.ini, never
  # deleted by the uninstall) is used again; anything else in it is the editor's
  local own_sub=""
  [ "${f##*/}" = "WhyNotCut" ] && own_sub=1
  if [ "$f" != "$p" ] && ! our_home "$f" && has_occupied "$f" "" "$own_sub"; then
    PROBLEM="$f already holds other files; choose an empty folder or one of its own"; return 0
  fi
  if [ -n "$HOME_OVR" ]; then
    norm_path "$H"
    if [ "$nf" = "$NORM" ] || ! within "$nf" "$NORM"; then
      PROBLEM="$f is outside the sandbox home $H (--home: nothing outside it is used)"; return 0
    fi
  fi
  PLACED="$f"
  return 0
}

keep_release() { # stage engine -> ROOT: --source (fix round 6, R5-5) - install.sh fetched and verified the release zip in
  # a folder of this run under the OS temp dir and deletes it when the run ends. Only now (the engine home passed every
  # check) is it kept in <engine>/downloads/release-<sha8> (zip + x/), the plugin root of this run: the core and its
  # background model download read the plugin files after install.sh has deleted the stage. A complete cache of the same
  # zip is reused. On a failure (fix round 7, M6-3; most likely a full disk) nothing it made stays (the partial copy, and
  # downloads/ and the engine home when it made them) and the run stops with exit 3, before the log and the core - it
  # never goes on from the stage install.sh deletes
  local stage="$1" dl="$2/downloads" dest plugin z same=1 zips="" made_engine="" made_dl=""
  dest="$dl/${stage##*/}"
  plugin="$dest/x/whynot-cut-marketplace/whynot-cut"
  if [ -L "$dl" ]; then  # (fix round 8, N-4) a downloads that is a link is never written through (nor cleaned inside)
    printf 'ERROR: %s\n' "could not keep the release in $dest: $dl is a link, which WhyNot Cut does not follow. Nothing was installed: remove or move the link, then run the installer again." >&2
    printf '%s\n' "تعذّر حفظ ملفات WhyNot Cut في مجلد المحرك لأن المجلد downloads فيه رابط، وWhyNot Cut لا يتبع الروابط، فلم يُثبَّت شيء. احذف الرابط أو انقله ثم شغّل المثبّت مرة أخرى." >&2
    exit 3
  fi
  { [ -d "$dest" ] && [ ! -L "$dest" ] && [ -f "$plugin/installer/core/wnc_install.py" ]; } || same=""
  for z in "$stage"/*; do
    [ -f "$z" ] || continue
    zips=1
    if [ -n "$same" ] && { [ ! -f "$dest/${z##*/}" ] || [ "$(file_sha "$dest/${z##*/}")" != "$(file_sha "$z")" ]; }
    then same=""; fi
  done
  [ -n "$zips" ] || same=""
  if [ -z "$same" ]; then
    [ -d "$2" ] || made_engine=1
    [ -d "$dl" ] || made_dl=1
    if ! { mkdir -p "$dl" && rm -rf "$dest.tmp" && cp -R "$stage" "$dest.tmp" && [ -z "$TEST_CACHE_FAIL" ] \
           && rm -rf "$dest" && mv "$dest.tmp" "$dest"; }; then
      rm -rf "$dest.tmp"  # (rm never follows a link)
      if [ -n "$made_dl" ]; then rmdir "$dl" 2>/dev/null; fi
      if [ -n "$made_engine" ]; then rmdir "$2" 2>/dev/null; fi
      printf 'ERROR: %s\n' "could not keep the release in $dest; most likely the disk is full. Nothing was installed: free some space, then run the installer again." >&2
      printf '%s\n' "تعذّر حفظ ملفات WhyNot Cut في مجلد المحرك (غالبًا لأن القرص ممتلئ)، فلم يُثبَّت شيء. وفّر مساحة ثم شغّل المثبّت مرة أخرى." >&2
      exit 3
    fi
  fi
  say "the release is kept in $dest"
  ROOT="$plugin"
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

in_foreground() { # our process group owns the terminal: reading it from the background would stop us (SIGTTIN)
  local st
  st="$(ps -o stat= -p $$ 2>/dev/null)"
  case "$st" in *+*) return 0 ;; esac
  return 1
}

has_keyboard() { # a person at OUR terminal, in the foreground: stdin is the terminal, or (curl | bash) stdout or
  # stderr is one and /dev/tty can be opened. A child of a tool (Claude's Bash tool, CI) without a terminal on stdin,
  # stdout and stderr never reads /dev/tty (fix round 1)
  if [ -t 0 ]; then in_foreground; return $?; fi
  { [ -t 1 ] || [ -t 2 ]; } || return 1
  { : </dev/tty; } 2>/dev/null || return 1
  in_foreground
}

can_ask() { # the location question: only on the Customise path (D-T1), never with --yes or --uninstall; the test
  # hook; else a terminal (or /dev/tty)
  [ -z "$YES" ] && [ -z "$UNINSTALL" ] && [ "$RUN_MODE" = "customise" ] || return 1
  [ -n "$ANSWERS" ] && return 0
  has_keyboard
}

# D-T1: the install size, the core's system.install_size_gb (argv: components.json, platform, model, skip list,
# git missing 1/0). macOS: JXA; elsewhere (Git Bash in tests) the same rule in Python.
JXA_SIZE='function run(argv) {
  ObjC.import("Foundation");
  var c = null;
  var d = $.NSData.dataWithContentsOfFile(argv[0]);
  var t = d.isNil() ? null : $.NSString.alloc.initWithDataEncoding(d, $.NSUTF8StringEncoding);
  if (t !== null && !t.isNil()) { try { c = JSON.parse(ObjC.unwrap(t).replace(/^\uFEFF/, "")); } catch (e) { c = null; } }
  function get(o, keys) {
    for (var i = 0; i < keys.length; i++) {
      if (o === null || typeof o !== "object" || Array.isArray(o) ||
          !Object.prototype.hasOwnProperty.call(o, keys[i])) { return null; }
      o = o[keys[i]];
    }
    return o;
  }
  function isInt(b) { return typeof b === "number" && Math.floor(b) === b; }
  function list(v) { return Array.isArray(v) ? v : []; }
  function sized(items, fb) {
    var s = 0, any = false;
    items.forEach(function (i) { if (i !== null && typeof i === "object" && isInt(i.bytes)) { s += i.bytes; any = true; } });
    return any ? s / 1073741824 : fb;
  }
  var plat = argv[1], model = argv[2], skip = "," + argv[3] + ",", git = argv[4] === "1", nvidia = argv[5] === "1";
  var sizes = {"large-v3": 2.9, "large-v3-turbo": 1.6, "medium": 1.5, "small": 0.5};
  var total = 0, b;
  if (skip.indexOf(",runtime,") < 0) { total += 0.5; }
  if (skip.indexOf(",ffmpeg,") < 0) { total += sized(list(get(c, ["ffmpeg", "assets", plat, "files"])), 0.1); }
  if (skip.indexOf(",fonts,") < 0) {
    total += sized(list(get(c, ["fonts", "files"])).concat(list(get(c, ["fonts", "licenses"]))), 0.01);
  }
  if (skip.indexOf(",model,") < 0) { b = get(c, ["models", model, "bytes"]); total += isInt(b) ? b / 1073741824 : (sizes[model] || 2.9); }
  if (plat.indexOf("win") === 0 && git && skip.indexOf(",gitbash,") < 0) { total += 0.4; }
  if (plat.indexOf("win") === 0 && nvidia && skip.indexOf(",gpu,") < 0) { total += 1.0; }
  return (Math.ceil(Math.round(total * 10 * 1e6) / 1e6) / 10).toFixed(1);
}'
PY_SIZE='import json, math, sys
try:
    c = json.loads(open(sys.argv[1], encoding="utf-8-sig").read())
except (OSError, ValueError):
    c = None
def get(o, keys):
    for k in keys:
        if not isinstance(o, dict) or k not in o:
            return None
        o = o[k]
    return o
def lst(v):
    return v if isinstance(v, list) else []
def sized(items, fb):
    s = [i["bytes"] for i in items if isinstance(i, dict) and type(i.get("bytes")) is int]
    return sum(s) / 1073741824 if s else fb
plat, model, skip, git, nvidia = sys.argv[2], sys.argv[3], sys.argv[4].split(","), sys.argv[5] == "1", \
    sys.argv[6] == "1"
sizes = {"large-v3": 2.9, "large-v3-turbo": 1.6, "medium": 1.5, "small": 0.5}
total = 0.0
if "runtime" not in skip:
    total += 0.5
if "ffmpeg" not in skip:
    total += sized(lst(get(c, ["ffmpeg", "assets", plat, "files"])), 0.1)
if "fonts" not in skip:
    total += sized(lst(get(c, ["fonts", "files"])) + lst(get(c, ["fonts", "licenses"])), 0.01)
if "model" not in skip:
    b = get(c, ["models", model, "bytes"])
    total += b / 1073741824 if type(b) is int else sizes.get(model, 2.9)
if plat.startswith("win") and git and "gitbash" not in skip:
    total += 0.4
if plat.startswith("win") and nvidia and "gpu" not in skip:
    total += 1.0
print("%.1f" % (math.ceil(round(total * 10, 6)) / 10))'

install_size() { # -> SIZE_GB, the core's system.install_size_gb (see JXA_SIZE)
  local git=0 nvidia=0 la="${LOCALAPPDATA:-}" c=0 m
  case "$PLAT" in
    win-*)  # (Git Bash in tests only: macOS has no Git or CUDA step)
      if [ ! -f "$la/Programs/Git/bin/bash.exe" ] && [ ! -f "$la/WhyNotCut/git/bin/bash.exe" ]; then git=1; fi
      if [ -n "$HOME_OVR" ] && [ "${WNC_TEST_NVIDIA:-}" = "1" ]; then nvidia=1; fi ;;
  esac
  SIZE_GB=""
  if [ "$OS_NAME" = "Darwin" ]; then
    SIZE_GB="$(osascript -l JavaScript -e "$JXA_SIZE" "$COMP" "$PLAT" "${MODEL_OPT:-large-v3}" "$SKIP" "$git" \
      "$nvidia" 2>/dev/null </dev/null)"
  elif [ -n "$JSON_PY" ]; then
    SIZE_GB="$("$JSON_PY" -I -c "$PY_SIZE" "$COMP" "$PLAT" "${MODEL_OPT:-large-v3}" "$SKIP" "$git" "$nvidia" \
      2>/dev/null </dev/null | tr -d '\r')"
  fi
  case "$SIZE_GB" in [0-9]*.[0-9]) return 0 ;; esac
  # no JSON reader: the same rule from the constants alone, in hundredths of a GB (runtime 0.5, ffmpeg 0.1, fonts
  # 0.01, the model, Git 0.4, CUDA 1.0), rounded up to one decimal
  case ",$SKIP," in *,runtime,*) ;; *) c=$((c + 50)) ;; esac
  case ",$SKIP," in *,ffmpeg,*) ;; *) c=$((c + 10)) ;; esac
  case ",$SKIP," in *,fonts,*) ;; *) c=$((c + 1)) ;; esac
  case "${MODEL_OPT:-large-v3}" in large-v3-turbo) m=160 ;; medium) m=150 ;; small) m=50 ;; *) m=290 ;; esac
  case ",$SKIP," in *,model,*) ;; *) c=$((c + m)) ;; esac
  case ",$SKIP," in *,gitbash,*) ;; *) [ "$git" = 1 ] && c=$((c + 40)) ;; esac
  case ",$SKIP," in *,gpu,*) ;; *) [ "$nvidia" = 1 ] && c=$((c + 100)) ;; esac
  c=$(((c + 9) / 10))
  SIZE_GB="$((c / 10)).$((c % 10))"
}

read_key() { # seconds -> K; status 0 when a key came. Only from the terminal: stdin when it is one, else /dev/tty
  K=""
  if [ -t 0 ]; then
    IFS= read -r -s -n 1 -t "$1" K
  else
    IFS= read -r -s -n 1 -t "$1" K </dev/tty 2>/dev/null
  fi
}

countdown() { # -> KEY: customise (C), key (any other key: go on at once) or timeout. "Press C to customise (10)..."
  # counts down in place for 10 s, reading one key a second from the terminal (read_key), or the sandbox-only hook
  # WNC_TEST_KEYS (waits WNC_TEST_COUNTDOWN_S seconds in all). Keys typed before the line appeared (the Enter after
  # the command) are not answers: bash 4+ drains them at once; bash 3.2 (no fractional timeout) spends the first
  # second draining them.
  local s=10 n=0
  KEY="timeout"
  printf '\rPress C to customise (%s)%s / %s ' "$s" "…" "اضغط C للتخصيص"
  if [ -z "$TEST_KEYS_SET" ]; then
    if [ "${BASH_VERSINFO[0]:-3}" -ge 4 ]; then
      while [ "$n" -lt 100 ] && read_key 0.05; do n=$((n + 1)); done
    else
      while [ "$n" -lt 100 ] && read_key 1; do n=$((n + 1)); done
      s=9
    fi
  fi
  while [ "$s" -ge 1 ] && [ "$KEY" = "timeout" ]; do
    printf '\rPress C to customise (%s)%s / %s ' "$s" "…" "اضغط C للتخصيص"
    if [ -n "$TEST_KEYS_SET" ]; then
      case "$TEST_KEYS" in
        ""|none) ;;
        [cC]*) KEY="customise" ;;
        *) KEY="key" ;;
      esac
    elif read_key 1; then
      KEY="key"
      case "$K" in [cC]) KEY="customise" ;; esac
    fi
    s=$((s - 1))
  done
  printf '\n'
  if [ -n "$TEST_KEYS_SET" ] && [ "$KEY" = "timeout" ] && [ "$TEST_COUNTDOWN" -gt 0 ]; then sleep "$TEST_COUNTDOWN"; fi
  return 0
}

select_mode() { # -> RUN_MODE: customise (--customise, or C during the countdown), default (a person at the
  # terminal who did not customise) or yes (--yes, --uninstall, or nobody at a terminal). The core gets --customise
  # for the first, --yes for the other two: the same strongest defaults and the same state.json.
  RUN_MODE="yes"
  [ -z "$UNINSTALL" ] || return 0
  if [ -n "$CUSTOMISE" ]; then RUN_MODE="customise"; return 0; fi
  install_size
  printf 'Installing everything WhyNot Cut needs (about %s GB)\n' "$SIZE_GB"
  printf 'جارٍ تثبيت كل ما يحتاجه WhyNot Cut (حوالي %s جيجابايت)\n' "$SIZE_GB"
  [ -z "$YES" ] || return 0
  if [ -z "$TEST_KEYS_SET" ] && ! has_keyboard; then return 0; fi
  RUN_MODE="default"
  countdown
  if [ "$KEY" = "customise" ]; then
    RUN_MODE="customise"
    printf '%s\n' "Customise: answer the questions below; Enter keeps the suggested answer."
    printf '%s\n' "التخصيص: أجب عن الأسئلة التالية؛ اضغط Enter لإبقاء الإجابة المقترحة."
  fi
  return 0
}

guard_norm() { # path -> NORM (norm_path), case folded on macOS too: APFS / HFS+ ignore case (fix round 1)
  norm_path "$1"
  if [ "$OS_NAME" = "Darwin" ]; then NORM="$(printf '%s' "$NORM" | tr '[:upper:]' '[:lower:]')"; fi
}

real_path() { # path -> REAL: every link on the way resolved (cd -P on the part that exists), "" when it cannot be
  local d="$1" rest="" up r
  while [ "${d%/}" != "$d" ] && [ "${d%/}" != "" ]; do d="${d%/}"; done
  while [ -n "$d" ] && [ ! -d "$d" ]; do
    rest="/${d##*/}$rest"
    up="${d%/*}"
    [ "$up" = "$d" ] && break
    d="$up"
  done
  [ -n "$d" ] || d="/"
  r="$(cd -P "$d" 2>/dev/null && pwd -P)" || { REAL=""; return 0; }
  case "$OS_NAME" in MINGW*|MSYS*|CYGWIN*) if command -v cygpath >/dev/null 2>&1; then r="$(cygpath -m "$r")"; fi ;; esac
  REAL="${r%/}$rest"
}

place_keys() { # path -> KEY1 (as written), KEY2 (links resolved), both from guard_norm
  guard_norm "$1"; KEY1="$NORM"
  real_path "$1"
  if [ -n "$REAL" ]; then guard_norm "$REAL"; KEY2="$NORM"; else KEY2="$KEY1"; fi
}

resolved_home_problem() { # path [mode] -> WHY (empty: fine), the core's base.resolved_home_problem: ~/.whynot-cut
  # itself is fine - unless it is a link (Addendum F): then where it points is checked like any resolved home (fix
  # round 3) and placed like a chosen folder (fix round 4: linked_target_problem). mode: install (every rule),
  # uninstall (a genuine engine home is not refused for client folders inside it), deferred (no "occupied" rule)
  local p="$1" mode="${2:-install}" a genuine="" skip=""
  WHY=""
  case "$p" in \\\\*|//*) place_problem "$p" ""; return 0 ;; esac
  lex_path "$p"; p="$LEX"  # (fix round 5, N4: x/nope/../.whynot-cut is ~/.whynot-cut; a trailing / or /. too)
  guard_norm "$p"; a="$NORM"
  guard_norm "$HOME/.whynot-cut"
  if [ "$a" = "$NORM" ]; then
    [ -L "$p" ] || return 0
    if [ ! -d "$p" ]; then
      WHY="a link to a folder that does not exist - reconnect the drive or remove the link"; return 0
    fi
    our_home "$p" 1 && genuine=1  # (fix round 5, N1: the leftover of an uninstall too)
    place_problem "$p" 1 ""  # (every client rule, at uninstall too: the target may be anyone's folder)
    if [ -z "$WHY" ]; then real_path "$p"; linked_target_problem "$REAL" "$genuine" "$mode"; fi
    if [ -n "$WHY" ]; then
      real_path "$p"
      WHY="a link to ${REAL:-a target that cannot be read}, which is ${WHY#a link to } - remove the link, or point"
      WHY="$WHY ~/.whynot-cut at an empty folder of its own, or run again with -EngineHome <folder> / --engine-home"
      WHY="$WHY <folder>"
    fi
    return 0
  fi
  if [ "$mode" = uninstall ] && [ -d "$p" ] && our_home "$p"; then skip="skip-clients"; fi
  place_problem "$p" "" "$skip"
}

linked_target_problem() { # real-target genuine mode -> WHY: the core's base._linked_target_problem - the target of a
  # linked ~/.whynot-cut must not hold the home folder, lie inside a client folder or the saved clients folder, nor
  # (install / uninstall) hold anything while not being a genuine engine home (no WhyNotCut subfolder can be made there)
  local r d up c shown
  WHY=""
  [ -n "$1" ] || return 0
  guard_norm "$1"; r="$NORM"
  place_keys "$HOME"
  if { [ "$KEY1" != "$r" ] && within "$KEY1" "$r"; } || { [ "$KEY2" != "$r" ] && within "$KEY2" "$r"; }; then
    WHY="a folder that holds your user folder"; return 0
  fi
  d="${1%/*}"
  while [ -n "$d" ]; do
    if [ -e "$d/.whynot-client" ]; then WHY="inside a client folder ($d holds .whynot-client)"; return 0; fi
    up="${d%/*}"
    [ "$up" = "$d" ] && break
    d="$up"
  done
  while IFS= read -r c; do
    [ -n "$c" ] || continue
    place_keys "$c"
    if { [ "$r" != "$KEY1" ] && within "$r" "$KEY1"; } || { [ "$r" != "$KEY2" ] && within "$r" "$KEY2"; }; then
      WHY="inside your clients folder $c"; return 0
    fi
  done <<EOF
$CLIENT_ROOTS
EOF
  if [ "$3" != deferred ] && [ -z "$2" ] && has_occupied "$1" 1; then
    shown="$(printf '%s\n' "$OCCUPIED" | head -n 3 | tr '\n' '|' | sed 's/|$//; s/|/, /g')"
    [ "$(printf '%s\n' "$OCCUPIED" | wc -l | tr -d ' ')" -gt 3 ] && shown="$shown, ..."
    WHY="a folder that already holds other files ($shown) and is not a WhyNot Cut engine folder (if it is your old"
    WHY="$WHY WhyNot Cut folder, move your own files out of it and run again)"
  fi
  return 0
}

place_problem() { # path link-ok -> WHY: a RESOLVED engine home must not be a link itself (unless link-ok: the
  # linked ~/.whynot-cut), a drive root or mount point, the home folder or Desktop /
  # Documents / Downloads themselves, the saved clients folder or a folder holding it, a folder with .whynot-client in
  # it or up to 3 levels below, or one too big to check for that (more than 5000 entries within 3 levels); every
  # comparison as written and with links resolved, case folded on macOS
  local p="$1" a b d c lp cnt rp
  WHY=""
  case "$p" in
    \\\\*|//*) WHY="a network share or device path; name a folder on a local drive"; return 0 ;;  # (fix round 2)
  esac
  while [ "${p%/}" != "$p" ] && [ "${p%/}" != "" ] && [ "${p%/}" != "${p%%:*}:" ]; do p="${p%/}"; done
  guard_norm "$p"; a="$NORM"
  case "$a" in /|[A-Za-z]:|[A-Za-z]:/) WHY="a drive root or a mount point"; return 0 ;; esac
  if [ -L "$p" ] && [ -z "${2:-}" ]; then
    WHY="a link or mount point (a junction, symlink or mounted folder); name the real folder instead"; return 0
  fi
  if is_mount "$p"; then WHY="a drive root or a mount point"; return 0; fi
  place_keys "$p"; a="$KEY1" b="$KEY2" rp="$REAL"
  case "$b" in /|[A-Za-z]:|[A-Za-z]:/) WHY="a drive root or a mount point"; return 0 ;; esac
  if [ -n "$rp" ] && is_mount "$rp"; then WHY="a drive root or a mount point"; return 0; fi  # (the real target too)
  place_keys "$HOME"
  if [ "$a" = "$KEY1" ] || [ "$a" = "$KEY2" ] || [ "$b" = "$KEY1" ] || [ "$b" = "$KEY2" ]; then
    WHY="your user folder itself"; return 0
  fi
  for d in Desktop Documents Downloads; do
    place_keys "$HOME/$d"
    if [ "$a" = "$KEY1" ] || [ "$a" = "$KEY2" ] || [ "$b" = "$KEY1" ] || [ "$b" = "$KEY2" ]; then
      WHY="your $d folder itself"; return 0
    fi
  done
  [ "${3:-}" = skip-clients ] && return 0  # (an uninstall of a genuine engine home: client folders inside stay)
  while IFS= read -r c; do
    [ -n "$c" ] || continue
    place_keys "$c"
    if within "$KEY1" "$a" || within "$KEY1" "$b" || within "$KEY2" "$a" || within "$KEY2" "$b"; then
      WHY="your clients folder $c, or it holds it"; return 0
    fi
  done <<EOF
$CLIENT_ROOTS
EOF
  if [ -d "$p" ]; then
    [ -n "$rp" ] || rp="$p"  # (the real folder: find does not enter a link named on its command line)
    lp="$(find "$rp" -maxdepth 4 -name .whynot-client 2>/dev/null </dev/null | head -n 1)"
    if [ -n "$lp" ]; then WHY="holding a client folder (${lp%/*} holds .whynot-client)"; return 0; fi
    cnt="$(find "$rp" -mindepth 1 -maxdepth 4 2>/dev/null </dev/null | head -n 5001 | wc -l | tr -d ' ')"
    if [ "${cnt:-0}" -gt 5000 ]; then
      WHY="too big to check for client folders (more than 5000 entries within 3 levels); choose an engine folder"
      WHY="$WHY of its own with -EngineHome / --engine-home"
    fi
  fi
  return 0
}

uninstall_place() { # path -> PLACED, PLACE_NOTE, PROBLEM: the folder --uninstall --engine-home names (fix round 5, N3),
  # the core's base.uninstall_engine_home, same rules and order: a full path that exists, not a network path, drive root,
  # mount point, link or inside the plugin folder; WhyNot Cut's own (our_home), or else its WhyNotCut subfolder when that
  # is WhyNot Cut's own and an install would have made it (the home folder, Desktop, Documents, Downloads, a folder
  # holding the editor's files); then not the home folder or holding it, not inside Claude's folder, in a sandbox inside
  # it, and the resolved-home guard in uninstall mode. Nothing is written here.
  local p="$1" n r d sub nf moved_in="" pointer_ok=""
  PLACED="" PLACE_NOTE="" PROBLEM=""
  case "$p" in
    \\\\*|//*) PROBLEM="$p is a network share or device path; name a folder on a local drive"; return 0 ;;
    /*|[A-Za-z]:/*|[A-Za-z]:\\*) ;;
    *) PROBLEM="$p is not a full path (for example $HOME/WhyNotCut)"; return 0 ;;
  esac
  lex_path "$p"; p="$LEX"
  norm_path "$p"; n="$NORM"
  case "$n" in
    /|[A-Za-z]:|[A-Za-z]:/) PROBLEM="$p is a drive root or a mounted volume, never a WhyNot Cut engine folder"; return 0 ;;
  esac
  if is_mount "$p"; then PROBLEM="$p is a drive root or a mounted volume, never a WhyNot Cut engine folder"; return 0; fi
  if [ -L "$p" ]; then
    PROBLEM="$p is a link or mount point; name the real folder (leave --engine-home out when it is your ~/.whynot-cut)"
    return 0
  fi
  if [ ! -d "$p" ]; then PROBLEM="$p does not exist; name the folder WhyNot Cut was installed in"; return 0; fi
  norm_path "$ROOT"; r="$NORM"
  if within "$n" "$r"; then PROBLEM="$p is inside the plugin folder $ROOT, never a WhyNot Cut engine folder"; return 0; fi
  norm_path "$HOME/.whynot-cut"
  [ "$NORM" = "$n" ] && pointer_ok=1
  PLACED="$p"
  if ! our_home "$p" "$pointer_ok"; then
    for d in "$HOME" "$HOME/Desktop" "$HOME/Documents" "$HOME/Downloads"; do
      norm_path "$d"
      [ "$NORM" = "$n" ] && moved_in=1
    done
    if [ -z "$moved_in" ] && has_occupied "$p" "$pointer_ok"; then moved_in=1; fi
    sub="${p%/}/WhyNotCut"
    if [ -z "$moved_in" ] || [ -L "$sub" ] || [ ! -d "$sub" ] || ! our_home "$sub"; then
      PROBLEM="$p is not a WhyNot Cut engine folder (no state.json or current of WhyNot Cut's, no Whisper models of its"
      PROBLEM="$PROBLEM own) and has no WhyNotCut folder of WhyNot Cut's in it; name the folder WhyNot Cut was installed in"
      PLACED=""
      return 0
    fi
    PLACED="$sub"
    PLACE_NOTE="$p is not a WhyNot Cut engine folder, but $sub is (an install named $p put WhyNot Cut there): uninstalling from $sub"
  fi
  norm_path "$PLACED"; nf="$NORM"
  norm_path "$HOME"
  if within "$NORM" "$nf"; then PROBLEM="$PLACED is your user folder or holds it"; PLACED=""; return 0; fi
  norm_path "$HOME/.claude"
  if within "$nf" "$NORM"; then PROBLEM="$PLACED is inside Claude's folder $HOME/.claude"; PLACED=""; return 0; fi
  if [ -n "$HOME_OVR" ]; then
    norm_path "$H"
    if [ "$nf" = "$NORM" ] || ! within "$nf" "$NORM"; then
      PROBLEM="$PLACED is outside the sandbox home $H (--home: nothing outside it is used)"; PLACED=""; return 0
    fi
  fi
  resolved_home_problem "$PLACED" uninstall
  if [ -n "$WHY" ]; then PROBLEM="$PLACED is $WHY"; PLACED=""; fi
  return 0
}

ask_line() { # default -> ANSWER (trimmed; empty = the default); status 1 when there is no more input
  printf 'Folder / المجلد [%s]: ' "$1"
  ANSWER=""
  if [ -n "$ANSWERS" ]; then
    if ! IFS= read -r ANSWER <&3 && [ -z "$ANSWER" ]; then printf '\n'; return 1; fi
    ANSWER_AT=$((ANSWER_AT + 1))
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
  local default="$1" with_model="$2" text ask="" tries=0 need p old_install n_new
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
    if is_engine_home "$default"; then
      printf 'WhyNot Cut is already installed in %s; Enter keeps it there.\n' "$default"
      printf '%s\n' "WhyNot Cut مثبّت بالفعل في هذا المجلد؛ اضغط Enter لإبقائه."
    fi
    if ask_line "$default" && [ -n "$ANSWER" ]; then text="$ANSWER"; CHOSEN=1; fi
  fi
  old_install=""  # WhyNot Cut already lives in the default folder (3.0, or a 2.x home: venv, models ...)
  if is_engine_home "$default" || has_occupied "$default" 1; then old_install=1; fi
  while [ "$tries" -lt 8 ]; do
    tries=$((tries + 1))
    typed_path "$text"; p="$TYPED"
    norm_path "$p"; n_new="$NORM"
    norm_path "$default"
    if [ "$n_new" = "$NORM" ]; then
      # the resolved home (default ~/.whynot-cut, or saved in the pointer / settings.json / a variable) is used as it
      # is (fix round 3): a 2.x home (venv, models, ...) is upgraded in place, never moved
      CHOSEN="" PROBLEM="" PLACE_NOTE="" PLACED="$p"
      if [ -n "$HOME_OVR" ]; then
        norm_path "$H"
        if [ "$n_new" = "$NORM" ] || ! within "$n_new" "$NORM"; then
          PROBLEM="$p is outside the sandbox home $H (--home: nothing outside it is used)"
        fi
      fi
    else
      engine_place "$p"  # a folder the editor chose: placed (its own WhyNotCut subfolder when it holds anything)
    fi
    if [ -z "$PROBLEM" ]; then
      if [ -n "$PLACE_NOTE" ]; then
        printf '%s\n' "$PLACE_NOTE"
        printf '%s\n' "هذا المجلد فيه ملفات أخرى، لذلك سيُثبَّت WhyNot Cut في مجلد خاص به داخله (WhyNotCut)، ولن يلمس الإلغاء باقي الملفات."
      fi
      p="$PLACED"
    fi
    if [ -z "$PROBLEM" ] && ! is_engine_home "$p"; then
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
      elif [ ! -f "$p/state.json" ]; then
        # claim the folder before anything lands in it (fix round 2): a run that stops before the core (a failed
        # download) leaves a GENUINE engine home, so the next run uses it again directly
        printf '{"schema": 1, "plugin": null, "updated_at": null, "steps": {}}\n' > "$p/state.json" 2>/dev/null \
          || PROBLEM="it cannot be written"
      fi
    fi
    if [ -z "$PROBLEM" ]; then
      norm_path "$p"; n_new="$NORM"
      norm_path "$default"
      if [ -n "$old_install" ] && [ "$n_new" != "$NORM" ]; then
        printf 'WARNING: the WhyNot Cut already installed in %s stays there and is no longer used; delete it yourself when you no longer need it.\n' "$default"
        printf '%s %s\n' "تنبيه: التثبيت القديم سيبقى في مكانه ولن يُستخدم بعد الآن؛ احذفه بنفسك إن لم تعد تحتاجه:" "$default"
      fi
      ENGINE="$p"
      return 0
    fi
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
case "$OS_NAME" in  # Git Bash: `pwd` may say /tmp/... for %TEMP%; the location checks compare Windows paths
  MINGW*|MSYS*|CYGWIN*) if command -v cygpath >/dev/null 2>&1; then ROOT="$(cygpath -m "$ROOT")"; fi ;;
esac
STAGE=""  # install.sh --source (fix round 6, R5-5): this run's release, staged under the OS temp dir
if [ -n "$RELEASE_STAGE" ]; then
  st="$(abs_path "$RELEASE_STAGE")"
  case "$OS_NAME" in
    MINGW*|MSYS*|CYGWIN*) if command -v cygpath >/dev/null 2>&1; then st="$(cygpath -m "$st")"; fi ;;
  esac
  # (round 8, MAC-1) both through real_path: the same release spelled through another prefix (/var vs /private/var)
  real_path "$st/x/whynot-cut-marketplace/whynot-cut"; norm_path "${REAL:-$st/x/whynot-cut-marketplace/whynot-cut}"
  n_st="$NORM"
  real_path "$ROOT"; norm_path "${REAL:-$ROOT}"
  case "${st##*/}" in
    release-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) [ "$n_st" = "$NORM" ] && STAGE="$st" ;;
  esac
  [ -n "$STAGE" ] || printf 'WARNING: --release-stage %s is not the folder of this run'"'"'s release; it is not kept\n' \
    "$RELEASE_STAGE"
fi
TEST_UV="" ANSWERS="" TEST_FREE="" TEST_KEYS="" TEST_KEYS_SET="" TEST_COUNTDOWN=10 ANSWER_AT=0 RUN_MODE="yes"
TEST_CACHE_FAIL=""
TEST_MOUNTS=""
if [ -n "$HOME_OVR" ]; then
  TEST_MOUNTS="${WNC_TEST_MOUNTS:-}"
  TEST_UV="${WNC_TEST_UV:-}" ANSWERS="${WNC_TEST_ANSWERS:-}" TEST_FREE="${WNC_TEST_FREE_GB:-}"
  [ "${WNC_TEST_CACHE_FAIL:-}" = 1 ] && TEST_CACHE_FAIL=1  # the --source cache copy fails
  if [ -n "${WNC_TEST_KEYS+x}" ]; then TEST_KEYS_SET=1 TEST_KEYS="$WNC_TEST_KEYS"; fi
  TEST_COUNTDOWN="${WNC_TEST_COUNTDOWN_S:-10}"
  case "$TEST_COUNTDOWN" in ''|*[!0-9]*) TEST_COUNTDOWN=10 ;; esac
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
# (fix rounds 4 and 5, N4) its lexical form before any test: a saved ~/.whynot-cut/, ~/.whynot-cut/. or
# <home>/nope/../.whynot-cut (nope missing: `[ -L ]` would not see through it) is ~/.whynot-cut
lex_path "$ENGINE"; ENGINE="$LEX"
DEFAULT_ENGINE="$ENGINE"
COMP="$ROOT/setup/components.json"
[ -n "$COMPONENTS" ] && COMP="$(abs_path "$COMPONENTS")"
IS_RESOLVED=1
if [ -n "$ENGINE_OPT" ]; then  # --engine-home naming the saved home itself is that home, used as it is (fix round 2)
  IS_RESOLVED=""
  typed_path "$ENGINE_OPT"; guard_norm "$TYPED"; n_opt="$NORM"
  guard_norm "$DEFAULT_ENGINE"
  case "$TYPED" in /*|[A-Za-z]:*) [ "$n_opt" = "$NORM" ] && IS_RESOLVED=1 ;; esac
fi
LINKED_DEFAULT=""  # ~/.whynot-cut that is a link: also checked before an uninstall (fix round 3)
if [ -L "$DEFAULT_ENGINE" ]; then
  guard_norm "$DEFAULT_ENGINE"; n_def="$NORM"
  guard_norm "$HOME/.whynot-cut"
  [ "$n_def" = "$NORM" ] && LINKED_DEFAULT=1
fi
if [ -n "$IS_RESOLVED" ]; then
  # (fix round 4) an uninstall too, for any resolved home - also with --engine-home naming it - so that nothing (log,
  # uv, Python) is written into a folder the core will refuse
  GUARD_MODE=install
  [ -n "$UNINSTALL" ] && GUARD_MODE=uninstall
  # task 9: a home saved somewhere in a place it must never be: stop and say the fix, before the countdown and any
  # download (fix round 1), also when --engine-home names that same folder (fix round 2)
  client_roots
  resolved_home_problem "$DEFAULT_ENGINE" "$GUARD_MODE"
  if [ -n "$WHY" ]; then
    printf 'ERROR: WhyNot Cut will not use %s as its engine home (from %s): it is %s. Nothing was changed. To fix it, run the installer again with -EngineHome <folder> / --engine-home <folder> (a folder of its own, for example ~/WhyNotCut).\n' \
      "$DEFAULT_ENGINE" "$ENGINE_SRC" "$WHY"
    printf '%s\n' "لن يستخدم WhyNot Cut هذا المجلد لملفات التشغيل. لإصلاح ذلك شغّل المثبّت مرة أخرى مع -EngineHome <folder> (على macOS: --engine-home <folder>) واختر مجلدًا خاصًا به."
    if [ -n "$LINKED_DEFAULT" ]; then
      printf '%s\n' "الرابط ~/.whynot-cut يشير إلى مجلد لا يصلح أو غير موجود: أعد توصيل القرص، أو احذف الرابط، أو وجّهه إلى مجلد فارغ خاص به، أو شغّل المثبّت مرة أخرى مع -EngineHome <folder>. وإن كان هو مجلد WhyNot Cut القديم نفسه وفيه ملفات أخرى لك، فانقلها خارجه ثم شغّل المثبّت مرة أخرى."
    fi
    exit 2
  fi
fi
LINK_REAL=""  # (fix round 5, N6) where a linked ~/.whynot-cut points now; the deferred delete checks it again
if [ -n "$LINKED_DEFAULT" ]; then real_path "$DEFAULT_ENGINE"; LINK_REAL="$REAL"; fi
select_mode  # D-T1: no question unless the editor customises (--customise, or C during the countdown)
if [ -n "$UNINSTALL" ]; then
  # no question: the folder the engine uses - also when --engine-home names it (fix round 5, N2: the linked
  # ~/.whynot-cut included, the core then applies the Addendum F rules) - or the folder --engine-home names, placed and
  # checked before anything is written (N3)
  if [ -n "$ENGINE_OPT" ] && [ -z "$IS_RESOLVED" ]; then
    typed_path "$ENGINE_OPT"
    client_roots
    uninstall_place "$TYPED"
    if [ -n "$PROBLEM" ]; then
      printf 'ERROR: WhyNot Cut cannot uninstall from %s: %s. Nothing was changed. To fix it, name the folder WhyNot Cut was installed in with -EngineHome <folder> / --engine-home <folder>, or leave it out to use the saved one.\n' \
        "$TYPED" "$PROBLEM"
      printf '%s\n' "لا يمكن إلغاء التثبيت من هذا المجلد. اكتب بعد -EngineHome <folder> (على macOS: --engine-home <folder>) المجلد الذي ثُبّت فيه WhyNot Cut، أو احذف هذا الخيار ليُستخدم المجلد المحفوظ."
      exit 2
    fi
    if [ -n "$PLACE_NOTE" ]; then
      printf '%s\n' "$PLACE_NOTE"
      printf '%s\n' "هذا المجلد ليس مجلد WhyNot Cut، لكن المجلد WhyNotCut داخله هو مجلده (ثبّته هناك تثبيت سابق)، لذلك سيُلغى التثبيت منه."
    fi
    ENGINE="$PLACED"; CHOSEN=1
  fi
else
  [ -n "$ANSWERS" ] && exec 3<"$ANSWERS"
  case ",$SKIP," in *,model,*) WITH_MODEL="" ;; *) WITH_MODEL=1 ;; esac
  select_engine_home "$DEFAULT_ENGINE" "$WITH_MODEL"
fi
[ -n "$HOME_OVR" ] && export WHYNOT_HOME="$ENGINE"
[ -n "$ANSWERS" ] && export WNC_TEST_ANSWERS_AT="$ANSWER_AT"  # the core reads the test answers after these

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
  if [ -n "$STAGE" ] && [ -z "$UNINSTALL" ]; then
    # --source: every check passed, so the release is kept in this engine home now (fix round 6, R5-5); an uninstall
    # needs it only while it runs, so it is never written into the folder it empties. A failed copy stops here, before
    # the log and the core (fix round 7, M6-3)
    keep_release "$STAGE" "$ENGINE"
    CORE="$ROOT/installer/core/wnc_install.py"
  fi
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
if [ -n "$UNINSTALL" ]; then
  [ -n "$YES" ] && set -- "$@" --yes
elif [ "$RUN_MODE" = "customise" ]; then
  set -- "$@" --customise
else
  set -- "$@" --yes  # the default install is exactly the --yes path (D-T1)
fi
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
