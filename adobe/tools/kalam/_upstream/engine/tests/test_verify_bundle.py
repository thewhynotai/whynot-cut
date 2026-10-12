import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import verify_bundle as V  # noqa: E402


def _tree(tmp_path):
    b = tmp_path / "Kalam-Windows"
    site = b / "runtime/python/Lib/site-packages"
    (b / "panel/engine/kalam").mkdir(parents=True)
    (b / "panel/js").mkdir(parents=True)
    site.mkdir(parents=True)
    (b / "runtime/python/python.exe").write_bytes(b"MZ")
    for pkg in V.REQUIRED:
        (site / pkg).mkdir()
    (site / "torch/lib").mkdir(parents=True, exist_ok=True)
    (site / "torch/lib/cudnn64_9.dll").write_bytes(b"MZ")
    (site / "torch/lib/cublas64_12.dll").write_bytes(b"MZ")
    (site / "onnxruntime/capi").mkdir(parents=True, exist_ok=True)
    (site / "onnxruntime/capi/onnxruntime_providers_cuda.dll").write_bytes(b"MZ")
    (site / "_soundfile_data").mkdir()
    (site / "_soundfile_data/libsndfile_x64.dll").write_bytes(b"MZ")
    (site / "numpy").mkdir(exist_ok=True)
    (site / "numpy/_core.cp312-win_amd64.pyd").write_bytes(b"MZ")
    (b / "panel/js/engine.js").write_text("var x = 1;", encoding="utf-8")
    for d in ("ct2-whisper-turbo-ar-dialectal", "ct2-whisper-large-v3-turbo"):
        (b / "runtime/models" / d).mkdir(parents=True)
        (b / "runtime/models" / d / "model.bin").write_bytes(b"x")
    (b / "runtime/models/parakeet-tdt-0.6b-v2-onnx").mkdir(parents=True)
    (b / "runtime/models/parakeet-tdt-0.6b-v2-onnx/encoder-model.onnx").write_bytes(b"x")
    (b / "runtime/VERSION").write_text("x", encoding="utf-8")
    return b, site


def test_clean_bundle_has_no_problems(tmp_path):
    b, _ = _tree(tmp_path)
    assert V.problems(b) == []


def test_mac_binary_is_reported(tmp_path):
    b, site = _tree(tmp_path)
    (site / "numpy/_core.cpython-312-darwin.so").write_bytes(b"x")
    assert any("darwin.so" in p for p in V.problems(b))


def test_mac_path_in_panel_is_reported(tmp_path):
    b, _ = _tree(tmp_path)
    (b / "panel/js/engine.js").write_text("var p = '/Users/macstoreeg/x';", encoding="utf-8")
    assert any("engine.js" in p for p in V.problems(b))


def test_missing_cuda_dll_and_package_reported(tmp_path):
    b, site = _tree(tmp_path)
    (site / "torch/lib/cudnn64_9.dll").unlink()
    (site / "faster_whisper").rmdir()
    ps = V.problems(b)
    assert any("cudnn" in p for p in ps) and any("faster_whisper" in p for p in ps)


def test_single_file_module_counts_as_present(tmp_path):
    b, site = _tree(tmp_path)
    (site / "soundfile").rmdir()
    (site / "soundfile.py").write_text("x", encoding="utf-8")
    assert V.problems(b) == []


def test_python_stdlib_text_is_not_scanned(tmp_path):
    b, _ = _tree(tmp_path)
    (b / "runtime/python/Lib/ntpath.py").write_text("# e.g. /Users/someone", encoding="utf-8")
    assert V.problems(b) == []


def test_soundfile_needs_its_windows_dll(tmp_path):
    b, site = _tree(tmp_path)
    (site / "_soundfile_data/libsndfile_x64.dll").unlink()
    assert any("libsndfile" in p for p in V.problems(b))


OBJDUMP = """
The Import Tables:
  lookup 0001 time 00000000 fwd 00000000 name 0002 addr 0003

    DLL Name: KERNEL32.dll
    vma:  Hint/Ord Member-Name Bound-To
    DLL Name: cublas64_13.dll
    DLL Name: cudart64_12.dll
    DLL Name: api-ms-win-crt-runtime-l1-1-0.dll
    DLL Name: nvcuda.dll
    DLL Name: MSVCP140.dll
"""


def test_dll_imports_are_read_from_objdump():
    assert V.dll_imports(OBJDUMP) == ["KERNEL32.dll", "cublas64_13.dll", "cudart64_12.dll",
                                      "api-ms-win-crt-runtime-l1-1-0.dll", "nvcuda.dll", "MSVCP140.dll"]


def test_missing_dlls_ignores_windows_and_driver_and_finds_the_rest():
    have = {"cudart64_12.dll"}
    assert V.missing_dlls(V.dll_imports(OBJDUMP), have) == ["cublas64_13.dll"]
