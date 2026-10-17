# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
# Ported from the owner's Kalam engine (engine/kalam_engine.py); see adobe/tools/README.md. The pipeline (stages, cleaning,
# phrases, correction, units, fitting, packing, the written files) is the upstream code. Changes (portability audit §3.1/§5,
# A6b, brief): `main(argv)` inside the package (`python -m lib.kalam.engine`), stdout written as UTF-8 BYTES with "\n" ends
# (one JSON object per line, ensure_ascii=False; never through a console code page), SRT / JSON written with
# encoding="utf-8", newline="\n" (byte-identical on every OS), the default models folder is the pack in the engine home
# (tools/kalam/models), HF_HOME defaults to tools/kalam/hf, KMP_DUPLICATE_LIB_OK on Windows, the per-run settings file is
# read once and DELETED (the API key lives nowhere else; it is never in argv, output, files, logs or reports and is scrubbed
# from error text), the aligner (lib/kalam/align.py, Task 16) is imported lazily so the package works without it, the
# doctor also shows the subscription state ("correction"), the run log goes to the engine-home log (no settings in it).
"""Kalam engine: WAV -> corrected, voice-timed captions (SRT + JSON).

usage: python -m lib.kalam.engine run --wav W --mode ar|en|other --out DIR --settings SETTINGS.json [--models DIR]
       python -m lib.kalam.engine doctor [--models DIR] [--quick]     (one JSON line: is everything in place?)
stdout: one JSON object per line, {"stage": loading|transcribing|aligning|correcting|captions|done|error, ...}
The API key is read from the settings file only (never from argv); the file is deleted as soon as it has been read.

The callers' contract for --settings: write the per-run settings file (it may hold the API key) into <engine home>/tools/kalam/run/
(Store.new_run_settings does it, user-only) or into the temp folder, never settings.json; the engine reads it once and deletes it.
A file anywhere else, a link, or settings.json is refused and left untouched: the caller deletes its own file then."""
import argparse
import json
import os
import platform as _os_platform
import subprocess
import sys
import time
import traceback
from pathlib import Path

from . import captions as C
from . import device as _device
from . import platform as _platform
from . import transcribe as _tr
from .audio import envelope_db, load_16k
from .clean import clean_garbled, drop_hallucinations, drop_loops, drop_nonspeech_tags, drop_unspoken
from .correct import correct, correction_line, find_claude_code, make_client, notice_how, rules_for
from .phrases import phrases
from . import revisions
from .rules import enforce
from .store import Store, default_models_dir, take_settings
from .transcribe import transcribe
from .units import apply_units, join_continuations

_SECRETS = []           # literals that must never reach stdout / logs / reports (the API key of this run)

RUN_SETTINGS_CONTRACT = (
    "The per-run settings file (it may hold the API key) must be written by the caller into <engine home>/tools/kalam/run/ "
    "(Store.new_run_settings does it, user-only) or into the temp folder, never settings.json. The engine reads it once and "
    "deletes it. If the engine refuses the file (it is elsewhere, a link, or settings.json) it leaves it untouched: the caller "
    "must delete its own file.")


def prepare_env() -> None:
    """process settings the engine needs before any model library loads"""
    if _platform.is_windows():
        # CTranslate2 and PyTorch each ship Intel OpenMP; two copies in one process must not abort the run
        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("HF_HOME", str(Store().hf_dir))          # models stay in the engine home, never the plugin folder


def _align_module():
    """lib/kalam/align.py (Task 16), imported when it is needed: the package imports and the doctor runs without it"""
    from . import align
    return align


def aligner_present() -> bool:
    """is the PINNED aligner in the model cache? (a pinned download leaves no "main" reference: ask for its revision)"""
    try:
        revisions.snapshot(_align_module().REPO, local_only=True)
        return True
    except Exception:
        return False


def _nvidia_smi():
    """nvidia-smi by its absolute path: a folder of PATH that is absolute (platform.find_on_path, the same discovery as
    for Claude: never the current folder, never a bare name), then System32 on Windows; None when it is not there"""
    found = _platform.find_on_path("nvidia-smi", os.environ.get("PATH", ""))
    if found:
        return found
    if _platform.is_windows():
        root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
        if root and os.path.isabs(root) and Path(root).is_absolute():       # a relative root would follow the cwd
            candidate = Path(root) / "System32" / "nvidia-smi.exe"
            if candidate.is_file():
                return str(candidate)
    return None


def _gpu() -> str:
    exe = _nvidia_smi()
    if not exe:
        return ""
    try:
        out = subprocess.run([exe, "--query-gpu=name,driver_version", "--format=csv,noheader"],
                             capture_output=True, text=True, encoding="utf-8", timeout=15).stdout.strip()
        return out or ""
    except Exception:
        return ""


def doctor(models: str, quick: bool) -> dict:
    """what a first run needs: Python, backend, GPU, each model (files, or loaded unless quick), Claude Code and how it
    signs in (the "correction" line: subscription or the refusal text)"""
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
    res["aligner"] = True if aligner_present() else "missing: aligner in the model cache"
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
                aligner = _align_module()
                aligner.align(noise, [{"w": "test", "s": 0.3, "e": 0.8}])
                aligner_dev = aligner._load()[2]
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
            "models": res, "claude": claude, "correction": correction_line(claude),
            "ok": all(v is True for v in res.values()) and claude is not None}


def say(**kw):
    """one JSON object per line on stdout as UTF-8 bytes with "\\n" (a Windows console code page or newline translation
    never touches it); a secret of this run is replaced by *** even if some message repeated it"""
    text = json.dumps(kw, ensure_ascii=False)
    for secret in _SECRETS:
        text = text.replace(secret, "***")
    data = (text + "\n").encode("utf-8")
    buf = getattr(sys.stdout, "buffer", None)
    if buf is not None:
        sys.stdout.flush()                         # text a library printed before must not land after (or inside) our line
        buf.write(data)
        buf.flush()
    else:                                          # a text-only stand-in for stdout
        sys.stdout.write(data.decode("utf-8"))
        sys.stdout.flush()


def _scrub(text: str) -> str:
    for secret in _SECRETS:
        text = text.replace(secret, "***")
    return text


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")      # LF, no BOM: byte-identical on every OS


def run(wav: str, mode: str, out: str, settings: dict, models: str, log=None) -> dict:
    log = log or Store().log
    t0 = time.time()
    try:
        aligner = _align_module().align
    except ImportError as e:
        raise RuntimeError("the aligner is not installed (lib/kalam/align.py): %s" % e) from None
    say(stage="loading")
    a = load_16k(wav)
    env = envelope_db(a)
    say(stage="transcribing", mode=mode, seconds=round(len(a) / 16000, 2))
    log("run start mode=%s seconds=%s" % (mode, round(len(a) / 16000, 2)))
    words = transcribe(a, mode, models)
    say(stage="aligning", words=len(words), device=_tr.last_device)
    words = aligner(a, words)
    words = drop_unspoken(drop_loops(drop_hallucinations(clean_garbled(drop_nonspeech_tags(words), mode))), env)
    limits = dict(max_line=int(settings.get("max_line", C.MAX_LINE)), max_lines=int(settings.get("max_lines", C.MAX_LINES)),
                  max_dur=float(settings.get("max_dur", C.MAX_DUR)))
    ps = phrases(words, float(settings.get("min_pause", 0.22)))   # whole spoken phrases go to correction
    glossary = settings.get("glossary") or {}
    texts, stats, notice = [p["text"] for p in ps], None, None
    if settings.get("correct", True):
        say(stage="correcting", phrases=len(ps))
        rules = rules_for(settings, mode)
        client, notice = make_client(settings, finder=find_claude_code)
        if notice is None:
            texts, stats = correct(texts, rules, glossary, settings.get("api_key") or "", client=client,
                                   effort=settings.get("effort", "medium"))
            notice = stats["error"]
    kept = set(stats["kept_source"]) if stats else set(range(len(ps)))
    od = Path(out)
    od.mkdir(parents=True, exist_ok=True)
    _write(od / "corrected.json", json.dumps(   # what the corrector returned, for checking breaks
        [{"raw": p["text"], "line": t, "kept_source": k in kept} for k, (p, t) in enumerate(zip(ps, texts))],
        ensure_ascii=False, indent=0))
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
    _write(od / "captions.srt", C.to_srt(caps))
    _write(od / "captions.json", json.dumps(
        [{"n": i + 1, "s": round(c["s"], 3), "e": round(c["e"], 3), "text": c["text"]} for i, c in enumerate(caps)],
        ensure_ascii=False, indent=0))
    _write(od / "words.json", json.dumps(words, ensure_ascii=False))
    done = {"stage": "done", "captions": len(caps), "srt": str(od / "captions.srt"), "json": str(od / "captions.json"),
            "corrected": bool(stats) and not stats["error"], "stats": stats, "elapsed": round(time.time() - t0, 1)}
    if notice:
        done["notice"] = str(notice)
        how = notice_how(notice) or (stats or {}).get("how")
        if how:
            done["how"] = how
    log("done captions=%d corrected=%s notice=%s" % (len(caps), done["corrected"], done.get("notice")))
    return done


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m lib.kalam.engine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", epilog=RUN_SETTINGS_CONTRACT)
    r.add_argument("--wav", required=True)
    r.add_argument("--mode", choices=["ar", "en", "other"], default="ar")
    r.add_argument("--out", required=True)
    r.add_argument("--settings", required=True, help="per-run settings file: in <engine home>/tools/kalam/run/ or the temp "
                   "folder; read once, then deleted by the engine (the caller deletes it if the engine refuses it)")
    r.add_argument("--models", default=str(default_models_dir()))
    d = sub.add_parser("doctor")
    d.add_argument("--models", default=str(default_models_dir()))
    d.add_argument("--quick", action="store_true")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    prepare_env()
    store = Store()
    if args.cmd == "doctor":
        rep = doctor(args.models, args.quick)
        say(**rep)
        store.log("doctor ok=%s backend=%s device=%s" % (rep["ok"], rep["backend"], rep["device"]))
        return 0 if rep["ok"] else 1
    del _SECRETS[:]
    try:
        settings = take_settings(args.settings)            # read once, deleted at once: the API key is nowhere else
        key = settings.get("api_key")
        if isinstance(key, str) and key:
            _SECRETS.append(key)
        say(**run(args.wav, args.mode, args.out, settings, args.models, log=lambda m: store.log(_scrub(m))))
        return 0
    except Exception as e:  # report to the panel instead of a bare traceback
        message = _scrub("%s: %s" % (type(e).__name__, e))
        store.log("error " + message)
        say(stage="error", error=message, trace=_scrub(traceback.format_exc()[-1500:]))
        return 1
    finally:
        del _SECRETS[:]


if __name__ == "__main__":
    sys.exit(main())
