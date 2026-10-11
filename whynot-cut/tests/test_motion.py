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


if __name__ == "__main__":
    unittest.main()
