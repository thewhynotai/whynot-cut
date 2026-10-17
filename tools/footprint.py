# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Resource footprint of one command or one running process (dev tool, not shipped in the plugin; 3.0 T4.10).

    python tools/footprint.py [--out f.json] -- <command> [args...]     run it and measure it (and its children)
    python tools/footprint.py [--out f.json] --pid 1234                watch a running process until it exits

Every SAMPLE_S (0.5 s) it samples the process tree's resident memory (RSS, MB) and CPU % (100 = one core), and the
machine's GPU % and used VRAM (MB) from nvidia-smi (None on a machine without it, e.g. a Mac). It prints JSON:
{"cmd" | "pid", "returncode", "wall_s", "samples", "rss_mb": {"peak", "mean"}, "cpu_pct": {...}, "gpu_pct": {...},
"vram_mb": {...}}. Stdlib only: Windows reads the process tree through the Toolhelp / psapi APIs (ctypes), Linux
/proc, macOS `ps`. GPU numbers are machine-wide (nvidia-smi has no per-process utilisation on a laptop GPU).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

SAMPLE_S = 0.5
KEYS = ("rss_mb", "cpu_pct", "gpu_pct", "vram_mb")
IS_WIN = os.name == "nt"


# --------------------------------------------------------------------------- pure parts (unit-tested)
def summarize(samples: list[dict]) -> dict:
    """{"samples": n, key: {"peak", "mean"}} over the samples that have a value for the key (None -> both None)."""
    out = {"samples": len(samples)}
    for k in KEYS:
        vals = [float(s[k]) for s in samples if s.get(k) is not None]
        out[k] = {"peak": max(vals), "mean": round(sum(vals) / len(vals), 1)} if vals else {"peak": None, "mean": None}
    return out


def parse_nvidia_smi(text: str) -> tuple[float | None, float | None]:
    """(GPU %, used VRAM MB) from `nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits`
    (the first GPU); a field that is not a number ("[N/A]") is None."""
    line = next((ln for ln in (text or "").splitlines() if ln.strip()), "")
    parts = [p.strip() for p in line.split(",")]

    def num(i):
        try:
            return float(parts[i])
        except (IndexError, ValueError):
            return None
    return num(0), num(1)


# --------------------------------------------------------------------------- sampling
class GpuSampler:
    """The latest (GPU %, used VRAM MB) from ONE `nvidia-smi -lms <every>` that streams a line per interval (starting
    nvidia-smi takes ~1-2 s on Windows: one call per sample could not keep 0.5 s). (None, None) without nvidia-smi."""

    def __init__(self, every: float = SAMPLE_S):
        import threading
        self.latest: tuple[float | None, float | None] = (None, None)
        self.p = None
        smi = shutil.which("nvidia-smi")
        if not smi:
            return
        try:
            self.p = subprocess.Popen([smi, "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits",
                                       f"-lms={max(100, int(every * 1000))}"], stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, text=True)
        except OSError:
            return
        self.t = threading.Thread(target=self._read, daemon=True)
        self.t.start()

    def _read(self):
        for line in self.p.stdout:
            got = parse_nvidia_smi(line)
            if got != (None, None):
                self.latest = got

    def sample(self) -> tuple[float | None, float | None]:
        return self.latest

    def close(self):
        if self.p is not None:
            if self.p.poll() is None:
                self.p.kill()
            self.p.wait()
            self.p.stdout.close()
            self.t.join(timeout=5)


if IS_WIN:
    import ctypes
    from ctypes import wintypes

    class _PE(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]

    class _PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _psapi = ctypes.WinDLL("psapi", use_last_error=True)
    _k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.Process32First.argtypes = _k32.Process32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PE)]
    _k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    _k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]

    def _tree(root: int) -> list[int]:
        snap = _k32.CreateToolhelp32Snapshot(0x2, 0)               # TH32CS_SNAPPROCESS
        if not snap or snap == wintypes.HANDLE(-1).value:
            return [root]
        kids: dict[int, list[int]] = {}
        try:
            e = _PE()
            e.dwSize = ctypes.sizeof(_PE)
            ok = _k32.Process32First(snap, ctypes.byref(e))
            while ok:
                kids.setdefault(e.th32ParentProcessID, []).append(e.th32ProcessID)
                ok = _k32.Process32Next(snap, ctypes.byref(e))
        finally:
            _k32.CloseHandle(snap)
        out, todo = [], [root]
        while todo:
            p = todo.pop()
            if p in out:
                continue
            out.append(p)
            todo += [c for c in kids.get(p, []) if c != p]
        return out

    def _proc(pid: int) -> tuple[float, float] | None:
        """(RSS MB, CPU seconds so far) of one process."""
        h = _k32.OpenProcess(0x1000 | 0x0010, False, pid)        # QUERY_LIMITED_INFORMATION | VM_READ
        if not h:
            return None
        try:
            pmc = _PMC()
            pmc.cb = ctypes.sizeof(_PMC)
            rss = pmc.WorkingSetSize / 2 ** 20 if _psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb) else 0.0
            c, x, k, u = (wintypes.FILETIME() for _ in range(4))
            cpu = ((k.dwHighDateTime << 32 | k.dwLowDateTime) + (u.dwHighDateTime << 32 | u.dwLowDateTime)) / 1e7 \
                if _k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(x), ctypes.byref(k), ctypes.byref(u)) else 0.0
            return rss, cpu
        finally:
            _k32.CloseHandle(h)

    def tree_usage(root: int) -> tuple[float, float]:
        rss = cpu = 0.0
        for p in _tree(root):
            got = _proc(p)
            if got:
                rss, cpu = rss + got[0], cpu + got[1]
        return rss, cpu
else:
    def tree_usage(root: int) -> tuple[float, float]:
        """(RSS MB, CPU seconds) of root and its descendants, from `ps` (Linux and macOS)."""
        try:
            r = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,rss=,time="], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return 0.0, 0.0
        rows = {}
        for ln in r.stdout.splitlines():
            f = ln.split()
            if len(f) >= 4 and f[0].isdigit() and f[1].isdigit():
                rows[int(f[0])] = (int(f[1]), float(f[2]) / 1024, _clock_s(f[3]))
        keep, todo = set(), [root]
        while todo:
            p = todo.pop()
            if p in keep or p not in rows:
                continue
            keep.add(p)
            todo += [c for c, (pp, _r, _t) in rows.items() if pp == p]
        return sum(rows[p][1] for p in keep), sum(rows[p][2] for p in keep)

    def _clock_s(t: str) -> float:
        days, _, hms = t.rpartition("-")
        parts = [float(x) for x in hms.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0.0)
        return (float(days or 0) * 24 + parts[0]) * 3600 + parts[1] * 60 + parts[2]


def _alive(pid: int) -> bool:
    if IS_WIN:
        h = _k32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        try:
            code = wintypes.DWORD()
            return bool(_k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259    # STILL_ACTIVE
        finally:
            _k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def watch(pid: int, wait_done, every: float = SAMPLE_S, clock=time.monotonic) -> list[dict]:
    """Samples of pid's tree every `every` seconds; `wait_done(s)` waits up to s seconds and says whether the process
    has ended (so the watch ends as soon as it does, not up to one interval later)."""
    samples, t0 = [], clock()
    last_t, last_cpu = t0, None
    gpu = GpuSampler(every)
    try:
        while True:
            rss, cpu = tree_usage(pid)
            now = clock()
            pct = None if last_cpu is None or now <= last_t else round(max(0.0, cpu - last_cpu) / (now - last_t) * 100,
                                                                        1)
            gp, vram = gpu.sample()
            samples.append({"t": round(now - t0, 2), "rss_mb": round(rss, 1), "cpu_pct": pct, "gpu_pct": gp,
                            "vram_mb": vram})
            last_t, last_cpu = now, cpu
            if wait_done(every):
                return samples
    finally:
        gpu.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pid", type=int, help="watch this running process instead of starting a command")
    ap.add_argument("--out", help="also write the JSON here")
    ap.add_argument("--every", type=float, default=SAMPLE_S)
    ap.add_argument("--timeout", type=float, default=None, help="kill the command after this many seconds")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    if a.pid:
        def gone(s):
            time.sleep(s)
            return not _alive(a.pid)
        t0 = time.monotonic()
        samples = watch(a.pid, gone, a.every)
        rep = {"pid": a.pid, "returncode": None}
        wall = time.monotonic() - t0
    elif cmd:
        t0 = time.monotonic()
        with subprocess.Popen(cmd) as p:
            def ended(s):
                try:
                    p.wait(timeout=s)
                    return True
                except subprocess.TimeoutExpired:
                    if a.timeout and time.monotonic() - t0 > a.timeout:
                        p.kill()                 # a stuck run: the report says "returncode" of a kill
                        p.wait()
                        return True
                    return False
            samples = watch(p.pid, ended, a.every)
            wall = time.monotonic() - t0
            rep = {"cmd": cmd, "returncode": p.wait()}
    else:
        ap.error("give a command after -- or --pid")
    rep.update(wall_s=round(wall, 2), **summarize(samples))
    text = json.dumps(rep, ensure_ascii=False, indent=2)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0 if rep.get("returncode") in (0, None) else 1


if __name__ == "__main__":
    sys.exit(main())
