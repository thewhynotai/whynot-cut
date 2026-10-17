# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 39 (L-T1): `tools/security/install_tools.py` and `versions.json` (Addendum L §L3).

Cases: C-SHA (a download whose sha256 differs is refused and nothing is left in the tools home), pins in
versions.json are well-formed, the dev lock matches its recorded sha256 (lock-hash test), and the dev lock carries a
hash for every requirement (L-G37 / hash-pinned lockfiles). No network, no real tool is installed by these tests.
Run:  tools/test.sh -p test_security_scan_install.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402
import hashlib
import io
import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEC = ROOT / "tools" / "security"
sys.path.insert(0, str(SEC))

import install_tools as it  # noqa: E402

VERS = json.loads((SEC / "versions.json").read_text(encoding="utf-8"))


class VersionsFile(unittest.TestCase):
    def test_every_binary_pinned_with_sha256_and_https_official_url(self):
        for name, b in VERS["binaries"].items():
            self.assertRegex(b["version"], r"^\d+\.\d+\.\d+$", name)
            for plat, p in b["platforms"].items():
                self.assertRegex(p["sha256"], r"^[0-9a-f]{64}$", (name, plat))
                self.assertTrue(p["url"].startswith("https://github.com/"), (name, plat))
                self.assertIn(b["version"], p["url"].replace("_amd64", "").replace("v", ""), (name, plat))

    def test_python_tools_pinned_exactly(self):
        for name, p in VERS["python_tools"]["packages"].items():
            self.assertRegex(p["version"], r"^\d+(\.\d+)+$", name)

    def test_lock_sha256_matches_the_lock(self):
        lock = ROOT / VERS["python_tools"]["lock"]
        self.assertEqual(hashlib.sha256(lock.read_bytes()).hexdigest(), VERS["python_tools"]["lock_sha256"])

    def test_lock_pins_match_versions_json(self):
        text = (ROOT / VERS["python_tools"]["lock"]).read_text(encoding="utf-8").lower()
        for name, p in VERS["python_tools"]["packages"].items():
            self.assertRegex(text, r"(?m)^%s==%s\b" % (re.escape(name), re.escape(p["version"])))

    def test_every_lock_requirement_has_a_hash(self):
        bad = it.lock_lines_without_hash((ROOT / VERS["python_tools"]["lock"]).read_text(encoding="utf-8"))
        self.assertEqual(bad, [])

    def test_option_lines_of_a_lock_are_not_requirements(self):
        text = ("--index-url https://pypi.org/simple\n--extra-index-url https://example.invalid/whl\n\n"
                "abc==1 \\\n    --hash=sha256:" + "a" * 64 + "\n")
        self.assertEqual(it.lock_lines_without_hash(text), [])

    def test_hash_checker_catches_a_planted_unhashed_line(self):
        text = "good==1.0 \\\n    --hash=sha256:" + "a" * 64 + "\nbad==2.0\n"
        self.assertEqual(it.lock_lines_without_hash(text), ["bad==2.0"])
        text2 = "multi==1.0 ; python_version >= '3.9' \\\n    --hash=sha256:" + "b" * 64 + " \\\n    --hash=sha256:" + "c" * 64 + "\n"
        self.assertEqual(it.lock_lines_without_hash(text2), [])


class Sha256Refusal(unittest.TestCase):
    def _spec(self, payload, sha):
        return {"url": "https://example.invalid/x.zip", "sha256": sha, "archive": "zip",
                "member": "tool.exe", "exe": "tool.exe"}

    def _zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("tool.exe", b"MZ fake")
        return buf.getvalue()

    def test_wrong_sha_is_refused_and_leaves_nothing(self):
        data = self._zip()
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "tools home مجلد"
            with self.assertRaises(it.InstallError) as cm:
                it.install_binary("tool", "1.0.0", self._spec(data, "0" * 64), home, fetch=lambda url: data)
            self.assertIn("sha256", str(cm.exception))
            self.assertFalse((home / "bin" / "tool.exe").exists())

    def test_right_sha_installs_and_records_manifest(self):
        data = self._zip()
        sha = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "tools home مجلد"
            exe = it.install_binary("tool", "1.0.0", self._spec(data, sha), home, fetch=lambda url: data)
            self.assertEqual(exe.read_bytes(), b"MZ fake")
            man = json.loads((home / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(man["tool"]["archive_sha256"], sha)
            self.assertEqual(man["tool"]["exe_sha256"], hashlib.sha256(b"MZ fake").hexdigest())

    def test_zip_member_with_path_traversal_name_is_not_extracted_outside(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("../evil.exe", b"x")
            z.writestr("tool.exe", b"ok")
        data = buf.getvalue()
        sha = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "h"
            it.install_binary("tool", "1.0.0", self._spec(data, sha), home, fetch=lambda url: data)
            self.assertFalse((Path(d) / "evil.exe").exists())

    def test_tampered_installed_file_is_detected(self):
        data = self._zip()
        sha = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "h"
            exe = it.install_binary("tool", "1.0.0", self._spec(data, sha), home, fetch=lambda url: data)
            self.assertIsNone(it.verify_installed("tool", home))
            exe.write_bytes(b"tampered")
            self.assertIn("sha256", it.verify_installed("tool", home))


if __name__ == "__main__":
    unittest.main()
