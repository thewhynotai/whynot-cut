"""3.0 F1 (Adobe track live round-trip): a still placed in Premiere is always the one drawn from the CURRENT plan.

`reel previews` records, next to the stills, what each one was drawn from (03_broll/.stills-manifest.json: a hash of the
event, its template, the brand inputs and the renderer, plus the plan fingerprint and each file's hash). Every build that
places those stills (ppro-build, the `reel serve` build, the preview video, the XML fallback) compares that record with
the plan as it is now and redraws, through the same previews code, only the stills that no longer match. A 2.x folder
(stills, no record) is redrawn once. A redraw that fails stops the build with one plain fix.

Fictional example-clinic data only; the bridge is faked (no Premiere), the engine home is the test sandbox.
Run one file: tools/test.sh -p test_previews_stills_manifest.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import hashlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import common  # noqa: E402
from lib.common import Context, Paths, read_json, write_json  # noqa: E402

MANIFEST = "03_broll/.stills-manifest.json"
HOOK = "هل في حاجات معينة"
NEW_HOOK = "قبل الليزر اعرف دول"


def decisions(hook=HOOK, name="د/ سلمى المثال"):
    """Three graphics of a fictional clinic reel: a hook bar (3 stills), a checklist (title + items) and a name card."""
    return {"video_id": "CLIP1", "global": {"main_footage": "data/Raw/CLIP1.mov"},
            "caption_highlights": [{"text": "التشخيص الصحيح", "at": "00:00:08.600"}],
            "decisions": [
                {"decision_id": "EDIT_001", "segment_id": "SEG_001", "evidence": "هل في حاجات معينة",
                 "start": "00:00:00.200", "end": "00:00:04.000", "semantic_intent": "hook", "visual_treatment": "hook",
                 "confidence": "high",
                 "graphics": [{"id": "GFX_001", "template": "hook_title", "start": "00:00:00.200",
                               "end": "00:00:03.500", "text": hook}]},
                {"decision_id": "EDIT_002", "segment_id": "SEG_002", "evidence": "أول حاجة التشخيص الصحيح",
                 "start": "00:00:05.000", "end": "00:00:10.000", "semantic_intent": "point", "visual_treatment": "list",
                 "confidence": "high",
                 "graphics": [{"id": "GFX_002", "template": "checklist", "start": "00:00:05.000", "end": "00:00:09.000",
                               "text": "x", "title": "خطوات",
                               "items": [{"text": "التشخيص", "at": "00:00:06.000"},
                                         {"text": "Isotretinoin", "at": "00:00:07.500", "latin": True}]},
                              {"id": "GFX_003", "template": "name_card", "start": "00:00:09.000", "end": "00:00:11.500",
                               "name": name, "lines": ["عيادة المثال"]}]}]}


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class _Reel(unittest.TestCase):
    """A planned, previewed fictional reel per test (each test changes it)."""

    def setUp(self):
        import test_pipeline as T
        from lib.client_db import build as build_db
        from lib.discover import run_discovery
        from lib.media import preflight
        from lib.previews import render_all
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root, self.p, _ = T.make_project(self.tmp)
        cm = common.use_context(Context(self.root, home=self.tmp / "home"))
        cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        build_db(self.p, run_discovery(self.p)["inventory"])
        preflight(self.p, [self.root / "data/Raw/CLIP1.mov"])
        for f in ("main-topic.md", "medical-content-review.md"):
            (self.p.p("01_analysis") / f).write_text("# stub\n", encoding="utf-8")
        for f in ("narrative-segments.json", "transcript-semantic-analysis.json", "editing-style.json"):
            write_json(self.p.p("01_analysis") / f, {"stub": True})
        self.replan()
        render_all(self.p, composite_preview=True)          # what `reel previews` does

    def replan(self, **kw):
        from lib.plan import compile_plan
        write_json(self.p.p("01_analysis/edit-decisions.json"), decisions(**kw))
        r = compile_plan(self.p)
        self.assertTrue(r["ok"], r.get("errors"))

    def still(self, name: str) -> Path:
        hit = sorted(self.p.p("03_broll").rglob(name))
        self.assertTrue(hit, f"no {name}")
        return hit[0]

    def snapshot(self) -> dict:
        """{still: (sha256, mtime_ns)} of every event still (captions are drawn per build anyway)."""
        return {f.relative_to(self.p.project).as_posix(): (sha(f), f.stat().st_mtime_ns)
                for f in self.p.p("03_broll").rglob("GFX_*.png")}

    def events(self) -> list:
        from lib.stamps import read_compiled
        return [e["event_id"] for e in read_compiled(self.p.p("01_analysis/timeline-spec.json"))["events"]]

    def stale(self) -> list:
        from lib.previews import stale_stills
        return stale_stills(self.p)["stale"]


class TestStillsManifest(_Reel):
    def test_previews_record_what_each_still_was_drawn_from(self):
        from lib.plan import plan_fingerprint
        man = read_json(self.p.p(MANIFEST))
        self.assertIsInstance(man, dict)
        self.assertEqual(man["plan_fingerprint"], plan_fingerprint(self.p))
        self.assertTrue(man["renderer"])
        self.assertEqual(sorted(man["events"]), sorted(self.events()))
        files = man["events"]["GFX_001"]["files"]
        self.assertEqual(sorted(Path(f).name for f in files), ["GFX_001.png", "GFX_001_bar.png", "GFX_001_fg.png"])
        self.assertIn("GFX_002_title.png", [Path(f).name for f in man["events"]["GFX_002"]["files"]])
        self.assertIn("GFX_002_i2.png", [Path(f).name for f in man["events"]["GFX_002"]["files"]])
        for ev in man["events"].values():
            self.assertRegex(ev["inputs"], r"^[0-9a-f]{64}$")
            for rel, digest in ev["files"].items():
                self.assertEqual(sha(self.p.p(rel)), digest, rel)
        self.assertEqual(self.stale(), [])

    def test_fresh_stills_are_not_redrawn(self):
        from lib import previews
        before = self.snapshot()
        with mock.patch.object(previews, "render_event", side_effect=AssertionError("redrawn")) as re:
            r = previews.ensure_fresh_stills(self.p)
        self.assertEqual(r["redrawn"], [])
        self.assertEqual(re.call_count, 0)
        self.assertEqual(self.snapshot(), before)                  # byte-identical, not even rewritten

    def test_changed_wording_redraws_only_that_graphic(self):
        from lib import previews
        before = self.snapshot()
        self.replan(hook=NEW_HOOK)                                  # `reel plan` again, no `reel previews`
        st = previews.stale_stills(self.p)
        self.assertEqual(st["stale"], ["GFX_001"])
        self.assertIn("plan", st["why"]["GFX_001"])
        r = previews.ensure_fresh_stills(self.p)
        self.assertEqual(r["redrawn"], ["GFX_001"])
        after = self.snapshot()
        for rel, (digest, mtime) in before.items():
            if "/GFX_001" in rel and not rel.endswith("_bar.png"):
                self.assertNotEqual(after[rel][0], digest, rel)    # the new wording is in the still
            elif "/GFX_001" not in rel:
                self.assertEqual(after[rel], (digest, mtime), rel)  # the others are not touched
        self.assertEqual(self.stale(), [])
        redrawn = {rel: d for rel, (d, _m) in after.items()}
        previews.render_all(self.p, composite_preview=True)       # a full `reel previews` draws the very same stills
        self.assertEqual({rel: d for rel, (d, _m) in self.snapshot().items()}, redrawn)

    def test_a_2x_folder_without_a_record_is_redrawn_once_to_the_same_stills(self):
        from lib import previews
        before = {rel: d for rel, (d, _m) in self.snapshot().items()}
        self.p.p(MANIFEST).unlink()
        st = previews.stale_stills(self.p)
        self.assertEqual(sorted(st["stale"]), sorted(self.events()))
        self.assertTrue(all("no record" in w for w in st["why"].values()), st["why"])
        r = previews.ensure_fresh_stills(self.p)
        self.assertEqual(sorted(r["redrawn"]), sorted(self.events()))
        self.assertTrue(self.p.p(MANIFEST).exists())
        self.assertEqual({rel: d for rel, (d, _m) in self.snapshot().items()}, before)
        self.assertEqual(self.stale(), [])

    def test_a_still_changed_or_removed_on_disk_is_redrawn(self):
        self.still("GFX_003.png").write_bytes(self.still("GFX_001.png").read_bytes())
        self.assertEqual(self.stale(), ["GFX_003"])
        self.still("GFX_001_bar.png").unlink()
        self.assertEqual(self.stale(), ["GFX_001", "GFX_003"])
        from lib.previews import ensure_fresh_stills
        self.assertEqual(ensure_fresh_stills(self.p)["redrawn"], ["GFX_001", "GFX_003"])
        self.assertEqual(self.stale(), [])

    def test_a_brand_change_redraws_every_still(self):
        tok_p = self.p.client_db / "branding/brand-tokens.json"
        tok = read_json(tok_p)
        tok.setdefault("roles", {}).setdefault("primary", {})["hex"] = "#7A2E8C"
        write_json(tok_p, tok)
        self.assertEqual(sorted(self.stale()), sorted(self.events()))

    def test_a_readability_threshold_change_redraws_every_still(self):     # F1 review minor 1
        # a client's motion.json may raise min_contrast: the brand colour may now fall back to white in the still
        from lib import motion_config
        cfg = dict(motion_config.motion_cfg(), min_contrast=7.0)
        with mock.patch.object(motion_config, "motion_cfg", return_value=cfg):
            self.assertEqual(sorted(self.stale()), sorted(self.events()))
        self.assertEqual(self.stale(), [])                        # back to the recorded thresholds: nothing stale

    def test_a_redraw_that_fails_says_the_one_fix_in_plain_words(self):
        from lib import previews
        from lib.errors import Guidance
        self.replan(hook=NEW_HOOK)
        locked = RuntimeError("GFX_001.png changed but is locked by another program.")
        with mock.patch.object(previews, "render_event", side_effect=locked):
            with self.assertRaises(Guidance) as cm:
                previews.ensure_fresh_stills(self.p)
        e = cm.exception
        self.assertIn("locked by another program", e.error)
        self.assertIn("reel previews", e.how)
        for jargon in ("manifest", "fingerprint", "hash", "inputs"):
            self.assertNotIn(jargon, (e.error + " " + e.how).lower())
        self.assertEqual(self.stale(), ["GFX_001"])                 # nothing pretends to be current


def ready_response(data: dict, prproj: Path) -> dict:
    """Premiere's answer to build_project when everything worked (the fake bridge)."""
    from test_frame_size import ready_response as ready
    return ready(data, prproj)


class TestBuildsPlaceCurrentStills(_Reel):
    def prproj(self) -> Path:
        return self.p.p(f"07_premiere/project/{self.p.video_id}_{common.project_prefix()}_EDIT.prproj")

    def build(self, fn=None):
        """ppro_build.build (or `fn`) with a fake bridge that answers like a Premiere where everything worked."""
        from lib import ppro_build
        sent, prproj = [], self.prproj()

        def submit(action, data=None, timeout=0, **kw):
            sent.append((action, data))
            return ready_response(data, prproj)
        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                mock.patch("lib.ppro_bridge.submit", side_effect=submit):
            r = (fn or ppro_build.build)(self.p)
        return r, sent

    def placed(self, sent: list, gid: str) -> Path:
        job = next(d for a, d in sent if a == "build_project")
        return Path(next(g["png"] for g in job["graphics"] if g["id"] == gid))

    def test_ppro_build_redraws_a_stale_still_before_placing_it(self):
        old = sha(self.still("GFX_001_fg.png"))
        self.replan(hook=NEW_HOOK)
        r, sent = self.build()
        self.assertEqual(r["status"], "PRPROJ_BUILT", r.get("checks"))
        self.assertEqual(r["stills_redrawn"], ["GFX_001"])
        staged = self.placed(sent, "GFX_001_fg")
        self.assertEqual(sha(staged), sha(self.still("GFX_001_fg.png")))     # Premiere gets the redrawn still
        self.assertNotEqual(sha(staged), old)
        self.assertEqual(self.stale(), [])

    def test_an_unchanged_plan_builds_without_redrawing(self):
        from lib import previews
        before = self.snapshot()
        with mock.patch.object(previews, "render_all", side_effect=AssertionError("redrawn")):
            r, _sent = self.build()
        self.assertEqual(r["status"], "PRPROJ_BUILT", r.get("checks"))
        self.assertNotIn("stills_redrawn", r)
        self.assertEqual(self.snapshot(), before)

    def test_a_failed_redraw_stops_the_build_before_premiere_gets_anything(self):
        from lib import previews
        self.replan(hook=NEW_HOOK)
        with mock.patch.object(previews, "render_event", side_effect=RuntimeError("disk said no")):
            r, sent = self.build()
        self.assertEqual(r["status"], "STILLS_OUT_OF_DATE")
        self.assertIs(r["ok"], False)
        self.assertIn("reel previews", r["how"])
        self.assertNotIn("build_project", [a for a, _d in sent])
        self.assertFalse(self.prproj().exists())
        from lib.errors import exit_code
        self.assertEqual(exit_code(r), 1)

    def test_a_2x_folder_is_redrawn_once_at_its_first_build(self):
        self.p.p(MANIFEST).unlink()
        r, sent = self.build()
        self.assertEqual(r["status"], "PRPROJ_BUILT", r.get("checks"))
        self.assertEqual(sorted(r["stills_redrawn"]), sorted(self.events()))
        self.assertTrue(self.p.p(MANIFEST).exists())
        self.prproj().unlink()
        r2, _ = self.build()
        self.assertNotIn("stills_redrawn", r2)                      # the second build has nothing to redraw

    def test_the_serve_build_redraws_too(self):
        from lib import ppro_build
        from lib.plan import APPROVAL_FORMAT, plan_fingerprint
        self.replan(hook=NEW_HOOK)                  # re-planned and re-approved, `reel previews` never run again
        write_json(self.p.p("01_analysis/plan-approval.json"),
                   {"approved": True, "by": "editor", "plan_fingerprint": plan_fingerprint(self.p),
                    "format": APPROVAL_FORMAT})
        r, sent = self.build(lambda p: ppro_build.build_for_serve({"project_path": str(self.prproj())}))
        self.assertEqual(r["status"], "PRPROJ_BUILT", r)
        self.assertEqual(r["stills_redrawn"], ["GFX_001"])
        self.assertEqual(sha(self.placed(sent, "GFX_001_fg")), sha(self.still("GFX_001_fg.png")))

    def test_the_preview_video_the_editor_watches_uses_current_stills(self):
        from lib.preview_video import render
        self.replan(hook=NEW_HOOK)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            r = render(self.p, width=270, label=False)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r.get("stills_redrawn"), ["GFX_001"])
        self.assertEqual(self.stale(), [])

    def test_the_xml_fallback_uses_current_stills(self):
        from lib.premiere_xml import build_xml
        self.replan(hook=NEW_HOOK)
        tm = build_xml(self.p, prefer_ae_renders=False)
        self.assertEqual([m for m in tm["missing_events"] if m.startswith("GFX")], [])     # (no SFX made here)
        self.assertEqual(tm.get("stills_redrawn"), ["GFX_001"])
        self.assertEqual(self.stale(), [])


if __name__ == "__main__":
    unittest.main()
