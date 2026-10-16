# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Hush: WAV reader and level envelope (Python twin of adobe/tools/hush/src/js/wav.js).

The JavaScript is the reference (the panel's live logic); this twin gives `reel hush` in chat the same numbers. Same
function names in snake_case, same result keys. Bit-faithful where it matters:

* sample values and the channel mean are evaluated in float64 in the JS order (channels added one after the other, then
  divided by the channel count); decoded samples and the envelope are stored as float32 like the JS Float32Array;
* the sum of squares of one hop is accumulated sequentially (np.cumsum along the hop, never np.sum, which is pairwise);
* the envelope is vectorised (a 10-minute 48 kHz file takes seconds), processed in blocks of hops to bound memory.
Errors are `WavError` (a ValueError) with the exact JS messages.
"""
from __future__ import annotations

import math
import struct

import numpy as np

__all__ = ["WavError", "header", "decode", "envelope", "hop_levels", "js_round"]

_BLOCK_HOPS = 4096  # hops per vectorised block (4096 * 480 frames * 8 bytes ~ 16 MB at 48 kHz)


class WavError(ValueError):
    """Same messages as the JS Errors: 'Not a WAV file', 'WAV has no fmt/data chunk', ..."""


def js_round(x):
    """JavaScript Math.round: halves go up (-2.5 -> -2), never Python's banker's round(). Exact: floor(x + 0.5) is
    wrong for 0.49999999999999994 (the sum rounds up to 1.0) and for odd integers from 2**52 on, so the fraction is
    compared instead. Infinity and NaN come back unchanged."""
    if x != x or x in (math.inf, -math.inf):
        return x
    f = math.floor(x)
    return f + 1 if x - f >= 0.5 else f


def _tag(data, o):
    # bytes past the end read as undefined in JS, and String.fromCharCode(undefined) is "\0"
    return "".join(chr(data[i]) if 0 <= i < len(data) else "\0" for i in range(o, o + 4))


def _u16(data, o):
    if o < 0 or o + 2 > len(data):
        raise WavError("Offset is outside the bounds of the DataView")
    return struct.unpack_from("<H", data, o)[0]


def _u32(data, o):
    if o < 0 or o + 4 > len(data):
        raise WavError("Offset is outside the bounds of the DataView")
    return struct.unpack_from("<I", data, o)[0]


def header(data):
    """RIFF walk: {format, channels, rate, bits, dataOff, dataLen}. data: bytes-like (the whole file)."""
    if _tag(data, 0) != "RIFF" or _tag(data, 8) != "WAVE":
        raise WavError("Not a WAV file")
    n = len(data)
    off, fmt, data_off, data_len = 12, None, -1, 0
    while off + 8 <= n:
        cid, ln = _tag(data, off), _u32(data, off + 4)
        if cid == "fmt ":
            fmt = {"format": _u16(data, off + 8), "channels": _u16(data, off + 10),
                   "rate": _u32(data, off + 12), "bits": _u16(data, off + 22)}
            if fmt["format"] == 0xFFFE and ln >= 26:
                fmt["format"] = _u16(data, off + 32)
        elif cid == "data":
            data_off = off + 8
            data_len = min(ln, n - data_off)  # ln can be 0/garbage on streamed files
            if ln == 0 or ln == 0xFFFFFFFF:
                data_len = n - data_off
            break
        off += 8 + ln + (ln & 1)
    if fmt is None or data_off < 0:
        raise WavError("WAV has no fmt/data chunk")
    return {"format": fmt["format"], "channels": fmt["channels"], "rate": fmt["rate"], "bits": fmt["bits"],
            "dataOff": data_off, "dataLen": data_len}


def _sample(data, p, fmt, bps):
    """One sample, the way W.sample reads it (the slow path for layouts the vector code does not cover)."""
    def dv(code, size):
        i = int(p)  # DataView takes ToIndex(p)
        if i < 0 or i + size > len(data):
            raise WavError("Offset is outside the bounds of the DataView")
        return struct.unpack_from("<" + code, data, i)[0]
    if fmt == 3:
        return dv("d", 8) if bps == 8 else dv("f", 4)
    if bps == 2:
        return dv("h", 2) / 32768
    if bps == 3:
        i = int(p)
        if i < 0 or i + 3 > len(data):
            return float("nan")
        v = data[i] | (data[i + 1] << 8) | (data[i + 2] << 16)
        return ((v ^ 0x800000) - 0x800000) / 8388608
    if bps == 4:
        return dv("i", 4) / 2147483648
    if p != int(p) or p < 0 or p >= len(data):
        return float("nan")  # bytes[p] is undefined for a fractional or out-of-range index
    return (data[int(p)] - 128) / 128


def _frames(h):
    bps, ch = h["bits"] / 8, h["channels"]
    if bps * ch == 0:
        if h["dataLen"] == 0:
            return math.nan  # JS: Math.floor(0 / 0) = NaN: no frames, and the duration is NaN too
        raise WavError("Invalid typed array length: Infinity")  # JS: frames = Infinity
    return math.floor(h["dataLen"] / (bps * ch))


def _mono(data, h, f0, f1):
    """Channel mean of frames f0..f1 as float64 (sum of channels in order, then / channels)."""
    ch, bits, fmt, off = h["channels"], h["bits"], h["format"], h["dataOff"]
    count = f1 - f0
    if count <= 0:
        return np.zeros(0, dtype=np.float64)
    bps = bits / 8
    whole = bits % 8 == 0
    nb = bits // 8
    if whole and ((fmt == 3 and nb in (4, 8)) or (fmt != 3 and nb in (1, 2, 3, 4))):
        base = off + f0 * ch * nb
        k = count * ch
        if fmt == 3:
            raw = np.frombuffer(data, dtype="<f4" if nb == 4 else "<f8", count=k, offset=base).astype(np.float64)
        elif nb == 1:
            raw = (np.frombuffer(data, dtype=np.uint8, count=k, offset=base).astype(np.float64) - 128) / 128
        elif nb == 2:
            raw = np.frombuffer(data, dtype="<i2", count=k, offset=base).astype(np.float64) / 32768
        elif nb == 3:
            b = np.frombuffer(data, dtype=np.uint8, count=3 * k, offset=base).reshape(k, 3).astype(np.int64)
            x = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
            raw = ((x ^ 0x800000) - 0x800000).astype(np.float64) / 8388608
        else:
            raw = np.frombuffer(data, dtype="<i4", count=k, offset=base).astype(np.float64) / 2147483648
        cols = raw.reshape(count, ch)
        acc = np.zeros(count, dtype=np.float64)
        for c in range(ch):  # the JS adds channel after channel
            acc = acc + cols[:, c]
        return acc / ch
    out = np.empty(count, dtype=np.float64)  # slow path: exotic widths
    for i in range(count):
        s = 0.0
        for c in range(ch):
            s += _sample(data, off + ((f0 + i) * ch + c) * bps, fmt, bps)
        out[i] = s / ch
    return out


def hop_levels(mono_chunk, frames, n):
    """RMS level per hop of n frames in dBFS (floor -100) as float32.

    mono_chunk(f0, f1) -> float64 array of those frames. Sum of squares per hop is sequential (cumsum), the divisor is
    the hop's own frame count (the last hop may be short), level = 20 * log10(rms) when rms > 1e-5 else -100."""
    count = math.ceil(frames / n) if frames > 0 else 0
    env = np.empty(count, dtype=np.float32)
    for i0 in range(0, count, _BLOCK_HOPS):
        i1 = min(count, i0 + _BLOCK_HOPS)
        f0, f1 = i0 * n, min(frames, i1 * n)
        mono = mono_chunk(f0, f1)
        sq = mono * mono
        rows = i1 - i0
        pad = np.zeros(rows * n, dtype=np.float64)
        pad[:len(sq)] = sq
        sums = np.cumsum(pad.reshape(rows, n), axis=1)[:, -1]
        idx = np.arange(i0, i1, dtype=np.int64)
        div = np.maximum(1, np.minimum(frames, (idx + 1) * n) - idx * n).astype(np.float64)
        v = np.sqrt(sums / div)
        env[i0:i1] = np.fromiter((20 * math.log10(x) if x > 1e-5 else -100.0 for x in v.tolist()),
                                 dtype=np.float64, count=rows)
    return env


def _div(a, b):
    """a / b with JavaScript's results for a zero divisor (Infinity / NaN) instead of an exception."""
    if a != a:
        return a
    if b:
        return a / b
    return float("inf") if a else float("nan")


def decode(data):
    """{sampleRate, samples (float32 mono mix), channels}"""
    h = header(data)
    frames = _frames(h)
    samples = _mono(data, h, 0, 0 if frames != frames else frames).astype(np.float32)
    return {"sampleRate": h["rate"], "samples": samples, "channels": h["channels"]}


def envelope(data, hop):
    """Level envelope straight from the file bytes: {env (float32 dB per hop), duration, sampleRate}."""
    h = header(data)
    frames = _frames(h)
    n = max(1, js_round(h["rate"] * hop))
    env = hop_levels(lambda f0, f1: _mono(data, h, f0, f1), 0 if frames != frames else frames, n)
    return {"env": env, "duration": _div(frames, h["rate"]), "sampleRate": h["rate"]}
