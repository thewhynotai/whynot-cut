import io, json, os, subprocess, sys, tempfile, unittest
from unittest import mock
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP))
import ownermsg as M  # noqa: E402
import history as H  # noqa: E402


class Mailbox(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.mkdtemp()

    def test_send_then_deliver_once(self):
        mid = M.send(self.state, "h1", "Please run the focused tests first.")
        self.assertEqual(M.counts(self.state, "h1"), {"pending": 1, "delivered": 0})
        got = M.deliver(self.state, "h1", "sess-1")
        self.assertEqual([m["id"] for m in got], [mid])
        self.assertEqual(M.deliver(self.state, "h1", "sess-1"), [])  # never twice
        self.assertEqual(M.counts(self.state, "h1"), {"pending": 0, "delivered": 1})
        rec = M.recent(self.state, "h1")[0]
        self.assertEqual(rec["delivered_to"], "sess-1")
        self.assertTrue(rec["delivered_at"])

    def test_accounts_are_isolated(self):
        M.send(self.state, "h1", "for h1")
        self.assertEqual(M.deliver(self.state, "h2", "s"), [])
        self.assertEqual(len(M.deliver(self.state, "h1", "s")), 1)

    def test_empty_text_is_refused(self):
        with self.assertRaises(ValueError):
            M.send(self.state, "h1", "   ")

    def test_bad_account_is_refused(self):
        with self.assertRaises(ValueError):
            M.send(self.state, "../x", "hi")

    def test_hook_output_is_claude_hook_json(self):
        M.send(self.state, "h1", "Stop after this card.")
        out = io.StringIO()
        M.hook_main(["h1"], json.dumps({"session_id": "abc", "hook_event_name": "PostToolUse"}), out, self.state)
        d = json.loads(out.getvalue())
        self.assertEqual(d["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("Stop after this card.", d["hookSpecificOutput"]["additionalContext"])
        self.assertIn("Yunus", d["hookSpecificOutput"]["additionalContext"])

    def test_hook_ignores_sub_agent_tool_calls(self):
        M.send(self.state, "h1", "for the main thread")
        out = io.StringIO()
        M.hook_main(["h1"], json.dumps({"session_id": "abc", "hook_event_name": "PostToolUse",
                                        "agent_id": "a83", "agent_type": "general-purpose"}), out, self.state)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(M.counts(self.state, "h1"), {"pending": 1, "delivered": 0})

    def test_failed_output_puts_the_message_back(self):
        M.send(self.state, "h1", "do not lose me")

        class Broken:
            def write(self, _):
                raise OSError("pipe closed")
        M.hook_main(["h1"], json.dumps({"session_id": "abc"}), Broken(), self.state)
        self.assertEqual(M.counts(self.state, "h1"), {"pending": 1, "delivered": 0})
        self.assertNotIn("delivered_at", M.recent(self.state, "h1")[0])

    def test_unreadable_message_goes_back_to_pending(self):
        os.makedirs(os.path.join(self.state, "mailbox", "h1", "pending"))
        with open(os.path.join(self.state, "mailbox", "h1", "pending", "bad.json"), "w") as f:
            f.write("{broken")
        self.assertEqual(M.deliver(self.state, "h1", "s"), [])
        self.assertEqual(M.counts(self.state, "h1")["delivered"], 0)

    def test_failed_delivery_mark_puts_the_message_back(self):
        M.send(self.state, "h1", "keep me")
        real = M._write
        def boom(path, data):
            if "delivered" in path:
                raise OSError("locked by antivirus")
            return real(path, data)
        with mock.patch.object(M, "_write", boom):
            self.assertEqual(M.deliver(self.state, "h1", "s"), [])
        self.assertEqual(M.counts(self.state, "h1"), {"pending": 1, "delivered": 0})

    def test_hook_with_nothing_prints_nothing(self):
        out = io.StringIO()
        M.hook_main(["h1"], "{}", out, self.state)
        self.assertEqual(out.getvalue(), "")

    def test_hook_never_fails_on_garbage(self):
        out = io.StringIO()
        M.hook_main(["h1"], "not json", out, self.state)  # no exception
        self.assertEqual(out.getvalue(), "")

    def test_hook_as_a_process_is_fast_and_clean(self):
        M.send(self.state, "h2", "hello")
        r = subprocess.run([sys.executable, "-X", "utf8", str(APP / "ownermsg.py"), "hook", "h2"],
                           input=json.dumps({"session_id": "z", "hook_event_name": "PostToolUse"}),
                           capture_output=True, text=True, encoding="utf-8",
                           env={**os.environ, "WNC_CC_STATE": self.state}, timeout=30)
        self.assertEqual(r.returncode, 0)
        self.assertIn("hello", json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"])


def snap(status="WORKING", task="BL-17", display="In progress", run="s1"):
    return {"accounts": [{"id": "h1", "name": "Helper 1", "status": {"code": status, "label": status, "reason": "r"},
                          "task_id": task, "session": {"id": run}}],
            "tasks": [{"id": "BL-17", "title": "Pointers", "display": display}], "alerts": []}


class History(unittest.TestCase):
    def test_first_snapshot_records_nothing(self):
        self.assertEqual(H.transitions(None, snap()), [])

    def test_only_changes_are_recorded(self):
        self.assertEqual(H.transitions(snap(), snap()), [])
        ev = H.transitions(snap(), snap(status="STALLED"))
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["kind"], "status")
        self.assertIn("Working → STALLED", ev[0]["text"].replace("WORKING", "Working"))

    def test_task_and_run_changes(self):
        ev = H.transitions(snap(), snap(task="BL-19", run="s2", display="Delivered, waiting for peer review"))
        kinds = sorted(e["kind"] for e in ev)
        self.assertEqual(kinds, ["run", "task", "task_state"])

    def test_alert_recorded_once_while_its_text_changes(self):
        a, b, c = snap(), snap(), snap()
        b["alerts"] = [{"key": "h1|status|STALLED", "level": "red", "who": "Helper 1", "text": "silent 61 min"}]
        c["alerts"] = [{"key": "h1|status|STALLED", "level": "red", "who": "Helper 1", "text": "silent 62 min"}]
        self.assertEqual([e["kind"] for e in H.transitions(a, b)], ["alert"])
        self.assertEqual(H.transitions(b, c), [])

    def test_append_and_search(self):
        p = os.path.join(tempfile.mkdtemp(), "history.jsonl")
        H.append(p, [{"at": "2026-10-22T03:00:00", "kind": "status", "account": "h1", "task": "BL-17", "text": "Helper 1: Working → Stalled"},
                     {"at": "2026-10-22T03:05:00", "kind": "task_state", "account": "h2", "task": "BL-04", "text": "BL-04 delivered"}])
        self.assertEqual([e["task"] for e in H.search(p)], ["BL-04", "BL-17"])  # newest first
        self.assertEqual([e["task"] for e in H.search(p, q="stalled")], ["BL-17"])
        self.assertEqual([e["task"] for e in H.search(p, account="h2")], ["BL-04"])


if __name__ == "__main__":
    unittest.main()
