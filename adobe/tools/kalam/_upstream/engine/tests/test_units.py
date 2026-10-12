"""Meaning units: Claude marks where a sentence/clause ends with "|"; captions break there."""
from kalam.captions import fit_phrases, pack
from kalam.phrases import phrases
from kalam.units import apply_units

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from test_captions import W, seq  # noqa: E402


def test_apply_units_marks_breaks_after_enforcing_each_unit():
    p = {"text": "raw", "s": 0, "e": 1, "words": []}
    apply_units(p, "لو ما حدش شايف إن انت جامد، | حتى لو كنت بتقدم كل حاجة في معادها |", {}, "ar")
    assert p["text"] == "لو ما حدش شايف إن انت جامد حتى لو كنت بتقدم كل حاجة في معادها"
    assert p["unit_breaks"] == {7} and p["unit_end"] is True


def test_apply_units_line_that_continues():
    p = {"text": "raw", "s": 0, "e": 1, "words": []}
    apply_units(p, "لو ما حدش شايف", {}, "ar")
    assert p["unit_breaks"] == set() and p["unit_end"] is False


def test_apply_units_without_markers_from_a_fallback():
    p = {"text": "raw", "s": 0, "e": 1, "words": []}
    apply_units(p, None, {}, "ar")
    assert p["unit_end"] is None and p["unit_breaks"] == set() and p["text"] == "raw"


def test_fit_breaks_only_at_meaning_units_and_lets_a_unit_run_long():
    text = "مش هيرقيك لو ما حدش شايف إن انت جامد حتى لو كنت بتقدم كل حاجة في معادها"
    p = phrases(W(*seq(text, 0.0, step=0.25)), 0.22)[0]
    apply_units(p, "مش هيرقيك | لو ما حدش شايف إن انت جامد | حتى لو كنت بتقدم كل حاجة في معادها |", {}, "ar")
    parts = fit_phrases([p], max_line=32, max_lines=1)
    assert [x["text"] for x in parts] == ["مش هيرقيك", "لو ما حدش شايف إن انت جامد", "حتى لو كنت بتقدم كل حاجة في معادها"]


def test_pack_joins_a_line_that_continues_across_a_pause():
    a, b = seq("لو ما حدش شايف", 0.0), seq("إن انت جامد", 1.5)          # 0.32 s breath mid-sentence
    ps = phrases(W(*a, *b), 0.22)
    apply_units(ps[0], "لو ما حدش شايف", {}, "ar")
    apply_units(ps[1], "إن انت جامد |", {}, "ar")
    assert [c["text"] for c in pack(fit_phrases(ps, 32, 1), max_line=32, max_lines=1)] == ["لو ما حدش شايف إن انت جامد"]


def test_pack_keeps_complete_units_as_their_own_captions():
    a, b = seq("الشغل الجامد", 0.0), seq("مش هيرقيك", 1.0)
    ps = phrases(W(*a, *b), 0.22)
    apply_units(ps[0], "الشغل الجامد |", {}, "ar")
    apply_units(ps[1], "مش هيرقيك |", {}, "ar")
    assert [c["text"] for c in pack(fit_phrases(ps, 32, 1), max_line=32, max_lines=1)] == ["الشغل الجامد", "مش هيرقيك"]


def test_a_long_whole_unit_is_one_caption_never_none():
    p = phrases(W(*seq("حتى لو كنت بتقدم كل حاجة في معادها", 0.0)), 0.22)[0]
    apply_units(p, "حتى لو كنت بتقدم كل حاجة في معادها |", {}, "ar")
    caps = pack(fit_phrases([p], 32, 1), max_line=32, max_lines=1)
    assert [c["text"] for c in caps] == ["حتى لو كنت بتقدم كل حاجة في معادها"]


def test_a_line_that_continues_is_joined_before_splitting():
    from kalam.units import join_continuations
    a = seq("لأن", 9.05, step=0.3)
    b = seq("الترقية ما بتحصلش بس على أساس المجهود اللي انت حاطه النهارده", 9.68, step=0.25)
    ps = phrases(W(*a, *b), 0.22)
    apply_units(ps[0], "لأن", {}, "ar")
    apply_units(ps[1], "الترقية ما بتحصلش بس | على أساس المجهود اللي انت حاطه النهارده |", {}, "ar")
    joined = join_continuations(ps)
    assert len(joined) == 1 and joined[0]["s"] == 9.05 and joined[0]["unit_breaks"] == {5}
    caps = pack(fit_phrases(joined, 32, 1), max_line=32, max_lines=1)
    assert [c["text"] for c in caps] == ["لأن الترقية ما بتحصلش بس", "على أساس المجهود اللي انت حاطه النهارده"]


def test_no_one_letter_caption_when_it_can_join_a_neighbour():
    from kalam.units import join_continuations
    a = seq("ناس مقدرة ف", 26.0, step=0.4)
    b = seq("دي حاجات الإدارة بتكون حطاها في الاعتبار", a[-1][2] + 0.3, step=0.3)
    ps = phrases(W(*a, *b), 0.22)
    apply_units(ps[0], "ناس مقدرة | ف", {}, "ar")
    apply_units(ps[1], "دي حاجات الإدارة بتكون حطاها في الاعتبار |", {}, "ar")
    caps = pack(fit_phrases(join_continuations(ps), 32, 1), max_line=32, max_lines=1)
    assert all(len(c["text"]) > 3 for c in caps), [c["text"] for c in caps]
