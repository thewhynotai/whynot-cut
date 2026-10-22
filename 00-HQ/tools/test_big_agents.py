import json, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import big_agents as ba  # noqa: E402


def line(usage=None, **kw):
    e = dict(kw)
    if usage is not None:
        e["message"] = {"usage": usage}
    return json.dumps(e).encode()


class Context(unittest.TestCase):
    def test_sums_all_input_kinds(self):
        u = {"input_tokens": 3, "cache_read_input_tokens": 200_000, "cache_creation_input_tokens": 60_000,
             "output_tokens": 999}
        self.assertEqual(ba.context_tokens(u), 260_003)
        self.assertEqual(ba.context_tokens(None), 0)

    def test_newest_usage_line_wins(self):
        lines = [line({"input_tokens": 10}), line({"input_tokens": 500_000}), line(type="user"), b"{broken"]
        self.assertEqual(ba.last_context(lines), 500_000)
        self.assertEqual(ba.last_context([line(type="user"), b"[1]"]), 0)

    def test_synthetic_zero_usage_is_skipped(self):
        zero = {"input_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "output_tokens": 0}
        self.assertEqual(ba.last_context([line({"input_tokens": 400_000}), line(zero)]), 400_000)

    def test_age_comes_from_the_newest_line_not_the_file_time(self):
        lines = [line({"input_tokens": 300_000}, timestamp="2026-10-15T00:12:47Z"), line(type="user")]
        ctx, newest, _ = ba.last_info(lines)
        self.assertEqual(ctx, 300_000)
        self.assertEqual(newest, 1792023167.0)  # a week-old agent stays old even if the app rewrote its file today
        self.assertEqual(ba.last_info([line(type="user")]), (0, None, None))

    def test_owner_and_bad_usage(self):
        lines = [line({"input_tokens": 300_000}, sessionId="parent-1"), line(["not", "a", "dict"]),
                 line({"input_tokens": None})]
        self.assertEqual(ba.last_info(lines), (300_000, None, "parent-1"))


class Main(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.dir = Path(tempfile.mkdtemp())
        self.saved = ba.FLAGS, ba.scan
        ba.scan = lambda now: [("agent-x", "local_s", 300_000, "fix round")]

    def tearDown(self):
        ba.FLAGS, ba.scan = self.saved

    def run_main(self):
        import contextlib, io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ba.main([])
        return out.getvalue()

    def test_corrupt_flag_file_still_prints(self):
        ba.FLAGS = self.dir / "flags.json"
        for bad in ("[1, 2]", '{"agent-x": 5}', "{broken"):
            ba.FLAGS.write_text(bad, encoding="utf-8")
            self.assertIn("BIG local_s 300k fix round", self.run_main())

    def test_unwritable_flag_path_still_prints(self):
        ba.FLAGS = self.dir / "missing-dir" / "flags.json"
        out = self.run_main()
        self.assertIn("BIG local_s 300k fix round", out)
        self.assertIn("flag file not written", out)

    def test_printed_once_then_quiet(self):
        ba.FLAGS = self.dir / "flags.json"
        self.assertIn("BIG", self.run_main())
        self.assertEqual(self.run_main().strip(), "none")


class Big(unittest.TestCase):
    def test_limit_finished_and_age(self):
        self.assertTrue(ba.is_big({}, 250_001, 60))
        self.assertFalse(ba.is_big({}, 250_000, 60))                 # at the limit is fine
        self.assertFalse(ba.is_big({"finished": True}, 900_000, 60))  # closed agents cost nothing more
        self.assertFalse(ba.is_big({}, 900_000, 36 * 60))             # not written for 36 min: not being continued

    def test_flag_once_per_two_hours(self):
        found = [("a", "s", 300_000, "x"), ("b", "s", 300_000, "y")]
        self.assertEqual(ba.to_flag(found, {"a": 1000.0}, 1000.0 + 3600), [found[1]])
        self.assertEqual(ba.to_flag(found, {"a": 1000.0}, 1000.0 + 7200), found)


if __name__ == "__main__":
    unittest.main()
