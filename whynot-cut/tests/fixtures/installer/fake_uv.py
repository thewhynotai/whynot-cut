"""Test-only stand-in for uv (tests/test_installer.py, T7.1 runtime step). Never shipped to editors.

How the installer core runs it: env WNC_TEST_UV (honoured only when the core runs in a sandbox, --home) names this
file or one of its wrappers. A value ending in `.py` is run as `<the core's own sys.executable> -B fake_uv.py ...`;
a value ending in `.sh` is run as `bash fake_uv.sh ...` (git keeps this file 100644, so it is never exec'd: EACCES on
macOS CI round 1); any other value (fake_uv.cmd on Windows) is run directly. The wrappers start this file with
$FAKE_UV_PYTHON (default `python` / `python3`).

Behaviour:
  --version                       prints `uv <FAKE_UV_VERSION or 0.0.0>`
  python install <v> ...          exit 0
  python find <v> ...             prints sys.executable on stdout (plus a warning on stderr, which the core must
                                  ignore); exit 1 instead, once, while the file $FAKE_UV_FIND_FAIL_ONCE is missing
                                  (it is created then), so the core goes on to `python install`
  venv <dir> [--python <py>] ...  `<py or sys.executable> -m venv --without-pip <dir>` (other flags ignored)
  pip sync ...                    exit 1 when FAKE_UV_FAIL=sync, else 0
Every call appends {"argv": [...], "UV_NO_CONFIG": <env value or null>} as one JSON line to $FAKE_UV_LOG (when
set), so a test can assert "no uv call" and that the core switched uv's config files off.
"""
import json
import os
import subprocess
import sys


def main(argv):
    log = os.environ.get("FAKE_UV_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"argv": argv, "UV_NO_CONFIG": os.environ.get("UV_NO_CONFIG")},
                               ensure_ascii=False) + "\n")
    if argv[:1] == ["--version"]:
        print("uv " + os.environ.get("FAKE_UV_VERSION", "0.0.0"))
        return 0
    if argv[:2] == ["python", "install"]:
        return 0
    if argv[:2] == ["python", "find"]:
        marker = os.environ.get("FAKE_UV_FIND_FAIL_ONCE")
        if marker and not os.path.exists(marker):
            open(marker, "w").close()
            sys.stderr.write("error: no managed Python found\n")
            return 1
        sys.stderr.write("warning: this line is on stderr and is not the interpreter\n")
        print(sys.executable)
        return 0
    if argv[:1] == ["venv"] and len(argv) >= 2:
        py = sys.executable
        if "--python" in argv:
            py = argv[argv.index("--python") + 1]
        return subprocess.run([py, "-m", "venv", "--without-pip", argv[1]], stdin=subprocess.DEVNULL).returncode
    if argv[:2] == ["pip", "sync"]:
        return 1 if os.environ.get("FAKE_UV_FAIL") == "sync" else 0
    sys.stderr.write(f"fake uv: unsupported call {argv!r}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
