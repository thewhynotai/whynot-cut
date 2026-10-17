# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 39 (L-T1): tests for the REAL findings of the first scan (triage: docs/security/baseline.json, reason
"real: ..."). The fix belongs to the file's owner; lane 3 sends a patch (D:/ClaudeData/claude-api-lane/lane3/hooks/L-T1/)
and these tests. Each strict test states the FIXED behaviour and is marked `expectedFailure` while its id is in OPEN, so
it is red-by-design today. When the owner applies the patch the test passes: unittest reports an UNEXPECTED SUCCESS (a
failing run), which is the signal to delete the id from OPEN and turn the test into a plain one.

  serve-security-which       serve/security.py resolves `icacls` and `whoami` through PATH before System32 (L-G11): a planted
                             icacls.exe / whoami.exe runs when the bearer-token file is locked down. Owner: Adobe track.
  bootstrap-staging-delete   installer/core/bootstrap.ps1 Install-WncUv deletes its staging folder with
                             `Remove-Item -Recurse` (follows junctions on Windows PowerShell 5.1, L-G12). Owner: installer track.
Run:  tools/test.sh -p test_security_scan_findings.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "whynot-cut" / "engine" / "reel"
_sys.path.insert(0, str(ENGINE))

OPEN = {"bootstrap-staging-delete"}
WINDOWS = unittest.skipUnless(os.name == "nt", "Windows only: the hazard is the Windows search order")


def open_issue(issue_id):
    """expectedFailure while `issue_id` is in OPEN, a plain test once it is not."""
    return unittest.expectedFailure if issue_id in OPEN else (lambda f: f)


def planted_tool_dir(name):
    """A temp folder holding <name>.cmd that writes marker.txt: a stand-in for a planted <name>.exe (harmless)."""
    d = Path(tempfile.mkdtemp(prefix="wncplant-", dir=os.environ.get("TMP")))
    (d / (name + ".cmd")).write_text('@echo planted> "%~dp0marker.txt"\r\n@exit /b 0\r\n', encoding="ascii")
    return d


class ServeSecurityToolPaths(unittest.TestCase):
    def _run_with_planted(self, name, call):
        from serve import security
        d = planted_tool_dir(name)
        path = os.pathsep.join([str(d), os.environ.get("PATH", "")])
        target = Path(tempfile.mkdtemp(prefix="wnctok-", dir=os.environ.get("TMP"))) / "engine.json"
        target.write_text("{}", encoding="utf-8")
        with mock.patch.dict(os.environ, {"PATH": path}):
            try:
                call(security, str(target))
            except (OSError, ValueError):
                pass  # the planted stand-in prints nothing: a failure after it ran is fine, we only look for the marker
        return (d / "marker.txt").exists()

    @WINDOWS
    @open_issue("serve-security-which")  # lane3/hooks/L-T1/serve-security-system32.patch
    def test_a_planted_icacls_in_path_is_never_run(self):
        self.assertFalse(self._run_with_planted("icacls", lambda s, p: s.restrict_to_user(p)))

    @WINDOWS
    @open_issue("serve-security-which")  # lane3/hooks/L-T1/serve-security-system32.patch
    def test_a_planted_whoami_in_path_is_never_run(self):
        self.assertFalse(self._run_with_planted("whoami", lambda s, p: s._sid_from_whoami()))

    @open_issue("serve-security-which")
    def test_source_has_no_which_for_system_tools(self):
        text = (ENGINE / "serve" / "security.py").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"which\(\s*[\"'](icacls|whoami)")


class BootstrapStagingDelete(unittest.TestCase):
    PS1 = ROOT / "whynot-cut" / "installer" / "core" / "bootstrap.ps1"

    def _recursive_removes(self):
        out = []
        for n, ln in enumerate(self.PS1.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            code = ln.split("#", 1)[0]
            if re.search(r"\bRemove-Item\b", code) and re.search(r"\s-r(?:e(?:c(?:u(?:r(?:s(?:e)?)?)?)?)?)?(?![A-Za-z])", code, re.I):
                out.append((n, ln.strip()))
        return out

    @open_issue("bootstrap-staging-delete")
    def test_no_recursive_remove_item_in_bootstrap(self):
        self.assertEqual(self._recursive_removes(), [])


if __name__ == "__main__":
    unittest.main()
