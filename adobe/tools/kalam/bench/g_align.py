# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""G-ALIGN (3.0 Task 18b): which CTC forced aligner places WhyNot Kalam's Arabic words more accurately?

Dev benchmark, NOT shipped. Runs in a scratch venv with torch + torchaudio 2.8 + transformers (never the engine
runtime). Default corpus: Arabic Speech Corpus v2.0 (benchmark only: nothing from it is written into the repo;
results.json holds utterance file ids and numbers only). Any corpus laid out as <set dir>/wav/*.wav +
<set dir>/textgrid/<same stem>.TextGrid with a "words" tier works: --set-dir NAME=DIR (repeatable), --text, --pauses.

Variants (same input times for all):
  mms-kalam A0   upstream Kalam engine/kalam/align.py itself (torchaudio forced_align), loaded from _upstream by path
  mms-kalam A1   whynot-cut/engine/reel/lib/align_w2v.py kind "mms" (numpy forced_align) - must equal A0 word for word
  ar             align_w2v kind "ar"  (jonatasgrosman/wav2vec2-large-xlsr-53-arabic), no separator
  ar-sep         align_w2v kind "ar", "|" between words
  ar-sep-harakat ar-sep with the round-0 tokenizer (harakat kept as targets): the "before" of fix round 1 (I4)
Every align_w2v window is also run through torchaudio.functional.forced_align on the same emissions: labels must be
identical and frame scores within 1e-6, else the run stops.
Input times: the truth jittered (seeded uniform +-150 ms, monotonic), or --input-times DIR with <stem>.json = the
real transcriber's times for exactly the truth words ([[s, e], ...] or [{"s":, "e":}, ...]; other lengths: skipped
and counted). Text: --text buckwalter (diacritics removed, ASC), buckwalter-vocalised (diacritics kept, as fully
vocalised input), arabic (labels already in Arabic script, used as written).

  python g_align.py selftest --out DIR                    numpy forced_align vs torchaudio on random emissions
  python g_align.py run --out DIR [--sets test,main]      one device per process: CUDA_VISIBLE_DEVICES=-1 -> CPU
  python g_align.py report --gpu A/results.json --cpu B/results.json   Markdown tables (raw and debiased) to stdout
Environment: HF_HOME = the scratch model cache, HF_HUB_OFFLINE=1.
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import os
import platform
import re
import sys
import time
import warnings
import zlib
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", message=".*forced_align has been deprecated.*")
warnings.filterwarnings("ignore", message=".*merge_tokens has been deprecated.*")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
UPSTREAM = REPO / "adobe" / "tools" / "kalam" / "_upstream" / "engine" / "kalam"
ENGINE = REPO / "whynot-cut" / "engine" / "reel"
CORPUS = Path(r"D:\ClaudeData\Temp\wnc-p4\align\data\asc\arabic-speech-corpus")   # default (ASC v2.0)
ASC_SETS = {"test": "test set", "main": "."}
SEED = 20261016
JITTER = 0.150
PAUSES = {"sil", "sp", "-", "", "dist"}      # ASC: "-" / "sil" pauses, "dist" corrupt; "sp" = short pause (HTK)
VARIANTS = ["mms-kalam-A0", "mms-kalam-A1", "ar", "ar-sep"]
EXTRA_VARIANTS = ["ar-sep-harakat"]
RATE = 16000

# Buckwalter as used by ASC ("^" is tha alongside the standard "v"); harakat / shadda / sukun / dagger alef dropped
_BW = {"'": "ء", "|": "آ", ">": "أ", "&": "ؤ", "<": "إ", "}": "ئ", "A": "ا", "b": "ب", "p": "ة", "t": "ت", "v": "ث",
       "^": "ث", "j": "ج", "H": "ح", "x": "خ", "d": "د", "*": "ذ", "r": "ر", "z": "ز", "s": "س", "$": "ش", "S": "ص",
       "D": "ض", "T": "ط", "Z": "ظ", "E": "ع", "g": "غ", "_": "ـ", "f": "ف", "q": "ق", "k": "ك", "l": "ل", "m": "م",
       "n": "ن", "h": "ه", "w": "و", "Y": "ى", "y": "ي", "{": "ٱ"}
_BW_DIAC = {"F": "\u064b", "N": "\u064c", "K": "\u064d", "a": "\u064e", "u": "\u064f", "i": "\u0650",
            "~": "\u0651", "o": "\u0652", "`": "\u0670"}
_BW_JUNK = set(" -.0123456789")   # stray label characters seen in 15 word labels (trailing "-", ".", "5", spaces)


def _load_path(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bw_to_arabic(t: str, vocalised: bool = False):
    """-> (arabic, cleaned?, unknown chars); diacritics removed unless vocalised"""
    out, cleaned, unknown = [], False, []
    for c in t:
        if c in _BW_DIAC:
            if vocalised:
                out.append(_BW_DIAC[c])
            continue
        if c in _BW_JUNK:
            cleaned = True
            continue
        if c in _BW:
            out.append(_BW[c])
        else:
            unknown.append(c)
    return "".join(out), cleaned, unknown


def words_tier(path):
    """the "words" tier of a Praat long-format TextGrid (BOM / CRLF tolerant) -> [(xmin, xmax, text)]"""
    with open(path, encoding="utf-8-sig") as f:
        txt = f.read().replace("\r\n", "\n")
    for it in re.split(r"\n\s*item \[\d+\]:\s*\n", txt)[1:]:
        m = re.search(r'name = "((?:[^"]|"")*)"', it)
        if m and m.group(1) == "words":
            return [(float(a), float(b), t.replace('""', '"')) for a, b, t in re.findall(
                r'xmin = ([-\d.eE+]+)\s*\n\s*xmax = ([-\d.eE+]+)\s*\n\s*text = "((?:[^"]|"")*)"', it)]
    raise ValueError(f"no words tier: {path}")


def jitter(truth, dur, uid):
    """seeded uniform +-JITTER on both edges, then monotonic (s_i >= e_{i-1}, e_i >= s_i + 10 ms) and clipped to
    [0, dur]; the seed per utterance = (SEED, crc32(utterance id))"""
    rng = np.random.default_rng([SEED, zlib.crc32(uid.encode("utf-8"))])
    out, prev = [], 0.0
    for s, e in truth:
        js = s + float(rng.uniform(-JITTER, JITTER))
        je = e + float(rng.uniform(-JITTER, JITTER))
        js = min(max(js, prev, 0.0), dur)
        je = min(max(je, js + 0.01), dur)
        out.append((js, je))
        prev = je
    return out


def label_text(t: str, mode: str):
    if mode == "arabic":
        return "".join(t.split()), False, []
    return bw_to_arabic(t, vocalised=mode == "buckwalter-vocalised")


def read_input_times(path):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [(float(x["s"]), float(x["e"])) if isinstance(x, dict) else (float(x[0]), float(x[1])) for x in raw]


def load_set(root, audio_mod, stats, text_mode="buckwalter", pauses=PAUSES, input_dir=None):
    root = Path(root)
    items = []
    for wav in sorted(glob.glob(str(root / "wav" / "*.wav"))):
        uid = Path(wav).stem
        tg = root / "textgrid" / (uid + ".TextGrid")
        a = audio_mod.load_16k(wav)
        dur = len(a) / RATE
        truth, texts = [], []
        for s, e, t in words_tier(tg):
            if t.strip() in pauses:
                continue
            ar, cleaned, unknown = label_text(t, text_mode)
            stats["cleaned"] += cleaned
            stats["unknown_chars"] += len(unknown)
            if not ar:
                stats["empty_after_clean"] += 1
                continue
            if e <= s:
                stats["nonpositive"] += 1
            truth.append((s, e))
            texts.append(ar)
        if input_dir:
            ip = Path(input_dir) / (uid + ".json")
            inp = read_input_times(ip) if ip.exists() else None
            if inp is None or len(inp) != len(truth):
                stats["input_missing_or_mismatch"] = stats.get("input_missing_or_mismatch", 0) + 1
                continue
        else:
            inp = jitter(truth, dur, uid)
        items.append({"id": uid, "a": a, "dur": dur, "truth": truth, "input": inp,
                      "words": [{"w": w, "s": s, "e": e} for w, (s, e) in zip(texts, inp)]})
    return items


class CheckedFA:
    """align_w2v.forced_align, checked against torchaudio.functional.forced_align on the same emissions"""

    def __init__(self, aw):
        import torch
        import torchaudio.functional as F
        self.aw, self.torch, self.F = aw, torch, F
        self.windows = 0
        self.label_mismatch = 0
        self.max_score_diff = 0.0
        self.check_time = 0.0
        self.np_time = 0.0

    def __call__(self, lp, targets, blank=0):
        t0 = time.perf_counter()
        lab, sc = self.aw.forced_align(lp, targets, blank=blank)
        t1 = time.perf_counter()
        tl, ts = self.F.forced_align(self.torch.from_numpy(np.ascontiguousarray(lp))[None],
                                     self.torch.from_numpy(np.asarray(targets, dtype=np.int32))[None], blank=blank)
        self.check_time += time.perf_counter() - t1
        self.np_time += t1 - t0
        self.windows += 1
        if not np.array_equal(tl[0].numpy().astype(np.int64), np.asarray(lab)):
            self.label_mismatch += 1
            raise SystemExit(f"PARITY FAIL numpy != torchaudio labels (window {self.windows})")
        d = float(np.max(np.abs(ts[0].numpy().astype(np.float64) - np.asarray(sc, dtype=np.float64))))
        self.max_score_diff = max(self.max_score_diff, d)
        if d > 1e-6:
            raise SystemExit(f"PARITY FAIL numpy != torchaudio scores by {d} (window {self.windows})")
        return lab, sc


def _old_ar_tokens(word: str, vocab: dict) -> str:
    """the round-0 align_w2v.ar_tokens (harakat and dagger alef kept as targets; NFC only): the I4 "before" variant"""
    import unicodedata
    old_map = {"\u0671": "\u0627", "\u0672": "\u0623", "\u0673": "\u0625", "\u06a9": "\u0643",
               "\u06aa": "\u0643", "\u06cc": "\u064a", "\u06d2": "\u064a", "\u06be": "\u0647",
               "\u06c1": "\u0647", "\u06d5": "\u0647", "\u06c0": "\u0647", "\u06af": "\u062c",
               "\u067e": "\u0628", "\u06a4": "\u0641", "\u0686": "\u062c", "\u0640": "", "|": "", "-": ""}
    out = []
    for c in unicodedata.normalize("NFC", word):
        c = old_map.get(c, c)
        if c and len(c) == 1 and c in vocab and not c.isdigit():
            out.append(c)
    return "".join(out)


def metrics(items, preds):
    on, off, lost, scores, fallback, nonover = [], [], 0, [], 0, 0
    son, soff = [], []                       # signed errors (pred - true): a systematic bias shows here
    rows = []
    for it, pw in zip(items, preds):
        u_on, u_off, u_lost, u_sc = [], [], 0, []
        for (ts, te), (is_, ie), p in zip(it["truth"], it["input"], pw):
            ps, pe, sc = p["s"], p["e"], p.get("score", 0.0)
            fb = p.get("aligned") is False or (ps == is_ and pe == ie and sc in (0.5, 0.0))
            no = pe <= ts or ps >= te
            u_lost += fb or no
            fallback += fb
            nonover += no and not fb
            u_on.append(abs(ps - ts) * 1000)
            u_off.append(abs(pe - te) * 1000)
            son.append((ps - ts) * 1000)
            soff.append((pe - te) * 1000)
            u_sc.append(sc)
        on += u_on
        off += u_off
        lost += u_lost
        scores += u_sc
        rows.append({"id": it["id"], "n": len(u_on), "dur": round(it["dur"], 3),
                     "onset_med_ms": round(float(np.median(u_on)), 1) if u_on else None,
                     "offset_med_ms": round(float(np.median(u_off)), 1) if u_off else None,
                     "lost": u_lost, "mean_score": round(float(np.mean(u_sc)), 4) if u_sc else None})
    side = {"son": np.array(son, dtype=np.float32), "soff": np.array(soff, dtype=np.float32),
            "utt": np.repeat(np.arange(len(rows)), [r["n"] for r in rows]).astype(np.int32)}
    on, off = np.array(on), np.array(off)

    def st(x):
        return {"median": round(float(np.median(x)), 1), "p90": round(float(np.percentile(x, 90)), 1),
                "p95": round(float(np.percentile(x, 95)), 1), "mean": round(float(np.mean(x)), 1)}
    return {"words": int(len(on)), "onset_ms": st(on), "offset_ms": st(off),
            "onset_within_ms": {k: round(float((on <= k).mean() * 100), 2) for k in (20, 50, 100)},
            "offset_within_ms": {k: round(float((off <= k).mean() * 100), 2) for k in (20, 50, 100)},
            "signed_onset_ms": {"median": round(float(np.median(son)), 1), "mean": round(float(np.mean(son)), 1)},
            "signed_offset_ms": {"median": round(float(np.median(soff)), 1), "mean": round(float(np.mean(soff)), 1)},
            "lost": int(lost), "lost_pct": round(lost / len(on) * 100, 3), "lost_fallback": int(fallback),
            "lost_no_overlap": int(nonover), "mean_score": round(float(np.mean(scores)), 4)}, rows, side


def cmd_selftest(args):
    import torch
    import torchaudio
    import torchaudio.functional as F
    sys.path.insert(0, str(ENGINE))
    from lib import align_w2v as aw
    rng = np.random.default_rng(SEED)
    n = mism = both_err = err_mismatch = 0
    maxd = 0.0
    for case in range(args.cases):
        C = int(rng.integers(2, 8))
        L = int(rng.integers(1, 9))
        T = int(rng.integers(1, 30))
        tg = rng.integers(1, C, L)
        if case % 4 == 0:
            lp = np.log(np.full((T, C), 1.0 / C, np.float32))                       # ties everywhere
        elif case % 4 == 1:
            lp = torch.log_softmax(torch.from_numpy(rng.integers(0, 3, (T, C)).astype(np.float32)), -1).numpy()
        else:
            lp = torch.log_softmax(torch.from_numpy(rng.normal(scale=3, size=(T, C)).astype(np.float32)), -1).numpy()
        try:
            a, b = F.forced_align(torch.from_numpy(lp)[None], torch.from_numpy(tg.astype(np.int32))[None], blank=0)
            ta = (a[0].numpy().astype(np.int64), b[0].numpy())
        except Exception:
            ta = None
        try:
            npr = aw.forced_align(lp, tg.astype(np.int32))
        except ValueError:
            npr = None
        n += 1
        if ta is None or npr is None:
            if (ta is None) != (npr is None):
                err_mismatch += 1
            else:
                both_err += 1
            continue
        if not np.array_equal(ta[0], npr[0]):
            mism += 1
        maxd = max(maxd, float(np.max(np.abs(ta[1] - npr[1]))))
    # speed on a realistic window: 25 s at 50 frames/s, 300 targets, 31 classes
    lp = torch.log_softmax(torch.from_numpy(rng.normal(size=(1250, 31)).astype(np.float32)), -1).numpy()
    tg = rng.integers(1, 31, 300).astype(np.int32)
    t0 = time.perf_counter()
    for _ in range(5):
        aw.forced_align(lp, tg)
    t_np = (time.perf_counter() - t0) / 5
    t0 = time.perf_counter()
    for _ in range(5):
        F.forced_align(torch.from_numpy(lp)[None], torch.from_numpy(tg)[None], blank=0)
    t_ta = (time.perf_counter() - t0) / 5
    res = {"cases": n, "label_mismatch": mism, "error_cases_both": both_err, "error_disagreement": err_mismatch,
           "max_score_diff": maxd, "window_1250x300_ms": {"numpy": round(t_np * 1000, 2),
                                                          "torchaudio": round(t_ta * 1000, 2)},
           "torch": torch.__version__, "torchaudio": torchaudio.__version__, "numpy": np.__version__}
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "selftest.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))
    if mism or err_mismatch or maxd > 1e-6:
        raise SystemExit("SELFTEST FAIL")


def _snapshot(repo, rev):
    from huggingface_hub import snapshot_download
    return snapshot_download(repo, revision=rev)


def cmd_run(args):
    import torch
    import torchaudio
    import transformers
    torch.backends.cudnn.deterministic = True     # A0 and A1 load the model separately: same kernels both times
    torch.backends.cudnn.benchmark = False
    sys.path.insert(0, str(ENGINE))
    from lib import align_w2v as aw
    up = _load_path("kalam_upstream_align", UPSTREAM / "align.py")
    up_audio = _load_path("kalam_upstream_audio", UPSTREAM / "audio.py")
    cuda = torch.cuda.is_available()
    dev_name = torch.cuda.get_device_name(0) if cuda else platform.processor()
    sets = [s for s in args.sets.split(",") if s]
    set_dirs = {k: Path(args.corpus) / v for k, v in ASC_SETS.items()}
    for sd in args.set_dir or []:
        k, _, v = sd.partition("=")
        set_dirs[k] = Path(v)
    pauses = set(args.pauses.split(",")) if args.pauses is not None else PAUSES
    variants = [v for v in args.variants.split(",") if v]
    os.makedirs(args.out, exist_ok=True)
    log_path = os.path.join(args.out, "run.log")

    def say(*a):
        msg = " ".join(str(x) for x in a)
        print(msg, flush=True)
        with open(log_path, "a", encoding="utf-8") as log:
            log.write(msg + "\n")

    t0 = time.perf_counter()
    stats = {"cleaned": 0, "unknown_chars": 0, "empty_after_clean": 0, "nonpositive": 0}
    data = {s: load_set(set_dirs[s], up_audio, stats, args.text, pauses, args.input_times) for s in sets}
    say(f"loaded {', '.join(f'{s}={len(v)} utt / {sum(len(i['truth']) for i in v)} words' for s, v in data.items())}"
        f" in {time.perf_counter() - t0:.1f}s; label stats {stats}; device {'cuda' if cuda else 'cpu'} {dev_name}")
    mms_dir = _snapshot(aw.MMS_REPO, aw.MMS_REV)
    ar_dir = _snapshot(aw.AR_REPO, aw.AR_REV)
    results = {"meta": {
        "python": sys.version.split()[0], "torch": torch.__version__, "torchaudio": torchaudio.__version__,
        "transformers": transformers.__version__, "numpy": np.__version__, "platform": platform.platform(),
        "device": "cuda" if cuda else "cpu", "device_name": dev_name, "cudnn_deterministic": True,
        "models": {"mms": [aw.MMS_REPO, aw.MMS_REV], "ar": [aw.AR_REPO, aw.AR_REV]},
        "seed": SEED, "jitter_s": None if args.input_times else JITTER, "pause_labels": sorted(pauses),
        "label_stats": stats, "text": args.text, "input_times": "real" if args.input_times else "jittered truth",
        "sets": {s: {"utterances": len(v), "words": sum(len(i["truth"]) for i in v),
                     "audio_s": round(sum(i["dur"] for i in v), 2)} for s, v in data.items()}},
        "aggregates": {}, "rows": {}, "timing": {}, "parity": {}}
    preds = {}
    sidecar = {}        # per-word signed errors (numbers only) for the paired bootstrap; stays in the scratch run dir
    inp_preds = {s: [[{"s": s_, "e": e_, "score": 1.0} for s_, e_ in it["input"]] for it in v]
                 for s, v in data.items()}
    for s in sets:
        agg, _, side = metrics(data[s], inp_preds[s])
        results["aggregates"].setdefault("input (jittered)", {})[s] = agg
        sidecar.update({f"input (jittered)|{s}|{k}": v for k, v in side.items()})
    # a finished variant is checkpointed (numbers only) so an interrupted run resumes with the same --out
    part_dir = os.path.join(args.out, "partial")
    os.makedirs(part_dir, exist_ok=True)
    results["meta"]["resumed_variants"] = []
    for var in variants:
        pj = os.path.join(part_dir, var + ".json")
        if os.path.exists(pj):
            with open(pj, encoding="utf-8") as f:
                part = json.load(f)
            if part.get("sets") == sets and part.get("device") == results["meta"]["device"] \
                    and part.get("text", "buckwalter") == args.text:
                for k in ("aggregates", "rows", "timing"):
                    results[k][var] = part[k]
                if part.get("np_parity"):
                    results["parity"].setdefault("numpy_vs_torchaudio", {})[var] = part["np_parity"]
                for s in sets:
                    preds[(var, s)] = [[{"s": a, "e": b, "score": c} for a, b, c in u] for u in part["preds"][s]]
                with np.load(os.path.join(part_dir, var + ".npz")) as z:
                    sidecar.update({k: z[k] for k in z.files})
                results["meta"]["resumed_variants"].append(var)
                say(f"[{var}] resumed from {pj} (finished in an earlier run)")
                continue
        if cuda:
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
        checker = None
        tl = time.perf_counter()
        if var == "mms-kalam-A0":
            up._model = None
            model, vocab, dev = up._load()
            run = up.align
        else:
            checker = CheckedFA(aw)
            kind = "mms" if var == "mms-kalam-A1" else "ar"
            cls = aw.Aligner
            if var == "ar-sep-harakat":
                class OldTok(aw.Aligner):
                    def tokens(self, word):
                        return _old_ar_tokens(word, self.vocab)

                    def readable(self, word):
                        return bool(_old_ar_tokens(word, self.vocab))
                cls = OldTok
            al = cls(kind, mms_dir if kind == "mms" else ar_dir, device="auto", word_sep=var.startswith("ar-sep"),
                     fa=checker)
            al._model()
            dev = al.device
            run = al.align
        if cuda:
            torch.cuda.synchronize()
        load_s = time.perf_counter() - tl
        say(f"[{var}] model loaded in {load_s:.1f}s on {dev}")
        results["timing"][var] = {"load_s": round(load_s, 2), "device": dev}
        for s in sets:
            out, errors = [], []
            c0 = checker.check_time if checker else 0.0
            cpu0 = time.process_time()
            tr = time.perf_counter()
            for k, it in enumerate(data[s]):
                try:
                    out.append(run(it["a"], it["words"]))
                except SystemExit:
                    raise
                except Exception as e:        # recorded, words count as lost (times kept, score 0)
                    errors.append([it["id"], type(e).__name__])
                    out.append([dict(w, score=0.0) for w in it["words"]])
                if (k + 1) % 200 == 0:
                    say(f"  [{var}/{s}] {k + 1}/{len(data[s])} {time.perf_counter() - tr:.1f}s")
            if cuda:
                torch.cuda.synchronize()
            wall = time.perf_counter() - tr
            cpu_s = time.process_time() - cpu0      # all threads of this process (less sensitive to other jobs)
            check = (checker.check_time - c0) if checker else 0.0
            wall_net = wall - check
            audio_s = results["meta"]["sets"][s]["audio_s"]
            preds[(var, s)] = out
            agg, rows, side = metrics(data[s], out)
            sidecar.update({f"{var}|{s}|{k}": v for k, v in side.items()})
            agg["errors"] = errors
            results["aggregates"].setdefault(var, {})[s] = agg
            results["rows"].setdefault(var, {})[s] = rows
            results["timing"][var][s] = {"wall_s": round(wall_net, 2), "rtf": round(wall_net / audio_s, 5),
                                         "torchaudio_check_s_excluded": round(check, 2),
                                         "process_cpu_s_incl_check": round(cpu_s, 1)}
            say(f"  [{var}/{s}] done {wall_net:.1f}s (+{check:.1f}s torchaudio check) RTF {wall_net / audio_s:.4f} "
                f"onset med {agg['onset_ms']['median']} p95 {agg['onset_ms']['p95']} lost {agg['lost']} "
                f"errors {len(errors)}")
        if cuda:
            results["timing"][var]["peak_gpu_mb"] = round(torch.cuda.max_memory_allocated() / 2 ** 20, 1)
        if checker:
            results["parity"].setdefault("numpy_vs_torchaudio", {})[var] = {
                "windows": checker.windows, "label_mismatch": checker.label_mismatch,
                "max_score_diff": checker.max_score_diff, "numpy_fa_s": round(checker.np_time, 2),
                "torchaudio_fa_s": round(checker.check_time, 2)}
        part = {"sets": sets, "device": results["meta"]["device"], "text": args.text,
                "aggregates": results["aggregates"][var],
                "rows": results["rows"][var], "timing": results["timing"][var],
                "np_parity": results["parity"].get("numpy_vs_torchaudio", {}).get(var),
                "preds": {s: [[[w["s"], w["e"], w.get("score")] for w in u] for u in preds[(var, s)]] for s in sets}}
        np.savez_compressed(os.path.join(part_dir, var + ".npz"),
                            **{k: v for k, v in sidecar.items() if k.startswith(var + "|")})
        with open(pj + ".tmp", "w", encoding="utf-8") as f:
            json.dump(part, f)
        os.replace(pj + ".tmp", pj)                  # the json is the "finished" marker: written last, atomically
        if var == "mms-kalam-A0":
            up._model = None
        del run
        if checker:
            del al
        else:
            del model
        import gc
        gc.collect()
        if cuda:
            torch.cuda.empty_cache()
    if "mms-kalam-A0" in variants and "mms-kalam-A1" in variants:
        par = {}
        for s in sets:
            a0, a1 = preds[("mms-kalam-A0", s)], preds[("mms-kalam-A1", s)]
            n = diff = lenmis = 0
            examples = []
            for it, u0, u1 in zip(data[s], a0, a1):
                for k, (w0, w1) in enumerate(zip(u0, u1)):
                    n += 1
                    if (w0["s"], w0["e"], w0.get("score")) != (w1["s"], w1["e"], w1.get("score")):
                        diff += 1
                        if len(examples) < 20:
                            examples.append({"id": it["id"], "word": k, "a0": [w0["s"], w0["e"], w0.get("score")],
                                             "a1": [w1["s"], w1["e"], w1.get("score")]})
                lenmis += len(u0) != len(u1)
            par[s] = {"words": n, "mismatch": diff, "length_mismatch": lenmis, "examples": examples}
        results["parity"]["a0_vs_a1"] = par
        say(f"A0 vs A1: {par if any(p['mismatch'] or p['length_mismatch'] for p in par.values()) else 'identical'} "
            f"({', '.join(f'{s}: {p['words']} words' for s, p in par.items())})")
    np.savez_compressed(os.path.join(args.out, "word_errors.npz"), **sidecar)
    results["meta"]["total_wall_s"] = round(time.perf_counter() - t0, 1)
    with open(os.path.join(args.out, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)
    say(f"written {os.path.join(args.out, 'results.json')} total {results['meta']['total_wall_s']}s")


def cmd_report(args):
    res = {}
    for k in ("gpu", "cpu"):
        p = getattr(args, k)
        if p:
            with open(p, encoding="utf-8") as f:
                res[k] = json.load(f)
    order = ["input (jittered)"] + VARIANTS + EXTRA_VARIANTS
    for k, r in res.items():
        for s in r["meta"]["sets"]:
            print(f"\n#### {k.upper()} - {s} set ({r['meta']['sets'][s]['utterances']} utt, "
                  f"{r['meta']['sets'][s]['words']} words, {r['meta']['sets'][s]['audio_s'] / 60:.1f} min)\n")
            print("| variant | onset med | p90 | p95 | mean | offset med | p90 | p95 | mean | onset <=20 / 50 / 100 ms "
                  "| bias onset / offset (signed median) | words lost (fallback + no overlap) | mean score | wall s "
                  "| RTF | load s | peak GPU MB |")
            print("|---|" + "---:|" * 16)
            for v in order:
                a = r["aggregates"].get(v, {}).get(s)
                if not a:
                    continue
                tm = r["timing"].get(v, {})
                ts = tm.get(s, {})
                o, f = a["onset_ms"], a["offset_ms"]
                w = a["onset_within_ms"]
                b_on = a.get("signed_onset_ms", {}).get("median", "-")
                b_off = a.get("signed_offset_ms", {}).get("median", "-")
                print(f"| {v} | {o['median']} | {o['p90']} | {o['p95']} | {o['mean']} | {f['median']} | {f['p90']} | "
                      f"{f['p95']} | {f['mean']} | {w['20']}% / {w['50']}% / {w['100']}% | {b_on} / {b_off} | "
                      f"{a['lost']} "
                      f"({a['lost_fallback']} + {a['lost_no_overlap']}) = {a['lost_pct']}% | {a['mean_score']} | "
                      f"{ts.get('wall_s', '-')} | {ts.get('rtf', '-')} | {tm.get('load_s', '-')} | "
                      f"{tm.get('peak_gpu_mb', '-')} |")
        print(f"\nparity ({k}): {json.dumps(r['parity'], ensure_ascii=False)}")
        side = os.path.join(os.path.dirname(os.path.abspath(getattr(args, k))), "word_errors.npz")
        if os.path.exists(side):
            with np.load(side) as z:
                debiased(z, r, k)
                bootstrap(z, r, k)


def debiased(z, r, label):
    """raw vs bias-corrected error: the signed median (a constant lead-in / hold) removed. "own" = each set's own
    median (an oracle: the best a constant can do); "main->test" = the main set's median applied to the test set (a
    calibration that does not see the test labels). The input row is the no-aligner baseline."""
    sets = list(r["meta"]["sets"])
    for s in sets:
        print(f"\n#### {label.upper()} - {s} set: raw vs bias-corrected (ms; med / p90 / p95, IQR of the signed error,"
              f" share within 50 ms)\n")
        print("| variant | onset raw | onset bias | onset debiased (own) | onset IQR | onset <=50 debiased | "
              "offset raw | offset bias | offset debiased (own) | offset IQR | offset <=50 debiased |"
              + (" onset debiased (main->test) | offset debiased (main->test) |" if s == "test" and "main" in sets
                 else ""))
        print("|---|" + "---:|" * (10 + (2 if s == "test" and "main" in sets else 0)))
        for v in ["input (jittered)"] + VARIANTS + EXTRA_VARIANTS:
            key = f"{v}|{s}|"
            if key + "son" not in z:
                continue
            cells = []
            cross = []
            for which in ("son", "soff"):
                x = z[key + which].astype(np.float64)
                b = float(np.median(x))
                raw, d = np.abs(x), np.abs(x - b)
                q = np.percentile
                cells += [f"{q(raw, 50):.1f} / {q(raw, 90):.1f} / {q(raw, 95):.1f}", f"{b:+.1f}",
                          f"{q(d, 50):.1f} / {q(d, 90):.1f} / {q(d, 95):.1f}", f"{q(x, 75) - q(x, 25):.1f}",
                          f"{(d <= 50).mean() * 100:.1f} %"]
                mk = f"{v}|main|{which}"
                if s == "test" and mk in z:
                    bm = float(np.median(z[mk].astype(np.float64)))
                    dc = np.abs(x - bm)
                    cross.append(f"{q(dc, 50):.1f} / {q(dc, 90):.1f} / {q(dc, 95):.1f} (bias {bm:+.1f})")
            print(f"| {v} | " + " | ".join(cells + cross) + " |")


def bootstrap(z, r, label, reps=2000):
    """paired bootstrap over utterances (every variant sees the same resampled utterances): 95 % interval of the
    difference variant - mms-kalam-A0 in median / p95 absolute error (ms); negative = more accurate than MMS"""
    rng = np.random.default_rng(SEED)
    for s in r["meta"]["sets"]:
        base = f"mms-kalam-A0|{s}|"
        if base + "son" not in z:
            continue
        utt = z[base + "utt"]
        n_utt = int(utt.max()) + 1
        order = np.argsort(utt, kind="stable")
        bounds = np.searchsorted(utt[order], np.arange(n_utt + 1))
        idx_of = [order[bounds[u]:bounds[u + 1]] for u in range(n_utt)]
        draws = [np.concatenate([idx_of[u] for u in rng.integers(0, n_utt, n_utt)]) for _ in range(reps)]
        b_on, b_off = np.abs(z[base + "son"]), np.abs(z[base + "soff"])
        print(f"\n#### {label.upper()} - {s} set: paired bootstrap ({reps} resamples of the {n_utt} utterances), "
              f"difference to mms-kalam-A0 in ms, point [95 % interval]\n")
        print("| variant | onset median | onset p95 | offset median | offset p95 |")
        print("|---|---:|---:|---:|---:|")
        for v in VARIANTS[1:] + EXTRA_VARIANTS + ["input (jittered)"]:
            key = f"{v}|{s}|"
            if key + "son" not in z:
                continue
            cells = []
            for va, ba in ((np.abs(z[key + "son"]), b_on), (np.abs(z[key + "soff"]), b_off)):
                for q in (50, 95):
                    point = np.percentile(va, q) - np.percentile(ba, q)
                    d = np.array([np.percentile(va[ix], q) - np.percentile(ba[ix], q) for ix in draws])
                    lo, hi = np.percentile(d, [2.5, 97.5])
                    cells.append(f"{point:+.1f} [{lo:+.1f}, {hi:+.1f}]")
            print(f"| {v} | " + " | ".join(cells) + " |")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("selftest")
    p.add_argument("--out", required=True)
    p.add_argument("--cases", type=int, default=50000)
    p = sub.add_parser("run")
    p.add_argument("--out", required=True)
    p.add_argument("--sets", default="test,main")
    p.add_argument("--variants", default=",".join(VARIANTS), help=f"also: {', '.join(EXTRA_VARIANTS)}")
    p.add_argument("--corpus", default=str(CORPUS), help="ASC root (sets test / main under it)")
    p.add_argument("--set-dir", action="append", help="NAME=DIR with wav/ and textgrid/ (overrides / adds a set)")
    p.add_argument("--text", choices=["buckwalter", "buckwalter-vocalised", "arabic"], default="buckwalter")
    p.add_argument("--pauses", help="comma-separated pause labels (default: ASC's sil,sp,-,dist and empty)")
    p.add_argument("--input-times", help="DIR of <stem>.json real word times (default: jittered truth)")
    p = sub.add_parser("report")
    p.add_argument("--gpu")
    p.add_argument("--cpu")
    args = ap.parse_args(argv)
    {"selftest": cmd_selftest, "run": cmd_run, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    main()
