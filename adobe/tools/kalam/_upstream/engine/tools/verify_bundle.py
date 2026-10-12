"""Check a built Kalam-Windows folder before it is handed out. usage: verify_bundle.py <bundle> [--no-load]
Static checks (Windows binaries only, packages, CUDA DLLs, models, no /Users/ paths), then the engine's doctor run
on this Mac against the bundle's own model files (CPU)."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REQUIRED = ["torch", "torchaudio", "transformers", "numpy", "soundfile", "anthropic", "huggingface_hub",
            "faster_whisper", "ctranslate2", "onnx_asr", "onnxruntime", "av", "tokenizers"]
CUDA = [("torch/lib", "cudnn64_9"), ("torch/lib", "cublas64_12"), ("onnxruntime/capi", "onnxruntime_providers_cuda"),
        ("_soundfile_data", "libsndfile_x64")]
MODELS = [("ct2-whisper-turbo-ar-dialectal", "model.bin"), ("ct2-whisper-large-v3-turbo", "model.bin"),
          ("parakeet-tdt-0.6b-v2-onnx", "encoder-model.onnx")]
TEXT = {".js", ".jsx", ".py", ".html", ".txt", ".xml", ".css", ".ps1", ".bat"}


# DLLs every Windows has, the NVIDIA driver's own, and the C++ runtime the installer puts in place (vc_redist)
SYSTEM_DLL = re.compile(r"^(api-ms-win-.*|ext-ms-.*|kernel32|user32|advapi32|shell32|ole32|oleaut32|ws2_32|shlwapi|"
                        r"bcrypt|crypt32|psapi|winmm|version|ntdll|iphlpapi|setupapi|dbghelp|gdi32|comdlg32|secur32|"
                        r"rpcrt4|userenv|wintrust|imm32|dxgi|d3d11|d3d12|dwmapi|powrprof|mswsock|normaliz|wldap32|"
                        r"nvcuda|nvml|msvcp140.*|vcruntime140.*|concrt140|vcomp140|ucrtbase)\.dll$", re.I)
CHECK_DLLS = ["torch/lib/torch_cuda.dll", "torch/lib/torch_cpu.dll", "ctranslate2/ctranslate2.dll",
              "onnxruntime/capi/onnxruntime.dll", "onnxruntime/capi/onnxruntime_providers_cuda.dll"]


def dll_imports(objdump_text: str) -> list:
    return re.findall(r"DLL Name:\s*(\S+)", objdump_text)


def missing_dlls(imports: list, available: set) -> list:
    have = {a.lower() for a in available}
    return [d for d in imports if not SYSTEM_DLL.match(d) and d.lower() not in have]


def import_problems(bundle) -> list:
    """every DLL the key Windows binaries load must be in the bundle or part of Windows / the driver"""
    b = Path(bundle)
    site = b / "runtime/python/Lib/site-packages"
    available = {f.name for f in b.rglob("*.dll")}
    out = []
    for rel in CHECK_DLLS:
        f = site / rel
        if not f.exists():
            out.append("missing %s" % rel)
            continue
        txt = subprocess.run(["/usr/bin/objdump", "-p", str(f)], capture_output=True, text=True).stdout
        out += ["%s needs %s (not in the bundle)" % (rel, d) for d in missing_dlls(dll_imports(txt), available)]
    return out


def problems(bundle) -> list:
    b = Path(bundle)
    site = b / "runtime/python/Lib/site-packages"
    out = []
    if not (b / "runtime/python/python.exe").exists():
        out.append("missing runtime/python/python.exe")
    out += ["missing package %s" % p for p in REQUIRED if not ((site / p).is_dir() or (site / (p + ".py")).is_file())]
    for f in site.rglob("*"):
        if f.suffix in (".so", ".dylib"):
            out.append("non-Windows binary: %s" % f.relative_to(b))
        elif f.suffix == ".pyd" and "-" in f.stem.split(".")[-1] and "win_amd64" not in f.name:
            out.append("wrong-platform extension: %s" % f.relative_to(b))
    for d, stem in CUDA:
        if not list((site / d).glob(stem + "*.dll")):
            out.append("missing Windows library %s/%s*.dll" % (d, stem))
    out += ["missing model %s/%s" % (d, f) for d, f in MODELS if not (b / "runtime/models" / d / f).exists()]
    if not (b / "runtime/VERSION").exists():
        out.append("missing runtime/VERSION")
    for f in b.rglob("*"):
        if f.is_file() and f.suffix in TEXT and "python" not in f.relative_to(b).parts[:2]:   # our files, not Python's
            if "/Users/" in f.read_text(encoding="utf-8", errors="ignore"):
                out.append("Mac path inside %s" % f.relative_to(b))
    return out


def load_check(bundle) -> dict:
    """the engine from the bundle, the models from the bundle, run on this Mac (portable backend, CPU)"""
    b = Path(bundle)
    env = dict(os.environ, KALAM_BACKEND="portable", HF_HOME=str(b / "runtime/hf"), HF_HUB_OFFLINE="1", PYTHONUTF8="1")
    p = subprocess.run([sys.executable, str(b / "panel/engine/kalam_engine.py"), "doctor", "--models",
                        str(b / "runtime/models")], env=env, capture_output=True, text=True, encoding="utf-8")
    lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
    return json.loads(lines[-1]) if lines else {"ok": False, "error": p.stderr[-2000:]}


def main(argv) -> int:
    ps = problems(argv[0]) + import_problems(argv[0])
    for p in ps:
        print("PROBLEM " + p)
    if "--no-load" not in argv:
        rep = load_check(argv[0])
        print("doctor: " + json.dumps(rep, ensure_ascii=False))
        if not all(v is True for v in rep.get("models", {"x": 0}).values()):
            ps.append("models do not load")
    print("BUNDLE OK" if not ps else "BUNDLE HAS %d PROBLEM(S)" % len(ps))
    return 0 if not ps else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
