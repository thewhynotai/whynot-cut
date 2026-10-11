#!/usr/bin/env python3
"""Create a synthetic demo client folder (assets/ + data/) with a 12 s 25 fps clip and a hand-made Arabic transcript,
then run the deterministic pipeline end-to-end (no Whisper, no Adobe) including the watchable preview MP4.
Works on macOS and Windows; uses an installed Arabic font when the Thmanyah brand font isn't available.

Usage (engine Python):  <engine home>/venv/{bin/python|Scripts/python.exe} examples/make_demo.py <EMPTY_FOLDER>
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "tests"))
sys.path.insert(0, str(HERE / "engine" / "reel"))
import test_pipeline as T  # noqa: E402  (reuses the fixture builder)
from lib import plat  # noqa: E402

dest = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp())
root, p, words = T.make_project(dest)
if not any((root / "assets/Font").iterdir()):
    for d in plat.font_dirs():
        hit = next((f for n in ("arialbd.ttf", "arial.ttf", "GeezaPro.ttc", "NotoSansArabic-Bold.ttf")
                    for f in (d.rglob(n) if d.is_dir() else [])), None)
        if hit:
            shutil.copy(hit, root / "assets/Font/")
            break
from lib.discover import run_discovery  # noqa: E402
from lib.client_db import build  # noqa: E402
from lib.media import preflight  # noqa: E402
from lib.plan import compile_plan  # noqa: E402
from lib.previews import render_all  # noqa: E402
from lib.sfx import synth_needed  # noqa: E402
from lib.premiere_xml import build_xml  # noqa: E402
from lib.preview_video import render as preview  # noqa: E402
from lib.qc import run_qc  # noqa: E402
from lib.handoff import build as handoff  # noqa: E402
from lib.common import write_json  # noqa: E402

build(p, run_discovery(p)["inventory"])
preflight(p, [root / "data/Raw/CLIP1.mov"])
tc = T.TestPlanToXML()
tc.p = p
tc._semantic_stub()
write_json(p.p("01_analysis/edit-decisions.json"), tc.decisions())
print(compile_plan(p))
render_all(p)
synth_needed({c["kind"] for c in json.loads(p.p("06_audio/audio-cue-sheet.json").read_text(encoding="utf-8"))["cues"]},
             p.p("06_audio/sfx"))
print(build_xml(p)["xml"])
print("preview:", preview(p, width=540)["video"])
print("QC ok:", run_qc(p)["ok"], "(expected False until a plan approval and visual verification are recorded)")
handoff(p)
print("Demo project:", p.project)
