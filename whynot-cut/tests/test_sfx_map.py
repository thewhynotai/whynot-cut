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
import unittest.mock as mock
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


    def test_unsafe_keys_are_guidance_naming_the_key(self):
        for bad in ("x/../../../../../../data/evil", "../x", "a/b", "a\\b", "a:b", "a*b", "a?b", 'a"b', "a<b", "a|b", ".",
                    "..", "", ".hidden", "con", "NUL", "x" * 65, "sp ace"):
            write_json(self.out_dir / "sfx-map.json", {bad: "data/SFX/a.wav"})
            with self.assertRaises(Guidance, msg=repr(bad)) as cm:
                sfx.load_map(self.out_dir / "sfx-map.json")
            self.assertIn(repr(bad), cm.exception.error)
            self.assertIn("sfx-map.json", cm.exception.how)

    def test_plain_keys_are_accepted(self):
        keys = ["whoosh", "door_knock", "Hit-2", "a", "x" * 64, "9lives"]
        write_json(self.out_dir / "sfx-map.json", {k: "data/SFX/a.wav" for k in keys})
        self.assertEqual(set(sfx.load_map(self.out_dir / "sfx-map.json")), set(keys))


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

    def test_traversal_key_is_refused_and_writes_nothing_outside_the_sfx_folder(self):
        make_tone(self.root / "data/SFX/a.wav")
        evil = "x/../../../../../../data/evil"
        with self.assertRaises(Guidance):
            sfx.install_mapped(evil, "data/SFX/a.wav", self.root, self.out_dir)
        with self.assertRaises(Guidance):
            sfx.install_needed({evil}, {evil: "data/SFX/a.wav"}, self.root, self.out_dir)
        everything = {p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(everything, {"data/SFX/a.wav"})                  # nothing written anywhere

    def test_source_longer_than_30_seconds_is_refused(self):
        make_tone(self.root / "data/SFX/long.wav", rate=8000, seconds=31)
        with self.assertRaises(Guidance) as cm:
            sfx.install_mapped("long", "data/SFX/long.wav", self.root, self.out_dir)
        self.assertIn("31 s", cm.exception.error)
        self.assertIn("long.wav", cm.exception.error)
        self.assertFalse((self.out_dir / "long.wav").exists())

    def test_ffmpeg_gets_nostdin_and_a_timeout_and_a_hang_is_guidance(self):
        make_tone(self.root / "data/SFX/h.wav")
        calls = []

        def hang(cmd, **kw):
            calls.append((cmd, kw))
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
        with mock.patch.object(sfx, "run", hang):
            with self.assertRaises(Guidance) as cm:
                sfx.install_mapped("h", "data/SFX/h.wav", self.root, self.out_dir)
        cmd, kw = calls[0]
        self.assertIn("-nostdin", cmd)
        self.assertEqual(kw.get("timeout"), sfx.CONVERT_TIMEOUT_S)
        self.assertIn("120 s", cm.exception.error)
        self.assertFalse((self.out_dir / "h.wav").exists())
        self.assertEqual([p.name for p in self.out_dir.glob("*")], [])    # no .converting leftovers

    def test_wav_held_open_is_a_close_the_project_message(self):
        make_tone(self.root / "data/SFX/k.wav")
        with mock.patch.object(Path, "replace", side_effect=PermissionError(13, "Access is denied")):
            with self.assertRaises(Guidance) as cm:
                sfx.install_mapped("k", "data/SFX/k.wav", self.root, self.out_dir)
        g = cm.exception
        self.assertIn("in use", g.error)
        self.assertNotIn("could not read", g.error)
        self.assertIn("Close the Premiere project", g.how)
        self.assertEqual([p.name for p in self.out_dir.glob("*")], [])
        self.assertFalse((self.out_dir / "k.provenance.json").exists())

    def test_unmapping_a_recipe_kind_removes_the_library_file_and_provenance(self):
        make_tone(self.root / "data/SFX/p.wav", seconds=0.5)
        res = sfx.install_needed({"pop"}, {"pop": "data/SFX/p.wav"}, self.root, self.out_dir)
        self.assertIn("provenance", res["pop"])
        self.assertAlmostEqual(res["pop"]["duration_s"], 0.5, delta=0.05)
        self.assertTrue((self.out_dir / "pop.provenance.json").is_file())
        res = sfx.install_needed({"pop"}, {}, self.root, self.out_dir)    # the entry was removed from the map
        self.assertFalse((self.out_dir / "pop.provenance.json").exists())
        self.assertNotIn("provenance", res["pop"])
        self.assertIn("procedural", res["pop"]["license"])
        self.assertAlmostEqual(res["pop"]["duration_s"], sfx.RECIPES["pop"][1], delta=0.02)   # synthesised again
        self.assertAlmostEqual(wav_info(self.out_dir / "pop.wav")[3] / 48000, sfx.RECIPES["pop"][1], delta=0.02)

    def test_mapped_recipe_name_overrides_an_existing_synthesised_file(self):
        sfx.install_needed({"pop"}, {}, self.root, self.out_dir)          # the synthesised pop.wav (0.18 s)
        make_tone(self.root / "data/SFX/p.wav", seconds=0.5)
        res = sfx.install_needed({"pop"}, {"pop": "data/SFX/p.wav"}, self.root, self.out_dir)
        self.assertIn("provenance", res["pop"])
        self.assertAlmostEqual(wav_info(self.out_dir / "pop.wav")[3] / 48000, 0.5, delta=0.05)
        prov = json.loads((self.out_dir / "pop.provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(prov["kind"], "pop")

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


    def compile_with_graphic(self, **extra):
        from lib.plan import compile_plan
        ed = self.tc.decisions()
        ed["decisions"][0]["graphics"][0].update(extra)
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed)
        return compile_plan(self.p)

    def test_graphic_default_sfx_unknown_kind_is_a_plan_error(self):
        r = self.compile_with_graphic(sfx="boom")
        self.assertFalse(r["ok"])
        msg = next(e for e in r["errors"] if "boom" in e)
        self.assertIn("graphics sfx", msg)
        for kind in sfx.RECIPES:
            self.assertIn(kind, msg)

    def test_graphic_default_sfx_recipe_mapped_and_none_pass(self):
        for kind in ("whoosh", "none", None):
            r = self.compile_with_graphic(sfx=kind)
            self.assertTrue(r["ok"], (kind, r.get("errors")))
        write_json(self.p.p("06_audio/sfx-map.json"), {"swoosh_x": "data/SFX/x.wav"})
        self.assertTrue(self.compile_with_graphic(sfx="swoosh_x")["ok"])
        r = self.compile_with_graphic(sfx="boom")
        self.assertTrue(any("swoosh_x" in e for e in r["errors"]))

    def test_non_string_kinds_are_plan_errors_not_crashes(self):
        for bad in ([], 5, {"a": 1}):
            r = self.compile_with({"type": bad, "at": "00:00:01.000"})
            self.assertFalse(r["ok"], bad)
            self.assertTrue(any("sound.type" in e and "not a sound kind" in e for e in r["errors"]), r["errors"])
            r = self.compile_with_graphic(sfx=bad)
            self.assertFalse(r["ok"], bad)
            self.assertTrue(any("graphics sfx" in e for e in r["errors"]), r["errors"])

    def test_map_with_an_unsafe_key_stops_the_plan_with_guidance(self):
        write_json(self.p.p("06_audio/sfx-map.json"), {"../x": "data/SFX/x.wav"})
        with self.assertRaises(Guidance) as cm:
            self.compile_with({"type": "pop", "at": "00:00:01.000"})
        self.assertIn("../x", cm.exception.error)


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

    def test_reel_sfx_traversal_key_is_guidance_and_writes_nothing_outside(self):
        make_tone(self.root / "data/SFX/a.wav")
        write_json(self.p.p("06_audio/sfx-map.json"), {"x/../../../../../../../../data/evil": "data/SFX/a.wav"})
        r = self.sfx_cmd()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        doc = json.loads(r.stdout)
        self.assertFalse(doc["ok"])
        self.assertIn("data/evil", doc["error"])
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertEqual([p.name for p in (self.root / "data").glob("evil*")], [])
        self.assertEqual([p.name for p in (self.root / "data").glob("*.wav")], [])

    def test_reel_sfx_unmapped_unknown_kind_is_guidance(self):
        r = self.sfx_cmd()                       # "boom" is neither a recipe nor mapped
        self.assertEqual(r.returncode, 1)
        self.assertIn("boom", json.loads(r.stdout)["error"])


if __name__ == "__main__":
    unittest.main()
