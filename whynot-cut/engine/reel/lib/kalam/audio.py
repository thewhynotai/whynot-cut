# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
# Ported from the owner's Kalam engine (kalam/audio.py); see adobe/tools/README.md. Change to the upstream file (portability
# audit §3.1): `soundfile` (libsndfile) is optional. The core engine runtime has none, so when it cannot be imported the WAV
# is read by `read_wav` below (PCM 8/16/24/32-bit and float 32/64-bit, mono or multi-channel, extensible header), which
# returns exactly the float32 array `soundfile.read(path, dtype="float32", always_2d=True)` gives (libsndfile's scale factors
# are powers of two, so the integer samples convert exactly), and everything after that is the owner's code unchanged.
"""Audio in: any WAV -> mono float32 16 kHz; level envelope in dB per 10 ms."""
import numpy as np

from ..hush import wav as _wav

RATE = 16000
HOP = 0.01


def read_wav(path: str) -> tuple:
    """(float32 array (frames, channels), sample rate) of a WAV file, with the standard library and numpy only.
    ValueError for a file that is not a WAV or a format only libsndfile reads (A-law, ADPCM, ...)."""
    with open(path, "rb") as f:
        data = f.read()
    h = _wav.header(data)                       # RIFF walk: format, channels, rate, bits, dataOff, dataLen
    ch, bits, fmt = h["channels"], h["bits"], h["format"]
    if ch < 1 or h["rate"] < 1:
        raise ValueError("WAV with no channels or no sample rate")
    width = bits // 8
    if (fmt, bits) not in ((1, 8), (1, 16), (1, 24), (1, 32), (3, 32), (3, 64)):
        raise ValueError("unsupported WAV format %d / %d-bit: soundfile is needed to read it" % (fmt, bits))
    frames = h["dataLen"] // (ch * width)
    raw = np.frombuffer(data, dtype=np.uint8, count=frames * ch * width, offset=h["dataOff"])
    if fmt == 3:
        a = raw.view("<f4" if bits == 32 else "<f8").astype(np.float32)
    elif bits == 8:                             # unsigned, offset 128
        a = (raw.astype(np.int16) - 128).astype(np.float32) * np.float32(2.0 ** -7)
    elif bits == 16:
        a = raw.view("<i2").astype(np.float32) * np.float32(2.0 ** -15)
    elif bits == 24:
        b = raw.reshape(-1, 3).astype(np.int32)
        v = ((b[:, 0] << 8) | (b[:, 1] << 16) | (b[:, 2] << 24)).astype(np.int32) >> 8       # sign-extended
        a = v.astype(np.float32) * np.float32(2.0 ** -23)
    else:
        a = raw.view("<i4").astype(np.float32) * np.float32(2.0 ** -31)
    return a.reshape(frames, ch), h["rate"]


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
