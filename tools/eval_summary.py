#!/usr/bin/env python3
"""Summarise a `claude plugin eval` run of the WhyNot Cut suite (3.0 T3.7).

The runner's own exit code uses --threshold on the MEAN case score (default 1.0); the suite's bar is per case: at
least 2 of 3 runs pass, where a run passes when every scored grader passed. This prints that table from
aggregate-result.json (or the --json file) and can write the compact baseline the phase gates compare against
("hold or improve", Addendum G G2). Cases tagged `pending` are listed but not counted in the bar.

Usage:
  python tools/eval_summary.py <aggregate-result.json> [more.json ...] [--baseline-out FILE] [--label v3.0.0-p3]
Later files override earlier ones per case (e.g. a full run, then a single-case re-run).
Exit 0 when every counted case passes at least 2/3 of its runs, else 1.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "whynot-cut"


def pending_cases() -> set[str]:
    """Cases whose case.yaml tags include `pending` (placeholders for later phases)."""
    out = set()
    for cy in (PLUGIN / "evals").glob("*/case.yaml"):
        for line in cy.read_text(encoding="utf-8").splitlines():
            if line.startswith("tags:") and "pending" in line.split(":", 1)[1].replace("[", " ").replace("]", " ") \
                    .replace(",", " ").split():
                out.add(cy.parent.name)
    return out


def load(paths: list[Path]) -> tuple[dict, dict]:
    """(meta of the last file, {case: row}) with rows {passed, runs, mean_score, judge, cli, date}."""
    rows, meta = {}, {}
    for p in paths:
        d = json.loads(p.read_text(encoding="utf-8"))
        suite = d.get("suite") or {}
        meta = {"cli": d.get("claudeVersion"), "date": (d.get("startedAt") or "")[:10],
                "judge": suite.get("judgeModel") or "haiku (default)", "ablation": suite.get("ablation")}
        for c in d.get("cases", []):
            runs = [r for arm in (c.get("arms") or {}).values() for r in arm]
            if not runs:
                continue
            rows[c["name"]] = {"passed": sum(1 for r in runs if r.get("passed")), "runs": len(runs),
                               "mean_score": round(sum(r.get("score", 0) for r in runs) / len(runs), 3),
                               "errors": sum(1 for r in runs if r.get("error")), **meta}
    return meta, rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("results", nargs="+", type=Path)
    ap.add_argument("--baseline-out", type=Path)
    ap.add_argument("--label", default="")
    a = ap.parse_args(argv)
    meta, rows = load(a.results)
    pend = pending_cases()
    ok = lambda r: 3 * r["passed"] >= 2 * r["runs"]                      # noqa: E731  (>= 2/3 of the runs)
    print("| case | runs passed | mean score | judge |")
    print("|---|---|---|---|")
    for name in sorted(rows):
        r = rows[name]
        note = " (pending)" if name in pend else ("" if ok(r) else " **below 2/3**")
        print(f"| {name}{note} | {r['passed']}/{r['runs']} | {r['mean_score']:.2f} | {r['judge']} |")
    counted = {n: r for n, r in rows.items() if n not in pend}
    good = sum(ok(r) for r in counted.values())
    full = sum(r["passed"] == r["runs"] for r in counted.values())
    print(f"\n{good}/{len(counted)} counted cases pass >= 2/3 ({full} at every run); {len(rows) - len(counted)} pending; "
          f"CLI {meta.get('cli')}, judge {meta.get('judge')}, ablation {meta.get('ablation')}, {meta.get('date')}")
    if a.baseline_out:
        base = {"label": a.label, "cli": meta.get("cli"), "date": meta.get("date"), "judge": meta.get("judge"),
                "ablation": meta.get("ablation"), "bar": "a case passes when >= 2/3 of its runs pass",
                "counted": len(counted), "pass": good, "pass_every_run": full, "pending": sorted(pend & set(rows)),
                "cases": {n: {k: rows[n][k] for k in ("passed", "runs", "mean_score")} for n in sorted(rows)}}
        a.baseline_out.write_text(json.dumps(base, indent=1, ensure_ascii=False) + "\n", encoding="utf-8",
                                  newline="\n")
    return 0 if good == len(counted) else 1


if __name__ == "__main__":
    sys.exit(main())
