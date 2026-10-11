"""Motion mode (2.2): host-aware bridge, AE capability probe, audio episodes, Gate 0 --as motion, icons, licensed
library, motion plan (truth, timing, layout), animatic, AE library, build/read-back, render, QC, plugin layer. Run:
    ~/.whynot-cut/venv/bin/python -m unittest discover -s <plugin>/tests -p test_motion.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True
import hashlib
import inspect
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import Paths, write_json, read_json  # noqa: E402
from test_pipeline import assert_js_syntax  # noqa: E402  (functions only: importing classes would run them twice)
from test_podcast import SHEET, ff, make_episode_client, run_guard, validated_plan  # noqa: E402,F401

AE_TPL = SK / "templates" / "after_effects"
CEP = SK / "templates" / "premiere" / "cep_bridge"


# --------------------------------------------------------------------------- fake CEP panel
class FakePanel:
    """Plays the CEP panel: heartbeat every 0.2 s; claims *.job.json and answers with the job's action (unless mute)."""

    def __init__(self, queue: Path, host: str = "AEFT", mute: bool = False, age_s: float = 0.0):
        self.q, self.host, self.mute, self.age = queue, host, mute, age_s
        self.stop = threading.Event()
        self.t = threading.Thread(target=self.loop, daemon=True)

    def __enter__(self):
        self.q.mkdir(parents=True, exist_ok=True)
        self.beat()
        self.t.start()
        return self

    def __exit__(self, *a):
        self.stop.set()
        self.t.join(2)

    def beat(self):
        tmp = self.q / "bridge.heartbeat.tmp"
        tmp.write_text(json.dumps({"at": (time.time() - self.age) * 1000, "busy": False, "version": "3.1.0",
                                   "host": self.host}), encoding="utf-8")
        try:
            tmp.replace(self.q / "bridge.heartbeat")
        except PermissionError:          # Windows: the reader has the file open this instant; next beat wins
            pass

    def loop(self):
        while not self.stop.is_set():
            if not self.age:
                self.beat()
            for jf in sorted(self.q.glob("*.job.json")):
                if self.mute:
                    continue
                job = json.loads(jf.read_text(encoding="utf-8"))
                run = jf.with_name(jf.name.replace(".job.json", ".running"))
                jf.rename(run)
                data = json.loads(Path(job["data_file"]).read_text(encoding="ascii"))
                inner = json.dumps({"ok": True, "echo": data["action"]})
                (self.q / f"{job['id']}.result.json").write_text(json.dumps({"ok": True, "result": inner}),
                                                                  encoding="utf-8")
                run.unlink()
            time.sleep(0.1)


class TestBridge(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.q = self.tmp / "ae-queue"
        self.script = self.tmp / "ae-scripts" / "nh_ae_bridge.jsx"
        self.script.parent.mkdir(parents=True)
        self.script.write_text("// x", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_queue_roundtrip(self):
        from lib import cep_queue
        with FakePanel(self.q):
            r = cep_queue.submit(self.q, self.script, "ping", {"a": 1, "t": "عربي"}, timeout=10)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["response"]["echo"], "ping")
        data_files = list(self.q.glob("*.data.json"))
        self.assertEqual(len(data_files), 1)
        raw = data_files[0].read_bytes()
        self.assertTrue(all(b < 128 for b in raw), "data file must be pure ASCII")

    def test_queue_timeout(self):
        from lib import cep_queue
        with FakePanel(self.q, mute=True):
            t0 = time.time()
            r = cep_queue.submit(self.q, self.script, "ping", timeout=1)
        self.assertFalse(r["ok"])
        self.assertIn("timeout", r["error"])
        self.assertLess(time.time() - t0, 4)

    def test_queue_dead_heartbeat(self):
        from lib import cep_queue
        with FakePanel(self.q, mute=True, age_s=30):
            r = cep_queue.submit(self.q, self.script, "ping", timeout=2)
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "bridge not running")

    def test_ppro_api_unchanged(self):
        from lib import ppro_bridge
        self.assertEqual(list(inspect.signature(ppro_bridge.submit).parameters), ["action", "data", "timeout", "script"])
        self.assertEqual(ppro_bridge.QUEUE.name, "ppro-queue")
        self.assertEqual(ppro_bridge.BRIDGE_VERSION, "3.1.0")

    def test_ae_status_needs_aeft(self):
        from lib import ae_bridge
        old = ae_bridge.QUEUE
        ae_bridge.QUEUE = self.q
        try:
            with FakePanel(self.q, host="PPRO", mute=True):
                st = ae_bridge.status()
            self.assertFalse(st["alive"])
            with FakePanel(self.q, host="AEFT", mute=True):
                st = ae_bridge.status()
            self.assertTrue(st["alive"], st)
            self.assertEqual(st["host"], "AEFT")
        finally:
            ae_bridge.QUEUE = old

    def test_bridge_js_hosts(self):
        js = (CEP / "js/bridge.js").read_text(encoding="utf-8")
        self.assertIn("PPRO: { queue: 'ppro-queue', scripts: 'ppro-scripts', entry: 'NHPP' }", js)
        self.assertIn("AEFT: { queue: 'ae-queue', scripts: 'ae-scripts', entry: 'NHAE' }", js)
        self.assertIn("getHostEnvironment", js)
        self.assertIn("VERSION = '3.1.0'", js)
        assert_js_syntax(self, CEP / "js/bridge.js")

    def test_manifest_hosts(self):
        root = ET.parse(CEP / "CSXS/manifest.xml").getroot()
        hosts = {h.get("Name"): h.get("Version") for h in root.iter("Host")}
        self.assertEqual(hosts, {"PPRO": "[22.0,99.9]", "AEFT": "[24.0,99.9]"})
        self.assertEqual(root.get("ExtensionBundleVersion"), "3.1.0")

    def test_ae_sync_scripts(self):
        from lib import ae_bridge
        old = ae_bridge.SCRIPTS
        ae_bridge.SCRIPTS = self.tmp / "synced"
        try:
            r1 = ae_bridge.sync_scripts()
            self.assertEqual(sorted(r1["synced"]), sorted(ae_bridge.LIBS))
            for name in ae_bridge.LIBS:
                self.assertEqual(hashlib.sha256((self.tmp / "synced" / name).read_bytes()).hexdigest(),
                                 hashlib.sha256((AE_TPL / name).read_bytes()).hexdigest())
            self.assertEqual(ae_bridge.sync_scripts()["synced"], [])
        finally:
            ae_bridge.SCRIPTS = old

    def test_ae_bridge_jsx_syntax(self):
        for name in ("nh_ae_bridge.jsx", "nh_motion_lib.jsx"):
            assert_js_syntax(self, AE_TPL / name)


class TestProbe(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_probe_job_shape(self):
        from lib import ae_probe
        job = ae_probe.probe_job({"headline": "ArialMT"})
        names = [c["name"] for c in job["comps"]]
        self.assertEqual(names, ["arabic_rtl", "word_reveal", "emphasis", "mixed", "brand_font", "icon"])
        wr = next(c for c in job["comps"] if c["name"] == "word_reveal")
        self.assertEqual(wr["cues"], [15, 30, 45, 60])
        self.assertTrue(wr["text"].startswith("واحد"))          # logical order, never pre-reversed
        self.assertEqual((job["w"], job["h"], job["fps"], job["frames"]), (1080, 1920, 30, 90))
        self.assertEqual(json.loads(json.dumps(job, ensure_ascii=True)), job)

    def test_capabilities_from_readback(self):
        from lib import ae_probe

        def rb(td, pr, composer="UNIVERSAL", templates=("Lossless", "High Quality", "Apple ProRes 422 HQ")):
            return {"ae_version": "26.0", "om_templates": list(templates), "comps": [
                {"name": "arabic_rtl", "ok": True, "composer": composer, "direction_textdocument": td,
                 "direction_paragraph_range": pr, "font_ps": "ArialMT", "substitute": False},
                {"name": "emphasis", "ok": True}, {"name": "brand_font", "ok": True, "font_ps": "ArialMT",
                                                    "requested_ps": "ArialMT", "substitute": False}]}
        self.assertEqual(ae_probe.capabilities_from(rb("RTL", "RTL"), "High Quality")["rtl_direction"], "textdocument")
        self.assertEqual(ae_probe.capabilities_from(rb("LTR", "RTL"), "High Quality")["rtl_direction"], "paragraph_range")
        self.assertIs(ae_probe.capabilities_from(rb("LTR", "LTR"), "High Quality")["rtl_direction"], False)
        caps = ae_probe.capabilities_from(rb("RTL", "RTL"), "High Quality")
        self.assertTrue(caps["composer_universal"])
        self.assertTrue(caps["fontobject"])
        self.assertTrue(caps["emphasis_animator"])
        self.assertEqual(caps["om_template"], "High Quality")
        self.assertFalse(ae_probe.capabilities_from(rb("RTL", "RTL", composer="LATIN"), "x")["composer_universal"])
        self.assertEqual(ae_probe.capabilities_from(rb("RTL", "RTL", templates=("Lossless", "Apple ProRes 422 HQ")),
                                                    "High Quality")["om_template"], "Apple ProRes 422 HQ")

    def test_record_and_verdict(self):
        from lib import ae_probe
        old = ae_probe.CAPS
        ae_probe.CAPS = self.tmp / "ae-capabilities.json"
        try:
            with self.assertRaises(SystemExit):
                ae_probe.record("ok", "n", "logical")             # nothing probed yet
            write_json(ae_probe.CAPS, {"ae_version": "26.0.1", "measured": {}, "verdict": None})
            r = ae_probe.record("ok", "joined, RTL", "logical")
            self.assertTrue(r["word_index_logical"])
            self.assertTrue(ae_probe.verdict_ok("26.0.1"))
            self.assertFalse(ae_probe.verdict_ok("99.0"))
            ae_probe.record("fail", "disconnected", "visual")
            self.assertFalse(ae_probe.verdict_ok("26.0.1"))
            with self.assertRaises(ValueError):
                ae_probe.record("maybe", "", "logical")
        finally:
            ae_probe.CAPS = old

    def test_aerender_cmd_paths(self):
        from lib import ae_render
        aep = Path("D:/0 Work/عميل/x y.aep")
        cmd = ae_render.aerender_cmd("aerender.exe", aep, "MAIN_X", self.tmp / "o u.mov", "Best Settings",
                                     "High Quality", 10, 20)
        self.assertIn(str(aep), cmd)
        for a, b in (("-project", str(aep)), ("-comp", "MAIN_X"), ("-s", "10"), ("-e", "20"),
                     ("-RStemplate", "Best Settings"), ("-OMtemplate", "High Quality"), ("-output", str(self.tmp / "o u.mov"))):
            self.assertEqual(cmd[cmd.index(a) + 1], b)
        self.assertNotIn("-s", ae_render.aerender_cmd("aerender.exe", aep, "C", self.tmp / "o.mov", "r", "o"))

    def test_extract_frames(self):
        from lib import ae_render
        v = self.tmp / "v.mp4"
        ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=30:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(v))
        outs = ae_render.extract_frames(v, [0, 30, 59], 30, self.tmp / "fr")
        self.assertEqual(len(outs), 3)
        self.assertTrue(all(p.exists() and p.suffix == ".png" for p in outs))


# --------------------------------------------------------------------------- audio-only episodes
def add_audio_episode(root: Path, name: str = "POD3.m4a", dur_s: float = 20) -> Path:
    """An audio-only episode (sine) + its sheet next to the video episode of make_episode_client."""
    f = root / "data/Episodes" / name
    ff("-f", "lavfi", "-i", f"sine=f=330:r=48000:d={dur_s}", "-ac", "2", "-c:a", "aac", str(f))
    (root / "data/Episodes" / (Path(name).stem + ".md")).write_text(SHEET, encoding="utf-8")
    return f


def fake_transcript(ep, n: int = 38, step: int = 500, dur_ms: int = 20000, words=None):
    from lib.transcribe import finalize
    ws = [{"id": i + 1, "segment_id": 1, "word": (words[i] if words else f"كلمه{i}"), "start_ms": i * step,
           "end_ms": i * step + int(step * 0.8), "probability": 0.9} for i in range(len(words) if words else n)]
    finalize(ep, {"source_video": "x", "backend": "test", "model": "none", "language": "ar",
                  "language_probability": 1.0, "duration_ms": dur_ms},
             [{"id": 1, "start_ms": 0, "end_ms": ws[-1]["end_ms"], "text": " ".join(w["word"] for w in ws),
               "avg_logprob": -0.2, "no_speech_prob": 0.0, "compression_ratio": 1.1, "words": [w["id"] for w in ws]}], ws)
    return ws


class TestAudioEpisodes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root = make_episode_client(cls.tmp, with_clip=False)
        add_audio_episode(cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_audio_episode_discovered(self):
        from lib.discover import run_discovery
        inv = run_discovery(Paths(self.root))["inventory"]
        by = {Path(f["rel"]).name: f for f in inv["files"]}
        self.assertEqual(by["POD3.m4a"]["role"], "episode")
        self.assertEqual(by["POD3.m4a"]["media"], "audio")
        self.assertEqual(by["EP12.mp4"]["media"], "video")
        self.assertEqual(by["POD3.md"]["role"], "episode_sheet")
        from lib.episode import list_episodes
        eps = {e["episode_id"]: e for e in list_episodes(self.root, refresh=True)}
        self.assertEqual(eps["POD3"]["media"], "audio")

    def test_prep_audio(self):
        from lib.episode import EpisodePaths, prep
        ep = EpisodePaths(self.root, "POD3")
        r = prep(ep)
        info = read_json(ep.p("00_inputs/episode.json"))
        self.assertEqual(info["media"], "audio")
        self.assertIsNone(info["intake_sheet"])
        self.assertFalse([w for w in r["warnings"] if "16:9" in w], r["warnings"])
        self.assertLessEqual(abs(info["duration_ms"] - 20000), 100)
        self.assertEqual(read_json(EpisodePaths(self.root, "EP12").p("00_inputs/episode.json"), {}).get("media", "video"),
                         "video")

    def test_preview_audio_card(self):
        from lib.episode import EpisodePaths, prep
        from lib.media import probe
        from lib.reels import render_candidates
        ep = EpisodePaths(self.root, "POD3")
        prep(ep)
        fake_transcript(ep)
        validated_plan(ep, [{"id": "R01", "in_ms": 2000, "out_ms": 6000, "duration_ms": 4000, "type": "advice",
                             "type_label": "نصيحة", "total": 7.5, "title": "t", "score": {}}])
        r = render_candidates(ep)
        self.assertTrue(r["ok"], r)
        pr = probe(ep.p("03_candidates/R01.mp4"))
        self.assertEqual((pr["video"]["display_width"], pr["video"]["display_height"]), (540, 960))
        self.assertTrue(pr["audio"])
        self.assertTrue(3.9 <= pr["duration_s"] <= 4.1, pr["duration_s"])
        self.assertTrue(ep.p("03_candidates/R01.jpg").exists())
        self.assertTrue(ep.p("03_candidates/_sheet.jpg").exists())


# --------------------------------------------------------------------------- Gate 0 --as motion
MOTION_KEYS = ("beats", "scene_s", "prefer", "avoid", "reveal", "ease", "transition", "theme", "captions",
               "speaker_badge", "progress", "voice_pulse", "max_words_on_screen", "emphasis_per_scene", "sfx_on_transition")


def motion_episode_fixture(tmp: Path):
    """The TestReelsSelect client (EP12, 20 s, 48 words every 400 ms, R01 drama 2-9 s, R02 advice 12-19 s), short
    windows allowed by the client profile, plus topics.json with T01 (2-9 s, no type)."""
    from lib.episode import EpisodePaths, prep
    from lib.transcribe import extract_audio, finalize
    root = make_episode_client(tmp)
    write_json(root / common.CLIENT_PROFILE_REL / "podcast.json", {"reel_duration_s": {"min": 1, "hard_min": 1}})
    write_json(root / common.CLIENT_PROFILE_REL / "motion.json", {"duration_s": {"hard_min": 1}})
    common.set_context(root)
    ep = EpisodePaths(root, "EP12")
    prep(ep)
    extract_audio(root / "data/Episodes/EP12.mp4", ep.p("02_transcription/dialogue_16k_mono.wav"))
    ws = []
    for i in range(48):
        s = i * 400 + (300 if i >= 25 else 0)
        ws.append({"id": i + 1, "segment_id": 1 if i < 25 else 2, "word": f"كلمه{i}", "start_ms": s, "end_ms": s + 360,
                   "probability": 0.9})
    segs = [{"id": k + 1, "start_ms": g[0]["start_ms"], "end_ms": g[-1]["end_ms"], "text": " ".join(w["word"] for w in g),
             "avg_logprob": -0.2, "no_speech_prob": 0.0, "compression_ratio": 1.1, "words": [w["id"] for w in g]}
            for k, g in enumerate((ws[:25], ws[25:]))]
    finalize(ep, {"source_video": "x", "backend": "test", "model": "none", "language": "ar",
                  "language_probability": 1.0, "duration_ms": 20000}, segs, ws)
    write_json(ep.p("01_analysis/speakers.json"), {
        "method": "inferred", "people": {"host": {"name": "Ahmed", "position": "left"},
                                         "guest": {"name": "Sara", "position": "right"}},
        "turns": [{"start": "00:00:00.000", "end": "00:00:05.000", "speaker": "host"},
                  {"start": "00:00:05.000", "end": "00:00:20.000", "speaker": "guest"}]})
    write_json(ep.p("01_analysis/topics.json"), {"topics": [
        {"id": "T01", "start": "00:00:02.000", "end": "00:00:09.000", "title": "first loss", "summary": "s"}]})
    validated_plan(ep, [
        {"id": "R01", "in_ms": 2000, "out_ms": 9000, "duration_ms": 7000, "type": "drama", "secondary_type": None,
         "title": "Sara's first loss", "total": 8.0, "score": {}, "avoid_hits": [], "needs_context": False}])
    return root, ep, ws


class TestMotionGate0(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root, self.ep, self.words = motion_episode_fixture(self.tmp)

    def tearDown(self):
        common.set_context(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def select(self, *picks, **kw):
        from lib.reels import select
        return select(self.ep, list(picks), kw.pop("adjust", []), kw.pop("by", "editor"), **kw)

    def test_recipes_have_motion_blocks(self):
        from lib import recipes, sfx
        for t, r in recipes.types().items():
            m = r["motion"]
            for k in MOTION_KEYS:
                self.assertIn(k, m, f"{t}.motion.{k}")
            self.assertTrue(m["sfx_on_transition"] is None or m["sfx_on_transition"] in sfx.RECIPES, t)
            for rule in m.get("sfx_rules", []):
                self.assertIn(rule["kind"], sfx.RECIPES, t)
        d, e = recipes.types()["drama"]["motion"], recipes.types()["emotional"]["motion"]
        self.assertEqual((d["reveal"], d["transition"], d["theme"], d["captions"]), ("word", "cut", "dark", "off"))
        self.assertEqual((e["reveal"], e["ease"], e["transition"], e["max_words_on_screen"], e["emphasis_per_scene"]),
                         ("line", "gentle", "fade", 18, 1))

    def test_profile_override_motion(self):
        from lib import recipes
        write_json(self.root / common.CLIENT_PROFILE_REL / "recipes.json",
                   {"types": {"advice": {"motion": {"theme": "dark"}}}})
        common.set_context(self.root)
        m = recipes.resolve("advice")["motion"]
        self.assertEqual(m["theme"], "dark")
        self.assertEqual(m["transition"], "wipe")

    def test_select_as_motion(self):
        r = self.select("R01", as_="motion")
        self.assertEqual(r["reels"][0]["reel_id"], "EP12_R01_MO")
        mo = Paths(self.root, "EP12_R01_MO")
        src = read_json(mo.p("00_inputs/source.json"))
        self.assertEqual((src["kind"], src["source_id"], src["format"], src["direction"], src["media"]),
                         ("motion_reel", "R01", "9x16", "rtl", "video"))
        self.assertIn("motion", src["recipe"])
        self.assertEqual(common.source_range(mo)["in_ms"], 2000)
        self.assertTrue(mo.p("02_transcription/words.json").exists())
        sel = read_json(self.ep.p("01_analysis/selection.json"))
        self.assertEqual((sel["history"][-1]["as"], sel["history"][-1]["format"]), ("motion", "9x16"))
        from lib.motion_config import is_motion, recipe_motion
        self.assertTrue(is_motion(mo))
        self.assertEqual(recipe_motion(mo)["transition"], "cut")      # drama

    def test_video_and_motion_coexist(self):
        self.select("R01")
        self.select("R01", as_="motion", fmt="16x9")
        self.assertTrue(Paths(self.root, "EP12_R01").p("00_inputs/source.json").exists())
        mo = read_json(Paths(self.root, "EP12_R01_MO").p("00_inputs/source.json"))
        self.assertEqual(mo["format"], "16x9")
        from lib.motion_config import is_motion
        self.assertFalse(is_motion(Paths(self.root, "EP12_R01")))

    def test_topic_rules(self):
        with self.assertRaises(SystemExit) as cm:
            self.select("T01")
        self.assertIn("--as motion", str(cm.exception))
        with self.assertRaises(SystemExit) as cm:
            self.select("T01", as_="motion")
        self.assertIn("advice", str(cm.exception))
        r = self.select("T01", as_="motion", type_="advice")
        src = read_json(Paths(self.root, "EP12_T01_MO").p("00_inputs/source.json"))
        self.assertEqual((src["content_type"], src["recipe"]["type"], src["source_id"]), ("advice", "advice", "T01"))
        self.assertTrue(0 <= src["in_ms"] < src["out_ms"], src)
        self.assertEqual(src["topic"]["title"], "first loss")
        self.assertEqual(r["reels"][0]["reel_id"], "EP12_T01_MO")

    def test_topic_too_long(self):
        write_json(self.root / common.CLIENT_PROFILE_REL / "motion.json", {"duration_s": {"hard_min": 1, "hard_max": 5}})
        common.set_context(self.root)
        with self.assertRaises(SystemExit) as cm:
            self.select("T01", as_="motion", type_="advice")
        self.assertIn("split it", str(cm.exception))

    def test_audio_episode_video_refused(self):
        from lib.episode import EpisodePaths, prep
        add_audio_episode(self.root)
        ep = EpisodePaths(self.root, "POD3")
        prep(ep)
        fake_transcript(ep)
        validated_plan(ep, [{"id": "R01", "in_ms": 2000, "out_ms": 9000, "duration_ms": 7000, "type": "advice",
                             "total": 7.0, "score": {}, "avoid_hits": []}])
        from lib.reels import select
        with self.assertRaises(SystemExit) as cm:
            select(ep, ["R01"], [], "editor")
        self.assertIn("no picture", str(cm.exception))
        r = select(ep, ["R01"], [], "editor", as_="motion")
        src = read_json(Paths(self.root, r["reels"][0]["reel_id"]).p("00_inputs/source.json"))
        self.assertEqual(src["media"], "audio")

    def test_episode_next_lists_motion(self):
        from lib.episode import episode_next
        self.select("R01", as_="motion")
        self.assertIn("EP12_R01_MO", episode_next(self.ep)["reels"])

    def test_cli_args(self):
        from lib import podcast_cli
        opts = {flags[0]: kw for flags, kw in podcast_cli.ARGS["reels-select"]}
        self.assertEqual(opts["--as"]["choices"], ["video", "motion"])
        self.assertEqual(opts["--format"]["choices"], ["9x16", "16x9"])
        self.assertIn("--type", opts)


# --------------------------------------------------------------------------- icons
def svg(body: str) -> str:
    return f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor">{body}</svg>'


class TestIcons(unittest.TestCase):
    def assertPts(self, got, want, places=6):
        self.assertEqual(len(got), len(want))
        for g, w in zip(got, want):
            self.assertAlmostEqual(g[0], w[0], places=places)
            self.assertAlmostEqual(g[1], w[1], places=places)

    def test_lines_and_relative(self):
        from lib.motion_icons import svg_to_shapes
        for d in ("M2 2 L22 2 L22 22 Z", "m2 2 l20 0 v20 z", "M2 2 H22 V22 Z"):
            sh = svg_to_shapes(svg(f'<path d="{d}"/>'), 24)
            self.assertEqual(len(sh), 1, d)
            self.assertTrue(sh[0]["closed"], d)
            self.assertPts(sh[0]["vertices"], [[-10, -10], [10, -10], [10, 10]])
            self.assertPts(sh[0]["inTangents"], [[0, 0]] * 3)
            self.assertPts(sh[0]["outTangents"], [[0, 0]] * 3)

    def test_cubic_and_smooth(self):
        from lib.motion_icons import svg_to_shapes
        s = svg_to_shapes(svg('<path d="M0 12 C0 0 24 0 24 12 S24 24 12 24"/>'), 24)[0]
        self.assertFalse(s["closed"])
        self.assertEqual(len(s["vertices"]), 3)
        self.assertPts([s["outTangents"][0]], [[0, -12]])
        self.assertPts([s["inTangents"][1], s["outTangents"][1]], [[0, -12], [0, 12]])
        self.assertPts([s["inTangents"][2]], [[12, 0]])

    def test_arc(self):
        from lib.motion_icons import flatten, svg_to_shapes
        s = svg_to_shapes(svg('<path d="M2 12 A10 10 0 0 1 22 12"/>'), 24)
        self.assertPts([s[0]["vertices"][0], s[0]["vertices"][-1]], [[-10, 0], [10, 0]])
        for poly in flatten(s, 0.2):
            for x, y in poly:
                self.assertAlmostEqual((x * x + y * y) ** 0.5, 10, delta=0.2)
        compact = svg_to_shapes(svg('<path d="M2 12a10 10 0 0120 0"/>'), 24)      # flags written without spaces
        self.assertPts([compact[0]["vertices"][-1]], [[10, 0]])

    def test_elements(self):
        from lib.motion_icons import svg_to_shapes
        c = svg_to_shapes(svg('<circle cx="12" cy="12" r="10"/>'), 24)[0]
        self.assertTrue(c["closed"])
        self.assertEqual(len(c["vertices"]), 4)
        for x, y in c["vertices"]:
            self.assertAlmostEqual((x * x + y * y) ** 0.5, 10, places=6)
        r = svg_to_shapes(svg('<rect x="3" y="3" width="18" height="18" rx="2"/>'), 24)[0]
        self.assertTrue(r["closed"])
        self.assertEqual(len(r["vertices"]), 8)
        ln = svg_to_shapes(svg('<line x1="5" y1="12" x2="19" y2="12"/>'), 24)[0]
        self.assertFalse(ln["closed"])
        self.assertPts(ln["vertices"], [[-7, 0], [7, 0]])
        pl = svg_to_shapes(svg('<polyline points="2 2 12 12 22 2"/>'), 24)[0]
        pg = svg_to_shapes(svg('<polygon points="2,2 12,12 22,2"/>'), 24)[0]
        self.assertFalse(pl["closed"])
        self.assertTrue(pg["closed"])
        self.assertEqual(len(pg["vertices"]), 3)
        big = svg_to_shapes(svg('<line x1="0" y1="12" x2="24" y2="12"/>'), 240)[0]   # scaled by size / viewBox
        self.assertPts(big["vertices"], [[-120, 0], [120, 0]])

    def test_vendored_index(self):
        from lib.motion_icons import ICON_DIR, load_index, svg_to_shapes
        idx = load_index()
        self.assertGreaterEqual(len(idx), 1000)
        self.assertIn("trending-up", idx)
        self.assertIn("check", idx)
        self.assertIn("ISC", (ICON_DIR / "LICENSE").read_text(encoding="utf-8"))
        for name in idx:
            shapes = svg_to_shapes((ICON_DIR / f"{name}.svg").read_text(encoding="utf-8"), 24)
            self.assertTrue(shapes, name)

    def test_search_closest_mirror(self):
        from lib.motion_icons import closest, icon_shapes, search, should_mirror
        self.assertEqual(search("trending up")[0]["name"], "trending-up")
        self.assertIn("trending-up", closest("trendingup"))
        self.assertTrue(should_mirror("arrow-right", "rtl"))
        self.assertFalse(should_mirror("arrow-right", "ltr"))
        self.assertFalse(should_mirror("heart", "rtl"))
        a, b = icon_shapes("arrow-right", 24), icon_shapes("arrow-right", 24, mirror=True)
        for sa, sb in zip(a, b):
            for va, vb in zip(sa["vertices"], sb["vertices"]):
                self.assertAlmostEqual(va[0], -vb[0])
                self.assertAlmostEqual(va[1], vb[1])


if __name__ == "__main__":
    unittest.main()
