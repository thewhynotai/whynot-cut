import json

import kalam_engine


def test_doctor_quick_reports_missing_models(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("KALAM_BACKEND", "portable")
    monkeypatch.setattr(kalam_engine, "aligner_present", lambda: False)   # never point huggingface_hub at tmp:
                                                                          # it keeps HF_HOME from first import
    code = kalam_engine.main(["doctor", "--models", str(tmp_path), "--quick"])
    rep = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == 1 and rep["ok"] is False
    assert rep["backend"] == "portable"
    assert set(rep["models"]) == {"arabic", "english", "other", "aligner"}
    assert all(v is not True for v in rep["models"].values())
    assert rep["device"] in ("cuda", "cpu") and "python" in rep and "claude" in rep


def test_doctor_quick_ok_when_files_exist(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("KALAM_BACKEND", "portable")
    monkeypatch.setattr(kalam_engine, "aligner_present", lambda: True)
    for d, f in (("ct2-whisper-turbo-ar-dialectal", "model.bin"), ("ct2-whisper-large-v3-turbo", "model.bin"),
                 ("parakeet-tdt-0.6b-v2-onnx", "encoder-model.onnx")):
        (tmp_path / d).mkdir()
        (tmp_path / d / f).write_bytes(b"x")
    kalam_engine.main(["doctor", "--models", str(tmp_path), "--quick"])
    rep = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rep["models"] == {"arabic": True, "english": True, "other": True, "aligner": True}
