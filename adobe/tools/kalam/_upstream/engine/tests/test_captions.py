from kalam.captions import pack, split_long, to_srt
from kalam.phrases import phrases


def W(*items):
    """W(("word", start, end), ...) -> word dicts"""
    return [{"w": w, "s": s, "e": e} for w, s, e in items]


def seq(text, start, step=0.3, gap=0.02):
    """consecutive words with tiny gaps (one spoken phrase)"""
    out, t = [], start
    for w in text.split():
        out.append((w, t, t + step - gap))
        t += step
    return out


def test_phrases_split_only_at_real_pauses():
    ws = W(*seq("Soft Tissue Injury", 1.0), *seq("انتو عارفين", 2.2))
    ps = phrases(ws, min_pause=0.22)
    assert [p["text"] for p in ps] == ["Soft Tissue Injury", "انتو عارفين"]
    assert ps[0]["s"] == 1.0 and abs(ps[0]["e"] - 1.88) < 1e-9


def test_captions_have_no_gaps_and_tail():
    ps = phrases(W(*seq("واحدة من المشاكل", 0.5), *seq("نبتدي من الأول", 3.0)), 0.22)
    caps = pack(ps)
    for a, b in zip(caps, caps[1:]):
        assert a["e"] == b["s"]
    assert caps[0]["s"] == 0.5
    assert abs(caps[-1]["e"] - (3.0 + 0.9 - 0.02 + 0.3)) < 1e-9


def test_stop_pause_always_ends_a_caption():
    ps = phrases(W(*seq("رقم ممتاز", 1.0), *seq("رقم كويس", 2.3)), 0.22)   # 0.72 s pause
    assert [c["text"] for c in pack(ps)] == ["رقم ممتاز", "رقم كويس"]


def test_short_phrases_join_until_full():
    ps = phrases(W(*seq("بصوا مثلًا", 1.0), *seq("الحالة دي", 1.9)), 0.22)       # 0.32 s pause
    assert [c["text"] for c in pack(ps)] == ["بصوا مثلًا الحالة دي"]


def test_never_more_than_two_lines_of_32():
    words = W(*seq("الكسر صغير قوي لكن فعلًا لو قلت للنايب ابعتلي صورة الـ Soft Tissue أو نزلت تبص", 0.0, step=0.25))
    caps = pack(split_long(phrases(words, 0.22)))
    for c in caps:
        lines = c["text"].split("\n")
        assert len(lines) <= 2
        assert all(len(l) <= 32 for l in lines)


def test_long_phrase_splits_at_biggest_internal_gap():
    a = seq("الـ Timing Of Fixation مهم جدًا", 0.0, gap=0.02)
    b = seq("وبعد كده طريقة الـ Fixation مهمة جدًا", a[-1][2] + 0.15, gap=0.02)   # 0.15 s: below min_pause
    parts = split_long(phrases(W(*a, *b), 0.22))
    assert [p["text"] for p in parts] == ["الـ Timing Of Fixation مهم جدًا", "وبعد كده طريقة الـ Fixation مهمة جدًا"]


def test_term_is_not_split_when_it_fits():
    ps = phrases(W(*seq("بنحط Spanning External Fixator", 0.0)), 0.22)
    assert [c["text"].replace("\n", " ") for c in pack(split_long(ps))] == ["بنحط Spanning External Fixator"]


def test_max_duration_ends_caption():
    ps = phrases(W(*seq("واحد", 0.0, step=2.0), *seq("اتنين", 2.3, step=2.0), *seq("تلاتة", 4.6, step=2.0)), 0.22)
    caps = pack(ps, max_dur=4.5)
    assert all(c["e"] - c["s"] <= 4.6 + 0.3 for c in caps) and len(caps) >= 2


def test_corrected_text_longer_than_two_lines_is_split_by_time():
    p = phrases(W(*seq("صفتشو انجري ده", 0.0)), 0.22)[0]
    p["text"] = "Soft Tissue Injury Associated With Broken Bone Zone Of Injury Example"   # grew after correction
    caps = pack([p])
    assert len(caps) == 2
    assert all(len(l) <= 32 for c in caps for l in c["text"].split("\n"))
    assert caps[0]["e"] == caps[1]["s"] and caps[0]["s"] == 0.0


def test_to_srt_format():
    srt = to_srt([{"s": 2.661, "e": 4.662, "text": "واحدة من المشاكل"}, {"s": 4.662, "e": 5.9, "text": "نبتدي"}])
    assert srt == "1\n00:00:02,661 --> 00:00:04,662\nواحدة من المشاكل\n\n2\n00:00:04,662 --> 00:00:05,900\nنبتدي\n"


def test_sentence_end_is_preferred_over_filling_the_caption():
    a = seq("نبتدي من الأول.", 0.0)
    b = seq("شباب جراحين العظام", a[-1][2] + 0.3)
    c = seq("قلنا إن واحدة من المشاكل", b[-1][2] + 0.25)
    caps = pack(split_long(phrases(W(*a, *b, *c), 0.22)))
    texts = [x["text"].replace("\n", " ") for x in caps]
    assert texts[0] == "نبتدي من الأول."
    assert any(t.endswith("قلنا إن واحدة من المشاكل") for t in texts)


def test_caption_never_ends_in_the_middle_of_a_short_sentence():
    a = seq("شباب جراحين العظام قلنا إن", 0.0)
    b = seq("واحدة من المشاكل اللي تعمل حاجة", a[-1][2] + 0.23)      # small breath inside one sentence
    caps = pack(split_long(phrases(W(*a, *b), 0.22)))
    assert [x["text"].replace("\n", " ") for x in caps] == ["شباب جراحين العظام قلنا إن واحدة من المشاكل اللي تعمل حاجة"] or \
        all(not x["text"].endswith("إن") for x in caps)


def test_wrap_keeps_latin_terms_on_one_line():
    from kalam.captions import wrap
    # the most balanced break would be "Soft\nTissue"; a term stays on one line when another break fits
    assert wrap("هي إن يبقى عندنا Soft Tissue Injury انتو عارفين") == "هي إن يبقى عندنا\nSoft Tissue Injury انتو عارفين"


def test_long_phrase_with_even_gaps_splits_after_sentence_end():
    ws = W(*seq("بصوا مثلًا الحالة دي لما يجيلك أشعة زي دي. الكسر صغير قوي لكن فعلًا لو قلت", 0.0, step=0.25))
    parts = split_long(phrases(ws, 0.22))
    assert parts[0]["text"].endswith("زي دي.")


# ---- fit_phrases: split (corrected) phrases to fit, at real word onsets, never inside a term ----
from kalam.captions import fit_phrases  # noqa: E402


def test_fit_one_line_never_splits_a_latin_term():
    raw = W(*seq("بصوا هنا الزون اوف إنجري عند العيان ده قد إيه", 37.4, step=0.24))
    p = phrases(raw, 0.22)[0]
    p["text"] = "بصوا هنا الـ Zone Of Injury عند العيان ده قد إيه"
    parts = fit_phrases([p], max_line=32, max_lines=1)
    texts = [x["text"] for x in parts]
    assert all(len(t) <= 32 for t in texts)
    assert not any(t.endswith("Zone Of") or t.startswith("Injury") or t.endswith("Zone") for t in texts), texts
    assert any("Zone Of Injury" in t for t in texts)


def test_fit_split_starts_on_a_real_word_onset():
    raw = W(("واحد", 0.0, 0.3), ("اتنين", 0.35, 0.7), ("تلاتة", 0.75, 1.1), ("اربعة", 3.0, 3.4), ("خمسة", 3.45, 3.8))
    p = phrases(raw, 5.0)[0]                                     # one phrase (slow speaker)
    p["text"] = "Soft Tissue Injury Associated With Broken Bone Zone"  # grew after correction
    parts = fit_phrases([p], max_line=32, max_lines=1)
    onsets = {w["s"] for w in raw}
    assert len(parts) >= 2 and all(x["s"] in onsets for x in parts)


def test_fit_unchanged_text_splits_at_biggest_pause():
    a = seq("الـ Timing Of Fixation مهم جدًا", 0.0)
    b = seq("وبعد كده طريقة الـ Fixation مهمة جدًا", a[-1][2] + 0.15)
    parts = fit_phrases(phrases(W(*a, *b), 0.22), max_line=32, max_lines=2)
    assert [x["text"] for x in parts] == ["الـ Timing Of Fixation مهم جدًا", "وبعد كده طريقة الـ Fixation مهمة جدًا"]
    assert parts[1]["s"] == b[0][1]


def test_fit_maps_corrected_words_to_the_right_raw_words():
    raw = W(*seq("المجهود اللي أنت حطه النهارده، حتى لأساس حاجات زي مثلا ال الربتيشن بتاعتك،", 0.0, step=0.3, gap=0.05))
    p = phrases(raw, 0.22)[0]
    p["text"] = "المجهود اللي انت حاطه النهارده حتى على أساس حاجات زي مثلًا الـ Reputation بتاعتك"
    parts = fit_phrases([p], max_line=32, max_lines=1)
    assert parts[0]["text"] == "المجهود اللي انت حاطه النهارده", [x["text"] for x in parts]
    assert parts[1]["s"] == raw[5]["s"]                      # "حتى" starts exactly when it is said
    assert not any(x["text"].endswith("الـ") for x in parts)
