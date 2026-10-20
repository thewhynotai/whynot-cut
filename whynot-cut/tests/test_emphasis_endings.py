"""Task 29 (R-4.7): the ending order (CTA -> follow -> sign-off), the one sign-off detector and the protected span.

Cases: lane4\\work\\task29\\cases.md G64-G76. `endings.check` works on the sequence clock; `endings.plan_check` is the
step the plan calls (tested here on a PlanInputs built by hand, so it needs no plan.py change).
Run:  bash tools/test.sh -p test_emphasis_endings.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import copy  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
FX = SK / "tests" / "fixtures" / "emphasis"

from lib import common  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402


def fx(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def N():
    from lib import endings
    return endings


WORDS = fx("words_ar.json")["words"]
END_ALL = fx("profile_endings_all.json")["endings"]


def ev(eid, a, b, template="cta", role=None, **params):
    p = dict(params)
    if role:
        p["ending"] = role
    return {"event_id": eid, "template": template, "start_ms": a, "end_ms": b, "params": p}


def errs(events, span=(20320, 22000), cfg=None, **kw):
    cfg = cfg or N().config(END_ALL, {})
    sp = {"start_ms": span[0], "end_ms": span[1], "source": "phrase", "note": None} if span else None
    return N().check(events, sp, cfg, **kw)


class TestSignOff(unittest.TestCase):
    def test_g64_marker_wins_then_phrase_then_fallback(self):
        cfg = N().config(END_ALL, {})
        s = N().sign_off_span(WORDS, cfg, 19000, 22000)
        self.assertEqual((s["start_ms"], s["end_ms"], s["source"]), (19000, 22000, "marker"))
        s = N().sign_off_span(WORDS, cfg, None, 22000)
        self.assertEqual((s["start_ms"], s["source"]), (20320, "phrase"))
        un = N().config(fx("profile_endings_signoff_unsaid.json")["endings"], {})
        s = N().sign_off_span(WORDS, un, None, 22000)
        self.assertEqual((s["start_ms"], s["end_ms"], s["source"]), (14000, 22000, "fallback"))
        self.assertIn("8", s["note"]["en"])
        self.assertIsNone(N().sign_off_span(WORDS, N().config({}, {}), None, 22000))

    def test_g64_parity_with_cut_proposals(self):
        """Until the cut_proposals patch calls endings.sign_off_span, both detectors must protect the same span."""
        from lib import cut_proposals as cp
        cases = [(END_ALL, None), (END_ALL, "00:00:19.000"), (fx("profile_endings_signoff_unsaid.json")["endings"], None),
                 ({"sign_off": {"on": False}}, None), ({"sign_off": {"on": True, "phrase": ""}}, None),
                 ({"sign_off": {"on": True, "phrase": "يَلّا   سلام"}}, None)]
        for prof, marker in cases:
            tmp = Path(tempfile.mkdtemp())
            try:
                root = tmp / "C"
                (root / "data").mkdir(parents=True)
                (root / "assets").mkdir()
                p = Paths(root, "CLIP1")
                p.ensure_project()
                write_json(p.p("02_transcription/words.json"), fx("words_ar.json"))
                write_json(p.p("01_analysis/edit-decisions.json"),
                           {"global": {"sign_off_at": marker} if marker else {}, "decisions": []})
                ctx = common.Context(root=root)
                with mock.patch.object(common.Context, "config",
                                       lambda self, name, _o=common.Context.config: dict(_o(self, name), endings=prof)
                                       if name == "profile.json" else _o(self, name)):
                    wj = fx("words_ar.json")
                    ws = cp.clean_words(wj["words"])
                    prot, _ = cp._protections(p, ws, [cp.norm_word(w["word"]) for w in ws], "ar", ctx, 22000)
                    ms = cp._ms(marker) if marker else None
                    got = N().sign_off_span(wj["words"], N().config(prof, {}), ms, 22000)
                self.assertEqual(prot["after_ms"], got["start_ms"] if got else None, (prof, marker))
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

    def test_g65_phrase_matching(self):
        w = copy.deepcopy(WORDS)
        w[-2]["word"], w[-1]["word"] = "يَـلّا", "سَلام"                    # harakat, tatweel
        s = N().sign_off_span(w, N().config(END_ALL, {}), None, 22000)
        self.assertEqual(s["source"], "phrase")
        en = [{"id": 1, "word": "See", "start_ms": 9000, "end_ms": 9300}, {"id": 2, "word": "YOU", "start_ms": 9350, "end_ms": 9600},
              {"id": 3, "word": "see", "start_ms": 10000, "end_ms": 10300}, {"id": 4, "word": "you", "start_ms": 10350, "end_ms": 10600}]
        cfg = N().config({"sign_off": {"on": True, "phrase": "see you"}}, {})
        self.assertEqual(N().sign_off_span(en, cfg, None, 11000)["start_ms"], 10000)      # said twice: the last one
        early = [{"id": 1, "word": "see", "start_ms": 1000, "end_ms": 1300}, {"id": 2, "word": "you", "start_ms": 1350, "end_ms": 1600},
                 {"id": 3, "word": "ok", "start_ms": 29000, "end_ms": 29300}]
        s = N().sign_off_span(early, cfg, None, 30000)
        self.assertEqual(s["source"], "fallback")                                             # only before the last 20 s
        digits = [{"id": 1, "word": "٣", "start_ms": 9000, "end_ms": 9300}, {"id": 2, "word": "سلام", "start_ms": 9350, "end_ms": 9600}]
        cfg = N().config({"sign_off": {"on": True, "phrase": "3 سلام"}}, {})
        self.assertEqual(N().sign_off_span(digits, cfg, None, 10000)["start_ms"], 9000)

    def test_g66_off_and_empty(self):
        self.assertIsNone(N().sign_off_span(WORDS, N().config({"sign_off": {"on": False, "phrase": "يلا سلام"}}, {}), None, 22000))
        s = N().sign_off_span(WORDS, N().config({"sign_off": {"on": True, "phrase": "  "}}, {}), None, 22000)
        self.assertEqual((s["start_ms"], s["source"]), (14000, "fallback"))
        self.assertIsNotNone(s["note"])


class TestOrder(unittest.TestCase):
    def test_g67_right_order_passes_every_other_is_refused(self):
        import itertools
        span = (20320, 22000)
        slots = [(15000, 17000), (17000, 19000)]
        parts = {"cta": None, "follow": None}
        good = [ev("GFX_C", 15000, 17000, role="cta"), ev("GFX_F", 17000, 19000, role="follow")]
        e, _ = errs(good, span)
        self.assertEqual(e, [])
        # the sign-off is the third part: a card after it is over or after the span
        n_bad = 0
        for order in itertools.permutations(["cta", "follow", "sign_off"]):
            if order == ("cta", "follow", "sign_off"):
                continue
            pos = {p: i for i, p in enumerate(order)}
            if pos["sign_off"] == 2:                         # only the two cards swapped
                evs = [ev("GFX_C", *slots[pos["cta"]], role="cta"), ev("GFX_F", *slots[pos["follow"]], role="follow")]
            else:                                            # a card after the sign-off starts
                after = [(20500, 21000), (21000, 21600)]
                cards = [p for p in order if p != "sign_off"]
                before = cards[:pos["sign_off"]]
                after_c = cards[pos["sign_off"]:]
                times = dict(zip(before, slots[-len(before):] if before else []))
                times.update(dict(zip(after_c, after)))
                evs = [ev("GFX_C", *times["cta"], role="cta"), ev("GFX_F", *times["follow"], role="follow")]
            e, _ = errs(evs, span)
            self.assertTrue(e, order)
            n_bad += 1
        self.assertEqual(n_bad, 5)
        self.assertTrue(parts is not None)

    def test_g67_overlapping_cta_and_follow_are_refused(self):
        e, _ = errs([ev("GFX_C", 15000, 17500, role="cta"), ev("GFX_F", 17000, 19000, role="follow")])
        self.assertTrue(any("wrong order" in x for x in e), e)
        e, _ = errs([ev("GFX_C", 15000, 17000, role="cta"), ev("GFX_F", 17000, 19000, role="follow")])
        self.assertEqual(e, [])                                          # touching is fine

    def test_g68_only_the_parts_switched_on(self):
        cta_off = N().config(fx("profile_endings_cta_off.json")["endings"], {})
        e, w = errs([ev("GFX_F", 17000, 19000, role="follow")], cfg=cta_off)
        self.assertEqual(e, [])
        follow_off = N().config(fx("profile_endings_follow_off.json")["endings"], {})
        e, w = errs([ev("GFX_C", 15000, 17000, role="cta")], cfg=follow_off)
        self.assertEqual(e, [])
        both = N().config(END_ALL, {"cta": {"on": False}, "follow": {"on": False}})
        e, w = errs([], cfg=both)
        self.assertEqual(e, [])
        e, w = errs([ev("GFX_C", 15000, 17000, role="cta")], cfg=cta_off)
        self.assertEqual(e, [])
        self.assertTrue(any("الجزء ده مقفول في البروفايل" in x for x in w), w)

    def test_g69_nothing_over_the_sign_off(self):
        for t in ("cta", "name_card", "logo_outro", "broll_card", "hook_title", "statement_highlight", "flash_transition"):
            e, _ = errs([ev("GFX_9", 20000, 20800, template=t)], (20320, 22000))
            self.assertTrue(any("حرّك GFX_9 قبل 00:20.32 أو قصّره" in x for x in e), (t, e))

    def test_g70_captions_stay_but_no_hide_window_starts_inside(self):
        e, _ = errs([], (20320, 22000), hidden=[(20500, 21000)])
        self.assertTrue(e)
        e, _ = errs([], (20320, 22000), hidden=[(15000, 16000)])
        self.assertEqual(e, [])
        for a in (20320, 21500):                                         # at the span start, in its last second
            e, _ = errs([], (20320, 22000), hidden=[(a, a + 300)])
            self.assertTrue(e, a)

    def test_g71_cards_that_do_not_fit_name_the_free_slot_and_the_length(self):
        e, _ = errs([ev("GFX_C", 18500, 19600, role="cta"), ev("GFX_F", 19600, 20320, role="follow")], (20320, 22000))
        self.assertTrue(e)
        txt = " ".join(e)
        self.assertIn("endings.follow.on: false", txt)
        self.assertIn("1.5", txt)                                   # the length the follow card needs
        self.assertIn("00:19.60", txt)                              # the free slot: 19.60 -> 20.32
        self.assertIn("00:20.32", txt)
        e, _ = errs([ev("GFX_C", 15000, 15800, role="cta")], (20320, 22000))
        self.assertTrue(any("1.2" in x for x in e), e)

    def test_g72_sequence_clock(self):
        """A card that ends before the sign-off in source time can overlap it once a pause before the sign-off is
        removed: plan_check maps the span with the time map and refuses."""
        from lib.plan import PlanInputs
        from lib.timemap import TimeMap
        with common.use_context(common.Context()):
            tm = TimeMap([[0, 19500], [20300, 22000]])
            seq_span = round(tm.ms(20320))
            card = ev("GFX_F", round(tm.ms(18000)), round(tm.ms(19500)) + 40, role="follow")
            inp = PlanInputs(words=WORDS, profile={"endings": END_ALL}, base={}, dur_ms=22000, lang="ar", ctx=None)
            errors, _w, info = N().plan_check(inp, {"tmap": tm, "events": [card]}, {})
        self.assertLess(seq_span, 20320)
        self.assertTrue(errors)
        self.assertEqual(info["span"]["start_ms"], seq_span)

    def test_g73_handle_fit_or_fail(self):
        measure = lambda text, px: len(text) * px * 0.55               # noqa: E731
        ok = N().fit_handle("@dr.example", measure, 900, 60, 32)
        self.assertEqual((ok["ok"], ok["size_px"], ok["text"]), (True, 60, "@dr.example"))
        shrunk = N().fit_handle("@" + "x" * 30, measure, 900, 60, 32)
        self.assertTrue(shrunk["ok"])
        self.assertLess(shrunk["size_px"], 60)
        self.assertGreaterEqual(shrunk["size_px"], 32)
        self.assertEqual(shrunk["text"], "@" + "x" * 30)                # never truncated or ellipsised
        long_ = fx("profile_endings_long_handle.json")["endings"]["follow"]["handle"]
        bad = N().fit_handle(long_, measure, 900, 60, 32)
        self.assertFalse(bad["ok"])
        e, _ = errs([ev("GFX_C", 15000, 17000, role="cta"), ev("GFX_F", 17000, 19000, role="follow")],
                    cfg=N().config(fx("profile_endings_long_handle.json")["endings"], {}), handle_fit=bad)
        self.assertTrue(any("الهاندل أطول من المساحة: اختصر الاسم أو شيل كارت المتابعة" in x for x in e))
        self.assertEqual(N().DEFAULTS["label_floor_px"], 32)

    def test_g74_cta_wording_from_the_client_voice(self):
        cfg = N().config(END_ALL, {})
        self.assertEqual(N().cta_keyword(cfg, "ar")[0], "رجيم")
        self.assertEqual(N().cta_keyword(cfg, "en")[0], "DIET")
        no_en = N().config(dict(END_ALL, cta={"on": True, "keyword_ar": "رجيم"}), {})
        kw, note = N().cta_keyword(no_en, "en")
        self.assertIsNone(kw)
        self.assertIn("CTA", note["en"])

    def test_g75_music_ducking_inside_the_span_is_a_warning(self):
        e, w = errs([], (20320, 22000), music_cues=[{"label": "duck", "at_ms": 21000}])
        self.assertEqual(e, [])
        self.assertTrue(any("duck" in x for x in w), w)

    def test_g76_no_new_error_for_a_card_over_a_cutaway(self):
        e, _ = errs([ev("GFX_C", 25700, 26900, role="cta")], (28000, 33700))
        self.assertEqual(e, [])


class TestEndingStart(unittest.TestCase):
    def test_the_ending_is_the_earliest_card_or_the_span(self):
        span = {"start_ms": 20320, "end_ms": 22000}
        self.assertEqual(N().ending_start(span, [ev("GFX_C", 15840, 17000, role="cta")]), 15840)
        self.assertEqual(N().ending_start(span, [ev("GFX_X", 1000, 2000, template="name_card")]), 20320)
        self.assertIsNone(N().ending_start(None, []))

    def test_roles(self):
        self.assertEqual(N().card_role(ev("A", 0, 1, template="cta")), "cta")
        self.assertEqual(N().card_role(ev("A", 0, 1, template="cta", role="follow")), "follow")
        self.assertIsNone(N().card_role(ev("A", 0, 1, template="logo_outro")))


if __name__ == "__main__":
    unittest.main()
