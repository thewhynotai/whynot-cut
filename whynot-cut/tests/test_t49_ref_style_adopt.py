# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.9 — `reel ref-style --adopt <ID>`: an old per-video style (2.x, authored per clip) merged into the
client-level reference style, the diff shown first, `--yes` to write.

Merge rule: keys only the video has are added; equal values change nothing; a different value KEEPS the client's and
is listed in editing-rules.json `conflicts` (both values, the video id) for the researcher and the editor to settle.
Dicts merge per key, lists are values (never concatenated). The video's own files are never touched; the reference
fingerprint is not either, so after `--yes` the style is reviewed and recorded (`reel ref-style --record`) as usual.
Case list: the wnc-queue track's task notes.
Run:  bash tools/test.sh -p test_t49_ref_style_adopt.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import argparse
import importlib.util
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

from lib import common  # noqa: E402
from lib import lead_steps  # noqa: E402  BL-15: a lead-only step runs with the guard's token
from lib import ref_style as RS  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402
from lib.errors import Guidance  # noqa: E402

CLI = SK / "engine/reel/cli.py"
STYLE = "01_analysis/editing-style.json"
R02 = {   # the shape of a 2.1 per-video file as the field test wrote them (values fictional)
    "source": "Reference reel TWN_REEL (the editor's own finished R02, 53.9 s) + profile style.json",
    "measured": {"cuts_per_minute": 10.03, "shot_median_s": 4.57, "first_cut_s": 9.78},
    "structure_observed": [{"at": "0-3 s", "what": "hook title at the top, cream box: «لو المضرب قرر يلف في إيدك؟»"},
                           {"at": "51-53 s", "what": "end card at the top: «الحلقة كاملة على القناة»"}],
    "rules": {"music": "none", "transitions": "hard cuts", "captions": "keywords style, gold keyword «إيمانهم»"},
}
R05 = {
    "source": "the editor's finished R05",
    "measured": {"cuts_per_minute": 12.0, "shot_median_s": 4.57, "hook_s": 2.5},
    "structure_observed": [{"at": "0-2 s", "what": "hook in a cream box"}],
    "rules": {"music": "none", "sfx": "a soft click on the hook only"},
}


def env():
    from test_plugin import isolated_env
    return isolated_env()


def make_client(tmp: Path) -> Path:
    root = tmp / "Dr Test د. تجربة"
    for d in ("assets/Brand", "data/Raw", "data/References"):
        (root / d).mkdir(parents=True)
    (root / ".whynot-client").write_text("{}", encoding="utf-8")
    (root / "data/References/ref_reel.mp4").write_bytes(b"reference-video")
    return root


def tree(folder: Path) -> dict:
    out = {}
    for dp, dns, fns in os.walk(folder):
        for n in dns + fns:
            p = Path(dp) / n
            st = p.lstat()
            out[str(p.relative_to(folder))] = (st.st_size, st.st_mtime_ns)
    return out


def dir_link(link: Path, target: Path):
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def cli_module():
    spec = importlib.util.spec_from_file_location("reel_cli_t49", CLI)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = make_client(self.tmp)
        self.sdir = self.root / RS.STYLE_REL

    def tearDown(self):
        common.set_context(None)
        for dp, dns, _fns in os.walk(self.tmp):
            for n in dns:
                p = Path(dp) / n
                if p.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(p)):
                    os.rmdir(p) if os.name == "nt" else p.unlink()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def video(self, vid: str, style, rel: str = STYLE, raw: str | None = None) -> Path:
        v = Paths(self.root, vid)
        v.ensure_project()
        f = v.p(rel)
        if raw is not None:
            f.write_text(raw, encoding="utf-8")
        else:
            write_json(f, style)
        return f

    def adopt(self, vid: str, yes: bool = False) -> dict:
        return RS.adopt(self.root, vid, yes=yes)

    def client_style(self) -> dict:
        return read_json(self.sdir / "editing-style.json")

    def client_rules(self) -> dict:
        return read_json(self.sdir / "editing-rules.json")


class TestFirstAdopt(Base):
    def test_the_diff_comes_first_and_nothing_is_written(self):
        self.video("R02", R02)
        before = tree(self.root)
        r = self.adopt("R02")
        self.assertTrue(r["ok"] and r["dry_run"] and r["changes"], r)
        self.assertEqual(r["source"], "output/projects/R02/01_analysis/editing-style.json")
        for k in ("measured.cuts_per_minute", "structure_observed", "rules.music"):
            self.assertIn(k, r["diff"]["added"])
        self.assertNotIn("source", r["diff"]["added"])        # that one video's own note: quoted in the analysis
        self.assertEqual(r["diff"]["conflicts"], [])
        self.assertEqual(sorted(r["would_write"]), sorted(f"{RS.STYLE_REL}/{f}" for f in RS.FILES))
        self.assertIn("--yes", r["how"])
        self.assertEqual(tree(self.root), before, "a dry run writes nothing")

    def test_yes_writes_the_client_style_from_the_video(self):
        self.video("R02", R02)
        r = self.adopt("R02", yes=True)
        self.assertTrue(r["ok"] and not r["dry_run"], r)
        style = self.client_style()
        for k in R02:
            if k != "source":
                self.assertEqual(style[k], R02[k], k)
        self.assertNotIn("source", style)
        prov = style["_adopted"]
        self.assertEqual([p["from"] for p in prov], ["output/projects/R02/01_analysis/editing-style.json"])
        self.assertEqual(len(prov[0]["sha1"]), 40)
        self.assertEqual(self.client_rules(), {k: [] for k in RS.RULE_KEYS})
        md = (self.sdir / "editing-style-analysis.md").read_text(encoding="utf-8")
        self.assertIn("R02", md)
        self.assertIn(R02["source"], md)                      # only what the video's file says: no invented prose
        st = RS.state(self.root)
        self.assertEqual(st["state"], "unrecorded")            # reviewed, then `reel ref-style --record`
        self.assertIn("ref-style --record", r["next"])

    def test_arabic_round_trips_as_text(self):
        self.video("R02", R02)
        self.adopt("R02", yes=True)
        raw = (self.sdir / "editing-style.json").read_text(encoding="utf-8")
        self.assertIn("«الحلقة كاملة على القناة»", raw)            # written as text, not \\u escapes
        self.assertEqual(self.client_style()["rules"]["captions"], R02["rules"]["captions"])


class TestSecondAdopt(Base):
    def setUp(self):
        super().setUp()
        self.video("R02", R02)
        self.adopt("R02", yes=True)
        self.video("R05", R05)

    def test_different_values_keep_the_client_and_are_listed(self):
        r = self.adopt("R05")
        self.assertIn("measured.hook_s", r["diff"]["added"])
        self.assertIn("rules.sfx", r["diff"]["added"])
        keys = {c["key"]: c for c in r["diff"]["conflicts"]}
        self.assertEqual(set(keys), {"measured.cuts_per_minute", "structure_observed"})
        self.assertEqual((keys["measured.cuts_per_minute"]["client"], keys["measured.cuts_per_minute"]["video"]),
                         (10.03, 12.0))
        self.assertNotIn("measured.shot_median_s", keys)           # equal: nothing
        self.adopt("R05", yes=True)
        style = self.client_style()
        self.assertEqual(style["measured"]["cuts_per_minute"], 10.03)
        self.assertEqual(style["measured"]["hook_s"], 2.5)
        self.assertEqual(style["structure_observed"], R02["structure_observed"])   # a list is a value, not concatenated
        self.assertEqual(style["rules"]["sfx"], R05["rules"]["sfx"])
        conflicts = self.client_rules()["conflicts"]
        c = next(x for x in conflicts if x.get("key") == "measured.cuts_per_minute")
        self.assertEqual((c["video"], c["client_value"], c["video_value"]), ("R05", 10.03, 12.0))
        self.assertEqual([p["from"].split("/")[2] for p in style["_adopted"]], ["R02", "R05"])

    def test_adopting_again_changes_nothing(self):
        self.adopt("R05", yes=True)
        before = tree(self.sdir)
        for vid in ("R02", "R05"):
            r = self.adopt(vid, yes=True)
            self.assertTrue(r["ok"], r)
            self.assertFalse(r["changes"], r)
        self.assertEqual(tree(self.sdir), before)
        n = sum(1 for x in self.client_rules()["conflicts"] if x.get("key") == "measured.cuts_per_minute")
        self.assertEqual(n, 1)


class TestSources(Base):
    def test_the_kept_legacy_copy_wins_over_a_current_copy(self):
        self.video("R02", {"captions": {"size": 1}, "_reference_style": {"from": RS.STYLE_REL}})
        self.video("R02", R02, rel="01_analysis/editing-style.legacy.json")
        r = self.adopt("R02")
        self.assertEqual(r["source"], "output/projects/R02/01_analysis/editing-style.legacy.json")
        self.assertNotIn("captions.size", r["diff"]["added"])

    def test_a_copy_of_the_client_style_is_refused(self):
        self.video("C0001", {"captions": {"size": 1}, "_reference_style": {"from": RS.STYLE_REL}})
        r = self.adopt("C0001", yes=True)
        self.assertIn("refused", r)
        self.assertFalse(self.sdir.exists())

    def test_per_video_rules_are_appended_once(self):
        self.sdir.mkdir(parents=True)
        write_json(self.sdir / "editing-style.json", {"measured": {"cuts_per_minute": 10.03}})
        write_json(self.sdir / "editing-rules.json", {"mandatory": ["hard cuts"], "preferences": [], "optional": [],
                                                      "conflicts": []})
        self.video("R07", {"measured": {"cuts_per_minute": 10.03}})
        self.video("R07", {"mandatory": ["hard cuts", "gold keyword «مهم»"], "optional": ["soft click"]},
                   rel="01_analysis/editing-rules.json")
        r = self.adopt("R07")
        self.assertEqual(r["diff"]["rules_added"], {"mandatory": ["gold keyword «مهم»"], "optional": ["soft click"]})
        self.adopt("R07", yes=True)
        self.assertEqual(self.client_rules()["mandatory"], ["hard cuts", "gold keyword «مهم»"])
        self.assertFalse(self.adopt("R07", yes=True)["changes"])

    def test_rules_that_are_not_lists_are_refused(self):
        self.video("R07", {"measured": {"cuts_per_minute": 9}})
        self.video("R07", {"mandatory": "hard cuts"}, rel="01_analysis/editing-rules.json")
        r = self.adopt("R07", yes=True)
        self.assertIn("refused", r)
        self.assertIn("editing-rules.json", r["refused"])
        self.assertFalse(self.sdir.exists())


class TestDamaged(Base):
    def assert_refused_untouched(self, vid: str, part: str):
        before = tree(self.root)
        r = self.adopt(vid, yes=True)
        self.assertIn("refused", r)
        self.assertIn(part, r["refused"] + r.get("how", ""))
        self.assertEqual(tree(self.root), before)

    def test_a_video_file_that_is_not_json(self):
        self.video("R02", None, raw="{not json")
        self.assert_refused_untouched("R02", "editing-style.json")

    def test_a_video_file_that_is_not_an_object(self):
        self.video("R02", ["a", "b"])
        self.assert_refused_untouched("R02", "editing-style.json")

    def test_a_damaged_client_style_is_never_overwritten(self):
        self.video("R02", R02)
        self.sdir.mkdir(parents=True)
        (self.sdir / "editing-style.json").write_text("{broken", encoding="utf-8")
        self.assert_refused_untouched("R02", "editing-style.json")
        (self.sdir / "editing-style.json").write_text("{}", encoding="utf-8")
        (self.sdir / "editing-rules.json").write_text("[1]", encoding="utf-8")
        self.assert_refused_untouched("R02", "editing-rules.json")

    def test_no_such_project_or_no_style(self):
        self.assert_refused_untouched("R99", "R99")
        Paths(self.root, "R03").ensure_project()
        self.assert_refused_untouched("R03", "R03")

    def test_bad_ids_are_refused(self):
        for bad in ("../x", "a/b", "a\\b", "C:x", ".."):
            with self.subTest(bad=bad):
                self.assertIn("refused", self.adopt(bad, yes=True))
        self.assertFalse(self.sdir.exists())

    def test_a_link_into_data_is_refused(self):
        self.video("R02", R02)
        (self.root / "output/client_database").mkdir(parents=True)
        dir_link(self.sdir, self.root / "data/References")
        before = tree(self.root / "data")
        r = self.adopt("R02", yes=True)
        self.assertIn("refused", r)
        self.assertEqual(tree(self.root / "data"), before)


class TestEffects(Base):
    def test_the_fingerprint_stays_and_video_copies_become_outdated(self):
        self.sdir.mkdir(parents=True)
        (self.sdir / "editing-style-analysis.md").write_text("# Reference style\n", encoding="utf-8")
        write_json(self.sdir / "editing-style.json", {"measured": {"cuts_per_minute": 10.03}})
        write_json(self.sdir / "editing-rules.json", {k: [] for k in RS.RULE_KEYS})
        self.assertTrue(RS.record(self.root)["ok"])
        c1 = Paths(self.root, "C0001")
        c1.ensure_project()
        self.assertTrue(RS.apply(c1)["ok"])
        f = self.video("R02", R02)
        own = f.read_bytes()
        fp = RS.state(self.root)["fingerprint"]
        self.adopt("R02", yes=True)
        st = RS.state(self.root)                      # review first: videos don't copy an unreviewed adopt (P1-2)
        self.assertEqual((st["state"], st["fingerprint"], st["adopted_unreviewed"]), ("unrecorded", fp, ["R02"]))
        self.assertFalse(RS.apply(c1)["ok"])
        self.assertTrue(RS.record(self.root)["ok"])
        self.assertEqual(RS.state(self.root)["state"], "current")
        self.assertEqual(RS.video_state(c1)["state"], "outdated")
        self.assertEqual(f.read_bytes(), own, "the video's own file is never touched")
        md = (self.sdir / "editing-style-analysis.md").read_text(encoding="utf-8")
        self.assertTrue(md.startswith("# Reference style\n"), "an existing analysis is kept, provenance appended")
        self.assertIn("R02", md)

    def test_next_on_a_legacy_video_names_adopt_until_it_is_adopted(self):
        self.video("R02", R02)
        n = RS.next_step(Paths(self.root, "R02"))
        self.assertTrue(any("ref-style --adopt R02" in x for x in n["notices"]), n["notices"])
        self.adopt("R02", yes=True)
        n = RS.next_step(Paths(self.root, "R02"))
        self.assertFalse(any("--adopt R02" in x for x in n["notices"]), n["notices"])


class TestRound1(Base):
    """What the first independent review of T4.9 found, each pinned here."""

    def test_a_link_to_another_clients_style_is_refused(self):
        other = make_client(self.tmp / "other")
        od = other / RS.STYLE_REL
        od.mkdir(parents=True)
        write_json(od / "editing-style.json", {"other_client": True})
        before = tree(other)
        self.video("R02", R02)
        (self.root / "output/client_database").mkdir(parents=True)
        dir_link(self.sdir, od)
        for yes in (False, True):                     # the diff too: it must not describe a write into another client
            r = self.adopt("R02", yes=yes)
            self.assertIn("refused", r)
            self.assertIn("another client", r["refused"])
        self.assertEqual(tree(other), before)

    def test_a_dry_run_refuses_a_link_into_data_too(self):
        self.video("R02", R02)
        (self.root / "output/client_database").mkdir(parents=True)
        dir_link(self.sdir, self.root / "data/References")
        self.assertIn("refused", self.adopt("R02"))

    def test_an_analysis_that_is_not_utf8_refuses_before_any_write(self):
        self.video("R02", R02)
        self.sdir.mkdir(parents=True)
        write_json(self.sdir / "editing-style.json", {"x": 1})
        (self.sdir / "editing-style-analysis.md").write_bytes("# تحليل\r\n".encode("cp1256"))
        before = tree(self.sdir)
        r = self.adopt("R02", yes=True)
        self.assertIn("refused", r)
        self.assertIn("UTF-8", r["refused"])
        self.assertEqual(tree(self.sdir), before)

    def test_bom_and_crlf_of_the_analysis_are_kept(self):
        self.video("R02", R02)
        self.sdir.mkdir(parents=True)
        (self.sdir / "editing-style-analysis.md").write_bytes(b"\xef\xbb\xbf# t\r\nline\r\n")
        self.adopt("R02", yes=True)
        raw = (self.sdir / "editing-style-analysis.md").read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf# t\r\nline\r\n"))
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))         # every line ending is CRLF

    def test_a_settled_conflict_is_not_brought_back(self):
        self.video("R02", R02)
        self.adopt("R02", yes=True)
        self.video("R05", R05)
        self.adopt("R05", yes=True)
        rules = self.client_rules()
        rules["conflicts"] = []                                      # the researcher settled them
        write_json(self.sdir / "editing-rules.json", rules)
        before = tree(self.sdir)
        r = self.adopt("R05", yes=True)
        self.assertFalse(r["changes"], r)
        self.assertIn("adopted already", r["message"])
        self.assertEqual(tree(self.sdir), before)

    def test_an_adopt_record_that_is_not_a_list_is_refused(self):
        self.video("R02", R02)
        self.sdir.mkdir(parents=True)
        write_json(self.sdir / "editing-style.json", {"_adopted": "by hand"})
        before = tree(self.sdir)
        self.assertIn("refused", self.adopt("R02", yes=True))
        self.assertEqual(tree(self.sdir), before)

    def test_true_is_not_one_and_dotted_keys_stay_apart(self):
        self.sdir.mkdir(parents=True)
        write_json(self.sdir / "editing-style.json", {"flag": 1, "a": {"b": 3}})
        self.video("R09", {"flag": True, "a.b": 2, "a": {"b": 3}})
        d = self.adopt("R09")["diff"]
        self.assertEqual([c["key"] for c in d["conflicts"]], ["flag"])
        self.assertEqual(d["added"], ["a\\.b"])

    def test_a_failure_part_way_puts_everything_back(self):
        """Review 2 P1-A: one file held open (a scan, an editor) while the others are replaced."""
        self.sdir.mkdir(parents=True)
        (self.sdir / "editing-style-analysis.md").write_text("# Reference style\n", encoding="utf-8")
        write_json(self.sdir / "editing-style.json", {"measured": {"cuts_per_minute": 9}})
        write_json(self.sdir / "editing-rules.json", {k: [] for k in RS.RULE_KEYS})
        self.assertTrue(RS.record(self.root)["ok"])
        self.video("R02", R02)
        before = {f.name: f.read_bytes() for f in self.sdir.iterdir()}
        from unittest import mock
        real_replace = os.replace
        calls = []

        def replace(a, b):
            calls.append(b)
            if len(calls) == 3:
                raise PermissionError(13, "held open", str(b))
            return real_replace(a, b)
        with mock.patch.object(RS.os if hasattr(RS, "os") else os, "replace", side_effect=replace):
            r = self.adopt("R02", yes=True)
        self.assertFalse(r["ok"], r)
        self.assertIn("put back", r["how"])
        self.assertEqual({f.name: f.read_bytes() for f in self.sdir.iterdir()}, before, "nothing changed, no .tmp")
        self.assertEqual(RS.state(self.root)["state"], "current")
        r = self.adopt("R02", yes=True)                               # and it goes through afterwards
        self.assertTrue(r["ok"] and r["changes"], r)
        self.assertEqual(RS.state(self.root)["state"], "unrecorded")

    def test_settled_conflicts_stay_settled_after_apply_renames_the_file(self):
        """Review 2 P1-B: --apply keeps the per-video file as editing-style.legacy.json (same bytes)."""
        self.sdir.mkdir(parents=True)
        (self.sdir / "editing-style-analysis.md").write_text("# Reference style\n", encoding="utf-8")
        write_json(self.sdir / "editing-style.json", {"measured": {"cuts_per_minute": 9}})
        write_json(self.sdir / "editing-rules.json", {k: [] for k in RS.RULE_KEYS})
        self.video("R02", R02)
        self.adopt("R02", yes=True)
        rules = self.client_rules()
        rules["conflicts"] = []
        write_json(self.sdir / "editing-rules.json", rules)
        self.assertTrue(RS.record(self.root)["ok"])
        self.assertTrue(RS.apply(Paths(self.root, "R02"))["ok"])         # renames R02's own file to .legacy
        self.assertTrue(Paths(self.root, "R02").p(RS.LEGACY_STYLE).exists())
        r = self.adopt("R02", yes=True)
        self.assertFalse(r["changes"], r)
        self.assertEqual(self.client_rules()["conflicts"], [])

    def test_a_store_with_assets_and_data_folders_is_not_a_client(self):
        """Review 2 P2: output/ on a mirror whose parent happens to have assets/ and data/ folders."""
        from lib import client_move_paths as CMP
        store = self.tmp / "Store"
        for d in ("assets", "data", "ClientC-output"):
            (store / d).mkdir(parents=True)
        self.assertIsNone(CMP.other_client(str(store / "ClientC-output" / "x.json"), self.root))
        (store / ".whynot-client").write_text("{}", encoding="utf-8")
        self.assertEqual(CMP.other_client(str(store / "ClientC-output" / "x.json"), self.root), str(store))

    def test_rules_keys_it_does_not_adopt_are_listed(self):
        self.video("R07", {"x": 1})
        self.video("R07", {"mandatory": ["hard cuts"], "notes": "keep music off"}, rel="01_analysis/editing-rules.json")
        self.assertEqual(self.adopt("R07")["diff"]["rules_not_adopted"], ["notes"])


class TestGuard(unittest.TestCase):
    """Only the lead writes an adopt (after the editor's OK); every subagent may show the diff (T49-GUARD.patch)."""

    def bash(self, cmd: str, agent: str | None):
        from test_plugin import GUARD, hook
        payload = {"tool_name": "Bash", "cwd": "/", "tool_input": {"command": cmd}}
        if agent:
            payload["agent_type"] = agent
        return hook(GUARD, payload)[0]

    def test_no_subagent_writes_an_adopt(self):
        for agent in ("whynot-cut:qc-reviewer", "whynot-cut:client-researcher", "whynot-cut:setup-doctor",
                      "whynot-cut:intake-inspector", "general-purpose"):
            with self.subTest(agent=agent):
                self.assertEqual(self.bash("reel ref-style --root . --adopt R02 --yes", agent), 2)
                self.assertEqual(self.bash("reel ref-style --root . --yes --adopt=R02", agent), 2)
                self.assertEqual(self.bash("reel ref-style --root . --adopt R02", agent), 0)     # the diff: fine

    def test_the_lead_writes_it(self):
        self.assertEqual(self.bash("reel ref-style --root . --adopt R02 --yes", None), 0)


class TestCli(Base):
    def reel(self, *argv):
        cmd = [sys.executable, "-B", str(CLI), "--root", str(self.root), "ref-style", *argv]
        e = {k: v for k, v in env().items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
        lead_steps.issue_for(cmd[3:], e)    # BL-15: the lead's token
        r = subprocess.run(cmd, capture_output=True, env=e)
        return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8", "replace")

    def test_adopt_is_a_writer_only_with_yes(self):
        m = cli_module()
        ns = dict(cmd="ref-style", record=False, apply=False, root=str(self.root))
        self.assertFalse(m.writes(argparse.Namespace(**ns, adopt="R02", yes=False)))
        self.assertTrue(m.writes(argparse.Namespace(**ns, adopt="R02", yes=True)))
        self.assertFalse(m.writes(argparse.Namespace(**ns, adopt=None, yes=False)))

    def test_dry_run_then_yes(self):
        self.video("R02", R02)
        code, out, err = self.reel("--adopt", "R02")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(json.loads(out)["dry_run"])
        self.assertFalse(self.sdir.exists())
        code, out, err = self.reel("--adopt", "R02", "--yes")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(json.loads(out)["dry_run"])
        self.assertEqual(self.client_style()["rules"]["captions"], R02["rules"]["captions"])

    def test_one_action_at_a_time(self):
        self.video("R02", R02)
        code, out, _err = self.reel("--adopt", "R02", "--record")
        self.assertEqual(code, 2, out)
        self.assertIn("refused", json.loads(out))
        self.assertFalse(self.sdir.exists())

    def test_yes_without_adopt_is_refused(self):
        before = tree(self.root)
        code, out, _err = self.reel("--yes")
        self.assertEqual(code, 2, out)
        self.assertEqual({k: v for k, v in tree(self.root).items() if "logs" not in k and ".whynot-lock" not in k},
                         {k: v for k, v in before.items()})

    def test_an_adopt_refusal_exits_2(self):
        code, out, _err = self.reel("--adopt", "R99", "--yes")
        self.assertEqual(code, 2, out)
        self.assertIn("R99", json.loads(out)["refused"])
        self.assertFalse(self.sdir.exists())


if __name__ == "__main__":
    unittest.main()
