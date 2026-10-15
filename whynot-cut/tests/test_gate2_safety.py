"""Gate 2 fix round G1 — Premiere rebuild safety and id/root validation.

B1  a failed rebuild that put the old project back keeps the record of what the PIPELINE saved, so the editor's changes
    are still seen by the next `--force`.
B2  closing the open project in Premiere saves it: the editor's unsaved work that this close wrote is never recorded as
    the pipeline's; the build refuses (EDITOR_CHANGES_PRESENT) unless --replace-edited.
B3  the bridge's own "no reply" timeout result counts as claimed (Premiere may still be writing).
B4  --video-id / --episode are one plain folder name (no separators, no `..`); writing commands refuse a --root without
    assets/ and data/.
Minors: `_prev_` names are unique below the second and their stem is glob-escaped; a relative WHYNOT_HOME is absolute.
Run:  bash tools/test.sh -p test_gate2_safety.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import errno  # noqa: E402
import gzip  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import types  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

SK = Path(__file__).resolve().parents[1]
CLI = SK / "engine" / "reel" / "cli.py"
if str(SK / "engine" / "reel") not in _sys.path:
    _sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import cep_queue, common, errors  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402

DATA = {"_missing": [], "graphics": [], "native_caption_track": False, "sharpen_v1": None,
        "sequence_name": "V1", "track_names": {}}


def gz(path: Path, text: str, mtime: float | None = None):
    with gzip.open(path, "wb") as f:
        f.write(f"<Project><Sequence>{text}</Sequence></Project>".encode("utf-8"))
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def ungz(path: Path) -> str:
    with gzip.open(path) as f:
        return f.read().decode("utf-8")


class _Client(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        ctx = common.use_context(common.Context(home=self.home))
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        root = self.tmp / "C"
        (root / "assets").mkdir(parents=True)
        (root / "data").mkdir()
        self.p = Paths(root, "V1")
        self.p.ensure_project()
        write_json(self.p.p("01_analysis/timeline-spec.json"), {"events": [], "duration_frames": 240, "main_segments": []})
        self.prj = self.p.p(f"07_premiere/project/V1_{common.project_prefix()}_EDIT.prproj")
        self.prj.parent.mkdir(parents=True, exist_ok=True)
        self.rec_p = self.p.p("07_premiere/ppro-build-result.json")

    def pipeline_built(self, text="BUILT", age_s=3600):
        """The project as the pipeline saved it `age_s` ago, and its build record."""
        from lib.verify import prproj_signature
        bt = time.time() - age_s
        gz(self.prj, text, bt)
        write_json(self.rec_p, {"status": "PRPROJ_BUILT", "project": str(self.prj), "prproj_mtime": bt,
                                "content_signature": prproj_signature(self.prj), "checks": {}})
        return bt

    def build(self, answer, close=None, at_job_data=None, close_result=None, **kw):
        """ppro_build.build with a fake bridge: `close(prj)` plays Premiere's save-and-close, `answer(prj)` the build;
        `at_job_data()` runs when the build gets past the close check. `close_result(data)` (T6.3) gives the close's
        readback for the data it was sent (a close that answers closed false saved nothing: `close` is not played);
        default {"closed": True}. Every (action, data) sent is kept in self.sent_data."""
        from lib import ppro_build
        sent = []
        self.sent_data = []

        def job_data(*a, **k):
            if at_job_data:
                at_job_data()
            return dict(DATA)

        def submit(action, data=None, timeout=0, **k):
            sent.append(action)
            self.sent_data.append((action, data))
            if action == "close_project_path":
                res = close_result(data) if close_result else {"closed": True}
                if close and res.get("closed") is not False:
                    close(self.prj)
                return {"ok": True, "response": {"ok": True, "action": action, "result": res}}
            return answer(self.prj)

        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                mock.patch("lib.ppro_bridge.submit", side_effect=submit), \
                mock.patch.object(ppro_build, "job_data", side_effect=job_data):
            r = ppro_build.build(self.p, **kw)
        return r, sent


def failed(prj):
    return {"ok": False, "error": "Premiere reported an error"}


class TestB1FailedRebuildKeepsTheEditorCheck(_Client):
    def test_editor_change_survives_a_failed_replace_edited_rebuild(self):
        bt = self.pipeline_built()
        gz(self.prj, "EDITED BY THE EDITOR", bt + 1800)                  # the editor saved real work in Premiere
        r, sent = self.build(failed, overwrite=True)
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)
        self.assertEqual(sent, [])
        r, sent = self.build(failed, overwrite=True, replace_edited=True)
        self.assertEqual(r["status"], "FAILED", r)
        self.assertTrue(r["previous_restored"])
        self.assertIn("EDITED BY THE EDITOR", ungz(self.prj))
        r, sent = self.build(failed, overwrite=True)                    # the next plain --force
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)
        self.assertEqual(errors.exit_code(r), 2)
        self.assertNotIn("build_project", sent)

    def test_the_failure_is_still_recorded(self):
        self.pipeline_built()
        r, _ = self.build(failed, overwrite=True)
        self.assertEqual(r["status"], "FAILED")
        rec = read_json(self.rec_p)
        self.assertEqual(rec["status"], "FAILED")
        self.assertTrue(rec["previous_restored"])


class TestB2CloseSaveIsNotThePipelines(_Client):
    def test_unsaved_editor_work_written_by_the_close_is_refused(self):
        self.pipeline_built()
        sig0 = read_json(self.rec_p)["content_signature"]
        r, sent = self.build(failed, close=lambda prj: gz(prj, "UNSAVED EDITOR WORK"), overwrite=True)
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)
        self.assertTrue(r["blocked"])
        self.assertEqual(errors.exit_code(r), 2)
        self.assertEqual(sent, ["close_project_path"])                  # nothing was built over it
        self.assertEqual(read_json(self.rec_p)["content_signature"], sig0)   # never recorded as the pipeline's
        self.assertIn("UNSAVED EDITOR WORK", ungz(self.prj))
        r, sent = self.build(failed, overwrite=True)                    # and the next --force still sees it
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)

    def test_replace_edited_goes_ahead(self):
        self.pipeline_built()
        r, sent = self.build(failed, close=lambda prj: gz(prj, "UNSAVED EDITOR WORK"), overwrite=True,
                             replace_edited=True)
        self.assertIn("build_project", sent)
        self.assertEqual(r["status"], "FAILED")

    def test_a_save_without_changes_is_the_pipelines(self):
        self.pipeline_built()
        r, sent = self.build(failed, close=lambda prj: gz(prj, "BUILT"), overwrite=True)    # same timeline, new time
        self.assertIn("build_project", sent)
        rec = read_json(self.rec_p)
        self.assertGreater(rec["prproj_mtime"], time.time() - 120)


class TestB2DirtyReportBeforeTheClose(_Client):
    """T6.3: the close asks Premiere to save only if clean (save "if_clean"). dirty true -> EDITOR_CHANGES_PRESENT before
    anything is written; with --replace-edited a second close saves ("always"). dirty false still runs the signature
    check (belt and braces); dirty null (no dirty API in this Premiere) is the signature path of today."""

    @staticmethod
    def dirty(value, api="dirty"):
        def result(data):
            if data.get("save") == "if_clean" and value is True:
                return {"path": data["path"], "dirty": True, "saved": False, "dirty_api": api, "closed": False,
                        "reason": "unsaved changes in Premiere"}
            saved = data.get("save") == "always" or value is not False
            return {"path": data["path"], "dirty": value, "saved": saved,
                    "dirty_api": api if value is not None else None, "closed": True}
        return result

    def saves(self):
        return [d.get("save") for a, d in self.sent_data if a == "close_project_path"]

    def test_dirty_true_is_refused_before_anything_is_written(self):
        self.pipeline_built()
        rec0 = self.rec_p.read_bytes()
        before = (self.prj.read_bytes(), self.prj.stat().st_mtime_ns)
        written = []
        r, sent = self.build(failed, close=lambda prj: gz(prj, "UNSAVED EDITOR WORK"), overwrite=True,
                             close_result=self.dirty(True), at_job_data=lambda: written.append("job_data"))
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)
        self.assertEqual(r["detail"], "unsaved changes in Premiere (nothing was saved or closed)")
        self.assertTrue(r["blocked"])
        self.assertIn("--replace-edited", r["fix"])
        self.assertEqual(errors.exit_code(r), 2)
        self.assertEqual(sent, ["close_project_path"])
        self.assertEqual(self.saves(), ["if_clean"])
        self.assertEqual((self.prj.read_bytes(), self.prj.stat().st_mtime_ns), before)     # bytes and mtime unchanged
        self.assertEqual(self.rec_p.read_bytes(), rec0)                                    # the record too
        self.assertEqual(written, [])
        self.assertEqual(list(self.prj.parent.glob("*_prev_*")), [])                       # nothing parked
        self.assertIs(r["closed_previous"]["result"]["dirty"], True)

    def test_replace_edited_closes_again_with_save_always(self):
        self.pipeline_built()
        r, sent = self.build(failed, close=lambda prj: gz(prj, "UNSAVED EDITOR WORK"), overwrite=True,
                             replace_edited=True, close_result=self.dirty(True))
        self.assertEqual(sent, ["close_project_path", "close_project_path", "build_project"])
        self.assertEqual(self.saves(), ["if_clean", "always"])
        self.assertEqual(r["status"], "FAILED", r)
        self.assertIs(r["closed_previous"]["result"]["saved"], True)                      # the second close's answer
        self.assertIn("UNSAVED EDITOR WORK", ungz(self.prj))                                 # restored, not lost

    def test_dirty_false_still_checks_the_signature(self):
        self.pipeline_built()
        sig0 = read_json(self.rec_p)["content_signature"]
        r, sent = self.build(failed, close=lambda prj: gz(prj, "EDITED ANYWAY"), overwrite=True,
                             close_result=self.dirty(False, "isDirty()"))
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)                         # the file changed: refused
        self.assertTrue(r["detail"]["content"].startswith("changed"), r)
        self.assertEqual(sent, ["close_project_path"])
        self.assertEqual(self.saves(), ["if_clean"])
        self.assertEqual(read_json(self.rec_p)["content_signature"], sig0)
        self.pipeline_built()
        r, sent = self.build(failed, close=lambda prj: gz(prj, "BUILT"), overwrite=True,
                             close_result=self.dirty(False, "isDirty()"))
        self.assertIn("build_project", sent)                                               # unchanged: goes ahead
        self.assertEqual(self.saves(), ["if_clean"])

    def test_dirty_null_is_todays_signature_path(self):
        self.pipeline_built()
        r, sent = self.build(failed, close=lambda prj: gz(prj, "UNSAVED EDITOR WORK"), overwrite=True,
                             close_result=self.dirty(None))
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)
        self.assertIn("saved by Premiere when the build closed", r["detail"]["content"])
        self.assertEqual(sent, ["close_project_path"])
        self.assertEqual(self.saves(), ["if_clean"])                                       # never a second close
        self.assertIn("UNSAVED EDITOR WORK", ungz(self.prj))
        self.pipeline_built()
        r, sent = self.build(failed, close=lambda prj: gz(prj, "BUILT"), overwrite=True, close_result=self.dirty(None))
        self.assertIn("build_project", sent)
        self.assertEqual(self.saves(), ["if_clean"])
        self.assertGreater(read_json(self.rec_p)["prproj_mtime"], time.time() - 120)

    def test_a_legacy_answer_without_dirty_is_todays_path(self):
        """A library from before T6.3 answers {closed, path} only: the signature decides, as before."""
        self.pipeline_built()
        r, sent = self.build(failed, close=lambda prj: gz(prj, "UNSAVED EDITOR WORK"), overwrite=True,
                             close_result=lambda data: {"closed": True, "path": data["path"]})
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)
        self.assertEqual(sent, ["close_project_path"])


def prproj_xml(*, cc="scanned", patching=None, bag_order=False, saved="2:16:19 AM", next_id=1000001, change=390,
               empty_node=False, view=0, start=None, end=3556224000000, items=1, text="A sample statement",
               opacity=100.0, tracks=2, markers=1, name="SAMPLE_RE_EDIT", in_point=0, effects_swapped=False,
               disabled=False, gain=0.0, pad=0):
    """A Premiere 26.5 project shaped like the 13-Oct captures (fictional names). The keyword defaults are one save of
    the build; `cc`, `patching`, `bag_order`, `saved`, `next_id`, `change`, `empty_node` and `view` are what Premiere
    itself rewrites (Gate 2 B2); the rest is editor content. `pad` adds that many sample bins (a large project)."""
    cc_el = ("<ContentCredentialsInfo>65536</ContentCredentialsInfo>" if cc == "pending"
             else "<CCFileModTime>1791830622799451</CCFileModTime>")
    scratch = ["<AudioPreviewLocation0>SameAsProject</AudioPreviewLocation0>",
               "<CCLibrariesLocation0>SameAsProject</CCLibrariesLocation0>",
               "<CapsuleMediaLocation0>SameAsProject</CapsuleMediaLocation0>",
               "<AutoSaveLocation0>SameAsProject</AutoSaveLocation0>"]
    seq_props = ["<MZ.ZeroPoint>0</MZ.ZeroPoint>", "<AMM.CurrentSolo>[]</AMM.CurrentSolo>",
                 f"<MZ.InPoint>{in_point}</MZ.InPoint>",
                 f"<MZ.EditLine>{view * 1000}</MZ.EditLine>",
                 f"<TL.SQVisibleBaseTime>{view * 254016000000}</TL.SQVisibleBaseTime>",
                 f"<Monitor.ProgramZoomOut>{3556224000000 + view}</Monitor.ProgramZoomOut>"]
    if patching:
        audio = ('<HSL.TimelinePatchingAndTargeting.AudioPatchesbf04c4b5_45_603a_45_2652_45_0974_45_7bc70000001f>'
                 '[{"mNumber":0,"mState":2},{"mNumber":1,"mState":2}]'
                 '</HSL.TimelinePatchingAndTargeting.AudioPatchesbf04c4b5_45_603a_45_2652_45_0974_45_7bc70000001f>')
        video = ('<HSL.TimelinePatchingAndTargeting.VideoPatches4b7f66de_45_1bb0_45_cba9_45_abba_45_e67900000017>'
                 '[{"mNumber":0,"mState":2},{"mNumber":-1,"mState":0}]'
                 '</HSL.TimelinePatchingAndTargeting.VideoPatches4b7f66de_45_1bb0_45_cba9_45_abba_45_e67900000017>')
        seq_props = ([audio, video] if patching == "audio_first" else [video, audio]) + seq_props
    if bag_order:
        scratch.reverse()
        seq_props.reverse()

    def track(i):
        props = ["<TL.SQTrackExpanded>0</TL.SQTrackExpanded>", f"<MZ.TrackName>V{i + 1} Sample Track</MZ.TrackName>"]
        if patching:
            props[1:1] = [f"<MZ.SourceTrackState>{2 if i == 0 else 0}</MZ.SourceTrackState>",
                          f"<MZ.SourceTrackNumber>{0 if i == 0 else -1}</MZ.SourceTrackNumber>"]
        if bag_order:
            props.reverse()
        return (f'<VideoClipTrack ObjectUID="0000000{i}-0000-4000-8000-000000000000" Version="1"><ClipTrack Version="2">'
                f'<Track Version="4"><Node Version="1"><Properties Version="1">{"".join(props)}</Properties></Node>'
                f'<ID>{i + 1}</ID><Index>{i}</Index></Track><ClipItems Version="3"><TrackItems Version="1">'
                + "".join(f'<TrackItem Index="{k}" ObjectRef="{134 + k}"/>' for k in range(items if i == 0 else 0))
                + "</TrackItems></ClipItems></ClipTrack></VideoClipTrack>")

    item = lambda k: (f'<VideoClipTrackItem ObjectID="{134 + k}" Version="8"><ClipTrackItem Version="8">'
                      f'<TrackItem Version="4"><TrackIndex>0</TrackIndex><Type>1</Type>'
                      + (f"<Start>{start}</Start>" if start is not None and k == 0 else "")
                      + f'<End>{end + k * 1000}</End></TrackItem><SubClip ObjectRef="140"/>'
                      f"<IsMuted>false</IsMuted><Disabled>{str(disabled and k == 0).lower()}</Disabled>"
                      f"</ClipTrackItem><FrameRect>0,0,1080,1920</FrameRect>"
                      f"</VideoClipTrackItem>")
    refs = [301, 302] if not effects_swapped else [302, 301]
    audio_item = [f"<Gain>{gain}</Gain>", "<IsMuted>false</IsMuted>", "<Channel>0</Channel>"]
    if bag_order:
        audio_item.reverse()
    bin_ = lambda k: (f'<BinProjectItem ObjectUID="5555{k:04d}-0000-4000-8000-000000000000" Version="3"><ProjectItem '
                      f'Version="1"><Name>Sample Bin {k}</Name><Node Version="1"><Properties Version="1">'
                      f'<Column.PropertyText.Comment>Sample note {k}</Column.PropertyText.Comment>'
                      f'<Column.PropertyText.Label>BE.Prefs.LabelColors.{k % 8}</Column.PropertyText.Label>'
                      f'</Properties></Node></ProjectItem></BinProjectItem>\n')
    marker = lambda k: (f'<Marker ObjectID="{108 + k}" Version="3"><DVAMarker>{{"DVAMarker":{{"mComment":'
                        f'"context_card | Sample marker {k}","mName":"GFX_00{k + 1}","mStartTime":{{"ticks":'
                        f'{74088000000 + k}}},"mType":"Comment"}}}}</DVAMarker></Marker>')
    return ('<?xml version="1.0" encoding="UTF-8" ?>\n<PremiereData Version="3">\n'
            f'<Project ObjectID="1" Version="40"><Node Version="1"><Properties Version="1">'
            f"<MZ.BuildVersion.Created>26.5.2x5 - 10/13/2026 2:16:19 AM</MZ.BuildVersion.Created>"
            f"<MZ.BuildVersion.Modified>26.5.2x5 - 10/13/2026 {saved}</MZ.BuildVersion.Modified>"
            f"</Properties></Node><NextID>{next_id}</NextID></Project>\n"
            f'<ScratchDiskSettings ObjectID="9" Version="4">{"".join(scratch)}</ScratchDiskSettings>\n'
            f'<MasterClip ObjectUID="11111111-0000-4000-8000-000000000000" Version="12"><Name>{name}</Name>'
            f"<MasterClipChangeVersion>{change}</MasterClipChangeVersion></MasterClip>\n"
            f'<MasterClip ObjectUID="22222222-0000-4000-8000-000000000000" Version="12">'
            + ('<Node Version="1">\n<ID>1000001</ID>\n</Node>' if empty_node else "")
            + '<LoggingInfo ObjectRef="45"/></MasterClip>\n'
            f'<Media ObjectUID="33333333-0000-4000-8000-000000000000" Version="30">'
            f"<ActualMediaFilePath>D:\\Sample Client\\stills\\typography__GFX_001.png</ActualMediaFilePath>{cc_el}"
            f"</Media>\n"
            + "".join(marker(k) for k in range(markers))
            + f'\n<Sequence ObjectUID="44444444-0000-4000-8000-000000000000" Version="12"><Node Version="1">'
            f'<Properties Version="1">{"".join(seq_props)}</Properties></Node><Name>Sample Sequence</Name></Sequence>\n'
            + "".join(track(i) for i in range(tracks)) + "\n"
            + "".join(item(k) for k in range(items))
            + f'\n<VideoComponentParam ObjectID="200" Version="10"><Name>Source Text</Name>'
            f"<CurrentValue>{text}</CurrentValue></VideoComponentParam>"
            f'<VideoComponentParam ObjectID="201" Version="10"><Name>Opacity</Name>'
            f"<CurrentValue>{opacity}</CurrentValue></VideoComponentParam>\n"
            f'<VideoComponentChain ObjectID="300" Version="3"><ComponentChain Version="3"><Components Version="1">'
            f'<Component Index="0" ObjectRef="{refs[0]}"/><Component Index="1" ObjectRef="{refs[1]}"/></Components>'
            f"</ComponentChain></VideoComponentChain>\n"
            f'<AudioClipTrackItem ObjectID="150" Version="8">{"".join(audio_item)}</AudioClipTrackItem>\n'
            + "".join(bin_(k) for k in range(pad)) + "</PremiereData>\n")


def write_prproj(path: Path, xml: str, mtime: float | None = None):
    with gzip.open(path, "wb") as f:
        f.write(xml.encode("utf-8"))
    if mtime is not None:
        os.utime(path, (mtime, mtime))


class TestB2SignatureIgnoresPremieresOwnDrift(unittest.TestCase):
    """Fix loop 1: what Premiere adds after the build's save (measured 13-Oct) is not an editor change; real edits are."""

    def sig(self, **kw):
        from lib.verify import prproj_signature
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        write_prproj(tmp / "p.prproj", prproj_xml(**kw))
        return prproj_signature(tmp / "p.prproj")

    def test_observed_close_saves_keep_the_signature(self):
        base = self.sig(cc="pending")                         # the build's save, first build in a fresh Premiere
        self.assertTrue(base.startswith("c2:"), base)
        drift = {
            "content-credentials scan done (cold start, 02:16)": dict(cc="scanned"),
            "timeline patching/targeting written after the save (02:09)": dict(cc="scanned", patching="audio_first"),
            "patching keys in another order (warm, 02:18)": dict(cc="pending", patching="video_first"),
            "property bags in another key order": dict(cc="pending", bag_order=True),
            "save stamp, ids, empty node": dict(cc="pending", saved="2:16:21 AM", next_id=1000002, change=391,
                                                empty_node=True),
            "timeline scrolled / zoomed, playhead moved": dict(cc="pending", view=7),
            "all of it at once": dict(cc="scanned", patching="video_first", bag_order=True, saved="2:17:00 AM",
                                      next_id=1000009, change=395, empty_node=True, view=3),
        }
        for what, kw in drift.items():
            with self.subTest(what):
                self.assertEqual(self.sig(**kw), base)
        self.assertEqual(self.sig(patching="audio_first"), self.sig(patching="video_first", bag_order=True))

    def test_each_real_edit_changes_it(self):
        base = self.sig(patching="audio_first")
        edits = {
            "clip moved": dict(start=254016000000),
            "clip trimmed": dict(end=3556224000000 - 10584000000),
            "clip added": dict(items=2),
            "clip removed": dict(items=0),
            "graphic text changed": dict(text="A different statement"),
            "effect value changed": dict(opacity=80.0),
            "track added": dict(tracks=3),
            "marker added": dict(markers=2),
        }
        seen = {base}
        for what, kw in edits.items():
            with self.subTest(what):
                s = self.sig(patching="audio_first", **kw)
                self.assertNotEqual(s, base)
                self.assertNotEqual(self.sig(patching="video_first", bag_order=True, cc="pending", **kw), base)
                seen.add(s)
        self.assertEqual(len(seen), len(edits) + 1)           # every edit is its own content

    def test_only_a_missing_project_has_no_signature(self):
        from lib.verify import prproj_signature
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.assertIsNone(prproj_signature(tmp / "missing.prproj"))
        (tmp / "x.prproj").write_bytes(b"not gzip")
        (tmp / "y.prproj").write_bytes(b"not gzip either")
        self.assertTrue(prproj_signature(tmp / "x.prproj").startswith("bytes:"))
        self.assertNotEqual(prproj_signature(tmp / "x.prproj"), prproj_signature(tmp / "y.prproj"))
        (tmp / "z.prproj").write_bytes(gzip.compress(b"<PremiereData>")[:-6])        # truncated gzip
        self.assertTrue(prproj_signature(tmp / "z.prproj").startswith("bytes:"))

    def test_a_readable_project_always_has_one(self):
        """Review fix: XML that ElementTree rejects (a truncated file, a character XML 1.0 forbids pasted into a title)
        is still signed, from its raw text: None would compare equal to None and let a rebuild go ahead."""
        from lib.verify import prproj_signature
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        for what, xml in {"truncated": "<PremiereData><Project>", "&#x1; in a name": prproj_xml(name="A&#x1;B"),
                          "raw \\x01 in a text": prproj_xml(text="A\x01B"),
                          "raw \\x0b in a text": prproj_xml(text="A\x0bB")}.items():
            with self.subTest(what):
                write_prproj(tmp / "y.prproj", xml)
                s = prproj_signature(tmp / "y.prproj")
                self.assertTrue(s and s.startswith("raw:"), s)
        write_prproj(tmp / "a.prproj", prproj_xml(name="A&#x1;B"))
        write_prproj(tmp / "b.prproj", prproj_xml(name="A&#x1;B", text="Edited"))
        self.assertNotEqual(prproj_signature(tmp / "a.prproj"), prproj_signature(tmp / "b.prproj"))

    def test_the_sort_rule_keeps_list_order_and_bag_values(self):
        """Review minor 4: only key/value records with all-different names are sorted. A same-named list keeps its
        order (effects are <Component Index=...> siblings), and sorting a record never drops a value."""
        base = self.sig()
        self.assertEqual(self.sig(bag_order=True), base)               # key order only: the same content
        edits = {"effect order (Component Index list)": dict(effects_swapped=True),
                 "sequence in point (MZ.InPoint, a bag value)": dict(in_point=254016000000),
                 "clip disabled": dict(disabled=True),
                 "audio gain (a sorted record)": dict(gain=-6.0),
                 "clip renamed": dict(name="SAMPLE_RE_EDIT_2")}
        for what, kw in edits.items():
            with self.subTest(what):
                self.assertNotEqual(self.sig(**kw), base)
                self.assertNotEqual(self.sig(bag_order=True, **kw), base)


def _selection(comp_id=1, param=4294967295, extra=""):
    """What Premiere writes on a component chain once it is shown or selected in Effect Controls (13-Oct recheck)."""
    return ('<Node Version="1"><Properties Version="1">'
            f"<MZ.ComponentChain.ActiveComponentID>{comp_id}</MZ.ComponentChain.ActiveComponentID>"
            f"<MZ.ComponentChain.ActiveComponentParamIndex>{param}</MZ.ComponentChain.ActiveComponentParamIndex>"
            f"{extra}</Properties></Node>")


def _with_chains(xml: str, empty_sel: str = "", used_sel: str = "") -> str:
    """The sample project plus an empty sequence chain (as ObjectID 139 in the capture), `empty_sel` inside it, and
    `used_sel` inside the chain that holds the two effects."""
    xml = xml.replace('<ComponentChain Version="3"><Components', f'<ComponentChain Version="3">{used_sel}<Components')
    return xml.replace("</PremiereData>", '<VideoComponentChain ObjectID="139" Version="3"><ComponentChain '
                       f'Version="3">{empty_sel}</ComponentChain></VideoComponentChain>\n</PremiereData>')


class TestB2EffectControlsSelectionIsViewState(unittest.TestCase):
    """Gate 2 recheck 13-Oct §8.2: Premiere re-saved a project when the panel switched projects; the only difference
    was which effect is selected in Effect Controls. That is UI selection, not editor work."""

    def sig(self, empty_sel="", used_sel="", **kw):
        from lib.verify import prproj_signature
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        write_prproj(tmp / "p.prproj", _with_chains(prproj_xml(**kw), empty_sel, used_sel))
        return prproj_signature(tmp / "p.prproj")

    def test_the_selection_keys_added_changed_or_removed_keep_the_signature(self):
        base = self.sig()
        self.assertTrue(base.startswith("c2:"), base)
        cases = {
            "added to an empty chain (the capture)": dict(empty_sel=_selection()),
            "changed to another effect": dict(empty_sel=_selection(2, 0)),
            "added to the chain with the effects": dict(used_sel=_selection(1, 4)),
            "on both chains, changed": dict(empty_sel=_selection(3, 1), used_sel=_selection(2, 4294967295)),
            "wrapper with another save-time key beside them": dict(
                empty_sel=_selection(extra="<MZ.EditLine>5</MZ.EditLine>")),
        }
        for what, kw in cases.items():
            with self.subTest(what):
                self.assertEqual(self.sig(**kw), base)
        self.assertEqual(self.sig(empty_sel=_selection(1, 4)), self.sig(empty_sel=_selection(9, 0), used_sel=_selection()))

    def test_the_wrapper_is_dropped_with_the_keys(self):
        """Presence or absence of the emptied Node/Properties must not change the hash, at any nesting depth."""
        nested = ('<Node Version="1"><Properties Version="1">' + _selection() + "</Properties></Node>")
        bare = _selection().removeprefix('<Node Version="1">').removesuffix("</Node>")      # Properties without a Node
        self.assertEqual(self.sig(empty_sel=_selection()), self.sig())
        self.assertEqual(self.sig(empty_sel=nested), self.sig())
        self.assertEqual(self.sig(empty_sel=bare), self.sig())

    def test_real_chain_content_still_counts_next_to_the_selection(self):
        base = self.sig(empty_sel=_selection(), used_sel=_selection(1, 4))
        edits = {
            "effect parameter value": dict(opacity=80.0),
            "graphic text": dict(text="A different statement"),
            "effect order": dict(effects_swapped=True),
        }
        for what, kw in edits.items():
            with self.subTest(what):
                self.assertNotEqual(self.sig(empty_sel=_selection(), used_sel=_selection(1, 4), **kw), base)
                self.assertNotEqual(self.sig(empty_sel=_selection(2, 0), used_sel=_selection(), **kw), self.sig())
                self.assertEqual(self.sig(empty_sel=_selection(2, 0), used_sel=_selection(), **kw), self.sig(**kw))
        # a different value kept in the same bag as the selection keys is editor content
        self.assertNotEqual(self.sig(empty_sel=_selection(extra="<Sample.Setting>7</Sample.Setting>")), self.sig())
        self.assertNotEqual(self.sig(empty_sel=_selection(extra="<Sample.Setting>7</Sample.Setting>")),
                            self.sig(empty_sel=_selection(extra="<Sample.Setting>8</Sample.Setting>")))
        # a chain that holds a real component is not an emptied wrapper
        self.assertNotEqual(self.sig(empty_sel='<Components Version="1"><Component Index="0" ObjectRef="9"/></Components>'),
                            self.sig())


class TestB2RebuildAfterPremieresDrift(_Client):
    def built_real(self, age_s=3600, **kw):
        from lib.verify import prproj_signature
        bt = time.time() - age_s
        write_prproj(self.prj, prproj_xml(**kw), bt)
        write_json(self.rec_p, {"status": "PRPROJ_BUILT", "project": str(self.prj), "prproj_mtime": bt,
                                "content_signature": prproj_signature(self.prj), "checks": {}})
        return bt

    def test_untouched_rebuild_after_a_cold_start_goes_ahead(self):
        self.built_real(age_s=5, cc="pending")
        drift = lambda prj: write_prproj(prj, prproj_xml(cc="scanned", patching="audio_first", bag_order=True,
                                                         saved="2:16:21 AM", next_id=1000002, empty_node=True))
        r, sent = self.build(failed, close=drift, overwrite=True)
        self.assertNotEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)
        self.assertIn("build_project", sent)

    def test_a_real_edit_under_the_drift_is_still_refused(self):
        self.built_real(age_s=5, cc="pending")
        sig0 = read_json(self.rec_p)["content_signature"]
        edit = lambda prj: write_prproj(prj, prproj_xml(cc="scanned", patching="audio_first", end=3000000000000))
        r, sent = self.build(failed, close=edit, overwrite=True)
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)
        self.assertEqual(sent, ["close_project_path"])
        self.assertEqual(read_json(self.rec_p)["content_signature"], sig0)

    def test_a_drift_only_save_long_after_the_build_is_not_the_editors(self):
        from lib.verify import editor_modified
        bt = self.built_real(cc="pending")
        write_prproj(self.prj, prproj_xml(cc="scanned", patching="video_first"), bt + 1800)
        self.assertIsNone(editor_modified(self.p))
        write_prproj(self.prj, prproj_xml(cc="scanned", patching="video_first", text="Edited"), bt + 2400)
        self.assertEqual(editor_modified(self.p)["content"], "changed")

    def test_a_2x_record_without_the_prefix_still_compares(self):
        """Records written by 2.2.1 / earlier 3.0 builds hold the old signature: an unchanged project is not reported
        as the editor's after the upgrade, and an edited one still is."""
        from lib.verify import _legacy_signature, editor_modified, signature_matches
        bt = time.time() - 3600
        xml = prproj_xml()
        write_prproj(self.prj, xml, bt)
        legacy = _legacy_signature(xml)
        self.assertFalse(legacy.startswith("c2:"))
        write_json(self.rec_p, {"status": "PRPROJ_BUILT", "project": str(self.prj), "prproj_mtime": bt,
                                "content_signature": legacy, "checks": {}})
        self.assertTrue(signature_matches(self.prj, legacy))
        write_prproj(self.prj, prproj_xml(saved="9:00:00 AM", next_id=1000005), bt + 1800)
        self.assertIsNone(editor_modified(self.p))
        write_prproj(self.prj, prproj_xml(items=2), bt + 2400)
        self.assertIsNotNone(editor_modified(self.p))

    def test_a_2x_record_is_upgraded_by_an_unchanged_close(self):
        from lib.verify import _legacy_signature
        xml = prproj_xml()
        write_prproj(self.prj, xml, time.time() - 5)
        write_json(self.rec_p, {"status": "PRPROJ_BUILT", "project": str(self.prj), "prproj_mtime": time.time() - 5,
                                "content_signature": _legacy_signature(xml), "checks": {}})
        r, sent = self.build(failed, close=lambda prj: write_prproj(prj, prproj_xml(saved="9:00:00 AM")),
                             overwrite=True)
        self.assertIn("build_project", sent)
        self.assertTrue(read_json(self.rec_p)["content_signature"].startswith("c2:"))
        r, sent = self.build(failed, close=lambda prj: write_prproj(prj, prproj_xml(text="Edited")), overwrite=True)
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)


class TestB2UnparsableProjectKeepsTheCheck(_Client):
    """Review fix 1: a project ElementTree cannot parse never turns the edit check off."""
    NAME = "SAMPLE&#x1;CLIP"            # pasted text with a character XML 1.0 forbids (fictional)
    built_real = TestB2RebuildAfterPremieresDrift.built_real

    def test_it_is_recorded_with_a_raw_signature(self):
        self.built_real(age_s=5, name=self.NAME)
        self.assertTrue(read_json(self.rec_p)["content_signature"].startswith("raw:"))

    def test_an_edit_saved_by_the_close_is_refused(self):
        self.built_real(age_s=5, name=self.NAME)
        sig0 = read_json(self.rec_p)["content_signature"]
        edit = lambda prj: write_prproj(prj, prproj_xml(name=self.NAME, end=3000000000000))
        r, sent = self.build(failed, close=edit, overwrite=True)
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)
        self.assertEqual(sent, ["close_project_path"])
        self.assertEqual(read_json(self.rec_p)["content_signature"], sig0)
        r, sent = self.build(failed, overwrite=True, replace_edited=True)
        self.assertIn("build_project", sent)

    def test_an_untouched_project_is_still_rebuilt(self):
        self.built_real(age_s=5, name=self.NAME)
        resave = lambda prj: write_prproj(prj, prproj_xml(name=self.NAME, saved="3:00:00 AM"))
        r, sent = self.build(failed, close=resave, overwrite=True)
        self.assertNotEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)
        self.assertIn("build_project", sent)

    def test_a_c2_record_against_a_project_that_now_only_signs_raw_is_changed(self):
        self.built_real(age_s=5)
        r, sent = self.build(failed, close=lambda prj: write_prproj(prj, prproj_xml(name=self.NAME)), overwrite=True)
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)

    def test_a_2x_record_compares_with_the_raw_hash(self):
        from lib.verify import _legacy_signature, prproj_signature, signature_matches
        xml = prproj_xml(name=self.NAME)
        write_prproj(self.prj, xml)
        cur = prproj_signature(self.prj)
        self.assertTrue(signature_matches(self.prj, _legacy_signature(xml)))
        self.assertTrue(signature_matches(self.prj, _legacy_signature(xml), current=cur))
        self.assertFalse(signature_matches(self.prj, _legacy_signature(prproj_xml(name=self.NAME, text="X")),
                                           current=cur))

    def test_editor_modified_sees_raw_projects(self):
        from lib.verify import editor_modified
        bt = self.built_real(name=self.NAME)
        write_prproj(self.prj, prproj_xml(name=self.NAME, saved="9:00:00 AM", next_id=1000004), bt + 1800)
        self.assertIsNone(editor_modified(self.p))                      # saved, not edited
        write_prproj(self.prj, prproj_xml(name=self.NAME, text="Edited"), bt + 2400)
        self.assertEqual(editor_modified(self.p)["content"], "changed")

    def test_a_project_that_is_not_gzip_is_compared_by_its_bytes(self):
        """No recorded signature and a file that is not gzip: the close is checked on the bytes, not None == None."""
        write_json(self.rec_p, {"status": "PRPROJ_BUILT", "project": str(self.prj), "prproj_mtime": time.time(),
                                "checks": {}})
        self.prj.write_bytes(b"not gzip")
        r, sent = self.build(failed, close=lambda prj: prj.write_bytes(b"not gzip, edited"), overwrite=True)
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)
        self.assertEqual(sent, ["close_project_path"])
        r, sent = self.build(failed, overwrite=True)                    # the close wrote nothing: goes ahead
        self.assertIn("build_project", sent)

    def test_an_existing_project_without_any_signature_counts_as_changed(self):
        """A file that exists but cannot be signed (unreadable), and no record: a change, unless --replace-edited."""
        write_prproj(self.prj, prproj_xml())
        write_json(self.rec_p, {"status": "PRPROJ_BUILT", "project": str(self.prj), "prproj_mtime": time.time(),
                                "checks": {}})
        with mock.patch("lib.verify.prproj_signature", return_value=None):
            r, sent = self.build(failed, overwrite=True)
            self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)
            self.assertEqual(sent, ["close_project_path"])
            r, sent = self.build(failed, overwrite=True, replace_edited=True)
            self.assertIn("build_project", sent)


class TestB2OneParsePerCheck(_Client):
    """Review minor 2: the close check hashes the project once (the record already holds the pipeline's c2 hash)."""
    built_real = TestB2RebuildAfterPremieresDrift.built_real

    def counted(self, **kw):
        from lib import verify
        at = []
        with mock.patch.object(verify, "_content_signature", side_effect=verify._content_signature) as m:
            r, sent = self.build(failed, at_job_data=lambda: at.append(m.call_count), **kw)
        return r, sent, at

    def test_the_close_check_parses_once(self):
        self.built_real(age_s=5, cc="pending")
        r, sent, at = self.counted(close=lambda prj: write_prproj(prj, prproj_xml(cc="scanned")), overwrite=True)
        self.assertIn("build_project", sent)
        self.assertEqual(at, [1])

    def test_with_an_editor_save_check_it_is_one_parse_each(self):
        bt = self.built_real(cc="pending")
        write_prproj(self.prj, prproj_xml(cc="scanned", patching="video_first"), bt + 1800)   # drift-only save
        r, sent, at = self.counted(close=lambda prj: write_prproj(prj, prproj_xml(cc="scanned")), overwrite=True)
        self.assertIn("build_project", sent)
        self.assertEqual(at, [2])                       # editor_modified before the close, the close check after it

    def test_editor_modified_reuses_a_fresh_hash(self):
        from lib import verify
        bt = self.built_real(cc="pending")
        write_prproj(self.prj, prproj_xml(cc="scanned", text="Edited"), bt + 1800)
        fresh = verify.prproj_signature(self.prj)
        with mock.patch.object(verify, "_content_signature", side_effect=verify._content_signature) as m:
            self.assertEqual(verify.editor_modified(self.p, current={str(self.prj): fresh})["content"], "changed")
            self.assertEqual(m.call_count, 0)
            self.assertIsNone(verify.editor_modified(self.p, current={str(self.prj): read_json(self.rec_p)
                                                                      ["content_signature"]}))
            self.assertEqual(m.call_count, 0)

    def test_a_large_project_hashes_in_reasonable_time(self):
        from lib.verify import prproj_signature
        xml = prproj_xml(pad=20000)
        self.assertGreater(len(xml), 5_000_000)
        write_prproj(self.prj, xml)
        t = time.perf_counter()
        s = prproj_signature(self.prj)
        dt = time.perf_counter() - t
        print(f"\n  c2 hash of a {len(xml) / 1e6:.1f} MB project XML: {dt:.2f} s", file=_sys.stderr)
        self.assertTrue(s.startswith("c2:"))
        self.assertLess(dt, 30.0)                       # generous: only a pathological slowdown fails


class TestB3NoReplyCountsAsClaimed(unittest.TestCase):
    def test_the_bridges_own_timeout_keeps_the_job_claimed(self):
        q = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, q, True)
        (q / "J1.result.json").write_text(json.dumps({"ok": False, "error": "no reply from PPRO within 20 min"}),
                                          encoding="utf-8")
        r = cep_queue._wait(q, "J1", time.time(), 5, 5, 0.01, "Premiere")
        self.assertIs(r["claimed"], True, r)
        self.assertFalse(r["ok"])
        (q / "J2.result.json").write_text(json.dumps({"ok": False, "error": "script not whitelisted"}), encoding="utf-8")
        self.assertNotIn("claimed", cep_queue._wait(q, "J2", time.time(), 5, 5, 0.01, "Premiere"))


class TestB4Ids(unittest.TestCase):
    def test_real_ids_stay_valid(self):
        from lib.episode import EpisodePaths
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        for vid in ("C0239", "CLIP_6EB37C", "EP02TEST_R02_MO", "EP12_R01", "C0239_MOV", "DR_SHERIF_INTRO_1A2B3C",
                    "Dr Sherif intro", "V1", "clip.v2", "Interview... part 2", "x..y"):
            self.assertEqual(Paths(root, vid).project.name, vid)
        for eid in ("EP12", "EP_1A2B3C", "POD3", "EP02TEST"):
            self.assertEqual(EpisodePaths(root, eid).project.name, eid)

    def test_traversal_and_separators_are_refused(self):
        from lib.episode import EpisodePaths
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        for bad in ("../../assets/X", "..", ".", "a/b", "a\\b", "C:X", "a/../b", "...", " V1", "V1.", "a\x00b"):
            with self.subTest(bad=bad), self.assertRaises(errors.Guidance):
                Paths(root, bad)
        for bad in ("../x", "EP 1", "a/b", "..", "EP1/../../data"):
            with self.subTest(bad=bad), self.assertRaises(errors.Guidance):
                EpisodePaths(root, bad)


def reel(*argv):
    r = subprocess.run([_sys.executable, "-B", str(CLI), *argv], capture_output=True, text=True, encoding="utf-8")
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        doc = None
    return r.returncode, doc, r.stderr


class TestB4Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "Client"
        (self.root / "assets" / "Logos").mkdir(parents=True)
        (self.root / "data" / "Raw").mkdir(parents=True)

    def snapshot(self, d: Path):
        return sorted(x.relative_to(d).as_posix() for x in d.rglob("*"))

    def test_a_video_id_that_climbs_out_is_refused(self):
        before = self.snapshot(self.root / "assets") + self.snapshot(self.root / "data")
        code, doc, err = reel("--root", str(self.root), "preflight", "--video-id", "../../assets/X")
        self.assertEqual(code, 1, (doc, err))
        self.assertIs(doc["ok"], False)
        self.assertIn("video id", doc["error"])
        self.assertEqual(self.snapshot(self.root / "assets") + self.snapshot(self.root / "data"), before)
        self.assertFalse((self.tmp / "assets").exists())

    def test_an_episode_that_climbs_out_is_refused(self):
        code, doc, err = reel("--root", str(self.root), "episode-prep", "--episode", "../../data/X")
        self.assertEqual(code, 1, (doc, err))
        self.assertIn("episode id", doc["error"])
        self.assertEqual(self.snapshot(self.root / "data"), ["Raw"])

    def test_writing_commands_refuse_a_root_that_is_not_a_client(self):
        for root in (self.tmp / "Downloads", self.root / "assets", self.root / "data" / "Raw"):
            root.mkdir(exist_ok=True)
            before = self.snapshot(root)
            with self.subTest(root=root.name):
                code, doc, err = reel("--root", str(root), "preflight", "--video-id", "C1")
                self.assertEqual(code, 1, (doc, err))
                self.assertIn("assets/ and data/", doc["error"])
                self.assertEqual(self.snapshot(root), before)

    def test_read_only_status_stays_lenient(self):
        wrong = self.tmp / "Downloads"
        wrong.mkdir()
        code, doc, err = reel("--root", str(wrong), "lock")
        self.assertNotIn("assets/ and data/", json.dumps(doc) if doc else err)


class TestMinors(unittest.TestCase):
    def test_relative_whynot_home_is_absolute(self):
        from lib import plat
        with mock.patch.dict(os.environ, {"WHYNOT_HOME": "rel-home"}):
            h = plat.engine_home()
        self.assertTrue(h.is_absolute(), h)
        self.assertEqual(h, Path(os.path.abspath("rel-home")))

    def test_prev_names_are_unique_and_glob_safe(self):
        from lib import ppro_build
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        prj = tmp / "X[1]_RE_EDIT.prproj"
        a, b = ppro_build.prev_name(prj), ppro_build.prev_name(prj)
        self.assertNotEqual(a, b)
        self.assertTrue(a.name.startswith("X[1]_RE_EDIT_prev_"))
        a.write_text("x", encoding="utf-8")
        with mock.patch.object(ppro_build, "project_prefix", return_value="RE"):
            p = Paths(tmp / "C", "X[1]")
            p.project = tmp / "proj"
            (p.project / "07_premiere/project").mkdir(parents=True)
            parked = p.project / "07_premiere/project" / a.name
            a.rename(parked)
            self.assertEqual(ppro_build.parked_previous(p)["file"], str(parked))


def low_disk(free: int):
    """shutil.disk_usage as a nearly full disk: `free` bytes left."""
    return mock.patch("lib.build_safety.shutil.disk_usage",
                      return_value=types.SimpleNamespace(total=10 ** 12, used=10 ** 12 - free, free=free))


class TestG2R1BuildSafety(_Client):
    """Addendum G2 R1 (H5 items 1 and 4): free space is checked before a rebuild touches anything, a full disk (ENOSPC)
    is said plainly with the previous project put back, and the build timeout grows with the clip."""

    def test_a_free_space_shortfall_is_refused_with_nothing_written(self):
        self.pipeline_built("OLD")
        before = (self.prj.read_bytes(), self.rec_p.read_bytes())
        with low_disk(100 * 2 ** 20):
            r, sent = self.build(failed, overwrite=True)
        self.assertEqual(r["status"], "NO_DISK_SPACE", r)
        self.assertIs(r["ok"], False)
        self.assertIn("not enough free space", r["error"])
        self.assertIn("Free up space", r["how"])
        self.assertEqual(sent, [])                                       # not even the close (it saves the project)
        self.assertEqual((self.prj.read_bytes(), self.rec_p.read_bytes()), before)
        self.assertEqual(list(self.prj.parent.glob("*_prev_*")), [])

    def test_enough_free_space_builds(self):
        self.pipeline_built("OLD")
        with low_disk(10 * 2 ** 30):
            r, sent = self.build(failed, overwrite=True)
        self.assertIn("build_project", sent)
        self.assertEqual(r["status"], "FAILED", r)

    def test_enospc_during_the_build_puts_the_old_project_back_and_says_so_plainly(self):
        self.pipeline_built("OLD")

        def disk_full(prj):
            e = OSError(errno.ENOSPC, "No space left on device")
            e.wnc_claimed = False                                        # cep_queue: the job file was never written
            raise e
        r, sent = self.build(disk_full, overwrite=True)
        self.assertEqual(r["status"], "DISK_FULL", r)
        self.assertIs(r["ok"], False)
        self.assertRegex(r["error"], r"^The disk is full: free up space on \S.* and try again$")
        self.assertIn("OLD", ungz(self.prj))                             # the previous project is back in place
        self.assertEqual(list(self.prj.parent.glob("*_prev_*")), [])

    def test_the_build_timeout_scales_with_the_clip_length(self):
        from lib import ppro_build
        seen = []

        def submit(action, data=None, timeout=0, **k):
            seen.append((action, timeout))
            return failed(None)
        for dur, want in ((30.0, 900), (150.0, 900), (600.0, 3600)):
            seen.clear()
            with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                    mock.patch("lib.ppro_bridge.submit", side_effect=submit), \
                    mock.patch.object(ppro_build, "job_data", return_value=dict(DATA, duration_s=dur)):
                ppro_build.build(self.p)
            self.assertEqual([t for a, t in seen if a == "build_project"], [want], dur)


def built_with_new(prj):
    gz(prj, "NEW")
    return {"ok": True, "response": {"ok": True, "action": "build_project", "result": {"placed": []}}}


class TestG2R1ServeBuildIsTheCliBuild(_Client):
    """Addendum G2 R1 (P0): build_project from `reel serve` runs the CLI's ppro-build (ppro_build.build_for_serve):
    Gate 1 approval, the build lock, the editor-changes and unsaved-changes checks and `_prev_` parking. The raw bridge
    action with the client's data is never sent, and overwrite_existing:true is --force, never --replace-edited."""

    def approve(self, fingerprint=None):
        from lib.plan import APPROVAL_FORMAT, plan_fingerprint
        write_json(self.p.p("01_analysis/plan-approval.json"),          # what a 3.0 approve-plan writes
                   {"approved": True, "by": "editor", "plan_fingerprint": fingerprint or plan_fingerprint(self.p),
                    "format": APPROVAL_FORMAT})

    def serve(self, answer, data=None, close_result=None):
        """build_project through serve's FileQueueAdapter, with this class's fake bridge (job_data faked as DATA)."""
        import asyncio
        from datetime import datetime, timedelta, timezone
        from lib import ppro_build
        from serve import adapters
        sent = []
        self.sent_data = []

        def submit(action, data=None, timeout=0, **k):
            sent.append(action)
            self.sent_data.append((action, data))
            if action == "close_project_path":
                res = close_result(data) if close_result else {"closed": True}
                return {"ok": True, "response": {"ok": True, "action": action, "result": res}}
            return answer(self.prj)
        req = {"protocol": 4, "id": "s1", "action": "build_project",
               "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat(),
               "data": dict({"project_path": str(self.prj), "overwrite_existing": True,
                             "xml_path": "C:\\elsewhere\\client.xml", "sequence_name": "S", "graphics": []}, **(data or {}))}
        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                mock.patch("lib.ppro_bridge.submit", side_effect=submit), \
                mock.patch.object(ppro_build, "job_data", return_value=dict(DATA)):
            res = asyncio.run(adapters.FileQueueAdapter().run(req))
        self.assertEqual((res["action"], res["id"]), ("build_project", "s1"))
        return res, sent

    def never(self, prj):
        raise AssertionError("build_project reached the bridge")

    def test_a_rebuild_parks_the_old_project_as_prev_while_holding_the_build_lock(self):
        self.pipeline_built("OLD")
        self.approve()
        lock = self.home / "ppro-queue" / cep_queue.LOCK_NAME
        seen = {}

        def answer(prj):
            seen.update(lock=lock.exists(), moved=not prj.exists(),
                        parked=["OLD" in ungz(f) for f in prj.parent.glob("*_prev_*.prproj")])
            return built_with_new(prj)
        res, sent = self.serve(answer)
        self.assertEqual(seen, {"lock": True, "moved": True, "parked": [True]})
        self.assertFalse(lock.exists())                                  # released after the build
        self.assertEqual(sent, ["close_project_path", "build_project"])
        self.assertNotIn("client.xml", json.dumps(self.sent_data[-1][1]))   # the job comes from the plan, not the request
        self.assertIn("NEW", ungz(self.prj))
        self.assertEqual(["OLD" in ungz(f) for f in self.prj.parent.glob("*_prev_*.prproj")], [True])
        self.assertIs(res["ok"], False)                                  # the fake readback fails the build checks
        self.assertIn("checks failed", res["error"])

    def test_unsaved_changes_in_premiere_are_refused_as_in_the_cli(self):
        self.pipeline_built("OLD")
        self.approve()
        res, sent = self.serve(self.never, close_result=lambda d: {"closed": False, "dirty": True})
        self.assertIs(res["ok"], False)
        self.assertIn("unsaved changes", res["error"])
        self.assertEqual(sent, ["close_project_path"])
        self.assertIn("OLD", ungz(self.prj))
        self.assertEqual(list(self.prj.parent.glob("*_prev_*")), [])

    def test_an_unapproved_or_stale_plan_is_refused(self):
        self.pipeline_built("OLD")
        for approve in (None, "an-older-plan"):
            if approve:
                self.approve(approve)
            res, sent = self.serve(self.never)
            self.assertIs(res["ok"], False, approve)
            self.assertIn("not approved", res["error"])
            self.assertEqual(sent, [])
            self.assertIn("OLD", ungz(self.prj))

    def test_overwrite_existing_takes_no_shortcut_past_the_editor_check(self):
        bt = self.pipeline_built("OLD")
        self.approve()
        gz(self.prj, "EDITED BY THE EDITOR", bt + 1800)
        res, sent = self.serve(self.never, data={"overwrite_existing": True})
        self.assertIs(res["ok"], False)
        self.assertIn("editor saved changes", res["error"])
        self.assertEqual(sent, [])
        self.assertIn("EDITED BY THE EDITOR", ungz(self.prj))

    def test_without_overwrite_an_existing_project_is_refused(self):
        self.pipeline_built("OLD")
        self.approve()
        res, sent = self.serve(lambda prj: {"ok": True, "response": {"ok": True, "action": "build_project", "result": {
            "error": "project exists (set overwrite_existing)"}}}, data={"overwrite_existing": False})
        self.assertIs(res["ok"], False)
        self.assertIn("already exists", res["error"])
        self.assertIn("overwrite_existing", res["how"])
        self.assertEqual(sent, [])

    def test_the_serve_journal_follows_the_builds_own_queue_job(self):
        """With H1's job journal: the build's queue job carries the plan's data, not the request's, so the router's
        watcher (a hash of the request data) cannot match it. The safe route links it: the first build_project job
        written to the queue once the build began is journaled with its job id and state (queued / claimed)."""
        from serve import jobs
        self.pipeline_built("OLD")
        self.approve()
        journal = jobs.Journal(self.home)
        journal.start("s1", action="build_project", session_kind="cli", route="cep", lane="premiere",
                      data={"project_path": "as the client sent it"})
        q = self.home / "ppro-queue"

        def answer(prj):                                                 # what cep_queue + the bridge leave behind
            (q / "J1.data.json").write_text(json.dumps({"action": "build_project", "job_id": "J1", "graphics": []}),
                                            encoding="utf-8")
            (q / "J1.running").write_text("", encoding="utf-8")
            deadline = time.time() + 10
            while time.time() < deadline and (journal.get("s1") or {}).get("state") != "claimed":
                time.sleep(0.1)
            return built_with_new(prj)
        self.serve(answer)
        entry = journal.get("s1")
        self.assertEqual((entry.get("job_id"), entry["state"]), ("J1", "claimed"))

    def test_a_project_path_that_is_not_this_reels_project_is_refused(self):
        self.approve()
        for path in (self.tmp / "elsewhere" / "V1_EDIT.prproj", self.prj.with_name("OTHER_EDIT.prproj"), "relative.prproj"):
            res, sent = self.serve(self.never, data={"project_path": str(path)})
            self.assertIs(res["ok"], False, path)
            self.assertIn("nothing was built", res["error"])
            self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
