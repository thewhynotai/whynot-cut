"""Whisper backends (3.0 T2.12: engine IM-13, decision D9): one interface, two engines, one output schema.

  ct2  faster-whisper / CTranslate2 (the verified backend): an NVIDIA GPU (fp16) when usable, else the CPU (int8) with
       `cpu_threads` = the machine's physical cores (faster-whisper's own default is 4). On the GPU, audio that VAD
       splits (episodes, clips longer than `long_clip_minutes`) is decoded by `BatchedInferencePipeline`.
  mlx  mlx-whisper on Apple Silicon (Metal), word timestamps. Not verified live yet (needs a Mac, T9.3).

`transcription.json` `backend`: auto (ct2; mlx on Apple Silicon once `mlx_verified`) | ct2 | mlx.
A runner from `make_runner` decodes one stretch of 16 kHz audio and returns chunk-relative times:
  {segments: [{id, start_ms, end_ms, text, avg_logprob, no_speech_prob, compression_ratio, words: [ids]}],
   words: [{id, segment_id, word, start_ms, end_ms, probability}], language, language_probability}
Models load from the complete local snapshot when there is one (no network: offline-safe, engine §4.4).
`bench` measures the real-time factor on this machine and caches it in <engine home>/bench for `reel doctor`.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

from .common import engine_home, load_config, log, models_dir, now_iso, read_json, write_json

BACKENDS = ("auto", "ct2", "mlx")
ALIASES = {"faster-whisper": "ct2", "ctranslate2": "ct2", "mlx-whisper": "mlx"}
LABEL = {"ct2": "faster-whisper", "mlx": "mlx-whisper"}
CT2_REPOS = {"large-v3": "Systran/faster-whisper-large-v3", "large-v3-turbo": "dropbox-dash/faster-whisper-large-v3-turbo",  # moved from mobiuslabsgmbh (HF redirect)
             "medium": "Systran/faster-whisper-medium", "small": "Systran/faster-whisper-small"}
MLX_REPOS = {"large-v3": "mlx-community/whisper-large-v3-mlx", "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
             "medium": "mlx-community/whisper-medium-mlx", "small": "mlx-community/whisper-small-mlx"}
MIN_MODEL_BYTES = 50 * 1024 * 1024        # an interrupted download leaves only the small config files
TEMPERATURES = [0.0, 0.2, 0.4]


# --------------------------------------------------------------------------- CPU threads
def _win_physical_cores() -> int | None:
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    size = wintypes.DWORD(0)
    k32.GetLogicalProcessorInformation(None, ctypes.byref(size))
    if not size.value:
        return None
    buf = ctypes.create_string_buffer(size.value)
    if not k32.GetLogicalProcessorInformation(buf, ctypes.byref(size)):
        return None
    ptr = ctypes.sizeof(ctypes.c_void_p)
    entry = 32 if ptr == 8 else 24          # SYSTEM_LOGICAL_PROCESSOR_INFORMATION: mask, relationship, 16-byte union
    raw = buf.raw[:size.value]
    rel = [int.from_bytes(raw[o + ptr:o + ptr + 4], "little") for o in range(0, len(raw) - entry + 1, entry)]
    return sum(1 for r in rel if r == 0) or None          # RelationProcessorCore


def _linux_physical_cores() -> int | None:
    cores, phys = set(), None
    for line in Path("/proc/cpuinfo").read_text(errors="replace").splitlines():
        k, _, v = line.partition(":")
        k = k.strip()
        if k == "physical id":
            phys = v.strip()
        elif k == "core id":
            cores.add((phys, v.strip()))
    return len(cores) or None


def _mac_physical_cores() -> int | None:
    """Apple Silicon: the performance cores (hw.perflevel0); the efficiency cores slow CTranslate2's kernels down.
    Intel Macs (no perflevel0): every physical core."""
    for key in ("hw.perflevel0.physicalcpu", "hw.physicalcpu"):
        r = subprocess.run(["sysctl", "-n", key], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip().isdigit() and int(r.stdout.strip()) > 0:
            return int(r.stdout.strip())
    return None


def physical_cores() -> int:
    """Physical CPU cores (hyper-threads are no help to CTranslate2's matrix kernels); os.cpu_count() if unknown."""
    n = None
    try:
        if sys.platform == "win32":
            n = _win_physical_cores()
        elif sys.platform == "darwin":
            n = _mac_physical_cores()
        else:
            n = _linux_physical_cores()
    except Exception:  # noqa: BLE001  (any probe failure: fall back to the logical count)
        n = None
    return max(1, int(n or os.cpu_count() or 4))


def cpu_threads(cfg: dict | None = None) -> int:
    """`transcription.json` cpu_threads: "auto" (or 0 / missing) = physical cores, else that number."""
    v = (cfg or {}).get("cpu_threads", "auto")
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = 0
    return n if n > 0 else physical_cores()


# --------------------------------------------------------------------------- backend choice
def _platform() -> tuple[str, str]:
    return sys.platform, platform.machine()


def is_apple_silicon(sysname: str | None = None, machine: str | None = None) -> bool:
    s, m = _platform()
    return (sysname or s) == "darwin" and (machine or m).lower() in ("arm64", "aarch64")


def mlx_available() -> bool:
    if "mlx_whisper" in sys.modules:
        return True
    import importlib.util
    try:
        return importlib.util.find_spec("mlx_whisper") is not None
    except (ImportError, ValueError):
        return False


def choose_backend(cfg: dict | None = None, explicit: str | None = None, *, sysname: str | None = None,
                   machine: str | None = None, mlx_ok=None) -> tuple[str, str | None]:
    """(ct2 | mlx, a note when the wish could not be honoured). `explicit` (a CLI flag) beats the config.
    `auto` picks mlx only once `mlx_verified` is true (set after the Mac parity test against faster-whisper on Arabic,
    T9.3); `backend: mlx` / `--backend mlx` uses it on Apple Silicon before that."""
    cfg = cfg or {}
    want = str(explicit or cfg.get("backend") or "auto").strip().lower()
    want = ALIASES.get(want, want)
    if want not in BACKENDS:
        raise ValueError(f"transcription backend {want!r} unknown: use one of {', '.join(BACKENDS)}")
    if want == "ct2":
        return "ct2", None
    apple = is_apple_silicon(sysname, machine)
    have = (mlx_ok or mlx_available)() if apple else False
    if want == "mlx":
        if apple and have:
            return "mlx", None
        return "ct2", ("mlx needs Apple Silicon: using faster-whisper" if not apple else
                       "mlx-whisper is not installed (reel setup installs it on Apple Silicon): using faster-whisper")
    if not apple:
        return "ct2", None
    if not have:
        return "ct2", ("Apple Silicon without mlx-whisper: faster-whisper runs on the CPU (reel setup installs "
                       "mlx-whisper on this Mac)")
    if not cfg.get("mlx_verified"):
        return "ct2", ("mlx-whisper is installed but not yet verified against faster-whisper on Arabic "
                       "(transcription.json mlx_verified): using faster-whisper; backend: mlx uses it anyway")
    return "mlx", None


# --------------------------------------------------------------------------- local snapshots (offline)
def _ct2_repo(model: str) -> str | None:
    try:
        from faster_whisper.utils import _MODELS
        return _MODELS.get(model) or CT2_REPOS.get(model)
    except Exception:  # noqa: BLE001
        return CT2_REPOS.get(model)


def _repo_dir(repo: str | None) -> Path | None:
    return models_dir() / ("models--" + repo.replace("/", "--")) if repo else None


def _snapshot(repo: str | None, need: list, min_bytes: int, any_of: list | None = None) -> Path | None:
    d = _repo_dir(repo)
    if d is None:
        return None
    snaps = d / "snapshots"
    if not snaps.is_dir():
        return None
    ref = d / "refs" / "main"
    first = [snaps / ref.read_text(encoding="utf-8").strip()] if ref.is_file() else []
    rest = sorted((s for s in snaps.iterdir() if s.is_dir()), key=lambda s: s.stat().st_mtime, reverse=True)
    for s in first + rest:
        if not s.is_dir() or not all((s / f).is_file() for f in need):
            continue
        big = [s / f for f in (any_of or []) if (s / f).is_file()]
        if any_of and not any(b.stat().st_size >= min_bytes for b in big):
            continue
        return s
    return None


def _ct2_needs(model: str) -> list:
    # the 128-mel models (large / large-v3, large-v3-turbo / turbo, distil-large-v3 and later): without
    # preprocessor_config.json faster-whisper silently falls back to 80 mel bins and transcribes garbage
    mel128 = "large-v3" in model or model in ("turbo", "large")       # faster-whisper's "large" = large-v3
    return ["config.json", "tokenizer.json"] + (["preprocessor_config.json"] if mel128 else [])


def snapshot_dir(model: str, min_bytes: int | None = None) -> Path | None:
    """The complete local faster-whisper snapshot of `model` (refs/main first, else the newest complete one), or None.
    Loading from this folder never touches the network; a model NAME makes huggingface_hub try it first (connection
    timeouts offline, and a failure when refs/main is missing after an interrupted first download)."""
    if Path(model).is_dir():
        return Path(model)
    mb = MIN_MODEL_BYTES if min_bytes is None else min_bytes
    return _snapshot(_ct2_repo(model), _ct2_needs(model), mb, ["model.bin"])


def partial_download(model: str) -> bool:
    """Some files of `model` are in the engine home but no complete snapshot (an interrupted download)."""
    d = _repo_dir(_ct2_repo(model))
    return bool(d and d.is_dir()) and snapshot_dir(model) is None


def mlx_snapshot_dir(model: str, min_bytes: int | None = None) -> Path | None:
    mb = MIN_MODEL_BYTES if min_bytes is None else min_bytes
    return _snapshot(MLX_REPOS.get(model), ["config.json"], mb, ["weights.safetensors", "weights.npz"])


def mlx_model_source(model: str) -> str:
    """A local MLX model folder: the complete snapshot, else downloaded once into the engine home (not ~/.cache)."""
    if Path(model).is_dir():
        return str(model)
    snap = mlx_snapshot_dir(model)
    if snap:
        return str(snap)
    repo = MLX_REPOS.get(model) or model
    from huggingface_hub import snapshot_download
    return str(snapshot_download(repo_id=repo, cache_dir=str(models_dir())))


# --------------------------------------------------------------------------- CTranslate2 loading
def _device_tries(cfg: dict, device: str | None, compute_type: str) -> list:
    want = (device or cfg.get("device") or "auto").lower()
    tries = []
    if want in ("auto", "cuda"):
        try:
            from . import plat
            import ctranslate2
            # skip the GPU when cuBLAS can't load: it only fails at the first inference, after loading 3 GB onto it
            if ctranslate2.get_cuda_device_count() > 0 and not plat.cuda_libs_missing():
                tries.append(("cuda", cfg.get("gpu_compute_type", "float16")))
        except Exception:  # noqa: BLE001
            pass
    if want != "cuda" or not tries:
        tries.append(("cpu", compute_type))
    return tries


def _offline() -> bool:
    return os.environ.get("HF_HUB_OFFLINE", "").strip().lower() in ("1", "true", "yes", "on")


def load_ct2(model_size: str, compute_type: str = "int8", device: str | None = None):
    """faster-whisper on an NVIDIA GPU when usable, else on the CPU. `transcription.json` device: auto | cpu | cuda.
    Returns (model, device, compute_type)."""
    from faster_whisper import WhisperModel
    cfg = load_config("transcription.json")
    tries = _device_tries(cfg, device, compute_type)
    snap = snapshot_dir(model_size)
    how = (f"run `reel model-download --model {model_size}` (about 3 GB for large-v3; it resumes an interrupted "
           "download) with an internet connection")
    if not snap and _offline():
        raise RuntimeError(f"Whisper model {model_size} is "
                           f"{'incomplete (an interrupted download)' if partial_download(model_size) else 'not downloaded'}"
                           f" and this computer is offline (HF_HUB_OFFLINE): {how}")
    kw = {"cpu_threads": cpu_threads(cfg)}
    if not snap:
        kw["download_root"] = str(models_dir())
    last = None
    for dev, ct in tries:
        try:
            return WhisperModel(str(snap) if snap else model_size, device=dev, compute_type=ct, **kw), dev, ct
        except Exception as e:  # noqa: BLE001  (e.g. CUDA runtime libraries missing -> CPU)
            last = e
    if not snap and partial_download(model_size):
        raise RuntimeError(f"Whisper model {model_size} is incomplete (an interrupted download) and could not be "
                           f"completed ({type(last).__name__}: {last}): {how}") from last
    raise last


# --------------------------------------------------------------------------- output schema
def _raw_ct2(s) -> dict:
    """A faster-whisper Segment as plain data (seconds), so segments can be re-decoded and spliced."""
    return {"start": s.start, "end": s.end, "text": s.text, "avg_logprob": s.avg_logprob,
            "no_speech_prob": s.no_speech_prob, "compression_ratio": s.compression_ratio,
            "words": [(w.word, w.start, w.end, w.probability) for w in (s.words or [])]}


def _shift(raw: dict, dt: float) -> dict:
    return dict(raw, start=raw["start"] + dt, end=raw["end"] + dt,
                words=[(w, a + dt, b + dt, p) for w, a, b, p in raw["words"]])


def _from_raw(raws: list, language, language_probability) -> dict:
    segs, words = [], []
    for r in raws:
        seg = {"id": len(segs) + 1, "start_ms": int(round(r["start"] * 1000)), "end_ms": int(round(r["end"] * 1000)),
               "text": (r["text"] or "").strip(), "avg_logprob": round(r["avg_logprob"], 3),
               "no_speech_prob": round(r["no_speech_prob"], 3), "compression_ratio": round(r["compression_ratio"], 3),
               "words": []}
        for w, ws, we, p in r["words"]:
            wd = {"id": len(words) + 1, "segment_id": seg["id"], "word": w.strip(), "start_ms": int(round(ws * 1000)),
                  "end_ms": int(round(we * 1000)), "probability": round(p, 3)}
            words.append(wd)
            seg["words"].append(wd["id"])
        segs.append(seg)
    return {"segments": segs, "words": words, "language": language, "language_probability": language_probability}


def ct2_result(segments, info) -> dict:
    return _from_raw([_raw_ct2(s) for s in segments], info.language, round(info.language_probability, 3))


def mlx_result(res: dict, language: str | None) -> dict:
    raws = [{"start": s["start"], "end": s["end"], "text": s.get("text", ""), "avg_logprob": s.get("avg_logprob", 0.0),
             "no_speech_prob": s.get("no_speech_prob", 0.0), "compression_ratio": s.get("compression_ratio", 0.0),
             "words": [(w["word"], w["start"], w["end"], w.get("probability", 0.0)) for w in (s.get("words") or [])]}
            for s in res.get("segments") or []]
    # mlx-whisper reports no language probability: 1.0 when the caller fixed the language, else unknown
    return _from_raw(raws, res.get("language") or language, 1.0 if language else None)


# --------------------------------------------------------------------------- batched safety nets
def suspect(raw: dict) -> str | None:
    """Why a batched segment must be decoded again sequentially, or None. The batched pipeline has none of 2.x's
    three safety nets: no temperature fallback when the text repeats (compression ratio > 2.4), no skip of silence
    the model 'heard' (no-speech > 0.6 with avg logprob < -1), and its ~30 s segments hide a known hallucination
    phrase from the whole-segment filter."""
    from .transcribe import hallucination_runs
    if raw["compression_ratio"] > 2.4:
        return "compression_ratio"
    if raw["no_speech_prob"] > 0.6 and raw["avg_logprob"] < -1.0:
        return "no_speech"
    if hallucination_runs([w[0] for w in raw["words"]] or (raw["text"] or "").split()):
        return "hallucination_phrase"
    return None


REDECODE_PAD_S = 0.5


def redecode_span(raws: list, k: int, total_s: float) -> tuple[float, float]:
    """The span decoded again for batched segment k: its edges come from DTW word alignment and are often 100-300 ms
    off, so a re-decode cut exactly there can clip the first or last word. Pad into the silence on each side: half the
    gap to the neighbouring segment (or the audio edge), at most 0.5 s. The neighbours' words lie outside their gaps,
    so nothing is decoded twice."""
    r = raws[k]
    prev_end = raws[k - 1]["end"] if k > 0 else 0.0
    next_start = raws[k + 1]["start"] if k + 1 < len(raws) else total_s
    before = min(REDECODE_PAD_S, max(0.0, (r["start"] - prev_end) / 2))
    after = min(REDECODE_PAD_S, max(0.0, (next_start - r["end"]) / 2))
    return max(0.0, r["start"] - before), min(total_s, r["end"] + after)


def _oom(e: Exception) -> bool:
    s = str(e).lower()
    return "out of memory" in s or "cuda_error_out_of_memory" in s


# --------------------------------------------------------------------------- runners
def _ct2_runner(model_size: str, vad: bool, log_to, batch_size: int, cfg: dict, compute_type: str = "int8",
                device: str | None = None):
    """`device`: "cpu" loads on the CPU (the GPU slot was not had, T4.10); None: the GPU when usable (the config)."""
    state: dict = {"backend": LABEL["ct2"], "vad": vad, "redecoded": []}
    want = device

    def effective_batch(device: str) -> int:
        return batch_size if (vad and device == "cuda" and batch_size > 1) else 0

    def load(device: str | None = None):
        expected = None if "device" in state else signature()
        state["model"], state["device"], state["compute_type"] = load_ct2(model_size, compute_type,
                                                                          device=device or want)
        state["cpu_threads"] = cpu_threads(cfg)
        set_batch(effective_batch(state["device"]))
        if expected and expected["device"] != state["device"]:      # the GPU would not even load the model
            state.setdefault("fallback_from", expected)
        log(log_to, f"Whisper {model_size} on {state['device']} ({state['compute_type']}), VAD {'on' if vad else 'off'}, "
                    + (f"batched x{state['batch_size']}" if state["batch_size"] else
                       f"sequential, {state['cpu_threads']} CPU threads"))

    def set_batch(bs: int):
        state["batch_size"] = bs if bs > 1 else 0
        state["pipeline"] = None
        if state["batch_size"]:
            from faster_whisper import BatchedInferencePipeline
            state["pipeline"] = BatchedInferencePipeline(state["model"])

    def signature() -> dict:
        """The decoder a checkpoint records: device, batched (batch size) or sequential (0), VAD. Before the model
        loads it is the expected one (no 3 GB load just to compare checkpoints)."""
        if "device" in state:
            return {"device": state["device"], "batch_size": state["batch_size"], "vad": vad}
        dev = _device_tries(cfg, want, compute_type)[0][0]
        return {"device": dev, "batch_size": effective_batch(dev), "vad": vad}

    def options(language, prompt):
        return dict(language=language, task="transcribe", beam_size=5, word_timestamps=True, vad_filter=vad,
                    condition_on_previous_text=False, initial_prompt=prompt, temperature=TEMPERATURES)

    def sequential(audio, language, prompt, vad_filter):
        segments, info = state["model"].transcribe(audio, **dict(options(language, prompt), vad_filter=vad_filter))
        return [_raw_ct2(s) for s in segments], info       # consumes the lazy generator: GPU errors surface here

    def decode(audio, language, prompt):
        if state["pipeline"] is None:
            raws, info = sequential(audio, language, prompt, vad)
            return _from_raw(raws, info.language, round(info.language_probability, 3))
        segments, info = state["pipeline"].transcribe(audio, batch_size=state["batch_size"], **options(language, prompt))
        raws, out, recs = [_raw_ct2(s) for s in segments], [], []
        lang = language or info.language
        total_s = len(audio) / 16000
        for k, r in enumerate(raws):
            why = suspect(r)
            if not why:
                out.append(r)
                continue
            a_s, b_s = redecode_span(raws, k, total_s)
            a, b = max(0, int(a_s * 16000)), min(len(audio), int(round(b_s * 16000)))
            again, beam = redecode(audio[a:b], lang, prompt) if b > a else ([], 5)
            again = [_shift(x, a / 16000) for x in again]
            recs.append({"start_ms": int(round(r["start"] * 1000)), "end_ms": int(round(r["end"] * 1000)),
                         "span_ms": [int(round(a_s * 1000)), int(round(b_s * 1000))], "reason": why,
                         "words_before": len(r["words"]), "words_after": sum(len(x["words"]) for x in again),
                         **({"beam_size": beam} if beam != 5 else {})})
            out.extend(again)
        state["redecoded"].extend(recs)      # only once the whole decode succeeded (no duplicates after a retry)
        return _from_raw(out, info.language, round(info.language_probability, 3))

    def redecode(span, lang, prompt):
        """The 2.x sequential decode of one suspect span; on a GPU out-of-memory, once more with beam 1 (far less
        memory) before the whole chunk degrades (smaller batch, then the CPU)."""
        try:
            return sequential(span, lang, prompt, False)[0], 5
        except Exception as e:  # noqa: BLE001
            if not _oom(e):
                raise
            segments, _ = state["model"].transcribe(span, **dict(options(lang, prompt), vad_filter=False, beam_size=1))
            return [_raw_ct2(x) for x in segments], 1

    def degrade(e):
        """GPU trouble: a smaller batch on an out-of-memory, then the CPU. Marked on the checkpoints that follow."""
        state.setdefault("fallback_from", signature())
        if state["batch_size"] > 1 and _oom(e):
            set_batch(state["batch_size"] // 2)
            log(log_to, f"GPU out of memory: retrying with "
                        + (f"batch x{state['batch_size']}" if state["batch_size"] else "sequential decoding"))
            return
        log(log_to, f"GPU transcription failed ({type(e).__name__}: {e}); retrying on CPU"
                    + (" - run `reel gpu-enable` (with the editor's OK, ~550 MB) for GPU speed"
                       if "cublas" in str(e).lower() else ""))
        load("cpu")

    def run(audio, start_ms, language, prompt):
        if "model" not in state:
            load()
        while True:
            try:
                return decode(audio, language, prompt)
            except Exception as e:  # noqa: BLE001  (GPU libraries can fail only at the first inference)
                if state["device"] != "cuda":
                    raise
                degrade(e)
    run.state, run.backend, run.signature = state, "ct2", signature
    run.load = lambda: run.state.get("model") or load()
    return run


def _mlx_runner(model_size: str, vad: bool, log_to):
    state: dict = {"backend": LABEL["mlx"], "device": "metal", "compute_type": "float16", "batch_size": 0,
                   "vad": False, "redecoded": []}   # mlx-whisper has no VAD: the episode chunks still cut in silence

    def load():
        import mlx_whisper
        state["mlx"] = mlx_whisper
        state["source"] = mlx_model_source(model_size)
        log(log_to, f"Whisper {model_size} via mlx-whisper (Metal) from {state['source']}")

    def run(audio, start_ms, language, prompt):
        if "mlx" not in state:
            load()
        res = state["mlx"].transcribe(audio, path_or_hf_repo=state["source"], language=language, task="transcribe",
                                      word_timestamps=True, condition_on_previous_text=False, initial_prompt=prompt,
                                      temperature=tuple(TEMPERATURES), verbose=None)
        return mlx_result(res, language)
    run.state, run.backend = state, "mlx"
    run.signature = lambda: {"device": "metal", "batch_size": 0, "vad": False}
    run.load = lambda: run.state.get("mlx") or load()
    return run


def make_runner(model_size: str, vad: bool, log_to=None, backend: str | None = None, batch_size: int | None = None,
                compute_type: str = "int8", device: str | None = None):
    """run(audio, start_ms, language, prompt) -> the schema above. The backend is chosen now (cheap); the model loads
    at the first call (or `run.load()`). run.state: backend label, device, compute_type, batch_size, cpu_threads,
    redecoded (batched segments decoded again); run.signature(): the decoder checkpoints record.
    `device="cpu"` (T4.10: the engine GPU slot was not had) loads on the CPU (passed through to load_ct2); MLX runs on
    the GPU (Metal), so a Mac then uses faster-whisper on the CPU."""
    cfg = load_config("transcription.json")
    name, note = choose_backend(cfg, backend)
    if name == "mlx" and device == "cpu":
        name, note = "ct2", ("the graphics card is not free for this job (busy, or WHYNOT_ACCEL=off): faster-whisper "
                             "on the CPU this time (slower)")
    if note:
        log(log_to, note)
    if name == "mlx":
        run = _mlx_runner(model_size, vad, log_to)
    else:
        bs = cfg.get("batch_size", 4) if batch_size is None else batch_size
        run = _ct2_runner(model_size, vad, log_to, max(0, int(bs or 0)), cfg, compute_type, device=device)
    run.state["backend_note"] = note
    return run


# --------------------------------------------------------------------------- parity (MLX vs CT2)
def parity(a: dict, b: dict, tol_ms: int = 80) -> dict:
    """Two decodings of the same audio agree: identical text after Arabic normalisation and every word's start/end
    within tol_ms (installer B.2: the MLX backend must match the verified CTranslate2 output)."""
    from .plan import norm
    ta = [(norm(w["word"]), w) for w in a.get("words", [])]
    tb = [(norm(w["word"]), w) for w in b.get("words", [])]
    ta, tb = [x for x in ta if x[0]], [x for x in tb if x[0]]
    text_equal = " ".join(t for t, _ in ta) == " ".join(t for t, _ in tb)
    drift = None
    if text_equal and len(ta) == len(tb):
        drift = max([max(abs(x["start_ms"] - y["start_ms"]), abs(x["end_ms"] - y["end_ms"]))
                     for (_, x), (_, y) in zip(ta, tb)] or [0])
    return {"ok": bool(text_equal and drift is not None and drift <= tol_ms), "text_equal": text_equal,
            "words": [len(ta), len(tb)], "max_drift_ms": drift, "tolerance_ms": tol_ms}


# --------------------------------------------------------------------------- bench
def bench_file() -> Path:
    return engine_home() / "bench" / "whisper-bench.json"


def bench(audio, model: str = "large-v3", backend: str | None = None, batch_size: int | None = None,
          source: str | None = None, clock=None) -> dict:
    """Decode `audio` (16 kHz float32, ~5 minutes of speech) once with VAD, as an episode chunk is decoded, and
    record the real-time factor (minutes of audio per minute of decoding) for `reel doctor`. The client's vocabulary
    hint is used when the request has a client (`--root`): it changes the speed (prompt tokens x beams x batch), so
    the cache key records it and the exact batch size."""
    import time
    clock = clock or time.perf_counter
    run = make_runner(model, vad=True, backend=backend, batch_size=batch_size)
    prompt = load_config("transcription.json").get("initial_prompt")
    t0 = clock()
    run.load()
    t1 = clock()
    t2 = clock()
    r = run(audio, 0, None, prompt)
    t3 = clock()
    st = run.state
    audio_s = round(len(audio) / 16000, 1)
    el = max(t3 - t2, 1e-6)
    entry = {"measured": now_iso(), "source": source, "audio_s": audio_s, "model": model, "backend": run.backend,
             "label": st.get("backend"), "device": st.get("device"), "compute_type": st.get("compute_type"),
             "batch_size": st.get("batch_size", 0), "cpu_threads": st.get("cpu_threads"),
             "load_s": round(t1 - t0, 2), "elapsed_s": round(el, 2), "rt_factor": round(audio_s / el, 2),
             "words": len(r.get("words", [])), "language": r.get("language"), "hint": bool(prompt),
             "hint_chars": len(prompt or ""), "redecoded": len(st.get("redecoded") or []),
             "system": f"{platform.system()} {platform.machine()}"}
    key = (f"{entry['backend']}/{model}/{entry['device']}/"
           f"{'batch' + str(entry['batch_size']) if entry['batch_size'] else 'sequential'}/"
           f"{'hint' if prompt else 'no-hint'}")
    f = bench_file()
    cache = read_json(f, {}) or {}
    cache.setdefault("results", {})[key] = entry
    cache["latest"] = key
    write_json(f, cache)
    return dict(entry, key=key, cache=str(f))


def read_bench() -> dict:
    """The cached bench for `reel doctor`: the latest result plus every configuration measured, or how to measure."""
    cache = read_json(bench_file(), {}) or {}
    res = cache.get("results") or {}
    e = res.get(cache.get("latest"))
    if not e:
        return {"measured": False, "how": "reel bench --audio <about 5 minutes of the client's speech> (runs Whisper "
                                          "once and records how fast it is on this computer)"}
    rt = e.get("rt_factor")
    return {"measured": True, "rt_factor": rt, "backend": e.get("backend"), "model": e.get("model"),
            "device": e.get("device"), "batch_size": e.get("batch_size"), "date": e.get("measured"),
            "summary": f"{e.get('model')} on {e.get('device')} ({e.get('backend')}"
                       + (f", batched x{e['batch_size']}" if e.get("batch_size") else "")
                       + (", with the client's vocabulary hint" if e.get("hint") else "") + f"): {rt} min of audio per "
                       f"minute" + (f"; a 60-minute episode ≈ {round(60 / rt, 1)} min" if rt else ""),
            "all": {k: v.get("rt_factor") for k, v in res.items()}}


# --------------------------------------------------------------------------- CLI (reel transcribe / episode-transcribe / bench)
RUN_ARGS = [
    (("--backend",), {"default": None, "choices": list(BACKENDS),
                      "help": "Whisper backend (default: transcription.json backend, auto = mlx-whisper on Apple Silicon "
                              "when installed, else faster-whisper)"}),
    (("--batch-size",), {"dest": "batch_size", "type": int, "default": None,
                         "help": "NVIDIA GPU batch on VAD-split audio (default: transcription.json batch_size; "
                                 "0 = sequential)"}),
]
BENCH_ARGS = [
    (("--audio",), {"default": None, "help": "a speech recording (any format ffmpeg reads); default with --root and "
                                            "--video-id/--episode: that project's 02_transcription audio"}),
    (("--seconds",), {"type": float, "default": 300.0, "help": "how much of it to decode (default 300)"}),
    (("--model",), {"default": None, "help": "default: preferences whisper_model, else large-v3"}),
]


def add_cli_args(name: str, sp) -> None:
    for flags, kw in RUN_ARGS + (BENCH_ARGS if name == "bench" else []):
        sp.add_argument(*flags, **kw)


def cli_bench(a, project=None) -> dict:
    """`reel bench`: the first --seconds of --audio (or the project's audio) at 16 kHz mono, decoded once."""
    import tempfile
    from .transcribe import extract_audio, whisper_audio
    src = Path(a.audio).expanduser() if a.audio else None
    if src is None and project is not None:
        src = project.p("02_transcription/dialogue_16k_mono.wav")
    if src is None or not src.is_file():          # through the CLI's handler: one JSON document, exit 1 (Gate 2)
        from .errors import Guidance
        raise Guidance(f"no speech recording to measure ({src} not found)" if src else "no speech recording to measure",
                       "reel bench --audio <a file with about 5 minutes of speech> (or --root <client> --episode <EP> "
                       "after episode-transcribe)", where=str(src) if src else None)
    if not a.model:
        from . import settings as S
        a.model = S.load().get("whisper_model") or "large-v3"
    with tempfile.TemporaryDirectory(prefix="whynot-bench-") as td:
        wav = extract_audio(src, Path(td) / "bench.wav", {"in_ms": 0, "out_ms": int(a.seconds * 1000)})
        audio = whisper_audio(wav)
    return bench(audio, model=a.model, backend=a.backend, batch_size=a.batch_size, source=str(src))
