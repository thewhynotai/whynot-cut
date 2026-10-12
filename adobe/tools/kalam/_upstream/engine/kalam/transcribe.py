"""Speech -> words [{w, s, e}] with the best model per mode: Apple GPU via MLX on a Mac, otherwise the portable
backends (faster-whisper for Whisper, ONNX for Parakeet) on an NVIDIA GPU or the CPU."""
from pathlib import Path

import numpy as np

from . import device as _device
from . import platform as _platform

ARABIC_DIR = "whisper-turbo-ar-dialectal"
OTHER_REPO = "mlx-community/whisper-large-v3-turbo"
ENGLISH_REPO = "mlx-community/parakeet-tdt-0.6b-v2"
CT2_ARABIC_DIR = "ct2-whisper-turbo-ar-dialectal"
CT2_OTHER_DIR = "ct2-whisper-large-v3-turbo"
ONNX_ENGLISH_DIR = "parakeet-tdt-0.6b-v2-onnx"
RATE = 16000
_parakeet = None
_fw = {}
_onnx = None
last_device = "apple-gpu"


def _whisper(a: np.ndarray, model: str, language) -> list:
    import mlx_whisper
    r = mlx_whisper.transcribe(a, path_or_hf_repo=model, language=language, word_timestamps=True,
                               condition_on_previous_text=False, verbose=None)
    return [{"w": w["word"].strip(), "s": float(w["start"]), "e": float(w["end"])}
            for seg in r["segments"] for w in seg.get("words", []) if w["word"].strip()]


def _parakeet_words(a: np.ndarray, chunk: float = 120.0, overlap: float = 15.0) -> list:
    global _parakeet
    import mlx.core as mx
    from parakeet_mlx import from_pretrained
    from parakeet_mlx.alignment import merge_longest_common_subsequence, merge_longest_contiguous
    from parakeet_mlx.audio import get_logmel
    if _parakeet is None:
        _parakeet = from_pretrained(ENGLISH_REPO)
    cfg = _parakeet.preprocessor_config
    data = mx.array(a.astype(np.float32))   # get_logmel needs float32 (it views the STFT by input dtype)
    tokens, step = [], int((chunk - overlap) * cfg.sample_rate)
    for start in range(0, max(1, len(a)), step):
        end = min(start + int(chunk * cfg.sample_rate), len(a))
        if end - start < cfg.hop_length:
            break
        res = _parakeet.generate(get_logmel(data[start:end], cfg))[0]
        off = start / cfg.sample_rate
        for t in res.tokens:
            t.start += off
            t.end = t.start + t.duration
        if not tokens:
            tokens = res.tokens
        else:
            try:
                tokens = merge_longest_contiguous(tokens, res.tokens, overlap_duration=overlap)
            except RuntimeError:
                tokens = merge_longest_common_subsequence(tokens, res.tokens, overlap_duration=overlap)
        if end == len(a):
            break
    words = []
    for t in tokens:   # sub-word tokens; a leading space starts a new word
        if t.text.startswith(" ") or not words:
            words.append({"w": t.text.strip(), "s": float(t.start), "e": float(t.end), "score": float(t.confidence)})
        else:
            words[-1]["w"] += t.text
            words[-1]["e"] = float(t.end)
    return [w for w in words if w["w"]]


def chunks(a: np.ndarray, rate: int = RATE, max_s: float = 25.0, look_s: float = 5.0, smooth_s: float = 0.2) -> list:
    """[(start, end)] sample ranges of at most max_s, each cut in the quietest 200 ms of its last look_s
    (energy smoothed over 200 ms, so a short dip inside a word never wins over a real pause)"""
    out, start, n, size, frame = [], 0, len(a), int(max_s * rate), int(0.02 * rate)
    k = max(1, int(round(smooth_s / 0.02)))
    while n - start > size:
        lo, hi = start + size - int(look_s * rate), start + size
        e = np.square(a[lo:hi].astype(np.float32))[: (hi - lo) // frame * frame].reshape(-1, frame).mean(axis=1)
        sm = np.convolve(e, np.ones(k) / k, mode="valid")          # sm[i] = mean of frames i..i+k-1
        q = int(np.argmin(sm))
        cut = lo + (q + k // 2) * frame if sm[q] < 0.25 * float(np.median(e)) else hi
        out.append((start, cut))
        start = cut
    out.append((start, n))
    return out


def _fw_words(a: np.ndarray, model_dir: str, language, factory=None) -> list:
    """faster-whisper on the GPU; any CUDA failure (loading or while transcribing) -> the same on the CPU, once"""
    global last_device
    _device.add_torch_dlls()
    if factory is None:
        from faster_whisper import WhisperModel as factory

    def run(model):
        segs, _ = model.transcribe(a.astype(np.float32), language=language, word_timestamps=True,
                                   condition_on_previous_text=False, vad_filter=False, beam_size=5)
        return [{"w": w.word.strip(), "s": float(w.start), "e": float(w.end)}
                for seg in segs for w in (seg.words or []) if w.word.strip()]

    if model_dir not in _fw:
        dev, ct = _device.pick()
        try:
            _fw[model_dir] = (factory(model_dir, device=dev, compute_type=ct), dev)
        except Exception:
            if dev == "cpu":
                raise
            _fw[model_dir] = (factory(model_dir, device="cpu", compute_type="int8"), "cpu")
    model, dev = _fw[model_dir]
    try:
        words = run(model)
    except Exception:
        if dev == "cpu":
            raise
        _fw[model_dir] = (factory(model_dir, device="cpu", compute_type="int8"), "cpu")
        model, dev = _fw[model_dir]
        words = run(model)
    last_device = dev
    return words


def session_providers(obj, depth: int = 3) -> list:
    """the execution providers an onnx-asr model really runs on (first onnxruntime session found inside it)"""
    seen, level = set(), [obj]
    for _ in range(depth + 1):
        nxt = []
        for o in level:
            if id(o) in seen:
                continue
            seen.add(id(o))
            if hasattr(o, "get_providers") and callable(o.get_providers):
                try:
                    return list(o.get_providers())
                except Exception:
                    pass
            nxt.extend(v for v in getattr(o, "__dict__", {}).values() if not isinstance(v, (str, bytes, int, float)))
        level = nxt
    return []


def _onnx_parakeet_words(a: np.ndarray, model_dir: str) -> list:
    global _onnx, last_device
    _device.add_torch_dlls()
    import onnx_asr
    import onnxruntime as rt
    if _onnx is None:
        gpu = "CUDAExecutionProvider" in rt.get_available_providers()
        prov = ["CUDAExecutionProvider", "CPUExecutionProvider"] if gpu else ["CPUExecutionProvider"]
        _onnx = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v2", model_dir, providers=prov).with_timestamps()
    last_device = "cuda" if "CUDAExecutionProvider" in session_providers(_onnx) else "cpu"
    words = []
    for s0, s1 in chunks(a):
        r = _onnx.recognize(a[s0:s1].astype(np.float32), sample_rate=RATE)
        off, end = s0 / RATE, s1 / RATE
        toks, ts = r.tokens or [], r.timestamps or []
        for k, (t, start) in enumerate(zip(toks, ts)):
            nxt = ts[k + 1] + off if k + 1 < len(ts) else end
            piece = t.replace("\u2581", " ")
            if piece.startswith(" ") or not words or words[-1].get("_chunk") != s0:
                words.append({"w": piece.strip(), "s": float(start + off), "e": float(nxt), "_chunk": s0})
            else:
                words[-1]["w"] += piece
                words[-1]["e"] = float(nxt)
    return [{"w": w["w"], "s": w["s"], "e": w["e"]} for w in words if w["w"]]


def transcribe(a: np.ndarray, mode: str, models_dir: str) -> list:
    if _platform.backend() == "portable":
        md = Path(models_dir)
        if mode == "ar":
            return _fw_words(a, str(md / CT2_ARABIC_DIR), "ar")
        if mode == "en":
            return _onnx_parakeet_words(a, str(md / ONNX_ENGLISH_DIR))
        return _fw_words(a, str(md / CT2_OTHER_DIR), None)
    if mode == "ar":
        return _whisper(a, str(Path(models_dir) / ARABIC_DIR), "ar")
    if mode == "en":
        return _parakeet_words(a)
    return _whisper(a, OTHER_REPO, None)
