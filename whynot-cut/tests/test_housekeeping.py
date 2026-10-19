# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 15 (T4.15): `lib/housekeeping.py`, the engine side of "Free up space" (`reel clean`).

Deleting is a way to lose data, so these tests hold the line the plan draws: dry run by default, an allowlist of
engine-home categories (not a denylist), real-path confinement on `lib/linksafe.py`, never entering a link (rule 15,
the 2026-10-14 junction incident), never a client folder, never a model in use, models only with their flag.

Every link here is made in the test's own temp folder: `_winapi.CreateJunction` on Windows, `os.symlink` elsewhere
(a test is skipped only when the OS refuses to make the link). Sentinel files outside the home are hashed before and
after to prove a target was never touched. Run:
    bash tools/test.sh -p test_housekeeping.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

from lib import common, errors, file_lock, linksafe, plat, runtime  # noqa: E402
from lib import housekeeping as HK  # noqa: E402

DAY = 24 * 3600
OLD = time.time() - 3 * DAY
IS_WIN = sys.platform == "win32"
PY = "python.exe" if IS_WIN else "python3"


def dir_link(link: Path, target: Path):
    """A directory link: a junction on Windows, a symlink elsewhere."""
    if IS_WIN:
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def file_link(test, link: Path, target, relative: bool = False):
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as e:
        test.skipTest(f"the OS refused a file symlink here: {e}")


def write(p: Path, data: bytes = b"x", mtime: float | None = None) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


def age_tree(p: Path, mtime: float = OLD):
    """Make every file and folder under p old (folders last, so writing the files does not refresh them)."""
    for d, dirs, files in os.walk(p, topdown=False):
        for n in files:
            if not os.path.islink(os.path.join(d, n)):
                os.utime(os.path.join(d, n), (mtime, mtime))
        os.utime(d, (mtime, mtime))


def tree_digest(root: Path) -> list:
    """Every name under root with its kind, size, mtime and content hash; links by their target, never entered."""
    out = []
    stack = [Path(root)]
    while stack:
        d = stack.pop()
        for e in sorted(os.scandir(d), key=lambda e: e.name):
            p = Path(e.path)
            rel = os.path.relpath(p, root)
            if linksafe.is_link(p):
                out.append((rel, "link", os.readlink(p) if not IS_WIN or os.path.islink(p) else "junction"))
            elif e.is_dir(follow_symlinks=False):
                out.append((rel, "dir"))
                stack.append(p)
            else:
                st = os.lstat(p)
                out.append((rel, "file", st.st_size, st.st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()))
    return out


def rm_links(root: Path):
    """Test cleanup: unlink every link under root as a name (never followed), so TemporaryDirectory's rmtree never
    meets one."""
    stack = [Path(root)]
    while stack:
        d = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        for e in entries:
            p = Path(e.path)
            try:
                if linksafe.is_link(p):
                    if IS_WIN and e.is_dir():
                        os.rmdir(p)
                    else:
                        os.unlink(p)
                elif e.is_dir(follow_symlinks=False):
                    os.chmod(p, stat.S_IRWXU)
                    stack.append(p)
                else:
                    os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass


class Home(unittest.TestCase):
    """A realistic engine home in a temp folder (Arabic + space in its name), plus an `outside` folder."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.tmp = Path(d.name)
        self.addCleanup(rm_links, self.tmp)
        self.home = self.tmp / "engine home منزل"
        self.outside = self.tmp / "outside"
        self.outside.mkdir()
        self.sentinel = write(self.outside / "sentinel.txt", b"keep me " * 100)
        self.clients = self.tmp / "Clients"
        (self.clients / "Dr A" / "assets").mkdir(parents=True)
        (self.clients / "Dr A" / "data").mkdir(parents=True)
        write(self.clients / "Dr A" / "assets" / "clip.mp4", b"c" * 500)
        env = {k: "" for k in plat.CLIENTS_ENV}
        env[plat.CLIENTS_ENV[0]] = str(self.clients)
        env[plat.HOME_ENV[0]] = str(self.home)          # this home is the engine home (venv_legacy asks)
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        saved = mock.patch.object(plat, "saved_options", return_value={"engine_home": str(self.home),
                                                                        "clients_root": ""})
        saved.start()                                    # the saved option names this home (persistent)
        self.addCleanup(saved.stop)
        self.build()

    def build(self):
        h = self.home
        # what must never go
        write(h / "signing" / "key.pem", b"k" * 10, OLD)
        write(h / "state.json", b"{}", OLD)
        write(h / "bridge" / "bundle.zxp", b"b" * 10, OLD)
        write(h / "bin" / ("uv.exe" if IS_WIN else "uv"), b"#!uv", OLD)
        write(h / "plugin-options.json", b"{}", OLD)
        write(h / "serve" / "jobs" / "j.json", b"{}", OLD)
        write(h / "python" / "base" / PY, b"py", OLD)
        write(h / "locks" / "gpu.lock", b"", OLD)
        write(h / "logs" / "time-saved.jsonl", b"t" * 50, OLD)
        write(h / "current", b"r-cur\n", OLD)
        self.runtime(h / "runtimes" / "r-cur", OLD + 300)
        # removable
        write(h / "cache" / "uv" / "wheels" / "a.whl", b"u" * 1000, OLD)
        write(h / "cache" / "accel.json", b"{}", OLD)
        write(h / "cache" / "font-index.json", b"f" * 2000, OLD)
        write(h / "cache" / "stuff" / "deep" / "x.bin", b"s" * 3000, OLD)
        age_tree(h / "cache")
        write(h / "logs" / "pipeline.log", b"p" * 100, OLD)
        write(h / "logs" / "pipeline.log.1", b"q" * 400, OLD)
        write(h / "logs" / "pipeline.log.2", b"q" * 300, OLD)
        write(h / "logs" / "serve.log.1", b"S" * 700, OLD)
        write(h / "logs" / "serve-audit.log", b"A" * 900, OLD)
        self.runtime(h / "runtimes" / "r-prev", OLD + 200)
        self.runtime(h / "runtimes" / "r-old", OLD + 100, extra=5000)
        write(h / "venv" / ("Scripts" if IS_WIN else "bin") / PY, b"v" * 600, OLD)
        write(h / "cuda" / "bin" / "cublas64_12.dll", b"c" * 800, OLD)
        write(h / "ppro-queue" / "job1.job.json", b"j" * 40, OLD)
        write(h / "ppro-queue" / "job1.result.json", b"r" * 60, OLD)
        write(h / "ppro-queue" / "heartbeat.json", b"{}", OLD)
        write(h / "ppro-queue" / ".build.lock", b"{}", OLD)
        write(h / "ppro-queue" / "fresh.job.json", b"n" * 10)
        m = h / "models"
        self.repo(m / "models--Systran--faster-whisper-large-v3", 4000)
        self.repo(m / "models--Systran--faster-whisper-medium", 2500)     # a fallback model (transcription.json)
        self.repo(m / "models--Systran--faster-whisper-small", 2500)      # in no chain, no profile: removable
        self.repo(m / "models--facebook--wav2vec2-xlsr-arabic", 1500)
        write(m / "models--Systran--faster-whisper-large-v3" / "blobs" / "old.incomplete", b"i" * 700, OLD)
        write(m / ".locks" / "models--Systran--faster-whisper-large-v3" / "x.lock", b"", OLD)
        write(m / "CACHEDIR.TAG", b"Signature", OLD)
        age_tree(m)
        write(m / "models--Systran--faster-whisper-large-v3" / "blobs" / "fresh.incomplete", b"i" * 70)

    def runtime(self, d: Path, mtime: float, extra: int = 0):
        write(d / "pyvenv.cfg", f"home = {self.home / 'python' / 'base'}\n".encode(), mtime)
        write(d / ("Scripts" if IS_WIN else "bin") / PY, b"r" * 100, mtime)
        if extra:
            write(d / "Lib" / "big.bin", b"e" * extra, mtime)
        age_tree(d, mtime)

    def repo(self, r: Path, size: int):
        write(r / "blobs" / "b1", b"m" * size)
        write(r / "refs" / "main", b"s1")
        (r / "snapshots" / "s1").mkdir(parents=True)
        try:
            os.symlink(os.path.join("..", "..", "blobs", "b1"), r / "snapshots" / "s1" / "model.bin")
        except (OSError, NotImplementedError):
            write(r / "snapshots" / "s1" / "model.bin", b"m" * 10)

    def status(self, **kw):
        st = {"kind": "runtime", "id": "r-cur", "broken": None, "up_to_date": True,
              "dir": str(self.home / "runtimes" / "r-cur")}
        st.update(kw)
        return mock.patch.object(HK.runtime, "status", return_value=st)

    def item(self, rep, key):
        return next(i for i in rep["items"] if i["key"] == key)

    def outside_hash(self):
        return tree_digest(self.outside)


# ------------------------------------------------------------------------------------------------ the plan's tests
class TestPlan(Home):
    def test_dry_run_is_default_and_changes_nothing(self):
        before = tree_digest(self.home)
        with self.status():
            rep = HK.clean(self.home)
        self.assertEqual(tree_digest(self.home), before)
        self.assertFalse(rep["apply"])
        self.assertTrue(any(i["bytes"] for i in rep["items"]))
        self.assertTrue(all(i["removed"] == 0 for i in rep["items"]))

    def test_scan_writes_nothing_even_with_models(self):
        before = tree_digest(self.home)
        with self.status():
            HK.scan(self.home)
            HK.clean(self.home, models=True)
        self.assertEqual(tree_digest(self.home), before)

    def test_apply_removes_only_the_allowlist(self):
        with self.status(), mock.patch.object(HK.subprocess, "run", side_effect=AssertionError("uv is opt-in")), \
                mock.patch.object(HK, "_prune_is_link_safe", return_value=False):
            rep = HK.clean(self.home, apply=True, models=True)
        h = self.home
        for keep in ("signing/key.pem", "state.json", "bridge/bundle.zxp", "plugin-options.json", "serve/jobs/j.json",
                     "python/base/" + PY, "locks/gpu.lock", "logs/time-saved.jsonl", "current", "runtimes/r-cur/pyvenv.cfg",
                     "runtimes/r-prev/pyvenv.cfg", "cache/accel.json", "logs/pipeline.log", "logs/serve.log.1",
                     "logs/serve-audit.log", "ppro-queue/heartbeat.json", "ppro-queue/.build.lock",
                     "ppro-queue/fresh.job.json", "models/models--Systran--faster-whisper-large-v3/blobs/b1",
                     "models/models--Systran--faster-whisper-large-v3/blobs/fresh.incomplete",
                     "models/models--facebook--wav2vec2-xlsr-arabic/blobs/b1", "models/CACHEDIR.TAG",
                     "models/models--Systran--faster-whisper-medium/blobs/b1",
                     "cuda/bin/cublas64_12.dll", "bin/" + ("uv.exe" if IS_WIN else "uv"),
                     "runtimes/r-old/pyvenv.cfg", "cache/uv/wheels/a.whl"):
            self.assertTrue((h / keep).exists(), keep)
        for gone in ("cache/font-index.json", "cache/stuff", "logs/pipeline.log.1", "logs/pipeline.log.2",
                     "venv", "ppro-queue/job1.job.json", "ppro-queue/job1.result.json",
                     "models/models--Systran--faster-whisper-large-v3/blobs/old.incomplete",
                     "models/models--Systran--faster-whisper-small"):
            self.assertFalse(os.path.lexists(h / gone), gone)
        self.assertEqual(self.outside_hash()[0][0], "sentinel.txt")
        self.assertGreater(rep["freed_bytes"], 0)
        for i in rep["items"]:
            self.assertIsNone(i["error"], i)

    def test_never_follows_a_junction_or_symlink(self):
        before = self.outside_hash()
        dir_link(self.home / "cache" / "x", self.outside)
        os.utime(self.home / "cache", (OLD, OLD))
        with self.status():
            dry = HK.scan(self.home)
            self.assertEqual(self.outside_hash(), before)
            HK.clean(self.home, apply=True, models=True)
        self.assertFalse(os.path.lexists(self.home / "cache" / "x"))
        self.assertTrue(self.sentinel.exists())
        self.assertEqual(self.outside_hash(), before)
        # the link's target is never counted as the cache's size
        self.assertLess(self.item(dry, "cache_other")["bytes"], 6000)

    def test_home_itself_a_junction(self):
        before = self.outside_hash()
        via = self.tmp / "home-link"
        dir_link(via, self.home)
        dir_link(self.home / "cache" / "out", self.outside)
        with self.status():
            rep = HK.clean(via, apply=True)
        self.assertFalse(os.path.lexists(self.home / "cache" / "font-index.json"))
        self.assertFalse(os.path.lexists(self.home / "cache" / "out"))
        self.assertTrue(linksafe.is_link(via))
        self.assertEqual(self.outside_hash(), before)
        self.assertTrue((self.home / "signing" / "key.pem").exists())
        # paths are reported as real paths, never through the link
        for i in rep["items"]:
            self.assertTrue(os.path.normcase(i["path"]).startswith(os.path.normcase(os.path.realpath(self.home))), i)

    def test_refuses_outside_home_and_clients_root(self):
        real = Path(os.path.realpath(self.home))
        with self.assertRaises(errors.Guidance):
            HK.safe_remove(self.clients / "Dr A", real)
        with self.assertRaises(errors.Guidance):
            HK.safe_remove(self.outside, real)
        with self.assertRaises(errors.Guidance) as cm:
            HK.safe_remove(real, real)
        self.assertIn("engine home itself", cm.exception.error)
        with self.assertRaises(errors.Guidance):
            HK.safe_remove(real / ".." / "outside", real)
        self.assertTrue((self.clients / "Dr A" / "assets" / "clip.mp4").exists())
        self.assertTrue(self.sentinel.exists())

    def test_clients_root_under_the_home_is_refused(self):
        inner = self.home / "cache" / "clients"
        (inner / "Dr B" / "media").mkdir(parents=True)
        write(inner / "Dr B" / "media" / "v.mp4", b"v" * 10)
        age_tree(inner)
        with mock.patch.dict(os.environ, {plat.CLIENTS_ENV[0]: str(inner)}):
            with self.assertRaises(errors.Guidance):
                HK.safe_remove(inner, Path(os.path.realpath(self.home)))
            with self.assertRaises(errors.Guidance):          # the clients root inside the item
                HK.safe_remove(self.home / "cache", Path(os.path.realpath(self.home)))
            with self.status():
                rep = HK.clean(self.home, apply=True)
        self.assertTrue((inner / "Dr B" / "media" / "v.mp4").exists())
        self.assertIsNotNone(self.item(rep, "cache_other")["error"])

    def test_hf_snapshot_links_removed_blobs_freed_nothing_outside(self):
        r = self.home / "models" / "models--Systran--faster-whisper-small"
        dir_link(r / "snapshots" / "s2", self.outside)
        before = self.outside_hash()
        with self.status():
            dry = HK.clean(self.home, models=True)
            rep = HK.clean(self.home, apply=True, models=True)
        self.assertFalse(os.path.lexists(r))
        self.assertEqual(self.outside_hash(), before)
        it = self.item(rep, "models_unused")
        self.assertEqual(it["removed"], self.item(dry, "models_unused")["bytes"])
        self.assertGreaterEqual(it["removed"], 2500)

    def test_models_in_use_kept_and_untouched_while_gpu_lock_held(self):
        ready, done = threading.Event(), threading.Event()

        def hold():
            with file_lock.locked(self.home / "locks" / "gpu", wait_s=0):
                ready.set()
                done.wait(30)
        t = threading.Thread(target=hold)
        t.start()
        try:
            self.assertTrue(ready.wait(10))
            before = tree_digest(self.home / "models")
            with self.status():
                rep = HK.clean(self.home, apply=True, models=True)
            it = self.item(rep, "models_unused")
            self.assertFalse(it["removable"])
            self.assertIn("transcri", it["why"])
            self.assertTrue((self.home / "models" / "models--Systran--faster-whisper-small").exists())
            # the old partial download is not a model in use: model_partial still goes; nothing else in models/
            after = [e for e in tree_digest(self.home / "models") if "old.incomplete" not in e[0]]
            self.assertEqual(after, [e for e in before if "old.incomplete" not in e[0]])
        finally:
            done.set()
            t.join(10)

    def test_settings_and_default_model_kept(self):
        with self.status():
            rep = HK.clean(self.home, apply=True, models=True)
        self.assertTrue((self.home / "models" / "models--Systran--faster-whisper-large-v3" / "blobs" / "b1").exists())
        (self.home / "models" / "models--Systran--faster-whisper-large-v3" / "blobs" / "fresh.incomplete").unlink()
        with self.status(), mock.patch.object(HK, "_wanted_models", return_value=({"small": "a test"}, None)):
            self.repo(self.home / "models" / "models--Systran--faster-whisper-small", 100)
            age_tree(self.home / "models" / "models--Systran--faster-whisper-small")
            HK.clean(self.home, apply=True, models=True)
        self.assertTrue((self.home / "models" / "models--Systran--faster-whisper-small").exists())
        self.assertFalse((self.home / "models" / "models--Systran--faster-whisper-large-v3" / "blobs" / "b1").exists())
        self.assertIsNone(self.item(rep, "models_unused")["error"])

    def test_rotate_logs(self):
        logs = self.home / "logs"
        big = write(logs / "big.log", b"B" * 6_000_000)
        write(logs / "big.log.1", b"1")
        write(logs / "big.log.2", b"2")
        write(logs / "big.log.3", b"3")
        write(logs / "serve.log", b"S" * 6_000_000)
        small = write(logs / "small.log", b"s")
        got = HK.rotate_logs(logs)
        self.assertEqual(got, ["big.log"])
        self.assertFalse(big.exists())
        self.assertEqual((logs / "big.log.1").stat().st_size, 6_000_000)
        self.assertEqual((logs / "big.log.2").read_bytes(), b"1")
        self.assertEqual((logs / "big.log.3").read_bytes(), b"2")
        self.assertFalse((logs / "big.log.4").exists())           # keep 3: the oldest copy is gone
        self.assertEqual((logs / "serve.log").stat().st_size, 6_000_000)   # serve rotates its own logs
        self.assertTrue(small.exists())
        self.assertEqual((logs / "time-saved.jsonl").read_bytes(), b"t" * 50)
        self.assertEqual(HK.rotate_logs(logs, max_bytes=0, keep=1), ["pipeline.log", "small.log"])
        self.assertEqual((logs / "pipeline.log.1").read_bytes(), b"p" * 100)

    def test_rotate_logs_refuses_a_linked_folder_and_skips_a_linked_log(self):
        dir_link(self.home / "logs2", self.outside)
        write(self.outside / "o.log", b"o" * 100)
        before = self.outside_hash()
        self.assertEqual(HK.rotate_logs(self.home / "logs2", max_bytes=0), [])
        self.assertEqual(self.outside_hash(), before)
        file_link(self, self.home / "logs" / "l.log", self.outside / "o.log")
        self.assertNotIn("l.log", HK.rotate_logs(self.home / "logs", max_bytes=0))
        self.assertEqual(self.outside_hash(), before)

    def test_auto_prune_respects_cap(self):
        never = mock.patch.object(HK.subprocess, "run", side_effect=AssertionError("auto_prune never runs uv"))
        with never:
            rep = HK.auto_prune(self.home, cap_bytes=10**9)
        self.assertEqual(rep["removed"], [])
        self.assertEqual(rep["uv_bytes"], 1000)
        self.assertEqual(rep["cache_bytes_before"], 2 + 2000 + 3000)     # the uv cache is outside the cap (Q1)
        self.assertTrue((self.home / "cache" / "font-index.json").exists())
        # over the cap: the oldest goes first, only down to the cap
        os.utime(self.home / "cache" / "font-index.json", (OLD - DAY, OLD - DAY))
        total = rep["cache_bytes_before"]
        with never:
            rep = HK.auto_prune(self.home, cap_bytes=total - 1)
        self.assertEqual(rep["removed"], ["font-index.json"])
        self.assertTrue((self.home / "cache" / "stuff" / "deep" / "x.bin").exists())
        self.assertTrue((self.home / "cache" / "uv" / "wheels" / "a.whl").exists())
        self.assertLessEqual(rep["cache_bytes_after"], total - 1)
        self.assertEqual(rep["errors"], [])
        # a cap of 0 still never removes what is in use now, accel.json or the uv cache
        write(self.home / "cache" / "now.json", b"n" * 10)
        with never:
            rep = HK.auto_prune(self.home, cap_bytes=0)
        self.assertTrue((self.home / "cache" / "now.json").exists())
        self.assertTrue((self.home / "cache" / "accel.json").exists())
        self.assertTrue((self.home / "cache" / "uv" / "wheels" / "a.whl").exists())

    def test_auto_prune_never_raises(self):
        with mock.patch.object(HK, "_measure", side_effect=OSError("disk gone")):
            rep = HK.auto_prune(self.home, cap_bytes=0)
        self.assertTrue(rep["errors"])

    def test_item_keys_are_the_documented_set(self):
        with self.status():
            rep = HK.scan(self.home)
        self.assertEqual([i["key"] for i in rep["items"]],
                         ["cache_other", "logs", "runtimes_old", "venv_legacy", "cuda_redist", "queues",
                          "model_partial", "models_unused", "uv_cache"])
        self.assertEqual(list(HK.KEYS), [i["key"] for i in rep["items"]])
        for i in rep["items"]:
            self.assertEqual(set(i), {"key", "path", "bytes", "removable", "why"})
            self.assertIsInstance(i["bytes"], int)
            self.assertTrue(i["why"])
        self.assertEqual(rep["removable_bytes"], sum(i["bytes"] for i in rep["items"] if i["removable"]))
        json.dumps(rep, ensure_ascii=False)


# ------------------------------------------------------------------------------------------------ executor cases
class TestExecutorCases(Home):
    def test_mirror_tree_with_links(self):
        client = self.clients / "Dr A"
        dir_link(self.home / "cache" / "stuff" / "inner", self.home / "cache" / "stuff" / "deep")
        file_link(self, self.home / "cache" / "stuff" / "rel.bin", os.path.join("deep", "x.bin"))
        dir_link(self.home / "cache" / "out", self.outside)
        dir_link(self.home / "logs" / "client", client)
        dir_link(self.home / "models" / "models--Systran--faster-whisper-small" / "snapshots" / "sx", client)
        age_tree(self.home / "cache" / "stuff")
        os.utime(self.home / "cache", (OLD, OLD))
        before_out, before_client = self.outside_hash(), tree_digest(client)
        with self.status():
            HK.clean(self.home, apply=True, models=True)
        self.assertEqual(self.outside_hash(), before_out)
        self.assertEqual(tree_digest(client), before_client)
        self.assertFalse(os.path.lexists(self.home / "cache" / "out"))
        self.assertFalse(os.path.lexists(self.home / "cache" / "stuff"))

    def test_incident_snapshot_junction_into_a_live_tree(self):
        live = self.tmp / "live repo"
        write(live / "src" / "engine.py", b"print('live')" * 50)
        snap = self.home / "cache" / "snap-1"
        snap.mkdir()
        dir_link(snap / "repo", live)
        write(snap / "copy.txt", b"c" * 10)
        age_tree(snap)
        os.utime(self.home / "cache", (OLD, OLD))
        before = tree_digest(live)
        with self.status():
            HK.clean(self.home, apply=True)
        self.assertEqual(tree_digest(live), before)
        self.assertFalse(os.path.lexists(snap))

    def test_models_flag_required(self):
        with self.status():
            rep = HK.clean(self.home, apply=True)
        it = self.item(rep, "models_unused")
        self.assertFalse(it["removable"])
        self.assertGreaterEqual(it["bytes"], 2500)
        self.assertIn("--models", it["why"])
        self.assertEqual(it["removed"], 0)
        self.assertTrue((self.home / "models" / "models--Systran--faster-whisper-small").exists())

    def test_locks_folder_never_removed(self):
        """Ruling Q2: locks/ is never removed (a lock file removed under a waiting process breaks the lock)."""
        stale = write(self.home / "locks" / "old-job.lock", b"", OLD - 30 * DAY)
        os.utime(self.home / "locks", (OLD - 30 * DAY, OLD - 30 * DAY))
        with self.status(), mock.patch.object(HK, "_uv_clean", return_value=None):
            dry = HK.scan(self.home, models=True, uv_cache=True)
            HK.clean(self.home, apply=True, models=True, uv_cache=True)
        HK.auto_prune(self.home, cap_bytes=0)
        self.assertTrue((self.home / "locks" / "gpu.lock").exists())
        self.assertTrue(stale.exists())
        self.assertTrue((self.home / "models" / ".locks" / "models--Systran--faster-whisper-large-v3" / "x.lock")
                        .exists())
        locks = os.path.normcase(os.path.realpath(self.home / "locks"))
        for i in dry["items"]:
            self.assertFalse(os.path.normcase(i["path"]).startswith(locks), i)
        self.assertNotIn("locks", HK._PATHS.values())

    @unittest.skipUnless(IS_WIN, "8.3 short names are a Windows feature")
    def test_windows_short_name_and_case(self):
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        n = ctypes.windll.kernel32.GetShortPathNameW(str(self.home), buf, 1024)
        variants = [Path(str(self.home).upper())]
        if n and buf.value and os.path.normcase(buf.value) != os.path.normcase(str(self.home)):
            variants.append(Path(buf.value))
        real = Path(os.path.realpath(self.home))
        for v in variants:
            with self.assertRaises(errors.Guidance):
                HK.safe_remove(Path(str(self.clients).upper()) / "DR A", real)
            with self.status():
                rep = HK.scan(v)
            self.assertGreater(self.item(rep, "cache_other")["bytes"], 0)
        with self.status():
            HK.clean(variants[-1], apply=True)
        self.assertFalse((self.home / "cache" / "font-index.json").exists())
        self.assertTrue(self.sentinel.exists())

    def test_nfd_and_nfc_names(self):
        nfd = unicodedata.normalize("NFD", "café-é.bin")
        nfc = unicodedata.normalize("NFC", "مُحَمَّد é.bin")
        write(self.home / "cache" / "names" / nfd, b"d" * 11, OLD)
        write(self.home / "cache" / "names" / nfc, b"c" * 13, OLD)
        age_tree(self.home / "cache" / "names")
        with self.status():
            rep = HK.clean(self.home, apply=True)
        self.assertFalse(os.path.lexists(self.home / "cache" / "names"))
        self.assertIsNone(self.item(rep, "cache_other")["error"])

    def test_read_only_file_is_removed(self):
        ro = write(self.home / "cache" / "stuff" / "ro.bin", b"r" * 20, OLD)
        os.chmod(ro, stat.S_IREAD)
        age_tree(self.home / "cache" / "stuff")
        with self.status():
            rep = HK.clean(self.home, apply=True)
        self.assertFalse(os.path.lexists(ro))
        self.assertIsNone(self.item(rep, "cache_other")["error"])

    def test_file_in_use_is_a_plain_line_never_a_crash(self):
        busy = self.home / "cache" / "font-index.json"
        real_unlink = os.unlink

        def unlink(p, *a, **kw):
            if os.path.basename(os.fspath(p)) == "font-index.json":
                raise PermissionError(13, "The process cannot access the file because it is being used")
            return real_unlink(p, *a, **kw)
        with self.status(), mock.patch.object(linksafe.os, "unlink", side_effect=unlink):
            rep = HK.clean(self.home, apply=True)
        it = self.item(rep, "cache_other")
        self.assertTrue(busy.exists())
        self.assertIn("font-index.json", it["error"])
        self.assertNotIn("Traceback", it["error"])
        self.assertFalse((self.home / "cache" / "stuff").exists())       # the rest of the item still went
        self.assertFalse((self.home / "logs" / "pipeline.log.1").exists())   # and the other items
        self.assertGreater(it["removed"], 0)

    @unittest.skipUnless(IS_WIN, "a real Windows sharing violation")
    def test_real_sharing_violation(self):
        busy = self.home / "cache" / "stuff" / "deep" / "x.bin"
        with self.status(), open(busy, "rb"):
            rep = HK.clean(self.home, apply=True)
            it = self.item(rep, "cache_other")
            self.assertTrue(busy.exists())
            self.assertTrue(it["error"])
        self.assertFalse((self.home / "cache" / "font-index.json").exists())

    def test_source_bans_unconfined_deletes(self):
        src = Path(HK.__file__).read_text(encoding="utf-8")
        for banned in ("rmtree", "Remove-Item", "shutil.move", "os.walk(", "shell=True", "os.removedirs",
                       "send2trash"):
            self.assertNotIn(banned, src, banned)


# ------------------------------------------------------------------------------------------------ owner pre-mortem
class TestOwnerPremortem(Home):
    def test_recently_used_model_kept_on_cpu_lane(self):
        med = self.home / "models" / "models--Systran--faster-whisper-small"
        self.assertTrue(HK.mark_model_used(med, self.home))
        with self.status():
            rep = HK.clean(self.home, apply=True, models=True)
        self.assertTrue(med.exists())
        self.assertIn("24", self.item(rep, "models_unused")["why"])
        stamp = med / HK.STAMP
        os.utime(stamp, (OLD, OLD))
        os.utime(med, (OLD, OLD))
        with self.status():
            HK.clean(self.home, apply=True, models=True)
        self.assertFalse(med.exists())

    def test_mark_model_used_never_writes_through_a_link(self):
        dir_link(self.home / "models" / "models--Systran--faster-whisper-tiny", self.outside)
        before = self.outside_hash()
        self.assertFalse(HK.mark_model_used(self.home / "models" / "models--Systran--faster-whisper-tiny",
                                            self.home))
        self.assertFalse(HK.mark_model_used(self.outside, self.home))
        self.assertEqual(self.outside_hash(), before)

    def test_incomplete_only_when_old(self):
        with self.status():
            dry = HK.scan(self.home)
            HK.clean(self.home, apply=True)
        self.assertEqual(self.item(dry, "model_partial")["bytes"], 700)
        blobs = self.home / "models" / "models--Systran--faster-whisper-large-v3" / "blobs"
        self.assertFalse((blobs / "old.incomplete").exists())
        self.assertTrue((blobs / "fresh.incomplete").exists())

    def test_repo_with_a_running_download_is_kept(self):
        med = self.home / "models" / "models--Systran--faster-whisper-small"
        write(med / "blobs" / "dl.incomplete", b"d" * 5)
        with self.status():
            rep = HK.clean(self.home, apply=True, models=True)
        self.assertTrue(med.exists())
        self.assertIn("download", self.item(rep, "models_unused")["why"])

    def test_client_shaped_folder_refused_without_clients_root(self):
        odd = self.home / "cache" / "Dr Lost"
        write(odd / "assets" / "a.mp4", b"a" * 30, OLD)
        (odd / "data").mkdir()
        age_tree(odd)
        with mock.patch.dict(os.environ, {plat.CLIENTS_ENV[0]: ""}), \
                mock.patch.object(HK, "_clients_root", return_value=None):
            with self.assertRaises(errors.Guidance):
                HK.safe_remove(odd, Path(os.path.realpath(self.home)))
            with self.assertRaises(errors.Guidance):
                HK.safe_remove(self.home / "cache", Path(os.path.realpath(self.home)))
            with self.status():
                rep = HK.clean(self.home, apply=True)
        self.assertTrue((odd / "assets" / "a.mp4").exists())
        self.assertIn("Dr Lost", self.item(rep, "cache_other")["error"])
        self.assertFalse((self.home / "cache" / "font-index.json").exists())   # the other entries still went

    def test_runtimes_old_waits_for_link_safe_prune(self):
        with self.status(), mock.patch.object(HK, "_prune_is_link_safe", return_value=False), \
                mock.patch.object(HK.runtime, "prune", side_effect=AssertionError("never called")):
            rep = HK.clean(self.home, apply=True)
        it = self.item(rep, "runtimes_old")
        self.assertFalse(it["removable"])
        self.assertGreaterEqual(it["bytes"], 5000)
        self.assertTrue((self.home / "runtimes" / "r-old").exists())

    def test_runtimes_old_keeps_current_and_previous(self):
        calls = []

        def prune(home, keep, dry_run=False):
            calls.append((sorted(keep), dry_run))
            return {"removed": ["r-old"], "kept": sorted(keep), "failed": {}}
        with self.status(), mock.patch.object(HK, "_prune_is_link_safe", return_value=True), \
                mock.patch.object(HK.runtime, "prune", side_effect=prune):
            dry = HK.scan(self.home)
            HK.clean(self.home, apply=True)
        self.assertTrue(self.item(dry, "runtimes_old")["removable"])
        self.assertEqual(calls[0], (["r-cur", "r-prev"], True))
        self.assertEqual(calls[-1], (["r-cur", "r-prev"], False))

    def test_no_current_runtime_keeps_every_runtime(self):
        (self.home / "current").unlink()
        with self.status(kind="venv", id=None), mock.patch.object(HK, "_prune_is_link_safe", return_value=True), \
                mock.patch.object(HK.runtime, "prune", side_effect=AssertionError("never called")):
            rep = HK.clean(self.home, apply=True)
        self.assertFalse(self.item(rep, "runtimes_old")["removable"])
        self.assertFalse(self.item(rep, "venv_legacy")["removable"])


# ------------------------------------------------------------------------------------------------ my own cases
class TestOwn(Home):
    def test_fresh_cache_entry_kept(self):
        write(self.home / "cache" / "gpu-enable-requirements.txt", b"g" * 9)
        with self.status():
            rep = HK.clean(self.home, apply=True)
        self.assertTrue((self.home / "cache" / "gpu-enable-requirements.txt").exists())
        self.assertTrue((self.home / "cache" / "accel.json").exists())
        self.assertTrue((self.home / "cache" / "uv" / "wheels" / "a.whl").exists())
        self.assertIsNone(self.item(rep, "cache_other")["error"])

    def test_uv_missing_reported_only(self):
        (self.home / "bin" / ("uv.exe" if IS_WIN else "uv")).unlink()
        with self.status(), mock.patch.object(HK.subprocess, "run", side_effect=AssertionError("no uv")):
            rep = HK.clean(self.home, apply=True, uv_cache=True)
        it = self.item(rep, "uv_cache")
        self.assertFalse(it["removable"])
        self.assertEqual(it["bytes"], 1000)
        self.assertIn("uv", it["why"])
        self.assertTrue((self.home / "cache" / "uv" / "wheels" / "a.whl").exists())

    def test_uv_cache_clean_argv_env_and_failures(self):
        seen = {}

        def run(argv, **kw):
            seen.update(argv=argv, **kw)
            (self.home / "cache" / "uv" / "wheels" / "a.whl").unlink()
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        with self.status(), mock.patch.object(HK.subprocess, "run", side_effect=run):
            rep = HK.clean(self.home, apply=True, uv_cache=True)
        uv = os.path.realpath(self.home / "bin" / ("uv.exe" if IS_WIN else "uv"))
        self.assertEqual([os.path.normcase(seen["argv"][0])] + seen["argv"][1:],
                         [os.path.normcase(uv), "cache", "clean"])
        self.assertFalse(seen.get("shell"))
        self.assertEqual(os.path.normcase(seen["env"]["UV_CACHE_DIR"]),
                         os.path.normcase(os.path.realpath(self.home / "cache" / "uv")))
        self.assertEqual(seen["env"]["UV_NO_CONFIG"], "1")
        self.assertTrue(seen["timeout"])
        self.assertEqual(self.item(rep, "uv_cache")["removed"], 1000)
        self.assertTrue(rep["ok"])
        write(self.home / "cache" / "uv" / "wheels" / "a.whl", b"u" * 1000, OLD)
        for err in (subprocess.CompletedProcess(["uv"], 2, b"", b"boom"), subprocess.TimeoutExpired("uv", 1),
                    OSError("cannot start")):
            with self.status(), mock.patch.object(HK.subprocess, "run",
                                                  **({"side_effect": err} if isinstance(err, BaseException)
                                                     else {"return_value": err})):
                rep = HK.clean(self.home, apply=True, uv_cache=True)
            self.assertTrue(self.item(rep, "uv_cache")["error"], err)
            self.assertFalse(rep["ok"], err)

    def test_uv_binary_behind_a_link_is_refused(self):
        exe = self.home / "bin" / ("uv.exe" if IS_WIN else "uv")
        exe.unlink()
        write(self.outside / "evil-uv", b"evil")
        file_link(self, exe, self.outside / "evil-uv")
        with self.status(), mock.patch.object(HK.subprocess, "run", side_effect=AssertionError("ran a linked uv")):
            rep = HK.clean(self.home, apply=True, uv_cache=True)
        self.assertFalse(self.item(rep, "uv_cache")["removable"])

    def test_unknown_repo_never_removed(self):
        with self.status():
            rep = HK.clean(self.home, apply=True, models=True)
        self.assertTrue((self.home / "models" / "models--facebook--wav2vec2-xlsr-arabic" / "blobs" / "b1").exists())
        self.assertIn("wav2vec2", json.dumps(rep))

    def test_venv_legacy_rules(self):
        venv = self.home / "venv"
        for kw in ({"up_to_date": False}, {"kind": "venv"}, {"broken": "r-cur"}):
            with self.status(**kw):
                rep = HK.scan(self.home)
            self.assertFalse(self.item(rep, "venv_legacy")["removable"], kw)
        with self.status(), mock.patch.object(HK.sys, "prefix", str(venv)):
            self.assertFalse(self.item(HK.scan(self.home), "venv_legacy")["removable"])
        with self.status():
            rep = HK.clean(self.home, apply=True)
        self.assertFalse(venv.exists())
        self.assertEqual(self.item(rep, "venv_legacy")["removed"], 600)

    def test_cuda_redist_rules(self):
        lib = self.home / "runtimes" / "r-cur" / "Lib" / "site-packages" / "torch" / "lib"
        with self.status():
            it = self.item(HK.scan(self.home), "cuda_redist")
        self.assertFalse(it["removable"])
        self.assertEqual(it["bytes"], 800)
        write(lib / "cublas64_12.dll", b"x")
        with self.status(), mock.patch.object(HK, "_os_key", return_value="windows"):
            self.assertFalse(self.item(HK.scan(self.home), "cuda_redist")["removable"])   # cublasLt missing
        write(lib / "cublasLt64_12.dll", b"x")
        with self.status(up_to_date=False), mock.patch.object(HK, "_os_key", return_value="windows"):
            self.assertFalse(self.item(HK.scan(self.home), "cuda_redist")["removable"])
        with self.status(), mock.patch.object(HK, "_os_key", return_value="mac"):
            self.assertFalse(self.item(HK.scan(self.home), "cuda_redist")["removable"])
        plib = self.home / "runtimes" / "r-cur" / "lib" / "python3.12" / "site-packages" / "torch" / "lib"
        write(plib / "libcublas.so.12", b"x")
        write(plib / "libcublasLt.so.12", b"x")
        with self.status(), mock.patch.object(HK, "_os_key", return_value="linux"):
            self.assertTrue(self.item(HK.scan(self.home), "cuda_redist")["removable"])
        with self.status(), mock.patch.object(HK, "_os_key", return_value="windows"):
            self.assertTrue(self.item(HK.scan(self.home), "cuda_redist")["removable"])
            rep = HK.clean(self.home, apply=True)
        self.assertFalse((self.home / "cuda").exists())
        self.assertEqual(self.item(rep, "cuda_redist")["removed"], 800)

    def test_queue_folder_behind_a_link_is_refused(self):
        q = self.home / "ae-queue"
        write(self.outside / "x.job.json", b"j", OLD)
        dir_link(q, self.outside)
        before = self.outside_hash()
        with self.status():
            dry = HK.clean(self.home)
            rep = HK.clean(self.home, apply=True)
        # the dry run already names the refusal and never counts a file behind the link
        self.assertIn("ae-queue", self.item(dry, "queues")["error"])
        self.assertEqual(self.item(dry, "queues")["bytes"], 100)
        self.assertEqual(self.outside_hash(), before)
        self.assertIn("ae-queue", self.item(rep, "queues")["error"])
        self.assertFalse((self.home / "ppro-queue" / "job1.job.json").exists())   # the real queue still swept

    def test_hard_link_frees_nothing_and_its_other_name_survives(self):
        src = write(self.home / "cache" / "hl" / "a.bin", b"h" * 100, OLD)
        other = self.outside / "b.bin"
        try:
            os.link(src, other)
        except OSError as e:
            self.skipTest(f"the OS refused a hard link here: {e}")
        age_tree(self.home / "cache" / "hl")
        with self.status():
            dry = HK.scan(self.home)
            HK.clean(self.home, apply=True)
        self.assertEqual(self.item(dry, "cache_other")["bytes"], 2000 + 3000)   # a.bin frees 0 bytes
        self.assertFalse(os.path.lexists(self.home / "cache" / "hl"))
        self.assertEqual(other.read_bytes(), b"h" * 100)

    def test_prune_link_safe_is_read_from_runtime(self):
        with mock.patch.object(HK.runtime, "PRUNE_LINK_SAFE", False, create=True):
            self.assertFalse(HK._prune_is_link_safe())
        with mock.patch.object(HK.runtime, "PRUNE_LINK_SAFE", True, create=True):
            self.assertTrue(HK._prune_is_link_safe())

    def test_one_item_failing_never_stops_the_rest(self):
        with self.status(), mock.patch.object(HK, "_venv_item", side_effect=RuntimeError("boom")):
            rep = HK.clean(self.home, apply=True)
        it = self.item(rep, "venv_legacy")
        self.assertIn("boom", it["error"])
        self.assertFalse(it["removable"])
        self.assertFalse((self.home / "cache" / "font-index.json").exists())

    def test_hostile_names_and_deep_tree(self):
        d = self.home / "cache" / "deep"
        cur = d
        for i in range(40):
            cur = cur / f"d{i}"
        write(cur / "f.bin", b"z" * 3, OLD)
        if not IS_WIN:
            write(self.home / "cache" / "bad\nname", b"b", OLD)
        age_tree(d)
        with self.status():
            rep = HK.clean(self.home, apply=True)
        self.assertFalse(os.path.lexists(d))
        json.dumps(rep, ensure_ascii=False)

    def test_too_deep_tree_is_refused_not_half_deleted(self):
        with mock.patch.object(HK, "_MAX_DEPTH", 3):
            d = self.home / "cache" / "deeper" / "a" / "b" / "c" / "d"
            write(d / "f.bin", b"z", OLD)
            age_tree(self.home / "cache" / "deeper")
            with self.assertRaises(errors.Guidance):
                HK.safe_remove(self.home / "cache" / "deeper", Path(os.path.realpath(self.home)))
        self.assertTrue((d / "f.bin").exists())

    def test_locks_folder_a_link_counts_as_held(self):
        locks = self.home / "locks"
        (locks / "gpu.lock").unlink()
        locks.rmdir()
        dir_link(locks, self.outside)
        with self.status():
            rep = HK.clean(self.home, apply=True, models=True)
        self.assertFalse(self.item(rep, "models_unused")["removable"])
        self.assertTrue((self.home / "models" / "models--Systran--faster-whisper-small").exists())

    def test_lock_file_present_but_free(self):
        with self.status():
            rep = HK.scan(self.home)
        self.assertEqual(rep["removable_bytes"], sum(i["bytes"] for i in rep["items"] if i["removable"]))
        with self.status():
            self.assertTrue(self.item(HK.clean(self.home, models=True), "models_unused")["removable"])

    def test_dry_run_is_deterministic_and_inside_the_home(self):
        with self.status():
            a = json.dumps(HK.scan(self.home), sort_keys=True, ensure_ascii=False)
            b = json.dumps(HK.scan(self.home), sort_keys=True, ensure_ascii=False)
        self.assertEqual(a, b)
        real = os.path.normcase(os.path.realpath(self.home))
        for i in json.loads(a)["items"]:
            self.assertTrue(os.path.normcase(i["path"]).startswith(real), i)

    def test_logs_item_spares_serve_and_live_logs(self):
        with self.status(), mock.patch.object(HK, "LOG_MAX", 50):
            dry = HK.scan(self.home)
            rep = HK.clean(self.home, apply=True)
        self.assertEqual(self.item(dry, "logs")["bytes"], 700)          # pipeline.log.1 + .2, never serve's copies
        logs = self.home / "logs"
        self.assertEqual((logs / "pipeline.log.1").read_bytes(), b"p" * 100)   # the big live log rotated, kept
        self.assertFalse((logs / "pipeline.log").exists())
        self.assertEqual((logs / "serve.log.1").read_bytes(), b"S" * 700)
        self.assertEqual((logs / "serve-audit.log").read_bytes(), b"A" * 900)
        self.assertEqual(self.item(rep, "logs")["removed"], 700)

    def test_home_missing_is_a_plain_answer(self):
        rep = HK.scan(self.tmp / "no home")
        self.assertEqual(rep["removable_bytes"], 0)
        self.assertEqual([i["key"] for i in rep["items"]], list(HK.KEYS))

    def test_ok_field(self):
        with self.status():
            self.assertTrue(HK.clean(self.home, apply=True)["ok"])
        with self.status(), mock.patch.object(HK, "_venv_item", side_effect=RuntimeError("boom")):
            self.assertFalse(HK.clean(self.home)["ok"])


# ------------------------------------------------------------------------------------------------ review round 1
class TestReviewRound1(Home):
    """Findings of the first fresh-eyes review (Opus): each one a test that failed on the reviewed code."""

    def test_runtime_switched_during_apply_is_never_removed(self):
        state = {"id": "r-cur"}

        def status(home):
            return {"kind": "runtime", "id": state["id"], "broken": None, "up_to_date": True,
                    "dir": str(self.home / "runtimes" / state["id"])}

        real_plan = HK._plan

        def plan(*a, **kw):                 # scanned; reel setup switches `current` before the removal starts
            items = real_plan(*a, **kw)
            self.runtime(self.home / "runtimes" / "r-new", time.time())
            (self.home / "current").write_text("r-new\n", encoding="utf-8")
            state["id"] = "r-new"
            return items
        calls = []
        with mock.patch.object(HK.runtime, "status", side_effect=status), \
                mock.patch.object(HK, "_plan", side_effect=plan), \
                mock.patch.object(HK, "_prune_is_link_safe", return_value=True), \
                mock.patch.object(HK.runtime, "prune", side_effect=lambda h, k, dry_run=False: (
                    calls.append((sorted(k), dry_run)) or {"removed": ["r-old"],
                                                         "kept": sorted(k), "failed": {}})):
            rep = HK.clean(self.home, apply=True)
        it = self.item(rep, "runtimes_old")
        self.assertEqual([c for c in calls if not c[1]], [])         # prune never ran for real
        self.assertIn("meanwhile", it["error"])
        self.assertEqual(it["removed"], 0)

    def test_building_runtime_blocks_runtime_removal(self):
        write(self.home / "runtimes" / ".r-x.building", b"{}")
        with self.status(), mock.patch.object(HK, "_prune_is_link_safe", return_value=True), \
                mock.patch.object(HK.runtime, "prune", side_effect=AssertionError("never during a build")):
            rep = HK.clean(self.home, apply=True)
        self.assertFalse(self.item(rep, "runtimes_old")["removable"])
        self.assertIn("building", self.item(rep, "runtimes_old")["why"])

    def test_previous_runtime_is_the_newest_completed_one(self):
        rt = self.home / "runtimes"
        self.runtime(rt / "r-new", time.time())                       # newer, but an abandoned build (no stamp)
        write(rt / "r-old" / runtime.STAMP, json.dumps({"id": "r-old", "created_at": "2026-10-01T00:00:00+00:00"})
              .encode())
        os.utime(rt / "r-old", (OLD, OLD))                            # still the oldest folder
        self.assertEqual(HK._keep_runtimes(rt, "r-cur"), {"r-cur", "r-old"})
        (rt / "r-old" / runtime.STAMP).unlink()
        os.utime(rt / "r-old", (OLD, OLD))                            # unlinking refreshed its folder time
        self.assertEqual(HK._keep_runtimes(rt, "r-cur"), {"r-cur", "r-new"})   # no completed one: the newest

    def test_legacy_home_found_through_its_venv_keeps_it(self):
        user = self.tmp / "user"
        user.mkdir()
        env = {k: "" for k in plat.HOME_ENV}
        with mock.patch.dict(os.environ, env), mock.patch.object(Path, "home", return_value=user), \
                mock.patch.object(plat, "saved_options", return_value={"engine_home": "", "clients_root": ""}):
            with self.status():
                it = self.item(HK.clean(self.home, apply=True), "venv_legacy")
            self.assertFalse(it["removable"])
            self.assertIn("venv", it["why"])
            self.assertTrue((self.home / "venv").exists())
            dir_link(user / plat.HOME_NAME, self.home)               # ~/.whynot-cut with `current`: found anyway
            with self.status():
                self.assertTrue(self.item(HK.scan(self.home), "venv_legacy")["removable"])
        with mock.patch.dict(os.environ, env), mock.patch.object(Path, "home", return_value=self.tmp / "nobody"), \
                mock.patch.object(plat, "saved_options", return_value={"engine_home": str(self.home),
                                                                       "clients_root": ""}):
            with self.status():
                self.assertTrue(self.item(HK.scan(self.home), "venv_legacy")["removable"])
        # an environment variable naming the home is not enough: other launchers don't have it (review round 2)
        with mock.patch.dict(os.environ, dict(env, **{plat.HOME_ENV[2]: str(self.home)})), \
                mock.patch.object(Path, "home", return_value=self.tmp / "nobody"), \
                mock.patch.object(plat, "saved_options", return_value={"engine_home": "", "clients_root": ""}):
            with self.status():
                self.assertFalse(self.item(HK.scan(self.home), "venv_legacy")["removable"])

    def test_a_kept_link_is_a_note_not_a_failure(self):
        stuff = self.home / "cache-real"
        os.replace(self.home / "cache", stuff)
        dir_link(self.home / "cache", stuff)
        with self.status():
            rep = HK.clean(self.home)
        self.assertTrue(rep["ok"])
        self.assertIn("link", self.item(rep, "cache_other")["error"])

    def test_auto_prune_fresh_entries_count_as_fixed(self):
        write(self.home / "cache" / "busy.bin", b"b" * 5000)        # in use now: can't go
        rep = HK.auto_prune(self.home, cap_bytes=4000)              # accel 2 + busy 5000 > 4000
        self.assertEqual(rep["removed"], [])
        self.assertTrue((self.home / "cache" / "font-index.json").exists())
        self.assertTrue(any("over the cap" in e for e in rep["errors"]))

    def test_auto_prune_uv_cache_is_outside_the_cap(self):
        """Ruling Q1: the uv cache goes only with the editor's opt-in, so after a handoff it is neither cleaned nor
        counted: a big uv cache (a cuda runtime's torch wheels) never empties the rest, never prints "over the cap"."""
        write(self.home / "cache" / "uv" / "wheels" / "torch.whl", b"t" * 20000, OLD)
        with mock.patch.object(HK.subprocess, "run", side_effect=AssertionError("auto_prune never runs uv")):
            rep = HK.auto_prune(self.home, cap_bytes=6000)          # uv 21000 > cap; the rest 5002 is under it
        self.assertEqual(rep["removed"], [])
        self.assertEqual(rep["errors"], [])
        self.assertEqual(rep["uv_bytes"], 21000)
        self.assertTrue((self.home / "cache" / "font-index.json").exists())
        self.assertTrue((self.home / "cache" / "stuff").exists())
        self.assertTrue((self.home / "cache" / "uv" / "wheels" / "torch.whl").exists())

    def test_entries_that_become_busy_after_the_scan_are_kept(self):
        real_plan = HK._plan
        font = self.home / "cache" / "font-index.json"
        part = self.home / "models" / "models--Systran--faster-whisper-large-v3" / "blobs" / "old.incomplete"

        def plan(*a, **kw):
            items = real_plan(*a, **kw)
            os.utime(font, None)                 # a font index rebuild starts after the scan
            os.utime(part, None)                 # a download resumes the old partial file
            return items
        with self.status(), mock.patch.object(HK, "_plan", side_effect=plan):
            rep = HK.clean(self.home, apply=True)
        self.assertTrue(font.exists())
        self.assertTrue(part.exists())
        self.assertFalse((self.home / "cache" / "stuff").exists())
        self.assertIsNone(self.item(rep, "cache_other")["error"])

    def test_gpu_locks_held_during_model_removal(self):
        seen = []
        real = HK.safe_remove

        def probe(p, a, within=None):
            if within == "models" and Path(p).name.startswith("models--"):
                box = {}

                def other():                      # another job (thread) tries the GPU lock meanwhile
                    try:
                        with file_lock.locked(self.home / "locks" / "gpu", wait_s=0):
                            box["got"] = True
                    except file_lock.LockTimeout:
                        box["got"] = False
                t = threading.Thread(target=other)
                t.start()
                t.join(10)
                seen.append(box.get("got"))
            return real(p, a, within)
        with self.status(), mock.patch.object(HK, "safe_remove", side_effect=probe):
            HK.clean(self.home, apply=True, models=True)
        self.assertIn(False, seen)
        self.assertNotIn(True, seen)
        with file_lock.locked(self.home / "locks" / "gpu", wait_s=0):    # released afterwards
            pass

    def test_gpu_job_started_after_the_scan_stops_model_removal(self):
        ready, done = threading.Event(), threading.Event()
        real_plan = HK._plan

        def hold():
            with file_lock.locked(self.home / "locks" / "gpu", wait_s=0):
                ready.set()
                done.wait(30)
        t = threading.Thread(target=hold)

        def plan(*a, **kw):
            items = real_plan(*a, **kw)          # scanned while free; a transcription starts right after
            t.start()
            ready.wait(10)
            return items
        try:
            with self.status(), mock.patch.object(HK, "_plan", side_effect=plan):
                rep = HK.clean(self.home, apply=True, models=True)
        finally:
            done.set()
            t.join(10)
        it = self.item(rep, "models_unused")
        self.assertTrue(it["removable"])
        self.assertIn("meanwhile", it["error"])
        self.assertTrue((self.home / "models" / "models--Systran--faster-whisper-small").exists())

    def test_gpu_lock_held_by_another_process(self):
        code = ("import sys; sys.path.insert(0, sys.argv[1]); from lib import file_lock; "
                "from pathlib import Path\nwith file_lock.locked(Path(sys.argv[2]), wait_s=5):\n"
                "    print('ready', flush=True); sys.stdin.readline()")
        with subprocess.Popen([sys.executable, "-B", "-c", code, str(Path(HK.__file__).parents[1]),
                               str(self.home / "locks" / "gpu")], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              text=True) as p:          # the with-block closes both pipes and waits (T2.17)
            try:
                self.assertEqual(p.stdout.readline().strip(), "ready")
                with self.status():
                    rep = HK.clean(self.home, apply=True, models=True)
                self.assertFalse(self.item(rep, "models_unused")["removable"])
                self.assertTrue((self.home / "models" / "models--Systran--faster-whisper-small").exists())
            finally:
                p.stdin.write("\n")
                p.stdin.flush()
                p.wait(30)

    def test_queue_file_sweep_could_not_remove_is_reported(self):
        with self.status(), mock.patch("lib.cep_queue.sweep", return_value=[]):
            rep = HK.clean(self.home, apply=True)
        it = self.item(rep, "queues")
        self.assertIn("could not be removed", it["error"])
        self.assertEqual(it["removed"], 0)


# ------------------------------------------------------------------------------------------------ fix round 1
class TestFixRound1(Home):
    """Review 36cd6ad (FAIL r1) and the executor's rulings Q1-Q4: each test failed on the reviewed code (red-before.log)
    or kills a named mutant (work/t415-fix1/mut.log)."""

    def setUp(self):
        super().setUp()
        self.small = self.home / "models" / "models--Systran--faster-whisper-small"
        self.medium = self.home / "models" / "models--Systran--faster-whisper-medium"

    def client_file(self, rel: str, data: bytes, client: str = "Dr A") -> Path:
        return write(self.clients / client / rel, data)

    def models_apply(self, **kw):
        with self.status():
            dry = HK.scan(self.home, models=True)
            rep = HK.clean(self.home, apply=True, models=True, **kw)
        return self.item(dry, "models_unused"), self.item(rep, "models_unused")

    # ---------------------------------------------------------------- Q3 / P2-1: --models never removes a model in use
    def test_fallback_models_kept(self):
        self.repo(self.home / "models" / "models--dropbox-dash--faster-whisper-large-v3-turbo", 1200)
        self.repo(self.home / "models" / "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo", 1100)
        age_tree(self.home / "models")
        dry, it = self.models_apply()
        for n in ("medium", "large-v3-turbo"):
            self.assertIn(n, dry["why"])
        self.assertTrue(self.medium.exists())
        self.assertTrue((self.home / "models" / "models--dropbox-dash--faster-whisper-large-v3-turbo").exists())
        self.assertTrue((self.home / "models" / "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo").exists())
        self.assertFalse(self.small.exists())
        self.assertEqual(it["removed"], dry["bytes"])

    def test_config_default_model_honoured(self):
        real = common.load_config

        def cfg(name, ctx=None):
            if name == "transcription.json":
                return {"default_model": "small", "fallback_models": []}
            return real(name, ctx)
        with mock.patch.object(common, "load_config", side_effect=cfg):
            dry, it = self.models_apply()
        self.assertTrue(self.small.exists())
        self.assertIn("small (in use: the default model)", dry["why"])

    def test_client_settings_model_kept(self):
        self.client_file(".claude/whynot-cut.local.md", b"---\nwhisper_model: small\n---\n")
        dry, it = self.models_apply()
        self.assertTrue(self.small.exists())
        self.assertIn("Dr A", dry["why"])
        self.assertIsNone(it["error"])

    def test_client_reel_profile_model_kept(self):
        self.client_file("output/client_database/reel-profile/transcription.json", b'{"default_model": "small"}')
        self.models_apply()
        self.assertTrue(self.small.exists())
        # a shipped profile (named by --profile or the client's profile.json) counts too
        (self.clients / "Dr A" / "output" / "client_database" / "reel-profile" / "transcription.json").unlink()
        shipped = self.tmp / "profiles"
        write(shipped / "clinic-x" / "profile.json", b'{"id": "clinic-x"}')
        write(shipped / "clinic-x" / "transcription.json", b'{"fallback_models": ["small"]}')
        with mock.patch.object(common, "PROFILES_DIR", shipped):
            self.models_apply()
        self.assertTrue(self.small.exists())
        with mock.patch.object(common, "PROFILES_DIR", self.tmp / "no-profiles"):
            self.models_apply()
        self.assertFalse(self.small.exists())

    def test_unreadable_client_settings_keeps_every_model(self):
        self.client_file(".claude/whynot-cut.local.md", b"---\nwhisper_model: large-v3\n---\n\xff\xfe not utf-8")
        dry, it = self.models_apply()
        self.assertFalse(dry["removable"])
        self.assertIn("can't be read", dry["why"])
        self.assertTrue(self.small.exists())
        self.assertEqual(it["removed"], 0)

    def test_broken_reel_profile_keeps_every_model(self):
        self.client_file("output/client_database/reel-profile/transcription.json", b'{"default_model": ')
        dry, _ = self.models_apply()
        self.assertFalse(dry["removable"])
        self.assertIn("Dr A", dry["why"])
        self.assertTrue(self.small.exists())
        shipped = self.tmp / "profiles"
        write(shipped / "clinic-x" / "transcription.json", b"{nope")
        with mock.patch.object(common, "PROFILES_DIR", shipped):
            (self.clients / "Dr A" / "output" / "client_database" / "reel-profile" / "transcription.json").unlink()
            dry, _ = self.models_apply()
        self.assertFalse(dry["removable"])
        self.assertTrue(self.small.exists())

    def test_missing_clients_root_keeps_every_model(self):
        with mock.patch.dict(os.environ, {plat.CLIENTS_ENV[0]: str(self.tmp / "unplugged disk")}):
            dry, _ = self.models_apply()
        self.assertFalse(dry["removable"])
        self.assertIn("can't be read", dry["why"])
        self.assertTrue(self.small.exists())
        with mock.patch.object(HK, "_clients_root", side_effect=errors.Guidance("can't read the clients folder "
                                                                                "setting", "fix it")):
            dry, _ = self.models_apply()
        self.assertFalse(dry["removable"])
        self.assertTrue(self.small.exists())

    def test_no_clients_root_still_removes_unused(self):
        with mock.patch.dict(os.environ, {k: "" for k in plat.CLIENTS_ENV}), \
                mock.patch.object(HK, "_clients_root", return_value=None):
            dry, it = self.models_apply()
        self.assertTrue(dry["removable"])
        self.assertFalse(self.small.exists())
        self.assertTrue(self.medium.exists())

    # ---------------------------------------------------------------- Q1 / P2-2: the uv cache is its own opt-in
    def test_uv_cache_is_opt_in_with_the_arabic_line(self):
        self.assertNotIn("cache_uv", HK.KEYS)
        with self.status(), mock.patch.object(HK.subprocess, "run", side_effect=AssertionError("never without opt-in")):
            dry = HK.scan(self.home, models=True)
            rep = HK.clean(self.home, apply=True, models=True)
        for r in (dry, rep):
            it = self.item(r, "uv_cache")
            self.assertFalse(it["removable"])
            self.assertEqual(it["bytes"], 1000)
            self.assertIn("التثبيت الجاي هيحمّل تاني (~1 MB)", it["why"])
            self.assertIn("the next setup downloads it again", it["why"])
            self.assertIn("--uv-cache", it["why"])
        self.assertTrue((self.home / "cache" / "uv" / "wheels" / "a.whl").exists())
        self.assertEqual(self.item(rep, "uv_cache")["removed"], 0)
        with self.status():
            it = self.item(HK.scan(self.home, uv_cache=True), "uv_cache")
        self.assertTrue(it["removable"])
        self.assertIn("التثبيت الجاي هيحمّل تاني", it["why"])
        write(self.home / "cache" / "uv" / "wheels" / "big.whl", b"w" * 2_600_000, OLD)
        with self.status():
            self.assertIn("(~3 MB)", self.item(HK.scan(self.home), "uv_cache")["why"])

    def test_uv_prune_is_gone(self):
        src = Path(HK.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"cache", "prune"', src)
        self.assertFalse(hasattr(HK, "_uv_prune"))

    def test_uv_cache_kept_while_a_runtime_builds(self):
        lock = self.home / "runtimes" / ".r-x.building"
        write(lock, b"{}")
        with self.status(), mock.patch.object(HK.subprocess, "run", side_effect=AssertionError("during a build")):
            rep = HK.clean(self.home, apply=True, uv_cache=True)
        it = self.item(rep, "uv_cache")
        self.assertFalse(it["removable"])
        self.assertIn("reel setup", it["why"])
        lock.unlink()
        real_plan = HK._plan

        def plan(*a, **kw):                  # setup starts building right after the scan
            items = real_plan(*a, **kw)
            write(lock, b"{}")
            return items
        with self.status(), mock.patch.object(HK, "_plan", side_effect=plan), \
                mock.patch.object(HK.subprocess, "run", side_effect=AssertionError("during a build")):
            rep = HK.clean(self.home, apply=True, uv_cache=True)
        it = self.item(rep, "uv_cache")
        self.assertTrue(it["removable"])
        self.assertIn("reel setup", it["error"])
        self.assertTrue((self.home / "cache" / "uv" / "wheels" / "a.whl").exists())

    def test_uv_cache_link_pointing_outside_is_refused(self):
        uvd = self.home / "cache" / "uv"
        dir_link(uvd / "inner", uvd / "wheels")              # a link that stays inside the uv cache is fine
        os.utime(uvd, (OLD, OLD))
        with self.status():
            self.assertTrue(self.item(HK.scan(self.home, uv_cache=True), "uv_cache")["removable"])
        dir_link(uvd / "out", self.outside)
        before = self.outside_hash()
        with self.status(), mock.patch.object(HK.subprocess, "run", side_effect=AssertionError("ran with a link out")):
            rep = HK.clean(self.home, apply=True, uv_cache=True)
        it = self.item(rep, "uv_cache")
        self.assertFalse(it["removable"])
        self.assertIn("link", it["why"])
        self.assertEqual(self.outside_hash(), before)
        (os.rmdir if IS_WIN else os.unlink)(uvd / "out")    # remove the junction / symlink as a name
        real_plan = HK._plan

        def plan(*a, **kw):                  # the link appears after the scan, before uv runs
            items = real_plan(*a, **kw)
            dir_link(uvd / "out", self.outside)
            return items
        with self.status(), mock.patch.object(HK, "_plan", side_effect=plan), \
                mock.patch.object(HK.subprocess, "run", side_effect=AssertionError("ran with a link out")):
            rep = HK.clean(self.home, apply=True, uv_cache=True)
        it = self.item(rep, "uv_cache")
        self.assertTrue(it["removable"])
        self.assertIn("link appeared", it["error"])
        self.assertEqual(self.outside_hash(), before)

    def test_auto_prune_never_runs_uv(self):
        write(self.home / "cache" / "uv" / "wheels" / "torch.whl", b"t" * 9000, OLD)
        with mock.patch.object(HK.subprocess, "run", side_effect=AssertionError("auto_prune ran uv")):
            rep = HK.auto_prune(self.home, cap_bytes=0)
        self.assertTrue((self.home / "cache" / "uv" / "wheels" / "torch.whl").exists())
        self.assertFalse(any("uv" in e for e in rep["errors"]), rep["errors"])

    def test_uv_cache_runs_last(self):
        self.assertEqual(HK.KEYS[-2:], ("models_unused", "uv_cache"))
        order = []
        real = HK.safe_remove

        def rm(p, a, within=None):
            order.append(("rm", Path(p).name))
            return real(p, a, within)
        with self.status(), mock.patch.object(HK, "safe_remove", side_effect=rm), \
                mock.patch.object(HK, "_uv_clean", side_effect=lambda *a, **kw: order.append(("uv",))):
            HK.clean(self.home, apply=True, models=True, uv_cache=True)
        self.assertGreater(len(order), 3)
        self.assertEqual(order[-1], ("uv",))
        self.assertEqual(order.count(("uv",)), 1)

    # ---------------------------------------------------------------- P2-3: the four guards no test pinned
    def test_venv_and_cuda_rechecked_before_removal(self):
        lib = self.home / "runtimes" / "r-cur" / "Lib" / "site-packages" / "torch" / "lib"
        write(lib / "cublas64_12.dll", b"x")
        write(lib / "cublasLt64_12.dll", b"x")
        state = {"ok": True}

        def status(home):
            return {"kind": "runtime", "id": "r-cur", "broken": None, "up_to_date": state["ok"],
                    "dir": str(self.home / "runtimes" / "r-cur")}
        real_plan = HK._plan

        def plan(*a, **kw):                  # the scan saw an up-to-date runtime; setup found it stale right after
            items = real_plan(*a, **kw)
            state["ok"] = False
            return items
        with mock.patch.object(HK.runtime, "status", side_effect=status), \
                mock.patch.object(HK, "_os_key", return_value="windows"), \
                mock.patch.object(HK, "_plan", side_effect=plan):
            rep = HK.clean(self.home, apply=True)
        for key in ("venv_legacy", "cuda_redist"):
            self.assertTrue(self.item(rep, key)["removable"], key)
            self.assertEqual(self.item(rep, key)["removed"], 0, key)
        self.assertTrue((self.home / "venv").exists())
        self.assertTrue((self.home / "cuda" / "bin" / "cublas64_12.dll").exists())

    def _locks_then(self, act):
        real = HK._gpu_locks

        @contextlib.contextmanager
        def locks(a):
            with real(a) as got:
                act()                        # something happens after the scan, while we wait for the locks
                yield got
        return mock.patch.object(HK, "_gpu_locks", side_effect=locks)

    def test_model_rechecked_under_the_gpu_lock(self):
        with self._locks_then(lambda: write(self.small / HK.STAMP, b"now\n")):
            dry, it = self.models_apply()
        self.assertTrue(dry["removable"])
        self.assertTrue(self.small.exists())
        self.assertEqual(it["removed"], 0)
        (self.small / HK.STAMP).unlink()
        age_tree(self.small)
        with self._locks_then(lambda: write(self.small / "blobs" / "dl.incomplete", b"d")):
            self.models_apply()
        self.assertTrue(self.small.exists())

    def test_unreadable_gpu_lock_counts_as_busy(self):
        for err in (PermissionError(13, "Access is denied"), errors.Guidance("the lock file is odd", "x")):
            with self.status(), mock.patch.object(file_lock, "locked", side_effect=err):
                rep = HK.clean(self.home, apply=True, models=True)
            it = self.item(rep, "models_unused")
            self.assertFalse(it["removable"], err)
            self.assertIn("can't be checked", it["why"])
            self.assertTrue(self.small.exists())

    def test_unknown_path_kind_is_never_a_folder(self):
        real = linksafe.is_link
        odd = {os.path.normcase(os.path.realpath(p)) for p in (self.home / "cache", self.small)}

        def is_link(p):
            if os.path.normcase(os.path.realpath(p)) in odd:
                raise errors.Guidance("can't tell whether this is a link (PermissionError)", "x")
            return real(p)
        with self.status(), mock.patch.object(linksafe, "is_link", side_effect=is_link):
            dry = HK.scan(self.home, models=True)
        self.assertFalse(self.item(dry, "cache_other")["removable"])
        self.assertIn("link", self.item(dry, "cache_other")["why"])
        it = self.item(dry, "models_unused")
        self.assertNotIn("small", it["why"])
        self.assertEqual(it["bytes"], 0)

    # ---------------------------------------------------------------- Q4 / P3-1: a half-removed runtime
    def half(self, name="r-half", size=9000) -> Path:
        d = self.home / "runtimes" / name
        write(d / ("Scripts" if IS_WIN else "bin") / PY, b"h" * size, OLD)
        age_tree(d)
        return d

    def old_prune(self, safe: bool = False):
        """runtime.prune as it is at HEAD (no link-safe mode) whether or not hooks/T4.15 is applied to this tree."""
        return mock.patch.object(HK, "_prune_is_link_safe", return_value=safe)

    def test_half_removed_with_the_link_safe_prune(self):
        d = self.half()
        calls = []

        def prune(home, keep, dry_run=False):
            calls.append((sorted(keep), dry_run))
            return {"removed": ["r-old"], "kept": sorted(keep), "failed": {}}
        with self.status(), self.old_prune(True), mock.patch.object(HK.runtime, "prune", side_effect=prune):
            dry = HK.scan(self.home)
            rep = HK.clean(self.home, apply=True)
        it = self.item(dry, "runtimes_old")
        self.assertIn("r-half", it["why"])
        self.assertEqual(it["bytes"], 9000 + HK._measure(self.home / "runtimes" / "r-old")["bytes"])
        self.assertFalse(os.path.lexists(d))
        self.assertEqual(calls[-1], (["r-cur", "r-prev"], False))
        self.assertGreaterEqual(self.item(rep, "runtimes_old")["removed"], 9000)

    def test_half_removed_runtime_listed_and_removed(self):
        d = self.half()
        seen = []
        real = HK.safe_remove

        def rm(p, a, within=None):
            seen.append((Path(p).name, within))
            return real(p, a, within)
        with self.status(), mock.patch.object(HK, "safe_remove", side_effect=rm), self.old_prune():
            dry = HK.scan(self.home)
            rep = HK.clean(self.home, apply=True)
        it = self.item(dry, "runtimes_old")
        self.assertTrue(it["removable"])
        self.assertIn("نسخة ناقصة / half-removed", it["why"])
        self.assertIn("r-half", it["why"])
        self.assertEqual(it["bytes"], 9000)               # the full old runtimes wait for the link-safe prune
        self.assertFalse(os.path.lexists(d))
        self.assertIn(("r-half", "runtimes"), seen)
        self.assertEqual(self.item(rep, "runtimes_old")["removed"], 9000)
        self.assertIsNone(self.item(rep, "runtimes_old")["error"])
        for keep in ("r-cur", "r-prev", "r-old"):
            self.assertTrue((self.home / "runtimes" / keep / "pyvenv.cfg").exists(), keep)

    def test_half_removed_runtime_never_current_or_during_build(self):
        (self.home / "runtimes" / "r-cur" / "pyvenv.cfg").unlink()       # the current one, damaged: never "half"
        with self.status(id="R-CUR"), mock.patch.object(HK, "_FOLD", True):
            rep = HK.clean(self.home, apply=True)
        self.assertNotIn("half-removed", self.item(rep, "runtimes_old")["why"])
        self.assertTrue((self.home / "runtimes" / "r-cur").exists())
        self.assertTrue((self.home / "runtimes" / "r-prev" / "pyvenv.cfg").exists())
        d = self.half()
        write(self.home / "runtimes" / ".r-x.building", b"{}")
        with self.status():
            rep = HK.clean(self.home, apply=True)
        self.assertFalse(self.item(rep, "runtimes_old")["removable"])
        self.assertTrue(d.exists())

    def test_half_removed_rechecked_before_removal(self):
        d = self.half()
        real_plan = HK._plan

        def plan(*a, **kw):                  # setup re-creates it as a runtime right after the scan
            items = real_plan(*a, **kw)
            write(d / "pyvenv.cfg", b"home = x\n")
            return items
        with self.status(), mock.patch.object(HK, "_plan", side_effect=plan), self.old_prune():
            rep = HK.clean(self.home, apply=True)
        self.assertTrue((d / "pyvenv.cfg").exists())
        self.assertEqual(self.item(rep, "runtimes_old")["removed"], 0)

    def test_half_removed_link_never_entered(self):
        write(self.outside / "rt" / "Scripts" / PY, b"o" * 50)
        lnk = self.home / "runtimes" / "r-lnk"
        dir_link(lnk, self.outside / "rt")
        before = self.outside_hash()
        with self.status(), self.old_prune():
            dry = HK.scan(self.home)
            HK.clean(self.home, apply=True)
        self.assertNotIn("r-lnk", self.item(dry, "runtimes_old")["why"])
        self.assertFalse(self.item(dry, "runtimes_old")["removable"])
        self.assertTrue(linksafe.is_link(lnk))                 # a runtime link is runtime.prune's (it unlinks names)
        self.assertEqual(self.outside_hash(), before)

    # ---------------------------------------------------------------- the review's P3s
    def test_an_apply_error_makes_ok_false(self):
        def item(a, models, now):
            return HK._item("cache_other", a, 5, True, "x", do=lambda: (0, "boom: a file is held"))
        with self.status(), mock.patch.object(HK, "_cache_other_item", side_effect=item):
            rep = HK.clean(self.home, apply=True)
            self.assertTrue(HK.clean(self.home)["ok"])     # the dry run runs no do()
        self.assertFalse(rep["ok"])
        self.assertIn("boom", self.item(rep, "cache_other")["error"])

    def test_model_partial_only_in_blobs(self):
        face = write(self.home / "models" / "face" / "detector.onnx.incomplete", b"f" * 300, OLD)
        snap = write(self.small / "snapshots" / "s1" / "w.bin.incomplete", b"s" * 200, OLD)
        with self.status():
            dry = HK.scan(self.home)
            HK.clean(self.home, apply=True)
        self.assertEqual(self.item(dry, "model_partial")["bytes"], 700)
        self.assertTrue(face.exists())
        self.assertTrue(snap.exists())

    def test_mark_model_used_only_inside_models(self):
        target = self.home / "cache" / "stuff"
        self.assertFalse(HK.mark_model_used(target, self.home))
        self.assertFalse((target / HK.STAMP).exists())
        self.assertTrue(HK.mark_model_used(self.small, self.home))

    def test_gpu_lock_failure_says_what_failed(self):
        with self.status(), mock.patch.object(linksafe, "makedirs", side_effect=PermissionError(13, "Access is denied")):
            rep = HK.clean(self.home, apply=True, models=True)
        it = self.item(rep, "models_unused")
        self.assertNotIn("started meanwhile", it["error"])
        self.assertIn("GPU lock could not be taken", it["error"])
        self.assertTrue(self.small.exists())

    def test_client_shaped_home_refuses_the_whole_run(self):
        (self.home / "assets").mkdir()
        (self.home / "data").mkdir()
        with self.status(), mock.patch.object(HK.subprocess, "run", side_effect=AssertionError("refused run")):
            dry = HK.scan(self.home, models=True, uv_cache=True)
            rep = HK.clean(self.home, apply=True, models=True, uv_cache=True)
        auto = HK.auto_prune(self.home, cap_bytes=2)     # = accel.json: everything old would go if not refused
        for i in dry["items"] + rep["items"]:
            self.assertFalse(i["removable"], i)
        self.assertTrue(all("client" in i["error"] for i in rep["items"]))
        self.assertFalse(rep["ok"])
        self.assertEqual(rep["freed_bytes"], 0)
        self.assertEqual(auto["removed"], [])
        self.assertTrue(auto["errors"])
        for keep in ("cache/font-index.json", "logs/pipeline.log.1", "venv", "models/models--Systran--faster-whisper-small"):
            self.assertTrue(os.path.lexists(self.home / keep), keep)

    def test_home_inside_a_client_folder_or_the_clients_root_is_refused(self):
        client = self.clients / "Dr A"
        write(client / ".whynot-client", b"{}")
        inner = client / "engine"
        os.replace(self.home, inner)
        with mock.patch.object(HK, "_clients_root", return_value=None), self.status():
            rep = HK.clean(inner, apply=True)
        self.assertEqual(rep["freed_bytes"], 0)
        self.assertTrue((inner / "cache" / "font-index.json").exists())
        loose = self.clients / "engine-home"
        os.replace(inner, loose)                              # not in a client, but inside the clients root
        with self.status():
            rep = HK.clean(loose, apply=True)
        self.assertEqual(rep["freed_bytes"], 0)
        self.assertTrue((loose / "cache" / "font-index.json").exists())
        self.assertIn("clients folder", self.item(rep, "cache_other")["error"])

    def test_current_runtime_case_variant_keeps_the_previous(self):
        rt = self.home / "runtimes"
        with mock.patch.object(HK, "_FOLD", True):
            self.assertEqual(HK._keep_runtimes(rt, "R-CUR"), {"r-cur", "r-prev"})
        with mock.patch.object(HK, "_FOLD", False):
            self.assertEqual(HK._keep_runtimes(rt, "r-cur"), {"r-cur", "r-prev"})


# ------------------------------------------------------------------------------------------------ fix round 2
class TestFixRound2(Home):
    """Review 41bc006 (FAIL r2). P2-2: ruling Q3's three branches no test pinned (each test is red on the reviewer's
    mutant C3, C5 or C6, lane5/work/41bc006/mutate.py). P3-1: the cheap guards (H1, U1, U3/U4, U6, R4, and a build
    re-checked before each half-removed runtime). P3-2: removable_bytes counts only what a yes frees."""

    def setUp(self):
        super().setUp()
        self.small = self.home / "models" / "models--Systran--faster-whisper-small"
        self.medium = self.home / "models" / "models--Systran--faster-whisper-medium"

    def models_apply(self, **kw):
        with self.status():
            dry = HK.scan(self.home, models=True)
            rep = HK.clean(self.home, apply=True, models=True, **kw)
        return self.item(dry, "models_unused"), self.item(rep, "models_unused")

    def client(self, name: str) -> Path:
        d = self.clients / name
        (d / "assets").mkdir(parents=True, exist_ok=True)
        (d / "data").mkdir(parents=True, exist_ok=True)
        return d

    # ---------------------------------------------------------------- P2-2 / Q3: the three unpinned branches
    def test_the_second_client_s_model_is_kept(self):                 # mutant C3 (only the first client read)
        self.client("Dr B")
        write(self.clients / "Dr B" / ".claude" / "whynot-cut.local.md", b"---\nwhisper_model: small\n---\n")
        with mock.patch.object(common, "PROFILES_DIR", self.tmp / "no-profiles"):
            dry, it = self.models_apply()
        self.assertIn("small (in use: client Dr B)", dry["why"])
        self.assertTrue(self.small.exists())
        self.assertIsNone(it["error"])
        self.assertEqual(it["removed"], 0)

    def test_a_shipped_profile_s_default_model_is_kept(self):          # mutant C5 (default_model dropped)
        shipped = self.tmp / "profiles"
        write(shipped / "clinic-x" / "profile.json", b'{"id": "clinic-x"}')
        write(shipped / "clinic-x" / "transcription.json", b'{"default_model": "small"}')
        with mock.patch.object(common, "PROFILES_DIR", shipped):    # no client names clinic-x
            dry, it = self.models_apply()
        self.assertIn("small (in use: profile clinic-x)", dry["why"])
        self.assertTrue(self.small.exists())
        self.assertEqual(it["removed"], 0)

    def test_a_client_reel_profile_s_fallback_is_kept(self):           # mutant C6 (fallback_models dropped)
        write(self.clients / "Dr A" / "output" / "client_database" / "reel-profile" / "transcription.json",
              b'{"fallback_models": ["small"]}')
        with mock.patch.object(common, "PROFILES_DIR", self.tmp / "no-profiles"):   # nothing shipped carries it
            dry, it = self.models_apply()
        self.assertIn("small (in use: client Dr A)", dry["why"])
        self.assertTrue(self.small.exists())
        self.assertEqual(it["removed"], 0)

    # ---------------------------------------------------------------- P3-1: the cheap guards
    def test_home_two_levels_inside_a_client_is_refused(self):         # mutant H1 (only the direct parent)
        client = self.clients / "Dr A"
        write(client / ".whynot-client", b"{}")
        inner = client / "sub" / "engine"
        inner.parent.mkdir()
        os.replace(self.home, inner)
        with mock.patch.object(HK, "_clients_root", return_value=None), self.status():
            rep = HK.clean(inner, apply=True, models=True)
            auto = HK.auto_prune(inner, cap_bytes=2)
        self.assertEqual(rep["freed_bytes"], 0)
        self.assertIn("inside a client folder (Dr A)", self.item(rep, "cache_other")["error"])
        self.assertEqual(auto["removed"], [])
        for keep in ("cache/font-index.json", "logs/pipeline.log.1", "models/models--Systran--faster-whisper-small"):
            self.assertTrue(os.path.lexists(inner / keep), keep)

    def test_uv_cache_link_to_elsewhere_in_the_home_is_refused(self):  # mutant U1 (inside the HOME counted fine)
        uvd = self.home / "cache" / "uv"
        dir_link(uvd / "m", self.home / "models")
        os.utime(uvd, (OLD, OLD))
        before = tree_digest(self.small)
        with self.status(), mock.patch.object(HK.subprocess, "run", side_effect=AssertionError("uv ran")):
            dry = HK.scan(self.home, uv_cache=True)
            rep = HK.clean(self.home, apply=True, uv_cache=True)
        for r in (dry, rep):
            it = self.item(r, "uv_cache")
            self.assertFalse(it["removable"])
            self.assertIn("m inside the uv cache is a link to outside it", it["why"])
        self.assertIsNone(self.item(rep, "uv_cache")["error"])     # uv never started
        self.assertTrue(linksafe.is_link(uvd / "m"))
        self.assertEqual(tree_digest(self.small), before)          # (no --models: the models stay as they were)
        self.assertTrue((self.medium / "blobs" / "b1").exists())

    def test_uv_cache_folder_itself_a_link(self):                     # mutants U4 (scan) and U3 (apply re-check)
        uvd = self.home / "cache" / "uv"
        real = self.outside / "uv-real"
        write(real / "wheels" / "o.whl", b"o" * 500)
        os.replace(uvd, self.tmp / "uv-was")
        dir_link(uvd, real)
        before = self.outside_hash()
        with self.status(), mock.patch.object(HK.subprocess, "run", side_effect=AssertionError("uv ran via a link")):
            dry = HK.scan(self.home, uv_cache=True)
            HK.clean(self.home, apply=True, uv_cache=True)
        it = self.item(dry, "uv_cache")
        self.assertFalse(it["removable"])
        self.assertIn("link", it["why"])
        self.assertEqual(self.outside_hash(), before)
        os.rmdir(uvd) if IS_WIN else os.unlink(uvd)          # the junction / symlink as a name
        os.replace(self.tmp / "uv-was", uvd)
        real_plan = HK._plan

        def plan(*a, **kw):                  # cache/uv is swapped for a link after the scan, before uv runs
            items = real_plan(*a, **kw)
            os.replace(uvd, self.tmp / "uv-was")
            dir_link(uvd, real)
            return items
        with self.status(), mock.patch.object(HK, "_plan", side_effect=plan), \
                mock.patch.object(HK.subprocess, "run", side_effect=AssertionError("uv ran via a link")):
            rep = HK.clean(self.home, apply=True, uv_cache=True)
        it = self.item(rep, "uv_cache")
        self.assertTrue(it["removable"])
        self.assertIn("changed meanwhile", it["error"])
        self.assertEqual(it["removed"], 0)
        self.assertEqual(self.outside_hash(), before)

    def test_uv_freed_bytes_are_measured_after_uv(self):              # mutant U6 (the scan size reported)
        write(self.home / "cache" / "uv" / "wheels" / "b.whl", b"b" * 400, OLD)

        def uv_clean(uv, cache_dir, timeout=HK.UV_TIMEOUT_S):  # uv frees only a part (a file another uv holds)
            os.unlink(Path(cache_dir) / "wheels" / "a.whl")
        with self.status(), mock.patch.object(HK, "_uv_clean", side_effect=uv_clean):
            rep = HK.clean(self.home, apply=True, uv_cache=True)
        it = self.item(rep, "uv_cache")
        self.assertEqual(it["bytes"], 1400)
        self.assertEqual(it["removed"], 1000)
        self.assertTrue((self.home / "cache" / "uv" / "wheels" / "b.whl").exists())

    def half(self, name: str, size: int = 9000) -> Path:
        d = self.home / "runtimes" / name
        write(d / ("Scripts" if IS_WIN else "bin") / PY, b"h" * size, OLD)
        age_tree(d)
        return d

    def test_a_build_started_after_the_scan_stops_runtime_removal(self):   # mutant R4 (build not re-checked)
        d = self.half("r-half")
        calls = []

        def prune(home, keep, dry_run=False):
            calls.append(dry_run)
            return {"removed": ["r-old"], "kept": sorted(keep), "failed": {}}
        real_plan = HK._plan

        def plan(*a, **kw):                  # reel setup starts building right after the scan
            items = real_plan(*a, **kw)
            write(self.home / "runtimes" / ".r-new.building", b"{}")
            return items
        with self.status(), mock.patch.object(HK, "_prune_is_link_safe", return_value=True), \
                mock.patch.object(HK.runtime, "prune", side_effect=prune), \
                mock.patch.object(HK, "_plan", side_effect=plan):
            rep = HK.clean(self.home, apply=True)
        it = self.item(rep, "runtimes_old")
        self.assertTrue(it["removable"])
        self.assertNotIn(False, calls)                       # no real prune ran
        self.assertEqual(it["removed"], 0)
        self.assertIn("changed the runtimes meanwhile", it["error"])
        self.assertTrue(d.exists())

    def test_a_build_started_between_two_half_removals_keeps_the_rest(self):
        h1, h2 = self.half("r-half1"), self.half("r-half2")
        real = HK.safe_remove

        def rm(p, a, within=None):
            got = real(p, a, within)
            if Path(p).parent.name == "runtimes":            # setup starts a build right after the first one went
                write(self.home / "runtimes" / ".r-new.building", b"{}")
            return got
        with self.status(), mock.patch.object(HK, "_prune_is_link_safe", return_value=False), \
                mock.patch.object(HK, "safe_remove", side_effect=rm):
            rep = HK.clean(self.home, apply=True)
        self.assertFalse(os.path.lexists(h1))
        self.assertTrue(h2.exists())
        self.assertEqual(self.item(rep, "runtimes_old")["removed"], 9000)

    # ---------------------------------------------------------------- P3-2: removable_bytes
    def test_removable_bytes_counts_only_what_a_yes_frees(self):
        with self.status():
            dry = HK.scan(self.home)
            rep = HK.clean(self.home)
            withm = HK.scan(self.home, models=True)
            done = HK.clean(self.home, apply=True)
        for r in (dry, rep, withm, done):
            self.assertNotIn("total_bytes", r)
            self.assertEqual(r["removable_bytes"], sum(i["bytes"] for i in r["items"] if i["removable"]))
        self.assertLess(dry["removable_bytes"], sum(i["bytes"] for i in dry["items"]))   # kept items are listed
        self.assertFalse(self.item(dry, "models_unused")["removable"])
        self.assertEqual(withm["removable_bytes"] - dry["removable_bytes"], self.item(withm, "models_unused")["bytes"])
        self.assertEqual(rep["removable_bytes"], dry["removable_bytes"])
        self.assertEqual(done["freed_bytes"], dry["removable_bytes"])


if __name__ == "__main__":
    unittest.main()
