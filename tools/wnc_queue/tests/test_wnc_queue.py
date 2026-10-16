"""wnc-queue tests: validation, stop conditions, timeout, recovery, STOP, cancel, single instance, heavy.sh wrapping,
logs, and end to end through the CLI with a runner killed mid-job. Run with the system Python (stdlib only):
    python -B -W error::ResourceWarning -m unittest discover -s tools/wnc_queue/tests -v
The shared suite loads this file too (whynot-cut/tests/test_wnc_queue.py, under the G79 sandbox)."""
import json
import os
import subprocess
import sys
import threading
import time
import unittest
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))

from wnc_queue import core, procs, runner, task  # noqa: E402
from wnc_queue.core import JobError, Paths  # noqa: E402

ENTRY = TOOLS / "wnc-queue.py"
TEMP_BASE = Path("D:/ClaudeData/Temp/wncq-tests") if core.IS_WIN and Path("D:/ClaudeData").is_dir() \
    else core.REPO / ".wncq-tests"
PY = sys.executable


def remove_tree(p: Path) -> None:
    core.remove_tree(p)          # the tool's own link-safe remover (COORDINATION rule 15), tested below


def pid_alive(pid: int) -> bool:
    if core.IS_WIN:
        import ctypes
        k = ctypes.WinDLL("kernel32")
        h = k.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return code.value == 259                        # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def wait_for(cond, what, timeout=60.0):
    end = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > end:
            raise AssertionError(f"not within {timeout}s: {what}")
        time.sleep(0.1)


class Base(unittest.TestCase):
    def setUp(self):
        TEMP_BASE.mkdir(parents=True, exist_ok=True)
        self.dir = TEMP_BASE / uuid.uuid4().hex[:10]
        self.dir.mkdir()
        self.addCleanup(remove_tree, self.dir)
        self.paths = Paths(self.dir / "home").ensure()
        self.cfg = core.load_config(self.paths)
        self.cfg.update(poll_s=0.1, sample_s=0.3, temp_root=str(self.dir / "tmp"), python=PY,
                        allowed_roots=[str(TEMP_BASE)], heavy_sh=str(self.fake_heavy()))

    def fake_heavy(self) -> Path:
        """Stands in for heavy.sh: records its arguments, then runs the command like the real one ("$@")."""
        f = self.dir / "heavy.sh"
        f.write_text('printf "%s\\n" "$@" > "$(dirname "$0")/heavy-args.txt"\n'
                     'echo "[heavy] $1 \'$2\' started" >&2\nshift 3\n"$@"; rc=$?\n'
                     'echo "[heavy] done rc=$rc" >&2\nexit $rc\n', encoding="utf-8", newline="\n")
        return f

    def script(self, name: str, body: str) -> str:
        f = self.dir / name
        f.write_text(body, encoding="utf-8")
        return str(f)

    def job(self, argv, **kw) -> dict:
        j = {"argv": argv, "cwd": str(self.dir), "heavy": "none", "owner": "test"}
        j.update(kw)
        return core.add_job(self.paths, j, self.cfg)

    def run_runner(self, timeout=120) -> int:
        r = runner.Runner(self.paths, self.cfg)
        out = {}
        t = threading.Thread(target=lambda: out.setdefault("rc", r.run()), daemon=True)
        t.start()
        t.join(timeout)
        self.assertFalse(t.is_alive(), "runner did not exit")
        return out["rc"]

    def done(self, jid) -> dict:
        d = core.read_json(self.paths.done / f"{jid}.json")
        self.assertIsNotNone(d, f"no done record for {jid}")
        return d


class ValidateTests(Base):
    def bad(self, msg_part, **kw):
        j = {"argv": ["python", "-V"], "cwd": str(self.dir)}
        j.update(kw)
        with self.assertRaises(JobError) as cm:
            core.validate(j, self.cfg)
        self.assertIn(msg_part, str(cm.exception))

    def test_allowlist(self):
        for exe in ("cmd", "powershell", "curl", "npx", "C:/Windows/System32/cmd.exe", "wscript"):
            self.bad("not allowlisted", argv=[exe, "/c", "echo"])
        for exe in ("python", "bash", "node", "npm", "gh", "git", "ffmpeg", "ffprobe", "reel"):
            self.assertEqual(core.validate({"argv": [exe, "x.py"], "cwd": str(self.dir)}, self.cfg)["argv"][0], exe)

    def test_no_ai(self):
        self.bad("AI work", argv=["node", "C:/Users/x/claude", "-p", "hi"])
        self.bad("AI work", argv=["npm", "exec", "claude.exe"])

    def test_no_shell_strings(self):
        self.bad("shell strings", argv=["bash", "-c", "echo hi"])
        self.bad("shell strings", argv=["bash", "-ec", "x"])
        self.bad("shell strings", argv=["sh", "-lc", "x"])
        core.validate({"argv": ["bash", "-e", "tools/test.sh", "-c", "x"], "cwd": str(self.dir)}, self.cfg)

    def test_cwd_and_forbidden_areas(self):
        self.bad("outside the repo", cwd="C:\\Windows")
        self.bad("absolute", cwd="relative/dir")
        self.bad("forbidden area", argv=["python", "x.py", "D:\\WhyNot Clients\\Dr X\\raw.mp4"])
        self.bad("forbidden area", argv=["python", "x.py", "C:/Users/LOQ/AppData/Roaming/Adobe/Premiere Pro/x"])
        self.bad("forbidden area", env={"X": "C:\\Users\\LOQ\\Documents\\Adobe\\Premiere Pro\\25.0"})
        self.bad("forbidden area", argv=["python", "x.py", "/Users/me/Library/Preferences/Adobe/x"])

    def test_network_allowlist(self):
        self.bad("not on the network allowlist", argv=["git", "clone", "https://evil.example.com/x.git"])
        core.validate({"argv": ["git", "clone", "https://github.com/thewhynotai/x.git"], "cwd": str(self.dir)},
                      self.cfg)
        core.validate({"argv": ["python", "dl.py", "https://objects.githubusercontent.com/a"],
                       "cwd": str(self.dir)}, self.cfg)

    def test_fields(self):
        self.bad("bad id", id="../x")
        self.bad("heavy class", heavy="turbo")
        self.bad("stop.mode", stop={"mode": "forever"})
        self.bad("stop.max", stop={"mode": "until_fail", "max": 0})
        self.bad("stop.regex", stop={"mode": "until_match"})
        self.bad("pass_regex", pass_regex="(")
        self.bad("priority", priority=1000)
        self.bad("timeout_s", timeout_s=0)
        self.bad("argv", argv="python -V")
        self.bad("argv", argv=[])
        self.bad("env", env={"1BAD": "x"})
        self.assertEqual(core.parse_duration("30m"), 1800)
        self.assertEqual(core.parse_duration("2h"), 7200)
        self.assertEqual(core.parse_duration(90), 90)
        with self.assertRaises(JobError):
            core.parse_duration("soon")

    def test_duplicate_id_and_order(self):
        a = self.job(["python", "-V"], id="a", priority=0)
        self.job(["python", "-V"], id="b", priority=5)
        self.job(["python", "-V"], id="c", priority=0)
        with self.assertRaises(JobError):
            self.job(["python", "-V"], id="a")
        self.assertEqual([j["id"] for j in core.queued_jobs(self.paths)], ["b", "a", "c"])
        self.assertEqual(a["attempts"], 0)


class SafetyReviewTests(Base):
    """The bypasses an independent review found (2026-10-15), each closed."""

    def bad(self, msg_part, argv):
        with self.assertRaises(JobError) as cm:
            core.validate({"argv": argv, "cwd": str(self.dir)}, self.cfg)
        self.assertIn(msg_part, str(cm.exception))

    def test_bash_options_before_c(self):
        self.bad("shell strings", ["bash", "-o", "errexit", "-c", "x"])
        self.bad("shell strings", ["bash", "-O", "extglob", "--norc", "-c", "x"])
        self.bad("shell strings", ["bash", "+e", "-xc", "x"])
        core.validate({"argv": ["bash", "-O", "extglob", "run.sh", "-c"], "cwd": str(self.dir)}, self.cfg)

    def test_ai_by_package_or_path(self):
        self.bad("AI work", ["npm", "exec", "--", "@anthropic-ai/claude-code", "-p", "hi"])
        self.bad("AI work", ["node", "C:/x/node_modules/@anthropic-ai/claude-code/cli.js"])
        core.validate({"argv": ["git", "log", "--author=noreply@anthropic.com"], "cwd": str(self.dir)}, self.cfg)

    def test_recursive_deletes(self):
        for argv in (["bash", "x.sh", "rm -rf build"], ["git", "x", "rm", "-fr", "x"],
                     ["node", "x.js", "Remove-Item -Path x -Recurse"], ["python", "x.py", "rmdir /S /Q x"]):
            self.bad("recursive deletes", argv)

    def test_batch_files(self):
        with self.assertRaises(JobError):
            core.check_batch_args("C:/nodejs/npm.cmd", ["run", 'a b" & echo INJ & "c'])
        with self.assertRaises(JobError):
            core.check_batch_args("C:/x/reel.CMD", ["%PATH:~0,3%"])
        core.check_batch_args("C:/nodejs/npm.cmd", ["run", "build", "--", "--x=1"])
        core.check_batch_args("C:/Python313/python.exe", ['a"b', "%x%"])        # a real exe gets argv exactly
        fake = self.dir / "python.bat"
        fake.write_text("@echo hi\n", encoding="utf-8")
        with self.assertRaises(JobError) as cm:
            core.resolve_exe(str(fake), self.dir, self.cfg)
        self.assertIn("batch file", str(cm.exception))

    def test_d_claude_root(self):
        if not Path("D:/Claude").is_dir():
            self.skipTest("no D:\\Claude here")
        core.validate({"argv": ["python", "-V"], "cwd": "D:\\Claude"}, self.cfg)

    def test_remove_tree_never_follows_a_junction(self):
        if not core.IS_WIN:
            self.skipTest("junctions are Windows only")
        outside = self.dir / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("precious", encoding="utf-8")
        tree = self.dir / "tree" / "sub"
        tree.mkdir(parents=True)
        (tree / "f.txt").write_text("x", encoding="utf-8")
        link = self.dir / "tree" / "link"
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        core.remove_tree(self.dir / "tree")
        self.assertFalse((self.dir / "tree").exists())
        self.assertEqual((outside / "keep.txt").read_text(encoding="utf-8"), "precious")


class DecideTests(unittest.TestCase):
    def d(self, stop, results):
        its = [{"n": i + 1, "passed": r, "rc": 0 if r else 1, "outcome": "exited"} for i, r in enumerate(results)]
        return runner.decide({"stop": stop, "iterations": its, "max_wait_s": 1})

    def test_modes(self):
        self.assertIsNone(self.d({"mode": "exit"}, []))
        self.assertEqual(self.d({"mode": "exit"}, [True])[0], "passed")
        self.assertEqual(self.d({"mode": "exit"}, [False])[0], "failed")
        self.assertIsNone(self.d({"mode": "repeat", "times": 3}, [True, False]))
        self.assertEqual(self.d({"mode": "repeat", "times": 3}, [True, False, True])[0], "failed")
        self.assertEqual(self.d({"mode": "repeat", "times": 2}, [True, True]), ("passed", "2/2 runs passed"))
        self.assertIsNone(self.d({"mode": "until_fail", "max": 3}, [True, True]))
        st, summary = self.d({"mode": "until_fail", "max": 20}, [True, True, False])
        self.assertEqual(st, "failed")
        self.assertIn("run 3 of 20 failed after 2 passes", summary)
        self.assertEqual(self.d({"mode": "until_fail", "max": 2}, [True, True])[0], "passed")
        self.assertIsNone(self.d({"mode": "until_streak", "k": 2, "max": 5}, [False, True]))
        self.assertEqual(self.d({"mode": "until_streak", "k": 2, "max": 5}, [False, True, True])[0], "passed")
        self.assertEqual(self.d({"mode": "until_streak", "k": 3, "max": 4}, [True, False, True, True])[0], "failed")

    def test_terminal_outcomes(self):
        base = {"stop": {"mode": "until_fail", "max": 5}, "max_wait_s": 9}
        for outcome, status in (("cancelled", "cancelled"), ("stopped", "stopped"), ("wait_timeout", "timeout"),
                                ("error", "error")):
            v = runner.decide(dict(base, iterations=[{"n": 1, "passed": False, "outcome": outcome}]))
            self.assertEqual(v[0], status)
        v = runner.decide(dict(base, iterations=[{"n": 1, "passed": False, "outcome": "timed_out", "run_s": 2}]))
        self.assertEqual(v[0], "timeout")


class RunnerTests(Base):
    def test_exit_pass_fail_and_record(self):
        ok = self.job(["python", "-c", "import sys; x = bytearray(60 * 2**20); print('hello'); sys.exit(0)"])
        bad = self.job(["python", "-c", "import sys; print('Traceback: boom'); sys.exit(3)"])
        self.assertEqual(self.run_runner(), 0)
        d = self.done(ok["id"])
        self.assertEqual((d["status"], d["passed"], d["exit_code"], d["iterations_run"]), ("passed", True, 0, 1))
        for k in ("summary", "log", "queued_at", "started_at", "finished_at", "wait_s", "run_s", "peak"):
            self.assertIn(k, d)
        self.assertIn("hello", Path(d["log"]).read_text(encoding="utf-8"))
        if core.IS_WIN:
            self.assertGreater(d["peak"]["ram_mb"], 50)        # the 60 MB bytearray, seen through the Job Object
            self.assertIsNotNone(d["peak"]["sys_ram_pct"])
        b = self.done(bad["id"])
        self.assertEqual((b["status"], b["exit_code"]), ("failed", 3))
        self.assertIn("boom", b["summary"])
        self.assertEqual(list(self.paths.running.iterdir()), [])
        self.assertEqual(list(self.paths.queue.iterdir()), [])
        self.assertEqual(core.read_json(self.paths.runner_json)["state"], "exited")

    def counter_script(self, fail_on: tuple) -> str:
        c = self.dir / "count.txt"
        return self.script("count.py", f"""import sys, pathlib
c = pathlib.Path(r"{c}")
n = int(c.read_text()) + 1 if c.exists() else 1
c.write_text(str(n))
print("run", n)
sys.exit(1 if n in {fail_on!r} else 0)
""")

    def test_repeat(self):
        j = self.job(["python", self.counter_script(())], stop={"mode": "repeat", "times": 3})
        self.run_runner()
        d = self.done(j["id"])
        self.assertEqual((d["status"], d["iterations_run"], d["passes"]), ("passed", 3, 3))

    def test_until_fail_stops_at_first_failure(self):
        j = self.job(["python", self.counter_script((3,))], stop={"mode": "until_fail", "max": 10})
        self.run_runner()
        d = self.done(j["id"])
        self.assertEqual((d["status"], d["iterations_run"], d["passes"]), ("failed", 3, 2))
        self.assertIn("run 3 of 10 failed", d["summary"])

    def test_until_streak(self):
        j = self.job(["python", self.counter_script((1, 2))], stop={"mode": "until_streak", "k": 2, "max": 8})
        self.run_runner()
        d = self.done(j["id"])
        self.assertEqual((d["status"], d["iterations_run"]), ("passed", 4))

    def test_until_match_stops_the_process(self):
        s = self.script("ready.py", "import time\nprint('warming', flush=True)\nprint('Server READY on 8080', "
                                    "flush=True)\ntime.sleep(120)\n")
        j = self.job(["python", s], stop={"mode": "until_match", "regex": r"READY on \d+"}, timeout_s=100)
        t0 = time.monotonic()
        self.run_runner()
        self.assertLess(time.monotonic() - t0, 60)
        d = self.done(j["id"])
        self.assertEqual(d["status"], "passed")
        self.assertIn("READY on 8080", d["summary"])
        j2 = self.job(["python", "-c", "print('nothing')"], stop={"mode": "until_match", "regex": "READY"})
        self.run_runner()
        self.assertEqual(self.done(j2["id"])["status"], "failed")

    def test_pass_and_fail_regex(self):
        a = self.job(["python", "-c", "print('Ran 5 tests'); print('OK')"], pass_regex=r"^OK$")
        b = self.job(["python", "-c", "print('Ran 0 tests')"], pass_regex=r"^OK$")
        c = self.job(["python", "-c", "print('WARNING: flaky thing')"], fail_regex="flaky")
        self.run_runner()
        self.assertEqual(self.done(a["id"])["status"], "passed")
        self.assertEqual(self.done(b["id"])["status"], "failed")
        dc = self.done(c["id"])
        self.assertEqual(dc["status"], "failed")
        self.assertIn("flaky", dc["summary"])

    def test_timeout_kills_the_whole_tree(self):
        pidf = self.dir / "grandchild.pid"
        s = self.script("tree.py", f"""import subprocess, sys, time, pathlib
p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
pathlib.Path(r"{pidf}").write_text(str(p.pid))
print("spawned", p.pid, flush=True)
time.sleep(120)
""")
        j = self.job(["python", s], timeout_s=3)
        t0 = time.monotonic()
        self.run_runner()
        self.assertLess(time.monotonic() - t0, 40)
        d = self.done(j["id"])
        self.assertEqual(d["status"], "timeout")
        self.assertTrue(d["iterations"][0]["timed_out"])
        gpid = int(pidf.read_text())
        wait_for(lambda: not pid_alive(gpid), "the grandchild is killed with the tree", 15)

    def test_stop_kill_switch(self):
        s = self.script("long.py", "import time\nprint('long', flush=True)\ntime.sleep(120)\n")
        j1 = self.job(["python", s], id="long1")
        r = runner.Runner(self.paths, dict(self.cfg, max_parallel=1))
        th = threading.Thread(target=r.run, daemon=True)
        th.start()
        wait_for(lambda: (self.paths.running / "long1.json").exists() and "long" in
                 (self.paths.log("long1").read_text(encoding="utf-8") if self.paths.log("long1").exists() else ""),
                 "job 1 is running")
        j2 = self.job(["python", "-V"], id="queued2")
        self.paths.stop.write_text("STOP", encoding="utf-8")
        th.join(40)
        self.assertFalse(th.is_alive())
        self.assertEqual(self.done(j1["id"])["status"], "stopped")
        self.assertTrue((self.paths.queue / f"{j2['id']}.json").exists(), "queued jobs stay queued under STOP")
        self.assertEqual(self.run_runner(), 0)                         # STOP present: exits at once, runs nothing
        self.assertTrue((self.paths.queue / f"{j2['id']}.json").exists())
        os.unlink(self.paths.stop)
        self.run_runner()
        self.assertEqual(self.done(j2["id"])["status"], "passed")

    def test_cancel_queued_and_running(self):
        q = self.job(["python", "-V"], id="q1")
        self.assertIn("cancelled", core.cancel_job(self.paths, "q1"))
        self.assertEqual(self.done(q["id"])["status"], "cancelled")
        s = self.script("long.py", "import time\nprint('long', flush=True)\ntime.sleep(120)\n")
        self.job(["python", s], id="r1", stop={"mode": "repeat", "times": 5})
        r = runner.Runner(self.paths, self.cfg)
        th = threading.Thread(target=r.run, daemon=True)
        th.start()
        wait_for(lambda: (core.read_json(self.paths.running / "r1.json") or {}).get("current"), "r1 runs")
        self.assertIn("cancel requested", core.cancel_job(self.paths, "r1"))
        th.join(40)
        self.assertFalse(th.is_alive())
        d = self.done("r1")
        self.assertEqual((d["status"], d["iterations_run"]), ("cancelled", 1))
        with self.assertRaises(JobError):
            core.cancel_job(self.paths, "nope")

    def plant_running(self, jid, attempts, iterations):
        j = core.validate({"id": jid, "argv": ["python", "-c", "print('resumed')"], "cwd": str(self.dir),
                           "heavy": "none", "stop": {"mode": "repeat", "times": 3}}, self.cfg)
        j["attempts"] = attempts
        j["iterations"] = [{"n": i + 1, "rc": 0, "passed": True, "outcome": "exited"} for i in range(iterations)]
        j["current"] = {"n": iterations + 1}
        core.write_json(self.paths.running / f"{jid}.json", j)
        core.write_json(self.paths.spec(jid), {"argv": []})

    def test_recovery_requeues_and_resumes(self):
        self.plant_running("stranded1", attempts=1, iterations=1)
        self.plant_running("stranded2", attempts=3, iterations=0)
        self.run_runner()
        d = self.done("stranded1")
        self.assertEqual((d["status"], d["iterations_run"], d["attempts"]), ("passed", 3, 2))
        self.assertTrue(any("recovered" in e for e in d["events"]))
        self.assertEqual(self.done("stranded2")["status"], "stranded")
        self.assertEqual(list(self.paths.running.iterdir()), [])

    def test_single_instance(self):
        held = runner.acquire_lock(self.paths.lock)
        self.addCleanup(runner.release_lock, held)
        self.job(["python", "-V"], id="waits")
        t0 = time.monotonic()
        self.assertEqual(runner.Runner(self.paths, self.cfg).run(), 3)
        self.assertLess(time.monotonic() - t0, 10)
        self.assertTrue(runner.lock_is_held(self.paths))
        self.assertTrue((self.paths.queue / "waits.json").exists(), "a refused runner touches nothing")

    def test_heavy_wrapping_and_exact_argv(self):
        tricky = ['q"uote', "a b", "/d/not/converted", "--x=/bar", "test_*.py", "it's", "عربي"]
        j = self.job(["python", "-c", "import json, sys; print('ARGV=' + json.dumps(sys.argv[1:]))", *tricky],
                     heavy="suite", id="wrapped")
        self.run_runner()
        d = self.done("wrapped")
        self.assertEqual(d["status"], "passed", d)
        args = (self.dir / "heavy-args.txt").read_text(encoding="utf-8").split("\n")
        self.assertEqual(args[:4], ["suite", f"wnc-queue:{j['id']}", "--", PY.replace("\\", "/")])
        log = Path(d["log"]).read_text(encoding="utf-8")
        line = next(x for x in log.splitlines() if x.startswith("ARGV="))
        self.assertEqual(json.loads(line[5:]), tricky)
        self.assertIn("[heavy] suite", log)

    def test_heavy_missing_is_an_error(self):
        self.cfg["heavy_sh"] = str(self.dir / "nope.sh")
        j = self.job(["python", "-V"], heavy="cpu")
        self.run_runner()
        d = self.done(j["id"])
        self.assertEqual(d["status"], "error")
        self.assertIn("heavy.sh not found", d["summary"])

    def test_refused_at_claim(self):
        core.write_json(self.paths.queue / "evil.json", {"id": "evil", "argv": ["cmd", "/c", "del x"],
                                                         "cwd": str(self.dir)})
        self.run_runner()
        d = self.done("evil")
        self.assertEqual(d["status"], "error")
        self.assertIn("refused", d["summary"])

    def test_temp_env_and_job_env(self):
        j = self.job(["python", "-c", "import os; print('T=' + os.environ['TEMP']); print('V=' + os.environ['WNCV'])"],
                     env={"WNCV": "x y"})
        self.run_runner()
        log = Path(self.done(j["id"])["log"]).read_text(encoding="utf-8")
        self.assertIn(f"T={Path(self.cfg['temp_root']) / j['id']}", log)
        self.assertIn("V=x y", log)

    def test_no_wnc_variable_reaches_a_job(self):
        """The product reserves WNC_* (its wrapper tests assert none reaches the engine): the runner's marker is
        JOB_QUEUE_ID, and a WNC_* the runner itself inherited is dropped."""
        from unittest import mock
        j = self.job(["python", "-c", "import os; print('K=' + ','.join(sorted(k for k in os.environ "
                      "if k.upper().startswith('WNC_')))); print('Q=' + os.environ['JOB_QUEUE_ID'])"])
        with mock.patch.dict(os.environ, {"WNC_RUNNER_SIDE": "1"}):
            self.run_runner()
        log = Path(self.done(j["id"])["log"]).read_text(encoding="utf-8")
        self.assertRegex(log, r"(?m)^K=\r?$")
        self.assertIn(f"Q={j['id']}", log)

    def test_log_rotation_and_prune(self):
        self.cfg["max_log_mb"] = 0.05                                 # ~52 KB cap
        j = self.job(["python", "-c", "print(('x' * 99 + '\\n') * 3000)"])
        self.run_runner()
        log = self.paths.log(j["id"])
        self.assertTrue(log.with_name(log.name + ".1").exists())
        self.assertLess(log.stat().st_size, 60 * 1024)
        old = self.paths.done / "ancient.json"
        old.write_text("{}", encoding="utf-8")
        old_log = self.paths.logs / "ancient.log"
        old_log.write_text("x", encoding="utf-8")
        t = time.time() - 40 * 86400
        for f in (old, old_log):
            os.utime(f, (t, t))
        runner.Runner(self.paths, self.cfg).prune()
        self.assertFalse(old.exists())
        self.assertFalse(old_log.exists())
        self.assertTrue((self.paths.done / f"{j['id']}.json").exists())

    def test_task_xml(self):
        xml = task.task_xml(self.paths, python_w="C:\\Python313\\pythonw.exe", user="PC\\me")
        root = ET.fromstring(xml.split("?>", 1)[1])
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        get = lambda path: root.find(path, ns).text  # noqa: E731
        self.assertEqual(get("t:Settings/t:MultipleInstancesPolicy"), "IgnoreNew")
        self.assertEqual(get("t:Settings/t:ExecutionTimeLimit"), "PT0S")
        self.assertEqual(get("t:Settings/t:DisallowStartIfOnBatteries"), "false")
        self.assertEqual(get("t:Settings/t:StopIfGoingOnBatteries"), "false")
        self.assertEqual(get("t:Settings/t:Priority"), "5")
        self.assertEqual(get("t:Triggers/t:TimeTrigger/t:Repetition/t:Interval"), "PT10M")
        self.assertEqual(get("t:Triggers/t:LogonTrigger/t:UserId"), "PC\\me")
        self.assertEqual(get("t:Principals/t:Principal/t:RunLevel"), "LeastPrivilege")
        self.assertEqual(get("t:Actions/t:Exec/t:Command"), "C:\\Python313\\pythonw.exe")
        self.assertIn(f'run --home "{self.paths.home}"', get("t:Actions/t:Exec/t:Arguments"))
        self.assertIsNone(ET.fromstring(task.task_xml(self.paths, logon=False).split("?>", 1)[1])
                          .find("t:Triggers/t:LogonTrigger", ns))


class RunnerReviewTests(Base):
    """Runner behaviour the independent review flagged (2026-10-15), each fixed and pinned here."""

    def test_until_match_when_the_job_exits_at_once(self):
        j = self.job(["python", "-c", "print('READY now')"], stop={"mode": "until_match", "regex": "READY"})
        self.run_runner()
        d = self.done(j["id"])
        self.assertEqual(d["status"], "passed", d["summary"])

    def test_carriage_return_progress_is_seen_live(self):
        # The LAST output is a bare-\r line and then silence: it must match at once (not wait for more output).
        s = self.script("prog.py", "import sys, time\nfor p in (10, 50, 100):\n    sys.stdout.write(f'dl {p}%\\r')\n"
                                   "    sys.stdout.flush()\n    time.sleep(0.3)\ntime.sleep(120)\n")
        j = self.job(["python", s], stop={"mode": "until_match", "regex": r"^dl 100%$"}, timeout_s=100)
        t0 = time.monotonic()
        self.run_runner()
        self.assertLess(time.monotonic() - t0, 60)
        self.assertEqual(self.done(j["id"])["status"], "passed")

    def test_rotation_while_the_log_is_held_open(self):
        self.cfg["max_log_mb"] = 0.05
        log = self.paths.log("held")
        log.write_text("", encoding="utf-8")
        with open(log, encoding="utf-8") as reader:                  # a tail / antivirus holding the file
            j = self.job(["python", "-c", "print(('y' * 99 + '\\n') * 3000); print('LAST LINE')"], id="held")
            self.run_runner()
            reader.read()
        d = self.done(j["id"])
        self.assertEqual(d["status"], "passed", d["summary"])
        self.assertIn("LAST LINE", log.read_text(encoding="utf-8"))
        if core.IS_WIN:                                    # proves the rename-failed path ran (the file was held)
            self.assertFalse(log.with_name(log.name + ".1").exists())

    def test_orphan_holding_the_pipe_is_killed(self):
        pidf = self.dir / "orphan.pid"
        s = self.script("orphan.py", f"""import subprocess, sys, pathlib
p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
pathlib.Path(r"{pidf}").write_text(str(p.pid))
print("parent exits", flush=True)
""")
        j = self.job(["python", s])
        t0 = time.monotonic()
        self.run_runner()
        self.assertLess(time.monotonic() - t0, 40)
        d = self.done(j["id"])
        self.assertEqual(d["status"], "passed")
        self.assertTrue(d["iterations"][0].get("orphans_killed"))
        wait_for(lambda: not pid_alive(int(pidf.read_text())), "the orphan is killed", 15)

    def test_job_env_never_reaches_heavy_sh(self):
        pydir = str(Path(PY).parent)
        j = self.job(["python", "-c", "import os; print('P=' + os.environ['PATH'])"], heavy="suite",
                     env={"PATH": pydir, "BASH_ENV": str(self.dir / "evil.sh")})
        (self.dir / "evil.sh").write_text("echo EVIL-RAN\n", encoding="utf-8", newline="\n")
        self.run_runner()
        d = self.done(j["id"])
        self.assertEqual(d["status"], "passed", d["summary"])
        self.assertTrue((self.dir / "heavy-args.txt").exists(), "heavy.sh still found dirname/printf")
        log = Path(d["log"]).read_text(encoding="utf-8")
        self.assertIn(f"P={pydir}", log)
        self.assertNotIn("EVIL-RAN", log)

    def waiting_heavy(self) -> str:
        f = self.dir / "busy-heavy.sh"
        f.write_text("sleep 600\n", encoding="utf-8", newline="\n")      # never gets a slot
        return str(f)

    def test_max_wait_and_stop_while_waiting_for_a_slot(self):
        self.cfg["heavy_sh"] = self.waiting_heavy()
        j = self.job(["python", "-V"], heavy="cpu", max_wait_s=2)
        t0 = time.monotonic()
        self.run_runner()
        self.assertLess(time.monotonic() - t0, 40)
        d = self.done(j["id"])
        self.assertEqual(d["status"], "timeout")
        self.assertIn("no heavy.sh slot", d["summary"])
        j2 = self.job(["python", "-V"], heavy="cpu", id="waits-stop")
        r = runner.Runner(self.paths, self.cfg)
        th = threading.Thread(target=r.run, daemon=True)
        th.start()
        wait_for(lambda: (core.read_json(self.paths.running / "waits-stop.json") or {}).get("current"), "waiting")
        self.paths.stop.write_text("STOP", encoding="utf-8")
        th.join(40)
        self.assertFalse(th.is_alive())
        self.assertEqual(self.done(j2["id"])["status"], "stopped")

    def test_job_temp_is_removed(self):
        j = self.job(["python", "-c", "import os, pathlib; (pathlib.Path(os.environ['TEMP']) / 'x').write_text('1')"])
        self.run_runner()
        self.assertEqual(self.done(j["id"])["status"], "passed")
        self.assertFalse((Path(self.cfg["temp_root"]) / j["id"]).exists())

    def test_prune_never_follows_a_junction(self):
        """A guard, not a proof of cleverness: prune deletes plain files only and must never start descending."""
        if not core.IS_WIN:
            self.skipTest("junctions are Windows only")
        target = self.dir / "elsewhere"
        target.mkdir()
        old = target / "old.log"
        old.write_text("keep", encoding="utf-8")
        t = time.time() - 90 * 86400
        os.utime(old, (t, t))
        link = self.paths.logs / "linked"
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=True)
        runner.Runner(self.paths, self.cfg).prune()
        self.assertTrue(old.exists())
        os.rmdir(link)                                  # the link only

    def test_a_job_queued_while_the_runner_exits_is_served(self):
        late = {}

        class Late(runner.Runner):
            def _serve(inner):
                super()._serve()
                if not late:                            # `add` lands after the empty-queue check, lock still held
                    late["job"] = self.job(["python", "-V"], id="late")
        self.assertEqual(Late(self.paths, self.cfg).run(), 0)
        self.assertEqual(self.done("late")["status"], "passed")

    def test_main_loop_survives_an_error(self):
        calls = []

        class Flaky(runner.Runner):
            def claim(inner):
                calls.append(1)
                if len(calls) == 1:
                    raise PermissionError("antivirus holds the file")
                return super().claim()
        j = self.job(["python", "-V"])
        self.assertEqual(Flaky(self.paths, self.cfg).run(), 0)
        self.assertEqual(self.done(j["id"])["status"], "passed")
        self.assertIn("main loop error 1", self.paths.runner_log.read_text(encoding="utf-8"))

    def test_leftovers_are_cleaned(self):
        core.write_json(self.paths.queue / "half.json.cancelling", {"id": "half", "argv": ["python", "-V"]})
        (self.paths.running / "gone.cancel").write_text("x", encoding="utf-8")
        self.run_runner()
        self.assertEqual(self.done("half")["status"], "cancelled")
        self.assertEqual(list(self.paths.running.iterdir()), [])
        self.assertEqual([f.name for f in self.paths.queue.iterdir()], [])

    def test_slot_kept_fresh(self):
        locks = self.dir / "locks"
        for name, label in (("heavy-1.d", "wnc-queue:mine"), ("heavy-2.d", "someone-else")):
            (locks / name).mkdir(parents=True)
            (locks / name / "owner").write_text(f"pid=1\nlabel={label}\n", encoding="utf-8")
            t = time.time() - 4 * 3600
            os.utime(locks / name, (t, t))
        self.cfg["locks_dir"] = str(locks)
        runner.Worker(runner.Runner(self.paths, self.cfg), {"id": "mine"}).keep_slot_fresh()
        self.assertGreater((locks / "heavy-1.d").stat().st_mtime, time.time() - 60)
        self.assertLess((locks / "heavy-2.d").stat().st_mtime, time.time() - 3 * 3600)


class SecondReviewTests(Base):
    """What the second independent review found (2026-10-15), each fixed and pinned here."""

    def bad(self, msg_part, argv):
        with self.assertRaises(JobError) as cm:
            core.validate({"argv": argv, "cwd": str(self.dir)}, self.cfg)
        self.assertIn(msg_part, str(cm.exception))

    def junction(self, link: Path, target: Path) -> None:
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_remove_tree_given_a_junction_removes_only_the_link(self):
        if not core.IS_WIN:
            self.skipTest("junctions are Windows only")
        outside = self.dir / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("precious", encoding="utf-8")
        root = self.dir / "tmproot"
        self.junction(root, outside)                    # a job replaced its own TEMP with a junction
        core.remove_tree(root)
        self.assertFalse(os.path.lexists(root), "the link itself is removed")
        self.assertEqual((outside / "keep.txt").read_text(encoding="utf-8"), "precious")
        nested = self.dir / "t2" / "a" / "b"            # and a junction deep inside, next to real files
        nested.mkdir(parents=True)
        (nested / "f.txt").write_text("x", encoding="utf-8")
        self.junction(nested / "j", outside)
        core.remove_tree(self.dir / "t2")
        self.assertFalse((self.dir / "t2").exists())
        self.assertTrue((outside / "keep.txt").exists())

    def test_runner_finish_never_empties_a_junctioned_temp(self):
        if not core.IS_WIN:
            self.skipTest("junctions are Windows only")
        outside = self.dir / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("precious", encoding="utf-8")
        s = self.script("swap.py", f"""import os, subprocess
t = os.environ["TEMP"]
os.rmdir(t)
subprocess.run(["cmd", "/c", "mklink", "/J", t, r"{outside}"], check=True, capture_output=True)
""")
        j = self.job(["python", s])
        self.run_runner()
        self.assertEqual(self.done(j["id"])["status"], "passed")
        self.assertTrue((outside / "keep.txt").exists())
        self.assertFalse(os.path.lexists(Path(self.cfg["temp_root"]) / j["id"]))

    def test_bash_value_options_and_double_dash(self):
        self.bad("shell strings", ["bash", "--rcfile", "x.sh", "-c", "echo hi"])
        self.bad("shell strings", ["bash", "--init-file", "x.sh", "-c", "echo hi"])
        core.validate({"argv": ["bash", "--", "run.sh", "-c"], "cwd": str(self.dir)}, self.cfg)

    def test_split_recursive_delete_flags(self):
        for argv in (["bash", "x.sh", "rm -r -f build"], ["bash", "x.sh", "rm --recursive --force x"],
                     ["git", "rm", "x", "-R"], ["python", "x.py", "rd /s /q x"], ["node", "x.js", "rmdir x /S"]):
            self.bad("recursive deletes", argv)
        core.validate({"argv": ["bash", "x.sh", "rm -f one.txt"], "cwd": str(self.dir)}, self.cfg)

    def test_a_batch_file_cannot_stand_in_by_bare_name(self):
        bindir = self.dir / "bin"
        bindir.mkdir()
        (bindir / "gh.bat").write_text("@echo fake\n", encoding="utf-8")
        (bindir / "npm.cmd").write_text("@echo npm\n", encoding="utf-8")
        if core.IS_WIN:
            with self.assertRaises(JobError) as cm:
                core.resolve_exe("gh", self.dir, self.cfg, str(bindir))
            self.assertIn("batch file", str(cm.exception))
            self.assertTrue(core.resolve_exe("npm", self.dir, self.cfg, str(bindir)).lower().endswith("npm.cmd"))
        cwd = os.getcwd()
        os.chdir(bindir)                                # a gh.bat in the current folder is never found
        self.addCleanup(os.chdir, cwd)
        self.assertIsNone(core.search_path("gh", str(self.dir)))

    def test_unreadable_queue_file_is_refused_and_the_runner_exits(self):
        bad = self.paths.queue / "hand-made.json"
        bad.write_text("{not json", encoding="utf-8")
        t = time.time() - 60
        os.utime(bad, (t, t))
        t0 = time.monotonic()
        self.assertEqual(self.run_runner(timeout=60), 0)
        self.assertLess(time.monotonic() - t0, 30)
        d = self.done("hand-made")
        self.assertEqual(d["status"], "error")
        self.assertIn("{not json", d["raw"])
        self.assertEqual(list(self.paths.queue.iterdir()), [])

    def test_a_crashing_runner_leaves_jobs_for_recovery(self):
        pidf, marker = self.dir / "c.pid", self.dir / "ran-once"
        s = self.script("once.py", f"""import os, pathlib, time
m = pathlib.Path(r"{marker}")
if not m.exists():
    m.write_text("1")
    pathlib.Path(r"{pidf}").write_text(str(os.getpid()))
    time.sleep(120)
""")
        j = self.job(["python", s], id="crash-victim")

        class Crashing(runner.Runner):
            MAX_LOOP_ERRORS, LOOP_ERROR_SLEEP_S = 3, 0.1

            def claim(inner):
                if inner.workers and pidf.exists():
                    raise RuntimeError("runner bug")
                return super().claim()
        out = {}
        th = threading.Thread(target=lambda: out.setdefault("rc", Crashing(self.paths, self.cfg).run()), daemon=True)
        th.start()
        th.join(60)
        self.assertFalse(th.is_alive())
        self.assertEqual(out["rc"], 1)
        wait_for(lambda: not pid_alive(int(pidf.read_text())), "the job tree was killed", 15)
        self.assertTrue((self.paths.running / "crash-victim.json").exists(), "left for recovery, not `stopped`")
        self.assertFalse((self.paths.done / "crash-victim.json").exists())
        self.run_runner()                                # the next 10-minute tick
        d = self.done(j["id"])
        self.assertEqual((d["status"], d["attempts"]), ("passed", 2), d["summary"])
        self.assertTrue(any("recovered" in e for e in d["events"]))

    def test_job_log_write_never_raises(self):
        from unittest import mock
        path = self.dir / "x.log"
        lg = runner.JobLog(path, 2 ** 20)
        lg.f.close()                                     # e.g. a reopen that failed earlier
        with mock.patch("builtins.open", side_effect=OSError("locked")):
            lg.write("lost line\n")
            lg.write("lost too\n")
        self.assertEqual(lg.lost, 2)
        lg.write("kept\n")
        lg.close()
        self.assertIn("kept", path.read_text(encoding="utf-8"))

    def test_an_error_in_the_poll_loop_kills_the_tree(self):
        from unittest import mock
        pidf = self.dir / "p.pid"
        s = self.script("sleepy.py", f"import os, pathlib, time\npathlib.Path(r'{pidf}').write_text(str(os.getpid()))"
                                     "\ntime.sleep(120)\n")
        def ram_pct():                                   # fails once the child is surely running
            if pidf.exists():
                raise RuntimeError("sampler bug")
            return 50.0
        j = self.job(["python", s])
        with mock.patch.object(procs, "system_ram_pct", side_effect=ram_pct):
            self.run_runner(timeout=60)
        d = self.done(j["id"])
        self.assertEqual(d["status"], "error")
        self.assertIn("sampler bug", d["summary"])
        self.assertTrue(pidf.exists())
        wait_for(lambda: not pid_alive(int(pidf.read_text())), "the job tree was killed", 15)

    def test_recovery_removes_the_temp_of_a_stranded_job(self):
        j = core.validate({"id": "strand-t", "argv": ["python", "-V"], "cwd": str(self.dir), "heavy": "none"},
                          self.cfg)
        j["attempts"] = 3
        core.write_json(self.paths.running / "strand-t.json", j)
        temp = Path(self.cfg["temp_root"]) / "strand-t"
        temp.mkdir(parents=True)
        (temp / "left.txt").write_text("x", encoding="utf-8")
        self.run_runner()
        self.assertEqual(self.done("strand-t")["status"], "stranded")
        self.assertFalse(temp.exists())

    def test_a_running_worker_keeps_its_slot_fresh(self):
        locks = self.dir / "locks"
        locks.mkdir()
        slot = locks / "heavy-9.d"
        heavy = self.dir / "slot-heavy.sh"
        lk = str(slot).replace("\\", "/")
        heavy.write_text(f'mkdir -p "{lk}"\nprintf "pid=%s\\nlabel=%s\\n" $$ "$2" > "{lk}/owner"\n'
                         f'touch -d "4 hours ago" "{lk}"\nshift 3\n"$@"\n', encoding="utf-8", newline="\n")
        self.cfg.update(heavy_sh=str(heavy), locks_dir=str(locks), slot_refresh_s=0.5)
        j = self.job(["python", "-c", "import time; time.sleep(3)"], heavy="cpu")
        self.run_runner()
        self.assertEqual(self.done(j["id"])["status"], "passed")
        self.assertGreater(slot.stat().st_mtime, time.time() - 60, "the worker touched its 4 h old slot")


class ThirdReviewTests(Base):
    """What the third independent review found (2026-10-15), each fixed and pinned here."""

    def bad(self, msg_part, argv):
        with self.assertRaises(JobError) as cm:
            core.validate({"argv": argv, "cwd": str(self.dir)}, self.cfg)
        self.assertIn(msg_part, str(cm.exception))

    def test_a_held_log_never_stops_the_queue(self):
        self.cfg["max_logs_total_mb"] = 0
        old = self.paths.logs / "old.log"
        old.write_text("x" * 1000, encoding="utf-8")
        t = time.time() - 3600
        os.utime(old, (t, t))
        j = self.job(["python", "-V"])
        with open(old, encoding="utf-8"):                     # someone tails it: unlink fails on Windows
            self.assertEqual(self.run_runner(), 0)
        self.assertEqual(self.done(j["id"])["status"], "passed")

    def test_bash_option_clusters_cannot_hide_c(self):
        self.bad("shell strings", ["bash", "-eo", "pipefail", "-c", "echo hi"])
        self.bad("shell strings", ["bash", "-xO", "extglob", "-c", "echo hi"])
        self.bad("needs a value", ["bash", "-o", "-c", "echo hi"])
        core.validate({"argv": ["bash", "-eo", "pipefail", "run.sh", "-c"], "cwd": str(self.dir)}, self.cfg)

    def test_more_recursive_deletes(self):
        for argv in (["python", "x.py", "del /s /q build"], ["node", "x.js", "robocopy a b /MIR"],
                     ["node", "x.js", "robocopy a b /e /move"]):
            self.bad("recursive deletes", argv)
        core.validate({"argv": ["node", "x.js", "robocopy a b /e"], "cwd": str(self.dir)}, self.cfg)

    def test_no_new_run_after_stop(self):
        s = self.script("stopper.py", f"import pathlib\npathlib.Path(r'{self.paths.stop}').write_text('STOP')\n")
        j = self.job(["python", s], stop={"mode": "repeat", "times": 3})
        self.run_runner()
        d = self.done(j["id"])
        self.assertEqual((d["status"], d["iterations_run"]), ("stopped", 1), d["summary"])

    def test_remove_tree_removes_read_only_files(self):
        import stat as st_
        tree = self.dir / "ro" / "pack"
        tree.mkdir(parents=True)
        f = tree / "x.pack"
        f.write_text("x", encoding="utf-8")
        os.chmod(f, st_.S_IREAD)
        core.remove_tree(self.dir / "ro")
        self.assertFalse((self.dir / "ro").exists())

    def test_an_entry_that_cannot_be_read_never_keeps_the_runner_alive(self):
        (self.paths.queue / "folder.json").mkdir()
        t0 = time.monotonic()
        self.assertEqual(self.run_runner(timeout=60), 0)
        self.assertLess(time.monotonic() - t0, 20)
        self.assertTrue((self.paths.queue / "folder.json").is_dir(), "left alone, never deleted")

    def test_a_briefly_unreadable_valid_job_is_not_refused(self):
        r = runner.Runner(self.paths, self.cfg)
        good = self.paths.queue / "good.json"
        core.write_json(good, {"argv": ["python", "-V"], "cwd": str(self.dir)})
        bad = self.paths.queue / "bad.json"
        bad.write_text("{oops", encoding="utf-8")
        t = time.time() - 60
        for f in (good, bad):
            os.utime(f, (t, t))
        for _ in range(r.BAD_PASSES - 1):
            r.reject_unreadable(good)
            r.reject_unreadable(bad)
            time.sleep(1.05)                                   # passes count at most once a second
        self.assertTrue(bad.exists(), "not refused before BAD_PASSES passes")
        r.reject_unreadable(good)
        r.reject_unreadable(bad)
        self.assertTrue(good.exists(), "valid JSON is never refused")
        self.assertFalse(bad.exists())
        self.assertEqual(self.done("bad")["status"], "error")

    def test_a_duplicate_id_never_overwrites_a_record(self):
        first = self.job(["python", "-V"], id="dup")
        self.run_runner()
        original = self.done("dup")
        core.write_json(self.paths.queue / "dup.json", dict(first, argv=["python", "-c", "print('again')"]))
        self.run_runner()
        self.assertEqual(self.done("dup")["finished_at"], original["finished_at"])
        refused = [core.read_json(f) for f in self.paths.done.glob("dup.refused-*.json")]
        self.assertEqual(len(refused), 1)
        self.assertIn("already running or done", refused[0]["summary"])

    def test_a_crlf_split_across_reads_is_one_line_end(self):
        # bytes, not text: Windows text-mode stdout would turn the \n into \r\n (a real empty line)
        s = self.script("split.py", "import sys, time\nsys.stdout.buffer.write(b'abc\\r'); sys.stdout.flush()\n"
                                    "time.sleep(0.5)\nsys.stdout.buffer.write(b'\\nxyz\\n'); sys.stdout.flush()\n")
        j = self.job(["python", s])
        self.run_runner()
        d = self.done(j["id"])
        self.assertEqual(d["status"], "passed")
        self.assertEqual([t for t in d["tail"] if not t.startswith(runner.NOISE)], ["abc", "xyz"])
        self.assertIn(b"abc\r\nxyz\n", Path(d["log"]).read_bytes())

    def test_status_says_attention_when_work_waits_with_no_runner(self):
        from unittest import mock
        from wnc_queue import cli
        import contextlib
        import io
        p = mock.patch.object(task, "installed", return_value=True)
        p.start()
        self.addCleanup(p.stop)

        def status():
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli.main(["--home", str(self.paths.home), "status"])
            return buf.getvalue().splitlines()
        j = core.validate({"id": "orphaned", "argv": ["python", "-V"], "cwd": str(self.dir)}, self.cfg)
        core.write_json(self.paths.running / "orphaned.json", j)
        out = status()
        self.assertTrue(out[0].startswith("ATTENTION"), out)
        self.assertTrue(any("no runner" in line for line in out), out)
        os.unlink(self.paths.running / "orphaned.json")
        core.write_json(self.paths.runner_json, {"state": "crashed", "heartbeat": "earlier"})
        self.assertTrue(any("crashed" in line for line in status()))
        core.write_json(self.paths.runner_json, {"state": "exited"})
        stuck = dict(j, id="stuck", queued_ns=time.time_ns() - 3600 * 10 ** 9)
        core.write_json(self.paths.queue / "stuck.json", stuck)
        out = status()
        self.assertTrue(out[0].startswith("ATTENTION") and any("queued 60 min" in line for line in out), out)
        os.unlink(self.paths.queue / "stuck.json")
        self.record_cancelled()
        self.assertTrue(status()[0].startswith("OK"), "a cancelled job is a choice, not a problem")

    def record_cancelled(self):
        core.write_json(self.paths.done / "c.json", core.done_record({"id": "c"}, "cancelled", "cancelled", log=None))


class FourthReviewTests(Base):
    """What the fourth independent review found (2026-10-15), each fixed and pinned here."""

    def test_a_recover_leftover_never_refuses_the_recovered_job(self):
        j = core.validate({"id": "left", "argv": ["python", "-V"], "cwd": str(self.dir), "heavy": "none"}, self.cfg)
        core.write_json(self.paths.queue / "left.json", j)          # recover() re-queued it ...
        core.write_json(self.paths.running / "left.json", j)        # ... but could not remove the old copy
        self.run_runner()
        self.assertEqual(self.done("left")["status"], "passed")
        self.assertEqual(list(self.paths.done.glob("left.refused-*.json")), [])

    def test_a_cancel_racing_claim_writes_no_false_refusal(self):
        from unittest import mock
        self.job(["python", "-V"], id="a1")
        core.write_json(self.paths.done / "a1.json", core.done_record({"id": "a1"}, "cancelled", "cancelled", log=None))
        real = os.replace

        def gone(src, dst):                                           # cancel took the file first
            if ".dup-" in str(dst):
                raise FileNotFoundError(src)
            return real(src, dst)
        with mock.patch.object(runner.os, "replace", side_effect=gone):
            self.assertIsNone(runner.Runner(self.paths, self.cfg).claim())
        self.assertEqual(list(self.paths.done.glob("a1.refused-*.json")), [])

    def test_a_skipped_unopenable_file_is_retried_later(self):
        r = runner.Runner(self.paths, self.cfg)
        core.write_json(self.paths.queue / "b1.json", {"argv": ["python", "-V"], "cwd": str(self.dir)})
        r._ignored["b1.json"] = time.monotonic() + 60
        self.assertFalse(r.claimable())
        r._ignored["b1.json"] = time.monotonic() - 1                  # its skip time is over
        self.assertTrue(r.claimable())
        self.assertEqual(r.ignored_now(), set())

    def test_unreadable_passes_count_once_per_second(self):
        r = runner.Runner(self.paths, self.cfg)
        bad = self.paths.queue / "bad.json"
        bad.write_text("{oops", encoding="utf-8")
        t = time.time() - 60
        os.utime(bad, (t, t))
        for _ in range(10):                                            # many claim() calls in one poll
            r.reject_unreadable(bad)
        self.assertTrue(bad.exists())

    def test_a_bom_job_file_is_read(self):
        f = self.paths.queue / "bom.json"
        f.write_bytes(b"\xef\xbb\xbf" + json.dumps({"id": "bom", "argv": ["python", "-V"],
                                                   "cwd": str(self.dir), "heavy": "none"}).encode("utf-8"))
        self.run_runner()
        self.assertEqual(self.done("bom")["status"], "passed")

    def test_compact_cmd_switches(self):
        for argv in (["python", "x.py", "rd/s/q x"], ["python", "x.py", "del /q/s x"],
                     ["node", "x.js", "robocopy a b /e /mov"]):
            with self.assertRaises(JobError):
                core.validate({"argv": argv, "cwd": str(self.dir)}, self.cfg)

    def test_status_sees_hand_written_and_unreadable_queue_files(self):
        from unittest import mock
        from wnc_queue import cli
        import contextlib
        import io
        p = mock.patch.object(task, "installed", return_value=True)
        p.start()
        self.addCleanup(p.stop)
        hand = self.paths.queue / "hand.json"
        core.write_json(hand, {"argv": ["python", "-V"], "cwd": str(self.dir)})   # no queued_ns
        t = time.time() - 3600
        os.utime(hand, (t, t))
        (self.paths.queue / "junk.json").write_text("{x", encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.main(["--home", str(self.paths.home), "status"])
        out = buf.getvalue()
        self.assertTrue(out.startswith("ATTENTION"), out)
        self.assertIn("queued 60 min", out)
        self.assertIn("not valid JSON: junk.json", out)


class FifthReviewTests(Base):
    """What the fifth independent review found (2026-10-15), each fixed and pinned here."""

    def test_ids_that_look_like_runner_files_are_refused(self):
        for jid in ("login.spec", "b.dup-1", "x.json", "a.cancel", "r.refused", "q.started", "x.log", "c.cancelling"):
            with self.assertRaises(JobError, msg=jid):
                core.validate({"id": jid, "argv": ["python", "-V"], "cwd": str(self.dir)}, self.cfg)
        core.validate({"id": "ok-id.v2", "argv": ["python", "-V"], "cwd": str(self.dir)}, self.cfg)

    def test_the_sweep_never_loses_what_a_leftover_meant(self):
        r = runner.Runner(self.paths, self.cfg)
        run = self.paths.running
        core.write_json(run / "d1.json.dup-77", {"id": "d1", "argv": ["python", "-V"]})   # refusal never written
        (run / "u1.json.refused").write_text("{garbage", encoding="utf-8")                 # record never written
        self.job(["python", "-V"], id="c1")                                                 # re-queued by recover()
        (run / "c1.cancel").write_text("x", encoding="utf-8")                              # the cancel that met it
        (run / "notes.txt").write_text("keep", encoding="utf-8")                           # not ours: untouched
        r.recover()
        self.assertEqual(len(list(self.paths.done.glob("d1*.json"))), 1)
        self.assertIn("already running or done", core.read_json(next(self.paths.done.glob("d1*.json")))["summary"])
        self.assertIn("{garbage", self.done("u1")["raw"])
        self.assertEqual(self.done("c1")["status"], "cancelled")
        self.assertFalse((self.paths.queue / "c1.json").exists())
        self.assertEqual(sorted(f.name for f in run.iterdir()), ["notes.txt"])

    def test_two_refusals_never_share_a_name(self):
        r = runner.Runner(self.paths, self.cfg)
        core.write_json(self.paths.done / "z.json", {"id": "z"})
        a = r.refusal_path("z")
        core.write_json(a, {"id": "z"})
        b = r.refusal_path("z")
        self.assertNotEqual(a, b)

    def test_bad_json_is_not_retried_for_seconds(self):
        f = self.dir / "bad.json"
        f.write_text("{nope", encoding="utf-8")
        t0 = time.monotonic()
        self.assertIsNone(core.read_json(f))
        self.assertLess(time.monotonic() - t0, 0.5)

    def test_a_bom_config_is_read(self):
        self.paths.config.write_bytes(b"\xef\xbb\xbf" + json.dumps({"max_parallel": 1}).encode("utf-8"))
        self.assertEqual(core.load_config(self.paths)["max_parallel"], 1)

    def test_delete_words_inside_paths_are_not_refused(self):
        for argv in (["python", "D:/x/del/s.py"], ["python", "tools/rd/s.py"],
                     ["ffmpeg", "-i", "D:/clips/Casa del Mar/s.mp4"], ["python", "-m", "pytest", "-k", "not del",
                                                                        "tests/s/test_x.py"],
                     ["npm", "run", "del", "--", "--path", "a/s"], ["python", "-m", "pytest", "-s"]):
            core.validate({"argv": argv, "cwd": str(self.dir)}, self.cfg)


class SixthReviewTests(Base):
    """What the sixth independent review found (2026-10-15), each fixed and pinned here."""

    def test_a_hand_written_reserved_name_never_touches_running_files(self):
        spec = self.paths.running / "x.spec.json"
        core.write_json(spec, {"argv": ["the", "real", "spec"]})               # job x waits for its slot
        core.write_json(self.paths.queue / "x.spec.json", {"id": "x.spec", "argv": ["python", "-V"]})
        self.assertIsNone(runner.Runner(self.paths, self.cfg).claim())
        self.assertEqual(core.read_json(spec)["argv"], ["the", "real", "spec"])
        recs = [core.read_json(f) for f in self.paths.done.glob("x.spec.refused-*.json")]
        self.assertEqual(len(recs), 1)
        self.assertIn("not a valid job id", recs[0]["summary"])

    def test_a_held_refusal_is_recorded_once(self):
        core.write_json(self.paths.done / "d.refused-20261015-000000-123-1.json", {"id": "d", "status": "error"})
        core.write_json(self.paths.running / "d.json.dup-123", {"id": "d", "argv": ["python", "-V"]})
        runner.Runner(self.paths, self.cfg).recover()
        self.assertEqual(len(list(self.paths.done.glob("d*.json"))), 1)
        self.assertEqual(list(self.paths.running.iterdir()), [])

    def test_an_unreadable_refusal_is_never_lost_or_doubled(self):
        core.write_json(self.paths.done / "u.json", {"id": "u", "status": "passed"})   # an older job with that id
        (self.paths.running / "u.json.refused").write_text("{garbage", encoding="utf-8")
        runner.Runner(self.paths, self.cfg).recover()
        recs = [core.read_json(f) for f in self.paths.done.glob("u.refused-*.json")]
        self.assertEqual([r["raw"] for r in recs], ["{garbage"])
        (self.paths.running / "u.json.refused").write_text("{garbage", encoding="utf-8")  # crash after the record
        runner.Runner(self.paths, self.cfg).recover()
        self.assertEqual(len(list(self.paths.done.glob("u.refused-*.json"))), 1)

    def test_argv_length_is_capped(self):
        with self.assertRaises(JobError) as cm:
            core.validate({"argv": ["python", "x" * 40000], "cwd": str(self.dir)}, self.cfg)
        self.assertIn("longer than", str(cm.exception))

    def test_robocopy_by_full_path_or_inside_code(self):
        for argv in (["node", "x.js", "C:/Windows/System32/robocopy.exe a b /MIR"],
                     ["python", "-c", "import os; os.system('robocopy a b /MIR')"],
                     ["python", "-c", "import os; os.system('rd /s /q x')"]):
            with self.assertRaises(JobError, msg=argv):
                core.validate({"argv": argv, "cwd": str(self.dir)}, self.cfg)

    def test_crafted_argv_is_checked_fast(self):
        for text in ("rd " * 10000, "del " * 8000, "rm -" + "r" * 32000):
            t0 = time.monotonic()
            core.is_destructive(text[:core.MAX_ARGV_CHARS])
            self.assertLess(time.monotonic() - t0, 1.0, text[:10])

    def test_ids_trailing_dot_refused_but_dotted_names_fine(self):
        with self.assertRaises(JobError):
            core.validate({"id": "t.", "argv": ["python", "-V"], "cwd": str(self.dir)}, self.cfg)
        for jid in ("app.logger", "data.jsonl", "auth.login-flow"):
            core.validate({"id": jid, "argv": ["python", "-V"], "cwd": str(self.dir)}, self.cfg)
        self.assertEqual(runner._log_owner("app.logger.log"), "app.logger")
        self.assertEqual(runner._log_owner("app.logger.log.1"), "app.logger")
        self.assertIsNone(runner._log_owner("notes.txt"))


class SeventhReviewTests(Base):
    """P2 findings of the seventh independent review (2026-10-15) that were cheap and close to rule 15."""

    def bad(self, argv):
        with self.assertRaises(JobError, msg=argv):
            core.validate({"argv": argv, "cwd": str(self.dir)}, self.cfg)

    def test_a_glued_rd_after_an_earlier_delete_word(self):
        self.bad(["python", "-c", "import os; os.system('del /q a.tmp & rd/s/q build')"])
        self.bad(["python", "-c", "import os; del x; os.system('rd/s/q y')"])

    def test_patterns_cross_newlines(self):
        self.bad(["python", "-c", "import os\nos.system('robocopy a b\\nc /MIR')".replace("\\n", "\n")])
        self.bad(["python", "-c", "x = 'remove-item a\n -Recurse'"])

    def test_runner_is_a_reserved_id(self):
        for jid in ("runner", "Runner"):
            with self.assertRaises(JobError):
                core.validate({"id": jid, "argv": ["python", "-V"], "cwd": str(self.dir)}, self.cfg)
        core.validate({"id": "runner-2", "argv": ["python", "-V"], "cwd": str(self.dir)}, self.cfg)

    def test_a_duplicate_in_another_case_never_takes_a_running_job(self):
        r = runner.Runner(self.paths, self.cfg)
        live = core.validate({"id": "Foo", "argv": ["python", "-V"], "cwd": str(self.dir)}, self.cfg)
        core.write_json(self.paths.running / "Foo.json", live)
        r.workers["Foo"] = object()                       # Foo is running
        core.write_json(self.paths.queue / "foo.json", {"id": "foo", "argv": ["python", "-V"], "cwd": str(self.dir)})
        self.assertIsNone(r.claim())
        self.assertEqual(core.read_json(self.paths.running / "Foo.json")["id"], "Foo")
        self.assertEqual(len(list(self.paths.done.glob("foo.refused-*.json"))), 1)


class GlanceTests(Base):
    """COORDINATION rule 17: a resuming session reads only a few lines, so the result comes first everywhere."""

    def setUp(self):
        super().setUp()
        from unittest import mock
        p = mock.patch.object(task, "installed", return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def record(self, jid, status, summary, owner="adobe", runs=None):
        runs = runs if runs is not None else [{"n": 1, "rc": 0 if status == "passed" else 1,
                                                "passed": status == "passed", "run_s": 75.0, "wait_s": 2.0}]
        rec = core.done_record({"id": jid, "owner": owner, "title": f"{jid} title", "iterations": runs}, status,
                               summary, log="x.log", peak={"ram_mb": 830}, tail=[f"tail line {i}" for i in range(20)])
        core.write_json(self.paths.done / f"{jid}.json", rec)
        return rec

    def cli(self, *args):
        import contextlib
        import io
        from wnc_queue import cli
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli.main(["--home", str(self.paths.home), *args])
        return rc, buf.getvalue().splitlines()

    def test_done_record_puts_the_result_first(self):
        rec = self.record("hunt", "failed", "run 7 of 20 failed after 6 passes: rc 1: AssertionError")
        self.assertEqual(list(rec)[:4], ["headline", "status", "passed", "summary"])
        self.assertEqual(list(rec)[-2:], ["iterations", "job"])
        self.assertTrue(rec["headline"].startswith("FAILED: run 7 of 20 failed"), rec["headline"])
        self.assertIn("[hunt, adobe; ran 1m15s]", rec["headline"])
        on_disk = json.loads((self.paths.done / "hunt.json").read_text(encoding="utf-8"))
        self.assertEqual(list(on_disk)[0], "headline")

    def test_result_passed_is_short_and_failed_shows_the_tail(self):
        self.record("ok", "passed", "20/20 runs passed (no failure found)")
        rc, out = self.cli("result", "ok")
        self.assertEqual(rc, 0)
        self.assertTrue(out[0].startswith("PASSED: 20/20 runs passed"), out)
        self.assertLessEqual(len(out), 4, out)                         # no output tail for a pass
        self.record("bad", "failed", "rc 1: boom")
        rc, out = self.cli("result", "bad")
        self.assertEqual(rc, 1)
        self.assertTrue(out[0].startswith("FAILED: rc 1: boom"), out)
        self.assertIn("  | tail line 19", out)
        self.assertNotIn("  | tail line 4", out)                       # last 15 only
        self.assertIn("  | tail line 19", self.cli("result", "ok", "--tail", "3")[1])

    def test_status_verdict_first_and_lists_only_what_needs_a_look(self):
        self.record("good1", "passed", "passed")
        self.record("good2", "passed", "passed", owner="guide")
        rc, out = self.cli("status")
        self.assertEqual(rc, 0)
        self.assertTrue(out[0].startswith("OK: 0 running, 0 queued, last 24 h 2 passed / 0 failed"), out)
        self.assertEqual(len(out), 2, out)                             # verdict + one details line
        self.record("hunt", "failed", "run 3 of 20 failed after 2 passes: rc 1")
        rc, out = self.cli("status")
        self.assertTrue(out[0].startswith("ATTENTION:"), out)
        self.assertTrue(any(line.lstrip().startswith("FAILED") and "hunt" in line for line in out), out)
        self.assertLessEqual(len(out), 5, out)
        rc, out = self.cli("status", "--owner", "guide")
        self.assertTrue(out[0].startswith("OK:") and "1 passed / 0 failed" in out[0], out)
        st = json.loads("\n".join(self.cli("status", "--json")[1]))
        self.assertEqual((st["verdict"], st["failed_recent"][0]["id"]), ("ATTENTION", "hunt"))

    def test_arabic_output_never_crashes_a_cp1252_console(self):
        self.record("ar", "failed", "rc 1: خطأ في الترجمة")
        env = dict(os.environ, PYTHONIOENCODING="cp1252")
        r = subprocess.run([PY, "-B", str(ENTRY), "--home", str(self.paths.home), "result", "ar"], env=env,
                           capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertTrue(r.stdout.startswith(b"FAILED: rc 1: "), r.stdout)

    def test_status_flags_stop(self):
        self.paths.stop.write_text("x", encoding="utf-8")
        out = self.cli("status")[1]
        self.assertTrue(out[0].startswith("ATTENTION:"), out)
        self.assertIn("STOP is set", out[1])

    def test_list_filters_by_owner(self):
        self.record("a1", "passed", "passed", owner="adobe")
        self.record("g1", "passed", "passed", owner="guide")
        out = "\n".join(self.cli("list", "--owner", "guide")[1])
        self.assertIn("g1", out)
        self.assertNotIn("a1", out)


class PressureTests(Base):
    """A verdict reached while system RAM peaked at >= 85% during the run says so in its headline: a timing failure
    under memory pressure is a machine verdict until it is re-checked, not a code verdict."""

    def setUp(self):
        super().setUp()
        from unittest import mock
        p = mock.patch.object(task, "installed", return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def rec(self, status, rams, passed=None, **kw):
        passed = passed if passed is not None else [status == "passed"] * len(rams)
        runs = [{"n": i + 1, "rc": 0 if ok else 1, "passed": ok, "run_s": 10.0, "wait_s": 0.0,
                 "peak_sys_ram_pct": r} for i, (r, ok) in enumerate(zip(rams, passed))]
        return core.done_record({"id": "j1", "owner": "g3", "iterations": runs}, status, "rc 1: 2 timing tests",
                                log="x.log", peak={"sys_ram_pct": max((r for r in rams if r is not None),
                                                                      default=None)}, **kw)

    def test_failure_under_pressure_says_so_first(self):
        r = self.rec("failed", [89])
        self.assertIs(r["pressure"], True)
        self.assertEqual(r["pressure_ram_peak_pct"], 89)
        self.assertTrue(r["headline"].startswith(
            "FAILED (under memory pressure: RAM peak 89%; re-check before treating it as a code verdict): rc 1"),
            r["headline"])
        self.assertEqual(list(r)[:4], ["headline", "status", "passed", "summary"])

    def test_timeout_under_pressure_too(self):
        self.assertTrue(self.rec("timeout", [92])["headline"].startswith("TIMEOUT (under memory pressure: RAM peak 92%"))

    def test_pass_under_pressure_is_a_note_only(self):
        r = self.rec("passed", [70, 88])
        self.assertIs(r["pressure"], True)
        self.assertTrue(r["headline"].startswith("PASSED (note: RAM peak 88% during the run): "), r["headline"])

    def test_below_the_threshold_nothing_changes(self):
        r = self.rec("failed", [84])
        self.assertIs(r["pressure"], False)
        self.assertNotIn("pressure_ram_peak_pct", r)
        self.assertTrue(r["headline"].startswith("FAILED: rc 1"), r["headline"])

    def test_only_the_failed_runs_explain_a_failure(self):
        """A flaky hunt whose failing run saw 60% is a code verdict, even if a passing run hit 90%."""
        r = self.rec("failed", [90, 60], passed=[True, False])
        self.assertIs(r["pressure"], False)
        self.assertTrue(self.rec("failed", [60, 90], passed=[True, False])["pressure"])

    def test_every_failed_run_must_have_run_under_pressure(self):
        """Review P1: run 3 failed at 60% is a code failure even if run 7 failed at 90%."""
        self.assertIs(self.rec("failed", [60, 90], passed=[False, False])["pressure"], False)
        r = self.rec("failed", [91, 87, 70], passed=[False, False, True])
        self.assertIs(r["pressure"], True)
        self.assertEqual(r["pressure_ram_peak_pct"], 87)          # the lowest: every failed run was at least there
        self.assertIs(self.rec("failed", [90, None], passed=[False, False])["pressure"], False)

    def test_deliberate_and_unstarted_runs_get_no_pressure_note(self):
        self.assertIs(self.rec("cancelled", [95])["pressure"], False)
        self.assertIs(self.rec("stopped", [95])["pressure"], False)
        self.assertIs(self.rec("error", [None])["pressure"], False)

    def test_runner_problems_never_read_as_memory_pressure(self):
        """error / stranded are about the runner or the job file; earlier runs' RAM doesn't explain them."""
        for st in ("error", "stranded"):
            with self.subTest(status=st):
                self.assertIs(self.rec(st, [95, 95], passed=[False, False])["pressure"], False)
        self.assertIs(self.rec("timeout", [95, None], passed=[False, False])["pressure"], False)  # slot wait

    def test_threshold_is_configurable(self):
        self.assertIs(self.rec("failed", [89], pressure_at=90)["pressure"], False)

    def test_a_bad_threshold_in_config_falls_back_to_85(self):
        for bad in ("85%", None, 0, 150, [1], True):
            with self.subTest(value=bad):
                self.paths.config.write_text(json.dumps({"pressure_ram_pct": bad}), encoding="utf-8")
                self.assertEqual(core.load_config(self.paths)["pressure_ram_pct"], 85.0)
                self.assertIs(self.rec("failed", [89], pressure_at=bad)["pressure"], True)
        self.paths.config.write_text(json.dumps({"pressure_ram_pct": 92}), encoding="utf-8")
        self.assertEqual(core.load_config(self.paths)["pressure_ram_pct"], 92.0)

    def test_a_run_shorter_than_one_poll_still_gets_its_sample(self):
        """A run that starts and ends between two samples still gets one (taken as it ends). The poll loop checks the
        started file before it checks the exit, so only a microseconds-wide window needed the extra check (review P2):
        this guards the behaviour, it can't force that window."""
        from unittest import mock
        self.cfg["sample_s"] = 1000                       # only the sample taken after the run ends can count
        j = self.job(["python", "-c", "raise SystemExit(1)"])
        started = self.paths.started(j["id"])
        with mock.patch.object(procs, "system_ram_pct", side_effect=lambda: 91 if started.exists() else 30):
            self.run_runner()
        d = self.done(j["id"])
        self.assertEqual(d["peak"]["sys_ram_pct"], 91)
        self.assertIs(d["pressure"], True)

    def test_status_row_marks_a_pressure_failure(self):
        core.write_json(self.paths.done / "j1.json", self.rec("failed", [89]))
        out = GlanceTests.cli(self, "status")[1]
        row = next(line for line in out if "j1" in line)
        self.assertIn("RAM 89%: re-check", row)
        js = json.loads("\n".join(GlanceTests.cli(self, "status", "--json")[1]))["failed_recent"][0]
        self.assertEqual((js["pressure"], js["pressure_ram_peak_pct"]), (True, 89))

    def slow_heavy(self) -> str:
        f = self.dir / "slow-heavy.sh"
        f.write_text('sleep 2\nshift 3\n"$@"\n', encoding="utf-8", newline="\n")    # 2 s "waiting for a slot"
        return str(f)

    def run_with_ram(self, waiting_pct, running_pct):
        from unittest import mock
        self.cfg["heavy_sh"] = self.slow_heavy()
        j = self.job(["python", "-c", "import time; time.sleep(1.5); raise SystemExit(1)"], heavy="cpu")
        started = self.paths.started(j["id"])
        with mock.patch.object(procs, "system_ram_pct",
                               side_effect=lambda: running_pct if started.exists() else waiting_pct):
            self.run_runner()
        return self.done(j["id"])

    def test_runner_flags_pressure_during_the_run(self):
        d = self.run_with_ram(50, 91)
        self.assertEqual(d["status"], "failed")
        self.assertIs(d["pressure"], True)
        self.assertEqual(d["peak"]["sys_ram_pct"], 91)
        self.assertIn("under memory pressure: RAM peak 91%", d["headline"])

    def test_ram_while_waiting_for_a_slot_is_not_the_runs(self):
        """Another suite filling RAM while this job still waits for its heavy.sh slot says nothing about this run."""
        d = self.run_with_ram(97, 40)
        self.assertIs(d["pressure"], False)
        self.assertEqual(d["peak"]["sys_ram_pct"], 40)
        self.assertTrue(d["headline"].startswith("FAILED: "), d["headline"])


class EndToEndTests(Base):
    """Through the real CLI, with the runner as its own process (as the scheduled task starts it)."""

    def cli(self, *args, check=True):
        cfgfile = self.paths.config
        if not cfgfile.exists():
            core.write_json(cfgfile, {"poll_s": 0.2, "sample_s": 0.5, "temp_root": str(self.dir / "tmp"),
                                      "python": PY, "allowed_roots": [str(TEMP_BASE)],
                                      "heavy_sh": str(self.fake_heavy())})
        r = subprocess.run([PY, "-B", str(ENTRY), "--home", str(self.paths.home), *args], capture_output=True,
                           text=True, cwd=str(self.dir), timeout=120)
        if check and r.returncode not in (0, 1, 2):
            raise AssertionError(f"wnc-queue {args} rc {r.returncode}: {r.stdout}{r.stderr}")
        return r

    def start_runner(self):
        p = subprocess.Popen([PY, "-B", str(ENTRY), "run", "--home", str(self.paths.home)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (p.poll() is None and p.kill(), p.wait()))
        return p

    def test_cli_end_to_end(self):
        r = self.cli("add", "--no-kick", "--title", "dummy job", "--repeat", "2", "--class", "cpu", "--owner",
                     "tests", "--", "python", "-c", "print('dummy ok')")
        jid = r.stdout.strip()
        self.assertTrue(core.ID_RE.match(jid), r.stdout + r.stderr)
        self.assertEqual(self.cli("result", jid).returncode, 2)
        self.assertIn("queued", self.cli("list").stdout)
        p = self.start_runner()
        self.assertEqual(p.wait(120), 0)
        res = self.cli("result", jid)
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn("PASSED", res.stdout)
        self.assertIn("2/2 runs passed", res.stdout)
        self.assertEqual(json.loads(self.cli("result", jid, "--json").stdout)["iterations_run"], 2)
        st = json.loads(self.cli("status", "--json").stdout)
        self.assertEqual((st["queued"], st["running"], st["done"], st["runner_alive"]), (0, 0, 1, False))
        self.assertEqual(self.cli("add", "--no-kick", "--", "cmd", "/c", "echo", check=False).returncode, 4)
        self.assertEqual(self.cli("result", "no-such-job", check=False).returncode, 3)

    def test_runner_killed_mid_job_recovers(self):
        pidf = self.dir / "child.pid"
        s = self.script("slow.py", f"""import os, pathlib, sys, time
pathlib.Path(r"{pidf}").write_text(str(os.getpid()))
print("slow start", flush=True)
time.sleep(float(sys.argv[1]))
print("slow done", flush=True)
""")
        jid = self.cli("add", "--no-kick", "--repeat", "2", "--id", "survivor", "--", "python", s, "4").stdout.strip()
        p = self.start_runner()
        wait_for(lambda: pidf.exists(), "run 1 started")
        child = int(pidf.read_text())
        p.kill()                                           # the runner dies (crash / reboot / restart)
        p.wait(30)
        wait_for(lambda: not pid_alive(child), "the job tree dies with its runner (KILL_ON_JOB_CLOSE)", 15)
        self.assertTrue((self.paths.running / f"{jid}.json").exists(), "left in running/ for recovery")
        p2 = self.start_runner()                           # what the 10-minute trigger does
        self.assertEqual(p2.wait(120), 0)
        d = json.loads(self.cli("result", jid, "--json").stdout)
        self.assertEqual((d["status"], d["iterations_run"], d["attempts"]), ("passed", 2, 2))
        self.assertTrue(any("recovered" in e for e in d["events"]))

    def test_second_runner_exits_while_one_runs(self):
        s = self.script("slow.py", "import time\nprint('x', flush=True)\ntime.sleep(12)\n")   # margin over the
        self.cli("add", "--no-kick", "--", "python", s)                                       # 3 s lock wait
        p = self.start_runner()
        wait_for(lambda: runner.lock_is_held(self.paths), "runner 1 holds the lock")
        p2 = self.start_runner()
        self.assertEqual(p2.wait(30), 3)
        self.assertEqual(p.wait(60), 0)


if __name__ == "__main__":
    unittest.main()
