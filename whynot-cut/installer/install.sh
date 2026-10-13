#!/usr/bin/env bash
# WhyNot Cut installer for macOS (Apple silicon and Intel) - per user, no admin rights, no Homebrew, no Xcode tools.
#
# From the extracted WhyNot Cut zip (Terminal, in the extracted folder):
#     bash whynot-cut/installer/install.sh
# One line (once the files are hosted, H3):
#     curl -fsSL https://thewhynot.ai/install.sh | bash
# With options, one line:
#     curl -fsSL https://thewhynot.ai/install.sh | bash -s -- --source <zip or https url> --source-sha256 <hex>
#
# Where the plugin comes from: this script's folder's parent when it holds setup/components.json (the zip layout
# whynot-cut/installer/install.sh). Otherwise (curl | bash: the script arrives on stdin and $0 is "bash") the release
# zip given by --source (a path or an https URL) and --source-sha256 is copied or downloaded into
# ~/.whynot-cut/downloads/release-<sha8>/, verified, and extracted; its whynot-cut-marketplace/whynot-cut folder is the
# plugin. Without --source the release index is used - until it is hosted (H3) the script says so and exits 2.
# Then installer/core/bootstrap.sh (uv + Python) runs and hands over to the Python installer core. Every option is
# described in installer/README.md. Exit code: the installer's (0 done, 1 a step failed, 2 cannot start, 3 a download
# or bootstrap step failed). On Windows use install.ps1 (Git Bash is refused unless the WNC_TEST_PLATFORM test hook is
# set together with --home).
# It asks no question by default (D-T1): it says how much it installs and counts down 10 seconds ("Press C to
# customise", read from the terminal, never from the piped script); C or --customise asks the questions (location,
# model, language, clients folder), every answer preselected; --yes skips the countdown too.
# Everything sits inside main(), called on the last line: under `curl | bash` nothing runs before the whole script has
# arrived, and no child reads the rest of the script from stdin. bash 3.2 compatible.

# Filled by the release tool once the files are hosted (H3). The index is JSON:
#   { "stable": { "url": "https://.../WhyNotCut-<version>.zip", "sha256": "<64 hex>" }, "beta": { ... } }
WNC_RELEASE_INDEX_URL='<release>'

main() {
  local home="" dry="" channel="" source="" source_sha="" root="" src="" here="" code=0 engine_home=""
  local pass=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --source) source="$2"; shift ;;
      --source-sha256) source_sha="$2"; shift ;;
      --home) home="$2"; pass+=("$1" "$2"); shift ;;
      --channel) channel="$2"; pass+=("$1" "$2"); shift ;;
      --engine-home) engine_home="$2"; pass+=("$1" "$2"); shift ;;
      --clients-folder|--language|--components|--skip|--model) pass+=("$1" "$2"); shift ;;
      --dry-run) dry=1; pass+=("$1") ;;
      --yes|-y|--uninstall|--remove-engine|--remove-models|--customise|--customize) pass+=("$1") ;;
      -h|--help) sed -n '2,22p' "${BASH_SOURCE[0]:-/dev/null}" 2>/dev/null || echo "see installer/README.md"; return 0 ;;
      *) echo "ERROR: unknown option $1 (see installer/README.md)" >&2; return 2 ;;
    esac
    shift
  done

  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
      if [ -z "$home" ] || [ -z "${WNC_TEST_PLATFORM:-}" ]; then
        echo "This is Windows: use install.ps1 on Windows (PowerShell), not install.sh." >&2
        return 2
      fi ;;
  esac

  src="${BASH_SOURCE[0]:-}"
  if [ -n "$src" ] && [ -f "$src" ]; then
    here="$(cd "$(dirname "$src")/.." 2>/dev/null && pwd)"
    if [ -n "$here" ] && [ -f "$here/setup/components.json" ]; then root="$here"; fi
  fi
  if [ -z "$root" ]; then
    wnc_release "$home" "$dry" "$channel" "$source" "$source_sha" "$engine_home" || return $?
    root="$RELEASE_ROOT"
    [ -n "$root" ] || return 0  # dry run: nothing fetched
  fi
  if [ -t 0 ]; then
    bash "$root/installer/core/bootstrap.sh" --plugin-root "$root" "${pass[@]}"
  else
    bash "$root/installer/core/bootstrap.sh" --plugin-root "$root" "${pass[@]}" </dev/null
  fi
  code=$?
  return $code
}

wnc_sha() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 < "$1" | awk '{print $1}'
  else sha256sum < "$1" | awk '{print $1}'; fi
}

wnc_py() { # a python for the non-macOS fallbacks (Git Bash in tests)
  local c
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import zipfile' >/dev/null 2>&1 </dev/null; then
      printf '%s\n' "$c"; return 0
    fi
  done
  return 1
}

wnc_unzip() { # zip dir
  local py
  if command -v unzip >/dev/null 2>&1; then unzip -q -o "$1" -d "$2" </dev/null; return $?; fi
  if [ "$(uname -s)" = "Darwin" ]; then ditto -x -k "$1" "$2" </dev/null; return $?; fi
  py="$(wnc_py)" || return 1
  "$py" -I -m zipfile -e "$1" "$2" </dev/null
}

# macOS: JavaScript for Automation (built in; plutil cannot hold JSON nulls). The JSON text and the key path arrive as
# run() arguments, never inside the script text. Prints the value; null or a missing key prints nothing.
WNC_JXA_INDEX_GET='function run(argv) {
  var v;
  try { v = JSON.parse(argv[0]); } catch (e) { return ""; }
  var keys = argv[1].split(".");
  for (var i = 0; i < keys.length; i++) {
    if (v === null || typeof v !== "object" || !Object.prototype.hasOwnProperty.call(v, keys[i])) { return ""; }
    v = v[keys[i]];
  }
  if (v === null || v === undefined) { return ""; }
  return (typeof v === "object") ? JSON.stringify(v) : String(v);
}'

wnc_index_get() { # json-text dotted.path (macOS: osascript JavaScript; elsewhere python)
  local py
  if [ "$(uname -s)" = "Darwin" ]; then
    osascript -l JavaScript -e "$WNC_JXA_INDEX_GET" "$1" "$2" 2>/dev/null </dev/null
    return $?
  fi
  py="$(wnc_py)" || return 1
  printf '%s' "$1" | "$py" -I -c '
import json, sys
v = json.load(sys.stdin)
for k in sys.argv[1].split("."):
    v = v.get(k) if isinstance(v, dict) else None
print("" if v is None else v)' "$2" 2>/dev/null | tr -d '\r'
}

wnc_engine_home() { # sandbox-home engine-home -> WNC_ENGINE: where the -Source release zip is cached
  # the engine home as bootstrap.sh will find it: --engine-home (its WhyNotCut subfolder when it holds other files or
  # is the home folder / Desktop / Documents / Downloads, as engine_place does), else the engine-home variables (not
  # in a sandbox), the pointer's engine_home, our settings.json pluginConfigs option, else ~/.whynot-cut. A rare
  # disagreement with the bootstrap only means the zip is cached elsewhere.
  local h="${1:-$HOME}" e="$2" n v cfg d
  if [ -n "$e" ]; then
    case "$e" in /*|[A-Za-z]:*) ;; *) e="$PWD/$e" ;; esac
    e="${e%/}"
    WNC_ENGINE="$e"
    if [ -f "$e/state.json" ] || [ -f "$e/current" ] || [ -f "$e/bin/uv" ] || [ -f "$e/bin/uv.exe" ]; then return 0; fi
    for d in "$h" "$h/Desktop" "$h/Documents" "$h/Downloads"; do
      if [ "${d%/}" = "$e" ]; then WNC_ENGINE="$e/WhyNotCut"; return 0; fi
    done
    if [ -d "$e" ] && [ -n "$(ls -A "$e" 2>/dev/null)" ]; then WNC_ENGINE="$e/WhyNotCut"; fi
    return 0
  fi
  if [ -z "$1" ]; then
    for n in WHYNOT_HOME CLAUDE_PLUGIN_OPTION_ENGINE_HOME REEL_HOME CLAUDE_PLUGIN_OPTION_REEL_HOME NH_ENV_DIR; do
      v="${!n:-}"
      if [ -n "$v" ]; then WNC_ENGINE="$v"; return 0; fi
    done
  fi
  v=""
  if [ -f "$h/.whynot-cut/plugin-options.json" ]; then
    v="$(wnc_index_get "$(cat "$h/.whynot-cut/plugin-options.json" 2>/dev/null)" engine_home)"
  fi
  if [ -z "$v" ]; then
    cfg="$h/.claude"
    [ -z "$1" ] && [ -n "${CLAUDE_CONFIG_DIR:-}" ] && cfg="$CLAUDE_CONFIG_DIR"
    if [ -f "$cfg/settings.json" ]; then
      v="$(wnc_index_get "$(cat "$cfg/settings.json" 2>/dev/null)" "pluginConfigs.whynot-cut@thewhynot-ai.options.engine_home")"
    fi
  fi
  WNC_ENGINE="${v:-$h/.whynot-cut}"
}

wnc_release() { # home dry channel source sha engine-home -> RELEASE_ROOT (empty after a dry run); status 2 / 3
  local home="$1" dry="$2" channel="$3" src="$4" sha="$5" engine="$6" name="" dir="" zip="" x="" plugin="" got="" idx=""
  RELEASE_ROOT=""
  if [ -z "$src" ]; then
    case "$WNC_RELEASE_INDEX_URL" in
      "<release"*)
        echo "WhyNot Cut hosting is not ready yet (H3): download the WhyNot Cut zip, extract it, then run bash whynot-cut/installer/install.sh"
        echo "الاستضافة غير جاهزة بعد (H3): نزّل ملف WhyNot Cut بصيغة zip، فكّه، ثم شغّل bash whynot-cut/installer/install.sh"
        return 2 ;;
    esac
    [ -n "$channel" ] || channel="stable"
    idx="$(curl -fsSL "$WNC_RELEASE_INDEX_URL" </dev/null)" \
      || { echo "ERROR: cannot read the release index $WNC_RELEASE_INDEX_URL" >&2; return 3; }
    src="$(wnc_index_get "$idx" "$channel.url")"
    sha="$(wnc_index_get "$idx" "$channel.sha256")"
    [ -n "$src" ] || { echo "ERROR: the release index has no $channel entry" >&2; return 3; }
    echo "WhyNot Cut $channel release: $src"
  fi
  if ! printf '%s' "$sha" | grep -Eq '^[0-9a-fA-F]{64}$'; then
    echo "ERROR: --source needs --source-sha256 <the 64-character sha256 of the zip>" >&2
    return 2
  fi
  sha="$(printf '%s' "$sha" | tr 'A-F' 'a-f')"
  case "$src" in
    https://*|http://127.0.0.1[:/]*|http://localhost[:/]*) ;;
    http://*) echo "ERROR: --source must be a file or an https:// URL: $src" >&2; return 2 ;;
    /*|[A-Za-z]:*) ;;
    *) src="$PWD/$src" ;;
  esac
  if [ -n "$home" ]; then
    case "$home" in /*|[A-Za-z]:*) ;; *) home="$PWD/$home" ;; esac
  fi
  wnc_engine_home "$home" "$engine"
  engine="$WNC_ENGINE"
  name="${src##*/}"; name="${name%%\?*}"
  [ -n "$name" ] || name="WhyNotCut.zip"
  dir="$engine/downloads/release-$(printf '%s' "$sha" | cut -c1-8)"
  if [ -n "$dry" ]; then
    echo "dry run: would fetch $src, check its sha256 $sha, extract it into $dir and run its installer"
    return 0
  fi
  zip="$dir/$name"; x="$dir/x"; plugin="$x/whynot-cut-marketplace/whynot-cut"
  if [ ! -f "$zip" ] || [ "$(wnc_sha "$zip")" != "$sha" ]; then
    mkdir -p "$dir" || { echo "ERROR: cannot create $dir" >&2; return 3; }
    rm -f "$zip.part"
    echo "fetching $src"
    case "$src" in
      http://*|https://*)
        # a plain file name inside $dir: a native Windows curl (Git Bash tests) cannot open non-ASCII paths
        if ! (cd "$dir" && curl -fL --retry 3 -sS -o "$name.part" "$src") </dev/null; then
          rm -f "$zip.part"; echo "ERROR: could not download $src" >&2; return 3
        fi ;;
      *) cp "$src" "$zip.part" || { echo "ERROR: cannot read $src" >&2; return 3; } ;;
    esac
    got="$(wnc_sha "$zip.part")"
    if [ "$got" != "$sha" ]; then
      rm -f "$zip.part"
      echo "ERROR: sha256 mismatch for $name (expected $sha, got $got); the file was deleted" >&2
      return 3
    fi
    mv -f "$zip.part" "$zip" && rm -rf "$x"
  fi
  echo "verified $name (sha256 ok)"
  if [ ! -f "$plugin/setup/components.json" ]; then
    rm -rf "$x.tmp" "$x"
    if ! { mkdir -p "$x.tmp" && wnc_unzip "$zip" "$x.tmp" && mv "$x.tmp" "$x"; }; then
      echo "ERROR: cannot extract $name" >&2
      return 3
    fi
  fi
  if [ ! -f "$plugin/installer/core/bootstrap.sh" ]; then
    echo "ERROR: $name is not a WhyNot Cut release zip (no whynot-cut-marketplace/whynot-cut/installer)" >&2
    return 3
  fi
  echo "WhyNot Cut files: $plugin"
  RELEASE_ROOT="$plugin"
}

main "$@"; exit $?
