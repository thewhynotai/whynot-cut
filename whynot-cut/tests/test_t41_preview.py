"""3.0 T4.1 smooth zoom and fades in the preview video (lib/preview_video.py), from the spec's `camera_ease` and
`fades` through lib/camera_ease.value_at / fade_gain, so the editor watches what Premiere will play.

The source is a still picture (a white square on black), so the square's width in a preview frame is the zoom at that
frame: a hard punch-in jumps, an eased one passes through an intermediate width (acceptance: "preview-video frame
test shows intermediate scale during the ease"). Picture fades darken the frame; sound fades ramp the mix. The frame
work is lane-independent: a GPU lane (encoder and decoder swapped for the CPU's here: no GPU in tests) gives the same
frames. A spec without the keys renders as before.
Run:  bash tools/test.sh -p test_t41_preview.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
import wave  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

import numpy as np  # noqa: E402

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import write_json  # noqa: E402
import test_pipeline as tp  # noqa: E402  (module import: its TestCases are not collected again here)

PW = 270                  # preview width (the sequence is 1080 x 1920: the preview is 270 x 480)
PH = 480
PUNCH = 1.5               # a strong punch-in so the widths are far apart
# sequence 24 fps: the punch-in runs 1.000-3.000 s = frames 24-72; 250 ms ease = 6 frames
F_BEFORE, F_START, F_MID, F_FULL, F_OUT_MID, F_AFTER = 18, 24, 27, 48, 69, 80


def ffmpeg():
    return common.ffmpeg_exe()


class _Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root, cls.p, _ = tp.make_project(cls.tmp)
        # the footage becomes a still picture: a 60 x 60 white square in the middle of a black 216 x 384 frame
        clip = cls.root / "data/Raw/CLIP1.mov"
        subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "color=c=black:s=216x384:r=25:d=12,drawbox=x=78:y=162:w=60:h=60:color=white:t=fill",
                        "-f", "lavfi", "-i", "sine=f=440:r=48000:d=12", "-ac", "2", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-shortest", str(clip)], check=True)
        from lib.discover import run_discovery
        from lib.client_db import build
        from lib.media import preflight
        from lib.plan import compile_plan
        with common.use_context(common.Context(root=cls.root)):
            build(cls.p, run_discovery(cls.p)["inventory"])
            preflight(cls.p, [clip])
            write_json(cls.p.p("01_analysis/edit-decisions.json"), {
                "video_id": "CLIP1",
                "global": {"main_footage": "data/Raw/CLIP1.mov",
                           "captions_hidden_ranges": [["00:00:00.000", "00:00:12.000"]]},
                "decisions": [{"decision_id": "EDIT_001", "segment_id": "SEG_001", "evidence": "هل في حاجات معينة",
                               "start": "00:00:00.200", "end": "00:00:04.000", "semantic_intent": "hook",
                               "visual_treatment": "hook", "confidence": "high",
                               "camera": {"type": "punch_in", "at": "00:00:01.000", "until": "00:00:03.000",
                                          "scale_factor": PUNCH}}]})
            r = compile_plan(cls.p)
            assert r["ok"], r["errors"]
        cls.spec_f = cls.p.p("01_analysis/timeline-spec.json")
        cls.base = json.loads(cls.spec_f.read_text(encoding="utf-8"))
        for k in ("camera_ease", "fades"):            # the plain spec (as before T4.1)
            cls.base.pop(k, None)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def write_spec(self, style: dict | None):
        """The spec with camera_ease / fades computed from `style` (None: the plain spec)."""
        from lib.camera_ease import spec_fields
        from lib.stamps import stamp
        spec = dict(self.base)
        if style is not None:
            fields, _ = spec_fields(spec["main_segments"], style, spec["fps"], spec["duration_ms"])
            spec.update(fields)
        write_json(self.spec_f, stamp(spec))
        return spec

    def render(self, lane="cpu"):
        from lib.preview_video import render
        with common.use_context(common.Context(root=self.root)), contextlib.redirect_stderr(io.StringIO()):
            r = render(self.p, width=PW, workers=1, lane=lane)
        self.assertTrue(r["ok"], r)
        return Path(r["video"])

    def frame(self, mp4: Path, n: int) -> np.ndarray:
        r = subprocess.run([ffmpeg(), "-loglevel", "error", "-i", str(mp4), "-vf", f"select=eq(n\\,{n})",
                            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True)
        a = np.frombuffer(r.stdout, dtype=np.uint8)
        self.assertEqual(a.size, PW * PH, f"frame {n}")
        return a.reshape(PH, PW)

    def width(self, mp4: Path, n: int) -> int:
        """The white square's width in frame n (the widest row in the middle band; captions are hidden)."""
        band = self.frame(mp4, n)[int(PH * 0.25):int(PH * 0.65)]
        return int((band > 128).sum(axis=1).max())

    def centre(self, mp4: Path, n: int) -> float:
        a = self.frame(mp4, n)
        return float(a[PH // 2 - 4:PH // 2 + 4, PW // 2 - 4:PW // 2 + 4].mean())


class TestSmoothZoom(_Fixture):
    def test_eased_punch_in_passes_through_an_intermediate_scale(self):
        self.write_spec({"camera": {"ease_ms": 250}})
        mp4 = self.render()
        w0, w_full = self.width(mp4, F_BEFORE), self.width(mp4, F_FULL)
        self.assertGreater(w_full, w0 * 1.35, (w0, w_full))            # the punch-in itself (x1.5)
        self.assertLessEqual(abs(self.width(mp4, F_START) - w0), 3)    # the ease starts from the picture before it
        mid = self.width(mp4, F_MID)
        self.assertTrue(w0 + 6 < mid < w_full - 6, (w0, mid, w_full))
        out_mid = self.width(mp4, F_OUT_MID)
        self.assertTrue(w0 + 3 < out_mid < w_full - 3, (w0, out_mid, w_full))
        self.assertLessEqual(abs(self.width(mp4, F_AFTER) - w0), 3)

    def test_the_same_frames_on_a_gpu_lane(self):
        """The ease is drawn before the encoder: a GPU lane (here with the CPU's codec arguments, no GPU in tests)
        gives the same intermediate frame."""
        from lib import accel
        self.write_spec({"camera": {"ease_ms": 250}})
        cpu_args = accel.h264_args("cpu", 23)
        with mock.patch.object(accel, "decode_args", return_value=[]), \
                mock.patch.object(accel, "h264_args", return_value=cpu_args):
            mp4 = self.render(lane="cuda")
        w0, mid, w_full = self.width(mp4, F_BEFORE), self.width(mp4, F_MID), self.width(mp4, F_FULL)
        self.assertTrue(w0 + 6 < mid < w_full - 6, (w0, mid, w_full))

    def test_r3_slow_push_grows_across_its_piece(self):
        """Round 3, item 1: a slow_push (static scale in the spec) pushes in across its whole piece."""
        from lib.camera_ease import spec_fields
        from lib.stamps import stamp
        spec = dict(self.base)
        spec["main_segments"] = [dict(m, camera="slow_push") if m.get("decision_id") == "EDIT_001" else m
                                 for m in spec["main_segments"]]
        spec.update(spec_fields(spec["main_segments"], {}, spec["fps"], spec["duration_ms"])[0])
        write_json(self.spec_f, stamp(spec))
        mp4 = self.render()
        w0, w_q, w_mid, w_end = (self.width(mp4, n) for n in (F_BEFORE, 36, F_FULL, 71))   # 36: a quarter into the push (bezier: slow start)
        self.assertLessEqual(abs(self.width(mp4, F_START) - w0), 3)
        self.assertTrue(w0 < w_q < w_mid < w_end, (w0, w_q, w_mid, w_end))
        self.assertGreater(w_end, w0 * 1.4)

    def test_without_the_keys_the_punch_is_hard_as_before(self):
        self.write_spec(None)
        mp4 = self.render()
        self.assertLessEqual(abs(self.width(mp4, F_START) - self.width(mp4, F_FULL)), 3)


class TestFades(_Fixture):
    def test_picture_fades_in_and_out(self):
        spec = self.write_spec({"camera": {"ease_ms": 0}, "fades": {"video_in_ms": 1000, "video_out_ms": 1000}})
        mp4 = self.render()
        last = spec["duration_frames"] - 1
        full = self.centre(mp4, 40)
        self.assertGreater(full, 200)
        self.assertLess(self.centre(mp4, 0), 30)
        self.assertTrue(70 < self.centre(mp4, 12) < 190, self.centre(mp4, 12))      # half way into the fade-in
        self.assertLess(self.centre(mp4, last), 40)

    def test_no_fade_keeps_the_first_frame(self):
        self.write_spec({"camera": {"ease_ms": 0}})
        mp4 = self.render()
        self.assertGreater(self.centre(mp4, 0), 200)

    def rms(self, x, a_s, b_s):
        seg = x[int(a_s * 48000):int(b_s * 48000)]
        return float(np.sqrt(np.mean(seg ** 2)))

    def audio(self, style):
        from lib.common import spec_footage
        from lib.preview_video import build_audio
        spec = self.write_spec(style)
        out = self.tmp / "a.wav"
        with common.use_context(common.Context(root=self.root)):
            build_audio(self.p, spec, out, spec_footage(self.p, spec))
        with wave.open(str(out)) as w:
            x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)[::2] / 32767
        return x, spec

    def test_sound_fades_in_and_out(self):
        x, spec = self.audio({"camera": {"ease_ms": 0}, "fades": {"audio_in_ms": 1000, "audio_out_ms": 1000}})
        end = spec["duration_frames"] / spec["fps"]
        steady = self.rms(x, 4.0, 4.2)
        self.assertGreater(steady, 0.01)
        self.assertLess(self.rms(x, 0.0, 0.1), steady * 0.15)
        self.assertTrue(steady * 0.3 < self.rms(x, 0.45, 0.55) < steady * 0.7)
        self.assertLess(self.rms(x, end - 0.1, end), steady * 0.15)

    def test_r3_the_hook_sfx_at_frame_0_is_not_faded(self):
        """Round 3, item 3: the dialogue (and music) fade in; an SFX cue at frame 0 plays at its full level."""
        sfx = self.tmp / "hook_sfx.wav"
        t = np.arange(int(0.4 * 48000)) / 48000
        x = (0.3 * np.sin(2 * np.pi * 1000 * t) * 32767).astype(np.int16)
        with wave.open(str(sfx), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(48000)
            w.writeframes(x.tobytes())
        cue_f = self.p.p("06_audio/audio-cue-sheet.json")
        keep = cue_f.read_text(encoding="utf-8")
        self.addCleanup(cue_f.write_text, keep, encoding="utf-8")
        write_json(cue_f, {"cues": [{"cue_id": "HOOK", "kind": "pop", "start_frame": 0, "gain_db": 0,
                                     "source_file": str(sfx)}], "fps": 24})
        y, _ = self.audio({"camera": {"ease_ms": 0}, "fades": {"audio_in_ms": 1000}})
        sfx_rms = 0.3 / np.sqrt(2)
        self.assertGreater(self.rms(y, 0.0, 0.1), sfx_rms * 0.8)          # the SFX at full level under the fade

    def test_no_sound_fade_keeps_the_start(self):
        x, _ = self.audio({"camera": {"ease_ms": 0}})
        self.assertGreater(self.rms(x, 0.3, 0.4), self.rms(x, 4.0, 4.2) * 0.8)


if __name__ == "__main__":
    unittest.main()
