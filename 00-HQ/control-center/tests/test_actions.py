import http.server, json, sys, tempfile, threading, unittest, urllib.request, urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import actions, ownermsg, server  # noqa: E402

CFG = {"state_dir": None, "accounts": [{"id": "main", "kind": "desktop", "name": "Main"},
                                      {"id": "h1", "kind": "helper", "name": "Helper 1"}]}


def cfg():
    c = dict(CFG)
    c["state_dir"] = tempfile.mkdtemp()
    return c


class Actions(unittest.TestCase):
    def test_ask_and_compact_only_queue_a_message(self):
        c = cfg()
        a = actions.Actions(c, alive=lambda h: True, run=lambda *x: self.fail("must not run anything"))
        r = a.perform("ask_status", "h1")
        self.assertTrue(r["ok"])
        r = a.perform("compact", "h1")
        self.assertTrue(r["ok"])
        texts = [m["text"] for m in ownermsg.recent(c["state_dir"], "h1")]
        self.assertTrue(any("PARTIAL report" in t for t in texts))
        self.assertTrue(any("what you are doing now" in t for t in texts))

    def test_start_is_refused_while_the_loop_runs(self):
        a = actions.Actions(cfg(), alive=lambda h: True, run=lambda *x: self.fail("must not start"))
        r = a.perform("start_auto", "h1")
        self.assertFalse(r["ok"])
        self.assertIn("already running", r["msg"])

    def test_start_runs_the_launcher_when_stopped(self):
        calls = []
        a = actions.Actions(cfg(), alive=lambda h: False, run=lambda args: calls.append(args) or (0, "started"))
        r = a.perform("start_auto", "h1")
        self.assertTrue(r["ok"])
        self.assertEqual(calls[0][-2:], ["h1", "--auto"])

    def test_double_click_is_refused(self):
        a = actions.Actions(cfg(), alive=lambda h: True, run=lambda *x: (0, ""))
        self.assertTrue(a.perform("ask_status", "h1")["ok"])
        self.assertFalse(a.perform("ask_status", "h1")["ok"])

    def test_helper_actions_need_a_helper(self):
        a = actions.Actions(cfg(), alive=lambda h: True, run=lambda *x: (0, ""))
        self.assertFalse(a.perform("compact", "main")["ok"])
        self.assertFalse(a.perform("rm_rf", "h1")["ok"])
        self.assertFalse(a.perform("ask_status", "../x")["ok"])

    def test_every_result_is_bilingual(self):
        a = actions.Actions(cfg(), alive=lambda h: True, run=lambda *x: (0, ""))
        for name, acct in (("ask_status", "h1"), ("start_auto", "h1"), ("nope", "h1")):
            r = a.perform(name, acct)
            self.assertTrue(r["msg"] and r["msg_ar"], r)


class Endpoint(unittest.TestCase):
    """POST /api/action needs the page cookie AND the per-run CSRF token AND a local origin."""

    def setUp(self):
        self.c = cfg()
        hub = server.Hub.__new__(server.Hub)
        hub.cfg, hub.snap, hub.lock, hub.clients = self.c, None, threading.Lock(), set()
        hub.hist = str(Path(self.c["state_dir"], "history.jsonl"))
        hub.csrf = "c" * 32
        hub.actions = actions.Actions(self.c, alive=lambda h: True, run=lambda *x: (0, ""))
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), None)
        port = self.srv.server_port
        self.srv.RequestHandlerClass = server.make_handler(hub, "t" * 32, port)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{port}"

    def tearDown(self):
        self.srv.shutdown()

    def post(self, headers):
        req = urllib.request.Request(self.base + "/api/action", method="POST",
                                     data=json.dumps({"action": "ask_status", "account": "h1"}).encode(),
                                     headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, None

    def test_needs_cookie_csrf_and_local_origin(self):
        ok = {"Cookie": "wnc_cc=" + "t" * 32, "X-CC-CSRF": "c" * 32, "Origin": self.base}
        self.assertEqual(self.post({k: v for k, v in ok.items() if k != "Cookie"})[0], 401)
        self.assertEqual(self.post({**ok, "X-CC-CSRF": "wrong"})[0], 403)
        self.assertEqual(self.post({**ok, "Origin": "http://evil.example"})[0], 403)
        code, body = self.post(ok)
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])


if __name__ == "__main__":
    unittest.main()
