"""Run the engine on one WAV with the MLX backend and the portable backend (faster-whisper / ONNX), without
correction, and compare. usage: compare_backends.py <wav> <ar|en|other> <work_dir>
Pass bar: text similarity >= 95 % after normalizing spelling variants (hamza forms, ta marbuta, alef maqsura,
punctuation: the correction step unifies these), median onset diff <= 0.08 s, caption rules hold on the portable run."""
import json
import os
import re
import statistics
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
MODELS = Path.home() / "Library/Application Support/Kalam/models"


def run(wav, mode, out, backend):
    out.mkdir(parents=True, exist_ok=True)
    sp = out / "settings.json"
    sp.write_text(json.dumps({"correct": False, "max_lines": 1}), encoding="utf-8")
    env = dict(os.environ, KALAM_BACKEND=backend, HF_HUB_OFFLINE="1", PYTHONUTF8="1",
               HF_HOME=str(Path.home() / "Library/Application Support/Kalam/hf"))
    p = subprocess.run([sys.executable, str(HERE / "kalam_engine.py"), "run", "--wav", wav, "--mode", mode, "--out", str(out),
                        "--settings", str(sp), "--models", str(MODELS)], env=env, capture_output=True, text=True,
                       encoding="utf-8")
    last = [json.loads(l) for l in p.stdout.splitlines() if l.startswith("{")][-1]
    if last.get("stage") != "done":
        raise SystemExit("%s failed: %s\n%s" % (backend, last, p.stderr[-2000:]))
    words = json.loads((out / "words.json").read_text(encoding="utf-8"))
    caps = json.loads((out / "captions.json").read_text(encoding="utf-8"))
    return last, words, caps


def norm(w):
    return "".join(c for c in w.lower() if c.isalnum())


def spelling(t):
    t = re.sub("[\u064b-\u0652\u0640]", "", t)
    for x, y in (("\u0623", "\u0627"), ("\u0625", "\u0627"), ("\u0622", "\u0627"), ("\u0629", "\u0647"), ("\u0649", "\u064a")):
        t = t.replace(x, y)
    return "".join(c for c in t.lower() if c.isalnum())


def rules(caps):
    gaps = sum(1 for a, b in zip(caps, caps[1:]) if b["s"] - a["e"] > 0.001)
    overlaps = sum(1 for a, b in zip(caps, caps[1:]) if b["s"] < a["e"] - 0.001)
    multi = sum(1 for c in caps if "\n" in c["text"])
    return {"captions": len(caps), "gaps": gaps, "overlaps": overlaps, "multi_line": multi,
            "longest": max((len(c["text"]) for c in caps), default=0)}


def main(wav, mode, work):
    work = Path(work)
    res = {}
    for b in ("mlx", "portable"):
        res[b] = run(wav, mode, work / b, b)
    (_, wm, cm), (dp, wp, cp) = res["mlx"], res["portable"]
    a, b = [norm(w["w"]) for w in wm], [norm(w["w"]) for w in wp]
    sm = SequenceMatcher(None, a, b, autojunk=False)
    matched = [(wm[i + k], wp[j + k]) for i, j, n in sm.get_matching_blocks() for k in range(n)]
    overlap = 2 * len(matched) / max(1, len(a) + len(b))
    onset = statistics.median(abs(x["s"] - y["s"]) for x, y in matched) if matched else 99
    text_sim = SequenceMatcher(None, spelling(" ".join(w["w"] for w in wm)), spelling(" ".join(w["w"] for w in wp)),
                               autojunk=False).ratio()
    rm, rp = rules(cm), rules(cp)
    ok = text_sim >= 0.95 and onset <= 0.08 and rp["overlaps"] == 0 and rp["multi_line"] == 0 and rp["gaps"] <= rm["gaps"]
    print(json.dumps({"wav": Path(wav).name, "mode": mode, "words_mlx": len(a), "words_portable": len(b),
                      "word_overlap": round(overlap, 3), "text_similarity": round(text_sim, 3), "median_onset_diff": round(onset, 3),
                      "rules_mlx": rm, "rules_portable": rp, "elapsed_mlx": res["mlx"][0]["elapsed"],
                      "elapsed_portable": dp["elapsed"], "PASS": ok}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
