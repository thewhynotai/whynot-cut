#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Keep each `claude plugin eval` run's transcripts so tools/token_report.py can measure usage per case (M5-T1, Q57-2).

Why: `--output-dir` keeps only aggregate-result.json and report.html (checked 2026-10-18 on the p3 output folders and
`claude plugin eval --help`). A run's trace is at its `tracePath` (<temp>/out/trace.jsonl) and its Claude Code
transcripts sit under that run's own config folder (<temp>/config/projects/); the runner deletes <temp> at the end
unless the eval ran with `--keep-temp`.

    claude plugin eval ./whynot-cut ... --keep-temp --output-dir <scratch> --json <scratch>/run.json
    python tools/eval_transcripts.py <scratch>/run.json --out <scratch>/transcripts
    python tools/token_report.py <scratch>/transcripts --json <scratch>/tokens.json

It COPIES (never moves) trace.jsonl and every *.jsonl / *.meta.json below <temp>/config/projects into
<out>/<case>/<arm>-run<k>/ and writes <out>/manifest.json (case, run, status, file count). Links and junctions are
never followed or copied. Case names that are not plain names are recorded as `unsafe-name` and never become folders.
<out> must be new or empty. Exit 0 when every run was collected, 3 when some were missing (the hint names
--keep-temp), 2 on bad input. Stdlib only. Not verified against a live eval run yet: the location of the run's
transcripts under <temp>/config/projects is inferred from the runner's leftover temp folders.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path

VERSION = "1.0.0"
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}")


def _is_link(path) -> bool:
    """A symlink or a Windows reparse point (junction); a path that cannot be inspected counts as one."""
    try:
        st = os.lstat(path)
    except OSError:
        return True
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & 0x400)


def _transcripts(projects: Path) -> list:
    """Relative paths of every *.jsonl and *.meta.json below `projects`, without entering links."""
    out, stack = [], [projects]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            continue
        for e in entries:
            p = Path(e.path)
            if _is_link(p):
                continue
            if e.is_dir(follow_symlinks=False):
                stack.append(p)
            elif e.name.endswith(".jsonl") or e.name.endswith(".meta.json"):
                out.append(p.relative_to(projects))
    return sorted(out)


def _runs(doc: dict) -> list:
    """[(case name, run key, tracePath or None)] in the aggregate's order."""
    out = []
    for case in doc.get("cases") or []:
        if not isinstance(case, dict):
            continue
        arms = case.get("arms")
        for arm, entries in (arms.items() if isinstance(arms, dict) else []):
            if not isinstance(entries, list):
                continue
            for k, entry in enumerate(entries, 1):
                tp = entry.get("tracePath") if isinstance(entry, dict) else None
                out.append((case.get("name"), f"{arm}-run{k}", tp if isinstance(tp, str) and tp else None))
    return out


def collect(doc: dict, out: Path) -> list:
    """Copy every run's transcripts into `out`; the manifest rows."""
    rows = []
    for case, run, trace in _runs(doc):
        row = {"case": case if isinstance(case, str) else str(case), "run": run, "status": "missing", "files": 0}
        rows.append(row)
        if not (isinstance(case, str) and SAFE_NAME.fullmatch(case) and ".." not in case
                and SAFE_NAME.fullmatch(run)):
            row["status"] = "unsafe-name"
            continue
        if trace is None:
            row["reason"] = "no tracePath"
            continue
        tp = Path(trace)
        temp = tp.parent.parent if tp.parent.name == "out" else tp.parent
        plan = []
        if tp.is_file() and not _is_link(tp):
            plan.append((tp, Path("trace.jsonl")))
        projects = temp / "config" / "projects"
        if projects.is_dir() and not _is_link(projects):
            plan += [(projects / rel, Path("projects") / rel) for rel in _transcripts(projects)]
        if not plan:
            row["reason"] = "the run's temp folder is gone (run the eval with --keep-temp)"
            continue
        dest = out / case / run
        for src, rel in plan:
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest / rel)
        row["status"], row["files"] = "collected", len(plan)
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="eval_transcripts", description=__doc__.split("\n\n")[0])
    ap.add_argument("aggregate", help="the eval's aggregate-result.json (or its --json file)")
    ap.add_argument("--out", required=True, help="a new or empty folder for the copies")
    a = ap.parse_args(argv)

    def refuse(msg):
        print(f"eval_transcripts: {msg}", file=sys.stderr)
        return 2

    try:
        with open(a.aggregate, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as e:
        return refuse(f"cannot read the aggregate result: {e}")
    if not isinstance(doc, dict) or not isinstance(doc.get("cases"), list):
        return refuse("not an eval aggregate result (no cases list)")
    if not _runs(doc):
        return refuse("the aggregate result lists no runs")
    out = Path(a.out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        return refuse(f"{out} exists and is not empty: nothing was copied")
    out.mkdir(parents=True, exist_ok=True)
    rows = collect(doc, out)
    manifest = {"tool": "eval_transcripts", "version": VERSION, "source": Path(a.aggregate).name, "runs": rows}
    with open(out / "manifest.json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    got = sum(r["status"] == "collected" for r in rows)
    print(f"eval_transcripts: {got} of {len(rows)} runs collected into {out}")
    if got < len(rows):
        print("eval_transcripts: some runs were not collected (see manifest.json); rerun the eval with --keep-temp "
              "so the runner keeps each run's temp folder", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
