"""Whisper backends (3.0 T2.12: engine IM-13, decision D9): one interface, two engines, one output schema.

  ct2  faster-whisper / CTranslate2 (the verified backend): an NVIDIA GPU (fp16) when usable, else the CPU (int8) with
       `cpu_threads` = the machine's physical cores (faster-whisper's own default is 4). On the GPU, audio that VAD
       splits (episodes, clips longer than `long_clip_minutes`) is decoded by `BatchedInferencePipeline`.
  mlx  mlx-whisper on Apple Silicon (Metal), word timestamps. Not verified live yet (needs a Mac, T9.3).

`transcription.json` `backend`: auto (mlx on Apple Silicon when mlx-whisper is installed, else ct2) | ct2 | mlx.
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
CT2_REPOS = {"large-v3": "Systran/faster-whisper-large-v3", "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
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


def physical_cores() -> int:
    """Physical CPU cores (hyper-threads are no help to CTranslate2's matrix kernels); os.cpu_count() if unknown."""
    n = None
    try:
        if sys.platform == "win32":
            n = _win_physical_cores()
        elif sys.platform == "darwin":
            r = subprocess.run(["sysctl", "-n", "hw.physicalcpu"], capture_output=True, text=True, timeout=5)
            n = int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else None
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
    """(ct2 | mlx, a note when the wish could not be honoured). `explicit` (a CLI flag) beats the config."""
    want = str(explicit or (cfg or {}).get("backend") or "auto").strip().lower()
    want = ALIASES.get(want, want)
    if want not in BACKENDS:
        raise ValueError(f"transcription backend {want!r} unknown: use one of {', '.join(BACKENDS)}")
    if want == "ct2":
        return "ct2", None
    apple = is_apple_silicon(sysname, machine)
    have = (mlx_ok or mlx_available)() if apple else False
    if apple and have:
        return "mlx", None
    if want == "auto":
        return "ct2", ("Apple Silicon without mlx-whisper: faster-whisper runs on the CPU (reel setup installs "
                       "mlx-whisper on this Mac)" if apple else None)
    return "ct2", ("mlx needs Apple Silicon: using faster-whisper" if not apple else
                   "mlx-whisper is not installed (reel setup installs it on Apple Silicon): using faster-whisper")


# --------------------------------------------------------------------------- local snapshots (offline)
def _ct2_repo(model: str) -> str | None:
    try:
        from faster_whisper.utils import _MODELS
        return _MODELS.get(model) or CT2_REPOS.get(model)
    except Exception:  # noqa: BLE001
        return CT2_REPOS.get(model)


def _snapshot(repo: str | None, need: list, min_bytes: int, any_of: list | None = None) -> Path | None:
    if not repo:
        return None
    d = models_dir() / ("models--" + repo.replace("/", "--"))
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


def snapshot_dir(model: str, min_bytes: int | None = None) -> Path | None:
    """The complete local faster-whisper snapshot of `model` (refs/main first, else the newest complete one), or None.
    Loading from this folder never touches the network; a model NAME makes huggingface_hub try it first (connection
    timeouts offline, and a failure when refs/main is missing after an interrupted first download)."""
    if Path(model).is_dir():
        return Path(model)
    mb = MIN_MODEL_BYTES if min_bytes is None else min_bytes
    return _snapshot(_ct2_repo(model), ["config.json", "tokenizer.json"], mb, ["model.bin"])


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
def load_ct2(model_size: str, compute_type: str = "int8", device: str | None = None):
    """faster-whisper on an NVIDIA GPU when usable, else on the CPU. `transcription.json` device: auto | cpu | cuda.
    Returns (model, device, compute_type)."""
    from faster_whisper import WhisperModel
    cfg = load_config("transcription.json")
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
    snap = snapshot_dir(model_size)
    kw = {"cpu_threads": cpu_threads(cfg)}
    if not snap:
        kw["download_root"] = str(models_dir())
    last = None
    for dev, ct in tries:
        try:
            return WhisperModel(str(snap) if snap else model_size, device=dev, compute_type=ct, **kw), dev, ct
        except Exception as e:  # noqa: BLE001  (e.g. CUDA runtime libraries missing -> CPU)
            last = e
    raise last


# --------------------------------------------------------------------------- output schema
def _seg_dict(segs, words, start, end, text, avg_logprob, no_speech_prob, compression_ratio, wlist):
    seg = {"id": len(segs) + 1, "start_ms": int(round(start * 1000)), "end_ms": int(round(end * 1000)),
           "text": text.strip(), "avg_logprob": round(avg_logprob, 3), "no_speech_prob": round(no_speech_prob, 3),
           "compression_ratio": round(compression_ratio, 3), "words": []}
    for w, ws, we, p in wlist:
        wd = {"id": len(words) + 1, "segment_id": seg["id"], "word": w.strip(), "start_ms": int(round(ws * 1000)),
              "end_ms": int(round(we * 1000)), "probability": round(p, 3)}
        words.append(wd)
        seg["words"].append(wd["id"])
    segs.append(seg)


def ct2_result(segments, info) -> dict:
    segs, words = [], []
    for s in segments:
        _seg_dict(segs, words, s.start, s.end, s.text, s.avg_logprob, s.no_speech_prob, s.compression_ratio,
                  [(w.word, w.start, w.end, w.probability) for w in (s.words or [])])
    return {"segments": segs, "words": words, "language": info.language,
            "language_probability": round(info.language_probability, 3)}


def mlx_result(res: dict, language: str | None) -> dict:
    segs, words = [], []
    for s in res.get("segments") or []:
        _seg_dict(segs, words, s["start"], s["end"], s.get("text", ""), s.get("avg_logprob", 0.0),
                  s.get("no_speech_prob", 0.0), s.get("compression_ratio", 0.0),
                  [(w["word"], w["start"], w["end"], w.get("probability", 0.0)) for w in (s.get("words") or [])])
    # mlx-whisper reports no language probability: 1.0 when the caller fixed the language, else unknown
    return {"segments": segs, "words": words, "language": res.get("language") or language,
            "language_probability": 1.0 if language else None}


# --------------------------------------------------------------------------- runners
def _ct2_runner(model_size: str, vad: bool, log_to, batch_size: int, cfg: dict, compute_type: str = "int8"):
    state: dict = {"backend": LABEL["ct2"], "vad": vad}

    def load(device: str | None = None):
        state["model"], state["device"], state["compute_type"] = load_ct2(model_size, compute_type, device=device)
        state["cpu_threads"] = cpu_threads(cfg)
        bs = batch_size if (vad and state["device"] == "cuda") else 0
        state["pipeline"] = None
        if bs > 1:
            from faster_whisper import BatchedInferencePipeline
            state["pipeline"] = BatchedInferencePipeline(state["model"])
        state["batch_size"] = bs if state["pipeline"] else 0
        log(log_to, f"Whisper {model_size} on {state['device']} ({state['compute_type']}), VAD {'on' if vad else 'off'}, "
                    + (f"batched x{state['batch_size']}" if state["batch_size"] else
                       f"sequential, {state['cpu_threads']} CPU threads"))

    def decode(audio, language, prompt):
        opts = dict(language=language, task="transcribe", beam_size=5, word_timestamps=True, vad_filter=vad,
                    condition_on_previous_text=False, initial_prompt=prompt, temperature=TEMPERATURES)
        if state["pipeline"] is not None:
            segments, info = state["pipeline"].transcribe(audio, batch_size=state["batch_size"], **opts)
        else:
            segments, info = state["model"].transcribe(audio, **opts)
        return ct2_result(segments, info)       # consumes the lazy generator: GPU errors surface here

    def run(audio, start_ms, language, prompt):
        if "model" not in state:
            load()
        try:
            return decode(audio, language, prompt)
        except Exception as e:  # noqa: BLE001  (GPU libraries can fail only at the first inference)
            if state["device"] != "cuda":
                raise
            log(log_to, f"GPU transcription failed ({type(e).__name__}: {e}); retrying on CPU"
                        + (" - run `reel gpu-enable` (with the editor's OK, ~550 MB) for GPU speed"
                           if "cublas" in str(e).lower() else ""))
            load("cpu")
            return decode(audio, language, prompt)
    run.state, run.backend, run.load = state, "ct2", lambda: run.state.get("model") or load()
    return run


def _mlx_runner(model_size: str, vad: bool, log_to):
    state: dict = {"backend": LABEL["mlx"], "device": "metal", "compute_type": "float16", "batch_size": 0,
                   "vad": False}      # mlx-whisper has no VAD: the episode chunks still cut in silence

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
    run.state, run.backend, run.load = state, "mlx", lambda: run.state.get("mlx") or load()
    return run


def make_runner(model_size: str, vad: bool, log_to=None, backend: str | None = None, batch_size: int | None = None,
                compute_type: str = "int8"):
    """run(audio, start_ms, language, prompt) -> the schema above. The backend is chosen now (cheap); the model loads
    at the first call (or `run.load()`). run.state: backend label, device, compute_type, batch_size, cpu_threads."""
    cfg = load_config("transcription.json")
    name, note = choose_backend(cfg, backend)
    if note:
        log(log_to, note)
    if name == "mlx":
        run = _mlx_runner(model_size, vad, log_to)
    else:
        bs = cfg.get("batch_size", 4) if batch_size is None else batch_size
        run = _ct2_runner(model_size, vad, log_to, max(0, int(bs or 0)), cfg, compute_type)
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
    record the real-time factor (minutes of audio per minute of decoding) for `reel doctor`."""
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
             "words": len(r.get("words", [])), "language": r.get("language"),
             "system": f"{platform.system()} {platform.machine()}"}
    key = f"{entry['backend']}/{model}/{entry['device']}/{'batched' if entry['batch_size'] else 'sequential'}"
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
                       + (f", batched x{e['batch_size']}" if e.get("batch_size") else "") + f"): {rt} min of audio per "
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
    if src is None or not src.is_file():
        print(__import__("json").dumps({
            "error": f"no speech recording to measure ({src} not found)" if src else "no speech recording to measure",
            "how": "reel bench --audio <a file with about 5 minutes of speech> (or --root <client> --episode <EP> "
                   "after episode-transcribe)"}, ensure_ascii=False))
        raise SystemExit(2)
    if not a.model:
        from . import settings as S
        a.model = S.load().get("whisper_model") or "large-v3"
    with tempfile.TemporaryDirectory(prefix="whynot-bench-") as td:
        wav = extract_audio(src, Path(td) / "bench.wav", {"in_ms": 0, "out_ms": int(a.seconds * 1000)})
        audio = whisper_audio(wav)
    return bench(audio, model=a.model, backend=a.backend, batch_size=a.batch_size, source=str(src))
