# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""T4.14 hook (onboard.py.patch): the doctor's accelerator line names the GPU precision of the model the editor uses
(transcription.json gpu_compute_types), not the old single key. Red without the patch.
Run:  bash tools/test.sh -p test_transcribe_precision_hooks.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import os
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
if str(SK / "engine" / "reel") not in _sys.path:
    _sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import onboard  # noqa: E402
from lib import settings as S  # noqa: E402

CUDA_VIDEO = {"kind": "cuda", "name": "NVIDIA GPU"}


class AcceleratorLine(unittest.TestCase):
    def line(self, cfg, model="large-v3"):
        with mock.patch.dict(os.environ, {"WHYNOT_ACCEL": "auto"}), \
                mock.patch.object(onboard, "load_config", return_value=cfg, create=True), \
                mock.patch("lib.common.load_config", return_value=cfg), \
                mock.patch.object(S, "load", return_value=dict(S.DEFAULTS, whisper_model=model)):
            return onboard.accelerator(CUDA_VIDEO, {"whisper_device": "cuda"}, backend="ct2")["line"]

    def test_the_models_precision_is_shown(self):
        cfg = {"gpu_compute_types": {"large-v3": "int8_float16", "large-v3-turbo": "float16"}}
        self.assertTrue(self.line(cfg).endswith("transcription: CUDA int8_float16"))
        self.assertTrue(self.line(cfg, "large-v3-turbo").endswith("transcription: CUDA float16"))

    def test_the_old_key_still_reads(self):
        self.assertTrue(self.line({"gpu_compute_type": "int8_float16"}).endswith("transcription: CUDA int8_float16"))
        self.assertTrue(self.line({}).endswith("transcription: CUDA float16"))

    def test_a_damaged_preferences_file_falls_back(self):
        with mock.patch.object(S, "load", side_effect=ValueError("bad")):
            with mock.patch.dict(os.environ, {"WHYNOT_ACCEL": "auto"}), \
                    mock.patch("lib.common.load_config", return_value={"gpu_compute_type": "float16"}):
                line = onboard.accelerator(CUDA_VIDEO, {"whisper_device": "cuda"}, backend="ct2")["line"]
        self.assertTrue(line.endswith("transcription: CUDA float16"))


if __name__ == "__main__":
    unittest.main()
