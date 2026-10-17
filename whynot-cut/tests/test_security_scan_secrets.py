# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 40 (L-T2): the secrets sweep: gitleaks over the working tree and the full history, `.gitleaks.toml`.

Case list: the lane's work folder `L-T2/cases.md`. Every secret here is invented and built from fragments at run time
inside a temp git repo (a folder name with a space and Arabic letters), so this file holds no key-shaped text and no
`.gitleaks.toml` allow rule is needed for it. Tests that need gitleaks skip with a reason when it is not installed.
Run:  tools/test.sh -p test_security_scan_secrets.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SEC = ROOT / "tools" / "security"
_sys.path.insert(0, str(SEC))

import install_tools as it  # noqa: E402
import scan  # noqa: E402

TOOLS_OK = not it.check_all()
NEEDS_TOOLS = unittest.skipUnless(TOOLS_OK, "scanners not installed: python tools/security/install_tools.py")
GIT = shutil.which("git", path=os.environ.get("PATH", ""))
NEEDS_GIT = unittest.skipUnless(GIT and os.path.isabs(GIT), "git not found")


def setUpModule():
    if os.environ.get("WNC_REQUIRE_SCANNERS") == "1" and not TOOLS_OK:
        raise AssertionError("WNC_REQUIRE_SCANNERS=1 but the scanners are not installed/intact: %s" % it.check_all())

KEY = "AKIA" + "QYLPMN5HHHFPZAM2"                       # AWS access key id shape
GHP = "ghp_" + "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0eF3hJ6"     # GitHub PAT shape (36 chars)
STRIPE = "sk_live_" + "9f8e7d6c5b4a39281706f5e4d3c2b1a0"
ANT = "sk-ant-api03-" + ("Qw3Er7Ty1Ui5Op9As2Df6Gh0Jk4Lz8Xc" * 3)[:93] + "AA"
JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ." + "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
PEM = ("-----BEGIN " + "RSA PRIVATE KEY-----\n" + "\n".join(["MIIEowIBAAKCAQEA" + "x7Q2m9Zk" * 6] * 6)
       + "\n-----END " + "RSA PRIVATE KEY-----\n")  # the markers are split so this file holds no private-key block itself
GENERIC = 'api_key = "' + "k8Jd92Lq0Zx7Vb3Nm5Tr1Yw6Uc4Hf2Ae" + '"'
CLASSES = {
    "aws": 'aws_key = "%s"\n' % KEY,
    "github": 'token = "%s"\n' % GHP,
    "stripe": 'stripe_key = "%s"\n' % STRIPE,
    "anthropic": 'ANTHROPIC = "%s"\n' % ANT,
    "jwt": 'auth = "%s"\n' % JWT,
    "private-key": PEM,
    "generic": GENERIC + "\n",
}
VALUES = [KEY, GHP, STRIPE, ANT, JWT.split(".")[2], "k8Jd92Lq0Zx7Vb3Nm5Tr1Yw6Uc4Hf2Ae", "x7Q2m9Zkx7Q2m9Zk"]


def git(repo, *args):
    p = subprocess.run([GIT, "-c", "user.email=t@t.invalid", "-c", "user.name=t", "-c", "core.autocrlf=false", *args],
                       cwd=str(repo), capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("git %s: %s" % (args, p.stderr.decode("utf-8", "replace")))
    return p.stdout.decode("utf-8", "replace")


def new_repo(base: Path) -> Path:
    repo = base / "مشروع سري" / "repo x"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", ".")
    (repo / "readme.txt").write_text("hello\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    return repo


def assert_no_values(tc, *blobs):
    text = "\n".join(blobs)
    for v in VALUES:
        tc.assertNotIn(v, text)


class AllowRules(unittest.TestCase):
    """S7: .gitleaks.toml allow rules can never hide a real pattern class."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = tomllib.loads((ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))

    def test_default_rules_stay_on(self):
        self.assertTrue(self.cfg["extend"]["useDefault"])
        self.assertNotIn("rules", self.cfg)  # no rule is redefined, disabled or replaced here
        self.assertNotIn("allowlist", self.cfg)  # only [[allowlists]] entries, each reviewed below

    def test_every_allow_rule_is_one_file_and_one_exact_value(self):
        al = [a for a in self.cfg["allowlists"] if "commits" not in a]
        self.assertGreaterEqual(len(al), 1)
        for a in al:
            self.assertEqual(a.get("condition"), "AND", a)
            for banned in ("stopwords", "rules", "regexTarget"):
                self.assertNotIn(banned, a, "%s makes an allow rule broader than one value" % banned)
            # gitleaks 8.30.1 skips a whole file for a path-bearing allow block that has no targetRules (see the header)
            self.assertEqual(a.get("targetRules"), ["generic-api-key"], a)
            self.assertEqual(len(a["paths"]), 1, a)
            self.assertEqual(len(a["regexes"]), 1, a)
            path = a["paths"][0]
            self.assertTrue(path.startswith("^") and path.endswith("$"), path)
            self.assertNotRegex(path, r"\.\*|\.\+|\|\(|\[\^", "a path allow must name one file, no wildcard: " + path)
            self.assertRegex(path, r"\\\.[A-Za-z0-9]+\$$", "a path allow must end in a file extension: " + path)
            rx = a["regexes"][0]
            self.assertTrue(rx.startswith("^") and rx.endswith("$"), rx)
            self.assertNotRegex(rx, r"\.\*|\.\+|\[|\||\\[dwsDWS]\+|\{", "a value allow is a literal: " + rx)
            literal = rx[1:-1].replace("\\", "")
            self.assertGreaterEqual(len(literal), 12, "too short to be an exact token: " + rx)
            self.assertTrue(a.get("description"))

    def test_a_commit_pinned_block_is_one_full_commit_one_file_one_rule_and_nothing_else(self):
        pinned = [a for a in self.cfg["allowlists"] if "commits" in a]
        self.assertLessEqual(len(pinned), 1, "a commit-pinned allow is an exception: one, with a reason")
        self.assertEqual(pinned, [a for a in self.cfg["allowlists"][-1:] if "commits" in a], "it stays the LAST block")
        for a in pinned:
            self.assertEqual(a.get("condition"), "AND")
            self.assertEqual(len(a["commits"]), 1)
            self.assertRegex(a["commits"][0], r"^[0-9a-f]{40}$", "a full 40-hex commit id, never an abbreviation or a range")
            self.assertEqual(len(a["paths"]), 1)
            self.assertRegex(a["paths"][0], r"^\^[\w.\\\[\]/-]+\$$")
            self.assertNotRegex(a["paths"][0], r"\.\*|\.\+|\|")
            self.assertEqual(len(a.get("targetRules", [])), 1)
            for banned in ("stopwords", "rules", "regexTarget", "regexes"):
                self.assertNotIn(banned, a)
            self.assertTrue(a.get("description"))

    @NEEDS_TOOLS
    @NEEDS_GIT
    def test_the_commit_pinned_block_silences_exactly_its_commit_and_is_needed(self):
        pinned = [a for a in self.cfg["allowlists"] if "commits" in a]
        for a in pinned:
            sha = a["commits"][0]
            if subprocess.run([GIT, "cat-file", "-e", sha + "^{commit}"], cwd=str(ROOT), capture_output=True).returncode != 0:
                continue  # an archive / stage without that history: nothing to prove here
            exe = str(scan.tool_exe("gitleaks"))
            args = [exe, "git", ".", "--log-opts", "%s^..%s" % (sha, sha), "--redact", "--no-banner", "--exit-code", "7", "-l", "error"]
            with_block = subprocess.run(args + ["--config", str(ROOT / ".gitleaks.toml")], cwd=str(ROOT), capture_output=True).returncode
            self.assertEqual(with_block, 0, "the pinned commit still reports with the repo config")
            with tempfile.TemporaryDirectory() as d:
                bare = Path(d) / "bare.toml"
                bare.write_text('title = "bare"\n[extend]\nuseDefault = true\n', encoding="utf-8")
                without = subprocess.run(args + ["--config", str(bare)], cwd=str(ROOT), capture_output=True).returncode
            self.assertEqual(without, 7, "the commit-pinned block hides nothing: remove it")

    @NEEDS_TOOLS
    def test_every_class_sample_is_still_caught_with_our_config_in_any_path(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "مشروع" / "tree"
            for name, text in CLASSES.items():
                p = root / "whynot-cut" / "tests" / ("sample_%s.py" % name)  # the most allow-looking place there is
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
            raw = Path(d) / "raw"
            raw.mkdir()
            r = scan.scan_gitleaks(root, raw)
            self.assertEqual(r["status"], "OK", r["note"])
            hit = {f["file"].split("sample_")[-1][:-3] for f in r["findings"]}
            self.assertEqual(hit, set(CLASSES), "classes hidden by the config: %s" % (set(CLASSES) - hit))
            assert_no_values(self, json.dumps(r), (raw / "gitleaks-tree.json").read_text(encoding="utf-8"))

    @NEEDS_TOOLS
    def test_an_allowlisted_fake_is_quiet_in_its_own_file_and_loud_anywhere_else(self):
        a = self.cfg["allowlists"][0]
        path = a["paths"][0][1:-1].replace("[\\\\/]", "/").replace("\\", "")
        value = a["regexes"][0][1:-1].replace("\\", "")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "tree"
            for rel in (path, "other/elsewhere.py"):
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('KEY = "%s"\n' % value, encoding="utf-8")
            raw = Path(d) / "raw"
            raw.mkdir()
            r = scan.scan_gitleaks(root, raw)
            files = {f["file"] for f in r["findings"]}
            self.assertNotIn(path, files)
            self.assertIn("other/elsewhere.py", files)

    @NEEDS_TOOLS
    def test_a_real_key_next_to_an_allowlisted_fake_in_the_same_file_is_caught(self):
        a = self.cfg["allowlists"][0]
        path = a["paths"][0][1:-1].replace("[\\\\/]", "/").replace("\\", "")
        value = a["regexes"][0][1:-1].replace("\\", "")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "tree"
            p = root / path
            p.parent.mkdir(parents=True)
            p.write_text('KEY = "%s"\nreal = "%s"\n' % (value, KEY), encoding="utf-8")
            raw = Path(d) / "raw"
            raw.mkdir()
            r = scan.scan_gitleaks(root, raw)
            self.assertEqual([f["rule"] for f in r["findings"]], ["aws-access-token"])

    @NEEDS_TOOLS
    def test_a_key_inside_a_zip_in_the_working_tree_is_found(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "tree"
            root.mkdir()
            with zipfile.ZipFile(root / "pack.zip", "w") as z:
                z.writestr("inner.txt", 'k = "%s"' % GHP)
            raw = Path(d) / "raw"
            raw.mkdir()
            r = scan.scan_gitleaks(root, raw)
            self.assertEqual([f["file"] for f in r["findings"]], ["pack.zip!inner.txt"])

    @NEEDS_TOOLS
    def test_a_second_generic_key_in_the_same_allowlisted_file_is_caught(self):
        a = self.cfg["allowlists"][0]
        path = a["paths"][0][1:-1].replace("[\\\\/]", "/").replace("\\", "")
        value = a["regexes"][0][1:-1].replace("\\", "")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "tree"
            p = root / path
            p.parent.mkdir(parents=True)
            p.write_text('KEY = "%s"\n%s\n' % (value, GENERIC), encoding="utf-8")
            raw = Path(d) / "raw"
            raw.mkdir()
            r = scan.scan_gitleaks(root, raw)
            self.assertEqual([(f["rule"], f["line"]) for f in r["findings"]], [("generic-api-key", 2)])


@NEEDS_TOOLS
@NEEDS_GIT
class HistorySweep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory()
        base = Path(cls._td.name)
        cls.repo = repo = new_repo(base)
        # S3: committed then deleted (history only)
        (repo / "old.env").write_text("aws_key = %r\n" % KEY, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "add env")
        cls.sha_add = git(repo, "rev-parse", "--short=12", "HEAD").strip()
        git(repo, "rm", "-q", "old.env")
        git(repo, "commit", "-q", "-m", "remove env")
        # S4: a secret only in a commit message
        (repo / "readme.txt").write_text("hello 2\n", encoding="utf-8")
        git(repo, "commit", "-q", "-am", "notes\n\nexport TOKEN=%s\n" % GHP)
        cls.sha_msg = git(repo, "rev-parse", "--short=12", "HEAD").strip()
        # S5: binary files (a NUL-bearing blob, and a zip), one deleted again
        (repo / "blob.dat").write_bytes(b"MZ\0\0\1\2binary header " + STRIPE.encode() + b" tail\0\0")
        import zipfile
        with zipfile.ZipFile(repo / "pack.zip", "w") as z:
            z.writestr("inner.txt", 'k = "%s"' % GHP)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "binaries")
        # S6: a large file with a key at the end (12 MB of filler)
        with open(repo / "big.log", "w", encoding="utf-8") as f:
            f.write(("filler line of text for the large file case\n" * 280000))
            f.write('aws_key = "%s"\n' % KEY.replace("QYLP", "QYLQ"))
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "large")
        cls.raw = base / "raw"
        cls.raw.mkdir()
        cls.tree = scan.scan_gitleaks(repo, cls.raw, history=False)
        cls.hist = scan.scan_gitleaks(repo, cls.raw, history=True)
        cls.msgs = scan.scan_commit_messages(repo, cls.raw)
        cls.bins = scan.scan_binary_secrets(repo, cls.raw, history=True)

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_deleted_file_is_in_history_not_in_tree(self):
        self.assertNotIn("old.env", {f["file"] for f in self.tree["findings"]})
        h = [f for f in self.hist["findings"] if f["file"] == "old.env"]
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["commit"], self.sha_add)
        self.assertEqual(h[0]["rule"], "aws-access-token")

    def test_the_history_note_records_the_scanned_sha_and_the_commit_count(self):
        head = git(self.repo, "rev-parse", "HEAD").strip()
        self.assertIn(head, self.hist["note"])  # the full SHA, so the report can be matched to a commit
        count = git(self.repo, "rev-list", "--all", "--count").strip()
        self.assertGreaterEqual(int(count), 6)
        self.assertIn("%s commits" % count, self.hist["note"])
        self.assertNotIn(head, self.tree["note"])  # the tree scan is not a history scan

    def test_large_file_is_scanned_to_the_end(self):
        self.assertIn("big.log", {f["file"] for f in self.tree["findings"]})
        self.assertIn("big.log", {f["file"] for f in self.hist["findings"]})

    def test_secret_in_commit_message_is_found_with_its_commit(self):
        self.assertEqual(self.msgs["status"], "OK", self.msgs["note"])
        got = [(f["file"], f["commit"]) for f in self.msgs["findings"]]
        self.assertEqual(got, [("<commit message>", self.sha_msg)])
        self.assertNotIn(self.sha_add, [c for _, c in got])

    def test_binary_blob_and_its_history_are_scanned_by_printable_runs(self):
        self.assertEqual(self.bins["status"], "OK", self.bins["note"])
        files = {f["file"] for f in self.bins["findings"]}
        self.assertTrue(any(f.startswith("blob.dat") for f in files), files)

    def test_binaries_skipped_by_gitleaks_itself_are_the_reason_for_the_sweep(self):
        self.assertNotIn("blob.dat", {f["file"] for f in self.tree["findings"]})

    def test_no_value_anywhere(self):
        blob = json.dumps([self.tree, self.hist, self.msgs, self.bins])
        for p in self.raw.glob("*.json"):
            blob += p.read_text(encoding="utf-8")
        assert_no_values(self, blob, KEY.replace("QYLP", "QYLQ"))

    def test_run_scans_secrets_with_history_lists_every_part_and_blocks(self):
        raw = self.raw / "all"
        raw.mkdir()
        res = scan.run_scans({"secrets"}, self.repo, raw, history=True)
        self.assertEqual([r["tool"] for r in res], ["gitleaks", "gitleaks-binaries", "gitleaks-history", "gitleaks-messages"])
        findings = [f for r in res for f in r["findings"]]
        new, acc, exp = scan.split_by_baseline(findings, {})
        self.assertEqual(scan.exit_code(res, [f for f in new if f["severity"] in scan.BLOCKING]), scan.EXIT_FINDINGS)

    def test_handoff_lines_hold_file_line_rule_commit_and_no_value(self):
        lines = scan.handoff_lines(self.hist["findings"] + self.msgs["findings"])
        self.assertTrue(lines)
        for ln in lines:
            self.assertRegex(ln, r"^\S.* line \d+ rule \S+( commit [0-9a-f]{7,12})?$")
        assert_no_values(self, "\n".join(lines))


@NEEDS_TOOLS
class CanaryAndPolicy(unittest.TestCase):
    def test_planted_canary_in_the_working_tree_is_caught_by_the_cli_and_blocks(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "مشروع" / "tree"
            root.mkdir(parents=True)
            (root / "canary.py").write_text('canary = "%s"\n' % KEY, encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = scan.main(["--secrets", "--root", str(root), "--out", str(Path(d) / "o"), "--raw", str(Path(d) / "r"),
                                  "--gate", "t", "--baseline", str(Path(d) / "none.json")])
            self.assertEqual(code, scan.EXIT_FINDINGS, buf.getvalue())
            rep = next((Path(d) / "o").glob("scan-*-t.md")).read_text(encoding="utf-8")
            self.assertIn("aws-access-token", rep)
            self.assertIn("Needs Yunus", rep)
            assert_no_values(self, rep, buf.getvalue())

    def test_a_gitleaks_hit_can_never_be_baselined(self):
        f = scan.finding("gitleaks", "aws-access-token", "HIGH", "a.py", 1, "m", "k")
        entry = {"fingerprint": f["fingerprint"], "tool": "gitleaks", "rule": f["rule"], "file": f["file"],
                 "reason": "fake", "owner_task": "L-T2", "review_date": "2099-01-01"}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "b.json"
            p.write_text(json.dumps({"accepted": [entry]}), encoding="utf-8")
            with self.assertRaises(scan.BaselineError) as cm:
                scan.load_baseline(p)
            self.assertIn("secret", str(cm.exception))
        new, acc, exp = scan.split_by_baseline([f], {f["fingerprint"]: entry})
        self.assertEqual((len(new), len(acc)), (1, 0))


class SweepHelpers(unittest.TestCase):
    def test_printable_runs_and_binary_detection(self):
        import secrets_sweep as ss
        data = b"\0\0abc\0\0longer printable run here\0xx\0"
        self.assertTrue(ss.is_binary(data))
        self.assertEqual(ss.printable_runs(data), "longer printable run here")
        self.assertFalse(ss.is_binary(b"plain text"))

    @unittest.skipUnless(os.name == "nt", "junctions are a Windows thing")
    def test_tree_walk_never_follows_a_junction(self):
        import secrets_sweep as ss
        with tempfile.TemporaryDirectory() as d:
            real = Path(d) / "outside"
            real.mkdir()
            (real / "x.bin").write_bytes(b"\0\0 findable text in outside \0")
            tree = Path(d) / "tree"
            tree.mkdir()
            (tree / "own.bin").write_bytes(b"\0\0 findable text in the tree \0")
            link = tree / "link"
            subprocess.run([os.path.join(os.environ["SystemRoot"], "System32", "cmd.exe"), "/c", "mklink", "/J", str(link), str(real)],
                           check=True, capture_output=True)
            try:
                names = sorted(os.path.basename(p) for p in ss.walk_files(tree))
                self.assertEqual(names, ["own.bin"])
                labels = [l for l, _ in ss.tree_binary_text(tree)[0]]
                self.assertEqual(labels, ["own.bin"])
            finally:
                os.rmdir(link)  # the link only, never its target
            self.assertTrue((real / "x.bin").exists())



@NEEDS_TOOLS
@NEEDS_GIT
class HistoryBinariesAndTags(unittest.TestCase):
    """Review of L-T2: a deleted binary blob in history, UTF-16 files, annotated tags, batching, fail-closed behaviour."""

    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory()
        cls.base = Path(cls._td.name)
        cls.repo = repo = new_repo(cls.base)
        (repo / "gone.dat").write_bytes(b"MZ\0\0\1\2header " + STRIPE.encode() + b" tail\0\0")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "add binary")
        cls.sha_add = git(repo, "rev-parse", "--short=7", "HEAD").strip()
        git(repo, "rm", "-q", "gone.dat")
        git(repo, "commit", "-q", "-m", "remove binary")
        (repo / "ps.txt").write_bytes(('aws_key = "%s"\r\n' % KEY).encode("utf-16"))  # PowerShell 5.1 `>` writes UTF-16LE + BOM
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "utf16")
        git(repo, "tag", "-a", "v9", "-m", "release notes\n\nexport TOKEN=%s" % GHP)
        cls.raw = cls.base / "raw"
        cls.raw.mkdir()

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def _bins(self):
        return scan.scan_binary_secrets(self.repo, self.raw, history=True)

    def test_a_binary_blob_deleted_from_history_is_found_with_its_commit_and_path(self):
        r = self._bins()
        self.assertEqual(r["status"], "OK", r["note"])
        hit = [f for f in r["findings"] if f["file"].startswith("blob ") and "gone.dat" in f["file"]]
        self.assertEqual(len(hit), 1, [f["file"] for f in r["findings"]])
        self.assertIn(self.sha_add, hit[0]["file"])
        self.assertNotIn("gone.dat", {p.name for p in self.repo.iterdir()})  # it really is only in history

    def test_a_utf16_file_is_read_in_the_tree_and_in_history(self):
        r = self._bins()
        files = [f["file"] for f in r["findings"]]
        self.assertIn("ps.txt", files)
        self.assertTrue(any(f.startswith("blob ") and "ps.txt" in f for f in files), files)

    def test_an_annotated_tag_message_is_scanned_and_named_by_its_tag(self):
        r = scan.scan_commit_messages(self.repo, self.raw)
        self.assertEqual(r["status"], "OK", r["note"])
        self.assertEqual([(f["file"], f["commit"]) for f in r["findings"]], [("<tag message>", "tag:v9")])

    def test_batching_does_not_change_the_result(self):
        import secrets_sweep as ss
        one = sorted(f["file"] for f in self._bins()["findings"])
        with mock.patch.object(ss, "BATCH_COUNT", 1):
            many = sorted(f["file"] for f in self._bins()["findings"])
        self.assertEqual(one, many)

    def test_small_stdin_chunks_keep_every_finding_attached_to_the_right_commit(self):
        with mock.patch.object(scan, "STDIN_CHUNK", 40):
            r = scan.scan_commit_messages(self.repo, self.raw)
        self.assertEqual([(f["file"], f["commit"]) for f in r["findings"]], [("<tag message>", "tag:v9")])

    def test_no_value_in_any_output(self):
        blob = json.dumps([self._bins(), scan.scan_commit_messages(self.repo, self.raw)])
        for p in self.raw.glob("*.json"):
            blob += p.read_text(encoding="utf-8")
        assert_no_values(self, blob)


@NEEDS_TOOLS
class HistoryFailsClosed(unittest.TestCase):
    """A history scan that could not read the history is FAILED, never 'nothing to scan'."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.d = Path(self._td.name)

    def test_a_folder_that_is_not_a_repository_fails_both_history_parts(self):
        (self.d / "a.txt").write_text("x\n", encoding="utf-8")
        for r in (scan.scan_commit_messages(self.d, self.d), scan.scan_binary_secrets(self.d, self.d, history=True)):
            self.assertEqual(r["status"], "FAILED", r["note"])
            self.assertIn("NOT read", r["note"])

    @NEEDS_GIT
    def test_a_git_that_fails_is_failed_not_empty(self):
        repo = new_repo(self.d)
        import secrets_sweep as ss
        real = scan.run

        def failing(argv, **kw):
            if "log" in argv or "cat-file" in argv:
                return 128, "", "fatal: detected dubious ownership"
            return real(argv, **kw)
        with mock.patch.object(scan, "run", side_effect=failing):
            self.assertEqual(scan.scan_commit_messages(repo, self.d)["status"], "FAILED")
            self.assertEqual(scan.scan_binary_secrets(repo, self.d, history=True)["status"], "FAILED")

    @NEEDS_GIT
    def test_a_gitfile_worktree_style_root_is_still_read(self):
        repo = new_repo(self.d)
        import secrets_sweep as ss
        self.assertTrue(ss.require_repo(repo, scan.run))  # git itself answers (a `.git` FILE would too)

    def test_truncated_and_missing_cat_file_answers(self):
        import secrets_sweep as ss
        sha_a, sha_b = "a" * 40, "b" * 40
        calls = {"n": 0}

        def run(argv, cwd=None, **kw):
            if "--batch-check=%(objecttype) %(objectname) %(objectsize)" in argv:
                return 0, "blob %s 11\nblob %s 11\n" % (sha_a, sha_b), ""
            return 0, ".git", ""

        def run_bytes(argv, cwd, data):
            calls["n"] += 1
            return 0, self.reply
        with mock.patch.object(ss, "git_exe", return_value="/usr/bin/git"):
            self.reply = (sha_a + " missing\n").encode() + (sha_b + " blob 11\n").encode() + b"\0abcdefghij\n"
            parts, big, allowed, unreadable = ss.history_binary_text(self.d, run, run_bytes)
            self.assertEqual((unreadable, [p[0] for p in parts]), (1, [sha_b]))  # a missing object does not drop the rest
            self.reply = (sha_a + " blob 11\n").encode() + b"ab"  # truncated stream
            with self.assertRaises(ss.SweepError):
                ss.history_binary_text(self.d, run, run_bytes)
            self.reply = b""  # no answer at all
            with self.assertRaises(ss.SweepError):
                ss.history_binary_text(self.d, run, run_bytes)


@NEEDS_TOOLS
class BinaryAllowList(unittest.TestCase):
    """docs/security/baseline-binaries.json pins a reviewed binary by its exact bytes (never by path alone)."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = Path(self._td.name) / "مشروع" / "tree"
        (self.root / "docs" / "security").mkdir(parents=True)
        self.data = b"\0\0font table " + GHP.encode() + b" \0"
        (self.root / "fonts.bin").write_bytes(self.data)

    def _allow(self, **entry):
        e = {"path": "fonts.bin", "reason": "a font table; the string is glyph data, reviewed", "owner_task": "executor", "review_date": "2027-01-17"}
        e.update(entry)
        (self.root / "docs" / "security" / "baseline-binaries.json").write_text(json.dumps({"allowed": [e]}), encoding="utf-8")

    def test_found_without_an_allow_entry_quiet_with_one_and_loud_again_when_the_bytes_change(self):
        raw = self.root.parent / "raw"
        raw.mkdir()
        self.assertEqual(len(scan.scan_binary_secrets(self.root, raw)["findings"]), 1)
        self._allow(sha256=hashlib.sha256(self.data).hexdigest())
        r = scan.scan_binary_secrets(self.root, raw)
        self.assertEqual(r["findings"], [])
        self.assertIn("reviewed binary", r["note"])
        (self.root / "fonts.bin").write_bytes(self.data + b"changed\0")
        self.assertEqual(len(scan.scan_binary_secrets(self.root, raw)["findings"]), 1)

    def test_a_path_alone_never_excuses_a_file_and_every_entry_needs_reason_owner_date(self):
        for bad in ({}, {"sha256": "abc"}, {"sha256": hashlib.sha256(b"x").hexdigest(), "reason": " "},
                    {"sha256": hashlib.sha256(b"x").hexdigest(), "owner_task": ""}, {"sha256": hashlib.sha256(b"x").hexdigest(), "review_date": "soon"}):
            self._allow(**bad)
            with self.assertRaises(scan.BaselineError, msg=str(bad)):
                scan.load_binary_allow(self.root)


@NEEDS_TOOLS
class EveryAllowBlockIsNeededAndSafe(unittest.TestCase):
    """Each [[allowlists]] block silences exactly its own fake in its own file and nothing else."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = tomllib.loads((ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))

    def _blocks(self):
        for a in self.cfg["allowlists"]:
            if "commits" in a:
                continue  # commit-pinned: proven by test_the_commit_pinned_block_silences_exactly_its_commit_and_is_needed
            rel = a["paths"][0][1:-1].replace("[\\\\/]", "/").replace("\\", "")
            yield a, rel

    def test_with_the_repo_config_the_real_file_is_quiet_and_without_the_block_it_is_not(self):
        for a, rel in self._blocks():
            src = ROOT / rel
            if not src.exists():
                continue  # the file this block excuses is not in this tree (a stage / archive): nothing to prove for it
            with tempfile.TemporaryDirectory() as d:
                root = Path(d) / "tree"
                dst = root / rel
                dst.parent.mkdir(parents=True)
                shutil.copyfile(src, dst)
                raw = Path(d) / "raw"
                raw.mkdir()
                quiet = scan.scan_gitleaks(root, raw)
                self.assertEqual(quiet["findings"], [], "%s still reports with the repo config" % rel)
                bare = Path(d) / "bare.toml"
                bare.write_text('title = "bare"\n[extend]\nuseDefault = true\n', encoding="utf-8")
                rc = subprocess.run([str(scan.tool_exe("gitleaks")), "dir", ".", "--config", str(bare), "--redact", "--no-banner",
                                     "--exit-code", "7", "-l", "error"], cwd=str(root), capture_output=True).returncode
                self.assertEqual(rc, 7, "the allow block for %s hides nothing: remove it" % rel)

    def test_a_real_key_added_to_each_allow_listed_file_is_still_reported(self):
        for a, rel in self._blocks():
            src = ROOT / rel
            if not src.exists():
                continue  # the file this block excuses is not in this tree (a stage / archive): nothing to prove for it
            with tempfile.TemporaryDirectory() as d:
                root = Path(d) / "tree"
                dst = root / rel
                dst.parent.mkdir(parents=True)
                shutil.copyfile(src, dst)
                with open(dst, "a", encoding="utf-8") as f:
                    f.write('\nreal = "%s"\n%s\n' % (KEY, GENERIC))
                raw = Path(d) / "raw"
                raw.mkdir()
                rules = sorted(f["rule"] for f in scan.scan_gitleaks(root, raw)["findings"])
                self.assertEqual(rules, ["aws-access-token", "generic-api-key"], rel)



@NEEDS_TOOLS
@NEEDS_GIT
class SweepEdgeCases(unittest.TestCase):
    """Second review of L-T2: ignored folders are read, a failed run leaves nothing behind, odd tag objects."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.base = Path(self._td.name)

    def test_binary_files_under_node_modules_dist_and_pycache_are_read_too(self):
        root = self.base / "tree"
        for sub in ("node_modules/x", "dist", "pkg/__pycache__"):
            (root / sub).mkdir(parents=True)
            (root / sub / "b.bin").write_bytes(b"\0\0 table " + GHP.encode() + b" \0")
        raw = self.base / "raw"
        raw.mkdir()
        r = scan.scan_binary_secrets(root, raw)
        self.assertEqual(sorted(f["file"] for f in r["findings"]),
                         ["dist/b.bin", "node_modules/x/b.bin", "pkg/__pycache__/b.bin"])

    def test_a_timed_out_or_failed_gitleaks_is_failed_leaves_no_report_and_quotes_nothing(self):
        root = self.base / "tree"
        root.mkdir()
        (root / "a.txt").write_text("x\n", encoding="utf-8")
        raw = self.base / "raw"
        raw.mkdir()
        out = raw / "gitleaks-tree.json"
        with mock.patch.object(scan, "run", side_effect=subprocess.TimeoutExpired("gitleaks", 1)):
            r = scan.scan_gitleaks(root, raw)
        self.assertEqual(r["status"], "FAILED")
        self.assertFalse(out.exists())

        def leaky(argv, **kw):
            out.write_text('[{"Secret": "%s"}]' % GHP, encoding="utf-8")  # a half-written, unscrubbed report
            return 2, "", "leaks: found " + GHP
        with mock.patch.object(scan, "run", side_effect=leaky):
            r = scan.scan_gitleaks(root, raw)
        self.assertEqual(r["status"], "FAILED")
        self.assertFalse(out.exists(), "an unscrubbed report must not outlive a failed run")
        self.assertNotIn(GHP, json.dumps(r))
        self.assertIn("withheld", r["note"])

        def boom(argv, **kw):
            out.write_text('[{"Secret": "%s", "File": "a.txt", "StartLine": 1}]' % GHP, encoding="utf-8")
            return 0, "", ""
        with mock.patch.object(scan, "run", side_effect=boom), mock.patch.object(scan, "parse_gitleaks", side_effect=TypeError("boom")):
            with self.assertRaises(TypeError):
                scan.scan_gitleaks(root, raw)
        self.assertFalse(out.exists())

    def test_a_timed_out_stdin_run_removes_its_report_and_fails_the_history_parts(self):
        repo = new_repo(self.base)
        raw = self.base / "raw"
        raw.mkdir()
        real = scan.run

        def timing_out(argv, **kw):
            if "stdin" in argv:
                (raw / "gitleaks-messages.json").write_text('[{"Secret": "%s"}]' % GHP, encoding="utf-8")
                raise subprocess.TimeoutExpired("gitleaks", 1)
            return real(argv, **kw)
        with mock.patch.object(scan, "run", side_effect=timing_out):
            r = scan.scan_commit_messages(repo, raw)
        self.assertEqual(r["status"], "FAILED")
        self.assertFalse((raw / "gitleaks-messages.json").exists())
        self.assertNotIn(GHP, json.dumps(r))

    def _tag_object(self, repo, text):
        p = subprocess.run([GIT, "hash-object", "-t", "tag", "-w", "--stdin"], cwd=str(repo), input=text.encode(), capture_output=True, check=True)
        return p.stdout.decode().strip()

    def test_an_empty_tag_message_does_not_hide_the_next_tag_and_a_tag_of_a_tag_is_followed(self):
        repo = new_repo(self.base)
        head = git(repo, "rev-parse", "HEAD").strip()
        who = "tagger t <t@t.invalid> 1700000000 +0000"
        empty = self._tag_object(repo, "object %s\ntype commit\ntag aaa-empty\n%s\n\n" % (head, who))
        inner = self._tag_object(repo, "object %s\ntype commit\ntag inner\n%s\n\nexport TOKEN=%s\n" % (head, who, GHP))
        outer = self._tag_object(repo, "object %s\ntype tag\ntag outer\n%s\n\nnothing to see\n" % (inner, who))
        git(repo, "update-ref", "refs/tags/aaa-empty", empty)
        git(repo, "update-ref", "refs/tags/zzz-outer", outer)
        raw = self.base / "raw"
        raw.mkdir()
        r = scan.scan_commit_messages(repo, raw)
        self.assertEqual(r["status"], "OK", r["note"])
        self.assertEqual([(f["file"], f["commit"]) for f in r["findings"]], [("<tag message>", "tag:zzz-outer")])

    def test_malformed_sizes_from_git_are_a_sweep_error_not_a_value_error(self):
        import secrets_sweep as ss

        def run(argv, cwd=None, **kw):
            if any("batch-check" in a for a in argv):
                return 0, "blob %s notanumber\n" % ("a" * 40), ""
            return 0, ".git", ""
        with mock.patch.object(ss, "git_exe", return_value="/usr/bin/git"):
            with self.assertRaises(ss.SweepError):
                ss.history_binary_text(self.base, run, lambda *a: (0, b""))


if __name__ == "__main__":
    unittest.main()
