import json

import setup_models as S


def test_preprocessor_config_has_the_models_mel_count(tmp_path):
    S.write_preprocessor(tmp_path, n_mels=128)
    cfg = json.load(open(tmp_path / "preprocessor_config.json"))
    assert cfg["feature_size"] == 128 and cfg["sampling_rate"] == 16000 and cfg["hop_length"] == 160


def test_portable_complete_needs_every_model(tmp_path):
    assert S.portable_missing(tmp_path) == [S.CT2_ARABIC, S.CT2_OTHER, S.ONNX_ENGLISH]
    for d, f in ((S.CT2_ARABIC, "model.bin"), (S.CT2_OTHER, "model.bin"), (S.ONNX_ENGLISH, "encoder-model.onnx")):
        (tmp_path / d).mkdir()
        (tmp_path / d / f).write_bytes(b"x")
    assert S.portable_missing(tmp_path) == []
