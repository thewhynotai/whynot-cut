import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[1] / "kalam_engine.py"
SUPPORT = Path.home() / "Library/Application Support"
SHERIF = SUPPORT / "Hush/bench/sherif.wav"
MODELS = SUPPORT / "Kalam/models"

pytestmark = pytest.mark.slow


def run(tmp_path, settings):
    sp = tmp_path / "settings.json"
    sp.write_text(json.dumps(settings), encoding="utf-8")
    p = subprocess.run([sys.executable, str(ENGINE), "run", "--wav", str(SHERIF), "--mode", "ar",
                        "--out", str(tmp_path), "--settings", str(sp), "--models", str(MODELS)],
                       capture_output=True, text=True, env={"HF_HOME": str(SUPPORT / "Kalam/hf"), "HF_HUB_OFFLINE": "1",
                                                           "PATH": "/usr/bin:/bin"})
    events = [json.loads(l) for l in p.stdout.splitlines() if l.startswith("{")]
    return p, events


def srt_blocks(text):
    out = []
    for blk in text.strip().split("\n\n"):
        ls = blk.split("\n")
        m = re.match(r"(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)$", ls[1])
        h1, m1, s1, f1, h2, m2, s2, f2 = map(int, m.groups())
        out.append((int(ls[0]), ((h1 * 60 + m1) * 60 + s1) * 1000 + f1, ((h2 * 60 + m2) * 60 + s2) * 1000 + f2, ls[2:]))
    return out


def test_uncorrected_run_writes_valid_gapless_srt(tmp_path):
    p, ev = run(tmp_path, {"correct": False})
    assert p.returncode == 0, p.stderr[-2000:]
    stages = [e["stage"] for e in ev]
    assert stages[0] == "loading" and stages[-1] == "done" and "aligning" in stages
    blocks = srt_blocks((tmp_path / "captions.srt").read_text(encoding="utf-8"))
    assert [b[0] for b in blocks] == list(range(1, len(blocks) + 1)) and len(blocks) >= 20
    assert all(a[2] == b[1] for a, b in zip(blocks, blocks[1:]))
    assert all(1 <= len(b[3]) <= 2 for b in blocks)
    text = " ".join(" ".join(b[3]) for b in blocks)
    assert not re.search(r"[.,!?،؟]", text)
    caps = json.loads((tmp_path / "captions.json").read_text(encoding="utf-8"))
    assert len(caps) == len(blocks) and ev[-1]["corrected"] is False and "notice" not in ev[-1]


def test_missing_key_still_makes_captions_with_notice(tmp_path):
    p, ev = run(tmp_path, {"correct": True, "backend": "api", "api_key": ""})
    assert p.returncode == 0 and ev[-1]["stage"] == "done"
    assert ev[-1]["corrected"] is False and ev[-1]["notice"] == "no_api_key"
    assert (tmp_path / "captions.srt").exists()
