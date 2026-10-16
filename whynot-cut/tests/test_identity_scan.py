# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 19 (R-T6, Addendum H R5.4): the identity scan `tools/identity_scan.py`.

Spec: docs/superpowers/specs/addendum-h/source-r-specs/R-9-qa-identity-rtl-matrix-distinctiveness.md (R-9.1).
The repo holds only keyed hashes (HMAC-SHA256, key outside the repo) of normalised tokens; the plain list and the key
live outside the repo. Every test here uses its OWN fictional tokens and its own test key in a temp folder; no real
token, plain list or key is ever read, written or printed by these tests (the real-tree test only reads the real key
when the owner's machine provides WNC_IDENTITY_KEY_FILE, and skips otherwise).
Run:  tools/test.sh -p test_identity_scan.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "identity_scan.py"
sys.path.insert(0, str(ROOT / "tools"))

import identity_scan as ids  # noqa: E402

# Fictional tokens only (made up for this test; they name nobody).
PLAIN = "\n".join([
    "# test list",
    "Zorblax Quentaro",
    "زوربلاكس كوينتارو",
    "شركة فلانتو",
    "qwmx-vexil.example",
    "Vexilor",
    "فلانتور",
    "الفلانكو",
    "دار الزوربو",
    "QuinVorge",
    "İzvexa",
    "سامو",
    "",
])
WORDS = ("zorblax", "quentaro", "زوربلاكس", "كوينتارو", "فلانتو", "qwmx", "vexil", "vexilor", "فلانتور", "فلانكو",
         "زوربو", "quinvorge", "zvexa", "سامو")
NAME_RX = r"<name:[0-9a-f]{12}>"


def run_cli(*args, env=None):
    e = dict(os.environ)
    e.pop("WNC_IDENTITY_KEY_FILE", None)
    e.pop("WNC_IDENTITY_KEY", None)          # a CI secret in the parent must not leak into these child runs
    if env:
        e.update(env)
    p = subprocess.run([sys.executable, "-I", str(TOOL), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=e, timeout=120)
    return p.returncode, p.stdout + p.stderr


class Fixture(unittest.TestCase):
    """A temp folder outside the repo: `secret/` holds the plain list and the key, `tree/` is the scanned tree."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.secret = self.tmp / "secret"
        self.secret.mkdir()
        self.tree = self.tmp / "tree"
        self.tree.mkdir()
        self.plain = self.secret / "plain.txt"
        self.plain.write_text(PLAIN, encoding="utf-8")
        self.key = self.secret / "test.key"
        ids.make_key(self.key, repo_root=ROOT)
        self.hashes = self.tmp / "hashes.json"
        ids.make_hashes(self.plain, self.key, self.hashes, repo_root=ROOT)
        self.db = ids.load_db(self.hashes)
        self.k = ids.read_key(self.key)

    def put(self, rel, text, encoding="utf-8"):
        f = self.tree / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding=encoding) if isinstance(text, str) else f.write_bytes(text)
        return f

    def hits(self):
        return ids.scan(self.tree, self.db, self.k)


class TestNormalise(unittest.TestCase):
    def test_case_nfkc_and_joiners_fold(self):
        self.assertEqual(ids.normalize("ZORBLAX-Quentaro"), ["zorblax", "quentaro"])
        self.assertEqual(ids.normalize("zorblax_quentaro.md"), ["zorblax", "quentaro", "md"])
        self.assertEqual(ids.normalize("ｚｏｒｂｌａｘ"), ["zorblax"])          # NFKC: full-width letters

    def test_arabic_variants_unified(self):
        self.assertEqual(ids.normalize("أَحْمَد"), ids.normalize("احمد"))     # harakat dropped, alef unified
        self.assertEqual(ids.normalize("إسلام آمن"), ["اسلام", "امن"])
        self.assertEqual(ids.normalize("مدرسة"), ids.normalize("مدرسه"))       # ta marbuta
        self.assertEqual(ids.normalize("على"), ids.normalize("علي"))           # alef maqsura
        self.assertEqual(ids.normalize("كــتاب"), ids.normalize("كتاب"))       # tatweel

    def test_format_characters_removed_not_split(self):
        self.assertEqual(ids.normalize("زو\u200fرب"), ["زورب"])
        self.assertEqual(ids.normalize("zor\u200bblax"), ["zorblax"])

    def test_hard_punctuation_splits_segments(self):
        self.assertEqual(ids.segments("Zorblax, Quentaro"), [["zorblax"], ["quentaro"]])
        self.assertEqual(ids.segments("end. Next"), [["end"], ["next"]])
        self.assertEqual(ids.segments("a.b.c"), [["a", "b", "c"]])           # a dot inside a word is a joiner
        self.assertEqual(ids.segments("«زوربلاكس» كوينتارو"), [["زوربلاكس"], ["كوينتارو"]])
        self.assertEqual(ids.segments("one - two"), [["one"], ["two"]])


class TestScan(Fixture):
    def test_planted_token_in_text_fails_with_line_number(self):
        self.put("notes/a.md", "line one\nline two\nsee Zorblax Quentaro here\n")
        h = self.hits()
        self.assertEqual([(x.path, x.line) for x in h], [("notes/a.md", 3)])

    def test_case_joiner_and_joined_forms_match(self):
        self.put("a.txt", "ZORBLAX-quentaro\nzorblax_quentaro\nZorblaxQuentaro\nqwmx-vexil.example\n")
        self.assertEqual(sorted(x.line for x in self.hits()), [1, 2, 3, 4])

    def test_arabic_variant_and_ta_marbuta_match(self):
        self.put("ar.md", "زوربلأكس كوينتارو\nشركه فلانتو\nزوربلاكس\u200f كوينتارو\n")
        self.assertEqual(sorted(x.line for x in self.hits()), [1, 2, 3])

    def test_comma_between_words_does_not_match(self):
        self.put("a.txt", "Zorblax, Quentaro\nزوربلاكس، كوينتارو\nquentaro zorblax\n")
        self.assertEqual(self.hits(), [])

    def test_partial_token_does_not_match(self):
        self.put("a.txt", "Zorblax alone\nQuentaro alone\nfلانتو\n")
        self.assertEqual(self.hits(), [])

    def test_token_in_file_or_folder_name_fails(self):
        self.put("docs/zorblax-quentaro/readme.md", "clean\n")
        self.put("x/ZorblaxQuentaro.png", b"\x89PNG\x00")
        h = sorted(self.hits(), key=lambda x: x.path)
        self.assertEqual([x.line for x in h], [0, 0])                   # each name reported once
        self.assertRegex(h[0].path, "^docs/" + NAME_RX + "$")            # the token never shows in the report
        self.assertRegex(h[1].path, "^x/" + NAME_RX + "$")

    def test_binary_content_is_skipped(self):
        self.put("blob.bin", b"\x00\x01Zorblax Quentaro\x00")
        self.assertEqual(self.hits(), [])

    def test_utf16_text_with_bom_is_read(self):
        self.put("u16.txt", "\ufeffhello Zorblax Quentaro\n", encoding="utf-16-le")
        self.assertEqual([x.line for x in self.hits()], [1])

    def test_links_are_not_followed(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "leak.md").write_text("Zorblax Quentaro\n", encoding="utf-8")
        link = self.tree / "linked"
        try:
            if os.name == "nt":
                r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
                if r.returncode != 0:
                    self.skipTest("could not create a junction")
            else:
                os.symlink(outside, link, target_is_directory=True)
            self.assertEqual(self.hits(), [])
        finally:
            if os.path.lexists(link):
                os.rmdir(link) if os.name == "nt" else os.unlink(link)

    def test_clean_tree_passes(self):
        self.put("a.md", "WhyNot Cut — our own words only.\nقص فيديو بالعربي\n")
        self.assertEqual(self.hits(), [])


class TestHardening(Fixture):
    """Code-review findings of 2026-10-16 (Task 19 round 1)."""

    def cli_scan(self, *extra, root=None):
        return run_cli("scan", "--root", str(root or self.tree), "--hashes", str(self.hashes), "--key-file",
                       str(self.key), *extra)

    def test_bad_root_fails_instead_of_passing(self):
        self.assertEqual(self.cli_scan(root=self.tmp / "missing")[0], 2)
        f = self.put("a.txt", "clean\n")
        self.assertEqual(self.cli_scan(root=f)[0], 2)                   # a file (e.g. a zip): extract it first
        empty = self.tmp / "empty"
        empty.mkdir()
        self.assertEqual(self.cli_scan(root=empty)[0], 2)               # nothing to scan is not "clean"
        self.assertEqual(run_cli("secrets", "--root", str(self.tmp / "missing"))[0], 2)

    def test_path_hits_are_redacted_in_every_report(self):
        self.put("docs/Zorblax Quentaro/readme.md", "Vexilor here\n")
        code, out = self.cli_scan()
        self.assertEqual(code, 1, out)
        for w in WORDS:
            self.assertNotIn(w, out.casefold())
        code, out = self.cli_scan("--json")
        doc = json.loads(out)
        self.assertTrue(doc["hits"])
        for h in doc["hits"]:
            self.assertRegex(h["path"], "^docs/" + NAME_RX)
        self.assertNotIn("zorblax", out.casefold())

    def test_token_across_path_parts_found_and_redacted(self):
        self.put("zorblax/quentaro.md", "clean\n")
        h = self.hits()
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0].line, 0)
        self.assertNotIn("zorblax", h[0].path.casefold())
        self.assertNotIn("quentaro", h[0].path.casefold())

    def test_token_wrapped_across_two_lines(self):
        self.put("a.md", "see Zorblax\nQuentaro here\n")
        self.assertEqual([x.line for x in self.hits()], [2])

    def test_wrap_stops_at_hard_punctuation_and_blank_lines(self):
        self.put("a.md", "end Zorblax.\nQuentaro\n\nZorblax\n\nQuentaro\nVexilor\nVexilor\n")
        self.assertEqual([x.line for x in self.hits()], [7, 8])        # only the two single-word hits

    def test_glued_forms_match(self):
        self.put("a.ts", "class VexilorScene {}\nvexilor2\nZorblaxQuentaroStudio\n")
        self.put("ar.md", "والفلانتور\nبفلانتور\nلفلانتور\nبالفلانتور\n")
        self.assertEqual(sorted((x.path, x.line) for x in self.hits()),
                         [("a.ts", 1), ("a.ts", 2), ("a.ts", 3), ("ar.md", 1), ("ar.md", 2), ("ar.md", 3),
                          ("ar.md", 4)])

    def test_escaped_text_matches(self):
        self.put("a.json", json.dumps({"t": "زوربلاكس كوينتارو"}) + "\n")   # \\uXXXX escapes (ensure_ascii)
        self.put("b.html", "<p>Zorblax&nbsp;Quentaro &#86;exilor</p>\n")
        self.put("c.txt", "https://example.com/?q=Zorblax%20Quentaro\n")
        self.assertEqual(sorted((x.path, x.line) for x in self.hits()), [("a.json", 1), ("b.html", 1), ("c.txt", 1)])

    def test_unreadable_files_are_reported_and_fail_the_gate(self):
        from unittest import mock
        self.put("ok.md", "clean\n")
        bad = self.put("locked.md", "x\n")
        real = ids._read_bytes

        def fake(path):
            if Path(path) == bad:
                raise PermissionError("locked")
            return real(path)
        with mock.patch.object(ids, "_read_bytes", fake):
            report = {}
            self.assertEqual(ids.scan(self.tree, self.db, self.k, report=report), [])
            self.assertEqual(report["unreadable"], ["locked.md"])
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(ids.main(["scan", "--root", str(self.tree), "--hashes", str(self.hashes),
                                           "--key-file", str(self.key)]), 0)
                self.assertEqual(ids.main(["scan", "--root", str(self.tree), "--hashes", str(self.hashes),
                                           "--key-file", str(self.key), "--require-key"]), 2)

    def test_oversized_file_name_still_scanned_content_skipped(self):
        from unittest import mock
        self.put("Vexilor.log", "Zorblax Quentaro\n" * 10)
        with mock.patch.object(ids, "MAX_BYTES", 16):
            h = self.hits()
        self.assertEqual([x.line for x in h], [0])

    def test_line_numbers_follow_newlines_only(self):
        self.put("a.txt", "a\fb\u2028c\nZorblax Quentaro\n")
        self.assertEqual([x.line for x in self.hits()], [2])

    def test_arabic_question_mark_quranic_marks_and_persian_letters(self):
        self.assertEqual(ids.segments("زوربلاكس؟ كوينتارو"), [["زوربلاكس"], ["كوينتارو"]])
        self.assertEqual(ids.normalize("زوربلا\u06e1كس"), ["زوربلاكس"])
        self.assertEqual(ids.normalize("زوربلاکس"), ["زوربلاكس"])         # Persian kaf
        self.assertEqual(ids.normalize("کوینتارو"), ["كوينتارو"])         # Persian kaf + yeh

    def test_git_mode_lists_tracked_files_and_folders_not_ignored_ones(self):
        repo = self.tmp / "gitrepo"
        repo.mkdir()
        if subprocess.run(["git", "init", "-q", str(repo)], capture_output=True).returncode != 0:
            self.skipTest("git not available")
        (repo / ".gitignore").write_text("ignored/\n", encoding="utf-8")
        (repo / "ignored").mkdir()
        (repo / "ignored" / "x.md").write_text("Zorblax Quentaro\n", encoding="utf-8")
        (repo / "Vexilor").mkdir()
        (repo / "Vexilor" / "a.md").write_text("clean\n", encoding="utf-8")
        files = ids.repo_files(repo)
        self.assertIn("Vexilor", files)
        self.assertIn("Vexilor/a.md", files)
        self.assertNotIn("ignored/x.md", files)
        h = ids.scan(repo, self.db, self.k)
        self.assertEqual([x.line for x in h], [0])

    def test_normaliser_version_mismatch_refuses(self):
        doc = json.loads(self.hashes.read_text(encoding="utf-8"))
        self.assertEqual(doc["norm_version"], ids._norm.NORM_VERSION)
        doc["norm_version"] = ids._norm.NORM_VERSION + 1
        self.hashes.write_text(json.dumps(doc), encoding="utf-8")
        self.put("a.md", "x\n")
        with self.assertRaises(ids.ScanError) as cm:
            ids.scan(self.tree, ids.load_db(self.hashes), self.k)
        self.assertIn("regenerate", str(cm.exception))

    def test_corrupt_hash_file_is_a_usage_error(self):
        bad = self.tmp / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ids.ScanError):
            ids.load_db(bad)
        bad.write_text(json.dumps({"format": 1, "mode": "keyed"}), encoding="utf-8")
        with self.assertRaises(ids.ScanError):
            ids.load_db(bad)
        self.put("a.md", "x\n")
        code, out = run_cli("scan", "--root", str(self.tree), "--hashes", str(bad), "--key-file", str(self.key))
        self.assertEqual(code, 2, out)

    def test_unexpected_error_exits_2_not_1(self):
        from unittest import mock
        self.put("a.md", "x\n")
        with mock.patch.object(ids, "scan", side_effect=RuntimeError("boom")):
            self.assertEqual(ids.main(["scan", "--root", str(self.tree), "--hashes", str(self.hashes),
                                       "--key-file", str(self.key)]), 2)

    def test_hex_key_from_environment(self):
        self.put("a.md", "Zorblax Quentaro\n")
        hexkey = self.key.read_text(encoding="ascii").strip()
        code, out = run_cli("scan", "--root", str(self.tree), "--hashes", str(self.hashes),
                            env={"WNC_IDENTITY_KEY": hexkey})
        self.assertEqual(code, 1, out)
        code, out = run_cli("scan", "--root", str(self.tree), "--hashes", str(self.hashes),
                            env={"WNC_IDENTITY_KEY": "abcd"})
        self.assertEqual(code, 2, out)                                  # too short to be a key

    def test_inside_repo_check_ignores_case_where_the_disk_does(self):
        fake = self.tmp / "CaseRepo"
        fake.mkdir()
        other = Path(str(fake).swapcase())
        if not other.exists():
            self.skipTest("case-sensitive file system")
        with self.assertRaises(ids.ScanError):
            ids.make_key(other / "k.key", repo_root=fake)
        self.assertFalse((fake / "k.key").exists())


class TestHardeningRound2(Fixture):
    """Code-review findings of 2026-10-16 (Task 19 round 2)."""

    def test_arabic_definite_tokens_after_a_proclitic(self):
        self.put("ar.md", "والفلانكو\nبالفلانكو\nللفلانكو\nالفلانكو\nودار الزوربو\n")
        self.assertEqual([x.line for x in self.hits()], [1, 2, 3, 4, 5])

    def test_camelcase_token_with_glued_neighbours(self):
        self.put("a.ts", "QuinVorgeScene\nquinVorge2\nmyQuinVorge\nquinvorge\n")
        self.assertEqual([x.line for x in self.hits()], [1, 2, 3, 4])

    def test_dotted_capital_i_folds_the_same_in_generator_and_scanner(self):
        self.put("a.md", "İzvexa\n")
        self.assertEqual([x.line for x in self.hits()], [1])

    def test_proclitic_strip_keeps_at_least_four_letters(self):
        self.put("a.md", "وسامو\nسامو\n")             # "و" + a 4-letter token: found; never a 3-letter remainder
        self.assertEqual([x.line for x in self.hits()], [1, 2])
        self.assertEqual(ids._norm.prefix_forms("وسام"), [])

    def test_quote_prefix_does_not_break_a_wrapped_phrase(self):
        self.put("a.md", "see Zorblax\n> Quentaro\n")
        self.put("b.html", "see Zorblax\n&gt; Quentaro\n")
        self.assertEqual(sorted((x.path, x.line) for x in self.hits()), [("a.md", 2), ("b.html", 2)])

    def test_percent_encoded_file_name_found_and_redacted(self):
        self.put("docs/Zorblax%20Quentaro.md", "clean\n")
        h = self.hits()
        self.assertEqual([x.line for x in h], [0])
        self.assertNotIn("zorblax", h[0].path.casefold())

    def test_deleted_tracked_file_is_not_unreadable(self):
        repo = self.tmp / "gitrepo2"
        repo.mkdir()
        if subprocess.run(["git", "init", "-q", str(repo)], capture_output=True).returncode != 0:
            self.skipTest("git not available")
        (repo / "a.md").write_text("clean\n", encoding="utf-8")
        (repo / "gone.md").write_text("clean\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True)
        (repo / "gone.md").unlink()
        report = {}
        self.assertEqual(ids.scan(repo, self.db, self.k, report=report), [])
        self.assertEqual(report["unreadable"], [])

    def test_unlistable_folder_is_reported_unreadable(self):
        from unittest import mock
        self.put("ok/a.md", "clean\n")
        self.put("locked/b.md", "clean\n")
        real = os.scandir

        def fake(path):
            if Path(path).name == "locked":
                raise PermissionError("denied")
            return real(path)
        with mock.patch.object(ids.os, "scandir", fake):
            report = {}
            ids.scan(self.tree, self.db, self.k, report=report)
        self.assertEqual(report["unreadable"], ["locked"])

    def test_secrets_report_redacts_identity_names_when_a_key_is_given(self):
        self.put("Zorblax Quentaro/x.env", "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8" + "\n")
        code, out = run_cli("secrets", "--root", str(self.tree), "--hashes", str(self.hashes), "--key-file",
                            str(self.key))
        self.assertEqual(code, 1, out)
        self.assertNotIn("zorblax", out.casefold())
        self.assertIn("<name:", out)


class TestParallel(Fixture):
    def test_parallel_scan_equals_single_process(self):
        for i in range(30):
            self.put(f"d{i % 3}/f{i}.md", "clean line\n" * 5 + ("Zorblax Quentaro\n" if i % 7 == 0 else ""))
        self.put("Vexilor/x.md", "see Zorblax\nQuentaro\n")
        one, many = {}, {}
        a = ids.scan(self.tree, self.db, self.k, report=one, jobs=1)
        b = ids.scan(self.tree, self.db, self.k, report=many, jobs=3, min_files_per_job=4)
        self.assertEqual(a, b)
        self.assertEqual(one, many)
        self.assertTrue(a)


class TestGenerator(Fixture):
    def test_hash_file_holds_no_plain_token(self):
        raw = self.hashes.read_text(encoding="utf-8").casefold()
        for w in WORDS:
            self.assertNotIn(w, raw)
        doc = json.loads(raw)
        self.assertEqual(doc["mode"], "keyed")
        self.assertTrue(doc["tokens"] and all(len(h) == 64 for h in doc["tokens"] + doc["first"]))
        self.assertEqual(doc["tokens"], sorted(doc["tokens"]))

    def test_plain_list_inside_the_repo_is_refused(self):
        with self.assertRaises(ids.ScanError):
            ids.make_hashes(ROOT / "tools" / "plain.txt", self.key, self.tmp / "h2.json", repo_root=ROOT)
        self.assertFalse((ROOT / "tools" / "plain.txt").exists())

    def test_key_inside_the_repo_is_refused(self):
        fake_repo = self.tmp / "repo"
        fake_repo.mkdir()
        with self.assertRaises(ids.ScanError):
            ids.make_key(fake_repo / "tools" / "new.key", repo_root=fake_repo)
        self.assertFalse((fake_repo / "tools" / "new.key").exists())
        with self.assertRaises(ids.ScanError):
            ids.make_hashes(self.plain, fake_repo / "k.key", self.tmp / "h3.json", repo_root=fake_repo)

    def test_key_is_never_overwritten(self):
        before = self.key.read_bytes()
        with self.assertRaises(ids.ScanError):
            ids.make_key(self.key, repo_root=ROOT)
        self.assertEqual(self.key.read_bytes(), before)

    def test_line_with_hard_punctuation_is_refused_without_echo(self):
        bad = self.secret / "bad.txt"
        bad.write_text("ok token\nzorblax, quentaro\n", encoding="utf-8")
        with self.assertRaises(ids.ScanError) as cm:
            ids.make_hashes(bad, self.key, self.tmp / "h4.json", repo_root=ROOT)
        self.assertIn("line 2", str(cm.exception))
        self.assertNotIn("zorblax", str(cm.exception).casefold())

    def test_cli_make_key_and_make_hashes_print_no_token(self):
        k2 = self.secret / "k2.key"
        code, out = run_cli("make-key", "--out", str(k2))
        self.assertEqual(code, 0, out)
        h2 = self.tmp / "h5.json"
        code, out = run_cli("make-hashes", "--plain", str(self.plain), "--key-file", str(k2), "--out", str(h2))
        self.assertEqual(code, 0, out)
        for w in WORDS:
            self.assertNotIn(w, out.casefold())


class TestCli(Fixture):
    def test_hit_report_names_path_and_line_never_the_token(self):
        self.put("notes/a.md", "x\nZorblax Quentaro\n")
        code, out = run_cli("scan", "--root", str(self.tree), "--hashes", str(self.hashes), "--key-file", str(self.key))
        self.assertEqual(code, 1, out)
        self.assertIn("notes/a.md:2", out)
        for w in WORDS:
            self.assertNotIn(w, out.casefold())

    def test_clean_scan_exits_zero_and_json_mode(self):
        self.put("a.md", "clean\n")
        code, out = run_cli("scan", "--root", str(self.tree), "--hashes", str(self.hashes), "--key-file", str(self.key),
                            "--json")
        self.assertEqual(code, 0, out)
        doc = json.loads(out)
        self.assertEqual(doc["hits"], [])
        self.assertGreaterEqual(doc["files"], 1)

    def test_key_from_environment_variable(self):
        self.put("a.md", "Zorblax Quentaro\n")
        code, out = run_cli("scan", "--root", str(self.tree), "--hashes", str(self.hashes),
                            env={"WNC_IDENTITY_KEY_FILE": str(self.key)})
        self.assertEqual(code, 1, out)

    def test_missing_key_skips_but_require_key_fails(self):
        self.put("a.md", "Zorblax Quentaro\n")
        code, out = run_cli("scan", "--root", str(self.tree), "--hashes", str(self.hashes))
        self.assertEqual(code, 0, out)
        self.assertIn("skipped: no key", out)
        code, out = run_cli("scan", "--root", str(self.tree), "--hashes", str(self.hashes), "--require-key")
        self.assertEqual(code, 2, out)

    def test_wrong_key_is_detected(self):
        other = self.secret / "other.key"
        ids.make_key(other, repo_root=ROOT)
        code, out = run_cli("scan", "--root", str(self.tree), "--hashes", str(self.hashes), "--key-file", str(other))
        self.assertEqual(code, 2, out)
        self.assertIn("does not match", out)


class TestSecrets(Fixture):
    FAKE_GH = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"

    def test_planted_fake_token_is_found_and_not_printed(self):
        self.put("cfg/x.env", f"token={self.FAKE_GH}\n")
        found = ids.scan_secrets(self.tree)
        self.assertEqual([(s.path, s.line, s.pattern) for s in found], [("cfg/x.env", 1, "github_token")])
        code, out = run_cli("secrets", "--root", str(self.tree))
        self.assertEqual(code, 1, out)
        self.assertNotIn(self.FAKE_GH, out)

    PERSON = "qwmx" + "person"        # built at run time: this file itself holds no personal-looking home path

    def test_personal_home_path_found_placeholders_allowed(self):
        self.put("a.md", f"C:\\Users\\{self.PERSON}\\file\n/Users/<you>/x\nC:\\Users\\Public\\y\n/Users/runner/z\n")
        found = ids.scan_secrets(self.tree)
        self.assertEqual([(s.line, s.pattern) for s in found], [(1, "home_path")])

    def test_lowercase_windows_home_is_found(self):
        self.put("a.md", f"c:\\users\\{self.PERSON}\\x\n")
        self.assertEqual([(s.line, s.pattern) for s in ids.scan_secrets(self.tree)], [(1, "home_path")])

    def test_url_paths_placeholders_and_regex_source_are_not_home_paths(self):
        self.put("a.md", "GET /users/<owner>/settings/billing\n"
                         f"https://api.example.com/users/{self.PERSON}/repos\n"
                         "/Users/$USER/x and /Users/{name}/y and C:\\Users\\%USERNAME%\\z\n"
                         'rx = r"(?:/Users/)([^\\\\/]+)"\n')
        self.assertEqual(ids.scan_secrets(self.tree), [])

    def test_prose_naming_a_home_folder_without_a_user_is_not_a_home_path(self):
        self.put("a.md", "a macOS home (/Users/, capitalised) or a Linux home (/home/), any case: c:\\users\\…\n"
                         "under C:\\Users\\, then /home/.cache and /Users/-x\n")
        self.assertEqual(ids.scan_secrets(self.tree), [])

    def test_file_urls_and_linux_homes_found_all_users_not(self):
        self.put("a.xml", f'<a href="file:///Users/{self.PERSON}/x.mov"/>\n/home/{self.PERSON}/y\n'
                          "C:\\Users\\All Users\\z\n")
        self.assertEqual([(s.line, s.pattern) for s in ids.scan_secrets(self.tree)], [(1, "home_path"), (2, "home_path")])

    def test_more_credential_patterns(self):
        fakes = {
            "aws_key": "ASIA" + "ABCDEFGHIJKLMNOP",
            "slack_token": "xapp-" + "1-A0123456789-0123456789-abcdef",
            "private_key": "-----BEGIN PGP " + "PRIVATE KEY BLOCK-----",
            "hf_token": "hf_" + "AbCdEfGhIjKlMnOpQrStUvWxYz012345",
            "npm_token": "npm_" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
            "gitlab_token": "glpat-" + "AbCdEfGhIjKlMnOpQrSt",
        }
        self.put("a.env", "\n".join(fakes.values()) + "\n")
        found = ids.scan_secrets(self.tree)
        self.assertEqual([s.pattern for s in found], list(fakes))

    def test_allowlist_is_case_exact_and_star_stays_in_one_folder(self):
        self.put("tests/sub/f.md", f"/Users/{self.PERSON}/a\n")
        self.put("Fixtures/g.md", f"/Users/{self.PERSON}/b\n")     # no "fixtures" folder: case-exact match
        allow = self.tmp / "allow.json"
        allow.write_text(json.dumps([{"path": "tests/*", "pattern": "home_path", "reason": "fixture"},
                                     {"path": "fixtures/*", "pattern": "home_path", "reason": "fixture"}]),
                         encoding="utf-8")
        self.assertEqual(sorted(s.path for s in ids.scan_secrets(self.tree, allowlist=allow)),
                         ["Fixtures/g.md", "tests/sub/f.md"])

    def test_allowlist_entry_needs_a_reason(self):
        allow = self.tmp / "allow.json"
        allow.write_text(json.dumps([{"path": "x/*", "pattern": "home_path"}]), encoding="utf-8")
        with self.assertRaises(ids.ScanError):
            ids.scan_secrets(self.tree, allowlist=allow)

    def test_allowlist_entry_silences_one_finding(self):
        self.put("tests/fixture.md", f"/Users/{self.PERSON}/a\n")
        allow = self.tmp / "allow.json"
        allow.write_text(json.dumps([{"path": "tests/*", "pattern": "home_path", "reason": "fixture"}]),
                         encoding="utf-8")
        self.assertEqual(ids.scan_secrets(self.tree, allowlist=allow), [])

    def test_utf8_bom_is_reported_except_powershell(self):
        self.put("a.md", "\ufeffhello\n")
        self.put("s.ps1", "\ufeffWrite-Host hi\n")
        found = ids.scan_secrets(self.tree)
        self.assertEqual([(s.path, s.pattern) for s in found], [("a.md", "bom")])


class TestRealTree(unittest.TestCase):
    def test_full_repo_scan_is_fast(self):
        """The acceptance bound (< 10 s on this PC), measured with a test key and ~100 fictional tokens whose FIRST
        words are common in our own repo (the worst case for the prefilters), in Arabic and English."""
        common = ["the", "data", "split", "panel", "system", "reel", "style", "في", "من", "على", "مع", "الكابشن"]
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            plain = td / "p.txt"
            plain.write_text("\n".join(f"{common[i % len(common)]} vexil{i}q token{i}zz" for i in range(100)),
                             encoding="utf-8")
            key = td / "k.key"
            ids.make_key(key, repo_root=ROOT)
            ids.make_hashes(plain, key, td / "h.json", repo_root=ROOT)
            t0 = time.perf_counter()
            hits = ids.scan(ROOT, ids.load_db(td / "h.json"), ids.read_key(key))
            took = time.perf_counter() - t0
        self.assertEqual(hits, [])
        self.assertLess(took, 10.0, f"full repo scan took {took:.1f} s")

    def test_repo_hash_file_is_hashes_only(self):
        f = ROOT / "tools" / "identity_hashes.json"
        if not f.exists():
            self.skipTest("tools/identity_hashes.json not generated yet")
        doc = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual(doc["mode"], "keyed")
        self.assertEqual(set(doc), {"format", "mode", "algo", "key_id", "norm_version", "max_words", "tokens", "first", "first2"})
        self.assertEqual(doc["norm_version"], ids._norm.NORM_VERSION)   # regenerate the hash file when it changes
        self.assertTrue(all(len(h) == 64 and int(h, 16) >= 0 for h in doc["tokens"] + doc["first"] + doc["first2"]))

    def test_real_tree_passes_with_the_owners_key(self):
        f = ROOT / "tools" / "identity_hashes.json"
        key = ids.key_from_env()                   # WNC_IDENTITY_KEY_FILE (owner's PC) or WNC_IDENTITY_KEY (CI secret)
        if key is None or not f.exists():
            self.skipTest("the owner's identity key is not on this machine (WNC_IDENTITY_KEY_FILE / WNC_IDENTITY_KEY)")
        hits = ids.scan(ROOT, ids.load_db(f), key)
        self.assertEqual([(h.path, h.line) for h in hits], [])


if __name__ == "__main__":
    unittest.main()
