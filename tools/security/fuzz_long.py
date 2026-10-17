#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""The long fuzz profile (Addendum L §L4.4, Phase 4 Task 48 / L-T10). Stdlib only. Run it through heavy.sh at a gate:

  bash "$HEAVY" job fuzz-long -- python tools/security/fuzz_long.py [--only test_fuzz_serve]

It runs each tests/test_fuzz_*.py with WNC_FUZZ_PROFILE=long (random seeds), collects the
`FUZZ-COUNT <test> <n> cap <c> space <s> heavy <bytes>` lines every run prints, and writes JSON + Markdown under dist/fuzz-long/.

The rule (executor ruling): EVERY target runs 10,000 examples. The only exception is a target whose single example is 100 KB or
more (`fuzz(heavy=<bytes>)` in tests/security/fuzz/_hyp.py): a HEAVY waiver, 1,500 examples, listed in the report with the
target name and the example size. A target whose strategy space is provably smaller than its required count
(`fuzz(space=<n>)`) is satisfied by exhausting that space. Exit code 0 only when every file passed AND no target ran fewer
examples than required (see `check_counts`); otherwise a clear message names each target and the count it missed.
The scratch folders of the run live in one per-run root (WNC_FUZZ_SCRATCH) that this script removes at the end, also when the
test process was ended by its watchdog (which cannot run cleanup code).
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fsutil import which_safe  # noqa: E402

REPO = HERE.parent.parent
TESTS = REPO / "whynot-cut" / "tests"
NO_TARGETS = ("test_fuzz_regressions",)     # the only test_fuzz_*.py file that holds no fuzz() target


def discover_files(tests=TESTS):
    """Every tests/test_fuzz_*.py with fuzz targets, found on disk so a new file cannot be left out of the gate."""
    return sorted(p.stem for p in Path(tests).glob("test_fuzz_*.py") if p.stem not in NO_TARGETS)


FILES = discover_files()
LIGHT_REQUIRED = 10000      # examples every target must run
HEAVY_REQUIRED = 1500       # examples a declared heavy target must run
HEAVY_MIN_BYTES = 100_000   # a heavy waiver needs a single example of at least this size
COUNT_RE = re.compile(r"^FUZZ-COUNT (\S+) (\d+) cap (\S+) space (\S+) heavy (\S+)$")


def _opt_int(text):
    return None if text == "None" else int(text)


def parse_counts(text):
    """The FUZZ-COUNT lines of a run's output -> [{test, count, cap, space, heavy}]."""
    out = []
    for ln in text.splitlines():
        m = COUNT_RE.match(ln.strip())
        if m:
            out.append({"test": m.group(1), "count": int(m.group(2)), "cap": _opt_int(m.group(3)),
                        "space": _opt_int(m.group(4)), "heavy": _opt_int(m.group(5))})
    return out


def required_for(c, light=LIGHT_REQUIRED, heavy=HEAVY_REQUIRED):
    """(examples this target must have run, why it may be fewer or None). `space` counts only when it is below the requirement."""
    need = heavy if c.get("heavy") else light
    space = c.get("space")
    if space is not None and space < need:
        return space, "space exhausted at %d" % space
    return need, None


def check_counts(counts, light=LIGHT_REQUIRED, heavy=HEAVY_REQUIRED, heavy_min_bytes=HEAVY_MIN_BYTES):
    """The problems in a list of parsed FUZZ-COUNT entries: a target that ran fewer examples than required (10,000, or 1,500 for a
    declared heavy target, or its whole space when that is smaller), a cap lowered below the requirement, a heavy waiver for an
    example under 100 KB, a `space` that is not smaller than the requirement. Empty list = the gate's example counts hold."""
    problems = []
    for c in counts:
        name = c["test"]
        heavy_size = c.get("heavy")
        if heavy_size is not None and heavy_size < heavy_min_bytes:
            problems.append({"test": name, "count": c["count"], "want": light,
                             "why": "heavy waiver for an example of only %d bytes (needs %d)" % (heavy_size, heavy_min_bytes)})
            continue
        need = heavy if heavy_size else light
        if c.get("space") is not None and c["space"] >= need:
            problems.append({"test": name, "count": c["count"], "want": need,
                             "why": "space %d is not smaller than the %d required examples" % (c["space"], need)})
            continue
        want, _ = required_for(c, light, heavy)
        if c["count"] < want:
            lowered = " (cap lowered to %s)" % c["cap"] if c.get("cap") is not None and c["cap"] < want else ""
            problems.append({"test": name, "count": c["count"], "want": want,
                             "why": "ran %d of the %d required examples%s" % (c["count"], want, lowered)})
    return problems


def waivers(counts):
    """The heavy targets with the size of one example, for the report."""
    return [{"test": c["test"], "bytes": c["heavy"], "required": HEAVY_REQUIRED, "ran": c["count"]} for c in counts if c.get("heavy")]


def run_file(bash, name, env, log):
    t0 = time.time()
    with open(log, "wb") as f:
        p = subprocess.run([bash, "tools/test.sh", "-p", name + ".py"], cwd=str(REPO), env=env, stdout=f, stderr=subprocess.STDOUT)
    text = Path(log).read_text(encoding="utf-8", errors="replace")
    counts = parse_counts(text)
    ran = re.search(r"^Ran (\d+) tests? in ([\d.]+)s", text, re.M)
    return {"file": name, "rc": p.returncode, "seconds": round(time.time() - t0), "tests": int(ran.group(1)) if ran else None,
            "counts": counts, "log": str(log)}


def report(results, today, smoke=None):
    lines = ["# Long fuzz profile (%s)" % today, ""]
    if smoke:
        lines += ["**SMOKE RUN (%d examples per target): NOT a gate result.**" % smoke, ""]
    lines += ["Every target runs %d examples; a HEAVY waiver (single example of %d bytes or more) runs %d. A target below its requirement "
              "fails the run." % (LIGHT_REQUIRED, HEAVY_MIN_BYTES, HEAVY_REQUIRED), "",
              "| File | rc | seconds | tests | targets | below target |", "|---|---|---|---|---|---|"]
    for r in results:
        lines.append("| %s | %d | %d | %s | %d | %d |" % (r["file"], r["rc"], r["seconds"], r["tests"], len(r["counts"]), len(r["below_target"])))
    lines += ["", "## HEAVY waivers (single example of 100 KB or more)", ""]
    waived = [dict(w, file=r["file"]) for r in results for w in waivers(r["counts"])]
    if waived:
        lines += ["| Target | Example size (bytes) | Required | Ran |", "|---|---|---|---|"]
        lines += ["| %s | %d | %d | %d |" % (w["test"], w["bytes"], w["required"], w["ran"]) for w in waived]
    else:
        lines.append("None: every target ran the full count.")
    lines += ["", "## Targets exhausted by a small strategy space", ""]
    spaced = [c for r in results for c in r["counts"] if c["space"] is not None]
    lines += ["- %s: space %d, ran %d" % (c["test"], c["space"], c["count"]) for c in spaced] or ["None."]
    problems = [(r["file"], p) for r in results for p in r["below_target"]]
    lines += ["", "## Below target", ""]
    lines += ["- BELOW TARGET %s: %s" % (p["test"], p["why"]) for _, p in problems] or ["None."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append")
    ap.add_argument("--out", default=str(REPO / "dist" / "fuzz-long"))
    ap.add_argument("--smoke", type=int, default=0, metavar="N",
                    help="run N examples per target to try this script out; always exits 3 (a smoke run is never a pass)")
    a = ap.parse_args(argv)
    bash = which_safe("bash")
    if not bash:
        print("bash not found on PATH", file=sys.stderr)
        return 4
    locks = os.environ.get("WNC_LOCKS_DIR")      # set by the machine's job runner (heavy.sh); unset elsewhere: nothing to check
    if locks and (Path(locks) / "FREEZE").exists():
        print("FREEZE is set: start nothing that runs the engine runtime", file=sys.stderr)
        return 75
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="wncfuzz-run-")
    examples = a.smoke or LIGHT_REQUIRED
    heavy = a.smoke or HEAVY_REQUIRED
    env = dict(os.environ, WNC_FUZZ_PROFILE="long", WNC_FUZZ_EXAMPLES=str(examples), WNC_FUZZ_HEAVY_EXAMPLES=str(heavy),
               WNC_FUZZ_SCRATCH=scratch)
    results, failed = [], False
    try:
        for name in (a.only or FILES):
            r = run_file(bash, name, env, out / (name + ".log"))
            r["below_target"] = check_counts(r["counts"]) if not a.smoke else []
            failed = failed or r["rc"] != 0 or bool(r["below_target"]) or not r["counts"]
            results.append(r)
            print("%-20s rc=%d %5ds tests=%s targets=%d below=%d" % (name, r["rc"], r["seconds"], r["tests"], len(r["counts"]), len(r["below_target"])), flush=True)
            for p in r["below_target"]:
                print("  BELOW TARGET %s: %s" % (p["test"], p["why"]), file=sys.stderr, flush=True)
            if not r["counts"]:
                print("  NO FUZZ-COUNT lines in %s: the long profile did not run (is Hypothesis installed?)" % r["log"], file=sys.stderr, flush=True)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    today = datetime.date.today().isoformat()
    (out / ("fuzz-long-%s.json" % today)).write_text(json.dumps(results, indent=1), encoding="utf-8")
    (out / ("fuzz-long-%s.md" % today)).write_text(report(results, today, a.smoke or None), encoding="utf-8")
    if failed:
        print("FUZZ LONG PROFILE FAILED: see the rc and BELOW TARGET lines above", file=sys.stderr)
        return 1
    if a.smoke:
        print("smoke run only: not a gate pass", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
