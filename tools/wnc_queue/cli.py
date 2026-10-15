"""wnc-queue CLI: add | list | status | result | cancel | stop | resume | run | install | uninstall | kick | paths.

    tools/wnc-queue add --title "bridge flaky hunt" --class suite --until-fail 20 --timeout 30m \\
        --owner executor -- bash tools/test.sh -p test_bridge_queue.py
    tools/wnc-queue result <id>          # exit 0 passed, 1 failed/timeout/cancelled, 2 not finished, 3 unknown id
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import core, runner, task
from .core import JobError, Paths


def _age(iso: str | None) -> str:
    if not iso:
        return "-"
    try:
        import datetime as dt
        s = (dt.datetime.now().astimezone() - dt.datetime.fromisoformat(iso)).total_seconds()
    except ValueError:
        return "?"
    for unit, n in (("d", 86400), ("h", 3600), ("m", 60)):
        if s >= n:
            return f"{int(s // n)}{unit}"
    return f"{int(s)}s"


def build_job(a: argparse.Namespace) -> dict:
    if a.file:
        try:
            job = json.loads(Path(a.file).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as e:
            raise JobError(f"--file {a.file}: {e}") from None
    else:
        argv = list(a.argv)
        if argv and argv[0] == "--":
            argv = argv[1:]
        if not argv:
            raise JobError("give the command after --, e.g. add -- bash tools/test.sh -p test_x.py")
        job = {"argv": argv}
    for key, val in (("id", a.id), ("title", a.title), ("cwd", a.cwd), ("owner", a.owner), ("heavy", a.heavy),
                     ("priority", a.priority), ("pass_regex", a.pass_regex), ("fail_regex", a.fail_regex),
                     ("max_attempts", a.max_attempts)):
        if val is not None:
            job[key] = val
    if a.timeout is not None:
        job["timeout_s"] = core.parse_duration(a.timeout)
    if a.max_wait is not None:
        job["max_wait_s"] = core.parse_duration(a.max_wait)
    if a.env:
        env = dict(job.get("env") or {})
        for kv in a.env:
            k, sep, v = kv.partition("=")
            if not sep:
                raise JobError(f"--env needs NAME=value, got {kv!r}")
            env[k] = v
        job["env"] = env
    modes = [m for m in (a.repeat, a.until_fail, a.until_streak, a.until_match) if m is not None]
    if len(modes) > 1:
        raise JobError("pick one stop condition: --repeat, --until-fail, --until-streak or --until-match")
    if a.repeat is not None:
        job["stop"] = {"mode": "repeat", "times": a.repeat}
    elif a.until_fail is not None:
        job["stop"] = {"mode": "until_fail", "max": a.until_fail}
    elif a.until_streak is not None:
        job["stop"] = {"mode": "until_streak", "k": a.until_streak, "max": a.max_runs or a.until_streak * 5}
    elif a.until_match is not None:
        job["stop"] = {"mode": "until_match", "regex": a.until_match}
    job.setdefault("cwd", str(Path.cwd()))
    return job


def kick_and_check(paths: Paths, jid: str) -> str:
    msg = task.kick(paths)
    if not msg.startswith("runner kicked"):        # detached start: nothing to re-check
        return msg
    for _ in range(30):                       # the runner may have been exiting just as we queued: kick again
        time.sleep(0.2)
        if runner.lock_is_held(paths) or not (paths.queue / f"{jid}.json").exists():
            return msg
    return task.kick(paths)


def cmd_add(a, paths):
    job = core.add_job(paths, build_job(a))
    print(job["id"])
    if not a.no_kick:
        print(kick_and_check(paths, job["id"]), file=sys.stderr)
    return 0


def _row(state, j):
    s = j.get("stop") or {}
    cur = j.get("current") or {}
    prog = f"run {cur.get('n')}" if cur else ""
    if state == "done":
        prog = f"{j.get('status')} {j.get('passes', 0)}/{j.get('iterations_run', 0)}"
    return (f"{state:<8} {j.get('id', '?'):<44} {str(j.get('priority', (j.get('job') or {}).get('priority', ''))):>4} "
            f"{(j.get('heavy') or (j.get('job') or {}).get('heavy') or ''):<6} {str(j.get('owner') or ''):<14} "
            f"{(s.get('mode') or ((j.get('job') or {}).get('stop') or {}).get('mode') or ''):<13} {prog:<16} "
            f"{_age(j.get('finished_at') or j.get('queued_at')):>5}  {str(j.get('title') or '')[:50]}")


def cmd_list(a, paths):
    paths.ensure()
    done = _jobs(paths.done, a.owner)
    rows = ([("running", j) for j in _jobs(paths.running, a.owner)]
            + [("queued", j) for j in core.queued_jobs(paths) if a.owner is None or j.get("owner") == a.owner]
            + [("done", j) for j in (done if a.all else done[:10])])
    if a.json:
        print(json.dumps([{"state": s, **{k: v for k, v in j.items() if not k.startswith("_")}} for s, j in rows],
                         indent=2, default=str))
        return 0
    print(f"{'STATE':<8} {'ID':<44} {'PRIO':>4} {'CLASS':<6} {'OWNER':<14} {'STOP':<13} {'PROGRESS':<16} {'AGE':>5}  TITLE")
    for s, j in rows:
        if j:
            print(_row(s, j))
    return 0


RECENT_H = 24
SHOW_MAX = 5
DELIBERATE = ("cancelled", "stopped")      # someone chose these: counted, never flagged
STUCK_S = 15 * 60                          # queued this long with no runner = the scheduler is not picking it up


def _queued_age(j: dict) -> float:
    if isinstance(j.get("queued_ns"), int):
        return time.time() - j["queued_ns"] / 1e9
    try:                                       # a hand-written job: the file's age
        return time.time() - j["_file"].stat().st_mtime
    except (KeyError, OSError):
        return 0.0


def _runner_problems(paths, hb: dict, alive: bool, running: list, queued: list, stop: bool) -> list[str]:
    """What a resuming session must not read as healthy: work waiting with no runner, or a runner that crashed."""
    out = []
    if alive:
        return out
    if running:
        out.append(f"{len(running)} job(s) in running/ but no runner: the next start recovers them "
                   "(`wnc-queue kick` starts one now)")
    if hb.get("state") == "crashed":
        out.append(f"the last runner crashed ({hb.get('heartbeat')}): see {paths.runner_log}")
    if queued and not stop:
        oldest = max((_queued_age(j) for j in queued), default=0)
        if oldest > STUCK_S:
            out.append(f"jobs queued {int(oldest // 60)} min with no runner: `wnc-queue kick`, then check "
                       f"{paths.runner_log}")
    return out


def _jobs(d: Path, owner: str | None) -> list[dict]:
    out = []
    for f in d.glob("*.json"):
        if f.name.endswith(".spec.json"):
            continue
        j = core.read_json(f)
        if isinstance(j, dict) and (owner is None or j.get("owner") == owner):
            try:
                j["_mtime"] = f.stat().st_mtime
            except OSError:                       # moved on (running -> done) while we read it
                continue
            out.append(j)
    return sorted(out, key=lambda j: j["_mtime"], reverse=True)


def _short(text, n=110) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "..."


def cmd_status(a, paths):
    """Result first: one verdict line (OK / ATTENTION), then only the jobs worth a look, then one line of details."""
    paths.ensure()
    hb = core.read_json(paths.runner_json) or {}
    alive = runner.lock_is_held(paths)
    owner = a.owner
    running = _jobs(paths.running, owner)
    unreadable: list = []
    queued = [j for j in core.queued_jobs(paths, unreadable) if owner is None or j.get("owner") == owner]
    done = _jobs(paths.done, owner)
    recent = [j for j in done if j["_mtime"] >= time.time() - RECENT_H * 3600]
    bad = [j for j in recent if j.get("status") not in ("passed", *DELIBERATE)]
    stop, installed = paths.stop.exists(), task.installed()
    problems = (["STOP is set: nothing runs until `wnc-queue resume`"] if stop else []) + \
               ([] if installed else ["scheduled task NOT installed: run `wnc-queue install`"]) + \
               _runner_problems(paths, hb, alive, running, queued, stop) +                ([f"{len(unreadable)} queue file(s) are not valid JSON: "
                 + ", ".join(f.name for f in unreadable[:3])] if unreadable else []) + \
               ([f"{len(bad)} job(s) failed in the last {RECENT_H} h"] if bad else [])
    verdict = "ATTENTION" if problems else "OK"
    chosen = sum(1 for j in recent if j.get("status") in DELIBERATE)
    head = (f"{verdict}: {len(running)} running, {len(queued)} queued, last {RECENT_H} h "
            f"{len(recent) - len(bad) - chosen} passed / {len(bad)} failed"
            + (f" / {chosen} cancelled or stopped" if chosen else "") + (f" (owner {owner})" if owner else ""))
    if a.json:
        print(json.dumps({
            "headline": head, "verdict": verdict, "problems": problems,
            "running_jobs": [{"id": j.get("id"), "owner": j.get("owner"), "run": (j.get("current") or {}).get("n"),
                              "title": j.get("title")} for j in running],
            "failed_recent": [{"id": j.get("id"), "status": j.get("status"), "summary": j.get("summary")}
                                  for j in bad],
            "home": str(paths.home), "runner_alive": alive, "runner": hb, "STOP": stop, "task_installed": installed,
            "queued": len(queued), "running": len(running), "done": len(done),
        }, indent=2, default=str))
        return 0
    print(head)
    for p in problems:
        print(f"  ! {p}")
    for j in running[:SHOW_MAX]:
        cur = j.get("current") or {}
        print(f"  running  {j.get('id')}  run {cur.get('n', '?')}, {_age(cur.get('since'))}  {_short(j.get('title'), 60)}")
    for j in bad[:SHOW_MAX]:
        print(f"  {str(j.get('status')).upper():<9}{j.get('id')}  {_age(j.get('finished_at'))} ago  {_short(j.get('summary'))}")
    hidden = max(0, len(running) - SHOW_MAX) + max(0, len(bad) - SHOW_MAX)
    if hidden:
        print(f"  ... {hidden} more: wnc-queue list")
    print(f"  details: runner {'pid ' + str(hb.get('pid')) if alive else 'idle'} | task "
          f"{core.TASK_NAME if installed else 'missing'} | STOP {'yes' if stop else 'no'} | {len(done)} done records "
          f"| {paths.home}")
    return 0


def cmd_result(a, paths):
    """Result first: line 1 is the verdict and summary; then counts, peaks and the log. The output tail is shown only
    when the job did not pass (or when --tail N asks for it)."""
    found = core.find(paths, a.id)
    if not found:
        print(f"no job {a.id}", file=sys.stderr)
        return 3
    state, j = found
    if a.json:
        print(json.dumps(j, indent=2, ensure_ascii=False))
    elif state != "done":
        cur = j.get("current") or {}
        print(f"{state.upper()}: {a.id}" + (f", run {cur.get('n')} for {_age(cur.get('since'))}" if cur else "")
              + f", {len(j.get('iterations', []))} runs finished so far")
    else:
        pk = j.get("peak") or {}
        print(j.get("headline") or core.headline(j))
        print(f"  {j.get('passes')}/{j.get('iterations_run')} runs passed | exit {j.get('exit_code')} | waited "
              f"{core.fmt_secs(j.get('wait_s'))} | finished {_age(j.get('finished_at'))} ago ({j.get('finished_at')})")
        if pk:
            print(f"  peak: job RAM {pk.get('ram_mb')} MB | job CPU {pk.get('cpu_pct')}% | system RAM "
                  f"{pk.get('sys_ram_pct')}% | GPU {pk.get('gpu_pct')}% | VRAM {pk.get('vram_mb')} MB")
        print(f"  log: {j.get('log')}")
        n = a.tail if a.tail is not None else (0 if j.get("status") == "passed" else 15)
        for line in (j.get("tail") or [])[-n:] if n else []:
            print(f"  | {line}")
    if state != "done":
        return 2
    return 0 if j.get("status") == "passed" else 1


def cmd_cancel(a, paths):
    print(core.cancel_job(paths, a.id))
    return 0


def cmd_stop(a, paths):
    paths.ensure()
    paths.stop.write_text(f"STOP {core.now_iso()}\n", encoding="utf-8")
    print(f"STOP set ({paths.stop}): running jobs are killed within seconds; queued jobs wait for `resume`")
    return 0


def cmd_resume(a, paths):
    core.unlink(paths.stop)
    print("STOP removed")
    if any(paths.queue.glob("*.json")):
        print(task.kick(paths))
    return 0


def cmd_run(a, paths):
    return runner.Runner(paths).run()


def cmd_install(a, paths):
    print(task.install(paths, dry_run=a.dry_run))
    return 0


def cmd_uninstall(a, paths):
    print(task.uninstall())
    return 0


def cmd_kick(a, paths):
    print(task.kick(paths))
    return 0


def cmd_paths(a, paths):
    for k in ("home", "queue", "running", "done", "logs", "stop", "config"):
        print(f"{k:<8} {getattr(paths, k)}")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wnc-queue", description="detached per-user runner for long NON-AI dev jobs")
    p.add_argument("--home", help="queue folder (default D:\\ClaudeData\\jobs, or $WNC_QUEUE_HOME)")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--home", default=argparse.SUPPRESS, help=argparse.SUPPRESS)   # also accepted after the command
    sub = p.add_subparsers(dest="cmd", required=True)
    _add = sub.add_parser
    sub.add_parser = lambda *a, **k: _add(*a, parents=[common], **k)  # noqa: E731
    s = sub.add_parser("add", help="queue a job; prints its id")
    s.add_argument("--file", help="a job JSON file instead of a command")
    s.add_argument("--id")
    s.add_argument("--title")
    s.add_argument("--cwd", help="default: the current folder (must be inside the repo or D:\\ClaudeData)")
    s.add_argument("--class", dest="heavy", choices=core.CLASSES, help="heavy.sh slot (default cpu)")
    s.add_argument("--timeout", help="per run, after the slot is held (default 1h): 90, 30m, 2h")
    s.add_argument("--max-wait", help="max wait for a heavy.sh slot (default 6h)")
    s.add_argument("--repeat", type=int, metavar="N", help="run N times")
    s.add_argument("--until-fail", type=int, metavar="N", help="run up to N times, stop at the first failure")
    s.add_argument("--until-streak", type=int, metavar="K", help="run until K consecutive passes (see --max-runs)")
    s.add_argument("--max-runs", type=int, help="cap for --until-streak (default 5*K)")
    s.add_argument("--until-match", metavar="REGEX", help="run once; pass and stop as soon as REGEX appears")
    s.add_argument("--pass-regex", help="a run passes only if this appears (and exit 0)")
    s.add_argument("--fail-regex", help="a run fails if this appears")
    s.add_argument("--env", action="append", metavar="NAME=VALUE")
    s.add_argument("--owner", help="your track (executor, adobe, installer, guide, wnc-queue)")
    s.add_argument("--priority", type=int, help="-100..100, higher first (default 0)")
    s.add_argument("--max-attempts", type=int,
                   help="starts allowed (default 3: it survives 2 runner deaths, then 'stranded')")
    s.add_argument("--no-kick", action="store_true", help="don't start the runner now")
    s.add_argument("argv", nargs=argparse.REMAINDER)
    s.set_defaults(fn=cmd_add)
    s = sub.add_parser("list", help="queued, running and recent done jobs")
    s.add_argument("--all", action="store_true")
    s.add_argument("--owner", help="only this track's jobs")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_list)
    s = sub.add_parser("status", help="one verdict line, the jobs worth a look, then details")
    s.add_argument("--owner", help="only this track's jobs")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_status)
    s = sub.add_parser("result", help="a job's outcome (exit 0 passed / 1 not passed / 2 unfinished / 3 unknown)")
    s.add_argument("id")
    s.add_argument("--json", action="store_true")
    s.add_argument("--tail", type=int, help="output lines to show (default: 15 when it did not pass, 0 when it did)")
    s.set_defaults(fn=cmd_result)
    s = sub.add_parser("cancel", help="cancel a queued or running job")
    s.add_argument("id")
    s.set_defaults(fn=cmd_cancel)
    for name, fn, h in (("stop", cmd_stop, "set the STOP kill switch"), ("resume", cmd_resume, "remove STOP"),
                        ("run", cmd_run, "run the runner in the foreground (the scheduled task does this)"),
                        ("uninstall", cmd_uninstall, "remove the scheduled task"),
                        ("kick", cmd_kick, "start the runner now"), ("paths", cmd_paths, "print the folders")):
        sub.add_parser(name, help=h).set_defaults(fn=fn)
    s = sub.add_parser("install", help="install the per-user scheduled task (no admin)")
    s.add_argument("--dry-run", action="store_true", help="print the task XML only")
    s.set_defaults(fn=cmd_install)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):            # an Arabic summary or tail line must not crash a cp1252 console
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    a = parser().parse_args(argv)
    paths = Paths(a.home)
    try:
        return a.fn(a, paths)
    except JobError as e:
        print(f"wnc-queue: {e}", file=sys.stderr)
        return 4
