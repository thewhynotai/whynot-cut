"""GPU when there is one that works, else CPU. On Windows the CUDA DLLs shipped inside PyTorch serve all engines."""
import os
import sys


def _ct2_cuda_count() -> int:
    import ctranslate2
    return ctranslate2.get_cuda_device_count()


def pick(probe_cuda=_ct2_cuda_count) -> tuple:
    """(device, compute_type) for CTranslate2: ("cuda", "float16") or ("cpu", "int8"); never raises"""
    try:
        if probe_cuda() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


_added = False


def add_torch_dlls() -> None:
    """Windows: put torch\\lib (cuBLAS, cuDNN) on the DLL search path before CTranslate2 / onnxruntime load"""
    global _added
    if _added or sys.platform != "win32":
        return
    _added = True
    try:
        import importlib.util
        spec = importlib.util.find_spec("torch")
        if spec and spec.origin:
            lib = os.path.join(os.path.dirname(spec.origin), "lib")
            if os.path.isdir(lib):
                os.add_dll_directory(lib)
                os.environ["PATH"] = lib + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass
