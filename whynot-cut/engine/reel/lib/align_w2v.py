# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Word forced alignment for WhyNot Kalam with a wav2vec2 CTC model, without torchaudio.

WhyNot Kalam places every transcribed word on the audio with a CTC model (the upstream algorithm in Kalam's
engine/kalam/align.py). Upstream calls torchaudio.functional.forced_align / merge_tokens, which torchaudio removes
after 2.8, so this module carries the same Viterbi in numpy (same contract and tie-breaking) and keeps the rest of
the upstream algorithm verbatim: the 25 s windows cut at the biggest gap, the audio window bounds, the input
normalisation, the fallbacks and the rounding. Only the tokenizer and forced_align are swapped.

Two models (the benchmark adobe/tools/kalam/bench/G-ALIGN-RESULTS.md decides which one ships, Addendum I1):
  kind "mms": MahmoudAshraf/mms-300m-1130-forced-aligner (CC-BY-NC-4.0), latin vocab; words romanized exactly like
              upstream roman() (mms_tokens);
  kind "ar":  jonatasgrosman/wav2vec2-large-xlsr-53-arabic (Apache-2.0), Arabic letter vocab with "|" as the word
              delimiter (word_sep=True puts it between words); ar_tokens maps the letters.
Both use blank id 0. numpy only at import: torch and transformers are imported inside the model runner.
"""
from __future__ import annotations

import json
import os
import unicodedata
from collections import namedtuple

import numpy as np

RATE = 16000
WINDOW = 25.0
MMS_REPO, MMS_REV = "MahmoudAshraf/mms-300m-1130-forced-aligner", "49402e9577b1158620820667c218cd494cc44486"
AR_REPO, AR_REV = "jonatasgrosman/wav2vec2-large-xlsr-53-arabic", "af46c2d8531b8dcbb5e23b952f739b372c2e5d2d"

Span = namedtuple("Span", "token start end score")   # like torchaudio's TokenSpan: frames [start, end)


# ---------------------------------------------------------------------------------------------- CTC Viterbi (numpy)
def forced_align(log_probs, targets, blank: int = 0):
    """CTC forced alignment: the most likely frame label path that collapses to `targets`.

    Same contract as torchaudio.functional.forced_align (2.8): log_probs (T, C) or (1, T, C), targets (L,) or (1, L)
    -> (labels, scores) of shape (T,) or (1, T); scores are the log-probs of the chosen label per frame. Same
    tie-breaking: "skip" (state i-2) wins only when strictly greater than both other candidates, "advance" (i-1) only
    when strictly greater than both, otherwise "stay"; at the end the last label wins over the trailing blank only when
    strictly greater. Errors like torchaudio: blank inside targets, empty targets, T < L + repeats -> ValueError.
    """
    lp = np.asarray(log_probs)
    tg = np.asarray(targets)
    batched = lp.ndim == 3
    if batched:
        if lp.shape[0] != 1 or tg.ndim != 2 or tg.shape[0] != 1:
            raise ValueError("only batch size 1 is supported")
        lp, tg = lp[0], tg[0]
    if lp.ndim != 2 or tg.ndim != 1:
        raise ValueError("log_probs must be (T, C) and targets (L,)")
    if not np.issubdtype(lp.dtype, np.floating):
        lp = lp.astype(np.float32)
    tg = tg.astype(np.int64)
    T, L = lp.shape[0], len(tg)
    if L == 0:
        raise ValueError("targets must not be empty")
    if (tg == blank).any():
        raise ValueError("targets shouldn't contain the blank index")
    R = int((tg[1:] == tg[:-1]).sum())
    if T < L + R:
        raise ValueError(f"targets length is too long for CTC: log_probs length {T}, targets length {L}, "
                         f"repeats {R}")
    S = 2 * L + 1
    neg = lp.dtype.type(-np.inf)
    lab = np.full(S, blank, dtype=np.int64)
    lab[1::2] = tg
    # skip i-2 -> i allowed: i odd, i != 1, targets differ (no repeat)
    skip = np.zeros(S, dtype=bool)
    if L > 1:
        skip[3::2] = tg[1:] != tg[:-1]
    bp = np.full((T, S), -1, dtype=np.int8)
    prev = np.full(S + 2, neg, dtype=lp.dtype)          # prev[k + 2] = alpha[k]; two -inf pads in front
    start = 0 if T - (L + R) > 0 else 1
    end = 1 if S == 1 else 2
    for i in range(start, end):
        prev[i + 2] = lp[0, lab[i]]
    cur = np.empty_like(prev)
    for t in range(1, T):
        if T - t <= L + R:
            if start % 2 == 1 and tg[start // 2] != tg[start // 2 + 1]:
                start += 1
            start += 1
        if t <= L + R:
            if end % 2 == 0 and end < 2 * L and tg[end // 2 - 1] != tg[end // 2]:
                end += 1
            end += 1
        cur.fill(neg)
        sl = start
        row = lp[t]
        if start == 0:
            cur[2] = prev[2] + row[blank]
            bp[t, 0] = 0
            sl += 1
        if sl < end:
            idx = np.arange(sl, end)
            x0 = prev[idx + 2]
            x1 = prev[idx + 1]
            x2 = np.where(skip[idx], prev[idx], neg)
            c2 = (x2 > x1) & (x2 > x0)
            c1 = ~c2 & (x1 > x0) & (x1 > x2)
            best = np.where(c2, x2, np.where(c1, x1, x0))
            bp[t, sl:end] = np.where(c2, 2, np.where(c1, 1, 0))
            cur[idx + 2] = best + row[lab[idx]]
        prev, cur = cur, prev
    k = S - 1 if prev[S - 1 + 2] > prev[S - 2 + 2] else S - 2
    path = np.empty(T, dtype=np.int64)
    for t in range(T - 1, -1, -1):
        path[t] = lab[k]
        k -= int(bp[t, k])
    scores = lp[np.arange(T), path]
    if batched:
        return path[None], scores[None]
    return path, scores


def merge_tokens(labels, scores, blank: int = 0) -> list:
    """runs of one label (blanks dropped) -> [Span(token, start, end, score)], score = mean of `scores` over the
    run's frames (pass probabilities, as upstream passes forced_align's scores .exp()) - torchaudio merge_tokens"""
    lab = np.asarray(labels).astype(np.int64).ravel()
    sc = np.asarray(scores).ravel()
    if len(lab) != len(sc):
        raise ValueError("labels and scores must have the same length")
    if not len(lab):
        return []
    edges = np.flatnonzero(np.diff(lab, prepend=-1, append=-1) != 0)
    out = []
    for s, e in zip(edges[:-1], edges[1:]):
        tok = int(lab[s])
        if tok != blank:
            out.append(Span(tok, int(s), int(e), float(np.mean(sc[s:e], dtype=sc.dtype if sc.dtype.kind == "f"
                                                                     else np.float64))))
    return out


# ------------------------------------------------------------------------------------------------------- tokenizers
# Copied from upstream Kalam engine/kalam/align.py (roman() and its tables, unchanged).
# Arabic letters -> latin sounds (Egyptian-ish): enough for acoustic alignment
_AR = {0x627: "a", 0x623: "a", 0x625: "i", 0x622: "aa", 0x621: "", 0x624: "u", 0x626: "i", 0x628: "b", 0x62A: "t",
       0x62B: "s", 0x62C: "g", 0x62D: "h", 0x62E: "kh", 0x62F: "d", 0x630: "z", 0x631: "r", 0x632: "z", 0x633: "s",
       0x634: "sh", 0x635: "s", 0x636: "d", 0x637: "t", 0x638: "z", 0x639: "a", 0x63A: "gh", 0x641: "f", 0x642: "a",
       0x643: "k", 0x644: "l", 0x645: "m", 0x646: "n", 0x647: "h", 0x629: "a", 0x648: "w", 0x64A: "y", 0x649: "a",
       0x6AF: "g"}
_NUM = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven",
        "8": "eight", "9": "nine"}


def mms_tokens(word: str, vocab: dict) -> str:
    """upstream Kalam roman(): the MMS aligner's latin characters for a word ("" = cannot be read)"""
    r = "".join(_AR.get(ord(c), _NUM.get(c, c)) for c in word.lower())
    return "".join(c for c in r if len(c) == 1 and c in vocab)


# characters outside the xlsr-arabic vocab that have a sound inside it ("" = silent, dropped)
_AR_MAP = {
    "ٱ": "ا",   # ٱ alef wasla -> ا
    "ٲ": "أ",   # ٲ -> أ
    "ٳ": "إ",   # ٳ -> إ
    "ک": "ك",   # ک Persian kaf -> ك
    "ڪ": "ك",   # ڪ swash kaf -> ك
    "ی": "ي",   # ی Persian yeh -> ي
    "ے": "ي",   # ے yeh barree -> ي
    "ھ": "ه",   # ھ heh doachashmee -> ه
    "ہ": "ه",   # ہ heh goal -> ه
    "ە": "ه",   # ە ae -> ه
    "ۀ": "ه",   # ۀ heh with yeh -> ه
    "گ": "ج",   # گ gaf (Egyptian hard g, written ج) -> ج
    "پ": "ب",   # پ peh -> ب
    "ڤ": "ف",   # ڤ veh -> ف
    "چ": "ج",   # چ tcheh -> ج
    "ـ": "",         # ـ tatweel: no sound (inside the vocab, but never a frame of speech)
    "|": "",              # the vocab's word delimiter never comes from a word
    "-": "",
}


def ar_tokens(word: str, vocab: dict) -> str:
    """xlsr-arabic characters for a word: NFC, a few letters mapped (_AR_MAP), digits and anything else outside the
    vocab dropped ("" = cannot be read)"""
    out = []
    for c in unicodedata.normalize("NFC", word):
        c = _AR_MAP.get(c, c)
        if c and len(c) == 1 and c in vocab and not c.isdigit():
            out.append(c)
    return "".join(out)


# ------------------------------------------------------------------------------------------------ upstream algorithm
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


class TorchRunner:
    """the wav2vec2 CTC model: raw 16 kHz chunk (float32) -> log-probs (T, V) as float32 numpy. The normalisation
    (x - mean) / (std + 1e-7) and the forward pass are upstream's torch ops, unchanged."""

    def __init__(self, model_dir: str, device: str = "auto"):
        import torch  # noqa: F401  (lazy: the engine imports this module without torch)
        from transformers import Wav2Vec2ForCTC
        model = Wav2Vec2ForCTC.from_pretrained(model_dir).eval()
        self.model, self.device = place_model(model, torch_device() if device == "auto" else device)

    def __call__(self, chunk: np.ndarray) -> np.ndarray:
        import torch
        c = torch.from_numpy(np.ascontiguousarray(chunk, dtype=np.float32).copy()).unsqueeze(0)
        with torch.inference_mode():
            x = (c - c.mean()) / (c.std() + 1e-7)
            em = torch.log_softmax(self.model(x.to(self.device)).logits, dim=-1).float().cpu()
        return em[0].numpy()


class Aligner:
    """align(audio_16k, words) -> words with "s", "e" (s, rounded to ms) and "score" (0..1) set.

    kind "mms" | "ar"; model_dir = a local snapshot of the model (config, weights, vocab.json); device "auto" (CUDA
    when a 0.2 s probe pass works there, else CPU), "cuda" or "cpu". word_sep (kind "ar"): put the "|" token between
    words. runner / vocab / fa are injection points (tests, the benchmark): runner(chunk) -> log-probs (T, V)."""

    def __init__(self, kind: str, model_dir: str | None = None, device: str = "auto", word_sep: bool = False, *,
                 runner=None, vocab: dict | None = None, fa=None):
        if kind not in ("mms", "ar"):
            raise ValueError(f"unknown aligner kind {kind!r} (mms | ar)")
        self.kind, self.model_dir, self.word_sep = kind, model_dir, bool(word_sep)
        self._device_req = device
        self._runner = runner
        if vocab is None:
            if model_dir is None:
                raise ValueError("vocab or model_dir is required")
            with open(os.path.join(model_dir, "vocab.json"), encoding="utf-8") as f:
                vocab = json.load(f)
        self.vocab = vocab
        self.fa = fa or forced_align
        self.device = None if runner is None else "fake"
        if self.word_sep and "|" not in vocab:
            raise ValueError("word_sep needs a '|' token in the vocab")

    def _model(self):
        if self._runner is None:
            self._runner = TorchRunner(self.model_dir, self._device_req)
            self.device = self._runner.device
        return self._runner

    def tokens(self, word: str) -> str:
        return mms_tokens(word, self.vocab) if self.kind == "mms" else ar_tokens(word, self.vocab)

    def align(self, a: np.ndarray, words: list) -> list:
        words = [dict(w) for w in words]
        dur = len(a) / RATE
        sep = [self.vocab["|"]] if self.word_sep else []
        for i, j in _windows(words):
            ws = words[i:j + 1]
            prev_e = words[i - 1]["e"] if i else 0.0
            next_s = words[j + 1]["s"] if j + 1 < len(words) else dur
            # audio window: up to 1.5 s around the words, never past the middle of the gap to a neighbour
            a0 = max(0.0, ws[0]["s"] - 1.5, (prev_e + ws[0]["s"]) / 2 if i else 0.0)
            a1 = min(dur, ws[-1]["e"] + 1.5, max(ws[-1]["e"] + 0.3, (ws[-1]["e"] + next_s) / 2))
            rs = [self.tokens(w["w"]) for w in ws]
            if not all(rs):
                # a script the tokenizer cannot read (Cyrillic, CJK, ...): keep the transcriber's own times
                for w in ws:
                    w["score"] = 0.5
                continue
            chunk = a[int(a0 * RATE):int(a1 * RATE)]
            targets = []
            for k, r in enumerate(rs):
                if k:
                    targets += sep
                targets += [self.vocab[c] for c in r]
            em = self._model()(chunk)
            if not targets or len(targets) >= em.shape[0]:
                for w in ws:
                    w["score"] = 0.0
                continue
            lab, sc = self.fa(em, np.array(targets, dtype=np.int32), blank=0)
            spans = merge_tokens(lab, np.exp(sc))
            ratio = len(chunk) / em.shape[0] / RATE
            pos = 0
            for w, r in zip(ws, rs):
                sp = spans[pos:pos + len(r)]
                pos += len(r) + len(sep)
                w["s"] = round(a0 + sp[0].start * ratio, 3)
                w["e"] = round(a0 + sp[-1].end * ratio, 3)
                w["score"] = round(float(np.mean([t.score for t in sp])), 3)
        return words
