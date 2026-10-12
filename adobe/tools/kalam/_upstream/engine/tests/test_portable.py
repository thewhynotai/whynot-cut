import numpy as np

from kalam import device
from kalam.transcribe import chunks

RATE = 16000


def _speech(seconds):
    rng = np.random.default_rng(0)
    return (0.3 * rng.standard_normal(int(seconds * RATE))).astype(np.float32)


def test_pick_uses_cuda_when_probe_finds_a_gpu():
    assert device.pick(probe_cuda=lambda: 1) == ("cuda", "float16")


def test_pick_falls_back_to_cpu_when_probe_raises():
    def broken():
        raise RuntimeError("cudnn64_9.dll not found")
    assert device.pick(probe_cuda=broken) == ("cpu", "int8")


def test_pick_cpu_when_no_gpu():
    assert device.pick(probe_cuda=lambda: 0) == ("cpu", "int8")


def test_chunks_cover_audio_without_overlap_and_max_25s():
    a = _speech(70)
    c = chunks(a)
    assert c[0][0] == 0 and c[-1][1] == len(a)
    assert all(c[i][1] == c[i + 1][0] for i in range(len(c) - 1))
    assert all(e - s <= 25 * RATE for s, e in c)


def test_chunks_cut_in_silence():
    a = _speech(40)
    a[int(22.0 * RATE):int(22.3 * RATE)] = 0
    first_end = chunks(a)[0][1] / RATE
    assert 22.0 <= first_end <= 22.3


def test_chunks_continuous_hard_cut():
    c = chunks(_speech(30))
    assert 20 * RATE <= c[0][1] <= 25 * RATE


def test_chunks_short_audio_is_one_chunk():
    a = _speech(5)
    assert chunks(a) == [(0, len(a))]


def test_align_device_choice():
    from kalam.align import torch_device
    assert torch_device(lambda: True) == "cuda"
    assert torch_device(lambda: False) == "cpu"
    assert torch_device(lambda: 1 / 0) == "cpu"


class _W:
    def __init__(self, word, start, end):
        self.word, self.start, self.end = word, start, end


class _Seg:
    words = [_W(" hello", 0.1, 0.4)]


def test_whisper_falls_back_to_cpu_when_cuda_fails_while_transcribing(monkeypatch):
    import kalam.transcribe as T
    made = []

    class Fake:
        def __init__(self, d, device, compute_type):
            self.device = device
            made.append(device)

        def transcribe(self, a, **kw):
            if self.device == "cuda":
                raise RuntimeError("CUBLAS_STATUS_NOT_SUPPORTED")
            return iter([_Seg()]), None

    monkeypatch.setattr(T._device, "pick", lambda: ("cuda", "float16"))
    monkeypatch.setattr(T, "_fw", {})
    words = T._fw_words(np.zeros(16000, dtype=np.float32), "/m/x", "ar", factory=Fake)
    assert words == [{"w": "hello", "s": 0.1, "e": 0.4}] and made == ["cuda", "cpu"] and T.last_device == "cpu"


def test_aligner_moves_to_cpu_when_a_cuda_forward_pass_fails():
    from kalam.align import place_model
    calls = []

    class M:
        dev = "cpu"

        def to(self, d):
            calls.append(d)
            self.dev = d
            return self

        def __call__(self, x):
            if self.dev == "cuda":
                raise RuntimeError("no kernel image is available for execution on the device")
            return "ok"

    m, dev = place_model(M(), "cuda", probe=lambda model, d: model(None))
    assert dev == "cpu" and calls == ["cuda", "cpu"] and m.dev == "cpu"


def test_session_providers_reports_what_onnx_really_uses():
    from kalam.transcribe import session_providers

    class Sess:
        def get_providers(self):
            return ["CPUExecutionProvider"]

    class Inner:
        def __init__(self):
            self._encoder = Sess()

    class Adapter:
        def __init__(self):
            self.asr = Inner()

    assert session_providers(Adapter()) == ["CPUExecutionProvider"]
    assert session_providers(object()) == []


def test_chunks_prefer_a_real_pause_over_a_dip_inside_a_word():
    a = _speech(30)
    a[int(21.0 * RATE):int(21.25 * RATE)] *= 0.01      # a real pause (room tone, not digital silence)
    a[int(24.50 * RATE):int(24.52 * RATE)] = 0         # 20 ms dip inside a word
    end = chunks(a)[0][1] / RATE
    assert 21.0 <= end <= 21.25, end
