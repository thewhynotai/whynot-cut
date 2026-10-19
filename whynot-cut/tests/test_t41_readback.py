"""3.0 T4.1 smooth zoom and fades: the ppro-build side (job fields from the spec, read-back checks) with the bridge
mocked, and the build_project contract.

* `ppro_build.ease_job_fields(spec)` -> {"camera_keys": the spec's runs (or []), "fades": seconds + end_s (or None)}.
  An old spec without the keys builds exactly as today (C14). No paths inside: identical on darwin and win32 (C32).
* `ppro_build.ease_checks(job, result)` -> {"punch_ins_eased", "fades_applied"}: true when nothing was asked; else each
  run has a read-back entry with 2 Scale + 2 Position keys per eased side, interpolation "bezier", ok (C27-C30).
* `build()` puts both into `checks`, so a short read-back gives PRPROJ_BUILT_WITH_ISSUES.
* Contract: `data` takes camera_keys and fades and still refuses an unknown field; `readback` names eased and faded (C31).
Run:  bash tools/test.sh -p test_t41_readback.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import gzip  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402
from contract import validator as V  # noqa: E402


def val(sf=1.0, ox=0.0, oy=0.0):
    return {"scale_factor": sf, "offset_x": ox, "offset_y": oy}


def run(pieces=(1, 1), ein=True, eout=True, did="EDIT_001"):
    a, b = pieces
    return {"decision_id": did, "camera": "punch_in", "pieces": [a, b],
            "ease_in": {"piece": a, "frames": 6, "from": val(), "value": val(1.1)} if ein else None,
            "ease_out": {"piece": b, "frames": 6, "value": val(1.1), "to": val()} if eout else None,
            "interpolation": "bezier"}


def spec(runs=None, fades=None):
    s = {"fps": 24, "duration_ms": 10000, "duration_frames": 240,
         "main_segments": [{"start_frame": 0, "end_frame": 24}, {"start_frame": 24, "end_frame": 72},
                           {"start_frame": 72, "end_frame": 240}], "events": []}
    if runs is not None:
        s["camera_ease"] = {"ease_ms": 250, "runs": runs}
    if fades is not None:
        s["fades"] = fades
    return s


SET = "bezier (set, not read back)"          # review I2: what the CEP bridge can honestly say


def eased(r, scale=4, pos=4, interp=SET, ok=True):
    return {"decision_id": r["decision_id"], "pieces": r["pieces"], "scale_keys": scale, "position_keys": pos,
            "interpolation": interp, "interpolation_verified": False, "ok": ok}


def pb():
    from lib import ppro_build
    return ppro_build


class TestJobFields(unittest.TestCase):
    def test_c14_an_old_spec_asks_for_nothing(self):
        """Review 2 M-f: nothing asked = nothing added to the job (the plain client's job as before T4.1)."""
        self.assertEqual(pb().ease_job_fields(spec()), {})
        self.assertEqual(pb().ease_job_fields(spec([], None)), {})

    def test_runs_and_fades_in_seconds(self):
        f = pb().ease_job_fields(spec([run()], {"video_in_ms": 500, "video_out_ms": 0, "audio_in_ms": 0,
                                                "audio_out_ms": 1500}))
        self.assertEqual(f["camera_keys"], [run()])
        self.assertEqual(f["fades"], {"video_in_s": 0.5, "video_out_s": 0.0, "audio_in_s": 0.0, "audio_out_s": 1.5,
                                      "end_s": 10.0})

    def test_end_follows_the_sequence_frames(self):
        s = spec(None, {"video_in_ms": 0, "video_out_ms": 1000, "audio_in_ms": 0, "audio_out_ms": 0})
        s["duration_frames"] = 250
        self.assertAlmostEqual(pb().ease_job_fields(s)["fades"]["end_s"], 250 / 24)

    def test_c32_darwin_and_windows_are_identical(self):
        s = spec([run(did="قص_١")], {"video_in_ms": 500, "video_out_ms": 0, "audio_in_ms": 0, "audio_out_ms": 0})
        outs = []
        for plat in ("darwin", "win32"):
            with mock.patch.object(sys, "platform", plat):
                outs.append(json.dumps(pb().ease_job_fields(s), sort_keys=True, ensure_ascii=False))
        self.assertEqual(outs[0], outs[1])


class TestRound3(unittest.TestCase):
    def test_item3_only_dialogue_music_and_originals_fade(self):
        base = [{"xml_index": "1-2", "id": "A01"}, {"xml_index": "3-4", "id": "A03"}, {"xml_index": "5-6", "id": "A04"},
                {"xml_index": "7-8", "id": "A05"}, {"xml_index": "9-10", "id": "A06"}, {"xml_index": "11-12", "id": "A07"}]
        self.assertEqual(pb().fade_audio_tracks(base), [1, 2, 9, 10, 11, 12])
        self.assertEqual(pb().fade_audio_tracks([{"xml_index": "1-2", "id": "A01"}]), [1, 2])

    def test_item3_the_job_names_the_audio_tracks_to_fade(self):
        fd = {"video_in_ms": 0, "video_out_ms": 0, "audio_in_ms": 500, "audio_out_ms": 0}
        f = pb().ease_job_fields(spec(None, fd), audio_tracks=[1, 2])
        self.assertEqual(f["fades"]["audio_tracks"], [1, 2])

    def test_item4_mid_ease_frames(self):
        s = spec([run((1, 1))])                      # piece 1 = frames 24-72, eases of 6 frames
        q = pb().ease_qc_frames(s)
        # round 4 M-6: the CENTRE of the frame, so a 29.97 time never snaps to the frame before
        self.assertEqual(q, [{"decision_id": "EDIT_001", "piece": 1, "frame": 27, "t_s": 1.146, "why": "mid ease-in"},
                             {"decision_id": "EDIT_001", "piece": 1, "frame": 69, "t_s": 2.896, "why": "mid ease-out"}])

    def test_r4_m6_frame_centres_at_25_and_29_97(self):
        for fps, want in ((25, 1.1), (30000 / 1001, 0.918)):
            with self.subTest(fps=fps):
                s = spec([run((1, 1))])
                s["fps"] = fps
                q = pb().ease_qc_frames(s)[0]
                self.assertEqual(q["frame"], 27)
                self.assertEqual(q["t_s"], want)
                self.assertEqual(int(q["t_s"] * fps), 27)       # inside frame 27, never at its very start
        self.assertEqual(pb().ease_qc_frames(spec()), [])

    def test_item4_a_slow_push_names_its_middle(self):
        r = run((1, 1), eout=False)
        r["camera"] = "slow_push"
        r["ease_in"]["frames"] = 47
        q = pb().ease_qc_frames(spec([r]))
        self.assertEqual([(x["frame"], x["why"]) for x in q], [(24 + 23, "mid push")])

    def test_item4_a_one_frame_ease_is_its_own_frame(self):
        r = run((1, 1), eout=False)
        r["ease_in"]["frames"] = 1
        self.assertEqual(pb().ease_qc_frames(spec([r]))[0]["frame"], 24)


class TestChecks(unittest.TestCase):
    def job(self, runs=(), fades=None):
        return {"camera_keys": list(runs), "fades": fades}

    def test_nothing_asked_adds_no_check(self):
        """Review 2 M-f: the two checks exist only when the plan asked for smooth zoom / fades."""
        self.assertEqual(pb().ease_checks(self.job(), {}), {})
        self.assertEqual(pb().ease_checks({}, {}), {})
        self.assertEqual(set(pb().ease_checks(self.job([run()]), {})), {"punch_ins_eased"})

    def test_all_there(self):
        r = run()
        self.assertTrue(pb().ease_checks(self.job([r]), {"eased": [eased(r)]})["punch_ins_eased"])

    def test_one_side_expects_two_keys(self):
        r = run(eout=False)
        self.assertTrue(pb().ease_checks(self.job([r]), {"eased": [eased(r, 2, 2)]})["punch_ins_eased"])
        self.assertFalse(pb().ease_checks(self.job([r]), {"eased": [eased(r, 4, 4)]})["punch_ins_eased"])

    def test_c27_fewer_keys_is_false(self):
        r = run()
        self.assertFalse(pb().ease_checks(self.job([r]), {"eased": [eased(r, 3, 4)]})["punch_ins_eased"])
        self.assertFalse(pb().ease_checks(self.job([r]), {"eased": [eased(r, 4, 2)]})["punch_ins_eased"])

    def test_c28_linear_is_false(self):
        r = run()
        for interp in ("linear (fallback)", "linear", None, "bezier"):      # plain "bezier" would claim a read-back
            with self.subTest(interp=interp):
                self.assertFalse(pb().ease_checks(self.job([r]), {"eased": [eased(r, interp=interp)]})["punch_ins_eased"])

    def test_not_ok_is_false(self):
        r = run()
        self.assertFalse(pb().ease_checks(self.job([r]), {"eased": [eased(r, ok=False)]})["punch_ins_eased"])

    def test_c29_an_older_bridge_without_eased(self):
        self.assertFalse(pb().ease_checks(self.job([run()]), {})["punch_ins_eased"])

    def test_a_run_missing_from_the_readback(self):
        a, b = run((1, 1), did="A"), run((3, 3), did="B")
        self.assertFalse(pb().ease_checks(self.job([a, b]), {"eased": [eased(a)]})["punch_ins_eased"])
        self.assertTrue(pb().ease_checks(self.job([a, b]), {"eased": [eased(a), eased(b)]})["punch_ins_eased"])

    def test_two_runs_of_one_decision_are_told_apart_by_their_pieces(self):
        a, b = run((1, 1), did="A"), run((3, 3), did="A")
        self.assertFalse(pb().ease_checks(self.job([a, b]), {"eased": [eased(a), eased(a)]})["punch_ins_eased"])

    def test_c30_fades(self):
        """Review 2 IMP-2: the picture fade is one black matte over everything, so fades_applied means: a matte clip
        over each fade window (from 0 to the fade-in end, from the fade-out start to the end) with its opacity keys;
        a sound fade still needs the first / last clip of A1 (review M5)."""
        fd = {"video_in_s": 1.0, "video_out_s": 1.0, "audio_in_s": 0.0, "audio_out_s": 1.0, "end_s": 8.0}
        tracks = {"video": [{"i": 1, "name": "V1", "clips": 3}], "audio": [{"i": 1, "name": "A1", "clips": 2}]}
        m_in, m_out = {"start": 0.0, "end": 1.0, "keys": 2}, {"start": 7.0, "end": 8.0, "keys": 2}
        ok = {"ok": True, "matte": [m_in, m_out], "audio": [{"track": 1, "clip": 1, "keys": 2}]}
        chk = pb().ease_checks

        def res(**kw):
            return {"faded": dict(ok, **kw), "tracks": tracks}
        self.assertTrue(chk(self.job(fades=fd), res())["fades_applied"])
        self.assertFalse(chk(self.job(fades=fd), {})["fades_applied"])
        self.assertFalse(chk(self.job(fades=fd), {"faded": ok})["fades_applied"])            # no track read-back
        self.assertFalse(chk(self.job(fades=fd), res(ok=False))["fades_applied"])
        self.assertFalse(chk(self.job(fades=fd), res(audio=[]))["fades_applied"])
        self.assertFalse(chk(self.job(fades=fd), res(matte=[m_out]))["fades_applied"])              # no fade-in matte
        self.assertFalse(chk(self.job(fades=fd), res(matte=[m_in]))["fades_applied"])               # no fade-out matte
        self.assertFalse(chk(self.job(fades=fd), res(matte=[m_in, dict(m_out, keys=1)]))["fades_applied"])
        self.assertFalse(chk(self.job(fades=fd), res(matte=[m_in, dict(m_out, start=6.0)]))["fades_applied"])
        self.assertFalse(chk(self.job(fades=fd), res(audio=[{"track": 1, "clip": 0, "keys": 2}]))["fades_applied"])
        self.assertTrue(chk(self.job(fades=dict(fd, audio_out_s=0.0)), res(audio=[]))["fades_applied"])
        self.assertTrue(chk(self.job(fades=dict(fd, video_out_s=0.0)), res(matte=[m_in]))["fades_applied"])

    def test_c30_old_per_layer_video_read_back_does_not_count(self):
        fd = {"video_in_s": 1.0, "video_out_s": 0.0, "audio_in_s": 0.0, "audio_out_s": 0.0, "end_s": 8.0}
        res = {"faded": {"ok": True, "video": [{"track": 1, "clip": 0, "keys": 2}], "audio": []},
               "tracks": {"video": [{"i": 1, "clips": 1}], "audio": [{"i": 1, "clips": 1}]}}
        self.assertFalse(pb().ease_checks(self.job(fades=fd), res)["fades_applied"])


class TestBuildChecks(unittest.TestCase):
    """build() with the bridge mocked: the two checks land in `checks` and decide the status."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        ctx = common.use_context(common.Context(home=self.tmp / "home"))
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        (self.tmp / "home").mkdir()
        root = self.tmp / "عميل تجربة"                       # Arabic client folder
        (root / "assets").mkdir(parents=True)
        (root / "data").mkdir()
        self.p = Paths(root, "V1")
        self.p.ensure_project()
        write_json(self.p.p("01_analysis/timeline-spec.json"), spec())
        self.prj = self.p.p(f"07_premiere/project/V1_{common.project_prefix()}_EDIT.prproj")
        self.prj.parent.mkdir(parents=True, exist_ok=True)

    def build(self, job_extra, result_extra):
        from lib import ppro_build
        data = {"_missing": [], "graphics": [], "native_caption_track": False, "sharpen_v1": None,
                "sequence_name": "V1", "track_names": {}, **job_extra}
        sent = []

        def submit(action, d=None, timeout=0, **k):
            sent.append((action, d))
            with gzip.open(self.prj, "wb") as f:
                f.write(b"<Project><Sequence>BUILT</Sequence></Project>")
            return {"ok": True, "claimed": True, "response": {"ok": True, "result": dict(result_extra)}}

        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                mock.patch("lib.ppro_bridge.submit", side_effect=submit), \
                mock.patch.object(ppro_build, "job_data", return_value=data):
            r = ppro_build.build(self.p)
        return r, sent

    def test_a_short_readback_is_an_issue(self):
        r_ = run()
        r, sent = self.build({"camera_keys": [r_], "fades": None}, {"eased": [eased(r_, 2, 2)]})
        self.assertIn("punch_ins_eased", r["checks"])
        self.assertFalse(r["checks"]["punch_ins_eased"])
        self.assertNotIn("fades_applied", r["checks"])                  # no fade asked: no check (review 2 M-f)
        self.assertNotEqual(r["status"], "PRPROJ_BUILT")
        job = dict(sent[-1][1])
        self.assertEqual(job["camera_keys"], [r_])             # sent to the bridge as is

    def test_the_readback_is_kept_in_the_result(self):
        r_ = run()
        r, _ = self.build({"camera_keys": [r_], "fades": None}, {"eased": [eased(r_)]})
        self.assertTrue(r["checks"]["punch_ins_eased"])
        self.assertEqual(r["result"]["eased"], [eased(r_)])


    def test_r4_m1_a_failed_fade_is_said_in_plain_words(self):
        r_ = {"video_in_s": 1.0, "video_out_s": 0.0, "audio_in_s": 0.0, "audio_out_s": 0.0, "end_s": 8.0}
        r, _ = self.build({"fades": r_}, {"faded": {"matte": [], "audio": [], "ok": False}})
        self.assertFalse(r["checks"]["fades_applied"])
        w = r["warnings"]
        self.assertTrue(any("fade" in x and "result." not in x and "faded" not in x for x in w), w)
        self.assertTrue(any("\u0621" <= ch <= "\u064a" for x in w for ch in x), w)

    def test_mf_a_plain_job_has_the_checks_of_before(self):
        r, sent = self.build({}, {})
        self.assertNotIn("punch_ins_eased", r["checks"])
        self.assertNotIn("fades_applied", r["checks"])
        self.assertNotIn("qc_frames", r)
        job = dict(sent[-1][1])
        self.assertNotIn("camera_keys", job)
        self.assertNotIn("fades", job)


class TestContract(unittest.TestCase):
    def data(self, **kw):
        d = {"project_path": "C:/x/R.prproj", "xml_path": "C:/x/R.xml", "sequence_name": "S",
             "settings": {"previewCodec": "apcs"}, "graphics": [], "markers": [],
             "track_names": {"video": [], "audio": []}}
        d.update(kw)
        return d

    def test_c31_data_takes_the_new_fields(self):
        d = self.data(camera_keys=[run()], fades={"video_in_s": 0.5, "video_out_s": 0, "audio_in_s": 0,
                                                  "audio_out_s": 0, "end_s": 8})
        self.assertEqual(V.validate(d, "build_project#/$defs/data"), [])
        self.assertEqual(V.validate(self.data(camera_keys=[], fades=None), "build_project#/$defs/data"), [])

    def test_c31_an_unknown_field_is_still_refused(self):
        self.assertNotEqual(V.validate(self.data(zzz=1), "build_project#/$defs/data"), [])

    def test_c31_a_bad_run_is_refused(self):
        self.assertNotEqual(V.validate(self.data(camera_keys=[{"pieces": "x"}]), "build_project#/$defs/data"), [])

    def test_readback_names_eased_and_faded(self):
        props = V.load("build_project")["$defs"]["readback"]["properties"]
        self.assertIn("eased", props)
        self.assertIn("faded", props)


if __name__ == "__main__":
    unittest.main()
