import numpy as np

from kalam.clean import drop_hallucinations, drop_loops, drop_unspoken


def W(*items):
    return [{"w": w, "s": s, "e": e, "score": sc} for w, s, e, sc in items]


def env_with_speech(total_s, speech_spans, loud=-20.0, quiet=-90.0, hop=0.01):
    env = np.full(int(total_s / hop), quiet, dtype=np.float32)
    for a, b in speech_spans:
        env[int(a / hop):int(b / hop)] = loud
    return env


def test_drop_loops_removes_runs_of_the_same_word():
    ws = W(*[("exca", i * 0.2, i * 0.2 + 0.1, 0.5) for i in range(6)], ("تمام", 1.4, 1.6, 0.9))
    assert [w["w"] for w in drop_loops(ws, max_repeat=3)] == ["تمام"]


def test_drop_loops_keeps_natural_repeats():
    ws = W(("جدًا", 0, 0.3, 0.9), ("جدًا", 0.3, 0.6, 0.9), ("مهم", 0.6, 0.9, 0.9))
    assert len(drop_loops(ws, max_repeat=3)) == 3


def test_drop_unspoken_keeps_low_score_word_inside_speech():
    env = env_with_speech(10, [(1.0, 5.0)])
    ws = W(("نبتدي", 2.0, 2.4, 0.9), ("الأول", 4.9, 5.3, 0.01))   # half on speech, aligner unsure
    assert [w["w"] for w in drop_unspoken(ws, env)] == ["نبتدي", "الأول"]


def test_drop_unspoken_removes_words_on_silence_far_from_speech():
    env = env_with_speech(12, [(1.0, 5.0)])
    ws = W(("كلام", 2.0, 2.4, 0.9), ("ترجمة", 9.0, 9.4, 0.0), ("نانسي", 9.4, 9.8, 0.0))
    assert [w["w"] for w in drop_unspoken(ws, env)] == ["كلام"]


def test_drop_hallucinations_removes_known_credit_lines():
    ws = W(("كلام", 0, 0.4, 0.9), ("ترجمة", 1, 1.3, 0.9), ("نانسي", 1.3, 1.6, 0.9), ("قنقر", 1.6, 1.9, 0.9))
    assert [w["w"] for w in drop_hallucinations(ws)] == ["كلام"]


def test_nonspeech_tags_are_removed():
    from kalam.clean import drop_nonspeech_tags
    ws = W(("[موسيقى]", 0, 1, 0.9), ("كلام", 1, 1.4, 0.9), ("♪", 1.5, 1.6, 0.9), ("(Music)", 2, 3, 0.9),
           ("[تصفيق", 3, 3.5, 0.9), ("حار]", 3.5, 4, 0.9), ("مهم", 4.2, 4.6, 0.9))
    assert [w["w"] for w in drop_nonspeech_tags(ws)] == ["كلام", "مهم"]


def test_room_tone_with_little_speech_still_counts_as_silence():
    rng = np.random.default_rng(1)
    env = (-60 + rng.uniform(-3, 3, 6000)).astype(np.float32)          # 60 s room tone
    env[100:400] = -20                                                  # 3 s of speech
    ws = W(("كلام", 1.5, 2.0, 0.9), ("شكرا", 40.0, 40.4, 0.0), ("للمشاهدة", 40.4, 41.0, 0.0))
    assert [w["w"] for w in drop_unspoken(ws, env)] == ["كلام"]


def test_garbled_whisper_tokens_are_cleaned():
    from kalam.clean import clean_garbled
    ws = W(("وحيرقوك،", 65.98, 66.6, 0.66), ("غيرqub", 66.62, 68.22, 0.64), ("-", 68.22, 68.4, 0.5),
           ("g", 68.4, 68.42, 0.003), ("up,", 68.5, 68.96, 0.0), ("Soft", 70.0, 70.3, 0.6), ("Tissue", 70.3, 70.7, 0.5))
    out = clean_garbled(ws, mode="ar")
    assert [w["w"] for w in out] == ["وحيرقوك،", "غير", "Soft", "Tissue"]


def test_garbled_cleanup_keeps_english_speech_in_english_mode():
    from kalam.clean import clean_garbled
    ws = W(("we", 0, 0.2, 0.04), ("go", 0.2, 0.4, 0.03), ("up", 0.4, 0.6, 0.02))
    assert len(clean_garbled(ws, mode="en")) == 3
