# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.5 (part B) — the cli.py hunk (hooks/BL-14/cli.patch): `reel client-move` / `reel client-clone`, their
lock rule (a dry run reads only; --apply holds the client's lock), the refused flag mixes, and the check that refuses a
copied client nobody migrated before any other command reads it. Goes to whynot-cut/tests/ with the patch.
Run:  bash tools/test.sh -p test_t45_cli.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

import cli  # noqa: E402
from test_t45_client_move import make_client, unlink_links  # noqa: E402

CLI = SK / "engine" / "reel" / "cli.py"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.src = make_client(self.tmp, "Acme عميل")
        (self.src / "output/.whynot-lock").unlink()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
        self.env.update(WHYNOT_LOCK_SESSION="t45-cli-test", PYTHONIOENCODING="utf-8")

    def tearDown(self):
        unlink_links(self.tmp)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def reel(self, *args):
        p = subprocess.run([sys.executable, "-s", str(CLI), *map(str, args)], capture_output=True, env=self.env,
                           encoding="utf-8", errors="replace", timeout=300)
        try:
            doc = json.loads(p.stdout)
        except ValueError:
            doc = None
        return p.returncode, doc, p.stderr


class TestVerbs(Base):
    def test_listed_in_help(self):
        out = subprocess.run([sys.executable, "-s", str(CLI), "--help"], capture_output=True, env=self.env,
                             encoding="utf-8", errors="replace").stdout
        self.assertIn("client-move", out)
        self.assertIn("client-clone", out)

    def test_dry_run_then_apply(self):
        dest = self.tmp / "Moved"
        rc, doc, err = self.reel("client-move", "--root", self.src, "--to", dest)
        self.assertEqual(rc, 0, err)
        self.assertFalse(doc["applied"])
        self.assertFalse(dest.exists())
        self.assertFalse((self.src / "output/.whynot-lock").exists())          # a dry run takes no lock
        rc, doc, err = self.reel("client-move", "--root", self.src, "--to", dest, "--apply")
        self.assertEqual(rc, 0, err)
        self.assertTrue(doc["applied"], doc)
        self.assertFalse((dest / "output/.whynot-lock").exists())
        self.assertFalse((self.src / "output/.whynot-lock").exists())          # the per-command lock ended with it
        rc, doc, err = self.reel("next", "--root", dest, "--video-id", "R01")
        self.assertEqual(rc, 0, err)
        self.assertEqual(doc["stale"], [])

    def test_clone_and_its_required_target(self):
        rc, _d, err = self.reel("client-clone", "--root", self.src)
        self.assertEqual(rc, 2)
        self.assertIn("--to", err)
        rc, doc, err = self.reel("client-clone", "--root", self.src, "--to", self.tmp / "Sister", "--apply")
        self.assertEqual(rc, 0, err)
        self.assertTrue((self.tmp / "Sister/.whynot-client").is_file())

    def test_flag_mixes_are_refused(self):
        for args in (("--to", self.tmp / "x", "--already-moved"), ("--from", self.tmp, "--to", self.tmp / "x"), ()):
            rc, doc, err = self.reel("client-move", "--root", self.src, *args)
            self.assertEqual(rc, 2, (args, err))
            self.assertIn("refused", doc)
            self.assertFalse((self.tmp / "x").exists())

    def test_a_refusal_exits_2(self):
        rc, doc, _e = self.reel("client-move", "--root", self.src, "--to", self.src / "output/x")
        self.assertEqual(rc, 2)
        self.assertIn("contain each other", doc["refused"])

    def test_lock_rule(self):
        for argv, want in ((["client-move", "--root", "r", "--to", "d"], False),
                           (["client-move", "--root", "r", "--to", "d", "--apply"], True),
                           (["client-move", "--root", "r", "--already-moved", "--apply"], True),
                           (["client-clone", "--root", "r", "--to", "d"], False),
                           (["client-clone", "--root", "r", "--to", "d", "--apply"], True)):
            a = type("A", (), {"cmd": argv[0], "apply": "--apply" in argv})()
            self.assertEqual(cli.writes(a), want, argv)


class TestCopiedClientGuard(Base):
    def test_a_copy_nobody_migrated_is_refused_until_it_is(self):
        hand = self.tmp / "copied by hand"
        shutil.copytree(self.src, hand, copy_function=shutil.copy2)
        for cmd in (("next", "--video-id", "R01"), ("status", "--video-id", "R01"), ("discover",)):
            rc, doc, err = self.reel(cmd[0], "--root", hand, *cmd[1:])
            self.assertEqual(rc, 2, (cmd, err))
            self.assertIn("is a copy of", doc["refused"])
            self.assertIn("--already-moved", doc["how"])
        rc, doc, err = self.reel("client-move", "--root", hand, "--already-moved")
        self.assertEqual(rc, 0, err)
        self.assertEqual(doc["old_root"], str(self.src))
        rc, doc, err = self.reel("client-move", "--root", hand, "--already-moved", "--apply")
        self.assertEqual(rc, 0, err)
        rc, doc, err = self.reel("next", "--root", hand, "--video-id", "R01")
        self.assertEqual(rc, 0, err)
        rc, doc, err = self.reel("next", "--root", self.src, "--video-id", "R01")     # the original: never refused
        self.assertEqual(rc, 0, err)


if __name__ == "__main__":
    unittest.main()
