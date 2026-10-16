"""Start a job's process tree so it can be measured and killed as a whole.

Windows: every job runs in its own Job Object (created suspended, assigned, then resumed: no child escapes), with
KILL_ON_JOB_CLOSE, so a timeout, cancel or STOP kills the whole tree, and a runner that dies (crash, reboot, restart)
takes its jobs with it; recovery then re-queues them. The Job Object also gives peak commit memory and CPU time.
POSIX: a new session (process group) killed with SIGKILL; peaks are not measured there (the Mac variant is a later add).
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time

IS_WIN = os.name == "nt"
CREATE_NO_WINDOW = 0x08000000
CREATE_SUSPENDED = 0x00000004

if IS_WIN:
    import ctypes
    from ctypes import wintypes as wt

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _nt = ctypes.WinDLL("ntdll")

    class _IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class _BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wt.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wt.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wt.DWORD), ("SchedulingClass", wt.DWORD)]

    class _EXT(ctypes.Structure):
        _fields_ = [("Basic", _BASIC), ("Io", _IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class _MEMUSE(ctypes.Structure):          # JOBOBJECT_MEMORY_USAGE_INFORMATION (class 28, Windows 10+)
        _fields_ = [("JobMemory", ctypes.c_ulonglong), ("PeakJobMemoryUsed", ctypes.c_ulonglong)]

    class _ACCT(ctypes.Structure):
        _fields_ = [("TotalUserTime", ctypes.c_longlong), ("TotalKernelTime", ctypes.c_longlong),
                    ("ThisPeriodTotalUserTime", ctypes.c_longlong), ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                    ("TotalPageFaultCount", wt.DWORD), ("TotalProcesses", wt.DWORD),
                    ("ActiveProcesses", wt.DWORD), ("TotalTerminatedProcesses", wt.DWORD)]

    class _MEMSTAT(ctypes.Structure):
        _fields_ = [("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD)] + \
                   [(n, ctypes.c_ulonglong) for n in ("t", "a", "tp", "ap", "tv", "av", "ae")]

    _k32.CreateJobObjectW.restype = wt.HANDLE
    _k32.CreateJobObjectW.argtypes = [wt.LPVOID, wt.LPCWSTR]
    _k32.SetInformationJobObject.argtypes = [wt.HANDLE, ctypes.c_int, wt.LPVOID, wt.DWORD]
    _k32.QueryInformationJobObject.argtypes = [wt.HANDLE, ctypes.c_int, wt.LPVOID, wt.DWORD, wt.LPVOID]
    _k32.AssignProcessToJobObject.argtypes = [wt.HANDLE, wt.HANDLE]
    _k32.TerminateJobObject.argtypes = [wt.HANDLE, wt.UINT]
    _k32.CloseHandle.argtypes = [wt.HANDLE]
    _k32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_MEMSTAT)]
    _nt.NtResumeProcess.argtypes = [wt.HANDLE]
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000


def system_ram_pct() -> int | None:
    if IS_WIN:
        m = _MEMSTAT()
        m.dwLength = ctypes.sizeof(_MEMSTAT)
        if _k32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return int(m.dwMemoryLoad)
        return None
    try:
        info = {}
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                k, v = line.split(":", 1)
                info[k] = int(v.split()[0])
        return int(100 - 100 * info["MemAvailable"] / info["MemTotal"])
    except (OSError, KeyError, ValueError):
        return None


def system_ram_total_mb() -> float | None:
    """Physical RAM of the machine in MB (the job's share of it decides whose memory pressure it was)."""
    if IS_WIN:
        m = _MEMSTAT()
        m.dwLength = ctypes.sizeof(_MEMSTAT)
        if _k32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return round(m.t / 2 ** 20, 1)
        return None
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except (OSError, ValueError, IndexError):
        pass
    return None


def gpu_sample() -> tuple[int, int] | None:
    """(GPU utilisation %, VRAM used MB) of the first NVIDIA GPU, machine-wide; None without nvidia-smi."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10,
                             creationflags=CREATE_NO_WINDOW if IS_WIN else 0).stdout
        u, m = out.strip().splitlines()[0].split(",")[:2]
        return int(float(u)), int(float(m))
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


class Tree:
    """One started command and every process it spawns."""

    def __init__(self, argv: list[str], cwd: str, env: dict):
        self.job = None
        self.in_job = False
        self.started = time.monotonic()
        if IS_WIN:
            self.job = _k32.CreateJobObjectW(None, None)
            if self.job:
                ext = _EXT()
                ext.Basic.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                _k32.SetInformationJobObject(self.job, 9, ctypes.byref(ext), ctypes.sizeof(ext))
            try:
                self.proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                             creationflags=CREATE_NO_WINDOW | CREATE_SUSPENDED)
            except OSError:
                if self.job:
                    _k32.CloseHandle(self.job)
                    self.job = None
                raise
            self.pid = self.proc.pid                     # kill() needs it if the resume below fails
            if self.job and _k32.AssignProcessToJobObject(self.job, int(self.proc._handle)):
                self.in_job = True
            if _nt.NtResumeProcess(int(self.proc._handle)) != 0:     # NTSTATUS: a suspended child would hang
                self.close()
                raise OSError("could not resume the job process")
        else:
            self.proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, start_new_session=True)
        self.pid = self.proc.pid

    def poll(self):
        return self.proc.poll()

    def kill(self) -> None:
        """Kill the whole tree (also orphans that outlived the top process)."""
        if IS_WIN:
            if self.in_job:
                _k32.TerminateJobObject(self.job, 1)
            else:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.pid)], capture_output=True,
                               creationflags=CREATE_NO_WINDOW)
        else:
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        try:
            self.proc.kill()
        except OSError:
            pass

    def stats(self) -> dict:
        """{"cpu_s": total CPU seconds, "peak_mb": peak commit of the tree, "mem_mb": its commit right now,
        "active": live processes} or {} (each key only when Windows answered)."""
        if not (IS_WIN and self.in_job):
            return {}
        a, e = _ACCT(), _EXT()
        ok1 = _k32.QueryInformationJobObject(self.job, 1, ctypes.byref(a), ctypes.sizeof(a), None)
        ok2 = _k32.QueryInformationJobObject(self.job, 9, ctypes.byref(e), ctypes.sizeof(e), None)
        out = {}
        if ok1:
            out["cpu_s"] = (a.TotalUserTime + a.TotalKernelTime) / 1e7
            out["active"] = int(a.ActiveProcesses)
        if ok2:
            out["peak_mb"] = round(e.PeakJobMemoryUsed / 2 ** 20, 1)
        m = _MEMUSE()
        if _k32.QueryInformationJobObject(self.job, 28, ctypes.byref(m), ctypes.sizeof(m), None):
            out["mem_mb"] = round(m.JobMemory / 2 ** 20, 1)
        return out

    def close(self) -> None:
        """Release the Job Object handle (kills anything still inside: KILL_ON_JOB_CLOSE)."""
        try:
            if self.proc.stdout:
                self.proc.stdout.close()
        except OSError:
            pass
        if self.proc.poll() is None:
            self.kill()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        if IS_WIN and self.job:
            _k32.CloseHandle(self.job)
            self.job = None
