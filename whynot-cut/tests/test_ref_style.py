"""Client-level reference style (Stage 5): authored once per client, reused by every video, flagged when the reference
edits in data/ change.
Run:  ~/.whynot-cut/venv/bin/python -m unittest discover -s <plugin>/tests -v
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402

CLI = SK / "engine/reel/cli.py"
STALE = "reference style stale — refresh client style + reel-profile style.json/notes.md"


def make_client(tmp) -> Path:
    root = Path(tmp) / "CL"
    for d in ("assets/Brand", "data/Raw", "data/References"):
        (root / d).mkdir(parents=True)
    (root / "data/Raw/C0001.MP4").write_bytes(b"raw-one")
    (root / "data/Raw/C0002.MP4").write_bytes(b"raw-two")
    (root / "data/References/style.md").write_text("# Style\nHard cuts, boxed captions.\n", encoding="utf-8")
    (root / "data/References/ref_reel.mp4").write_bytes(b"reference-video")
    return root


def author(root: Path, cpm=10.0):
    d = root / "output/client_database/reference_style"
    d.mkdir(parents=True, exist_ok=True)
    (d / "editing-style-analysis.md").write_text("# Reference style\nmeasured: 10 cuts/min\n", encoding="utf-8")
    write_json(d / "editing-style.json", {"measured": {"cuts_per_minute": cpm}, "captions": {"box": True, "size": 62}})
    write_json(d / "editing-rules.json", {"mandatory": ["hard cuts"], "preferences": ["boxed captions"],
                                          "optional": [], "conflicts": []})
    return d


def bump_mtime(f: Path, by: int = 30):
    st = f.stat()
    os.utime(f, (st.st_atime + by, st.st_mtime + by))


def reel(root: Path, *argv, video_id=None):
    cmd = [sys.executable, str(CLI), "--root", str(root)] + (["--video-id", video_id] if video_id else []) + list(argv)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (json.loads(r.stdout) if r.stdout.strip().startswith("{") else r.stdout), r.stderr


class TestFingerprint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_client(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reference_set_is_only_the_reference_edits(self):
        from lib.ref_style import reference_set
        refs = {r["rel"]: r["role"] for r in reference_set(self.root)}
        self.assertEqual(refs, {"data/References/style.md": "editing_reference_doc",
                                "data/References/ref_reel.mp4": "editing_reference_video"})

    def test_fingerprint_changes_on_add_edit_remove(self):
        from lib.ref_style import fingerprint, reference_set
        fp0 = fingerprint(reference_set(self.root))
        self.assertEqual(fp0, fingerprint(reference_set(self.root)))                 # stable
        (self.root / "data/Raw/C0003.MP4").write_bytes(b"new raw clip")
        self.assertEqual(fp0, fingerprint(reference_set(self.root)))                 # footage is not a reference
        new = self.root / "data/References/second.mp4"
        new.write_bytes(b"another reference")
        fp1 = fingerprint(reference_set(self.root))
        self.assertNotEqual(fp0, fp1)                                               # added
        bump_mtime(self.root / "data/References/style.md")
        fp2 = fingerprint(reference_set(self.root))
        self.assertNotEqual(fp1, fp2)                                               # edited (touched)
        new.unlink()
        self.assertNotEqual(fp2, fingerprint(reference_set(self.root)))             # removed


class TestClientStyle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_client(self.tmp.name)
        common.set_context(self.root)

    def tearDown(self):
        common.set_context(None)
        self.tmp.cleanup()

    def test_missing_then_unrecorded_then_current(self):
        from lib import ref_style
        s = ref_style.state(self.root)
        self.assertEqual(s["state"], "missing")
        self.assertIn("editing-rules.json", s["message"])
        author(self.root)
        self.assertEqual(ref_style.state(self.root)["state"], "unrecorded")
        r = ref_style.record(self.root, by="client-researcher")
        self.assertTrue(r["ok"], r)
        self.assertEqual(ref_style.state(self.root)["state"], "current")
        rec = read_json(self.root / "output/client_database/reference_style/reference-set.json")
        self.assertEqual({x["rel"] for x in rec["references"]},
                         {"data/References/style.md", "data/References/ref_reel.mp4"})

    def test_record_refuses_incomplete_rules(self):
        from lib import ref_style
        d = author(self.root)
        write_json(d / "editing-rules.json", {"mandatory": []})
        r = ref_style.record(self.root)
        self.assertFalse(r["ok"])
        self.assertTrue(any("conflicts" in x for x in r["problems"]), r["problems"])
        (d / "editing-style-analysis.md").unlink()
        self.assertTrue(any("editing-style-analysis.md" in x for x in ref_style.record(self.root)["problems"]))

    def test_stale_lists_what_changed(self):
        from lib import ref_style
        author(self.root)
        ref_style.record(self.root)
        (self.root / "data/References/new_ref.mp4").write_bytes(b"new")
        bump_mtime(self.root / "data/References/style.md")
        (self.root / "data/References/ref_reel.mp4").unlink()
        s = ref_style.state(self.root)
        self.assertEqual(s["state"], "stale")
        self.assertEqual(s["added"], ["data/References/new_ref.mp4"])
        self.assertEqual(s["changed"], ["data/References/style.md"])
        self.assertEqual(s["removed"], ["data/References/ref_reel.mp4"])
        self.assertIn(STALE, s["message"])
        self.assertIn("ref-style --record", s["message"])

    def test_rerecord_warns_when_profile_style_not_refreshed(self):
        from lib import ref_style
        prof = self.root / common.CLIENT_PROFILE_REL
        prof.mkdir(parents=True)
        write_json(prof / "style.json", {"remove_pauses": {"min_pause_ms": 300}})
        (prof / "notes.md").write_text("# notes\n", encoding="utf-8")
        author(self.root)
        self.assertEqual(ref_style.record(self.root)["warnings"], [])
        old = 1_600_000_000                                     # the profile was last written long before
        for f in ("style.json", "notes.md"):
            os.utime(prof / f, (old, old))
        (self.root / "data/References/new_ref.mp4").write_bytes(b"new")
        w = ref_style.record(self.root)["warnings"]
        self.assertTrue(any("style.json" in x for x in w), w)
        self.assertTrue(any("notes.md" in x for x in w), w)
        self.assertTrue(any("unchanged" in x and "editing-style.json" in x for x in w), w)   # client style not touched

    def test_apply_reuses_one_style_for_two_videos_with_overrides(self):
        from lib import ref_style
        author(self.root)
        ref_style.record(self.root)
        v1, v2 = Paths(self.root, "C0001"), Paths(self.root, "C0002")
        for v in (v1, v2):
            v.ensure_project()
        write_json(v2.p("01_analysis/editing-style-overrides.json"),
                   {"reason": "this reel is a list", "style": {"captions": {"size": 58}}, "rules": {"preferences": ["checklist"]}})
        a1, a2 = ref_style.apply(v1), ref_style.apply(v2)
        self.assertTrue(a1["ok"] and a2["ok"], (a1, a2))
        s1 = read_json(v1.p("01_analysis/editing-style.json"))
        s2 = read_json(v2.p("01_analysis/editing-style.json"))
        self.assertEqual(s1["captions"], {"box": True, "size": 62})
        self.assertEqual(s2["captions"], {"box": True, "size": 58})                 # per-video override only
        self.assertEqual(s1["measured"], s2["measured"])                            # the same client style
        self.assertEqual(s1["_reference_style"]["fingerprint"], ref_style.state(self.root)["fingerprint"])
        r2 = read_json(v2.p("01_analysis/editing-rules.json"))
        self.assertEqual(r2["preferences"], ["boxed captions", "checklist"])
        self.assertEqual(read_json(v1.p("01_analysis/editing-rules.json"))["preferences"], ["boxed captions"])
        self.assertEqual(ref_style.video_state(v1)["state"], "current")
        # the client style is refined later -> both copies are outdated, neither is silently changed
        author(self.root, cpm=12.0)
        self.assertEqual(ref_style.video_state(v1)["state"], "outdated")
        self.assertEqual(read_json(v1.p("01_analysis/editing-style.json"))["measured"]["cuts_per_minute"], 10.0)
        # a new override after the copy -> outdated too
        ref_style.record(self.root)
        ref_style.apply(v2)
        (self.root / "data/References/extra.md").write_text("# one more reference\n", encoding="utf-8")
        ref_style.record(self.root)            # re-recorded, style files unchanged -> the copy still holds
        self.assertEqual(ref_style.video_state(v2)["state"], "current")
        write_json(v2.p("01_analysis/editing-style-overrides.json"), {"style": {"captions": {"size": 50}}})
        self.assertEqual(ref_style.video_state(v2)["state"], "outdated")

    def test_apply_refuses_until_client_style_current(self):
        from lib import ref_style
        v = Paths(self.root, "C0001")
        v.ensure_project()
        r = ref_style.apply(v)
        self.assertFalse(r["ok"])
        self.assertFalse(v.p("01_analysis/editing-style.json").exists())
        author(self.root)
        ref_style.record(self.root)
        (self.root / "data/References/new_ref.mp4").write_bytes(b"new")
        r = ref_style.apply(v)
        self.assertFalse(r["ok"])
        self.assertIn(STALE, r["blocked"])

    def test_apply_keeps_a_legacy_per_video_style(self):
        from lib import ref_style
        v = Paths(self.root, "C0001")
        v.ensure_project()
        write_json(v.p("01_analysis/editing-style.json"), {"authored": "per video, before client-level style"})
        self.assertEqual(ref_style.video_state(v)["state"], "legacy")
        author(self.root)
        ref_style.record(self.root)
        self.assertTrue(ref_style.apply(v)["ok"])
        self.assertEqual(read_json(v.p("01_analysis/editing-style.legacy.json"))["authored"],
                         "per video, before client-level style")

    def test_client_level_measurements_without_a_video(self):
        from lib.common import ffmpeg_exe
        from lib.ref_analysis import analyze_all
        ref = self.root / "data/References/ref_reel.mp4"
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=216x384:r=25:d=2",
                        "-pix_fmt", "yuv420p", str(ref)], check=True)
        res = analyze_all(Paths(self.root), [ref], {str(ref): 2.0})
        self.assertEqual(len(res["references"]), 1)
        self.assertTrue((self.root / "output/client_database/reference_analysis/cache.json").exists())
        self.assertFalse((self.root / "output/projects").exists())


class TestReelNext(unittest.TestCase):
    """`reel next` asks for the client style once, reuses it after, and flags it when references change."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_client(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def remaining(self, vid):
        code, out, err = reel(self.root, "next", video_id=vid)
        self.assertEqual(code, 0, err)
        return out

    def test_author_once_reuse_then_stale(self):
        out = self.remaining("C0001")
        self.assertTrue(any(s.startswith("AUTHOR client reference style") for s in out["remaining"]), out["remaining"])
        self.assertFalse(any("01_analysis/editing-style.json" in s for s in out["remaining"]))
        self.assertEqual(out["reference_style"]["state"], "missing")
        author(self.root)
        code, rec, err = reel(self.root, "ref-style", "--record", "--by", "client-researcher")
        self.assertEqual(code, 0, err)
        self.assertTrue(rec["ok"], rec)
        for vid in ("C0001", "C0002"):                     # current: no video asks to re-author
            out = self.remaining(vid)
            self.assertFalse(any("AUTHOR client reference style" in s or "stale" in s for s in out["remaining"]),
                             out["remaining"])
            self.assertIn("ref-style --apply", " ".join(out["remaining"]))
            code, ap, err = reel(self.root, "ref-style", "--apply", video_id=vid)
            self.assertEqual(code, 0, err)
            self.assertTrue(ap["ok"], ap)
            out = self.remaining(vid)
            self.assertFalse(any("ref-style" in s or "editing-style" in s for s in out["remaining"]), out["remaining"])
            self.assertEqual(out["reference_style"]["state"], "current")
        bump_mtime(self.root / "data/References/ref_reel.mp4")
        out = self.remaining("C0002")
        hit = [s for s in out["remaining"] if s.startswith(STALE)]
        self.assertTrue(hit, out["remaining"])
        self.assertIn("data/References/ref_reel.mp4", hit[0])
        code, st, _ = reel(self.root, "ref-style")
        self.assertEqual(st["state"], "stale")
        code, ap, _ = reel(self.root, "ref-style", "--apply", video_id="C0001")
        self.assertEqual(code, 2)                          # never copies a stale style

    def test_ref_analyze_step_not_needed_once_the_style_is_copied(self):
        write_json(self.root / "output/discovery/input-inventory.json", {"files": [
            {"path": str(self.root / "data/References/ref_reel.mp4"), "rel": "data/References/ref_reel.mp4",
             "role": "editing_reference_video", "kind": "video"}]})
        author(self.root)
        reel(self.root, "ref-style", "--record")
        self.assertIn("ref-analyze", self.remaining("C0002")["remaining"])     # measurements + copy still to do
        reel(self.root, "ref-style", "--apply", video_id="C0002")
        self.assertNotIn("ref-analyze", self.remaining("C0002")["remaining"])  # measured per client, style copied

    def test_legacy_video_style_is_not_reauthored(self):
        v = Paths(self.root, "C0001")
        v.ensure_project()
        write_json(v.p("01_analysis/editing-style.json"), {"authored": "per video"})
        out = self.remaining("C0001")
        self.assertFalse(any("reference style" in s or "editing-style" in s for s in out["remaining"]), out["remaining"])
        self.assertTrue(any("client reference style" in n for n in out["notices"]), out)

    def test_plan_points_to_apply_when_style_missing(self):
        v = Paths(self.root, "C0001")
        v.ensure_project()
        author(self.root)
        reel(self.root, "ref-style", "--record")
        code, out, err = reel(self.root, "plan", video_id="C0001")
        self.assertIn("01_analysis/editing-style.json", out["missing_semantic_files"])
        self.assertIn("ref-style --apply", out["how"])


class TestDiscoveryDocs(unittest.TestCase):
    def test_document_without_reference_hint_is_unclassified(self):
        from lib.discover import discover
        with tempfile.TemporaryDirectory() as t:
            root = make_client(t)
            (root / "data/notes.md").write_text("random notes\n", encoding="utf-8")
            (root / "data/Music").mkdir()
            write_json(root / "data/Music/music.json", {"tracks": []})
            inv = discover(Paths(root), read_docs=False)["inventory"]
            roles = {f["rel"]: f["role"] for f in inv["files"]}
            self.assertEqual(roles["data/References/style.md"], "editing_reference_doc")
            self.assertEqual(roles["data/notes.md"], "unclassified")
            self.assertEqual(roles["data/Music/music.json"], "unclassified")
            warn = [w for w in inv["warnings"] if "data/notes.md" in w]
            self.assertTrue(warn and "data/References" in warn[0], inv["warnings"])
            self.assertFalse(any("music.json" in w for w in inv["warnings"]), inv["warnings"])


class TestHooksAndGuard(unittest.TestCase):
    def test_session_context_flags_stale_reference_style(self):
        from test_plugin import CTX, hook
        from lib import ref_style
        with tempfile.TemporaryDirectory() as t:
            root = make_client(t)
            author(root)
            ref_style.record(root)
            code, out, _ = hook(CTX, {"cwd": str(root)})
            self.assertNotIn("stale", json.loads(out)["hookSpecificOutput"]["additionalContext"])
            (root / "data/References/new_ref.mp4").write_bytes(b"new")
            code, out, _ = hook(CTX, {"cwd": str(root)})
            self.assertEqual(code, 0)
            self.assertIn(STALE, json.loads(out)["hookSpecificOutput"]["additionalContext"])

    def test_qc_reviewer_cannot_record_or_apply(self):
        from test_plugin import GUARD, hook

        def bash(cmd):
            return hook(GUARD, {"tool_name": "Bash", "agent_type": "whynot-cut:qc-reviewer", "cwd": "/",
                                "tool_input": {"command": cmd}})[0]
        self.assertEqual(bash("reel ref-style --root . --record"), 2)
        self.assertEqual(bash("reel ref-style --root . --video-id C1 --apply"), 2)
        self.assertEqual(bash("reel ref-style --root ."), 0)


class TestDocsMatchEngine(unittest.TestCase):
    """What the engine checks is what the docs tell the agents to write."""
    def test_client_level_files_documented(self):
        from lib import ref_style
        for rel in ("skills/client-craft/SKILL.md", "skills/client-craft/references/editing-reference-analysis.md",
                    "agents/client-researcher.md"):
            txt = (SK / rel).read_text(encoding="utf-8")
            self.assertIn("reference_style/", txt, rel)
            self.assertIn("ref-style --record", txt, rel)
        ref = (SK / "skills/client-craft/references/editing-reference-analysis.md").read_text(encoding="utf-8")
        for f in ref_style.FILES + ref_style.RULE_KEYS:
            self.assertIn(f, ref)
        for rel in ("skills/story-craft/SKILL.md", "agents/story-editor.md", "skills/edit/SKILL.md"):
            txt = (SK / rel).read_text(encoding="utf-8")
            self.assertIn("ref-style --apply", txt, rel)
            self.assertIn("editing-style-overrides.json", txt, rel)

    def test_no_doc_asks_for_per_video_reauthoring(self):
        for f in list((SK / "skills").rglob("*.md")) + list((SK / "agents").glob("*.md")):
            self.assertNotIn("01_analysis/editing-style-analysis.md", f.read_text(encoding="utf-8"), f)


if __name__ == "__main__":
    unittest.main()
