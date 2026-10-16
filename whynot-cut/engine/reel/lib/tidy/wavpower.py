# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Tidy: mean power per 1 ms of a 16-bit PCM WAV (Python twin of E.wavPower, _upstream/js/engine.js, and of
TidySync.wavInfo, adobe/tools/tidy/src/js/sync.js). The input of the sound sync.

* `wav_info(head)`: the RIFF/WAVE header (latin-1 text of the first KBs) -> {rate, channels, bits, dataOffset,
  dataSize} or None, chunk walk and rules exactly as the JS (16-bit PCM or WAVE_FORMAT_EXTENSIBLE only).
* `wav_power(path)`: one float64 per 1 ms frame, `mean(sample^2)` over the frame's `round(rate / 1000) * channels`
  interleaved samples (sample = int16 / 32768), streamed in pieces of at most 4 MiB so a one-hour recording never sits
  in memory, numpy-vectorised. Bit-faithful to the JS for rates that are a multiple of 1000 Hz: v * v is exact in
  float64 (a multiple of 2**-30 below 1), so every partial sum of a frame (a few hundred such terms) is exact too and
  the order of the additions cannot change it; the sum is still taken sequentially in the JS order (np.cumsum along the
  frame), and the division is the same IEEE division. The result is the same array as the JS Float64Array.

A3 #7 drift guard. For any other rate (44.1 kHz, 22.05 kHz, 11.025 kHz ...) the JS frame is round(rate / 1000) samples
(44 for 44.1 kHz), i.e. 44 / 44.1 = 0.9977 of a millisecond: about 8 s of drift per hour of audio, and every sync offset
read from such power curves would be wrong by that. Those files are resampled per channel to 48 kHz first (linear
interpolation at the exact sample times t = j / 48000, integer arithmetic for the positions, streamed with the one
source sample of look-ahead the interpolation needs kept between pieces, so piece borders do not click), then framed
with the same 48 * channels samples per millisecond. A 48 kHz file never takes this path: its output is unchanged.

Differences from the JS on purpose: the output is not pre-allocated from the header's data size (a streamed WAV with
size 0xFFFFFFFF would ask the JS for gigabytes), it is collected piece by piece and ends at the end of the file; a header
with 0 channels or a rate below 500 Hz (frame 0 in the JS: RangeError) raises WavPowerError.
"""
from __future__ import annotations

import math
import os

import numpy as np

__all__ = ["WavPowerError", "wav_info", "wav_power", "PIECE", "TARGET_RATE"]

PIECE = 4194304          # bytes read at a time
TARGET_RATE = 48000      # Hz: what a rate that is not a multiple of 1000 is resampled to
_BLOCK = 262144          # output samples interpolated at a time (bounds memory in the resampling path)


class WavPowerError(ValueError):
    """'Not a 16-bit WAV: <file>' like the JS Error."""


def _u16(s, i):
    return ord(s[i]) | (ord(s[i + 1]) << 8)


def _u32(s, i):
    return (ord(s[i]) | (ord(s[i + 1]) << 8) | (ord(s[i + 2]) << 16)) + ord(s[i + 3]) * 16777216


def wav_info(head):
    """RIFF/WAVE header -> {'rate', 'channels', 'bits', 'dataOffset', 'dataSize'} or None. `head` is the latin-1 text
    of the first KBs (str) or those bytes."""
    s = head.decode("latin-1") if isinstance(head, (bytes, bytearray, memoryview)) else head
    if not s or len(s) < 20 or s[0:4] != "RIFF" or s[8:12] != "WAVE":
        return None
    i = 12
    fmt = None
    while i + 8 <= len(s):
        cid = s[i:i + 4]
        size = _u32(s, i + 4)
        if cid == "fmt " and i + 24 <= len(s):
            fmt = {"format": _u16(s, i + 8), "channels": _u16(s, i + 10), "rate": _u32(s, i + 12), "bits": _u16(s, i + 22)}
        elif cid == "data":
            if not fmt or (fmt["format"] != 1 and fmt["format"] != 65534) or fmt["bits"] != 16:
                return None
            return {"rate": fmt["rate"], "channels": fmt["channels"], "bits": 16, "dataOffset": i + 8, "dataSize": size}
        i += 8 + size + (size & 1)
    return None


class _Framer:
    """Sums squares frame by frame in the JS order; `feed` takes the squared samples of one piece (any length: a frame
    may continue into the next piece), `out` collects the finished frames, at most `total`."""

    def __init__(self, frame: int, total: int):
        self.frame, self.total = frame, total
        self.idx = 0
        self.acc = 0.0
        self.cnt = 0
        self.out: list = []

    @property
    def full(self) -> bool:
        return self.idx >= self.total

    def feed(self, sq: np.ndarray) -> None:
        frame = self.frame
        m = len(sq)
        off = 0
        if self.cnt and m:
            take = min(frame - self.cnt, m)
            self.acc = float(np.cumsum(np.concatenate((np.array([self.acc]), sq[:take])))[-1])   # sequential, from acc
            self.cnt += take
            off = take
            if self.cnt == frame:
                self.out.append(np.array([self.acc / frame]))
                self.idx += 1
                self.acc, self.cnt = 0.0, 0
                if self.full:
                    return
        rest = sq[off:]
        k = len(rest) // frame
        if k:
            kk = min(k, self.total - self.idx)
            sums = np.cumsum(rest[:kk * frame].reshape(kk, frame), axis=1)[:, -1]
            self.out.append(sums / frame)
            self.idx += kk
            if self.full:
                return
        left = rest[k * frame:]
        if len(left):
            self.acc = float(np.cumsum(left)[-1])
            self.cnt = len(left)

    def result(self) -> np.ndarray:
        return np.concatenate(self.out) if self.out else np.zeros(0, dtype=np.float64)


def _squares(data: bytes):
    """Squares of the int16 samples of `data` (float64, v = int16 / 32768), whole samples only (an odd byte is dropped,
    as the JS loop does)."""
    m = len(data) // 2
    v = np.frombuffer(data, dtype="<i2", count=m).astype(np.float64) / 32768.0
    return v * v


def _power_direct(f, info: dict, frame: int) -> np.ndarray:
    total = math.floor(info["dataSize"] / 2 / frame)
    buflen = PIECE - (PIECE % (frame * 2)) or frame * 2
    pos = info["dataOffset"]
    end = pos + info["dataSize"]
    fr = _Framer(frame, total)
    f.seek(pos)
    while pos < end and not fr.full:
        data = f.read(min(buflen, end - pos))
        n = len(data)
        if n <= 0:
            break
        fr.feed(_squares(data))
        pos += n
    return fr.result()


def _power_resampled(f, info: dict) -> np.ndarray:
    rate, ch = info["rate"], info["channels"]
    f.seek(0, 2)
    avail = max(0, min(info["dataSize"], f.tell() - info["dataOffset"]))
    n_src = avail // (2 * ch)                     # source frames (one sample per channel each)
    n_out = n_src * TARGET_RATE // rate           # 48 kHz samples that lie inside the recording
    total = n_out // (TARGET_RATE // 1000)        # whole milliseconds
    fr = _Framer((TARGET_RATE // 1000) * ch, total)
    if total == 0:
        return fr.result()
    n_out = total * (TARGET_RATE // 1000)
    per_piece = max(1, PIECE // (2 * ch))
    f.seek(info["dataOffset"])
    buf = np.zeros((0, ch), dtype=np.float64)     # source frames from index `base`
    base = 0
    read = 0
    next_j = 0
    while next_j < n_out:
        eof = read >= n_src
        if not eof:
            take = min(per_piece, n_src - read)
            data = f.read(take * 2 * ch)
            got = len(data) // (2 * ch)
            if got <= 0:
                n_src = read                      # the file ended early: the rest is the end
                eof = True
            else:
                v = np.frombuffer(data, dtype="<i2", count=got * ch).astype(np.float64) / 32768.0
                buf = np.concatenate((buf, v.reshape(got, ch)))
                read += got
                eof = read >= n_src
        last = base + len(buf) - 1                # index of the newest source frame we hold
        if eof:
            jmax = n_out
        else:
            jmax = min(n_out, ((last * TARGET_RATE) - 1) // rate + 1 if last > 0 else 0)
        while next_j < jmax:
            j = np.arange(next_j, min(jmax, next_j + _BLOCK), dtype=np.int64)
            pr = j * rate
            i0 = np.minimum(pr // TARGET_RATE, base + len(buf) - 1)   # (a file that ended early: hold its last sample)
            frac = (pr % TARGET_RATE).astype(np.float64) / TARGET_RATE
            i1 = np.minimum(i0 + 1, base + len(buf) - 1)
            a = buf[i0 - base]
            b = buf[i1 - base]
            v = a + (b - a) * frac[:, None]
            fr.feed((v * v).reshape(-1))
            next_j = int(j[-1]) + 1
            if fr.full:
                return fr.result()
        keep = (next_j * rate) // TARGET_RATE     # nothing before this source frame is needed again
        if keep > base:
            buf = buf[min(keep - base, len(buf)):]
            base = keep
        if eof and next_j >= jmax:
            break
    return fr.result()


def wav_power(path) -> np.ndarray:
    """Mean power per millisecond of the 16-bit WAV at `path`: float64 array (see the module doc). Raises
    WavPowerError for anything that is not a 16-bit PCM / extensible WAV, OSError when it cannot be read."""
    with open(path, "rb") as f:
        info = wav_info(f.read(65536).decode("latin-1"))
        if not info:
            raise WavPowerError("Not a 16-bit WAV: %s" % path)
        rate, ch = info["rate"], info["channels"]
        if ch < 1 or rate < 500:
            raise WavPowerError("Not a usable WAV (%d channels, %d Hz): %s" % (ch, rate, path))
        if rate % 1000 == 0:
            return _power_direct(f, info, (rate // 1000) * ch)
        return _power_resampled(f, info)
