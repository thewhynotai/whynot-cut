"""Kalam engine: WAV -> corrected, voice-timed captions (SRT + JSON).

usage: kalam_engine.py run --wav W --mode ar|en|other --out DIR --settings SETTINGS.json [--models DIR]
       kalam_engine.py doctor [--models DIR] [--quick]     (one JSON line: is everything in place?)
stdout: one JSON object per line, {"stage": loading|transcribing|aligning|correcting|captions|done|error, ...}
The API key is read from the settings file only (never from argv)."""
import argparse
import json
import os
import platform as _os_platform
import subprocess
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.platform == "win32":
    # CTranslate2 and PyTorch each ship Intel OpenMP; two copies in one process must not abort the run
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from kalam import captions as C            # noqa: E402
from kalam.align import align              # noqa: E402
from kalam.audio import envelope_db, load_16k   # noqa: E402
from kalam.clean import clean_garbled, drop_hallucinations, drop_loops, drop_nonspeech_tags, drop_unspoken   # noqa: E402
from kalam.correct import correct, make_client, rules_for   # noqa: E402
from kalam.phrases import phrases          # noqa: E402
from kalam.rules import enforce            # noqa: E402
from kalam.transcribe import transcribe    # noqa: E402
from kalam.units import apply_units, join_continuations   # noqa: E402

from kalam import device as _device         # noqa: E402
from kalam import platform as _platform     # noqa: E402
from kalam import transcribe as _tr         # noqa: E402
from kalam.correct import find_claude_code  # noqa: E402

if _platform.is_windows():
    DEFAULT_MODELS = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Kalam" / "models"
else:
    DEFAULT_MODELS = Path.home() / "Library/Application Support/Kalam/models"


def aligner_present() -> bool:
    from huggingface_hub import snapshot_download
    from kalam.align import REPO
    try:
        snapshot_download(REPO, local_files_only=True)
        return True
    except Exception:
        return False


def _gpu() -> str:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
                             capture_output=True, text=True, encoding="utf-8", timeout=15).stdout.strip()
        return out or ""
    except Exception:
        return ""


def doctor(models: str, quick: bool) -> dict:
    """what a first run needs: Python, backend, GPU, each model (files, or loaded unless quick), Claude Code"""
    md, backend = Path(models), _platform.backend()
    if backend == "portable":
        _device.add_torch_dlls()
        files = {"arabic": md / _tr.CT2_ARABIC_DIR / "model.bin", "other": md / _tr.CT2_OTHER_DIR / "model.bin",
                 "english": md / _tr.ONNX_ENGLISH_DIR / "encoder-model.onnx"}
        dev = _device.pick()[0]
    else:
        files = {"arabic": md / _tr.ARABIC_DIR / "weights.safetensors"}
        dev = "apple-gpu"
    res = {k: (True if f.exists() else "missing: %s" % f) for k, f in files.items()}
    if backend != "portable":
        res["english"] = res["other"] = True       # MLX repos live in the HF cache, checked by loading
    res["aligner"] = True if aligner_present() else "missing: MMS aligner in the model cache"
    aligner_dev = None
    if not quick:
        # the same steps as a real run, in the same process and order: transcribe, then align
        import numpy as np
        noise = (np.random.default_rng(0).standard_normal(32000) * 0.05).astype(np.float32)
        devices = {}
        for key, mode in (("arabic", "ar"), ("english", "en"), ("other", "other")):
            if res[key] is True:
                try:
                    _tr.transcribe(noise, mode, str(md))
                    devices[key] = _tr.last_device
                except Exception as e:
                    res[key] = "%s: %s" % (type(e).__name__, str(e)[:200])
        if res["aligner"] is True:
            try:
                from kalam.align import _load as _load_aligner
                align(noise, [{"w": "test", "s": 0.3, "e": 0.8}])
                aligner_dev = _load_aligner()[2]
            except Exception as e:
                res["aligner"] = "%s: %s" % (type(e).__name__, str(e)[:200])
        if backend == "portable" and devices:
            dev = devices.get("arabic", next(iter(devices.values())))
        res_devices = devices
    else:
        res_devices = {}
    claude = find_claude_code()
    return {"python": sys.version.split()[0], "platform": _os_platform.platform(), "backend": backend, "device": dev,
            "gpu": _gpu(), "devices": dict(res_devices, aligner=aligner_dev) if aligner_dev else res_devices,
            "models": res, "claude": claude,
            "ok": all(v is True for v in res.values()) and claude is not None}


def say(**kw):
    print(json.dumps(kw, ensure_ascii=False), flush=True)


def run(wav: str, mode: str, out: str, settings: dict, models: str) -> dict:
    t0 = time.time()
    say(stage="loading")
    a = load_16k(wav)
    env = envelope_db(a)
    say(stage="transcribing", mode=mode, seconds=round(len(a) / 16000, 2))
    words = transcribe(a, mode, models)
    say(stage="aligning", words=len(words), device=_tr.last_device)
    words = align(a, words)
    words = drop_unspoken(drop_loops(drop_hallucinations(clean_garbled(drop_nonspeech_tags(words), mode))), env)
    limits = dict(max_line=int(settings.get("max_line", C.MAX_LINE)), max_lines=int(settings.get("max_lines", C.MAX_LINES)),
                  max_dur=float(settings.get("max_dur", C.MAX_DUR)))
    ps = phrases(words, float(settings.get("min_pause", 0.22)))   # whole spoken phrases go to correction
    glossary = settings.get("glossary") or {}
    texts, stats, notice = [p["text"] for p in ps], None, None
    if settings.get("correct", True):
        say(stage="correcting", phrases=len(ps))
        rules = rules_for(settings, mode)
        client, notice = make_client(settings)
        if notice is None:
            texts, stats = correct(texts, rules, glossary, settings.get("api_key") or "", client=client,
                                   effort=settings.get("effort", "medium"))
            notice = stats["error"]
    kept = set(stats["kept_source"]) if stats else set(range(len(ps)))
    (Path(out) / "corrected.json").parent.mkdir(parents=True, exist_ok=True)
    (Path(out) / "corrected.json").write_text(json.dumps(   # what the corrector returned, for checking breaks
        [{"raw": p["text"], "line": t, "kept_source": k in kept} for k, (p, t) in enumerate(zip(ps, texts))],
        ensure_ascii=False, indent=0), encoding="utf-8")
    for k, (p, t) in enumerate(zip(ps, texts)):
        if k in kept:                       # uncorrected line: rules only, no meaning-unit marks
            p["text"] = enforce(t, glossary, mode)
            apply_units(p, None, glossary, mode)
        else:
            apply_units(p, t, glossary, mode)
    ps = join_continuations([p for p in ps if p["text"]], float(settings.get("stop_pause", C.STOP_PAUSE)))
    ps = C.fit_phrases(ps, **limits)  # then split to fit, at real word onsets
    say(stage="captions", phrases=len(ps))
    caps = C.pack(ps, stop_pause=float(settings.get("stop_pause", C.STOP_PAUSE)), **limits)
    od = Path(out)
    od.mkdir(parents=True, exist_ok=True)
    (od / "captions.srt").write_text(C.to_srt(caps), encoding="utf-8")
    (od / "captions.json").write_text(json.dumps(
        [{"n": i + 1, "s": round(c["s"], 3), "e": round(c["e"], 3), "text": c["text"]} for i, c in enumerate(caps)],
        ensure_ascii=False, indent=0), encoding="utf-8")
    (od / "words.json").write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    done = {"stage": "done", "captions": len(caps), "srt": str(od / "captions.srt"), "json": str(od / "captions.json"),
            "corrected": bool(stats) and not stats["error"], "stats": stats, "elapsed": round(time.time() - t0, 1)}
    if notice:
        done["notice"] = notice
    return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--wav", required=True)
    r.add_argument("--mode", choices=["ar", "en", "other"], default="ar")
    r.add_argument("--out", required=True)
    r.add_argument("--settings", required=True)
    r.add_argument("--models", default=str(DEFAULT_MODELS))
    d = sub.add_parser("doctor")
    d.add_argument("--models", default=str(DEFAULT_MODELS))
    d.add_argument("--quick", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "doctor":
        rep = doctor(args.models, args.quick)
        say(**rep)
        return 0 if rep["ok"] else 1
    try:
        settings = json.loads(Path(args.settings).read_text(encoding="utf-8"))
        say(**run(args.wav, args.mode, args.out, settings, args.models))
        return 0
    except Exception as e:  # report to the panel instead of a bare traceback
        say(stage="error", error="%s: %s" % (type(e).__name__, e), trace=traceback.format_exc()[-1500:])
        return 1


if __name__ == "__main__":
    sys.exit(main())
