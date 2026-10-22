import os, sys, tempfile, unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import collect  # noqa: E402

CFG = {"state_dir": tempfile.mkdtemp(), "accounts": [], "thresholds": {"working_seconds": 180}, "routines": []}


class Agents(unittest.TestCase):
    def test_both_scan_shapes(self):
        c = collect.Collector(dict(CFG))
        for row, ctx in ((("p", {}, {}, "claude-opus-5-5", "high", 600), None),
                         (("p", {}, {}, "claude-opus-5-5", "high", 4321, 600), 4321)):
            c.slow["agents"] = [row]
            got = c.agents([], c.slow, 0)
            self.assertEqual(got[0]["age_min"], 10)
            self.assertEqual(got[0]["context_tokens"], ctx)


class RealSnapshotSmoke(unittest.TestCase):
    """Builds one snapshot from this PC's real files (read-only, no slow sources, temp state folder)."""

    def test_build(self):
        import common
        cfg = common.load_config()
        cfg["state_dir"] = tempfile.mkdtemp()
        s = collect.Collector(cfg).build()
        self.assertEqual([a["id"] for a in s["accounts"]], [a["id"] for a in cfg["accounts"]])
        for a in s["accounts"]:
            self.assertTrue(a["status"]["label_ar"])
        for t in s["tasks"]:
            self.assertTrue(t["display_ar"] and t["explain"] and t["explain_ar"], t["id"])
        for x in s["alerts"]:
            self.assertTrue(x["text_ar"], x)


class DesktopApp(unittest.TestCase):
    def test_cli_sessions_are_not_the_desktop_app(self):
        app = r"c:\program files\windowsapps\claude_3.1623.1.0_x64__pzs8sxrjxfjjc\app\claude.exe"
        cli = r"c:\users\loq\appdata\roaming\claude\claude-code\2.1.304\aed62990b91e\claude.exe"
        self.assertTrue(collect.desktop_app_running([cli, app]))
        self.assertFalse(collect.desktop_app_running([cli]))


class SlowErrors(unittest.TestCase):
    def test_failed_queue_command_is_an_error_not_an_empty_queue(self):
        c = collect.Collector(dict(CFG, accounts=[]))
        with mock.patch.object(collect.al, "_run", return_value=("", None)):
            c.refresh_slow()
        self.assertIn("queue", c.slow["errors"])


class LastRunLog(unittest.TestCase):
    def test_between_runs_the_newest_run_log_is_shown(self):
        auto = Path(tempfile.mkdtemp())
        old, new = auto / "run-20261022-010000.jsonl", auto / "run-20261022-025654.jsonl"
        old.write_text("{}\n"); new.write_text("{}\n")
        os.utime(old, (1, 1))
        self.assertEqual(collect.runlog.run_log({"state": "yielding"}, auto), str(new))
        self.assertEqual(collect.runlog.run_log({"state": "running", "log": str(old)}, auto), str(old))
        self.assertEqual(collect.runlog.run_log({}, Path(tempfile.mkdtemp())), "")


class BoardId(unittest.TestCase):
    def test_review_round_suffix(self):
        self.assertEqual(collect.board_id("S6b-r3", ["S6b", "BL-17"]), "S6b")
        self.assertEqual(collect.board_id("BL-17", ["S6b", "BL-17"]), "BL-17")
        self.assertIsNone(collect.board_id("ZZ-1", ["S6b"]))


def acct(code="WORKING", ok=True, level="ok"):
    return {"id": "h1", "name": "Helper 1", "status": {"code": code, "label": code, "label_ar": code, "reason": "why", "reason_ar": "ليه"}, "session": {"id": "s"},
            "connection": {"ok": ok, "signed_in": "x@y", "detail": "Signed in as x@y"},
            "context": {"level": level, "percent": 90, "tokens": 900000, "window": 1000000}}


def snap(**kw):
    s = {"accounts": [acct()], "tasks": [], "pc": {"ram": 50}, "routines": [], "needs_you": [],
         "sources": {"slow": {"errors": {}}}}
    s.update(kw)
    return s


class Alerts(unittest.TestCase):
    def test_quiet_when_all_is_well(self):
        self.assertEqual(collect.alerts(snap(), {}), [])

    def test_red_first_then_amber(self):
        s = snap(accounts=[acct("STALLED", level="danger")], pc={"ram": 91},
                 needs_you=["Q-009 — approve the medical text", "Q-010 — Optional: nicer icons"])
        out = collect.alerts(s, {})
        self.assertEqual(out[0]["level"], "red")
        texts = " ".join(a["text"] for a in out)
        self.assertIn("Context 90% full", texts)
        self.assertIn("RAM 91%", texts)
        self.assertIn("Q-009", texts)
        self.assertNotIn("Q-010", texts)  # optional asks are not alerts

    def test_alert_keys_are_stable_when_numbers_change(self):
        a1 = collect.alerts(snap(accounts=[acct("STALLED", level="danger")], pc={"ram": 91}), {})
        s2 = snap(accounts=[acct("STALLED", level="danger")], pc={"ram": 93})
        s2["accounts"][0]["status"]["reason"] = "silent for 1 h 02 min"
        s2["accounts"][0]["context"]["tokens"] = 910000
        a2 = collect.alerts(s2, {})
        self.assertEqual([x["key"] for x in a1], [x["key"] for x in a2])
        self.assertNotEqual([x["text"] for x in a1], [x["text"] for x in a2])

    def test_wrong_account_is_red(self):
        out = collect.alerts(snap(accounts=[acct(ok=False)]), {})
        self.assertEqual(out[0]["level"], "red")
        self.assertIn("Account check failed", out[0]["text"])


if __name__ == "__main__":
    unittest.main()
