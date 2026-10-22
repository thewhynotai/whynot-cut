import datetime as dt, io, json, os, shutil, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import console, ownermsg  # noqa: E402

SNAP = {"accounts": [
    {"id": "h1", "name": "Helper 1", "kind": "helper", "status": {"code": "WORKING", "label": "Working", "colour": "green",
                                                                "reason": "log written"},
     "model_name": "Opus 5.5", "effort": "medium", "session": {"id": "19d70f76-9e72", "run": 5, "started": "2026-10-22 02:56:54"},
     "task_id": "BL-17", "task": {"id": "BL-17", "title": "Pointers", "display": "In progress", "progress": {"done": 2, "total": 6}},
     "action": "Full test suite 'h1-BL-17' (heavy queue)", "usage": "5-hour window 30% used",
     "context": {"tokens": 251572, "window": 1000000, "percent": 25, "level": "ok"},
     "connection": {"auto_on": True, "loop": "running", "detail": "Signed in as mayar@"}, "mailbox": {"pending": 0, "delivered": 0}},
    {"id": "h2", "name": "Helper 2", "status": {"label": "Idle", "colour": "gray"}, "task_id": None}],
    "tasks": [{"id": "BL-17", "title": "Pointers", "display": "In progress", "summary": "Keep pointers apart.",
               "steps": [{"label": "Card ready", "state": "done", "evidence": "card"}], "blocker": "", "depends": ""}]}


class Console(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.profile = self.tmp / "h1"
        (self.profile / "auto").mkdir(parents=True)
        self.log = self.tmp / "run.jsonl"
        self.log.write_text(json.dumps({"type": "assistant", "timestamp": "2026-10-22T00:10:00Z",
                                        "message": {"content": [{"type": "text", "text": "Starting BL-17."}]}}) + "\n",
                            encoding="utf-8")
        (self.profile / "auto" / "status.json").write_text(json.dumps({"state": "running", "log": str(self.log)}))
        self.cfg = {"state_dir": str(self.tmp / "state"), "refresh": {"stale_minutes": 35},
                    "accounts": [{"id": "h1", "name": "Helper 1", "email": "mayar@thewhynot.ai", "role": "Engine",
                                  "kind": "helper", "profile": str(self.profile), "work_dir": "D:\\WNC-work\\h1"}]}
        os.makedirs(self.cfg["state_dir"])
        snap = dict(SNAP, generated_at=dt.datetime.now().isoformat(timespec="seconds"))
        Path(self.cfg["state_dir"], "snapshot.json").write_text(json.dumps(snap), encoding="utf-8")
        self.out = io.StringIO()
        self.patch = mock.patch.object(sys, "stdout", self.out)
        self.patch.start()
        self.c = console.HelperConsole(self.cfg, self.cfg["accounts"][0])
        self.c.size = os.terminal_size((100, 30))
        self.c.refresh_snapshot()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_header_shows_identity_status_task_action_context(self):
        lines = self.c.header()
        joined = " ".join(l if isinstance(l, str) else " ".join(l) for l in lines)
        for want in ("HELPER 1", "mayar@thewhynot.ai", "Working", "Opus 5.5", "effort medium", "BL-17 — Pointers",
                     "2/6 steps", "Full test suite", "252K / 1M (25%)", "5-hour window 30% used", "AUTO on"):
            self.assertIn(want, joined)

    def test_plain_text_is_sent_to_this_helper_only(self):
        self.c.submit("Run the focused tests first.")
        msgs = ownermsg.recent(self.cfg["state_dir"], "h1")
        self.assertEqual([m["text"] for m in msgs], ["Run the focused tests first."])
        self.assertIn("next step", self.out.getvalue())

    def test_delivery_is_announced_once(self):
        ownermsg.send(self.cfg["state_dir"], "h1", "hello")
        ownermsg.deliver(self.cfg["state_dir"], "h1", "sess-123456")
        self.c.check_delivery()
        self.c.check_delivery()
        self.assertEqual(self.out.getvalue().count("was delivered"), 1)

    def test_stop_asks_first(self):
        with mock.patch.object(self.c, "run_cmd") as run:
            self.c.submit("/stop")
            run.assert_not_called()
            self.c.submit("/stop")
            run.assert_called_once_with(["Stop-Helper-Auto.cmd", "h1"])

    def test_chat_is_refused_while_auto_runs(self):
        with mock.patch.object(self.c, "run_cmd") as run:
            self.c.submit("/chat")
            run.assert_not_called()
        self.assertIn("/stop first", self.out.getvalue())

    def test_chat_is_refused_while_auto_is_switched_on_even_if_the_loop_is_dead(self):
        (self.profile / "auto" / "AUTO-ON").write_text("")
        with mock.patch.object(self.c, "loop_alive", return_value=False), mock.patch.object(self.c, "run_cmd") as run:
            self.c.submit("/chat")
            run.assert_not_called()
        self.assertIn("keepalive", self.out.getvalue())

    def test_feed_shows_new_events_only(self):
        self.c.follow_run(first=True)
        self.c.follow_run()
        self.assertEqual(self.out.getvalue().count("Starting BL-17."), 1)

    def test_old_snapshot_in_a_fresh_file_is_called_stale(self):
        old = dict(SNAP, generated_at=(dt.datetime.now() - dt.timedelta(minutes=50)).isoformat(timespec="seconds"))
        Path(self.cfg["state_dir"], "snapshot.json").write_text(json.dumps(old), encoding="utf-8")  # mtime = now
        self.c.snap_mtime = 0
        self.c.refresh_snapshot()
        left, right = self.c.header()[0]
        self.assertIn("monitor data 50 min old", right)

    def test_quit(self):
        self.assertEqual(self.c.submit("/quit"), "quit")


class Lock(unittest.TestCase):
    def test_second_terminal_for_same_account_is_refused(self):
        cfg = {"state_dir": tempfile.mkdtemp()}
        self.assertTrue(console.take_lock(cfg, "h1"))
        p = Path(cfg["state_dir"], "consoles", "h1.lock")
        p.write_text(f"{os.getppid()} 0")  # a live process that is not us
        self.assertFalse(console.take_lock(cfg, "h1"))
        p.write_text("999999 0")  # dead pid: stale lock is taken over
        self.assertTrue(console.take_lock(cfg, "h1"))


if __name__ == "__main__":
    unittest.main()
