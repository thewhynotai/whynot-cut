import numpy as np

import kalam.align as A


def test_window_with_unromanizable_words_keeps_transcriber_times(monkeypatch):
    vocab = {c: i + 4 for i, c in enumerate("abcdefghijklmnopqrstuvwxyz'")}
    vocab["<blank>"] = 0
    monkeypatch.setattr(A, "_load", lambda: (None, vocab, "cpu"))       # the model must not even be needed
    words = [{"w": "Привет", "s": 2.5, "e": 3.0}, {"w": "мир", "s": 4.5, "e": 5.0},
             {"w": "5", "s": 6.5, "e": 6.8}, {"w": "друзья", "s": 8.5, "e": 9.0}]
    out = A.align(np.zeros(16000 * 12, dtype=np.float32), words)
    assert [(w["s"], w["e"]) for w in out] == [(w["s"], w["e"]) for w in words]
    assert all(w["score"] == 0.5 for w in out)
