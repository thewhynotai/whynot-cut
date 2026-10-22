"""Parallel full suite (OPS-09): `tools/test.sh --parallel N [--fresh]` runs this with the engine runtime.

Each top-level test module that `unittest discover -s whynot-cut/tests` finds runs in its own fresh process (same
interpreter flags as the serial run, TEMP/TMP/TMPDIR inherited unchanged), N at a time, longest first. No new module
starts while RAM >= 85 %. The serial-lane ids run alone after the parallel phase. The strict rule: every test that fails
or errors in its first run is a failure; each one is then re-run alone only to label it ("fails alone too" /
"load-sensitive (passed alone)"); the label never changes the exit code. A run counts only when every worker wrote its
result record and exited by itself: otherwise exit 2, and no cache entry and no durations are written.
Exit: 0 complete and green, 1 complete with failures, 2 incomplete or refused. Stdlib only, Python 3.9+.
"""
from __future__ import annotations

import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAM_LIMIT = 85
STILL_RUNNING_S = 300
SEP1, SEP2 = "=" * 70, "-" * 70
DEFAULT_SERIAL_LANE = ("test_identity_scan.TestRealTree.test_full_repo_scan_is_fast",
                       "test_serve_progress.AdapterRun", "test_serve_progress.ThroughTheDaemon",
                       # loaded by test_wnc_queue under its own module name; failed only under load (fix round 4)
                       "test_wnc_queue/wnc_queue_tool_tests.RunnerTests.test_timeout_kills_the_whole_tree")
VALID_MODULE = re.compile(r"[_a-z]\w*\.py$", re.IGNORECASE)        # unittest.loader.VALID_MODULE_NAME
HOLDER_ID = re.compile(r"^\w+ \((.+)\)$")                           # "setUpClass (mod.Class)" -> "mod.Class"
SUBTEST_ID = re.compile(r"^(\w+(?:\.\w+)+) [\[(]")                  # "mod.C.test_x (i=1)" -> "mod.C.test_x"
ENV_KEY_PREFIXES = ("WHYNOT_", "WHYNOTCUT_", "WNC_", "NH_")         # env that switches tests on/off: in the key
ENV_KEY_SKIP = ("WHYNOT_SUITE_CACHE", "WHYNOT_PARALLEL_")           # ...except the tool's own control vars
RECORD_INTS = ("tests_run", "skipped", "expected_failures")
RUN_DIR = Path(tempfile.gettempdir()) / f"wnc-par-{os.getpid()}"   # per-module records and logs (not the tests' TEMP)


def out(line=""):
    print(line, flush=True)


# ------------------------------------------------------------------------------------------------ discovery, order
def discover_modules(tests_dir: Path) -> list:
    """The modules `unittest discover -s tests_dir` (pattern test*.py) imports: top-level files only. A sub-folder
    with __init__.py would make discover recurse into it: refused (ValueError), never silently skipped."""
    pkgs = sorted(p.name for p in tests_dir.iterdir() if p.is_dir() and (p / "__init__.py").is_file())
    if pkgs:
        raise ValueError("test package(s) found, parallel mode cannot split them: " + ", ".join(pkgs))
    return sorted(p.stem for p in tests_dir.iterdir()
                  if p.is_file() and VALID_MODULE.match(p.name) and fnmatch.fnmatch(p.name, "test*.py"))


def order_modules(mods, durations: dict, sizes: dict) -> list:
    """Longest first. A module without a recorded duration is estimated from its file size at the known
    seconds-per-byte rate (pure size order when nothing is recorded)."""
    known = [m for m in mods if m in durations]
    kb = sum(sizes.get(m, 0) for m in known)
    rate = (sum(durations[m] for m in known) / kb) if known and kb else None

    def est(m):
        if m in durations:
            return durations[m]
        return sizes.get(m, 0) * rate if rate is not None else sizes.get(m, 0)
    return sorted(mods, key=lambda m: (-est(m), m))


# ------------------------------------------------------------------------------------------------------------- RAM
_ram_note = [False]


def ram_percent():
    """Used RAM in %, or None when it can't be read. WHYNOT_PARALLEL_FAKE_RAM_FILE (tests) names a file holding it."""
    fake = os.environ.get("WHYNOT_PARALLEL_FAKE_RAM_FILE")
    try:
        if fake:
            return float(Path(fake).read_text(encoding="utf-8").strip())
        if os.name == "nt":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + \
                           [(n, ctypes.c_ulonglong) for n in ("t", "a", "tp", "ap", "tv", "av", "ae")]
            ms = MS()
            ms.dwLength = ctypes.sizeof(MS)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
                return None
            return float(ms.dwMemoryLoad)
        if sys.platform == "darwin":
            total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
                                       check=True).stdout.strip())
            vm = subprocess.run(["vm_stat"], capture_output=True, text=True, check=True).stdout
            page = int(re.search(r"page size of (\d+)", vm).group(1))
            free = sum(int(re.search(rf"{k}:\s+(\d+)", vm).group(1))
                       for k in ("Pages free", "Pages inactive", "Pages speculative"))
            return 100.0 * (1 - free * page / total)
        info = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines() if ":" in line)
        total, avail = (int(info[k].split()[0]) for k in ("MemTotal", "MemAvailable"))
        return 100.0 * (1 - avail / total)
    except Exception:
        return None


def read_ram():
    r = ram_percent()
    if r is None and not _ram_note[0]:
        _ram_note[0] = True
        out("parallel: RAM cannot be read on this system; the RAM brake is off")
    return r


# ---------------------------------------------------------------------------------------------------------- worker
def _selector(test_id: str) -> str:
    m = HOLDER_ID.match(test_id) or SUBTEST_ID.match(test_id)
    return m.group(1) if m else test_id


def lane_entry(s: str) -> tuple:
    """Serial-lane entry -> (test module, selector). 'mod.Class.test' -> ('mod', 'mod.Class.test');
    'mod/other.Class.test' -> ('mod', 'other.Class.test') for a test its module loads under another module name."""
    if "/" in s:
        module, sel = s.split("/", 1)
        return module, sel
    return s.split(".")[0], s


def _matches(test_id: str, sels) -> bool:
    tid = _selector(test_id)
    return any(tid == s or tid.startswith(s + ".") for s in sels)


def _flat(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from _flat(t)
        else:
            yield t


def worker(a) -> int:
    """Run one module (optionally only / except some ids) and write its result record."""
    t0 = time.time()
    # Import exactly like the serial `python -m unittest discover` run from the repo root: there sys.path[0] is the
    # cwd (repo root), not this script's tools/ folder (review r1 P1-1). With -P/PYTHONSAFEPATH neither is added.
    if sys.path and not getattr(sys.flags, "safe_path", False) \
            and Path(sys.path[0] or ".").resolve() == Path(__file__).resolve().parent:
        sys.path[0] = os.getcwd()
    tests_dir = str(Path(a.tests_dir).resolve())
    suite = unittest.TestLoader().discover(tests_dir, pattern=a.worker + ".py")
    if a.only or a.exclude:
        keep = [t for t in _flat(suite)
                if (not a.only or _matches(t.id(), a.only)) and not (a.exclude and _matches(t.id(), a.exclude))]
        suite = unittest.TestSuite(keep)
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=1).run(suite)
    sys.stderr.flush()

    def items(pairs, kind):
        return [{"kind": kind, "id": t.id(), "desc": result.getDescription(t), "tb": tb} for t, tb in pairs]
    rec = {"module": a.worker, "complete": True, "tests_run": result.testsRun, "skipped": len(result.skipped),
           "expected_failures": len(result.expectedFailures),
           "problems": items(result.failures, "FAIL") + items(result.errors, "ERROR")
           + [{"kind": "UNEXPECTED SUCCESS", "id": t.id(), "desc": result.getDescription(t), "tb": ""}
              for t in result.unexpectedSuccesses],
           "duration": round(time.time() - t0, 3)}
    tmp = Path(a.record + ".part")
    tmp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    os.replace(str(tmp), a.record)
    return 0


def valid_record(rec, module) -> bool:
    return (isinstance(rec, dict) and rec.get("complete") is True and rec.get("module") == module
            and all(isinstance(rec.get(k), int) and rec[k] >= 0 for k in RECORD_INTS)
            and isinstance(rec.get("problems"), list) and isinstance(rec.get("duration"), (int, float)))


# ---------------------------------------------------------------------------------------------------------- parent
class Job:
    def __init__(self, a, module, tag, only=(), exclude=()):
        self.module, self.tag = module, tag
        base = RUN_DIR / tag
        base.mkdir(parents=True, exist_ok=True)
        self.record = base / "record.json"
        self.log = base / "worker.log"
        if self.record.exists():
            self.record.unlink()
        cmd = [sys.executable] + (["-s"] if sys.flags.no_user_site else []) + \
              ["-B", "-W", "error::ResourceWarning", str(Path(__file__).resolve()), "--worker", module,
               "--tests-dir", a.tests_dir, "--record", str(self.record)]
        for s in only:
            cmd += ["--only", s]
        for s in exclude:
            cmd += ["--exclude", s]
        # TEMP/TMP/TMPDIR stay exactly the parent's (= serial's, set by tools/test.sh): a longer TEMP broke semgrep
        # (fix round 3), and a shorter one could turn a serial failure into a pass. Each module sandboxes inside TEMP.
        env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
        self.t0 = time.time()
        with open(self.log, "wb") as logf:
            self.proc = subprocess.Popen(cmd, cwd=a.repo, env=env, stdout=logf, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL)
        self.rc = None
        self.rec = None
        self.why = ""

    def finish(self):
        """After the process ended: read and check the record. Returns True when complete."""
        self.rc = self.proc.returncode
        try:
            self.rec = json.loads(self.record.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.rec = None
        if self.rec is None:
            self.why = f"no result record (worker exit code {self.rc})"
        elif not valid_record(self.rec, self.module):
            self.why, self.rec = "malformed result record", None
        elif self.rc != 0:
            self.why, self.rec = f"worker did not exit by itself (exit code {self.rc})", None
        return self.rec is not None

    def tidy(self):
        """Remove only the files this run wrote and the folders if empty (never a recursive delete)."""
        for f in (self.record, self.log):
            try:
                f.unlink()
            except OSError:
                pass
        try:
            self.record.parent.rmdir()
        except OSError:
            pass

    def log_tail(self, n=30):
        try:
            return self.log.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
        except OSError:
            return []


def run_jobs(specs, workers, stats):
    """specs: list of (args for Job). Runs them `workers` at a time with the RAM brake. Returns finished Jobs."""
    poll = float(os.environ.get("WHYNOT_PARALLEL_POLL", "2"))
    pending, running, done = list(specs), [], []
    waiting_said, last_report, last_sample = False, time.time(), 0.0
    while pending or running:
        if time.time() - last_sample >= 1:        # the peak also covers the tail after the last start (r1 P3-6)
            last_sample = time.time()
            ram = read_ram()
            if ram is not None:
                stats["ram_peak"] = max(stats["ram_peak"] or 0, ram)
        for j in [j for j in running if j.proc.poll() is not None]:
            running.remove(j)
            j.finish()
            done.append(j)
        while pending and len(running) < workers:
            ram = read_ram()
            if ram is not None:
                stats["ram_peak"] = max(stats["ram_peak"] or 0, ram)
            if ram is not None and ram >= RAM_LIMIT:
                if not waiting_said:
                    out(f"parallel: RAM brake: {ram:.0f}% >= {RAM_LIMIT}%, waiting before the next module")
                    waiting_said = True
                break
            waiting_said = False
            running.append(Job(*pending.pop(0)))
        if time.time() - last_report >= STILL_RUNNING_S and running:
            last_report = time.time()
            out("parallel: still running: " + ", ".join(f"{j.tag} ({time.time() - j.t0:.0f}s)" for j in running))
        time.sleep(poll if pending and len(running) < workers else 0.05)
    return done


def git_out(repo: Path, *args) -> bytes:
    """git without optional locks: a `git status` must never take index.lock in a shared checkout (review r2 P3-1)."""
    return subprocess.run(["git", "--no-optional-locks", *args], cwd=str(repo), capture_output=True,
                          check=True).stdout


def tree_stamp(repo: Path):
    """(path, mtime_ns, size) of every tracked or untracked non-ignored file, or None when git can't tell. Compared
    at the start and the end of a run: an edit that is reverted during the run still moves the mtime, so it is seen
    even when the key is the same at both ends (review r2 P1-1)."""
    try:
        listed = git_out(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    except (OSError, subprocess.CalledProcessError):
        return None
    stamp = []
    for rel in sorted(set(listed.split(b"\0")) - {b""}):
        try:
            st = (repo / rel.decode("utf-8", "surrogateescape")).stat()
            stamp.append((rel, st.st_mtime_ns, st.st_size))
        except OSError:
            stamp.append((rel, None, None))
    return stamp


def atomic_write(path: Path, text: str):
    """Write via a temp file in the same folder + os.replace, so a parallel reader never sees half a file (r2 P3-2)."""
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(str(tmp), str(path))
    finally:
        if tmp.exists():
            tmp.unlink()


def dirty_key(repo: Path):
    """sha + hash of the dirty tree, or None when git can't tell (then: no cache). The hash covers `git status` of the
    whole repo (modified, staged, deleted, untracked non-ignored) plus the RAW working-tree bytes of every path it
    lists, so a line-ending-only change counts too (review r1 P2-1, P3-7). No `git diff HEAD`: those bytes add nothing
    the listed paths' raw bytes don't hold, and diff refreshes .git/index even with --no-optional-locks (git 2.56:
    a file with a new mtime and the same bytes; OPS-09 equivalence run 3)."""
    def g(*args):
        return git_out(repo, *args)
    try:
        sha = g("rev-parse", "HEAD").decode().strip()
        status = g("status", "--porcelain=v1", "-z", "--untracked-files=all")
        h = hashlib.sha256(status + b"\0")
        paths, toks, i = set(), status.split(b"\0"), 0
        while i < len(toks):
            t = toks[i]
            if len(t) > 3:
                paths.add(t[3:])
                if t[:1] in (b"R", b"C") and i + 1 < len(toks):   # rename/copy: the next token is the source path
                    i += 1
                    paths.add(toks[i])
            i += 1
        for rel in sorted(paths):
            f = repo / rel.decode("utf-8", "surrogateescape")
            h.update(rel + b"\0")
            try:
                h.update(f.read_bytes() if f.is_file() else b"<not a file>")
            except OSError:
                h.update(b"<unreadable>")
            h.update(b"\0")
        return sha, h.hexdigest()[:16]
    except (OSError, subprocess.CalledProcessError):
        return None


def env_key() -> str:
    """The environment variables that switch tests on or off (review r1 P2-2), sorted, as one string."""
    return "\0".join(f"{k}={v}" for k, v in sorted(os.environ.items())
                     if k.upper().startswith(ENV_KEY_PREFIXES) and not k.upper().startswith(ENV_KEY_SKIP))


def cache_dir() -> Path:
    env = os.environ.get("WHYNOT_SUITE_CACHE")
    if env:
        return Path(env)
    if Path("D:/ClaudeData").is_dir():
        return Path("D:/ClaudeData/suite-cache")
    return Path(os.environ.get("WHYNOT_HOME") or Path.home() / ".whynot-cut") / "suite-cache"


def format_report(results, incomplete, labels, lane, workers, wall, stats, n_modules) -> tuple:
    lines = []
    total = skipped = xfail = 0
    counts = {"FAIL": 0, "ERROR": 0, "UNEXPECTED SUCCESS": 0}
    for j in results:
        r = j.rec
        total += r["tests_run"]
        skipped += r["skipped"]
        xfail += r["expected_failures"]
        for p in r["problems"]:
            counts[p["kind"]] += 1
            if p["kind"] != "UNEXPECTED SUCCESS":
                lines += [SEP1, f"{p['kind']}: {p['desc']}", SEP2, p["tb"].rstrip("\n"), ""]
    # the parallel: summary first, so the last lines are always `Ran ...` and the verdict, as in serial (r1 P3-1)
    peak = "n/a" if stats["ram_peak"] is None else f"{stats['ram_peak']:.0f}%"
    lines.append(f"parallel: workers={workers} wall={wall:.1f}s modules={n_modules} serial_lane={len(lane)} "
                 f"ram_peak={peak}")
    slow = sorted((j for j in results if j.tag.startswith("m-")), key=lambda j: -j.rec["duration"])[:5]
    if slow:
        lines.append("parallel: slowest: " + ", ".join(f"{j.module} ({j.rec['duration']:.1f}s)" for j in slow))
    for j in incomplete:
        lines.append(f"parallel: INCOMPLETE {j.tag}: {j.why}; last lines of its log:")
        lines += ["    " + x for x in j.log_tail()]
    for tid, label in labels:
        lines.append(f"parallel: label: {tid}: {label}")
    lines += [SEP2, "Ran %d test%s in %.3fs" % (total, "" if total == 1 else "s", wall), ""]
    extra = [f"skipped={skipped}"] if skipped else []
    extra += [f"expected failures={xfail}"] if xfail else []
    if incomplete:                                # every OK/FAILED grep fails closed on it (r1 P3-2)
        code = 2
        lines.append("FAILED (incomplete: " + ", ".join(f"{j.tag}: {j.why}" for j in incomplete) + ")")
    elif any(counts.values()):
        code = 1
        parts = [f"failures={counts['FAIL']}"] if counts["FAIL"] else []
        parts += [f"errors={counts['ERROR']}"] if counts["ERROR"] else []
        parts += extra
        parts += [f"unexpected successes={counts['UNEXPECTED SUCCESS']}"] if counts["UNEXPECTED SUCCESS"] else []
        lines.append("FAILED (" + ", ".join(parts) + ")")
    else:
        code = 0
        lines.append("OK" + (" (" + ", ".join(extra) + ")" if extra else ""))
    return "\n".join(lines) + "\n", code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools/test.sh --parallel")
    ap.add_argument("--workers", type=int)
    ap.add_argument("--fresh", action="store_true", help="ignore the per-commit cache")
    ap.add_argument("--repo", default=str(ROOT))
    ap.add_argument("--tests-dir")
    ap.add_argument("--serial-lane", default=",".join(DEFAULT_SERIAL_LANE), help="comma-separated ids; '' = none")
    ap.add_argument("--worker", help=argparse.SUPPRESS)
    ap.add_argument("--record", help=argparse.SUPPRESS)
    ap.add_argument("--only", action="append", default=[], help=argparse.SUPPRESS)
    ap.add_argument("--exclude", action="append", default=[], help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    a.repo = str(Path(a.repo).resolve())
    a.tests_dir = str(Path(a.tests_dir or Path(a.repo) / "whynot-cut" / "tests").resolve())
    if a.worker:
        return worker(a)                          # stdout/stderr left as serial unittest has them (r1 P3-3)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    try:
        return parent(a)
    except Exception as e:                        # a crash inside the tool is "broken" (2), never "failures" (1)
        import traceback
        traceback.print_exc(file=sys.stdout)   # on stdout, so the FAILED line below stays the last line
        sys.stdout.flush()
        out(f"FAILED (incomplete: tool error: {type(e).__name__}: {e})")
        return 2


def parent(a) -> int:
    if a.workers is None or a.workers < 2:
        out("parallel: --parallel needs N >= 2 workers")
        return 2
    lane = tuple(s.strip() for s in a.serial_lane.split(",") if s.strip())
    tests_dir = Path(a.tests_dir)
    try:
        mods = discover_modules(tests_dir)
    except (OSError, ValueError) as e:
        out(f"parallel: refused: {e}")
        return 2
    missing = [s for s in lane if lane_entry(s)[0] not in mods]
    if missing:
        out("parallel: refused: serial-lane id(s) name no test module: " + ", ".join(missing))
        return 2

    cdir = cache_dir()
    tool_ver = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]
    runtime = f"{sys.executable}|{sys.version}|s={sys.flags.no_user_site}"

    def cache_key():
        dk = dirty_key(Path(a.repo))
        if not dk:
            return None
        h = hashlib.sha256("|".join([dk[0], dk[1], runtime, tool_ver, a.tests_dir, ",".join(lane), env_key()])
                           .encode("utf-8")).hexdigest()[:20]
        return f"{dk[0][:12]}-{h}"
    key = cache_key()
    stamp0 = tree_stamp(Path(a.repo))
    if not key:
        out("parallel: no git state for the cache key; the cache is not used")
    entry = cdir / f"{key}.json" if key else None
    if entry and not a.fresh and entry.is_file():
        try:
            c = json.loads(entry.read_text(encoding="utf-8"))
            sys.stdout.write(f"reused: {key} from {c['date']}\n{c['report']}")
            sys.stdout.flush()
            return int(c["code"])
        except (OSError, ValueError, KeyError):
            out("parallel: unreadable cache entry; running")

    dur_file = cdir / "durations.json"
    try:
        durations = json.loads(dur_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        durations = {}
    sizes = {m: (tests_dir / f"{m}.py").stat().st_size for m in mods}
    order = order_modules(mods, durations, sizes)
    stats = {"ram_peak": None}
    out(f"parallel: {len(mods)} modules, {a.workers} workers, serial lane {len(lane)} id(s)")
    t0 = time.time()
    entries = [lane_entry(s) for s in lane]
    specs = [(a, m, f"m-{m}", (), tuple(sel for mod, sel in entries if mod == m)) for m in order]
    done = run_jobs(specs, a.workers, stats)
    done += run_jobs([(a, mod, f"lane-{i}", (sel,), ()) for i, (mod, sel) in enumerate(entries)], 1, stats)
    wall = time.time() - t0
    incomplete = [j for j in done if j.rec is None]
    results = [j for j in done if j.rec is not None]
    for j in results:
        if j.tag.startswith("lane-") and j.rec["tests_run"] == 0:
            j.why = f"serial-lane id {lane[int(j.tag[5:])]} matched no test"
            incomplete.append(j)
    results = [j for j in results if j not in incomplete]

    labels, relabel = [], []                      # informative only: never changes the code or the FAILED line
    for j in results:
        for p in j.rec["problems"]:
            if p["kind"] == "UNEXPECTED SUCCESS":
                continue
            r = run_jobs([(a, j.module, "relabel", (_selector(p["id"]),), ())], 1, stats)[0]
            relabel.append(r)
            if r.rec is None or r.rec["tests_run"] == 0:
                labels.append((p["id"], "label unknown (re-run incomplete)"))
            elif r.rec["problems"]:
                labels.append((p["id"], "fails alone too"))
            else:
                labels.append((p["id"], "load-sensitive (passed alone)"))

    report, code = format_report(results, incomplete, labels, lane, a.workers, wall, stats, len(mods))
    kept = list(incomplete)                       # an incomplete or problem module's log stays for diagnosis
    for j in results + relabel:
        if j in results and j.rec["problems"]:
            kept.append(j)
        else:
            j.tidy()
    for j in kept:
        out(f"parallel: log kept: {j.tag}: {j.log}")
    try:
        RUN_DIR.rmdir()
    except OSError:
        pass
    # complete or nothing: only a complete run of the code the key names is stored (r1 P1-2: the key is taken again
    # after the run; if the tree changed meanwhile, nothing is stored). Stored before the report is printed, so any
    # note here comes before it and the verdict stays the last line. A failed write is only a note (r1 P3-5).
    if code != 2 and key and cache_key() != key:
        out("parallel: tree changed during the run; not cached")
    elif code != 2 and key and (stamp0 is None or tree_stamp(Path(a.repo)) != stamp0):
        out("parallel: tree touched during the run; not cached")
    elif code != 2:
        try:
            cdir.mkdir(parents=True, exist_ok=True)
            for j in results:
                if j.tag.startswith("m-"):
                    durations[j.module] = j.rec["duration"]
            atomic_write(dur_file, json.dumps(durations, indent=1, sort_keys=True))
            if entry:
                atomic_write(entry, json.dumps({"date": datetime.datetime.now().isoformat(timespec="seconds"),
                                                "code": code, "report": report}, ensure_ascii=False))
        except OSError as e:
            out(f"parallel: could not write the cache ({e}); not cached")
    sys.stdout.write(report)
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
