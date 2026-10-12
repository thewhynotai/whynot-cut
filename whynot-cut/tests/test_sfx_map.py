"""3.0 T2.7 (engine IM-10): SFX kinds are checked at plan time and the client's SFX library is mapped for real.
`compile_plan` rejects a `sound[].type` that is neither a procedural recipe nor a key of 06_audio/sfx-map.json (the error
lists the valid kinds); `reel sfx` converts each mapped library file to 06_audio/sfx/<kind>.wav (48 kHz, like the
synthesised ones) with a provenance JSON beside it, and a map entry pointing at a missing file is plain-English guidance.
Run:  <engine venv python> -m unittest discover -s <plugin>/tests -p test_sfx_map.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import sfx  # noqa: E402
from lib.common import ffmpeg_exe, read_json, write_json  # noqa: E402
from lib.errors import Guidance  # noqa: E402

CLI = SK / "engine/reel/cli.py"


def make_tone(path: Path, rate=44100, channels=1, seconds=0.3):
    """A tiny sine file; the extension picks the container (wav / flac)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    codec = ["-c:a", "pcm_s16le"] if path.suffix == ".wav" else []
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=f=880:r={rate}:d={seconds}",
                    "-ac", str(channels), *codec, str(path)], check=True)
    return path


def wav_info(path: Path):
    with wave.open(str(path), "rb") as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()


class TestMapKinds(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.out_dir = Path(self._tmp.name) / "out/06_audio"

    def test_no_map_means_recipes_only(self):
        self.assertEqual(sfx.load_map(self.out_dir / "sfx-map.json"), {})
        self.assertEqual(sfx.valid_kinds({}), sorted(sfx.RECIPES))

    def test_map_keys_extend_the_valid_kinds(self):
        write_json(self.out_dir / "sfx-map.json", {"_comment": "ignored", "swoosh_x": "data/SFX/a.wav",
                                                   "pop": {"file": "data/SFX/p.wav"}})
        m = sfx.load_map(self.out_dir / "sfx-map.json")
        self.assertEqual(set(m), {"swoosh_x", "pop"})                     # "_" keys are notes, not kinds
        self.assertEqual(sfx.valid_kinds(m), sorted(set(sfx.RECIPES) | {"swoosh_x"}))

    def test_bad_map_is_guidance(self):
        write_json(self.out_dir / "sfx-map.json", ["not", "an", "object"])
        with self.assertRaises(Guidance) as cm:
            sfx.load_map(self.out_dir / "sfx-map.json")
        self.assertIn("sfx-map.json", cm.exception.error)
        write_json(self.out_dir / "sfx-map.json", {"boom": 5})
        with self.assertRaises(Guidance):
            sfx.load_map(self.out_dir / "sfx-map.json")


class TestInstall(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "CLIENT"
        self.out_dir = self.root / "out/06_audio/sfx"

    def test_mono_44k_flac_becomes_48k_stereo_wav_with_provenance(self):
        src = make_tone(self.root / "data/SFX/boom.flac", rate=44100, channels=1)
        before = src.read_bytes()
        r = sfx.install_mapped("boom", "data/SFX/boom.flac", self.root, self.out_dir)
        rate, ch, width, frames = wav_info(self.out_dir / "boom.wav")
        self.assertEqual((rate, ch, width), (48000, 2, 3))                # like synth(): 48 kHz / stereo / 24-bit
        self.assertGreater(frames, 48000 * 0.2)
        prov = json.loads((self.out_dir / "boom.provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(prov["kind"], "boom")
        self.assertEqual(prov["source"], str(src.resolve()))
        self.assertEqual(prov["sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(prov["map_entry"], "data/SFX/boom.flac")
        self.assertTrue(prov["converted_at"])
        self.assertEqual(r["file"], str(self.out_dir / "boom.wav"))
        self.assertAlmostEqual(r["duration_s"], 0.3, delta=0.05)
        self.assertEqual(src.read_bytes(), before)                        # the client library is read-only

    def test_entry_forms_and_absolute_path(self):
        src = make_tone(self.root / "data/SFX/a.wav", rate=48000, channels=2)
        sfx.install_mapped("a", {"file": "data/SFX/a.wav", "note": "x"}, self.root, self.out_dir)
        self.assertEqual(wav_info(self.out_dir / "a.wav")[:2], (48000, 2))
        prov = json.loads((self.out_dir / "a.provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(prov["map_entry"], {"file": "data/SFX/a.wav", "note": "x"})
        sfx.install_mapped("b", str(src), self.root, self.out_dir)       # absolute path
        self.assertTrue((self.out_dir / "b.wav").is_file())

    def test_missing_file_is_guidance_naming_kind_and_file(self):
        with self.assertRaises(Guidance) as cm:
            sfx.install_mapped("boom", "data/SFX/nope.wav", self.root, self.out_dir)
        g = cm.exception
        self.assertIn("boom", g.error)
        self.assertIn("nope.wav", g.error)
        self.assertIn("sfx-map.json", g.how)
        self.assertFalse((self.out_dir / "boom.wav").exists())

    def test_not_audio_is_guidance_and_leaves_nothing(self):
        bad = self.root / "data/SFX/notes.wav"
        bad.parent.mkdir(parents=True)
        bad.write_text("not audio", encoding="utf-8")
        with self.assertRaises(Guidance) as cm:
            sfx.install_mapped("boom", "data/SFX/notes.wav", self.root, self.out_dir)
        self.assertIn("boom", cm.exception.error)
        self.assertFalse((self.out_dir / "boom.wav").exists())
        self.assertFalse((self.out_dir / "boom.provenance.json").exists())

    def test_same_source_is_reused_changed_source_is_reconverted(self):
        src = make_tone(self.root / "data/SFX/c.wav", seconds=0.2)
        sfx.install_mapped("c", "data/SFX/c.wav", self.root, self.out_dir)
        t0 = (self.out_dir / "c.wav").stat().st_mtime_ns
        sfx.install_mapped("c", "data/SFX/c.wav", self.root, self.out_dir)
        self.assertEqual((self.out_dir / "c.wav").stat().st_mtime_ns, t0)
        make_tone(src, seconds=0.5)
        r = sfx.install_mapped("c", "data/SFX/c.wav", self.root, self.out_dir)
        self.assertAlmostEqual(r["duration_s"], 0.5, delta=0.05)

    def test_install_needed_mixes_mapped_and_procedural(self):
        make_tone(self.root / "data/SFX/m.wav")
        res = sfx.install_needed({"m", "pop"}, {"m": "data/SFX/m.wav"}, self.root, self.out_dir)
        self.assertEqual(sorted(res), ["m", "pop"])
        self.assertIn("provenance", res["m"])
        self.assertIn("procedural", res["pop"]["license"])
        self.assertTrue((self.out_dir / "pop.wav").is_file())

    def test_install_needed_unknown_kind_is_guidance_listing_valid(self):
        with self.assertRaises(Guidance) as cm:
            sfx.install_needed({"zzz"}, {}, self.root, self.out_dir)
        self.assertIn("zzz", cm.exception.error)
        self.assertIn("whoosh", cm.exception.error + cm.exception.how)


class TestPlanValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_pipeline as T
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root, cls.p, _ = T.make_project(Path(cls._tmp.name))
        cls.tc = T.TestPlanToXML()
        cls.tc.p = cls.p
        cls.tc._semantic_stub()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def tearDown(self):
        m = self.p.p("06_audio/sfx-map.json")
        if m.exists():
            m.unlink()

    def compile_with(self, *sound):
        from lib.plan import compile_plan
        ed = self.tc.decisions()
        ed["decisions"][0]["sound"] = [dict(s) for s in sound]
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed)
        return compile_plan(self.p)

    def test_unknown_kind_is_a_plan_error_listing_the_valid_kinds(self):
        r = self.compile_with({"type": "kaboom", "at": "00:00:01.000"})
        self.assertFalse(r["ok"])
        msg = next(e for e in r["errors"] if "kaboom" in e)
        self.assertIn("EDIT_001", msg)
        for kind in sfx.RECIPES:
            self.assertIn(kind, msg)

    def test_recipe_kind_and_default_pop_pass(self):
        r = self.compile_with({"type": "whoosh", "at": "00:00:01.000"}, {"at": "00:00:02.000"})
        self.assertTrue(r["ok"], r.get("errors"))

    def test_mapped_kind_passes_and_is_listed_in_the_error_for_others(self):
        write_json(self.p.p("06_audio/sfx-map.json"), {"swoosh_x": "data/SFX/x.wav"})
        self.assertTrue(self.compile_with({"type": "swoosh_x", "at": "00:00:01.000"})["ok"])
        r = self.compile_with({"type": "kaboom", "at": "00:00:01.000"})
        self.assertFalse(r["ok"])
        self.assertTrue(any("swoosh_x" in e for e in r["errors"]))


class TestCli(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        import test_pipeline as T
        self.root, self.p, _ = T.make_project(Path(self._tmp.name))
        write_json(self.p.p("06_audio/audio-cue-sheet.json"), {"cues": [{"kind": "pop"}, {"kind": "boom"}]})

    def sfx_cmd(self):
        return subprocess.run([sys.executable, "-B", str(CLI), "--root", str(self.root), "--video-id", "CLIP1", "sfx"],
                              capture_output=True, text=True)

    def test_reel_sfx_installs_mapped_and_synthesises_the_rest(self):
        make_tone(self.root / "data/SFX/boom.flac")
        write_json(self.p.p("06_audio/sfx-map.json"), {"boom": "data/SFX/boom.flac"})
        r = self.sfx_cmd()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        d = self.p.p("06_audio/sfx")
        self.assertEqual(wav_info(d / "boom.wav")[:2], (48000, 2))
        self.assertTrue((d / "boom.provenance.json").is_file())
        self.assertTrue((d / "pop.wav").is_file())
        lib = read_json(d / "sfx-library.json")
        self.assertEqual(sorted(lib), ["boom", "pop"])

    def test_reel_sfx_missing_library_file_is_guidance_not_a_traceback(self):
        write_json(self.p.p("06_audio/sfx-map.json"), {"boom": "data/SFX/gone.wav"})
        r = self.sfx_cmd()
        self.assertEqual(r.returncode, 1)
        doc = json.loads(r.stdout)
        self.assertFalse(doc["ok"])
        self.assertIn("gone.wav", doc["error"])
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_reel_sfx_unmapped_unknown_kind_is_guidance(self):
        r = self.sfx_cmd()                       # "boom" is neither a recipe nor mapped
        self.assertEqual(r.returncode, 1)
        self.assertIn("boom", json.loads(r.stdout)["error"])


if __name__ == "__main__":
    unittest.main()
