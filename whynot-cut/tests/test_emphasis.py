"""Task 29 (R-4.7): emphasis punch-in candidates — scoring, phrases and spacing, face safety, collisions, output.

Cases: lane4\\work\\task29\\cases.md A1-A14, B15-B24, C25-C40, D41-D51, E52-E56, I85-I89 (F57-F63 are in
test_emphasis_plan.py, G64-G76 in test_emphasis_endings.py). Fixtures are synthetic (tests/fixtures/emphasis): faces are
injected (a face-samples document or a fake detector), audio levels are given or generated with numpy. Expected values
are computed here from closed forms, never read back from the module.
Run:  bash tools/test.sh -p test_emphasis.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import copy  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import shutil  # noqa: E402
import statistics  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
FX = SK / "tests" / "fixtures" / "emphasis"

from lib import common  # noqa: E402
from lib.common import Paths, write_json, read_json  # noqa: E402


def fx(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def ws(phrases, t0=0, word_ms=400, gap=80, phrase_gap=400, id0=1):
    """Word records: words of a phrase `gap` ms apart, phrases `phrase_gap` ms apart."""
    out, t, i = [], t0, id0
    for k, ph in enumerate(phrases):
        if k:
            t += phrase_gap - gap
        for w in ph.split():
            out.append({"id": i, "segment_id": 1, "word": w, "start_ms": t, "end_ms": t + word_ms, "probability": 0.9})
            t += word_ms + gap
            i += 1
    return out


def samples_doc(fn, t0=0, t1=40000, step=250, w=1080, h=1920):
    """A face-samples document: fn(t_ms) -> faces at each sample time (frame centres at 4 fps)."""
    return {"schema": 1, "video_id": "CLIP1", "footage": "data/Raw/CLIP1.mov", "range": {"in_ms": 0, "out_ms": t1},
            "display": {"w": w, "h": h}, "fps": 4, "detector": "injected", "notes": [],
            "samples": [{"t_ms": t, "faces": fn(t)} for t in range(t0 + step // 2, t1, step)]}


def E():
    from lib import emphasis
    return emphasis


def N():
    from lib import endings
    return endings


def inp(**over):
    """A build() input: the main Arabic clip, native 1080x1920 presenter, no audio, faces_916, nothing else on."""
    wj = fx("words_ar.json")
    base = {"video_id": "CLIP1", "words": copy.deepcopy(wj["words"]), "lang": "ar",
            "media_end_ms": wj["meta"]["duration_ms"], "levels": None, "audio_source": None,
            "remove_pauses": False, "pauses": None, "ed": {}, "proposals": None,
            "endings": N().config({}, {}), "marker_ms": None, "recipe": None, "terms": [], "statements": None,
            "speakers": {}, "frame": E().geometry(1080, 1920), "faces": {"status": "ok", "doc": fx("faces_916.json")},
            "verse": [], "ease_ms": 250, "fps": 30, "settings": E().settings(), "head": E().head_ratio(),
            "inputs_sha1": "t"}
    base.update(over)
    return base


def build(**over):
    return E().build(inp(**over))


def kept(doc):
    return [(c["start_ms"], c["end_ms"]) for c in doc["candidates"]]


def drop_codes(doc):
    return {tuple(d["word_ids"]): d["code"] for d in doc["dropped"]}


def head(face, top=0.45, bottom=0.15, side=0.20):
    cx, cy, w, h = face
    return [cx - w / 2 - side * w, cy - h / 2 - top * h, cx + w / 2 + side * w, cy + h / 2 + bottom * h]


def s_max_916(face, W=1080, H=1920, margin=0.06, cap=1.12):
    """Closed form for a native 9:16 picture (base scale 1, no offsets) with the zoom anchored on the head centre:
    each edge of the head box moves away from the anchor by the factor s; the anchor never needs more shift than the
    picture slack gives (|y - H/2| (s - 1) <= H (s - 1) / 2)."""
    x0, y0, x1, y1 = head(face)
    X0, Y0, X1, Y1 = x0 * W, y0 * H, x1 * W, y1 * H
    cx, cy = (X0 + X1) / 2, (Y0 + Y1) / 2
    mW, mH = margin * W, margin * H
    lim = [(cx - mW) / (cx - X0), (W - mW - cx) / (X1 - cx), (cy - mH) / (cy - Y0), (H - mH - cy) / (Y1 - cy)]
    return min([cap] + lim)


# ============================================================================== A. the score
class TestScore(unittest.TestCase):
    def tone_words(self, amps, sr=8000):
        """Words of 400 ms (gap 80 ms) each holding a 100 Hz sine of amplitude amps[i] (40 whole cycles: RMS = A/sqrt 2)."""
        import numpy as np
        words = ws([" ".join(f"w{i}" for i in range(len(amps)))])
        x = np.zeros(int((words[-1]["end_ms"] + 100) * sr / 1000))
        for w, a in zip(words, amps):
            i0, i1 = w["start_ms"] * sr // 1000, w["end_ms"] * sr // 1000
            t = np.arange(i1 - i0) / sr
            x[i0:i1] = a * np.sin(2 * np.pi * 100 * t)
        return words, x, sr

    @staticmethod
    def oracle_z(levels):
        out = []
        n = len(levels)
        for i in range(n):
            others = sorted((j for j in range(n) if j != i), key=lambda j: (abs(j - i), j))[:8]
            vals = [levels[j] for j in others]
            sd = statistics.pstdev(vals) if vals else 0.0
            out.append(0.0 if not vals or sd < 1e-9 else (levels[i] - statistics.fmean(vals)) / sd)
        return out

    def test_a01_loudness_term_hand_computed(self):
        amps = [0.1, 0.2, 0.15, 0.4, 0.1, 0.12, 0.3, 0.05, 0.2, 0.25, 0.1, 0.6, 0.1]
        words, x, sr = self.tone_words(amps)
        lv = E().word_levels(words, x, sr)
        want_db = [20 * math.log10(a / math.sqrt(2) + 1e-9) for a in amps]
        for got, want in zip(lv, want_db):
            self.assertAlmostEqual(got, want, places=6)
        z = E().loudness_z(lv)
        for got, want in zip(z, self.oracle_z(want_db)):
            self.assertAlmostEqual(got, want, places=6)
        sc = E().score_words(words, lv, set(), set(), set(), set(), E().settings()["values"])
        for s, zz in zip(sc, z):
            self.assertAlmostEqual(s["total"] - 0.2 * s["after_pause"], round(0.6 * zz, 4), places=3)

    def test_a02_neighbours_at_the_edges_and_short_clips(self):
        lv = [0.0, 10.0, 3.0, 7.0, 1.0, 9.0, 2.0, 8.0, 4.0, 6.0, 5.0, 11.0]
        for got, want in zip(E().loudness_z(lv), self.oracle_z(lv)):
            self.assertAlmostEqual(got, want, places=9)
        short = [1.0, 4.0, 2.0, 8.0]                       # fewer than 9 words: all the others
        for got, want in zip(E().loudness_z(short), self.oracle_z(short)):
            self.assertAlmostEqual(got, want, places=9)
        self.assertEqual(E().loudness_z([42.0]), [0.0])

    def test_a03_flat_audio_is_zero_never_nan(self):
        import numpy as np
        for lv in ([-20.0] * 12, E().word_levels(ws(["a b c d e f g h i j"]), np.zeros(80000), 8000)):
            z = E().loudness_z(lv)
            self.assertTrue(all(v == 0.0 and math.isfinite(v) for v in z), z)

    def test_a04_after_pause_boundary(self):
        w = [{"id": 1, "word": "a", "start_ms": 0, "end_ms": 400}, {"id": 2, "word": "b", "start_ms": 699, "end_ms": 900},
             {"id": 3, "word": "c", "start_ms": 1200, "end_ms": 1500}]
        self.assertEqual(E().after_pause(w, 300), [1, 0, 1])          # 299 ms -> 0, 300 ms -> 1, the first word -> 1
        sc = E().score_words(w, None, set(), set(), set(), set(), E().settings()["values"])
        self.assertEqual([s["total"] for s in sc], [0.2, 0.0, 0.2])

    def test_a05_spoken_numbers(self):
        def flagged(text):
            words = ws([text])
            return {words[i]["word"] for i in E().number_words(words)}
        self.assertEqual(flagged("قال ٣ حاجات"), {"٣"})
        self.assertEqual(flagged("خد 3.5 مجم"), {"3.5"})
        self.assertEqual(flagged("دفعت خمسمية جنيه"), {"خمسمية"})
        self.assertEqual(flagged("five hundred people"), {"five", "hundred"})
        self.assertEqual(flagged("الست دي قالتلي"), set())
        self.assertEqual(flagged("هي ست كويسة"), set())                # «ست» a lady: no unit next to it
        self.assertEqual(flagged("الراجل ده ميت خلاص"), set())          # «ميت» dead
        self.assertEqual(flagged("نمت ست ساعات"), {"ست"})

    def test_a06_client_terms(self):
        from lib.safety.lexicon import _folded
        terms = _folded(["أوزمبيك", "Ozempic"])
        words = ws(["كان بالأوزمبيك وأوزمبيك وأوزِمبيك واوزمبك OZEMPIC واوزون أوزة"])
        got = {words[i]["word"] for i in E().client_words(words, terms)}
        self.assertEqual(got, {"بالأوزمبيك", "وأوزمبيك", "وأوزِمبيك", "واوزمبك", "OZEMPIC"})
        short = ws(["الليزر ليزا ليزز"])                                   # a 4-letter term: no one-letter mishearing
        self.assertEqual({short[i]["word"] for i in E().client_words(short, _folded(["ليزر"]))}, {"الليزر"})

    def test_a07_cta_keyword_after_the_normaliser_and_off_per_video(self):
        doc = fx("profile_endings_all.json")["endings"]
        words = fx("words_ar.json")["words"]
        cfg = N().config(doc, {})
        kw, _ = N().cta_keyword(cfg, "ar")
        got = {words[i]["word"] for i in E().phrase_words(words, kw)}
        self.assertEqual(got, {"رِجيـم"})
        off = N().config(doc, {"cta": {"on": False}})
        self.assertEqual(N().cta_keyword(off, "ar"), (None, None))
        d1 = build(endings=cfg)
        d0 = build(endings=off)
        sc1 = {c["word"]: c["score"]["cta"] for c in d1["scored"]}
        sc0 = {c["word"]: c["score"]["cta"] for c in d0["scored"]}
        self.assertEqual(sc1["رِجيـم"], 0.2)
        self.assertEqual(sc0["رِجيـم"], 0.0)

    def test_a08_key_word_missing_and_wrong(self):
        words = fx("words_ar.json")["words"]
        st = [{"statement_id": "ST_001", "start": "00:00:04.960", "end": "00:00:07.760",
               "text": "أنا نزلت خمسمية جرام في الأسبوع", "key_word": "جرام"},
              {"statement_id": "ST_002", "start": "00:00:13.120", "end": "00:00:15.440", "text": "الست دي قالتلي سر مهم",
               "key_word": "دواء"}]
        ids, notes = E().key_words(words, st)
        self.assertEqual({words[i]["word"] for i in ids}, {"جرام"})
        self.assertTrue(any("ST_002" in n["en"] for n in notes), notes)
        ids, notes = E().key_words(words, [{"statement_id": "ST_001", "text": "x"}])
        self.assertEqual(ids, set())
        self.assertEqual(len(notes), 1)
        self.assertIn("key_word", notes[0]["en"])
        ids, notes = E().key_words(words, None)
        self.assertEqual(ids, set())
        self.assertEqual(len(notes), 1)

    def test_a09_boosts_stack_and_parts_are_stored(self):
        w = ws(["قال ٣ حاجات"])
        sc = E().score_words(w, None, {1}, {1}, set(), {1}, E().settings()["values"])
        self.assertEqual(sc[1]["number"], 0.3)
        self.assertEqual(sc[1]["key"], 0.3)
        self.assertEqual(sc[1]["client"], 0.2)
        self.assertAlmostEqual(sc[1]["total"], 0.8, places=9)
        for s in sc:
            self.assertAlmostEqual(s["total"], round(0.6 * s["loudness_z"] + 0.2 * s["after_pause"] + s["number"]
                                                     + s["client"] + s["cta"] + s["key"], 4), places=9)

    def test_a10_no_pitch_term(self):
        self.assertEqual(E().PARTS, ("loudness_z", "after_pause", "number", "client", "cta", "key"))
        sc = E().score_words(ws(["a b"]), None, set(), set(), set(), set(), E().settings()["values"])
        self.assertEqual(set(sc[0]), set(E().PARTS) | {"total"})

    def test_a10_the_r47_starting_values_and_their_override(self):
        d = E().DEFAULTS
        self.assertEqual((d["w_loud"], d["w_pause"], d["boost_number"], d["boost_client"], d["boost_cta"], d["boost_key"]),
                         (0.6, 0.2, 0.3, 0.2, 0.2, 0.3))
        self.assertEqual((d["pause_ms"], d["neighbours"], d["phrase_gap_ms"], d["min_len_ms"], d["max_len_ms"],
                          d["hook_ms"], d["tail_ms"]), (300, 8, 250, 1200, 4000, 1500, 1500))
        self.assertEqual((d["s_min"], d["s_cap"], d["margin"], d["gap_calm_s"], d["gap_energetic_s"], d["gap_default_s"],
                          d["sample_fps"]), (1.05, 1.12, 0.06, 6, 4, 6, 4))
        with mock.patch.object(common.Context, "config", lambda self, name: {"values": {
                "w_loud": {"value": 0.7, "basis": "measured on 40 reels"}, "margin": -1, "pause_ms": "x"}}
                if name == "emphasis.json" else {}):
            st = E().settings(common.Context())
        self.assertEqual((st["values"]["w_loud"], st["basis"]["w_loud"]), (0.7, "measured on 40 reels"))
        self.assertEqual((st["values"]["margin"], st["values"]["pause_ms"]), (0.06, 300))     # bad values keep the default
        self.assertIn("not measured", st["basis"]["margin"])

    def test_a11_no_audio_is_one_line_never_a_crash(self):
        doc = build(levels=None, audio_source=None)
        self.assertTrue(all(c["score"]["loudness_z"] == 0.0 for c in doc["scored"]))
        lines = [n for n in doc["notes"] if n["code"] == "no_audio"]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["ar"], "مفيش صوت متنضف، الترتيب بالكلام بس")

    def test_a12_mixed_arabic_and_english_on_one_scale(self):
        from lib.safety.lexicon import _folded
        wj = fx("words_mixed.json")
        doc = build(words=wj["words"], media_end_ms=wj["meta"]["duration_ms"], terms=_folded(["Ozempic", "أوزمبيك"]),
                    faces={"status": "missing", "doc": None})
        sc = {c["word"]: c["score"] for c in doc["scored"]}
        self.assertEqual(sc["Ozempic"]["client"], 0.2)
        self.assertEqual(sc["semaglutide"]["total"], sc["وال"]["total"])      # a Latin word is not penalised

    def test_a13_bad_word_records_are_skipped_and_listed(self):
        good = ws(["واحد اتنين تلاتة اربعة خمسة ستة"])
        bad = [{"id": 90, "word": "x"}, {"id": 91, "word": "y", "start_ms": 500, "end_ms": 500},
               {"id": 92, "word": 7, "start_ms": 600, "end_ms": 700},
               {"id": 93, "word": "z", "start_ms": 700, "end_ms": 800, "probability": float("nan")}, "junk"]
        words, skipped = E().clean_words(good + bad)
        self.assertEqual([w["id"] for w in words], [w["id"] for w in good])
        self.assertEqual(len(skipped), 5)
        doc = build(words=good + bad)
        self.assertEqual(len([n for n in doc["notes"] if n["code"] == "bad_words"]), 1)

    def test_a14_rounding_and_ties(self):
        w = ws(["كلام جميل", "جدا خالص"], phrase_gap=400)
        sc = E().score_words(w, [1.00001, 1.00002, 1.0, 1.0], set(), set(), set(), set(), E().settings()["values"])
        self.assertTrue(all(round(s["total"], 4) == s["total"] for s in sc))
        order = E().rank_order([{"score": {"total": 0.5}, "start_ms": 900, "word_ids": [3]},
                                {"score": {"total": 0.5}, "start_ms": 100, "word_ids": [9]},
                                {"score": {"total": 0.5}, "start_ms": 100, "word_ids": [2]},
                                {"score": {"total": 0.7}, "start_ms": 5000, "word_ids": [1]}])
        self.assertEqual([c["word_ids"][0] for c in order], [1, 2, 9, 3])


# ============================================================================== B. candidates, phrases, spacing
class TestCandidates(unittest.TestCase):
    def test_main_scenario_exact(self):
        """No audio, no endings, no recipe (6 s gap): the number phrases rank first; greedy by score keeps P3 (4.96 s),
        drops P5 (5.92 s after it), keeps P6 (13.12 s). P3 sits on the cy 0.30 face, P6 on the centred one."""
        doc = build()
        self.assertEqual(kept(doc), [(4960, 7760), (13120, 15440)])
        a, b = doc["candidates"]
        self.assertAlmostEqual(a["s_max"], math.floor(s_max_916([0.5, 0.30, 0.2, 0.23]) * 1e4) / 1e4, places=4)
        self.assertEqual(b["s_max"], 1.12)
        self.assertEqual((a["rank"], a["r"], b["rank"], b["r"]), (1, 1.0, 2, 0.0))
        self.assertEqual(a["scale"], a["s_max"])
        self.assertEqual(b["scale"], 1.05)
        self.assertEqual(a["word"], "خمسمية")
        codes = drop_codes(doc)
        self.assertEqual(codes[(22,)], "near")                         # «٣»: 5.92 s after a stronger punch
        self.assertEqual(codes[(1,)], "hook")

    def test_b15_phrase_breaks(self):
        w = [{"id": 1, "word": "a", "start_ms": 0, "end_ms": 400}, {"id": 2, "word": "b.", "start_ms": 649, "end_ms": 900},
             {"id": 3, "word": "c", "start_ms": 1000, "end_ms": 1400}, {"id": 4, "word": "d", "start_ms": 1650, "end_ms": 2000},
             {"id": 5, "word": "e", "start_ms": 2100, "end_ms": 2400}, {"id": 6, "word": "f", "start_ms": 2500, "end_ms": 2900}]
        turns = [{"start_ms": 0, "end_ms": 2450, "speaker": "host"}, {"start_ms": 2450, "end_ms": 9000, "speaker": "guest"}]
        # 249 ms gap: same phrase; after «b.»: sentence end; 250 ms gap: break; e|f: a speaker turn
        self.assertEqual(E().phrases(w, 250, turns), [(0, 1), (2, 2), (3, 4), (5, 5)])

    def test_b15_long_phrase_is_clamped_to_4s_short_one_extends_or_drops(self):
        long_ = ws(["كلام جميل جدا عن الأكل الصحي كل يوم في البيت"], t0=2000)    # 10 words, 4720 ms
        long_[1]["word"] = "١٠"                                     # the top word early in the phrase
        doc = build(words=long_, media_end_ms=20000, faces={"status": "missing", "doc": None})
        (c,) = doc["candidates"]
        self.assertEqual(c["start_ms"], 2000)
        self.assertLessEqual(c["end_ms"] - c["start_ms"], 4000)
        self.assertEqual(c["end_ms"], 2000 + 8 * 480 - 80)          # the last whole word inside 4 s
        late = ws(["كلام جميل جدا عن الأكل الصحي كل يوم في البيت ده كمان"], t0=2000)   # top word late: the punch
        late[8]["word"] = "١٠"                                                          # starts at it
        doc = build(words=late, media_end_ms=20000, faces={"status": "missing", "doc": None})
        (c,) = doc["candidates"]
        self.assertEqual(c["start_ms"], late[8]["start_ms"])
        # a 2-word phrase (880 ms) followed by more words in the same kept range: extended to 1.2 s and more
        short = ws(["٣ كيلو"], t0=3000) + ws(["كمان شوية"], t0=3880 + 100, id0=3)
        doc = build(words=short, media_end_ms=12000, faces={"status": "missing", "doc": None})
        (c,) = doc["candidates"]
        self.assertGreaterEqual(c["end_ms"] - c["start_ms"], 1200)
        alone = ws(["٣ كيلو"], t0=3000)
        doc = build(words=alone, media_end_ms=12000, faces={"status": "missing", "doc": None})
        self.assertEqual(doc["candidates"], [])
        self.assertEqual(drop_codes(doc)[(1,)], "short")

    def gap_words(self, second_at):
        a = ws(["٣ كيلو في الأسبوع"], t0=2000)
        b = ws(["كيلو ٥ في الشهر"], t0=second_at, id0=10)
        return a + b

    def test_b16_minimum_gap_exact_and_one_ms_less(self):
        doc = build(words=self.gap_words(8000), media_end_ms=20000, faces={"status": "missing", "doc": None})
        self.assertEqual([c["start_ms"] for c in doc["candidates"]], [2000, 8000])
        doc = build(words=self.gap_words(7999), media_end_ms=20000, faces={"status": "missing", "doc": None})
        self.assertEqual([c["start_ms"] for c in doc["candidates"]], [2000])
        d = next(x for x in doc["dropped"] if x["word_ids"] == [11])
        self.assertEqual((d["code"], d["why"]), ("near", "قريب من punch أقوى"))

    def test_b16_energetic_types_use_4s(self):
        from lib.recipes import resolve
        self.assertEqual(E().min_gap_ms(resolve("advice"), E().settings()["values"]), 4000)
        self.assertEqual(E().min_gap_ms(resolve("comedy"), E().settings()["values"]), 4000)
        self.assertEqual(E().min_gap_ms(resolve("drama"), E().settings()["values"]), 6000)
        self.assertEqual(E().min_gap_ms(None, E().settings()["values"]), 6000)

    def test_b17_greedy_by_score_not_by_time_and_repeatable(self):
        w = ws(["كلام جميل جدا خالص"], t0=2000) + ws(["كيلو ٥ في الشهر"], t0=6000, id0=10) + \
            ws(["كلام جميل جدا خالص"], t0=10000, id0=20)
        a = build(words=w, media_end_ms=20000, faces={"status": "missing", "doc": None})
        b = build(words=copy.deepcopy(w), media_end_ms=20000, faces={"status": "missing", "doc": None})
        self.assertEqual([c["start_ms"] for c in a["candidates"]], [6000])        # by time it would keep 2 s and 10 s
        self.assertEqual(json.dumps(a, sort_keys=True, ensure_ascii=False),
                         json.dumps(b, sort_keys=True, ensure_ascii=False))

    def test_b18_recipe_quota(self):
        from lib.recipes import resolve
        w = []
        for k in range(6):                                      # strong candidates every 5 s (gap 4 s allows all)
            w += ws(["كيلو ٥ في الشهر"], t0=2000 + k * 5000, id0=1 + k * 10)
        doc = build(words=w, media_end_ms=40000, recipe=resolve("advice"), faces={"status": "missing", "doc": None})
        starts = [c["start_ms"] for c in doc["candidates"]]
        for s in starts:
            self.assertLessEqual(sum(1 for t in starts if s <= t < s + 30000), 2)
        q = [d for d in doc["dropped"] if d["code"] == "quota"]
        self.assertTrue(q)
        self.assertEqual(q[0]["why"], "حد الـ recipe")

    def test_b19_hook_on_the_sequence_clock_and_the_hook_title(self):
        w = ws(["٣ كيلو في الأسبوع"], t0=1600) + ws(["٥ كيلو في الشهر"], t0=9000, id0=10)
        # pauses removed: 0-1000 kept, 1000-1500 removed, so 1600 source is 1100 on the sequence: inside the hook
        doc = build(words=w, media_end_ms=20000, remove_pauses=True,
                    pauses={"keep_ms": [[0, 1000], [1500, 20000]], "cuts_ms": [[1000, 1500]]},
                    faces={"status": "missing", "doc": None})
        self.assertEqual([c["start_ms"] for c in doc["candidates"]], [9000])
        self.assertEqual(drop_codes(doc)[(1,)], "hook")
        ed = {"decisions": [{"decision_id": "EDIT_002", "start": "00:00:08.500", "end": "00:00:11.000",
                             "graphics": [{"id": "GFX_1", "template": "hook_title", "text": "x",
                                           "start": "00:00:08.500", "end": "00:00:11.000"}]}]}
        doc = build(words=w, media_end_ms=20000, ed=ed, faces={"status": "missing", "doc": None})
        self.assertEqual([c["start_ms"] for c in doc["candidates"]], [1600])
        self.assertEqual(drop_codes(doc)[(10,)], "hook")

    def test_b20_clip_start(self):
        early = ws(["٣ كيلو في الأسبوع"], t0=0)
        early[0]["start_ms"], early[0]["end_ms"] = 400, 700
        doc = build(words=early[:1] + ws(["كمان وكمان"], t0=800, id0=5), media_end_ms=9000,
                    faces={"status": "missing", "doc": None})
        self.assertEqual(drop_codes(doc).get((1,)), "hook")
        exact = ws(["٣ كيلو في الأسبوع"], t0=1500)
        doc = build(words=exact, media_end_ms=9000, faces={"status": "missing", "doc": None})
        self.assertEqual([c["start_ms"] for c in doc["candidates"]], [1500])
        # the top word after 1.5 s in a phrase that starts before it: the punch starts at the first word after the hook
        mid = ws(["في الأسبوع ٣ كيلو كمان وكمان"], t0=1000)
        doc = build(words=mid, media_end_ms=9000, faces={"status": "missing", "doc": None})
        (c,) = doc["candidates"]
        self.assertEqual(c["start_ms"], 1960)

    def test_b21_clip_end_with_a_sign_off_and_with_endings_off(self):
        words = fx("words_ar.json")["words"]
        cfg = N().config(fx("profile_endings_all.json")["endings"], {})
        doc = build(endings=cfg, marker_ms=19500)
        for c in doc["candidates"]:
            self.assertLessEqual(c["end_ms"], 19500)
        self.assertEqual(drop_codes(doc)[(35,)], "ending")         # P8 cut back to 880 ms
        doc = build()                                                    # endings off: the last 1.5 s
        for c in doc["candidates"]:
            self.assertLessEqual(c["end_ms"], 22000 - 1500)
        self.assertEqual(drop_codes(doc)[(38,)], "ending")
        self.assertTrue(words)

    def test_b22_short_clip_empty_is_valid(self):
        doc = build(words=ws(["قصير جدا"], t0=0), media_end_ms=3000, faces={"status": "missing", "doc": None})
        self.assertEqual(doc["candidates"], [])
        self.assertIn("none", [n["code"] for n in doc["notes"]])

    def test_b23_rank_ratio(self):
        self.assertEqual(E().rank_ratios([0.9]), [(1, 1.0)])
        self.assertEqual(E().rank_ratios([0.9, 0.5, 0.5, 0.1]), [(1, 1.0), (2, 0.5), (2, 0.5), (3, 0.0)])
        self.assertEqual(E().scale_for(1.1, 1.0), 1.1)
        self.assertEqual(E().scale_for(1.1, 0.0), 1.05)
        self.assertEqual(E().scale_for(1.1, 0.5), 1.075)

    def test_b24_scale_cap(self):
        from lib.recipes import resolve
        v = E().settings()["values"]
        self.assertEqual(E().cap_for(resolve("emotional"), v), 1.10)
        self.assertEqual(E().cap_for(resolve("comedy"), v), 1.12)
        self.assertEqual(E().cap_for(None, v), 1.12)
        doc = build(recipe=resolve("drama"))
        for c in doc["candidates"]:
            self.assertLessEqual(c["scale"], resolve("drama")["camera"]["max_scale"])
            self.assertLessEqual(c["scale"], 1.12)
        emo = build(recipe=resolve("emotional"))
        self.assertEqual(emo["candidates"], [])
        self.assertIn("النوع ده زوم بطيء بس", [n["ar"] for n in emo["notes"]])


# ============================================================================== C. face safety
class TestFaceSafety(unittest.TestCase):
    def one(self, faces_fn, words=None, frame=None, **kw):
        w = words or ws(["٣ كيلو في الأسبوع ده"], t0=3000)
        doc = build(words=w, media_end_ms=12000, frame=frame or E().geometry(1080, 1920),
                    faces={"status": "ok", "doc": samples_doc(faces_fn, t1=12000)}, **kw)
        return doc

    def test_c25_head_box_ratio_echoed(self):
        h = E().head_ratio()
        self.assertEqual(h["value"], {"top": 0.45, "bottom": 0.15, "side": 0.20})
        self.assertIn("not measured", h["basis"])
        doc = build()
        self.assertEqual(doc["head_from_face"], h)
        self.assertEqual(E().head_box([0.5, 0.4, 0.2, 0.2], h["value"]), head([0.5, 0.4, 0.2, 0.2]))

    def test_c26_margin_boundary(self):
        face = [0.5, 0.30, 0.2, 0.23]
        want = s_max_916(face)
        fr = E().geometry(1080, 1920)
        env = head(face)
        ok = lambda s: E().evaluate(fr, env, 5000, s, 0.06)["ok"]   # noqa: E731
        self.assertTrue(ok(want - 0.001))
        self.assertFalse(ok(want + 0.001))
        got = E().s_max(fr, env, 5000, 1.12, 0.06)["s_max"]
        self.assertAlmostEqual(got, want, delta=2e-4)
        self.assertLessEqual(got, want)

    def test_c26_s_max_never_above_the_cap(self):
        face = [0.5, 0.30, 0.2, 0.2275]                 # closed form ~1.131: just above the cap
        self.assertGreater(s_max_916(face, cap=2.0), 1.12)
        self.assertLess(s_max_916(face, cap=2.0), 1.14)
        self.assertEqual(E().s_max(E().geometry(1080, 1920), head(face), 5000, 1.12, 0.06)["s_max"], 1.12)
        doc = self.one(lambda t: [face])
        self.assertEqual(doc["candidates"][0]["s_max"], 1.12)

    def test_c27_union_of_samples_not_the_median(self):
        def drift(t):                    # the face rises 80 px (0.0417 of 1920) in the middle of the punch
            return [[0.5, 0.335 if t < 4000 else 0.335 - 0.0417, 0.2, 0.23]]
        doc = self.one(drift)
        (c,) = doc["candidates"]
        still = s_max_916([0.5, 0.335 - 0.0417 / 2, 0.2, 0.23])         # the median face
        self.assertLess(c["s_max"], still)
        lo = head([0.5, 0.335 - 0.0417, 0.2, 0.23])
        hi = head([0.5, 0.335, 0.2, 0.23])
        env = [min(lo[0], hi[0]), min(lo[1], hi[1]), max(lo[2], hi[2]), max(lo[3], hi[3])]
        self.assertAlmostEqual(c["s_max"], E().s_max(E().geometry(1080, 1920), env, 3000, 1.12, 0.06)["s_max"], places=4)

    def test_c28_the_three_named_moments(self):
        doc = self.one(lambda t: [[0.5, 0.42, 0.2, 0.23]])
        (c,) = doc["candidates"]
        for t in (c["start_ms"], (c["start_ms"] + c["end_ms"]) // 2, c["end_ms"]):
            self.assertTrue(any(abs(u - t) <= 125 for u in c["faces_used"]), (t, c["faces_used"]))
        sparse = samples_doc(lambda t: [[0.5, 0.42, 0.2, 0.23]], t1=12000, step=1000)
        d = build(words=ws(["٣ كيلو في الأسبوع ده"], t0=3000), media_end_ms=12000, faces={"status": "ok", "doc": sparse})
        (c,) = d["candidates"]
        self.assertIn("أقرب عينة على بعد", c["reason"])

    def test_c29_face_anchored_offset_and_clamp(self):
        fr = E().geometry(1080, 1920)
        env = head([0.5, 0.30, 0.2, 0.23])
        ev = E().evaluate(fr, env, 5000, 1.08, 0.06)
        yc = (env[1] + env[3]) / 2 * 1920
        self.assertAlmostEqual(ev["offset_y"], (yc - 960) * (1 - 1.08), places=2)
        self.assertAlmostEqual(ev["offset_x"], 0.0, places=2)
        # a 16:9 source in a 9:16 frame cover-scaled: the face far right, the horizontal shift clamps at the slack
        fr2 = E().geometry(1920, 1080, S=1920 / 1080, box=-800.0)
        env2 = head([0.97, 0.40, 0.05, 0.09])
        ev2 = E().evaluate(fr2, env2, 5000, 1.1, 0.0)
        P = 1920 / 1080 * 1.1
        slack = (1920 * P - 1080) / 2
        self.assertLessEqual(abs(-800.0 + ev2["offset_x"]), slack + 0.01)

    def test_c30_kept_punches_cover_the_frame(self):
        doc = build()
        fr = E().geometry(1080, 1920)
        for c in doc["candidates"]:
            P, cx, cy = E().compose(fr, c["start_ms"], c["scale"], c["offset_x"], c["offset_y"])
            self.assertLessEqual(cx - 1080 * P / 2, 0.0 + 1e-6)
            self.assertGreaterEqual(cx + 1080 * P / 2, 1080 - 1e-6)
            self.assertLessEqual(cy - 1920 * P / 2, 0.0 + 1e-6)
            self.assertGreaterEqual(cy + 1920 * P / 2, 1920 - 1e-6)

    def test_c31_near_the_top_at_9_16(self):
        doc = self.one(lambda t: [[0.5, 0.30, 0.2, 0.23]])
        (c,) = doc["candidates"]
        self.assertLess(c["s_max"], 1.12)
        self.assertAlmostEqual(c["s_max"], s_max_916([0.5, 0.30, 0.2, 0.23]), delta=2e-4)
        doc = self.one(lambda t: [[0.5, 0.20, 0.2, 0.23]])
        self.assertEqual(doc["candidates"], [])
        d = doc["dropped"][0]
        self.assertEqual((d["code"], d["why"]), ("edge", "الوش قريب من طرف الكادر"))

    def test_c32_the_4_5_window_is_the_boundary(self):
        from lib.plan import window_rect
        win = window_rect("4:5", None, 1080, 1920)                     # 1080x1350 at y 285
        self.assertEqual((win["h"], win["y"]), (1350, 285))
        # head top 20 px under the window top: face h 0.1 -> head top = cy - 0.05 - 0.045
        cy = (285 + 20) / 1920 + 0.095
        f = lambda t: [[0.5, cy, 0.15, 0.1]]                           # noqa: E731
        doc = self.one(f, frame=E().geometry(1080, 1920, window=win))
        self.assertEqual(doc["candidates"], [])
        self.assertEqual(doc["dropped"][0]["code"], "edge")
        doc = self.one(f)                                              # the same face in 9:16 framing
        self.assertEqual(len(doc["candidates"]), 1)

    def test_c33_close_up(self):
        doc = self.one(lambda t: [[0.5, 0.45, 0.8, 0.75]])
        self.assertEqual(doc["candidates"], [])
        d = doc["dropped"][0]
        self.assertEqual((d["code"], d["why"]), ("closeup", "لقطة قريبة أصلاً"))

    def test_c34_two_faces_that_fit_together(self):
        a, b = [0.35, 0.42, 0.15, 0.12], [0.65, 0.30, 0.15, 0.12]
        doc = self.one(lambda t: [a, b])
        (c,) = doc["candidates"]
        ha, hb = head(a), head(b)
        env = [min(ha[0], hb[0]), min(ha[1], hb[1]), max(ha[2], hb[2]), max(ha[3], hb[3])]
        self.assertAlmostEqual(c["s_max"], E().s_max(E().geometry(1080, 1920), env, 3000, 1.12, 0.06)["s_max"], places=4)
        self.assertLessEqual(c["s_max"], min(self.one(lambda t: [a])["candidates"][0]["s_max"],
                                             self.one(lambda t: [b])["candidates"][0]["s_max"]))

    def podcast_frame(self, shots, speakers=None):
        from lib.shots import frame_shots
        layer = frame_shots(shots, speakers, 1920, 1080)
        return E().geometry(1920, 1080, S=1920 / 1080, layer=layer)

    def test_c35_speaker_follow_wide_shot(self):
        sp = fx("speakers_follow.json")
        shots = [{"start_ms": 0, "end_ms": 20000, "faces": [[0.25, 0.4, 0.1, 0.18], [0.75, 0.4, 0.1, 0.18]], "n_faces": 2}]
        fr = self.podcast_frame(shots, sp)
        # the guest speaks from 9 s: the crop follows the right face; the left face is half out at the crop edge?
        # no: 0.25 is far out of a 1080-wide crop centred on 0.75 -> not protected
        w = ws(["٣ كيلو في الأسبوع ده"], t0=11000)
        only = build(words=w, media_end_ms=20000, frame=fr, speakers=sp,
                     faces={"status": "ok", "doc": samples_doc(lambda t: [[0.75, 0.4, 0.1, 0.18]], t1=20000)})
        both = build(words=w, media_end_ms=20000, frame=fr, speakers=sp,
                     faces={"status": "ok", "doc": samples_doc(lambda t: [[0.25, 0.4, 0.1, 0.18],
                                                                          [0.75, 0.4, 0.1, 0.18]], t1=20000)})
        self.assertEqual(only["candidates"][0]["s_max"], both["candidates"][0]["s_max"])
        # a second face fully inside the crop does veto: it is protected too
        near = build(words=w, media_end_ms=20000, frame=fr, speakers=sp,
                     faces={"status": "ok", "doc": samples_doc(lambda t: [[0.66, 0.4, 0.1, 0.18],
                                                                          [0.75, 0.4, 0.1, 0.18]], t1=20000)})
        self.assertLess(near["candidates"][0]["s_max"] if near["candidates"] else 0.0, only["candidates"][0]["s_max"])
        # half visible (>= 50 % inside) is protected, less is not
        P0, cx0, _ = E().compose(fr, 11000, 1.0, 0.0, 0.0)
        self.assertTrue(E().visible_share(fr, [0.75, 0.4, 0.1, 0.18], P0, cx0, 960.0) > 0.99)

    def test_c36_no_face_presenter_needs_review_centred(self):
        doc = build(faces={"status": "ok", "doc": fx("faces_none.json")})
        self.assertTrue(doc["candidates"])
        for c in doc["candidates"]:
            self.assertEqual((c["scale"], c["needs_review"], c["default_keep"]), (1.05, True, False))
            self.assertEqual((c["offset_x"], c["offset_y"]), (0.0, 0.0))
            self.assertIn("مفيش وش متقاس هنا، راجعها بنفسك", c["reason"])
            self.assertIsNone(c["s_max"])

    def test_c37_detector_off_one_note(self):
        doc = build(faces={"status": "ok", "doc": fx("faces_model_off.json")})
        self.assertTrue(all(c["needs_review"] for c in doc["candidates"]))
        off = [n for n in doc["notes"] if n["code"] == "face_model_off"]
        self.assertEqual(len(off), 1)
        self.assertIn("reel doctor", off[0]["en"])
        self.assertTrue(all("reel doctor" not in c["reason_en"] for c in doc["candidates"]))

    def test_c38_no_samples_file(self):
        doc = build(faces={"status": "missing", "doc": None})
        self.assertTrue(doc["candidates"])
        for c in doc["candidates"]:
            self.assertTrue(c["needs_review"])
            self.assertIn("شغّل reel emphasis --faces", c["reason"])

    def test_c39_sampler_coordinates_are_in_source_units(self):
        """The sampler decodes at the source's own aspect (no pad): a face drawn at source cx 0.5 reads 0.5 for 9:16,
        4:3 and 21:9 sources (a 640x360 padded decode would read 0.5 only for 16:9)."""
        from PIL import Image
        for dw, dh in ((1080, 1920), (1440, 1080), (2560, 1080)):
            W, H = E().decode_size(dw, dh)
            self.assertAlmostEqual(W / H, dw / dh, delta=0.02)
            self.assertEqual((W % 2, H % 2), (0, 0))

            def decode(argv, W=W, H=H):
                im = Image.new("RGB", (W, H))
                return [im.tobytes()], ""

            def faces_fn(im):
                return [(0.5, 0.25, 0.1, 0.1)] if im.size == (W, H) else []
            doc = E().sample_faces("x.mp4", 0, 250, dw, dh, faces_fn=faces_fn, decode=decode)
            self.assertEqual(doc["samples"][0]["faces"], [[0.5, 0.25, 0.1, 0.1]])
            self.assertEqual(doc["display"], {"w": dw, "h": dh})

    def test_c40_rotation_uses_the_display_size(self):
        pre = {"files": [{"path": "data/Raw/P.mov", "name": "P.mov",
                          "video": {"width": 1920, "height": 1080, "display_width": 1080, "display_height": 1920,
                                    "rotation": 90}}]}
        fr = E().geometry_from(pre, "data/Raw/P.mov", {}, {}, (1080, 1920), {}, {})
        self.assertEqual((fr["dw"], fr["dh"]), (1080, 1920))
        seen = []

        def decode(argv):
            seen.append(argv)
            return [], ""
        E().sample_faces("P.mov", 0, 1000, fr["dw"], fr["dh"], faces_fn=lambda im: [], decode=decode)
        vf = seen[0][seen[0].index("-vf") + 1]
        W, H = E().decode_size(1080, 1920)
        self.assertIn(f"scale={W}:{H}", vf)
        self.assertLess(W, H)


# ============================================================================== D. collisions
class TestCollisions(unittest.TestCase):
    def test_d41_source_cutaway(self):
        r02 = fx("podcast_r02.json")
        from lib.shots import frame_shots
        fr = E().geometry(1920, 1080, S=1920 / 1080, layer=frame_shots(r02["shots"]["shots"], None, 1920, 1080))
        w = []
        for k, t in enumerate(range(2000, 33000, 3000)):
            w += ws(["٣ كيلو في الأسبوع"], t0=t, id0=1 + 10 * k)
        doc = build(words=w, media_end_ms=33700, frame=fr, faces={"status": "ok", "doc": r02["samples"]})
        for c in doc["candidates"]:
            self.assertFalse(c["start_ms"] < 28500 and 15800 < c["end_ms"], c)
        self.assertIn("cutaway", {d["code"] for d in doc["dropped"]})
        # a single-camera source cutaway (preflight reframe cutaways_ms)
        fr1 = E().geometry(1080, 1920, cutaways=[(4000, 8000)])
        doc = build(frame=fr1)
        for c in doc["candidates"]:
            self.assertFalse(c["start_ms"] < 8000 and 4000 < c["end_ms"])

    def ed_with(self, template, a="00:00:05.000", b="00:00:06.000", **g):
        return {"decisions": [{"decision_id": "EDIT_001", "start": a, "end": b,
                               "graphics": [dict({"id": "GFX_1", "template": template, "text": "x", "start": a, "end": b}, **g)]}]}

    def test_d42_full_screen(self):
        from lib.qc import FULL_SCREEN
        for t in sorted(FULL_SCREEN):
            doc = build(ed=self.ed_with(t))
            self.assertNotIn(4960, [c["start_ms"] for c in doc["candidates"]], t)
            self.assertEqual(drop_codes(doc)[(12,)], "full_screen", t)
            self.assertEqual(next(d for d in doc["dropped"] if d["word_ids"] == [12])["why"], "تحت كارت full-screen")

    def test_d43_overlays_warn_never_drop(self):
        for t in ("name_card", "statement_highlight", "glass_card"):
            doc = build(ed=self.ed_with(t), faces={"status": "ok",
                                                   "doc": samples_doc(lambda t_: [[0.5, 0.62, 0.3, 0.3]], t1=22000)})
            c = next(c for c in doc["candidates"] if c["start_ms"] == 4960)
            self.assertTrue(any(w["code"] == "overlay_face" for w in c["warnings"]), (t, c["warnings"]))

    def test_d44_captions_never_block(self):
        ed = {"caption_highlights": [{"text": "خمسمية", "at": "00:00:05.920"}]}
        self.assertEqual(kept(build(ed=ed)), kept(build()))

    def test_d45_accepted_cut_words(self):
        doc = build(ed={"global": {"cut_words": [12]}})
        self.assertEqual(drop_codes(doc).get((12,)), "cut_word")
        doc = build(ed={"global": {"cut_words": [14]}})               # «في» inside P3: the punch stays in one kept range
        c = next(c for c in doc["candidates"] if c["word"] == "خمسمية")
        self.assertLessEqual(c["end_ms"], 6880)

    def test_d46_cut_proposals(self):
        pre = [{"id": "CP-001", "kind": "filler", "start_ms": 5900, "end_ms": 6340, "word_ids": [12], "default": "proposed"}]
        doc = build(proposals=pre)
        d = next(x for x in doc["dropped"] if 12 in x["word_ids"])
        self.assertEqual((d["code"], d["why"]), ("proposed", "مقترح للقص"))
        un = [dict(pre[0], default="keep")]
        doc = build(proposals=un)
        c = next(c for c in doc["candidates"] if c["word"] == "خمسمية")
        self.assertTrue(any(w["code"] == "unticked_proposal" for w in c["warnings"]))
        self.assertEqual(kept(build(proposals=None)), kept(build()))

    def test_d47_a_pause_cut_shortens_the_span(self):
        from lib.timemap import TimeMap
        keep = [[0, 6400], [6800, 22000]]                              # the pause 6400-6800 inside P3 is removed
        doc = build(remove_pauses=True, pauses={"keep_ms": keep, "cuts_ms": [[6400, 6800]]})
        c = next(c for c in doc["candidates"] if c["word"] == "خمسمية")
        self.assertLessEqual(c["end_ms"], 6400)
        with common.use_context(common.Context()):
            whole = TimeMap(keep, [{"decision_id": "EMP", "type": "punch_in", "at_ms": 4960, "until_ms": 7760,
                                    "scale_factor": 1.11}])
            self.assertIn(1.17, [p["scale_factor"] for p in whole.pieces])        # the mask step past the cap
            ours = TimeMap(keep, [{"decision_id": "EMP", "type": "punch_in", "at_ms": c["start_ms"],
                                   "until_ms": c["end_ms"], "scale_factor": 1.11}])
            self.assertEqual({p["scale_factor"] for p in ours.pieces if p["decision_id"] == "EMP"}, {1.11})

    def test_d48_existing_story_camera_moves(self):
        for t in ("punch_in", "slow_push", "reframe", "punch_out"):
            ed = {"decisions": [{"decision_id": "EDIT_002", "start": "00:00:05.260", "end": "00:00:08.400",
                                 "camera": {"type": t, "at": "00:00:05.260", "until": "00:00:08.400"}}]}
            doc = build(ed=ed)
            self.assertNotIn("خمسمية", [c["word"] for c in doc["candidates"]], t)
            self.assertEqual(drop_codes(doc)[(12,)], "camera")
        ours = {"decisions": [{"decision_id": "EMPH_01", "start": "00:00:04.960", "end": "00:00:07.760",
                               "camera": {"type": "punch_in", "at": "00:00:04.960", "until": "00:00:07.760",
                                          "emphasis": {"candidate": "EMP_01"}}}]}
        self.assertEqual(kept(build(ed=ours)), kept(build()))          # a kept emphasis punch never blocks itself

    def test_d49_shot_change_inside_the_span(self):
        from lib.shots import frame_shots
        shots = [{"start_ms": 0, "end_ms": 6500, "faces": [[0.5, 0.4, 0.1, 0.18]], "n_faces": 1},
                 {"start_ms": 6500, "end_ms": 22000, "faces": [[0.3, 0.4, 0.1, 0.18]], "n_faces": 1}]
        fr = E().geometry(1920, 1080, S=1920 / 1080, layer=frame_shots(shots, None, 1920, 1080))
        sd = samples_doc(lambda t: [[0.5, 0.4, 0.1, 0.18]] if t < 6500 else [[0.3, 0.4, 0.1, 0.18]], t1=22000,
                         w=1920, h=1080)
        doc = build(frame=fr, faces={"status": "ok", "doc": sd})
        c = next(c for c in doc["candidates"] if c["word"] == "خمسمية")
        self.assertLessEqual(c["end_ms"], 6500)

    def test_d49_a_top_word_across_a_shot_change_is_dropped(self):
        from lib.shots import frame_shots
        shots = [{"start_ms": 0, "end_ms": 6100, "faces": [[0.5, 0.4, 0.1, 0.18]], "n_faces": 1},
                 {"start_ms": 6100, "end_ms": 22000, "faces": [[0.3, 0.4, 0.1, 0.18]], "n_faces": 1}]
        fr = E().geometry(1920, 1080, S=1920 / 1080, layer=frame_shots(shots, None, 1920, 1080))
        sd = samples_doc(lambda t: [[0.5, 0.4, 0.1, 0.18]] if t < 6100 else [[0.3, 0.4, 0.1, 0.18]], t1=22000,
                         w=1920, h=1080)
        doc = build(frame=fr, faces={"status": "ok", "doc": sd})          # «خمسمية» 5920-6320 crosses 6100
        self.assertEqual(drop_codes(doc)[(12,)], "shot")

    def test_f59_hard_sides_at_a_shot_change_and_next_to_a_story_move(self):
        from lib.shots import frame_shots
        shots = [{"start_ms": 0, "end_ms": 4960, "faces": [[0.5, 0.4, 0.1, 0.18]], "n_faces": 1},
                 {"start_ms": 4960, "end_ms": 22000, "faces": [[0.3, 0.4, 0.1, 0.18]], "n_faces": 1}]
        fr = E().geometry(1920, 1080, S=1920 / 1080, layer=frame_shots(shots, None, 1920, 1080))
        sd = samples_doc(lambda t: [[0.5, 0.4, 0.1, 0.18]] if t < 4960 else [[0.3, 0.4, 0.1, 0.18]], t1=22000,
                         w=1920, h=1080)
        doc = build(frame=fr, faces={"status": "ok", "doc": sd})
        c = next(c for c in doc["candidates"] if c["start_ms"] == 4960)
        self.assertEqual((c["ease"]["in"], c["ease"]["out"]), ("hard: at another shot", "eased"))
        self.assertIn("الدخول حاد لأنه على لقطة تانية", c["reason"])
        ed = {"decisions": [{"decision_id": "EDIT_002", "start": "00:00:07.760", "end": "00:00:08.100",
                             "camera": {"type": "reframe", "at": "00:00:07.760", "until": "00:00:08.100"}}]}
        doc = build(ed=ed)
        c = next(c for c in doc["candidates"] if c["word"] == "خمسمية")
        self.assertEqual((c["ease"]["in"], c["ease"]["out"]), ("eased", "hard: next to another camera move"))

    def test_d50_manual_verse_gets_no_punch(self):
        doc = build(verse=[(4900, 7800)])
        for c in doc["candidates"]:
            self.assertFalse(c["start_ms"] < 7800 and 4900 < c["end_ms"])
        self.assertEqual(drop_codes(doc)[(12,)], "verse")

    def test_d51_sign_off_span(self):
        cfg = N().config(fx("profile_endings_all.json")["endings"], {})
        doc = build(endings=cfg)
        for c in doc["candidates"]:
            self.assertLessEqual(c["end_ms"], 20320)


# ============================================================================== E. podcast reframe scale
class TestPodcast(unittest.TestCase):
    def r02(self, words=None, **kw):
        from lib.shots import frame_shots
        r = fx("podcast_r02.json")
        fr = E().geometry(1920, 1080, S=1920 / 1080, layer=frame_shots(r["shots"]["shots"], None, 1920, 1080))
        w = words or ws(["٣ كيلو في الأسبوع ده"], t0=10000)
        return build(words=w, media_end_ms=33700, frame=fr, faces={"status": "ok", "doc": r["samples"]}, **kw), fr

    def test_e52_composition_on_the_reframed_crop(self):
        doc, fr = self.r02()
        (c,) = doc["candidates"]
        self.assertEqual(c["s_max"], 1.12)                              # face-anchored: the cap (frame-centred: ~1.11)
        from lib.shots import compose_camera
        got = compose_camera([{"decision_id": "EMP", "type": "punch_in", "at_ms": c["start_ms"], "until_ms": c["end_ms"],
                               "scale_factor": c["scale"], "offset_x": c["offset_x"], "offset_y": c["offset_y"]}],
                             fr["layer"], 1920, 1080)
        e = next(x for x in got if x["decision_id"] == "EMP")
        shot = next(x for x in fr["layer"] if x["at_ms"] <= c["start_ms"] < x["until_ms"])
        self.assertAlmostEqual(e["scale_factor"], round(shot["scale_factor"] * c["scale"], 5), places=5)
        # the head (top at y ~199.8 unpunched) stays inside with the 6 % margin
        P, cx, cy = E().compose(fr, c["start_ms"], c["scale"], c["offset_x"], c["offset_y"])
        hb = head([0.5445, 0.3653, 0.1547, 0.275])
        self.assertGreaterEqual(cy + (hb[1] - 0.5) * 1080 * P, 0.06 * 1920 - 0.01)

    def test_e53_offset_clamp_binds(self):
        """A face near the source edge: the shot offset is already at the clamp, so the face is not centred. The punch
        is measured on the COMPOSED offset (compose_camera clamps it so the frame stays filled): an offset pushing past
        the clamp comes back clamped; the head-anchored offset needs no clamp and keeps the face where it was."""
        from lib.shots import frame_shots
        shots = [{"start_ms": 0, "end_ms": 20000, "faces": [[0.93, 0.4, 0.04, 0.07]], "n_faces": 1}]
        layer = frame_shots(shots, None, 1920, 1080)
        lim = (1920 * 1920 / 1080 - 1080) / 2
        self.assertAlmostEqual(abs(layer[0]["offset_x"]), lim, delta=0.5)
        fr = E().geometry(1920, 1080, S=1920 / 1080, layer=layer)
        P, cx, _ = E().compose(fr, 5000, 1.08, -900.0, 0.0)            # a story offset past the clamp
        self.assertAlmostEqual(cx + 1920 * P / 2, 1080, delta=0.02)    # clamped: the right edge sits on the frame edge
        env = head([0.93, 0.4, 0.04, 0.07])
        ev = E().evaluate(fr, env, 5000, 1.08, 0.06)
        self.assertTrue(ev["ok"])
        P, cx, _ = E().compose(fr, 5000, 1.08, ev["offset_x"], ev["offset_y"])
        P0, cx0, _ = E().compose(fr, 5000, 1.0, 0.0, 0.0)
        hc = (env[0] + env[2]) / 2
        self.assertAlmostEqual(cx + (hc - 0.5) * 1920 * P, cx0 + (hc - 0.5) * 1920 * P0, delta=0.6)
        self.assertLessEqual(cx - 1920 * P / 2, 1e-6)                  # and the frame stays filled
        self.assertGreaterEqual(cx + 1920 * P / 2, 1080 - 0.02)

    def test_e54_speaker_follow_target_is_protected(self):
        from lib.shots import frame_shots
        sp = fx("speakers_follow.json")
        shots = [{"start_ms": 0, "end_ms": 20000, "faces": [[0.25, 0.4, 0.1, 0.18], [0.75, 0.4, 0.1, 0.18]], "n_faces": 2}]
        fr = E().geometry(1920, 1080, S=1920 / 1080, layer=frame_shots(shots, sp, 1920, 1080))
        sd = samples_doc(lambda t: [[0.25, 0.4, 0.1, 0.18], [0.75, 0.12, 0.1, 0.18]], t1=20000, w=1920, h=1080)
        doc = build(words=ws(["٣ كيلو في الأسبوع ده"], t0=11000), media_end_ms=20000, frame=fr, speakers=sp,
                    faces={"status": "ok", "doc": sd})
        # the guest (right) speaks from 9 s, head near the top: the target's head limits the punch
        self.assertTrue(not doc["candidates"] or doc["candidates"][0]["s_max"] < 1.12)

    def test_e54_the_followed_speaker_leaning_out_still_vetoes(self):
        from lib.shots import frame_shots
        sp = fx("speakers_follow.json")
        shots = [{"start_ms": 0, "end_ms": 20000, "faces": [[0.25, 0.4, 0.1, 0.18], [0.75, 0.4, 0.1, 0.18]], "n_faces": 2}]
        fr = E().geometry(1920, 1080, S=1920 / 1080, layer=frame_shots(shots, sp, 1920, 1080))
        lean = samples_doc(lambda t: [[0.25, 0.4, 0.1, 0.18], [0.93, 0.4, 0.1, 0.18]], t1=20000, w=1920, h=1080)
        P0, cx0, cy0 = E().compose(fr, 11000, 1.0, 0.0, 0.0)
        self.assertLess(E().visible_share(fr, [0.93, 0.4, 0.1, 0.18], P0, cx0, cy0), 0.5)
        doc = build(words=ws(["٣ كيلو في الأسبوع ده"], t0=11000), media_end_ms=20000, frame=fr, speakers=sp,
                    faces={"status": "ok", "doc": lean})
        self.assertEqual(doc["candidates"], [])                      # protected (the guest), so the punch is unsafe
        self.assertEqual(doc["dropped"][0]["code"], "edge")

    def test_e55_window_over_a_podcast(self):
        from lib.plan import window_rect
        from lib.shots import frame_shots
        r = fx("podcast_r02.json")
        win = window_rect("4:5", None, 1080, 1920)
        fr = E().geometry(1920, 1080, S=1920 / 1080, layer=frame_shots(r["shots"]["shots"], None, 1920, 1080), window=win)
        k45 = max(1080 / 1920, 1350 / 1080) / (1920 / 1080)
        self.assertAlmostEqual(fr["k45"], k45, places=9)
        P, cx, cy = E().compose(fr, 10000, 1.0, 0.0, 0.0)
        self.assertAlmostEqual(P, 1920 / 1080 * k45, places=4)
        doc = build(words=ws(["٣ كيلو في الأسبوع ده"], t0=10000), media_end_ms=33700, frame=fr,
                    faces={"status": "ok", "doc": r["samples"]})
        for c in doc["candidates"]:
            P, cx, cy = E().compose(fr, c["start_ms"], c["scale"], c["offset_x"], c["offset_y"])
            hb = head([0.5445, 0.3653, 0.1547, 0.275])
            self.assertGreaterEqual(cy + (hb[1] - 0.5) * 1080 * P, 285 + 0.06 * 1350 - 0.01)
            self.assertEqual(c["ease"]["in"], "hard: 4:5 window")

    def test_e56_story_offset_never_undoes_the_shot_centring(self):
        doc, fr = self.r02()
        (c,) = doc["candidates"]
        self.assertAlmostEqual(c["offset_x"], 0.0, delta=1.0)           # the face is already at the shot centre


# ============================================================================== I. output, determinism, the verb
def project(tmp: Path, words_doc=None, faces=True):
    """A client folder with one native 9:16 clip (synthetic, no media decoded): words, preflight, faces."""
    root = tmp / "عميل تجربة"
    (root / "data/Raw").mkdir(parents=True)
    (root / "assets").mkdir()
    (root / "data/Raw/CLIP1.mov").write_bytes(b"\0")
    p = Paths(root, "CLIP1")
    p.ensure_project()
    write_json(p.p("02_transcription/words.json"), words_doc or fx("words_ar.json"))
    write_json(p.p("00_inputs/preflight.json"), {"files": [{"path": str(root / "data/Raw/CLIP1.mov"), "name": "CLIP1.mov",
                                                            "video": {"display_width": 1080, "display_height": 1920}}]})
    write_json(p.p("01_analysis/edit-decisions.json"), {"video_id": "CLIP1", "global": {"main_footage": "data/Raw/CLIP1.mov"},
                                                        "decisions": []})
    if faces:
        write_json(p.p(E().FACES_FILE), dict(fx("faces_916.json"), footage="data/Raw/CLIP1.mov"))
    return root, p


class TestOutput(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root, self.p = project(self.tmp)
        self.ctx = common.set_context(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_i85_shape(self):
        doc = E().run(self.p, self.ctx, audio=False)
        for k in ("schema", "video_id", "inputs_sha1", "detector", "head_from_face", "settings", "candidates", "dropped",
                  "notes"):
            self.assertIn(k, doc)
        c = doc["candidates"][0]
        for k in ("id", "word_ids", "start_ms", "end_ms", "score", "rank", "r", "s_max", "scale", "offset_x", "offset_y",
                  "faces_used", "ease", "needs_review", "reason", "reason_en", "decision"):
            self.assertIn(k, c)
        self.assertEqual(set(c["score"]), {"total", "loudness_z", "after_pause", "number", "client", "cta", "key"})
        self.assertIn(c["ease"]["in"].split(":")[0], ("eased", "hard"))
        cam = c["decision"]["camera"]
        self.assertEqual((cam["type"], cam["scale_factor"], cam["emphasis"]["candidate"]), ("punch_in", c["scale"], c["id"]))
        for d in doc["dropped"]:
            self.assertTrue(d["why"] and d["why_en"] and d["code"])
        self.assertEqual(read_json(self.p.p(E().FILE)), doc)

    def test_i86_byte_identical_and_platform_free(self):
        outs = []
        for plat in ("darwin", "win32", "win32"):
            with mock.patch.object(sys, "platform", plat):
                E().run(self.p, self.ctx, audio=False)
            outs.append(self.p.p(E().FILE).read_bytes())
        self.assertEqual(len(set(outs)), 1)

    def test_i87_never_applied(self):
        ed = self.p.p("01_analysis/edit-decisions.json")
        appr = self.p.p("01_analysis/plan-approval.json")
        write_json(appr, {"approved": True, "by": "editor", "plan_fingerprint": "x"})
        before = (hashlib.sha1(ed.read_bytes()).hexdigest(), hashlib.sha1(appr.read_bytes()).hexdigest())
        E().run(self.p, self.ctx, audio=False)
        self.assertEqual(before, (hashlib.sha1(ed.read_bytes()).hexdigest(), hashlib.sha1(appr.read_bytes()).hexdigest()))

    def test_i88_refusals_write_nothing(self):
        from lib.errors import Guidance
        self.p.p("02_transcription/words.json").unlink()
        with self.assertRaises(Guidance):
            E().run(self.p, self.ctx, audio=False)
        self.assertFalse(self.p.p(E().FILE).exists())
        self.p.p("02_transcription/words.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(Guidance):
            E().run(self.p, self.ctx, audio=False)
        self.assertFalse(self.p.p(E().FILE).exists())
        write_json(self.p.p("02_transcription/words.json"), fx("words_ar.json"))
        self.p.p(E().FACES_FILE).write_text("{broken", encoding="utf-8")       # damaged samples: needs review, no crash
        doc = E().run(self.p, self.ctx, audio=False)
        self.assertTrue(doc["candidates"] and all(c["needs_review"] for c in doc["candidates"]))
        self.assertIn("faces_damaged", [n["code"] for n in doc["notes"]])

    def test_i88_stale_samples_are_not_used(self):
        write_json(self.p.p(E().FACES_FILE), dict(fx("faces_916.json"), footage="data/Raw/OTHER.mov"))
        doc = E().run(self.p, self.ctx, audio=False)
        self.assertTrue(all(c["needs_review"] for c in doc["candidates"]))
        self.assertIn("faces_stale", [n["code"] for n in doc["notes"]])

    def test_i89_one_decode_pass_and_the_cpu_fallback(self):
        calls = []

        def decode(argv):
            calls.append(argv)
            return [bytes(360 * 640 * 3)] * 240, ""
        doc = E().sample_faces("x.mov", 0, 60000, 1080, 1920, faces_fn=lambda im: [], decode=decode)
        self.assertEqual(len(calls), 1)
        self.assertIn("fps=4", calls[0][calls[0].index("-vf") + 1])
        self.assertEqual(len(doc["samples"]), 240)
        calls.clear()

        def flaky(argv):
            calls.append(argv)
            if "cuda" in argv:
                return [], "Error while decoding: CUDA_ERROR_OUT_OF_MEMORY"
            return [bytes(360 * 640 * 3)] * 40, ""
        with mock.patch("lib.accel.decode_args", side_effect=lambda ln: ["-hwaccel", "cuda"] if ln != "cpu" else []), \
                mock.patch("lib.accel.is_gpu_failure", return_value=True), mock.patch("lib.accel.note_fallback"):
            doc = E().sample_faces("x.mov", 0, 10000, 1080, 1920, faces_fn=lambda im: [], decode=flaky, lane="cuda")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(doc["samples"]), 40)

    def test_i_faces_run_writes_the_samples_file_with_injected_faces(self):
        import contextlib
        self.p.p(E().FACES_FILE).unlink()
        slots = []

        @contextlib.contextmanager
        def slot(site, **kw):
            slots.append(site)
            yield "cpu"

        def decode(argv):
            return [bytes(360 * 640 * 3)] * 8, ""
        with mock.patch("lib.gpu_lock.site_slot", slot):
            doc = E().run(self.p, self.ctx, faces=True, faces_fn=lambda im: [(0.5, 0.42, 0.2, 0.23)], decode=decode,
                          audio=False)
        self.assertEqual(slots, ["shots"])
        fs = read_json(self.p.p(E().FACES_FILE))
        self.assertEqual((fs["detector"], fs["footage"], fs["display"]), ("injected", "data/Raw/CLIP1.mov",
                                                                         {"w": 1080, "h": 1920}))
        self.assertEqual(doc["detector"], "injected")

    def test_i_inputs_sha1_follows_the_inputs(self):
        a = E().inputs_sha1(self.p, self.ctx)
        self.assertEqual(a, E().inputs_sha1(self.p, self.ctx))
        ed = read_json(self.p.p("01_analysis/edit-decisions.json"))
        ed["decisions"].append({"decision_id": "EDIT_009"})                   # a decision: not an input
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed)
        self.assertEqual(a, E().inputs_sha1(self.p, self.ctx))
        ed["global"]["cut_words"] = [12]                                       # cut words: an input
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed)
        self.assertNotEqual(a, E().inputs_sha1(self.p, self.ctx))

    def test_i_audio_from_the_clean_dialogue_file(self):
        import numpy as np
        import wave
        sr = 8000
        x = np.zeros(sr * 22)
        for k, w in enumerate(fx("words_ar.json")["words"]):          # quiet words of slightly varying level, one loud
            a = 0.8 if w["id"] == 12 else 0.04 + 0.01 * (k % 3)
            i0, i1 = w["start_ms"] * sr // 1000, w["end_ms"] * sr // 1000
            x[i0:i1] = a * np.sin(2 * np.pi * 100 * np.arange(i1 - i0) / sr)
        f = self.p.p("06_audio/dialogue/dialogue_clean.wav")
        f.parent.mkdir(parents=True, exist_ok=True)
        pcm = (np.clip(x, -1, 1) * 8388607).astype(np.int32)
        b = bytearray()
        for v in pcm.tolist():
            b += int(v).to_bytes(4, "little", signed=True)[:3]
        with wave.open(str(f), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(3)
            w.setframerate(sr)
            w.writeframes(bytes(b))
        got = E().read_wav(f)
        self.assertEqual(got[1], sr)
        self.assertAlmostEqual(float(np.max(np.abs(got[0]))), 0.8, places=3)
        doc = E().run(self.p, self.ctx)
        sc = {s["word"]: s["score"] for s in doc["scored"]}
        self.assertGreater(sc["خمسمية"]["loudness_z"], 2.0)
        self.assertNotIn("no_audio", [n["code"] for n in doc["notes"]])
        self.assertEqual(doc["settings"]["audio"], "06_audio/dialogue/dialogue_clean.wav")

    def test_a11_the_footage_audio_when_there_is_no_clean_dialogue(self):
        import subprocess
        ff = common.ffmpeg_exe()
        clip = self.root / "data/Raw/CLIP1.mov"
        subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=300:r=48000:d=22",
                        "-c:a", "pcm_s16le", str(clip)], check=True)
        doc = E().run(self.p, self.ctx)
        self.assertEqual(doc["settings"]["audio"], "footage")
        self.assertNotIn("no_audio", [n["code"] for n in doc["notes"]])


if __name__ == "__main__":
    unittest.main()
