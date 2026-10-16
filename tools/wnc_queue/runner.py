"""The wnc-queue runner: one per user (lock), takes queued jobs through heavy.sh, enforces timeouts and stop
conditions, writes done/<id>.json, recovers jobs stranded in running/, honours STOP, exits when the queue is empty."""
from __future__ import annotations

import codecs
import collections
import glob
import json
import os
import re
import threading
import time
import traceback
from pathlib import Path

from . import core, procs
from .core import JobError, Paths, now_iso, read_json, unlink, write_json

TRAMPOLINE = Path(__file__).resolve().parent / "trampoline.py"
NOISE = ("[heavy] ", "[wnc-queue] ")          # our own lines never feed a job's regexes
LINE_END = re.compile(r"(\r\n|\r|\n)")

if core.IS_WIN:
    import msvcrt
else:
    import fcntl


def acquire_lock(path: Path, wait_s: float = 3.0):
    """Single-instance lock (an OS byte lock: released when the process dies, so it can never go stale)."""
    f = open(path, "a+b")
    deadline = time.monotonic() + wait_s
    while True:
        try:
            if core.IS_WIN:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except OSError:
            if time.monotonic() >= deadline:
                f.close()
                return None
            time.sleep(0.2)


def release_lock(f) -> None:
    try:
        if core.IS_WIN:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(f, fcntl.LOCK_UN)
    except OSError:
        pass
    f.close()


def lock_is_held(paths: Paths) -> bool:
    if not paths.lock.exists():
        return False
    f = acquire_lock(paths.lock, wait_s=0)
    if f is None:
        return True
    release_lock(f)
    return False


def _log_owner(name: str) -> str | None:
    """The job id a log file belongs to: <id>.log or <id>.log.1 (an id may itself contain ".log", e.g. app.logger)."""
    m = re.fullmatch(r"(.+)[.]log(?:[.]1)?", name)
    return m.group(1) if m else None


def _unlink_quiet(path: Path, tries: int = 5) -> bool:
    """Remove one file, retrying briefly while antivirus or an indexer holds it; never raises."""
    for i in range(tries):
        try:
            unlink(path)
            return True
        except OSError:
            time.sleep(0.1 * (i + 1))
    return False


class JobLog:
    """A job's log: line-flushed (tail-able), rotated to <id>.log.1 when it passes the cap. write() never raises:
    a log that can't be written (antivirus, disk full) costs lines (counted in `lost`), never the job's result."""

    def __init__(self, path: Path, cap_bytes: int):
        self.path, self.cap = path, max(cap_bytes, 4096)
        self.lock = threading.Lock()
        self.f = None
        self.lost = 0
        self._open()
        try:
            self.size = path.stat().st_size
        except OSError:
            self.size = 0
        self.next_try = self.cap

    def _open(self) -> None:
        try:
            self.f = open(self.path, "a", encoding="utf-8", newline="")
        except OSError:
            self.f = None

    def _close(self) -> None:
        try:
            if self.f:
                self.f.close()
        except OSError:
            pass
        self.f = None

    def write(self, s: str) -> None:
        with self.lock:
            if self.f is None:
                self._open()
            try:
                self.f.write(s)
                self.f.flush()
            except (AttributeError, OSError, ValueError):
                self.lost += 1
                self._close()                  # reopened on the next write
                return
            self.size += len(s.encode("utf-8", "replace"))
            if self.size > self.next_try:
                self._close()
                try:
                    os.replace(self.path, self.path.with_name(self.path.name + ".1"))
                except OSError:                # someone has it open (a tail, an antivirus scan): retry 1 MB later
                    self.next_try = self.size + 2 ** 20
                    self._open()
                    return
                self._open()
                self.size, self.next_try = 0, self.cap
                if self.f:
                    try:
                        self.f.write(f"[wnc-queue] log rotated at {now_iso()} (older part: {self.path.name}.1)\n")
                    except (OSError, ValueError):
                        pass

    def close(self) -> None:
        with self.lock:
            self._close()


def _describe(it: dict) -> str:
    if it.get("outcome") == "timed_out":
        s = f"timed out after {it.get('run_s')} s"
    else:
        s = f"rc {it.get('rc')}"
    if it.get("fail_line"):
        s += f" (fail_regex: {it['fail_line'][:200]})"
    elif it.get("hint"):
        s += f": {it['hint'][:200]}"
    return s


def decide(job: dict):
    """None while the stop condition says run again, else (status, summary). Pure: unit-tested on its own."""
    stop, its = job["stop"], job.get("iterations", [])
    mode, n = stop["mode"], len(its)
    if its:
        last = its[-1]
        o = last.get("outcome")
        if o == "cancelled":
            return "cancelled", f"cancelled during run {n} ({n - 1} runs finished before)"
        if o == "stopped":
            return "stopped", f"STOP kill switch: killed during run {n}"
        if o == "wait_timeout":
            return "timeout", f"no heavy.sh slot within max_wait ({job.get('max_wait_s')} s) for run {n}"
        if o == "error":
            return "error", f"run {n} could not start: {last.get('error') or last.get('hint') or '?'}"
    passes = sum(1 for i in its if i.get("passed"))
    fail_status = lambda it: "timeout" if it.get("outcome") == "timed_out" else "failed"  # noqa: E731
    if mode in ("exit", "until_match"):
        if n == 0:
            return None
        it = its[-1]
        if it.get("passed"):
            return "passed", "passed" + (f" (matched: {it['matched'][:200]})" if it.get("matched") else "")
        if mode == "until_match" and it.get("outcome") == "exited":
            return "failed", f"exited ({_describe(it)}) without the stop regex appearing"
        return fail_status(it), _describe(it)
    if mode == "repeat":
        total = stop["times"]
        if n < total:
            return None
        if passes == total:
            return "passed", f"{total}/{total} runs passed"
        bad = [i["n"] for i in its if not i.get("passed")]
        return "failed", f"{passes}/{total} runs passed; failed runs: {bad[:20]}; first: {_describe(its[bad[0] - 1])}"
    if mode == "until_fail":
        total = stop["max"]
        if n and not its[-1].get("passed"):
            return fail_status(its[-1]), f"run {n} of {total} failed after {n - 1} passes: {_describe(its[-1])}"
        if n >= total:
            return "passed", f"{total}/{total} runs passed (no failure found)"
        return None
    k, total = stop["k"], stop["max"]
    streak = 0
    for i in reversed(its):
        if not i.get("passed"):
            break
        streak += 1
    if streak >= k:
        return "passed", f"{k} consecutive passes after {n} runs ({n - passes} failed before)"
    if n >= total:
        return "failed", f"no {k}-pass streak in {total} runs ({passes} passed)"
    return None


HINT_RE = re.compile(r"(FAIL|ERROR|Error|Traceback|AssertionError|Exception)")


class Worker(threading.Thread):
    def __init__(self, runner: "Runner", job: dict):
        super().__init__(name=f"job-{job['id']}", daemon=True)
        self.runner, self.job = runner, job
        self.paths, self.cfg = runner.paths, runner.cfg
        self.tail: collections.deque = collections.deque(maxlen=40)

    def run(self) -> None:
        log = None
        try:
            log = JobLog(self.paths.log(self.job["id"]), int(self.cfg["max_log_mb"] * 2 ** 20))
            self._run(log)
        except Exception:                                    # never strand a job on a runner bug
            tb = traceback.format_exc()
            self.runner.log(f"job {self.job.get('id')} crashed the worker:\n{tb}")
            self.finish("error", f"runner error: {tb.strip().splitlines()[-1]}")
        finally:
            if log:
                log.close()

    def _run(self, log: JobLog) -> None:
        job = self.job
        log.write(f"\n=== wnc-queue job {job['id']} '{job['title']}' attempt {job['attempts']} "
                  f"(owner {job['owner']}, class {job['heavy']}) {now_iso()} ===\n")
        try:
            exe = core.resolve_exe(job["argv"][0], Path(job["cwd"]), self.cfg, (job.get("env") or {}).get("PATH"))
            core.check_batch_args(exe, job["argv"][1:])
            core.check_command_line(exe, job["argv"][1:])
        except JobError as e:
            log.write(f"[wnc-queue] refused: {e}\n")
            self.finish("error", f"refused: {e}")
            return
        argv = [exe] + job["argv"][1:]
        while True:
            verdict = decide(job)
            if verdict:
                self.finish(*verdict)
                return
            n = len(job["iterations"]) + 1
            if self.runner.abort_event.is_set():   # never start another run once the runner is failing / STOP is on
                log.write(f"[wnc-queue] runner aborted before run {n}: left for recovery\n")
                return
            if self.runner.stop_event.is_set() or self.paths.stop.exists():
                self.finish("stopped", f"STOP kill switch: stopped before run {n} ({n - 1} runs finished)")
                return
            if self.paths.cancel(job["id"]).exists():
                self.finish("cancelled", f"cancelled before run {n} ({n - 1} runs finished)")
                return
            job["current"] = {"n": n, "since": now_iso()}
            write_json(self.paths.running / f"{job['id']}.json", job)
            it = self.iteration(argv, n, log)
            if it.get("outcome") == "aborted":     # the runner is crashing: leave the job in running/ so the next
                log.write(f"[wnc-queue] runner aborted during run {n}: left for recovery\n")   # start re-queues it
                return
            job.pop("current", None)
            job["iterations"].append(it)
            write_json(self.paths.running / f"{job['id']}.json", job)

    def _of(self) -> str:
        s = self.job["stop"]
        total = s.get("times") or s.get("max")
        return f"/{total}" if total else ""

    def iteration(self, argv: list[str], n: int, log: JobLog) -> dict:
        job, p, cfg = self.job, self.paths, self.cfg
        jid = job["id"]
        unlink(p.started(jid))
        temp = Path(cfg["temp_root"]) / jid
        temp.mkdir(parents=True, exist_ok=True)
        jenv = {"TEMP": str(temp), "TMP": str(temp), "TMPDIR": str(temp), "JOB_QUEUE_ID": jid,
                "PYTHONIOENCODING": "utf-8"}          # logs are UTF-8; a job's env may override any of these
        jenv.update(job.get("env") or {})
        write_json(p.spec(jid), {"argv": argv, "cwd": job["cwd"], "env": jenv, "started_file": str(p.started(jid))})
        fwd = lambda s: str(s).replace("\\", "/")  # noqa: E731  (MSYS leaves C:/x alone; never quotes or globs it)
        inner = [cfg["python"], "-B", str(TRAMPOLINE), str(p.spec(jid))]
        it = {"n": n, "rc": None, "passed": False, "outcome": None, "wait_s": 0.0, "run_s": 0.0,
              "started_at": None, "ended_at": None}
        if job["heavy"] != "none":
            bash, heavy = cfg.get("bash"), cfg.get("heavy_sh")
            if not bash or not heavy or not Path(heavy).is_file():
                it.update(outcome="error", error=f"heavy.sh not found ({heavy}) or no bash ({bash})",
                          ended_at=now_iso())
                log.write(f"[wnc-queue] {it['error']}\n")
                return it
            cmd = [bash, fwd(heavy), core.HEAVY_KIND[job["heavy"]], f"wnc-queue:{jid}", "--"] + [fwd(a) for a in inner]
        else:
            cmd = inner
        # heavy.sh's bash gets the runner's own environment: the job env (PATH, BASH_ENV …) is applied by the
        # trampoline only, so a job can never change how heavy.sh measures RAM or takes its slot.
        # No WNC_* name ever reaches a job: the product reserves that prefix (its tests assert no WNC_ variable
        # reaches the engine), so the runner's marker is JOB_QUEUE_ID, and an inherited WNC_* is the runner's own.
        # Nor HEAVY_INSIDE: a runner started from inside a heavy.sh job would hand it on, and heavy.sh would treat
        # the queued job as a nested call of that (maybe long dead) outer job instead of taking its own slot.
        env = {k: v for k, v in os.environ.items()
               if not k.upper().startswith("WNC_") and k.upper() != "HEAVY_INSIDE"}
        env["JOB_QUEUE_ID"] = jid
        pass_re = re.compile(job["pass_regex"]) if job.get("pass_regex") else None
        fail_re = re.compile(job["fail_regex"]) if job.get("fail_regex") else None
        match_re = re.compile(job["stop"]["regex"]) if job["stop"]["mode"] == "until_match" else None
        st = {"pass_hit": False, "fail_line": None, "matched": None}
        self.tail.clear()
        log.write(f"\n=== run {n}{self._of()} start {now_iso()} ===\n")
        t0_wall, t0 = time.time(), time.monotonic()
        lost_before = log.lost
        try:
            tree = procs.Tree(cmd, job["cwd"], env)
        except OSError as e:
            it.update(outcome="error", error=f"cannot start: {e}", ended_at=now_iso())
            log.write(f"[wnc-queue] {it['error']}\n")
            return it

        def line(text: str, end: str) -> None:
            try:
                log.write(text + end)
            except (OSError, ValueError):               # never stop draining the pipe (a full pipe hangs the job)
                log.lost += 1
            self.tail.append(text)
            if text.startswith(NOISE):
                return
            if pass_re and pass_re.search(text):
                st["pass_hit"] = True
            if fail_re and st["fail_line"] is None and fail_re.search(text):
                st["fail_line"] = text.strip()
            if match_re and st["matched"] is None and match_re.search(text):
                st["matched"] = text.strip()

        def raw(s: str) -> None:
            try:
                log.write(s)
            except (OSError, ValueError):
                pass

        def reader():
            """Lines end at \\n, \\r\\n or a bare \\r (ffmpeg / download progress), so progress shows as it happens.
            A bare \\r ends its line at once, even as the last byte of a read: if the next read starts with \\n
            (a \\r\\n split across reads), that \\n only goes to the log, it is not an empty line."""
            dec = codecs.getincrementaldecoder("utf-8")("replace")
            buf, after_cr = "", False
            while True:
                chunk = tree.proc.stdout.read1(65536)
                buf += dec.decode(chunk, final=not chunk)
                if after_cr and buf.startswith("\n"):
                    raw("\n")
                    buf, after_cr = buf[1:], False
                elif buf:
                    after_cr = False
                parts = LINE_END.split(buf)
                buf = parts.pop()                          # the unfinished tail (or "" after a line end)
                for i in range(0, len(parts), 2):
                    line(parts[i], parts[i + 1])
                if parts and not buf and parts[-1] == "\r":
                    after_cr = True
                if len(buf) > 65536:                       # a huge line without an end: take it as it is
                    line(buf, "\n")
                    buf = ""
                if not chunk:
                    if buf:
                        line(buf, "\n")
                    return
        rt = threading.Thread(target=reader, daemon=True)
        try:
            rt.start()
        except BaseException:                    # no reader: the job would block on a full pipe forever
            try:
                tree.kill()
            finally:
                tree.close()
            raise
        started_ts = None
        peak = {"ram_mb": None, "cpu_pct": None, "sys_ram_pct": None, "gpu_pct": None, "vram_mb": None}
        last = {"t": time.monotonic(), "cpu": 0.0, "sampled": 0.0}
        at_peak = {"mb": None}
        ncpu = os.cpu_count() or 1

        def bump(k, v):
            if v is not None and (peak[k] is None or v > peak[k]):
                peak[k] = v

        def sample(ended: bool = False):
            s = tree.stats()
            now_m = time.monotonic()
            if "cpu_s" in s:
                dt_ = now_m - last["t"]
                if dt_ > 0.5:
                    bump("cpu_pct", round(100 * (s["cpu_s"] - last["cpu"]) / dt_ / ncpu, 1))
                    last["t"], last["cpu"] = now_m, s["cpu_s"]
            bump("ram_mb", s.get("peak_mb"))
            if started_ts is not None:           # machine-wide: only while THIS run runs (not its slot wait)
                pct = procs.system_ram_pct()
                if ended and peak["sys_ram_pct"] is not None:
                    pct = None          # the run was sampled while it ran: RAM after it exited is not the run's
                if pct is not None and not ended:
                    # the job's own memory at the machine's peak (not its peak over the whole run): whose RAM it was
                    mem = s.get("mem_mb")
                    if peak["sys_ram_pct"] is None or pct > peak["sys_ram_pct"]:
                        at_peak["mb"] = mem
                    elif pct == peak["sys_ram_pct"] and mem is not None and (at_peak["mb"] is None
                                                                               or mem < at_peak["mb"]):
                        at_peak["mb"] = mem     # a tie (whole percents): the smaller figure, the cautious reading
                # a run too short for any in-run sample keeps the after-exit one; its job figure stays unknown
                # (the whole-run peak stands in), since after exit the job holds ~0
                bump("sys_ram_pct", pct)
                g = self.runner.gpu
                if g:
                    bump("gpu_pct", g[0])
                    bump("vram_mb", g[1])
            last["sampled"] = now_m

        outcome = None
        refresh_s = float(cfg.get("slot_refresh_s", 600))
        try:
            while True:
                if started_ts is None and p.started(jid).exists():
                    started_ts = time.time()
                    it["started_at"] = now_iso()
                if tree.poll() is not None:
                    break
                now_m = time.monotonic()
                if p.cancel(jid).exists():
                    outcome = "cancelled"
                elif self.runner.abort_event.is_set():
                    outcome = "aborted"
                elif self.runner.stop_event.is_set():
                    outcome = "stopped"
                elif started_ts is None and now_m - t0 > job["max_wait_s"]:
                    outcome = "wait_timeout"
                elif started_ts is not None and time.time() - started_ts > job["timeout_s"]:
                    outcome = "timed_out"
                elif st["matched"] is not None:
                    outcome = "matched"
                if outcome:
                    tree.kill()
                    break
                if now_m - last["sampled"] >= cfg["sample_s"]:
                    sample()
                if started_ts is not None and job["heavy"] != "none" and now_m - last.get("kept", 0) > refresh_s:
                    self.keep_slot_fresh()
                    last["kept"] = now_m
                time.sleep(0.2)
            try:
                rc = tree.proc.wait(timeout=30)
            except Exception:
                tree.kill()
                rc = tree.proc.wait(timeout=30)
            if started_ts is None and p.started(jid).exists():   # started between the loop's last check and its exit
                started_ts = time.time()
            sample(ended=True)
            rt.join(timeout=3)
            if rt.is_alive():                    # an orphan still holds the output pipe: kill the rest of the tree
                tree.kill()
                it["orphans_killed"] = True
                rt.join(timeout=10)
        except BaseException:                    # a runner bug mid-run: never leave the job's processes behind
            try:
                tree.kill()
            finally:
                tree.close()
            raise
        tree.close()
        if outcome is None and st["matched"] is not None:   # printed the match and exited before the next poll
            outcome = "matched"
        end_wall = time.time()
        try:
            started_ts = float(p.started(jid).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if started_ts is not None:
            it["wait_s"] = round(max(0.0, started_ts - t0_wall), 1)
            it["run_s"] = round(max(0.0, end_wall - started_ts), 1)
        else:
            it["wait_s"] = round(end_wall - t0_wall, 1)
        if outcome is None:
            outcome = "exited" if started_ts is not None else "error"
            if outcome == "error":
                it["error"] = f"heavy.sh/bash exited rc {rc} before the job started"
        it.update(rc=rc, outcome=outcome, ended_at=now_iso(), matched=st["matched"], fail_line=st["fail_line"],
                  timed_out=outcome == "timed_out")
        it.update({f"peak_{k}": v for k, v in peak.items()})
        it["ram_total_mb"] = procs.system_ram_total_mb()
        it["job_mb_at_ram_peak"] = at_peak["mb"]
        if outcome == "matched":
            it["passed"] = True
        elif outcome == "exited":
            it["passed"] = (rc == 0 and match_re is None and (pass_re is None or st["pass_hit"])
                            and st["fail_line"] is None)
        hints = [t for t in self.tail if HINT_RE.search(t) and not t.startswith(NOISE)]
        if hints and not it["passed"]:
            it["hint"] = hints[-1].strip()
        it["tail"] = list(self.tail)[-8:] if not it["passed"] else []
        log.write(f"=== run {n}{self._of()} {outcome} rc={rc} passed={it['passed']} wait={it['wait_s']}s "
                  f"run={it['run_s']}s {now_iso()} ===\n")
        if log.lost > lost_before:                 # the log could not take every line (held, disk full)
            it["log_lines_lost"] = log.lost - lost_before
        unlink(p.started(jid))
        unlink(p.spec(jid))
        return it

    def keep_slot_fresh(self) -> None:
        """heavy.sh frees a slot whose owner can't be checked once it is old (v2: silent for 10 min, v1: 3 h): touch
        ours while the job runs. heavy.sh v2's own sampler touches it too; this keeps it held if that one dies."""
        label = f"label=wnc-queue:{self.job['id']}"
        try:
            for d in Path(self.cfg["locks_dir"]).glob("*.d"):
                try:
                    if label in (d / "owner").read_text(encoding="utf-8").splitlines():
                        os.utime(d)
                except OSError:
                    pass
        except OSError:
            pass

    def finish(self, status: str, summary: str) -> None:
        job, p = self.job, self.paths
        jid = job["id"]
        its = job.get("iterations", [])
        peak = {}
        for k in ("ram_mb", "cpu_pct", "sys_ram_pct", "gpu_pct", "vram_mb"):
            vals = [i.get(f"peak_{k}") for i in its if i.get(f"peak_{k}") is not None]
            peak[k] = max(vals) if vals else None
        lost = sum(i.get("log_lines_lost") or 0 for i in its)
        extra = {"log_lines_lost": lost} if lost else {}
        rec = core.done_record(job, status, summary, log=str(p.log(jid)), peak=peak, tail=list(self.tail)[-15:],
                               pressure_at=self.cfg.get("pressure_ram_pct"), **extra)
        write_json(p.done / f"{jid}.json", rec)
        for f in (p.running / f"{jid}.json", p.spec(jid), p.started(jid), p.cancel(jid)):
            unlink(f)
        core.remove_tree(Path(self.cfg["temp_root"]) / jid)          # the job's TEMP (never through a link)
        self.runner.log(f"job {jid} {status}: {summary}")


class Runner:
    def __init__(self, paths: Paths | None = None, cfg: dict | None = None):
        self.paths = (paths or Paths()).ensure()
        self.cfg = cfg or core.load_config(self.paths)
        self.stop_event = threading.Event()        # STOP switch: jobs end as `stopped`
        self.abort_event = threading.Event()       # the runner itself is failing: jobs stay in running/ for recovery
        self.workers: dict[str, Worker] = {}
        self.gpu = None
        self._gpu_thread: threading.Thread | None = None
        self._unreadable: dict[str, tuple[int, float]] = {}  # queue file -> (passes it failed, last counted at)
        self._ignored: dict[str, float] = {}      # queue files that cannot even be opened -> retry after (monotonic)
        self._done = threading.Event()
        self._log_lock = threading.Lock()

    # -- logging -----------------------------------------------------------------------------------------------
    def log(self, msg: str) -> None:
        with self._log_lock:
            f = self.paths.runner_log
            try:
                if f.exists() and f.stat().st_size > 2 * 2 ** 20:      # keep runner.log + .1 .. .3
                    for i in (2, 1):
                        if f.with_name(f"runner.log.{i}").exists():
                            os.replace(f.with_name(f"runner.log.{i}"), f.with_name(f"runner.log.{i + 1}"))
                    os.replace(f, f.with_name("runner.log.1"))
                with open(f, "a", encoding="utf-8") as fh:
                    fh.write(f"{now_iso()} [{os.getpid()}] {msg}\n")
            except OSError:
                pass

    def heartbeat(self, state: str = "running") -> None:
        write_json(self.paths.runner_json, {"pid": os.getpid(), "state": state, "started_at": self.started_at,
                                            "heartbeat": now_iso(), "active": sorted(self.workers),
                                            "home": str(self.paths.home)})

    # -- housekeeping ------------------------------------------------------------------------------------------
    def prune(self) -> None:
        p, cfg = self.paths, self.cfg
        cutoff = time.time() - cfg["retention_days"] * 86400
        keep = {"runner.log", "runner.log.1", "runner.log.2", "runner.log.3"}
        for d in (p.done, p.logs):
            for f in d.iterdir():
                try:
                    if f.is_file() and not f.is_symlink() and f.name not in keep and f.stat().st_mtime < cutoff:
                        unlink(f)
                except OSError:
                    pass
        for f in p.queue.iterdir():               # half-written temp files left by a killed writer
            try:
                if f.name.endswith(".tmp") and f.stat().st_mtime < time.time() - 86400:
                    unlink(f)
            except OSError:
                pass
        active = {f.stem for f in p.running.glob("*.json")}
        logs = []
        for f in p.logs.iterdir():
            try:
                if f.is_file() and not f.is_symlink() and f.name not in keep and _log_owner(f.name) not in active:
                    st = f.stat()
                    logs.append((st.st_mtime, st.st_size, f))
            except OSError:
                pass
        total = sum(size for _, size, _ in logs)
        cap = cfg["max_logs_total_mb"] * 2 ** 20
        for _, size, f in sorted(logs, key=lambda x: x[0]):
            if total <= cap:
                break
            try:
                unlink(f)
                total -= size
            except OSError:                        # held open (someone tails it): try the next one
                pass

    def recover(self) -> None:
        """Jobs left in running/ by a runner that died (crash, reboot, restart): re-queue or mark them stranded."""
        p = self.paths
        for f in list(p.running.glob("*.json")):
            if f.name.endswith(".spec.json"):
                continue
            try:                                         # one held file must not stop the recovery of the others
                self._recover_one(f)
            except Exception:
                self.log(f"recover {f.name} failed (retried on the next start):\n{traceback.format_exc()}")
        for f in list(p.running.iterdir()):              # leftovers, matched by their exact shapes only
            try:
                self._sweep_one(f)
            except Exception:
                self.log(f"sweep {f.name} failed:\n{traceback.format_exc()}")
        for f in p.queue.glob("*.json.cancelling"):         # a `cancel` that died between its two steps
            try:
                jid = f.name[: -len(".json.cancelling")]
                if not (p.done / f"{jid}.json").exists():
                    write_json(p.done / f"{jid}.json", core.done_record(read_json(f) or {"id": jid}, "cancelled",
                                                                        "cancelled before it started", log=None))
                unlink(f)
            except OSError:
                pass

    LEFTOVER_RE = re.compile(r"(?P<id>.+?)(?P<kind>\.spec\.json|\.started|\.cancel|\.json\.dup-\d+|\.json\.refused)")

    def _sweep_one(self, f: Path) -> None:
        """One file in running/ that is not a job: remove it once its job is gone, but never lose what it meant."""
        p = self.paths
        m = self.LEFTOVER_RE.fullmatch(f.name)
        if not m or not f.is_file():
            return
        jid, kind = m.group("id"), m.group("kind")
        if kind.startswith(".json.dup-"):            # a refused queue file (duplicate or bad id)
            pid = kind[len(".json.dup-"):]
            if not self.refusals(jid, pid):        # its record never got written
                j = read_json(f)
                write_json(self.refusal_path(jid, unique=True), core.done_record(
                    j if isinstance(j, dict) else {"id": jid}, "error",
                    f"refused: id {jid!r} is invalid, or already running or done (queue it again with a new id)",
                    log=None))
            _unlink_quiet(f)
            return
        if kind == ".json.refused":                  # an unreadable queue file: record it if a crash cut that short
            raw = f.read_bytes()[:2000].decode("utf-8", "replace")
            known = [p.done / f"{jid}.json", *self.refusals(jid)]
            if not any((read_json(r) or {}).get("raw") == raw for r in known if r.exists()):
                write_json(self.refusal_path(jid), core.done_record(
                    {"id": jid}, "error", "refused: the queue file is not a JSON object (fix it and queue it again)",
                    log=None, raw=raw))
            _unlink_quiet(f)
            return
        if (p.running / f"{jid}.json").exists():     # its job is still here: keep it (recover() just honoured it)
            return
        if kind == ".cancel" and (p.queue / f"{jid}.json").exists():
            core.cancel_job(p, jid)                  # a cancel that met recover(): cancel the re-queued copy
        _unlink_quiet(f)

    def _recover_one(self, f: Path) -> None:
        p = self.paths
        jid = f.stem
        core.remove_tree(Path(self.cfg["temp_root"]) / jid)   # its tree died with the old runner; a re-queued
        leftovers = (f, p.spec(jid), p.started(jid))          # job gets a fresh TEMP on its next run
        if (p.done / f"{jid}.json").exists():
            for x in (*leftovers, p.cancel(jid)):
                _unlink_quiet(x)
            return
        job = read_json(f)
        if not isinstance(job, dict):
            write_json(p.done / f"{jid}.json", core.done_record({"id": jid}, "error", "unreadable job file in "
                                                                 "running/ after a runner stop", log=None))
        elif p.cancel(jid).exists():
            job.pop("current", None)
            write_json(p.done / f"{jid}.json", core.done_record(job, "cancelled", "cancelled while the runner "
                                                                "was down", log=str(p.log(jid))))
            _unlink_quiet(p.cancel(jid))
        elif job.get("attempts", 0) < job.get("max_attempts", 3):
            job.pop("current", None)
            n = len(job.get("iterations", []))
            job.setdefault("events", []).append(f"{now_iso()} recovered from running/ (runner stopped mid-job, "
                                                f"{n} runs kept; the interrupted run repeats)")
            write_json(p.queue / f"{jid}.json", job)
            self.log(f"recovered {jid}: re-queued (attempt {job.get('attempts', 0)} of {job.get('max_attempts')})")
        else:
            job.pop("current", None)
            write_json(p.done / f"{jid}.json", core.done_record(
                job, "stranded", f"runner stopped mid-job {job.get('attempts')} times; not retried",
                log=str(p.log(jid))))
            self.log(f"recovered {jid}: stranded (attempts used up)")
        for x in leftovers:            # if one is held, claim() treats running/<id>.json as a leftover and drops it
            _unlink_quiet(x)

    BAD_GRACE_S = 5.0     # a queue file that is still not a JSON object after this long is refused (hand-written)
    MAX_LOOP_ERRORS = 30  # consecutive main-loop errors before the runner gives up (jobs are then left for recovery)
    LOOP_ERROR_SLEEP_S = 2.0

    BAD_PASSES = 3        # ... and only after this many claim passes in a row found it unreadable (not a brief lock)

    def claimable(self) -> bool:
        """Anything in queue/ the runner must still deal with. Unreadable files are refused by claim(), and files it
        cannot even open are ignored after a few passes, so neither keeps the runner alive for long."""
        skip = self.ignored_now()
        return any(f.name not in skip and f.is_file() for f in self.paths.queue.glob("*.json"))

    IGNORE_S = 60.0       # a queue file that cannot be opened is skipped this long, then read again

    def ignored_now(self) -> set[str]:
        now = time.monotonic()
        for name in [n for n, until in self._ignored.items() if until <= now]:
            del self._ignored[name]
        return set(self._ignored)

    def refusals(self, jid: str, pid: str | None = None) -> list[Path]:
        """done/<jid>.refused-<date>-<time>-<pid>-<n>.json records of THIS id (by refusal_path's exact shape; a glob
        also matched another id's records, like those of a crafted id "a.refused-x-4242-y" for id "a")."""
        rx = re.compile(re.escape(jid) + r"\.refused-\d{8}-\d{6}-(\d+)-\d+\.json", re.I)
        out = []
        for f in self.paths.done.glob(f"{glob.escape(jid)}.refused-*.json"):
            m = rx.fullmatch(f.name)
            if m and (pid is None or m.group(1) == pid):
                out.append(f)
        return out

    def refusal_path(self, stem: str, unique: bool = False) -> Path:
        """done/<stem>.json, unless that id already has a record or is running: never overwrite either. With
        unique, always done/<stem>.refused-<time>-<pid>-<n>.json (the sweep finds it by the pid)."""
        d = self.paths.done / f"{stem}.json"
        n = 0
        while d.exists() or (n == 0 and (unique or (self.paths.running / f"{stem}.json").exists())):
            n += 1
            d = self.paths.done / f"{stem}.refused-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{n}.json"
        return d

    def reject_unreadable(self, f: Path) -> None:
        p = self.paths
        n, last = self._unreadable.get(f.name, (0, 0.0))
        if time.monotonic() - last >= 1.0:              # claim() runs many times per poll: count once a second
            n, last = n + 1, time.monotonic()
        self._unreadable[f.name] = (n, last)
        try:
            data = f.read_bytes()
            age = time.time() - f.stat().st_mtime
        except OSError as e:
            if n >= self.BAD_PASSES:
                self._ignored[f.name] = time.monotonic() + self.IGNORE_S
                self._unreadable.pop(f.name, None)
                self.log(f"skipping queue/{f.name} for {int(self.IGNORE_S)} s: it cannot be read ({e})")
            return
        try:
            if isinstance(json.loads(data.decode("utf-8-sig")), dict):
                self._unreadable.pop(f.name, None)     # it was only locked for a moment: claimed on the next pass
                return
        except ValueError:
            pass
        if n < self.BAD_PASSES or age < self.BAD_GRACE_S:
            return
        dst = p.running / (f.name + ".refused")
        try:
            os.replace(f, dst)
        except OSError:
            return
        rec = core.done_record({"id": f.stem}, "error", "refused: the queue file is not a JSON object (fix it and "
                               "queue it again)", log=None, raw=data[:2000].decode("utf-8", "replace"))
        write_json(self.refusal_path(f.stem), rec)
        _unlink_quiet(dst)
        self._unreadable.pop(f.name, None)
        self.log(f"refused {f.name}: not a JSON object")

    def claim(self) -> dict | None:
        p = self.paths
        bad: list[Path] = []
        jobs = core.queued_jobs(p, bad, skip=self.ignored_now())
        for f in bad:
            self.reject_unreadable(f)
        for j in jobs:
            src = j.pop("_file")
            why = None
            if not core.ID_RE.match(src.stem) or core.RESERVED_ID_RE.search(src.stem):
                why = f"refused: {src.name!r} is not a valid job id (it could collide with the runner's own files)"
            elif src.stem.casefold() in {w.casefold() for w in self.workers} or (p.done / src.name).exists():
                why = f"refused: id {src.stem!r} is already running or done (queue it again with a new id)"
            if why:                                    # checked BEFORE the move: running/ may hold <id>.spec.json
                hold = p.running / f"{src.name}.dup-{os.getpid()}"
                try:
                    os.replace(src, hold)              # own it first: a racing `cancel` may have just taken it
                except OSError:
                    continue
                write_json(self.refusal_path(src.stem, unique=True), core.done_record(j, "error", why, log=None))
                _unlink_quiet(hold)                    # still held? the next start's sweep removes it (no 2nd record)
                self.log(f"{why} ({src.name})")
                continue
            dst = p.running / src.name
            if dst.exists():                           # not one of our workers: a leftover of a recover() that could
                try:                                   # not remove it; the queue copy is the current one
                    unlink(dst)
                except OSError:
                    continue
            try:
                os.replace(src, dst)
            except (FileNotFoundError, PermissionError):
                continue
            raw = read_json(dst) or {}
            try:
                job = core.validate(raw, self.cfg)
                if job["id"] != src.stem:
                    raise JobError(f"id {job['id']!r} does not match the file name {src.name}")
            except JobError as e:
                rec = core.done_record(raw if isinstance(raw, dict) else {}, "error", f"refused: {e}", log=None)
                rec["id"] = src.stem
                unlink(dst)
                write_json(self.refusal_path(src.stem), rec)
                self.log(f"refused {src.stem}: {e}")
                continue
            job["attempts"] = int(job.get("attempts", 0)) + 1
            job["started_at"] = job.get("started_at") or now_iso()
            write_json(dst, job)
            return job
        return None

    # -- main loop -----------------------------------------------------------------------------------------------
    def _gpu_loop(self) -> None:
        while not self._done.is_set():
            if self.workers:
                self.gpu = procs.gpu_sample()
            self._done.wait(5)

    def run(self) -> int:
        lock = acquire_lock(self.paths.lock)
        if lock is None:
            return 3
        self.started_at = now_iso()
        while True:
            crashed = False
            try:
                self._serve()
            except Exception:                     # logged, never silent under pythonw
                crashed = True
                self.log(f"runner crashed: running jobs are left for recovery by the next start\n"
                         f"{traceback.format_exc()}")
                self.abort_event.set()            # workers kill their trees and leave the jobs in running/
                for w in list(self.workers.values()):
                    w.join(60)
            finally:
                self._done.set()
                try:
                    self.heartbeat("crashed" if crashed else "exited")
                except OSError:
                    pass
                release_lock(lock)
            if crashed:
                return 1                          # the next start (10-min tick) recovers and re-queues the jobs
            # A job queued while this runner was deciding to exit: its `add` saw the lock still held and did not
            # kick a new runner, so take the lock back and serve it (if another runner got it first, that one does).
            if self.paths.stop.exists() or self.stop_event.is_set() or not self.claimable():
                return 0
            lock = acquire_lock(self.paths.lock, wait_s=1.0)   # a `status` probe may hold it for an instant
            if lock is None:
                return 0
            self.log("jobs arrived while exiting: serving them")
            self._done.clear()

    def _serve(self) -> None:
        if self.paths.stop.exists():
            self.log("STOP file present: not starting (remove it with `wnc-queue resume`)")
            return
        self.log(f"runner start (home {self.paths.home})")
        self.heartbeat()
        for step in (self.prune, self.recover):    # housekeeping must never keep the queue from being served
            try:
                step()
            except Exception:
                self.log(f"{step.__name__} failed (serving the queue anyway):\n{traceback.format_exc()}")
        if self._gpu_thread is None or not self._gpu_thread.is_alive():
            self._gpu_thread = threading.Thread(target=self._gpu_loop, daemon=True)
            self._gpu_thread.start()
        last_hb, errors = 0.0, 0
        while True:
            try:
                if self.paths.stop.exists() and not self.stop_event.is_set():
                    self.log("STOP file: killing running jobs, leaving the queue as it is")
                    self.stop_event.set()
                for jid, w in list(self.workers.items()):
                    if not w.is_alive():
                        del self.workers[jid]
                if self.stop_event.is_set():
                    if not self.workers:
                        break
                else:
                    while len(self.workers) < int(self.cfg["max_parallel"]):
                        job = self.claim()
                        if job is None:
                            break
                        self.log(f"start {job['id']} ({job['heavy']}, {job['stop']['mode']}, owner {job['owner']})")
                        w = Worker(self, job)
                        self.workers[job["id"]] = w
                        w.start()
                    if not self.workers and not self.claimable():
                        break
                if time.monotonic() - last_hb > 5:
                    self.heartbeat()
                    last_hb = time.monotonic()
                errors = 0
            except Exception:                     # e.g. antivirus holding a file: log, wait, retry; jobs keep running
                errors += 1
                self.log(f"main loop error {errors}:\n{traceback.format_exc()}")
                if errors >= self.MAX_LOOP_ERRORS:
                    raise
                time.sleep(self.LOOP_ERROR_SLEEP_S)
            time.sleep(self.cfg["poll_s"])
        self.log("runner exit (queue empty)" if not self.stop_event.is_set() else "runner exit (STOP)")
