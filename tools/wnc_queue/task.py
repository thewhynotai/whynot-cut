"""The per-user scheduled task that starts the runner (Windows: schtasks, current user, no admin).

Triggers: at logon and every 10 minutes; IgnoreNew (one instance) on top of the runner's own lock; no time limit;
runs on battery; Normal priority (task priority 5). The runner exits when the queue is empty, so an idle machine pays
one short Python start every 10 minutes. `kick` starts it at once after `add`. macOS launchd variant: later (noted in
docs/dev/wnc-queue.md), not built.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from . import core
from .core import Paths

ENTRY = core.TOOLS / "wnc-queue.py"
NO_WINDOW = 0x08000000 if core.IS_WIN else 0


def gui_python() -> str:
    p = Path(sys.executable)
    w = p.with_name("pythonw.exe")
    return str(w) if core.IS_WIN and w.is_file() else str(p)


def user_id() -> str:
    dom, user = os.environ.get("USERDOMAIN", ""), os.environ.get("USERNAME", "")
    return f"{dom}\\{user}" if dom else user


def task_xml(paths: Paths, python_w: str | None = None, user: str | None = None, logon: bool = True,
             start: str = "2026-01-01T00:00:00") -> str:
    python_w, user = python_w or gui_python(), user or user_id()
    args = f'-B "{ENTRY}" run --home "{paths.home}"'
    logon_xml = (f"<LogonTrigger><Enabled>true</Enabled><UserId>{escape(user)}</UserId></LogonTrigger>"
                 if logon else "")
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>wnc-queue runner (WhyNot Cut dev tool, tools/wnc_queue): runs queued NON-AI jobs from {escape(str(paths.home))} and exits when the queue is empty. Stop: create the STOP file there.</Description>
    <URI>\\{core.TASK_NAME}</URI>
  </RegistrationInfo>
  <Triggers>
    {logon_xml}
    <TimeTrigger>
      <Repetition><Interval>PT10M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>{start}</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{escape(user)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>5</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(python_w)}</Command>
      <Arguments>{escape(args)}</Arguments>
      <WorkingDirectory>{escape(str(paths.home))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, creationflags=NO_WINDOW)


def installed() -> bool:
    return core.IS_WIN and _schtasks("/query", "/tn", core.TASK_NAME).returncode == 0


def install(paths: Paths, dry_run: bool = False) -> str:
    if not core.IS_WIN:
        raise SystemExit("install: Windows only for now (a macOS launchd agent is a later add)")
    paths.ensure()
    xml_path = paths.home / "task.xml"
    xml = task_xml(paths)
    if dry_run:
        return xml
    xml_path.write_text(xml, encoding="utf-16")
    r = _schtasks("/create", "/tn", core.TASK_NAME, "/xml", str(xml_path), "/f")
    if r.returncode != 0:                     # a logon trigger may need rights this user lacks: the 10-min trigger
        xml_path.write_text(task_xml(paths, logon=False), encoding="utf-16")     # still starts it after logon
        r2 = _schtasks("/create", "/tn", core.TASK_NAME, "/xml", str(xml_path), "/f")
        if r2.returncode != 0:
            raise SystemExit(f"schtasks /create failed: {r.stderr.strip()} / {r2.stderr.strip()}")
        return f"installed {core.TASK_NAME} (every 10 min; logon trigger refused: {r.stderr.strip()})"
    return f"installed {core.TASK_NAME} (at logon + every 10 min)"


def uninstall() -> str:
    r = _schtasks("/delete", "/tn", core.TASK_NAME, "/f")
    return "removed" if r.returncode == 0 else f"not removed: {r.stderr.strip()}"


def query() -> str:
    r = _schtasks("/query", "/tn", core.TASK_NAME, "/v", "/fo", "LIST")
    return r.stdout if r.returncode == 0 else ""


def kick(paths: Paths) -> str:
    """Start the runner now. Through the scheduled task when installed (it then outlives every Claude session)."""
    if installed():
        r = _schtasks("/run", "/tn", core.TASK_NAME)
        if r.returncode == 0:
            return "runner kicked (scheduled task)"
    argv = [gui_python(), "-B", str(ENTRY), "run", "--home", str(paths.home)]
    dn = subprocess.DEVNULL
    if core.IS_WIN:
        base = 0x00000008 | 0x00000200                     # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        for flags in (base | 0x01000000, base):            # | CREATE_BREAKAWAY_FROM_JOB when the parent job allows
            try:
                subprocess.Popen(argv, creationflags=flags, stdin=dn, stdout=dn, stderr=dn, close_fds=True)
                return ("runner started detached (the scheduled task is NOT installed: run `wnc-queue install`, "
                        "or this runner may stop with the Claude app)")
            except OSError:
                continue
        raise SystemExit("could not start the runner")
    subprocess.Popen(argv, stdin=dn, stdout=dn, stderr=dn, start_new_session=True)
    return "runner started detached (no scheduler on this OS yet)"
