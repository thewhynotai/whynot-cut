"""Phase 4 Task 19 release side (Addendum H R-T6): `tools/release.py handoff` runs the keyed identity scan over the whole
assembled hand-off folder (<out>.new) just before it is swapped in: the Mac clone's working tree, its git history
(commit messages, every patch, ref and tag names, tag messages, .git metadata), every generated file, and the members of
every .zip / .ccx / .zxp (the plugin zip included), extracted to a temp folder outside the tree.
  * identity: HARD. A finding, a scan error, a file it could not read while a key is in use, a timeout, or (on a real
    release, not a PREVIEW) a missing key stops the hand-off and nothing is swapped in. A PREVIEW without a key is
    logged as skipped. The scanner that runs is the release commit's own tools/identity_scan.py (sha256 logged).
  * secrets: REPORT-ONLY until the committed tree's real home paths are fixed or allowlisted.
Fictional tokens only (test key and hashes made in a temp folder; they name nobody).
Run:  tools/test.sh -p test_release_identity_gate.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_release_handoff as trh  # noqa: E402  (the shared fake repo + release module loader)

rel = trh.rel
ROOT = trh.REPO
sys.path.insert(0, str(ROOT / "tools"))
import identity_scan as ids  # noqa: E402

PLAIN = "# fictional test list\nZorblax Quentaro\nVexilor\n"
# The hand-off tests commit the real scanner and normaliser, whose docstrings use "Vexilor" as their CamelCase example;
# their hash list holds the other fictional token only.
PLAIN_HANDOFF = "# fictional test list\nZorblax Quentaro\n"
NO_KEY_ENV = {k: v for k, v in os.environ.items() if k not in (ids.KEY_ENV, ids.KEY_HEX_ENV)}
NORM = ROOT / "whynot-cut" / "engine" / "reel" / "lib" / "cut_proposals_norm.py"


def _fake(doc: str) -> list:
    """A stand-in scanner that prints `doc` and exits 0."""
    return [sys.executable, "-c", f"print({doc!r})"]


CLEAN = '{"hits": [], "files": 3, "unreadable": [], "name_only": 0, "git": {"repos": 0, "commits": 0, "refs": 0, ' \
        '"tags": 0}, "archives": {"archives": 0, "members": 0}}'


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _snapshot(root: Path) -> list:
    return sorted((p.relative_to(root).as_posix(), p.stat().st_size if p.is_file() else -1) for p in root.rglob("*"))


class KeyMixin:
    def make_key_and_hashes(self, tmp: Path, plain: str = PLAIN):
        secret = tmp / "secret"
        secret.mkdir()
        (secret / "plain.txt").write_text(plain, encoding="utf-8")
        self.key = secret / "test.key"
        ids.make_key(self.key, repo_root=ROOT)
        self.hashes = tmp / "hashes.json"
        ids.make_hashes(secret / "plain.txt", self.key, self.hashes, repo_root=ROOT)

    def with_key(self):
        return mock.patch.dict(os.environ, {**NO_KEY_ENV, ids.KEY_ENV: str(self.key)}, clear=True)

    def without_key(self):
        return mock.patch.dict(os.environ, NO_KEY_ENV, clear=True)


class GateFixture(KeyMixin, unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.make_key_and_hashes(self.tmp)
        self.tree = self.tmp / "tree"
        (self.tree / "docs").mkdir(parents=True)
        (self.tree / "docs" / "ok.md").write_text("A clean page about captions.\n", encoding="utf-8")
        self.lines = []

    def gate(self, require_key, root=None):
        return rel.identity_gate(root or self.tree, require_key=require_key, log=self.lines.append, hashes=self.hashes)

    def refused(self, root=None, require_key=True) -> str:
        with self.with_key(), self.assertRaises(rel.HandoffError) as cm:
            self.gate(require_key=require_key, root=root)
        msg = str(cm.exception)
        self.assertNotIn("vexilor", msg.lower())                    # the scan's output is redacted
        self.assertNotIn("zorblax", msg.lower())
        return msg

    def git_repo(self, files: dict, msg="first", name="g") -> Path:
        repo = self.tmp / name
        repo.mkdir()
        trh.git(repo, "init", "-q", "-b", "main")
        self.commit(repo, files, msg)
        return repo

    def commit(self, repo: Path, files: dict, msg: str) -> str:
        for rel_path, text in files.items():
            p = repo / rel_path
            if text is None:
                trh.git(repo, "rm", "-q", rel_path)
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(text.encode("utf-8"))
        trh.git(repo, "add", "-A")
        trh.git(repo, "commit", "-q", "--allow-empty", "-m", msg)
        return trh.git(repo, "rev-parse", "HEAD")


class TestIdentityGate(GateFixture):
    def test_a_planted_token_stops_the_handoff(self):
        (self.tree / "docs" / "leak.md").write_text("Made like Vexilor does it.\n", encoding="utf-8")
        msg = self.refused()
        self.assertIn("identity scan (tree): exit 1", msg)
        self.assertIn("docs/leak.md", msg)
        with self.with_key(), self.assertRaises(rel.HandoffError):    # a PREVIEW with a key is just as hard
            self.gate(require_key=False)

    def test_a_planted_token_in_a_file_name_stops_it(self):
        (self.tree / "docs" / "vexilor-notes.md").write_text("nothing here\n", encoding="utf-8")
        self.refused()

    def test_a_clean_tree_passes_and_says_so(self):
        with self.with_key():
            line = self.gate(require_key=True)
        self.assertIn("identity scan (tree): 0 findings in", line)
        self.assertEqual(self.lines[-1], line)

    def test_a_release_without_a_key_is_refused(self):
        with self.without_key(), self.assertRaises(rel.HandoffError) as cm:
            self.gate(require_key=True)
        self.assertIn("exit 2", str(cm.exception))
        self.assertIn("no key", str(cm.exception))

    def test_a_preview_without_a_key_is_logged_as_skipped(self):
        (self.tree / "docs" / "leak.md").write_text("Vexilor\n", encoding="utf-8")
        with self.without_key():
            line = self.gate(require_key=False)
        self.assertIn("skipped, no key", line)

    def test_unreadable_scan_output_is_an_error_not_a_pass(self):
        fake = [sys.executable, "-c", "print('not json')"]
        with self.assertRaises(rel.HandoffError) as cm:
            rel.identity_gate(self.tree, require_key=False, log=self.lines.append, cmd=fake)
        self.assertIn("unreadable output", str(cm.exception))

    # ---- G13: name-only files are counted in the log line
    def test_name_only_files_are_counted(self):
        (self.tree / "docs" / "pic.png").write_bytes(b"\x89PNG\x00\x01\x02 Vexilor\x00")
        with self.with_key():
            line = self.gate(require_key=True)
        self.assertRegex(line, r"\b1 name-only\b")

    # ---- G14 / G15: unreadable files with a key in use
    def test_unreadable_files_with_a_key_stop_a_preview(self):
        doc = CLEAN.replace('"unreadable": []', '"unreadable": ["docs/a.md", "docs/<name:abc>"]')
        with self.assertRaises(rel.HandoffError) as cm:
            rel.identity_gate(self.tree, require_key=False, log=self.lines.append, cmd=_fake(doc))
        self.assertIn("2 path(s) could not be read", str(cm.exception))
        self.assertIn("docs/a.md", str(cm.exception))

    def test_a_preview_without_a_key_still_just_skips(self):
        doc = '{"skipped": "no key", "hits": [], "files": 0}'
        line = rel.identity_gate(self.tree, require_key=False, log=self.lines.append, cmd=_fake(doc))
        self.assertIn("skipped, no key", line)

    # ---- G16 / G17: exit 0 must also mean no hits in a well-formed report
    def test_exit_0_with_hits_is_refused(self):
        doc = CLEAN.replace('"hits": []', '"hits": [{"path": "x.md", "line": 1, "hash": "abc"}]')
        with self.assertRaises(rel.HandoffError) as cm:
            rel.identity_gate(self.tree, require_key=False, log=self.lines.append, cmd=_fake(doc))
        self.assertIn("1 finding", str(cm.exception))

    def test_exit_0_without_a_hits_list_is_refused(self):
        for doc in ('[]', '{"files": 1}', CLEAN.replace(', "git": {"repos": 0, "commits": 0, "refs": 0, "tags": 0}',
                                                         '')):
            with self.subTest(doc=doc[:30]), self.assertRaises(rel.HandoffError):
                rel.identity_gate(self.tree, require_key=False, log=self.lines.append, cmd=_fake(doc))

    # ---- G18: a hung scan
    def test_a_hung_identity_scan_is_refused(self):
        hang = [sys.executable, "-c", "import time; time.sleep(60)"]
        with mock.patch.object(rel, "SCAN_TIMEOUT", 2), self.assertRaises(rel.HandoffError) as cm:
            rel.identity_gate(self.tree, require_key=False, log=self.lines.append, cmd=hang)
        self.assertIn("timed out", str(cm.exception))

    # ---- G20: the scanner given is the one that runs; its sha256 is logged
    def test_the_given_scanner_runs_and_its_sha_is_logged(self):
        stub = self.tmp / "stub_scan.py"
        stub.write_text(f"print({CLEAN!r})\n", encoding="utf-8")
        line = rel.identity_gate(self.tree, require_key=False, log=self.lines.append, scanner=stub)
        self.assertIn("0 findings in 3 paths", line)
        self.assertTrue(any(_sha(stub) in ln for ln in self.lines), self.lines)

    # ---- re-review P3-a: a killed scan leaves no history text in TEMP
    def test_a_timeout_leaves_no_temp_files(self):
        base = Path(tempfile.gettempdir())
        probe = f"wnc-probe-{os.getpid()}-{id(self)}"
        code = ("import os, tempfile, time; d = tempfile.mkdtemp(prefix='wnc-idscan-'); "
                f"open(os.path.join(d, {probe!r}), 'w').write('history text'); time.sleep(60)")
        with mock.patch.object(rel, "SCAN_TIMEOUT", 3), self.assertRaises(rel.HandoffError) as cm:
            rel.identity_gate(self.tree, require_key=False, log=self.lines.append, cmd=[sys.executable, "-c", code])
        self.assertIn("timed out", str(cm.exception))
        left = list(base.glob(f"*/{probe}")) + list(base.glob(f"*/*/{probe}"))
        self.assertEqual(left, [])

    # ---- re-review P3-b: the hash file and the normaliser the scan used are logged
    def test_the_hash_file_and_normaliser_are_logged(self):
        import json
        with self.with_key():
            self.gate(require_key=True)
        n = len(json.loads(self.hashes.read_text(encoding="utf-8"))["tokens"])
        log = "\n".join(self.lines)
        self.assertIn(f"{self.hashes.name} sha256 {_sha(self.hashes)}, {n} tokens", log)
        self.assertIn(f"normaliser sha256 {_sha(NORM)}", log)

    # ---- re-review P3-c: the JSON report is one ASCII line (U+2028 / NEL in a path cannot split it)
    def test_the_json_report_is_one_ascii_line(self):
        import json
        import subprocess
        (self.tree / "docs" / "a b\u0085c.md").write_text("Made like Vexilor\n", encoding="utf-8")
        with self.with_key():
            r = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "identity_scan.py"), "scan", "--json",
                                "--root", str(self.tree), "--hashes", str(self.hashes)],
                               capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertTrue(r.stdout.isascii())
        lines = r.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(len(json.loads(lines[0])["hits"]), 1)

    def test_a_release_whose_commit_has_no_scanner_is_refused(self):
        with self.with_key(), self.assertRaises(rel.HandoffError) as cm:
            rel.identity_gate(self.tree, require_key=True, log=self.lines.append, hashes=self.hashes,
                              scanner=self.tmp / "missing" / "identity_scan.py")
        self.assertIn("identity_scan.py", str(cm.exception))


class TestGitHistory(GateFixture):
    """G1-G8: the clone ships its full history; the gate scans it too."""

    def test_a_token_only_in_an_earlier_commit_is_refused(self):
        repo = self.git_repo({"docs/ok.md": "clean\n", "docs/old.md": "Made like Vexilor does it.\n"})
        bad = trh.git(repo, "rev-parse", "HEAD")
        self.commit(repo, {"docs/old.md": None}, "drop the page")
        msg = self.refused(repo)
        self.assertIn("@git:" + bad[:12], msg)

    def test_a_token_only_in_a_commit_message_is_refused(self):
        repo = self.git_repo({"docs/ok.md": "clean\n"})
        bad = self.commit(repo, {"docs/two.md": "clean too\n"}, "ported the Zorblax Quentaro way")
        msg = self.refused(repo)
        self.assertIn("@git:" + bad[:12], msg)
        self.assertIn("(message)", msg)

    def test_a_file_name_only_in_history_is_refused(self):
        repo = self.git_repo({"docs/vexilor-notes.md": "clean\n"})
        trh.git(repo, "mv", "docs/vexilor-notes.md", "docs/notes.md")
        self.commit(repo, {}, "rename")
        self.refused(repo)

    def test_a_tag_name_is_refused(self):
        repo = self.git_repo({"docs/ok.md": "clean\n"})
        trh.git(repo, "tag", "vexilor-1.0")
        self.assertIn("@git:ref", self.refused(repo))

    def test_an_annotated_tag_message_is_refused(self):
        repo = self.git_repo({"docs/ok.md": "clean\n"})
        trh.git(repo, "tag", "-a", "v1.0", "-m", "the Vexilor drop")
        self.assertIn("@git:tag", self.refused(repo))

    def test_a_branch_name_is_refused(self):
        repo = self.git_repo({"docs/ok.md": "clean\n"})
        trh.git(repo, "branch", "feature/vexilor")
        self.refused(repo)

    def test_git_metadata_text_is_scanned(self):
        repo = self.git_repo({"docs/ok.md": "clean\n"})
        (repo / ".git" / "description").write_text("Vexilor mirror\n", encoding="utf-8")
        self.assertIn(".git/description", self.refused(repo))

    def test_a_clean_repo_passes_and_counts_its_history(self):
        repo = self.git_repo({"docs/ok.md": "clean\n"})
        self.commit(repo, {"docs/two.md": "clean too\n"}, "second")
        before = _snapshot(repo)
        with self.with_key():
            line = self.gate(require_key=True, root=repo)
        self.assertRegex(line, r"git history: 2 commit\(s\)")
        self.assertEqual(_snapshot(repo), before)                    # G21: nothing written into the tree

    # ---- re-review P2-b: history text the old pass dropped as "name-only"
    def test_a_nul_text_diff_in_history_is_scanned(self):
        repo = self.git_repo({".gitattributes": "*.dat diff\n", "docs/ok.md": "clean\n"})
        (repo / "docs" / "x.dat").write_bytes(b"head\x00\nMade like Vexilor\n\x00tail\n")
        bad = self.commit(repo, {}, "add the data")
        self.commit(repo, {"docs/x.dat": None}, "drop it")
        self.assertIn("@git:" + bad[:12], self.refused(repo))

    def test_a_huge_single_line_in_history_is_scanned(self):
        repo = self.git_repo({"docs/ok.md": "clean\n"})
        bad = self.commit(repo, {"docs/big.txt": "filler " * 3_100_000 + "Made like Vexilor\n"}, "big")
        self.commit(repo, {"docs/big.txt": None}, "drop it")
        self.assertIn("@git:" + bad[:12], self.refused(repo))

    def test_a_binary_zip_only_in_history_is_opened(self):
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("index.html", "Made like Vexilor")
        repo = self.git_repo({".gitattributes": "*.zip binary\n", "docs/ok.md": "clean\n"})
        (repo / "docs" / "a.zip").write_bytes(buf.getvalue())
        bad = self.commit(repo, {}, "add the zip")
        self.commit(repo, {"docs/a.zip": None}, "drop it")
        msg = self.refused(repo)
        self.assertIn("@git:" + bad[:12] + ":docs/a.zip!index.html", msg)

    def test_a_no_diff_text_file_only_in_history_is_scanned(self):
        repo = self.git_repo({".gitattributes": "*.md -diff\n", "docs/ok.md": "clean\n"})
        bad = self.commit(repo, {"docs/secret.md": "Made like Vexilor\n"}, "add")
        self.commit(repo, {"docs/secret.md": None}, "drop it")
        self.assertIn("@git:" + bad[:12] + ":docs/secret.md", self.refused(repo))

    def test_a_nested_clone_is_found(self):
        outer = self.tmp / "outer"
        (outer / "Mac").mkdir(parents=True)
        (outer / "LABEL.txt").write_text("label: x\n", encoding="utf-8")
        self.git_repo({"docs/old.md": "Vexilor\n"}, name="outer/Mac/repo")
        self.commit(outer / "Mac" / "repo", {"docs/old.md": None}, "drop")
        self.assertIn("Mac/repo@git:", self.refused(outer))


class TestArchives(GateFixture):
    """G9-G12: .zip / .ccx / .zxp members are extracted outside the tree and scanned."""

    def test_a_token_in_a_ccx_member_is_refused(self):
        trh.make_zip(self.tree / "Windows" / "Panel.ccx", {"manifest.json": "{}",
                                                          "html/index.html": "<p>Made like Vexilor</p>"})
        before = _snapshot(self.tree)
        self.assertIn("Windows/Panel.ccx!html/index.html", self.refused())
        self.assertEqual(_snapshot(self.tree), before)               # G21: members never land in the tree

    def test_a_token_in_a_member_name_is_refused(self):
        trh.make_zip(self.tree / "Windows" / "Bridge.zxp", {"js/vexilor.js": "// clean\n"})
        self.assertIn("Windows/Bridge.zxp!", self.refused())

    def test_a_nested_archive_is_scanned(self):
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("index.html", "Zorblax Quentaro inside")
        trh.make_zip(self.tree / "Windows" / "plugin.zip", {"m/adobe/Panel.ccx": buf.getvalue(), "m/ok.md": "ok"})
        self.assertIn("Windows/plugin.zip!m/adobe/Panel.ccx!index.html", self.refused())

    def test_a_big_nested_archive_is_opened(self):                  # re-review P2-a: > 20 MB inside a zip
        import io
        import zipfile
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w", zipfile.ZIP_STORED) as z:
            z.writestr("pad.bin", b"\0" * 21_000_000)
            z.writestr("index.html", "Made like Vexilor")
        (self.tree / "Windows").mkdir()
        with zipfile.ZipFile(self.tree / "Windows" / "plugin.zip", "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("m/Panel.ccx", inner.getvalue())
        self.assertIn("Windows/plugin.zip!m/Panel.ccx!index.html", self.refused())

    def test_a_corrupt_archive_with_a_key_is_refused(self):
        (self.tree / "Windows").mkdir()
        (self.tree / "Windows" / "Panel.ccx").write_bytes(b"PK\x03\x04 not really a zip")
        self.assertIn("Windows/Panel.ccx", self.refused())                      # a release: the scan exits 2
        self.assertIn("could not be read", self.refused(require_key=False))      # a PREVIEW with a key: refused too

    def test_a_clean_archive_passes_and_is_counted(self):
        trh.make_zip(self.tree / "Windows" / "Panel.ccx", {"manifest.json": "{}", "html/index.html": "<p>ok</p>"})
        with self.with_key():
            line = self.gate(require_key=True)
        self.assertRegex(line, r"2 archive member\(s\) in 1 archive\(s\)")


class TestSecretReport(GateFixture):
    def test_findings_are_counted_never_raised(self):
        (self.tree / "notes.md").write_text("see C:\\Users\\someone\\Desktop\\x.txt\n", encoding="utf-8")
        with self.without_key():
            n = rel.secret_report(self.tree, log=self.lines.append)
        self.assertGreaterEqual(n, 1)
        self.assertIn("report-only", self.lines[-1])

    def test_a_broken_scan_is_reported_not_raised(self):
        n = rel.secret_report(self.tree, log=self.lines.append, cmd=[sys.executable, "-c", "import sys; sys.exit(3)"])
        self.assertEqual(n, -1)
        self.assertIn("could not run", self.lines[-1])

    def test_a_hung_scan_is_reported_not_raised(self):            # G19
        hang = [sys.executable, "-c", "import time; time.sleep(60)"]
        with mock.patch.object(rel, "SCAN_TIMEOUT", 2):
            n = rel.secret_report(self.tree, log=self.lines.append, cmd=hang)
        self.assertEqual(n, -1)
        self.assertIn("timed out", self.lines[-1])


@unittest.skipUnless(trh.GIT, "git not on PATH")
class TestHandoffRunsTheGate(trh.HandoffCase):
    def test_a_gate_failure_swaps_nothing_in(self):
        repo = trh.make_repo(self.tmp / "src")
        with mock.patch.object(rel, "identity_gate", side_effect=rel.HandoffError("identity scan (repo): exit 1: x")), \
                self.assertRaises(rel.HandoffError):
            self.run_handoff(repo)
        self.assertFalse(self.out.exists())
        self.assertFalse(self.out.with_name(self.out.name + ".new").exists())

    def test_the_assembled_folder_is_scanned_once_with_the_clones_scanner(self):   # H7
        repo = trh.make_repo(self.tmp / "src")
        seen = []

        def spy(root, require_key, log=None, **kw):
            root = Path(root)
            seen.append((root.name, require_key, kw.get("scanner")))
            names = {p.name for p in root.rglob("*")}
            for must in ("LABEL.txt", "WHAT-WORKS-NOW-AR.md", "README-AR.md", "checksums.txt", "START-HERE.md",
                         "whynot-cut-9.9.9.zip"):
                self.assertIn(must, names)                       # every generated file is there when it runs
            self.assertFalse((root / ".stage").exists())
            return "ok"
        with mock.patch.object(rel, "identity_gate", side_effect=spy), \
                mock.patch.object(rel, "secret_report", return_value=0):
            summary = self.run_handoff(repo)
        new = self.out.with_name(self.out.name + ".new")
        self.assertEqual(seen, [(new.name, False, new / "Mac" / "repo" / "tools" / "identity_scan.py")])
        self.assertEqual(summary["secret_findings"], {"repo": 0, ".stage": 0})


@unittest.skipUnless(trh.GIT, "git not on PATH")
class TestRealGateInTheHandoff(KeyMixin, trh.HandoffCase):
    """H1-H6: no mock of the gate. A non-PREVIEW hand-off with a test key file; the fake repo commits its own
    tools/identity_scan.py, the normaliser and tools/identity_hashes.json (the test hashes), so the clone's scanner and
    the clone's hash file are what judge the release."""

    def setUp(self):
        super().setUp()
        self.make_key_and_hashes(self.tmp, PLAIN_HANDOFF)
        self.lines = []

    def gate_repo(self, extra=None) -> Path:
        tracked = {"tools/identity_scan.py": (ROOT / "tools" / "identity_scan.py").read_text(encoding="utf-8"),
                   "tools/identity_hashes.json": self.hashes.read_text(encoding="utf-8"),
                   "whynot-cut/engine/reel/lib/cut_proposals_norm.py": NORM.read_text(encoding="utf-8")}
        return trh.make_repo(self.tmp / "src", extra_tracked={**tracked, **(extra or {})})

    def release(self, repo, label="9.9.9"):
        with self.with_key():
            return self.run_handoff(repo, label=label, preview=False, log=lambda *a, **k: self.lines.append(
                " ".join(map(str, a))))

    def refused(self, repo, label="9.9.9") -> str:
        with self.assertRaises(rel.HandoffError) as cm:
            self.release(repo, label)
        self.assertFalse(self.out.exists())
        self.assertFalse(self.out.with_name(self.out.name + ".new").exists())
        msg = str(cm.exception)
        self.assertIn("exit 1", msg)
        self.assertNotIn("zorblax", msg.lower())                      # redacted
        self.assertNotIn("quentaro", msg.lower())
        return msg

    def test_h1_a_working_tree_token_is_refused(self):
        repo = self.gate_repo({"docs/notes.md": "Made the Zorblax Quentaro way.\n"})
        self.assertIn("Mac/repo/docs/notes.md", self.refused(repo))

    def test_h2_a_token_only_in_history_is_refused(self):
        repo = self.gate_repo({"docs/old.md": "Made the Zorblax Quentaro way.\n"})
        bad = trh.git(repo, "rev-parse", "HEAD")
        trh.git(repo, "rm", "-q", "docs/old.md")
        trh.git(repo, "commit", "-q", "-m", "drop the page")
        self.assertIn("Mac/repo@git:" + bad[:12], self.refused(repo))

    def test_h3_a_token_only_in_a_generated_file_is_refused(self):
        repo = self.gate_repo()
        self.assertIn("LABEL.txt", self.refused(repo, label="Zorblax-Quentaro-9.9.9"))

    def test_h4_a_token_inside_a_ccx_member_is_refused(self):
        repo = self.gate_repo()
        trh.make_zip(repo / "whynot-cut/adobe/WhyNotCut-Premiere-9.9.9.ccx",
                     {"manifest.json": "{}", "html/index.html": "<p>Made the Zorblax Quentaro way</p>"})
        self.assertIn("Windows/WhyNotCut-Premiere-9.9.9.ccx!html/index.html", self.refused(repo))

    def test_h5_a_clean_release_passes_with_the_clones_scanner(self):
        repo = self.gate_repo()
        summary = self.release(repo)
        self.assertTrue((self.out / "LABEL.txt").is_file())
        self.assertFalse(summary["preview"])
        log = "\n".join(self.lines)
        self.assertIn(_sha(repo / "tools" / "identity_scan.py"), log)
        self.assertRegex(log, r"identity scan \(Final Out\.new\): 0 findings in \d+ paths; git history: 3 commit")

    def test_h6_the_clones_scanner_is_the_one_that_runs(self):
        repo = self.gate_repo({"tools/identity_scan.py": "import sys\nprint('stub scanner ran', file=sys.stderr)\n"
                                                          "sys.exit(2)\n"})
        with self.assertRaises(rel.HandoffError) as cm:
            self.release(repo)
        self.assertIn("stub scanner ran", str(cm.exception))
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
