# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
# Ported from the owner's Kalam engine (kalam/device.py); see adobe/tools/README.md. Change to the upstream file (portability
# audit §3.1): add_torch_dlls first enables the CUDA libraries the engine already knows (lib/plat.enable_cuda_libs: the
# engine home's cuda/bin and NVIDIA's pip wheels, Windows DLL directories or a Linux preload), then, on Windows, adds torch\lib
# of the Kalam pack when torch is installed (unchanged). pick() is unchanged (the CT2 CUDA count rule).
"""GPU when there is one that works, else CPU. On Windows the CUDA DLLs shipped inside PyTorch serve all engines."""
import os
import sys

from .. import plat as _plat


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
    """Make the CUDA libraries loadable before CTranslate2 / onnxruntime load: the engine's own (plat.enable_cuda_libs),
    and on Windows the torch/lib folder (cuBLAS, cuDNN) of the Kalam pack when it is installed. Once per process; never raises."""
    global _added
    if _added:
        return
    _added = True
    try:
        _plat.enable_cuda_libs()
    except Exception:
        pass
    if sys.platform != "win32":
        return
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
