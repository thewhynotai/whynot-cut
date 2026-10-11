"""Test-only stand-in for uv (tests/test_installer.py, T7.1 runtime step). Never shipped to editors.

How the installer core runs it: env WNC_TEST_UV (honoured only when the core runs in a sandbox, --home) names this
file or one of its wrappers. A value ending in `.py` is run as `<the core's own sys.executable> -B fake_uv.py ...`;
any other value (fake_uv.cmd on Windows, fake_uv.sh elsewhere) is run directly. The wrappers start this file with
$FAKE_UV_PYTHON (default `python` / `python3`).

Behaviour:
  --version                       prints `uv <FAKE_UV_VERSION or 0.0.0>`
  python install <v>              exit 0
  python find <v>                 prints sys.executable
  venv <dir> [--python <py>] ...  `<py or sys.executable> -m venv --without-pip <dir>` (other flags ignored)
  pip sync ...                    exit 1 when FAKE_UV_FAIL=sync, else 0
Every call appends its argv as one JSON line to $FAKE_UV_LOG (when set), so a test can assert "no uv call".
"""
import json
import os
import subprocess
import sys


def main(argv):
    log = os.environ.get("FAKE_UV_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(argv, ensure_ascii=False) + "\n")
    if argv[:1] == ["--version"]:
        print("uv " + os.environ.get("FAKE_UV_VERSION", "0.0.0"))
        return 0
    if argv[:2] == ["python", "install"]:
        return 0
    if argv[:2] == ["python", "find"]:
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
