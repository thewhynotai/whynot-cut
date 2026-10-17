# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
# Ported from the owner's Kalam engine (kalam/audio.py); see adobe/tools/README.md. Change to the upstream file (portability
# audit §3.1): `soundfile` (libsndfile) is optional. The core engine runtime has none, so when it cannot be imported the WAV
# is read by `read_wav` below (PCM 8/16/24/32-bit and float 32/64-bit, mono or multi-channel, extensible header), which
# returns exactly the float32 array `soundfile.read(path, dtype="float32", always_2d=True)` gives (libsndfile's scale factors
# are powers of two, so the integer samples convert exactly), and everything after that is the owner's code unchanged.
"""Audio in: any WAV -> mono float32 16 kHz; level envelope in dB per 10 ms."""
import mmap

import numpy as np

from ..hush import wav as _wav

RATE = 16000
HOP = 0.01


BLOCK_FRAMES = 16384            # frames converted at a time: the peak is the output array plus about one block


def _decode(raw: np.ndarray, fmt: int, bits: int) -> np.ndarray:
    """one block of raw bytes -> float32 samples (1-D); libsndfile's scale factors are powers of two"""
    if fmt == 3:
        return raw.view("<f4" if bits == 32 else "<f8").astype(np.float32)
    if bits == 8:                                   # unsigned, offset 128
        return (raw.astype(np.int16) - 128).astype(np.float32) * np.float32(2.0 ** -7)
    if bits == 16:
        return raw.view("<i2").astype(np.float32) * np.float32(2.0 ** -15)
    if bits == 24:
        b = raw.reshape(-1, 3).astype(np.int32)
        v = ((b[:, 0] << 8) | (b[:, 1] << 16) | (b[:, 2] << 24)).astype(np.int32) >> 8       # sign-extended
        return v.astype(np.float32) * np.float32(2.0 ** -23)
    return raw.view("<i4").astype(np.float32) * np.float32(2.0 ** -31)


def _fill(mm, h: dict) -> np.ndarray:
    """decode the data chunk of the memory-mapped file block by block into ONE float32 array (frames, channels); every view
    of the map is gone when this returns, so the map can be closed"""
    ch, bits, fmt = h["channels"], h["bits"], h["format"]
    width = bits // 8
    frames = h["dataLen"] // (ch * width)
    out = np.empty((frames, ch), dtype=np.float32)
    if frames:
        raw = np.frombuffer(mm, dtype=np.uint8, count=frames * ch * width, offset=h["dataOff"])
        step = max(1, int(BLOCK_FRAMES))
        for start in range(0, frames, step):
            end = min(frames, start + step)
            out[start:end] = _decode(raw[start * ch * width:end * ch * width], fmt, bits).reshape(end - start, ch)
    return out


def read_wav(path: str) -> tuple:
    """(float32 array (frames, channels), sample rate) of a WAV file, with the standard library and numpy only. The file is
    memory-mapped and converted in blocks: the peak is the returned array plus about one block, never the file bytes and the
    samples side by side. ValueError for a file that is not a WAV, an RF64 / W64 file (over 4 GB) or a format only libsndfile
    reads (A-law, ADPCM, ...): those need soundfile."""
    with open(path, "rb") as f:
        try:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        except ValueError:
            raise ValueError("Not a WAV file (it is empty)") from None
        try:
            if mm[:4] in (b"RF64", b"BW64", b"riff"):
                raise ValueError("RF64 / W64 WAV (over 4 GB): soundfile is needed to read it")
            h = _wav.header(mm)                     # RIFF walk: format, channels, rate, bits, dataOff, dataLen
            if h["channels"] < 1 or h["rate"] < 1:
                raise ValueError("WAV with no channels or no sample rate")
            if (h["format"], h["bits"]) not in ((1, 8), (1, 16), (1, 24), (1, 32), (3, 32), (3, 64)):
                raise ValueError("unsupported WAV format %d / %d-bit: soundfile is needed to read it" % (h["format"], h["bits"]))
            return _fill(mm, h), h["rate"]
        finally:
            mm.close()


def _read(path: str) -> tuple:
    try:
        import soundfile as sf
    except ImportError:
        return read_wav(path)
    return sf.read(path, dtype="float32", always_2d=True)


def load_16k(path: str) -> np.ndarray:
    a, sr = _read(path)
    a = a.mean(axis=1)
    if sr == RATE:
        return a
    if sr % RATE == 0:
        k = sr // RATE
        return a[: len(a) // k * k].reshape(-1, k).mean(axis=1).astype(np.float32)
    t = np.arange(0, len(a) / sr, 1.0 / RATE)
    return np.interp(t, np.arange(len(a)) / sr, a).astype(np.float32)


def envelope_db(a: np.ndarray, hop: float = HOP) -> np.ndarray:
    n = int(RATE * hop)
    frames = len(a) // n
    rms = np.sqrt((a[: frames * n].reshape(frames, n) ** 2).mean(axis=1))
    return (20 * np.log10(np.maximum(rms, 1e-5))).astype(np.float32)
