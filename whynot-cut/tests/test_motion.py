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

    def test_install_never_downgrades(self):
        """Peer request: `reel setup`/`ppro-install` from an older plugin silently put bridge 3.0.0 back over 3.1.0 (and
        dropped the After Effects host). A newer installed bundle is kept unless --force."""
        from lib import plat, ppro_bridge as pb
        saved = (pb.EXT_DIR, pb.QUEUE, pb.SCRIPTS, pb.LIB, plat.player_debug_mode)
        pb.EXT_DIR, pb.QUEUE, pb.SCRIPTS = self.tmp / "ext" / pb.EXT_ID, self.tmp / "ppro-queue", self.tmp / "ppro-scripts"
        pb.LIB = pb.SCRIPTS / pb.LIB.name                                 # never the real engine-home scripts folder
        plat.player_debug_mode = lambda: {}
        cfg = pb.EXT_DIR / "bridge-config.json"
        try:
            pb.EXT_DIR.mkdir(parents=True)
            cfg.write_text(json.dumps({"version": "9.0.0"}), encoding="utf-8")
            r = pb.install()
            self.assertTrue(r.get("skipped"), r)
            self.assertTrue("9.0.0" in r["detail"] and pb.BRIDGE_VERSION in r["detail"] and "--force" in r["detail"], r)
            self.assertEqual(json.loads(cfg.read_text(encoding="utf-8"))["version"], "9.0.0")
            cfg.unlink()                                                    # manifest only (no bridge-config.json)
            (pb.EXT_DIR / "CSXS").mkdir()
            (pb.EXT_DIR / "CSXS/manifest.xml").write_text('<ExtensionManifest ExtensionBundleVersion="9.1.0">',
                                                         encoding="utf-8")
            self.assertTrue(pb.install().get("skipped"))
            r = pb.install(force=True)
            self.assertFalse(r.get("skipped"), r)
            self.assertEqual(json.loads(cfg.read_text(encoding="utf-8"))["version"], pb.BRIDGE_VERSION)
            cfg.write_text(json.dumps({"version": "3.0.0"}), encoding="utf-8")        # older: replaced without --force
            self.assertFalse(pb.install().get("skipped"))
            self.assertEqual(json.loads(cfg.read_text(encoding="utf-8"))["version"], pb.BRIDGE_VERSION)
        finally:
            pb.EXT_DIR, pb.QUEUE, pb.SCRIPTS, pb.LIB, plat.player_debug_mode = saved

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
        self.assertEqual(names, ["arabic_rtl", "word_reveal", "emphasis", "mixed", "brand_font", "icon",
                                 "index_map", "reveal_step", "word_layers"])
        im = next(c for c in job["comps"] if c["name"] == "index_map")
        self.assertIn("textIndex", im["fill_expr"])
        rs = next(c for c in job["comps"] if c["name"] == "reveal_step")
        self.assertIn("textIndex", rs["opacity_expr"])
        from lib.ae_probe import look_points
        self.assertIn(("index_map_23", 6 * 90 + 23), look_points())
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

    def test_topic_avoid_guard(self):
        """Review: a topic window mentioning a sheet `avoid:` topic needs --confirm-avoid, like a reel candidate."""
        epj = self.ep.p("00_inputs/episode.json")
        info = read_json(epj)
        write_json(epj, dict(info, sheet=dict(info.get("sheet") or {}, avoid=["كلمه7"])))     # said at 2.8 s, inside T01
        with self.assertRaises(SystemExit) as cm:
            self.select("T01", as_="motion", type_="advice")
        self.assertIn("--confirm-avoid T01", str(cm.exception))
        r = self.select("T01", as_="motion", type_="advice", confirm_avoid=["T01"])
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


# --------------------------------------------------------------------------- licensed library
def make_pack(base: Path, pid: str, license: str, attribution: str = "", proof: str = "", items=None, write_json_=True):
    d = base / pid
    d.mkdir(parents=True, exist_ok=True)
    items = items if items is not None else [{"id": "doctor", "file": "doctor.svg", "tags": ["doctor"]}]
    for it in items:
        f = d / it["file"]
        if it["file"].endswith(".png"):
            from PIL import Image
            Image.new("RGBA", (40, 40), (255, 0, 0, 128)).save(f)
        elif not f.exists():
            f.write_text(svg('<path d="M2 2 L22 2 L22 22 Z" fill="#20ACAF"/>'), encoding="utf-8")
    if write_json_:
        write_json(d / "pack.json", {"id": pid, "name": pid, "license": license, "source": "https://example.com",
                                     "attribution": attribution, "proof": proof, "items": items})
    return d


class TestLibrary(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def packs(self):
        from lib.motion_library import load_packs
        return {p["id"]: p for p in load_packs(self.tmp)}

    def test_license_rules(self):
        make_pack(self.tmp, "open", "CC0-1.0")
        make_pack(self.tmp, "by_empty", "CC-BY-4.0")
        make_pack(self.tmp, "by_ok", "CC-BY-4.0", attribution="Art by X (CC BY 4.0)")
        make_pack(self.tmp, "bought", "commercial")
        make_pack(self.tmp, "bought_ok", "commercial", proof="invoice 123")
        make_pack(self.tmp, "free", "free")
        make_pack(self.tmp, "nojson", "MIT", write_json_=False)
        p = self.packs()
        self.assertTrue(p["open"]["ok"])
        self.assertFalse(p["by_empty"]["ok"])
        self.assertTrue(any("attribution" in x for x in p["by_empty"]["problems"]))
        self.assertTrue(p["by_ok"]["ok"])
        self.assertFalse(p["bought"]["ok"])
        self.assertTrue(p["bought_ok"]["ok"])
        self.assertFalse(p["free"]["ok"])
        self.assertFalse(p["nojson"]["ok"])
        self.assertTrue(p["nojson"]["problems"])

    def test_resolve(self):
        from lib.motion_library import resolve
        make_pack(self.tmp, "open", "CC0-1.0", items=[{"id": "doctor", "file": "doctor.svg", "tags": []},
                                                     {"id": "pic", "file": "pic.png", "tags": []}])
        make_pack(self.tmp, "free", "free")
        r = resolve("open/doctor", self.tmp)
        self.assertEqual((r["kind"], r["license"], r["pack"]), ("svg", "CC0-1.0", "open"))
        self.assertEqual(resolve("open/pic", self.tmp)["kind"], "png")
        with self.assertRaises(ValueError):
            resolve("free/doctor", self.tmp)
        with self.assertRaises(ValueError):
            resolve("open/nothing", self.tmp)

    def test_svg_ok(self):
        from lib.motion_library import svg_ok
        self.assertTrue(svg_ok(svg('<path d="M0 0 L1 1" fill="#000"/>'))[0])
        bad = svg('<defs><linearGradient id="g"/></defs><path d="M0 0 L1 1" fill="url(#g)"/>')
        self.assertFalse(svg_ok(bad)[0])
        many = svg("".join('<path d="M0 0 L1 1"/>' for _ in range(301)))
        self.assertFalse(svg_ok(many)[0])


# --------------------------------------------------------------------------- motion script truth
SPOKEN = "انا قلت ان الشركه دي هتنجح".split()


def scene(sid, typ, at="كلمه1", **kw):
    return dict({"id": sid, "type": typ, "at": at}, **kw)


class TestMotionTruth(unittest.TestCase):
    def test_subsequence(self):
        from lib.motion_script import match_subsequence
        r = match_subsequence("قلت ان الشركه دي هتنجح", SPOKEN, 0.4)
        self.assertTrue(r["ok"], r)
        self.assertAlmostEqual(r["dropped_ratio"], 1 / 6)
        self.assertEqual(r["idx"], [1, 2, 3, 4, 5])
        self.assertFalse(match_subsequence("قلت الشركه هتنجح", SPOKEN, 0.4)["ok"])          # 3 of 6 dropped
        r = match_subsequence("قلت الشركه هتنجح جدا", SPOKEN, 1.0)
        self.assertFalse(r["ok"])
        self.assertEqual(r["added"], ["جدا"])
        self.assertFalse(match_subsequence("هتنجح الشركه", SPOKEN, 1.0)["ok"])              # order kept
        self.assertTrue(match_subsequence("إن الشركة", SPOKEN, 1.0)["ok"])                 # spelling variants
        self.assertTrue(match_subsequence("قُلْت", SPOKEN, 1.0)["ok"])                      # tashkeel

    def test_fields(self):
        from lib.motion_script import check_fields
        good = {"beats": [{"id": "B1", "role": "hook"}], "scenes": [
            scene("S01", "kinetic_quote", "@start", beat="B1", text="x"),
            scene("S02", "list_steps", items=[{"text": "a", "at": "a"}, {"text": "b", "at": "b"}]),
            scene("S03", "outro", "@end", cta="تابعنا")]}
        self.assertEqual(check_fields(good), [])
        cases = {
            "duplicate": [scene("S01", "kinetic_quote", "@start", text="x"), scene("S01", "kinetic_quote", text="y")],
            "unknown type": [scene("S01", "kinetic_quote", "@start", text="x"), scene("S02", "dance")],
            "missing text": [scene("S01", "kinetic_quote", "@start")],
            "1 item": [scene("S01", "list_steps", "@start", items=[{"text": "a", "at": "a"}])],
            "6 items": [scene("S01", "list_steps", "@start", items=[{"text": "a", "at": "a"}] * 6)],
            "no @start": [scene("S01", "kinetic_quote", "كلام", text="x")],
            "@end early": [scene("S01", "kinetic_quote", "@start", text="x"), scene("S02", "outro", "@end", cta="c"),
                           scene("S03", "kinetic_quote", text="y")],
        }
        for name, scenes in cases.items():
            errs = check_fields({"scenes": scenes})
            self.assertEqual(len(errs), 1, (name, errs))
            self.assertRegex(errs[0], r"S0\d", name)

    def test_field_value_typos(self):
        """Final review: a typo in transition_in / theme / captions / reveal silently became a cut, the dark theme, no
        captions or a word reveal. motion-plan names it."""
        from lib.motion_script import check_fields

        def two(**kw):
            return {"scenes": [scene("S01", "kinetic_quote", "@start", text="x"),
                               scene("S02", "kinetic_quote", text="y", **kw)]}
        for kw in ({"transition_in": "push", "theme": "light", "captions": "off", "reveal": "line"}, {"captions": "on"},
                   {"transition_in": "fade", "theme": "brand", "reveal": "word"}):
            self.assertEqual(check_fields(two(**kw)), [], kw)
        for field, bad in (("transition_in", "puhs"), ("theme", "drak"), ("captions", "of"), ("reveal", "words")):
            errs = check_fields(two(**{field: bad}))
            self.assertEqual(len(errs), 1, (field, errs))
            self.assertTrue(errs[0].startswith("S02") and field in errs[0] and repr(bad) in errs[0], errs)
        self.assertEqual(check_fields(dict(two(), theme="brand", captions="subtitles")), [])
        for field, bad in (("theme", "brnad"), ("captions", "subtitle")):                    # the video-wide values
            errs = check_fields(dict(two(), **{field: bad}))
            self.assertEqual(len(errs), 1, (field, errs))
            self.assertTrue(field in errs[0] and repr(bad) in errs[0], errs)

    def test_editorial(self):
        from lib.motion_script import check_editorial, fill_placeholders
        self.assertTrue(check_editorial("«كلام»", set()))
        self.assertTrue(check_editorial("3 خطوات", {"5"}))
        self.assertEqual(check_editorial("3 خطوات", {"3"}), [])
        self.assertEqual(fill_placeholders("مع {guest}", {"guest": "Sara — CEO"}), ("مع Sara", []))
        self.assertEqual(fill_placeholders("{host}", {"guest": "Sara"})[1], ["host"])

    def test_numbers(self):
        from lib.motion_script import check_number
        self.assertTrue(check_number("٣", "عندنا 3 فروع"))
        self.assertFalse(check_number("1,000,000", "مليون عميل"))
        self.assertTrue(check_number("70%", "٧٠ في المية"))
        self.assertFalse(check_number("93", "سنة 2019 و 3 فروع"))                         # digit runs, not substrings


# --------------------------------------------------------------------------- timing
def words_every(n=60, step=400, dur=360):
    return [{"id": i + 1, "word": f"كلمه{i}", "start_ms": i * step, "end_ms": i * step + dur} for i in range(n)]


def fps_context(tmp: Path, timebase: int, ntsc: bool) -> Path:
    root = tmp / f"FPS{timebase}{'n' if ntsc else ''}"
    write_json(root / common.CLIENT_PROFILE_REL / "sequence-settings.json", {"general": {"timebase": timebase, "ntsc": ntsc}})
    (root / "assets").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)
    common.set_context(root)
    return root


MCFG = {"scene_lead_ms": 150, "outro_ms": 2500, "word_reveal_ms": 180, "total_ms": 24000}


class TestMotionTiming(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        common.set_context(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_anchors(self):
        from lib.motion_timing import anchor_scenes
        ws = words_every()
        sc = [scene("S01", "kinetic_quote", "@start"), scene("S02", "kinetic_quote", "كلمه10 كلمه11"),
              scene("S03", "kinetic_quote", "كلمه25 كلمه26"), scene("S04", "outro", "@end")]
        a, errs = anchor_scenes(sc, ws, MCFG)
        self.assertEqual(errs, [])
        self.assertEqual([x["start_ms"] for x in a], [0, 3850, 9850, ws[-1]["end_ms"]])
        self.assertEqual([x["end_ms"] for x in a], [3850, 9850, ws[-1]["end_ms"], ws[-1]["end_ms"] + 2500])
        self.assertEqual([x["word_idx"] for x in a[:3]], [0, 10, 25])
        self.assertTrue(a[3]["outro"])
        no_outro, _ = anchor_scenes(sc[:3], ws, MCFG)
        self.assertEqual(no_outro[-1]["end_ms"], 24000)                     # the window's end

    def test_anchor_errors(self):
        from lib.motion_timing import anchor_scenes
        ws = words_every()
        _, errs = anchor_scenes([scene("S01", "kinetic_quote", "@start"), scene("S02", "kinetic_quote", "ليس هنا")], ws, MCFG)
        self.assertEqual(len(errs), 1)
        self.assertIn("S02", errs[0])
        _, errs = anchor_scenes([scene("S01", "kinetic_quote", "@start"), scene("S02", "kinetic_quote", "كلمه25"),
                                 scene("S03", "kinetic_quote", "كلمه10")], ws, MCFG)
        self.assertEqual(len(errs), 1)
        self.assertIn("S03", errs[0])
        self.assertIn("order", errs[0])

    def test_cues_with_pauses(self):
        from lib.common import seq_fps
        from lib.motion_timing import cue_frames
        from lib.timemap import TimeMap
        ws = words_every(40, 500)
        k = next(i for i, w in enumerate(ws) if w["start_ms"] == 6000)
        for tb, ntsc in ((24, False), (25, False), (30, True), (30, False)):
            fps_context(self.tmp, tb, ntsc)
            tm = TimeMap([[0, 4000], [5000, 12000]])
            self.assertEqual(cue_frames([k], ws, tm, seq_fps()), [round(5.0 * seq_fps())], (tb, ntsc))

    def test_no_drift_long_window(self):
        from lib.common import seq_fps
        from lib.motion_timing import cue_frames
        from lib.timemap import TimeMap
        ws = [{"id": 1, "word": "x", "start_ms": 179600, "end_ms": 179900}]
        for tb, ntsc in ((30, True), (24, True)):
            fps_context(self.tmp, tb, ntsc)
            want = round(179.6 * seq_fps())
            self.assertEqual(cue_frames([0], ws, None, seq_fps()), [want], (tb, ntsc))
            self.assertEqual(cue_frames([0], ws, TimeMap([[0, 180000]]), seq_fps()), [want], (tb, ntsc))

    def test_hero_and_too_short(self):
        from lib.motion_timing import frame_scenes, hero_frame
        self.assertEqual(hero_frame(100, 160, 12, 30, 180), 112)            # ceil(5.4) = 6 reveal frames + 6
        fps_context(self.tmp, 30, False)
        ok, errs = frame_scenes([{"id": "S01", "start_ms": 0, "end_ms": 6000, "cues_ms": [3000]}], None, 30.0, MCFG, [0])
        self.assertEqual(errs, [])
        self.assertEqual((ok[0]["start_frame"], ok[0]["end_frame"], ok[0]["cue_frames"]), (0, 180, [90]))
        self.assertEqual(ok[0]["hero_frame"], 90 + 6 + 6)
        fine, errs = frame_scenes([{"id": "S06", "start_ms": 0, "end_ms": 5170, "cues_ms": [5000]}], None, 30.0, MCFG, [0])
        self.assertEqual(errs, [])                                         # continuous speech: last word near the cut
        self.assertEqual(fine[0]["hero_frame"], 154)
        _, errs = frame_scenes([{"id": "S07", "start_ms": 0, "end_ms": 5170, "cues_ms": [5150]}], None, 30.0, MCFG, [0])
        self.assertEqual(len(errs), 1)
        self.assertIn("S07", errs[0])
        self.assertIn("too short", errs[0])
        out, _ = frame_scenes([{"id": "S09", "start_ms": 20000, "end_ms": 22500, "outro": True, "cues_ms": []}],
                              None, 30.0, MCFG, [0])
        self.assertEqual(out[0]["end_frame"] - out[0]["start_frame"], 75)   # the outro keeps its length past the audio


# --------------------------------------------------------------------------- layout
def test_font() -> Path | None:
    from lib.plat import font_dirs
    return next((f for d in font_dirs() if d.exists() for f in sorted(d.glob("*.ttf"))
                 if f.name.lower() in ("arial.ttf", "dejavusans.ttf", "notosansarabic-regular.ttf",
                                       "ibmplexsansarabic-medium.ttf")), None)


class TestMotionLayout(unittest.TestCase):
    def test_wrap_glue(self):
        from lib.motion_layout import wrap
        for text, keep in (("الـ Isotretinoin مهم جدا", "الـ Isotretinoin"), ("عندنا 3 مليون عميل", "3 مليون"),
                           ("Vitamin D3 مهم", "Vitamin D3")):
            lines = wrap(text, 10, 3)
            self.assertTrue(any(keep in ln for ln in lines), (text, lines))
            self.assertEqual(" ".join(lines), text)
        two = wrap("كلمه اولي وتانيه وتالته", 14, 2)
        self.assertEqual(len(two), 2)
        self.assertTrue(all(len(ln.split()) == 2 for ln in two), two)

    def test_fit(self):
        from lib import hb_text
        from lib.motion_layout import fit
        font = test_font()
        if font is None or not hb_text.AVAILABLE:
            self.skipTest("no test font / HarfBuzz")
        short = fit("كلام قصير", str(font), 900, (120, 56), 3)
        long_ = fit("كلام اطول بكتير من الاول ومحتاج سطرين او تلاته علشان يتقري كويس", str(font), 900, (120, 56), 3)
        self.assertTrue(short["ok"] and long_["ok"])
        self.assertGreaterEqual(short["size"], long_["size"])
        self.assertTrue(all(w <= 900 for w in long_["widths"]))
        self.assertLessEqual(len(long_["lines"]), 3)
        self.assertFalse(fit("كلمه " * 80, str(font), 900, (120, 56), 3)["ok"])

    def test_contrast(self):
        from lib.motion_layout import contrast, pick_text_color
        self.assertAlmostEqual(contrast((255, 255, 255), (0, 0, 0)), 21.0, places=3)
        cfg = {"min_contrast": 4.5, "min_contrast_large": 3.0, "large_px": 64}
        name, ratio = pick_text_color((0x20, 0xAC, 0xAF), [("white", (255, 255, 255)), ("ink", (0x1F, 0x2A, 0x2A))], 64, cfg)
        self.assertEqual(name, "ink")
        with self.assertRaises(ValueError):
            pick_text_color((0xA0, 0xA0, 0xA0), [("white", (0xDD, 0xDD, 0xDD)), ("ink", (0x66, 0x66, 0x66))], 40, cfg)

    def test_place_direction(self):
        from lib.motion_config import format_spec
        from lib.motion_layout import place
        fmt = format_spec("9x16")
        self.assertGreater(place("list_steps", "number", fmt, "rtl")[0], fmt["w"] / 2)
        self.assertLess(place("list_steps", "number", fmt, "ltr")[0], fmt["w"] / 2)
        x, y = place("kinetic_quote", "text", fmt, "rtl")
        self.assertEqual(x, fmt["w"] / 2)
        self.assertTrue(fmt["safe"]["top"] < y < fmt["h"] - fmt["safe"]["bottom"])
        self.assertGreater(place("comparison", "first", fmt, "rtl")[0], fmt["w"] / 2)   # first = the reading-start side


# --------------------------------------------------------------------------- motion plan compiler
W40 = [f"كلمه{i}" for i in range(40)]


def motion_plan_fixture(tmp: Path, recipe_type: str = "drama", direction: str = "rtl"):
    """A motion project EP12_R01_MO: 40 words every 300 ms (12 s window), pauses.json (nothing removed), a cleaned
    dialogue WAV, brand tokens and a typography file pointing at a system font (None when no test font)."""
    from lib.recipes import resolve
    from lib.reels import select
    root, ep, _ = motion_episode_fixture(tmp)
    select(ep, ["R01"], [], "editor", as_="motion")
    reel = Paths(root, "EP12_R01_MO")
    fake_transcript(reel, step=300, dur_ms=12000, words=W40)
    src = read_json(reel.p("00_inputs/source.json"))
    src.update(duration_ms=12000, direction=direction, recipe=resolve(recipe_type), content_type=recipe_type)
    write_json(reel.p("00_inputs/source.json"), src)
    write_json(reel.p("06_audio/dialogue/pauses.json"), {"keep_ms": [[0, 12000]], "removed_ms": 0,
                                                          "source_duration_ms": 12000})
    ff("-f", "lavfi", "-i", "sine=f=200:r=48000:d=12", "-ac", "2", "-c:a", "pcm_s16le",
       str(reel.p("06_audio/dialogue/dialogue_clean.wav")))
    font = test_font()
    db = reel.client_db
    write_json(db / "branding/brand-tokens.json", {
        "roles": {"primary": {"hex": "#20ACAF"}, "neutral_light": {"hex": "#FFFFFF"}},
        "derived": {"paper_tint": {"hex": "#F4F1EA"}, "ink": {"hex": "#1F2A2A"}}})
    if font:
        write_json(db / "branding/typography.json", {"families": {"Test": {"weights": [
            {"style": s, "file": str(font), "postscript_name": "ArialMT"} for s in ("black", "bold", "medium", "regular")]}},
            "roles": {r: {"postscript_name": "ArialMT"} for r in ("caption", "headline", "body", "term", "small")}})
    return root, ep, reel


def mscript(*scenes, **top):
    return dict({"reel_id": "EP12_R01_MO", "beats": [{"id": "B1", "role": "hook"}, {"id": "B2", "role": "peak"}],
                 "scenes": list(scenes)}, **top)


def good_script():
    return mscript(
        scene("S01", "kinetic_quote", "@start", beat="B1", text=" ".join(W40[:10]), emphasis=["كلمه2"]),
        scene("S02", "stat_counter", "كلمه10 كلمه11", beat="B2", value="10", evidence="كلمه10 كلمه11",
              label="عميل جديد", label_source="editorial"),
        scene("S03", "list_steps", "كلمه20", items=[{"text": "كلمه20 كلمه21", "at": "كلمه20"},
                                                   {"text": "كلمه25", "at": "كلمه25"}]),
        scene("S04", "outro", "@end", cta="تابع {show}"))


class TestMotionPlan(unittest.TestCase):
    def setUp(self):
        if test_font() is None:
            self.skipTest("no test font for HarfBuzz fitting")
        self.tmp = Path(tempfile.mkdtemp())
        self.root, self.ep, self.reel = motion_plan_fixture(self.tmp)

    def tearDown(self):
        common.set_context(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def compile(self, script):
        from lib.motion_plan import compile_motion
        write_json(self.reel.p("01_analysis/motion-script.json"), script)
        return compile_motion(self.reel)

    def test_compile_ok(self):
        r = self.compile(good_script())
        self.assertTrue(r["ok"], r["errors"])
        plan = read_json(self.reel.p("01_analysis/motion-plan.json"))
        sc = plan["scenes"]
        self.assertEqual([s["id"] for s in sc], ["S01", "S02", "S03", "S04"])
        for a, b in zip(sc, sc[1:]):
            self.assertEqual(a["end_frame"], b["start_frame"])
        self.assertEqual(plan["duration_frames"], sc[-1]["end_frame"])
        self.assertEqual(plan["dir"], -1)
        kq = next(e for e in sc[0]["elements"] if e["kind"] == "text")
        self.assertEqual(len(kq["tokens"]), 10)
        self.assertTrue(all(isinstance(t["cue_frame"], int) for t in kq["tokens"]))
        self.assertEqual(kq["emphasis"], [3])
        self.assertTrue(kq["rtl"])
        self.assertEqual(kq["cue_hash"], hashlib.sha1(json.dumps([t["cue_frame"] for t in kq["tokens"]]).encode()).hexdigest()[:12])
        counter = next(e for e in sc[1]["elements"] if e["kind"] == "counter")
        self.assertEqual(counter["target"], 10)
        md = self.reel.p("01_analysis/motion-plan.md").read_text(encoding="utf-8")
        for sid in ("S01", "S02", "S03", "S04"):
            self.assertIn(sid, md)
        self.assertIn("editorial", md)
        self.assertIn("تابع بودكاست التجربة", md)                     # {show} filled from the sheet
        self.assertEqual(common.load_status(self.reel)["status"], "ANALYZED")
        self.assertTrue(Path(plan["audio"]["dialogue"]).exists())

    def test_truth_errors_block(self):
        lib = self.tmp / "lib"
        make_pack(lib, "free", "free")
        write_json(self.root / common.CLIENT_PROFILE_REL / "motion.json", {"duration_s": {"hard_min": 1},
                                                                          "library_dir": str(lib)})
        common.set_context(self.root)
        info_p = self.ep.p("00_inputs/episode.json")
        info = read_json(info_p)
        info["sheet"]["guest"] = ""
        write_json(info_p, info)
        bad = mscript(
            scene("S01", "kinetic_quote", "@start", text="كلمه0 كلمه1 زياده"),
            scene("S02", "icon_point", "كلمه8", icon="trendingup", text="كلمه8 كلمه9"),
            scene("S03", "context_card", "كلمه14", text="مع {guest}"),
            scene("S04", "illustration_scene", "كلمه20", illustration="free/doctor"),
            scene("S05", "title_card", "كلمه26", title="ط" * 200, title_source="editorial"))
        r = self.compile(bad)
        self.assertFalse(r["ok"])
        errs = " | ".join(r["errors"])
        for needle in ("زياده", "trending-up", "guest", "free", "too long"):
            self.assertIn(needle, errs)
        self.assertEqual(len([e for e in r["errors"] if "S05" in e]), 1)

    def test_episode_changed_refused(self):
        src = read_json(self.reel.p("00_inputs/source.json"))
        src["fingerprint"] = "0" * 40
        write_json(self.reel.p("00_inputs/source.json"), src)
        with self.assertRaises(SystemExit) as cm:
            self.compile(good_script())
        self.assertIn("changed", str(cm.exception))

    def test_number_approval(self):
        s = good_script()
        s["scenes"][1]["value"] = "1000000"
        r = self.compile(s)
        self.assertTrue(r["ok"], r["errors"])
        self.assertEqual(len(r["approvals"]), 1)
        self.assertIn("S02", r["approvals"][0])

    def test_dense_scene(self):
        s = mscript(scene("S01", "kinetic_quote", "@start", text=" ".join(W40[:20])),
                    scene("S02", "kinetic_quote", "كلمه20", text=" ".join(W40[20:34])))
        r = self.compile(s)
        self.assertFalse(r["ok"])
        self.assertTrue(any("S01" in e and "words" in e for e in r["errors"]), r["errors"])
        self.assertTrue(any("S02" in w and "words" in w for w in r["warnings"]), r["warnings"])

    def test_recipe_warnings(self):
        src = read_json(self.reel.p("00_inputs/source.json"))
        from lib.recipes import resolve
        src["recipe"] = resolve("emotional")
        write_json(self.reel.p("00_inputs/source.json"), src)
        r = self.compile(good_script())
        self.assertTrue(any("S03" in w and "list_steps" in w for w in r["warnings"]), r["warnings"])
        s = good_script()
        s["scenes"][2]["recipe_note"] = "the speaker lists two steps"
        r = self.compile(s)
        self.assertFalse(any("S03" in w and "list_steps" in w for w in r["warnings"]), r["warnings"])
        self.assertIn("the speaker lists two steps", self.reel.p("01_analysis/motion-plan.md").read_text(encoding="utf-8"))

    def test_single_speaker_no_turns(self):
        self.reel.p("00_inputs/speakers.json").unlink()
        r = self.compile(dict(good_script(), captions="subtitles"))
        self.assertTrue(r["ok"], r["errors"])
        plan = read_json(self.reel.p("01_analysis/motion-plan.json"))
        self.assertIsNone(plan["persistent"]["speaker_badge"])
        self.assertTrue(plan["persistent"]["captions"]["cues"])

    def test_ltr_mirror(self):
        from lib.motion_config import format_spec
        w = format_spec("9x16")["w"]
        s = good_script()
        s["scenes"][1] = scene("S02", "icon_point", "كلمه10", icon="arrow-right", text="كلمه10 كلمه11")
        r = self.compile(s)
        self.assertTrue(r["ok"], r["errors"])
        plan = read_json(self.reel.p("01_analysis/motion-plan.json"))
        num = next(e for e in plan["scenes"][2]["elements"] if e["name"].startswith("S03_number"))
        self.assertGreater(num["x"], w / 2)
        self.assertTrue(next(e for e in plan["scenes"][1]["elements"] if e["kind"] == "icon")["mirror"])
        src = read_json(self.reel.p("00_inputs/source.json"))
        src["direction"] = "ltr"
        write_json(self.reel.p("00_inputs/source.json"), src)
        r = self.compile(s)
        plan = read_json(self.reel.p("01_analysis/motion-plan.json"))
        self.assertEqual(plan["dir"], 1)
        num = next(e for e in plan["scenes"][2]["elements"] if e["name"].startswith("S03_number"))
        self.assertLess(num["x"], w / 2)
        self.assertFalse(next(e for e in plan["scenes"][1]["elements"] if e["kind"] == "icon")["mirror"])

    def test_cc_by_asset_listed(self):
        lib = self.tmp / "lib"
        make_pack(lib, "people", "CC-BY-4.0", attribution="People by X (CC BY 4.0)")
        write_json(self.root / common.CLIENT_PROFILE_REL / "motion.json", {"duration_s": {"hard_min": 1},
                                                                          "library_dir": str(lib)})
        common.set_context(self.root)
        s = good_script()
        s["scenes"][1] = scene("S02", "illustration_scene", "كلمه10", illustration="people/doctor")
        r = self.compile(s)
        self.assertTrue(r["ok"], r["errors"])
        plan = read_json(self.reel.p("01_analysis/motion-plan.json"))
        a = next(x for x in plan["assets"] if x["ref"] == "people/doctor")
        self.assertEqual((a["license"], a["attribution"]), ("CC-BY-4.0", "People by X (CC BY 4.0)"))

    def test_approve_plan_motion(self):
        from lib.motion_plan import fingerprint
        self.assertTrue(self.compile(good_script())["ok"])
        cli = SK / "engine" / "reel" / "cli.py"
        r = subprocess.run([sys.executable, "-B", str(cli), "approve-plan", "--root", str(self.root), "--video-id",
                            "EP12_R01_MO", "--by", "editor"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = read_json(self.reel.p("01_analysis/plan-approval.json"))
        self.assertEqual(rec["plan_fingerprint"], fingerprint(self.reel))
        s = good_script()
        s["scenes"][0]["text"] = " ".join(W40[:9])
        write_json(self.reel.p("01_analysis/motion-script.json"), s)
        self.assertNotEqual(rec["plan_fingerprint"], fingerprint(self.reel))


# --------------------------------------------------------------------------- animatic
class CompiledMotion(unittest.TestCase):
    """A compiled good_script() motion project, shared by the animatic, JSX, build, render and QC tests."""
    @classmethod
    def setUpClass(cls):
        if test_font() is None:
            raise unittest.SkipTest("no test font for HarfBuzz fitting")
        from lib.motion_plan import compile_motion
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root, cls.ep, cls.reel = motion_plan_fixture(cls.tmp)
        write_json(cls.reel.p("01_analysis/motion-script.json"), good_script())
        r = compile_motion(cls.reel)
        assert r["ok"], r["errors"]
        cls.plan = read_json(cls.reel.p("01_analysis/motion-plan.json"))

    @classmethod
    def tearDownClass(cls):
        common.set_context(None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        common.set_context(self.root)


class TestAnimatic(CompiledMotion):
    def test_animatic(self):
        from lib.media import probe
        from lib.motion_animatic import render
        r = render(self.reel)
        d = self.reel.p("08_quality_control/animatic")
        self.assertEqual(len(r["stills"]), len(self.plan["scenes"]))
        self.assertTrue((d / "_storyboard.jpg").exists())
        pr = probe(Path(r["mp4"]))
        want = self.plan["duration_frames"] / self.plan["fps"]
        self.assertAlmostEqual(pr["duration_s"], want, delta=1.5 / self.plan["fps"] + 0.05)
        self.assertTrue(pr["audio"])

    def test_kinetic_still_has_text(self):
        import numpy as np
        from PIL import Image
        from lib.motion_animatic import render
        r = render(self.reel)
        im = np.asarray(Image.open(r["stills"][0]).convert("RGB")).astype(int)
        bg = np.array([int(round(c * 255)) for c in self.plan["scenes"][0]["bg"]])
        diff = np.abs(im - bg).sum(axis=2) > 60
        self.assertGreater(diff.mean(), 0.01)

    def test_mix(self):
        from lib.media import probe
        from lib.motion_audio import mix
        out = mix(self.plan, self.root, self.tmp / "mix.wav")
        pr = probe(out)
        self.assertAlmostEqual(pr["duration_s"], self.plan["duration_frames"] / self.plan["fps"], delta=0.05)


# --------------------------------------------------------------------------- AE motion library + job
def nhm_code() -> str:
    src = (AE_TPL / "nh_motion_lib.jsx").read_text(encoding="utf-8")
    return src


class TestMotionJSX(CompiledMotion):
    def test_lib_syntax(self):
        for name in ("nh_motion_lib.jsx", "nh_ae_bridge.jsx"):
            assert_js_syntax(self, AE_TPL / name)

    def test_fallback_script(self):
        from lib.motion_build import write_fallback_script
        p = write_fallback_script(self.reel)
        assert_js_syntax(self, p)
        src = p.read_text(encoding="utf-8")
        self.assertIn("NHM.build(", src)
        self.assertTrue(all(ord(c) < 128 for c in src.split("var NH_JOB = ", 1)[1].split(";\n", 1)[0]))

    def test_job_ascii_paths(self):
        from lib import motion_build
        plan_p = self.reel.p("01_analysis/motion-plan.json")
        keep = plan_p.read_text(encoding="utf-8")
        try:
            plan = json.loads(keep)
            plan["audio"]["dialogue"] = "D:/0 Work/عميل/حلقة 1.wav"
            write_json(plan_p, plan)
            j = motion_build.write_job(self.reel)
            raw = j.read_bytes()
            self.assertTrue(all(b < 128 for b in raw))
            job = json.loads(raw.decode("ascii"))
            self.assertEqual(job["plan"]["audio"]["dialogue"], "D:/0 Work/عميل/حلقة 1.wav")
            self.assertEqual(job["aep_path"], str(motion_build.aep_path(self.reel)))
            self.assertIn(job["caps_source"], ("probe", "default"))
            self.assertTrue(all("layer_out_frame" in s for s in job["plan"]["scenes"]))
            kq = next(e for e in job["plan"]["scenes"][0]["elements"] if e["kind"] == "text")
            self.assertEqual(len(kq["line_cues"]), len(kq["lines"]))
        finally:
            plan_p.write_text(keep, encoding="utf-8")

    def test_lib_uses_frame_duration(self):
        src = nhm_code()
        self.assertTrue("frameDuration" in src)
        self.assertNotRegex(src, r"/\s*NH\.FPS")
        self.assertNotIn(".indexOf(", src.split("/* expressions */")[0])   # ES3: no Array.indexOf in ExtendScript code

    def test_lib_defines_core(self):
        src = nhm_code()
        for fn in ("NHM.build = function", "NHM.S.kinetic_quote = function", "NHM.S.title_card = function",
                   "NHM.P.background = function", "NHM.P.captions = function", "NHM.P.speaker_badge = function",
                   "NHM.P.progress = function", "NHM.P.voice_pulse = function", "NHM.transition = function",
                   "NHM.textEl = function", "setValuesAtTimes"):
            self.assertTrue(fn in src, fn)
        bridge = (AE_TPL / "nh_ae_bridge.jsx").read_text(encoding="utf-8")
        self.assertIn("NHAE.actions.build_motion = function", bridge)
        self.assertIn('reason: "dirty"', bridge)

    def test_fallback_refuses_unsaved_project(self):
        """Final review: the --script-only/--run-script fallback called app.newProject() with no dirty check. It must
        refuse exactly like the bridge (NHAE.mayDiscard): unsaved or unknown state in a saved/non-empty project."""
        from lib.motion_build import write_fallback_script
        script = write_fallback_script(self.reel).read_text(encoding="utf-8")
        saved = {"name": "work.aep", "fsName": "D:/their/work.aep"}
        for project, want in (({"dirty": True, "numItems": 3, "file": saved}, ["alert"]),
                              ({"dirty": None, "numItems": 3, "file": saved}, ["alert"]),
                              ({"dirty": False, "numItems": 3, "file": saved}, ["newProject"]),
                              ({"dirty": None, "numItems": 0, "file": None}, ["newProject"])):
            js = ("var calls = [];\nfunction alert(m) { calls.push('alert'); }\n"
                  "var app = {project: " + json.dumps(project) + ", beginUndoGroup: function () {}, "
                  "endUndoGroup: function () {},\n"
                  "  newProject: function () { calls.push('newProject'); throw new Error('STOP'); }};\n"
                  "try { (function () {\n" + script + "\n})(); } catch (e) { if (e.message !== 'STOP') { "
                  "calls.push('error: ' + e); } }\nconsole.log(JSON.stringify(calls));\n")
            self.assertEqual(json.loads(node_run(self, js)), want, project)

    def test_fallback_refusal_is_its_result(self):
        """Review (Minor 4): the refusing script's own result names the project (osascript reports it on macOS)."""
        from lib.motion_build import write_fallback_script
        script = write_fallback_script(self.reel).read_text(encoding="utf-8")
        project = {"dirty": True, "numItems": 3, "file": {"name": "work.aep", "fsName": "D:/their/work.aep"}}
        js = ("function alert(m) {}\nvar app = {project: " + json.dumps(project) + ", newProject: function () {}};\n"
              "var src = " + json.dumps(script) + ";\n"
              "console.log(JSON.stringify(String((function () { return eval(src); })())));\n")
        self.assertEqual(json.loads(node_run(self, js)), "WHYNOT_REFUSED: work.aep")


def jsx_fn(src: str, name: str) -> str:
    """Body of `name = function` in the JSX source (up to the next top-level `NHM.` assignment)."""
    a = src.index(name + " = function")
    b = src.find("\nNHM.", a + 1)
    return src[a:b if b > 0 else len(src)]


class TestMotionScenesJSX(unittest.TestCase):
    def test_every_scene_type_defined(self):
        from lib.motion_script import SCENE_TYPES
        src = nhm_code()
        for t in SCENE_TYPES:
            self.assertTrue(f"NHM.S.{t} = function" in src, t)

    def test_persistent_text_direction_follows_text(self):
        """Review: captions and the speaker badge were always RTL; Latin captions in an English (ltr) window got RTL
        paragraph direction (punctuation at the wrong end)."""
        src = nhm_code()
        self.assertTrue("NHM.isArabic = function" in src)
        for fn, var in (("NHM.P.captions", "q.text"), ("NHM.P.speaker_badge", "g.name")):
            body = jsx_fn(src, fn)
            self.assertFalse("rtl: true" in body, fn)
            self.assertTrue(f"rtl: NHM.isArabic({var})" in body, fn)
        import re
        rx = re.search(r"NHM\.isArabic = function \(s\) \{\s*return (/\[.*?\]/)\.test", src).group(1)
        py = re.compile(rx.strip("/"))
        self.assertTrue(py.search("كلمه") and py.search("ﻻ") and not py.search("Hello, world!"))

    def test_comparison_divider_above_scene_bg(self):
        """Review: moveToEnd() put the divider under the scene's own _bg solid on themed scenes."""
        body = jsx_fn(nhm_code(), "NHM.S.comparison")
        self.assertTrue('scene.id + "_bg"' in body and "moveBefore(" in body, body)

    def test_icons_draw_on_and_round_caps(self):
        src = nhm_code()
        self.assertTrue("ADBE Vector Filter - Trim" in src)
        self.assertTrue("ADBE Vector Stroke Line Cap" in src)
        self.assertTrue("ADBE Vector Trim End" in jsx_fn(src, "NHM.iconEl"))

    def test_counter_expression(self):
        body = jsx_fn(nhm_code(), "NHM.counterEl")
        self.assertTrue('"ADBE Text Document").expression' in body)
        self.assertTrue("linear(time" in body)

    def test_direction_from_plan(self):
        src = nhm_code()
        for fn in ("NHM.appear", "NHM.transition", "NHM.S.timeline"):
            self.assertTrue("NHM.plan.dir" in jsx_fn(src, fn), fn)

    def test_syntax(self):
        assert_js_syntax(self, AE_TPL / "nh_motion_lib.jsx")


# --------------------------------------------------------------------------- build, read-back, protection
def rb_from_plan(job: dict) -> dict:
    """A read-back exactly as AE would report a faithful build of this job."""
    plan = job["plan"]
    scenes = []
    for sc in plan["scenes"]:
        layers = []
        for el in sc["elements"]:
            if el.get("kind") in ("text", "counter"):
                layers.append({"name": el["name"], "kind": "text", "text": el.get("text", "") if el["kind"] == "text" else "0",
                               "font_ps": el["font_ps"], "substitute": False, "composer": "UNIVERSAL",
                               "direction": "RTL" if el.get("rtl") else "LTR", "direction_pr": "RTL" if el.get("rtl") else "LTR",
                               "rect": [el["x"] - 20, el["y"] - 20, 40, 40], "comment": el.get("cue_hash") or ""})
        scenes.append({"id": sc["id"], "comp": f"{sc['id']}_{sc['type']}", "in_frame": sc["start_frame"],
                       "out_frame": sc["layer_out_frame"], "layers": layers})
    return {"main": {"name": "MAIN_" + plan["reel_id"]}, "scenes": scenes, "missing_or_substituted": []}


class FakeAE:
    def __init__(self, dirty=False, project_path=None, fonts_ok=True, version="26.0", readback=None, num_items=3):
        self.dirty, self.project_path, self.fonts_ok, self.version = dirty, project_path, fonts_ok, version
        self.readback, self.jobs, self.num_items = readback, [], num_items

    @staticmethod
    def ok(result):
        return {"ok": result.get("ok", True) is not False, "response": {"ok": result.get("ok", True) is not False,
                                                                        "result": result}}

    def status(self, max_age_s=5.0):
        return {"alive": True, "busy": False, "host": "AEFT", "detail": "ok"}

    def submit(self, action, data=None, timeout=900):
        if action == "ping":
            return self.ok({"ae_version": self.version, "dirty": self.dirty, "project_path": self.project_path,
                            "num_items": self.num_items})
        if action == "fonts":
            return self.ok({"fonts": {n: {"found": self.fonts_ok, "substitute": False} for n in data["postscript_names"]},
                            "missing_or_substituted": []})
        if action == "build_motion":
            self.jobs.append(data["job"])
            if self.dirty:
                return self.ok({"ok": False, "reason": "dirty", "project": "theirs.aep"})
            Path(data["job"]["aep_path"]).write_bytes(b"AEP built " + str(len(self.jobs)).encode())
            return self.ok({"made": [s["id"] for s in data["job"]["plan"]["scenes"]], "failed": [], "warnings": [],
                            "saved": data["job"]["aep_path"]})
        if action == "readback":
            return self.ok(self.readback(data["job"]) if self.readback else rb_from_plan(data["job"]))
        return {"ok": False, "error": f"unexpected {action}"}


class TestMotionBuild(CompiledMotion):
    def setUp(self):
        super().setUp()
        from lib import ae_bridge, ae_probe, motion_build, plat
        self.mods = (ae_bridge, ae_probe, plat)
        self.saved = (ae_bridge.submit, ae_bridge.status, ae_probe.verdict_ok, plat.newest_app)
        self.ae = FakeAE()
        ae_bridge.submit, ae_bridge.status = self.ae.submit, self.ae.status
        ae_probe.verdict_ok = lambda v: v == "26.0"
        plat.newest_app = lambda key: {"name": "Adobe After Effects 2026", "exe": "AfterFX.exe"}
        self.mb = motion_build
        for f in (motion_build.aep_path(self.reel), self.reel.p("04_after_effects/motion-build-result.json")):
            f.unlink(missing_ok=True)
        shutil.rmtree(self.reel.p("04_after_effects/project/backups"), ignore_errors=True)
        common.set_status(self.reel, "ANALYZED", "test reset")
        self.approve()

    def tearDown(self):
        (ae_bridge, ae_probe, plat) = self.mods
        ae_bridge.submit, ae_bridge.status, ae_probe.verdict_ok, plat.newest_app = self.saved

    def approve(self):
        from lib.motion_plan import fingerprint
        write_json(self.reel.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor",
                                                                   "plan_fingerprint": fingerprint(self.reel)})

    def test_build_ok(self):
        r = self.mb.build(self.reel)
        self.assertEqual(r["status"], "PROJECT_ASSEMBLED", r)
        self.assertTrue(r["comparison"]["ok"])
        self.assertEqual(r["aep_sha1"], hashlib.sha1(self.mb.aep_path(self.reel).read_bytes()).hexdigest())
        self.assertEqual(common.load_status(self.reel)["status"], "PROJECT_ASSEMBLED")
        self.assertEqual(read_json(self.reel.p("04_after_effects/motion-build-result.json"))["status"], "PROJECT_ASSEMBLED")

    def test_refusals(self):
        self.reel.p("01_analysis/plan-approval.json").unlink()
        r = self.mb.build(self.reel)
        self.assertEqual(r["status"], "REFUSED")
        self.assertTrue(any("approv" in x for x in r["reasons"]), r["reasons"])
        self.approve()
        from lib import ae_probe
        ae_probe.verdict_ok = lambda v: False
        r = self.mb.build(self.reel)
        self.assertTrue(any("probe" in x for x in r["reasons"]), r["reasons"])
        ae_probe.verdict_ok = lambda v: True
        self.ae.fonts_ok = False
        r = self.mb.build(self.reel)
        self.assertEqual(r["status"], "REFUSED")
        self.assertTrue(any("font" in x for x in r["reasons"]), r["reasons"])
        r = self.mb.build(self.reel, allow_fallback_font=True)
        self.assertEqual(r["status"], "PROJECT_ASSEMBLED", r)
        self.assertTrue(r["fallback_font"])
        self.assertTrue(all(e["font_ps"] == r["fallback_font"] for s in self.ae.jobs[-1]["plan"]["scenes"]
                            for e in s["elements"] if e.get("font_ps")))

    def test_stale_approval(self):
        sp = self.reel.p("01_analysis/motion-script.json")
        keep = sp.read_bytes()
        s = read_json(sp)
        try:
            s["notes"] = "edited after approval"
            write_json(self.reel.p("01_analysis/motion-script.json"), s)
            r = self.mb.build(self.reel)
            self.assertEqual(r["status"], "REFUSED")
            self.assertTrue(any("stale" in x for x in r["reasons"]), r["reasons"])
        finally:
            sp.write_bytes(keep)

    def test_dirty_session(self):
        self.ae.dirty, self.ae.project_path = True, "D:/their/work.aep"
        r = self.mb.build(self.reel)
        self.assertEqual(r["status"], "REFUSED")
        self.assertTrue(any("save or close" in x for x in r["reasons"]), r["reasons"])
        self.assertEqual(self.ae.jobs, [])
        self.ae.dirty = False
        self.assertEqual(self.mb.build(self.reel)["status"], "PROJECT_ASSEMBLED")

    def test_unknown_dirty_refused(self):
        """Review: AE that cannot report `dirty` (null) must not count as clean: app.newProject() would discard work."""
        n = len(self.ae.jobs)
        self.ae.dirty, self.ae.project_path = None, "D:/their/work.aep"
        r = self.mb.build(self.reel)
        self.assertEqual(r["status"], "REFUSED", r)
        self.assertTrue(any("unsaved" in x for x in r["reasons"]), r["reasons"])
        self.assertEqual(len(self.ae.jobs), n)
        self.ae.project_path, self.ae.num_items = None, 0          # an empty untitled project has nothing to lose
        self.assertEqual(self.mb.build(self.reel)["status"], "PROJECT_ASSEMBLED")
        bridge = (AE_TPL / "nh_ae_bridge.jsx").read_text(encoding="utf-8")
        self.assertNotIn("info.dirty === true", bridge)
        self.assertEqual(bridge.count("NHAE.mayDiscard(info)"), 2)

    def test_rebuild_protection(self):
        self.assertEqual(self.mb.build(self.reel)["status"], "PROJECT_ASSEMBLED")
        aep = self.mb.aep_path(self.reel)
        aep.write_bytes(b"EDITED IN AE")
        self.assertTrue(self.mb.editor_changed(self.reel))
        r = self.mb.build(self.reel)
        self.assertEqual(r["status"], "REFUSED")
        self.assertTrue(any("changed" in x for x in r["reasons"]), r["reasons"])
        r = self.mb.build(self.reel, replace_edited=True)
        self.assertEqual(r["status"], "PROJECT_ASSEMBLED")
        backups = list(self.reel.p("04_after_effects/project/backups").glob("*.aep"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b"EDITED IN AE")

    def fake_run_script_env(self, titles: list[str], ae=None):
        """`--run-script` without the bridge: After Effects' window titles (the OS query) and the AfterFX launcher
        replaced. `ae(jsx, timeout, done)` plays After Effects; by default it records the launch and returns at once."""
        from lib import adobe_run
        launched = []
        saved = (self.mb.__dict__.get("_ae_titles"), adobe_run.run_after_effects)
        self.mb._ae_titles = lambda: list(titles)
        adobe_run.run_after_effects = lambda jsx, timeout, done=None: (launched.append(jsx) or
                                                                       (ae(jsx, timeout, done) if ae else {"stdout": ""}))

        def restore():
            adobe_run.run_after_effects = saved[1]
            if saved[0] is None:
                self.mb.__dict__.pop("_ae_titles", None)
            else:
                self.mb._ae_titles = saved[0]
        self.addCleanup(restore)
        return launched

    def test_run_script_refuses_unsaved_project_at_once(self):
        """Review (Minor 4): `--run-script` launched the fallback script into an After Effects holding unsaved work; the
        script refused (an alert in AE) and the engine waited the whole --timeout to report "no read-back". After
        Effects' title ends with " *" while its project has unsaved changes (seen live in AE 26.5, the path elided in
        the middle): the engine refuses at once, naming the project, without launching anything."""
        for title, name in (("Adobe After Effects 2026 - D:\\0 Work\\0 Pegasus IM ... ts\\EP02_R02_MO\\04_after_effects"
                             "\\project\\EP02_R02_MO_RE_MOTION.aep *", "EP02_R02_MO_RE_MOTION.aep"),
                            ("Adobe After Effects 2026 - Untitled Project.aep *", "Untitled Project.aep")):
            launched = self.fake_run_script_env(["", title])
            t0 = time.time()
            r = self.mb.run_script(self.reel, timeout=30)
            self.assertEqual(r["status"], "REFUSED", r)
            self.assertTrue(any(name in x and "unsaved changes" in x for x in r["reasons"]), r["reasons"])
            self.assertEqual(launched, [])
            self.assertLess(time.time() - t0, 10)
        self.assertFalse(self.reel.p(self.mb.RESULT).exists())          # a refusal, like build()'s, records nothing

    def test_run_script_clean_project_launches(self):
        """A saved project (no " *") and no After Effects running both launch the script."""
        for titles in (["Adobe After Effects 2026 - D:\\work\\EP02_R02_MO_RE_MOTION.aep"], []):
            launched = self.fake_run_script_env(titles)
            self.mb.run_script(self.reel, timeout=1)
            self.assertEqual(len(launched), 1, titles)

    def test_run_script_timeout_says_why(self):
        """Review (Minor 4): when the .aep never appears (e.g. After Effects could not tell whether its project is saved,
        so the script refused with an alert), the result says so instead of only "no read-back"."""
        def ae_never_saves(jsx, timeout, done):
            t0 = time.time()
            while time.time() - t0 < timeout and not done():
                time.sleep(0.05)
            return {"stdout": ""}
        self.fake_run_script_env([], ae_never_saves)
        r = self.mb.run_script(self.reel, timeout=1)
        self.assertEqual(r["status"], "FAILED", r)
        why = " ".join(r["reasons"])
        self.assertIn("not saved", why)
        self.assertIn("unsaved changes", why)
        self.assertNotIn("no read-back", why)

    def test_run_script_reads_the_script_refusal(self):
        """macOS (no window titles): osascript returns the script's own result; a refusal ends the run as REFUSED."""
        launched = self.fake_run_script_env([], lambda jsx, timeout, done: {"stdout": "WHYNOT_REFUSED: work.aep\n"})
        r = self.mb.run_script(self.reel, timeout=30)
        self.assertEqual(len(launched), 1)
        self.assertEqual(r["status"], "REFUSED", r)
        self.assertTrue(any("work.aep" in x and "unsaved changes" in x for x in r["reasons"]), r["reasons"])

    def test_refused_replace_edited_keeps_no_backup(self):
        """Final review: --replace-edited copied the editor's .aep to backups/ before the preconditions, so a build
        refused for another reason (here: no Gate 1 approval) still left a backup behind."""
        self.assertEqual(self.mb.build(self.reel)["status"], "PROJECT_ASSEMBLED")
        self.mb.aep_path(self.reel).write_bytes(b"EDITED IN AE")
        self.reel.p("01_analysis/plan-approval.json").unlink()
        r = self.mb.build(self.reel, replace_edited=True)
        self.assertEqual(r["status"], "REFUSED", r)
        self.assertEqual(list(self.reel.p("04_after_effects/project/backups").glob("*.aep")), [])
        self.assertEqual(self.mb.aep_path(self.reel).read_bytes(), b"EDITED IN AE")

    def test_compare(self):
        from lib.motion_config import format_spec
        from lib.motion_readback import compare
        job = self.mb.job_data(self.reel)
        plan, fmt, caps = job["plan"], format_spec(job["plan"]["format"]), job["caps"]
        self.assertTrue(compare(plan, rb_from_plan(job), fmt, caps)["ok"])

        def mutate(fn):
            rb = rb_from_plan(job)
            fn(rb)
            return compare(plan, rb, fmt, caps)
        first_text = lambda rb: rb["scenes"][0]["layers"][0]
        cases = {
            "substitute": lambda rb: first_text(rb).update(substitute=True),
            "string": lambda rb: first_text(rb).update(text="شيء تاني"),
            "box": lambda rb: first_text(rb).update(rect=[400, fmt["safe"]["top"] - 80, 40, 40]),
            "missing scene": lambda rb: rb["scenes"].pop(1),
            "cue hash": lambda rb: first_text(rb).update(comment="0" * 12),
            "missing fonts": lambda rb: rb.update(missing_or_substituted=["ArialMT"]),
        }
        for name, fn in cases.items():
            r = mutate(fn)
            self.assertFalse(r["ok"], name)
            self.assertTrue(r["failures"], name)

    def test_script_only(self):
        r = self.mb.script_only(self.reel)
        self.assertEqual(r["status"], "SCRIPT_ONLY")
        assert_js_syntax(self, Path(r["jsx"]))
        self.assertNotEqual(common.load_status(self.reel)["status"], "PROJECT_ASSEMBLED")


class TestBridgeLibLoading(unittest.TestCase):
    """Live AE 26.5 showed `NHM is undefined`: $.evalFile inside a function keeps the libraries' globals local."""
    def test_libs_loaded_at_top_level(self):
        src = (AE_TPL / "nh_ae_bridge.jsx").read_text(encoding="utf-8")
        head = src.split("NHAE.q = function", 1)[0]
        self.assertNotIn("(function", head)
        self.assertIn('$.evalFile(new File(NHAE_HERE + "/nh_ae_lib.jsx"))', head)
        self.assertIn('$.evalFile(new File(NHAE_HERE + "/nh_motion_lib.jsx"))', head)
        self.assertIn("libs_loaded", src)


# --------------------------------------------------------------------------- render, MP4, cover, frames
class TestMotionRender(CompiledMotion):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from lib.common import fps_arg
        from lib import motion_build
        motion_build.aep_path(cls.reel).parent.mkdir(parents=True, exist_ok=True)
        motion_build.aep_path(cls.reel).write_bytes(b"AEP")
        cls.dur = cls.plan["duration_frames"] / cls.plan["fps"]
        cls.fakes = {}
        for name, d, audio in (("ok", cls.dur, True), ("short", cls.dur - 1.0, True), ("mute", cls.dur, False)):
            f = cls.tmp / f"fake_{name}.mov"
            args = ["-f", "lavfi", "-i", f"testsrc2=s={cls.plan['w']}x{cls.plan['h']}:r={fps_arg()}:d={d:.3f}"]
            if audio:
                args += ["-f", "lavfi", "-i", f"sine=f=300:r=48000:d={d:.3f}", "-c:a", "aac"]
            ff(*args, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-t", f"{d:.3f}", str(f))
            cls.fakes[name] = f

    def setUp(self):
        super().setUp()
        from lib import ae_render
        self.saved = ae_render.render
        self.use("ok")

    def tearDown(self):
        from lib import ae_render
        ae_render.render = self.saved

    def use(self, name):
        from lib import ae_render
        src = self.fakes[name]

        def fake(aep, comp, out, rs, om, start_frame=None, end_frame=None, timeout=3600, log=None):
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, out)
            return {"status": "RENDERED", "returncode": 0, "output": str(out), "elapsed_s": 0.1, "log": None}
        ae_render.render = fake

    def test_frame_points(self):
        from lib.motion_render import frame_points
        pts = frame_points(self.plan)
        heroes = [p for p in pts if p["kind"] == "hero"]
        self.assertEqual(len(heroes), len(self.plan["scenes"]))
        mids = [p for p in pts if p["kind"] == "reveal_mid"]
        self.assertEqual({p["scene"] for p in mids}, {"S01", "S03"})          # kinetic quote + list
        kq = next(p for p in mids if p["scene"] == "S01")
        toks = next(e for e in self.plan["scenes"][0]["elements"] if e["kind"] == "text")["tokens"]
        self.assertEqual(kq["expect"]["revealed_tokens"], len([t for t in toks if t["cue_frame"] <= kq["frame"]]))
        self.assertTrue(0 < kq["expect"]["revealed_tokens"] < len(toks))
        trans = [p for p in pts if p["kind"] == "transition_mid"]
        self.assertEqual(len(trans), len([s for s in self.plan["scenes"] if s["transition_in"]["frames"] > 0]))
        self.assertEqual(pts, sorted(pts, key=lambda p: p["frame"]))

    def test_render_ok(self):
        from lib.motion_render import render
        r = render(self.reel)
        self.assertEqual(r["status"], "RENDERED", r)
        self.assertTrue(Path(r["mp4"]).exists())
        self.assertTrue(Path(r["cover"]).exists())
        self.assertEqual((r["probe"]["w"], r["probe"]["h"]), (self.plan["w"], self.plan["h"]))

    def test_render_duration_mismatch(self):
        from lib.motion_render import render
        self.use("short")
        r = render(self.reel)
        self.assertEqual(r["status"], "FAILED")
        self.assertTrue(any("duration" in x for x in r["reasons"]), r["reasons"])

    def test_render_no_audio(self):
        from lib.media import probe
        from lib.motion_render import render
        self.use("mute")
        r = render(self.reel)
        self.assertEqual(r["status"], "RENDERED", r)
        self.assertTrue(probe(Path(r["mp4"]))["audio"])
        self.assertTrue(any("audio" in w for w in r["warnings"]), r["warnings"])

    def test_frames(self):
        from lib.motion_render import frame_points, frames, render
        render(self.reel)
        r = frames(self.reel)
        pts = frame_points(self.plan)
        self.assertEqual(r["frames"], len(pts))
        d = Path(r["dir"])
        self.assertTrue((d / "_sheet.jpg").exists())
        fj = read_json(d / "frames.json")
        self.assertEqual(len(fj["frames"]), len(pts))
        self.assertTrue(all((d / f["file"]).exists() for f in fj["frames"]))
        self.assertIn("expect", fj["frames"][0])

    @unittest.skipUnless(sys.platform == "win32", "only Windows refuses to delete a file another program holds open")
    def test_open_output_says_close_the_file(self):
        """Final review: a player holding the previous MOV/MP4 open made motion-render die with a raw PermissionError
        (Windows) instead of saying which file to close."""
        from lib.motion_build import render_path
        from lib.motion_render import render
        r = render(self.reel)
        self.assertEqual(r["status"], "RENDERED", r)
        self.assertEqual(render(self.reel, scenes=["S01"])["status"], "RENDERED")
        piece = self.reel.p(f"04_after_effects/render/pieces/{self.reel.video_id}_S01.mov")
        for f, kw in ((render_path(self.reel), {}), (Path(r["mp4"]), {}), (piece, {"scenes": ["S01"]})):
            with open(f, "rb"):
                try:
                    render(self.reel, **kw)
                except SystemExit as e:
                    msg = str(e)
                except PermissionError as e:
                    self.fail(f"{f.name}: raw {e!r}")
                else:
                    self.fail(f"{f.name}: no refusal while the file is open")
            self.assertIn("close the file", msg)
            self.assertIn(f.name, msg)


class TestWordLayers(unittest.TestCase):
    """Live AE 26.5 probe: an expression selector "Based On: Words" maps textIndex inconsistently for RTL Arabic
    (indexes 1, 2 and 4 all lit the first word). Word/line reveals therefore use one text layer per word."""
    def test_word_layers_defined_and_used(self):
        src = nhm_code()
        self.assertTrue("NHM.wordLayers = function" in src)
        body = jsx_fn(src, "NHM.textEl")
        self.assertTrue("NHM.wordLayers(" in body)
        self.assertNotIn("NHM.revealWords(", body)
        wl = jsx_fn(src, "NHM.wordLayers")
        self.assertTrue("sourceRectAtTime" in wl)
        self.assertTrue("guideLayer" in wl)
        self.assertTrue("transform.scale[0]" in wl)        # an emphasised (scaled) word keeps its space (live frame)

    def test_shape_layer_reacquires_trim(self):
        body = jsx_fn(nhm_code(), "NHM.shapeLayer")
        stroke_at = body.index('addProperty("ADBE Vector Graphic - Stroke")')
        self.assertGreater(body.find('property("ADBE Vector Filter - Trim")', stroke_at), stroke_at)

    def test_probe_has_word_layers_comp(self):
        from lib.ae_probe import look_points, probe_job
        names = [c["name"] for c in probe_job({"headline": "ArialMT"})["comps"]]
        self.assertIn("word_layers", names)
        self.assertIn(("word_layers_20", names.index("word_layers") * 90 + 20), look_points())


# --------------------------------------------------------------------------- motion QC, verify, next, handoff, publish
def bursty_wav(path: Path, seconds: float, seed: int = 7):
    """Speech-like loudness bursts (so envelope correlation is meaningful), 48 kHz mono."""
    import wave
    import numpy as np
    rng = np.random.default_rng(seed)
    n = int(seconds * 48000)
    env = np.repeat(rng.uniform(0.05, 1.0, int(seconds * 6) + 1), 8000)[:n]
    x = (np.sin(2 * np.pi * 220 * np.arange(n) / 48000) * env * 0.5 * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(x.tobytes())
    return path


class TestMotionQC(CompiledMotion):
    def setUp(self):
        super().setUp()
        import time as _t
        from lib import motion_build
        from lib.motion_plan import fingerprint
        from lib.common import fps_arg
        r = self.reel
        self.dur = self.plan["duration_frames"] / self.plan["fps"]
        dia = bursty_wav(Path(self.plan["audio"]["dialogue"]), self.dur)
        anim = r.p(f"08_quality_control/animatic/{r.video_id}_animatic.mp4")
        anim.parent.mkdir(parents=True, exist_ok=True)
        anim.write_bytes(b"animatic")
        write_json(r.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor",
                                                           "plan_fingerprint": fingerprint(r)})
        aep = motion_build.aep_path(r)
        aep.parent.mkdir(parents=True, exist_ok=True)
        aep.write_bytes(b"AEP built")
        write_json(r.p("04_after_effects/motion-build-result.json"), {
            "status": "PROJECT_ASSEMBLED", "aep": str(aep), "aep_sha1": hashlib.sha1(b"AEP built").hexdigest(),
            "comparison": {"ok": True, "failures": [], "warnings": []}, "readback": {"scenes": []}, "reasons": []})
        _t.sleep(1.1)
        main = motion_build.render_path(r)
        main.parent.mkdir(parents=True, exist_ok=True)
        ff("-f", "lavfi", "-i", f"testsrc2=s=108x192:r={fps_arg()}:d={self.dur:.3f}", "-i", str(dia), "-c:v", "libx264",
           "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(main))
        write_json(r.p("04_after_effects/motion-render-result.json"), {"status": "RENDERED", "main": str(main),
                                                                       "reasons": [], "warnings": [], "pieces": []})
        write_json(r.p("06_audio/dialogue/cut-verification.json"), {"ok": True, "verdict": "no speech cut"})
        _t.sleep(1.1)
        run = r.p("08_quality_control/ae_frames/run-20990101-000000")
        run.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        Image.new("RGB", (40, 40)).save(run / "_sheet.jpg")
        write_json(run / "frames.json", {"frames": []})
        from lib.motion_qc import record_visual
        record_visual(r, "pass", "frames viewed", "claude")

    def tearDown(self):
        shutil.rmtree(self.reel.p("08_quality_control/ae_frames"), ignore_errors=True)

    def checks(self):
        from lib.motion_qc import run
        r = run(self.reel)
        return r, {c["check"]: c["result"] for c in r["checks"]}

    def test_complete_passes(self):
        r, c = self.checks()
        self.assertTrue(r["ok"], r["failed"])
        for k in ("plan_valid", "approval_current", "aep_fresh", "readback", "render", "audio_sync", "cut_proof",
                  "visual_verified", "licenses"):
            self.assertEqual(c[k], "PASS", k)
        self.assertTrue(self.reel.p("08_quality_control/qc-results.json").exists())

    def test_piece_render_after_rebuild_fails_render(self):
        """Review: a `--scenes` piece render after a rebuild must not let QC pass on the old MAIN render / MP4."""
        import time as _t
        from lib import motion_build
        from lib.motion_qc import record_visual
        r = self.reel
        _t.sleep(1.1)
        aep = motion_build.aep_path(r)
        aep.write_bytes(b"AEP rebuilt")
        bres = r.p("04_after_effects/motion-build-result.json")
        write_json(bres, dict(read_json(bres), aep_sha1=hashlib.sha1(b"AEP rebuilt").hexdigest()))
        _t.sleep(1.1)
        piece = r.p(f"04_after_effects/render/pieces/{r.video_id}_S01.mov")
        piece.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(motion_build.render_path(r), piece)
        piece.touch()
        rr = r.p("04_after_effects/motion-render-result.json")
        write_json(rr, dict(read_json(rr), pieces=[{"scene": "S01", "file": str(piece), "start_frame": 0,
                                                    "end_frame": 10, "rendered_at": _t.time()}]))
        _t.sleep(1.1)
        run = r.p("08_quality_control/ae_frames/run-20990101-000001")
        run.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        Image.new("RGB", (40, 40)).save(run / "_sheet.jpg")
        record_visual(r, "pass", "piece frames viewed", "claude")
        res, c = self.checks()
        self.assertEqual(c["render"], "FAIL", c)
        self.assertFalse(res["ok"])

    def test_silent_render_fails_render_check(self):
        """Final review: a MOV without an audio stream passed the render check and only failed later as audio_sync
        «no audio to compare»; the render check names it."""
        from lib import motion_build
        from lib.common import fps_arg
        silent = self.tmp / "silent.mov"
        ff("-f", "lavfi", "-i", f"testsrc2=s=108x192:r={fps_arg()}:d={self.dur:.3f}", "-c:v", "libx264", "-preset",
           "ultrafast", "-pix_fmt", "yuv420p", str(silent))
        shutil.copyfile(silent, motion_build.render_path(self.reel))
        r, c = self.checks()
        self.assertEqual(c["render"], "FAIL", c)
        self.assertIn("no audio stream", next(x["detail"] for x in r["checks"] if x["check"] == "render"))

    def test_audio_sync_near_miss_hint(self):
        """Final review: the render's full mix (music + SFX) is correlated with the dry dialogue; a loud music bed can
        pull it just under 0.9 with no diagnostic. QC keeps the FAIL but says what it measured and what to look at."""
        from lib import motion_build
        from lib.common import fps_arg

        def sync():
            r, c = self.checks()
            return c["audio_sync"], next(x["detail"] for x in r["checks"] if x["check"] == "audio_sync")
        res, detail = sync()
        self.assertEqual(res, "PASS", detail)
        self.assertNotIn("music", detail)
        dia = Path(self.plan["audio"]["dialogue"])
        bed = bursty_wav(self.tmp / "bed.wav", self.dur, seed=99)             # measured: correlation 0.86
        mixed = self.tmp / "loud_bed.mov"
        ff("-f", "lavfi", "-i", f"testsrc2=s=108x192:r={fps_arg()}:d={self.dur:.3f}", "-i", str(dia), "-i", str(bed),
           "-filter_complex", "[2:a]volume=0.8[b];[1:a][b]amix=inputs=2:normalize=0[a]", "-map", "0:v", "-map", "[a]",
           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(mixed))
        shutil.copyfile(mixed, motion_build.render_path(self.reel))
        res, detail = sync()
        # loose on purpose (review Minor 8): the exact value depends on ffmpeg's amix/AAC; the band rules are pinned
        # with fixed values in TestAudioSyncDetail
        import re
        corr = float(re.search(r"correlation (\d\.\d+)", detail).group(1))
        self.assertEqual(res == "PASS", corr >= 0.9, detail)
        self.assertEqual("just under 0.9" in detail, 0.8 <= corr < 0.9, detail)

    def test_audio_sync_bed_diagnostic(self):
        """Final review: when the plan's music/SFX bed pulls the dialogue correlation under 0.9, QC also compares the
        render with the engine's planned mix (dialogue + music + SFX) and says whether the voice itself is in sync."""
        from lib import motion_build
        from lib.common import fps_arg
        from lib.motion_audio import mix
        plan_p = self.reel.p("01_analysis/motion-plan.json")
        keep = plan_p.read_bytes()
        self.addCleanup(plan_p.write_bytes, keep)
        plan = json.loads(keep.decode("utf-8"))
        bed = bursty_wav(self.tmp / "bed.wav", self.dur, seed=99)
        plan["audio"]["music"] = {"file": str(bed), "level_db": -1.94, "fade_out_frames": 0}     # 0.8 x the voice
        write_json(plan_p, plan)
        planned = mix(plan, self.root, self.tmp / "planned.wav")
        rendered = self.tmp / "planned_render.mov"
        ff("-f", "lavfi", "-i", f"testsrc2=s=108x192:r={fps_arg()}:d={self.dur:.3f}", "-i", str(planned), "-c:v",
           "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(rendered))
        shutil.copyfile(rendered, motion_build.render_path(self.reel))
        r, c = self.checks()
        detail = next(x["detail"] for x in r["checks"] if x["check"] == "audio_sync")
        self.assertEqual(c["audio_sync"], "FAIL", detail)                  # the 0.9 rule stands (spec ruling)
        self.assertRegex(detail, r"planned mix[^;]*correlation (0\.9\d*|1\.0), offset 0")
        self.assertIn("the render matches the planned mix", detail)

    def test_audio_sync_bed_diagnostic_edges(self):
        """Review: the planned-mix comparison must also say when the render does NOT match the plan, must not build a
        silently different mix when a planned file is gone, and must not leave its scratch mix in the QC folder."""
        from lib import motion_build
        from lib.common import fps_arg
        plan_p = self.reel.p("01_analysis/motion-plan.json")
        keep = plan_p.read_bytes()
        self.addCleanup(plan_p.write_bytes, keep)
        plan = json.loads(keep.decode("utf-8"))
        dia = Path(plan["audio"]["dialogue"])
        planned_bed, other_bed = (bursty_wav(self.tmp / f"bed{s}.wav", self.dur, seed=s) for s in (99, 5))
        rendered = self.tmp / "other_bed.mov"                     # AE rendered a different bed than the plan's
        ff("-f", "lavfi", "-i", f"testsrc2=s=108x192:r={fps_arg()}:d={self.dur:.3f}", "-i", str(dia), "-i", str(other_bed),
           "-filter_complex", "[2:a]volume=0.8[b];[1:a][b]amix=inputs=2:normalize=0[a]", "-map", "0:v", "-map", "[a]",
           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(rendered))
        shutil.copyfile(rendered, motion_build.render_path(self.reel))

        def detail_with(music_file):
            write_json(plan_p, dict(plan, audio=dict(plan["audio"], music={"file": str(music_file), "level_db": -1.94,
                                                                           "fade_out_frames": 0})))
            r, c = self.checks()
            self.assertEqual(c["audio_sync"], "FAIL")
            return next(x["detail"] for x in r["checks"] if x["check"] == "audio_sync")
        self.assertIn("does not match the planned mix", detail_with(planned_bed))
        gone = self.tmp / "renamed_track.wav"
        d = detail_with(gone)
        self.assertIn("planned mix unavailable", d)
        self.assertIn(gone.name, d)
        self.assertEqual([f.name for f in self.reel.p("08_quality_control").glob("*.wav")], [])

    def test_each_check_fails(self):
        import time as _t
        from lib import motion_build
        r = self.reel
        bres = r.p("04_after_effects/motion-build-result.json")
        good_b = read_json(bres)

        def expect_fail(name):
            _, c = self.checks()
            self.assertEqual(c[name], "FAIL", (name, c))

        appr = read_json(r.p("01_analysis/plan-approval.json"))
        write_json(r.p("01_analysis/plan-approval.json"), dict(appr, plan_fingerprint="x"))
        expect_fail("approval_current")
        write_json(r.p("01_analysis/plan-approval.json"), appr)

        write_json(bres, dict(good_b, comparison={"ok": False, "failures": ["S01: font"]}))
        expect_fail("readback")
        write_json(bres, dict(good_b, status="BUILT_UNVERIFIED", readback=None, comparison=None))
        expect_fail("readback")
        write_json(bres, good_b)

        aep = motion_build.aep_path(r)
        aep.write_bytes(b"EDITED")
        expect_fail("aep_fresh")
        expect_fail("render")                                  # the .aep is now newer than the render
        aep.write_bytes(b"AEP built")
        _t.sleep(1.1)
        main = motion_build.render_path(r)
        main.touch()

        dia = Path(self.plan["audio"]["dialogue"])
        late = self.tmp / "late.wav"
        ff("-i", str(dia), "-af", f"adelay={int(3000 / self.plan['fps'])}", str(late))
        keep = dia.read_bytes()
        dia.write_bytes(late.read_bytes())
        expect_fail("audio_sync")
        dia.write_bytes(keep)

        cv = r.p("06_audio/dialogue/cut-verification.json")
        cv.unlink()
        expect_fail("cut_proof")
        write_json(cv, {"ok": True})

        _t.sleep(1.1)
        newer = r.p("08_quality_control/ae_frames/run-20991231-000000")
        newer.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        Image.new("RGB", (40, 40)).save(newer / "_sheet.jpg")
        expect_fail("visual_verified")
        shutil.rmtree(newer)

        plan_p = r.p("01_analysis/motion-plan.json")
        keep_plan = plan_p.read_bytes()
        plan = json.loads(keep_plan.decode("utf-8"))
        plan["assets"] = [{"ref": "x/y", "license": "free", "attribution": ""}]
        write_json(plan_p, plan)
        expect_fail("licenses")
        plan_p.write_bytes(keep_plan)

    def test_next_order_and_stale(self):
        import time as _t
        from lib.motion_qc import motion_next
        n = motion_next(self.reel)
        self.assertTrue(n["next"].startswith(("qc", "handoff")), n)       # qc may be stale from an earlier test
        _t.sleep(1.1)
        sp = self.reel.p("01_analysis/motion-script.json")
        sp.write_bytes(sp.read_bytes())                        # touched: newer than the compiled plan
        n = motion_next(self.reel)
        self.assertTrue(n["stale"] and n["stale"][0].startswith("motion-plan"), n)

    def test_verify_record_motion(self):
        import time as _t
        cli = SK / "engine" / "reel" / "cli.py"
        base = [sys.executable, "-B", str(cli), "verify", "--record", "--verdict", "pass", "--notes", "x",
                "--root", str(self.root), "--video-id", "EP12_R01_MO"]
        r = subprocess.run(base, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = read_json(self.reel.p("08_quality_control/visual-verification.json"))
        self.assertIn("ae_frames", rec["sheet"])
        _t.sleep(1.1)
        from lib import motion_build
        motion_build.render_path(self.reel).touch()
        r = subprocess.run(base, capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(r.returncode, 0)

    def test_handoff_motion(self):
        from lib.handoff import motion_readme
        plan_p = self.reel.p("01_analysis/motion-plan.json")
        keep = plan_p.read_bytes()
        try:
            plan = json.loads(keep.decode("utf-8"))
            plan["assets"] = [{"ref": "people/doctor", "license": "CC-BY-4.0", "attribution": "People by X (CC BY 4.0)"}]
            write_json(plan_p, plan)
            md = motion_readme(self.reel).read_text(encoding="utf-8")
        finally:
            plan_p.write_bytes(keep)
        from lib.motion_build import aep_path
        self.assertIn(aep_path(self.reel).name, md)
        self.assertIn("MAIN_", md)
        self.assertIn("ArialMT", md)
        self.assertIn("People by X (CC BY 4.0)", md)

    def test_publish_cc_by(self):
        from test_podcast import good_pub, good_reel
        from lib.publish import check
        plan_p = self.reel.p("01_analysis/motion-plan.json")
        keep = plan_p.read_bytes()
        try:
            plan = json.loads(keep.decode("utf-8"))
            plan["assets"] = [{"ref": "people/doctor", "license": "CC-BY-4.0", "attribution": "People by X (CC BY 4.0)"}]
            write_json(plan_p, plan)
            write_json(self.ep.p("publish/publish.json"), good_pub())
            reel = good_reel()
            reel["reel_id"] = "EP12_R01_MO"
            write_json(self.ep.p("publish/reels/EP12_R01_MO.json"), reel)
            r = check(self.ep)
            self.assertTrue(any("People by X" in e for e in r["errors"]), r["errors"])
            reel["instagram"]["caption"] = str(reel["instagram"].get("caption", "")) + "\nPeople by X (CC BY 4.0)"
            write_json(self.ep.p("publish/reels/EP12_R01_MO.json"), reel)
            r = check(self.ep)
            self.assertFalse(any("People by X" in e for e in r["errors"]), r["errors"])
        finally:
            plan_p.write_bytes(keep)


# --------------------------------------------------------------------------- plugin layer
GUARD_PY = SK / "hooks" / "guard.py"


def guard_write(path: str, agent: str | None = None) -> int:
    payload = {"tool_name": "Write", "tool_input": {"file_path": path, "content": "x"}, "cwd": "."}
    if agent:
        payload["agent_type"] = agent
    from test_plugin import isolated_env
    return subprocess.run([sys.executable, "-B", str(GUARD_PY)], input=json.dumps(payload), capture_output=True,
                          text=True, encoding="utf-8", env=isolated_env()).returncode


def front(p: Path) -> str:
    return p.read_text(encoding="utf-8").split("---")[1]


class TestMotionPluginLayer(unittest.TestCase):
    def test_agents(self):
        md = front(SK / "agents/motion-director.md")
        for k in ("name: motion-director", "description:", "tools:", "model: opus"):
            self.assertIn(k, md)
        ab = front(SK / "agents/ae-builder.md")
        for k in ("name: ae-builder", "description:", "tools:", "model:"):
            self.assertIn(k, ab)
        tools = next(ln for ln in ab.splitlines() if ln.startswith("tools:"))
        self.assertNotIn("Write", tools)
        self.assertNotIn("Edit", tools)

    def test_motion_skill(self):
        s = (SK / "skills/motion/SKILL.md").read_text(encoding="utf-8")
        for k in ("--as motion", "Gate 1", "animatic", "ae-probe", "verify --record", "motion-build", "approve-plan"):
            self.assertIn(k, s)
        for ref in ("motion-scenes.md", "motion-beats.md", "ae-motion.md"):
            self.assertTrue((SK / "skills/motion-craft/references" / ref).exists(), ref)

    def test_guard(self):
        self.assertEqual(run_guard("reel ae-probe --record ok --word-order logical", agent="ae-builder"), 2)
        self.assertEqual(run_guard("reel motion-build --video-id X", agent="whynot-cut:qc-reviewer"), 2)
        self.assertEqual(run_guard("reel motion-build --video-id X"), 0)                 # not an extra
        self.assertEqual(run_guard("reel ae-status"), 0)
        self.assertEqual(guard_write("C:/Users/x/AppData/Roaming/Adobe/After Effects/26.0/Adobe After Effects 26.0 Prefs.txt"), 2)
        self.assertEqual(guard_write("C:/Users/x/Library/Preferences/Adobe/After Effects/26.0/Adobe After Effects 26.0 Prefs-indep-general.txt"), 2)

    def test_guard_ae_prefs_message_on_shell_paths(self):
        """Final review: a shell write to an After Effects preference file was refused as «the client's source folder
        (After Effects preferences) is read-only»; it gets the preferences wording, as the Write tool does."""
        pref = "C:/Users/x/AppData/Roaming/Adobe/After Effects/26.0/Adobe After Effects 26.0 Prefs.txt"
        for tool, cmd in (("Bash", f'cp new.txt "{pref}"'), ("Bash", f'echo x > "{pref}"'),
                          ("PowerShell", f'Copy-Item new.txt "{pref}"')):
            r = subprocess.run([sys.executable, "-B", str(GUARD_PY)], capture_output=True, text=True, encoding="utf-8",
                               input=json.dumps({"tool_name": tool, "tool_input": {"command": cmd}, "cwd": "."}))
            self.assertEqual(r.returncode, 2, (cmd, r.stderr))
            self.assertIn("After Effects preferences are the editor's to change", r.stderr, cmd)
            self.assertNotIn("source folder", r.stderr, cmd)

    def test_session_context_mentions_motion(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            root = tmp / "C"
            for d in ("assets", "data/Episodes"):
                (root / d).mkdir(parents=True)
            (root / "data/Episodes/POD.m4a").write_bytes(b"x")
            (root / ".whynot-client").write_text("{}", encoding="utf-8")     # 3.0: positive client marker
            r = subprocess.run([sys.executable, "-B", str(SK / "hooks/session_context.py")], input=json.dumps({"cwd": str(root)}),
                               capture_output=True, text=True, encoding="utf-8", cwd=str(root))
            self.assertIn("motion", r.stdout)
            self.assertIn("POD", r.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_reels_plan_md_motion_flag(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            from lib.episode import EpisodePaths
            from lib.reels import write_reels_plan_md
            root = tmp / "C"
            (root / "assets").mkdir(parents=True)
            (root / "data").mkdir(parents=True)
            ep = EpisodePaths(root, "EP1")
            ep.ensure_project()
            md = write_reels_plan_md(ep, {"duration_ms": 60000, "candidates": [
                {"id": "R01", "total": 7.0, "type": "advice", "type_label": "x", "in_ms": 0, "out_ms": 30000,
                 "duration_ms": 30000, "title": "t", "motion_fit": True, "motion_why": "numbers and steps"}]})
            self.assertIn("motion", md.read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestMotionRelease(unittest.TestCase):
    def test_versions(self):
        pj = json.loads((SK / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        mj = json.loads((SK.parent / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
        # the exact number is pinned once, in test_release_hygiene.py; here only that the three agree
        self.assertEqual(mj["metadata"]["version"], pj["version"])
        self.assertEqual(mj["plugins"][0]["version"], pj["version"])
        for k in ("motion", "after-effects", "animation"):
            self.assertIn(k, pj["keywords"])
        self.assertIn("After Effects", pj["description"])

    def test_docs(self):
        log = (SK / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## 2.2.0", log)
        self.assertLess(log.index("## 2.2.1"), log.index("## 2.2.0"))      # the newest release on top
        readme = (SK / "README.md").read_text(encoding="utf-8")
        for k in ("/whynot-cut:motion", "--as motion", "motion-build", "ae-probe"):
            self.assertIn(k, readme)
        notices = (SK / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("Lucide", notices)
        self.assertIn("ISC", notices)

    def test_package_rules(self):
        sys.path.insert(0, str(SK.parent))
        try:
            import package
        finally:
            sys.path.remove(str(SK.parent))
        self.assertFalse(package.wanted(SK.parent / "tools" / "vendor_lucide.py"))
        self.assertTrue(package.wanted(SK / "templates/motion/icons/lucide/LICENSE"))
        self.assertTrue(package.wanted(SK / "templates/motion/icons/lucide/icons.json"))
        self.assertTrue(package.wanted(SK / "THIRD_PARTY_NOTICES.md"))


class TestTransitionOverlap(unittest.TestCase):
    """Live run (EP02TEST_R02_MO): the last word of a scene spoken inside the next scene's push window was flagged
    'too short', but transitions play AFTER the outgoing scene's end (its layer stays on during the overlap)."""
    def test_transition_after_end(self):
        from lib.motion_timing import frame_scenes
        common.set_context(None)
        out, errs = frame_scenes([{"id": "S01", "start_ms": 0, "end_ms": 3000, "cues_ms": [2800]}], None, 30.0,
                                 MCFG, [12])
        self.assertEqual(errs, [])
        self.assertTrue(out[0]["cue_frames"][0] <= out[0]["hero_frame"] <= out[0]["end_frame"] - 1, out[0])


class TestLiveFindings(unittest.TestCase):
    """Live run (EP02TEST_R02_MO) storyboard: captions repeated words already on screen in list/icon scenes, and the
    outro repeated the show name already inside the CTA."""
    @classmethod
    def setUpClass(cls):
        if test_font() is None:
            raise unittest.SkipTest("no test font for HarfBuzz fitting")
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root, cls.ep, cls.reel = motion_plan_fixture(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        common.set_context(None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        common.set_context(self.root)

    def test_captions_hidden_where_speech_is_shown(self):
        from lib.motion_plan import compile_motion
        s = dict(good_script(), captions="subtitles")
        s["scenes"][1] = scene("S02", "icon_point", "كلمه10", icon="trophy", text="كلمه10 كلمه11")
        write_json(self.reel.p("01_analysis/motion-script.json"), s)
        r = compile_motion(self.reel)
        self.assertTrue(r["ok"], r["errors"])
        plan = read_json(self.reel.p("01_analysis/motion-plan.json"))
        shown = [(x["start_frame"], x["end_frame"]) for x in plan["scenes"] if x["type"] in ("icon_point", "list_steps")]
        for c in plan["persistent"]["captions"]["cues"]:
            for a, b in shown:
                self.assertFalse(c["start_frame"] < b and c["end_frame"] > a, (c, a, b))

    def test_timeline_when_digits_need_approval(self):
        """Review (spec §4.1 Numbers): digits in timeline.when not said as digits go to approval, not an error — a year
        said in words («ألفين وتسعتاشر») is written 2019 on screen."""
        from lib.motion_plan import compile_motion
        s = good_script()
        s["scenes"][2] = scene("S03", "timeline", "كلمه20", points=[
            {"label": "كلمه20 كلمه21", "at": "كلمه20", "when": "1999"},
            {"label": "كلمه25", "at": "كلمه25", "when": "«2005»"}])
        write_json(self.reel.p("01_analysis/motion-script.json"), s)
        r = compile_motion(self.reel)
        self.assertFalse(r["ok"])                                       # quotes in an editorial line are still errors
        self.assertTrue(any("quotation" in e for e in r["errors"]), r["errors"])
        self.assertFalse(any("not said in this window" in e for e in r["errors"]), r["errors"])
        s["scenes"][2]["points"][1]["when"] = "2005"
        write_json(self.reel.p("01_analysis/motion-script.json"), s)
        r = compile_motion(self.reel)
        self.assertTrue(r["ok"], r["errors"])
        self.assertTrue(any("1999" in a for a in r["approvals"]) and any("2005" in a for a in r["approvals"]),
                        r["approvals"])

    def test_hero_after_every_spoken_word(self):
        """Live frames: S04 (icon_point) had its hero frame 11 frames in, before 6 of its 8 words had appeared,
        because speech text built through `either` (icon/title/label/illustration) never reached the scene cues."""
        from lib.motion_plan import compile_motion
        s = good_script()
        s["scenes"][1] = scene("S02", "icon_point", "كلمه10", icon="trophy", text="كلمه10 كلمه11 كلمه12 كلمه13")
        write_json(self.reel.p("01_analysis/motion-script.json"), s)
        r = compile_motion(self.reel)
        self.assertTrue(r["ok"], r["errors"])
        plan = read_json(self.reel.p("01_analysis/motion-plan.json"))
        for sc in plan["scenes"]:
            cues = [t["cue_frame"] for e in sc["elements"] for t in e.get("tokens") or []]
            if cues:
                self.assertTrue(sc["hero_frame"] >= max(cues), (sc["id"], sc["hero_frame"], max(cues)))

    def test_outro_no_duplicate_show(self):
        from lib.motion_plan import compile_motion
        write_json(self.reel.p("01_analysis/motion-script.json"), good_script())       # cta "تابع {show}"
        self.assertTrue(compile_motion(self.reel)["ok"])
        plan = read_json(self.reel.p("01_analysis/motion-plan.json"))
        outro = plan["scenes"][-1]
        self.assertFalse(any(e["name"].startswith("S04_show") for e in outro["elements"]))


class TestFontRoles(unittest.TestCase):
    """Live run: a brand with only Medium/SemiBold/Bold weights (no Black) got an EMPTY PostScript name for the
    headline roles ('Unable to set font' in After Effects)."""
    def test_nearest_weight_file_and_name_together(self):
        if test_font() is None:
            self.skipTest("no test font")
        tmp = Path(tempfile.mkdtemp())
        try:
            root, ep, reel = motion_plan_fixture(tmp)
            f = str(test_font())
            write_json(reel.client_db / "branding/typography.json", {"families": {"Brand": {"weights": [
                {"style": "Medium", "file": f, "postscript_name": "Brand-Medium"},
                {"style": "SemiBold", "file": f, "postscript_name": "Brand-SemiBold"},
                {"style": "Bold", "file": f, "postscript_name": "Brand-Bold"}]}}})
            from lib.motion_plan import compile_motion
            write_json(reel.p("01_analysis/motion-script.json"), good_script())
            r = compile_motion(reel)
            self.assertTrue(r["ok"], r["errors"])
            plan = read_json(reel.p("01_analysis/motion-plan.json"))
            for role, spec in plan["fonts"].items():
                self.assertTrue(spec["ps"].startswith("Brand-"), (role, spec))
            self.assertEqual(plan["fonts"]["title"]["ps"], "Brand-Bold")      # nearest to Black
            self.assertEqual(plan["fonts"]["body"]["ps"], "Brand-Medium")
            for s in plan["scenes"]:
                for e in s["elements"]:
                    if e.get("kind") in ("text", "counter"):
                        self.assertTrue(e["font_ps"], e["name"])
        finally:
            common.set_context(None)
            shutil.rmtree(tmp, ignore_errors=True)


class TestFallbackRefit(CompiledMotion):
    """Live run: with --allow-fallback-font the layout was measured with the brand font file but After Effects drew
    the wider fallback font (S01 left the safe area by 9 px). The plan must be re-fitted with the fallback font."""
    def test_find_font_file(self):
        from lib.motion_layout import find_font_file
        tf = test_font()
        import freetype
        ps = freetype.Face(str(tf)).postscript_name.decode()
        self.assertEqual(Path(find_font_file(ps)).name.lower(), tf.name.lower())
        self.assertIsNone(find_font_file("NoSuchFont-Bold"))

    def test_build_refits_with_fallback(self):
        import freetype
        from lib import ae_bridge, ae_probe, motion_build, plat
        from lib.motion_plan import fingerprint
        ps = freetype.Face(str(test_font())).postscript_name.decode()
        write_json(self.root / common.CLIENT_PROFILE_REL / "motion.json",
                   {"duration_s": {"hard_min": 1}, "fallback_fonts": {"windows": ps, "mac": ps}})
        common.set_context(self.root)
        typ = self.reel.client_db / "branding/typography.json"
        keep_typ = typ.read_bytes()
        f = str(test_font())
        write_json(typ, {"families": {"Brand": {"weights": [{"style": st, "file": f, "postscript_name": "Brand-" + st}
                                                            for st in ("Medium", "Bold")]}}})
        from lib.motion_plan import compile_motion
        self.assertTrue(compile_motion(self.reel)["ok"])
        self.assertTrue(read_json(self.reel.p("01_analysis/motion-plan.json"))["fonts"]["title"]["ps"].startswith("Brand-"))
        write_json(self.reel.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor",
                                                                   "plan_fingerprint": fingerprint(self.reel)})
        self.addCleanup(typ.write_bytes, keep_typ)
        saved = (ae_bridge.submit, ae_bridge.status, ae_probe.verdict_ok, plat.newest_app)
        ae = FakeAE(fonts_ok=False)
        ae_bridge.submit, ae_bridge.status = ae.submit, ae.status
        ae_probe.verdict_ok = lambda v: True
        plat.newest_app = lambda key: {"name": "AE", "exe": "AfterFX.exe"}
        try:
            r = motion_build.build(self.reel, allow_fallback_font=True)
        finally:
            ae_bridge.submit, ae_bridge.status, ae_probe.verdict_ok, plat.newest_app = saved
        self.assertEqual(r["status"], "PROJECT_ASSEMBLED", r)
        # the job carries the layout re-fitted with the font After Effects draws ...
        job = json.loads(self.reel.p("04_after_effects/data/motion-job.json").read_text(encoding="ascii"))["plan"]
        self.assertTrue(all(v["ps"] == ps for v in job["fonts"].values()), job["fonts"])
        self.assertEqual(Path(job["fonts"]["title"]["file"]).name.lower(), test_font().name.lower())
        # ... but the approved plan keeps the brand fonts (review: a later plain rebuild must not ship the fallback)
        plan = read_json(self.reel.p("01_analysis/motion-plan.json"))
        self.assertTrue(plan["fonts"]["title"]["ps"].startswith("Brand-"), plan["fonts"])
        self.assertEqual(plan["fingerprint"], fingerprint(self.reel))
        res = read_json(self.reel.p(motion_build.RESULT))
        self.assertEqual(res["fallback_font"], ps)
        self.assertTrue(any(n.startswith("Brand-") for n in res["brand_fonts"]), res.get("brand_fonts"))
        from lib.handoff import motion_readme
        txt = motion_readme(self.reel).read_text(encoding="utf-8")
        needs = txt.split("## Needs you", 1)[1]
        self.assertTrue(ps in needs and "Brand-" in needs, needs)

    def test_readme_fallback_fonts_plural(self):
        """Final review: «…Bold, …Medium is not installed: install it» — several missing brand fonts read as plural."""
        from lib.handoff import motion_readme
        res = self.reel.p("04_after_effects/motion-build-result.json")
        keep = res.read_bytes() if res.exists() else None
        self.addCleanup(lambda: res.write_bytes(keep) if keep is not None else res.unlink(missing_ok=True))
        for fonts, want in ((["Brand-Bold", "Brand-Medium"], "Brand-Bold, Brand-Medium are not installed: install them"),
                            (["Brand-Bold"], "Brand-Bold is not installed: install it")):
            write_json(res, {"status": "PROJECT_ASSEMBLED", "fallback_font": "SegoeUI-Bold", "brand_fonts": fonts})
            needs = motion_readme(self.reel).read_text(encoding="utf-8").split("## Needs you", 1)[1]
            self.assertIn(want, needs)


class TestLockedAudio(CompiledMotion):
    """Live run (Windows): After Effects holds imported audio open, so recompiling must never rewrite a file it
    imported: the sequence dialogue is content-addressed and existing SFX are reused."""
    def test_dialogue_content_addressed(self):
        import time as _t
        from lib.motion_audio import sequence_dialogue
        from lib.timemap import TimeMap
        tm = TimeMap([[0, 12000]])
        a = sequence_dialogue(self.reel, tm)
        self.assertRegex(a.name, r"^dialogue_motion_seq_[0-9a-f]{8}\.wav$")
        t0 = a.stat().st_mtime
        _t.sleep(1.1)
        b = sequence_dialogue(self.reel, tm)
        self.assertEqual(a, b)
        self.assertEqual(b.stat().st_mtime, t0)                     # not rewritten
        c = sequence_dialogue(self.reel, TimeMap([[0, 5000], [6000, 12000]]))
        self.assertNotEqual(a, c)                                    # different content -> a new file name

    def test_sfx_reused(self):
        import time as _t
        from lib.motion_audio import sfx_files
        d = self.reel.p("06_audio/sfx")
        f = sfx_files({"pop"}, d)["pop"]
        t0 = f.stat().st_mtime
        _t.sleep(1.1)
        self.assertEqual(sfx_files({"pop"}, d)["pop"].stat().st_mtime, t0)

    def test_qc_uses_plan_dialogue(self):
        src = (SK / "engine/reel/lib/motion_qc.py").read_text(encoding="utf-8")
        self.assertNotIn('"06_audio/dialogue/dialogue_motion_seq.wav"', src)

    def test_unreferenced_dialogue_pruned(self):
        """Final review: content-addressed dialogue_motion_seq_*.wav files piled up. Files neither the plan nor the
        last build job names are removed; one that After Effects (or a player) holds open is left for a later run."""
        from lib.motion_audio import sequence_dialogue
        from lib.timemap import TimeMap
        d = self.reel.p("06_audio/dialogue")
        in_plan = Path(self.plan["audio"]["dialogue"])
        in_job, stale, held = (d / f"dialogue_motion_seq_{h}.wav" for h in ("10b10b10", "0badf00d", "0ffe1d00"))
        for f in (in_job, stale, held):
            f.write_bytes(b"RIFF")
            self.addCleanup(f.unlink, missing_ok=True)
        job = self.reel.p("04_after_effects/data/motion-job.json")
        job.parent.mkdir(parents=True, exist_ok=True)
        job.write_text(json.dumps({"plan": {"audio": {"dialogue": str(in_job)}}}), encoding="ascii")
        self.addCleanup(job.unlink, missing_ok=True)
        lock = open(held, "rb") if sys.platform == "win32" else None
        try:
            new = sequence_dialogue(self.reel, TimeMap([[0, 4000], [5000, 12000]]))
        finally:
            if lock:
                lock.close()
        self.assertFalse(stale.exists())
        for f in (new, in_plan, in_job):
            self.assertTrue(f.exists(), f.name)
        if lock:
            self.assertTrue(held.exists())

    def test_dialogue_named_by_a_project_kept(self):
        """Review: a build refused after write_job (or a --script-only/--run-script build, which writes no job) left
        no record of the dialogue the existing .aep imports, so a later re-plan deleted it (missing footage in the
        editor's project). A dialogue named in any project .aep (backups too) or by basename in the plan/job (paths
        from another machine after a hand-over) is kept."""
        from lib.motion_audio import sequence_dialogue
        from lib.timemap import TimeMap
        d = self.reel.p("06_audio/dialogue")
        proj = self.reel.p("04_after_effects/project")
        (proj / "backups").mkdir(parents=True, exist_ok=True)
        in_aep, in_backup, moved, stale = (d / f"dialogue_motion_seq_{h}.wav"
                                           for h in ("a1a1a1a1", "b2b2b2b2", "c3c3c3c3", "0dead0ff"))
        for f in (in_aep, in_backup, moved, stale):
            f.write_bytes(b"RIFF")
            self.addCleanup(f.unlink, missing_ok=True)
        aep, bak = proj / "EP12_R01_MO_RE_MOTION.aep", proj / "backups" / "EP12_R01_MO_RE_MOTION.edited-1.aep"
        aep.write_bytes(b"RIFX\x00fnam" + str(in_aep).encode("utf-8") + b"\x00more")      # AE stores paths as UTF-8
        bak.write_bytes(b"RIFX\x00" + in_backup.name.encode("utf-16-le") + b"\x00")
        for f in (aep, bak):
            self.addCleanup(f.unlink, missing_ok=True)
        job = self.reel.p("04_after_effects/data/motion-job.json")
        job.parent.mkdir(parents=True, exist_ok=True)
        job.write_text(json.dumps({"plan": {"audio": {"dialogue": "E:/old pc/06_audio/dialogue/" + moved.name}}}),
                       encoding="ascii")
        self.addCleanup(job.unlink, missing_ok=True)
        sequence_dialogue(self.reel, TimeMap([[0, 4500], [5500, 12000]]))
        self.assertFalse(stale.exists())
        for f in (in_aep, in_backup, moved):
            self.assertTrue(f.exists(), f.name)


class TestDialogue24Bit(CompiledMotion):
    """Live run: audio-clean writes dialogue_clean.wav as 24-bit PCM; sequence_dialogue decoded it as 16-bit and
    produced noise (−0.8 LUFS from a −14.3 LUFS source)."""
    def test_24bit_source_keeps_loudness(self):
        from lib.audio_clean import _lufs
        from lib.motion_audio import envelope, sequence_dialogue
        from lib.timemap import TimeMap
        src = self.reel.p("06_audio/dialogue/dialogue_clean.wav")
        keep = src.read_bytes()
        try:
            tmp24 = self.tmp / "d24.wav"
            ff("-f", "lavfi", "-i", "sine=f=220:r=48000:d=12", "-af", "volume=0.25", "-ac", "2", "-c:a", "pcm_s24le",
               str(tmp24))
            src.write_bytes(tmp24.read_bytes())
            out = sequence_dialogue(self.reel, TimeMap([[0, 12000]]))
            self.assertAlmostEqual(_lufs(out), _lufs(tmp24), delta=1.0)
            vals = envelope(out, 24.0, 48)
            self.assertTrue(0.5 < sum(vals) / len(vals) <= 1.0, vals[:5])       # steady tone, not noise
        finally:
            src.write_bytes(keep)


# --------------------------------------------------------------------------- final-review minors (2.2.0)
def node_run(tc, js: str) -> str:
    """Runs JavaScript in node: After Effects / CEP code driven through a fake host object. Returns stdout."""
    if not shutil.which("node"):
        tc.skipTest("needs node")
    r = subprocess.run(["node", "-"], input=js, capture_output=True, text=True, encoding="utf-8", timeout=120)
    tc.assertEqual(r.returncode, 0, r.stderr[-1500:])
    return r.stdout


class TestReviewMinorsPlan(unittest.TestCase):
    """Final-review minors in the plan compiler (one motion project, compiled per test)."""
    @classmethod
    def setUpClass(cls):
        if test_font() is None:
            raise unittest.SkipTest("no test font for HarfBuzz fitting")
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root, cls.ep, cls.reel = motion_plan_fixture(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        common.set_context(None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        common.set_context(self.root)

    def compile(self, script):
        from lib.motion_plan import compile_motion
        write_json(self.reel.p("01_analysis/motion-script.json"), script)
        return compile_motion(self.reel), read_json(self.reel.p("01_analysis/motion-plan.json"))

    @staticmethod
    def cues_in(plan, sid):
        sc = next(x for x in plan["scenes"] if x["id"] == sid)
        cues = ((plan["persistent"].get("captions") or {}).get("cues")) or []
        return [c for c in cues if c["start_frame"] < sc["end_frame"] and c["end_frame"] > sc["start_frame"]]

    def test_scene_captions_override(self):
        """Spec §3.4: a scene's own `captions` overrides the video's — "off" hides them in that scene, "on" shows them
        there when the video has none. Only the automatic hiding (speech on screen) existed."""
        s = dict(good_script(), captions="subtitles")
        r, plan = self.compile(s)
        self.assertTrue(r["ok"], r["errors"])
        self.assertTrue(self.cues_in(plan, "S02"))                  # the stat counter shows captions by default
        s["scenes"][1]["captions"] = "off"
        r, plan = self.compile(s)
        self.assertTrue(r["ok"], r["errors"])
        self.assertEqual(self.cues_in(plan, "S02"), [])
        s = good_script()                                           # drama: captions off for the video
        s["scenes"][1]["captions"] = "on"
        r, plan = self.compile(s)
        self.assertTrue(r["ok"], r["errors"])
        cues = plan["persistent"]["captions"]["cues"]
        self.assertTrue(cues)
        self.assertEqual(cues, self.cues_in(plan, "S02"))

    def test_comparison_verdict_not_said_one_error(self):
        """Final review: a speech-source comparison `verdict` that is not said was reported, then ALSO run through the
        editorial checks (a second error and a bogus editorial line)."""
        s = good_script()
        s["scenes"][1] = scene("S02", "comparison", "كلمه10", first={"label": "كلمه11"}, second={"label": "كلمه13"},
                               verdict="الافضل 100")
        r, _ = self.compile(s)
        self.assertFalse(r["ok"])
        self.assertEqual(len([e for e in r["errors"] if "verdict" in e]), 1, r["errors"])
        self.assertFalse(any(e["field"] == "verdict" for e in r["editorial_lines"]), r["editorial_lines"])


class TestAEHostBehaviour(unittest.TestCase):
    """Final-review minors in the After Effects / CEP JavaScript, run in node with a fake host."""
    def test_progress_grows_in_reading_direction(self):
        """Final review: in LTR the progress bar grew from the centre. It fills from the reading-start edge: the bar's
        group is anchored (and positioned, so it does not move) at the left edge in LTR, the right edge in RTL."""
        libs = (AE_TPL / "nh_ae_lib.jsx").read_text(encoding="utf-8") + "\n" + nhm_code()
        js = libs + r"""
function F() { this.kids = {}; this.added = []; }
F.prototype.property = function (k) { return typeof k === "number" ? this.added[k - 1] : (this.kids[k] = this.kids[k] || new F()); };
F.prototype.addProperty = function (k) { var f = new F(); this.added.push(f); this.kids[k] = this.kids[k] || f; return f; };
F.prototype.setValue = function (v) { this.value = v; };
F.prototype.setValueAtTime = function (t, v) { (this.keys = this.keys || []).push(v); };
function bar(dir) {
  var main = {width: 1080, height: 1920, frameDuration: 1 / 24, layers: {addShape: function () { return new F(); }}};
  var L = NHM.P.progress(main, {persistent: {progress: true}, safe: {top: 250}, theme: {accent: [1, 0, 0]},
                                direction: dir < 0 ? "rtl" : "ltr", dir: dir, duration_frames: 240});
  var g = L.property("ADBE Root Vectors Group").property(1);
  var size = g.property("ADBE Vectors Group").property(1).property("ADBE Vector Rect Size").value;
  var t = g.property("ADBE Vector Transform Group");
  function ev(e) { var content = function () { return {content: function () { return {size: size}; }}; }; return e ? eval(e) : [0, 0]; }
  return {anchor: ev(t.property("ADBE Vector Anchor").expression), position: ev(t.property("ADBE Vector Position").expression),
          scale: t.property("ADBE Vector Scale").keys};
}
console.log(JSON.stringify({ltr: bar(1), rtl: bar(-1)}));
"""
        out = json.loads(node_run(self, js))
        for d, edge in (("ltr", -540), ("rtl", 540)):
            self.assertEqual(out[d]["anchor"], [edge, 0], d)
            self.assertEqual(out[d]["position"], [edge, 0], d)
            self.assertEqual(out[d]["scale"], [[0, 100], [100, 100]], d)

    def test_bridge_reads_host_once(self):
        """Final review (cosmetic): bridge.js asked CEP for the host environment twice at start-up."""
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        ext, base = tmp / "ext", tmp / "home"
        ext.mkdir()
        base.mkdir()
        (ext / "bridge-config.json").write_text(json.dumps({"base": str(base)}), encoding="utf-8")
        js = ("var EXT = " + json.dumps(str(ext)) + ", HOMEDIR = " + json.dumps(str(tmp)) + ", n = 0, nodeRequire = require;\n"
              "globalThis.window = {require: function (m) { return m === 'os' ? {homedir: function () { return HOMEDIR; },"
              " platform: function () { return process.platform; }} : nodeRequire(m); },\n"
              "  __adobe_cep__: {getHostEnvironment: function () { n++; return JSON.stringify({appName: 'AEFT'}); },\n"
              "                  getSystemPath: function () { return EXT; }, evalScript: function () {}}};\n"
              "globalThis.document = {getElementById: function () { return {textContent: ''}; }};\n"
              "globalThis.setInterval = function () { return 0; };\n"
              + (CEP / "js" / "bridge.js").read_text(encoding="utf-8") + "\nconsole.log(JSON.stringify({calls: n}));\n")
        self.assertEqual(json.loads(node_run(self, js))["calls"], 1)
        self.assertTrue((base / "ae-queue").is_dir())                 # it is the After Effects bridge

    def test_bridge_escaper_ascii_under_any_decoding(self):
        """Final review: NHAE.q's regex held a raw U+FFFF character. Read with another encoding than UTF-8 that one
        character becomes three, the class stops at U+00EF and Arabic leaks unescaped into the result JSON. The
        escaper gives pure ASCII however the file is decoded."""
        raw = (AE_TPL / "nh_ae_bridge.jsx").read_bytes()
        s = chr(0x628) + chr(0x627) + chr(1) + 'x"'
        for enc in ("utf-8", "latin-1"):
            src = raw.decode(enc)
            a = src.index("NHAE.q = function")
            b = src.index("\n};", a) + 3
            js = ("var NHAE = {};\n" + src[a:b] + "\nvar s = " + json.dumps(s) + ", out = NHAE.q(s);\n"
                  "console.log(JSON.stringify({ascii: out.split('').every(function (c) { return c.charCodeAt(0) < 128; }),"
                  " back: JSON.parse(out) === s}));\n")
            self.assertEqual(json.loads(node_run(self, js)), {"ascii": True, "back": True}, enc)


class TestMotionCodeHygiene(unittest.TestCase):
    """Final-review minors that are about the code itself (dead helpers, a bad line join)."""
    ENGINE = SK / "engine" / "reel"

    def test_motion_qc_has_no_dead_helpers(self):
        """Final review: motion_qc.plan_fonts and motion_qc.sha1 were never called. Every public function of motion_qc
        is used by the engine (inside the module or imported elsewhere), not only defined."""
        import ast
        import re
        mod = self.ENGINE / "lib" / "motion_qc.py"
        src = mod.read_text(encoding="utf-8")
        others = "\n".join(f.read_text(encoding="utf-8") for f in self.ENGINE.rglob("*.py") if f != mod)
        public = [n.name for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]
        for fn in public:
            inside = len(re.findall(rf"(?<![\w.]){fn}\(", src)) - len(re.findall(rf"\bdef {fn}\(", src))
            outside = re.search(rf"motion_qc import[^\n]*\b{fn}\b|motion_qc\.{fn}\b", others)
            self.assertTrue(inside > 0 or outside, f"motion_qc.{fn} is never used")

    def test_no_stray_space_runs(self):
        """Final review (cosmetic): `... else         "read the reasons ..."` in motion_cli (a bad line join). No motion
        module has a run of 3+ spaces between two code tokens on a line (alignment before a # comment is fine; spaces
        inside strings are content)."""
        import tokenize
        skip = (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING)
        bad = []
        for f in sorted((self.ENGINE / "lib").glob("motion_*.py")):
            with open(f, "rb") as fh:
                toks = [t for t in tokenize.tokenize(fh.readline) if t.type not in skip]
            bad += [f"{f.name}:{b.start[0]}" for a, b in zip(toks, toks[1:])
                    if a.end[0] == b.start[0] and b.start[1] - a.end[1] >= 3 and b.type != tokenize.COMMENT]
        self.assertEqual(bad, [])


class TestArabicPaths(unittest.TestCase):
    """Live run from a client folder named in Arabic (whynot-test/بودكاست-تجربة): FreeType could not open a font file
    under it (Windows), and aerender received the project path as "???" (it reads its command line in the ANSI code
    page)."""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def font_copy(self) -> tuple[Path, Path]:
        from lib import hb_text
        font = test_font()
        if font is None or not hb_text.AVAILABLE:
            self.skipTest("no test font / HarfBuzz")
        d = self.tmp / "خطوط"
        d.mkdir()
        return font, Path(shutil.copy2(font, d / font.name))

    def test_font_in_arabic_folder_measures(self):
        from lib import hb_text
        from lib.motion_layout import fit
        font, copy = self.font_copy()
        a, b = hb_text.HBFontSpec(str(font), 48), hb_text.HBFontSpec(str(copy), 48)
        self.assertEqual((b.resolved, b.getmetrics()), (a.resolved, a.getmetrics()))
        text = "كلام اطول بكتير من الاول ومحتاج سطرين"
        self.assertEqual(hb_text.measure(text, b), hb_text.measure(text, a))
        self.assertEqual(fit(text, str(copy), 900, (120, 56), 3), fit(text, str(font), 900, (120, 56), 3))

    def test_find_font_file_in_arabic_folder(self):
        import freetype
        from lib import motion_layout, plat
        font, copy = self.font_copy()
        ps = freetype.Face(str(font)).postscript_name.decode()
        saved = (plat.font_dirs, dict(motion_layout._FONT_FILES))
        plat.font_dirs = lambda: [copy.parent]
        motion_layout._FONT_FILES.clear()
        try:
            self.assertEqual(motion_layout.find_font_file(ps), str(copy))
        finally:
            plat.font_dirs = saved[0]
            motion_layout._FONT_FILES.clear()
            motion_layout._FONT_FILES.update(saved[1])

    def fake_aerender(self, windows: bool = True):
        """aerender's process call replaced: records the command and what -project held, writes the -output file.
        windows: the platform the render believes it runs on (the ANSI command line is a Windows trait)."""
        from lib import ae_render, plat
        saved_win = plat.IS_WIN
        plat.IS_WIN = windows
        self.addCleanup(setattr, plat, "IS_WIN", saved_win)
        calls = []

        def run(cmd, check=True, timeout=None, **kw):
            proj, out = Path(cmd[cmd.index("-project") + 1]), Path(cmd[cmd.index("-output") + 1])
            calls.append({"cmd": list(cmd), "project_bytes": proj.read_bytes() if proj.exists() else None})
            out.write_bytes(b"MOV " + proj.read_bytes())
            return subprocess.CompletedProcess(cmd, 0, "", "")
        saved = (ae_render.run, ae_render.aerender_exe)
        ae_render.run, ae_render.aerender_exe = run, lambda: sys.executable
        self.addCleanup(lambda: setattr(ae_render, "run", saved[0]) or setattr(ae_render, "aerender_exe", saved[1]))
        return calls

    def project(self, folder: str) -> tuple[Path, Path]:
        d = self.tmp / folder
        (d / "render").mkdir(parents=True)
        aep = d / "EP02_MOTION.aep"
        aep.write_bytes(b"AEP")
        return aep, d / "render" / "EP02_MAIN.mov"

    def test_arabic_project_rendered_through_ascii_paths(self):
        from lib import ae_render
        calls = self.fake_aerender()
        aep, out = self.project("مشروع")
        r = ae_render.render(aep, "MAIN_EP02", out, "Best Settings", "High Quality", 0, 10)
        self.assertEqual(r["status"], "RENDERED", r)
        cmd = calls[0]["cmd"]
        staged_aep, staged_out = cmd[cmd.index("-project") + 1], cmd[cmd.index("-output") + 1]
        self.assertTrue(staged_aep.isascii() and staged_out.isascii(), cmd)
        self.assertEqual(calls[0]["project_bytes"], b"AEP")             # a copy of the real project
        self.assertEqual(out.read_bytes(), b"MOV AEP")                  # moved to the real output
        self.assertFalse(Path(staged_aep).parent.exists())              # stage removed
        self.assertEqual(r["output"], str(out))

    def test_ascii_project_not_staged(self):
        from lib import ae_render
        calls = self.fake_aerender()
        aep, out = self.project("project")
        self.assertEqual(ae_render.render(aep, "MAIN_EP02", out, "Best Settings", "High Quality")["status"], "RENDERED")
        cmd = calls[0]["cmd"]
        self.assertEqual((cmd[cmd.index("-project") + 1], cmd[cmd.index("-output") + 1]), (str(aep), str(out)))

    def test_arabic_project_direct_on_macos(self):
        """Review: the ANSI command line is Windows-only. On macOS (UTF-8 argv) an Arabic project renders in place,
        with no temp copy of the .aep and no cross-volume move of the render."""
        from lib import ae_render
        calls = self.fake_aerender(windows=False)
        aep, out = self.project("مشروع")
        self.assertEqual(ae_render.render(aep, "MAIN_EP02", out, "Best Settings", "High Quality")["status"], "RENDERED")
        cmd = calls[0]["cmd"]
        self.assertEqual((cmd[cmd.index("-project") + 1], cmd[cmd.index("-output") + 1]), (str(aep), str(out)))

    @unittest.skipUnless(sys.platform == "win32", "only Windows refuses to replace a file another program holds open")
    def test_unmovable_render_kept(self):
        """Review: when the finished render could not be moved into place (the old file open in a player, a full disk),
        the stage was deleted with it. The render stays in the stage and the result says where it is."""
        from lib import ae_render
        self.fake_aerender()
        aep, out = self.project("مشروع")
        out.write_bytes(b"OLD")
        with open(out, "rb"):
            r = ae_render.render(aep, "MAIN_EP02", out, "Best Settings", "High Quality")
        self.assertEqual(r["status"], "FAILED", r)
        kept = Path(r.get("kept") or "")
        self.assertTrue(kept.is_file(), r)
        self.addCleanup(shutil.rmtree, kept.parent, True)
        self.assertEqual(kept.read_bytes(), b"MOV AEP")
        self.assertIn(str(kept), r["msg"])
        self.assertIn("close", r["msg"])

    def test_non_ascii_temp_folder_is_named(self):
        import tempfile as tf
        from lib import ae_render
        calls = self.fake_aerender()
        aep, out = self.project("مشروع")
        temp = self.tmp / "مؤقت"
        temp.mkdir()
        saved, tf.tempdir = tf.tempdir, str(temp)
        try:
            r = ae_render.render(aep, "MAIN_EP02", out, "Best Settings", "High Quality")
        finally:
            tf.tempdir = saved
        self.assertEqual(r["status"], "FAILED", r)
        self.assertIn("ASCII", r.get("msg", ""))
        self.assertIn("TEMP", r.get("msg", ""))
        self.assertEqual(calls, [])


class TestAudioSyncDetail(unittest.TestCase):
    """Review (Minor 8): the near-miss note was tested only through an ffmpeg mix whose measured correlation (0.86) a
    future ffmpeg could move out of the band. The band rules, with fixed values."""
    def test_band(self):
        from lib.motion_qc import sync_detail
        for corr, note in ((0.79, False), (0.8, True), (0.85, True), (0.899, True), (0.9, False), (0.999, False)):
            d = sync_detail({"corr": corr, "offset_frames": 0})
            self.assertIn(f"correlation {corr}, offset 0 frames", d)
            self.assertEqual("just under 0.9" in d, note, (corr, d))

    def test_nothing_measured(self):
        from lib.motion_qc import sync_detail
        d = sync_detail({"corr": None, "offset_frames": None, "detail": "no audio to compare"})
        self.assertIn("no audio to compare", d)
        self.assertNotIn("just under", d)


if __name__ == "__main__":
    unittest.main()
