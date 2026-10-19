# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Manual verse slot (owner decision 2026-10-18): the plugin never writes Quran text. A recited verse in the
transcript gets empty captions, its overlapping graphics blanked or dropped (with a warning), a Premiere marker
«آية: يضيفها المونتير يدويًا» (comment = source timecodes + the cue only) and one NEEDS-YOU line.

This file: detection and resolution (lib/manual_verse.py, pure) and the compiled plan (lib/plan.py). The other outputs
(NEEDS-YOU, previews, burned captions, publish, the needs-you schema) are in test_manual_verse_outputs.py.
The fixture verse is a placeholder of neutral words (tests/fixtures/manual_verse/speech.json): no Quran text beyond the
common cue phrases. Case ids: D:/ClaudeData/claude-api-lane/work/manual-verse/cases.md.
Run:  bash tools/test.sh -p test_manual_verse.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import common  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402

FIX = SK / "tests" / "fixtures" / "manual_verse" / "speech.json"
DATA = json.loads(FIX.read_text(encoding="utf-8"))
VERSE = DATA["verse"]
SC = DATA["scenarios"]


def MV():
    from lib import manual_verse
    return manual_verse


def build_words(text: str, start: int = 200, dur: int = 350, gap: int = 50) -> list:
    """Words with times: each lasts `dur` ms, `gap` ms apart; a `|900` token puts a 900 ms pause before the next."""
    words, t, pause = [], start, None
    for tok in text.split():
        if tok.startswith("|"):
            pause = int(tok[1:])
            continue
        if pause is not None and words:
            t = words[-1]["end_ms"] + pause
        pause = None
        words.append({"id": len(words) + 1, "segment_id": 1, "word": tok, "start_ms": t, "end_ms": t + dur,
                      "probability": 0.9})
        t += dur + gap
    return words


def verse_window(words: list) -> tuple:
    vs = [w for w in words if w["word"] in VERSE]
    return vs[0]["start_ms"], vs[-1]["end_ms"]


def word_at(words: list, text: str, n: int = 0) -> dict:
    return [w for w in words if w["word"] == text][n]


def has_verse(text: str) -> list:
    return [v for v in VERSE if v in str(text)]


def cfg(religious=True, phrases=()):
    return {"religious": religious, "phrases": [MV().tokens(p) for p in phrases], "warnings": []}


def decision(did, gid, a, b, evidence, text, template="statement_highlight", sound=None, **kw):
    d = {"decision_id": did, "segment_id": "S1", "evidence": evidence, "start": a, "end": b,
         "semantic_intent": "point", "visual_treatment": "bar", "confidence": "high",
         "graphics": [{"id": gid, "template": template, "start": a, "end": b, "text": text, **kw}]}
    if sound:
        d["sound"] = sound
    return d


def verse_project(tmp: Path, words: list, domain="religious", decisions=(), extra=None, glob=None, pauses=None,
                  flags=None):
    """A client folder with one transcribed clip (no real video: the plan only checks the file exists)."""
    root = tmp / "CLIENT"
    for d in ("assets/Font", "data/Raw"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "data/Raw/CLIP1.mov").write_bytes(b"\0")
    if domain:
        write_json(root / common.CLIENT_PROFILE_REL / "profile.json", {"domain": domain})
    p = Paths(root, "CLIP1")
    p.ensure_project()
    for w in words:
        if flags and w["word"] in flags:
            w["flagged"] = {"note": "unsure"}
    dur = words[-1]["end_ms"] + 1000
    segs = [{"id": 1, "start_ms": words[0]["start_ms"], "end_ms": words[-1]["end_ms"],
             "text": " ".join(w["word"] for w in words), "avg_logprob": -0.2, "no_speech_prob": 0.01,
             "compression_ratio": 1.2, "words": [w["id"] for w in words]}]
    meta = {"source_video": str(root / "data/Raw/CLIP1.mov"), "backend": "test", "model": "none", "language": "ar",
            "language_probability": 1.0, "duration_ms": dur}
    common.set_context(root)
    from lib.transcribe import finalize
    finalize(p, meta, segs, [dict(w) for w in words])
    ed = {"video_id": "CLIP1", "global": {"main_footage": "data/Raw/CLIP1.mov", **(glob or {})},
          "decisions": list(decisions), **(extra or {})}
    write_json(p.p("01_analysis/edit-decisions.json"), ed)
    if pauses:
        write_json(p.p("06_audio/dialogue/pauses.json"), pauses)
    return root, p


class Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.addCleanup(common.set_context, None)

    def compile(self, p):
        from lib.plan import compile_plan
        res = compile_plan(p)
        self.assertTrue(res["ok"], res["errors"])
        return res, read_json(p.p("01_analysis/timeline-spec.json"))


# --------------------------------------------------------------------------- detection (pure)
class TestDetect(unittest.TestCase):
    def test_D1_cue_plus_verse_plus_pause(self):
        w = build_words(SC["recited"])
        spans = MV().detect(w, cfg())
        self.assertEqual(len(spans), 1, spans)
        a, b = verse_window(w)
        s = spans[0]
        self.assertEqual((s["src_start_ms"], s["src_end_ms"]), (a, b))      # starts AFTER «قال تعالى»
        self.assertEqual((s["cue"], s["end"], s["guessed_end"], s["source"]), ("qala_taala", "pause", False, "detected"))

    def test_D2_pause_right_after_the_cue_does_not_end_the_span(self):
        w = build_words(SC["after_pause"])
        spans = MV().detect(w, cfg())
        self.assertEqual([(s["src_start_ms"], s["src_end_ms"]) for s in spans], [verse_window(w)])

    def test_D3_aya_sura_fil_aya_never_open_a_span(self):
        w = build_words(SC["not_cues"])
        for religious in (True, False):
            self.assertEqual(MV().detect(w, cfg(religious)), [])
        self.assertEqual(MV().detect(w, MV().config({"domain": "religious"})), [])      # the real lexicon too

    def test_D4_lexicon_phrase_for_a_religious_client(self):
        w = build_words(SC["phrase"])
        spans = MV().detect(w, cfg(True, [DATA["fake_lexicon_phrase"]]))
        a, b = word_at(w, "سحاب")["start_ms"], word_at(w, "نجم")["end_ms"]
        self.assertEqual([(s["src_start_ms"], s["src_end_ms"], s["cue"], s["end"]) for s in spans],
                         [(a, b, "verse_phrase", "phrase")])

    def test_D5_lexicon_phrase_ignored_for_other_clients(self):
        w = build_words(SC["phrase"])
        self.assertEqual(MV().detect(w, cfg(False, [DATA["fake_lexicon_phrase"]])), [])

    def test_D6_basmala_is_part_of_the_span(self):
        w = build_words(SC["basmala"])
        spans = MV().detect(w, cfg(False))
        self.assertEqual(len(spans), 1, spans)
        self.assertEqual(spans[0]["src_start_ms"], word_at(w, "بسم")["start_ms"])
        self.assertEqual(spans[0]["src_end_ms"], word_at(w, "قمر")["end_ms"])
        self.assertEqual(spans[0]["cue"], "basmala")

    def test_D7_twelve_second_cap(self):
        w = build_words("اهلا بيكم قال تعالى " + " ".join(VERSE * 8) + " |900 وده كلام")
        spans = MV().detect(w, cfg())
        start = w[4]["start_ms"]
        self.assertEqual(len(spans), 1, spans)
        self.assertEqual((spans[0]["src_start_ms"], spans[0]["src_end_ms"]), (start, start + MV().CAP_MS))
        self.assertEqual((spans[0]["end"], spans[0]["guessed_end"]), ("cap", True))

    def test_D8_isti_adha_basmala_verse_chain_merges(self):
        w = build_words(SC["chain"])
        spans = MV().detect(w, cfg(False))
        self.assertEqual(len(spans), 1, spans)
        self.assertEqual((spans[0]["src_start_ms"], spans[0]["src_end_ms"]),
                         (word_at(w, "أعوذ")["start_ms"], word_at(w, "قمر")["end_ms"]))
        self.assertEqual(spans[0]["cue"], "istiadha")

    def test_D9_joined_waw_and_diacritics(self):
        w = build_words(SC["joined"])
        self.assertEqual([(s["src_start_ms"], s["src_end_ms"]) for s in MV().detect(w, cfg(False))], [verse_window(w)])

    def test_D10_cue_at_the_end_opens_nothing(self):
        self.assertEqual(MV().detect(build_words(SC["end_cue"]), cfg()), [])

    def test_D10b_basmala_at_the_end_is_itself_the_span(self):
        w = build_words("اهلا بيكم بسم الله الرحمن الرحيم")              # mutation survivor M10
        self.assertEqual([(s["src_start_ms"], s["src_end_ms"], s["end"]) for s in MV().detect(w, cfg(False))],
                         [(w[2]["start_ms"], w[-1]["end_ms"], "speech_end")])

    def test_D3b_short_isti_adha_alone_is_everyday_speech(self):
        self.assertEqual(MV().detect(build_words("أعوذ بالله يا جماعة ده كلام غريب"), cfg()), [])

    def test_speech_end_without_pause_is_not_guessed(self):
        w = build_words("اهلا قال تعالى " + " ".join(VERSE))
        s = MV().detect(w, cfg())
        self.assertEqual([(x["src_end_ms"], x["end"], x["guessed_end"]) for x in s],
                         [(w[-1]["end_ms"], "speech_end", False)])

    def test_bad_words_are_skipped(self):
        w = build_words(SC["recited"])
        w.insert(3, {"id": 99, "word": None})
        w.insert(4, "x")
        self.assertEqual(len(MV().detect(w, cfg())), 1)


class TestResolve(unittest.TestCase):
    def setUp(self):
        self.w = build_words(SC["recited"])
        self.det = MV().detect(self.w, cfg())

    def test_D11_editor_adds_and_removes(self):
        a, b = verse_window(self.w)
        spans, errs, warns = MV().resolve(self.det, {"manual_verse_off": [{"start_ms": a + 100, "end_ms": a + 200}]})
        self.assertEqual((spans, errs, warns), ([], [], []))
        spans, errs, warns = MV().resolve([], {"manual_verse": [{"start_ms": 1000, "end_ms": 3000, "note": "x"}]})
        self.assertEqual(errs, [])
        self.assertEqual([(s["id"], s["src_start_ms"], s["src_end_ms"], s["source"], s["cue"]) for s in spans],
                         [("MV01", 1000, 3000, "editor", "editor")])
        # the editor's span wins over a detected one it overlaps; ids follow the time order
        spans, _e, _w = MV().resolve(self.det, {"manual_verse": [{"start_ms": 100, "end_ms": 300},
                                                                 {"start_ms": a - 100, "end_ms": b + 500}]})
        self.assertEqual([(s["id"], s["src_start_ms"], s["src_end_ms"], s["source"]) for s in spans],
                         [("MV01", 100, 300, "editor"), ("MV02", a - 100, b + 500, "editor")])

    def test_D12_bad_entries(self):
        for bad in ("x", [{"start_ms": "abc", "end_ms": 10}], [{"start_ms": 500, "end_ms": 400}], [7]):
            _s, errs, _w = MV().resolve([], {"manual_verse": bad})
            self.assertEqual(len(errs), 1, (bad, errs))
            _s, errs, _w = MV().resolve([], {"manual_verse_off": bad})
            self.assertEqual(len(errs), 1, (bad, errs))
        spans, errs, warns = MV().resolve(self.det, {"manual_verse_off": [{"start_ms": 0, "end_ms": 50}]})
        self.assertEqual((len(spans), errs, len(warns)), (1, [], 1))
        self.assertIn("manual_verse_off", warns[0])

    def test_clock_strings_are_times(self):
        spans, errs, _w = MV().resolve([], {"manual_verse": [{"start_ms": "00:00:01.000", "end_ms": "00:00:02.500"}]})
        self.assertEqual((errs, spans[0]["src_start_ms"], spans[0]["src_end_ms"]), ([], 1000, 2500))


class TestConfig(unittest.TestCase):
    def test_religious_reads_the_verse_phrase_list_through_review_domains(self):
        from lib import review_domains
        terms = next(r["terms"] for r in review_domains.lexicon("religious")["rules"] if r["id"] == "verse-phrase")
        c = MV().config({"domain": "religious"})
        self.assertTrue(c["religious"])
        self.assertEqual(c["phrases"], [MV().tokens(t) for t in terms])
        self.assertTrue(MV().config({"review_domains": ["religious"]})["religious"])

    def test_other_clients_never_read_the_lexicon(self):
        from lib import review_domains
        with mock.patch.object(review_domains, "lexicon", side_effect=AssertionError("read")):
            for prof in ({"domain": "medical"}, {}, {"domain": "general"}, None):
                c = MV().config(prof)
                self.assertEqual((c["religious"], c["phrases"], c["warnings"]), (False, [], []))

    def test_D13_unreadable_lexicon_keeps_the_fixed_cues(self):
        from lib import review_domains
        from lib.errors import Guidance
        with mock.patch.object(review_domains, "lexicon", side_effect=Guidance("broken", "fix it")):
            c = MV().config({"domain": "religious"})
        self.assertEqual((c["religious"], c["phrases"], len(c["warnings"])), (True, [], 1))
        self.assertEqual(len(MV().detect(build_words(SC["recited"]), c)), 1)

    def test_a_profile_the_registry_refuses_falls_back_to_the_legacy_domain(self):
        c = MV().config({"domain": "religious", "review_domains": ["no-such-domain"]})
        self.assertTrue(c["religious"])


class TestHelpers(unittest.TestCase):
    def test_filter_cues_split_edge_keeps_outside_words(self):
        w = build_words(SC["recited"])
        a, b = verse_window(w)
        q = word_at(w, "قال")
        after = word_at(w, "معناه")
        cues = [{"start_ms": q["start_ms"], "end_ms": word_at(w, "نهر")["end_ms"], "text": "قال تعالى شجرة نهر"},
                {"start_ms": word_at(w, "جبل")["start_ms"], "end_ms": after["end_ms"], "text": "جبل سحاب قمر وده معناه"},
                {"start_ms": after["end_ms"] + 50, "end_ms": after["end_ms"] + 900, "text": "نص معدّل بإيد المونتير"}]
        out = MV().filter_cues(cues, [(a, b)], w)
        self.assertEqual([c["text"] for c in out], ["قال تعالى", "وده معناه", "نص معدّل بإيد المونتير"])
        self.assertLessEqual(out[0]["end_ms"], a)
        self.assertGreaterEqual(out[1]["start_ms"], b)
        self.assertEqual(out[2], cues[2])                                        # untouched cue: as written

    def test_filter_cues_drops_a_word_the_span_edge_cuts_through(self):
        w = build_words(SC["recited"])                                     # mutation survivor M19
        s = word_at(w, "شجرة")
        edge = s["start_ms"] + 250                                         # an editor's span starting mid-word
        cue = {"start_ms": word_at(w, "قال")["start_ms"], "end_ms": word_at(w, "نهر")["end_ms"],
               "text": "قال تعالى شجرة نهر"}
        out = MV().filter_cues([cue], [(edge, verse_window(w)[1])], w)
        self.assertEqual([c["text"] for c in out], ["قال تعالى"])

    def test_repeats(self):
        seqs = [MV().tokens(" ".join(VERSE))]
        self.assertTrue(MV().repeats("كلام شجرة نهر جبل كلام", seqs))
        self.assertTrue(MV().repeats("وشَجَرَة نهر جبل", seqs))                   # joined و and diacritics
        self.assertFalse(MV().repeats("شجرة وكلام نهر", seqs))
        self.assertFalse(MV().repeats("", seqs))
        self.assertTrue(MV().repeats("نهر", [MV().tokens("نهر")]))               # a one-word span: the word itself

    def test_keep_piece(self):
        kp = MV().keep_piece
        self.assertEqual(kp(0, 1000, [(2000, 3000)]), (0, 1000))
        self.assertEqual(kp(0, 2500, [(2000, 3000)]), (0, 2000))
        self.assertEqual(kp(2500, 4000, [(2000, 3000)]), (3000, 4000))
        self.assertIsNone(kp(1500, 3400, [(2000, 3000)]))                        # 500 + 400 ms: both under 600
        self.assertEqual(kp(1000, 4000, [(2000, 3000)]), (1000, 2000))          # the part before wins
        self.assertEqual(kp(1700, 4000, [(2000, 3000)]), (3000, 4000))          # before is too short: the part after
        self.assertEqual(kp(1400, 3000, [(2000, 3000)]), (1400, 2000))          # exactly 600 ms is kept

    def test_marker_comment_has_timecodes_and_cue_only(self):
        s = {"id": "MV01", "src_start_ms": 3200, "src_end_ms": 7400, "cue": "qala_taala", "guessed_end": False}
        c = MV().marker_comment(s)
        self.assertIn("بعد: قال تعالى", c)
        self.assertIn("00:00:03.200", c)
        self.assertIn("00:00:07.400", c)
        self.assertIn("النهاية متخمّنة", MV().marker_comment(dict(s, guessed_end=True)))
        self.assertIn("البسملة", MV().marker_comment(dict(s, cue="basmala")))
        self.assertNotIn("الرحمن", MV().marker_comment(dict(s, cue="basmala")))   # named, never quoted


# --------------------------------------------------------------------------- the compiled plan
class TestPlan(Base):
    def setUp(self):
        super().setUp()
        self.w = build_words(SC["recited"])
        self.a, self.b = verse_window(self.w)

    def bar_over_span(self):
        s = word_at(self.w, "الصبر")["start_ms"]
        return decision("EDIT_001", "GFX_001", s, self.b + 1200, "هنتكلم عن الصبر", "الصبر")

    def test_P1_captions_bar_marker(self):
        _root, p = verse_project(self.tmp, self.w, decisions=[self.bar_over_span()])
        res, spec = self.compile(p)
        # captions: the -seq files, nothing inside the span, no verse word
        self.assertEqual(spec["caption_source"], "02_transcription/captions-short-seq.srt")
        from lib import srt as srtlib
        for name in ("captions-short-seq", "subtitles-seq"):
            cues = srtlib.read_srt(p.p(f"02_transcription/{name}.srt"))
            self.assertTrue(cues, name)
            for c in cues:
                self.assertEqual(has_verse(c["text"]), [], (name, c))
                self.assertFalse(c["start_ms"] < self.b and self.a < c["end_ms"], (name, c))
        sw = read_json(p.p("02_transcription/words-seq.json"))["words"]
        self.assertEqual([x for x in sw if x["word"] in VERSE], [])
        self.assertIn("مفتاح", [x["word"] for x in sw])
        # the bar: shortened to end where the verse starts, with a warning naming it
        ev = next(e for e in spec["events"] if e["event_id"] == "GFX_001")
        self.assertEqual(ev["end_ms"], self.a)
        self.assertEqual(ev["end_frame"], common.ms_to_frame(self.a))
        self.assertTrue(any("GFX_001" in x for x in res["warnings"]), res["warnings"])
        # the marker
        mk = spec["markers"]
        self.assertEqual(len(mk), 1, mk)
        self.assertEqual((mk[0]["name"], mk[0]["colour"]), ("آية: يضيفها المونتير يدويًا", MV().MARKER_COLOUR))
        self.assertEqual(mk[0]["start_frame"], common.ms_to_frame(self.a))
        self.assertIn("بعد: قال تعالى", mk[0]["comment"])
        self.assertIn(common.fmt_ts(self.a, "."), mk[0]["comment"])
        self.assertEqual(has_verse(json.dumps(mk, ensure_ascii=False)), [])
        sp = spec["manual_verse"]
        self.assertEqual([(x["id"], x["src_start_ms"], x["src_end_ms"], x["guessed_end"]) for x in sp],
                         [("MV01", self.a, self.b, False)])

    def test_P2_bar_with_little_left_is_dropped_with_its_cues(self):
        d = decision("EDIT_002", "GFX_002", self.a - 200, self.b + 100, "قال تعالى", "كلام")
        _root, p = verse_project(self.tmp, self.w, decisions=[d])
        res, spec = self.compile(p)
        self.assertNotIn("GFX_002", [e["event_id"] for e in spec["events"]])
        self.assertTrue(any("GFX_002" in x and "600" in x for x in res["warnings"]), res["warnings"])
        broll = read_json(p.p("03_broll/broll-manifest.json"))["assets"]
        self.assertNotIn("GFX_002", [x["asset_id"] for x in broll])
        cues = read_json(p.p("06_audio/audio-cue-sheet.json"))["cues"]
        self.assertNotIn("GFX_002", [c.get("related_visual") for c in cues])

    def test_P3_graphic_repeating_the_verse_is_dropped_anywhere(self):
        s, e = word_at(self.w, "حياتنا")["start_ms"], self.w[-1]["end_ms"]
        d = decision("EDIT_003", "GFX_003", s, e, "في حياتنا كلها", "شجرة نهر جبل", template="glass_card")
        _root, p = verse_project(self.tmp, self.w, decisions=[d])
        res, spec = self.compile(p)
        self.assertEqual(spec["events"], [])
        self.assertTrue(any("GFX_003" in x for x in res["warnings"]), res["warnings"])
        self.assertEqual([has_verse(x) for x in res["warnings"] if has_verse(x)], [])

    def test_P4_hand_written_cues_split_at_the_edge(self):
        _root, p = verse_project(self.tmp, self.w)
        from lib import srt as srtlib
        q, n, j, m = (word_at(self.w, x) for x in ("قال", "نهر", "جبل", "معناه"))
        hand = [{"start_ms": q["start_ms"], "end_ms": n["end_ms"], "text": "قال تعالى شجرة نهر"},
                {"start_ms": j["start_ms"], "end_ms": m["end_ms"], "text": "جبل سحاب قمر وده معناه"},
                {"start_ms": m["end_ms"] + 50, "end_ms": m["end_ms"] + 900, "text": "تعديل يدوي"}]
        for name in ("captions-short", "subtitles"):
            srtlib.write_srt(p.p(f"02_transcription/{name}.srt"), hand)
        _res, _spec = self.compile(p)
        got = [c["text"] for c in srtlib.read_srt(p.p("02_transcription/captions-short-seq.srt"))]
        self.assertEqual(got, ["قال تعالى", "وده معناه", "تعديل يدوي"])

    def test_P5_pause_removal_maps_the_span(self):
        cut0 = self.b + 50
        cut1 = word_at(self.w, "وده")["start_ms"] - 50
        dur = self.w[-1]["end_ms"] + 1000
        _root, p = verse_project(self.tmp, self.w, glob={"remove_pauses": True},
                                 pauses={"keep_ms": [[0, cut0], [cut1, dur]], "cuts_ms": [[cut0, cut1]]})
        _res, spec = self.compile(p)
        self.assertTrue(spec["time_map"])
        from lib.timemap import TimeMap
        tm = TimeMap(spec["time_map"]["keep_ms"])
        mv = spec["manual_verse"][0]
        self.assertEqual((mv["start_ms"], mv["end_ms"]), (round(tm.ms(self.a)), round(tm.ms(self.b))))
        self.assertEqual(spec["markers"][0]["start_frame"], tm.frame(self.a))
        from lib import srt as srtlib
        for c in srtlib.read_srt(p.p("02_transcription/captions-short-seq.srt")):
            self.assertEqual(has_verse(c["text"]), [], c)

    def test_P6_no_output_holds_a_verse_word(self):
        s = word_at(self.w, "الصبر")["start_ms"]
        mid = (self.a + self.b) // 2
        decs = [decision("EDIT_001", "GFX_001", s, self.b + 1200, "هنتكلم عن الصبر", "الصبر"),
                decision("EDIT_002", "GFX_002", self.a, self.b, "شجرة نهر جبل", "معنى", template="term_callout",
                         sound=[{"type": "pop", "at": mid, "cue_id": "SFX_IN_VERSE"}])]
        _root, p = verse_project(self.tmp, self.w, decisions=decs, flags={"سحاب", "مفتاح"},
                                 glob={"cut_words": [{"word_ids": [word_at(self.w, "نهر")["id"]], "reason": "x"}]})
        before = {f: f.stat().st_mtime_ns for f in p.project.rglob("*") if f.is_file()}
        res, spec = self.compile(p)
        self.assertTrue(any("SFX_IN_VERSE" in x for x in res["warnings"]), res["warnings"])
        self.assertNotIn("SFX_IN_VERSE", [c["cue_id"] for c in read_json(p.p("06_audio/audio-cue-sheet.json"))["cues"]])
        written = [f for f in p.project.rglob("*") if f.is_file() and before.get(f) != f.stat().st_mtime_ns]
        self.assertTrue(any(f.name == "timeline-spec.json" for f in written))
        for f in written:
            text = f.read_text(encoding="utf-8")
            self.assertEqual(has_verse(text), [], f)
        plan_md = p.p("01_analysis/edit-plan.md").read_text(encoding="utf-8")
        self.assertIn("## آيات يضيفها المونتير", plan_md)
        self.assertIn("MV01", plan_md)
        self.assertIn("بعد: قال تعالى", plan_md)

    def test_P11_evidence_quoting_the_verse_is_replaced(self):
        s, e = word_at(self.w, "حياتنا")["start_ms"], self.w[-1]["end_ms"]   # mutation survivor P5
        d = decision("EDIT_004", "GFX_004", s, e, "شجرة نهر جبل", "حياتنا", template="glass_card")
        _root, p = verse_project(self.tmp, self.w, decisions=[d])
        _res, spec = self.compile(p)
        ev = [x for x in spec["events"] if x["event_id"] == "GFX_004"]
        self.assertEqual([x["evidence"] for x in ev], [MV().PLACEHOLDER])
        self.assertEqual(has_verse(json.dumps(spec, ensure_ascii=False)), [])

    def test_P5b_span_cut_away_whole_gets_no_marker(self):
        cut0 = self.b + 50                                                # mutation survivor P16
        cut1 = word_at(self.w, "وده")["start_ms"] - 50
        dur = self.w[-1]["end_ms"] + 1000
        _root, p = verse_project(self.tmp, self.w, glob={"remove_pauses": True},
                                 pauses={"keep_ms": [[0, cut0], [cut1, dur]], "cuts_ms": [[cut0, cut1]]},
                                 extra={"manual_verse_off": [{"start_ms": self.a, "end_ms": self.b}],
                                        "manual_verse": [{"start_ms": cut0 + 100, "end_ms": cut1 - 100}]})
        _res, spec = self.compile(p)
        self.assertNotIn("manual_verse", spec)
        self.assertNotIn("markers", spec)

    def test_P7_plain_clip_unchanged(self):
        w = build_words(SC["plain"])
        d = decision("EDIT_001", "GFX_001", w[2]["start_ms"], w[6]["end_ms"], "النهارده هنتكلم عن السكر", "السكر")
        for domain in (None, "religious", "medical"):
            with self.subTest(domain=domain):
                td = Path(tempfile.mkdtemp(dir=self.tmp))
                _root, p = verse_project(td, [dict(x) for x in w], domain=domain, decisions=[d])
                _res, spec = self.compile(p)
                self.assertNotIn("manual_verse", spec)
                self.assertNotIn("markers", spec)
                self.assertEqual(spec["caption_source"], "02_transcription/captions-short.srt")
                for f in ("captions-short-seq.srt", "subtitles-seq.srt", "words-seq.json"):
                    self.assertFalse(p.p(f"02_transcription/{f}").exists(), f)
                self.assertNotIn("آيات يضيفها", p.p("01_analysis/edit-plan.md").read_text(encoding="utf-8"))

    def test_P8_medical_clip_basmala_has_no_captions(self):
        w = build_words(SC["basmala"])
        _root, p = verse_project(self.tmp, w, domain="medical")
        _res, spec = self.compile(p)
        from lib import srt as srtlib
        for c in srtlib.read_srt(p.p("02_transcription/captions-short-seq.srt")):
            self.assertEqual(has_verse(c["text"]), [], c)
            self.assertNotIn("الرحيم", c["text"])
        self.assertEqual(spec["manual_verse"][0]["src_start_ms"], word_at(w, "بسم")["start_ms"])
        self.assertIn("البسملة", spec["markers"][0]["comment"])

    def test_P9_cap_is_recorded(self):
        w = build_words("اهلا بيكم قال تعالى " + " ".join(VERSE * 8) + " |900 وده كلام جميل")
        _root, p = verse_project(self.tmp, w)
        res, spec = self.compile(p)
        self.assertTrue(spec["manual_verse"][0]["guessed_end"])
        self.assertIn("النهاية متخمّنة", spec["markers"][0]["comment"])
        self.assertTrue(any("12" in x and "MV01" in x for x in res["warnings"]), res["warnings"])

    def test_editor_override_in_the_plan(self):
        w = build_words(SC["plain"])
        extra = {"manual_verse": [{"start_ms": w[3]["start_ms"], "end_ms": w[5]["end_ms"], "note": "سمعتها"}]}
        _root, p = verse_project(self.tmp, w, domain=None, extra=extra)
        _res, spec = self.compile(p)
        self.assertEqual([(x["source"], x["cue"]) for x in spec["manual_verse"]], [("editor", "editor")])
        _root, p = verse_project(Path(tempfile.mkdtemp(dir=self.tmp)), self.w,
                                 extra={"manual_verse_off": [{"start_ms": self.a, "end_ms": self.b}]})
        _res, spec = self.compile(p)
        self.assertNotIn("manual_verse", spec)

    def test_bad_override_is_a_plan_error(self):
        _root, p = verse_project(self.tmp, self.w, extra={"manual_verse": [{"start_ms": "x"}]})
        from lib.plan import compile_plan
        res = compile_plan(p)
        self.assertFalse(res["ok"])
        self.assertTrue(any("manual_verse" in e for e in res["errors"]), res["errors"])

    def test_flagged_word_inside_the_span_is_not_named(self):
        _root, p = verse_project(self.tmp, self.w, flags={"سحاب"})
        res, _spec = self.compile(p)
        flag_w = [x for x in res["warnings"] if "uncertain" in x]
        self.assertEqual(len(flag_w), 1, res["warnings"])
        self.assertNotIn("سحاب", flag_w[0])


if __name__ == "__main__":
    unittest.main()
