"""3.0 T2.6 (engine IM-9): the editor handoff README follows what was really built.
A native Premiere build (`ppro-build-result.json` PRPROJ_BUILT*) gets "open the .prproj" (track map, caption lanes,
nothing to import); only the XML fallback gets the import steps; After Effects / Photoshop rows appear only when those
extras were used; a "Licensed material" section appears only when `05_assets/magnific-manifest.json` exists. Golden
READMEs (native, XML fallback, motion) live in tests/fixtures/handoff/; set UPDATE_GOLDEN=1 to rewrite them.
Run:  <engine venv python> -m unittest discover -s <plugin>/tests -v
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib.common import Paths, set_context, write_json  # noqa: E402
from lib.handoff import build, motion_readme  # noqa: E402
from lib.plan import APPROVAL_FORMAT, plan_fingerprint  # noqa: E402

GOLDEN = SK / "tests" / "fixtures" / "handoff"

NATIVE_NAMES = {
    "video": ["V1 Main Footage", "V2 B-roll (full screen)", "V3 Graphic bars (sweep)", "V4 Graphic text",
              "V5 Cards (closing glass)", "V6 Caption bars (sweep)", "V7 Captions (animated)", "V8 Transitions"],
    "audio": ["A1 Dialogue (clean) L", "A2 Dialogue (clean) R", "A3 SFX L", "A4 SFX R"]}


def normalise(text: str, root: Path) -> str:
    """Strip what differs between runs and machines: the timestamp, the temp root, path separators."""
    for form in (str(root), root.as_posix(), str(root.resolve()), root.resolve().as_posix()):
        text = text.replace(form, "<ROOT>")
    text = text.replace("\\", "/")
    text = re.sub(r"\d{4}-\d\d-\d\dT[\d:.]+(?:Z|[+-]\d\d:\d\d)?", "<TS>", text)
    return text.rstrip() + "\n"


def spec() -> dict:
    ev = [{"event_id": "GFX_001", "template": "statement_bar", "track": 3, "start_frame": 10, "end_frame": 80,
           "start_tc": "00:00:00:10", "approval_required": True, "evidence": "الصداع النصفي مش دايماً من التوتر",
           "params": {"text": "x"}}]
    return {"generated": "2026-10-11T10:00:00", "video_id": "CLIP1", "fps": 24, "duration_ms": 12000,
            "duration_frames": 288, "main_footage": "data/Raw/CLIP1.mp4", "base_scale_percent": 100.0,
            "framing": {"aspect": "9:16", "mode": "center"}, "events": ev, "main_segments": [], "time_map": None}


def stored_prefix(test, root: Path, prefix: str = "RE"):
    """The goldens name files <id>_RE_…: the client stores that prefix (T3.10: a stored prefix is kept; without one the
    folder's initials apply), and the engine reads it through the client's Context."""
    write_json(root / "output/client_database/reel-profile/profile.json", {"prefix": prefix})
    set_context(root)
    test.addCleanup(set_context, None, None)


class HandoffFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "CLIENT"
        (self.root / "assets").mkdir(parents=True)
        (self.root / "data/Raw").mkdir(parents=True)
        stored_prefix(self, self.root)
        self.p = Paths(self.root, "CLIP1")
        self.p.ensure_project()
        write_json(self.p.p("01_analysis/timeline-spec.json"), spec())
        write_json(self.p.p("08_quality_control/qc-results.json"), {"ok": True})

    # ---- state builders
    def approve(self):
        write_json(self.p.p("01_analysis/plan-approval.json"),
                   {"approved": True, "by": "editor", "note": "", "at": "2026-10-11T10:00:00",
                    "plan_fingerprint": plan_fingerprint(self.p), "format": APPROVAL_FORMAT})

    def manifest(self, native: bool):
        tracks = {"video": [{"xml_index": 1, "id": "V1", "name": "Main footage", "clips": 3},
                            {"xml_index": 2, "id": "C02", "name": "Captions", "clips": 0}],
                  "audio": [{"xml_index": "1-2", "id": "A1", "name": "Dialogue (L/R mono pair)", "clips": 3}]}
        name = "base-manifest.json" if native else "timeline-manifest.json"
        xml = self.p.p(f"07_premiere/interchange/CLIP1_RE_EDIT{'_base' if native else ''}.xml")
        xml.parent.mkdir(parents=True, exist_ok=True)
        xml.write_text("<xmeml/>", encoding="utf-8")
        write_json(self.p.p(f"07_premiere/{name}"),
                   {"xml": str(xml), "sequence_name": "CLIP1_RE_EDIT", "fps": 24, "source_fps": 25.0,
                    "base_scale_percent": 100.0, "tracks": tracks,
                    "mode": "premiere_native_graphics" if native else "rendered_graphics_in_xml"})

    def native_build(self, status="PRPROJ_BUILT", failed_checks=()):
        self.manifest(native=True)
        prproj = self.p.p("07_premiere/project/CLIP1_RE_EDIT.prproj")
        prproj.parent.mkdir(parents=True, exist_ok=True)
        prproj.write_bytes(b"prproj")
        checks = {"prproj_saved_this_run": True, "frame_1080x1920": True, "fps_24": True, "linear_color_on": True,
                  "all_graphics_placed": True, "caption_track_ok": True, "dialogue_on_A1_A2": True}
        for c in failed_checks:
            checks[c] = False
        counts = [3, 0, 2, 2, 1, 4, 4, 0]
        write_json(self.p.p("07_premiere/ppro-build-result.json"), {
            "status": status, "checks": checks, "project": str(prproj), "at": "2026-10-11T11:00:00",
            "job_data": {"sequence_name": "CLIP1_RE_EDIT", "track_names": NATIVE_NAMES, "native_caption_track": True},
            "result": {"tracks": {"video": [{"i": i + 1, "name": n, "clips": counts[i]}
                                            for i, n in enumerate(NATIVE_NAMES["video"])],
                                  "audio": [{"i": i + 1, "name": n, "clips": 3 if i < 2 else 1}
                                            for i, n in enumerate(NATIVE_NAMES["audio"])]}}})

    def readme(self) -> str:
        build(self.p)
        return self.p.p("09_handoff/README.md").read_text(encoding="utf-8")

    def checklist(self) -> str:
        return self.p.p("09_handoff/final-editor-checklist.md").read_text(encoding="utf-8")

    def golden(self, name: str, text: str):
        got = normalise(text, self.root)
        path = GOLDEN / name
        if os.environ.get("UPDATE_GOLDEN") == "1":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(got, encoding="utf-8", newline="\n")
        self.assertTrue(path.exists(), f"golden file {path} is missing (UPDATE_GOLDEN=1 to write it)")
        self.assertEqual(got, path.read_text(encoding="utf-8"))

    def magnific(self, entries):
        write_json(self.p.p("05_assets/magnific-manifest.json"), {"entries": entries})


class TestNativeHandoff(HandoffFixture):
    def test_native_golden(self):
        self.approve()
        self.native_build()
        self.golden("native.md", self.readme())

    def test_native_says_open_the_project_and_has_no_xml_steps(self):
        self.native_build()
        md = self.readme()
        self.assertIn("`07_premiere/project/CLIP1_RE_EDIT.prproj`", md)     # relative, forward slashes on every OS
        for legacy in ("FCP7", "File › Import…", "Rename tracks", "Save As", "(AE render)", "SCRIPT ONLY"):
            self.assertNotIn(legacy, md)
        self.assertIn("V7 Captions (animated)", md)           # the caption lanes from the real track map
        self.assertIn("V6 Caption bars (sweep)", md)
        self.assertNotIn("## 2. After Effects", md)
        self.assertNotIn("## 3. Photoshop", md)

    def test_native_checklist_has_no_import_or_rename_steps(self):
        self.native_build()
        self.readme()
        cl = self.checklist()
        self.assertIn("CLIP1_RE_EDIT.prproj", cl)
        for legacy in ("Import XML", "Rename tracks", "Save As `.prproj`", "Spot-check every AE comp"):
            self.assertNotIn(legacy, cl)

    def test_built_with_issues_lists_the_failed_checks(self):
        self.native_build("PRPROJ_BUILT_WITH_ISSUES", failed_checks=("all_graphics_placed", "linear_color_on"))
        md = self.readme()
        self.assertIn("PRPROJ_BUILT_WITH_ISSUES", md)
        self.assertIn("all_graphics_placed", md)
        self.assertIn("linear_color_on", md)
        self.assertNotIn("FCP7", md)

    def test_readback_line_does_not_overclaim(self):
        self.native_build()
        self.assertIn("read-back: all 7 checks passed — nothing to set by hand", self.readme())
        self.native_build("PRPROJ_BUILT_WITH_ISSUES", failed_checks=("linear_color_on",))
        md = self.readme()
        self.assertIn("read-back: 6 of 7 passed — see the failures below", md)
        self.assertNotIn("nothing to set by hand", md)
        rec_p = self.p.p("07_premiere/ppro-build-result.json")
        import json
        rec = json.loads(rec_p.read_text(encoding="utf-8"))
        rec["checks"] = {}
        write_json(rec_p, rec)
        md = self.readme()
        self.assertIn("no read-back checks were recorded", md)
        self.assertNotIn("nothing to set by hand", md)
        self.assertNotIn("0 of 0", md)

    def test_track_map_falls_back_to_the_premiere_read_back(self):
        """A result written before 3.0 has no job_data: the map comes from what Premiere reported."""
        self.native_build()
        rec_p = self.p.p("07_premiere/ppro-build-result.json")
        import json
        rec = json.loads(rec_p.read_text(encoding="utf-8"))
        del rec["job_data"]
        write_json(rec_p, rec)
        md = self.readme()
        self.assertIn("V7 Captions (animated)", md)
        self.assertIn("A3 SFX L", md)

    def test_stale_approval_still_never_reads_approved_by(self):
        self.approve()
        self.native_build()
        spec2 = spec()
        spec2["duration_frames"] = 264
        write_json(self.p.p("01_analysis/timeline-spec.json"), spec2)
        md = self.readme()
        self.assertNotIn("approved by editor", md)
        self.assertIn("plan changed since approval — re-approve", md)


class TestBuildResultRecordsTheTrackMap(HandoffFixture):
    def test_ppro_build_writes_job_data_for_the_handoff(self):
        """`reel ppro-build` stores the names it gave the tracks (job_data.track_names), so the handoff can print them."""
        from unittest import mock
        from lib import ppro_build
        prj = self.p.p("07_premiere/project/CLIP1_RE_EDIT.prproj")
        prj.parent.mkdir(parents=True, exist_ok=True)
        data = {"_missing": [], "project_path": str(prj), "graphics": [], "native_caption_track": True,
                "sequence_name": "CLIP1_RE_EDIT", "track_names": NATIVE_NAMES, "markers": [], "srt_path": "x"}

        def submit(action, payload, timeout=0):
            prj.write_bytes(b"prproj")
            return {"ok": True, "response": {"result": {"settings_after": {}, "placed": [], "captionTrack": True,
                                                         "tracks": {"video": [], "audio": []}}}}
        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}),                 mock.patch("lib.ppro_bridge.submit", side_effect=submit),                 mock.patch.object(ppro_build, "job_data", return_value=data):
            ppro_build.build(self.p)
        from lib.common import read_json
        rec = read_json(self.p.p("07_premiere/ppro-build-result.json"))
        self.assertEqual(rec["job_data"]["track_names"], NATIVE_NAMES)
        self.assertTrue(rec["job_data"]["native_caption_track"])
        self.assertEqual(rec["job_data"]["sequence_name"], "CLIP1_RE_EDIT")
        self.assertNotIn("graphics", rec["job_data"])          # the map only, not the whole job


class TestXmlFallbackHandoff(HandoffFixture):
    def test_fallback_golden(self):
        self.approve()
        self.manifest(native=False)
        self.golden("xml_fallback.md", self.readme())

    def test_no_build_result_keeps_the_import_steps(self):
        self.manifest(native=False)
        md = self.readme()
        self.assertIn("File › Import…", md)
        self.assertIn("Sequence Settings", md)
        self.assertIn("not built natively", md)
        self.assertIn("reel ppro-build", md)                  # and says how to get the native project instead

    def test_failed_native_build_falls_back_and_says_why(self):
        self.manifest(native=False)
        write_json(self.p.p("07_premiere/ppro-build-result.json"),
                   {"status": "FAILED", "checks": {"prproj_saved_this_run": False}, "project": "x",
                    "premiere_error": "Premiere closed during the build"})
        md = self.readme()
        self.assertIn("FAILED", md)
        self.assertIn("Premiere closed during the build", md)
        self.assertIn("File › Import…", md)

    def test_captions_line_does_not_claim_an_ae_render_without_one(self):
        self.manifest(native=False)
        self.assertNotIn("(AE render)", self.readme())
        cap = self.p.p("04_after_effects/compositions/CAPTIONS.mov")
        cap.parent.mkdir(parents=True, exist_ok=True)
        cap.write_bytes(b"mov")
        write_json(self.p.p("04_after_effects/ae-build-result.json"), {"status": "AEP_BUILT"})
        self.assertIn("(AE render)", self.readme())


class TestExtrasRows(HandoffFixture):
    def test_ae_and_ps_rows_only_when_extras_were_used(self):
        self.native_build()
        md = self.readme()
        self.assertNotIn("After Effects", md)
        self.assertNotIn("Photoshop", md)
        write_json(self.p.p("04_after_effects/ae-build-result.json"), {"status": "AEP_BUILT"})
        write_json(self.p.p("05_photoshop/ps-build-result.json"), {"status": "PSD_BUILT"})
        md = self.readme()
        self.assertIn("| After Effects comps (.aep, editable) | AEP_BUILT |", md)
        self.assertIn("| Photoshop layered PSDs | PSD_BUILT |", md)
        self.assertIn("## 2. After Effects", md)
        self.assertIn("## 3. Photoshop", md)

    def test_generated_script_not_run_reads_as_script_only(self):
        self.native_build()
        jsx = self.p.p("04_after_effects/scripts/build_CLIP1_graphics.jsx")
        jsx.parent.mkdir(parents=True, exist_ok=True)
        jsx.write_text("// jsx", encoding="utf-8")
        self.assertIn("SCRIPT ONLY — run the JSX", self.readme())


def appendix_f(**kw) -> dict:
    """A record as the master plan's Appendix F defines it (the Phase 5 `05_assets/magnific-manifest.json` entry)."""
    rec = {"asset_id": "MG-0007", "need_id": "N03", "local_path": "05_assets/magnific/logo_upscaled.png",
           "sha256": "ab" * 32, "source": "mcp-creation", "creation_id": "c-991", "tool": "images_upscale",
           "model": "magnific-precision", "prompt": None, "reference_inputs": ["output/client_database/assets/logo_small.png"],
           "credits_before": 12840, "credits_after": 12750, "plan_at_generation": "premium+",
           "created_at": "2026-10-11T12:00:00+03:00", "license_type": "ai-generated-paid", "license_url": None,
           "attribution_required": False, "attribution_text": None,
           "used_in": [{"item": "CLIP1", "at": ["00:00:01.2-00:00:03.0"]}],
           "relevance_anchor": {"segment": "s041", "start": "00:12:03.40", "end": "00:12:06.10", "phrase": "x"},
           "sensitivity_review": {"by": "medical-reviewer", "verdict": "ok"}, "approved_by": "editor",
           "transferable_to_client": False}
    rec.update(kw)
    return rec


class TestLicensedMaterial(HandoffFixture):
    STOCK = dict(asset_id="MG-0008", need_id="N05", local_path="05_assets/magnific/waiting-room.mp4",
                 source="stock-rest", stock_id="5530", tool=None, model=None, license_type="stock-premium",
                 attribution_required=True, attribution_text="Photo by A. Author / Magnific")
    ENTRIES = [appendix_f(), STOCK]

    def test_absent_without_a_manifest(self):
        self.native_build()
        md = self.readme()
        self.assertNotIn("Licensed material", md)
        self.assertNotIn("not transferable", md)

    def test_golden_with_appendix_f_records(self):
        self.approve()
        self.native_build()
        self.magnific(self.ENTRIES)
        self.golden("native_licensed.md", self.readme())

    def test_rows_read_the_appendix_f_fields(self):
        self.native_build()
        self.magnific(self.ENTRIES)
        md = self.readme()
        self.assertIn("## Licensed material", md)
        self.assertIn("| MG-0007 | N03 | 05_assets/magnific/logo_upscaled.png | image | images_upscale / magnific-precision | "
                      "ai-generated-paid; agency-licensed, not transferable |", md)
        self.assertIn("| MG-0008 | N05 | 05_assets/magnific/waiting-room.mp4 | video | stock 5530 | "
                      "stock-premium; attribution: Photo by A. Author / Magnific; agency-licensed, not transferable |", md)

    def test_transferable_record_is_not_marked_agency_only(self):
        self.native_build()
        self.magnific([appendix_f(transferable_to_client=True)])
        md = self.readme()
        self.assertIn("ai-generated-paid |", md)
        self.assertNotIn("not transferable", md)
        self.magnific([appendix_f(transferable_to_client=None)])         # missing/unknown counts as not transferable
        self.assertIn("not transferable", self.readme())

    def test_kind_comes_from_the_tool_then_the_extension(self):
        from lib.handoff import _asset_kind
        self.assertEqual(_asset_kind({"tool": "video_generate"}), "video")
        self.assertEqual(_asset_kind({"tool": "audio_sfx_generate"}), "audio")
        self.assertEqual(_asset_kind({"tool": None, "local_path": "a/b.MOV"}), "video")
        self.assertEqual(_asset_kind({"file": "a/b.png"}), "image")
        self.assertEqual(_asset_kind({}), "—")

    def test_bare_list_and_wrapped_lists_are_accepted(self):
        self.native_build()
        for wrap in (lambda e: e, lambda e: {"entries": e}, lambda e: {"assets": e}, lambda e: {"items": e}):
            write_json(self.p.p("05_assets/magnific-manifest.json"), wrap([appendix_f()]))
            self.assertIn("| MG-0007 |", self.readme())

    def test_a_corrupt_manifest_is_reported_not_fatal(self):
        self.native_build()
        self.p.p("05_assets").mkdir(parents=True, exist_ok=True)
        self.p.p("05_assets/magnific-manifest.json").write_text("{not json", encoding="utf-8")
        md = self.readme()
        self.assertIn("## Licensed material", md)
        self.assertIn("could not be read", md)
        self.assertNotIn("not transferable", md)

    def test_an_empty_manifest_says_none_listed(self):
        self.native_build()
        self.magnific([])
        md = self.readme()
        self.assertIn("## Licensed material", md)               # the manifest exists, with no entries yet
        self.assertIn("none listed yet", md)
        self.assertNotIn("not transferable", md)

    def test_fallback_handoff_also_gets_the_section(self):
        self.manifest(native=False)
        self.magnific(self.ENTRIES)
        self.assertIn("agency-licensed, not transferable", self.readme())


class TestMotionHandoff(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "CLIENT"
        (self.root / "assets").mkdir(parents=True)
        (self.root / "data").mkdir(parents=True)
        stored_prefix(self, self.root)
        self.p = Paths(self.root, "EP12_R01_MO")
        self.p.ensure_project()
        write_json(self.p.p("08_quality_control/qc-results.json"), {"ok": True})
        write_json(self.p.p("01_analysis/motion-plan.json"), {
            "reel_id": "EP12_R01_MO", "format": "9:16", "fps": 24, "duration_frames": 720,
            "scenes": [{"id": "S01", "type": "hook", "start_frame": 0, "end_frame": 240,
                        "elements": [{"font_ps": "ArialMT"}]},
                       {"id": "S02", "type": "stat", "start_frame": 240, "end_frame": 720,
                        "elements": [{"font_ps": "Arial-BoldMT"}]}],
            "assets": [{"ref": "people/doctor", "license": "CC-BY-4.0", "attribution": "People by X (CC BY 4.0)"}],
            "audio": {"music": None}, "approvals": ["doctor to approve the statistic on S02"]})

    def test_motion_golden(self):
        md = motion_readme(self.p).read_text(encoding="utf-8")
        got = normalise(md, self.root)
        path = GOLDEN / "motion.md"
        if os.environ.get("UPDATE_GOLDEN") == "1":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(got, encoding="utf-8", newline="\n")
        self.assertTrue(path.exists(), f"golden file {path} is missing (UPDATE_GOLDEN=1 to write it)")
        self.assertEqual(got, path.read_text(encoding="utf-8"))

    def test_motion_licensed_material_section_only_with_a_manifest(self):
        self.assertNotIn("Licensed material", motion_readme(self.p).read_text(encoding="utf-8"))
        write_json(self.p.p("05_assets/magnific-manifest.json"),
                   {"entries": [appendix_f(local_path="05_assets/magnific/bg.png")]})
        md = motion_readme(self.p).read_text(encoding="utf-8")
        self.assertIn("## Licensed material", md)
        self.assertIn("agency-licensed, not transferable", md)


if __name__ == "__main__":
    unittest.main()
