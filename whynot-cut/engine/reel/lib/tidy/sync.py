# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Tidy: sync the recordings of one shoot by their sound (Python twin of adobe/tools/tidy/src/js/sync.js).

Loudness envelopes are cross-correlated (FFT) for the coarse offset at 100 Hz, then refined at 1 kHz. A clip whose best match
is not clearly better than the rest is left out: it is never placed at a guess. Offsets are seconds from the reference's
start (negative = earlier).

Faithful to the JavaScript, which is the reference: same names in snake_case, same keys in the same order, same constants.
* The FFT is the JS one: iterative radix-2 (bit reversal, then butterflies per stage with the twiddle factor advanced by the
  same rotation recurrence), vectorised over the blocks of a stage with numpy, NOT numpy's own FFT. Every butterfly is the
  same sequence of float64 operations as in the JS, so the values agree to rounding (the only difference left is the libm
  sin / cos / log, at most a last-bit difference). Peaks, offsets and ties therefore come out the same.
* Sums that the JS accumulates one value at a time are taken with np.cumsum (sequential), never np.sum (pairwise): the
  refine dot products, the 10 ms power means, the frame sums of `envelope` and the mean removal.
* `wav_info` is the shared twin of TidySync.wavInfo (lib/tidy/wavpower.py).
"""
from __future__ import annotations

import math

import numpy as np

from . import jsutil as J
from .wavpower import wav_info

__all__ = ["MIN_CONFIDENCE", "REFINE_SPAN", "envelope", "from_power", "wav_info", "fft", "offset", "refine", "plan", "layout"]

MIN_CONFIDENCE = 3
REFINE_SPAN = 120   # seconds of overlap used for the fine search


def _arr(x) -> np.ndarray:
    return np.ascontiguousarray(np.asarray(x, dtype=np.float64))


def _seq_sum(x: np.ndarray) -> float:
    """The sum of x added one value at a time, from 0 (JS `s += x[i]`)."""
    return float(np.cumsum(x)[-1]) if len(x) else 0.0


def _round(x: float) -> int:
    return math.floor(x + 0.5)      # JS Math.round


def _log_mean_removed(vals: np.ndarray) -> np.ndarray:
    n = len(vals)
    out = np.log(vals + 1e-4)
    mean = _seq_sum(out) / n if n else 0.0
    return out - mean


def _frame_sums(sq: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """For every frame the sequential sum of sq[a:b] (b - a varies by at most one sample)."""
    n = len(a)
    out = np.zeros(n)
    lengths = b - a
    block = 100000
    for s in range(0, n, block):
        la = lengths[s:s + block]
        width = int(la.max()) if len(la) else 0
        if width <= 0:
            continue
        idx = a[s:s + block, None] + np.arange(width)[None, :]
        mat = np.where(np.arange(width)[None, :] < la[:, None], sq[np.minimum(idx, len(sq) - 1)], 0.0)
        out[s:s + block] = np.cumsum(mat, axis=1)[:, -1]       # zeros after the end of a frame add nothing, exactly
    return out


def envelope(samples, rate, out_rate) -> np.ndarray:
    """Log RMS per output frame, mean removed."""
    x = _arr(samples)
    frame = rate / out_rate
    n = math.floor(len(x) / frame)
    if n <= 0:
        return np.zeros(0)
    sq = x * x
    i = np.arange(n, dtype=np.float64)
    a = np.floor(i * frame + 0.5).astype(np.int64)
    b = np.floor((i + 1) * frame + 0.5).astype(np.int64)
    s = _frame_sums(sq, a, b)
    out = np.log(np.sqrt(s / np.maximum(1, b - a)) + 1e-4)
    mean = _seq_sum(out) / n
    return out - mean


def from_power(power_hi) -> dict:
    """Mean power per 1 ms (streamed from a WAV) -> {env (100 Hz), hi (1 kHz), seconds}."""
    p = _arr(power_hi)
    n = len(p) // 10
    p100 = (np.cumsum(p[:n * 10].reshape(n, 10), axis=1)[:, -1] / 10) if n else np.zeros(0)
    return {"env": _log_mean_removed(np.sqrt(p100)), "hi": _log_mean_removed(np.sqrt(p)), "seconds": len(p) / 1000}


_TWIDDLE = {}


def _twiddles(half: int, inverse: bool):
    """cr[k], ci[k] of one butterfly stage: 1, then rotated by (wr, wi) k times, the JS recurrence."""
    k = (half, inverse)
    if k not in _TWIDDLE:
        ang = (2 if inverse else -2) * math.pi / (2 * half)
        wr, wi = math.cos(ang), math.sin(ang)
        cr, ci = [0.0] * half, [0.0] * half
        a, b = 1.0, 0.0
        for j in range(half):
            cr[j], ci[j] = a, b
            t = a * wr - b * wi
            b = a * wi + b * wr
            a = t
        _TWIDDLE[k] = (np.array(cr), np.array(ci))
    return _TWIDDLE[k]


def _bit_reversed(n: int) -> np.ndarray:
    bits = n.bit_length() - 1
    idx = np.arange(n, dtype=np.int64)
    rev = np.zeros(n, dtype=np.int64)
    for k in range(bits):
        rev |= ((idx >> k) & 1) << (bits - 1 - k)
    return rev


def fft(re, im, inverse: bool = False):
    """The radix-2 FFT of sync.js on float64 arrays (length a power of two); returns new arrays (re, im)."""
    n = len(re)
    rev = _bit_reversed(n)
    re = _arr(re)[rev]
    im = _arr(im)[rev]
    length = 2
    while length <= n:
        half = length >> 1
        cr, ci = _twiddles(half, inverse)
        r, m = re.reshape(-1, length), im.reshape(-1, length)
        ra, rb, ma, mb = r[:, :half], r[:, half:], m[:, :half], m[:, half:]
        tr = rb * cr - mb * ci
        ti = rb * ci + mb * cr
        nrb, nmb = ra - tr, ma - ti
        ra += tr
        ma += ti
        rb[...] = nrb
        mb[...] = nmb
        length <<= 1
    if inverse:
        re = re / n
        im = im / n
    return re, im


def offset(ref, x, rate) -> dict:
    """Where x starts on ref's clock: {offset (s), confidence (best peak / best peak elsewhere)}."""
    ref, x = _arr(ref), _arr(x)
    lr, lx = len(ref), len(x)
    n = 1
    while n < lr + lx:
        n <<= 1
    ar, ai, br, bi = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    ar[:lr] = ref
    br[:lx] = x
    ar, ai = fft(ar, ai, False)
    br, bi = fft(br, bi, False)
    cr = ar * br + ai * bi          # ref * conj(x)
    ci = ai * br - ar * bi
    ar, _ = fft(cr, ci, True)
    min_overlap = min(lr, lx) * 0.25
    idx = np.arange(n, dtype=np.int64)
    lag = np.where(idx < n - lx + 1, idx, idx - n)
    ov = np.minimum(lr, lag + lx) - np.maximum(0, lag)
    ok = (ov >= min_overlap) & (lag < lr) & (lag > -lx)
    best, best_lag = -math.inf, 0
    cand = np.where(ok & ~np.isnan(ar), ar, -np.inf)
    if ok.any():
        k = int(np.argmax(cand))
        if cand[k] > -math.inf:
            best, best_lag = float(cand[k]), int(lag[k])
    guard = _round(0.5 * rate)
    far = ok & (np.abs(lag - best_lag) > guard)
    mag = np.where(far & ~np.isnan(ar), np.abs(ar), 0.0)
    second = float(mag.max()) if len(mag) else 0.0
    conf = best / second if second > 0 else (99 if best > 0 else 0)
    return {"offset": best_lag / rate, "confidence": conf}


def refine(ref_hi, x_hi, rate, coarse, span=None) -> float:
    """Best offset within +-span s of the coarse one, on a high-rate envelope (normalized dot product)."""
    ref_hi, x_hi = _arr(ref_hi), _arr(x_hi)
    c = _round(coarse * rate)
    w = _round((span if J.truthy(span) else 0.5) * rate)
    best, best_l = -math.inf, c
    lr, lx = len(ref_hi), len(x_hi)
    max_half = _round(REFINE_SPAN * rate / 2)
    for L in range(c - w, c + w + 1):
        a, b = max(0, L), min(lr, L + lx)                 # overlap on ref's clock
        if b - a < rate:
            continue
        mid = (a + b) >> 1
        half = min((b - a) >> 1, max_half)
        frm, to = mid - half, mid + half
        s = float(np.cumsum(ref_hi[frm:to] * x_hi[frm - L:to - L])[-1]) if to > frm else 0.0
        s = s / (to - frm) if to > frm else math.nan
        if s > best:
            best, best_l = s, L
    return best_l / rate


def plan(tracks: list) -> dict:
    """tracks: [{id, env (100 Hz), hi (1 kHz), seconds}] -> {ref, placed: [{id, offset, confidence}], skipped: [id]}."""
    ref = None
    placed, skipped = [], []
    for t in tracks:
        if ref is None or t["seconds"] > ref["seconds"]:
            ref = t
    if ref is None:
        return {"ref": None, "placed": [], "skipped": []}
    for t in tracks:
        if t is ref:
            placed.append({"id": t["id"], "offset": 0, "confidence": 99})
            continue
        r = offset(ref["env"], t["env"], 100)
        if r["confidence"] < MIN_CONFIDENCE:
            skipped.append(t["id"])
            continue
        placed.append({"id": t["id"], "offset": refine(ref["hi"], t["hi"], 1000, r["offset"], 0.5), "confidence": r["confidence"]})
    return {"ref": ref["id"], "placed": placed, "skipped": skipped}


def layout(plan_: dict, roles: dict) -> dict:
    """A sync plan + roles {id: {role: 'cam'|'mic', cam: n, seconds}} -> {cams: [{nodeId, start, track}], mics: [{nodeId, start}],
    skipped}, shifted so the earliest clip starts at 0; Cam n goes on video track n-1; a clip that would overlap another on
    its camera's track gets a new track after all camera tracks (overwriting would silently drop one angle)."""
    lowest = 0
    cams, mics = [], []
    for p in plan_["placed"]:
        if p["offset"] < lowest:
            lowest = p["offset"]
    for p in plan_["placed"]:
        r = roles.get(J.key(p["id"])) if J.truthy(roles.get(J.key(p["id"]))) else {}
        start = p["offset"] - lowest
        if r.get("role") == "mic":
            mics.append({"nodeId": p["id"], "start": start})
        else:
            cam = r.get("cam")
            secs = r.get("seconds")
            cams.append({"nodeId": p["id"], "start": start, "end": start + (secs if J.truthy(secs) else 0),
                         "track": max(0, (cam if J.truthy(cam) else 1) - 1)})
    cams.sort(key=lambda c: c["start"])
    top = -1
    busy = {}
    for c in cams:
        if c["track"] > top:
            top = c["track"]
    for c in cams:
        if c["track"] in busy and busy[c["track"]] > c["start"] + 1e-6:
            j = top + 1
            while j in busy and busy[j] > c["start"] + 1e-6:
                j += 1
            c["track"] = j
            if j > top:
                top = j
        busy[c["track"]] = max(busy.get(c["track"], 0), c["end"])
        del c["end"]
    return {"cams": cams, "mics": mics, "skipped": list(plan_["skipped"])}
