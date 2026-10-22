import json, sys, tempfile, threading, unittest, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import server  # noqa: E402


class Identity(unittest.TestCase):
    def test_running_url_needs_our_server_not_any_listener(self):
        """A foreign program on the port must never be handed the page key."""
        cfg = {"state_dir": tempfile.mkdtemp()}
        import http.server

        class Foreign(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(200); self.end_headers(); self.wfile.write(b"hello")

            def log_message(self, *a):
                pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), Foreign)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            Path(cfg["state_dir"], "server.json").write_text(json.dumps({"port": srv.server_port, "token": "x" * 32,
                                                                          "pid": 1}))
            self.assertIsNone(server.running_url(cfg))
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()


class SlowPage(unittest.TestCase):
    def test_a_full_page_queue_keeps_the_newest_snapshot(self):
        import queue
        hub = server.Hub.__new__(server.Hub)
        q = queue.Queue(maxsize=2)
        hub.clients = {q}
        for n in range(5):
            hub.push({"n": n})
        got = [json.loads(q.get_nowait())["n"] for _ in range(q.qsize())]
        self.assertEqual(got[-1], 4)
