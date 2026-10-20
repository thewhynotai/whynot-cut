"""Addendum M5-T4 (Task 59), the executor's cli.py hunks: `reel client-brief` (writes
output/client_database/client-brief.md when a source changed; --force), `reel client-db` refreshing it right after the
database, and `reel next` (so `reel brief` too, which shows next's notices) saying when it is missing or stale.
The library side (lib/client_brief.py) is tested in test_client_brief.py.
Case list: D:/ClaudeData/claude-api-lane/lane4/work/task59/cases.md (call sites, C10, D19).
Run:  bash tools/test.sh -p test_client_brief_cli.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402

CLI = SK / "engine/reel/cli.py"
FIX = SK / "tests" / "fixtures" / "brief" / "clients"
BRIEF = "output/client_database/client-brief.md"


def cli_module():
    spec = importlib.util.spec_from_file_location("reel_cli_t59c", CLI)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run_main(m, argv):
    so, se = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
        try:
            m.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, so.getvalue(), se.getvalue()


def make_root(tmp: Path, which: str | None = "basic") -> Path:
    root = tmp / "عميل تجربة Dr X"
    for d in ("assets", "data/Raw"):
        (root / d).mkdir(parents=True)
    (root / ".whynot-client").write_text('{"whynot_client": 1}', encoding="utf-8")
    if which:
        shutil.copytree(FIX / which / "output", root / "output")
    return root


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t59cli_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.m = cli_module()
        self.addCleanup(common.set_context, None)

    def main(self, root, *argv):
        return run_main(self.m, ["--root", str(root), *argv])


class TestVerb(Base):
    def test_client_brief_is_a_writer_without_a_video_id(self):
        self.assertIn("client-brief", self.m.CORE_WRITES)
        self.assertNotIn("client-brief", self.m.CORE_READS)
        self.assertIn("client-brief", self.m.NO_ID)
        self.assertIn("client-brief", self.m.CORE_COMMANDS)
        self.assertIn("1,000 tokens", self.m.CORE_COMMANDS["client-brief"])

    def test_c10_builds_then_leaves_it_alone(self):
        root = make_root(self.tmp)
        code, so, se = self.main(root, "client-brief")
        self.assertEqual(code, 0, se)
        doc = json.loads(so)
        self.assertTrue(doc["rebuilt"])
        self.assertEqual(doc["path"], BRIEF)
        self.assertIn("first build", doc["reason"])
        self.assertIn(BRIEF, doc["summary"])
        body = (root / BRIEF).read_bytes()
        code, so, se = self.main(root, "client-brief")
        self.assertEqual(code, 0, se)
        self.assertFalse(json.loads(so)["rebuilt"])
        self.assertEqual((root / BRIEF).read_bytes(), body)
        code, so, _ = self.main(root, "client-brief", "--force")
        self.assertTrue(json.loads(so)["rebuilt"])
        self.assertIn("on request", json.loads(so)["reason"])

    def test_d19_no_client_database_refuses_and_writes_nothing(self):
        root = make_root(self.tmp, which=None)
        code, so, se = self.main(root, "client-brief")
        self.assertNotEqual(code, 0)
        self.assertIn("reel client-db", so + se)
        self.assertFalse((root / "output/client_database").exists())

    def test_client_db_refreshes_the_brief(self):
        root = make_root(self.tmp)
        write_json(root / "output/discovery/input-inventory.json", {"files": [], "file_count": 0, "by_role": {}})
        status = {"colors": 1, "fonts": 1, "images": 1, "issues": [], "ready": False}
        with mock.patch("lib.client_db.build", return_value=dict(status)):
            code, so, se = self.main(root, "client-db")
        self.assertEqual(code, 0, se)
        doc = json.loads(so)
        self.assertIn("client brief rebuilt", doc["client_brief"])
        self.assertTrue((root / BRIEF).exists())
        with mock.patch("lib.client_db.build", return_value=dict(status)):
            code, so, se = self.main(root, "client-db")
        self.assertIn("client brief current", json.loads(so)["client_brief"])

    def test_client_db_never_fails_on_a_brief_problem(self):
        root = make_root(self.tmp)
        write_json(root / "output/discovery/input-inventory.json", {"files": [], "file_count": 0, "by_role": {}})
        from lib import client_brief
        from lib.errors import Guidance
        with mock.patch("lib.client_db.build", return_value={"issues": [], "ready": False}), \
                mock.patch.object(client_brief, "ensure", side_effect=Guidance("a link is on that path", "x")):
            code, so, se = self.main(root, "client-db")
        self.assertEqual(code, 0, se)
        self.assertIn("not rebuilt", json.loads(so)["client_brief"])
        self.assertIn("reel client-brief", json.loads(so)["client_brief"])


class TestNext(Base):
    def notices(self, root, vid="C0001"):
        Paths(root, vid).ensure_project()
        code, so, se = self.main(root, "--video-id", vid, "next")
        self.assertEqual(code, 0, se)
        return json.loads(so)["notices"]

    def test_next_says_missing_then_stale_then_nothing(self):
        root = make_root(self.tmp)
        self.assertTrue(any("client brief not built yet" in n and "reel client-brief" in n
                            for n in self.notices(root)))
        self.main(root, "client-brief")
        self.assertFalse(any("client brief" in n for n in self.notices(root)))
        p = root / "output/client_database/reel-profile/profile.json"
        p.write_bytes(p.read_bytes() + b" ")
        n = [x for x in self.notices(root) if "client brief" in x]
        self.assertTrue(n and "stale" in n[0] and "profile.json" in n[0], n)

    def test_next_is_silent_without_a_client_database(self):
        root = make_root(self.tmp, which=None)
        self.assertFalse(any("client brief" in n for n in self.notices(root)))

    def test_next_never_fails_on_a_brief_problem(self):
        root = make_root(self.tmp)
        from lib import client_brief
        with mock.patch.object(client_brief, "notice", side_effect=OSError("boom")):
            n = self.notices(root)
        self.assertTrue(any("could not be checked" in x for x in n))

    def test_motion_next_carries_the_notice(self):
        root = make_root(self.tmp)
        write_json(root / "output/projects/EP01_R01_MO/00_inputs/source.json",
                   {"kind": "motion_reel", "footage": "data/Episodes/EP01.mp4", "in_ms": 0, "out_ms": 30000})
        code, so, se = self.main(root, "--video-id", "EP01_R01_MO", "next")
        self.assertEqual(code, 0, se)
        doc = json.loads(so)
        self.assertEqual(doc.get("kind"), "motion")
        self.assertTrue(any("client brief not built yet" in n for n in doc["notices"]))

    def test_reel_brief_shows_it(self):
        root = make_root(self.tmp)
        Paths(root, "C0001").ensure_project()
        code, so, se = self.main(root, "--video-id", "C0001", "brief")
        self.assertEqual(code, 0, se)
        self.assertIn("client brief not built yet", so)
        self.assertIn("reel client-brief", so)


if __name__ == "__main__":
    unittest.main()
