"""Forced alignment: place every transcribed word exactly on the audio (MMS-300m CTC aligner)."""
import json
import os

import numpy as np

REPO = "MahmoudAshraf/mms-300m-1130-forced-aligner"
RATE = 16000
WINDOW = 25.0
_model = None

# Arabic letters -> latin sounds (Egyptian-ish): enough for acoustic alignment
_AR = {0x627: "a", 0x623: "a", 0x625: "i", 0x622: "aa", 0x621: "", 0x624: "u", 0x626: "i", 0x628: "b", 0x62A: "t",
       0x62B: "s", 0x62C: "g", 0x62D: "h", 0x62E: "kh", 0x62F: "d", 0x630: "z", 0x631: "r", 0x632: "z", 0x633: "s",
       0x634: "sh", 0x635: "s", 0x636: "d", 0x637: "t", 0x638: "z", 0x639: "a", 0x63A: "gh", 0x641: "f", 0x642: "a",
       0x643: "k", 0x644: "l", 0x645: "m", 0x646: "n", 0x647: "h", 0x629: "a", 0x648: "w", 0x64A: "y", 0x649: "a",
       0x6AF: "g"}
_NUM = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven",
        "8": "eight", "9": "nine"}


def _cuda_available() -> bool:
    import torch
    return torch.cuda.is_available()


def torch_device(probe=_cuda_available) -> str:
    """"cuda" on a working NVIDIA GPU, else "cpu" (Apple's MPS is not used: CPU is fast enough here)"""
    try:
        return "cuda" if probe() else "cpu"
    except Exception:
        return "cpu"


def _probe(model, dev):
    import torch
    with torch.inference_mode():
        model(torch.zeros(1, RATE // 5, device=dev))


def place_model(model, dev: str, probe=_probe):
    """move to dev and run one 0.2 s forward pass there; any failure (e.g. a GPU too new for this torch) -> CPU"""
    model = model.to(dev)
    if dev != "cpu":
        try:
            probe(model, dev)
        except Exception:
            dev = "cpu"
            model = model.to(dev)
    return model, dev


def _load():
    global _model
    if _model is None:
        from huggingface_hub import snapshot_download
        from transformers import Wav2Vec2ForCTC
        d = snapshot_download(REPO)
        vocab = json.load(open(os.path.join(d, "vocab.json"), encoding="utf-8"))
        model, dev = place_model(Wav2Vec2ForCTC.from_pretrained(d).eval(), torch_device())
        _model = (model, vocab, dev)
    return _model


def roman(word: str, vocab: dict) -> str:
    r = "".join(_AR.get(ord(c), _NUM.get(c, c)) for c in word.lower())
    return "".join(c for c in r if len(c) == 1 and c in vocab)


def _windows(words: list) -> list:
    """index ranges of words spanning <= WINDOW seconds, cut at the biggest gap near the limit"""
    out, i = [], 0
    while i < len(words):
        j = i
        while j + 1 < len(words) and words[j + 1]["e"] - words[i]["s"] <= WINDOW:
            j += 1
        if j + 1 < len(words) and j > i:
            lo = i + (j - i) // 2
            j = max(range(lo, j + 1), key=lambda k: words[k + 1]["s"] - words[k]["e"])
        out.append((i, j))
        i = j + 1
    return out


def align(a: np.ndarray, words: list) -> list:
    import torch
    import torchaudio.functional as F
    model, vocab, dev = _load()
    words = [dict(w) for w in words]
    dur = len(a) / RATE
    for i, j in _windows(words):
        ws = words[i:j + 1]
        prev_e = words[i - 1]["e"] if i else 0.0
        next_s = words[j + 1]["s"] if j + 1 < len(words) else dur
        # audio window: up to 1.5 s around the words, never past the middle of the gap to a neighbour
        a0 = max(0.0, ws[0]["s"] - 1.5, (prev_e + ws[0]["s"]) / 2 if i else 0.0)
        a1 = min(dur, ws[-1]["e"] + 1.5, max(ws[-1]["e"] + 0.3, (ws[-1]["e"] + next_s) / 2))
        rs = [roman(w["w"], vocab) for w in ws]
        if not all(rs):
            # a script the romanizer cannot read (Cyrillic, CJK, ...): keep the transcriber's own times
            for w in ws:
                w["score"] = 0.5
            continue
        chunk = torch.from_numpy(a[int(a0 * RATE):int(a1 * RATE)].copy()).unsqueeze(0)
        targets = [vocab[c] for r in rs for c in r]
        with torch.inference_mode():
            x = (chunk - chunk.mean()) / (chunk.std() + 1e-7)
            em = torch.log_softmax(model(x.to(dev)).logits, dim=-1).float().cpu()
        if not targets or len(targets) >= em.shape[1]:
            for w in ws:
                w["score"] = 0.0
            continue
        lab, sc = F.forced_align(em, torch.tensor([targets], dtype=torch.int32), blank=0)
        spans = F.merge_tokens(lab[0], sc[0].exp())
        ratio = chunk.shape[1] / em.shape[1] / RATE
        pos = 0
        for w, r in zip(ws, rs):
            sp = spans[pos:pos + len(r)]
            pos += len(r)
            w["s"] = round(a0 + sp[0].start * ratio, 3)
            w["e"] = round(a0 + sp[-1].end * ratio, 3)
            w["score"] = round(float(np.mean([t.score for t in sp])), 3)
    return words
