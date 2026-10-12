import os
from pathlib import Path

import pytest

from kalam.align import align
from kalam.audio import envelope_db, load_16k
from kalam.transcribe import transcribe

SUPPORT = Path.home() / "Library/Application Support"
SHERIF = SUPPORT / "Hush/bench/sherif.wav"
ENGLISH = SUPPORT / "Hush/test/speech.wav"          # macOS "say" test clip, 48 kHz
MODELS = SUPPORT / "Kalam/models"
os.environ.setdefault("HF_HOME", str(SUPPORT / "Kalam/hf"))

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def sherif_words():
    a = load_16k(str(SHERIF))
    return a, align(a, transcribe(a, "ar", str(MODELS)))


def test_load_16k_resamples_48k(tmp_path):
    a = load_16k(str(ENGLISH))
    assert abs(len(a) / 16000 - 17.68) < 0.05 or abs(len(a) / 16000 - 15.12) < 0.05
    assert envelope_db(a).shape[0] == int(len(a) / 160)


def test_arabic_transcribe_and_align(sherif_words):
    a, ws = sherif_words
    assert len(ws) >= 190
    assert all(w["s"] <= w["e"] for w in ws)
    assert all(ws[i]["s"] <= ws[i + 1]["s"] + 1e-6 for i in range(len(ws) - 1))
    shabab = [w for w in ws if w["w"] == "شباب"]
    assert shabab and abs(shabab[0]["s"] - 5.87) < 0.2
    assert all("score" in w for w in ws)


def test_english_parakeet():
    a = load_16k(str(ENGLISH))
    ws = align(a, transcribe(a, "en", str(MODELS)))     # Parakeet starts ~0.25 s early; alignment fixes it
    text = " ".join(w["w"] for w in ws).lower()
    assert "silence" in text and "final sentence" in text
    hello = [w for w in ws if w["w"].lower().strip(",.") == "hello"]
    assert hello and abs(hello[0]["s"] - 1.21) < 0.1
