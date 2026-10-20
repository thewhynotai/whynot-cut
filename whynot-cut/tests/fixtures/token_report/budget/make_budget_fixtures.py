# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Builds the budget fixtures of tests/test_token_report_budget.py (Addendum M, M5-T2, report-only at Gate 4).

Three recorded single-clip runs (r1, r2, r3) in the Claude Code transcript layout (main session + one subagent), a
transcript.json per run where the run has one, and two runs files:
  runs.json          the plain fixture: r1, r2, r3, all complete with passing quality graders -> PASS
  runs-planted.json  the same with r2 replaced by r2x3, every usage number of r2 times 3 -> FAIL naming r2x3
Record helpers come from ../make_fixtures.py (the real Claude Code key names; the content is made up). The fictional
client name, path and prompt planted there sit in every record, in the run folder names, in the transcript's source
path and in the video id, so the anonymisation test can look for them in the tool's output.

The M5.2 unit (what the budgets are judged in): fresh x1, 5m write x1.25, 1h write x2, cache read x0.1, output x5,
scaled per model by its fresh input price over the lead's (claude-opus-5-5 $4: Opus x1, claude-sonnet-5-5 $2: x0.5).
One run = BASE (hand-calculated below) + TURNS identical lead turns + one last turn whose fresh input makes the run
total exactly its target, so the tests can assert the targets without recomputing the tool's formula.

    python make_budget_fixtures.py     rewrite the committed fixture files next to this script
The test suite checks that the committed files equal what this script builds (no drift).
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_mf():
    spec = importlib.util.spec_from_file_location("wnc_token_report_fixtures_b", HERE.parent / "make_fixtures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MF = _load_mf()
PROJECT_DIR = MF.PROJECT_DIR                      # path-mangled planted client folder name
VIDEO_ID = "ZORBLAX_C01"                          # holds the planted client name: must never be printed
COMMIT = "1234567890abcdef1234567890abcdef12345678"
GRADERS = ("plan-validation", "qc-frames")

# Hand calculation of BASE, M5.2 unit (Opus x1):
#   m1 setup            fresh 2,000 + w5 40,000 x1.25 + out 1,000 x5               =  2,000 + 50,000 + 5,000 =  57,000
#   m2 preflight        fresh 100 + read 60,000 x0.1 + out 500 x5                 =    100 +  6,000 + 2,500 =   8,600
#   m3 transcribe+spawn fresh 50 + read 80,000 x0.1 + out 800 x5                  =     50 +  8,000 + 4,000 =  12,050
#   m4 plan             fresh 100 + w1 20,000 x2 + read 100,000 x0.1 + out 2,000x5 = 100+40,000+10,000+10,000 = 60,100
#   m5 previews         fresh 100 + read 120,000 x0.1 + out 1,000 x5              =    100 + 12,000 + 5,000 =  17,100
#   subagent (Sonnet)   (fresh 1,000 + w5 100,000 x1.25 + read 200,000 x0.1 + out 20,000 x5) x0.5
#                       = (1,000 + 125,000 + 20,000 + 100,000) x 0.5                                     = 123,000
#   BASE = 57,000 + 8,600 + 12,050 + 60,100 + 17,100 + 123,000                                          = 277,850
# One lead turn (reel qc loop): fresh 100 + read 140,000 x0.1 + out 20,000 x5 = 100 + 14,000 + 100,000   = 114,100
#   (its context is 100 + 140,000 = 140,100: inside the 150,000 guard rail)
BASE = 277_850
TURN = 114_100
TURN_CONTEXT = 140_100
RUNS = {        # run: (target weighted, M5.2 unit; lead turns; transcript duration_ms or None)
    "r1": (1_900_000, 14, 54_300),
    "r2": (2_100_000, 15, 60_000),
    "r3": (2_300_000, 17, None),
}
# r1: 277,850 + 14 x 114,100 = 1,875,250 -> last turn fresh 24,750 -> 1,900,000
# r2: 277,850 + 15 x 114,100 = 1,989,350 -> last turn fresh 110,650 -> 2,100,000
# r3: 277,850 + 17 x 114,100 = 2,217,550 -> last turn fresh 82,450 -> 2,300,000
PLANTED_RUN, PLANTED_FROM, PLANTED_FACTOR = "r2x3", "r2", 3     # 3 x 2,100,000 = 6,300,000 > 3,125,000


def _u(scale, **kw):
    return MF.usage(**{k: v * scale for k, v in kw.items()})


def run_records(run: str, scale: int = 1):
    """(main records, subagent records) of one run; every usage number times `scale`."""
    target, turns, _ = RUNS[run]
    sid = f"sess-{run}"
    seq = MF.Seq(f"bud-{run}")
    root = '"' + MF.PLANTED_PATH + '"'
    R = [MF.user(seq, sid, MF.PLANTED_PROMPT)] + MF.noise(seq, sid)
    R.append(MF.asst(seq, sid, f"msg_{run}_m1", _u(scale, fresh=2000, w5=40000, out=1000)))
    R.append(MF.asst(seq, sid, f"msg_{run}_m2", _u(scale, fresh=100, read=60000, out=500),
                     [MF.bash(f"reel preflight --root {root} --video-id {VIDEO_ID}", f"toolu_{run}_2")]))
    R.append(MF.asst(seq, sid, f"msg_{run}_m3", _u(scale, fresh=50, read=80000, out=800),
                     [MF.bash(f"reel transcribe --root {root} --video-id {VIDEO_ID}", f"toolu_{run}_3"),
                      MF.agent(f"toolu_{run}_A")]))
    R.append(MF.user(seq, sid, [{"type": "tool_result", "tool_use_id": f"toolu_{run}_A", "content": "done"}]))
    R.append(MF.asst(seq, sid, f"msg_{run}_m4", _u(scale, fresh=100, w1=20000, read=100000, out=2000),
                     [MF.bash(f"reel plan --root {root} --video-id {VIDEO_ID}", f"toolu_{run}_4")]))
    R.append(MF.asst(seq, sid, f"msg_{run}_m5", _u(scale, fresh=100, read=120000, out=1000),
                     [MF.bash(f"reel previews --root {root} --video-id {VIDEO_ID}", f"toolu_{run}_5")]))
    for k in range(turns):
        content = [MF.bash(f"reel qc --root {root} --video-id {VIDEO_ID}", f"toolu_{run}_q{k}")] if k == 0 else None
        R.append(MF.asst(seq, sid, f"msg_{run}_t{k:03d}", _u(scale, fresh=100, read=140000, out=20000), content))
    last = target - BASE - turns * TURN
    R.append(MF.asst(seq, sid, f"msg_{run}_last", _u(scale, fresh=last)))
    sub_seq = MF.Seq(f"bud-{run}-sub")
    S = [MF.user(sub_seq, sid, MF.PLANTED_PROMPT, sidechain=True, agent_id=f"{run}a1"),
         MF.asst(sub_seq, sid, f"msg_{run}_s1", _u(scale, fresh=1000, w5=100000, read=200000, out=20000),
                 model=MF.SONNET, sidechain=True, agent_id=f"{run}a1")]
    return R, S


def transcript(duration_ms: int) -> str:
    doc = {"meta": {"source_video": MF.PLANTED_PATH + "\\EP01.mp4", "duration_ms": duration_ms, "language": "ar",
                    "model": "large-v3"},
           "segments": [{"id": 0, "start_ms": 0, "end_ms": duration_ms, "text": MF.PLANTED_CLIENT, "words": []}]}
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1) + "\n"


def _run_files(out: dict, folder: str, run: str, scale: int) -> None:
    main, sub = run_records(run, scale)
    base = f"single-clip/{folder}/{PROJECT_DIR}/sess-{run}"
    out[base + ".jsonl"] = MF.dumps(main)
    out[base + f"/subagents/agent-{run}a1.jsonl"] = MF.dumps(sub)
    out[base + f"/subagents/agent-{run}a1.meta.json"] = json.dumps(MF.meta(f"toolu_{run}_A", 1, MF.SONNET),
                                                                   sort_keys=True) + "\n"


def _run_entry(name: str, folder: str, duration) -> dict:
    e = {"mode": "single-clip", "run": name, "transcripts": [f"single-clip/{folder}/{PROJECT_DIR}"],
         "status": "complete",
         "quality": [{"grader": g, "passed": True} for g in GRADERS]}
    if duration is not None:
        e["speech_transcript"] = f"single-clip/{folder}/transcript.json"
    return e


NOT_MEASURED = [{"mode": "podcast-reel", "reason": "fixture: no recorded podcast-reel run"},
                {"mode": "motion", "reason": "fixture: no recorded motion run"}]


def runs_doc(planted: bool) -> dict:
    entries = []
    for run, (_, _, dur) in RUNS.items():
        if planted and run == PLANTED_FROM:
            entries.append(_run_entry(PLANTED_RUN, PLANTED_RUN, dur))
        else:
            entries.append(_run_entry(run, run, dur))
    return {"tool": "budget_runs", "version": 1, "commit": COMMIT, "runs": entries, "not_measured": NOT_MEASURED}


def build() -> dict:
    """{relative path: file text} of every fixture file below this folder."""
    out = {}
    for run, (_, _, dur) in RUNS.items():
        _run_files(out, run, run, 1)
        if dur is not None:
            out[f"single-clip/{run}/transcript.json"] = transcript(dur)
    _run_files(out, PLANTED_RUN, PLANTED_FROM, PLANTED_FACTOR)
    out[f"single-clip/{PLANTED_RUN}/transcript.json"] = transcript(RUNS[PLANTED_FROM][2])
    out["runs.json"] = json.dumps(runs_doc(False), indent=1, sort_keys=True) + "\n"
    out["runs-planted.json"] = json.dumps(runs_doc(True), indent=1, sort_keys=True) + "\n"
    return out


def write(root: Path = HERE) -> list:
    written = []
    for rel, body in sorted(build().items()):
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        written.append(rel)
    return written


if __name__ == "__main__":
    for rel in write():
        print(rel)
    sys.exit(0)
