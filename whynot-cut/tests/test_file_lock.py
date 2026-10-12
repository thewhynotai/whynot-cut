"""3.0 T2.4 (engine IM-11, MI-23): concurrency-safe writes. A per-file OS lock (`lib/file_lock.py`) around every
read-modify-write of a shared file: project-status.json (set_status), clip-ids.json, the client's reference-analysis
cache, discovery (one per client at a time) and an episode's Gate 0 (`reels.select`, which also validates every pick
before it writes anything). Run:
    <engine python> -m unittest discover -s whynot-cut/tests -p test_file_lock.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import multiprocessing
import os
import contextlib
import errno
import io
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
ENGINE = SK / "engine" / "reel"
sys.path.insert(0, str(ENGINE))

from lib import common, errors, file_lock  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402

WRITERS = 8
UPDATES = 25            # 8 x 25 = 200: the whole run fits the capped status history (T2.15, STATUS_HISTORY_MAX)


def _status_writer(root: str, video_id: str, writer: int, n: int, start) -> None:
    """One of the stress-test processes (module level: multiprocessing spawns it by name)."""
    start.wait(60)
    p = Paths(root, video_id)
    for k in range(n):
        common.set_status(p, "TRANSCRIBED", f"w{writer}-{k}", f"stage{writer}")


def _child(code: str, timeout: float = 60) -> subprocess.CompletedProcess:
    """Run engine code in a fresh process of the engine runtime (the sandbox environment is inherited)."""
    pre = f"import sys; sys.dont_write_bytecode = True; sys.path.insert(0, {str(ENGINE)!r})\n"
    return subprocess.run([sys.executable, "-B", "-c", pre + code], capture_output=True, text=True,
                          encoding="utf-8", timeout=timeout)


class TempDir(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)


class TestLock(TempDir):
    def test_lock_file_sits_next_to_the_file(self):
        f = self.tmp / "a" / "status.json"
        with file_lock.locked(f) as lp:
            self.assertEqual(lp, self.tmp / "a" / "status.json.lock")
            self.assertTrue(lp.is_file())

    def test_reentrant_in_one_thread(self):
        f = self.tmp / "x.json"
        with file_lock.locked(f, wait_s=1):
            with file_lock.locked(f, wait_s=1):
                common.write_json(f, {"n": 1})
            common.update_json(f, lambda d: dict(d, n=d["n"] + 1))
        self.assertEqual(read_json(f), {"n": 2})

    def test_another_thread_waits_and_then_times_out(self):
        f = self.tmp / "x.json"
        got = []

        def other():
            try:
                with file_lock.locked(f, wait_s=0.2):
                    got.append("locked")
            except file_lock.LockTimeout as e:
                got.append(e)
        with file_lock.locked(f):
            t = threading.Thread(target=other)
            t.start()
            t.join(10)
        self.assertIsInstance(got[0], file_lock.LockTimeout)
        t = threading.Thread(target=other)          # released: the next one gets it at once
        t.start()
        t.join(10)
        self.assertEqual(got[1], "locked")

    def test_threads_never_lose_an_update(self):
        f = self.tmp / "count.json"
        write_json(f, {"n": 0})

        def bump():
            for _ in range(60):
                common.update_json(f, lambda d: dict(d, n=d["n"] + 1))
        ts = [threading.Thread(target=bump) for _ in range(4)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(60)
        self.assertEqual(read_json(f)["n"], 240)

    def test_another_process_is_refused_while_held(self):
        f = self.tmp / "x.json"
        code = (f"from lib.file_lock import locked, LockTimeout\n"
                f"try:\n    with locked({str(f)!r}, wait_s=0.3):\n        print('locked')\n"
                f"except LockTimeout as e:\n    print('busy', e.error)\n")
        with file_lock.locked(f):
            r = _child(code)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("busy x.json is busy"), r.stdout)
        self.assertEqual(_child(code).stdout.strip(), "locked")

    def test_a_crashed_holder_leaves_no_stale_lock(self):
        """The OS drops the lock with the process: no pid record, no takeover, no waiting."""
        f = self.tmp / "x.json"
        r = _child(f"import os\nfrom lib.file_lock import locked\nwith locked({str(f)!r}):\n"
                   f"    print('held', flush=True)\n    os._exit(3)\n")
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "held"), r.stderr)
        t0 = time.monotonic()
        with file_lock.locked(f, wait_s=2):
            pass
        self.assertLess(time.monotonic() - t0, 1.0)

    def test_timeout_is_guidance_not_a_traceback(self):
        d = errors.describe(file_lock.LockTimeout(self.tmp / "project-status.json", 120))
        self.assertFalse(d["ok"])
        self.assertIn("project-status.json is busy", d["error"])
        self.assertIn("run this command again", d["how"])
        self.assertEqual(d["where"], str(self.tmp / "project-status.json"))

    def test_update_json_starts_from_a_copy_of_the_default(self):
        default = {"history": []}
        f = self.tmp / "new.json"
        doc = common.update_json(f, lambda d: d["history"].append(1), default)
        self.assertEqual((doc, read_json(f), default), ({"history": [1]}, {"history": [1]}, {"history": []}))


class TestVolumeWithoutLocks(TempDir):
    """T2.4 review I1: a volume that refuses OS file locks (macOS SMB/AFP/File Provider: ENOTSUP/ENOLCK; a Windows
    virtual drive: EINVAL) must not fail every locked write. The folder is noted once in the engine log and goes on
    with the in-process lock only. Both platforms' code paths are driven with a mocked lock call."""
    UNSUPPORTED = [errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOLCK, errno.ENOSYS, errno.EINVAL]

    def refusing(self, win: bool, err: int):
        """A context: the platform's lock call (msvcrt.locking / fcntl.flock) fails with `err`, the engine home and the
        once-per-folder memory are the test's own. Yields the mocked call."""
        call = mock.Mock(side_effect=OSError(err, os.strerror(err)))
        if win:
            mod = types.SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0, locking=call)
        else:
            mod = types.SimpleNamespace(LOCK_EX=2, LOCK_NB=4, LOCK_UN=8, flock=call)
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(common, "engine_home", lambda: self.tmp / "home"))
        stack.enter_context(mock.patch.object(file_lock, "_unsupported_noted", set()))
        stack.enter_context(mock.patch.object(file_lock, "IS_WIN", win))
        stack.enter_context(mock.patch.object(file_lock, "msvcrt" if win else "fcntl", mod, create=True))
        self.addCleanup(stack.close)
        return stack, call

    def log_lines(self):
        log = self.tmp / "home" / "logs" / "pipeline.log"
        return log.read_text(encoding="utf-8").splitlines() if log.is_file() else []

    def scenario(self, win: bool, err: int):
        stack, call = self.refusing(win, err)
        with stack:
            f = self.tmp / "client" / "project-status.json"
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                with file_lock.locked(f, wait_s=1):
                    common.write_json(f, {"n": 1})
                    with file_lock.locked(f, wait_s=1):              # still re-entrant
                        pass
                    got = []
                    t = threading.Thread(target=lambda: got.append(_try_lock(f)))
                    t.start()
                    t.join(10)
                    self.assertEqual(got, [False], "another thread must still be excluded (in-process lock)")
                with file_lock.locked(f, wait_s=1):                   # a second cycle: noted once, not twice
                    pass
            self.assertEqual(out.getvalue(), "", "nothing on stdout/stderr")
            self.assertTrue(call.called)
            self.assertEqual(read_json(f), {"n": 1})
            lines = self.log_lines()
            self.assertEqual(len(lines), 1, lines)
            self.assertIn("file_lock:", lines[0])
            self.assertIn(str(f.parent), lines[0])
            self.assertIn("inside this process only", lines[0])
        shutil.rmtree(self.tmp / "home", True)

    def test_posix_flock_refused_is_noted_once_and_work_goes_on(self):
        for err in self.UNSUPPORTED:
            with self.subTest(errno=errno.errorcode.get(err, err)):
                self.scenario(False, err)

    def test_windows_byte_range_lock_refused_is_noted_once_and_work_goes_on(self):
        for err in self.UNSUPPORTED:
            with self.subTest(errno=errno.errorcode.get(err, err)):
                self.scenario(True, err)

    def test_each_folder_is_noted_once(self):
        stack, _ = self.refusing(False, errno.ENOTSUP)
        with stack:
            for d in ("a", "b", "a"):
                with file_lock.locked(self.tmp / d / "x.json", wait_s=1):
                    pass
            self.assertEqual(len(self.log_lines()), 2)

    def test_other_os_errors_are_still_errors(self):
        for win in (False, True):
            with self.subTest(win=win):
                stack, _ = self.refusing(win, errno.EIO)
                with stack, self.assertRaises(OSError) as cm:
                    with file_lock.locked(self.tmp / "x.json", wait_s=1):
                        pass
                self.assertEqual(cm.exception.errno, errno.EIO)

    def test_a_busy_file_is_still_waited_for_not_mistaken_for_no_support(self):
        stack, _ = self.refusing(True, errno.EACCES)       # the Windows "someone else holds it" answer
        with stack, self.assertRaises(file_lock.LockTimeout):
            with file_lock.locked(self.tmp / "x.json", wait_s=0.1):
                pass
        self.assertEqual(self.log_lines(), [])


class TestLockFileCannotBeOpened(TempDir):
    """T2.4 review minor 4: a lock file that cannot be created is not waited for for 120 s."""

    def test_permission_error_retries_briefly_then_names_the_folder(self):
        f = self.tmp / "ro" / "project-status.json"
        denied = mock.Mock(side_effect=PermissionError(errno.EACCES, "Permission denied"))
        t0 = time.monotonic()
        with mock.patch.object(file_lock, "OPEN_RETRY_S", 0.2), mock.patch.object(file_lock.os, "open", denied):
            with self.assertRaises(errors.Guidance) as cm:
                with file_lock.locked(f, wait_s=60):
                    self.fail("must not lock")
        self.assertLess(time.monotonic() - t0, 10)
        self.assertGreater(denied.call_count, 1, "retried for a moment (a scanner holds the file briefly)")
        self.assertNotIsInstance(cm.exception, file_lock.LockTimeout)
        self.assertIn("project-status.json.lock", cm.exception.error)
        self.assertIn(str(f.parent), cm.exception.error)
        self.assertIn(str(f.parent), cm.exception.how)
        d = errors.describe(cm.exception)
        self.assertEqual((d["ok"], errors.exit_code(d)), (False, 1))

    def test_a_transient_permission_error_still_gets_the_lock(self):
        f = self.tmp / "x.json"
        real = os.open
        calls = []

        def flaky(*a, **kw):
            calls.append(1)
            if len(calls) < 4:
                raise PermissionError(errno.EACCES, "Permission denied")
            return real(*a, **kw)
        with mock.patch.object(file_lock.os, "open", flaky):
            with file_lock.locked(f, wait_s=5):
                pass
        self.assertEqual(len(calls), 4)

    def test_any_other_open_failure_is_guidance_at_once(self):
        f = self.tmp / "x.json"
        full = mock.Mock(side_effect=OSError(errno.ENOSPC, "No space left on device"))
        with mock.patch.object(file_lock.os, "open", full):
            with self.assertRaises(errors.Guidance) as cm:
                with file_lock.locked(f, wait_s=60):
                    pass
        self.assertEqual(full.call_count, 1)
        self.assertIn(str(self.tmp), cm.exception.error)


class TestTimeoutIsARefusal(TempDir):
    """T2.4 review minor 5: a busy-file timeout exits 2 like the writer-lease refusal ("wait, run again")."""

    def test_document_has_blocked_and_exits_2(self):
        exc = file_lock.LockTimeout(self.tmp / "project-status.json", 120)
        d = errors.describe(exc)
        self.assertFalse(d["ok"])
        self.assertIn("project-status.json is busy", d["blocked"])
        self.assertIn("run this command again", d["how"])
        self.assertEqual(errors.exit_code(d), 2)

    def test_other_guidance_still_exits_1(self):
        d = errors.describe(errors.Guidance("x", "y"))
        self.assertNotIn("blocked", d)
        self.assertEqual(errors.exit_code(d), 1)

    def test_a_real_timeout_through_the_cli_handler_exits_2(self):
        f = self.tmp / "x.json"
        holder = []

        def other():
            try:
                with file_lock.locked(f, wait_s=0.1):
                    pass
            except file_lock.LockTimeout as e:
                holder.append(e)
        with file_lock.locked(f):
            t = threading.Thread(target=other)
            t.start()
            t.join(10)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as cm:
            errors.emit(errors.report(holder[0], self.tmp / "pipeline.log", "reel discover"))
        self.assertEqual(cm.exception.code, 2)
        self.assertIn('"blocked"', out.getvalue())


class TestDiscoveryChecksTheRootFirst(TempDir):
    """T2.4 review minor 3: a wrong --root must not get `output/discovery/*.lock` files."""

    def run_it(self, root: Path):
        from lib import discover
        with self.assertRaises(FileNotFoundError) as cm:
            discover.run_discovery(Paths(root))
        self.assertIn("Expected assets/ and data/", str(cm.exception))

    def test_a_folder_that_is_not_a_client_gets_no_files(self):
        wrong = self.tmp / "Downloads"
        wrong.mkdir()
        self.run_it(wrong)
        self.assertEqual(list(wrong.iterdir()), [])

    def test_a_root_inside_assets_or_data_gets_no_files(self):
        client = self.tmp / "Client"
        (client / "assets" / "Logos").mkdir(parents=True)
        (client / "data" / "Raw").mkdir(parents=True)
        before = sorted(p.relative_to(client).as_posix() for p in client.rglob("*"))
        for inner in (client / "assets", client / "data", client / "data" / "Raw"):
            self.run_it(inner)
        self.assertEqual(sorted(p.relative_to(client).as_posix() for p in client.rglob("*")), before)

    def test_a_client_folder_missing_only_data_is_refused_too(self):
        client = self.tmp / "Half"
        (client / "assets").mkdir(parents=True)
        self.run_it(client)
        self.assertFalse((client / "output").exists())


class TestSetStatusStress(TempDir):
    def test_eight_processes_lose_no_status_update(self):
        """Acceptance (T2.4): 8 writer processes x N set_status calls on ONE project-status.json, no update lost.
        Every note must survive, so the run stays within the 200-entry history cap (T2.15); with a no-op lock the
        same run loses updates (checked in T2.15 fix round 1)."""
        self.assertLessEqual(WRITERS * UPDATES, common.STATUS_HISTORY_MAX)    # else the cap, not a race, drops notes
        p = Paths(self.tmp, "CLIP1")
        p.ensure_project()
        ctx = multiprocessing.get_context("spawn")
        start = ctx.Event()
        procs = [ctx.Process(target=_status_writer, args=(str(self.tmp), "CLIP1", w, UPDATES, start))
                 for w in range(WRITERS)]
        for pr in procs:
            pr.start()
        start.set()
        for pr in procs:
            pr.join(120)
        self.assertEqual([pr.exitcode for pr in procs], [0] * WRITERS)
        st = common.load_status(p)
        notes = [h["note"] for h in st["history"]]
        self.assertEqual(len(notes), WRITERS * UPDATES)
        self.assertEqual(sorted(notes), sorted(f"w{w}-{k}" for w in range(WRITERS) for k in range(UPDATES)))
        for w in range(WRITERS):                    # each writer's own updates land in its own order
            mine = [int(n.split("-")[1]) for n in notes if n.startswith(f"w{w}-")]
            self.assertEqual(mine, list(range(UPDATES)))
        self.assertEqual(sorted(st["stages"]), sorted(f"stage{w}" for w in range(WRITERS)))
        qc = common.status_path(p).parent
        self.assertEqual(sorted(x.name for x in qc.iterdir()), ["project-status.json", "project-status.json.lock"])


class TestSharedFilesAreLocked(TempDir):
    """Each shared read-modify-write holds the file's lock: a probe from another thread cannot take it meanwhile."""

    def held(self, path) -> bool:
        out = []

        def probe():
            try:
                with file_lock.locked(path, wait_s=0.05):
                    out.append(False)
            except file_lock.LockTimeout:
                out.append(True)
        t = threading.Thread(target=probe)
        t.start()
        t.join(10)
        return out[0]

    def client(self) -> Path:
        root = self.tmp / "Client"
        (root / "assets").mkdir(parents=True)
        (root / "data" / "Raw").mkdir(parents=True)
        (root / "data" / "Raw" / "C0001.mp4").write_bytes(b"\0" * 64)
        return root

    def test_discovery_runs_one_at_a_time_per_client(self):
        from lib import discover
        root = self.client()
        seen = []
        real = discover.discover

        def spy(paths, **kw):
            seen.append(self.held(paths.output / "discovery" / "input-inventory.json"))
            return real(paths, **kw)
        env = {"platform": "test", "adobe_apps": [], "aerender": None, "tools": {}, "python_modules": {}}
        with mock.patch.object(discover, "discover", spy), mock.patch.object(discover, "audit_environment",
                                                                             return_value=env):
            discover.run_discovery(Paths(root))
        self.assertEqual(seen, [True])
        self.assertFalse(self.held(Paths(root).output / "discovery" / "input-inventory.json"))
        self.assertTrue((root / "output" / "discovery" / "input-inventory.json").is_file())

    def test_clip_ids_update_holds_the_map_lock(self):
        from lib import clip_ids
        root = self.client()
        seen = []
        real = clip_ids.assign

        def spy(*a, **kw):
            seen.append(self.held(Paths(root).output / clip_ids.MAP_REL))
            return real(*a, **kw)
        inv = {"files": [{"rel": "data/Raw/C0001.mp4", "role": "source_footage"}]}
        with mock.patch.object(clip_ids, "assign", spy):
            ids = clip_ids.clip_ids(root, inv)
        self.assertEqual(seen, [True])
        self.assertEqual(list(ids.values()), ["data/Raw/C0001.mp4"])

    def test_set_status_holds_the_status_lock(self):
        p = Paths(self.tmp, "CLIP1")
        p.ensure_project()
        seen = []
        real = common.write_json

        def spy(path, data):
            if Path(path).name == "project-status.json":
                seen.append(self.held(path))
            return real(path, data)
        with mock.patch.object(common, "write_json", spy):
            common.set_status(p, "TRANSCRIBED", "x", "transcribe")
        self.assertEqual(seen, [True])

    def test_reference_cache_keeps_entries_another_reel_added_meanwhile(self):
        from lib import ref_analysis
        root = self.client()
        p = Paths(root)
        refs = []
        for n in ("a", "b"):
            f = self.tmp / f"ref_{n}.mp4"
            f.write_bytes(n.encode() * 32)
            refs.append(f)
        cache = p.output / "client_database" / "reference_analysis" / "cache.json"

        def fake(v, cache_dir, dur):
            if Path(v).name == "ref_a.mp4":            # a parallel reel finishes its own reference meanwhile
                write_json(cache, {"other|1|1": {"video": "other"}})
            return {"video": str(v), "duration_s": 1.0, "cut_count": 0, "cuts_per_minute": 0.0, "shot_stats": {},
                    "first_cut_s": None, "contact_sheets": [], "shot_durations_s": [1.0]}
        with mock.patch.object(ref_analysis, "analyze_reference", fake), mock.patch.object(ref_analysis, "log"):
            ref_analysis.analyze_all(p, refs, {})
        keys = read_json(cache)
        self.assertIn("other|1|1", keys)
        self.assertEqual(sum(1 for k in keys if "ref_" in k), 2)


try:                                                   # the Gate 0 fixture of the podcast suite
    import test_podcast as _tp
except Exception:  # noqa: BLE001
    _tp = None


@unittest.skipIf(_tp is None, "test_podcast fixture not importable")
class TestReelsSelectAtomic(unittest.TestCase):
    """reels.select validates every pick before it writes anything: a bad pick leaves no half-made Gate 0."""
    setUp = _tp.TestReelsSelect.setUp if _tp else None
    tearDown = _tp.TestReelsSelect.tearDown if _tp else None
    select = _tp.TestReelsSelect.select if _tp else None

    def assert_untouched(self):
        self.assertFalse(Paths(self.root, "EP12_R01").p("00_inputs/source.json").exists())
        self.assertFalse(self.ep.p("01_analysis/selection.json").exists())

    def test_a_bad_later_pick_writes_nothing(self):
        with self.assertRaises(SystemExit) as cm:          # R02's adjusted window is below the 1 s minimum
            self.select("R01", "R02", adjust=["R02:in=00:00:18.700"], confirm_avoid=["R02"])
        self.assertIn("R02", str(cm.exception))
        self.assert_untouched()

    def test_an_existing_reel_without_force_writes_nothing(self):
        self.select("R02", confirm_avoid=["R02"])
        before = read_json(self.ep.p("01_analysis/selection.json"))
        src = read_json(Paths(self.root, "EP12_R02").p("00_inputs/source.json"))
        with self.assertRaises(SystemExit) as cm:
            self.select("R01", "R02", adjust=["R02:in=00:00:14.000"], confirm_avoid=["R02"])
        self.assertIn("needs --force", str(cm.exception))
        self.assertFalse(Paths(self.root, "EP12_R01").p("00_inputs/source.json").exists())
        self.assertEqual(read_json(self.ep.p("01_analysis/selection.json")), before)
        self.assertEqual(read_json(Paths(self.root, "EP12_R02").p("00_inputs/source.json")), src)

    def test_good_picks_still_all_land_in_order(self):
        r = self.select("R02", "R01", confirm_avoid=["R02"])
        self.assertEqual([x["reel_id"] for x in r["reels"]], ["EP12_R02", "EP12_R01"])
        self.assertEqual([x["status"] for x in r["reels"]], ["created", "created"])
        sel = read_json(self.ep.p("01_analysis/selection.json"))
        self.assertEqual(sel["history"][-1]["picked"], ["R02", "R01"])

    def test_a_write_failure_on_pick_2_leaves_it_to_be_redone(self):
        """T2.4 review minor 2: source.json is written LAST per pick, so a pick that failed half way has none (it
        is not "unchanged" on the re-run) and the re-run makes it."""
        from lib import reels
        real = reels.slice_transcript
        calls = []

        def flaky(*a, **kw):
            calls.append(1)
            if len(calls) == 2:
                raise OSError(28, "No space left on device")
            return real(*a, **kw)
        with mock.patch.object(reels, "slice_transcript", flaky):
            with self.assertRaises(OSError):
                self.select("R01", "R02", confirm_avoid=["R02"])
        self.assertTrue(Paths(self.root, "EP12_R01").p("00_inputs/source.json").is_file())
        self.assertFalse(Paths(self.root, "EP12_R02").p("00_inputs/source.json").exists())
        self.assertFalse(self.ep.p("01_analysis/selection.json").exists())
        r = self.select("R01", "R02", confirm_avoid=["R02"])
        self.assertEqual([(x["reel_id"], x["status"]) for x in r["reels"]],
                         [("EP12_R01", "unchanged"), ("EP12_R02", "created")])
        self.assertTrue(Paths(self.root, "EP12_R02").p("00_inputs/source.json").is_file())
        self.assertEqual(read_json(self.ep.p("01_analysis/selection.json"))["history"][-1]["picked"], ["R01", "R02"])

    def test_select_holds_the_selection_lock(self):
        from lib import reels
        seen = []
        real = reels.slice_transcript
        f = self.ep.p("01_analysis/selection.json")

        def spy(*a, **kw):
            out = []
            t = threading.Thread(target=lambda: out.append(_try_lock(f)))
            t.start()
            t.join(10)
            seen.append(out[0])
            return real(*a, **kw)
        with mock.patch.object(reels, "slice_transcript", spy):
            self.select("R01")
        self.assertEqual(seen, [False])


def _try_lock(path) -> bool:
    try:
        with file_lock.locked(path, wait_s=0.05):
            return True
    except file_lock.LockTimeout:
        return False


if __name__ == "__main__":
    unittest.main()
