"""Audio in: any WAV -> mono float32 16 kHz; level envelope in dB per 10 ms."""
import numpy as np
import soundfile as sf

RATE = 16000
HOP = 0.01


def load_16k(path: str) -> np.ndarray:
    a, sr = sf.read(path, dtype="float32", always_2d=True)
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
