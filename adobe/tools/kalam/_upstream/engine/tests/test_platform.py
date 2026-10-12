import sys
from pathlib import Path

from kalam import platform as P
from kalam.correct import _run_cli


def test_claude_candidates_windows():
    home = Path("C:/Users/Ali")
    c = P.claude_candidates({"APPDATA": "C:/Users/Ali/AppData/Roaming"}, home, windows=True)
    assert str(home / ".local" / "bin" / "claude.exe") in c
    assert str(Path("C:/Users/Ali/AppData/Roaming") / "npm" / "claude.cmd") in c
    assert not any(x.startswith("/opt/") for x in c)


def test_claude_candidates_mac():
    c = P.claude_candidates({}, Path("/Users/x"), windows=False)
    assert "/opt/homebrew/bin/claude" in c
    assert "/Users/x/.local/bin/claude" in c


def test_backend_env_forces_portable(monkeypatch):
    monkeypatch.setenv("KALAM_BACKEND", "portable")
    assert P.backend() == "portable"


def test_backend_is_portable_off_mac(monkeypatch):
    monkeypatch.delenv("KALAM_BACKEND", raising=False)
    monkeypatch.setattr(P.sys, "platform", "win32")
    assert P.backend() == "portable"


def test_run_cli_utf8(tmp_path):
    code, out = _run_cli([sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
                         "هيرقيك Reputation", str(tmp_path))
    assert code == 0 and out == "هيرقيك Reputation"
