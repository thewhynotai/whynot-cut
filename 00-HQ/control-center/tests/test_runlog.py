import json, os, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import runlog  # noqa: E402


def line(**kw):
    return json.dumps(kw) + "\n"


def asst(content, usage=None, ts="2026-10-22T01:00:00.000Z", parent=None, model="claude-opus-5-5"):
    return line(type="assistant", timestamp=ts, parent_tool_use_id=parent,
                message={"model": model, "content": content, "usage": usage or {}})


class ContextTokens(unittest.TestCase):
    def test_sums_the_three_input_kinds(self):
        u = {"input_tokens": 2, "cache_creation_input_tokens": 492, "cache_read_input_tokens": 251078, "output_tokens": 16}
        self.assertEqual(runlog.context_tokens(u), 251572)

    def test_empty_usage_is_none(self):
        self.assertIsNone(runlog.context_tokens({}))
        self.assertIsNone(runlog.context_tokens(None))


class HumanTool(unittest.TestCase):
    def test_heavy_queue_suite_names_the_label(self):
        t = runlog.human_tool("Bash", {"command": "bash C:/x/heavy.sh suite h1-BL-17 -- bash tools/test.sh"})
        self.assertEqual(t, "Full test suite 'h1-BL-17' (heavy queue)")

    def test_bash_uses_its_description(self):
        self.assertEqual(runlog.human_tool("Bash", {"command": "git switch -c h1/BL-17", "description": "Create branch"}),
                         "Create branch")

    def test_edit_shows_short_path(self):
        self.assertEqual(runlog.human_tool("Edit", {"file_path": r"D:\WNC-work\h1\engine\core\paths.py"}),
                         "Editing core/paths.py")

    def test_agent(self):
        self.assertEqual(runlog.human_tool("Task", {"description": "Review the diff"}), "Sub-agent: Review the diff")

    def test_unknown_tool_is_its_name(self):
        self.assertEqual(runlog.human_tool("Monitor", {}), "Monitor")


class Feed(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "run.jsonl")

    def write(self, text, mode="a"):
        with open(self.path, mode, encoding="utf-8") as f:
            f.write(text)

    def test_reads_incrementally_and_tracks_context_and_action(self):
        self.write(line(type="system", subtype="init", session_id="s1", model="claude-opus-5-5", cwd="D:\\w"), "w")
        f = runlog.RunFeed(self.path)
        ev = f.poll()
        self.assertEqual(f.session_id, "s1")
        self.assertEqual([e["kind"] for e in ev], ["start"])
        self.write(asst([{"type": "text", "text": "Starting BL-17."},
                         {"type": "tool_use", "name": "Read", "input": {"file_path": "D:/a/b/c.md"}}],
                        {"input_tokens": 10, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 5}))
        ev = f.poll()
        self.assertEqual([e["kind"] for e in ev], ["say", "tool"])
        self.assertEqual(f.context, 1015)
        self.assertEqual(f.context_at, "2026-10-22T01:00:00.000Z")
        self.assertEqual(f.action, "Reading b/c.md")
        self.assertEqual(f.last_text, "Starting BL-17.")
        self.assertEqual(f.poll(), [])  # nothing new = nothing repeated

    def test_partial_line_waits_for_its_end(self):
        full = line(type="system", subtype="init", session_id="s2", model="m")
        self.write(full[:20], "w")
        f = runlog.RunFeed(self.path)
        self.assertEqual(f.poll(), [])
        self.write(full[20:])
        self.assertEqual([e["kind"] for e in f.poll()], ["start"])

    def test_subagent_lines_do_not_change_the_context(self):
        self.write(asst([], {"input_tokens": 100}), "w")
        self.write(asst([{"type": "text", "text": "inner"}], {"input_tokens": 9}, parent="toolu_1"))
        f = runlog.RunFeed(self.path)
        f.poll()
        self.assertEqual(f.context, 100)

    def test_tool_wait_rate_limit_denial_and_result(self):
        self.write(asst([{"type": "tool_use", "name": "Bash", "input": {"command": "sleep 1", "description": "Wait"}}]), "w")
        self.write(line(type="tool_progress", heartbeat=True, elapsed_time_seconds=900))
        self.write(line(type="rate_limit_event", rate_limit_info={
            "status": "allowed", "resetsAt": 1792633200, "rateLimitType": "five_hour",
            "unifiedWindows": {"five_hour": {"utilization": 0.25, "resetsAt": 1792633200}}}))
        self.write(line(type="system", subtype="permission_denied", message="Permission to use Bash denied"))
        f = runlog.RunFeed(self.path)
        f.poll()
        self.assertEqual(f.tool_wait, 900)
        self.assertEqual(f.rate, {"five_hour_pct": 25, "resets_at": 1792633200, "status": "allowed"})
        self.assertEqual(f.denials, 1)
        self.write(line(type="result", is_error=False, subtype="success", result="Done.",
                        modelUsage={"claude-opus-5-5": {"contextWindow": 1000000}}))
        ev = f.poll()
        self.assertEqual(ev[-1]["kind"], "end")
        self.assertEqual(f.window, 1000000)
        self.assertTrue(f.result["ok"])
        self.assertEqual(f.tool_wait, 0)

    def test_tool_error_is_an_event(self):
        self.write(line(type="user", message={"content": [{"type": "tool_result", "is_error": True,
                                                           "content": "Exit code 1\nboom"}]}), "w")
        f = runlog.RunFeed(self.path)
        ev = f.poll()
        self.assertEqual(ev[0]["kind"], "error")
        self.assertIn("boom", ev[0]["text"])

    def test_bad_json_line_is_skipped(self):
        self.write("not json\n" + line(type="system", subtype="init", session_id="s", model="m"), "w")
        f = runlog.RunFeed(self.path)
        self.assertEqual(len(f.poll()), 1)

    def test_missing_file_is_quiet(self):
        f = runlog.RunFeed(os.path.join(self.dir, "nope.jsonl"))
        self.assertEqual(f.poll(), [])


class TranscriptTail(unittest.TestCase):
    def test_newest_main_thread_usage(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "t.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write(asst([], {"input_tokens": 5}, ts="2026-10-22T00:00:00Z"))
            f.write(asst([], {"input_tokens": 7, "cache_read_input_tokens": 488524}, ts="2026-10-22T00:26:41Z"))
            f.write(json.dumps({"type": "assistant", "isSidechain": True, "timestamp": "x",
                                "message": {"model": "m", "usage": {"input_tokens": 1}}}) + "\n")
            f.write(json.dumps({"type": "assistant", "message": {"model": "<synthetic>", "usage": {}}}) + "\n")
        got = runlog.transcript_context(p)
        self.assertEqual(got, {"tokens": 488531, "at": "2026-10-22T00:26:41Z", "model": "claude-opus-5-5"})

    def test_no_usage(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "t.jsonl")
        Path(p).write_text(line(type="user", message={"content": "hi"}), encoding="utf-8")
        self.assertIsNone(runlog.transcript_context(p))


class Windows(unittest.TestCase):
    def test_learn_and_lookup(self):
        d = tempfile.mkdtemp()
        reg = runlog.WindowRegistry(os.path.join(d, "w.json"))
        self.assertIsNone(reg.get("claude-opus-5-5"))
        reg.learn("claude-opus-5-5", 1000000, "h1 run x")
        reg2 = runlog.WindowRegistry(os.path.join(d, "w.json"))
        self.assertEqual(reg2.get("claude-opus-5-5")["size"], 1000000)
        self.assertEqual(reg2.get("claude-opus-5-5[1m]")["size"], 1000000)  # suffix-tolerant


if __name__ == "__main__":
    unittest.main()
